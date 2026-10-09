import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.reviewer.arw_measure import observe_review
from tools.reviewer.review_continuations import HttpArchive


class NativeContinuationTests(unittest.TestCase):
    def test_recovered_work_ledger_keeps_original_phase_and_excludes_shutdown(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            ledger=[{'alive':True,'at':10,'estimated':False},
                    {'alive':False,'at':20,'estimated':True},
                    {'alive':True,'at':90,'estimated':True}]
            (folder/'review-work-events.json').write_text(json.dumps(ledger))
            record={'accepted':{'runId':'same-run','messageId':'same-message'},
                    'role':'commit-audit-reviewer','instanceId':'instance','started_at':10}
            class Machine:
                def call(self,operation,value,**kwargs):
                    assert operation=='list_agents' and value=={'runId':'same-run'}
                    return {'runId':'same-run','state':'idle',
                            'completion':{'status':'ready'},'measurement':{}}
            with patch('tools.reviewer.arw_measure.time.time',return_value=100):
                result=observe_review(Machine(),record,folder)
            self.assertEqual(result['review_work_seconds'],20)
            self.assertEqual(result['deadlines'][0]['started_at'],10)
            self.assertEqual(result['deadlines'][0]['time_basis'],'review-work')
            self.assertEqual(json.loads((folder/'review-work-events.json').read_text())[:3],ledger)

    def observe(self,terminal,*,report='partial judgments',expired=False,stale=False,rejected=False,timeout=False,global_recovery_incomplete=False):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);draft=folder/'review.jsonl';draft.write_text(report)
            native=folder/'session.jsonl'
            native.write_text(json.dumps({'payload':dict(terminal,turn_id='old-turn')})+'\n')
            recovery=folder/'recovery.json';recovery.write_text(json.dumps({'threadId':'same-thread','sessionPath':str(native)}))
            binding=folder/'binding.json';binding.write_text(json.dumps({'handoff':'Unchanged original task.','reportPath':str(draft),'identity':{'kind':'isolated','instanceId':'instance'}}))
            initial={'runId':'same-run','threadId':'same-thread','turnId':'old-turn','state':'idle','completion':{'status':'incomplete'},'measurement':{}}
            ready={**initial,'turnId':'new-turn','completion':{'status':'ready'},'recoveryIncomplete':global_recovery_incomplete}
            active={**ready,'state':'running','completion':None}
            observations=[initial]+([active] if global_recovery_incomplete else [])+[ready]
            class Machine:
                def __init__(self):self.followups=[];self.waits=0;self.passive_polls=0
                def call(self,operation,value,**kwargs):
                    if operation=='list_agents':
                        assert json.loads(recovery.read_text()).get('state')!='starting', 'Managed observation races pending task preparation'
                        return observations.pop(0)
                    if operation=='wait_agent':self.waits+=1;return {'cursor':1}
                    if operation=='followup_task':
                        assert not draft.read_bytes()
                        self.followups.append(value)
                        draft.write_text('Complete original judgments.')
                        if rejected:
                            recovery.write_text(json.dumps({'threadId':'same-thread','sessionPath':str(native),
                                'state':'failed','failure':{'code':'reviewer-runtime-failed','message':'Native root is not safely idle for new task settings.'}}))
                        else:
                            recovery.write_text(json.dumps({'threadId':'same-thread','sessionPath':str(native),
                                'state':'starting' if stale or timeout else 'running',
                                'turnId':'old-turn' if stale or timeout else 'new-turn'}))
                        return {'runId':'same-run','messageId':'continued-message','recoveryPath':str(recovery)}
                    raise AssertionError(operation)
            machine=Machine()
            record={'accepted':{'runId':'same-run','messageId':'first-message','recoveryPath':str(recovery)},'role':'commit-audit-reviewer','instanceId':'instance','report':str(draft),'binding_path':str(binding),'started_at':time.time()-(3601 if expired else 0),'selection':{'automatic_continuation':True}}
            def passive_poll(_):
                machine.passive_polls+=1
                recovery.write_text(json.dumps({'threadId':'same-thread','sessionPath':str(native),
                    'state':'running','turnId':'new-turn'}))
            with patch('tools.reviewer.arw_measure.time.sleep',side_effect=passive_poll):
                result=observe_review(machine,record,folder,continuation_start_timeout=0 if timeout else 120)
            saved=(folder/'automatic-continuations/1/report-before.jsonl')
            return result,machine.followups,machine.passive_polls,saved.read_text() if saved.exists() else None

    def test_early_end_keeps_thread_draft_and_initial_budget_despite_stale_observation(self):
        result,calls,waits,draft=self.observe({'type':'task_complete','last_agent_message':'I will finish the report.'},stale=True)
        self.assertTrue(result['complete'])
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0]['runId'],'same-run')
        self.assertTrue(calls[0]['handoff'].startswith('Unchanged original task.'))
        self.assertEqual(draft,'partial judgments')
        self.assertEqual(waits,1)  # Passive file polling, never a managed wait/inspect.
        self.assertEqual(len(result['deadlines']),1)
        self.assertEqual(result['deadlines'][0]['phase'],'initial')

    def test_confirmed_unknown_tool_rejection_supplies_actual_feedback(self):
        result,calls,_,_=self.observe({'type':'task_complete','error':{'message':'[invalid_response] Model returned unknown tool: exec_command'}})
        self.assertTrue(result['complete'])
        self.assertIn('Model returned unknown tool: exec_command',calls[0]['handoff'])
        self.assertIn('That rejected tool call was not executed.',calls[0]['handoff'])

    def test_ready_block_with_prose_preserves_report_and_does_not_wake_model(self):
        result,calls,_,saved=self.observe({'type':'task_complete','last_agent_message':
            'All checks on the bound report passed.\n\n```json\n{"status":"ready"}\n```'})
        self.assertFalse(result['complete'])  # Native format failure retained.
        self.assertEqual(calls,[])
        self.assertIsNone(saved)  # Original report was neither cleared nor redone.

    def test_accepted_followup_failure_returns_without_waiting_on_old_terminal(self):
        result,calls,waits,draft=self.observe({'type':'task_complete','last_agent_message':'More work remains.'},stale=True,rejected=True)
        self.assertFalse(result['complete'])
        self.assertEqual(len(calls),1)
        self.assertEqual(waits,0)
        self.assertEqual(result['continuation_dispatch_failure']['status'],'failed')
        self.assertIn('safely idle',result['continuation_dispatch_failure']['failure']['message'])
        self.assertEqual(draft,'partial judgments')

    def test_global_persistence_marker_does_not_reject_confirmed_same_thread_turn(self):
        result,calls,_,_=self.observe({'type':'task_complete','last_agent_message':'More work remains.'},global_recovery_incomplete=True)
        self.assertTrue(result['complete'])
        self.assertEqual(len(calls),1)
        self.assertTrue(result['recovery_limitations'][0]['upstream_global_recovery_incomplete'])

    def test_missing_new_turn_expires_as_unknown_without_redispatch(self):
        result,calls,waits,_=self.observe({'type':'task_complete','last_agent_message':'More work remains.'},stale=True,timeout=True)
        self.assertFalse(result['complete'])
        self.assertEqual(len(calls),1)
        self.assertEqual(waits,0)
        self.assertEqual(result['continuation_dispatch_failure']['status'],'unconfirmed')

    def test_mechanical_status_network_failure_and_unverified_argument_error_do_not_retry(self):
        terminals=[{'type':'task_complete','last_agent_message':'```json\n{"status":"ready"}\n```'},
                   {'type':'task_complete','last_agent_message':'`{"status":"ready"}`'},
                   {'type':'task_complete','error':{'message':'503 connection failed'}},
                   {'type':'task_complete','error':{'message':'[invalid_response] Unterminated string starting at:'}}]
        for terminal in terminals:
            with self.subTest(terminal=terminal):
                result,calls,_,draft=self.observe(terminal)
                self.assertFalse(result['complete'])
                self.assertEqual(calls,[])
                self.assertIsNone(draft)

    def test_expired_initial_budget_is_not_extended(self):
        result,calls,_,_=self.observe({'type':'task_complete','last_agent_message':'More work remains.'},expired=True)
        self.assertFalse(result['complete'])
        self.assertEqual(calls,[])

    def test_http_observer_can_start_before_native_log_database_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);db=folder/'logs.sqlite'
            archive=HttpArchive(db,folder);archive.thread.start()
            try:
                with sqlite3.connect(db) as connection:
                    connection.execute('create table logs(id integer,ts integer,ts_nanos integer,level text,target text,feedback_log_body text,thread_id text,process_uuid text)')
                    connection.execute("insert into logs values(1,1,0,'DEBUG','codex_http_client::client','first real request','thread','process')")
            finally:archive.close()
            rows=[json.loads(l) for l in (folder/'http-log-archive.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['body'],'first real request')
            self.assertIsNone(archive.error)


if __name__=='__main__':unittest.main()
