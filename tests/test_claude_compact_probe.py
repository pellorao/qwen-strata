"""The Claude Code compaction probe uses qwen-agent's own variables and judges each size against the threshold."""
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest import mock
import urllib.request

from tools.ops import claude_compact_probe as probe

TIER = {'context_window': 206584, 'auto_compact_token_limit': 150000}
MODEL = 'qwen3.8-flash-next-iq3_xxs'
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def post(base, body):
    request = urllib.request.Request(base + '/v1/messages', json.dumps(body).encode(), {'Content-Type': 'application/json'})
    with OPENER.open(request, timeout=10) as reply:
        return reply.read().decode()


def fake_claude(compacts_above):
    """Stands in for `claude -p`: reports what the server claims and compacts when the claim exceeds the limit."""
    state = {'claimed': None}

    def run(command, **kwargs):
        if command[-1] == '--version':
            return subprocess.CompletedProcess(command, 0, '9.9.9 (Claude Code)\n', '')
        base = kwargs['env']['ANTHROPIC_BASE_URL']
        mid = command[-1].startswith('Read')
        if '--continue' not in command:
            first = {'model': MODEL, 'stream': False, 'messages': [{'role': 'user', 'content': 'hi'}],
                     **({'tools': [{'name': 'Read'}]} if mid else {})}
            reply = json.loads(post(base, first))
            state['claimed'] = reply['usage']['input_tokens']
            if not mid:
                return subprocess.CompletedProcess(command, 0, 'OK.\n', '')
        if state['claimed'] > compacts_above:
            summary = json.loads(post(base, {'model': MODEL, 'stream': False, 'messages': [
                {'role': 'user', 'content': probe.MARKER + ', paying close attention.'}]}))
            assert 'summary' in summary['content'][0]['text']
        post(base, {'model': MODEL, 'stream': True, 'messages': [{'role': 'user', 'content': 'go on'}]})
        return subprocess.CompletedProcess(command, 0, 'OK.\n', '')
    return run


class EnvironmentTests(unittest.TestCase):
    def test_takes_qwen_agent_variables_for_the_tier(self):
        env = probe.agent_environment('http://127.0.0.1:9', MODEL, 'high', TIER)
        self.assertEqual(env['CLAUDE_CODE_MAX_CONTEXT_TOKENS'], '206584')
        self.assertEqual(env['CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE'], '150000')
        self.assertEqual(env['CLAUDE_CODE_MAX_OUTPUT_TOKENS'], '24576')
        self.assertTrue(env['ANTHROPIC_BASE_URL'].startswith('http://127.0.0.1:9'))
        self.assertEqual(env['ANTHROPIC_AUTH_TOKEN'], 'fake-loopback')
        self.assertNotIn('CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE',
                         probe.agent_environment('http://127.0.0.1:9', MODEL, 'high', TIER, blocking_override=False))

    def test_default_point_without_override(self):
        self.assertEqual(probe.blocking_limit(206584), 183584)
        self.assertEqual(probe.blocking_limit(156584), 133584)


class ServerTests(unittest.TestCase):
    def test_claims_the_size_and_answers_the_summary_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = probe.FakeAnthropic(tmp, 150100, note=Path(tmp) / 'note.txt')
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                tool = json.loads(post(base, {'model': MODEL, 'messages': [], 'tools': [{'name': 'Read'}]}))
                stream = post(base, {'model': MODEL, 'stream': True, 'messages': [{'role': 'user', 'content': 'x'}]})
                summary = json.loads(post(base, {'model': MODEL, 'messages': [{'role': 'user', 'content': probe.MARKER}]}))
            finally:
                server.shutdown()
                server.server_close()
            self.assertEqual((tool['content'][0]['type'], tool['usage']['input_tokens']), ('tool_use', 150100))
            self.assertIn('"input_tokens": 150100', stream)
            self.assertIn('text_delta', stream)
            self.assertEqual(summary['usage']['input_tokens'], probe.SUMMARY_CLAIM)
            self.assertEqual([e['compaction'] for e in server.log], [False, False, True])
            self.assertTrue((Path(tmp) / 'request-3.json').is_file())


class VerdictTests(unittest.TestCase):
    def grid(self, compacts_above):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(probe.subprocess, 'run', fake_claude(compacts_above)):
            summary = probe.run(Path(tmp) / 'out', tier=TIER, claude='claude', log=lambda _: None)
            saved = json.loads((Path(tmp) / 'out/summary.json').read_text())
        self.assertEqual(saved['pass'], summary['pass'])
        return summary

    def test_passes_when_compaction_follows_the_threshold(self):
        summary = self.grid(150000)
        self.assertTrue(summary['pass'])
        self.assertEqual(summary['claude_version'], '9.9.9 (Claude Code)')
        self.assertEqual(summary['agent_environment']['CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE'], '150000')
        self.assertEqual(sorted((c['way'], c['claimed'], c['compacted']) for c in summary['cells']),
                         [('mid-turn', 149900, False), ('mid-turn', 150100, True),
                          ('two-turn', 149900, False), ('two-turn', 150100, True)])
        self.assertTrue(all(c['continued'] for c in summary['cells'] if c['compacted']))

    def test_fails_when_claude_code_falls_back_to_its_own_limit(self):
        summary = self.grid(183584)
        self.assertFalse(summary['pass'])
        self.assertEqual({c['claimed'] for c in summary['cells'] if not c['ok']}, {150100})


if __name__ == '__main__':
    unittest.main()
