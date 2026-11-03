"""The zero-model sandbox probe runs the native Codex binary on a published tier, against real targets."""
import json
from pathlib import Path
import tempfile
import unittest
import unittest.mock

from tools.reviewer.native_cli_binding import CODEX, CODEX_VENDOR
from tools.reviewer import wsl_client
from tools.safety import verify_reviewer_sandbox
from tools.safety.reviewer_permissions import restricted_profile


class ProbeConfigurationTests(unittest.TestCase):
    def test_harness_takes_the_tier_it_is_given(self):
        tier = {'context_window': 206584, 'auto_compact_token_limit': 150000}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            _, args = wsl_client.configuration(out, out, 'http://127.0.0.1:1/v1',
                                               model_slug='qwen3.8-flash-next-iq3_xxs', tier=tier)
            values = dict(args[i + 1].split('=', 1) for i in range(0, len(args), 2))
            self.assertEqual((values['model_context_window'], values['model_auto_compact_token_limit']),
                             ('206584', '150000'))
            model = json.loads((out / 'catalog.json').read_text())['models'][0]
            self.assertEqual((model['context_window'], model['max_context_window']), (206584, 206584))
            with self.assertRaises(TypeError):
                wsl_client.configuration(out, out, 'x', model_slug='qwen3.8-flash-next-iq3_xxs')

    def test_profile_keeps_the_native_binary_readable(self):
        self.assertTrue(CODEX.is_relative_to(CODEX_VENDOR))
        if not CODEX_VENDOR.exists():
            self.skipTest('native Codex not installed')
        with tempfile.TemporaryDirectory() as tmp:
            project, scratch = Path(tmp) / 'p', Path(tmp) / 's'
            project.mkdir(); scratch.mkdir()
            grants = restricted_profile(project, scratch)['permissions.review.filesystem']
            self.assertEqual(grants[str(CODEX_VENDOR.resolve())], 'read')
            self.assertEqual(grants[str(scratch.resolve())], 'write')

    def test_denied_targets_exist_and_name_the_hosts_model_endpoint(self):
        targets = verify_reviewer_sandbox.denied_targets('rtx3080ti')
        deployment = json.loads((wsl_client.ROOT / 'config/deployments/rtx3080ti.json').read_text())
        self.assertEqual(targets['model_api'], [deployment['listen_address'], deployment['port']])
        self.assertTrue(Path(targets['other_project']).is_file())

    def test_unreachable_network_targets_are_vacuous_controls(self):
        import socket
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        live = ['127.0.0.1', listener.getsockname()[1]]
        free = socket.socket()
        free.bind(('127.0.0.1', 0))
        dead = ['127.0.0.1', free.getsockname()[1]]
        free.close()
        try:
            self.assertTrue(verify_reviewer_sandbox.reachable(live))
            self.assertFalse(verify_reviewer_sandbox.reachable(dead))
            with unittest.mock.patch.object(verify_reviewer_sandbox, 'PUBLIC_TARGET', tuple(live)):
                controls = verify_reviewer_sandbox.network_controls({'model_api': dead})
            self.assertEqual(controls, {'public_network': True, 'model_api': False})
        finally:
            listener.close()


if __name__ == '__main__':
    unittest.main()
