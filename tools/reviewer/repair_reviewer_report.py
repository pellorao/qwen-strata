"""Format normalization of a Reviewer report on an independent copy.

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

Markdown reports (every markdown report scenario, such as Code Spec and
Code Standards; user 2026-10-12): everything before the first
finding (a line starting with `1. ` style numbering or `- `) is a preamble
such as a title or scope note and is removed. Findings and their evidence
locators stay as written; locator errors still count.
"""
import argparse
import copy
import hashlib
import json
import re
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


def without_lines(rows):
    rows = copy.deepcopy(rows)
    for _, _, item in evidence(rows):
        del item['lines']
    return rows


def check_only_lines_changed(original, normalized, changes):
    """Round trip: apart from `lines`, the copy equals the original field by
    field, and every changed `lines` is exactly the recorded before -> [before]."""
    assert without_lines(normalized) == without_lines(original), 'normalization changed more than lines'
    changed = {(c['row'], c['evidence']): c for c in changes}
    for (row, index, before), (_, _, after) in zip(evidence(original), evidence(normalized)):
        change = changed.get((row, index))
        if change is None:
            assert after['lines'] == before['lines'], f'unrecorded lines change at row {row}'
        else:
            assert before['lines'] == change['before'] and after['lines'] == [before['lines']], \
                f'lines change at row {row} is not before -> [before]'


def normalize(rows):
    """Return the normalized copy and the list of changes."""
    original = rows
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
    check_only_lines_changed(original, rows, changes)
    return rows, changes


FINDING_START = re.compile(r'(?:[1-9][0-9]*\. |- )')


def check_only_preamble_removed(original, normalized, changes):
    """Round trip: the copy is the original minus the recorded leading lines,
    and none of those lines starts a finding."""
    lines = original.splitlines(keepends=True)
    removed = changes[0]['before'] if changes else []
    assert lines[:len(removed)] == removed, 'removed lines are not the leading lines'
    assert not any(FINDING_START.match(line) for line in removed), 'removed lines include a finding'
    assert normalized == ''.join(lines[len(removed):]), 'normalization changed more than the preamble'


def normalize_markdown(text):
    """Return the copy without the preamble and the list of changes."""
    lines = text.splitlines(keepends=True)
    first = next((i for i, line in enumerate(lines) if FINDING_START.match(line)), 0)
    removed = lines[:first]
    changes = [{'kind': 'markdown-preamble', 'before': removed}] if any(line.strip() for line in removed) else []
    normalized = ''.join(lines[len(removed):]) if changes else text
    check_only_preamble_removed(text, normalized, changes)
    return normalized, changes


def summary(changes):
    counts = {}
    for change in changes:
        counts[change['kind']] = counts.get(change['kind'], 0) + 1
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--report', type=Path, required=True, help='Original bound report (review.jsonl or .md)')
    parser.add_argument('--out', type=Path, required=True, help='Normalized copy (a new file)')
    args = parser.parse_args()
    raw = args.report.read_bytes()
    if args.report.suffix == '.md':
        normalized, changes = normalize_markdown(raw.decode('utf-8'))
        output = normalized
    else:
        rows = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
        normalized, changes = normalize(rows)
        output = ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in normalized)
    record = {'original': str(args.report), 'original_sha256': hashlib.sha256(raw).hexdigest(),
              'changes': summary(changes), 'details': changes}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if changes:
        args.out.write_text(output, encoding='utf-8')
        record['normalized'] = str(args.out)
        record['normalized_sha256'] = hashlib.sha256(args.out.read_bytes()).hexdigest()
    assert hashlib.sha256(args.report.read_bytes()).hexdigest() == record['original_sha256']
    args.out.with_name(args.out.name + '.changes.json').write_text(json.dumps(record, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps({'changes': record['changes'], 'normalized': record.get('normalized')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
