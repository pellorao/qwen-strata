"""Format normalization of a Commit Audit report on an independent copy.

Project scoring policy (user 2026-10-11): low-frequency, random representation
slips do not count against the score. Only the way evidence lines are written
is normalized; results, findings, evidence files and the lines pointed at stay
the same. The same rules apply to every instance regardless of its score, and
the original report is never changed.

  (a) a scalar `lines` value n becomes [n];
  (b) a report whose range-like entries are mostly (RANGE_SHARE) bare pairs
      of strictly increasing integers rather than nested [[a, b]] ranges wrote
      its ranges as pairs: each such [a, b] becomes [[a, b]]. Reports that
      mostly use nested ranges keep their pairs as two single lines.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

RANGE_SHARE = 0.8


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def is_pair(lines):
    return (isinstance(lines, list) and len(lines) == 2 and all(map(is_int, lines))
            and lines[0] < lines[1])


def evidence(rows):
    for row_index, row in enumerate(rows, 1):
        for evidence_index, item in enumerate(row.get('evidence') or []):
            if isinstance(item, dict) and 'lines' in item:
                yield row_index, evidence_index, item


def normalize(rows):
    """Return the normalized copy and the list of changes."""
    rows = copy.deepcopy(rows)
    changes = []
    for row, index, item in evidence(rows):
        if is_int(item['lines']):
            changes.append({'kind': 'scalar-lines', 'row': row, 'evidence': index,
                            'before': item['lines'], 'after': [item['lines']]})
            item['lines'] = [item['lines']]
    arrays = [item['lines'] for _, _, item in evidence(rows) if isinstance(item['lines'], list)]
    pairs = sum(map(is_pair, arrays))
    nested = sum(isinstance(element, list) for lines in arrays for element in lines)
    if pairs and pairs / (pairs + nested) >= RANGE_SHARE:
        for row, index, item in evidence(rows):
            if is_pair(item['lines']):
                changes.append({'kind': 'pair-as-range', 'row': row, 'evidence': index,
                                'before': item['lines'], 'after': [item['lines']]})
                item['lines'] = [item['lines']]
    return rows, changes


def summary(changes):
    counts = {}
    for change in changes:
        counts[change['kind']] = counts.get(change['kind'], 0) + 1
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--report', type=Path, required=True, help='Original bound review.jsonl')
    parser.add_argument('--out', type=Path, required=True, help='Normalized copy (a new file)')
    args = parser.parse_args()
    raw = args.report.read_bytes()
    rows = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
    normalized, changes = normalize(rows)
    record = {'original': str(args.report), 'original_sha256': hashlib.sha256(raw).hexdigest(),
              'changes': summary(changes), 'details': changes}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if changes:
        args.out.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in normalized), encoding='utf-8')
        record['normalized'] = str(args.out)
        record['normalized_sha256'] = hashlib.sha256(args.out.read_bytes()).hexdigest()
    assert hashlib.sha256(args.report.read_bytes()).hexdigest() == record['original_sha256']
    args.out.with_name(args.out.name + '.changes.json').write_text(json.dumps(record, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps({'changes': record['changes'], 'normalized': record.get('normalized')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
