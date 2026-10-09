from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.metrics.strata_tokens import parse_engine_log, sum_engine_tokens


class StrataTokenTests(unittest.TestCase):
    def test_prompt_chunk_clamp_is_not_an_incomplete_token_record(self):
        text = ('strata serve: prompt chunk 16384 -> 8192 tokens so its buffers fit in every expert cache\n'
                'strata serve: prompt 20 tokens = 5 reused + 15 read in 3 ms, '
                '2 generated in 4 ms\n')
        self.assertEqual(sum_engine_tokens(parse_engine_log(text)),
                         {'uncached_input': 15, 'cached_input': 5, 'output': 2})
        for text in ('strata serve: prompt ', 'strata serve: prompt chunk 16384 ->'):
            with self.assertRaises(ValueError):
                parse_engine_log(text)
    def test_budget_continuation_counts_both_physical_passes(self):
        text = ('strata serve: prompt 50072 tokens = 13058 reused + 37014 read in 11834 ms, '
                '4096 generated in 37856 ms\n'
                'strata serve: prompt 54186 tokens = 54167 reused + 19 read in 118 ms, '
                '406 generated in 3563 ms\n')
        self.assertEqual(sum_engine_tokens(parse_engine_log(text)),
                         {'uncached_input': 37033, 'cached_input': 67225, 'output': 4502})

    def test_cancelled_partial_prefill_counts_only_actual_reads(self):
        text = ('strata serve: prompt 200000 tokens = 1000 reused + 50 of 199000 read '
                'in 10 ms, 0 generated in 0 ms')
        self.assertEqual(sum_engine_tokens(parse_engine_log(text)),
                         {'uncached_input': 50, 'cached_input': 1000, 'output': 0})

    def test_missing_or_truncated_record_cannot_be_zero_cost(self):
        self.assertIsNone(sum_engine_tokens(parse_engine_log('model startup complete')))
        with self.assertRaises(ValueError):
            parse_engine_log('strata serve: prompt 50072 tokens = 13058 reused')
        with self.assertRaises(ValueError):
            parse_engine_log('strata serve: prompt 10 tokens = 8 reused + 5 read in 1 ms, '
                             '1 generated in 1 ms')


if __name__ == '__main__':
    unittest.main()
