import sys
import tempfile
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.metrics.model_lifetime import ModelAliveClock,alive_seconds

class LifetimeTests(unittest.TestCase):
    def test_clips_to_task_and_merges_overlaps_without_double_counting(self):
        self.assertEqual(alive_seconds(1000,10000,[{'start_ms':0,'end_ms':3000},{'start_ms':2000,'end_ms':5000},{'start_ms':8000,'end_ms':20000}]),6)
    def test_shutdown_pauses_clock_and_alive_recovery_counts_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'lifetime.json';clock=ModelAliveClock(path)
            clock.observe(True,0);clock.observe(False,100);clock.observe(True,10000)
            self.assertEqual(clock.elapsed(0,10050),150)
            restored=ModelAliveClock(path)
            self.assertEqual(restored.elapsed(0,10100),200)
            self.assertEqual(restored.elapsed(10020,10100),80)

if __name__=='__main__':unittest.main()
