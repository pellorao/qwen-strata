"""Generated deployments use project/private host inputs without leaking credentials."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.ops.deployment_source import (HOST_ENVIRONMENT, current_host, require_current_host,
                                         frontend_configuration, load_host, model_configuration, published_tier,
                                         served_model, source_bytes, render_manual, wsl_path, MANUAL, MANUAL_HOSTS)
import hashlib
import shutil


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

    def test_presence_penalty_is_an_installation_default(self):
        self.host('tuned', engine_overrides={}, installation_defaults={
            'reasoning_effort': 'high', 'temperature': 0.0, 'top_p': 1.0, 'top_k': 20, 'presence_penalty': 0.0})
        self.assertEqual(model_configuration('Q2_0', 'tuned', self.root)['request_defaults'],
                         {'reasoning_effort': 'high', 'temperature': 0.0, 'top_p': 1.0, 'top_k': 20,
                          'presence_penalty': 0.0})
        # The whitelist grows by this key only: other sampling keys still need a reason to become host defaults
        self.host('tuned', engine_overrides={}, installation_defaults={'min_p': 0.0})
        with self.assertRaisesRegex(ValueError, 'installation defaults'):
            model_configuration('Q2_0', 'tuned', self.root)

    def test_context_tiers_need_a_compaction_limit_inside_the_window(self):
        self.host('tuned', engine_overrides={}, context_tiers={'Q2_0': [{'context_window': 65536, 'auto_compact_token_limit': 65536}]})
        with self.assertRaisesRegex(ValueError, 'context_tiers'):
            model_configuration('Q2_0', 'tuned', self.root)

    def iq3_template(self, args):
        (self.root/'config/templates/iq3_xxs-prebuilt.json').write_text(
            json.dumps({'exe': 'x', 'port': 8100, 'args': args}), encoding='utf-8')

    def test_a_host_serves_exactly_one_known_model(self):
        for models in (['Q2_0', 'IQ3_XXS'], [], ['Q8'], 'Q2_0'):
            self.host('stray', engine_overrides={}, models=models)
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                load_host('stray', self.root)
        self.assertEqual(served_model('tuned', self.root), 'Q2_0')
        (self.root/'project.private.toml').unlink()  # the public host file alone names it
        self.assertEqual(served_model('plain', self.root), 'Q2_0')

    def test_unserved_model_data_stays_unpublished(self):
        """Overrides, environment and tiers of installed but unserved models stay in the host file only."""
        self.iq3_template(['--prefill', '512'])
        self.host('tuned', models=['IQ3_XXS'], engine_overrides={'prefill': 8192},
                  model_overrides={'Q2_0': {'vram-reserve-mib': 512}, 'IQ3_XXS': {'spec': 4}},
                  model_environment={'Q2_0': {'STRATA_ADAPT_LAG': 1}, 'IQ3_XXS': {'STRATA_ADAPT_LAG': 2}},
                  context_tiers={'Q2_0': [{'context_window': 156584, 'auto_compact_token_limit': 100000}],
                                 'IQ3_XXS': [{'context_window': 206584, 'auto_compact_token_limit': 150000}]})
        served = model_configuration('IQ3_XXS', 'tuned', self.root)
        self.assertEqual(served['args'], ['--prefill', '8192', '--spec', '4', '--max-context', '206584'])
        self.assertEqual(served['engine_environment'], {'STRATA_ADAPT_LAG': 2})
        with self.assertRaisesRegex(ValueError, 'not registered'):
            model_configuration('Q2_0', 'tuned', self.root)
        public = json.loads(source_bytes('config/deployment.json', 'tuned', self.root))
        self.assertEqual(public['models'], ['IQ3_XXS'])
        for field in ('model_overrides', 'model_environment', 'context_tiers'):
            self.assertEqual(list(public[field]), ['IQ3_XXS'], field)
        with self.assertRaisesRegex(ValueError, 'not registered'):
            source_bytes('config/templates/q2_0-prebuilt.json', 'tuned', self.root)

    def test_model_overrides_apply_only_to_that_model(self):
        self.iq3_template(['--prefill', '512'])
        self.host('tuned', models=['IQ3_XXS'], engine_overrides={'prefill': 8192},
                  model_overrides={'Q2_0': {'vram-reserve-mib': 512}})
        self.assertEqual(model_configuration('IQ3_XXS', 'tuned', self.root)['args'], ['--prefill', '8192'])
        self.host('tuned', models=['IQ3_XXS'], engine_overrides={}, model_overrides={'IQ3_XXS': {'prefill': None}})
        self.assertEqual(model_configuration('IQ3_XXS', 'tuned', self.root)['args'], [])
        self.host('stray', engine_overrides={}, model_overrides={'Q8': {'vram-reserve-mib': 512}})
        with self.assertRaisesRegex(ValueError, 'model_overrides'):
            load_host('stray', self.root)

    def test_model_environment_applies_only_to_that_model(self):
        self.iq3_template([])
        self.host('tuned', models=['IQ3_XXS'], engine_overrides={},
                  model_environment={'IQ3_XXS': {'STRATA_ADAPT_LAG': 2}})
        self.assertEqual(model_configuration('IQ3_XXS', 'tuned', self.root)['engine_environment']['STRATA_ADAPT_LAG'], 2)
        self.host('tuned', engine_overrides={}, model_environment={'IQ3_XXS': {'STRATA_ADAPT_LAG': 2}})
        self.assertNotIn('STRATA_ADAPT_LAG', model_configuration('Q2_0', 'tuned', self.root).get('engine_environment', {}))
        self.host('stray', engine_overrides={}, model_environment={'Q8': {'STRATA_ADAPT_LAG': 2}})
        with self.assertRaisesRegex(ValueError, 'model_environment'):
            load_host('stray', self.root)

    def test_condition_overlays_the_served_model_until_a_plain_render(self):
        self.iq3_template(['--spec', '4', '--expert-profile', 'shipped'])
        self.host('tuned', models=['IQ3_XXS'], engine_overrides={},
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
        public = json.loads(source_bytes('config/deployment.json', 'tuned', self.root, condition))
        self.assertEqual(public['deployment_condition'], 'trial')
        self.assertNotIn('deployment_condition', json.loads(source_bytes('config/deployment.json', 'tuned', self.root)))
        # An unserved quantization is not a condition model (multi-model conditions are not implemented)
        for bad in ({**condition, 'model': 'Q2_0'}, {**condition, 'model_environment': {'PATH': 'x'}},
                    {**condition, 'extra': 1}):
            with self.assertRaisesRegex(ValueError, 'deployment condition'):
                load_host('tuned', self.root, bad)

    def test_condition_sampling_overlays_only_the_condition(self):
        self.iq3_template([])
        self.host('tuned', models=['IQ3_XXS'], engine_overrides={},
                  installation_defaults={'reasoning_effort': 'high', 'temperature': 0.0, 'top_p': 1.0, 'top_k': 20})
        condition = {'id': 'sampling-t06', 'model': 'IQ3_XXS', 'request_defaults': {'temperature': 0.6, 'top_p': 0.95, 'min_p': 0.0, 'presence_penalty': 0.0}}
        self.assertEqual(model_configuration('IQ3_XXS', 'tuned', self.root, condition)['request_defaults'],
                         {'reasoning_effort': 'high', 'temperature': 0.6, 'top_p': 0.95, 'top_k': 20,
                          'min_p': 0.0, 'presence_penalty': 0.0})
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

    def test_installed_catalog_lists_only_the_served_model_with_its_default_tier(self):
        (self.root/'config').mkdir(exist_ok=True)
        catalog = {'models': [{'slug': 'qwen3.8-flash-next-q2_0', 'context_window': 1, 'max_context_window': 1},
                              {'slug': 'qwen3.8-flash-next-iq3_xxs', 'context_window': 1, 'max_context_window': 1}]}
        (self.root/'config/model-catalog.json').write_text(json.dumps(catalog), encoding='utf-8')
        rendered = json.loads(source_bytes('config/model-catalog.json', 'tuned', self.root))
        self.assertEqual([(m['slug'], m['context_window'], m['max_context_window']) for m in rendered['models']],
                         [('qwen3.8-flash-next-q2_0', 156584, 156584)])
        with self.assertRaisesRegex(ValueError, 'no context tier for served model Q2_0'):
            source_bytes('config/model-catalog.json', 'plain', self.root)
        self.host('stray', engine_overrides={}, models=['IQ2_XS'],
                  context_tiers={'IQ2_XS': [{'context_window': 156584, 'auto_compact_token_limit': 100000}]})
        with self.assertRaisesRegex(ValueError, 'catalog needs one entry'):
            source_bytes('config/model-catalog.json', 'stray', self.root)

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


class CurrentHostTests(unittest.TestCase):
    """One project copy per machine (user 2026-10-24): the copy knows which registered host it runs on."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'config/deployments').mkdir(parents=True)
        for identifier in ('rtx3080ti', 'rtx4070tis'):
            (self.root/'config/deployments'/(identifier+'.json')).write_text('{}', encoding='utf-8')
        environment = mock.patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop(HOST_ENVIRONMENT, None)

    def private(self, text):
        (self.root/'project.private.toml').write_text(text, encoding='utf-8')

    def test_without_a_choice_the_host_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'names no host'):
            current_host(self.root)
        self.private('[hosts.rtx3080ti]\ninstallation_path = "C:\\\\x"\n')
        with self.assertRaisesRegex(ValueError, 'names no host'):
            current_host(self.root)

    def test_private_file_names_this_machine(self):
        self.private('local_host = "rtx4070tis"\n[hosts.rtx4070tis]\ninstallation_path = "C:\\\\x"\n')
        self.assertEqual(current_host(self.root), 'rtx4070tis')

    def test_environment_overrides_the_private_file(self):
        self.private('local_host = "rtx4070tis"\n')
        os.environ[HOST_ENVIRONMENT] = 'rtx3080ti'
        self.assertEqual(current_host(self.root), 'rtx3080ti')

    def test_unregistered_or_invalid_host_is_refused(self):
        for value in ('rtx9999', '../rtx3080ti', 'RTX3080TI'):
            os.environ[HOST_ENVIRONMENT] = value
            with self.assertRaisesRegex(ValueError, 'not registered'):
                current_host(self.root)
        os.environ.pop(HOST_ENVIRONMENT)
        self.private('local_host = 1\n')
        with self.assertRaisesRegex(ValueError, 'not registered'):
            current_host(self.root)

    def test_installation_work_only_targets_this_machine(self):
        self.private('local_host = "rtx4070tis"\n')
        self.assertEqual(require_current_host('rtx4070tis', self.root), 'rtx4070tis')
        with self.assertRaisesRegex(ValueError, 'not this machine'):
            require_current_host('rtx3080ti', self.root)


REAL_ROOT = Path(__file__).resolve().parents[1]
# SHA-256 of the README deployed on rtx3080ti when the manual became a host template (2026-10-24); the render must keep
# it byte for byte. A deliberate manual change updates this pin together with the deployment.
DEPLOYED_MANUAL_SHA256 = '315df23f08038392d2424e7548fdc4178d6199e24c941be185b4a42a3f7508b6'


class ManualRenderingTests(unittest.TestCase):
    """The caller manual is rendered per host from the template, the host file and the host's own paragraphs."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'docs').mkdir()
        shutil.copytree(REAL_ROOT/'config/deployments', self.root/'config/deployments')
        shutil.copyfile(REAL_ROOT/MANUAL, self.root/MANUAL)
        shutil.copytree(REAL_ROOT/MANUAL_HOSTS, self.root/MANUAL_HOSTS)
        (self.root/'project.private.toml').write_text(
            "[hosts.rtx3080ti]\ninstallation_path = 'C:\\Users\\pello\\AppData\\Local\\Programs\\qwen-3.8-flash-next'\n"
            "[hosts.rtx4070tis]\ninstallation_path = 'C:\\Users\\pello\\AppData\\Local\\Programs\\qwen-3.8-flash-next'\n",
            encoding='utf-8')

    def test_rtx3080ti_renders_the_deployed_manual(self):
        rendered = render_manual('rtx3080ti', self.root).encode()
        self.assertEqual(hashlib.sha256(rendered).hexdigest(), DEPLOYED_MANUAL_SHA256)
        self.assertEqual(source_bytes(MANUAL, 'rtx3080ti', self.root), rendered)
        self.assertNotIn(b'{{', rendered)

    def test_values_follow_the_host_file(self):
        path = self.root/'config/deployments/rtx3080ti.json'
        value = json.loads(path.read_text(encoding='utf-8'))
        value.update(listen_address='10.0.0.9', port=8123)
        value['context_tiers']['IQ3_XXS'] = [{'context_window': 100000, 'auto_compact_token_limit': 70000}]
        path.write_text(json.dumps(value), encoding='utf-8')
        rendered = render_manual('rtx3080ti', self.root)
        self.assertIn('base_url = "http://10.0.0.9:8123/strata/v1"', rendered)
        self.assertIn('model_context_window = 100000\nmodel_auto_compact_token_limit = 70000', rendered)
        self.assertNotIn('192.168.60.212', rendered.split('## 已观察到的执行异常')[0])

    def test_host_without_its_data_or_paragraphs_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'lacks what the manual names: listen_address, port, context_tiers.IQ3_XXS'):
            render_manual('rtx4070tis', self.root)
        (self.root/MANUAL_HOSTS/'rtx3080ti.md').unlink()
        with self.assertRaisesRegex(ValueError, 'no manual paragraphs'):
            render_manual('rtx3080ti', self.root)

    def test_unknown_placeholder_is_refused(self):
        with (self.root/MANUAL).open('a', encoding='utf-8') as stream:
            stream.write('{{host.unwritten}}\n')
        with self.assertRaisesRegex(ValueError, 'host.unwritten'):
            render_manual('rtx3080ti', self.root)

    def test_wsl_path(self):
        self.assertEqual(wsl_path('C:\\Users\\pello\\x y'), '/mnt/c/Users/pello/x y')
        self.assertEqual(wsl_path('D:\\模型'), '/mnt/d/模型')
        for bad in ('\\\\server\\share\\x', 'relative\\x', 'C:x'):
            with self.assertRaises(ValueError):
                wsl_path(bad)


# Strata 0.2.4 serve/server.py MODEL_CARD_SAMPLING["qwen4exp"]: the keys it fills for a request when neither the request
# nor the run config's sampling block names them (the thinking-off set adds presence_penalty 1.5).
MODEL_CARD_KEYS = {'thinking': {'temperature', 'top_p', 'top_k'},
                   'instruct': {'temperature', 'top_p', 'top_k', 'presence_penalty'}}


class ProjectHostDefaultsTests(unittest.TestCase):
    def test_hosts_with_sampling_defaults_pin_every_model_card_key(self):
        """A host that sets its own sampling must set every key the model card would otherwise fill, or a
        thinking-off request silently gets the card's value (presence_penalty 1.5 under greedy)."""
        root = Path(__file__).resolve().parents[1]
        for path in sorted((root/'config/deployments').glob('*.json')):
            defaults = json.loads(path.read_text(encoding='utf-8')).get('installation_defaults', {})
            if not {'temperature', 'top_p', 'top_k'} & set(defaults):
                continue
            for mode, keys in MODEL_CARD_KEYS.items():
                with self.subTest(host=path.stem, mode=mode):
                    self.assertLessEqual(keys, set(defaults))


if __name__ == '__main__':unittest.main()
