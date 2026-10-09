import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import controller_backend


class StartupBoundaryTests(unittest.TestCase):
    def test_installation_defaults_apply_without_options_and_explicit_choices_win(self):
        value=json.loads(self.original)
        value.update(request_defaults={'reasoning_effort':'high','reasoning_budget_tokens':8192,'max_tokens':24576},
                     engine_environment={'STRATA_PREFILL_CPU_SHARE':'auto'})
        self.path.write_text(json.dumps(value))
        _,default=self.backend._configuration({})
        self.assertEqual(default['_request_defaults'],value['request_defaults'])
        self.assertEqual(default['_engine_environment'],value['engine_environment'])
        self.assertNotIn('request_defaults',default)
        _,override=self.backend._configuration({'request_defaults':{'reasoning_effort':'low'},
                                               'engine_environment':{'STRATA_PREFILL_CPU_SHARE':0}})
        self.assertEqual(override['_request_defaults'],{'reasoning_effort':'low'})
        self.assertEqual(override['_engine_environment'],{'STRATA_PREFILL_CPU_SHARE':0})
        with self.assertRaises(ValueError):self.backend._configuration({'request_defaults':{'max_tokens':8192}})

    def test_cpu_prefill_share_is_explicit_and_does_not_expand_other_environment_values(self):
        for value in (0,'auto',None):
            _,config=self.backend._configuration({'engine_environment':{'STRATA_PREFILL_CPU_SHARE':value}})
            self.assertEqual(config['_engine_environment'],{'STRATA_PREFILL_CPU_SHARE':value})
        for value in (True,False,0.0,1,'0','AUTO','auto ',[],{}):
            with self.assertRaises(ValueError):
                self.backend._configuration({'engine_environment':{'STRATA_PREFILL_CPU_SHARE':value}})
        for name in ('STRATA_HC_SPLIT','STRATA_ADAPT_NOWAIT','STRATA_BATCH_TRACE'):
            with self.assertRaises(ValueError):
                self.backend._configuration({'engine_environment':{name:'auto'}})
        self.assertEqual(self.path.read_text(),self.original)

    def test_loop_only_selection_keeps_other_startup_instructions_and_rejects_coercion(self):
        _,normal=self.backend._configuration({})
        self.assertTrue(normal['_loop_prevention_instructions_enabled'])
        _,diagnostic=self.backend._configuration({'loop_prevention_instructions':False})
        self.assertTrue(diagnostic['_startup_instructions_enabled'])
        self.assertFalse(diagnostic['_loop_prevention_instructions_enabled'])
        self.assertEqual(self.path.read_text(),self.original)
        for invalid in (0,1,None,'false'):
            with self.assertRaises(ValueError):self.backend._configuration({'loop_prevention_instructions':invalid})

    def test_startup_prompt_diagnostic_selection_is_explicit_and_baseline_is_preserved(self):
        _,normal=self.backend._configuration({})
        self.assertTrue(normal['_startup_instructions_enabled'])
        _,diagnostic=self.backend._configuration({'startup_instructions':False,'engine_environment':{'STRATA_BATCH_TRACE':1}})
        self.assertFalse(diagnostic['_startup_instructions_enabled'])
        self.assertEqual(diagnostic['_engine_environment'],{'STRATA_BATCH_TRACE':1})
        self.assertEqual(self.path.read_text(),self.original)
        for invalid in (0,1,None,'false'):
            with self.assertRaises(ValueError):self.backend._configuration({'startup_instructions':invalid})
        with self.assertRaises(ValueError):self.backend._configuration({'engine_environment':{'STRATA_BATCH_TRACE':0}})

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/'config').mkdir();self.path=self.root/'config/q2_0-prebuilt.json'
        self.original=json.dumps({'args':['--expert-profile','default.bin','--prefill','16384','--pool-workers','23']})
        self.path.write_text(self.original)
        self.override=patch.object(controller_backend,'ROOT',self.root);self.override.start()
        self.backend=controller_backend.Backend.__new__(controller_backend.Backend)

    def tearDown(self): self.override.stop();self.temp.cleanup()

    def test_caller_cannot_select_executable_or_pass_arbitrary_engine_flags(self):
        for options in ({'exe':'other-program'}, {'engine_overrides':{'native':'other.gguf'}},
                        {'engine_overrides':{'pool-workers':True}}, {'engine_overrides':{'pool-workers':8.0}},
                        {'engine_overrides':None}):
            with self.assertRaises(ValueError):self.backend._configuration(options)
        self.assertEqual(self.path.read_text(),self.original)

    def test_model_switch_reloads_target_preset_and_drops_previous_overrides(self):
        presets = {
            'Q2_0': (700, 'high', 8192, 24576, 'auto'),
            'IQ2_XS': (500, 'medium', 4096, 16384, 0),
            'IQ3_XXS': (981, 'low', 2048, 8192, None),
        }
        originals = {}
        for model, (reserve, effort, thinking, output, cpu_share) in presets.items():
            value = {'args': ['--vram-reserve-mib', str(reserve)],
                     'request_defaults': {'reasoning_effort': effort,
                                          'reasoning_budget_tokens': thinking, 'max_tokens': output}}
            if cpu_share is not None:
                value['engine_environment'] = {'STRATA_PREFILL_CPU_SHARE': cpu_share}
            path = self.root/'config'/(model.lower()+'-prebuilt.json')
            path.write_text(json.dumps(value)); originals[path] = path.read_bytes()
        _, overridden = self.backend._configuration({'model': 'Q2_0',
            'engine_overrides': {'vram-reserve-mib': 1200},
            'request_defaults': {'reasoning_effort': 'low'},
            'engine_environment': {'STRATA_PREFILL_CPU_SHARE': 0}})
        self.assertEqual(overridden['args'][1], '1200')
        for model in ('IQ2_XS', 'IQ3_XXS', 'Q2_0'):
            selected, value = self.backend._configuration({'model': model})
            reserve, effort, thinking, output, cpu_share = presets[model]
            self.assertEqual(selected, model)
            self.assertEqual(value['args'][1], str(reserve))
            self.assertEqual(value['_request_defaults'], {'reasoning_effort': effort,
                'reasoning_budget_tokens': thinking, 'max_tokens': output})
            self.assertEqual(value['_engine_environment'], {} if cpu_share is None else
                {'STRATA_PREFILL_CPU_SHARE': cpu_share})
        for path, original in originals.items():
            self.assertEqual(path.read_bytes(), original)

    def test_profile_traversal_and_symlink_escape_are_rejected(self):
        folder=self.root/'data/profiles';folder.mkdir(parents=True)
        outside=self.root/'outside.bin';outside.write_bytes(b'outside')
        (folder/'escape.bin').symlink_to(outside)
        for path in (str(outside),str(folder/'../outside.bin'),str(folder/'escape.bin'),'relative.bin'):
            with self.assertRaises(ValueError):self.backend._configuration({'profile_file':path})

    def test_supported_override_and_profile_do_not_rewrite_baseline(self):
        folder=self.root/'data/profiles';folder.mkdir(parents=True)
        profile=folder/'review.bin';profile.write_bytes(b'profile')
        model,value=self.backend._configuration({'engine_overrides':{'prefill':4096},'profile_file':str(profile)})
        self.assertEqual(model,'Q2_0');self.assertEqual(value['args'][value['args'].index('--prefill')+1],'4096')
        self.assertEqual(value['args'][value['args'].index('--expert-profile')+1],str(profile))
        self.assertEqual(self.path.read_text(),self.original)

    def test_extended_flags_and_request_defaults_remain_scoped(self):
        _,value=self.backend._configuration({'engine_overrides':{'adapt-every':2,'expert-cache-per-layer':True},
            'request_defaults':{'temperature':.3,'reasoning_effort':'medium','max_tokens':8192},
            'engine_environment':{'STRATA_HC_SPLIT':0}})
        self.assertIn('--expert-cache-per-layer',value['args'])
        self.assertEqual(value['_engine_environment'],{'STRATA_HC_SPLIT':0})
        self.assertEqual(self.path.read_text(),self.original)
        for options in ({'engine_environment':{'PATH':'other'}}, {'engine_environment':{'STRATA_HC_SPLIT':True}},
            {'request_defaults':{'max_tokens':8192}}, {'request_defaults':{'temperature':True}},
            {'request_defaults':{'top_k':1.5}}, {'engine_overrides':{'expert-cache':5000.0}},
            {'engine_overrides':{'expert-cache-per-layer':'true'}}):
            with self.assertRaises(ValueError):self.backend._configuration(options)

    def test_capacity_candidates_are_integer_and_leave_baseline_untouched(self):
        for capacity in (80000,125000,188000,250000,120584,156584,206584,256584):
            _,config=self.backend._configuration({'engine_overrides':{'max-context':capacity}})
            self.assertEqual(config['args'][config['args'].index('--max-context')+1],str(capacity))
        for invalid in (True,125000.0,124999,'125000',None):
            with self.assertRaises(ValueError):
                self.backend._configuration({'engine_overrides':{'max-context':invalid}})
        self.assertEqual(self.path.read_text(),self.original)

    def test_native_output_fitting_is_explicit_boolean_and_does_not_rewrite_baseline(self):
        _,default=self.backend._configuration({})
        self.assertNotIn('fit_max_tokens',default)
        for enabled in (True,False):
            _,config=self.backend._configuration({'fit_max_tokens':enabled})
            self.assertIs(config['fit_max_tokens'],enabled)
            self.assertEqual(self.path.read_text(),self.original)
        for invalid in (1,0,'true',None,{}):
            with self.assertRaises(ValueError):
                self.backend._configuration({'fit_max_tokens':invalid})


if __name__=='__main__':unittest.main()
