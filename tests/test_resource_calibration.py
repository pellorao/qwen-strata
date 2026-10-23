import sys,json,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import importlib.util,tempfile,hashlib
from tools.tuning.resource_calibration import inspect_reply, classify_rows, experiment_schedule, frozen_inputs, load_facts, kv_facts, disk_read_delta
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('ple_workload',ROOT/'benchmarks/resource-calibration-v1/ple_workload.py')
ple_workload=importlib.util.module_from_spec(spec);spec.loader.exec_module(ple_workload)
spec=importlib.util.spec_from_file_location('calibration_workload',ROOT/'benchmarks/resource-calibration-v1/workload.py')
calibration_workload=importlib.util.module_from_spec(spec);spec.loader.exec_module(calibration_workload)
FAKE_VOCAB={'Ġ'+''.join(chr(97+(i//26**k)%26)for k in range(4))+'q':i for i in range(26000)}

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
    def test_generic_conditions_carry_overrides_and_reject_gaps(self):
        plan={'host':'rtx3080ti','candidate_dimension':'pcie-frac','schema':'conditions-v2',
              'conditions':[{'id':'measured','overrides':{'pcie-frac':None}},{'id':'zero','overrides':{'pcie-frac':'0.00'}}],
              'schedule':[{'condition':c,'repetition':r}for r in(1,2,3)for c in('measured','zero')]}
        jobs=experiment_schedule(plan)
        self.assertEqual(len(jobs),6);self.assertEqual(jobs[0]['overrides'],{'pcie-frac':None})
        self.assertEqual(jobs[1]['label'],'zero-r1')
        plan['schedule']=plan['schedule'][:-1]
        with self.assertRaises(ValueError):experiment_schedule(plan)
        plan['conditions'][0]={'id':'measured'}
        with self.assertRaises(ValueError):experiment_schedule(plan)
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

    def test_context_length_validation_may_run_one_default_condition(self):
        plan={'host':'rtx3080ti','candidate_dimension':'context-length','schema':'conditions-v2',
              'conditions':[{'id':'default-160k','overrides':{'max-context':206584}}],
              'schedule':[{'condition':'default-160k','repetition':r}for r in(1,2,3)]}
        self.assertEqual([j['label']for j in experiment_schedule(plan)],['default-160k-r1','default-160k-r2','default-160k-r3'])
        plan['candidate_dimension']='pcie-frac'
        with self.assertRaises(ValueError):experiment_schedule(plan)


class LongContextWorkloadTests(unittest.TestCase):
    def test_version1_is_unchanged_for_frozen_plans(self):
        plan=json.loads((ROOT/'benchmarks/resource-calibration-v1/iq3_xxs-night-2026-10-12/kv-long/plan-150k.json').read_text())
        workload=calibration_workload.build(3609)
        for case,binding in zip(workload['cases'],plan['workload']['case_bindings']):
            text=workload['shared_prefix']+case['question']
            self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),binding['user_text_sha256'])
            self.assertNotIn('alternatives',case)

    def test_version2_asks_distinguishable_same_label_pairs(self):
        workload=calibration_workload.build(3754,2);first=workload['cases'][0]
        ids=[r['id']for r in first['expected']];self.assertEqual(len(set(ids)),28)
        self.assertEqual(ids[0],'R00999');self.assertEqual(ids[14],'R01999')
        labels={json.loads(line)['id']:json.loads(line)['label']for line in workload['shared_prefix'].splitlines()if line.startswith('{')}
        for a,b in zip(ids[:14],ids[14:]):self.assertEqual(labels[a],labels[b])
        for want,alts in zip(first['expected'],first['alternatives']['same-label']):
            self.assertTrue(alts)
            for alt in alts:self.assertNotEqual({k:v for k,v in alt.items()if k!='id'},{k:v for k,v in want.items()if k!='id'})

    def test_version2_does_not_clamp_available(self):
        workload=calibration_workload.build(3754,2)
        for case in workload['cases'][1:]:
            self.assertIn('do not clamp',case['question'])
        self.assertTrue(any(r['available']<0 for r in workload['cases'][2]['expected']))

    def test_rows_name_same_label_confusion_and_other_errors(self):
        expected=[{'id':'R1','v':1},{'id':'R2','v':2},{'id':'R3','v':3},{'id':'R4','v':4}]
        alts={'same-label':[[{'id':'R1','v':9}],[{'id':'R2','v':8}],[],[]]}
        got=[{'id':'R1','v':9},{'id':'R2','v':5},{'id':'R3','v':3}]
        self.assertEqual(classify_rows(got,expected,alts),['same-label','other','ok','missing'])
        reply={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(got)}}]}
        self.assertEqual(inspect_reply(reply,expected,alts)['row_classes'][0],'same-label')

    def test_alternatives_are_bound_by_the_plan(self):
        workload=calibration_workload.build(2000,2)
        digest=lambda v:hashlib.sha256(v.encode()).hexdigest()
        bindings=[{'id':c['id'],'user_text_sha256':digest(workload['shared_prefix']+c['question']),
                   'expected_sha256':digest(json.dumps(c['expected'],sort_keys=True,separators=(',',':'))),
                   'alternatives_sha256':digest(json.dumps(c['alternatives'],sort_keys=True,separators=(',',':')))}
                  for c in workload['cases']]
        plan={'host':'rtx3080ti','candidate_dimension':'context-length','schema':'conditions-v2',
              'authorization':{'approved':True},'baseline':{'start_options':{'model':'IQ3_XXS'}},
              'conditions':[{'id':'d','overrides':{'max-context':206584}}],
              'schedule':[{'condition':'d','repetition':r}for r in(1,2,3)],'model_instances':3,'logical_requests':9,
              'source_sha256':{},'workload':{'case_bindings':bindings}}
        with tempfile.TemporaryDirectory()as folder:
            paths=[Path(folder)/'plan.json',Path(folder)/'workload.json']
            paths[0].write_text(json.dumps(plan));paths[1].write_text(json.dumps(workload))
            frozen_inputs(*paths)
            workload['cases'][0]['alternatives']['same-label'][0]=[]
            paths[1].write_text(json.dumps(workload))
            with self.assertRaises(ValueError):frozen_inputs(*paths)


class PleReadPathTests(unittest.TestCase):
    def plan(self,name):return json.loads((ROOT/f'benchmarks/resource-calibration-v1/rtx3080ti-iq3_xxs-{name}-plan.json').read_text())

    def test_each_repetition_reads_unseen_text_and_targets_are_in_order(self):
        workload=ple_workload.build(FAKE_VOCAB)
        self.assertEqual(workload,ple_workload.build(FAKE_VOCAB))
        texts=[c['user_text']for r in workload['repetitions'].values()for c in r['cases']]
        self.assertEqual(len(set(texts)),9)
        case=workload['repetitions']['2']['cases'][0];text=case['user_text']
        lines=[f"TARGET {t['target']}: code={t['code']} amount={t['amount']}"for t in case['expected']]
        self.assertEqual(len(lines),ple_workload.TARGETS)
        self.assertEqual(sorted(lines,key=text.index),lines)
        body=text.split('BEGIN TEXT\n')[1].split('\nEND TEXT')[0]
        self.assertEqual(body.count('TARGET'),ple_workload.TARGETS)
        self.assertEqual(len(body.split())-ple_workload.TARGETS*4,ple_workload.FILLER_WORDS)

    def test_probe_plan_is_three_load_only_thread_counts(self):
        plan=self.plan('ple-probe');jobs=experiment_schedule(plan)
        self.assertTrue(plan['probe_only']);self.assertEqual(plan['logical_requests'],0)
        self.assertEqual([(j['condition'],j['environment'])for j in jobs],
                         [(f'io{n}',{'STRATA_IO_THREADS':n})for n in(4,16,64)])
        self.assertTrue(all(j['overrides']=={'ple-io':'direct'}for j in jobs))

    def test_main_plans_are_latin_squares_differing_only_in_condition_c(self):
        for c in('c-io16','c-io64','c-inflight1024'):
            plan=self.plan('ple-path-'+c);jobs=experiment_schedule(plan)
            rows=[[j['condition']for j in jobs if j['repetition']==r]for r in(1,2,3)]
            self.assertEqual(rows,[['direct','mmap',c],['mmap',c,'direct'],[c,'direct','mmap']])
            self.assertEqual(plan['conditions'][:2],[{'id':'direct','overrides':{'ple-io':'direct'}},{'id':'mmap','overrides':{'ple-io':'mmap'}}])
            self.assertEqual(plan['per_logical_request_work_seconds_limit'],300)

    def test_per_repetition_workload_binds_every_repetition(self):
        workload=ple_workload.build(FAKE_VOCAB);plan=self.plan('ple-path-c-io16')
        plan['source_sha256']={};digest=lambda b:__import__('hashlib').sha256(b).hexdigest()
        plan['workload']['case_bindings']={r:[{'id':c['id'],'user_text_sha256':digest(c['user_text'].encode()),
            'expected_sha256':digest(json.dumps(c['expected'],sort_keys=True,separators=(',',':')).encode())}for c in v['cases']]
            for r,v in workload['repetitions'].items()}
        with tempfile.TemporaryDirectory()as folder:
            paths=[Path(folder)/'plan.json',Path(folder)/'workload.json']
            paths[0].write_text(json.dumps(plan));paths[1].write_text(json.dumps(workload))
            frozen_inputs(*paths)
            workload['repetitions']['3']['cases'][1]['user_text']+=' '
            paths[1].write_text(json.dumps(workload))
            with self.assertRaisesRegex(ValueError,'Frozen request'):frozen_inputs(*paths)
            del workload['repetitions']['3'];paths[1].write_text(json.dumps(workload))
            with self.assertRaisesRegex(ValueError,'Frozen request'):frozen_inputs(*paths)

    def test_kv_facts_read_the_effective_residency(self):
        log = ('strata generate: KV streaming: 20480 of 256584 cells per QSA layer in VRAM, the K/V in 3.03 GiB of pinned RAM\n'
               'strata generate: expert cache auto: 5.57 GiB free, 512 MiB reserved (+183 MiB for the draft head) -> 2990 slots\n'
               'Windows commit: 29.4 GiB left of a 95.8 GiB limit\nstrata serve: 280 MiB of VRAM free with everything loaded')
        self.assertEqual(kv_facts(log), {'kv_resident_cells': 20480, 'kv_total_cells': 256584, 'kv_pinned_gib': 3.03,
                                         'expert_slots': 2990, 'free_mib_loaded': 280, 'commit_left_gib': 29.4})
        self.assertIsNone(kv_facts('')['kv_resident_cells'])

    def test_load_facts_read_effective_ple_mode_and_large_pages(self):
        slow=('strata generate: loaded 39.97 GiB at 5.84 GiB/s\nexpert arena: large pages refused for 1 B\n'
              'strata generate: WARNING: --ple-io direct measures slow here (12850 rows/s, about 53 MB/s of random\n'
              'Windows commit: 14.2 GiB left of a 79.8 GiB limit (RAM + page file)\n')
        self.assertEqual(load_facts(slow),{'ple_probe_rows_per_s':12850,'ple_switched_to_mmap':False,'large_pages_refused':True,
                                           'commit_left_gib':14.2,'load_gib_per_s':5.84})
        fine=load_facts('strata generate: PLE direct read probe: 40210 rows/s (fine)\nexpert arena: large pages ok')
        self.assertEqual((fine['ple_probe_rows_per_s'],fine['large_pages_refused'],fine['commit_left_gib']),(40210,False,None))
        switched=load_facts('--ple-io direct measures slow here (9000 rows/s, about 37 MB/s of random 4 KiB reads): using --ple-io mmap instead')
        self.assertTrue(switched['ple_switched_to_mmap'])
        self.assertIsNone(load_facts('')['ple_probe_rows_per_s'])

    def test_disk_read_delta_keeps_unknown_process_reads_unknown(self):
        self.assertEqual(disk_read_delta({'system_read_bytes':10,'process_read_bytes':None},{'system_read_bytes':25,'process_read_bytes':7}),
                         {'system_read_bytes':15,'process_read_bytes':None})


if __name__=='__main__':unittest.main()
