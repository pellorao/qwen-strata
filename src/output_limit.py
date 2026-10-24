"""Output-limit retry: a streamed Responses answer that runs out of its output limit is generated once more inside
the frontend, with a notice to the model, so the caller never sees the cut-off answer.

Why: Codex ends its turn on `response.incomplete` (reason max_output_tokens) and never tells the model why, so a model
that tried to write a long file in one call stops dead.  The fix is generic: the only signal is the protocol's own
"output limit reached" (`response.incomplete` with reason max_output_tokens); no tool name, prompt text or client is
looked at.  Messages (Claude Code) is left alone: Claude Code already hands a cut-off tool call back to the model as a
failed call and goes on, and a retry there would have to reopen a content-block index, which the Anthropic stream
does not allow.

How the stream stays hidden: frames go to the caller as they arrive, except the frames that finish an item
(`response.*.done` events up to `response.output_item.done`).  Those are held only until the next frame, which in
Strata's streams follows at once, so a client sees the same bytes in the same order with no added delay.  When the
answer ends at the limit, the held frames of the cut-off item and the terminal event are dropped: the caller has seen
that item start and grow (progress only) but never complete, so it never enters the caller's history or reaches a
tool.  The frontend then asks the engine again: the same request, the items that did complete, and NOTICE as a user
message, which goes only to the engine (as loop_reminder does).  The retry's events follow on the same stream,
renumbered as part of the first response.

The retry also gets more room when the limit is the frontend's own default (the caller set none): max_output_tokens
doubles, up to RETRY_LIMIT_CAP, and the thinking budget stays, so all the added room goes to the answer.  Why: a notice
alone did not help (strata-codex CStd low-a9, 2026-10-22): the thinking ran to its budget in both attempts and, under
greedy decoding, the retry again put the whole output into one tool call, which could not fit in the room left for
the answer.  A lower limit would only cut sooner, since the model never sees the number.  A limit the caller set is
kept: the retry then carries the notice only.

No retry when an action item (anything but reasoning or a message) already completed in the answer: the caller may
already be running it.  After MAX_RETRIES, when a retry cannot start, or on any unexpected error, the held frames go
out as they came (the caller sees the limit as before).  Every limit hit is logged with the limit, the discarded
attempt's usage and seconds; the engine log has every attempt too, which is where measurement counts tokens.  The
usage the caller gets is the last attempt's, which is the one that matches its context.
"""
import copy
import json
import time

MAX_RETRIES = 1
RETRY_LIMIT_FACTOR = 2     # a retry may write this many times the limit the frontend itself set (see the module doc)
RETRY_LIMIT_CAP = 24576    # ... but no more than the largest total the service presets (high effort)
PATH = '/v1/responses'
NOTICE = ('[Output limit: automatic notice from the model service, not from the user]\n'
          'Your previous response reached the output limit and was cut off while writing {what}; the cut-off part '
          'was discarded and was not run or saved. Respond to the last request again. {room} shorten it, or if the '
          'output must be long, split it into several smaller steps (for example several smaller tool calls) '
          'instead of repeating the same single long one.')
ROOM_RAISED = 'This response has more room than the previous one, but keep it as short as you can:'
ROOM_SAME = 'Keep this response well under the limit:'
PASSIVE_ITEMS = ('reasoning', 'message')


def wanted(path, body):
    """A streamed Responses request this guard handles."""
    return path == PATH and body.get('stream') is True


def frames(reply):
    """Complete SSE frames (each ending in a blank line) as raw bytes; a trailing partial frame comes last as is."""
    pending = b''
    while chunk := reply.read1(65536):
        pending += chunk
        end = pending.rfind(b'\n\n')
        if end < 0:
            continue
        whole, pending = pending[:end + 2], pending[end + 2:]
        start = 0
        while (cut := whole.find(b'\n\n', start)) >= 0:
            yield whole[start:cut + 2]
            start = cut + 2
    if pending:
        yield pending


def parse(frame):
    """(event name or None, raw data line or None); the data is decoded only where it is needed."""
    kind, raw = None, None
    for line in frame.split(b'\n'):
        if line.startswith(b'event:'):
            kind = line[6:].strip().decode()
        elif line.startswith(b'data:'):
            raw = line[5:]
    return kind, raw


def decode(raw):
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def describe(item):
    if not item:
        return 'its answer'
    kind = item.get('type')
    if kind == 'reasoning':
        return 'its reasoning'
    if kind == 'message':
        return 'a message'
    name = item.get('name')
    return f'a tool call ({name})' if name else f'a {kind} item'


class Stream:
    """One caller stream across its attempts."""

    def __init__(self, body, own_limit=False):
        self.body = body
        self.limit = body.get('max_output_tokens')  # of the current attempt
        self.own_limit = own_limit  # the limit is the frontend's default, not the caller's: a retry may raise it
        self.done = []            # completed passive items the caller has, in order
        self.acted = False        # an action item completed: no retry
        self.attempt = 0          # 0 = the caller's own request; then retries
        self.held = []            # frames waiting for the next frame
        self.limited = False      # this attempt ended at the output limit
        self.cut = None           # the item being written when it did
        self.usage = None         # this attempt's usage, for the log
        self.events = 0           # events sent or dropped in all attempts: the next sequence number
        self.items = 0            # output items announced in all attempts: the next output index
        self.offset = 0           # output-index shift of this attempt
        self.base = []            # completed items of earlier attempts, ahead of this attempt's output
        self.opening = False      # a retry's response.created / first response.in_progress are still to come
        self.response_id = None
        self.pending_item = None  # an item that ended incomplete; its output_item.done is held

    def flush(self):
        out, self.held = b''.join(self.held), []
        return out

    def feed(self, frame):
        kind, raw = parse(frame)
        if raw is None:               # a comment or keep-alive
            if self.held:
                self.held.append(frame)
                return b''
            return frame
        data = None
        if kind is None or self.attempt:
            data = decode(raw)
            kind = kind or (data or {}).get('type')
        if self.attempt and data is not None:
            if self.opening and kind in ('response.created', 'response.in_progress'):
                self.opening = kind == 'response.created'
                return b''
            self.opening = False
            data['sequence_number'] = self.events
            if isinstance(data.get('output_index'), int):
                data['output_index'] += self.offset
            if isinstance(data.get('response'), dict):
                data['response'] = dict(data['response'], id=self.response_id,
                                        output=copy.deepcopy(self.base) + list(data['response'].get('output') or []))
            frame = f'event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n'.encode()
        self.events += 1
        if kind == 'response.created' and not self.attempt:
            data = data or decode(raw)
            self.response_id = ((data or {}).get('response') or {}).get('id')
        elif kind == 'response.output_item.added':
            self.items += 1
        elif kind == 'response.output_item.done':
            data = data or decode(raw)
            item = (data or {}).get('item') or {}
            if item.get('status') == 'incomplete':
                self.held.append(frame)
                self.pending_item = item
                return b''
            self.pending_item = None
            if item.get('type') in PASSIVE_ITEMS:
                self.done.append(item)
            else:
                self.acted = True
            return self.flush() + frame
        elif kind and kind.startswith('response.') and kind.endswith('.done') and self.pending_item is None:
            self.held.append(frame)   # finishes an item whose output_item.done comes next
            return b''
        elif kind == 'response.incomplete':
            data = data or decode(raw)
            response = (data or {}).get('response') or {}
            if (response.get('incomplete_details') or {}).get('reason') == 'max_output_tokens':
                self.limited = True
                self.usage = response.get('usage')
                self.cut = describe(self.pending_item)
                self.held.append(frame)
                return b''
        self.pending_item = None
        return self.flush() + frame

    def retry_body(self):
        body = copy.deepcopy(self.body)
        items = body.get('input')
        if isinstance(items, str):
            items = [{'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': items}]}]
        limit = self.retry_limit()
        notice = NOTICE.format(what=self.cut, room=ROOM_RAISED if limit != self.limit else ROOM_SAME)
        body['input'] = list(items or []) + copy.deepcopy(self.done) + [
            {'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': notice}]}]
        if limit is not None:
            body['max_output_tokens'] = limit
        return body

    def retry_limit(self):
        """The retry's output limit: raised only when the frontend set the limit; the thinking budget stays."""
        if self.own_limit and isinstance(self.limit, int) and not isinstance(self.limit, bool):
            return max(self.limit, min(self.limit * RETRY_LIMIT_FACTOR, RETRY_LIMIT_CAP))
        return self.limit

    def next_attempt(self):
        self.attempt += 1
        self.limit = self.retry_limit()   # the limit this attempt runs under, for its log line
        self.offset, self.base, self.opening = self.items, copy.deepcopy(self.done), True
        self.held, self.limited, self.cut, self.usage, self.pending_item = [], False, None, None, None


def relay(body, reply, write, open_upstream, log, own_limit=False):
    """Stream `reply` to `write`, retrying inside when it ends at the output limit (see the module doc).
    `open_upstream(body)` returns (connection, reply) for a retry; `log(text)` notes every limit hit; `own_limit`
    says the frontend, not the caller, set the request's max_output_tokens."""
    stream, connection, started = Stream(body, own_limit), None, time.monotonic()
    try:
        while True:
            for frame in frames(reply):
                out = stream.feed(frame)
                if out:
                    write(out)
            if not stream.limited:
                write(stream.flush())
                return
            retry = stream.attempt < MAX_RETRIES and not stream.acted
            log(f'output limit: {PATH} attempt {stream.attempt + 1} reached max_output_tokens {stream.limit} while '
                f'writing {stream.cut} after {time.monotonic() - started:.1f} s, usage {json.dumps(stream.usage)}; '
                + (f'discarded, retrying with the notice and max_output_tokens {stream.retry_limit()} '
                   f'(limit set by the {"frontend" if stream.own_limit else "caller"})' if retry else
                   'returned as is (' + ('an action item already completed' if stream.acted else 'no retries left')
                   + ')'))
            if not retry:
                write(stream.flush())
                return
            try:
                retry_body = stream.retry_body()
                if connection is not None:
                    connection.close()
                connection, reply = open_upstream(retry_body)
                if reply.status != 200:
                    raise RuntimeError(f'HTTP {reply.status}')
            except Exception as error:
                log(f'output limit: {PATH} retry could not start ({type(error).__name__}: {error}); '
                    'the cut-off answer is returned')
                write(stream.flush())
                return
            stream.next_attempt()
            started = time.monotonic()
    except OSError:
        raise                         # the caller or the engine left: the frontend closes the connection
    except Exception as error:
        log(f'output limit: {PATH} relay failed ({type(error).__name__}: {error}); held frames are returned as is')
        write(stream.flush())
    finally:
        if connection is not None:
            connection.close()
