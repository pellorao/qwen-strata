"""The agent launcher points each agent at the frontend with the lease key only."""
from importlib.machinery import SourceFileLoader
import json
from pathlib import Path
import unittest

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
        self.assertTrue(json.loads(config['model_catalog_json']).endswith('config/model-catalog.json'))
        self.assertEqual(env, {'QWEN_STRATA_KEY': 'lease-key'})
        self.assertNotIn('lease-key', ' '.join(command))

    def test_claude_uses_frontend_prefix_and_single_model(self):
        command, env = agent.claude(Fake(), 'qwen3.8-flash-next-q2_0', 'high', [])
        self.assertEqual(command, ['claude'])
        self.assertEqual(env['ANTHROPIC_BASE_URL'], 'http://192.168.60.212:8000/strata')
        self.assertEqual(env['ANTHROPIC_AUTH_TOKEN'], 'lease-key')
        self.assertEqual({env[k] for k in env if k.endswith('_MODEL')}, {'qwen3.8-flash-next-q2_0'})


if __name__ == '__main__':
    unittest.main()
