"""Extract visible execution observations; leave failure-recovery semantics for Main Agent."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from tools.ops import deployment_source
from tools.reviewer.wsl_client import save


def load_lines(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def bridge_requests(result):
    native=result.get('native',{})
    if 'bridge_requests' in native:return native['bridge_requests']
    # Earlier trials retain complete trace files even though their helper did not
    # return the index. Read those files; never rewrite their result.json.
    installation=Path(deployment_source.wsl_path(deployment_source.load_host(deployment_source.current_host())['installation_root']))
    digest=hashlib.sha256(str(Path(result['report']).parents[2]).encode()).hexdigest()[:12]
    folder=installation/('.tmp/wsl-profile-measurement-'+digest)/(result['label']+'-bridge-trace')
    if not folder.is_dir():return None
    rows=[]
    for path in folder.glob('*-input.json'):
        prefix=path.name[:-len('-input.json')]
        output=folder/(prefix+'-output.json');error=folder/(prefix+'-error.json')
        rows.append({'id':prefix,'started_at':path.stat().st_mtime,
            'completed_at':output.stat().st_mtime if output.exists() else None,
            'output_status':json.loads(output.read_text()).get('status') if output.exists() else None,
            'error':json.loads(error.read_text()) if error.exists() else None})
    return sorted(rows,key=lambda x:x['started_at'])


def observe(trial):
    result=json.loads((trial/'result.json').read_text())
    harness=trial/'fixed-scratch/harness'
    events=load_lines(harness/'events.jsonl')
    sessions=[]
    for path in (harness/'codex-home/sessions').rglob('*.jsonl'):
        records=load_lines(path)
        meta=next((r['payload'] for r in records if r['type']=='session_meta'),{})
        sessions.append((path,records,meta))
    parent=next((records for _,records,meta in sessions if meta.get('id')==result.get('thread_id')),[])
    calls={}
    failures=[]
    unknown_tool_outputs=[]
    outputs=0
    for pos,record in enumerate(parent):
        payload=record.get('payload',{})
        if record.get('type')!='response_item':continue
        kind=payload.get('type')
        if kind in ('function_call','custom_tool_call'):
            calls[payload['call_id']]={'name':payload.get('name'),'arguments':payload.get('arguments',payload.get('input'))}
        if kind not in ('function_call_output','custom_tool_call_output'):continue
        outputs+=1
        value=payload.get('output','')
        value=value if isinstance(value,str) else json.dumps(value)
        exit_match=re.search(r'(?:Process exited with code |Exit code: )(-?\d+)',value)
        denied=bool(re.search(r'(?im)^(?:approval policy is Never; reject command|[^\n]*(?:bash|cat|ls|touch|mkdir|rm|git)[^\n]*:.*(?:Permission denied|Read-only file system|Operation not permitted)|.*tool (?:call )?(?:rejected|denied)|.*rejected by user)',value))
        patch_error=kind=='custom_tool_call_output' and bool(re.match(r'(?is)\s*(?:error|failed|patch verification failed)',value))
        parser_error=bool(re.match(r'(?is)\s*(?:Error parsing|Invalid tool call|tool error|apply_patch verification failed|exec_command (?:rejected|failed))',value))
        failed=bool((exit_match and int(exit_match[1])!=0) or denied or patch_error or parser_error)
        known_success=bool(exit_match and int(exit_match[1])==0) or value.startswith('Success. Updated the following files:')
        running='Session ID:' in value or 'Process running with session ID' in value
        if not failed and not known_success and not running:
            unknown_tool_outputs.append({'timestamp':record['timestamp'],'call_id':payload.get('call_id'),
                'call':calls.get(payload.get('call_id')),'output':value})
        if failed:
            subsequent=[]
            for later in parent[pos+1:]:
                p=later.get('payload',{})
                if later.get('type')=='response_item' and p.get('type') in ('function_call','custom_tool_call'):
                    subsequent.append({'timestamp':later['timestamp'],'name':p.get('name'),
                        'arguments':p.get('arguments',p.get('input'))})
                    if len(subsequent)==3:break
            failures.append({'timestamp':record['timestamp'],'call_id':payload.get('call_id'),
                'call':calls.get(payload.get('call_id')),'exit_code':int(exit_match[1]) if exit_match else None,
                'permission_denial_candidate':denied,'output':value,'next_visible_calls':subsequent})
    api_errors=[e for e in events if e['event'].get('method')=='error']
    completed=[e['event']['params']['item'] for e in events if e['event'].get('method')=='item/completed']
    tool_items=[x for x in completed if x['type'] not in ('reasoning','userMessage','agentMessage')]
    approvals=[e['event']['params'] for e in events if e['event'].get('method')=='item/autoApprovalReview/completed']
    trace=bridge_requests(result)
    observed_bridge_failures=[r for r in (trace or []) if r.get('error') or r.get('output_status')=='failed']
    unknown=[r for r in (trace or []) if r.get('completed_at') is None and not r.get('error')]
    guardian_count=sum('guardian' in json.dumps(meta.get('source')) for _,_,meta in sessions)
    observation={'label':result['label'],'execution_mode':result.get('execution_mode','sandbox-deny'),
        'task_wall_s':result.get('measurement',{}).get('elapsed_s'),'load_wall_s':result.get('load_s'),
        'user_turn_count':sum(e['event'].get('method')=='turn/started' and e['event'].get('params',{}).get('threadId')==result.get('thread_id') for e in events),
        'api_request_count':len(trace) if trace is not None else None,
        'api_count_includes_guardian':bool(guardian_count),'guardian_session_count':guardian_count,
        'tool_call_count':len(calls),'tool_output_count':outputs,'completed_tool_item_count':len(tool_items),
        'tool_failure_candidates':failures,'api_error_events':api_errors,
        'unknown_tool_outputs':unknown_tool_outputs,
        'bridge_failure_records':observed_bridge_failures,'bridge_outcome_unknown':unknown,
        'api_failure_count':0 if trace is not None and not unknown and not observed_bridge_failures and not api_errors else None,
        'approval_count':len(approvals),'approval_wall_s':sum((a['completedAtMs']-a['startedAtMs'])/1000 for a in approvals),
        'approvals':approvals,'failure_adjudication_required':bool(failures or unknown_tool_outputs or api_errors or observed_bridge_failures or unknown),
        'visible_tool_items':tool_items,'bridge_requests':trace}
    save(trial/'observations.json',observation)
    return observation


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trial',type=Path)
    result=observe(parser.parse_args().trial.resolve())
    print(json.dumps({k:result[k] for k in ('label','api_request_count','tool_call_count','api_failure_count','approval_count','failure_adjudication_required')},indent=2))
