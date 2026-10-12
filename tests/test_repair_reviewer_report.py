import unittest

from tools.reviewer.repair_reviewer_report import (check_only_lines_changed, check_only_preamble_removed, normalize,
                                                   normalize_markdown)


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

    def test_pairs_read_as_ranges_when_the_report_uses_them_throughout(self):
        rows, changes = normalize(report([1, 11], [4, 19], [3, 5], [7, 8], [2]))
        self.assertEqual(written(rows), [[[1, 11]], [[4, 19]], [[3, 5]], [[7, 8]], [2]])
        self.assertEqual(len(changes), 4)

    def test_pairs_dominating_a_few_nested_ranges_are_read_as_ranges(self):
        rows, changes = normalize(report([1, 11], [4, 19], [3, 5], [7, 8], [[2, 6]], [9]))
        self.assertEqual(written(rows), [[[1, 11]], [[4, 19]], [[3, 5]], [[7, 8]], [[2, 6]], [9]])
        self.assertEqual(len(changes), 4)

    def test_reports_mostly_using_nested_ranges_keep_pairs(self):
        original = report([1, 11], [[4, 19]], [[3, 5]], [6], [[2, 6]])
        rows, changes = normalize(original)
        self.assertEqual(rows, original)
        self.assertEqual(changes, [])

    def test_decreasing_pairs_and_single_lines_are_not_ranges(self):
        original = report([9, 3], [4], [6])
        rows, changes = normalize(original)
        self.assertEqual(rows, original)
        self.assertEqual(changes, [])

    def test_original_is_not_modified(self):
        original = report(3, [1, 2], [4, 5], [6, 7], [8, 9])
        snapshot = [dict(r, evidence=[dict(e) for e in r['evidence']]) for r in original]
        normalize(original)
        self.assertEqual(original, snapshot)

    def test_round_trip_rejects_changes_outside_lines(self):
        original = report(3, [1, 2], [4, 5], [6, 7], [8, 9])
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
            check_only_preamble_removed(original, text.replace('first', 'changed'), changes)
        with self.assertRaises(AssertionError):
            check_only_preamble_removed(original, text, [{'kind': 'markdown-preamble', 'before': ['# Title\n', '1. `a.mjs:3` - first\n']}])


if __name__ == '__main__':
    unittest.main()
