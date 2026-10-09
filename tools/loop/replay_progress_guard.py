"""Replay closed native evidence; no model/SSH/tool calls or artifact rewriting."""
import argparse
import collections
import hashlib
import json
from pathlib import Path

from tools.loop.command_loop_guard import artifact_observation
from tools.loop.progress_guard import initial_state, observe_commands, observe_incomplete_end, observe_artifact


def _events(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def replay(folder):
    folder = Path(folder)
    record = json.loads((folder / 'result.json').read_text())
    binding = json.loads((folder / 'main-exact-delta-render/manifest.json').read_text())
    session = Path(binding['session_path'])
    raw = session.read_bytes()
    if hashlib.sha256(raw).hexdigest() != binding['session_sha256']:
        raise ValueError('Bound native session changed')
    events = _events(session)
    thread = record['runtime_result']['threadId']
    if events[0]['payload']['id'] != thread:
        raise ValueError('Native session identity differs')
    commands = {}
    for event in events:
        p = event.get('payload', {})
        if event.get('type') == 'response_item' and p.get('type') == 'function_call' and p.get('name') == 'exec_command':
            commands[p['call_id']] = json.loads(p['arguments'])['cmd']
    terminal_evidence = {}
    for path in (folder / 'automatic-continuations').glob('*/prior-terminal.json'):
        value = json.loads(path.read_text())
        if value['classification'] == 'premature-normal-end':
            terminal_evidence[value['runtime_result']['turnId']] = path.parent / 'report-before.jsonl'
    state = initial_state([record['instanceId'], 'offline'])
    observed = set()
    hints = []
    command_count = 0
    unknown_checkpoints = 0
    for index, event in enumerate(events):
        p = event.get('payload', {})
        if event.get('type') != 'event_msg':
            continue
        if p.get('type') == 'item_completed' and p.get('thread_id') == thread:
            item = p.get('item', {})
            if item.get('type') != 'CommandExecution' or item['id'] in observed or item['id'] not in commands:
                continue
            observed.add(item['id'])
            body = item.get('aggregated_output')
            fact = {'threadId': thread, 'turnId': p['turn_id'], 'itemId': item['id'], 'position': index,
                    'command': commands[item['id']], 'cwd': item.get('cwd', '').removeprefix('file://'),
                    'exitCode': item.get('exit_code'), 'output': body,
                    'outputDigest': hashlib.sha256(body.encode()).hexdigest() if isinstance(body, str) else None}
            command_count += 1
            for hint in observe_commands(state, [fact], thread):
                hints.append({'native_event': index, **hint})
        if p.get('type') == 'task_complete':
            checkpoint = terminal_evidence.get(p.get('turn_id'))
            if checkpoint is None:
                unknown_checkpoints += 1
                continue
            # The saved report is a real boundary observation. In-between
            # artifact states are not reconstructed from model claims or exit0.
            observation = artifact_observation(checkpoint)
            for hint in observe_incomplete_end(state, p['turn_id'], observation):
                hints.append({'native_event': index, **hint})
            observe_artifact(state, {'known': True, 'exists': True,
                'content_sha256': hashlib.sha256(b'[]').hexdigest()}, external_reset=True)
    labels_path = folder / 'main-loop-recount.json'
    labels = json.loads(labels_path.read_text()) if labels_path.exists() else None
    group_results = []
    if labels:
        for group in labels['groups']:
            labeled_ids = {events[e['native_event']]['payload'].get('call_id') for e in group['evidence']}
            matches = [h for h in hints if any(identity[1] in labeled_ids for identity in h['evidence_ids']
                                              if isinstance(identity, list))]
            group_results.append({'group': group['group'], 'type': group['type'], 'reason': group['reason'],
                                  'matched_hint_events': [h['native_event'] for h in matches]})
    return {'instance_id': record['instanceId'], 'thread_id': thread,
            'native_session_sha256': binding['session_sha256'], 'executed_commands_observed': command_count,
            'hints_by_kind': dict(collections.Counter(h['kind'] for h in hints)), 'hints': hints,
            'confirmed_group_matching': group_results, 'unknown_or_nonincomplete_checkpoints': unknown_checkpoints,
            'limitations': ['This does not measure model receipt or response to a hint.',
                'Artifact observations exist only at saved continuation checkpoints; intermediate writes are unknown.',
                'Reasoning-loop labels are not command events; do not infer semantic thinking-loop recall.',
                'Unmatched hints need manual review; unlabelled events are not automatically negative ground truth.'],
            'model_runs': 0, 'model_requests': 0}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--batch-directory', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    results = [replay(folder) for folder in sorted((a.batch_directory / 'run').glob('*instance-*'))]
    (a.out / 'replay.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps([{'instance': v['instance_id'], 'commands': v['executed_commands_observed'],
                      'hints': v['hints_by_kind']} for v in results]))


if __name__ == '__main__':
    main()
