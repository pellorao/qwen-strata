import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.reviewer.review_observations import observe


class ObservationsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.trial=Path(self.temp.name)
        self.harness=self.trial/'fixed-scratch/harness'
        (self.harness/'codex-home/sessions').mkdir(parents=True)
        self.records=[{'type':'session_meta','payload':{'id':'parent','source':'cli'}}]
        self.events=[]
        self.result={'label':'test','thread_id':'parent','native':{'bridge_requests':[
            {'id':'one','started_at':1,'completed_at':2,'output_status':'completed','error':None}]}}

    def tearDown(self):self.temp.cleanup()

    def call(self,identifier,output):
        self.records.extend([
            {'timestamp':'2026-10-03T00:00:00Z','type':'response_item','payload':{
                'type':'function_call','name':'exec_command','call_id':identifier,'arguments':'{"cmd":"cat source"}'}},
            {'timestamp':'2026-10-03T00:00:01Z','type':'response_item','payload':{
                'type':'function_call_output','call_id':identifier,'output':output}}])

    def run_observe(self):
        (self.trial/'result.json').write_text(json.dumps(self.result))
        (self.harness/'events.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in self.events))
        (self.harness/'codex-home/sessions/parent.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in self.records))
        return observe(self.trial)

    def test_literal_error_in_read_source_is_not_execution_failure(self):
        self.call('ok','Process exited with code 0\nOutput:\nthrow new Error("Permission denied");')
        r=self.run_observe()
        self.assertEqual(r['tool_call_count'],1)
        self.assertEqual(r['tool_failure_candidates'],[])
        self.assertEqual(r['api_failure_count'],0)

    def test_denial_preserves_followup_for_manual_recovery_judgment(self):
        self.call('denied','Process exited with code 1\nOutput:\ncat: outside: Permission denied')
        self.call('retry','Process exited with code 0\nOutput:\nsource')
        r=self.run_observe()
        self.assertEqual(len(r['tool_failure_candidates']),1)
        self.assertTrue(r['tool_failure_candidates'][0]['permission_denial_candidate'])
        self.assertEqual(len(r['tool_failure_candidates'][0]['next_visible_calls']),1)
        self.assertTrue(r['failure_adjudication_required'])

    def test_missing_bridge_output_is_unknown_not_zero_failure(self):
        self.result['native']['bridge_requests'][0]['completed_at']=None
        self.result['native']['bridge_requests'][0]['output_status']=None
        r=self.run_observe()
        self.assertIsNone(r['api_failure_count'])
        self.assertTrue(r['failure_adjudication_required'])

    def test_approval_latency_does_not_count_as_user_turn(self):
        self.events=[{'event':{'method':'turn/started','params':{'threadId':'parent'}}},
            {'event':{'method':'item/autoApprovalReview/completed','params':{
                'startedAtMs':1000,'completedAtMs':4500}}}]
        r=self.run_observe()
        self.assertEqual(r['user_turn_count'],1)
        self.assertEqual(r['approval_count'],1)
        self.assertEqual(r['approval_wall_s'],3.5)

    def test_invalid_patch_then_wrapped_success_is_counted_once(self):
        self.call('invalid',"apply_patch verification failed: invalid patch: missing Begin Patch")
        self.call('corrected','Exit code: 0\nWall time: 0.1 seconds\nOutput:\nSuccess. Updated the following files:')
        r=self.run_observe()
        self.assertEqual(len(r['tool_failure_candidates']),1)
        self.assertEqual(r['unknown_tool_outputs'],[])

    def test_never_rejects_escalation_before_command_completed_event(self):
        self.call('denied','approval policy is Never; reject command — you cannot ask for escalated permissions if the approval policy is Never')
        self.call('default','Process exited with code 0\nOutput:')
        r=self.run_observe()
        self.assertEqual(len(r['tool_failure_candidates']),1)
        self.assertTrue(r['tool_failure_candidates'][0]['permission_denial_candidate'])
        self.assertEqual(r['unknown_tool_outputs'],[])


if __name__=='__main__':unittest.main()
