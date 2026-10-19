"""Run unchanged ARW handoffs through unchanged ARW Reviewer runtime APIs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shlex
import subprocess
import sys
import threading
import time

from tools.reviewer.arw_metrics import collect_cost
from tools.metrics.strata_tokens import parse_engine_log, sum_engine_tokens, engine_rates
from tools.reviewer.review_deadlines import ReviewDeadline
from tools.metrics.review_work_time import ReviewWorkClock
from tools.reviewer.wsl_client import ROOT,save
from tools.metrics.context_capacity import CONTEXT_WINDOWS
from tools.metrics.prompt_policy import compaction_config
from tools.reviewer.providers import (api_model, api_provider, credential_deny_paths, credential_present, link_login, process_environment,
    provider_config, release_login, service_tier, shell_exclude, validate_api_selection, web_search_mode)

sys.path.append(str(ROOT / 'src'))
from startup_instructions import startup_prompt_bytes


ARW_PAUSE_PREFIX='The Reviewer runtime paused this same task after '


def strata_provider(installation, context_window=None):
    """ARW provider entry: callers choose only the model and, optionally, a published context tier."""
    if context_window is not None and type(context_window) is not int:
        raise ValueError('Unsupported measurement context window')
    return {'driver': 'strata', 'installationDirectory': str(installation),
            **({} if context_window is None else {'contextWindow': context_window})}


def local_review_catalog(source, target, model, context_window=None, strata_installation=None):
    """Declare installed text search and route guardian to the local model."""
    catalog = json.loads(Path(source).read_text())
    if strata_installation is not None:
        # ARW's own Strata provider: it takes the lease, starts the model with the installation
        # defaults and a published context tier, and applies its continuation, pause and work-budget policy.
        catalog['providers'] = {'qwen_strata': strata_provider(strata_installation, context_window)}
    slug = 'qwen3.8-flash-next-' + model.lower()
    selected = next((m for m in catalog['models'] if m['slug'] == slug), None)
    if selected is None:
        raise ValueError('Selected local model is absent from measurement catalog')
    selected['auto_review_model_override'] = slug
    # Borrowed OpenAI metadata advertised image search, which the installed
    # text-only Brave adapter does not implement.
    selected['web_search_tool_type'] = 'text'
    if context_window is not None and strata_installation is None:
        if type(context_window) is not int or context_window not in (80000,125000,188000,250000,*CONTEXT_WINDOWS):
            raise ValueError('Unsupported measurement context window')
        selected['context_window'] = context_window
        selected['max_context_window'] = context_window
    save(target, catalog)
    return target


class Machine:
    def __init__(self,source,configuration,folder):
        self.source,self.folder=source,folder
        self.log=(folder/'machine.jsonl').open('a')
        self.errors=(folder/'machine-stderr.log').open('a')
        self.queue=queue.Queue();self.number=0
        env=dict(os.environ,QWEN_ARW_RUNTIME_FILE=str(configuration))
        self.proc=subprocess.Popen(['node',str(ROOT/'tools/reviewer/arw_runtime.mjs'),'client','background-agent'],
            cwd=source,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.errors,text=True)
        self.reader=threading.Thread(target=self.read,daemon=True);self.reader.start()

    def read(self):
        for line in self.proc.stdout:
            self.log.write(line);self.log.flush()
            try:self.queue.put(json.loads(line))
            except ValueError:pass

    def call(self,operation,value,timeout=120):
        self.number+=1;identifier=str(self.number)
        self.proc.stdin.write(json.dumps({'id':identifier,'operation':operation,'input':value})+'\n')
        self.proc.stdin.flush()
        result=self.queue.get(timeout=timeout)
        if result.get('id')!=identifier:raise RuntimeError('Unexpected machine response identity')
        if not result.get('ok'):raise RuntimeError(json.dumps(result.get('error')))
        return result['result']

    def close(self):
        self.proc.stdin.close();self.proc.wait(timeout=20);self.reader.join(timeout=5)
        self.log.close();self.errors.close()


def native_tokens(measurement):
    usage=measurement.get('usage',{})
    i,c,o=(usage.get(k) for k in ('inputTokens','cachedInputTokens','outputTokens'))
    return {'uncached_input':i-c if type(i) is int and type(c) is int and i>=c else None,
            'cached_input':c,'output':o}


def capture_engine_log(installation,model,offset,folder,measurement_host):
    content=measurement_host.log_bytes_since(model,offset).decode(errors='replace')
    (folder/'engine-request-log.txt').write_text(content)
    requests=parse_engine_log(content)
    save(folder/'engine-rates.json',engine_rates(requests))
    return requests,sum_engine_tokens(requests)


def stop_and_capture_engine_log(controller,installation,model,offset,folder,measurement_host=None):
    """Wait for confirmed stop before the final snapshot, including late counters."""
    stopped=controller.stop()
    if stopped.get('status')!='stopped':
        raise RuntimeError('Model stop is unconfirmed; do not capture final counters or start the next instance')
    requests,tokens=capture_engine_log(installation,model,offset,folder,measurement_host)
    return stopped,requests,tokens


def log_offset(installation,model,measurement_host):
    return measurement_host.log_offset(model)


def review_request_path(preparation, handoff):
    instance=next(i for c in json.loads(Path(preparation['preparedPath']).read_text())['contracts']
                  for i in c['instances'] if i['instanceId']==handoff['instanceId'])
    if instance.get('requestPath'):
        return instance['requestPath']
    # Native Spec Readiness contracts deliberately omit this dispatch field.
    # Read the exact handoff reference without changing the prepared record.
    prompt=handoff['input']['handoff'] if 'input' in handoff else handoff['prompt']
    references=re.findall(r'Read the immutable Reviewer Request from this exact path relative to the scenario root: (\S+\.json)\.', prompt)
    if len(references)!=1:
        raise ValueError('Requires one exact native Reviewer Request reference')
    relative=Path(references[0]);project=Path(handoff['scenarioRoot']).resolve()
    request=(project/relative).resolve()
    if relative.is_absolute() or '..' in relative.parts or not request.is_relative_to(project) or not request.is_file():
        raise ValueError('Native Reviewer Request reference is outside or absent from its scenario')
    return str(request)


def review_shell_environment(runtime_file):
    """Restore this measurement's arw shim after Bash login initialization."""
    runtime=Path(runtime_file).resolve()
    shim=runtime.parent/'bin'
    if not (shim/'arw').is_file():
        raise ValueError('Measurement arw entry is missing')
    bootstrap=shim/'resolve-arw.sh'
    bootstrap.write_text('export PATH='+shlex.quote(str(shim))+':"$PATH"\n')
    save(runtime.parent/'shell-bootstrap.json',{
        'path':str(bootstrap),'sha256':hashlib.sha256(bootstrap.read_bytes()).hexdigest(),
        'purpose':'Resolve the measurement JSONL arw entry after login-shell PATH changes',
        'global_shell_configuration_modified':False})
    return {'QWEN_ARW_RUNTIME_FILE':str(runtime),'BASH_ENV':str(bootstrap)}


# The provider key is read by Codex itself through env_key; Reviewer shell commands never need it (user 2026-10-12).
REVIEW_SHELL_EXCLUDE=['STRATA_API_KEY']


def review_shell_policy(runtime_file,exclude=REVIEW_SHELL_EXCLUDE):
    """Codex shell_environment_policy for Reviewer commands: hide the provider key, restore the arw shim."""
    return {'exclude':list(exclude),'set':review_shell_environment(runtime_file)}


def driver_context(selection):
    """A driver-owned run states its harness window and compaction limit; nothing falls back to a guess."""
    window,limit=selection.get('context_window'),selection.get('auto_compact_token_limit')
    if type(window) is not int or type(limit) is not int or not 0<limit<window:
        raise ValueError('A driver-owned selection needs its context_window and auto_compact_token_limit')
    return window,limit


SPEC_STAGES={'runtime-migration':0,'artifact-promotion':1}


def spec_repetition_order(jobs):
    """Order each Spec Readiness repetition runtime-migration, then artifact-promotion; each runs in its own fresh root thread."""
    return sorted(jobs,key=lambda j:(j[1]['instanceId'].rsplit('-',1)[1],SPEC_STAGES[j[1]['scenarioId']])
                  if j[1].get('scenarioId') in SPEC_STAGES else ('',0))


def review_settings(selection,runtime_file,folder):
    """Native Reviewer settings. A selection without a provider is the Strata path and keeps its exact settings."""
    provider=api_provider(selection)
    if provider is None:
        settings={'model':'qwen3.8-flash-next-'+selection['model'].lower(),'modelProvider':'qwen_strata',
            'reasoningEffort':selection['effort'],'serviceTier':service_tier(selection),'config':{
                'shell_environment_policy':review_shell_policy(runtime_file),
                'model_providers':{'qwen_strata':{'name':'Local Strata','base_url':os.environ['QWEN_ARW_MODEL_BASE'],
                    'wire_api':'responses','env_key':'STRATA_API_KEY','requires_openai_auth':False,'supports_websockets':False}}}}
        if selection.get('model_owner')!='arw':  # ARW's provider sets the window from the selected installation tier
            settings['config']['model_context_window']=driver_context(selection)[0]
        if selection.get('loop_reminder')=='on':  # deprecated frontend loop reminder, off unless selected
            settings['config']['model_providers']['qwen_strata']['http_headers']={'X-Loop-Reminder':'on'}
    else:
        # The provider's own window and compaction defaults apply unless the selection states a compaction limit.
        # With a relay (run_api, D14) Codex reaches the provider through it; the endpoint is the only change.
        relay=os.environ.get('QWEN_API_RELAY_BASE') if provider['relay'] else None
        settings={'model':api_model(selection),'modelProvider':provider['codex_id'],
            'reasoningEffort':selection['effort'],'serviceTier':service_tier(selection),'config':{
                'shell_environment_policy':review_shell_policy(runtime_file,shell_exclude(provider)),
                **provider_config(provider,relay)}}
    if web_search_mode(selection) is not None:
        settings['config']['web_search']=web_search_mode(selection)
    if 'auto_compact_token_limit' in selection:
        settings['config']['model_auto_compact_token_limit']=selection['auto_compact_token_limit']
    settings['config']=compaction_config(settings['config'],folder/'prompt-policy',
        include_project_base=selection.get('project_compaction_instructions',True))
    return settings


def api_startup_instructions(selection):
    """D4 for API providers: the project startup prompt as Strata loads it (deprecated loop block removed).
    None on the Strata path, where the service appends it; {'enabled': False} only for an explicit no-prompt arm."""
    if api_provider(selection) is None:
        return None
    if selection.get('startup_instructions',True) is False:
        return None
    source_raw=(ROOT/'config/prompts/startup-instructions.txt').read_bytes()
    raw=startup_prompt_bytes(source_raw,False)
    return {'enabled':True,'placement':'appended to developer instructions','path':'config/prompts/startup-instructions.txt',
            'sha256':hashlib.sha256(raw).hexdigest(),'source_sha256':hashlib.sha256(source_raw).hexdigest(),
            'loop_prevention_enabled':False,'text':raw.decode('utf-8').strip()}


def execute_review(machine,source,preparation,handoff,folder,selection,catalog,run_metadata=None,previous=None,new_thread=False):
    native_input=handoff.get('input')
    project=Path(native_input['cwd'] if native_input else handoff['scenarioRoot']);folder.mkdir(parents=True,exist_ok=False)
    generation=next((g for g in preparation['generations'] if g['instanceId']==handoff['instanceId']),None)
    # Code Spec and Code Standards handoffs carry no Request; resolve it only
    # when the report binding must come from that Request.
    report=Path(native_input['reportPath']) if native_input else Path(handoff['resultPath']) if 'resultPath' in handoff else Path(generation['draftPath']) if generation and 'draftPath' in generation else Path(json.loads(Path(review_request_path(preparation,handoff)).read_text())['draftPath'])
    report.parent.mkdir(parents=True,exist_ok=True)
    if not report.exists():report.write_text('')
    instructions=native_input['instructions'] if native_input else (project/f'docs/agents/roles/{handoff["reviewerId"]}.md').read_text()+'\n'+(project/'docs/agents/reviewer.md').read_text()
    identity=preparation['identity'];state=Path(native_input['stateDirectory']) if native_input else source/'.tmp/codex'/identity['sessionId']/'measurement-recovery'
    state.mkdir(parents=True,exist_ok=True)
    settings=review_settings(selection,os.environ['QWEN_ARW_RUNTIME_FILE'],folder)
    prompt_receipt=json.loads((folder/'prompt-policy/compact-prompt-policy.json').read_text())
    expected=selection.get('compaction_prompt_policy')
    if expected and prompt_receipt['rendered_sha256']!=expected['rendered_sha256']:
        raise RuntimeError('Compaction prompt changed after approved startup preflight')
    bound={**native_input,'settings':settings} if native_input else {'role':handoff['agentType'],'identity':{'kind':'isolated','instanceId':handoff['instanceId']},
        'instructions':instructions,'handoff':handoff['prompt'],'cwd':str(project),
        'writePaths':[str(report.parent)],'reportPath':str(report),'stateDirectory':str(state),'settings':settings}
    startup=api_startup_instructions(selection)
    if startup:
        # Strata appends this prompt to the caller instructions server-side; an API provider gets the same bytes
        # appended to the developer instructions (D4), never replacing the Role.
        bound['instructions']=bound['instructions'].rstrip('\n')+'\n\n'+startup['text']
    note=selection.get('measurement_note')
    if note:
        # Frozen capability-measurement addendum: appended only, never replacing the native handoff or Role.
        raw=(ROOT/note['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=note['sha256']:
            raise RuntimeError('Measurement note differs from the approved selection')
        bound['handoff']=bound['handoff'].rstrip('\n')+'\n\n'+raw.decode().strip()
    if new_thread:
        if previous is not None:
            raise ValueError('A same-thread follow-up cannot request a new thread')
        bound['newThread']=True
    if previous is not None:
        if not previous.get('complete'):
            raise ValueError('Same-thread continuation requires a completed original task')
        # The native recovery identity belongs to the thread, while the new
        # frozen handoff retains its own instance ID and report binding.
        prior_binding=json.loads((Path(previous['binding_path'])).read_text())
        bound['identity']=prior_binding['identity']
        bound['runId']=previous['accepted']['runId']
    save(folder/'binding.json',bound)
    record={'instanceId':handoff['instanceId'],'role':handoff['reviewerId'],'scenarioId':handoff.get('scenarioId'),
        'report':str(report),'binding_path':str(folder/'binding.json'),'selection':selection,'started_at':time.time(),'prompt_sha256':hashlib.sha256(bound['handoff'].encode()).hexdigest()}
    record.update(run_metadata or {})
    if note:record['measurement_note']=note
    if api_provider(selection) is not None:
        record['provider']=api_provider(selection)
        record['startup_instructions']=startup or {'enabled':False}
        record['instructions_sha256']=hashlib.sha256(bound['instructions'].encode()).hexdigest()
    record['compaction_prompt_policy']=prompt_receipt
    # Bind the actual startup snapshot before dispatch, including a failed or
    # interrupted submission that never returns a terminal result.
    save(folder/'result.json',record)
    record['accepted']=followup_when_idle(machine,bound) if previous else machine.call('spawn_agent',bound)
    save(folder/'result.json',record)
    record=observe_review(machine,record,folder)
    if previous is not None and record['runtime_result'].get('threadId')!=previous['runtime_result'].get('threadId'):
        raise RuntimeError('Same-thread continuation changed the native Reviewer thread')
    record['report_sha256']=hashlib.sha256(report.read_bytes()).hexdigest()
    save(folder/'result.json',record)
    return record


def native_work_start(result):
    """ARW measurement.startedAt in seconds: set when the native root exists, after the provider loaded the model."""
    started=result.get('measurement',{}).get('startedAt')
    return started/1000 if type(started) in (int,float) and started>0 else None


def followup_when_idle(machine,bound,*,poll=5,limit=3600):
    """Send a same-thread follow-up once ARW has finished the original task.

    reviewer-busy means ARW is still running (or natively continuing) the original task;
    wait for its terminal state instead of abandoning the run. An ARW early-exit pause
    belongs to the user and is not waited out."""
    deadline=time.monotonic()+limit
    while True:
        try:return machine.call('followup_task',bound)
        except RuntimeError as error:
            if '"reviewer-busy"' not in str(error) or time.monotonic()>=deadline:raise
        while True:
            state=machine.call('list_agents',{'runId':bound['runId']})
            if any(n.get('type')=='message' and str(n.get('text','')).startswith(ARW_PAUSE_PREFIX)
                   for n in state.get('notifications',[])):
                raise RuntimeError('ARW paused the original task before the follow-up; the user decides')
            if state.get('completion') and state.get('state') not in ('starting','running','working'):break
            if time.monotonic()>=deadline:raise RuntimeError('Original task did not reach a terminal state for the follow-up')
            time.sleep(poll)


def observe_review(machine,record,folder,*,continuation_start_timeout=120):
    run_id=record['accepted']['runId'];cursor=0;last_progress=0
    awaiting_turn=None;original_thread=None;continuation_requested_at=None
    phase_start=record.get('review_phase_started_at',record['started_at'])
    work_clock=ReviewWorkClock(folder/'review-work-events.json')
    if not work_clock.events:
        work_clock.set_working(True,phase_start)
    elif not work_clock.events[-1]['alive']:
        work_clock.set_working(True,time.time(),estimated=True)
    phase='revision' if record.get('revisions') else 'initial'
    deadline=ReviewDeadline(folder,record['accepted'],phase_start,phase=phase,
        work_elapsed=lambda:work_clock.elapsed(phase_start,time.time()),
        limit_seconds=record.get('selection',{}).get('review_time_limit_seconds') if phase=='initial' else None)
    arw_owned=record.get('selection',{}).get('model_owner')=='arw'
    native_start=None
    while True:
        if record.get('user_pause_at') is not None and time.time()>=record['user_pause_at']:
            record['user_pause']={'at':time.time(),'reason':'User local-machine deadline; do not auto-continue.'}
            record['runtime_result']=machine.call('list_agents',{'runId':run_id})
            record['measurement']=record['runtime_result'].get('measurement',{})
            record['complete']=False
            break
        if awaiting_turn is not None:
            # Reviewer inspect/wait operations reserve managed work. Calling
            # them while upstream prepares changed settings races its safe
            # unload check (entry.work identity), even for an idle root.
            # Observe the atomically persisted receipt without reserving work.
            recovery=json.loads(Path(record['accepted']['recoveryPath']).read_text())
            if recovery.get('threadId')!=original_thread:
                raise RuntimeError('Automatic continuation changed the native thread identity')
            failure=recovery.get('failure') if recovery.get('state')=='failed' else None
            if not failure and (recovery.get('state')=='starting'
                    or not recovery.get('turnId') or recovery['turnId']==awaiting_turn):
                if time.monotonic()-continuation_requested_at>=continuation_start_timeout:
                    record['continuation_dispatch_failure']={'status':'unconfirmed','at':time.time(),
                        'reason':'Accepted continuation did not establish a new native turn within the dispatch wait.',
                        'runtime_result':result,'recovery_state':recovery.get('state')}
                    record['runtime_result']=result;record['measurement']=result.get('measurement',{})
                    record['tokens']=native_tokens(record['measurement']);record['complete']=False
                    break
                time.sleep(.1)
                continue
        result=machine.call('list_agents',{'runId':run_id})
        save(folder/'latest.json',result)
        if native_start is None:native_start=native_work_start(result)
        if arw_owned:
            # ARW enforces the work budget itself; its early-exit pause waits for the user.
            pause=next((n for n in result.get('notifications',[]) if n.get('type')=='message'
                        and str(n.get('text','')).startswith(ARW_PAUSE_PREFIX)),None)
            if pause:
                record['arw_pause']={'at':time.time(),'notification':pause}
                record['runtime_result']=result;record['measurement']=result.get('measurement',{})
                record['tokens']=native_tokens(record['measurement']);record['complete']=False
                break
        else:deadline.advance(machine,result)
        if record.get('selection',{}).get('command_loop_guard',{}).get('enabled'):
            from tools.loop.command_loop_guard import observe_command_loops
            observe_command_loops(machine,record,result,folder)
        if time.monotonic()-last_progress>30:
            print(json.dumps({'role':record['role'],'instanceId':record['instanceId'],'runtime':result.get('state'),
                'completion':result.get('completion'),'wall_s':result.get('measurement',{}).get('wallClockMs',0)/1000}),flush=True)
            last_progress=time.monotonic()
        if awaiting_turn is not None:
            if result.get('threadId')!=original_thread:
                raise RuntimeError('Automatic continuation changed the native thread identity')
            recovery=json.loads(Path(record['accepted']['recoveryPath']).read_text())
            failure=recovery.get('failure') if recovery.get('state')=='failed' else None
            if result.get('recoveryIncomplete'):
                record.setdefault('recovery_limitations',[]).append({
                    'at':time.time(),'upstream_global_recovery_incomplete':True,
                    'turnId':result.get('turnId'),
                    'note':'Preserved global persistence limitation; current dispatch requires its own failure/turn evidence.'})
            if failure:
                record['continuation_dispatch_failure']={'status':'failed','at':time.time(),
                    'failure':failure,'runtime_result':result}
                record['runtime_result']=result;record['measurement']=result.get('measurement',{})
                record['tokens']=native_tokens(record['measurement']);record['complete']=False
                break
            if not result.get('turnId') or result['turnId']==awaiting_turn:
                if time.monotonic()-continuation_requested_at>=continuation_start_timeout:
                    # Acceptance is not proof of a new turn. Preserve unknown
                    # delivery; never resend or count ended-turn idle as work.
                    record['continuation_dispatch_failure']={'status':'unconfirmed','at':time.time(),
                        'reason':'Accepted continuation did not establish a new native turn within the dispatch wait.',
                        'runtime_result':result}
                    record['runtime_result']=result;record['measurement']=result.get('measurement',{})
                    record['tokens']=native_tokens(record['measurement']);record['complete']=False
                    break
                observation=machine.call('wait_agent',{'runId':run_id,'cursor':cursor,'timeout_ms':10000},timeout=30)
                cursor=observation.get('cursor',cursor)
                continue
            awaiting_turn=None
            started=result.get('measurement',{}).get('startedAt')
            at=started/1000 if type(started) in (int,float) else time.time()
            work_clock.set_working(True,at,estimated=True)
        if result.get('completion') and result.get('state') not in ('starting','running','working'):
            record['runtime_result']=result;record['measurement']=result.get('measurement',{})
            record['tokens']=native_tokens(record['measurement'])
            record['complete']=result['completion']['status']=='ready'
            if (not record['complete'] and record.get('selection',{}).get('automatic_continuation')
                    and not deadline.facts().get('interrupt')):
                from tools.reviewer.review_continuations import terminal_kind
                recovery=json.loads(Path(record['accepted']['recoveryPath']).read_text())
                if recovery.get('threadId')!=result.get('threadId') or not recovery.get('sessionPath'):
                    raise RuntimeError('Cannot bind an ended task to its exact native history')
                report=Path(record['report']);native=Path(recovery['sessionPath'])
                kind,terminal=terminal_kind(native,result,report)
                record['terminal_classification']=kind
                if kind in ('premature-normal-end','recoverable-tool-response-failure'):
                    work_clock.set_working(False,time.time())
                    if work_clock.elapsed(phase_start,time.time())<deadline.value['interrupt_after_seconds']:
                        round_folder=folder/'automatic-continuations'/str(len(record.get('continuations',[]))+1)
                        round_folder.mkdir(parents=True,exist_ok=False)
                        prior=report.read_bytes()
                        (round_folder/'report-before.jsonl').write_bytes(prior)
                        prefix=native.read_bytes()
                        save(round_folder/'prior-terminal.json',{'runtime_result':result,'terminal':terminal,
                            'classification':kind,'report_sha256':hashlib.sha256(prior).hexdigest(),
                            'native_session_path':str(native),'native_prefix_bytes':len(prefix),
                            'native_prefix_sha256':hashlib.sha256(prefix).hexdigest()})
                        instruction=('Continue the SAME original review task in this thread using the unchanged Request and existing evidence. '
                            'The required review or bound report delivery is unfinished. Complete the remaining work, personally write '
                            'the complete report to the exact bound path, verify delivery, and return the original required status. '
                            'The prior draft was preserved before this continuation; the bound file is empty as required by the native '
                            'follow-up API. Restore your own established judgments from this thread and finish the missing work. '
                            'This is the same initial-review phase and cumulative budget; do not read other instances or hidden sources.')
                        if kind == 'premature-normal-end':
                            from tools.loop.command_loop_guard import progress_continuation_feedback
                            feedback = progress_continuation_feedback(record, result, folder)
                            if feedback:
                                instruction += '\n\n' + feedback
                        if kind.startswith('recoverable-tool'):
                            instruction+=' The native response failed: '+terminal['error']['message']+'. '
                            instruction+=('That rejected tool call was not executed. Use the current declared tools and valid, short JSON arguments. '
                                'If this was a compaction request, output only the requested summary without tools. '
                                'Other earlier successful actions remain completed.')
                        bound=json.loads(Path(record['binding_path']).read_text())
                        bound.update(runId=run_id,handoff=bound['handoff']+'\n\n'+instruction)
                        save(round_folder/'binding.json',bound)
                        report.write_bytes(b'')
                        from tools.loop.command_loop_guard import progress_external_report_reset
                        progress_external_report_reset(record, folder)
                        continuation_requested_at=time.monotonic()
                        try:accepted=machine.call('followup_task',bound)
                        except BaseException:
                            report.write_bytes(prior)  # a refused continuation must not leave the delivered report empty
                            raise
                        if accepted.get('runId')!=run_id:
                            raise RuntimeError('Automatic continuation changed the native run identity')
                        record.setdefault('continuations',[]).append({'classification':kind,
                            'prior_turn_id':result.get('turnId'),'accepted':accepted,'evidence':str(round_folder)})
                        record['accepted']=accepted
                        awaiting_turn=result.get('turnId')
                        if not awaiting_turn:
                            raise RuntimeError('Ended task has no exact turn identity for continuation')
                        original_thread=result['threadId']
                        save(folder/'result.json',record)
                        continue
            break
        observation=machine.call('wait_agent',{'runId':run_id,'cursor':cursor,'timeout_ms':10000},timeout=30)
        cursor=observation.get('cursor',cursor)
    work_clock.set_working(False,time.time())
    record['finished_at']=time.time()
    record['review_work_seconds']=work_clock.elapsed(phase_start,record['finished_at'])
    record['review_work_seconds_estimated']=any(e.get('estimated',False) for e in work_clock.events)
    record['review_work_time_source']='Persisted review-work intervals; tools and active recovery included, shutdown and ended-turn idle excluded; estimated transitions retained in the ledger.'
    if arw_owned and native_start is not None and phase_start<native_start<=record['finished_at']:
        # ARW-owned dispatch includes the provider's model load (first instance of a batch) and daemon startup.
        # Work starts when ARW creates the native root and sends the first model request.
        record['review_dispatch_work_seconds']=record['review_work_seconds']
        record['review_work_seconds']=work_clock.elapsed(native_start,record['finished_at'])
        record['review_work_time_source']=('From ARW measurement.startedAt (native root created, first model request follows; '
            'provider model load and daemon dispatch excluded) to task end; '+record['review_work_time_source'])
    record.setdefault('deadlines',[]).append(deadline.facts())
    save(folder/'result.json',record)
    return record


def generate_original(source,preparation,handoff,folder):
    generation=next((g for g in preparation['generations'] if g['instanceId']==handoff['instanceId']),None)
    if generation is None:
        return {'artifactPaths':[handoff['input']['reportPath'] if 'input' in handoff else handoff['resultPath']]}
    if 'command' in generation:
        process=subprocess.run(generation['command'],shell=True,cwd=generation['workdir'],
            capture_output=True,text=True)
        (folder/'generation-stdout.txt').write_text(process.stdout)
        (folder/'generation-stderr.txt').write_text(process.stderr)
        return {'exit_code':process.returncode,'command':generation['command'],
            # The original spec-readiness CLI prints the artifact path, not
            # JSON. Keep its exact stdout and do not reinterpret a draft.
            'artifactPaths':[process.stdout.strip()] if process.returncode==0 and process.stdout.strip() else []}
    request=folder/'generation-request.json';response=folder/'generation-result.json'
    save(request,{'repositoryRoot':str(source),'scenarioRoot':generation['workdir'],
        'requestPath':generation['requestPath']})
    process=subprocess.run(['node',str(ROOT/'tools/reviewer/arw_native.mjs'),'commit-audit-generate',
        str(request),str(response)],cwd=generation['workdir'],capture_output=True,text=True)
    (folder/'generation-stdout.txt').write_text(process.stdout)
    (folder/'generation-stderr.txt').write_text(process.stderr)
    return {'exit_code':process.returncode,'result':json.loads(response.read_text()) if response.exists() else None}


def read_daemon_message(stream,process,timeout=60):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        value=stream.readline()
        if value:return json.loads(value)
        if process.poll() is not None:raise RuntimeError('Original ARW daemon exited before its response')
        time.sleep(.1)
    raise RuntimeError('Original ARW daemon response is uncertain')


def commit_audit_generated(generation):
    """Upstream success is {files}; failed generation has status='failed'."""
    result=generation.get('result')
    return (generation.get('exit_code')==0 and isinstance(result,dict)
        and result.get('status')!='failed' and isinstance(result.get('files'),list)
        and bool(result['files']) and all(isinstance(f,dict)
            and isinstance(f.get('sourcePath'),str) and bool(f['sourcePath'])
            and isinstance(f.get('targetPath'),str) and bool(f['targetPath'])
            for f in result['files']))


def audit_generation(machine,source,preparation,handoff,folder,record):
    attempts=[]
    while True:
        attempt_folder=folder/f'generation-{len(attempts)+1}'
        attempt_folder.mkdir()
        result=generate_original(source,preparation,handoff,attempt_folder)
        attempts.append(result);record['generation_attempts']=attempts
        record['generation']=result;save(folder/'result.json',record)
        if commit_audit_generated(result):return record
        # Main inspects exact upstream errors and decides whether substantive
        # progress supports revision. Never repair, reinterpret or score here.
        decision_path=folder/f'generation-{len(attempts)}-decision.json'
        last_progress=0
        while not decision_path.exists():
            if time.monotonic()-last_progress>30:
                print(json.dumps({'instanceId':record['instanceId'],'generation':'needs-main-decision',
                    'attempt':len(attempts),'decision_path':str(decision_path),'result':result}),flush=True)
                last_progress=time.monotonic()
            time.sleep(1)
        decision=json.loads(decision_path.read_text())
        if decision['action']=='finish':return record
        if decision['action']!='revise' or not isinstance(decision.get('handoff'),str):
            raise ValueError('Main generation decision requires finish or the complete revised handoff')
        report=Path(record['report'])
        (attempt_folder/'review-original.jsonl').write_bytes(report.read_bytes())
        binding=json.loads((folder/'binding.json').read_text())
        binding.update(runId=record['accepted']['runId'],handoff=decision['handoff'])
        # The upstream runtime requires an existing empty file for every task.
        # Preserve the failed report above, retaining the immutable Request path.
        report.write_text('')
        record.setdefault('revisions',[]).append({'runtime_result':record['runtime_result'],
            'measurement':record['measurement'],'decision':decision,'report_sha256':record['report_sha256']})
        record['review_phase_started_at']=time.time()
        record['accepted']=machine.call('followup_task',binding)
        save(folder/'result.json',record)
        record=observe_review(machine,record,folder)
        record['report_sha256']=hashlib.sha256(report.read_bytes()).hexdigest()
        if not record['complete']:return record


def arw_owned_health(measurement_host):
    """Frontend /health needs no lease: the loaded model and its startup-prompt hashes."""
    import urllib.request
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(measurement_host.deployment['frontend_url'].rstrip('/')+'/health',timeout=30) as reply:
        return json.load(reply)


def cold_start_arw_batch(measurement_host,folder):
    """ARW's provider reuses a resident model, so take the lease first, stop the model and return the lease."""
    with measurement_host.controller(folder) as controller:  # acquiring stops a resident model
        status=controller.call('/model/status')
        if status.get('status')!='stopped':
            raise RuntimeError('Resident model did not stop before the ARW-owned batch')
    health=arw_owned_health(measurement_host)
    if health.get('model') is not None:
        raise RuntimeError('Frontend still reports a loaded model after the cold-start stop')
    return {'model_status':status,'health':health}


def capture_segment(measurement_host,model,start,end,folder):
    """Engine log bytes [start,end) belong to one instance: ARW holds the lease for the whole batch."""
    content=measurement_host.log_bytes_since(model,start)[:end-start].decode(errors='replace')
    (folder/'engine-request-log.txt').write_text(content)
    requests=parse_engine_log(content)
    save(folder/'engine-rates.json',engine_rates(requests))
    started=re.findall(r'engine started: (.*)',content)
    return requests,sum_engine_tokens(requests),started[-1] if started else None


def start_arw_telemetry(measurement_host,folder):
    """Host resource and GPU thermal sampling for one instance, from its dispatch to its segment close."""
    from tools.metrics.host_telemetry import start
    folder.mkdir(parents=True,exist_ok=False)
    return start(measurement_host,folder),folder


def finish_arw_telemetry(measurement_host,telemetry):
    from tools.metrics.host_telemetry import finish
    binding,folder=telemetry
    return finish(measurement_host,binding,folder)


def close_arw_segment(record,measurement_host,model,end,telemetry=None):
    folder=Path(record['binding_path']).parent
    requests,tokens,started=capture_segment(measurement_host,model,record['engine_log_start_offset'],end,folder)
    record.update(engine_requests=requests,engine_tokens=tokens,engine_log_end_offset=end,engine_started=started)
    if telemetry:
        record['telemetry']=finish_arw_telemetry(measurement_host,telemetry)
        record['telemetry_folder']=str(telemetry[1])
    incomplete=not record.get('complete',False)
    record['token_consumption']=None if incomplete else tokens
    record['token_consumption_source']='engine log segment between this and the next dispatch; API usage is diagnostic only'
    if incomplete:
        save(folder/'internal-counter-coverage.json',{'complete_instance_token_counts':False,
            'reason':'Unfinished instance requires a Main audit of pending main/compaction/guardian requests.',
            'recorded_complete_stages':len(requests),'api_usage_used_as_consumption':False})
    save(folder/'result.json',record)


def load_resume_cleanup(path, recovering_native=False):
    """An absent cleanup record is uncertain, never evidence of safe closure."""
    path=Path(path)
    if not path.exists():
        if not recovering_native:
            raise ValueError('Original cleanup record is missing; verify native exit before recovery')
        return {'cleanup':{'status':'unknown'},'reason':'Original cleanup record is missing'}
    return json.loads(path.read_text())


def prepared_jobs(preparation_paths,schedule=None,profile=None):
    """Prepared instances in the Main-owned schedule order, or in preparation order."""
    preparations=[json.loads(p.read_text()) for p in preparation_paths]
    source=Path(preparations[0]['repositoryRoot'])
    if any(p['repositoryRoot']!=str(source) or p['identity']!=preparations[0]['identity'] for p in preparations):raise ValueError('Mixed upstream preparation identity')
    by_path={str(path.resolve()):prep for path,prep in zip(preparation_paths,preparations)}
    jobs=[]
    if schedule:
        seen=set()
        for item in schedule:
            preparation=by_path[str(Path(item['preparation']).resolve())]
            handoff=next(h for h in preparation['handoffs'] if h['instanceId']==item['instanceId'])
            if handoff['instanceId'] in seen:raise ValueError('Duplicate native instance in schedule')
            seen.add(handoff['instanceId']);jobs.append((preparation,handoff,item.get('profile')))
        if seen!={h['instanceId'] for p in preparations for h in p['handoffs']}:
            raise ValueError('Schedule must retain all original prepared instances')
    else:jobs=[(p,h,profile) for p in preparations for h in p['handoffs']]
    return preparations,source,jobs


def api_review_catalog(source,target,selection):
    """API provider catalog: the selected model's native entry. Guardian and search stay native unless the
    selection names a guardian model (D6) or a web_search mode (D5); there is no ARW Strata provider."""
    catalog=json.loads(Path(source).read_text())
    catalog.pop('providers',None)
    model=api_model(selection)
    selected=next((m for m in catalog['models'] if m['slug']==model),None)
    if selected is None:
        raise ValueError('Selected API model is absent from the measurement catalog')
    guardian=selection.get('guardian_model')
    if guardian is not None:
        if not isinstance(guardian,str) or not guardian:raise ValueError('Unsupported guardian model')
        selected['auto_review_model_override']=guardian
    save(target,catalog)
    return target


def run_api(out,selection,preparation_paths,catalog,schedule=None,limit=None):
    """Run prepared handoffs on an API provider through the same ARW runtime: no lease, no host, no engine log.

    Token consumption is the native API usage (Reviewer rounds plus guardian histories, tools.reviewer.arw_metrics),
    labeled as such; the provider key stays in this process environment and Codex reads it through env_key."""
    from tools.reviewer.native_cli_binding import selection_native_cli
    native_cli=selection_native_cli(selection.get('native_cli'))
    provider=validate_api_selection(selection)
    if not credential_present(provider):
        raise ValueError('Provider credential is not available: '+(provider['env_key'] or 'the benchmark ChatGPT login'))
    if os.environ.get('STRATA_API_KEY'):
        raise ValueError('A Strata key is present; API provider runs never hold a Strata lease')
    out.mkdir(parents=True,exist_ok=False)
    compaction_config({},out/'prompt-policy-preflight',include_project_base=selection.get('project_compaction_instructions',True))
    catalog=api_review_catalog(catalog,out/'native-model-catalog.json',selection)
    preparations,source,jobs=prepared_jobs(preparation_paths,schedule)
    jobs=spec_repetition_order(jobs)
    save(out/'schedule.json',[{'preparation':p['preparedPath'],'instanceId':h['instanceId'],'profile':None} for p,h,_ in jobs])
    if limit is not None:
        save(out/'deferred.json',[h['instanceId'] for _,h,_ in jobs[limit:]]);jobs=jobs[:limit]
    runtime=out/'runtime.json';native_install=out/'arw-installation';cleanup_path=out/'arw-cleanup.json'
    shim=out/'bin';shim.mkdir();entry=shim/'arw'
    entry.write_text('#!/bin/sh\nexec node '+shlex.quote(str(ROOT/'tools/reviewer/arw_runtime.mjs'))+' client "$@"\n');entry.chmod(0o755)
    save(runtime,{'repositoryRoot':str(source),'programDirectory':preparations[0].get('programDirectory',str(source)),
                  'installationDirectory':str(native_install),
                  **({'codexExecutable':native_cli['executable'],'nativeCliBinding':native_cli} if native_cli else {}),
                  'catalog':str(catalog),'cleanupPath':str(cleanup_path),
                  'denyRead':credential_deny_paths(provider)})
    os.environ['QWEN_ARW_RUNTIME_FILE']=str(runtime)
    # A fresh CODEX_HOME per run; a ChatGPT login enters it only as a link to the benchmark login (never opened).
    codex_home=native_install/'codex-home';login=link_login(provider,codex_home)
    relay=None
    if provider['relay']:
        from tools.reviewer.api_relay import Relay
        relay=Relay(provider['base_url'],out/'relay').__enter__();os.environ['QWEN_API_RELAY_BASE']=relay.url
    save(out/'provider-binding.json',{'provider':provider,'login_link':login,'relay':relay.url if relay else None})
    old_path=os.environ['PATH'];os.environ['PATH']=str(shim)+os.pathsep+old_path
    records=[];safe=True
    daemon_log=(out/'daemon-stderr.log').open('w');daemon_path=out/'daemon-stdout.jsonl';daemon_output=daemon_path.open('w')
    daemon=subprocess.Popen(['node',str(ROOT/'tools/reviewer/arw_runtime.mjs'),'daemon',str(runtime)],
        stdin=subprocess.PIPE,stdout=daemon_output,stderr=daemon_log,text=True,env=process_environment(provider))
    daemon_reader=daemon_path.open();machine=None
    try:
        value=read_daemon_message(daemon_reader,daemon)
        if not value.get('ready'):raise RuntimeError('Original ARW manager did not start')
        save(out/'arw-providers.json',value.get('providers',{}))
        machine=Machine(source,runtime,out)
        for preparation,handoff,_ in jobs:
            selection_native_cli(selection.get('native_cli'))
            folder=out/handoff['instanceId'];safe=False
            record=execute_review(machine,source,preparation,handoff,folder,selection,catalog,
                {'runtime_installation':str(native_install),'model_owner':'api'})
            if record.get('arw_pause'):
                raise RuntimeError('ARW paused the Reviewer task after repeated early exits; the user decides how to continue')
            if record['runtime_result'].get('state') in ('starting','running','working','unknown'):
                raise RuntimeError('Current native work is not terminal; preserve the ARW runtime for recovery')
            if record['complete']:
                if handoff['reviewerId']=='commit-audit-reviewer' and selection.get('generation_policy')!='first-delivery-only':
                    record=audit_generation(machine,source,preparation,handoff,folder,record)
                else:record['generation']=generate_original(source,preparation,handoff,folder)
            safe=True
            record['cost']=collect_cost(record,native_install/'codex-home')
            combined=record['cost']['combined_api_tokens']
            record['token_consumption']=combined if record.get('complete') and None not in combined.values() else None
            record['token_consumption_source']=('API usage reported by the provider: Reviewer rounds plus guardian '
                                               'histories; no engine log exists for an API provider')
            # D14: what the provider returned, not what was asked; unknown without the relay.
            record['service_tier_returned']=relay.summary(record['started_at'],time.time()) if relay else None
            save(folder/'result.json',record);records.append(record);save(out/'results.json',records)
    finally:
        if machine:machine.close()
        if safe:
            daemon.stdin.close()
            value=read_daemon_message(daemon_reader,daemon)
            if value:save(cleanup_path,value)
            if value and value.get('cleanup',{}).get('status')=='ready':daemon.wait(timeout=30)
            else:safe=False
        daemon_log.close();daemon_output.close();daemon_reader.close()
        os.environ['PATH']=old_path;os.environ.pop('QWEN_ARW_RUNTIME_FILE',None);os.environ.pop('QWEN_API_RELAY_BASE',None)
        if relay:relay.close()
        if safe:save(out/'login-release.json',{'status':release_login(provider,codex_home)})
        if not safe:
            save(out/'recovery-required.json',{'reason':'Reviewer completion or native cleanup is uncertain; preserve the ARW runtime.',
                'runtime':str(runtime),'model_owner':'api','daemon_pid':daemon.pid})
            print('Reviewer state requires recovery; the ARW runtime has been preserved.',flush=True)
    return records


def run(installation,out,selection,preparation_paths,catalog,profile=None,schedule=None,resume=False,resume_native_install=None,host=None,limit=None):
    from tools.reviewer.native_cli_binding import selection_native_cli
    native_cli = selection_native_cli(selection.get('native_cli'))
    if api_provider(selection) is not None:
        raise ValueError('An API provider selection runs through run_api, without a host or lease')
    if host is None:
        raise ValueError('Provide a registered host')
    from tools.ops.measurement_host import MeasurementHost
    # a tuning condition is deployed before the run; sources and model configuration are checked with it overlaid
    measurement_host=MeasurementHost(host,installation,selection.get('deployment_condition'))
    installation=measurement_host.installation
    if selection.get('host_id')!=host or selection.get('host_hardware')!=measurement_host.deployment.get('hardware'):
        raise ValueError('Selection is not frozen for this host; prepare a host-specific selection first')
    arw_owned=selection.get('model_owner')=='arw'
    if arw_owned and (selection.get('engine_overrides') or selection.get('engine_environment') or selection.get('sampling')
            or selection.get('automatic_continuation') or selection.get('startup_instructions') is False
            or selection.get('loop_prevention_instructions') or 'auto_compact_token_limit' in selection or profile or resume):
        raise ValueError('ARW-owned model runs choose only the model, effort and a published context tier; '
                         'engine, sampling and compaction settings are installation defaults, with ARW continuation and no resume')
    if not arw_owned:driver_context(selection)
    old_runtime=json.loads((out/'runtime.json').read_text()) if resume else {}
    cleanup_path=Path(old_runtime.get('cleanupPath',out/'arw-cleanup.json'))
    if resume:
        if not out.is_dir() or (out/'controller-key.private.json').exists():
            raise ValueError('Resume requires a closed previous batch with no retained ownership')
        cleanup=load_resume_cleanup(cleanup_path,recovering_native=resume_native_install is not None)
        if cleanup.get('cleanup',{}).get('status')!='ready' and resume_native_install is None:
            raise ValueError('Original host cleanup is not confirmed; recover it first')
    else:
        if resume_native_install is not None:raise ValueError('Native recovery requires resume.')
        out.mkdir(parents=True,exist_ok=False)
    compaction_config({},out/'prompt-policy-preflight',include_project_base=selection.get('project_compaction_instructions',True))
    catalog = local_review_catalog(catalog, out/'native-model-catalog.json', selection['model'],selection.get('context_window'),
                                   installation if arw_owned else None)
    preparations,source,jobs=prepared_jobs(preparation_paths,schedule,profile)
    if arw_owned:jobs=spec_repetition_order(jobs)
    save(out/'schedule.json',[{'preparation':p['preparedPath'],'instanceId':h['instanceId'],'profile':f} for p,h,f in jobs])
    if limit is not None:  # run the first instances now; the rest stay prepared for a later --resume
        save(out/'deferred.json',[h['instanceId'] for _,h,_ in jobs[limit:]]);jobs=jobs[:limit]
    records=json.loads((out/'results.json').read_text()) if resume else []
    completed={r['instanceId']:r for r in records}
    for _,handoff,current_profile in jobs:
        prior=completed.get(handoff['instanceId'])
        if prior is None:continue
        if prior.get('selection')!=selection or prior.get('profile')!=current_profile:
            raise ValueError('Prior instance fixed conditions differ from this schedule')
        if hashlib.sha256(Path(prior['report']).read_bytes()).hexdigest()!=prior['report_sha256']:
            raise ValueError('Prior report bytes changed; do not silently reuse it')
    if set(completed)-{h['instanceId'] for _,h,_ in jobs}:
        raise ValueError('Prior results contain an instance outside the original schedule')
    runtime=out/'runtime.json'
    native_install=Path(old_runtime.get('installationDirectory',out/'arw-installation'))
    recovery_proof=None
    if resume_native_install is not None:
        from tools.reviewer.arw_recovery import verify_stopped_runtime
        native_install=Path(resume_native_install).resolve()
        pending=[h['instanceId'] for _,h,_ in jobs if h['instanceId'] not in completed]
        recovery_proof=verify_stopped_runtime(out,source,native_install,records,pending)
        cleanup_path=out/(native_install.name+'-cleanup.json')
    shim=out/'bin';shim.mkdir(exist_ok=resume);entry=shim/'arw'
    entry.write_text('#!/bin/sh\nexec node '+shlex.quote(str(ROOT/'tools/reviewer/arw_runtime.mjs'))+' client "$@"\n');entry.chmod(0o755)
    if measurement_host:
        save(out/'host-source-preflight.json',measurement_host.verify_sources())
    expected_startup=None
    if arw_owned:
        source_raw=(ROOT/'config/prompts/startup-instructions.txt').read_bytes()
        if measurement_host.read_deployed_bytes('config/prompts/startup-instructions.txt')!=source_raw:
            raise RuntimeError('Installed startup prompt differs from the project source')
        expected_startup={'enabled':True,'sha256':hashlib.sha256(startup_prompt_bytes(source_raw,False)).hexdigest(),
                          'source_sha256':hashlib.sha256(source_raw).hexdigest(),'loop_prevention_enabled':False}
    if arw_owned:
        save(out/'cold-start.json',cold_start_arw_batch(measurement_host,out/'cold-start'))
    controller=None if arw_owned else measurement_host.controller(out).__enter__()
    open_segment=None;telemetry=None
    safe_to_release=True
    try:
        if recovery_proof:
            from tools.reviewer.arw_recovery import archive_recovery
            archive_recovery(out,recovery_proof)
        save(runtime,{'repositoryRoot':str(source),'programDirectory':preparations[0].get('programDirectory',str(source)),
                      'installationDirectory':str(native_install),
                      **({'codexExecutable':native_cli['executable'],'nativeCliBinding':native_cli} if native_cli else {}),
                      'catalog':str(catalog),'cleanupPath':str(cleanup_path),
                      # G7: Strata arms deny the same credential paths as the API arms.
                      'denyRead':credential_deny_paths(None)})
        # With ARW owning the model, its provider connection replaces this base URL and key.
        os.environ['STRATA_API_KEY']=controller.key if controller else 'arw-owned'
        os.environ['QWEN_ARW_MODEL_BASE']=(controller.model_base if controller
            else measurement_host.deployment['frontend_url'].rstrip('/')+'/strata')+'/v1'
        os.environ['QWEN_ARW_RUNTIME_FILE']=str(runtime)
        old_path=os.environ['PATH'];os.environ['PATH']=str(shim)+os.pathsep+old_path
        suffix=('-resume-'+str(time.time_ns())) if resume else ''
        daemon_log=(out/('daemon'+suffix+'-stderr.log')).open('w')
        daemon_path=out/('daemon'+suffix+'-stdout.jsonl')
        daemon_output=daemon_path.open('w')
        daemon=subprocess.Popen(['node',str(ROOT/'tools/reviewer/arw_runtime.mjs'),'daemon',str(runtime)],
            stdin=subprocess.PIPE,stdout=daemon_output,stderr=daemon_log,text=True,env=process_environment(None))
        daemon_reader=daemon_path.open()
        machine=None;http_archive=None
        try:
            value=read_daemon_message(daemon_reader,daemon)
            if not value.get('ready'):raise RuntimeError('Original ARW manager did not start')
            if arw_owned:
                # The manager must hold exactly the provider this run bound, read through ARW's own catalog.
                expected={**strata_provider(installation,selection.get('context_window')),'maxInstances':1}
                if value.get('providers',{}).get('qwen_strata')!=expected:
                    raise RuntimeError('ARW manager did not read the bound Strata provider')
                save(out/'arw-providers.json',value['providers'])
            machine=Machine(source,runtime,out)
            if selection.get('archive_http'):
                from tools.reviewer.review_continuations import HttpArchive
                http_archive=HttpArchive(native_install/'codex-home/logs_2.sqlite',out)
                http_archive.thread.start()
            last_repetition=None
            for preparation,handoff,current_profile in jobs:
                    selection_native_cli(selection.get('native_cli'))
                    if handoff['instanceId'] in completed:
                        print(json.dumps({'instanceId':handoff['instanceId'],'reuse':'exact prior report/settings/profile; no Reviewer rerun'}),flush=True)
                        continue
                    # Yield the GPU between instances, never inside one: a file in this directory stops the batch
                    # before the next repetition starts, and the batch closes normally.
                    repetition=handoff['instanceId'].rsplit('-instance-',1)[-1]
                    yield_dir=os.environ.get('ARW_MEASURE_YIELD_DIR')
                    if yield_dir and repetition!=last_repetition and any(Path(yield_dir).glob('*')):
                        print(json.dumps({'yield':'priority flag present','before':handoff['instanceId']}),flush=True)
                        break
                    last_repetition=repetition
                    if arw_owned:
                        offset=log_offset(installation,selection['model'],measurement_host)
                        if open_segment:
                            close_arw_segment(open_segment,measurement_host,selection['model'],offset,telemetry)
                            save(out/'results.json',records);open_segment=None;telemetry=None
                        safe_to_release=False
                        telemetry=start_arw_telemetry(measurement_host,out/'telemetry'/handoff['instanceId'])
                        record=execute_review(machine,source,preparation,handoff,out/handoff['instanceId'],selection,catalog,
                            {'runtime_installation':str(native_install),'engine_log_start_offset':offset,
                             'measurement_host':measurement_host.metadata(),'strata_release':measurement_host.installed_release(),
                             'model_owner':'arw'})
                        if record.get('arw_pause'):
                            raise RuntimeError('ARW paused the Reviewer task after repeated early exits; the user decides '
                                               'whether to continue it (send_message) or end it (interrupt_agent)')
                        if record['runtime_result'].get('state') in ('starting','running','working','unknown'):
                            raise RuntimeError('Current native work is not terminal; preserve the ARW runtime for recovery')
                        health=arw_owned_health(measurement_host)
                        record['frontend_health']=health
                        if (health.get('model')!='qwen3.8-flash-next-'+selection['model'].lower()
                                or health.get('startup_instructions')!=expected_startup):
                            raise RuntimeError('Loaded model or startup prompt differs from the approved selection')
                        if record['complete']:record['generation']=generate_original(source,preparation,handoff,out/handoff['instanceId'])
                        safe_to_release=True
                        record['cost']=collect_cost(record,native_install/'codex-home')
                        save(out/handoff['instanceId']/'result.json',record);records.append(record);open_segment=record
                        save(out/'results.json',records)
                        continue
                    options={'model':selection['model'],'engine_overrides':selection['engine_overrides'],
                        'request_defaults':dict(selection.get('sampling',{}),reasoning_effort=selection['effort']),
                        'engine_environment':selection.get('engine_environment',{})}
                    if 'startup_instructions' in selection:
                        options['startup_instructions']=selection['startup_instructions']
                    if 'loop_prevention_instructions' in selection:
                        options['loop_prevention_instructions']=selection['loop_prevention_instructions']
                    if current_profile:options['profile_file']=current_profile
                    profile_before=measurement_host.profile_sha256(selection['model']) if measurement_host and current_profile is None else None
                    status,load_s=controller.start(**options)
                    if status.get('native_health',{}).get('max_context')!=selection['context_window']:
                        raise RuntimeError('Loaded Strata capacity differs from the selected harness window')
                    startup=status.get('native_health',{}).get('startup_instructions')
                    if selection.get('startup_instructions',True) is False:
                        if not startup or startup.get('enabled') is not False:
                            raise RuntimeError('Diagnostic no-startup selection did not take effect')
                        save(out/'disabled-startup-receipt.json',startup)
                        raw=b''
                    elif startup:
                        source_raw=(ROOT/startup['path']).read_bytes()
                        installed_raw=(measurement_host.read_deployed_bytes(startup['path']) if measurement_host
                            else (installation/startup['path']).read_bytes())
                        if source_raw!=installed_raw:
                            raise RuntimeError('Installed startup prompt differs from the project source')
                        include_loop=selection.get('loop_prevention_instructions',False)
                        if (startup.get('enabled') is not True or startup.get('loop_prevention_enabled') is not include_loop
                                or startup.get('source_sha256')!=hashlib.sha256(source_raw).hexdigest()):
                            raise RuntimeError('Loop prevention selection did not take effect')
                        raw=startup_prompt_bytes(source_raw,include_loop)
                        if hashlib.sha256(raw).hexdigest()!=startup['sha256']:
                            raise RuntimeError('Loaded startup instructions differ from installed bytes')
                    offset=log_offset(installation,selection['model'],measurement_host)
                    folder=out/handoff['instanceId']
                    metadata={'start_status':status,'load_s':load_s,'profile':current_profile,
                              'runtime_installation':str(native_install),'engine_log_start_offset':offset}
                    if measurement_host:
                        metadata['measurement_host']=measurement_host.metadata()
                        metadata['strata_release']=measurement_host.installed_release()
                        metadata['default_profile_sha256_before']=profile_before
                    if startup:metadata['startup_instructions']=dict(startup,text=raw.decode('utf-8'))
                    safe_to_release=False
                    try:
                        record=execute_review(machine,source,preparation,handoff,folder,selection,catalog,metadata)
                        if record.get('continuation_dispatch_failure',{}).get('status')=='unconfirmed' or record['runtime_result'].get('state') in ('starting','running','working','unknown'):
                            save(folder/'result.json',record)
                            raise RuntimeError('Current native work is not terminal; preserve model and ownership for recovery')
                        safe_to_release=True
                        if record['complete']:
                            if handoff['reviewerId']=='commit-audit-reviewer' and selection.get('generation_policy')!='first-delivery-only':
                                safe_to_release=False
                                record=audit_generation(machine,source,preparation,handoff,folder,record)
                                safe_to_release=True
                            else:record['generation']=generate_original(source,preparation,handoff,folder)
                        record.update(start_status=status,load_s=load_s,profile=current_profile)
                        if startup:
                            record['startup_instructions']=dict(startup,text=raw.decode('utf-8'))
                    finally:
                        if safe_to_release:
                            try:
                                stopped,requests,engine_tokens=stop_and_capture_engine_log(
                                    controller,installation,selection['model'],offset,folder,measurement_host)
                            except Exception:
                                safe_to_release=False
                                raise
                    record['engine_requests']=requests;record['engine_tokens']=engine_tokens
                    record['engine_log_capture_after_confirmed_stop']=True
                    interrupted=any(d.get('interrupt',{}).get('status')=='accepted' for d in record.get('deadlines',[]) if d.get('interrupt'))
                    needs_counter_audit=interrupted or not record.get('complete',False)
                    record['token_consumption']=None if needs_counter_audit else engine_tokens
                    record['token_consumption_source']='completed native engine stages after confirmed stop; API usage is diagnostic only'
                    if needs_counter_audit:
                        save(folder/'internal-counter-coverage.json',{
                            'complete_instance_token_counts':False,
                            'reason':'Unfinished/interrupted instance requires a Main audit of pending main/compaction/guardian requests; completed counters alone do not prove complete scope.',
                            'recorded_complete_stages':len(requests),
                            'capture_after_confirmed_stop':True,
                            'main_counter_coverage_audit_pending':True,
                            'api_usage_used_as_consumption':False})
                    if measurement_host and profile_before:
                        profile_after=measurement_host.profile_sha256(selection['model'])
                        record['default_profile_sha256_after']=profile_after
                        record['default_profile_unchanged']=profile_before==profile_after
                    record['cost']=collect_cost(record,native_install/'codex-home')
                    record['stop']=stopped;save(folder/'result.json',record);records.append(record)
                    save(out/'results.json',records)
        finally:
            if machine:machine.close()
            if safe_to_release:
                safe_to_release=False
                daemon.stdin.close()
                value=read_daemon_message(daemon_reader,daemon)
                if value:
                    cleanup=value;save(cleanup_path,cleanup)
                    safe_to_release=cleanup.get('cleanup',{}).get('status')=='ready'
                if safe_to_release:daemon.wait(timeout=30)
            daemon_log.close();daemon_output.close();daemon_reader.close()
            if open_segment and safe_to_release:
                # ARW released its lease at closure; the last instance's segment ends at the log's end now.
                close_arw_segment(open_segment,measurement_host,selection['model'],
                                  log_offset(installation,selection['model'],measurement_host),telemetry)
                save(out/'results.json',records);telemetry=None
            if http_archive:http_archive.close()
            os.environ['PATH']=old_path
            for key in ('STRATA_API_KEY','QWEN_ARW_MODEL_BASE','QWEN_ARW_RUNTIME_FILE'):os.environ.pop(key,None)
    finally:
        if telemetry:  # an instance that never reached its segment close must not leave the sampler running
            try:save(telemetry[1]/'unclosed-segment.json',finish_arw_telemetry(measurement_host,telemetry))
            except Exception as error:print('Telemetry sampler stop failed: '+type(error).__name__,flush=True)
        if safe_to_release:
            if controller:controller.__exit__(None,None,None)
        else:
            save(out/'recovery-required.json',{'reason':'Reviewer completion or native cleanup is uncertain; preserve ownership and model.',
                'runtime':str(runtime),'credential_file':str(controller.credential) if controller else None,
                'model_owner':'arw' if arw_owned else 'driver',
                'daemon_pid':daemon.pid if 'daemon' in locals() else None})
            print('Reviewer state requires recovery; the private ownership file has been preserved.',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-root',type=Path)
    parser.add_argument('--host',help='Registered deployment host; use its frozen selection and independent preparation/output directory.')
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--selection',type=Path,required=True)
    parser.add_argument('--preparation',type=Path,action='append',required=True)
    parser.add_argument('--catalog',type=Path,required=True)
    parser.add_argument('--profile')
    parser.add_argument('--schedule',type=Path,help='Main-owned execution order and profile bindings; retain every original instance.')
    parser.add_argument('--resume',action='store_true',help='Continue a closed batch, verifying prior bytes and fixed conditions; never rerun recorded instances.')
    parser.add_argument('--limit',type=int,help='Run only the first N scheduled instances; the others are listed in deferred.json.')
    parser.add_argument('--resume-native-install',type=Path,help='After verified native exit, retain old busy state and use fresh isolated state for never-started instances.')
    args=parser.parse_args()
    selection=json.loads(args.selection.read_text())
    if api_provider(selection) is not None:
        if args.host or args.install_root or args.profile or args.resume or args.resume_native_install:
            parser.error('API provider runs take no host, installation, profile or resume')
        run_api(args.out.resolve(),selection,args.preparation,args.catalog.resolve(),
                json.loads(args.schedule.read_text()) if args.schedule else None,args.limit)
        sys.exit(0)
    run(args.install_root,args.out.resolve(),json.loads(args.selection.read_text()),args.preparation,args.catalog.resolve(),args.profile,
        json.loads(args.schedule.read_text()) if args.schedule else None,args.resume,args.resume_native_install,args.host,args.limit)
