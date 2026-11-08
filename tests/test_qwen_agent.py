"""The agent launcher points each agent at the frontend with the lease key only."""
from importlib.machinery import SourceFileLoader
import json
import signal
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import frontend  # noqa: E402

agent = SourceFileLoader('qwen_agent', str(Path(__file__).resolve().parents[1] / 'scripts/wsl/qwen-agent')).load_module()


class Fake:
    base, key = 'http://192.168.60.212:8000', 'lease-key'


ROOT = Path(__file__).resolve().parents[1]
HOST = json.loads((ROOT / 'config/deployments/rtx3080ti.json').read_text(encoding='utf-8'))
TIERS = {m: HOST['context_tiers'][m] for m in HOST['models']}  # what the installation publishes
DEFAULT = TIERS['IQ3_XXS'][0]


class LauncherTests(unittest.TestCase):
    def test_shutdown_signal_is_taken_once_so_the_release_is_not_interrupted(self):
        saved = {n: signal.getsignal(getattr(signal, n)) for n in agent.SHUTDOWN_SIGNALS}
        try:
            with self.assertRaises(SystemExit):
                agent.shut_down()
            for name in agent.SHUTDOWN_SIGNALS:
                self.assertEqual(signal.getsignal(getattr(signal, name)), signal.SIG_IGN)
        finally:
            for name, handler in saved.items():
                signal.signal(getattr(signal, name), handler)

    def test_child_environment_drops_credentials_and_parent_session(self):
        parent = {'PATH': '/bin', 'CLAUDE_CONFIG_DIR': '/tmp/cfg', 'CLAUDE_CONFIG_DIRX': 'x', 'ANTHROPIC_API_KEY': 'x',
                  'OPENAI_API_KEY': 'x', 'AI_AGENT': 'claude-code', 'CLAUDECODE': '1', 'CLAUDE_CODE_SESSION_ID': 's',
                  'CLAUDE_CODE_MESSAGING_SOCKET': '/run/s', 'CLAUDE_CODE_MESSAGING_TOKEN': 't',
                  'CLAUDE_CODE_CHILD_SESSION': '1', 'CLAUDE_CODE_ENTRYPOINT': 'cli', 'CLAUDE_EFFORT': 'high', 'CLAUDE_PID': '1'}
        self.assertEqual(agent.child_environment(parent, {}), {'PATH': '/bin', 'CLAUDE_CONFIG_DIR': '/tmp/cfg'})

    def test_child_environment_launcher_values_win(self):
        _, own = agent.claude(Fake(), 'qwen3.8-flash-next-iq3_xxs', 'high', DEFAULT, ['-p', 'hi'])
        parent = {'ANTHROPIC_BASE_URL': 'http://elsewhere', 'CLAUDE_CODE_EFFORT_LEVEL': 'low'}
        env = agent.child_environment(parent, own)
        self.assertEqual(env['ANTHROPIC_BASE_URL'], 'http://192.168.60.212:8000/strata')
        self.assertEqual(env['CLAUDE_CODE_EFFORT_LEVEL'], 'high')
        self.assertEqual(env['CLAUDE_CODE_MAX_CONTEXT_TOKENS'], '206584')

    def test_claude_tool_search_is_off_whatever_the_caller_sets(self):
        """Strata implements neither defer_loading nor tool_reference, so every tool must be sent inline."""
        _, own = agent.claude(Fake(), 'qwen3.8-flash-next-iq3_xxs', 'high', DEFAULT, [])
        self.assertEqual(own['ENABLE_TOOL_SEARCH'], 'false')
        for value in ('true', 'auto', '1'):
            env = agent.child_environment({'PATH': '/bin', 'ENABLE_TOOL_SEARCH': value}, own)
            self.assertEqual(env['ENABLE_TOOL_SEARCH'], 'false')

    def test_codex_uses_strata_provider_and_key_variable(self):
        command, env = agent.codex(Fake(), 'qwen3.8-flash-next-iq3_xxs', 'medium', DEFAULT, ['exec', 'hi'])
        config = dict(command[i + 1].split('=', 1) for i in range(1, len(command) - 2, 2) if command[i] == '-c')
        self.assertEqual(command[0], 'codex')
        self.assertEqual(command[-2:], ['exec', 'hi'])
        self.assertEqual(json.loads(config['model_providers.qwen_strata.base_url']), 'http://192.168.60.212:8000/strata/v1')
        self.assertEqual(json.loads(config['model_reasoning_effort']), 'medium')
        self.assertEqual(json.loads(config['web_search']), 'live')
        self.assertTrue(json.loads(config['model_catalog_json']).endswith('config/model-catalog.json'))
        self.assertEqual((json.loads(config['model_context_window']), json.loads(config['model_auto_compact_token_limit'])),
                         (206584, 150000))
        self.assertEqual(env, {'QWEN_STRATA_KEY': 'lease-key'})
        self.assertNotIn('lease-key', ' '.join(command))

    def test_claude_uses_frontend_prefix_single_model_and_strata_approval(self):
        command, env = agent.claude(Fake(), 'qwen3.8-flash-next-iq3_xxs', 'high', DEFAULT, ['-p', 'hi'])
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
        self.assertEqual(env['CLAUDE_CODE_MAX_CONTEXT_TOKENS'], '206584')
        self.assertEqual((env['CLAUDE_CODE_EFFORT_LEVEL'], env['CLAUDE_CODE_MAX_OUTPUT_TOKENS']), ('high', '24576'))
        self.assertEqual(env['CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE'], '150000')
        self.assertNotIn('lease-key', ' '.join(command))
        self.assertEqual(env['ANTHROPIC_BASE_URL'], 'http://192.168.60.212:8000/strata')
        self.assertEqual(env['ANTHROPIC_AUTH_TOKEN'], 'lease-key')
        self.assertEqual({env[k] for k in env if k.endswith('_MODEL')}, {'qwen3.8-flash-next-iq3_xxs'})

    def test_claude_gets_the_effort_output_and_compaction_codex_gets(self):
        """Claude Code sends its own max_tokens, so each effort's total must equal what the frontend fills in
        for Codex, and its compaction limit must equal Codex's auto-compact threshold."""
        for tier in (t for tiers in TIERS.values() for t in tiers):
            for effort, (_, total) in ((e, frontend.EFFORT_BUDGETS[e]) for e in ('low', 'medium', 'high')):
                env = agent.claude(Fake(), 'qwen3.8-flash-next-iq3_xxs', effort, tier, [])[1]
                self.assertEqual((env['CLAUDE_CODE_EFFORT_LEVEL'], env['CLAUDE_CODE_MAX_OUTPUT_TOKENS']), (effort, str(total)))
                config = dict(item.split('=', 1) for item in agent.codex(Fake(), 'm', effort, tier, [])[0][2::2])
                self.assertEqual(env['CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE'], config['model_auto_compact_token_limit'])
                self.assertEqual(env['CLAUDE_CODE_MAX_CONTEXT_TOKENS'], config['model_context_window'])
                # A request at the threshold plus a full output budget must still fit in the window.
                self.assertLess(tier['auto_compact_token_limit'] + total, tier['context_window'])

    def test_default_tier_is_the_first_published_and_a_missing_one_fails(self):
        saved = agent.INSTALL
        try:
            with tempfile.TemporaryDirectory() as folder:
                agent.INSTALL = Path(folder)
                (agent.INSTALL / 'config').mkdir()
                (agent.INSTALL / 'config/deployment.json').write_text(json.dumps(
                    {'models': ['IQ3_XXS'], 'context_tiers': {'IQ3_XXS': TIERS['IQ3_XXS']}}))
                self.assertEqual(agent.default_tier('IQ3_XXS'), DEFAULT)
                with self.assertRaises(SystemExit):
                    agent.default_tier('Q2_0')  # an unserved model publishes no tier in the installation
                (agent.INSTALL / 'config/deployment.json').write_text(json.dumps({}))
                with self.assertRaises(SystemExit):
                    agent.default_tier('IQ3_XXS')
        finally:
            agent.INSTALL = saved

    def test_model_defaults_to_the_served_one_and_others_are_refused(self):
        saved = agent.INSTALL
        try:
            with tempfile.TemporaryDirectory() as folder:
                agent.INSTALL = Path(folder)
                (agent.INSTALL / 'config').mkdir()
                (agent.INSTALL / 'config/deployment.json').write_text(json.dumps({'models': ['IQ3_XXS']}))
                self.assertEqual(agent.served_model(), 'IQ3_XXS')
                self.assertEqual(agent.served_model('IQ3_XXS'), 'IQ3_XXS')
                with self.assertRaisesRegex(SystemExit, 'serves only IQ3_XXS'):
                    agent.served_model('Q2_0')
                (agent.INSTALL / 'config/deployment.json').write_text(json.dumps({}))
                with self.assertRaises(SystemExit):
                    agent.served_model()
        finally:
            agent.INSTALL = saved


if __name__ == '__main__':
    unittest.main()
