from datetime import datetime
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.metrics import engine_speed
from tools.metrics.engine_speed import SummaryError, local_time, render, summarize


def record(prompt, reused, read, generated, decode_ms=1000):
    return (f'strata serve: prompt {prompt} tokens = {reused} reused + {read} read in 500 ms (x tok/s), '
            f'{generated} generated in {decode_ms} ms')


def request(second, status=200, route='/strata/v1/responses'):
    return f'2026-11-09 06:00:{second:02d}.123 10.0.0.1 "POST {route} HTTP/1.1" {status} -'


START_1 = '[strata] 2026-11-09 05:00:00 engine started: --serve --flag-a'
ENGINE = '\n'.join([START_1, record(1000, 0, 1000, 10), record(120000, 119000, 1000, 100),
                    record(130000, 129000, 1000, 100),
                    '[strata] 2026-11-09 06:30:00 engine started: --serve --flag-a', record(140000, 139000, 1000, 50)])
FRONTEND = '\n'.join([request(10), request(20), request(30, status=500), request(40, route='/lease/acquire'),
                      request(50), '2026-11-09 06:30:10.000 10.0.0.1 "POST /strata/v1/responses HTTP/1.1" 200 -'])


class EngineSpeedTests(unittest.TestCase):
    def window(self, **options):
        return summarize(ENGINE, FRONTEND, datetime(2026, 11, 9, 6, 0, 0), datetime(2026, 11, 9, 7, 0, 0), **options)

    def test_records_get_the_time_of_the_matching_request(self):
        # Only 200 generation POSTs count: 06:00:10, 06:00:20, 06:00:50 pair with the first three records.
        summary = summarize(ENGINE, FRONTEND, datetime(2026, 11, 9, 6, 0, 15), datetime(2026, 11, 9, 6, 0, 30))
        self.assertEqual((summary['requests'], summary['output_tokens']), (1, 100))
        self.assertEqual(self.window()['requests'], 4)
        self.assertEqual(self.window()['unaligned'], 0)

    def test_rates_reuse_and_context_filter(self):
        summary = self.window()
        self.assertEqual(summary['output_tokens'], 260)
        self.assertAlmostEqual(summary['output_tok_per_s'], 65)
        self.assertAlmostEqual(summary['uncached_input_tok_per_s'], 4000 / 2.0 * 1)
        filtered = self.window(min_context=100000, max_context=150000)
        self.assertEqual((filtered['requests_in_window'], filtered['requests']), (4, 3))
        self.assertEqual(filtered['output_tokens'], 250)
        self.assertAlmostEqual(filtered['reuse_ratio'], (119000 + 129000 + 139000) / (119000 + 129000 + 139000 + 3000))
        empty = self.window(min_context=500000)
        self.assertEqual(empty['requests'], 0)
        self.assertIsNone(empty['output_tok_per_s'])
        self.assertIn('n/a', render(empty))

    def test_count_mismatch_is_reported_not_hidden(self):
        summary = summarize(ENGINE, FRONTEND.replace(request(50), ''), datetime(2026, 11, 9, 6, 0, 0),
                            datetime(2026, 11, 9, 7, 0, 0))
        self.assertEqual(summary['unaligned'], 1)

    def test_fingerprint_ignores_timestamp_and_never_shows_the_line(self):
        other = ENGINE.replace('2026-11-09 06:30:00', '2026-11-09 06:31:00')
        first = self.window()['engine_configs']
        self.assertEqual(first, summarize(other, FRONTEND, datetime(2026, 11, 9, 6), datetime(2026, 11, 9, 7))['engine_configs'])
        self.assertNotIn('flag-a', render(self.window()))
        changed = summarize(ENGINE.replace('--flag-a', '--flag-b'), FRONTEND, datetime(2026, 11, 9, 6),
                            datetime(2026, 11, 9, 7))['engine_configs']
        self.assertNotEqual(first, changed)

    def test_rotated_log_is_stated(self):
        with self.assertRaises(SummaryError):
            summarize(record(10, 0, 10, 1), FRONTEND, datetime(2026, 11, 9))
        early = summarize(ENGINE, FRONTEND, datetime(2026, 11, 1), datetime(2026, 11, 9, 7))
        self.assertFalse(early['covered_from_start'])
        self.assertIn('rotated', render(early))

    def test_time_parsing(self):
        self.assertEqual(local_time('2026-11-09T06:15:00'), datetime(2026, 11, 9, 6, 15))
        with self.assertRaises(SummaryError):
            local_time('yesterday')

    def test_errors_never_leak_private_text(self):
        secret = '/mnt/c/private-install-root'
        with patch('tools.ops.deployment_source.current_host', side_effect=ValueError(secret)), \
                patch.object(sys, 'argv', ['engine_speed', '--since', '2026-11-09T06:00:00']):
            with self.assertRaises(SystemExit) as caught:
                engine_speed.main()
        self.assertNotIn('private', str(caught.exception))
        self.assertIn('ValueError', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
