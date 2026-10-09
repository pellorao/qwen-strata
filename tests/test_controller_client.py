"""Measurement telemetry must not discard completed model responses."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.ops.controller_client import usage_counts


class UsageCountsTest(unittest.TestCase):
    def test_split_phase_cache_can_exceed_original_request_input(self):
        # Real training encountered this shape: the reused thinking prefix is
        # longer than the original user input. These counters cannot be mixed.
        raw = {'prompt_tokens': 16535,
               'prompt_tokens_details': {'cached_tokens': 20631},
               'completion_tokens': 16367}
        counts = usage_counts(raw)
        self.assertIsNone(counts['uncached_input'])
        self.assertIsNone(counts['cached_input'])
        self.assertEqual(counts['output'], 16367)
        self.assertIn('exceeds', counts['reason'])
        self.assertEqual(raw['prompt_tokens_details']['cached_tokens'], 20631)

    def test_valid_response_keeps_three_token_categories(self):
        self.assertEqual(usage_counts({
            'input_tokens': 100, 'input_tokens_details': {'cached_tokens': 60},
            'output_tokens': 7}),
            {'uncached_input': 40, 'cached_input': 60, 'output': 7})


if __name__ == '__main__':
    unittest.main()
