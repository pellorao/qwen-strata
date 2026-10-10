"""Generated deployments use project/private host inputs without leaking credentials."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.ops.deployment_source import frontend_configuration, load_host, model_configuration, source_bytes


class SourceRenderingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = root = Path(self.temp.name)
        (root/'config/deployments').mkdir(parents=True)
        (root/'config/templates').mkdir()
        self.host('tuned', engine_overrides={'prefill': 8192}, listen_address='192.168.60.212', port=8000,
                  installation_defaults={'max_context': 156584, 'reasoning_effort': 'high', 'max_tokens': 24576,
                                         'cpu_prefill_share': 'auto', 'top_k': 20})
        self.host('plain', engine_overrides={})
        (root/'project.private.toml').write_text("""[hosts.tuned]
installation_path='D:\\模型\\Strata'
frontend_url='http://192.168.60.212:8000'
brave_api_key='secret-sentinel'
[hosts.plain]
installation_path='C:\\Strata'
[hosts.stray]
installation_path='C:\\Strata'
""", encoding='utf-8')
        template = {'exe': '${INSTALL_ROOT}\\runtime\\engine.exe', 'port': 8100,
                    'args': ['--prefill', '16384', '--max-context', '250000']}
        (root/'config/templates/q2_0-prebuilt.json').write_text(json.dumps(template), encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def host(self, identifier, **fields):
        value = {'schema_version': 2, 'id': identifier, 'cuda_arch': 86, 'models': ['Q2_0'], **fields}
        (self.root/'config/deployments'/(identifier+'.json')).write_text(json.dumps(value), encoding='utf-8')

    def test_host_defaults_render_only_for_that_host(self):
        tuned = model_configuration('Q2_0', 'tuned', self.root)
        plain = model_configuration('Q2_0', 'plain', self.root)
        self.assertEqual(tuned['exe'], 'D:\\模型\\Strata\\runtime\\engine.exe')
        self.assertEqual(tuned['args'], ['--prefill', '8192', '--max-context', '156584'])
        self.assertEqual(tuned['request_defaults'], {'reasoning_effort': 'high', 'max_tokens': 24576, 'top_k': 20})
        self.assertEqual(tuned['engine_environment'], {'STRATA_PREFILL_CPU_SHARE': 'auto'})
        self.assertEqual(plain['args'], ['--prefill', '16384', '--max-context', '250000'])
        self.assertNotIn('request_defaults', plain)
        self.assertNotIn('engine_environment', plain)

    def test_model_overrides_apply_only_to_that_model(self):
        (self.root/'config/templates/iq3_xxs-prebuilt.json').write_text(
            json.dumps({'exe': 'x', 'port': 8100, 'args': ['--prefill', '512']}), encoding='utf-8')
        self.host('tuned', models=['Q2_0', 'IQ3_XXS'], engine_overrides={'prefill': 8192},
                  model_overrides={'Q2_0': {'vram-reserve-mib': 512}})
        self.assertEqual(model_configuration('Q2_0', 'tuned', self.root)['args'],
                         ['--prefill', '8192', '--max-context', '250000', '--vram-reserve-mib', '512'])
        self.assertEqual(model_configuration('IQ3_XXS', 'tuned', self.root)['args'], ['--prefill', '8192'])
        self.host('tuned', models=['Q2_0', 'IQ3_XXS'], engine_overrides={}, model_overrides={'IQ3_XXS': {'prefill': None}})
        self.assertEqual(model_configuration('IQ3_XXS', 'tuned', self.root)['args'], [])
        self.host('stray', engine_overrides={}, model_overrides={'IQ2_XS': {'vram-reserve-mib': 512}})
        with self.assertRaisesRegex(ValueError, 'model_overrides'):
            load_host('stray', self.root)

    def test_public_outputs_never_carry_private_values(self):
        self.assertEqual(frontend_configuration('tuned', self.root),
                         {'listen_address': '192.168.60.212', 'port': 8000, 'model_port': 8100})
        public = source_bytes('config/deployment.json', 'tuned', self.root).decode('utf-8')
        for private in ('secret-sentinel', 'frontend_url', 'installation_root', '模型'):
            self.assertNotIn(private, public)

    def test_old_schema_and_unknown_fields_are_rejected(self):
        self.host('old', schema_version=1)
        with self.assertRaisesRegex(ValueError, 'schema'):
            load_host('old', self.root)
        self.host('leaky', engine_overrides={}, password='x')
        with self.assertRaisesRegex(ValueError, 'Unknown deployment field'):
            load_host('leaky', self.root)


if __name__ == '__main__':unittest.main()
