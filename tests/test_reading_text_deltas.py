import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.reviewer.reading_text_deltas import exact_line_changes


class ExactReadingDeltaTests(unittest.TestCase):
    def test_insert_delete_and_final_newline_are_preserved(self):
        result = exact_line_changes('a\nb\nc\n', 'a\nchanged\nc')
        self.assertEqual(result, [{'old_lines': [2, 3], 'new_lines': [2, 3],
                                  'new_text': 'changed\nc'}])

    def test_failed_or_unfaithful_diff_falls_back_to_full_text(self):
        for error in (AttributeError('missing index'), TypeError('invalid bound')):
            with self.subTest(error=type(error).__name__), patch(
                    'tools.reviewer.reading_text_deltas.difflib.SequenceMatcher', side_effect=error):
                self.assertIsNone(exact_line_changes('a\n', 'b\n'))
        with patch('tools.reviewer.reading_text_deltas.difflib.SequenceMatcher') as matcher:
            matcher.return_value.get_opcodes.return_value = [('equal', 0, 1, 0, 1)]
            self.assertIsNone(exact_line_changes('a\n', 'b\n'))
