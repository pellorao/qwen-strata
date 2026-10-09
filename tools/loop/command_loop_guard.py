"""Upstream duplicate-command hints through the original ARW message channel."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[2]
_NATIVE_READERS = {}


def artifact_observation(path):
    """Observable artifact state only; whitespace changes are not new judgments."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return {'known': True, 'exists': False, 'content_sha256': None}
    except OSError:
        return {'known': False}
    try:
        rows = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
        canonical = json.dumps(rows, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    except (ValueError, UnicodeError):
        canonical = raw
    return {'known': True, 'exists': True,
            'content_sha256': hashlib.sha256(canonical).hexdigest(), 'bytes': len(raw)}


def _progress_state(record, folder):
    from tools.loop.progress_guard import initial_state
    directory = Path(folder) / 'progress-guard'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'state.json'
    scope = [record['instanceId'], record.get('review_phase_started_at', record.get('started_at'))]
    state = json.loads(path.read_text()) if path.exists() else initial_state(scope)
    if state['scope'] != scope:
        state = initial_state(scope)
    return directory, path, state


def _save_progress(path, state):
    temporary = path.with_suffix('.json.stage')
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def _record_progress_event(directory, record, result, hint, receipt=None, error=None):
    row = {'at': time.time(), 'thread_id': result.get('threadId'), 'turn_id': result.get('turnId'),
           'run_id': record['accepted']['runId'], **hint,
           'native_receipt': receipt, 'model_receipt_verified': False}
    if error:
        row['delivery_error_type'] = type(error).__name__
    with (directory / 'events.jsonl').open('a') as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + '\n')


def _observe_progress(machine, record, result, folder):
    from tools.loop.native_command_evidence import NativeCommandEvidence
    from tools.loop.progress_guard import observe_artifact, observe_commands
    directory, path, state = _progress_state(record, folder)
    for name, expected in (record['selection']['command_loop_guard'].get('implementation_sha256') or {}).items():
        if name not in ('progress_guard.py', 'native_command_evidence.py', 'command_loop_guard.py'):
            raise ValueError('Unknown bound progress guard component')
        if hashlib.sha256((ROOT / 'tools' / name).read_bytes()).hexdigest() != expected:
            raise ValueError('Frozen progress guard implementation changed')
    observe_artifact(state, artifact_observation(record['report']))
    facts = (result.get('snapshot') or {}).get('commandFacts', [])
    recovery_path = record.get('accepted', {}).get('recoveryPath')
    if recovery_path and Path(recovery_path).exists():
        recovery = json.loads(Path(recovery_path).read_text())
        if (recovery.get('threadId') == result['threadId'] and recovery.get('sessionPath')
                and Path(recovery['sessionPath']).is_file()):
            key = (recovery['sessionPath'], result['threadId'])
            reader = _NATIVE_READERS.setdefault(key, NativeCommandEvidence(*key))
            facts = reader.enrich(facts)
    hints = observe_commands(state, facts, result['threadId'])
    _save_progress(path, state)
    for hint in hints:
        receipt = None
        error = None
        try:
            receipt = machine.call('send_message', {'runId': record['accepted']['runId'],
                'turnId': result['turnId'], 'message': hint['instruction']})
        except Exception as failure:
            error = failure
        _record_progress_event(directory, record, result, hint, receipt, error)


def progress_continuation_feedback(record, result, folder):
    """Called only for a normal incomplete end, by the original continuation owner."""
    from tools.loop.progress_guard import ALGORITHM, observe_incomplete_end
    policy = record.get('selection', {}).get('command_loop_guard') or {}
    if not policy.get('enabled') or policy.get('algorithm') != ALGORITHM:
        return ''
    directory, path, state = _progress_state(record, folder)
    hints = observe_incomplete_end(state, result['turnId'], artifact_observation(record['report']))
    _save_progress(path, state)
    for hint in hints:
        _record_progress_event(directory, record, result, hint)
    return '\n\n'.join(h['instruction'] for h in hints)


def progress_external_report_reset(record, folder):
    from tools.loop.progress_guard import ALGORITHM, observe_artifact
    policy = record.get('selection', {}).get('command_loop_guard') or {}
    if policy.get('enabled') and policy.get('algorithm') == ALGORITHM:
        _, path, state = _progress_state(record, folder)
        observe_artifact(state, artifact_observation(record['report']), external_reset=True)
        _save_progress(path, state)


def observe_command_loops(machine,record,result,folder):
    policy=record.get('selection',{}).get('command_loop_guard')
    if not policy or not policy.get('enabled'):return
    from tools.loop.progress_guard import ALGORITHM
    if policy.get('algorithm') not in ('frozen-arw-strata-command-policy', ALGORITHM):
        raise ValueError('Unsupported loop detector')
    snapshot=result.get('snapshot') or {}
    root=next((m for m in snapshot.get('members',[])if m['threadId']==result.get('threadId')),None)
    if not root or root['state']!='active' or not result.get('turnId'):return
    if policy['algorithm'] == ALGORITHM:
        _observe_progress(machine, record, result, folder)
        return
    source=Path(machine.source)/'lib/background-agent/strata-work-policy.mjs'
    if hashlib.sha256(source.read_bytes()).hexdigest()!=policy['source_sha256']:
        raise ValueError('Approved duplicate-command policy changed')
    directory=Path(folder)/'command-loop-guard';directory.mkdir(parents=True,exist_ok=True)
    state_file=directory/'state.json';state=json.loads(state_file.read_text())if state_file.exists()else None
    request={'repositoryRoot':str(machine.source),'threadId':result['threadId'],'facts':snapshot.get('commandFacts',[]),'state':state}
    reply=subprocess.run(['node',str(ROOT/'tools/loop/arw_command_loop_guard.mjs')],input=json.dumps(request),capture_output=True,text=True,check=True)
    observed=json.loads(reply.stdout);state_file.write_text(json.dumps(observed['state'],indent=2)+'\n')
    for hint in observed['hints']:
        event={'at':time.time(),'thread_id':result['threadId'],'turn_id':result['turnId'],'run_id':record['accepted']['runId'],'instruction':hint['instruction'],'native_receipt':None,'model_receipt_verified':False}
        try:
            receipt=machine.call('send_message',{'runId':record['accepted']['runId'],'turnId':result['turnId'],'message':hint['instruction']})
            event['native_receipt']=receipt
            if receipt.get('deliveryStatus')=='accepted'and receipt.get('messageId'):
                observed['state']['repeatMessageId']=receipt['messageId'];state_file.write_text(json.dumps(observed['state'],indent=2)+'\n')
        except Exception as error:
            # An unknown hint delivery must not replay a command or kill a task.
            event['delivery_error_type']=type(error).__name__
        with(directory/'events.jsonl').open('a')as stream:stream.write(json.dumps(event,ensure_ascii=False)+'\n')
