"""ARW measurement cell: counting valid instances, stop rules and the startup-prompt check, with a fake instance runner."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.arw import measure


def result(valid, notes=None):
    return {'status': 'succeeded', 'record': {'validity': {'valid': valid, 'notes': notes}}}


class NoWatch:
    binding = None
    stopped = mock.MagicMock()
    def __init__(self, expected): pass
    def start(self): pass


def cell(tmp, outcomes, count=2):
    queue = list(outcomes)
    def instance(work, scenario, name, session=None, effort=None):
        path = Path(tmp) / name
        path.mkdir()
        (path / 'score.json').write_text('{}')
        return queue.pop(0), path, 5.0
    guard = mock.MagicMock()
    with mock.patch.object(measure, 'guard_runs', guard), \
            mock.patch.object(measure.arw_run, 'expected_startup_sha', return_value='x'), \
            mock.patch.object(measure, 'StartupWatch', NoWatch), mock.patch('builtins.print'):
        return measure.run_cell('w', 'spec-readiness', Path(tmp) / 'out', count, instance=instance)


class CellTests(unittest.TestCase):
    def test_voids_do_not_count_and_valid_instances_are_stored(self):
        with tempfile.TemporaryDirectory() as tmp:
            records = cell(tmp, [result(True), result(False, 'no-completion'), result(True)])
            self.assertEqual([r['valid'] for r in records], [True, False, True])
            self.assertTrue((Path(tmp) / 'out/a1/score.json').is_file())
            self.assertEqual(len(json.loads((Path(tmp) / 'out/records.json').read_text())), 3)

    def test_repeated_void_reason_stops_the_cell(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, 'inspect-blocked'):
                cell(tmp, [result(False, 'inspect-blocked')] * 2)

    def test_failed_start_stops_at_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, 'failed'):
                cell(tmp, [{'status': 'failed', 'stage': 'start'}])


class ProvisionalTests(unittest.TestCase):
    def test_scores_each_saved_report_and_keeps_the_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ('a1', 'a2'):
                (Path(tmp) / name).mkdir()
                (Path(tmp) / name / 'report.txt').write_text('r')
            runner = mock.Mock(side_effect=lambda cmd, **kw: mock.Mock(stdout=json.dumps({'scores': {'final': 0.5 if 'a1' in cmd else 0.25}})))
            with mock.patch.object(measure.arw_pin, 'ensure', return_value=Path('/x')):
                self.assertEqual(measure.provisional('w', tmp, 'lower', runner=runner), {'a1': 0.5, 'a2': 0.25})
            self.assertEqual(json.loads((Path(tmp) / 'a2/provisional-lower.json').read_text())['scores']['final'], 0.25)
            self.assertIn('--provisional', runner.call_args.args[0])


if __name__ == '__main__':unittest.main()
