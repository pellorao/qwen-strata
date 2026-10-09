import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.reviewer.context_measure import paired_handoffs, context_start_options, startup_binding
from tools.reviewer.arw_measure import execute_review, review_request_path
from tools.metrics.context_capacity import context_capacity, validate_context_pair, THRESHOLDS
from tools.metrics.prompt_policy import verify_loaded_startup


class ContextMeasurementTests(unittest.TestCase):
    def test_full_prompt_receipt_needs_sha_but_not_diagnostic_only_flags(self):
        sha='a'*64;metadata={'path':'config/prompts/startup-instructions.txt','sha256':sha}
        self.assertEqual(verify_loaded_startup(metadata,sha),metadata)
        for changed in ({'enabled':False},{'loop_prevention_enabled':False},{'sha256':'b'*64},{'path':None}):
            with self.assertRaises(ValueError):verify_loaded_startup({**metadata,**changed},sha)
    def test_current_baseline_works_without_legacy_startup_binding(self):
        root=Path(__file__).resolve().parents[1]
        baseline=json.loads((root/'config/maintenance-baseline.json').read_text())
        before=json.dumps(baseline,sort_keys=True)
        binding=startup_binding(baseline)
        self.assertEqual(binding['installation_relative_path'],'config/prompts/startup-instructions.txt')
        self.assertEqual(len(binding['sha256']),64)
        options=context_start_options(baseline,206584,150000)
        self.assertEqual(options['request_defaults']['reasoning_budget_tokens'],8192)
        self.assertEqual(options['request_defaults']['max_tokens'],24576)
        self.assertFalse(options['fit_max_tokens'])
        self.assertEqual(json.dumps(baseline,sort_keys=True),before)
        with self.assertRaises(ValueError):startup_binding({**baseline,'startup_instructions':{
            'installation_relative_path':'config/prompts/startup-instructions.txt','sha256':'0'*64}})

    def test_medium_budget_is_not_overwritten_by_high_baseline(self):
        root=Path(__file__).resolve().parents[1]
        baseline=json.loads((root/'config/maintenance-baseline.json').read_text())
        baseline['harness']['model_reasoning_effort']='medium'
        with self.assertRaises(ValueError):context_start_options(baseline,156584,100000)
        defaults=baseline['start_options']['request_defaults']
        defaults.update(reasoning_effort='medium',reasoning_budget_tokens=4096,max_tokens=16384)
        for threshold,window in ((100000,156584),(150000,206584)):
            options=context_start_options(baseline,window,threshold)
            self.assertEqual(options['request_defaults']['max_tokens'],16384)
            self.assertEqual(options['request_defaults']['reasoning_budget_tokens'],4096)
            self.assertTrue(options['loop_prevention_instructions'])
        baseline['start_options']['startup_instructions']=False
        with self.assertRaises(ValueError):context_start_options(baseline,156584,100000)

    def test_current_native_handoff_retains_exact_report_permission_and_instructions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);report=root/'reports/result.jsonl';report.parent.mkdir()
            request=root/'request.json';request.write_text('{}')
            prepared=root/'prepared.json';prepared.write_text(json.dumps({'contracts':[{'instances':[
                {'instanceId':'native','requestPath':str(request)}]}]}))
            runtime=root/'runtime.json';runtime.write_text('{}')
            shim=root/'bin/arw';shim.parent.mkdir();shim.write_text('#!/bin/sh\nexit 0\n')
            native={'role':'spec-readiness-reviewer','identity':{'kind':'isolated','instanceId':'native'},
                'instructions':'Exact original role and full shared rules.', 'handoff':'Exact original handoff.',
                'cwd':str(root),'writePaths':[str(report)],'reportPath':str(report),'stateDirectory':str(root/'state')}
            handoff={'input':native,'instanceId':'native','reviewerId':'spec-readiness-reviewer',
                     'scenarioId':'artifact-promotion','scenarioRoot':str(root)}
            prep={'preparedPath':str(prepared),'identity':{'sessionId':'owner'},'generations':[]}
            class Machine:
                def call(self,operation,bound):
                    self.bound=bound
                    return {'runId':'run','messageId':'message'}
            machine=Machine()
            with patch.dict('os.environ',{'QWEN_ARW_RUNTIME_FILE':str(runtime),'QWEN_ARW_MODEL_BASE':'http://local/v1'}),patch('tools.reviewer.arw_measure.observe_review',lambda m,r,f:r):
                execute_review(machine,root,prep,handoff,root/'stage',
                    {'model':'Q2_0','effort':'high','context_window':156584,'auto_compact_token_limit':100000},root/'catalog.json')
            self.assertEqual({k:machine.bound[k] for k in native},native)
            self.assertEqual(machine.bound['writePaths'],[str(report)])
            self.assertEqual(native['writePaths'],[str(report)])

    def test_native_request_dispatch_preserves_prepared_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);request=root/'requests/request.json';request.parent.mkdir()
            request.write_text('{}')
            prepared=root/'prepared.json';prepared.write_text(json.dumps({'contracts':[{'instances':[
                {'instanceId':'native','scenarioRoot':str(root)}]}]}))
            before=prepared.read_bytes()
            prep={'preparedPath':str(prepared)}
            handoff={'instanceId':'native','scenarioRoot':str(root),'prompt':
                'Read the immutable Reviewer Request from this exact path relative to the scenario root: requests/request.json.'}
            self.assertEqual(review_request_path(prep,handoff),str(request))
            self.assertEqual(prepared.read_bytes(),before)
            for reference in ('../request.json',str(request),'requests/absent.json'):
                with self.subTest(reference=reference),self.assertRaises(ValueError):
                    review_request_path(prep,{**handoff,'prompt':handoff['prompt'].replace('requests/request.json',reference)})
            with self.assertRaises(ValueError):review_request_path(prep,{**handoff,'prompt':'No exact native reference'})
            with self.assertRaises(ValueError):review_request_path(prep,{**handoff,'prompt':handoff['prompt']*2})

    def test_capacity_preserves_high_output_budget_at_maximum_overrun(self):
        expected=(120584,156584,206584,256584)
        for threshold,window in zip(THRESHOLDS,expected):
            self.assertEqual(context_capacity(threshold),window)
            validate_context_pair(threshold,window)
            self.assertEqual(window-(threshold+32000)-8,24576)
        for threshold,window in ((64000,80000),(100000,125000),(150000,188000),(200000,250000),
                                 (64000,120584.0),(64000,True)):
            with self.assertRaises(ValueError):validate_context_pair(threshold,window)
        for threshold in (True,64000.0,'64000',None,64001):
            with self.assertRaises(ValueError):context_capacity(threshold)

    def test_pair_order_and_partial_pair_rejection(self):
        runtime={'scenarioId':'runtime-migration','instanceId':'runtime-x-instance-1'}
        artifact={'scenarioId':'artifact-promotion','instanceId':'artifact-x-instance-1'}
        self.assertEqual(paired_handoffs({'handoffs':[artifact,runtime]},1),[runtime,artifact])
        with self.assertRaises(ValueError):paired_handoffs({'handoffs':[artifact]},1)

    def test_followup_keeps_recovery_identity_but_uses_new_report_and_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);project=root/'scenario';roles=project/'docs/agents/roles';roles.mkdir(parents=True)
            runtime=root/'runtime.json';runtime.write_text('{}')
            shim=root/'bin/arw';shim.parent.mkdir();shim.write_text('#!/bin/sh\nexit 0\n')
            (roles/'spec-readiness-reviewer.md').write_text('role')
            (roles.parent/'reviewer.md').write_text('reviewer')
            request=root/'request.json';report=root/'reports/second.jsonl'
            request.write_text(json.dumps({'draftPath':str(report)}))
            prepared=root/'prepared.json';prepared.write_text(json.dumps({'contracts':[{'instances':[
                {'instanceId':'second','requestPath':str(request)}]}]}))
            binding=root/'first-binding.json';binding.write_text(json.dumps({'identity':{'kind':'isolated','instanceId':'first'}}))
            prep={'identity':{'sessionId':'owner'},'preparedPath':str(prepared),'generations':[]}
            handoff={'instanceId':'second','scenarioId':'artifact-promotion','reviewerId':'spec-readiness-reviewer',
                'agentType':'spec-readiness-reviewer','scenarioRoot':str(project),'prompt':'second full frozen handoff'}
            class Machine:
                def call(self,operation,bound):
                    self.operation=operation;self.bound=bound
                    return {'runId':'same-run','messageId':'second-message'}
            machine=Machine()
            def observe(m,record,folder):
                record.update(runtime_result={'threadId':'same-thread'},complete=True)
                self.assertNotIn('revisions',record)
                return record
            prior={'complete':True,'binding_path':str(binding),'accepted':{'runId':'same-run'},
                'runtime_result':{'threadId':'same-thread'}}
            for threshold in THRESHOLDS:
                window=context_capacity(threshold)
                with self.subTest(window=window):
                    with patch.dict('os.environ',{'QWEN_ARW_RUNTIME_FILE':str(runtime),'QWEN_ARW_MODEL_BASE':'http://local/v1'}),patch('tools.reviewer.arw_measure.observe_review',observe):
                        execute_review(machine,root,prep,handoff,root/f'stage2-{window}',
                            {'model':'Q2_0','effort':'medium','context_window':window,'auto_compact_token_limit':threshold},root/'catalog.json',previous=prior)
                    self.assertEqual(machine.operation,'followup_task')
                    self.assertEqual(machine.bound['identity']['instanceId'],'first')
                    self.assertEqual(machine.bound['reportPath'],str(report))
                    config=machine.bound['settings']['config']
                    self.assertEqual(config['model_context_window'],window)
                    self.assertEqual(config['model_auto_compact_token_limit'],threshold)
                    compact=Path(config['experimental_compact_prompt_file']).read_text()
                    self.assertIn('Do not perform the task or call tools',compact)
                    self.assertIn('CONTEXT CHECKPOINT COMPACTION',compact)
                    self.assertNotIn('compact_prompt',config)


if __name__=='__main__':unittest.main()
