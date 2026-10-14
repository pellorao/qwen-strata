from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.metrics.speed_probe import bodies, material, rates, run, time_limit_seconds, STARTUP_SHA256
from tools.metrics.strata_tokens import parse_engine_log

LOG = '''strata serve: prompt 1200 tokens = 0 reused + 1200 read in 600.0 ms (2000 tok/s), 16 generated in 200.0 ms
strata serve: prompt 41200 tokens = 1100 reused + 40100 read in 18227.3 ms (2200 tok/s), 512 generated in 5389.5 ms
'''


class SpeedProbeTests(unittest.TestCase):
    def test_rates_use_engine_records_and_token_difference(self):
        result = rates(parse_engine_log(LOG), 140000)
        self.assertEqual(result['material_tokens'], 40000)
        self.assertAlmostEqual(result['beta_bytes_per_token'], 3.5)
        self.assertAlmostEqual(result['P_tokens_per_second'], 40100 / 18.2273)
        self.assertAlmostEqual(result['G_tokens_per_second'], 512 / 5.3895)

    def test_k_calibration_reproduces_b_over_10k_minutes(self):
        beta, P, G, B = 3.5, 2200.0, 88.0, 150000
        k = G * (0.006 * beta - 1 / P)
        self.assertAlmostEqual(time_limit_seconds(B, beta, P, G, k), B / 10000 * 60)

    def test_material_counts_file_bytes_and_bodies_share_instruction(self):
        with tempfile.TemporaryDirectory() as directory:
            a = Path(directory) / 'a.md'; a.write_text('rule\n')
            b = Path(directory) / 'b.mjs'; b.write_text('export const x = 1;\n')
            text, size = material([a, b])
            self.assertEqual(size, 5 + 20)
            baseline, probe = bodies(text, 64)
            self.assertTrue(probe['messages'][0]['content'].endswith(baseline['messages'][0]['content']))
            self.assertEqual(probe['max_tokens'], 64)

    def test_too_few_or_degenerate_records_are_rejected(self):
        with self.assertRaises(ValueError):
            rates(parse_engine_log(LOG.splitlines()[0]), 100)
        flipped = '\n'.join(reversed(LOG.strip().splitlines()))
        with self.assertRaises(ValueError):
            rates(parse_engine_log(flipped), 100)

    def test_run_against_fake_host_releases_and_records(self):
        calls = []
        class Owner:
            def __enter__(self): calls.append('acquire'); return self
            def __exit__(self, *exc): calls.append('release')
            def call(self, path, body=None, timeout=900):
                calls.append(path)
                return {'status': 'stopped'} if path == '/model/status' else {'choices': []}
            def start(self, **options):
                calls.append(('start', options))
                return {'native_health': {'max_context': 206584, 'startup_instructions': {
                    'path': 'config/prompts/startup-instructions.txt', 'sha256': STARTUP_SHA256}}}, 30.0
            def stop(self): calls.append('stop'); return {'status': 'stopped'}
        class Host:
            installation = Path('/nonexistent')
            def controller(self, folder): return Owner()
            def log_offset(self, model): return 0
            def log_bytes_since(self, model, offset): return LOG.encode()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'spec.md'; source.write_text('x' * 140000)
            result = run(Host(), [source], Path(directory) / 'probe')
            self.assertAlmostEqual(result['beta_bytes_per_token'], 3.5)
            self.assertTrue((Path(directory) / 'probe/speed-probe.json').exists())
        self.assertEqual(calls.count('/strata/v1/chat/completions'), 2)
        self.assertEqual(calls[-2:], ['stop', 'release'])


if __name__ == '__main__':
    unittest.main()
