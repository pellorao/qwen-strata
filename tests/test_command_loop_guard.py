import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.loop.command_loop_guard import observe_command_loops
from tools.reviewer.freeze_arw_source import materialize


class CommandLoopGuardTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'source'
  directory=ROOT/'benchmarks/reviewer-suite-v1/source-snapshots/current';m=json.loads((directory/'manifest.json').read_text());archive=directory/m['snapshot']['file']
  materialize(m,archive,self.root)
  self.sha=hashlib.sha256((self.root/'lib/background-agent/strata-work-policy.mjs').read_bytes()).hexdigest()
 def tearDown(self):self.tmp.cleanup()
 def facts(self):
  return [{'threadId':'root','turnId':'turn','itemId':str(i),'position':i,'command':'read synthetic.txt','cwd':'/synthetic','exitCode':1,'outputDigest':'same-failure'}for i in range(1,4)]
 def call(self,facts,state=None):
  p=subprocess.run(['node',str(ROOT/'tools/loop/arw_command_loop_guard.mjs')],input=json.dumps({'repositoryRoot':str(self.root),'threadId':'root','facts':facts,'state':state}),capture_output=True,text=True,check=True);return json.loads(p.stdout)
 def test_exact_three_repeats_use_real_upstream_hint_without_fake_receipt(self):
  r=self.call(self.facts());self.assertEqual(len(r['hints']),1);self.assertIn('three times consecutively',r['hints'][0]['instruction']);self.assertIsNone(r['state']['repeatMessageId'])
 def test_changed_output_resets_repetition_and_mirrored_facts_are_not_replayed(self):
  facts=self.facts();facts[1]['outputDigest']='new-evidence';self.assertEqual(self.call(facts)['hints'],[])
  first=self.call(self.facts());again=self.call(self.facts(),first['state']);self.assertEqual(again['hints'],[])
 def test_real_message_admission_is_recorded_separately_from_model_receipt(self):
  class Machine:
   source=self.root
   def call(inner,operation,value):inner.sent=(operation,value);return {'runId':'run','messageId':'real-admission-id','deliveryStatus':'accepted'}
  machine=Machine();record={'selection':{'command_loop_guard':{'enabled':True,'algorithm':'frozen-arw-strata-command-policy','source_sha256':self.sha}},'accepted':{'runId':'run'}}
  result={'threadId':'root','turnId':'turn','snapshot':{'members':[{'threadId':'root','state':'active'}],'commandFacts':self.facts()}}
  observe_command_loops(machine,record,result,self.root/'out');self.assertEqual(machine.sent[0],'send_message');self.assertEqual(machine.sent[1]['turnId'],'turn')
  row=json.loads((self.root/'out/command-loop-guard/events.jsonl').read_text());self.assertFalse(row['model_receipt_verified']);self.assertEqual(row['native_receipt']['messageId'],'real-admission-id')
  state=json.loads((self.root/'out/command-loop-guard/state.json').read_text());self.assertEqual(state['repeatMessageId'],'real-admission-id')
 def test_disabled_policy_never_sends_a_message(self):
  observe_command_loops(None,{'selection':{}},{},self.root/'disabled');self.assertFalse((self.root/'disabled').exists())
 def test_starting_with_null_snapshot_does_not_send_or_persist(self):
  record={'selection':{'command_loop_guard':{'enabled':True,'algorithm':'frozen-arw-strata-command-policy'}}}
  observe_command_loops(None,record,{'state':'starting','snapshot':None},self.root/'starting')
  self.assertFalse((self.root/'starting').exists())


if __name__=='__main__':unittest.main()
