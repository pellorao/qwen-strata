import json
import shutil
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

    def test_code_mode_items_are_checked_as_actions(self):
        events = [{'type': 'session_meta', 'payload': {'id': 't', 'cwd': ROOT, 'base_instructions': 'x'}},
                  message('developer', 'role'), message('user', 'ARW messageId: m1\n\nhandoff'),
                  {'type': 'response_item', 'payload': {'type': 'custom_tool_call', 'name': 'exec', 'call_id': 'x1',
                                                        'input': 'await tools.exec_command({cmd: "ls"})'}},
                  {'type': 'event_msg', 'payload': {'type': 'item_completed', 'item': {
                      'type': 'CommandExecution', 'id': 'i1', 'command': ['/bin/bash', '-lc', f'cat {ROOT}/a'],
                      'cwd': ROOT, 'aggregated_output': 'ok', 'exit_code': 0}}},
                  {'type': 'event_msg', 'payload': {'type': 'item_completed', 'item': {
                      'type': 'CommandExecution', 'id': 'i2', 'command': ['/bin/bash', '-lc', 'cat ~/.codex/auth.json'],
                      'cwd': '/home/u', 'exit_code': 1}}},
                  {'type': 'event_msg', 'payload': {'type': 'item_completed', 'item': {
                      'type': 'FileChange', 'id': 'i3', 'changes': {f'{ROOT}/b': {}, '/home/u/x': {}}}}},
                  message('assistant', '{"status":"ready"}')]
        with tempfile.NamedTemporaryFile('w', suffix='.jsonl', delete=False) as f:
            f.write('\n'.join(json.dumps(e) for e in events))
        try:
            r = inspect(f.name)
        finally:
            Path(f.name).unlink()
        mine = [a for a in r['actions'] if a['tool'].startswith('exec>')]
        self.assertEqual([a['tool'] for a in mine], ['exec>command', 'exec>command', 'exec>file_change'])
        self.assertEqual(mine[0]['reasons'], [])
        self.assertIn('workdir outside root', ' '.join(mine[1]['reasons']))
        self.assertIn('session/credential material', ' '.join(mine[1]['reasons']))
        self.assertEqual(mine[2]['reasons'], ['patch outside root: /home/u/x'])

    def test_credential_values_are_redacted(self):
        jwt = 'eyJhbGciOiJub25lIn0.eyJleHAiOjQxMDI0NDQ4MDB9.c3ludGhldGlj'
        text = redact(f'Bearer abcdefghijklmnopqrst {{"refresh_token": "rt-123456789"}} sk-abcdefghijklmnopqrstuv {jwt} '
                      'ANTHROPIC_AUTH_TOKEN=abcdefghijk keep')
        for value in (jwt, 'abcdefghijklmnopqrst', 'rt-123456789', 'sk-abcdefghijklmnopqrstuv', 'abcdefghijk'):
            self.assertNotIn(value, text)
        self.assertTrue(text.endswith(' keep'))
        self.assertEqual(redact('cat request.json'), 'cat request.json')
        for text in ("{'access_token': 'at-123456789'}", '"{\\"id_token\\": \\"it-123456789\\"}"',
                     'STRATA_REMOTE_PASSWORD=pw-123456789'):
            self.assertNotIn('-123456789', redact(text))

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

    def test_startup_sha_ignores_codex_arg0_directory(self):
        a = self.run_session(developer='<path>/h/codex-home/tmp/arg0-linux/codex-arg08p0Hjt</path>')
        b = self.run_session(developer='<path>/h/codex-home/tmp/arg0-linux/codex-arg0HGVGOv</path>')
        c = self.run_session(developer='<path>/h/codex-home/tmp/arg0-linux/other</path>')
        self.assertEqual(a['startup']['developer@1'], b['startup']['developer@1'])
        self.assertNotEqual(a['startup']['developer@1'], c['startup']['developer@1'])


if __name__ == '__main__':
    unittest.main()


class InspectClaudeStreamTest(unittest.TestCase):
    """Claude Code stream-json: actions, flags, tool-call counts, work time and API tokens."""
    def stream(self, events):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        path = Path(folder) / 'stream.jsonl'
        path.write_text('\n'.join(json.dumps(e) for e in events) + '\n')
        return path

    def test_unparsed_bash_input_is_shown_raw_not_as_empty_command(self):
        from tools.reviewer.inspect_session import inspect_claude
        def use(n, value):
            return {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'id': f't{n}', 'name': 'Bash', 'input': value}]}}
        events = [{'type': 'system', 'subtype': 'init', 'session_id': 's1', 'cwd': ROOT},
                  use(1, '{"command": "ls -la'), use(2, {}), use(3, {'cmd': 'ls'}), use(4, {'command': 'ls'})]
        r = inspect_claude(self.stream(events), ROOT)
        texts = [a['text'] for a in r['actions']]
        self.assertEqual(texts, ['[输入解析失败] {"command": "ls -la', '[输入解析失败] {}', '[输入解析失败] {"cmd": "ls"}', 'ls'])
        flagged = ['bash input not parsed' in a['reasons'] for a in r['actions']]
        self.assertEqual(flagged, [True, True, True, False])

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
                  {'type': 'system', 'subtype': 'permission_denied', 'tool_name': 'Write', 'decision_reason': 'outside',
                   'message': '/tmp/x is outside the working directory'},
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
        self.assertEqual([m['text'] for m in r['messages']],
                         ['Done.', 'permission_denied Write: outside: /tmp/x is outside the working directory'])
        self.assertEqual([m['role'] for m in r['messages']], ['assistant', 'harness'])
        out = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, out, True)
        summary = render(r, out)
        self.assertIn('工作时间 1.5 分钟', (out / 'actions.md').read_text())
        self.assertEqual(summary['flagged_actions'], [2, 3, 4, 5])

    def test_background_task_notification_turn_adds_its_own_result(self):
        # Claude Code 2.1.303 -p: a backgrounded command outlives the first result; after it stops, a notification
        # turn ends with a second result whose duration_ms, num_turns, usage and denials cover that turn only
        # (modelUsage is cumulative). CA r2 strata-medium-a2: 1092441 + 5174 ms, not 5174.
        from tools.reviewer.inspect_session import inspect_claude
        def at(m):
            return {'type': 'assistant', 'timestamp': f'2026-10-20T01:{m:02d}:00Z', 'message': {'content': [{'type': 'text', 'text': 'x'}]}}
        def res(ms, turns, usage, denials=(), model=None):
            e = {'type': 'result', 'subtype': 'success', 'duration_ms': ms, 'num_turns': turns, 'usage': usage,
                 'permission_denials': list(denials), 'result': f'r{turns}'}
            if model:
                e['modelUsage'] = {'m': model}
            return e
        u1 = {'input_tokens': 50, 'cache_creation_input_tokens': 0, 'cache_read_input_tokens': 2000, 'output_tokens': 80}
        u2 = {'input_tokens': 4, 'cache_creation_input_tokens': 0, 'cache_read_input_tokens': 100, 'output_tokens': 3}
        events = [{'type': 'system', 'subtype': 'init', 'session_id': 's'}, at(0), res(1092441, 57, u1, [{}]),
                  {'type': 'system', 'subtype': 'task_notification', 'status': 'stopped'},
                  {'type': 'system', 'subtype': 'init', 'session_id': 's'}, at(27), res(5174, 1, u2)]
        r = inspect_claude(self.stream(events), ROOT)
        self.assertEqual((r['work_seconds'], r['result_events'], r['num_turns'], r['permission_denials'], r['final']),
                         (1097.615, 2, 58, 1, 'r1'))
        self.assertEqual(r['stream_span_seconds'], 1620.0)
        self.assertEqual({k: r['tokens'][k] for k in ('uncached_input', 'cached_input', 'output')},
                         {'uncached_input': 54, 'cached_input': 2100, 'output': 83})
        events[-1] = res(5174, 1, u2, model={'inputTokens': 54, 'cacheCreationInputTokens': 0,
                                             'cacheReadInputTokens': 2100, 'outputTokens': 83})
        self.assertEqual(inspect_claude(self.stream(events), ROOT)['tokens']['output'], 83)

    def test_missing_result_falls_back_to_timestamps_and_unknown_tokens(self):
        from tools.reviewer.inspect_session import inspect_claude
        events = [{'type': 'system', 'subtype': 'init', 'session_id': 's'},
                  {'type': 'assistant', 'timestamp': '2026-10-19T05:00:00Z', 'message': {'content': [{'type': 'text', 'text': 'a'}]}},
                  {'type': 'assistant', 'timestamp': '2026-10-19T05:02:00Z', 'message': {'content': [{'type': 'text', 'text': 'b'}]}}]
        r = inspect_claude(self.stream(events), ROOT)
        self.assertEqual((r['work_seconds'], r['work_time_source']), (120.0, 'event timestamp span'))
        self.assertIsNone(r['tokens']['output']);self.assertEqual(r['final'], 'b')
