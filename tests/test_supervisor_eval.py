"""Route B's supervisor answers are combined by program, and its view of a flag stays compact."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.loop.loop_replay import Observation
from tools.loop.supervisor_eval import HEAD, TAIL, decide, view


class SupervisorEvalTests(unittest.TestCase):
    def test_only_the_same_step_without_progress_is_a_repeat(self):
        answer = '{"same_step": "%s", "progress": "%s", "reason": "r"}'
        self.assertEqual(decide(answer % ('yes', 'no')), 1.0)
        self.assertEqual(decide(answer % ('yes', 'yes')), 0.0)
        self.assertEqual(decide(answer % ('no', 'no')), 0.0)
        self.assertEqual(decide(answer % ('maybe', 'no')), 0.5)
        self.assertEqual(decide('no json'), 0.5)

    def test_view_omits_the_middle_of_a_long_gap(self):
        trace = [Observation('t', 'x', {'kind': 'task', 'text': 'do it'})] + [
            Observation(str(n), 'x', {'kind': 'reasoning', 'text': f'step {n}'}) for n in range(1, 40)]
        text = view(trace, 2, 39)
        self.assertIn('do it', text)
        self.assertIn('step 2', text)
        self.assertIn('step 39', text)
        self.assertEqual(text.count('[between reasoning]'), HEAD + TAIL)
        self.assertIn(f'[... {39 - 2 - 1 - HEAD - TAIL} records omitted ...]', text)


if __name__ == '__main__':
    unittest.main()
