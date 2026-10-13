import copy
import json
from pathlib import Path, PureWindowsPath
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.reviewer.arw_measure import capture_engine_log, log_offset, run
from tools.ops.measurement_host import MeasurementHost, host_selection


class MeasurementHostTests(unittest.TestCase):
    def remote(self):
        host=MeasurementHost.__new__(MeasurementHost)
        host.identifier='rtx3080ti'
        host.windows_root=PureWindowsPath('C:/strata')
        host.installation=Path('/mnt/c/strata')
        host.deployment={'hardware':{'vram_gib':12},'engine_overrides':{'prefill':8192},
                         'frontend_url':'http://192.168.0.4:8000'}
        return host

    def test_controller_uses_private_frontend_url_and_metadata_omits_it(self):
        host=self.remote()
        with patch('tools.ops.measurement_host.Controller') as controller:
            host.controller(Path('/tmp/measurement-test'))
        self.assertEqual(controller.call_args.kwargs['base_url'],'http://192.168.0.4:8000')
        self.assertNotIn('192.168.0.4',json.dumps(host.metadata()))

    def test_host_selection_freezes_hardware_without_mutating_approved_source(self):
        source={'engine_overrides':{'prefill':16384,'spec-min-p':.7},'sampling':{'temperature':0}}
        before=copy.deepcopy(source)
        with patch('tools.ops.measurement_host.load_host',return_value=self.remote().deployment):
            result=host_selection(source,'rtx3080ti')
        self.assertEqual(source,before)
        self.assertEqual(result['engine_overrides'],{'prefill':8192,'spec-min-p':.7})
        self.assertEqual(result['sampling'],source['sampling'])
        self.assertEqual(result['host_id'],'rtx3080ti')
        with patch('tools.ops.measurement_host.load_host',return_value=self.remote().deployment):
            owned=host_selection({'model_owner':'arw','engine_overrides':{}},'rtx3080ti')
        self.assertEqual(owned['engine_overrides'],{})  # ARW starts the model with installation defaults

    def test_smoke_baseline_retains_host_overrides_and_generation_budget(self):
        host=self.remote();host.deployment['engine_overrides']['pool-affinity']='all'
        source={'start_options':{'engine_overrides':{'prefill':16384,'pool-affinity':'auto','max-context':156584},
                                'request_defaults':{'reasoning_effort':'high','max_tokens':24576}}}
        before=copy.deepcopy(source);rendered=host.maintenance_baseline(source)
        self.assertEqual(source,before)
        self.assertEqual(rendered['start_options']['engine_overrides'],
                         {'prefill':8192,'pool-affinity':'all','max-context':156584})
        self.assertEqual(rendered['start_options']['request_defaults'],source['start_options']['request_defaults'])

    def test_smoke_profile_rejects_another_installation_path(self):
        host=self.remote()
        baseline={'profile':{'installation_relative_path':'profiles/default.json','sha256':'known','save_enabled':False}}
        good={'args':['--expert-profile','C:/strata/profiles/default.json'],'expert_profile_save':False}
        with patch.object(host,'configuration',return_value=good),patch.object(host,'profile_sha256',return_value='known'),patch.object(host,'read_deployed_bytes',return_value=b'config'):
            self.assertEqual(host.maintenance_profile_binding(baseline)['profile'],baseline['profile'])
        bad={**good,'args':['--expert-profile','C:/other-host/profiles/default.json']}
        with patch.object(host,'configuration',return_value=bad),self.assertRaisesRegex(ValueError,'binding differs'):
            host.maintenance_profile_binding(baseline)

    def test_unbound_main_selection_is_rejected_before_model_work(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'run'
            with patch('tools.ops.measurement_host.MeasurementHost',return_value=self.remote()),self.assertRaisesRegex(ValueError,'not frozen'):
                run(None,target,{'engine_overrides':{'prefill':16384}},[],Path('/unused'),host='rtx3080ti')
            self.assertFalse(target.exists())

    def test_target_configuration_is_verified_not_used_as_source(self):
        host=self.remote()
        expected={'args':['--prefill','8192'],'log':'C:/strata/logs/q2.log'}
        with patch('tools.ops.measurement_host.model_configuration',return_value=expected),patch.object(host,'read_deployed_bytes',return_value=json.dumps({**expected,'args':['--prefill','16384']}).encode()),self.assertRaisesRegex(RuntimeError,'differs'):
            host.configuration('Q2_0')

    def test_private_paths_cannot_be_read_via_public_deployment_reader(self):
        host=self.remote()
        for relative in ('.state/ownership.json','installation.private.toml'):
            with self.assertRaises(ValueError):
                host.read_deployed_bytes(relative)

    def test_log_access_reads_only_bytes_after_offset(self):
        host=self.remote()
        with tempfile.TemporaryDirectory() as directory:
            log=Path(directory)/'q2.log';log.write_bytes(b'before|after')
            with patch.object(host,'log_path',return_value=log):
                self.assertEqual(host.log_offset('Q2_0'),12)
                self.assertEqual(host.log_bytes_since('Q2_0',7),b'after')
                with self.assertRaisesRegex(RuntimeError,'shrank'):host.log_bytes_since('Q2_0',13)
        with self.assertRaises(ValueError):host.log_bytes_since('Q2_0',-1)

    def test_driver_uses_host_internal_tokens_and_phase_times(self):
        host=self.remote()
        raw=b'strata serve: prompt 150 tokens = 30 reused + 120 read in 10 ms, 7 generated in 3 ms\n'
        with tempfile.TemporaryDirectory() as directory,patch.object(host,'log_offset',return_value=37),patch.object(host,'log_bytes_since',return_value=raw) as read,patch('tools.reviewer.arw_measure.subprocess.check_output',side_effect=AssertionError('Wrong host path access')):
            self.assertEqual(log_offset(host.installation,'Q2_0',host),37)
            stages,tokens=capture_engine_log(host.installation,'Q2_0',37,Path(directory),host)
            self.assertEqual(tokens,{'uncached_input':120,'cached_input':30,'output':7})
            self.assertEqual(stages[0]['prompt_ms'],10)
            self.assertEqual((Path(directory)/'engine-request-log.txt').read_bytes(),raw)
            read.assert_called_once_with('Q2_0',37)


    def test_preflight_reports_a_resident_model_instead_of_assuming_stopped(self):
        from tools.ops import measurement_host
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)/'preflight'
            class Host:
                def __init__(self,*a,**k):self.deployment={'models':[]}
                def verify_sources(self):return {'files':[]}
                def controller(self,folder):
                    class C:
                        def call(self,path,timeout):return {'lease':'free','model':'qwen3.8-flash-next-iq3_xxs'}
                    return C()
            with patch.object(measurement_host,'MeasurementHost',Host),\
                 patch('sys.argv',['measurement_host','--host','rtx3080ti','--out',str(out)]),\
                 patch('builtins.print'):
                measurement_host.main()
            receipt=json.loads((out/'preflight.json').read_text())
        self.assertEqual(receipt['resident_model'],'qwen3.8-flash-next-iq3_xxs')
        self.assertNotIn('model_started',receipt)

if __name__=='__main__':unittest.main()
