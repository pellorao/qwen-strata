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
  (e) a row whose `source` line does not hold the requirement it quotes, while the quoted `requirement` text matches
      exactly one other line of the same file (user 2026-10-21; e.g. a report whose row numbers are shifted by one):
      the row is moved to that line. The lines compared are the gate-1 requirement lines of that file in the Commit
      Audit request, or, for a gate-2 document (spec lines are free), every line of that document (user 2026-10-22:
      the same repair in both gates). A text matches a line when every backquoted span of the text is in the line
      and at least 80% of the text's other words (articles and prepositions ignored, plural -s dropped) are in the
      line; no match, several matches, or a target line another row ends up on as well leaves the row as written.
      Each moved row is one format error. Only `source.line` moves: it names which requirement a row judges, while
      the row quotes that requirement. Evidence `lines` are scored locators and are never moved (user 2026-10-22).

Markdown reports (Code Spec, Code Standards; user 2026-10-12):
  (b) everything before the first finding (a line starting with `1. ` style
      numbering or `- `) is a preamble such as a title or scope note and is
      removed;
  (b') after the first finding, a non-blank line that neither starts a finding
      nor starts with whitespace (ARW's markdownFindingBlocks: such a line is
      not part of any finding, so the whole report is a representation error
      and ARW's fallback parse drops the line; e.g. a fenced code block written
      at column 0 inside a finding) is removed. All such lines of a report are
      one repair, counted once in r like the one review-format-invalid
      diagnostic ARW gives the report as written (scorer units);
  (c) a backquoted locator that names only a file (`name.mjs:3`) gets its
      directory when exactly one frozen source has that name and every line
      is within it.
  (d) a locator part (`path:a` or `path:a-b`, or a bare `a-b` part that belongs
      to the nearest path) whose start lies beyond the end of that frozen
      source, when the lines are those of a harness-spilled tool-output file
      instead (Claude Code saves a large output, such as the staged diff, to a
      file and the model cites its lines; user 2026-10-20): converted through
      the diff hunk headers of the spill files when exactly one reading exists:
      every spill whose lines at the start and end are new-side diff lines of
      the named file, and whose every new-side line in between equals the
      frozen source line it maps to (the spill line without its diff prefix
      character), gives the same source lines. A part no spill reads that way,
      or that two spills read differently, stays as written (an invalid
      locator). The caller gives every spill kept for the handoff
      (bench_records.read_spills); a part within its source file is read as
      written, and the repair record counts those a spill would also read
      uniquely (`diagnostics.inRangeSpillReadable`, scoring unchanged).
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


STOPWORDS = frozenset('a an the to of in on at or and is are be by for with under that it its their as if from'.split())
SPAN = re.compile(r'`([^`]+)`')
WORD = re.compile(r'[a-z0-9]+')


def requirement_words(text):
    """(backquoted spans, other content words) of a requirement text."""
    spans = frozenset(SPAN.findall(text))
    words = {w[:-1] if len(w) > 3 and w.endswith('s') else w
             for w in WORD.findall(SPAN.sub(' ', text).lower()) if w not in STOPWORDS}
    return spans, frozenset(words)


def text_matches(quoted, line_text, threshold=0.8):
    spans, words = requirement_words(quoted)
    line_spans, line_words = requirement_words(line_text)
    if not spans <= line_spans or not (spans or words):
        return False
    return not words or len(words & line_words) / len(words) >= threshold


def requirement_moves(rows, requirements):
    """{row number: (before line, after line, text)} of the rows whose quoted requirement belongs to exactly one other
    line of their file. requirements maps file -> {line: text} (request_requirements: gate-1 requirement lines,
    gate-2 documents in full)."""
    moves = {}
    for number, row in enumerate(rows, 1):
        source, quoted = row.get('source'), row.get('requirement')
        if not (isinstance(source, dict) and is_int(source.get('line')) and isinstance(quoted, str)):
            continue
        lines = requirements.get(source.get('filePath'))
        if not lines or source['line'] not in lines or text_matches(quoted, lines[source['line']]):
            continue
        hits = [line for line, text in lines.items() if line != source['line'] and text_matches(quoted, text)]
        if len(hits) == 1:
            moves[number] = (source['line'], hits[0], quoted)
    # A target another row also ends on (moved or staying) is not unique: drop those moves until stable.
    while True:
        end = {}
        for number, row in enumerate(rows, 1):
            source = row.get('source')
            if isinstance(source, dict):
                line = moves[number][1] if number in moves else source.get('line')
                end.setdefault((source.get('filePath'), line), []).append(number)
        bad = [n for n, (_, after, _) in moves.items() if len(end[(rows[n - 1]['source']['filePath'], after)]) > 1]
        if not bad:
            return moves
        for n in bad:
            del moves[n]


def check_only_source_lines_changed(original, normalized, moves):
    for number, (before, after) in enumerate(zip(original, normalized), 1):
        if number in moves:
            assert before['source']['line'] == moves[number][0] and after['source']['line'] == moves[number][1], \
                f'source line change at row {number} is not the recorded one'
            after = {**after, 'source': {**after['source'], 'line': before['source']['line']}}
        assert after == before, f'requirement move changed more than source.line at row {number}'


def normalize(rows, requirements=None):
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
    moves = requirement_moves(rows, requirements) if requirements else {}
    unmoved = copy.deepcopy(rows)
    for number, (before, after, quoted) in sorted(moves.items()):
        changes.append({'kind': 'requirement-line', 'row': number, 'filePath': rows[number - 1]['source']['filePath'],
                        'before': before, 'after': after, 'requirement': quoted})
        rows[number - 1]['source']['line'] = after
    check_only_source_lines_changed(unmoved, rows, moves)
    return rows, changes


FINDING_START = re.compile(r'(?:[1-9][0-9]*\. |- )')
CONTINUATION = re.compile(r'\s')
SHORT_LOCATOR = re.compile(r'`(?P<name>[^`\s/:]+\.[A-Za-z0-9]+):(?P<lines>[1-9][0-9]*(?:-[1-9][0-9]*)?(?:,[1-9][0-9]*(?:-[1-9][0-9]*)?)*)`')


def line_numbers(lines):
    return [int(n) for part in lines.split(',') for n in part.split('-')]


def stray_lines(body):
    """Indexes of the lines after the first finding that ARW reads as part of no finding (b')."""
    first = next((i for i, line in enumerate(body) if FINDING_START.match(line)), None)
    if first is None:
        return []
    return [i for i, line in enumerate(body) if i > first and line.strip() and not FINDING_START.match(line)
            and not CONTINUATION.match(line)]


def apply_changes(original, changes):
    """Rebuild the copy from the original and the recorded changes."""
    lines = original.splitlines(keepends=True)
    preamble = [c for c in changes if c['kind'] == 'markdown-preamble']
    removed = preamble[0]['before'] if preamble else []
    assert lines[:len(removed)] == removed, 'removed lines are not the leading lines'
    assert not any(FINDING_START.match(line) for line in removed), 'removed lines include a finding'
    lines = lines[len(removed):]
    stray = [c for c in changes if c['kind'] == 'markdown-stray-lines']
    assert len(stray) <= 1, 'stray lines recorded twice'
    if stray:
        indexes = stray[0]['lines']
        assert indexes and indexes == stray_lines(lines), 'removed lines are not the lines outside every finding'
        assert [lines[i] for i in indexes] == stray[0]['before'], 'removed lines differ from the recorded ones'
        lines = [line for i, line in enumerate(lines) if i not in set(indexes)]
    for change in changes:
        if change['kind'] in ('short-evidence-path', 'spill-locator'):
            line = lines[change['line']]
            assert line[change['column']:].startswith(change['before']), 'locator is not where it was recorded'
            lines[change['line']] = line[:change['column']] + change['after'] + line[change['column'] + len(change['before']):]
    return ''.join(lines)


def check_only_markdown_changes(original, normalized, changes):
    """Round trip: the copy is the original minus the recorded preamble with the
    recorded short locators completed, and nothing else changed."""
    for change in changes:
        if change['kind'] == 'short-evidence-path':
            assert change['after'].startswith('`') and change['after'].endswith('/' + change['before'][1:]), \
                'locator change is not a directory prefix'
        if change['kind'] == 'spill-locator':
            assert NUMBER.sub('N', change['before']) == NUMBER.sub('N', change['after']), \
                'spill locator change is not a line-number conversion'
            assert change['converted'], 'spill locator change converts nothing'
    assert normalized == apply_changes(original, changes), 'normalization changed more than the recorded items'


def normalize_markdown(text, sources=None, spills=(), texts=None, diagnostics=None):
    """Return the copy and the list of changes.

    sources maps each frozen source path to its line count. A backquoted
    locator naming only a file (`name.mjs:3`) is completed with its directory
    when exactly one source has that name and every line is within it.
    spills are the texts of harness-spilled tool-output files and texts maps
    each frozen source path to its lines (text.split('\n')); (d) needs both.
    diagnostics, a dict, receives inRangeSpillReadable."""
    lines = text.splitlines(keepends=True)
    first = next((i for i, line in enumerate(lines) if FINDING_START.match(line)), 0)
    removed = lines[:first]
    changes = [{'kind': 'markdown-preamble', 'before': removed}] if any(line.strip() for line in removed) else []
    body = lines[len(removed):] if changes else lines
    stray = stray_lines(body)
    if stray:
        changes.append({'kind': 'markdown-stray-lines', 'lines': stray, 'before': [body[i] for i in stray]})
        body = [line for i, line in enumerate(body) if i not in set(stray)]
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
    maps = [spill_map(spill) for spill in spills]
    found = {'inRangeSpillReadable': 0}
    if maps and sources and texts:
        current = apply_changes(text, changes).splitlines(keepends=True)
        for index, line in enumerate(current):
            offset = 0
            for match in BACKQUOTED.finditer(line):
                converted = spill_conversion(match[0][1:-1], sources, maps, texts, found)
                if converted is None:
                    continue
                after, parts = converted
                after = f'`{after}`'
                changes.append({'kind': 'spill-locator', 'line': index, 'column': match.start() + offset,
                                'before': match[0], 'after': after, 'converted': parts})
                offset += len(after) - len(match[0])
    normalized = text
    if changes:
        normalized = apply_changes(text, changes)
    check_only_markdown_changes(text, normalized, changes)
    if diagnostics is not None:
        diagnostics.update(found)
    return normalized, changes


NUMBER = re.compile(r'[0-9]+')
BACKQUOTED = re.compile(r'`[^`\n]+`')
LOCATOR_PART = re.compile(r'^(?:(?P<path>[^\s:`]+/[^\s:`]+|[^\s:`/]+\.[A-Za-z0-9]+):)?(?P<start>[1-9][0-9]*)(?:-(?P<end>[1-9][0-9]*))?$')
HUNK = re.compile(r'^@@ -[0-9]+(?:,(?P<old>[0-9]+))? \+(?P<new_start>[0-9]+)(?:,(?P<new>[0-9]+))? @@')


def spill_map(text):
    """Line number in a spilled tool output -> (path, new-side line, content without the diff prefix) for the context
    and added lines of every diff hunk in it; other lines (headers, removed lines, other output) map to nothing.
    Lines are split at '\n' only, as a file viewer numbers them."""
    out, path, old, new, line_no = {}, None, 0, 0, 0
    for number, line in enumerate(text.split('\n'), 1):
        if old > 0 or new > 0:
            if line.startswith('\\'):
                continue
            if line.startswith('-'):
                old -= 1
                continue
            if line.startswith('+') or line.startswith(' ') or line == '':
                if path is not None:
                    out[number] = (path, line_no, line[1:])
                line_no += 1
                new -= 1
                if not line.startswith('+'):
                    old -= 1
                continue
            old = new = 0
        if line.startswith('diff --git '):
            path = None
        elif line.startswith('+++ '):
            target = line[4:].strip()
            path = target[2:] if target.startswith('b/') else None
        elif (hunk := HUNK.match(line)) and path is not None:
            old = int(hunk['old'] if hunk['old'] is not None else 1)
            new = int(hunk['new'] if hunk['new'] is not None else 1)
            line_no = int(hunk['new_start'])
    return out


def spill_reading(path, start, end, sources, maps, texts):
    """The one source range (a, b) every spill that reads spill lines start-end as new-side lines of path agrees on,
    each mapped line in between equal to the frozen source line; None when no spill or several readings."""
    results = set()
    for mapping in maps:
        a, b = mapping.get(start), mapping.get(end)
        if not (a and b and a[0] == path == b[0] and a[1] <= b[1] <= sources[path]):
            continue
        lines = texts.get(path) or []
        inside = [mapping[n] for n in range(start, end + 1) if n in mapping]
        if all(m[0] == path and m[1] <= len(lines) and lines[m[1] - 1] == m[2] for m in inside):
            results.add((a[1], b[1]))
    return next(iter(results)) if len(results) == 1 else None


def spill_conversion(content, sources, maps, texts, found=None):
    """(converted content, converted parts) of one backquoted locator, or None when no part is converted. found counts
    the parts within their source that a spill would also read uniquely (diagnostic only)."""
    parts, path, changed, converted = content.split(','), None, [], []
    for part in parts:
        match = LOCATOR_PART.match(part)
        if match is None:
            return None
        path = match['path'] or path
        if path is None or path not in sources:
            return None
        start, end = int(match['start']), int(match['end'] or match['start'])
        reading = spill_reading(path, start, end, sources, maps, texts)
        if start <= sources[path]:
            if reading is not None and found is not None:
                found['inRangeSpillReadable'] += 1
            changed.append(part)
            continue
        if reading is None:
            changed.append(part)
            continue
        a, b = reading
        lines = f'{a}-{b}' if match['end'] else f'{a}'
        new = f"{match['path']}:{lines}" if match['path'] else lines
        changed.append(new)
        converted.append({'before': part, 'after': new})
    if not converted:
        return None
    return ','.join(changed), converted


def staged_texts(root):
    """Texts of the files in the scenario index (the frozen source)."""
    git = lambda *args: subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True).stdout
    return {path: git('show', ':' + path) for path in git('ls-files').splitlines()}


def staged_sources(root, texts=None):
    """Line counts of the files in the scenario index (the frozen source)."""
    return {path: len(text.splitlines()) for path, text in (texts if texts is not None else staged_texts(root)).items()}


def request_requirements(report, scenario_root):
    """File -> {line: text} of the lines a Commit Audit row may quote, from the request next to the report
    (reports/review.jsonl beside request.json): the gate-1 requirement lines of each issue file, and every line of
    each gate-2 document (spec lines are free; a file that is also a gate-1 file keeps its gate-1 lines). None when
    there is no such request or scenario."""
    request = Path(report).parent.parent / 'request.json'
    if scenario_root is None or not request.is_file():
        return None
    try:
        data = json.loads(request.read_text(encoding='utf-8'))
    except ValueError:
        return None
    texts = staged_texts(scenario_root)
    out = {}
    for issue in data.get('gate1') or []:
        for item in issue.get('requirements') or []:
            lines = texts.get(item.get('filePath'), '').split('\n')
            if is_int(item.get('line')) and 1 <= item['line'] <= len(lines):
                out.setdefault(item['filePath'], {})[item['line']] = lines[item['line'] - 1]
    for gate in data.get('gate2') or []:
        for document in gate.get('documents') or []:
            if document in texts and document not in out:
                out[document] = dict(enumerate(texts[document].split('\n'), 1))
    return out


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
    parser.add_argument('--spill', type=Path, action='append', default=[],
                        help='harness-spilled tool-output file of the session (markdown reports); repeatable')
    args = parser.parse_args()
    raw = args.report.read_bytes()
    diagnostics = {}
    if args.report.suffix == '.md':
        texts = staged_texts(args.scenario_root) if args.scenario_root else None
        normalized, changes = normalize_markdown(raw.decode('utf-8'), staged_sources(None, texts) if texts else None,
                                                 [p.read_text(encoding='utf-8', errors='replace') for p in args.spill],
                                                 {k: v.split('\n') for k, v in texts.items()} if texts else None,
                                                 diagnostics)
        output = normalized
    else:
        try:
            rows = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
        except json.JSONDecodeError as error:
            # a row that is not JSON has no single meaning to repair: the report is scored by ARW as written
            rows, diagnostics['unparseable'] = None, str(error)
        if rows is None:
            changes, output = [], None
        else:
            normalized, changes = normalize(rows, request_requirements(args.report, args.scenario_root))
            output = ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in normalized)
    record = {'original': str(args.report), 'original_sha256': hashlib.sha256(raw).hexdigest(),
              **({'spills': [{'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in args.spill]}
                 if args.spill else {}),
              'changes': summary(changes), 'details': changes,
              **({'diagnostics': diagnostics} if args.spill or diagnostics else {})}
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
