import json
import tempfile
import unittest
from pathlib import Path

from tools.reviewer.inspect_session import inspect

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
