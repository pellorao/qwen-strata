"""Output-limit retry: a streamed Responses or Messages answer that runs out of its output limit is generated once
more inside the frontend, with a notice to the model, so the caller never sees the cut-off answer.

Why: Codex ends its turn on `response.incomplete` (reason max_output_tokens) and never tells the model why, so a model
that tried to write a long file in one call stops dead.  The fix is generic: the only signal is the protocol's own
"output limit reached" (Responses `response.incomplete` with reason max_output_tokens, Messages `stop_reason`
max_tokens); no tool name, prompt text or client is looked at.

How the stream stays hidden: frames go to the caller as they arrive, except the frames that finish an item
(Responses `*.done` events up to `response.output_item.done`; Messages `content_block_stop`).  Those are held only
until the next frame, which in Strata's streams follows at once, so a client sees the same bytes in the same order
with no added delay.  When the answer ends at the limit, the held frames of the cut-off item and the terminal event
are dropped: the caller has seen that item start and grow (progress only) but never complete, so it never enters the
caller's history or reaches a tool.  The frontend then asks the engine again: the same request, the items that did
complete, and NOTICE as a user message, which goes only to the engine (as loop_reminder does).  The retry's events
follow on the same stream, renumbered as part of the first response.

No retry when an action item (anything but reasoning, text or thinking) already completed in the answer: the caller
may already be running it.  After MAX_RETRIES, or when a retry cannot start, the held frames go out as they came
(the caller sees the limit as before).  Every limit hit is logged with the discarded attempt's usage and seconds; the
engine log has every attempt too, which is where measurement counts tokens.  The usage the caller gets is the last
attempt's, which is the one that matches its context.
"""
import copy
import json
import time

MAX_RETRIES = 1
NOTICE = ('[Output limit: automatic notice from the model service, not from the user]\n'
          'Your previous response reached the per-response output limit of {limit} tokens (thinking included) and '
          'was cut off while writing {what}. The cut-off part was discarded and was not run or saved. '
          'Continue the task, keeping each response well under the limit: split long output into several smaller '
          'steps.')
RESPONSES, MESSAGES = '/v1/responses', '/v1/messages'
PASSIVE_ITEMS = ('reasoning', 'message')
PASSIVE_BLOCKS = ('text', 'thinking', 'redacted_thinking')


def wanted(path, body):
    """A streamed generation request this guard handles."""
    return path in (RESPONSES, MESSAGES) and body.get('stream') is True


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


def encode(kind, data):
    return f'event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n'.encode()


class Stream:
    """Shared state of one caller stream across its attempts."""

    def __init__(self, path, body):
        self.path, self.body = path, body
        self.limit = body.get('max_output_tokens' if path == RESPONSES else 'max_tokens')
        self.done = []          # completed passive items (Responses) or blocks (Messages) the caller has, in order
        self.acted = False      # an action item completed: no retry
        self.attempt = 0        # 0 = the caller's own request; then retries
        self.held = []          # frames waiting for the next frame
        self.limited = False    # this attempt ended at the output limit
        self.cut = None         # what was being written when it did
        self.usage = None       # this attempt's usage, for the log

    def flush(self):
        out, self.held = b''.join(self.held), []
        return out

    def notice(self):
        return NOTICE.format(limit=self.limit, what=self.cut or 'its answer')


class ResponsesStream(Stream):
    def __init__(self, path, body):
        super().__init__(path, body)
        self.events = 0           # events sent or dropped in all attempts: the next sequence number
        self.items = 0            # output items announced in all attempts: the next output index
        self.offset = 0           # output-index shift of this attempt
        self.base = []            # completed items of earlier attempts, ahead of this attempt's output
        self.opening = False      # a retry's response.created / first response.in_progress are still to come
        self.response_id = None
        self.pending_item = None  # an item that ended incomplete; its output_item.done is held

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
            frame = encode(kind, data)
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
                self.cut = describe_item(self.pending_item)
                self.held.append(frame)
                return b''
        self.pending_item = None
        return self.flush() + frame

    def retry_body(self):
        body = copy.deepcopy(self.body)
        items = body.get('input')
        if isinstance(items, str):
            items = [{'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': items}]}]
        body['input'] = list(items or []) + copy.deepcopy(self.done) + [
            {'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': self.notice()}]}]
        return body

    def next_attempt(self):
        self.attempt += 1
        self.offset, self.base, self.opening = self.items, copy.deepcopy(self.done), True
        self.held, self.limited, self.cut, self.usage, self.pending_item = [], False, None, None, None


def describe_item(item):
    if not item:
        return None
    kind = item.get('type')
    if kind == 'reasoning':
        return 'its reasoning'
    if kind == 'message':
        return 'a message'
    name = item.get('name')
    return f'a tool call ({name})' if name else f'a {kind} item'


class MessagesStream(Stream):
    def __init__(self, path, body):
        super().__init__(path, body)
        self.blocks = {}         # index -> block being built in this attempt
        self.offset = 0          # content-block index shift of this attempt
        self.next_index = 0      # first free index across attempts
        self.held_index = None   # the block whose content_block_stop is held

    def feed(self, frame):
        kind, raw = parse(frame)
        if raw is None:
            if self.held:
                self.held.append(frame)
                return b''
            return frame
        data = decode(raw)
        kind = kind or (data or {}).get('type')
        if self.attempt and data is not None:
            if kind == 'message_start':
                return b''
            if isinstance(data.get('index'), int):
                data['index'] += self.offset
            frame = encode(kind, data)
        if self.limited:                   # the rest of the cut-off answer (message_stop)
            self.held.append(frame)
            return b''
        index = (data or {}).get('index')
        if kind == 'message_delta' and ((data or {}).get('delta') or {}).get('stop_reason') == 'max_tokens':
            self.limited = True
            self.usage = (data or {}).get('usage')
            self.cut = describe_block(self.blocks.get(self.held_index)) if self.held_index is not None else None
            self.held.append(frame)
            return b''
        out = self.complete()
        if kind == 'content_block_stop':
            self.held.append(frame)
            self.held_index = index
            return out
        if kind == 'content_block_start':
            self.blocks[index] = dict((data or {}).get('content_block') or {})
            if isinstance(index, int):
                self.next_index = max(self.next_index, index + 1)
        elif kind == 'content_block_delta':
            add_delta(self.blocks.get(index), (data or {}).get('delta') or {})
        return out + frame

    def complete(self):
        """The held content_block_stop is final: the block is the caller's now."""
        if not self.held or self.held_index is None:
            return b''
        block = self.blocks.get(self.held_index) or {}
        self.held_index = None
        if block.get('type') in PASSIVE_BLOCKS:
            self.done.append(finished_block(block))
        else:
            self.acted = True
        return self.flush()

    def retry_body(self):
        body = copy.deepcopy(self.body)
        messages = list(body.get('messages') or [])
        notice = {'type': 'text', 'text': self.notice()}
        if self.done:
            messages += [{'role': 'assistant', 'content': copy.deepcopy(self.done)},
                         {'role': 'user', 'content': [notice]}]
        elif messages and messages[-1].get('role') == 'user':
            last = dict(messages[-1])
            content = last.get('content')
            last['content'] = ([{'type': 'text', 'text': content}] if isinstance(content, str) else list(content or []))
            last['content'].append(notice)
            messages[-1] = last
        else:
            messages.append({'role': 'user', 'content': [notice]})
        body['messages'] = messages
        return body

    def next_attempt(self):
        cut = self.held_index if self.limited else None
        self.attempt += 1
        # the retry's blocks take the cut-off block's place, so the caller's open block is the one that continues
        self.offset = cut if cut is not None else self.next_index
        self.blocks, self.held, self.limited, self.cut, self.usage, self.held_index = {}, [], False, None, None, None


def add_delta(block, delta):
    if block is None:
        return
    kind = delta.get('type')
    if kind == 'text_delta':
        block['text'] = (block.get('text') or '') + (delta.get('text') or '')
    elif kind == 'thinking_delta':
        block['thinking'] = (block.get('thinking') or '') + (delta.get('thinking') or '')
    elif kind == 'signature_delta':
        block['signature'] = (block.get('signature') or '') + (delta.get('signature') or '')


def finished_block(block):
    if block.get('type') == 'thinking':
        return {'type': 'thinking', 'thinking': block.get('thinking') or '', 'signature': block.get('signature') or ''}
    if block.get('type') == 'text':
        return {'type': 'text', 'text': block.get('text') or ''}
    return dict(block)


def describe_block(block):
    if not block:
        return None
    kind = block.get('type')
    if kind in ('thinking', 'redacted_thinking'):
        return 'its reasoning'
    if kind == 'text':
        return 'a message'
    name = block.get('name')
    return f'a tool call ({name})' if name else f'a {kind} block'


def relay(path, body, reply, write, open_upstream, log):
    """Stream `reply` to `write`, retrying inside when it ends at the output limit (see the module doc).
    `open_upstream(body)` returns (connection, reply) for a retry; `log(text)` notes every limit hit."""
    stream = (ResponsesStream if path == RESPONSES else MessagesStream)(path, body)
    connection, started = None, time.monotonic()
    try:
        while True:
            for frame in frames(reply):
                out = stream.feed(frame)
                if out:
                    write(out)
            if not stream.limited:
                write(stream.flush())
                return
            seconds = time.monotonic() - started
            retry = stream.attempt < MAX_RETRIES and not stream.acted
            log(f'output limit: {path} attempt {stream.attempt + 1} reached {stream.limit} tokens while writing '
                f'{stream.cut or "its answer"} after {seconds:.1f} s, usage {json.dumps(stream.usage)}; '
                + ('discarded, retrying with the notice' if retry else
                   'returned as is (' + ('an action item already completed' if stream.acted else 'no retries left')
                   + ')'))
            if not retry:
                write(stream.flush())
                return
            try:
                if connection is not None:
                    connection.close()
                connection, reply = open_upstream(stream.retry_body())
                if reply.status != 200:
                    raise OSError(f'HTTP {reply.status}')
            except OSError as error:
                log(f'output limit: {path} retry could not start ({error}); the cut-off answer is returned')
                write(stream.flush())
                return
            stream.next_attempt()
            started = time.monotonic()
    finally:
        if connection is not None:
            connection.close()
