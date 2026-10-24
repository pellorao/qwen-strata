import unittest

from tools.tuning import loop_stats as ls


class LoopStatsTest(unittest.TestCase):
    def test_generation_repeat(self):
        unit = 'the quick brown fox jumps over the lazy dog again. '
        self.assertTrue(ls.repeated_tail('intro ' + unit * 4))
        self.assertFalse(ls.repeated_tail('intro ' + unit * 3))
        self.assertFalse(ls.repeated_tail('abc ' * 30))  # unit shorter than 40 characters repeats as a longer unit only
        self.assertFalse(ls.repeated_tail('plain varied text ' + ''.join(str(i) for i in range(900))))

    def test_tool_loop(self):
        same = ('exec', '{"cmd": "ls  -la"}', 'out')
        self.assertEqual(ls.tool_loops([same, ('exec', '{"cmd": "ls -la"}', 'out'), same]), 1)
        self.assertEqual(ls.tool_loops([same, same, ('exec', '{"cmd":"ls"}', 'x'), same, same]), 0)
        self.assertEqual(ls.tool_loops([same, same, ('exec', 'a', 'o'), same, same, same]), 1)

    def test_reply_lines(self):
        self.assertTrue(ls.repeated_lines('\n'.join(['Checking the file again'] * 5)))
        self.assertFalse(ls.repeated_lines('\n'.join(['Checking the file again'] * 4)))
        self.assertFalse(ls.repeated_lines('\n'.join(['ok', '---', '```'] * 9)))

    def test_summary_upper_bound(self):
        out = ls.summarize([{'requests': 50, 'G': 0, 'T': 0, 'R': 0}, {'requests': 50, 'G': 0, 'T': 1, 'R': 0}])
        self.assertEqual(out['G']['upper_95_per_100'], 3.0)
        self.assertEqual(out['T']['positive_sessions'], 1)
        self.assertNotIn('upper_95_per_100', out['T'])


if __name__ == '__main__':
    unittest.main()
