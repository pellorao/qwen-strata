"""Generated deployments use project/private host inputs without leaking credentials."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.ops.deployment_source import model_configuration, service_configuration, source_bytes


class SourceRenderingTests(unittest.TestCase):
    def test_machine_defaults_do_not_change_another_host_or_public_baseline(self):
        root=Path(__file__).resolve().parents[1]
        before=(root/'config/maintenance-baseline.json').read_bytes()
        remote=model_configuration('Q2_0','rtx3080ti',root)
        local=model_configuration('Q2_0','local',root)
        self.assertEqual(remote['args'][remote['args'].index('--max-context')+1],'156584')
        self.assertEqual(remote['request_defaults'],{'reasoning_effort':'high','reasoning_budget_tokens':8192,'max_tokens':24576,
                                                   'temperature':0.0,'top_p':1.0,'top_k':20})
        self.assertEqual(remote['engine_environment'],{'STRATA_PREFILL_CPU_SHARE':'auto'})
        self.assertEqual(local['args'][local['args'].index('--max-context')+1],'250000')
        self.assertNotIn('request_defaults',local)
        self.assertNotIn('engine_environment',local)
        self.assertEqual((root/'config/maintenance-baseline.json').read_bytes(),before)

    def test_foreign_paths_ports_and_credentials_are_separated_from_public_templates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);(root/'config/deployments').mkdir(parents=True)
            (root/'config/templates').mkdir()
            profile = {'schema_version': 1, 'id': 'test', 'connection_host': 'test',
                       'transport': 'ssh-windows', 'cuda_arch': 86, 'models': ['Q2_0'],
                       'engine_overrides': {'prefill': 8192}, 'listen_address': '192.168.60.212',
                       'allowed_clients': ['192.168.0.2']}
            (root/'config/deployments/test.json').write_text(json.dumps(profile), encoding='utf-8')
            (root/'hosts.private.toml').write_text("""[hosts.test]
transport='ssh-windows'
ip='192.168.0.4'
installation_path='D:\\模型\\Strata'
[hosts.test.ssh]
port=2222
username='private-user'
password='secret-sentinel'
[hosts.test.service]
listen_port=8000
access_port=28000
model_port=8100
""", encoding='utf-8')
            template = {'exe': '${INSTALL_ROOT}\\runtime\\engine.exe',
                        'args': ['--prefill', '16384'], 'port': 8100}
            (root/'config/templates/q2_0-prebuilt.json').write_text(json.dumps(template), encoding='utf-8')
            model = model_configuration('Q2_0', 'test', root)
            self.assertEqual(model['exe'], 'D:\\模型\\Strata\\runtime\\engine.exe')
            self.assertEqual(model['args'], ['--prefill', '8192'])
            service = service_configuration('test', root)
            self.assertEqual(service['listen_port'], 8000)
            self.assertEqual(service['model_port'], 8100)
            self.assertEqual(service['access_base_url'], 'http://192.168.0.4:28000')
            public = source_bytes('config/deployment.json', 'test', root).decode('utf-8')
            self.assertNotIn('secret-sentinel', public)
            self.assertNotIn('private-user', public)
            self.assertNotIn('password', public)
            self.assertFalse((root/'installation').exists())


if __name__ == '__main__':unittest.main()
