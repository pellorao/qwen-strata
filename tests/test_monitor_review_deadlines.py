import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.reviewer import monitor_review_deadlines as monitor


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.batch = Path(self.temp.name) / 'batch'
        self.batch.mkdir()
        (self.batch / 'runtime.json').write_text(json.dumps({'repositoryRoot': str(self.batch)}))
        self.folder = Path(self.temp.name) / 'monitor'

    def run_monitor(self, sleep):
        with mock.patch.object(monitor, 'Machine'), mock.patch.object(monitor.time, 'sleep', sleep):
            monitor.monitor(self.batch, self.folder)
        return json.loads((self.folder / 'status.json').read_text())

    def test_a_schedule_caught_mid_write_is_retried(self):
        (self.batch / 'schedule.json').write_text('[{"instanceId": "a"')  # truncated, as a reader can see it
        (self.batch / 'results.json').write_text('[]')
        calls = []

        def sleep(_):
            calls.append(1)
            (self.batch / 'schedule.json').write_text('[{"instanceId": "a"}]')
            (self.batch / 'results.json').write_text('[{"instanceId": "a"}]')
        self.assertEqual(self.run_monitor(sleep)['status'], 'finished')
        self.assertEqual(len(calls), 1)

    def test_a_result_without_an_accepted_run_fails_with_a_clear_message(self):
        (self.batch / 'schedule.json').write_text('[{"instanceId": "a"}]')
        (self.batch / 'results.json').write_text('[]')
        (self.batch / 'a').mkdir()
        (self.batch / 'a/result.json').write_text('{"started_at": 1}')
        with self.assertRaisesRegex(ValueError, 'a: result.json holds no accepted run'):
            self.run_monitor(lambda _: None)
        status = json.loads((self.folder / 'status.json').read_text())
        self.assertEqual(status['status'], 'failed')
        self.assertIn('no accepted run', status['error'])


if __name__ == '__main__':
    unittest.main()
