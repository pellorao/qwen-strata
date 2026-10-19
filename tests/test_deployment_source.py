"""Generated deployments use project/private host inputs without leaking credentials."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.ops.deployment_source import frontend_configuration, load_host, model_configuration, published_tier, source_bytes


class SourceRenderingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = root = Path(self.temp.name)
        (root/'config/deployments').mkdir(parents=True)
        (root/'config/templates').mkdir()
        self.host('tuned', engine_overrides={'prefill': 8192}, listen_address='192.168.60.212', port=8000,
                  installation_defaults={'reasoning_effort': 'high', 'max_tokens': 24576,
                                         'cpu_prefill_share': 'auto', 'top_k': 20},
                  context_tiers={'Q2_0': [{'context_window': 156584, 'auto_compact_token_limit': 100000},
                                          {'context_window': 65536, 'auto_compact_token_limit': 40000}]})
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
        self.assertEqual(tuned['context_tiers'][1], {'context_window': 65536, 'auto_compact_token_limit': 40000})
        self.assertEqual(plain['args'], ['--prefill', '16384', '--max-context', '250000'])
        self.assertNotIn('context_tiers', plain)
        self.assertNotIn('request_defaults', plain)
        self.assertNotIn('engine_environment', plain)

    def test_guardian_defaults_render_and_come_in_pairs(self):
        self.host('tuned', engine_overrides={}, installation_defaults={
            'reasoning_effort': 'high', 'guardian_reasoning_budget_tokens': 1536, 'guardian_max_tokens': 2048})
        self.assertEqual(model_configuration('Q2_0', 'tuned', self.root)['request_defaults'],
                         {'reasoning_effort': 'high', 'guardian_reasoning_budget_tokens': 1536, 'guardian_max_tokens': 2048})
        self.host('tuned', engine_overrides={}, installation_defaults={'guardian_max_tokens': 2048})
        with self.assertRaisesRegex(ValueError, 'Guardian'):
            model_configuration('Q2_0', 'tuned', self.root)

    def test_context_tiers_need_a_compaction_limit_inside_the_window(self):
        self.host('tuned', engine_overrides={}, context_tiers={'Q2_0': [{'context_window': 65536, 'auto_compact_token_limit': 65536}]})
        with self.assertRaisesRegex(ValueError, 'context_tiers'):
            model_configuration('Q2_0', 'tuned', self.root)

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

    def test_model_environment_applies_only_to_that_model(self):
        (self.root/'config/templates/iq3_xxs-prebuilt.json').write_text(
            json.dumps({'exe': 'x', 'port': 8100, 'args': []}), encoding='utf-8')
        self.host('tuned', models=['Q2_0', 'IQ3_XXS'], engine_overrides={},
                  model_environment={'IQ3_XXS': {'STRATA_ADAPT_LAG': 2}})
        self.assertEqual(model_configuration('IQ3_XXS', 'tuned', self.root)['engine_environment']['STRATA_ADAPT_LAG'], 2)
        self.assertNotIn('STRATA_ADAPT_LAG', model_configuration('Q2_0', 'tuned', self.root).get('engine_environment', {}))
        self.host('stray', engine_overrides={}, model_environment={'IQ2_XS': {'STRATA_ADAPT_LAG': 2}})
        with self.assertRaisesRegex(ValueError, 'model_environment'):
            load_host('stray', self.root)

    def test_condition_overlays_one_model_until_a_plain_render(self):
        (self.root/'config/templates/iq3_xxs-prebuilt.json').write_text(
            json.dumps({'exe': 'x', 'port': 8100, 'args': ['--spec', '4', '--expert-profile', 'shipped']}), encoding='utf-8')
        self.host('tuned', models=['Q2_0', 'IQ3_XXS'], engine_overrides={},
                  installation_defaults={'cpu_prefill_share': 'auto'},
                  model_environment={'IQ3_XXS': {'STRATA_ADAPT_LAG': 2}})
        condition = {'id': 'trial', 'model': 'IQ3_XXS',
                     'model_overrides': {'spec': 3, 'expert-profile': '${INSTALL_ROOT}\\data\\profiles\\p.bin'},
                     'model_environment': {'STRATA_PREFILL_CPU_SHARE': None}}
        tried = model_configuration('IQ3_XXS', 'tuned', self.root, condition)
        self.assertEqual(tried['args'], ['--spec', '3', '--expert-profile', 'D:\\模型\\Strata\\data\\profiles\\p.bin'])
        # null leaves the variable unset; the host's own environment stays
        self.assertEqual(tried['engine_environment'], {'STRATA_ADAPT_LAG': 2})
        plain = model_configuration('IQ3_XXS', 'tuned', self.root)
        self.assertEqual(plain['args'], ['--spec', '4', '--expert-profile', 'shipped'])
        self.assertEqual(plain['engine_environment'], {'STRATA_PREFILL_CPU_SHARE': 'auto', 'STRATA_ADAPT_LAG': 2})
        self.assertEqual(model_configuration('Q2_0', 'tuned', self.root, condition),
                         model_configuration('Q2_0', 'tuned', self.root))
        public = json.loads(source_bytes('config/deployment.json', 'tuned', self.root, condition))
        self.assertEqual(public['deployment_condition'], 'trial')
        self.assertNotIn('deployment_condition', json.loads(source_bytes('config/deployment.json', 'tuned', self.root)))
        for bad in ({**condition, 'model': 'IQ2_XS'}, {**condition, 'model_environment': {'PATH': 'x'}},
                    {**condition, 'extra': 1}):
            with self.assertRaisesRegex(ValueError, 'deployment condition'):
                load_host('tuned', self.root, bad)

    def test_condition_sampling_overlays_only_its_model(self):
        (self.root/'config/templates/iq3_xxs-prebuilt.json').write_text(
            json.dumps({'exe': 'x', 'port': 8100, 'args': []}), encoding='utf-8')
        self.host('tuned', models=['Q2_0', 'IQ3_XXS'], engine_overrides={},
                  installation_defaults={'reasoning_effort': 'high', 'temperature': 0.0, 'top_p': 1.0, 'top_k': 20})
        condition = {'id': 'sampling-t06', 'model': 'IQ3_XXS', 'request_defaults': {'temperature': 0.6, 'top_p': 0.95}}
        self.assertEqual(model_configuration('IQ3_XXS', 'tuned', self.root, condition)['request_defaults'],
                         {'reasoning_effort': 'high', 'temperature': 0.6, 'top_p': 0.95, 'top_k': 20})
        self.assertEqual(model_configuration('Q2_0', 'tuned', self.root, condition),
                         model_configuration('Q2_0', 'tuned', self.root))
        self.assertEqual(model_configuration('IQ3_XXS', 'tuned', self.root)['request_defaults']['temperature'], 0.0)
        for bad in ({'max_tokens': 1}, {'reasoning_effort': 'low'}, {'temperature': '0.6'}, []):
            with self.assertRaisesRegex(ValueError, 'deployment condition'):
                load_host('tuned', self.root, {**condition, 'request_defaults': bad})

    def test_public_outputs_never_carry_private_values(self):
        self.assertEqual(frontend_configuration('tuned', self.root),
                         {'listen_address': '192.168.60.212', 'port': 8000, 'model_port': 8100})
        public = source_bytes('config/deployment.json', 'tuned', self.root).decode('utf-8')
        for private in ('secret-sentinel', 'frontend_url', 'installation_root', '模型'):
            self.assertNotIn(private, public)

    def test_catalog_window_is_each_installed_models_default_tier(self):
        (self.root/'config').mkdir(exist_ok=True)
        catalog = {'models': [{'slug': 'qwen3.8-flash-next-q2_0', 'context_window': 1, 'max_context_window': 1},
                              {'slug': 'qwen3.8-flash-next-iq3_xxs', 'context_window': 1, 'max_context_window': 1}]}
        (self.root/'config/model-catalog.json').write_text(json.dumps(catalog), encoding='utf-8')
        rendered = json.loads(source_bytes('config/model-catalog.json', 'tuned', self.root))
        self.assertEqual([(m['context_window'], m['max_context_window']) for m in rendered['models']],
                         [(156584, 156584), (1, 1)])  # IQ3_XXS is not installed on this host
        with self.assertRaisesRegex(ValueError, 'no context tier for installed model Q2_0'):
            source_bytes('config/model-catalog.json', 'plain', self.root)

    def test_published_tier_reads_only_public_tiers_and_never_guesses(self):
        (self.root/'project.private.toml').unlink()
        self.assertEqual(published_tier('tuned', 'Q2_0', project=self.root),
                         {'context_window': 156584, 'auto_compact_token_limit': 100000})
        self.assertEqual(published_tier('tuned', 'Q2_0', 65536, self.root)['auto_compact_token_limit'], 40000)
        with self.assertRaisesRegex(ValueError, 'no 206584 tier'):
            published_tier('tuned', 'Q2_0', 206584, self.root)
        with self.assertRaisesRegex(ValueError, 'no context tier for Q2_0'):
            published_tier('plain', 'Q2_0', project=self.root)

    def test_old_schema_and_unknown_fields_are_rejected(self):
        self.host('old', schema_version=1)
        with self.assertRaisesRegex(ValueError, 'schema'):
            load_host('old', self.root)
        self.host('leaky', engine_overrides={}, password='x')
        with self.assertRaisesRegex(ValueError, 'Unknown deployment field'):
            load_host('leaky', self.root)


if __name__ == '__main__':unittest.main()
