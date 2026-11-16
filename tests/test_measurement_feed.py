"""Offline completion/export fixtures; never import model runners."""
import copy
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys

from tools.metrics.measurement_feed import finalize, BINDING


class MeasurementFeedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.output = self.root / 'tasks/measurements.jsonl'
        self.binding = copy.deepcopy(BINDING)
        self.binding.update(version='v0.2.99', ts='2026-11-16T21:00:00+09:00')
        self.scores = self.root / 'scores.json'
        self.scores.write_text(json.dumps({'summary': {'total': {
            'n': [10, 10], 'mean_v0.2.99': .62}}}))
        self.speed = self.root / 'speed.txt'
        self.speed.write_text(
            '== decode all requests\n125k n=4/4 v0.2.99=150.4\n150k n=4/4 v0.2.99=152.9\n'
            '== cold prefill initial\n125k n=4/4 v0.2.99=2621.3\n150k n=4/4 v0.2.99=2600.7\n')

    def run_export(self):
        return finalize(self.binding, self.scores, self.speed, self.output)

    def test_complete_batch_appends_both_tiers_with_finished_time_and_bindings(self):
        self.output.parent.mkdir(parents=True)
        self.output.write_text('{"existing":true}')
        result = self.run_export()
        rows = [json.loads(s) for s in self.output.read_text().splitlines()]
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1:], result)
        self.assertEqual([r['context_tier'] for r in result], ['125k', '150k'])
        self.assertEqual([r['decode_tok_s'] for r in result], [150.4, 152.9])
        for row in result:
            self.assertEqual(row['host'], 'rtx3080ti')
            self.assertEqual(row['ts'], datetime.fromisoformat(self.binding['ts']).timestamp())
            self.assertEqual(row['version'], 'v0.2.99')
            self.assertEqual(row['configuration'], BINDING['configuration'])
            self.assertEqual(row['intelligence_score'], .62)
            self.assertEqual(row['speed_protocol'], BINDING['speed_protocols'][row['context_tier']])
            self.assertNotIn('summary', row)

    def test_incomplete_wrong_protocol_and_nonfinite_results_never_append(self):
        original = self.speed.read_text()
        for bad in [original.replace('150k n=4/4', '150k n=3/4'),
                    original.replace('cold prefill initial', 'incremental prefill cached reqs'),
                    original.replace('v0.2.99=152.9', 'v0.2.98=152.9'),
                    original.replace('v0.2.99=152.9', 'v0.2.99=nan')]:
            with self.subTest(bad=bad):
                self.speed.write_text(bad)
                with self.assertRaises(ValueError):
                    self.run_export()
                self.assertFalse(self.output.exists())
        self.speed.write_text(original)
        for key, value in [('host', 'other'), ('ts', ''), ('ts', '2026-11-16'),
                           ('configuration', 'short-smoke'), ('intelligence_protocol', 'loop')]:
            with self.subTest(key=key, value=value):
                saved = self.binding[key]
                self.binding[key] = value
                with self.assertRaises(ValueError):
                    self.run_export()
                self.assertFalse(self.output.exists())
                self.binding[key] = saved

    def test_score_design_and_score_range_are_validated_before_any_write(self):
        for total in [{'n': [5, 5], 'mean_v0.2.99': .6},
                      {'n': [10, 10], 'mean_v0.2.99': float('nan')},
                      {'n': [10, 10], 'mean_v0.2.99': 1.1}]:
            self.scores.write_text(json.dumps({'summary': {'total': total}}))
            with self.assertRaises(ValueError):
                self.run_export()
            self.assertFalse(self.output.exists())

    def test_formal_completion_entrypoint_uses_injected_output_and_propagates_failure(self):
        binding_path = self.root / 'binding.json'
        binding_path.write_text(json.dumps(self.binding))
        command = [sys.executable, str(Path(__file__).resolve().parents[1] /
                   'scripts/wsl/finalize-stress-measurement'),
                   '--binding', str(binding_path), '--scores', str(self.scores),
                   '--speed', str(self.speed), '--output', str(self.output)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        original = self.output.read_bytes()
        self.speed.write_text('incomplete batch')
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.output.read_bytes(), original)
