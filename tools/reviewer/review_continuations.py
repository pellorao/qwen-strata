"""Resume project-owned Reviewer tasks without changing their native threads or budgets.

Batch bindings and evidence stay in the caller-selected temporary batch directory.
This program is invoked only after the user authorizes its actual model scope.
"""
from pathlib import Path
import hashlib,json,os,re,sqlite3,subprocess,sys,threading,time


from tools.reviewer.arw_measure import Machine,read_daemon_message,log_offset,capture_engine_log,generate_original
from tools.ops.controller_client import Controller
from tools.reviewer.review_deadlines import ReviewDeadline
from tools.reviewer.wsl_client import save
from tools.metrics.strata_tokens import parse_engine_log,sum_engine_tokens
from tools.metrics.review_work_time import recorded_work_time, ReviewWorkClock

load=lambda p:json.loads(Path(p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()

class HttpArchive:
 def __init__(self,db,folder):
  self.db=db;self.folder=folder;self.stop=threading.Event();self.error=None;self.rows=0
  self.last=0
  if Path(db).exists():
   with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True) as c:
    try:self.last=c.execute('select coalesce(max(id),0) from logs').fetchone()[0]
    except sqlite3.OperationalError as error:
     if 'no such table: logs' not in str(error):raise
  self.first=self.last;self.thread=threading.Thread(target=self.run,daemon=True)
 def run(self):
  archive=self.folder/'http-log-archive.jsonl'
  while True:
   try:
    out=archive.open('x');break
   except FileExistsError:
    archive=self.folder/('http-log-archive-resume-'+str(time.time_ns())+'.jsonl')
  self.archive_path=archive
  with out:
   while True:
    try:
     with sqlite3.connect('file:'+str(self.db)+'?mode=ro',uri=True,timeout=.5) as c:
      rows=c.execute("select id,ts,ts_nanos,level,target,feedback_log_body,thread_id,process_uuid from logs where id>? and target in ('codex_http_client::client','codex_core::responses_retry') order by id",(self.last,)).fetchall()
     for row in rows:
      d=dict(zip(('id','ts','ts_nanos','level','target','body','thread_id','process_uuid'),row));d['body']=re.sub(r'(?i)(bearer\s+)[A-Za-z0-9._~-]+',r'\1[REDACTED]',d['body'] or '')
      out.write(json.dumps(d,ensure_ascii=False)+'\n');self.last=row[0];self.rows+=1
     out.flush();self.error=None
    except sqlite3.Error as e:self.error=type(e).__name__
    save(self.folder/'http-archive-status.json',{'status':'closed' if self.stop.is_set() else 'archiving','started_after_id':self.first,'last_id':self.last,'rows':self.rows,'error':self.error,'at':time.time(),'observer_model_requests':0,'archive_file':archive.name})
    if self.stop.is_set():break
    self.stop.wait(1)
 def close(self):self.stop.set();self.thread.join(timeout=10);assert not self.thread.is_alive()

def terminal_kind(native,observation,report):
 # Classify a normal premature end only from the exact latest native terminal.
 ev=[json.loads(l) for l in native.read_text().splitlines()]
 terminal=next((e['payload'] for e in reversed(ev) if e.get('payload',{}).get('type') in ('task_complete','turn_aborted') and (not observation.get('turnId') or e['payload'].get('turn_id')==observation['turnId'])),None)
 if terminal is None:raise ValueError(f'{native}: no task_complete or turn_aborted event'+(f" for turn {observation['turnId']}" if observation.get('turnId') else ''))
 if terminal['type']=='turn_aborted':return 'interrupted',terminal
 if terminal.get('error'):
  message=terminal['error'].get('message','')
  if '[invalid_response]' in message and 'Model returned unknown tool:' in message:return 'recoverable-tool-response-failure',terminal
  if '[invalid_response]' in message and 'Unterminated string starting at:' in message:return 'recoverable-tool-argument-response-failure',terminal
  return 'protocol-or-native-failure',terminal
 if (observation.get('completion') or {}).get('status')=='ready':return 'ready',terminal
 message=terminal.get('last_agent_message') or ''
 trimmed=message.strip()
 fence=re.fullmatch(r'```(?:json)?\s*(.*?)\s*```',trimmed,re.S)
 # A single final ready block may have explanatory prose before it. Keep
 # the native format failure, but let Main handle it without another review.
 if not fence and trimmed.count('```')==2:
  fence=re.search(r'(?:^|\n)```(?:json)?\s*(.*?)\s*```\s*$',trimmed,re.S)
 inline=re.fullmatch(r'`([^`\n]+)`',trimmed)
 wrapper=fence or inline
 if wrapper and report.stat().st_size:
  try:fenced=json.loads(wrapper.group(1))
  except ValueError:fenced=None
  if fenced=={'status':'ready'}:return 'final-status-format-only',terminal
 try:status=json.loads(trimmed)
 except ValueError:status={}
 # A plain ready status with a delivered report: the native completion check failed, not the model.
 if status=={'status':'ready'} and report.stat().st_size:return 'ready-unverified-needs-main',terminal
 if isinstance(status,dict) and status.get('status')=='incomplete':return 'explicit-incomplete-needs-main',terminal
 return 'premature-normal-end',terminal

def current_round_started(observation,submitted):
 value=observation.get('measurement',{}).get('startedAt')
 return isinstance(value,(int,float)) and not isinstance(value,bool) and value/1000>=submitted-.5

def pre_execution_rejection(terminal, phases, installation):
 # Native errors are classification evidence, never token values. Verify that
 # the installed capacity guard raises before Engine.generate and no engine
 # execution stage was logged. Other empty captures remain unknown.
 message=terminal.get('error',{}).get('message','')
 if phases or not ('exceeds the context' in message and 'requests are never truncated' in message):return None
 source=Path(installation)/'runtime/Strata/serve/server.py'
 body=source.read_text()
 guard=body.index('raise ValueError(f"prompt ({len(ids)} tokens) + max tokens ({max_new}) exceeds the context ')
 assert body.index('return ids, kwargs.get("enable_thinking", True) is not False, max_new',guard)>guard
 assert body.index('self.engine.generate(',guard)>guard
 return {'kind':'capacity-rejected-before-engine-execution','source':str(source),'source_sha256':sha(source),'engine_stages':0,'native_error':message}

def continuation_token_totals(segments, phases):
 unknown=[s for s in segments if s['engine_tokens'] is None and not s.get('pre_execution_rejection')]
 assert not unknown,'Missing executed-phase token records remain unknown'
 totals=sum_engine_tokens(phases)
 if totals is None:
  assert segments and all(s.get('pre_execution_rejection') for s in segments)
  totals={'uncached_input':0,'cached_input':0,'output':0}
 assert {k:sum((s['engine_tokens'] or {}).get(k,0) for s in segments) for k in totals}==totals
 return totals

class ContinuationRunner:
 def __init__(self,batch,installation,runtime_approval=None,post_timeout_approval=None):
  self.batch=Path(batch).resolve();self.project=Path(__file__).resolve().parents[2]
  self.runtime_approval=Path(runtime_approval) if runtime_approval else None
  self.post_timeout_approval=Path(post_timeout_approval) if post_timeout_approval else None
  self.extension=load(self.post_timeout_approval) if self.post_timeout_approval else None
  if self.extension:
   assert self.extension['user_approval'] and self.extension['additional_work_seconds']==3600
  self.installation=Path(installation);self.output=self.batch/'premature-continuations'

 def preflight(self,job,rec):
  B,R,I=self.batch,self.project,self.installation
  source=Path(load(job['dispatch'])['repositoryRoot']);manifest=load(R/'benchmarks/reviewer-suite-v1/source-manifest.json')
  approval=load(self.runtime_approval) if self.runtime_approval else None
  if approval:assert approval['applied'] and approval['user_approval']
  for name,expected in manifest['sha256'].items():
   if approval and name in approval.get('source_sha256_after',{}):
    assert manifest['sha256'][name]==approval['source_sha256_before'][name]
    expected=approval['source_sha256_after'][name]
   elif approval and name=='lib/background-agent/manager.mjs':expected=approval['applied_sha256']
   assert sha(source/name)==expected,name
  fixed=load(B/'fixed-inputs.json')
  for name,expected in fixed['files'].items():
   replacement=(self.extension or {}).get('harness_sha256_after',{}).get(name)
   if replacement:
    assert (self.extension['harness_sha256_before'][name]==expected
            and name in ('tools/reviewer/arw_measure.py',)),name
    expected=replacement
   assert sha(R/name)==expected,name
  for name,expected in (self.extension or {}).get('runtime_tool_sha256',{}).items():assert sha(R/name)==expected,name
  if self.extension:
   authorized=self.extension['instances'][Path(job['folder']).name]
   assert authorized['threadId']==rec['runtime_result']['threadId'] and authorized['runId']==rec['accepted']['runId']
  for req in fixed['requests']:assert sha(req['path'])==req['sha256']
  assert os.environ.get('CODEX_THREAD_ID')==load(job['dispatch'])['identity']['sessionId']
  for key in ('profile','startup_instructions'):
   v=load(B/'baseline.json')[key];assert sha(I/v['installation_relative_path'])==v['sha256']
  assert sha(rec['compaction_prompt_policy']['rendered_path'])==rec['compaction_prompt_policy']['rendered_sha256']

 def preserve_initial(self,job,where):
  B,R,I=self.batch,self.project,self.installation
  f=Path(job['folder']);rec=load(f/'results.json')[0];assert rec['stop']['status']=='stopped' and not rec['complete']
  cleanup=load(f/'arw-cleanup.json')['cleanup']
  if cleanup['status']!='ready':
   proof=load(f/'failed-terminal-cleanup/verified-exit.json');assert proof['manager_exit_confirmed'] and proof['maintenance_ownership_returned']
  assert not (f/'controller-key.private.json').exists()
  assert rec['selection']==load(job['selection']) and sha(rec['report'])==rec['report_sha256']
  assert not rec['complete']
  recovery=load(rec['accepted']['recoveryPath']);assert not recovery.get('failure')
  assert recovery['threadId']==rec['runtime_result']['threadId'] and recovery['runId']==rec['accepted']['runId']
  assert os.environ.get('CODEX_THREAD_ID')==load(Path(job['dispatch']))['identity']['sessionId']
  with sqlite3.connect('file:'+str(f/'arw-installation/background-agent-state/messages.sqlite')+'?mode=ro',uri=True) as cx:
   row=cx.execute('select owner_id,thread_id,state,task_state from agents where run_id=?',(rec['accepted']['runId'],)).fetchone()
  assert row==(os.environ['CODEX_THREAD_ID'],recovery['threadId'],'exited','ended'),row
  source=Path(load(job['dispatch'])['repositoryRoot'])
  self.preflight(job,rec)
  initial=where/'initial-preservation';initial.mkdir()
  for name in ('results.json','run-finished.json','runtime.json','arw-cleanup.json'):(initial/name).write_bytes((f/name).read_bytes())
  report_copy=initial/'review.jsonl';report_copy.write_bytes(Path(rec['report']).read_bytes());assert sha(report_copy)==rec['report_sha256']
  native=Path(recovery['sessionPath']);raw=native.read_bytes();assert json.loads(raw.splitlines()[0])['payload']['id']==recovery['threadId']
  binding=load(rec['binding_path']);assert binding['identity']['instanceId']==job['instanceId']
  (initial/'binding.json').write_bytes(Path(rec['binding_path']).read_bytes())
  artifacts={}
  for path in Path(rec['report']).parent.glob('*.audit.json'):
   copy=initial/path.name;copy.write_bytes(path.read_bytes());artifacts[str(path)]={'preserved':str(copy),'sha256':sha(copy)}
  save(initial/'provenance.json',{'instanceId':job['instanceId'],'report_path':rec['report'],'report_copy':str(report_copy),'report_sha256':rec['report_sha256'],'session_path':str(native),'session_prefix_bytes':len(raw),'session_prefix_sha256':hashlib.sha256(raw).hexdigest(),'native_thread_id':recovery['threadId'],'recovery_path':rec['accepted']['recoveryPath'],'recovery_sha256':sha(rec['accepted']['recoveryPath']),'initial_artifacts':artifacts,'model_requests':0})
  return rec,binding,source


 def continue_one(self,job):
  B,R,I,OUT=self.batch,self.project,self.installation,self.output
  name=Path(job['folder']).name;f=Path(job['folder']);where=OUT/name
  resuming=where.exists() and (where/'segments.json').exists()
  if resuming:
   rec=load(where/'initial-preservation/results.json')[0];bound=load(where/'initial-preservation/binding.json');source=Path(load(job['dispatch'])['repositoryRoot'])
   assert (where/'ended-round-state-repair/proof.json').exists() or (self.extension and (f/'post-timeout-state-repair/proof.json').exists())
   self.preflight(job,rec)
  else:
   where.mkdir(exist_ok=False);rec,bound,source=self.preserve_initial(job,where)
  original_runtime=load(f/'runtime.json');binding=dict(bound);binding.pop('newThread',None);binding['runId']=rec['accepted']['runId']
  report=Path(rec['report']);native=Path(load(rec['accepted']['recoveryPath'])['sessionPath'])
  selection=rec['selection'];segments=load(where/'segments.json') if resuming else [];spent=rec['measurement']['wallClockMs']/1000+sum(x['reviewer_wall_seconds'] for x in segments);warning=next((x['deadline']['reminder'] for x in reversed(segments) if x['deadline'].get('reminder')),None)
  controller=Controller(I,where)
  if (where/'controller-key.private.json').exists():
   held=load(where/'controller-key.private.json');assert held['base_url']==controller.base;controller.key=held['key'];assert controller.call('/model/status')['status']=='running'
  else:
   assert controller.call('/health')['lease']=='free';controller.__enter__()
  previous_alive=recorded_work_time(B,f,rec,int(segments[-1]['finished_at']*1000))['seconds'] if segments else spent
  # An explicitly authorized extension is a distinct capped stage. Earlier
  # timeout, work intervals and all original segments remain historical facts.
  if self.extension:
   previous_alive=sum(s['reviewer_wall_seconds'] for s in segments if s.get('post_timeout_stage'))
   if previous_alive>=3600:
    raise ValueError('The authorized additional work budget is already exhausted')
   warning=None
   save(where/'post-timeout-authorization.json',self.extension)
  safe=False;daemon=None;machine=None;observer=None;old_path=os.environ['PATH']
  os.environ['PATH']=str(f/'bin')+os.pathsep+old_path
  try:
   os.environ['STRATA_API_KEY']=controller.key;os.environ['QWEN_ARW_MODEL_BASE']=controller.model_base+'/v1';os.environ['QWEN_ARW_RUNTIME_FILE']=str(f/'runtime.json')
   observer_dir=where/'http-observers'/str(time.time_ns());observer_dir.mkdir(parents=True)
   observer=HttpArchive(f/'arw-installation/codex-home/logs_2.sqlite',observer_dir);observer.thread.start()
   # Continuations resume threads bound to the 100K tier, whatever the installation default is.
   options={'model':selection['model'],'context_window':156584,'engine_overrides':selection['engine_overrides'],'request_defaults':selection['sampling'],'engine_environment':selection['engine_environment'],'fit_max_tokens':False}
   held_status=controller.call('/model/status')
   if held_status['status']=='running':
    status=held_status;load_s=0
   else:
    assert held_status['status']=='stopped'
    status,load_s=controller.start(**options)
   work_clock=ReviewWorkClock(observer_dir/'review-work-events.json')
   work_start=time.time()
   budget_alive=lambda:previous_alive+work_clock.elapsed(work_start,time.time())
   job_offset=log_offset(I,selection['model'])
   save(observer_dir/'job-log-offset.json',{'offset':job_offset,'scope':'Only phases executed under this acquired ownership; stopped intervals excluded'})
   save(observer_dir/'start-status.json',{'status':status,'load_s':load_s,'startup_instructions':rec['startup_instructions'],'compaction_prompt_policy':rec['compaction_prompt_policy']})
   assert status['native_health']['max_context']==156584
   assert status['native_health']['startup_instructions']['sha256']==rec['startup_instructions']['sha256']
   suffix='-'+str(time.time_ns())
   daemon_log=(where/('daemon'+suffix+'-stderr.log')).open('x');daemon_out=(where/('daemon'+suffix+'-stdout.jsonl')).open('x')
   daemon=subprocess.Popen(['node',str(R/'tools/reviewer/arw_runtime.mjs'),'daemon',str(f/'runtime.json')],stdin=subprocess.PIPE,stdout=daemon_out,stderr=daemon_log,text=True,cwd=R)
   reader=(where/('daemon'+suffix+'-stdout.jsonl')).open();ready=read_daemon_message(reader,daemon);assert ready.get('ready')
   machine=Machine(source,f/'runtime.json',where)
   before=machine.call('list_agents',{'runId':binding['runId']});assert before['threadId']==rec['runtime_result']['threadId'] and before['state']=='exited' and before['taskState']=='ended'
   save(observer_dir/'native-before.json',before)
   while budget_alive()<3600:
    work_clock.set_working(True,time.time())
    round_dir=where/f'round-{len(segments)+1}';round_dir.mkdir()
    # Upstream followup requires an empty bound report. Save each prior artifact first.
    (round_dir/'report-before.jsonl').write_bytes(report.read_bytes());prior_sha=sha(report)
    reminder=('The previous turn ended before the original task and its required delivery were complete. Continue the SAME original Commit Audit task in this thread using its existing history and unchanged Request. Do the remaining work, write the COMPLETE report to the exact Request-bound draftPath, verify it, then return only the required status JSON. A progress statement or promise is not delivery. The previous draft was preserved before this round and the bound path is now empty because the native follow-up requires it; restore your own established judgments and finish the remaining work. Do not read other instances, hidden expectations, harness code or external history. Keep the original restrictions and do not request extra authorization. This continues the same initial-review budget; it does not reset the deadline.')
    if name in ('low-1','low-2','low-4') or segments and segments[-1]['terminal_kind'] in ('recoverable-tool-response-failure','recoverable-tool-argument-response-failure'):
     failure_message = segments[-1]['terminal'].get('error',{}).get('message') if segments and segments[-1]['terminal_kind'] in ('recoverable-tool-response-failure','recoverable-tool-argument-response-failure') else 'stream disconnected before completion: [invalid_response] Model returned unknown tool: exec_command'
     reminder += ' A preceding model-generation request failed with: '+failure_message+'. The rejected tool call WAS NOT EXECUTED; this was not a shell-command execution result.'
     if 'Unterminated string starting at:' in failure_message:
      reminder += ' Your generated tool arguments were incomplete or invalid JSON. Use the current tool schema, correctly escape quotes and newlines, and keep each call short. If a complete report is too long for one tool call, write it in several smaller valid calls; do not keep repeating a large truncated call.'
     reminder += ' The original observed failure occurred during automatic context summarization. When asked to compact or summarize, return only the requested summary and do not call tools. During ordinary review, use only the tool names declared by the current request. Use the actual preserved history and results, avoid replaying successful actions, and continue the unfinished review. The original failure remains recorded.'
    reminder += f' Remaining active initial-review budget is approximately {max(0,3600-budget_alive()):.0f} seconds; do not spend it repeating unchanged checks. Finish only if the required review and delivery are complete.'
    if self.extension:
     reminder=reminder.replace('This continues the same initial-review budget; it does not reset the deadline.',
      'The original initial-review deadline was exceeded and remains recorded. The user explicitly authorized this separate additional solving stage, capped at 60 minutes of review work. Stops and idle between ended turns are excluded. Finish the same original task; this is not a new independent review.')
    task=dict(binding,handoff=bound['handoff']+'\n\n'+reminder)
    save(round_dir/'binding.json',task);offset=log_offset(I,selection['model']);submitted=time.time()
    report.write_bytes(b'')
    save(round_dir/'engine-log-offset.json',{'offset':offset})
    save(round_dir/'submission-intent.json',{'status':'unknown-until-ack','submitted_at':submitted,'runId':binding['runId'],'threadId':rec['runtime_result']['threadId'],'report_before_sha256':prior_sha,'prior_active_seconds':spent,'remaining_seconds':max(0,3600-budget_alive())})
    try:
     accepted=machine.call('followup_task',task)
    except RuntimeError as rejected:
     try:detail=json.loads(str(rejected))
     except ValueError:raise rejected
     if detail.get('message')!='Native Agent facts are incomplete.' or not segments or segments[-1]['terminal_kind'] not in ('recoverable-tool-response-failure','recoverable-tool-argument-response-failure'):raise
     snapshot=machine.call('list_agents',{'runId':binding['runId']})
     assert snapshot.get('completion') and snapshot['threadId']==rec['runtime_result']['threadId']
     assert not snapshot['pendingRequests'] and not snapshot['snapshot']['clientRequests']
     assert len(snapshot['snapshot']['members'])==1 and snapshot['snapshot']['members'][0]['state']=='failed'
     save(round_dir/'followup-rejected-before-acceptance.json',{'error':detail,'snapshot':snapshot,'model_requests_for_rejected_followup':0})
     machine.close();machine=None
     reset=round_dir/'harness-reset';reset.mkdir()
     mp=reset/'maintenance.json'
     stop=subprocess.run(['node',str(B/'close-failed-native.mjs'),str(f/'runtime.json'),str(mp)],capture_output=True,text=True,timeout=45)
     (reset/'maintenance-stdout.jsonl').write_text(stop.stdout);(reset/'maintenance-stderr.log').write_text(stop.stderr)
     reset_wire=load(mp);assert reset_wire.get('ok') and reset_wire['result']['status']=='ready'
     daemon.stdin.close();secondary=read_daemon_message(reader,daemon);save(reset/'secondary-cleanup.json',secondary);daemon.wait(timeout=30)
     assert not Path('/proc',str(reset_wire['result']['managerPid'])).exists()
     daemon_log=(reset/'daemon-stderr.log').open('x');daemon_out=(reset/'daemon-stdout.jsonl').open('x')
     daemon=subprocess.Popen(['node',str(R/'tools/reviewer/arw_runtime.mjs'),'daemon',str(f/'runtime.json')],stdin=subprocess.PIPE,stdout=daemon_out,stderr=daemon_log,text=True,cwd=R)
     reader=(reset/'daemon-stdout.jsonl').open();restored=read_daemon_message(reader,daemon);assert restored.get('ready')
     machine=Machine(source,f/'runtime.json',where)
     restored_state=machine.call('list_agents',{'runId':binding['runId']});assert restored_state['state']=='exited' and restored_state['threadId']==rec['runtime_result']['threadId']
     accepted=machine.call('followup_task',task)
    assert accepted['runId']==binding['runId'] and accepted['deliveryStatus']=='accepted';save(round_dir/'accepted.json',accepted)
    timer=None;started=None;last_progress=0;cursor=0
    while True:
     observation=machine.call('list_agents',{'runId':binding['runId']});save(round_dir/'latest.json',observation)
     assert observation['threadId']==rec['runtime_result']['threadId'],'Original native thread changed'
     m=observation.get('measurement',{})
     if started is None and current_round_started(observation,submitted):
      started=m['startedAt']/1000
      timer=ReviewDeadline(round_dir,accepted,started,phase='initial',start_source='User-authorized post-timeout stage' if self.extension else 'Recorded review work intervals; tools and active recovery counted, shutdown and sleep excluded',work_elapsed=budget_alive)
      if warning is not None:timer.value['reminder']=warning
     if timer:
      timer.advance(machine,observation)
      if timer.value['reminder'] is not None:warning=timer.value['reminder']
      facts=observation.get('snapshot',{})
      if budget_alive()>=3600 and not timer.value['interrupt'] and not observation.get('completion') and facts.get('factsComplete') is False:
       assert len(facts.get('members',[]))==1 and facts['members'][0]['state']=='active'
       assert facts.get('unknownReasons')==[observation['threadId']+': current native turn context is missing.']
       intent={'scope':'Original cumulative initial-review hard deadline','at':time.time(),'observation':observation,'original_interrupt':None}
       save(round_dir/'cutoff-missing-native-context.json',intent)
       try:
        receipt=machine.call('interrupt_agent',{'runId':binding['runId'],'turnId':observation['turnId']})
        assert receipt.get('accepted');intent['original_interrupt']=receipt
       except RuntimeError as error:
        assert any(message in str(error) for message in ('Native group facts are incomplete for interruption.','Active native turn changed.'))
        intent['original_interrupt_error']=str(error);intent['protected_stop_started_at']=time.time()
        intent['protected_stop']=controller.stop();intent['protected_stop_completed_at']=time.time()
        assert intent['protected_stop']['status']=='stopped'
        work_clock.set_working(False,intent['protected_stop_completed_at'])
       save(round_dir/'cutoff-missing-native-context.json',intent)
       timer.value['interrupt']={'status':'accepted' if intent.get('original_interrupt') else 'original-refused-protected-model-stopped','record':str(round_dir/'cutoff-missing-native-context.json')}
       save(timer.path,timer.value)
     current_active=spent+(m.get('wallClockMs',0)/1000 if started is not None else 0)
     save(OUT/'progress.json',{'status':'running-approved-continuations','pid':os.getpid(),'current':name,'runId':binding['runId'],'threadId':rec['runtime_result']['threadId'],'round':len(segments)+1,'active_seconds':current_active,'review_work_seconds':budget_alive(),'remaining_seconds':max(0,3600-budget_alive()),'runtime_state':observation.get('state'),'observer_rows':observer.rows,'observer_error':observer.error,'at':time.time()})
     if time.monotonic()-last_progress>30:
      print(json.dumps({'instance':name,'threadId':rec['runtime_result']['threadId'],'round':len(segments)+1,'active_minutes':round(current_active/60,2),'runtime':observation.get('state'),'completion':observation.get('completion')}),flush=True);last_progress=time.monotonic()
     if started is not None and observation.get('completion') and observation.get('state') not in ('starting','running','working'):break
     if started is None and observation.get('taskState')=='unknown':
      raise RuntimeError('Accepted follow-up was not delivered; preserve the receipt and investigate instead of treating an old terminal as the new round')
     observation_wait=machine.call('wait_agent',{'runId':binding['runId'],'cursor':cursor,'timeout_ms':10000},timeout=30);cursor=observation_wait.get('cursor',cursor)
    assert started is not None and isinstance(m.get('wallClockMs'),(int,float))
    kind,terminal=terminal_kind(native,observation,report)
    if m.get('finishedAt') is None:
     from datetime import datetime
     event=next(e for e in reversed([json.loads(l) for l in native.read_text().splitlines()]) if e.get('payload',{}).get('type') in ('task_complete','turn_aborted') and e['payload'].get('turn_id')==observation['turnId'])
     save(round_dir/'original-measurement-missing-end.json',m);m=dict(m)
     m['finishedAt']=int(datetime.fromisoformat(event['timestamp'].replace('Z','+00:00')).timestamp()*1000);m['wallClockMs']=m['finishedAt']-m['startedAt'];assert m['wallClockMs']>=0
     if isinstance(event['payload'].get('duration_ms'),(int,float)):assert abs(m['wallClockMs']-event['payload']['duration_ms'])<1000
    seconds=m['wallClockMs']/1000;phases,tokens=capture_engine_log(I,selection['model'],offset,round_dir)
    segment={'round':len(segments)+1,'threadId':rec['runtime_result']['threadId'],'accepted':accepted,'runtime_result':observation,'measurement':m,'reviewer_wall_seconds':seconds,'started_at':started,'finished_at':m['finishedAt']/1000,'engine_requests':phases,'engine_tokens':tokens,'report_sha256':sha(report),'report_bytes':report.stat().st_size,'terminal_kind':kind,'terminal':terminal,'deadline':timer.facts()}
    if tokens is None:segment['pre_execution_rejection']=pre_execution_rejection(terminal,phases,I)
    if self.extension:segment['post_timeout_stage']=str(self.post_timeout_approval)
    (round_dir/'review-after.jsonl').write_bytes(report.read_bytes());save(round_dir/'result.json',segment);segments.append(segment);spent+=seconds
    save(where/'segments.json',segments)
    print(json.dumps({'instance':name,'round_closed':len(segments),'kind':kind,'active_minutes':spent/60,'report_bytes':report.stat().st_size}),flush=True)
    if kind not in ('premature-normal-end','recoverable-tool-response-failure','recoverable-tool-argument-response-failure') or budget_alive()>=3600:
     work_clock.set_working(False,time.time())
     break
   safe=True
   capture_engine_log(I,selection['model'],job_offset,observer_dir)
   merged=''.join((where/f"round-{s['round']}"/'engine-request-log.txt').read_text()+'\n' for s in segments)
   (where/'engine-request-log.txt').write_text(merged)
   final_phases=parse_engine_log(merged);final_tokens=continuation_token_totals(segments,final_phases)
   generation=None
   if segments and segments[-1]['terminal_kind'] in ('ready','final-status-format-only') and report.stat().st_size:
    gen_dir=where/'generation-final';gen_dir.mkdir();dispatch=load(job['dispatch']);generation=generate_original(source,dispatch,dispatch['handoffs'][0],gen_dir)
   stopped=controller.stop();assert stopped['status']=='stopped'
   machine.close();machine=None
   maintenance=where/'maintenance-close.json'
   closed=subprocess.run(['node',str(B/'close-failed-native.mjs'),str(f/'runtime.json'),str(maintenance)],capture_output=True,text=True,timeout=45)
   (where/'maintenance-close-stdout.jsonl').write_text(closed.stdout);(where/'maintenance-close-stderr.log').write_text(closed.stderr)
   wire=load(maintenance);assert wire.get('ok') and wire['result']['status']=='ready','Maintenance could not confirm stopped native work'
   daemon.stdin.close();cleanup=read_daemon_message(reader,daemon);save(where/'arw-cleanup.json',cleanup)
   daemon.wait(timeout=30)
   assert not Path('/proc',str(wire['result']['managerPid'])).exists(), 'Manager still alive after maintenance'
   rt=load(f/'runtime.json')
   script='const {readAppServerProcessIdentity}=await import(process.argv[1]);console.log(JSON.stringify(await readAppServerProcessIdentity({runtimeDirectory:process.argv[2]})));'
   app=load_json_output=subprocess.check_output(['node','--input-type=module','-e',script,(Path(rt['repositoryRoot'])/'lib/background-agent/process-identity.mjs').as_uri(),rt['runtimeDirectory']],text=True)
   app=json.loads(app);assert app['state'] in ('absent','ended'),app
   cleanup={'cleanup':wire['result'],'manager_exit_confirmed':True,'app_server':app,'secondary_cleanup_retained':str(where/'arw-cleanup.json')}
   save(where/'single-authoritative-cleanup-proof.json',cleanup)
   observer.close();observer=None
   assert sha(I/load(B/'baseline.json')['profile']['installation_relative_path'])==load(B/'baseline.json')['profile']['sha256']
   combined={k:rec['engine_tokens'][k]+final_tokens[k] for k in final_tokens}
   elapsed=segments[-1]['finished_at']-rec['measurement']['startedAt']/1000
   value={'status':'closed-continued-original-instance','instanceId':job['instanceId'],'threadId':rec['runtime_result']['threadId'],'initial_record':str(where/'initial-preservation/results.json'),'initial_report_sha256':rec['report_sha256'],'final_report_path':str(report),'final_report_sha256':sha(report),'segment_count':len(segments),'initial_active_seconds':rec['measurement']['wallClockMs']/1000,'continuation_active_seconds':sum(s['reviewer_wall_seconds'] for s in segments),'combined_active_seconds':spent,'elapsed_seconds_including_stopped_gaps':elapsed,'excluded_non_work_interval_seconds':elapsed-spent,'initial_engine_tokens':rec['engine_tokens'],'continuation_engine_tokens':final_tokens,'combined_engine_tokens':combined,'stop':stopped,'native_cleanup':cleanup,'generation':generation,'terminal_kind':segments[-1]['terminal_kind'],'ownership_returned':False,'independent_repeats_added':0,'full_native_inspection':'pending'}
   if self.extension:value['post_timeout_stage']={'approval':str(self.post_timeout_approval),'work_seconds':budget_alive(),'original_timeout_preserved':True}
   controller.__exit__(None,None,None);value['ownership_returned']=True;save(where/'result.json',value);save(where/'run-finished.json',{'ownership_returned':True,'model_stopped':True,'finished_at':time.time()})
   print(json.dumps({'instance':name,'status':value['status'],'terminal_kind':value['terminal_kind'],'combined_active_minutes':spent/60,'ownership_returned':True}),flush=True)
   return value
  except BaseException as e:
   if 'work_clock' in locals():work_clock.set_working(False,time.time())
   save(where/'recovery-required.json',{'status':'paused-for-main','error':str(e),'pid':os.getpid(),'daemon_pid':daemon.pid if daemon else None,'private_ownership_file':str(controller.credential),'model_retries':False,'completed_segments':len(segments),'safe_terminal_observed':safe})
   raise
  finally:
   os.environ['PATH']=old_path
   for k in ('STRATA_API_KEY','QWEN_ARW_MODEL_BASE','QWEN_ARW_RUNTIME_FILE'):os.environ.pop(k,None)


if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--batch-directory',required=True)
 parser.add_argument('--installation-directory',required=True)
 parser.add_argument('--runtime-approval',help='Explicitly approved local frozen-runtime exception receipt')
 parser.add_argument('--post-timeout-approval',help='Exact two-instance additional-stage authorization and current harness hashes')
 parser.add_argument('--names',nargs='+',required=True)
 args=parser.parse_args()
 runner=ContinuationRunner(args.batch_directory,args.installation_directory,args.runtime_approval,args.post_timeout_approval)
 B=runner.batch;OUT=runner.output;results=[]
 try:
  for name in args.names:
   job=next(j for j in load(B/'jobs.json') if Path(j['folder']).name==name)
   assert not (OUT/name/'run-finished.json').exists(),'Closed-stage receipt must be preserved separately before an authorized extension'
   results.append(runner.continue_one(job))
  save(OUT/'approved-continuation-results.json',results)
  save(OUT/'progress.json',{'status':'all-authorized-continuations-closed-awaiting-main-inspection-and-scoring','pid':os.getpid(),'closed_names':args.names,'new_independent_repeats':0,'finished_at':time.time()})
 except BaseException as e:
  save(OUT/'progress.json',{'status':'paused-for-main','pid':os.getpid(),'error':str(e),'model_retries':False,'at':time.time()});raise
