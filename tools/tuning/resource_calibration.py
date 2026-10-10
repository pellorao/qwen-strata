"""Run an explicitly approved, frozen resource comparison through ownership APIs."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import urllib.error

from tools.reviewer.arw_measure import stop_and_capture_engine_log, log_offset
from tools.ops.measurement_host import MeasurementHost
from tools.metrics.prompt_policy import verify_loaded_startup
from tools.metrics.strata_tokens import engine_rates, task_rates
from tools.reviewer.wsl_client import ROOT, save


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def inspect_reply(response, expected):
    """Distinguish incomplete delivery from a complete but wrong answer."""
    choice=response['choices'][0];message=choice['message'];text=message.get('content') or ''
    strict_json=True
    try:value=json.loads(text)
    except (ValueError,TypeError):
        value=None;strict_json=False
        # Recognize an already delivered array inside framing text, without
        # converting a format failure into another attempt at a better answer.
        decoder=json.JSONDecoder()
        for match in re.finditer(r'[\[{]',text):
            try:candidate,_=decoder.raw_decode(text[match.start():])
            except ValueError:continue
            if isinstance(candidate,list) and len(candidate)>=len(expected):value=candidate;break
    refusal=bool(message.get('refusal'))
    complete=isinstance(value,list) and len(value)>=len(expected)
    # A complete wrapped array is a format failure, not permission to ask for a better answer.
    if isinstance(value,dict):complete=any(isinstance(v,list) and len(v)>=len(expected) for v in value.values())
    canonical=lambda v:json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False)
    return {'complete':complete,'pass':strict_json and complete and canonical(value)==canonical(expected),
            'refusal':refusal,'finish_reason':choice.get('finish_reason'),
            'output_rows':len(value) if isinstance(value,list) else None,'text':text}


def frozen_inputs(plan_path,workload_path):
    plan=json.loads(Path(plan_path).read_text());workload=json.loads(Path(workload_path).read_text())
    if not (plan.get('authorization') or {}).get('approved') and (plan.get('authorization') or {}).get('user_response')!='agree':
        raise ValueError('This exact resource work is not approved')
    if plan['authorization'].get('paused_by_user'):
        raise ValueError('This exact resource work is not approved and resumed')
    schedule=experiment_schedule(plan)
    if len(schedule)!=plan['model_instances'] or len(schedule)*3!=plan['logical_requests']:
        raise ValueError('Requested execution count differs from the approved work')
    for path,sha in plan['source_sha256'].items():
        if digest((ROOT/path).read_bytes())!=sha:raise ValueError('Frozen source changed: '+path)
    for case,binding in zip(workload['cases'],plan['workload']['case_bindings'],strict=True):
        text=case.get('user_text',workload.get('shared_prefix','')+case.get('question',''))
        if case['id']!=binding['id'] or digest(text.encode())!=binding['user_text_sha256']:
            raise ValueError('Frozen request changed')
        if digest(json.dumps(case['expected'],sort_keys=True,separators=(',',':')).encode())!=binding['expected_sha256']:
            raise ValueError('Frozen expected values changed')
    return plan,workload


def experiment_schedule(plan):
    """Admit only the concrete resource comparisons selected in this project."""
    if plan.get('host')!='rtx3080ti':raise ValueError('Unapproved resource host')
    dimension=plan['candidate_dimension']
    if plan.get('schema')=='conditions-v2':
        # Each condition names its own engine overrides (null drops a template flag) and environment.
        conditions={c['id']:c for c in plan['conditions']}
        if len(conditions)<2 or len(conditions)!=len(plan['conditions']):raise ValueError('Unapproved conditions')
        for c in conditions.values():
            if set(c)-{'id','overrides','environment'} or not c.get('overrides') and not c.get('environment'):
                raise ValueError('Condition must change an engine override or environment value')
        jobs=[{'label':f"{j['condition']}-r{j['repetition']}",'condition':j['condition'],'repetition':j['repetition'],
               'overrides':dict(conditions[j['condition']].get('overrides',{})),
               'environment':dict(conditions[j['condition']].get('environment',{}))}for j in plan['schedule']]
        expected={(c,r)for c in conditions for r in [1,2,3]}
        if len(jobs)!=len(expected) or {(j['condition'],j['repetition'])for j in jobs}!=expected:
            raise ValueError('Duplicate, missing or extra resource observation')
        return jobs
    if dimension=='pool-affinity':
        if plan['conditions']!=['auto','all'] or plan['pool_workers']!=23:
            raise ValueError('Unapproved affinity conditions')
        jobs=[{'label':label,'condition':'auto'if label.startswith('auto')else'all',
               'repetition':int(label[-1]),'overrides':{'pool-affinity':'auto'if label.startswith('auto')else'all'}}
              for label in plan['schedule']]
    elif dimension=='pool-workers':
        if plan['conditions']!=[23,15,12] or plan['fixed_pool_affinity']!='all':
            raise ValueError('Unapproved worker conditions')
        jobs=[{'label':f"workers{j['workers']}-r{j['repetition']}",
               'condition':j['workers'],'repetition':j['repetition'],
               'overrides':{'pool-affinity':'all','pool-workers':j['workers']}}
              for j in plan['schedule']]
    elif dimension=='ple-io':
        if plan['conditions']!=['direct','mmap'] or plan['fixed_pool_affinity']!='all' or plan['pool_workers']!=23:
            raise ValueError('Unapproved PLE conditions')
        jobs=[{'label':f"{j['mode']}-r{j['repetition']}",
               'condition':j['mode'],'repetition':j['repetition'],
               'overrides':{'pool-affinity':'all','pool-workers':23,'ple-io':j['mode']}}
              for j in plan['schedule']]
    elif dimension=='prefill':
        if plan['conditions']!=[8192,16384] or plan['fixed_pool_affinity']!='all' or plan['pool_workers']!=23:
            raise ValueError('Unapproved prefill conditions')
        jobs=[{'label':f"prefill{j['tokens']}-r{j['repetition']}",
               'condition':j['tokens'],'repetition':j['repetition'],
               'overrides':{'pool-affinity':'all','pool-workers':23,'prefill':j['tokens']}}
              for j in plan['schedule']]
    elif dimension=='STRATA_PREFILL_CPU_SHARE':
        conditions=plan['conditions']
        if [(c['id'],c['engine_environment_value'],c['repeats'])for c in conditions]!=[('off',0,3),('on','auto',3)]:
            raise ValueError('Unapproved CPU-prefill-share conditions')
        values={c['id']:c['engine_environment_value']for c in conditions}
        jobs=[{'label':f"cpu-{j['condition']}-r{j['repetition']}", 'condition':j['condition'],
               'repetition':j['repetition'],'overrides':{},
               'environment':{'STRATA_PREFILL_CPU_SHARE':values[j['condition']]}}for j in plan['schedule']]
    elif dimension=='vram-reserve-mib':
        if plan['conditions']!=[1024,768,512] or plan['fixed_pool_affinity']!='all' or plan['pool_workers']!=23:
            raise ValueError('Unapproved VRAM reserve conditions')
        jobs=[{'label':f"reserve{j['reserve']}-r{j['repetition']}",'condition':j['reserve'],'repetition':j['repetition'],
               'overrides':{'pool-affinity':'all','pool-workers':23,'vram-reserve-mib':j['reserve']}}
              for j in plan['schedule']]
    else:raise ValueError('Unapproved resource dimension')
    conditions=[c['id']for c in plan['conditions']]if dimension=='STRATA_PREFILL_CPU_SHARE'else plan['conditions']
    expected={(c,r)for c in conditions for r in [1,2,3]}
    if len(jobs)!=len(expected) or {(j['condition'],j['repetition'])for j in jobs}!=expected:
        raise ValueError('Duplicate, missing or extra resource observation')
    return jobs


def logical_request(owner,body,expected,folder,limit):
    folder.mkdir();started=time.monotonic();row={'started_at':time.time(),'calls':0,'pass':False,'complete':False}
    body=copy.deepcopy(body)
    while time.monotonic()-started<limit:
        remaining=limit-(time.monotonic()-started)
        row['calls']+=1;save(folder/f'request-{row["calls"]}.json',body)
        try:
            if body.get('stream'):
                from tools.metrics.streamed_chat import request
                reply,timing=request(owner,body,folder,row['calls'],remaining)
                row.setdefault('stream_timings',[]).append(timing)
            else:reply=owner.call('/strata/v1/chat/completions',body,timeout=remaining)
        except (TimeoutError,urllib.error.URLError) as error:
            if isinstance(error,TimeoutError) or isinstance(getattr(error,'reason',None),TimeoutError):
                row['timeout']=True;break
            raise
        save(folder/f'response-{row["calls"]}.json',reply)
        inspection=inspect_reply(reply,expected);save(folder/f'inspection-{row["calls"]}.json',{k:v for k,v in inspection.items()if k!='text'})
        row.update({k:v for k,v in inspection.items()if k!='text'})
        if inspection['complete'] or inspection['refusal']:break
        # Normal early completion without the assigned delivery: same source/history and remaining work budget.
        message=reply['choices'][0]['message']
        prior={'role':'assistant','content':inspection['text']}
        if message.get('reasoning_content'):prior['reasoning_content']=message['reasoning_content']
        body['messages'].extend([prior,{'role':'user','content':
            'Continue the same assigned task from the existing source and history. The complete requested JSON array has not been delivered. Return the complete array; do not restart the task or change the source.'}])
    row['ended_at']=time.time();row['work_seconds']=time.monotonic()-started
    if not row['complete'] and not row.get('refusal'):row['deadline_reached']=True
    save(folder/'result.json',row);return row


def run_case(host,plan,workload,job,folder):
    folder.mkdir();options=copy.deepcopy(plan['baseline']['start_options']);model=options.get('model','Q2_0')
    options['engine_overrides'].update(job['overrides']);label=job['label'];condition=job['condition']
    options.setdefault('engine_environment',{}).update(job.get('environment',{}))
    row={'label':label,'condition':condition,'repetition':job['repetition'],'started_at':time.time(),'requests':[],
         'driver_sha256':digest(Path(__file__).read_bytes()),'pass':False,'ownership_returned':False}
    save(folder/'start-options.json',options)
    owner=host.controller(folder/'controller');offset=None;stopped=None;telemetry=None
    try:
        with owner:
            if owner.call('/model/status')['status']!='stopped':raise RuntimeError('Model was not stopped')
            offset=log_offset(host.installation,model,host);save(folder/'engine-offset.json',{'offset':offset})
            try:
                status,row['load_seconds']=owner.start(**options);health=status['native_health'];startup=health['startup_instructions']
                save(folder/'start-status.json',{'status':status['status'],'max_context':health.get('max_context'),
                    'model_pid':status.get('model_pid'),'startup_instructions':startup})
                if health.get('max_context')!=156584:
                    raise RuntimeError('Actual capacity or startup policy differs')
                verify_loaded_startup(startup,plan['prompt_binding']['startup_sha256'])
                if job.get('environment'):
                    binding=host._remote('''import json,sys,os
from pathlib import Path
import psutil
expected=os.path.normcase(str(Path(sys.argv[1])/'runtime/Strata/engine/strata.exe'))
rows=[]
for p in psutil.process_iter(['pid','exe']):
 if os.path.normcase(p.info['exe'] or '')==expected:
  rows.append({'pid':p.pid,'cpu_prefill_share':p.environ().get('STRATA_PREFILL_CPU_SHARE')})
print(json.dumps(rows))
''',(str(host.windows_root),))
                    save(folder/'effective-engine-environment.json',binding)
                    expected=str(job['environment'].get('STRATA_PREFILL_CPU_SHARE'))
                    if len(binding)!=1 or binding[0]['cpu_prefill_share']!=expected:
                        raise RuntimeError('Effective CPU-share environment differs from selected condition')
                if plan.get('schema')=='conditions-v2':
                    started=re.findall(r'engine started: (.*)',host.log_bytes_since(model,offset).decode(errors='replace'))
                    args=started[-1].split() if started else []
                    effective={k:(args[args.index('--'+k)+1]if '--'+k in args else None)for k in options['engine_overrides']}
                    save(folder/'effective-engine-args.json',effective);row['effective_args']=effective
                    if not started or any(effective[k]!=(None if v is None else str(v))for k,v in options['engine_overrides'].items()):
                        raise RuntimeError('Effective engine arguments differ from selected condition')
                if 'vram-reserve-mib' in job['overrides']:
                    loaded=host.log_bytes_since(model,offset).decode(errors='replace')
                    cache=re.search(r'expert cache auto: ([\d.]+) GiB free, (\d+) MiB reserved.*?-> (\d+) slots',loaded)
                    after=re.search(r'(\d+) MiB of VRAM free with everything loaded',loaded)
                    effective={'free_gib_before_cache':float(cache[1])if cache else None,'reserve_mib':int(cache[2])if cache else None,
                               'cache_slots':int(cache[3])if cache else None,'free_mib_loaded':int(after[1])if after else None}
                    save(folder/'effective-vram.json',effective);row['effective_vram']=effective
                    if effective['reserve_mib']!=job['overrides']['vram-reserve-mib']:
                        raise RuntimeError('Effective VRAM reserve differs from selected condition')
                (folder/'startup-instructions.txt').write_bytes((ROOT/'config/prompts/startup-instructions.txt').read_bytes())
                from tools.metrics.prompt_policy import compaction_config
                compaction_config({},folder/'prompt-binding')
                if plan.get('telemetry',{}).get('interval_seconds')==1:
                    from tools.metrics.host_telemetry import start
                    telemetry=start(host,folder)
                for number,case in enumerate(workload['cases'],1):
                    body=copy.deepcopy(plan['baseline']['request_options']['chat'])
                    body['messages']=[{'role':'user','content':case.get('user_text',workload.get('shared_prefix','')+case.get('question',''))}]
                    if plan.get('stream_chat'):body['stream']=True
                    request_offset=log_offset(host.installation,model,host)
                    save(folder/f'request-{number}-engine-offset.json',{'offset':request_offset})
                    print(json.dumps({'instance':label,'request':case['id'],'event':'started'}),flush=True)
                    result=logical_request(owner,body,case['expected'],folder/f'request-{number}',plan['per_logical_request_work_seconds_limit'])
                    row['requests'].append(dict(result,id=case['id']));save(folder/'partial.json',row)
                    if plan.get('capture_each_request'):
                        from tools.reviewer.arw_measure import capture_engine_log
                        detail=folder/f'request-{number}';st,tk=capture_engine_log(host.installation,model,request_offset,detail,host)
                        save(detail/'engine-stages.json',st);save(detail/'engine-counts.json',tk)
                    print(json.dumps({'instance':label,'request':case['id'],'event':'closed','pass':result['pass'],
                                      'work_seconds':result['work_seconds'],'actual_calls':result['calls']}),flush=True)
                    if result.get('timeout') or result.get('deadline_reached'):
                        row['remaining_requests_not_executed']='Work deadline; stop/cancel before issuing more work';break
            finally:
                # Includes counters flushed by the stop/cancellation; never snapshot before stop.
                stopped,stages,tokens=stop_and_capture_engine_log(owner,host.installation,model,offset,folder,host)
                save(folder/'stop.json',stopped)
                work=sum(r['work_seconds']for r in row['requests']);row.update(tokens=tokens,internal_stages=len(stages),
                    review_work_seconds=work,frontend_requests=sum(r['calls']for r in row['requests']),
                    engine_log_sha256=digest((folder/'engine-request-log.txt').read_bytes()),
                    **engine_rates(stages),**task_rates(tokens,work))
                save(folder/'engine-stages.json',stages)
                if telemetry:
                    from tools.metrics.host_telemetry import finish
                    row['telemetry']=finish(host,telemetry,folder)
        row['ownership_returned']=True
        row['pass']=len(row['requests'])==3 and all(r['pass']for r in row['requests']) and row['tokens'] is not None
        row['status']='closed-valid-observation'
    except Exception as error:
        row['error_type']=type(error).__name__;row['status']='infrastructure-error-needs-impact-assessment'
        # Never print credential-bearing transport errors. Preserve the lease file on unconfirmed cleanup.
        row['ownership_returned']=not owner.credential.exists()
    row['ended_at']=time.time();save(folder/'result.json',row);return row


def run(plan_path,workload_path,out,resume=False):
    plan,workload=frozen_inputs(plan_path,workload_path);out=Path(out);out.mkdir(parents=True,exist_ok=resume)
    progress_path=out/'progress.json'
    progress=json.loads(progress_path.read_text())if resume else{'status':'running','started_at':time.time(),'rows':[],'attempts':[]}
    host=MeasurementHost(plan['host']);save(out/'source-verification.json',host.verify_sources())
    if host.profile_sha256(plan['baseline']['start_options'].get('model','Q2_0'))!=plan['default_profile_sha256_verified']:raise RuntimeError('Default profile changed')
    for job in experiment_schedule(plan):
        label=job['label']
        if any(r['label']==label and r['status']=='closed-valid-observation'for r in progress['rows']):continue
        attempts=sum(r['label']==label for r in progress['attempts'])+1;folder=out/f'{label}-attempt-{attempts}'
        progress['active_instance']=label;progress['status']='running';save(progress_path,progress)
        row=run_case(host,plan,workload,job,folder);row['attempt_directory']=folder.name
        progress['attempts'].append(row)
        if row['status']=='closed-valid-observation':progress['rows'].append(row)
        else:
            progress['status']='stopped-for-impact-assessment';save(progress_path,progress);return progress
        progress.pop('active_instance',None);save(progress_path,progress)
    progress.update(status='all-approved-observations-closed-awaiting-main-inspection',finished_at=time.time());save(progress_path,progress)
    return progress


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',type=Path,required=True);p.add_argument('--workload',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--resume',action='store_true');a=p.parse_args()
    result=run(a.plan,a.workload,a.out,a.resume);print(json.dumps({'status':result['status'],'closed_instances':len(result['rows'])}),flush=True)
