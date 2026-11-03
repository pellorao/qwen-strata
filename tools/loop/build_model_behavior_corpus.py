"""Normalize native model behavior as compact offline fixtures, without context dumps.

Only explicit native-record inputs are read. No model, SSH, controller or other
external call is made. Labels annotate evidence; unreviewed data are not negatives.
"""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re


def sha(value):
    return hashlib.sha256(value).hexdigest()


_CREDENTIAL = re.compile(
    r'(?i)(\b(?:STRATA_API_KEY|OPENAI_API_KEY|BRAVE_API_KEY|ANTHROPIC_AUTH_TOKEN|api_key|password|'
    r'access_token|refresh_token|id_token|auth_token|secret_key)\b[\"\x27]?\s*[:=]\s*[\"\x27]?)([^\s\"\x27,}]+)|'
    r'(\bBearer\s+)([A-Za-z0-9._-]{12,})|'
    r'(\bAuthorization\b[\"\x27]?\s*[:=]\s*[\"\x27]?Basic\s+)([A-Za-z0-9+/=]{8,})|'
    r'(\b)(sk-[A-Za-z0-9_-]{16,})|'
    # A bare `token` is also ordinary prose and code ("token: `x`"): only a secret-like value (8+ token characters
    # with a digit) counts.
    r'(\btoken\b[\"\x27]?\s*[:=]\s*[\"\x27]?)((?=[A-Za-z0-9._~+/=-]*\d)[A-Za-z0-9._~+/=-]{8,})')


def scrub(text):
    """Return text and offset changes, never emit a matched credential value."""
    edits = []
    def replace(match):
        group = next(g for g in (2, 4, 6, 8, 10) if match[g])
        value = match[group]
        if value.startswith(('$', '<')):
            return match[0]
        edits.append({'start': match.start(group), 'end': match.end(group), 'replacement_length': 10})
        return match[group - 1] + '<redacted>'
    return _CREDENTIAL.sub(replace, text), edits


def safe_value(value):
    if isinstance(value, str):
        return scrub(value)[0]
    if isinstance(value, list):
        return [safe_value(x) for x in value]
    if isinstance(value, dict):
        return {k: ('<redacted>' if re.fullmatch(
            r'(?i)(password|(?:[A-Z_]*_)?api_?key|(?:(?:ANTHROPIC|access|refresh|id|auth)_)*token|secret_key|authorization)', k) else safe_value(v))
            for k, v in value.items()}
    return value


def model_text(event):
    p = event.get('payload', {})
    item = p.get('item', {})
    if event.get('type') == 'response_item':
        if p.get('type') == 'reasoning':
            return 'reasoning', '\n'.join(x.get('text', '') for x in p.get('summary', []))
        if p.get('type') == 'message' and p.get('role') in ('assistant', 'user'):
            return p['role'], '\n'.join(x.get('text', '') for x in p.get('content', []))
    if event.get('type') == 'event_msg' and p.get('type') == 'item_completed':
        if item.get('type') == 'Reasoning':
            return 'reasoning', '\n'.join(item.get('summary_text', []))
        if item.get('type') == 'AgentMessage':
            return 'assistant', '\n'.join(x.get('text', '') for x in item.get('content', []))
    return None, None


def normalize(path, expected):
    raw = path.read_bytes()
    if sha(raw) != expected['sha256']:
        raise ValueError('Native input changed after inventory')
    events = [json.loads(line) for line in raw.splitlines()]
    meta = events[0].get('payload', {})
    if events[0].get('type') != 'session_meta' or meta.get('id') != expected['thread_id']:
        raise ValueError('Native identity mismatch')
    thread = meta['id']
    completed = {}
    results = {}
    response_texts = []
    model_names = set()
    event_turns = {}
    scan_turn = None
    for n, event in enumerate(events):
        p = event.get('payload', {})
        if event.get('type') == 'turn_context' or (event.get('type') == 'event_msg' and p.get('type') == 'task_started'):
            scan_turn = p.get('turn_id', scan_turn)
        event_turns[n] = p.get('turn_id', p.get('internal_chat_message_metadata_passthrough', {}).get('turn_id', scan_turn))
        if event.get('type') == 'turn_context' and isinstance(p.get('model'), str):
            model_names.add(p['model'])
        kind, text = model_text(event)
        if kind and event.get('type') == 'response_item':
            response_texts.append((n, kind, text))
        if event.get('type') == 'response_item' and p.get('type') in (
                'function_call_output', 'custom_tool_call_output', 'tool_search_output'):
            output = p.get('tools') if p.get('type') == 'tool_search_output' else p.get('output')
            results[(event_turns[n], p.get('call_id'))] = (n, output)
        if (event.get('type') == 'event_msg' and p.get('type') == 'item_completed'
                and p.get('thread_id') == thread and p.get('item', {}).get('type') == 'CommandExecution'):
            completed[(event_turns[n], p['item']['id'])] = (n, p)
    mirror_map = {}
    claimed = set()
    # Match only nearby, one-to-one native mirrors. Equal text from two genuine
    # model items remains two observations, even when their digests are equal.
    for n, event in enumerate(events):
        if event.get('type') != 'event_msg':
            continue
        kind, text = model_text(event)
        if kind:
            candidates = [(abs(n - j), j) for j, k, t in response_texts
                          if j not in claimed and k == kind and t == text and abs(n - j) <= 4
                          and event_turns[n] == event_turns[j]]
            if candidates:
                j = min(candidates)[1]
                mirror_map[n] = j
                claimed.add(j)
    mirrors = defaultdict(list)
    for n, target in mirror_map.items():
        mirrors[target].append(n)
    facts = []
    task_inputs = []
    omitted = Counter()
    current_turn = None
    saw_model = False
    for n, event in enumerate(events):
        p = event.get('payload', {})
        native_type = event.get('type')
        kind, text = model_text(event)
        if native_type == 'turn_context':
            current_turn = p.get('turn_id', current_turn)
        if native_type == 'event_msg' and p.get('type') == 'task_started':
            current_turn = p.get('turn_id', current_turn)
        turn = p.get('turn_id', p.get('internal_chat_message_metadata_passthrough', {}).get('turn_id', current_turn))
        if n in mirror_map:
            omitted['native_text_mirror'] += 1
            continue
        item_id = p.get('id', p.get('item', {}).get('id', p.get('call_id', str(n))))
        common = {'trace_id': thread, 'turn_id': turn, 'item_id': item_id,
                  'source_events': [n] + mirrors[n], 'timestamp': event.get('timestamp')}
        if kind:
            original_text = text
            if kind == 'user':
                if text.lstrip().startswith(('# AGENTS.md instructions', '<permissions instructions>', '<skills_instructions>')):
                    omitted['initial_handoff_or_context_message'] += 1
                    continue
                text = re.sub(r'<environment_context>.*?</environment_context>', '', text, flags=re.S).strip()
                if not text:
                    omitted['context_only_message'] += 1
                    continue
                if not saw_model:
                    # The original task is relevant to whether a repeated action
                    # was requested. Retain it once, apart from model behavior;
                    # per-turn environment/policy snapshots still do not survive.
                    clean, edits = scrub(text)
                    task_inputs.append({'source_event': n, 'source_text_sha256': sha(original_text.encode())})
                    facts.append(common | {'kind': 'task', 'text': clean, 'source_text_sha256': sha(original_text.encode()),
                                           'text_sha256': sha(clean.encode()), 'redactions': edits})
                    continue
                kind = 'feedback'
            else:
                saw_model = True
            clean, edits = scrub(text)
            facts.append(common | {'kind': kind, 'text': clean, 'source_text_sha256': sha(original_text.encode()),
                'text_sha256': sha(clean.encode()), 'redactions': edits})
            continue
        if native_type == 'response_item' and p.get('type') in (
                'function_call', 'custom_tool_call', 'tool_search_call'):
            saw_model = True
            call_id = p.get('call_id')
            call_key = (event_turns[n], call_id)
            args = p.get('input') if p.get('type') == 'custom_tool_call' else p.get('arguments')
            if isinstance(args, str) and p.get('type') != 'custom_tool_call':
                try:
                    args = json.loads(args)
                except ValueError:
                    pass
            row = common | {'kind': 'tool', 'item_id': call_id,
                            'name': p.get('name', p.get('type')), 'arguments': safe_value(args),
                            'source_arguments_sha256': sha(json.dumps(args, ensure_ascii=False, sort_keys=True).encode())}
            output = None
            if call_key in completed:
                j, done = completed[call_key]
                detail = done['item']
                row['source_events'].append(j)
                row['exit_code'] = detail.get('exit_code')
                row['cwd_sha256'] = sha(str(detail.get('cwd', meta.get('cwd'))).encode())
                output = detail.get('aggregated_output')
                if isinstance(args, dict) and isinstance(args.get('cmd'), str):
                    row['source_command_sha256'] = sha(args['cmd'].encode())
            if call_key in results:
                j, reply = results[call_key]
                row['source_events'].append(j)
                if output is None:
                    output = reply
                row['result_present'] = True
            else:
                row['result_present'] = False
            if isinstance(output, str):
                row['output'], row['output_redactions'] = scrub(output)
                row['source_output_sha256'] = sha(output.encode())
                row['output_sha256'] = sha(row['output'].encode())
            elif output is not None:
                row['output'] = safe_value(output)
            facts.append(row)
            continue
        if native_type == 'event_msg' and p.get('type') in (
                'task_started', 'task_complete', 'turn_aborted', 'context_compacted', 'error'):
            boundary = p['type']
            facts.append(common | {'kind': 'boundary', 'event': boundary,
                                  'timestamp': event.get('timestamp')})
            continue
        if native_type == 'compacted':
            # Summaries/compaction are a separate phase, not ordinary current
            # task reasoning or proof of a new repeated operation.
            facts.append(common | {'kind': 'boundary', 'event': 'compacted',
                                  'timestamp': event.get('timestamp')})
            continue
        omitted[native_type + ':' + str(p.get('type'))] += 1
    return {'trace_id': thread, 'native_sha256': expected['sha256'], 'native_event_count': len(events),
            'model_provider': meta.get('model_provider'), 'cli_version': meta.get('cli_version'),
            'model_catalog_names': sorted(model_names), 'behavior_fact_count': len(facts),
            'initial_task_inputs': task_inputs,
            'omitted_categories': dict(omitted)}, facts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-inventory', type=Path, required=True)
    parser.add_argument('--labels', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    inventory = json.loads(args.source_inventory.read_text())
    labels = json.loads(args.labels.read_text())
    by_thread = defaultdict(list)
    for case in labels['positive_cases']:
        by_thread[case['thread_id']].append(case)
    normal_by_thread = defaultdict(list)
    for case in labels.get('negative_cases', []):
        normal_by_thread[case['thread_id']].append(case)
    traces = []
    boundaries = []
    args.out.mkdir(parents=True, exist_ok=True)
    data_path = args.out / 'behavior.jsonl.gz'
    plain_bytes = 0
    with data_path.open('wb') as raw_stream, gzip.GzipFile(filename='', fileobj=raw_stream, mode='wb', mtime=0) as stream:
        for source in inventory['selected_unique_threads']:
            trace, facts = normalize(Path(source['path']), source)
            trace['source_batch'] = Path(source['path']).parts[1]
            trace['collection_scope'] = 'all-surviving-qwen-strata-native-records'
            trace['anti_loop_comparison_trace'] = bool(by_thread[trace['trace_id']]) or any(
                r['thread_id'] == trace['trace_id'] for r in labels['runs'])
            trace['annotation_status'] = 'partly-reviewed' if trace['anti_loop_comparison_trace'] else 'unreviewed'
            trace['execution_origin'] = 'simulation' if 'mock' in source['path'].lower() else 'unclassified'
            event_map = {n: f for f in facts for n in f['source_events']}
            annotations = defaultdict(list)
            normal_annotations = defaultdict(list)
            for case in by_thread[trace['trace_id']]:
                for mark in case['evidence_marks']:
                    fact = event_map.get(mark['event'])
                    if fact is None:
                        boundaries.append({'case_id': case['case_id'], 'event': mark['event'], 'reason': 'native event not mapped'})
                        continue
                    annotations[id(fact)].append({'case_id': case['case_id'], 'source_event': mark['event'],
                        'source_start': mark['start'], 'source_end': mark['end'],
                        'source_text_sha256': mark['text_sha256'], 'kind': case['historical_type']})
            for case in normal_by_thread[trace['trace_id']]:
                for block in case['blocks']:
                    fact = event_map.get(block['event'])
                    if fact is None:
                        boundaries.append({'case_id': case['case_id'], 'event': block['event'], 'reason': 'normal evidence not mapped'})
                        continue
                    normal_annotations[id(fact)].append({'case_id': case['case_id'], 'source_event': block['event'],
                        'source_start': block.get('start', 0), 'source_end': block.get('end'),
                        'expectation': case['expectation']})
            for fact in facts:
                fact['loop_annotations'] = annotations[id(fact)]
                fact['normal_annotations'] = normal_annotations[id(fact)]
                whole_normal = any(a['source_start'] == 0 and a['source_end'] == len(fact.get('text', ''))
                                   for a in fact['normal_annotations']) and not fact.get('redactions')
                fact['label'] = ('not-model-output' if fact['kind'] in ('boundary', 'feedback', 'task') else
                                 'contains-annotated-loop' if fact['loop_annotations'] else
                                 'normal' if whole_normal else
                                 'contains-normal-region' if fact['normal_annotations'] else 'pending-review')
                line = (json.dumps(fact, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
                plain_bytes += len(line)
                stream.write(line)
            traces.append(trace)
    metadata = {'schema_version': 1, 'status': 'cleaned-whole-behavior-corpus-awaits-complete-annotation',
        'traces': traces, 'source_native_bytes': sum(s['size'] for s in inventory['selected_unique_threads']),
        'cleaned_uncompressed_bytes': plain_bytes, 'compressed_bytes': data_path.stat().st_size,
        'behavior_sha256': sha(data_path.read_bytes()), 'label_source_sha256': sha(args.labels.read_bytes()),
        'fact_count': sum(t['behavior_fact_count'] for t in traces), 'unmapped_known_loop_evidence': boundaries,
        'normalizer_sha256': sha(Path(__file__).read_bytes()),
        'model_runs': 0, 'model_requests': 0,
        'annotation_rule': 'After full review, all model behavior is labelled loop or normal; missing/unreviewed evidence is pending, never an implicit negative.',
        'retention': 'Model behavior, tool observations, feedback and one initial task binding retained; per-turn context, environment/system/skills snapshots and native mirrors omitted.'}
    (args.out / 'behavior-manifest.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in metadata.items() if k not in ('traces', 'unmapped_known_loop_evidence')}))
    print('unmapped_known_loop_evidence', len(boundaries))


if __name__ == '__main__':
    main()
