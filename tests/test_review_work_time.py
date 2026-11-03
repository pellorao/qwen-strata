from pathlib import Path
import tempfile
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
from tools.metrics.review_work_time import ReviewWorkClock, recorded_work_time

class WorkTimeTests(unittest.TestCase):
    def test_loaded_sleep_is_excluded_but_working_tool_wait_is_included(self):
        with tempfile.TemporaryDirectory() as directory:
            clock=ReviewWorkClock(Path(directory)/'work.json')
            clock.set_working(True,0)
            # Work stays active throughout a tool wait.
            self.assertEqual(clock.elapsed(0,60),60)
            clock.set_working(False,100)
            # Model may still be loaded for hours; no active task.
            self.assertEqual(clock.elapsed(0,10000),100)
            clock.set_working(True,10000)
            self.assertEqual(clock.elapsed(0,10050),150)

    def work(self, folder, segments, receipt=None):
        batch=Path(folder)
        run=batch/'premature-continuations'/'r1';run.mkdir(parents=True)
        (run/'run-finished.json').write_text('{}');(run/'segments.json').write_text(json.dumps(segments))
        if receipt is not None:(run/'hard-budget-native-facts-failure.json').write_text(json.dumps(receipt))
        return batch/'r1'

    def test_missing_fields_give_clear_errors_not_key_errors(self):
        original={'measurement':{'startedAt':0,'finishedAt':1000}}
        with tempfile.TemporaryDirectory() as folder:
            r1=self.work(folder,[{'measurement':{'startedAt':2000}}])
            with self.assertRaisesRegex(ValueError,'lacks measurement'):recorded_work_time(Path(folder),r1,original,5000)
        with tempfile.TemporaryDirectory() as folder:
            r1=self.work(folder,[{'measurement':{'startedAt':2000,'finishedAt':3000}}],{'protected_stop':True})
            with self.assertRaisesRegex(ValueError,'neither'):recorded_work_time(Path(folder),r1,original,5000)
        with tempfile.TemporaryDirectory() as folder:
            r1=self.work(folder,[{'measurement':{'startedAt':2000,'finishedAt':3000}}],
                         {'protected_stop':True,'protected_stop_completed_at':2.5})
            self.assertIn('seconds',recorded_work_time(Path(folder),r1,original,5000))

if __name__=='__main__':unittest.main()
