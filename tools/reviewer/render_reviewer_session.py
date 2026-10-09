"""Render a complete closed native session for Main's manual inspection.

This records reading material and exact duplicate bindings, never a verdict.
No model/controller requests or modification of the original session.
"""
from pathlib import Path
import hashlib
import json
import sys

import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--batch-directory', required=True)
parser.add_argument('--name')
parser.add_argument('--record', type=Path, help='Closed single record from the current shared batch layout.')
parser.add_argument('--codex-home', type=Path)
parser.add_argument('--prepared', type=Path)
parser.add_argument('--allow-loaded-between-stages',action='store_true',help='Read a closed logical stage while the same merged instance retains its loaded model.')
parser.add_argument('--out', required=True)
args = parser.parse_args()
BASE = Path(args.batch_directory).resolve()
name = args.name
if args.record:
    assert args.codex_home and args.prepared
    record=json.loads(args.record.read_text())
    assert record.get('finished_at')
    if args.allow_loaded_between_stages:
        assert record['runtime_result']['taskState']=='ended', 'Logical stage is still active'
        assert record['runtime_result']['snapshot']['factsComplete'], 'Native closure facts unavailable'
    else:
        assert record.get('stop',{}).get('status')=='stopped'
    folder=args.record.parent
    job={'instanceId':record['instanceId'],'prepared_path':str(args.prepared),
         'native_prepared_sha256':hashlib.sha256(args.prepared.read_bytes()).hexdigest()}
else:
    assert name, '--name or --record is required'
    jobs = json.loads((BASE / 'jobs.json').read_text())
    job = next(j for j in jobs if Path(j['folder']).name == name)
    folder = Path(job['folder'])
    assert (folder / 'run-finished.json').exists(), 'Only render closed initial reviews'
    records = json.loads((folder / 'results.json').read_text())
    assert len(records) == 1
    record = dict(records[0])
continued = BASE/'premature-continuations'/(name or record['instanceId'])
if continued.exists():
    assert (continued/'run-finished.json').exists(), 'Continuation is not closed'
    final = json.loads((continued/'result.json').read_text())
    assert final['ownership_returned']
    record['report'] = final['final_report_path']
    record['report_sha256'] = final['final_report_sha256']
assert hashlib.sha256(Path(record['report']).read_bytes()).hexdigest() == record['report_sha256']
thread = record['runtime_result']['threadId']
home=args.codex_home if args.record else folder / 'arw-installation/codex-home'
sessions = list((home / 'sessions').rglob('*' + thread + '.jsonl'))
assert len(sessions) == 1
session = sessions[0]
raw = session.read_bytes()
events = [json.loads(line) for line in raw.splitlines()]
assert events[0]['type'] == 'session_meta' and events[0]['payload']['id'] == thread
calls = {}
outputs = {}
for i, event in enumerate(events):
    p = event.get('payload', {})
    if event['type'] == 'response_item' and p.get('type') in ('function_call', 'custom_tool_call'):
        assert p['call_id'] not in calls
        calls[p['call_id']] = i
    if event['type'] == 'response_item' and p.get('type') in ('function_call_output', 'custom_tool_call_output'):
        assert p['call_id'] not in outputs
        outputs[p['call_id']] = i
for call_id, output_index in outputs.items():
    assert call_id in calls and calls[call_id] < output_index

out = Path(args.out).resolve()
assert out.is_relative_to(BASE), 'Inspection details must stay under the temporary batch directory'
if out.exists():
    previous = json.loads((out / 'manifest.json').read_text())
    assert previous['manual_review_complete'] is False
    assert previous['session_sha256'] == hashlib.sha256(raw).hexdigest()
    for generated in out.iterdir():
        assert generated.name in ('manifest.json', 'index.json', 'usage-events.json') or generated.name.startswith('page-')
        generated.unlink()
else:
    out.mkdir(parents=True)
pages = []
page = ''
index = []
duplicates = []
for i, event in enumerate(events):
    p = event.get('payload', {})
    duplicate = None
    if event['type'] == 'event_msg' and p.get('type') == 'item_completed':
        item = p.get('item', {})
        if item.get('type') == 'Reasoning' and not item.get('raw_content'):
            observed = item.get('summary_text')
            for j in sorted(range(max(0, i - 8), min(len(events), i + 8)), key=lambda j: abs(j - i)):
                q = events[j].get('payload', {})
                if events[j]['type'] == 'response_item' and q.get('type') == 'reasoning':
                    canonical = [v.get('text') for v in q.get('summary', [])]
                    if observed == canonical:
                        duplicate = {'canonical_event': j, 'kind': 'exact-reasoning-summary'}
                        break
        if item.get('type') == 'CommandExecution':
            command = item.get('command', [])
            formatted = item.get('formatted_output')
            candidate_index = outputs.get(item.get('id'))
            for j in [] if candidate_index is None else [candidate_index]:
                q = events[j].get('payload', {})
                if events[j]['type'] != 'response_item' or q.get('type') != 'function_call_output':
                    continue
                call_index = calls[q['call_id']]
                call = events[call_index]['payload']
                try:
                    arguments = json.loads(call['arguments'])
                except (ValueError, KeyError):
                    continue
                output = q.get('output', '')
                # Extra untruncated aggregate output is distinct evidence.
                if 'Output:\n' in output and command and command[-1] == arguments.get('cmd'):
                    canonical_output = output.split('Output:\n', 1)[1]
                    if formatted == canonical_output and item.get('aggregated_output', '') in ('', formatted):
                        duplicate = {'canonical_event': j, 'call_event': call_index,
                                     'kind': 'exact-command-and-formatted-output'}
                    break
    if duplicate is not None:
        duplicates.append({'event': i, **duplicate})
        body = json.dumps({'exact_duplicate': duplicate}, ensure_ascii=False)
    elif event['type'] == 'event_msg' and p.get('type') in ('token_count', 'token_usage_record'):
        # Keep complete numeric diagnostic events in an independent JSON file.
        body = 'Numeric usage diagnostic: complete payload retained in usage-events.json.'
    else:
        body = json.dumps(p, ensure_ascii=False, indent=2)
    block = f"EVENT {i} ordinal={event.get('ordinal')} {event.get('timestamp')} {event['type']}\n{body}\n\n"
    if page and len(page) + len(block) > 15000:
        pages.append(page)
        page = ''
    # Keep very large tool/startup blocks intact; read with line pagination.
    page += block
    index.append({'event': i, 'type': event['type'], 'payload_type': p.get('type'),
                  'page': len(pages) + 1, 'duplicate': duplicate})
if page:
    pages.append(page)
for n, content in enumerate(pages, 1):
    (out / f'page-{n:03}.txt').write_text(content)
(out / 'usage-events.json').write_text(json.dumps([
    {'event': i, 'record': e} for i, e in enumerate(events)
    if e['type'] == 'event_msg' and e.get('payload', {}).get('type') in ('token_count', 'token_usage_record')
], indent=2) + '\n')
(out / 'index.json').write_text(json.dumps(index, indent=2) + '\n')
manifest = {
    'status': 'rendered-awaiting-full-main-inspection',
    'instanceId': job['instanceId'], 'threadId': thread,
    'session_path': str(session), 'session_sha256': hashlib.sha256(raw).hexdigest(),
    'event_count': len(events), 'page_count': len(pages),
    'tool_call_count': len(calls), 'tool_result_count': len(outputs),
    'unresolved_calls': [c for c in calls if c not in outputs],
    'exact_duplicates': duplicates,
    'report_path': record['report'], 'report_sha256': record['report_sha256'],
    'prepared_path': job['prepared_path'], 'prepared_sha256': job['native_prepared_sha256'],
    'manual_review_complete': False,
}
(out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({k: manifest[k] for k in ('status', 'event_count', 'page_count', 'tool_call_count', 'tool_result_count', 'unresolved_calls')}))
