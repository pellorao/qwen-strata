"""Validate Main's repetition-label overlay against the immutable cleaned corpus."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def validate(directory: Path) -> dict:
    annotation_path = directory / 'main-annotations.json'
    annotation = json.loads(annotation_path.read_text(encoding='utf-8'))
    manifest = json.loads((directory / 'behavior-manifest.json').read_text(encoding='utf-8'))
    blob = (directory / 'behavior.jsonl.gz').read_bytes()
    facts = [json.loads(line) for line in gzip.decompress(blob).splitlines()]
    sources = {row['trace_id']: row for row in manifest['traces']}
    lookup = {(row['trace_id'], tuple(row['source_events']), row['kind']): row for row in facts}
    issues = []
    if digest(blob) != annotation['behavior_sha256'] or digest(blob) != manifest['behavior_sha256']:
        issues.append('behavior-digest-mismatch')
    rows = annotation['normal_traces'] + annotation.get('mixed_traces', [])
    trace_counts = Counter(row['trace_id'] for row in rows)
    if set(trace_counts) != set(sources) or any(n != 1 for n in trace_counts.values()):
        issues.append('trace-partition-mismatch')
    labels = {}
    for row in rows:
        trace = row['trace_id']
        if row['native_sha256'] != sources[trace]['native_sha256']:
            issues.append(f'native-digest:{trace}')
        for label in row['fact_labels']:
            key = (trace, tuple(label['source_events']), label['kind'])
            if key in labels:
                issues.append(f'duplicate-label:{key}')
            labels[key] = label
            fact = lookup.get(key)
            if fact is None:
                issues.append(f'unknown-fact:{key}')
                continue
            expected = fact.get('text_sha256', fact.get('source_arguments_sha256'))
            if label['evidence_sha256'] != expected:
                issues.append(f'content-digest:{key}')
            if label.get('output_sha256') is not None and label['output_sha256'] != fact.get('output_sha256'):
                issues.append(f'output-digest:{key}')
            if label['label'] not in ('normal', 'mixed', 'loop'):
                issues.append(f'pending-or-invalid-label:{key}')
    expected_keys = {key for key in lookup if key[2] in ('reasoning', 'assistant', 'tool')}
    if set(labels) != expected_keys:
        issues.append(f'fact-coverage:missing={len(expected_keys-set(labels))},extra={len(set(labels)-expected_keys)}')

    groups = annotation['loops']
    group_ids = Counter(g['case_id'] for g in groups)
    if any(n != 1 for n in group_ids.values()):
        issues.append('duplicate-loop-id')
    seed_ids = {g['case_id'] for g in json.loads((directory / 'cases.json').read_text(encoding='utf-8'))['positive_cases']}
    if not seed_ids <= set(group_ids):
        issues.append('missing-historical-loop-id')
    for key, label in labels.items():
        if set(label.get('loop_case_ids', [])) - set(group_ids):
            issues.append(f'unknown-loop-label:{key}')
    for group in groups:
        trace = group['trace_id']
        if group['source_native_sha256'] != sources[trace]['native_sha256']:
            issues.append(f'loop-native-digest:{group["case_id"]}')
        for mark in group['evidence_marks']:
            matching = [f for f in facts if f['trace_id']==trace and mark['event'] in f['source_events'] and f['kind'] in ('reasoning','assistant','tool')]
            valid = False
            for fact in matching:
                values = [fact.get('text'), fact.get('output')]
                arguments = fact.get('arguments')
                if isinstance(arguments, dict):
                    values.extend(v for v in arguments.values() if isinstance(v, str))
                elif isinstance(arguments, str):
                    values.append(arguments)
                for value in values:
                    if isinstance(value, str) and 0 <= mark['start'] < mark['end'] <= len(value):
                        if digest(value[mark['start']:mark['end']].encode()) == mark['text_sha256']:
                            valid = True
            if not valid:
                issues.append(f'loop-span:{group["case_id"]}:{mark["event"]}:{mark["start"]}')
            linked = [label for key,label in labels.items() if key[0]==trace and mark['event'] in key[1] and group['case_id'] in label.get('loop_case_ids',[])]
            if not linked:
                issues.append(f'unlinked-loop:{group["case_id"]}:{mark["event"]}')
        count = group['iterations_including_first']
        if count < 2 or group['extra_repeats'] != count-1:
            issues.append(f'loop-count:{group["case_id"]}')
    complete = not issues and not annotation['remaining_trace_ids'] and len(labels)==len(expected_keys)
    return dict(schema_version=1,status='full-annotations-integrity-pass' if complete else 'fail',
        behavior_sha256=digest(blob),annotation_sha256=digest(annotation_path.read_bytes()),
        traces_total=len(sources),traces_complete=len(trace_counts),traces_pending=len(annotation['remaining_trace_ids']),
        complete_fact_labels=dict(Counter(r['label'] for r in labels.values())),complete_model_tool_facts=len(labels),
        non_model_facts=len(facts)-len(expected_keys),confirmed_groups=len(groups),
        new_bounded_groups=annotation['progress_counts']['new_confirmed_bounded_groups'],
        historical_groups_retained=len(seed_ids),
        loop_modes=dict(Counter(g['mode'] for g in groups)),
        confirmed_iterations_including_first_lower_bound=sum(g['iterations_including_first'] for g in groups),
        confirmed_extra_repeats_lower_bound=sum(g['extra_repeats'] for g in groups),
        issues=issues,annotation_complete=complete,detector_acceptance=False,f1=None,model_runs=0,model_requests=0,
        scope='Full Main repetition-label overlay integrity only; historical count lower bounds and causal replay adapter limitations remain explicit. Not a detector score or safety/task-quality acceptance.')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, default=Path('benchmarks/loop-detection-v2'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = validate(args.corpus)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    raise SystemExit(0 if result['annotation_complete'] else 1)


if __name__ == '__main__':
    main()
