"""Replay frozen detector examples, without model calls or test-label inputs."""
import argparse
import hashlib
import json
from pathlib import Path
from tools.loop.progress_guard import initial_state, observe_commands
from tools.loop.reasoning_loop_guard import observe_model_text


def replay(case):
    state = initial_state(['corpus-replay'])
    positions = {}
    for block in case['blocks']:
        positions[block['item_id']] = block['event']
        common = {'threadId': case['thread_id'], 'turnId': block['turn_id'], 'itemId': block['item_id']}
        if block['kind'] == 'reasoning':
            observed = observe_model_text(state, [common | {'text': block['text'],
                'sourceOffset': block['start']}], case['thread_id'])
        else:
            observed = observe_commands(state, [common | {'command': block['command'],
                'cwd': block['cwd'], 'exitCode': block['exit_code'],
                'output': block['output'], 'outputDigest': block['output_sha256']}], case['thread_id'])
        for hint in observed:
            yield hint, positions.copy()


def evaluate(case):
    hints = []
    for hint, positions in replay(case):
        spans = hint.get('evidence_spans', [])
        matches = []
        if spans:
            for identity, start, end in spans:
                matches.append({i for i, marker in enumerate(case['evidence_marks'])
                                if positions.get(identity[1]) == marker['event']
                                and start < marker['end'] and end > marker['start']})
            independent = any(
                (left[0] != right[0] or left[2] <= right[1] or right[2] <= left[1])
                and any(a != b for a in matches[i] for b in matches[j])
                for i, left in enumerate(spans)
                for j, right in enumerate(spans) if j > i)
        else:
            ids = list({tuple(x) for x in hint.get('evidence_ids', [])})
            matches = [{i for i, marker in enumerate(case['evidence_marks'])
                        if positions.get(identity[1]) == marker['event']} for identity in ids]
            independent = any(a != b for i, left in enumerate(matches)
                              for right in matches[i + 1:] for a in left for b in right)
        if independent:
            matched = set().union(*matches)
            hints.append({'kind': hint['kind'], 'matched_iterations': sorted(matched),
                          'evidence_spans': spans})
    return {'case_id': case['case_id'], 'matched': bool(hints), 'qualified_hints': hints}


def validate_fixtures(corpus):
    """Check preserved excerpt bytes and identities independently of detection."""
    errors = []
    seen = set()
    for category in ('positive_cases', 'negative_cases'):
        for case in corpus.get(category, []):
            if case['case_id'] in seen:
                errors.append([case['case_id'], 'duplicate identity'])
            seen.add(case['case_id'])
            blocks = {b['event']: b for b in case['blocks']}
            for block in case['blocks']:
                for field in ('text', 'output'):
                    if field in block and isinstance(block[field], str):
                        expected = block.get(field + '_sha256')
                        if expected != hashlib.sha256(block[field].encode()).hexdigest():
                            errors.append([case['case_id'], block['event'], field + ' SHA'])
                if block['kind'] == 'reasoning' and block['end'] - block['start'] != len(block['text']):
                    errors.append([case['case_id'], block['event'], 'excerpt bounds'])
            for marker in case.get('evidence_marks', []):
                block = blocks[marker['event']]
                text = block.get('text', block.get('annotation_text', block.get('command')))
                start = marker['start'] - block.get('start', 0)
                end = marker['end'] - block.get('start', 0)
                if not isinstance(text, str) or not 0 <= start < end <= len(text):
                    errors.append([case['case_id'], marker['event'], 'marker bounds'])
                elif hashlib.sha256(text[start:end].encode()).hexdigest() != marker['text_sha256']:
                    errors.append([case['case_id'], marker['event'], 'marker SHA'])
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, default=Path('benchmarks/loop-detection-v2/cases.json'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--fixtures-only', action='store_true')
    args = parser.parse_args()
    corpus = json.loads(args.corpus.read_text())
    errors = validate_fixtures(corpus)
    rows = [] if args.fixtures_only else [evaluate(case) for case in corpus['positive_cases']]
    negatives = [] if args.fixtures_only else [
        {'case_id': case['case_id'], 'hint_count': sum(1 for _ in replay(case))}
        for case in corpus.get('negative_cases', [])]
    passed = not errors and all(r['matched'] for r in rows) and not any(r['hint_count'] for r in negatives)
    result = {'status': ('fixtures-valid' if not errors else 'fixture-invalid') if args.fixtures_only else (
                  'pass' if passed else 'coverage-or-specificity-incomplete'),
              'corpus_sha256': hashlib.sha256(args.corpus.read_bytes()).hexdigest(),
              'positive_cases': len(rows), 'matched': sum(r['matched'] for r in rows),
              'negative_cases': len(negatives), 'negative_cases_with_hints': sum(bool(r['hint_count']) for r in negatives),
              'fixture_errors': errors, 'model_runs': 0, 'model_requests': 0,
              'implementation_sha256': {name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
                  for name in ('progress_guard.py', 'reasoning_loop_guard.py', 'verify_loop_detection_corpus.py')},
              'observations': rows, 'negative_observations': negatives}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('observations', 'negative_observations')}))
    for row in rows:
        if not row['matched']:
            print('MISS', row['case_id'])
    return 0 if result['status'] in ('pass', 'fixtures-valid') else 1


if __name__ == '__main__':
    raise SystemExit(main())
