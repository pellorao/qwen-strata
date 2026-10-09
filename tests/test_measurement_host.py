import base64
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
        host.identifier='rtx3080ti';host.remote=True
        host.windows_root=PureWindowsPath('C:/strata')
        host.installation=Path(str(host.windows_root))
        host.settings={'api_base_url':'http://192.168.0.4:28000','STRATA_REMOTE_PASSWORD':'private-test-value'}
        host.deployment={'transport':'ssh-windows','hardware':{'vram_gib':12},
                         'engine_overrides':{'prefill':8192}}
        return host

    def test_remote_controller_uses_external_port_without_local_launcher(self):
        host=self.remote()
        with patch('tools.ops.measurement_host.Controller') as controller:
            host.controller(Path('/tmp/measurement-test'))
        self.assertEqual(controller.call_args.kwargs['base_url'],'http://192.168.0.4:28000')
        self.assertNotIn('private-test-value',json.dumps(host.metadata()))
        self.assertNotIn('settings',host.metadata())

    def test_host_selection_freezes_hardware_without_mutating_approved_source(self):
        source={'engine_overrides':{'prefill':16384,'spec-min-p':.7},'sampling':{'temperature':0}}
        before=copy.deepcopy(source)
        with patch('tools.ops.measurement_host.load_host',return_value=self.remote().deployment):
            result=host_selection(source,'rtx3080ti')
        self.assertEqual(source,before)
        self.assertEqual(result['engine_overrides'],{'prefill':8192,'spec-min-p':.7})
        self.assertEqual(result['sampling'],source['sampling'])
        self.assertEqual(result['host_id'],'rtx3080ti')

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

    def test_unbound_main_selection_is_rejected_before_remote_model_work(self):
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
        with patch.object(host,'_remote') as remote,self.assertRaises(ValueError):
            host.read_deployed_bytes('.state/ownership.json')
        remote.assert_not_called()

    def test_remote_search_receipt_uses_bound_remote_path(self):
        host=self.remote();digest='a'*64;call='wc_'+'b'*32;record={'result':{'results':[]}}
        with patch.object(host,'_remote',return_value=record) as remote:
            self.assertEqual(host.read_search_operation(digest,call),record)
        self.assertEqual(remote.call_args.args[1],('C:\\strata','.state/search/'+digest+'/'+call+'.json'))
        with patch.object(host,'_remote') as remote,self.assertRaises(ValueError):
            host.read_search_operation('../ownership','wc_'+'b'*32)
        remote.assert_not_called()

    def test_remote_log_access_never_translates_remote_paths_as_local_wsl(self):
        host=self.remote();raw=b'actual remote engine segment'
        with patch.object(host,'configuration',return_value={'log':'C:/strata/logs/q2.log'}),patch.object(host,'_remote',side_effect=[{'size':37},{'data':base64.b64encode(raw).decode()}]),patch('tools.ops.measurement_host.subprocess.check_output',side_effect=AssertionError('Remote WSL path translation')):
            self.assertEqual(host.log_offset('Q2_0'),37)
            self.assertEqual(host.log_bytes_since('Q2_0',37),raw)
        with self.assertRaises(ValueError):host.log_bytes_since('Q2_0',-1)

    def test_driver_uses_remote_internal_tokens_and_phase_times(self):
        host=self.remote()
        raw=b'strata serve: prompt 150 tokens = 30 reused + 120 read in 10 ms, 7 generated in 3 ms\n'
        with tempfile.TemporaryDirectory() as directory,patch.object(host,'log_offset',return_value=37),patch.object(host,'log_bytes_since',return_value=raw) as read,patch('tools.reviewer.arw_measure.subprocess.check_output',side_effect=AssertionError('Wrong host path access')):
            self.assertEqual(log_offset(host.installation,'Q2_0',host),37)
            stages,tokens=capture_engine_log(host.installation,'Q2_0',37,Path(directory),host)
            self.assertEqual(tokens,{'uncached_input':120,'cached_input':30,'output':7})
            self.assertEqual(stages[0]['prompt_ms'],10)
            self.assertEqual((Path(directory)/'engine-request-log.txt').read_bytes(),raw)
            read.assert_called_once_with('Q2_0',37)


if __name__=='__main__':unittest.main()
