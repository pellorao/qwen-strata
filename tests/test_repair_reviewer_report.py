import unittest

from tools.reviewer.repair_reviewer_report import (check_only_lines_changed, check_only_markdown_changes, normalize, text_matches,
                                                   normalize_markdown, spill_map)


def report(*lines):
    return [{'result': 'gap', 'evidence': [{'filePath': 'a.mjs', 'lines': value} for value in lines]
             + [{'command': 'node -e 1', 'exitCode': 0}]}]


def written(rows):
    return [item['lines'] for row in rows for item in row['evidence'] if 'lines' in item]


class NormalizeTest(unittest.TestCase):
    def test_scalar_lines_become_arrays(self):
        rows, changes = normalize(report(3, [4], [[5, 9]]))
        self.assertEqual(written(rows), [[3], [4], [[5, 9]]])
        self.assertEqual([c['kind'] for c in changes], ['scalar-lines'])

    def test_pairs_are_two_lines_and_stay_as_written(self):
        original = report([1, 11], [4, 19], [3, 5], [7, 8], [2], [9, 3])
        rows, changes = normalize(original)
        self.assertEqual(rows, original)
        self.assertEqual(changes, [])

    def test_original_is_not_modified(self):
        original = report(3, [1, 2], [[4, 5]])
        snapshot = [dict(r, evidence=[dict(e) for e in r['evidence']]) for r in original]
        normalize(original)
        self.assertEqual(original, snapshot)

    def test_round_trip_rejects_changes_outside_lines(self):
        original = report(3, [1, 2], [[4, 5]])
        rows, changes = normalize(original)
        check_only_lines_changed(original, rows, changes)
        rows[0]['result'] = 'satisfied'
        with self.assertRaises(AssertionError):
            check_only_lines_changed(original, rows, changes)

    def test_round_trip_rejects_unrecorded_lines_changes(self):
        original = report([1, 2], [[4, 5]], [[6, 7]])
        rows, changes = normalize(original)
        rows[0]['evidence'][0]['lines'] = [1, 3]
        with self.assertRaises(AssertionError):
            check_only_lines_changed(original, rows, changes)


FINDINGS = '1. `a.mjs:3` - first\n   - Evidence: `a.mjs:3`\n\n2. `b.mjs:4` - second\n'


class NormalizeMarkdownTest(unittest.TestCase):
    def test_title_and_scope_note_before_the_first_finding_are_removed(self):
        text, changes = normalize_markdown('# Code Spec Review\n\nScope: staged diff.\n\n' + FINDINGS)
        self.assertEqual(text, FINDINGS)
        self.assertEqual(changes, [{'kind': 'markdown-preamble',
                                    'before': ['# Code Spec Review\n', '\n', 'Scope: staged diff.\n', '\n']}])

    def test_bullet_findings_start_the_report(self):
        text, changes = normalize_markdown('Summary\n- `a.mjs:3` - first\n')
        self.assertEqual(text, '- `a.mjs:3` - first\n')
        self.assertEqual(len(changes), 1)

    def test_reports_starting_with_a_finding_or_without_findings_are_unchanged(self):
        for original in (FINDINGS, '\n' + FINDINGS, 'No findings.\n', '# Title\nNo findings.\n'):
            self.assertEqual(normalize_markdown(original), (original, []))

    def test_later_lines_including_invalid_locators_are_kept(self):
        body = FINDINGS + '   Evidence: 09:00 <= 11:00\n# trailing note\n'
        text, _ = normalize_markdown('# Title\n' + body)
        self.assertEqual(text, body)

    def test_round_trip_rejects_changes_beyond_the_preamble(self):
        original = '# Title\n' + FINDINGS
        text, changes = normalize_markdown(original)
        with self.assertRaises(AssertionError):
            check_only_markdown_changes(original, text.replace('first', 'changed'), changes)
        with self.assertRaises(AssertionError):
            check_only_markdown_changes(original, text, [{'kind': 'markdown-preamble', 'before': ['# Title\n', '1. `a.mjs:3` - first\n']}])


SOURCES = {'src/a/one.mjs': 40, 'src/b/two.mjs': 10, 'src/b/same.mjs': 5, 'src/c/same.mjs': 5}


class ShortLocatorTest(unittest.TestCase):
    def test_unique_short_locators_in_range_get_their_directory(self):
        text = '1. `src/a/one.mjs:3` - x\n   - fee at `one.mjs:20-26`, days at `two.mjs:1,3`\n'
        fixed, changes = normalize_markdown(text, SOURCES)
        self.assertEqual(fixed, '1. `src/a/one.mjs:3` - x\n   - fee at `src/a/one.mjs:20-26`, days at `src/b/two.mjs:1,3`\n')
        self.assertEqual([c['kind'] for c in changes], ['short-evidence-path'] * 2)

    def test_root_level_source_locators_are_already_complete(self):
        sources = dict(SOURCES, **{'governing-spec.md': 40})
        text = '1. `governing-spec.md:19` - x\n'
        fixed, changes = normalize_markdown(text, sources)
        self.assertEqual(fixed, text)
        self.assertEqual(changes, [])

    def test_ambiguous_out_of_range_or_unknown_locators_stay(self):
        text = '1. `src/a/one.mjs:3` - x\n   - `same.mjs:2`, `two.mjs:11`, `nine.mjs:1`, `:109`, `09:00 <= 11:00`\n'
        self.assertEqual(normalize_markdown(text, SOURCES), (text, []))

    def test_preamble_and_short_locators_are_both_recorded(self):
        fixed, changes = normalize_markdown('# T\n\n1. `one.mjs:3` - x\n', SOURCES)
        self.assertEqual(fixed, '1. `src/a/one.mjs:3` - x\n')
        self.assertEqual([c['kind'] for c in changes], ['markdown-preamble', 'short-evidence-path'])

    def test_round_trip_rejects_a_locator_rewritten_to_another_file(self):
        text = '1. `one.mjs:3` - x\n'
        fixed, changes = normalize_markdown(text, SOURCES)
        changes[0]['after'] = '`src/b/two.mjs:3`'
        with self.assertRaises(AssertionError):
            check_only_markdown_changes(text, fixed, changes)


# A spilled tool output: 3 lines of other output, then a staged diff of src/a/one.mjs (new-side lines 10-13 at spill
# lines 9 and 11-13, removed line at 10) and of src/b/two.mjs (new-side lines 1-3 at spill lines 19-21).
SPILL = ('# Rules\n\nsome text\n'
         'diff --git a/src/a/one.mjs b/src/a/one.mjs\nindex 1..2 100644\n--- a/src/a/one.mjs\n+++ b/src/a/one.mjs\n'
         '@@ -10,3 +10,4 @@ const x\n context ten\n-old eleven\n+new eleven\n+new twelve\n context thirteen\n'
         'diff --git a/src/b/two.mjs b/src/b/two.mjs\nnew file mode 100644\n--- /dev/null\n+++ b/src/b/two.mjs\n'
         '@@ -0,0 +1,3 @@\n+one\n+two\n+three\n')
SPILL_SOURCES = {'src/a/one.mjs': 13, 'src/b/two.mjs': 3}
SPILL_TEXTS = {'src/a/one.mjs': [f'line {n}' for n in range(1, 10)] + ['context ten', 'new eleven', 'new twelve',
                                                                        'context thirteen', ''],
               'src/b/two.mjs': ['one', 'two', 'three', '']}


def spill_normalize(text, sources=SPILL_SOURCES, spills=(SPILL,), texts=SPILL_TEXTS, diagnostics=None):
    return normalize_markdown(text, sources, list(spills), texts, diagnostics)


class SpillLocatorTest(unittest.TestCase):
    def test_spill_map_follows_hunk_headers(self):
        mapping = spill_map(SPILL)
        self.assertEqual(mapping[9], ('src/a/one.mjs', 10, 'context ten'))
        self.assertNotIn(10, mapping)  # removed line
        self.assertEqual([mapping[n][:2] for n in (11, 12, 13)], [('src/a/one.mjs', 11), ('src/a/one.mjs', 12),
                                                                ('src/a/one.mjs', 13)])
        self.assertEqual(mapping[19], ('src/b/two.mjs', 1, 'one'))
        self.assertEqual(mapping[21], ('src/b/two.mjs', 3, 'three'))
        self.assertNotIn(3, mapping)
        self.assertNotIn(18, mapping)  # hunk header

    def test_lines_are_split_at_newlines_only(self):
        # A form feed or line separator inside other output is not a line break for a file viewer.
        mapping = spill_map('a\x0cb\u2028c\n' + SPILL)
        self.assertEqual(mapping[10], ('src/a/one.mjs', 10, 'context ten'))

    def test_out_of_range_parts_that_one_spill_reads_are_converted(self):
        text = '- `src/a/one.mjs:2,11-12,src/b/two.mjs:20` - x\n'
        diagnostics = {}
        fixed, changes = spill_normalize(text, diagnostics=diagnostics)
        # `2` lies within one.mjs and is read as written; `11-12` is within the file too; only 20 is beyond two.mjs.
        self.assertEqual(fixed, '- `src/a/one.mjs:2,11-12,src/b/two.mjs:2` - x\n')
        self.assertEqual([c['converted'] for c in changes], [[{'before': 'src/b/two.mjs:20', 'after': 'src/b/two.mjs:2'}]])
        # `11-12` within the file is also a unique spill reading (spill lines 11-12 are one.mjs 11-12): diagnostic only.
        self.assertEqual(diagnostics, {'inRangeSpillReadable': 1})
        fixed, changes = spill_normalize('- `src/b/two.mjs:19-21`, `src/b/two.mjs:1,19`\n')
        self.assertEqual(fixed, '- `src/b/two.mjs:1-3`, `src/b/two.mjs:1,1`\n')
        self.assertEqual(sum(len(c['converted']) for c in changes), 2)

    def test_unmapped_crossing_or_ambiguous_parts_stay(self):
        sources = {'src/a/one.mjs': 8, 'src/b/two.mjs': 2}
        for text in ('- `src/a/one.mjs:50` - no spill line\n', '- `src/a/one.mjs:10` - removed line\n',
                     '- `src/a/one.mjs:13-19` - crosses into another file\n', '- `src/b/two.mjs:11` - line of one.mjs\n',
                     '- `src/b/two.mjs:21` - beyond the staged source\n'):
            self.assertEqual(spill_normalize(text, sources), (text, []))
        shifted = 'one more line\n' + SPILL
        text = '- `src/b/two.mjs:20` - x\n'
        self.assertEqual(spill_normalize(text, spills=(SPILL, shifted)), (text, []))
        self.assertEqual(normalize_markdown(text, SPILL_SOURCES), (text, []))
        # Without the frozen source texts nothing is converted (content cannot be checked).
        self.assertEqual(normalize_markdown(text, SPILL_SOURCES, [SPILL]), (text, []))

    def test_a_second_spill_reading_differently_makes_the_part_ambiguous(self):
        # Why only viewed spills are offered: an unviewed spill holding the same diff at other line numbers would
        # otherwise make a cited part ambiguous (bench_records.read_spills keeps it out).
        text = '- `src/b/two.mjs:20` - x\n'
        unviewed = 'x\n' + SPILL
        self.assertEqual(spill_normalize(text, spills=(SPILL, unviewed)), (text, []))
        self.assertEqual(spill_normalize(text, spills=(SPILL,))[0], '- `src/b/two.mjs:2` - x\n')

    def test_a_spill_of_another_version_is_not_converted(self):
        text = '- `src/b/two.mjs:19-21` - x\n'
        other = dict(SPILL_TEXTS, **{'src/b/two.mjs': ['one', 'TWO', 'three', '']})
        self.assertEqual(spill_normalize(text, texts=other), (text, []))
        # One spill of the frozen version and one of another version that reads the same lines: only the frozen one
        # counts, so the reading stays unique.
        stale = SPILL.replace('+two\n', '+TWO\n')
        fixed, changes = spill_normalize(text, spills=(SPILL, stale))
        self.assertEqual(fixed, '- `src/b/two.mjs:1-3` - x\n')

    def test_round_trip_rejects_a_spill_change_beyond_line_numbers(self):
        text = '- `src/b/two.mjs:20` - x\n'
        fixed, changes = spill_normalize(text)
        check_only_markdown_changes(text, fixed, changes)
        changes[0]['after'] = '`src/a/one.mjs:2`'
        with self.assertRaises(AssertionError):
            check_only_markdown_changes(text, fixed, changes)


if __name__ == '__main__':
    unittest.main()


F = '.scratch/x/issues/01.md'
KEY = {F: {7: 'Connect dispatch planning and execution.',
           19: '- [x] Under `docs/p.md`, `nextRetryDelay` applies the Retry timing rules to every server-provided `retryAfter`',
           20: '- [x] `canPlanRoute` treats an actor holding `routes:admin` as owning every depot.',
           21: '- [x] `canPlanRoute` refuses every suspended actor.',
           22: '- [x] `renameTemp` renames the temporary bytes after they are durable.',
           23: '- [x] `renameTemp` renames the temporary bytes after they are logged.'}}


def row(line, requirement, file=F):
    return {'source': {'filePath': file, 'line': line}, 'requirement': requirement, 'result': 'satisfied',
            'evidence': [{'filePath': 'a.mjs', 'lines': [1]}]}


class RequirementLineTest(unittest.TestCase):
    def test_unique_text_moves_the_row_and_counts_one_change(self):
        original = [row(7, '`nextRetryDelay` applies Retry timing rules to every server-provided `retryAfter`.'),
                    row(19, '`canPlanRoute` treats an actor holding `routes:admin` as owning every depot.')]
        rows, changes = normalize(original, KEY)
        self.assertEqual([r['source']['line'] for r in rows], [19, 20])
        self.assertEqual([(c['kind'], c['row'], c['before'], c['after']) for c in changes],
                         [('requirement-line', 1, 7, 19), ('requirement-line', 2, 19, 20)])
        self.assertEqual(original[0]['source']['line'], 7)

    def test_ambiguous_text_stays(self):
        original = [row(7, '`renameTemp` renames the temporary bytes after they are durable or logged.')]
        rows, changes = normalize(original, KEY)
        self.assertEqual((rows, changes), (original, []))

    def test_text_that_fits_its_own_line_stays(self):
        original = [row(21, '`canPlanRoute` refuses every suspended actor.'),
                    row(20, '`canPlanRoute` treats an actor holding `routes:admin` as owning every depot')]
        rows, changes = normalize(original, KEY)
        self.assertEqual((rows, changes), (original, []))

    def test_no_match_or_unlisted_line_or_other_file_stays(self):
        original = [row(7, '`unknownFn` does something else entirely.'), row(5, '`canPlanRoute` refuses every suspended actor.'),
                    row(7, '`canPlanRoute` refuses every suspended actor.', file='other.md')]
        rows, changes = normalize(original, KEY)
        self.assertEqual((rows, changes), (original, []))

    def test_move_onto_a_line_another_row_keeps_is_dropped(self):
        original = [row(7, '`canPlanRoute` refuses every suspended actor.'),
                    row(21, '`canPlanRoute` refuses every suspended actor.')]
        rows, changes = normalize(original, KEY)
        self.assertEqual((rows, changes), (original, []))

    def test_text_matching(self):
        self.assertTrue(text_matches('`f` returns the stops.', '- [x] `f` returns every one of the stops'))
        self.assertFalse(text_matches('`g` returns the stops.', '`f` returns the stops'))

    def test_without_requirements_nothing_moves(self):
        original = [row(7, '`canPlanRoute` refuses every suspended actor.')]
        self.assertEqual(normalize(original)[1], [])
