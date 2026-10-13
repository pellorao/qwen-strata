"""No model requests: ARW-owned work time starts at ARW's native start, not at dispatch (model load excluded)."""
import json, sys, tempfile, time
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tools.reviewer.arw_measure as arw_measure


class Machine:
    def __init__(self, result):
        self.result = result

    def call(self, operation, value, timeout=120):
        return self.result if operation == 'list_agents' else {}


class ArwOwnedWorkStartTests(TestCase):
    def observe(self, owner, native_offset):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            dispatched = time.time() - 100
            result = {'runId': 'r', 'state': 'completed', 'completion': {'status': 'ready'},
                      'measurement': {'startedAt': (dispatched + native_offset) * 1000, 'wallClockMs': 1}}
            record = {'accepted': {'runId': 'r', 'messageId': 'm', 'recoveryPath': str(folder / 'recovery.json')}, 'started_at': dispatched,
                      'role': 'x', 'instanceId': 'i', 'selection': {'model_owner': owner} if owner else {}}
            return arw_measure.observe_review(Machine(result), record, folder), dispatched

    def test_arw_owned_excludes_model_load_before_native_start(self):
        record, dispatched = self.observe('arw', 30)
        self.assertAlmostEqual(record['review_work_seconds'], record['finished_at'] - dispatched - 30, places=2)
        self.assertAlmostEqual(record['review_dispatch_work_seconds'], record['finished_at'] - dispatched, places=2)
        self.assertIn('measurement.startedAt', record['review_work_time_source'])

    def test_project_owned_keeps_dispatch_start(self):
        record, dispatched = self.observe(None, 30)
        self.assertAlmostEqual(record['review_work_seconds'], record['finished_at'] - dispatched, places=2)
        self.assertNotIn('review_dispatch_work_seconds', record)

    def test_native_start_missing_keeps_dispatch_start(self):
        self.assertIsNone(arw_measure.native_work_start({'measurement': {}}))
