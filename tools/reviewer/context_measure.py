"""Run exactly one approved, same-thread pair using the frozen ARW runtime.

Main inspects the first delivery and generation before authorizing stage two in
stage-1-main-decision.json. This never creates additional reviewer revisions.
The caller must hold explicit approval for the instance or entire batch.
Approval is batch-specific; zero compactions is also valid.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import time

from tools.reviewer.arw_measure import (Machine, stop_and_capture_engine_log, execute_review,
    generate_original, local_review_catalog, log_offset, read_daemon_message)
from tools.reviewer.arw_metrics import collect_cost
from tools.ops.controller_client import Controller
from tools.reviewer.wsl_client import ROOT, save
from tools.metrics.prompt_policy import compaction_config, verify_loaded_startup
from tools.metrics.context_capacity import (validate_context_pair, COMPACTION_OVERRUN_BUDGET,
    MAX_OUTPUT_BUDGET, CONTEXT_SLACK)
from tools.ops.measurement_host import MeasurementHost


def context_start_options(baseline, window, threshold):
    """Keep the frozen effort budgets while deriving the agreed capacity."""
    validate_context_pair(threshold, window)
    options=json.loads(json.dumps(baseline['start_options']))
    defaults=options['request_defaults']
    effort=defaults['reasoning_effort']
    budgets={'medium':(4096,16384),'high':(8192,24576)}
    if effort not in budgets or (defaults['reasoning_budget_tokens'],defaults['max_tokens'])!=budgets[effort]:
        raise ValueError('Spec Readiness effort and frozen budgets disagree')
    if baseline.get('harness',{}).get('model_reasoning_effort',effort)!=effort:
        raise ValueError('Harness effort differs from generation defaults')
    if options.get('startup_instructions',True) is not True or options.get('loop_prevention_instructions',True) is not True:
        raise ValueError('This comparison requires complete project startup instructions')
    options.update(startup_instructions=True,loop_prevention_instructions=True,fit_max_tokens=False)
    options['engine_overrides']['max-context']=window
    return options


def startup_binding(baseline):
    """Current project prompt is the source; an older explicit binding must agree."""
    raw=(ROOT/'config/prompts/startup-instructions.txt').read_bytes()
    if not raw.strip():raise ValueError('Project startup instructions are empty')
    expected={'installation_relative_path':'config/prompts/startup-instructions.txt',
              'sha256':hashlib.sha256(raw).hexdigest()}
    if baseline.get('startup_instructions',expected)!=expected:
        raise ValueError('Explicit startup binding differs from the current project source')
    return expected


def paired_handoffs(preparation, repetition):
    pair=[h for h in preparation['handoffs'] if h['instanceId'].endswith(f'-instance-{repetition}')]
    by_scene={h['scenarioId']:h for h in pair}
    if len(pair)!=2 or set(by_scene)!={'runtime-migration','artifact-promotion'}:
        raise ValueError('Requires one complete, frozen Spec Readiness repetition')
    return [by_scene['runtime-migration'],by_scene['artifact-promotion']]


def run(installation, out, baseline_path, preparation_path, catalog_path, window, threshold, repetition, new_thread=False):
    validate_context_pair(threshold, window)
    out.mkdir(parents=True,exist_ok=False)
    baseline=json.loads(baseline_path.read_text())
    prep=json.loads(preparation_path.read_text());source=Path(prep['repositoryRoot'])
    jobs=paired_handoffs(prep,repetition)
    options=context_start_options(baseline,window,threshold)
    startup_bound=startup_binding(baseline)
    measurement_host=MeasurementHost('local',installation)
    source_verification=measurement_host.verify_sources()
    selection={'model':options['model'],'effort':options['request_defaults']['reasoning_effort'],
        'engine_overrides':options['engine_overrides'],'engine_environment':options['engine_environment'],
        'sampling':options['request_defaults'],'context_window':window,'auto_compact_token_limit':threshold,
        'host_id':'local','host_hardware':measurement_host.deployment.get('hardware'),
        'startup_instructions':True,'loop_prevention_instructions':True,
        'server_options':{'fit_max_tokens':False},
        'context_capacity_policy':{'formula':'threshold + overrun + max_output + slack',
            'compaction_overrun_budget':COMPACTION_OVERRUN_BUDGET,
            'max_output_budget':MAX_OUTPUT_BUDGET,'slack':CONTEXT_SLACK}}
    compaction_config({},out/'prompt-policy')
    selection['compaction_prompt_policy']=json.loads((out/'prompt-policy/compact-prompt-policy.json').read_text())
    save(out/'selection.json',selection);save(out/'start-options.json',options)
    save(out/'source-verification.json',source_verification)
    (out/'startup-instructions.txt').write_bytes((ROOT/'config/prompts/startup-instructions.txt').read_bytes())
    save(out/'startup-prompt-policy.json',{'source':'config/prompts/startup-instructions.txt',
        'sha256':startup_bound['sha256'],'startup_instructions':True,'loop_prevention_instructions':True})
    catalog=local_review_catalog(catalog_path,out/'native-model-catalog.json',selection['model'],window)
    runtime=out/'runtime.json';native_install=out/'arw-installation';cleanup_path=out/'arw-cleanup.json'
    runtime_info={'repositoryRoot':str(source),'programDirectory':prep.get('programDirectory',str(source)),
        'installationDirectory':str(native_install),
        'catalog':str(catalog),'cleanupPath':str(cleanup_path)}
    save(runtime,runtime_info)
    shim=out/'bin';shim.mkdir();entry=shim/'arw'
    entry.write_text('#!/bin/sh\nexec node '+shlex.quote(str(ROOT/'tools/reviewer/arw_runtime.mjs'))+' client "$@"\n')
    entry.chmod(0o755)
    controller=Controller(installation,out).__enter__()
    safe=True;records=[];daemon=None;machine=None;stopped=None
    previous_env={k:os.environ.get(k) for k in ('PATH','STRATA_API_KEY','QWEN_ARW_MODEL_BASE','QWEN_ARW_RUNTIME_FILE')}
    try:
        if controller.call('/ownership/status')['status']!='stopped':
            raise RuntimeError('Fresh merged instance requires a stopped model')
        for name,bound in (('profile',baseline['profile']),('startup_instructions',startup_bound)):
            path=installation/bound['installation_relative_path']
            if hashlib.sha256(path.read_bytes()).hexdigest()!=bound['sha256']:
                raise RuntimeError('Frozen baseline changed: '+name)
        os.environ.update(STRATA_API_KEY=controller.key,QWEN_ARW_MODEL_BASE=controller.base+'/v1',
            QWEN_ARW_RUNTIME_FILE=str(runtime),PATH=str(shim)+os.pathsep+os.environ['PATH'])
        daemon_path=out/'daemon-stdout.jsonl'
        with (out/'daemon-stderr.log').open('w') as err,daemon_path.open('w') as output:
            daemon=subprocess.Popen(['node',str(ROOT/'tools/reviewer/arw_runtime.mjs'),'daemon',str(runtime)],
                stdin=subprocess.PIPE,stdout=output,stderr=err,text=True)
            with daemon_path.open() as reader:
                try:
                    if not read_daemon_message(reader,daemon).get('ready'):
                        raise RuntimeError('Original ARW manager did not start')
                    machine=Machine(source,runtime,out)
                    offset=log_offset(installation,selection['model'],measurement_host)
                    save(out/'engine-offset.json',{'offset':offset})
                    status,load_s=controller.start(**options)
                    if status.get('native_health',{}).get('max_context')!=window:
                        raise RuntimeError('Actual Strata capacity differs from approved window')
                    startup=status.get('native_health',{}).get('startup_instructions')
                    verify_loaded_startup(startup,startup_bound['sha256'])
                    save(out/'start-status.json',{'status':status,'load_s':load_s})
                    prior=None
                    for index,handoff in enumerate(jobs,1):
                        # Never replace the loaded model between the two tasks.
                        live=controller.call('/ownership/status')
                        if live.get('model_pid')!=status.get('model_pid'):
                            raise RuntimeError('Model process changed during merged instance')
                        folder=out/f'stage-{index}'
                        safe=False
                        record=execute_review(machine,source,prep,handoff,folder,selection,catalog,
                            {'start_status':status,'load_s':load_s,'runtime_installation':str(native_install)},previous=prior,
                            new_thread=new_thread and index==1)
                        safe=True
                        original=Path(record['report']).read_bytes()
                        (folder/'original-review.jsonl').write_bytes(original)
                        record['generation']=generate_original(source,prep,handoff,folder)
                        save(folder/'result.json',record);records.append(record);save(out/'results.json',records)
                        if index==1:
                            decision_path=out/'stage-1-main-decision.json'
                            print(json.dumps({'stage':1,'status':'awaiting-main-inspection',
                                'decision_path':str(decision_path),'complete':record['complete'],
                                'generation_exit_code':record['generation'].get('exit_code')}),flush=True)
                            while not decision_path.exists():time.sleep(1)
                            decision=json.loads(decision_path.read_text())
                            save(out/'stage-1-main-decision-consumed.json',decision)
                            if decision['action']=='finish':break
                            if decision['action']!='continue':raise ValueError('Invalid Main decision')
                            if hashlib.sha256(Path(record['report']).read_bytes()).hexdigest()!=record['report_sha256']:
                                raise RuntimeError('First bound report changed before continuation')
                            prior=json.loads(json.dumps(record))
                            if not prior['complete']:
                                # Only Main may recognize a status-only mechanical
                                # defect; retain native incomplete and all evidence.
                                if decision.get('mechanical_final_status_ready') is not True:
                                    raise ValueError('Incomplete first task lacks a mechanical Main recovery')
                                prior['complete']=True
                        elif hashlib.sha256(Path(records[0]['report']).read_bytes()).hexdigest()!=records[0]['report_sha256']:
                            raise RuntimeError('Second task altered the frozen first report')
                    stopped,requests,tokens=stop_and_capture_engine_log(
                        controller,installation,selection['model'],offset,out,measurement_host)
                    save(out/'stop.json',stopped)
                    save(out/'engine-tokens.json',{'stages':requests,'token_consumption':tokens,
                        'source':'Raw read/reused/generated stages over this exclusive fresh model lifetime'})
                    if records:
                        combined=json.loads(json.dumps(records[-1]))
                        combined['revisions']=[{'measurement':r['measurement']} for r in records[:-1]]
                        save(out/'metrics-audit.json',collect_cost(combined,native_install/'codex-home'))
                finally:
                    if machine:machine.close()
                    if safe:
                        if stopped is None:controller.stop()
                        safe=False
                        daemon.stdin.close()
                        cleanup=read_daemon_message(reader,daemon)
                        save(cleanup_path,cleanup)
                        safe=cleanup.get('cleanup',{}).get('status')=='ready'
                        if safe:daemon.wait(timeout=30)
    finally:
        for k,v in previous_env.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v
        if safe:controller.__exit__(None,None,None)
        else:save(out/'recovery-required.json',{'reason':'Completion or cleanup uncertain; preserve lease and runtime',
            'credential_file':str(controller.credential),'daemon_pid':daemon.pid if daemon else None})
    save(out/'run-finished.json',{'records':len(records),'ownership_returned':safe,
        'status':'awaiting-main-scoring-and-user-audit','next_instance_started':False})
    print(json.dumps({'status':'awaiting-main-scoring-and-user-audit','records':len(records),'ownership_returned':safe}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('installation','out','baseline','preparation','catalog'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--window',type=int,required=True)
    parser.add_argument('--threshold',type=int,required=True)
    parser.add_argument('--repetition',type=int,default=1)
    parser.add_argument('--new-thread',action='store_true',help='Explicitly approved replacement attempt after archiving the previous report and recovery record.')
    args=parser.parse_args()
    run(args.installation,args.out.resolve(),args.baseline,args.preparation,args.catalog,args.window,args.threshold,args.repetition,args.new_thread)
