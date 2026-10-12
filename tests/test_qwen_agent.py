"""The agent launcher points each agent at the frontend with the lease key only."""
from importlib.machinery import SourceFileLoader
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import frontend  # noqa: E402

agent = SourceFileLoader('qwen_agent', str(Path(__file__).resolve().parents[1] / 'scripts/wsl/qwen-agent')).load_module()


class Fake:
    base, key = 'http://192.168.60.212:8000', 'lease-key'


class LauncherTests(unittest.TestCase):
    def test_codex_uses_strata_provider_and_key_variable(self):
        command, env = agent.codex(Fake(), 'qwen3.8-flash-next-q2_0', 'medium', ['exec', 'hi'])
        config = dict(command[i + 1].split('=', 1) for i in range(1, len(command) - 2, 2) if command[i] == '-c')
        self.assertEqual(command[0], 'codex')
        self.assertEqual(command[-2:], ['exec', 'hi'])
        self.assertEqual(json.loads(config['model_providers.qwen_strata.base_url']), 'http://192.168.60.212:8000/strata/v1')
        self.assertEqual(json.loads(config['model_reasoning_effort']), 'medium')
        self.assertEqual(json.loads(config['web_search']), 'live')
        self.assertTrue(json.loads(config['model_catalog_json']).endswith('config/model-catalog.json'))
        self.assertEqual(env, {'QWEN_STRATA_KEY': 'lease-key'})
        self.assertNotIn('lease-key', ' '.join(command))

    def test_claude_uses_frontend_prefix_single_model_and_strata_approval(self):
        command, env = agent.claude(Fake(), 'qwen3.8-flash-next-q2_0', 'high', ['-p', 'hi'])
        self.assertEqual(command[0], 'claude')
        self.assertEqual(command[-2:], ['-p', 'hi'])
        self.assertEqual(command[command.index('--permission-mode') + 1], 'default')
        settings = json.loads(command[command.index('--settings') + 1])
        self.assertTrue(settings['skipWebFetchPreflight'])
        self.assertEqual(settings['permissions']['deny'], ['WebSearch'])
        self.assertNotIn('autoMode', settings)
        hook = settings['hooks']['PermissionRequest'][0]['hooks'][0]
        self.assertTrue(hook['command'].endswith('bin/qwen-approve'))
        self.assertGreaterEqual(hook['timeout'], 150)
        compact = settings['hooks']['PreCompact'][0]['hooks'][0]['command']
        self.assertTrue(compact.startswith('cat ') and compact.endswith('config/prompts/compact-prompt.txt'))
        self.assertEqual(command[command.index('--mcp-config') + 2], '--permission-mode')
        server = json.loads(command[command.index('--mcp-config') + 1])['mcpServers']['brave']
        self.assertTrue(server['args'][0].endswith('src/brave_mcp.py'))
        self.assertEqual(env['CLAUDE_CODE_MAX_CONTEXT_TOKENS'], '156584')
        self.assertEqual((env['CLAUDE_CODE_EFFORT_LEVEL'], env['CLAUDE_CODE_MAX_OUTPUT_TOKENS']), ('high', '24576'))
        self.assertEqual(env['CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE'], '100000')
        self.assertNotIn('lease-key', ' '.join(command))
        self.assertEqual(env['ANTHROPIC_BASE_URL'], 'http://192.168.60.212:8000/strata')
        self.assertEqual(env['ANTHROPIC_AUTH_TOKEN'], 'lease-key')
        self.assertEqual({env[k] for k in env if k.endswith('_MODEL')}, {'qwen3.8-flash-next-q2_0'})

    def test_claude_gets_the_effort_output_and_compaction_codex_gets(self):
        """Claude Code sends its own max_tokens, so each effort's total must equal what the frontend fills in
        for Codex, and its compaction limit must equal Codex's auto-compact threshold."""
        for effort, (_, total) in ((e, frontend.EFFORT_BUDGETS[e]) for e in ('low', 'medium', 'high')):
            env = agent.claude(Fake(), 'qwen3.8-flash-next-iq3_xxs', effort, [])[1]
            self.assertEqual((env['CLAUDE_CODE_EFFORT_LEVEL'], env['CLAUDE_CODE_MAX_OUTPUT_TOKENS']), (effort, str(total)))
            config = dict(item.split('=', 1) for item in agent.codex(Fake(), 'm', effort, [])[0][2::2])
            self.assertEqual(env['CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE'], config['model_auto_compact_token_limit'])
            self.assertEqual(env['CLAUDE_CODE_MAX_CONTEXT_TOKENS'], config['model_context_window'])


if __name__ == '__main__':
    unittest.main()
