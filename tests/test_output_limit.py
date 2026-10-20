"""Output-limit retry in the frontend (Responses only).  The fixtures are streams written by Strata v0.1.45's own
builders (serve.responses.Assembler, serve.server.anthropic_events) and serialized as its server writes them."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import output_limit

FIXTURES = Path(__file__).resolve().parent / 'fixtures/output_limit'
UNCHANGED = ('responses-text', 'responses-calls', 'responses-unfinished-stop', 'responses-limit-after-call',
             'responses-keepalive', 'responses-failed')
BODY = {'model': 'm', 'stream': True, 'max_output_tokens': 8192,
        'input': [{'type': 'message', 'role': 'user', 'content': 'write the report'}]}


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
    def close(self):
        pass


def events(raw):
    out = []
    for frame in raw.split(b'\n\n'):
        kind, data = output_limit.parse(frame + b'\n\n')
        if data is not None:
            out.append((kind, json.loads(data)))
    return out


def run(first, retries=(), size=65536, body=BODY):
    written, asked, logged = [], [], []
    replies = iter(retries)

    def open_upstream(retry):
        asked.append(retry)
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return Connection(), reply

    output_limit.relay(body, Reply(first, size), written.append, open_upstream, logged.append)
    return b''.join(written), asked, logged


class UnchangedTests(unittest.TestCase):
    def test_streams_that_need_no_retry_pass_byte_for_byte_in_any_chunking(self):
        for name in UNCHANGED:
            raw = fixture(name)
            for size in (1, 7, 64, 65536):
                with self.subTest(name=name, size=size):
                    out, asked, _ = run(raw, size=size)
                    self.assertEqual(out, raw)
                    self.assertEqual(asked, [])

    def test_keepalives_and_failure_events_pass_as_they_come(self):
        kinds = [k for k, _ in events(fixture('responses-keepalive'))]
        self.assertGreater(kinds.count('response.in_progress'), 2)       # mid-stream keep-alives are in the fixture
        self.assertEqual(events(fixture('responses-failed'))[-1][0], 'response.failed')

    def test_only_item_finishing_frames_wait_and_only_for_the_next_frame(self):
        for name in (n for n in UNCHANGED if 'limit' not in n):
            raw = fixture(name)
            stream = output_limit.Stream(BODY)
            sent, frames = b'', list(output_limit.frames(Reply(raw)))
            for at, frame in enumerate(frames):
                sent += stream.feed(frame)
                seen = b''.join(frames[:at + 1])
                self.assertTrue(seen.startswith(sent))
                for waiting in seen[len(sent):].split(b'\n\n')[:-1]:
                    kind, _ = output_limit.parse(waiting + b'\n\n')
                    with self.subTest(name=name, frame=at):
                        self.assertTrue(kind is None or kind.endswith('.done'), kind)
            self.assertEqual(sent + stream.flush(), raw)

    def test_a_retry_that_cannot_start_returns_the_cut_off_answer_as_it_came(self):
        raw = fixture('responses-limit-custom')
        for retry in (OSError('refused'), Reply(b'{"error": 1}', status=503)):
            out, asked, logged = run(raw, [retry])
            self.assertEqual(out, raw)
            self.assertEqual(len(asked), 1)
            self.assertIn('could not start', logged[-1])

    def test_a_retry_body_that_cannot_be_built_counts_as_a_retry_that_cannot_start(self):
        raw = fixture('responses-limit-custom')
        out, asked, logged = run(raw, body=dict(BODY, input=5))
        self.assertEqual((out, asked), (raw, []))
        self.assertIn('could not start (TypeError', logged[-1])

    def test_an_unexpected_error_releases_the_held_frames_and_ends(self):
        raw = fixture('responses-calls')
        cut = raw.index(b'event: response.output_item.done')    # first item-finishing frames are held here
        written, logged = [], []

        class Broken(Reply):
            def read1(self, size):
                if self.at >= cut + 10:
                    raise ValueError('bad chunk')
                return super().read1(min(size, cut + 10 - self.at))

        output_limit.relay(BODY, Broken(raw), written.append, None, logged.append)
        self.assertEqual(b''.join(written), raw[:raw.rindex(b'\n\n', 0, cut + 10) + 2])
        self.assertIn('relay failed (ValueError: bad chunk)', logged[-1])

    def test_a_caller_that_left_is_not_written_to_again(self):
        def gone(raw):
            raise BrokenPipeError()
        with self.assertRaises(OSError):
            output_limit.relay(BODY, Reply(fixture('responses-text')), gone, None, lambda text: None)

    def test_only_streamed_responses_are_guarded(self):
        self.assertTrue(output_limit.wanted('/v1/responses', {'stream': True}))
        self.assertFalse(output_limit.wanted('/v1/responses', {}))
        self.assertFalse(output_limit.wanted('/v1/messages', {'stream': True}))
        self.assertFalse(output_limit.wanted('/v1/chat/completions', {'stream': True}))

    def test_notice_text_is_pinned_and_names_no_number(self):
        self.assertEqual(hashlib.sha256(output_limit.NOTICE.encode()).hexdigest(), '82ab19ed6f2d5f698b8d491a3ce825703236c1da7b57ba30f7e2d10e7af40d31')
        self.assertNotIn('{limit}', output_limit.NOTICE)


class RetryTests(unittest.TestCase):
    def test_cut_off_call_is_hidden_and_the_retry_continues_the_same_response(self):
        out, asked, logged = run(fixture('responses-limit-custom'), [Reply(fixture('responses-retry-ok'))])
        sent = events(out)
        kinds = [k for k, _ in sent]
        self.assertNotIn('response.incomplete', kinds)
        self.assertEqual(kinds.count('response.created'), 1)
        self.assertEqual(kinds[-1], 'response.completed')
        done = [d['item'] for k, d in sent if k == 'response.output_item.done']
        self.assertEqual([(i['type'], i['status']) for i in done],
                         [('reasoning', 'completed'), ('reasoning', 'completed'), ('custom_tool_call', 'completed')])
        self.assertEqual(done[-1]['call_id'], 'call_r1')
        numbers = [d['sequence_number'] for _, d in sent]
        self.assertEqual(numbers, sorted(set(numbers)))
        self.assertEqual([d['output_index'] for k, d in sent if k == 'response.output_item.added'], [0, 1, 2, 3])
        final = sent[-1][1]['response']
        self.assertEqual(final['id'], 'resp_limit_custom')
        self.assertEqual([i['type'] for i in final['output']], ['reasoning', 'reasoning', 'custom_tool_call'])
        self.assertEqual(final['usage']['output_tokens'], 300)          # the attempt the caller keeps
        retry = asked[0]
        self.assertEqual(retry['input'][:1], BODY['input'])
        self.assertEqual(retry['input'][1]['type'], 'reasoning')
        notice = retry['input'][-1]
        self.assertEqual((notice['type'], notice['role']), ('message', 'user'))
        self.assertEqual(notice['content'][0]['text'], output_limit.NOTICE.format(what='a tool call (apply_patch)'))
        self.assertEqual(BODY['input'], [{'type': 'message', 'role': 'user', 'content': 'write the report'}])
        self.assertIn('max_output_tokens 8192', logged[0])
        self.assertIn('"output_tokens": 8192', logged[0])
        self.assertIn('retrying', logged[0])

    def test_a_retry_that_is_cut_off_again_is_returned_as_the_limit(self):
        out, asked, logged = run(fixture('responses-limit-function'), [Reply(fixture('responses-limit-reasoning'))])
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
        out, asked, logged = run(raw)
        self.assertEqual((out, asked), (raw, []))
        self.assertIn('an action item already completed', logged[0])

    def test_a_string_input_becomes_a_user_message_ahead_of_the_notice(self):
        stream = output_limit.Stream(dict(BODY, input='hi'))
        stream.cut = 'its answer'
        self.assertEqual([i['role'] for i in stream.retry_body()['input']], ['user', 'user'])


if __name__ == '__main__':
    unittest.main()
