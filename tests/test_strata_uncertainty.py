import unittest
from tools.metrics.strata_tokens import bounded_rates


class BoundedRatesTests(unittest.TestCase):
    records = [{'input': 300, 'cached': 200, 'uncached': 100,
                'prompt_ms': 2000, 'output': 40, 'decode_ms': 4000}]

    def test_missing_stage_keeps_known_counts_and_propagates_denominators(self):
        r = bounded_rates(self.records,
                          {'uncached_input': [0, 20], 'cached_input': [0, 30],
                           'output': [0, 10]},
                          {'input': [0, 1], 'decode': [0, 2]}, [10, 12])
        self.assertEqual(r['tokens_interval']['uncached_input'], [100, 120])
        self.assertEqual(r['tokens_interval']['cached_input'], [200, 230])
        self.assertEqual(r['engine_input_tokens_per_second_interval'], [100 / 3, 60])
        self.assertEqual(r['engine_output_tokens_per_second_interval'], [40 / 6, 12.5])
        self.assertEqual(r['task_output_tokens_per_second_interval'], [40 / 12, 5])

    def test_complete_coverage_collapses_bounds(self):
        r = bounded_rates(self.records,
                          {k: [0, 0] for k in ('uncached_input', 'cached_input', 'output')},
                          {'input': [0, 0], 'decode': [0, 0]}, [10, 10])
        self.assertEqual(r['engine_input_tokens_per_second_interval'], [50, 50])
        self.assertEqual(r['task_output_tokens_per_second_interval'], [4, 4])

    def test_unproven_or_invalid_upper_bounds_are_rejected(self):
        for bound in ([0, float('inf')], [2, 1], [-1, 1], [0, None]):
            with self.subTest(bound=bound), self.assertRaises(ValueError):
                bounded_rates(self.records,
                              {'uncached_input': bound, 'cached_input': [0, 0], 'output': [0, 0]},
                              {'input': [0, 0], 'decode': [0, 0]}, [10, 10])


if __name__ == '__main__':
    unittest.main()
