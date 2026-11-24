"""ARW measurement cell: counting valid instances, stop rules and the startup-prompt check, with a fake instance runner."""
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.arw import measure


def result(valid, notes=None):
    return {'status': 'succeeded', 'record': {'validity': {'valid': valid, 'notes': notes}}}


class NoWatch:
    binding = None
    stopped = mock.MagicMock()
    def __init__(self, expected, abort=None): pass
    def start(self): pass


def cell(tmp, outcomes, count=2, first=1):
    queue = list(outcomes)
    def instance(work, scenario, name, session=None, effort=None, started=None):
        path = Path(tmp) / name
        path.mkdir()
        (path / 'score.json').write_text('{}')
        return queue.pop(0), path, 5.0
    guard = mock.MagicMock()
    with mock.patch.object(measure, 'guard_runs', guard), \
            mock.patch.object(measure.arw_run, 'expected_startup_sha', return_value='x'), \
            mock.patch.object(measure, 'StartupWatch', NoWatch), mock.patch('builtins.print'):
        return measure.run_cell('w', 'spec-readiness', Path(tmp) / 'out', count, first=first, instance=instance)


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


    def test_resume_keeps_earlier_records_and_counts_their_valid_instances(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'out'
            out.mkdir()
            old = [{'name': 'a1', 'status': 'succeeded', 'valid': True, 'reason': None, 'seconds': 1}]
            (out / 'records.json').write_text(json.dumps(old))
            records = cell(tmp, [result(True)], count=2, first=2)
            self.assertEqual([r['name'] for r in records], ['a1', 'a2'])
            self.assertEqual([r['name'] for r in json.loads((out / 'records.json').read_text())], ['a1', 'a2'])

    def test_records_are_saved_after_each_instance(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(IndexError):
                cell(tmp, [result(True)], count=2)  # the second instance has no outcome left: the fake runner fails
            self.assertEqual(len(json.loads((Path(tmp) / 'out/records.json').read_text())), 1)


def wait_binding(watch):
    for _ in range(100):
        if watch.binding is not None:
            break
        time.sleep(0.005)
    watch.stopped.set()
    watch.join(1)


class WatchTests(unittest.TestCase):
    def reading(self, sha):
        return {'model': 'm', 'startup_instructions': {'sha256': sha}}

    def test_mismatch_aborts_the_instance_at_the_first_loaded_reading(self):
        abort = mock.Mock()
        watch = measure.StartupWatch('want', read=lambda: self.reading('other'), abort=abort)
        with mock.patch.object(measure, 'POLL', 0):
            watch.start()
            wait_binding(watch)
        self.assertFalse(watch.binding['ok'])
        abort.assert_called_once()

    def test_match_does_not_abort(self):
        abort = mock.Mock()
        watch = measure.StartupWatch('want', read=lambda: self.reading('want'), abort=abort)
        with mock.patch.object(measure, 'POLL', 0):
            watch.start()
            wait_binding(watch)
        self.assertTrue(watch.binding['ok'])
        abort.assert_not_called()

    def test_killer_stops_the_latest_process_group(self):
        process = mock.Mock(pid=123)
        with mock.patch.object(measure.os, 'killpg') as killpg:
            measure.killer([process])()
        killpg.assert_called_once_with(123, measure.signal.SIGTERM)

    def test_abort_before_registration_stops_the_process_when_registered(self):
        process = mock.Mock(pid=456)
        processes = []
        abort = measure.killer(processes)
        with mock.patch.object(measure.os, 'killpg') as killpg:
            abort()
            killpg.assert_not_called()
            abort.register(process)
        killpg.assert_called_once_with(456, measure.signal.SIGTERM)


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
