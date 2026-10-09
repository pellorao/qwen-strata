from pathlib import Path
import tempfile
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.metrics.review_work_time import ReviewWorkClock

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

if __name__=='__main__':unittest.main()
