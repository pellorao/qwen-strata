import json
import tempfile
import unittest
from pathlib import Path

from tools.reviewer.inspect_session import inspect, redact

ROOT = '/home/u/run/ca/1'


def call(n, cmd, workdir=ROOT, name='exec_command'):
    args = {'cmd': cmd} if workdir is None else {'cmd': cmd, 'workdir': workdir}
    return [{'type': 'response_item', 'timestamp': '2026-10-11T00:00:00Z',
             'payload': {'type': 'function_call', 'name': name, 'call_id': f'c{n}',
                         'arguments': json.dumps(args)}},
            {'type': 'response_item', 'payload': {'type': 'function_call_output', 'call_id': f'c{n}',
                                                  'output': 'Process exited with code 0\nOutput:\nok'}}]


def message(role, text):
    return {'type': 'response_item', 'payload': {'type': 'message', 'role': role,
                                                 'content': [{'type': 'input_text', 'text': text}]}}


class InspectSessionTest(unittest.TestCase):
    def run_session(self, *calls, developer='role'):
        events = [{'type': 'session_meta', 'payload': {'id': 't', 'cwd': ROOT, 'base_instructions': 'x'}},
                  message('developer', developer), message('user', 'ARW messageId: m1\n\nhandoff')]
        for i, c in enumerate(calls):
            events += call(i, *c) if isinstance(c, tuple) else call(i, c)
        events.append(message('assistant', '{"status":"ready"}'))
        with tempfile.NamedTemporaryFile('w', suffix='.jsonl', delete=False) as f:
            f.write('\n'.join(json.dumps(e) for e in events))
        try:
            return inspect(f.name)
        finally:
            Path(f.name).unlink()

    def test_confined_calls_are_not_flagged(self):
        r = self.run_session(f'cat {ROOT}/request.json', 'rg -n foo src',
                             'R=reports; cat "$R/x"; node -e "fs.readFileSync(ROOT + \'/reports/a\')"',
                             'printf "%s" "$f" | sort; [ "$(ls)" ] && echo /dev/null',
                             'ls | while read -r g; do echo "$g"; done',
                             "jq -r --arg h x '.[]|select(.p==$h)' request.json")
        self.assertEqual([a['reasons'] for a in r['actions']], [[], [], [], ['unassigned variable: $f'], [], []])
        self.assertEqual(r['startup']['messageId'], 'm1')
        self.assertEqual(r['final'], '{"status":"ready"}')

    def test_escapes_are_flagged(self):
        r = self.run_session('cat /home/u/run/ca/2/request.json', 'cat ../../expected.json',
                             ('ls', '/home/u/run/ca/1x'), 'env | grep ARW', 'cat ~/.codex/auth.json')
        reasons = [' '.join(a['reasons']) for a in r['actions']]
        self.assertIn('outside root', reasons[0])
        self.assertIn('escapes root', reasons[1])
        self.assertIn('workdir outside root', reasons[2])
        self.assertIn('environment/identity query', reasons[3])
        self.assertIn('environment or home path', reasons[4])
        self.assertIn('session/credential material', reasons[4])

    def test_credential_values_are_redacted(self):
        jwt = 'eyJhbGciOiJub25lIn0.eyJleHAiOjQxMDI0NDQ4MDB9.c3ludGhldGlj'
        text = redact(f'Bearer abcdefghijklmnopqrst {{"refresh_token": "rt-123456789"}} sk-abcdefghijklmnopqrstuv {jwt} '
                      'ANTHROPIC_AUTH_TOKEN=abcdefghijk keep')
        for value in (jwt, 'abcdefghijklmnopqrst', 'rt-123456789', 'sk-abcdefghijklmnopqrstuv', 'abcdefghijk'):
            self.assertNotIn(value, text)
        self.assertTrue(text.endswith(' keep'))
        self.assertEqual(redact('cat request.json'), 'cat request.json')

    def test_second_scenario_root_is_allowed(self):
        second = '/home/u/run/ap/1'
        events = [{'type': 'session_meta', 'payload': {'id': 't', 'cwd': ROOT, 'base_instructions': 'x'}},
                  message('developer', 'role'), message('user', 'ARW messageId: m1\n\nhandoff')]
        events += call(0, 'cat docs/a.md', second) + call(1, 'cat ../../x', second)
        with tempfile.NamedTemporaryFile('w', suffix='.jsonl', delete=False) as f:
            f.write('\n'.join(json.dumps(e) for e in events))
        try:
            r = inspect(f.name, allow=[second])
        finally:
            Path(f.name).unlink()
        self.assertEqual(r['actions'][0]['reasons'], [])
        self.assertIn('escapes root', ' '.join(r['actions'][1]['reasons']))

    def test_startup_sha_ignores_date_and_codex_home(self):
        a = self.run_session(developer='date 2026-10-11; skills /x/01-a/run/codex-home/skills/.system')
        b = self.run_session(developer='date 2026-10-12; skills /x/02-b/run/codex-home/skills/.system')
        c = self.run_session(developer='date 2026-10-12; other role')
        self.assertEqual(a['startup']['developer@1'], b['startup']['developer@1'])
        self.assertNotEqual(a['startup']['developer@1'], c['startup']['developer@1'])


if __name__ == '__main__':
    unittest.main()


class InspectClaudeStreamTest(unittest.TestCase):
    """Claude Code stream-json: actions, flags, tool-call counts, work time and API tokens."""
    def stream(self, events):
        folder = tempfile.mkdtemp()
        path = Path(folder) / 'stream.jsonl'
        path.write_text('\n'.join(json.dumps(e) for e in events) + '\n')
        return path

    def test_actions_flags_counts_and_work_time(self):
        from tools.reviewer.inspect_session import inspect_claude, render
        def use(n, name, value, at):
            return {'type': 'assistant', 'timestamp': f'2026-10-19T05:00:{at:02d}.000Z',
                    'message': {'content': [{'type': 'tool_use', 'id': f't{n}', 'name': name, 'input': value}]}}
        def result(n, text, error=False):
            return {'type': 'user', 'timestamp': '2026-10-19T05:00:30.000Z',
                    'message': {'content': [{'type': 'tool_result', 'tool_use_id': f't{n}', 'content': text, 'is_error': error}]}}
        events = [{'type': 'system', 'subtype': 'init', 'session_id': 's1', 'tools': ['Read', 'Bash'], 'model': 'm',
                   'cwd': ROOT, 'claude_code_version': '2.1.303'},
                  use(1, 'Read', {'file_path': f'{ROOT}/src/a.mjs'}, 0), result(1, 'one'),
                  use(2, 'Read', {'file_path': '/home/u/run/ca/expected.json'}, 5),
                  result(2, 'Claude requested permissions to read from /home/u/run/ca/expected.json, but you haven\'t granted it yet.', True),
                  use(3, 'Grep', {'pattern': 'foo', 'path': '../other'}, 9), result(3, 'x'),
                  use(4, 'Bash', {'command': 'env | grep KEY'}, 12), result(4, 'none'),
                  use(5, 'Glob', {'pattern': '**/*.md'}, 15),
                  {'type': 'assistant', 'message': {'content': [{'type': 'thinking', 'thinking': 'not read'},
                                                                {'type': 'text', 'text': 'Done.'}]}},
                  {'type': 'system', 'subtype': 'compact_boundary'},
                  {'type': 'result', 'subtype': 'success', 'duration_ms': 90000, 'num_turns': 6, 'result': 'Final.',
                   'permission_denials': [{}],
                   'modelUsage': {'a': {'inputTokens': 10, 'cacheCreationInputTokens': 90, 'cacheReadInputTokens': 500, 'outputTokens': 40},
                                  'b': {'inputTokens': 5, 'cacheCreationInputTokens': 0, 'cacheReadInputTokens': 0, 'outputTokens': 1}}}]
        r = inspect_claude(self.stream(events), ROOT)
        reasons = [' '.join(a['reasons']) for a in r['actions']]
        self.assertEqual(reasons[0], '')
        self.assertIn('target outside root', reasons[1]);self.assertIn('denied/permission in result', reasons[1])
        self.assertIn('escapes root', reasons[2])
        self.assertIn('environment/identity query', reasons[3])
        self.assertIn('no result', reasons[4])
        self.assertEqual([a['time'] for a in r['actions']], ['+0s', '+5s', '+9s', '+12s', '+15s'])
        self.assertEqual((r['tool_calls'], r['tool_call_counts']), (5, {'Read': 2, 'Grep': 1, 'Bash': 1, 'Glob': 1}))
        self.assertEqual((r['work_seconds'], r['work_time_source'], r['stream_span_seconds']), (90.0, 'result duration_ms', 30.0))
        self.assertEqual((r['compactions'], r['final'], r['permission_denials'], r['threadId']), (1, 'Final.', 1, 's1'))
        self.assertEqual({k: r['tokens'][k] for k in ('uncached_input', 'cached_input', 'output')}, {'uncached_input': 105, 'cached_input': 500, 'output': 41})
        self.assertEqual([m['text'] for m in r['messages']], ['Done.'])
        out = Path(tempfile.mkdtemp())
        summary = render(r, out)
        self.assertIn('工作时间 1.5 分钟', (out / 'actions.md').read_text())
        self.assertEqual(summary['flagged_actions'], [2, 3, 4, 5])

    def test_missing_result_falls_back_to_timestamps_and_unknown_tokens(self):
        from tools.reviewer.inspect_session import inspect_claude
        events = [{'type': 'system', 'subtype': 'init', 'session_id': 's'},
                  {'type': 'assistant', 'timestamp': '2026-10-19T05:00:00Z', 'message': {'content': [{'type': 'text', 'text': 'a'}]}},
                  {'type': 'assistant', 'timestamp': '2026-10-19T05:02:00Z', 'message': {'content': [{'type': 'text', 'text': 'b'}]}}]
        r = inspect_claude(self.stream(events), ROOT)
        self.assertEqual((r['work_seconds'], r['work_time_source']), (120.0, 'event timestamp span'))
        self.assertIsNone(r['tokens']['output']);self.assertEqual(r['final'], 'b')
