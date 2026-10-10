"""Loop reminders: replay the conversation a request carries through the mechanical detector and, when the model's
last step repeats earlier work, append a one-off notice to the request forwarded to the model.

Nothing is kept between requests: the history in each request is the whole state, so a resumed or retried
conversation gets the same decision. The notice goes only into the forwarded request, never into the caller's
history, so it does not pile up in later context. A chain of repeats that was already reminded stays silent until it
recurs AGAIN more times; a new chain is reminded at once. Nothing is refused or interrupted.
"""
from collections import Counter, namedtuple
import json

from loop_detector import Mechanical

ALERT = 0.5            # detector probability that counts as a repeat (the scoring contract's threshold)
AGAIN = 2              # further recurrences of an already reminded chain before it is reminded again
OPT_OUT = 'X-Loop-Reminder'  # request header; "off" disables the reminder for that request

NOTICE = ('[Loop check: automatic notice from the model service, not from the user]\n'
          'Your last step (step {step}) closely repeats {what} {where}. '
          'Check whether the current work is stuck in a loop without progress: compare what this step adds with '
          'what the earlier steps already produced. If nothing new is being learned or delivered, use the results '
          'you already have, change the approach, or report the blocker. If the repetition is deliberate and is '
          'making progress, continue. This notice does not stop or refuse anything.')

Observation = namedtuple('Observation', 'payload')


def _text(content):
    """Plain text of a message content: a string or a list of text-like parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return '\n\n'.join(part.get('text') or part.get('thinking') or '' for part in content
                           if isinstance(part, dict) and part.get('type') in (
                               'text', 'input_text', 'output_text', 'reasoning_text', 'summary_text', 'thinking'))
    return ''


def _arguments(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _output(value):
    return value if isinstance(value, str) else _text(value) or json.dumps(value, ensure_ascii=False)


def steps(path, body):
    """[(step number or None for an input, [payload, ...])] in conversation order; a step is one model response."""
    out, step = [], 0

    def add(kind, records):
        nonlocal step
        if kind == 'model':
            step += 1
            out.append((step, records))
        elif records:
            out.append((None, records))

    if path == '/v1/chat/completions':
        messages = body.get('messages') or []
        outputs = {m.get('tool_call_id'): _output(m.get('content')) for m in messages if m.get('role') == 'tool'}
        for m in messages:
            if m.get('role') == 'assistant':
                records = [{'kind': 'reasoning', 'text': m.get('reasoning_content') or m.get('reasoning') or ''},
                           {'kind': 'assistant', 'text': _text(m.get('content'))}]
                records += [{'kind': 'tool', 'name': (c.get('function') or {}).get('name'),
                             'arguments': _arguments((c.get('function') or {}).get('arguments')),
                             'output': outputs.get(c.get('id'))} for c in m.get('tool_calls') or []]
                add('model', records)
            elif m.get('role') == 'user':
                add('input', [{'kind': 'feedback', 'text': _text(m.get('content'))}])
    elif path == '/v1/responses':
        items = body.get('input')
        if not isinstance(items, list):
            return out
        outputs = {i.get('call_id'): _output(i.get('output')) for i in items
                   if isinstance(i, dict) and i.get('type') in ('function_call_output', 'custom_tool_call_output')}
        current = None
        for item in items:
            if not isinstance(item, dict):
                continue
            kind, role = item.get('type'), item.get('role')
            record = None
            if kind == 'reasoning':
                record = {'kind': 'reasoning', 'text': _text(item.get('content')) or _text(item.get('summary'))}
            elif kind == 'message' and role == 'assistant':
                record = {'kind': 'assistant', 'text': _text(item.get('content'))}
            elif kind in ('function_call', 'custom_tool_call'):
                record = {'kind': 'tool', 'name': item.get('name'),
                          'arguments': _arguments(item.get('arguments', item.get('input'))),
                          'output': outputs.get(item.get('call_id'))}
            if record:
                if current is None:
                    current = []
                    add('model', current)
                current.append(record)
                continue
            current = None     # whatever the model says after an output or input is its next response
            if (kind == 'message' or kind is None) and role == 'user':
                add('input', [{'kind': 'feedback', 'text': _text(item.get('content'))}])
    elif path == '/v1/messages':
        messages = body.get('messages') or []
        outputs = {part.get('tool_use_id'): _output(part.get('content'))
                   for m in messages if m.get('role') == 'user' and isinstance(m.get('content'), list)
                   for part in m['content'] if isinstance(part, dict) and part.get('type') == 'tool_result'}
        for m in messages:
            content = m.get('content')
            parts = content if isinstance(content, list) else [{'type': 'text', 'text': content or ''}]
            parts = [p for p in parts if isinstance(p, dict)]
            if m.get('role') == 'assistant':
                records = []
                for part in parts:
                    if part.get('type') == 'thinking':
                        records.append({'kind': 'reasoning', 'text': part.get('thinking') or ''})
                    elif part.get('type') == 'text':
                        records.append({'kind': 'assistant', 'text': part.get('text') or ''})
                    elif part.get('type') == 'tool_use':
                        records.append({'kind': 'tool', 'name': part.get('name'), 'arguments': part.get('input'),
                                        'output': outputs.get(part.get('id'))})
                add('model', records)
            elif m.get('role') == 'user':  # a turn holding only tool results is not new input
                text = _text([p for p in parts if p.get('type') == 'text'])
                if text:
                    add('input', [{'kind': 'feedback', 'text': text}])
    return out


def decide(conversation):
    """Notice text for the last model step, or None."""
    detector = Mechanical()
    detector.reset(None)
    segment_step, record_step = [], [None]   # step of each stored segment / each record (records count from 1)
    sent, count, notice = {}, Counter(), None

    def origin(root):
        return record_step[detector.tools[root][0]] if isinstance(root, str) else segment_step[root]

    for step, records in conversation:
        roots, kinds = set(), []
        for payload in records:
            p = detector.observe(Observation(payload))
            record_step.append(step)
            segment_step.extend([step] * (len(detector.seen) - len(segment_step)))
            if step is not None and p >= ALERT:
                roots |= detector.roots
                kinds.append(payload['kind'])
        if step is None:     # an input after the step (a user turn, a compaction prompt) closes it
            notice = None
            continue
        fire = False
        for root in roots:
            count[root] += 1
            if root not in sent or count[root] - sent[root] >= AGAIN:
                sent[root], fire = count[root], True
        notice = None
        if fire:
            what = 'the same tool call with the same result' if set(kinds) == {'tool'} else 'reasoning or text'
            first = min((origin(r) for r in roots if origin(r) is not None), default=step)
            where = ('earlier within this same step' if first == step
                     else f'first seen at step {first} of this conversation')
            notice = NOTICE.format(step=step, what=what, where=where)
    return notice


def apply(path, body, headers):
    """Append the notice to the request body when due; return the notice (for the log) or None."""
    if (headers.get(OPT_OUT) or '').lower() == 'off':
        return None
    notice = decide(steps(path, body))
    if not notice:
        return None
    if path == '/v1/chat/completions':
        body['messages'].append({'role': 'user', 'content': notice})
    elif path == '/v1/responses':
        body['input'].append({'type': 'message', 'role': 'user',
                              'content': [{'type': 'input_text', 'text': notice}]})
    else:
        last = body['messages'][-1]
        if last.get('role') == 'user':
            content = last.get('content')
            last['content'] = ([{'type': 'text', 'text': content}] if isinstance(content, str) else list(content))
            last['content'].append({'type': 'text', 'text': notice})
        else:
            body['messages'].append({'role': 'user', 'content': notice})
    return notice
