"""Output-limit retry in the frontend.  The fixtures are streams written by Strata v0.1.45's own builders
(serve.responses.Assembler, serve.server.anthropic_events) and serialized as its server writes them."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import output_limit

FIXTURES = Path(__file__).resolve().parent / 'fixtures/output_limit'
UNCHANGED = ('responses-text', 'responses-calls', 'responses-unfinished-stop', 'responses-limit-after-call',
             'messages-text', 'messages-tool', 'messages-limit-after-tool')


def fixture(name):
    return (FIXTURES / f'{name}.sse').read_bytes()


class Reply:
    def __init__(self, raw, size=65536, status=200):
        self.raw, self.size, self.status, self.at = raw, size, status, 0

    def read1(self, size):
        chunk = self.raw[self.at:self.at + min(size, self.size)]
        self.at += len(chunk)
        return chunk


class Connection:
    closed = False

    def close(self):
        self.closed = True


def events(raw):
    out = []
    for frame in raw.split(b'\n\n'):
        kind, data = output_limit.parse(frame + b'\n\n')
        if data is not None:
            out.append((kind, json.loads(data)))
    return out


def run(path, body, first, retries=(), size=65536):
    written, asked, logged = [], [], []
    replies = iter(retries)

    def open_upstream(retry):
        asked.append(retry)
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return Connection(), reply

    output_limit.relay(path, body, Reply(first, size), written.append, open_upstream, logged.append)
    return b''.join(written), asked, logged


RESPONSES_BODY = {'model': 'm', 'stream': True, 'max_output_tokens': 8192,
                  'input': [{'type': 'message', 'role': 'user', 'content': 'write the report'}]}
MESSAGES_BODY = {'model': 'm', 'stream': True, 'max_tokens': 8192,
                 'messages': [{'role': 'user', 'content': 'write the report'}]}


def body_for(name):
    return RESPONSES_BODY if name.startswith('responses') else MESSAGES_BODY


def path_for(name):
    return '/v1/responses' if name.startswith('responses') else '/v1/messages'


class UnchangedTests(unittest.TestCase):
    def test_streams_that_need_no_retry_pass_byte_for_byte_in_any_chunking(self):
        for name in UNCHANGED:
            raw = fixture(name)
            for size in (1, 7, 64, 65536):
                with self.subTest(name=name, size=size):
                    out, asked, _ = run(path_for(name), body_for(name), raw, size=size)
                    self.assertEqual(out, raw)
                    self.assertEqual(asked, [])

    def test_only_item_finishing_frames_wait_and_only_for_the_next_frame(self):
        held_kinds = ('content_block_stop',)
        for name in (n for n in UNCHANGED if 'limit' not in n):
            raw = fixture(name)
            stream = (output_limit.ResponsesStream if name.startswith('responses') else
                      output_limit.MessagesStream)(path_for(name), body_for(name))
            sent, frames = b'', list(output_limit.frames(Reply(raw)))
            for at, frame in enumerate(frames):
                sent += stream.feed(frame)
                pending = b''.join(frames[:at + 1])[len(sent):]
                self.assertTrue(b''.join(frames[:at + 1]).startswith(sent))
                for waiting in pending.split(b'\n\n')[:-1]:
                    kind, _ = output_limit.parse(waiting + b'\n\n')
                    with self.subTest(name=name, frame=at):
                        self.assertTrue(kind is None or kind in held_kinds or kind.endswith('.done')
                                        or kind == 'response.output_item.done', kind)
            self.assertEqual(sent + stream.flush(), raw)

    def test_a_retry_that_cannot_start_returns_the_cut_off_answer_as_it_came(self):
        for name, retry in (('responses-limit-custom', OSError('refused')),
                            ('messages-limit-tool', Reply(b'{"error": 1}', status=503))):
            raw = fixture(name)
            out, asked, logged = run(path_for(name), body_for(name), raw, [retry])
            self.assertEqual(out, raw)
            self.assertEqual(len(asked), 1)
            self.assertIn('could not start', logged[-1])

    def test_only_streamed_responses_and_messages_are_guarded(self):
        self.assertTrue(output_limit.wanted('/v1/responses', {'stream': True}))
        self.assertTrue(output_limit.wanted('/v1/messages', {'stream': True}))
        self.assertFalse(output_limit.wanted('/v1/responses', {}))
        self.assertFalse(output_limit.wanted('/v1/chat/completions', {'stream': True}))
        self.assertFalse(output_limit.wanted('/v1/messages/count_tokens', {'stream': True}))

    def test_notice_text_is_pinned(self):
        self.assertEqual(hashlib.sha256(output_limit.NOTICE.encode()).hexdigest(),
                         '35c411d02af1b3ec98b1edf36bdfd2ec9c3d22f4ff4b2c4805b87cc3ae5b4872')


class ResponsesRetryTests(unittest.TestCase):
    def test_cut_off_call_is_hidden_and_the_retry_continues_the_same_response(self):
        out, asked, logged = run('/v1/responses', RESPONSES_BODY, fixture('responses-limit-custom'),
                                 [Reply(fixture('responses-retry-ok'))])
        sent = events(out)
        kinds = [k for k, _ in sent]
        self.assertNotIn('response.incomplete', kinds)
        self.assertEqual(kinds.count('response.created'), 1)
        self.assertEqual(kinds[-1], 'response.completed')
        done = [d['item'] for k, d in sent if k == 'response.output_item.done']
        self.assertEqual([(i['type'], i['status']) for i in done],
                         [('reasoning', 'completed'), ('reasoning', 'completed'), ('custom_tool_call', 'completed')])
        self.assertEqual(done[-1]['call_id'], 'call_r1')
        self.assertNotIn('call_c1', [i.get('call_id') for i in done])
        numbers = [d['sequence_number'] for _, d in sent]
        self.assertEqual(numbers, sorted(set(numbers)))
        indexes = [d['output_index'] for k, d in sent if k == 'response.output_item.added']
        self.assertEqual(indexes, [0, 1, 2, 3])
        final = sent[-1][1]['response']
        self.assertEqual(final['id'], 'resp_limit_custom')
        self.assertEqual([i['type'] for i in final['output']], ['reasoning', 'reasoning', 'custom_tool_call'])
        self.assertEqual(final['usage']['output_tokens'], 300)          # the attempt the caller keeps
        retry = asked[0]
        self.assertEqual(retry['input'][:1], RESPONSES_BODY['input'])
        self.assertEqual(retry['input'][1]['type'], 'reasoning')
        notice = retry['input'][-1]
        self.assertEqual((notice['type'], notice['role']), ('message', 'user'))
        self.assertEqual(notice['content'][0]['text'],
                         output_limit.NOTICE.format(limit=8192, what='a tool call (apply_patch)'))
        self.assertEqual(RESPONSES_BODY['input'], [{'type': 'message', 'role': 'user', 'content': 'write the report'}])
        self.assertIn('"output_tokens": 8192', logged[0])
        self.assertIn('retrying', logged[0])

    def test_a_retry_that_is_cut_off_again_is_returned_as_the_limit(self):
        out, asked, logged = run('/v1/responses', RESPONSES_BODY, fixture('responses-limit-function'),
                                 [Reply(fixture('responses-limit-reasoning'))])
        self.assertEqual(len(asked), 1)
        sent = events(out)
        self.assertEqual(sent[-1][0], 'response.incomplete')
        self.assertEqual(sent[-1][1]['response']['id'], 'resp_limit_function')
        self.assertIn('no retries left', logged[-1])
        retry = asked[0]
        self.assertEqual([i['type'] for i in retry['input'][1:-1]], ['reasoning', 'message'])
        self.assertIn('a tool call (exec_command)', retry['input'][-1]['content'][0]['text'])

    def test_an_answer_with_a_completed_action_is_not_retried(self):
        raw = fixture('responses-limit-after-call')
        out, asked, logged = run('/v1/responses', RESPONSES_BODY, raw)
        self.assertEqual((out, asked), (raw, []))
        self.assertIn('an action item already completed', logged[0])


class MessagesRetryTests(unittest.TestCase):
    def test_cut_off_tool_use_is_hidden_and_the_retry_takes_its_place(self):
        out, asked, logged = run('/v1/messages', MESSAGES_BODY, fixture('messages-limit-tool'),
                                 [Reply(fixture('messages-retry-ok'))])
        sent = events(out)
        kinds = [k for k, _ in sent]
        self.assertEqual(kinds.count('message_start'), 1)
        self.assertEqual(kinds.count('message_stop'), 1)
        stops = [d['delta']['stop_reason'] for k, d in sent if k == 'message_delta']
        self.assertEqual(stops, ['tool_use'])
        starts = [(d['index'], d['content_block']['type']) for k, d in sent if k == 'content_block_start']
        self.assertEqual(starts, [(0, 'thinking'), (1, 'tool_use'), (1, 'thinking'), (2, 'tool_use')])
        closed = [d['index'] for k, d in sent if k == 'content_block_stop']
        self.assertEqual(closed, [0, 1, 2])         # the cut-off block 1 is never closed before its replacement
        retry = asked[0]
        self.assertEqual(retry['messages'][0], MESSAGES_BODY['messages'][0])
        self.assertEqual(retry['messages'][1], {'role': 'assistant', 'content': [
            {'type': 'thinking', 'thinking': 'write it all', 'signature': ''}]})
        self.assertEqual(retry['messages'][2]['content'][0]['text'],
                         output_limit.NOTICE.format(limit=8192, what='a tool call (Write)'))
        self.assertIn('retrying', logged[0])

    def test_notice_joins_the_last_user_turn_when_nothing_completed(self):
        stream = output_limit.MessagesStream('/v1/messages', MESSAGES_BODY)
        stream.cut = 'a message'
        body = stream.retry_body()
        self.assertEqual(len(body['messages']), 1)
        self.assertEqual(body['messages'][0]['content'][0], {'type': 'text', 'text': 'write the report'})
        self.assertTrue(body['messages'][0]['content'][1]['text'].startswith('[Output limit: automatic notice'))
        self.assertEqual(MESSAGES_BODY['messages'][0]['content'], 'write the report')


if __name__ == '__main__':
    unittest.main()
