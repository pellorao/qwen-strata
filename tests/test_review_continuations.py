import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.reviewer.review_continuations import current_round_started, terminal_kind, continuation_token_totals

class ContinuationBoundaries(unittest.TestCase):
    def test_accepted_followup_does_not_reuse_old_terminal_measurement(self):
        old = {'state': 'exited', 'completion': {'status': 'incomplete'},
               'measurement': {'startedAt': 100_000}}
        self.assertFalse(current_round_started(old, 200))
        current = dict(old, state='running', completion=None,
                       measurement={'startedAt': 200_010})
        self.assertTrue(current_round_started(current, 200))

    def classify(self, terminal, *, report='nonempty', turn_id='current'):
        with tempfile.TemporaryDirectory() as directory:
            native, draft = Path(directory)/'session.jsonl', Path(directory)/'review.jsonl'
            native.write_text(json.dumps({'payload': dict(terminal, turn_id=turn_id)})+'\n')
            draft.write_text(report)
            return terminal_kind(native, {'turnId': 'current',
                                          'completion': {'status':'incomplete'}}, draft)[0]

    def test_known_tool_rejection_is_recoverable_but_network_failure_is_not(self):
        terminal={'type':'task_complete','error':{'message':'[invalid_response] Model returned unknown tool: exec_command'}}
        self.assertEqual(self.classify(terminal),'recoverable-tool-response-failure')
        terminal['error']['message']='503: upstream connection failed'
        self.assertEqual(self.classify(terminal),'protocol-or-native-failure')

    def test_code_fence_is_mechanical_only_for_ready_status(self):
        self.assertEqual(self.classify({'type':'task_complete','last_agent_message':'```json\n{"status":"ready"}\n```'}),'final-status-format-only')
        self.assertEqual(self.classify({'type':'task_complete','last_agent_message':'```json\n{"progress":"not finished"}\n```'}),'premature-normal-end')

    def test_explanatory_prose_and_one_final_ready_block_is_mechanical(self):
        terminal={'type':'task_complete','last_agent_message':
                  'All checks on the bound draft are complete and well formed.\n\n```json\n{"status":"ready"}\n```'}
        self.assertEqual(self.classify(terminal),'final-status-format-only')
        self.assertEqual(self.classify(terminal,report=''),'premature-normal-end')

    def test_plain_ready_with_report_is_not_a_premature_end(self):
        terminal={'type':'task_complete','last_agent_message':'{"status":"ready"}'}
        self.assertEqual(self.classify(terminal),'ready-unverified-needs-main')
        self.assertEqual(self.classify(terminal,report=''),'premature-normal-end')

    def test_multiple_blocks_or_non_ready_final_block_are_not_repaired(self):
        message='```json\n{"status":"incomplete"}\n```\n```json\n{"status":"ready"}\n```'
        self.assertEqual(self.classify({'type':'task_complete','last_agent_message':message}),'premature-normal-end')
        message='More review remains.\n```json\n{"status":"incomplete"}\n```'
        self.assertEqual(self.classify({'type':'task_complete','last_agent_message':message}),'premature-normal-end')

    def test_other_turn_terminal_cannot_end_current_round(self):
        with self.assertRaises(StopIteration):
            self.classify({'type':'task_complete'},turn_id='previous')

    def test_empty_engine_capture_is_not_assumed_zero(self):
        with self.assertRaises(AssertionError):
            continuation_token_totals([{'engine_tokens':None}], [])

    def test_proven_pre_execution_rejection_has_no_executed_phase_tokens(self):
        rejected={'engine_tokens':None,'pre_execution_rejection':{'kind':'capacity-rejected-before-engine-execution'}}
        self.assertEqual(continuation_token_totals([rejected], []),
                         {'uncached_input':0,'cached_input':0,'output':0})
        phase={'uncached':20,'cached':30,'output':4}
        executed={'engine_tokens':{'uncached_input':20,'cached_input':30,'output':4}}
        self.assertEqual(continuation_token_totals([executed,rejected], [phase]),executed['engine_tokens'])

if __name__=='__main__':
    unittest.main()
