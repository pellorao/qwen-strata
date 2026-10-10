import sys,json,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.tuning.resource_calibration import inspect_reply, experiment_schedule

class ResourceCalibrationTests(unittest.TestCase):
    def test_cpu_share_schedule_retains_only_approved_six_and_environment_change(self):
        root=Path(__file__).resolve().parents[1]
        plan=json.loads((root/'benchmarks/resource-calibration-v1/rtx3080ti-cpu-share-plan.json').read_text())
        jobs=experiment_schedule(plan)
        self.assertEqual(len(jobs),6)
        self.assertEqual({(x['condition'],x['repetition'])for x in jobs},{(c,r)for c in ['off','on']for r in [1,2,3]})
        for job in jobs:
            self.assertEqual(job['overrides'],{})
            self.assertEqual(job['environment'],{'STRATA_PREFILL_CPU_SHARE':0 if job['condition']=='off'else'auto'})
        plan['schedule'][1]=plan['schedule'][0]
        with self.assertRaises(ValueError):experiment_schedule(plan)

    def test_prefill_scope_retains_two_three_repeat_conditions(self):
        plan={'host':'rtx3080ti','candidate_dimension':'prefill','conditions':[8192,16384],
              'fixed_pool_affinity':'all','pool_workers':23,
              'schedule':[{'tokens':c,'repetition':r}for c in [8192,16384]for r in [1,2,3]]}
        jobs=experiment_schedule(plan)
        self.assertEqual(len(jobs),6)
        for job in jobs:self.assertEqual(job['overrides'],{'pool-affinity':'all','pool-workers':23,'prefill':job['condition']})
        plan['schedule'][1]=plan['schedule'][0]
        with self.assertRaises(ValueError):experiment_schedule(plan)
    def test_ple_scope_changes_only_io_mode_with_six_unique_observations(self):
        root=Path(__file__).resolve().parents[1]
        plan=json.loads((root/'benchmarks/resource-calibration-v1/rtx3080ti-ple-io-plan.json').read_text())
        jobs=experiment_schedule(plan)
        self.assertEqual(len(jobs),6)
        self.assertEqual({(j['condition'],j['repetition'])for j in jobs},{(m,r)for m in ['direct','mmap']for r in [1,2,3]})
        for job in jobs:self.assertEqual(job['overrides'],{'pool-affinity':'all','pool-workers':23,'ple-io':job['condition']})
        plan['schedule'][1]=plan['schedule'][0]
        with self.assertRaises(ValueError):experiment_schedule(plan)
    def test_worker_scope_has_nine_independent_three_repeat_conditions(self):
        root=Path(__file__).resolve().parents[1]
        plan=json.loads((root/'benchmarks/resource-calibration-v1/rtx3080ti-worker-plan.json').read_text())
        jobs=experiment_schedule(plan)
        self.assertEqual(len(jobs),9)
        self.assertEqual({(j['condition'],j['repetition'])for j in jobs},{(w,r)for w in [23,15,12]for r in [1,2,3]})
        self.assertTrue(all(j['overrides']['pool-affinity']=='all'for j in jobs))
        plan['schedule'][1]=plan['schedule'][0]
        with self.assertRaises(ValueError):experiment_schedule(plan)
    def test_vram_reserve_scope_has_nine_observations_changing_only_reserve(self):
        root=Path(__file__).resolve().parents[1]
        plan=json.loads((root/'benchmarks/resource-calibration-v1/rtx3080ti-vram-reserve-plan.json').read_text())
        jobs=experiment_schedule(plan)
        self.assertEqual(len(jobs),9)
        self.assertEqual({(j['condition'],j['repetition'])for j in jobs},{(v,r)for v in [1024,768,512]for r in [1,2,3]})
        for job in jobs:self.assertEqual(job['overrides'],{'pool-affinity':'all','pool-workers':23,'vram-reserve-mib':job['condition']})
        plan['conditions']=[1024,768,256]
        with self.assertRaises(ValueError):experiment_schedule(plan)
    def reply(self,value,raw=False):return {'choices':[{'finish_reason':'stop','message':{'content':value if raw else json.dumps(value)}}]}
    def test_complete_wrong_answer_is_not_retried(self):
        result=inspect_reply(self.reply([{'id':'x','available':8}]),[{'id':'x','available':9}])
        self.assertTrue(result['complete']);self.assertFalse(result['pass'])
    def test_native_boolean_is_not_accepted_as_integer(self):
        result=inspect_reply(self.reply([{'active':1}]),[{'active':True}])
        self.assertTrue(result['complete']);self.assertFalse(result['pass'])
    def test_partial_and_progress_messages_require_continuation(self):
        expected=[{'id':'a'},{'id':'b'}]
        for value,raw in [([{'id':'a'}],False),('I will continue checking.',True)]:
            self.assertFalse(inspect_reply(self.reply(value,raw),expected)['complete'])
        self.assertTrue(inspect_reply(self.reply(expected),expected)['pass'])
    def test_complete_wrong_wrapper_is_final_format_failure(self):
        result=inspect_reply(self.reply({'rows':[{'id':'a'}]}),[{'id':'a'}])
        self.assertTrue(result['complete']);self.assertFalse(result['pass'])
    def test_complete_fenced_array_does_not_trigger_a_retry(self):
        expected=[{'id':'a'}]
        result=inspect_reply(self.reply('```json\n'+json.dumps(expected)+'\n```',True),expected)
        self.assertTrue(result['complete']);self.assertFalse(result['pass'])

if __name__=='__main__':unittest.main()
