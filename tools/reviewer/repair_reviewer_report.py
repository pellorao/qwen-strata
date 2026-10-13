"""Format normalization of a Reviewer report on an independent copy.

Only writing that has exactly one meaning under the frozen ARW locator
definitions is repaired (user 2026-10-12, same for tuning and benchmark);
results, findings, evidence files and the lines pointed at stay the same. The
same rules apply to every instance regardless of its score, and the original
report is never changed.

JSONL reports (Commit Audit; `lines` is an array of positive integers or
[start, end] closed ranges):
  (a) a scalar `lines` value n becomes [n]. A top-level [a, b] is two lines
      by definition and is left as written.

Markdown reports (Code Spec, Code Standards; user 2026-10-12):
  (b) everything before the first finding (a line starting with `1. ` style
      numbering or `- `) is a preamble such as a title or scope note and is
      removed;
  (c) a backquoted locator that names only a file (`name.mjs:3`) gets its
      directory when exactly one frozen source has that name and every line
      is within it.
Other locator errors (out-of-range lines, non-file text) stay as written.
Whether a repaired report is still penalized is decided by the scorer: the
ARW patch keeps the original's diagnostics.
"""
import argparse
import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path

def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


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
    check_only_lines_changed(original, rows, changes)
    return rows, changes


FINDING_START = re.compile(r'(?:[1-9][0-9]*\. |- )')
SHORT_LOCATOR = re.compile(r'`(?P<name>[^`\s/:]+\.[A-Za-z0-9]+):(?P<lines>[1-9][0-9]*(?:-[1-9][0-9]*)?(?:,[1-9][0-9]*(?:-[1-9][0-9]*)?)*)`')


def line_numbers(lines):
    return [int(n) for part in lines.split(',') for n in part.split('-')]


def apply_changes(original, changes):
    """Rebuild the copy from the original and the recorded changes."""
    lines = original.splitlines(keepends=True)
    preamble = [c for c in changes if c['kind'] == 'markdown-preamble']
    removed = preamble[0]['before'] if preamble else []
    assert lines[:len(removed)] == removed, 'removed lines are not the leading lines'
    assert not any(FINDING_START.match(line) for line in removed), 'removed lines include a finding'
    lines = lines[len(removed):]
    for change in changes:
        if change['kind'] == 'short-evidence-path':
            line = lines[change['line']]
            assert line[change['column']:].startswith(change['before']), 'short locator is not where it was recorded'
            lines[change['line']] = line[:change['column']] + change['after'] + line[change['column'] + len(change['before']):]
    return ''.join(lines)


def check_only_markdown_changes(original, normalized, changes):
    """Round trip: the copy is the original minus the recorded preamble with the
    recorded short locators completed, and nothing else changed."""
    for change in changes:
        if change['kind'] == 'short-evidence-path':
            assert change['after'].startswith('`') and change['after'].endswith('/' + change['before'][1:]), \
                'locator change is not a directory prefix'
    assert normalized == apply_changes(original, changes), 'normalization changed more than the recorded items'


def normalize_markdown(text, sources=None):
    """Return the copy and the list of changes.

    sources maps each frozen source path to its line count. A backquoted
    locator naming only a file (`name.mjs:3`) is completed with its directory
    when exactly one source has that name and every line is within it."""
    lines = text.splitlines(keepends=True)
    first = next((i for i, line in enumerate(lines) if FINDING_START.match(line)), 0)
    removed = lines[:first]
    changes = [{'kind': 'markdown-preamble', 'before': removed}] if any(line.strip() for line in removed) else []
    body = lines[len(removed):] if changes else lines
    for index, line in enumerate(body):
        offset = 0
        for match in SHORT_LOCATOR.finditer(line):
            # A root-level source (`governing-spec.md:3`) is already a complete locator.
            paths = [p for p in sources or {} if p.rsplit('/', 1)[-1] == match['name']]
            if match['name'] in (sources or {}) or len(paths) != 1 or max(line_numbers(match['lines'])) > sources[paths[0]]:
                continue
            before, after = match[0], f"`{paths[0]}:{match['lines']}`"
            changes.append({'kind': 'short-evidence-path', 'line': index, 'column': match.start() + offset,
                            'before': before, 'after': after})
            offset += len(after) - len(before)
    normalized = text
    if changes:
        normalized = apply_changes(text, changes)
    check_only_markdown_changes(text, normalized, changes)
    return normalized, changes


def staged_sources(root):
    """Line counts of the files in the scenario index (the frozen source)."""
    git = lambda *args: subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True).stdout
    return {path: len(git('show', ':' + path).splitlines()) for path in git('ls-files').splitlines()}


def summary(changes):
    counts = {}
    for change in changes:
        counts[change['kind']] = counts.get(change['kind'], 0) + 1
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--report', type=Path, required=True, help='Original bound report (review.jsonl or .md)')
    parser.add_argument('--out', type=Path, required=True, help='Normalized copy (a new file)')
    parser.add_argument('--scenario-root', type=Path, help='Scenario repository whose index holds the frozen source (markdown reports)')
    args = parser.parse_args()
    raw = args.report.read_bytes()
    if args.report.suffix == '.md':
        normalized, changes = normalize_markdown(raw.decode('utf-8'), staged_sources(args.scenario_root) if args.scenario_root else None)
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
