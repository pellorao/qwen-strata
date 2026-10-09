"""Evidence preservation and replay gates, without model or service calls."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.loop.verify_loop_detection_corpus import evaluate, validate_fixtures


class CorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = json.loads((ROOT / 'benchmarks/loop-detection-v2/cases.json').read_text())

    def test_all_preserved_excerpts_and_iteration_marks_have_matching_bytes(self):
        self.assertEqual(validate_fixtures(self.corpus), [])

    def test_altered_excerpt_is_detected_without_access_to_original_sessions(self):
        changed = copy.deepcopy(self.corpus)
        block = next(b for c in changed['positive_cases'] for b in c['blocks']
                     if b['kind'] == 'reasoning')
        block['text'] = block['text'].replace(block['text'][0], 'X', 1)
        self.assertTrue(validate_fixtures(changed))

    def test_same_run_reused_in_reports_does_not_increase_executed_review_count(self):
        ledger = json.loads((ROOT / 'benchmarks/loop-detection-v2/inventory.json').read_text())
        rows = ledger['runs']
        self.assertEqual(len({r['instance_id'] for r in rows}), len(rows))
        self.assertEqual(sum(r['reviewer_executed'] for r in rows), 30)
        self.assertEqual(sum(r['performance_sample_eligible'] for r in rows), 24)
        self.assertEqual(sum(not r['reviewer_executed'] for r in rows), 1)
        self.assertEqual({r['host'] for r in rows}, {'local', 'rtx3080ti'})

    def test_one_passage_overlapping_two_markers_is_not_two_witnesses(self):
        case = {'case_id': 'overlap', 'evidence_marks': [
            {'event': 1, 'start': 0, 'end': 100},
            {'event': 1, 'start': 40, 'end': 120}]}
        hint = {'kind': 'reasoning-return', 'evidence_spans': [
            [['turn', 'a'], 50, 80], [['turn', 'b'], 0, 20]]}
        with patch('tools.loop.verify_loop_detection_corpus.replay', return_value=iter([(hint, {'a': 1, 'b': 9})])):
            self.assertFalse(evaluate(case)['matched'])

    def test_two_nonoverlapping_native_passages_match_distinct_iterations(self):
        case = {'case_id': 'distinct', 'evidence_marks': [
            {'event': 1, 'start': 0, 'end': 100},
            {'event': 2, 'start': 40, 'end': 120}]}
        hint = {'kind': 'reasoning-return', 'evidence_spans': [
            [['turn', 'a'], 20, 60], [['turn', 'b'], 50, 80]]}
        with patch('tools.loop.verify_loop_detection_corpus.replay', return_value=iter([(hint, {'a': 1, 'b': 2})])):
            self.assertTrue(evaluate(case)['matched'])


if __name__ == '__main__':
    unittest.main()
