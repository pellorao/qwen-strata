"""Scoring contract v7: full replay, one alert threshold, group credit falling linearly with lateness."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.loop.loop_replay import LoopGroup, Observation, alert, replay


class Scripted:
    """Returns a fixed probability per record and records what it was shown."""
    def __init__(self, scores):
        self.scores, self.seen, self.resets = scores, [], []

    def reset(self, trace):
        self.resets.append(trace)

    def observe(self, observation):
        self.seen.append(observation)
        return self.scores.get(observation.id, 0.0)


def records(*ids, trace='t'):
    return [Observation(i, trace, {'text': i, 'label': 'loop', 'loop_annotations': ['g']}) for i in ids]


class ReplayTests(unittest.TestCase):
    def test_one_threshold(self):
        self.assertEqual([alert(p) for p in (0.51, 0.5, 0.49, True, False)], [True, True, False, True, False])
        with self.assertRaises(ValueError):
            alert(1.2)

    def test_everything_is_replayed_and_answers_are_hidden(self):
        detector = Scripted({'b': 0.9})
        replay(records('a', 'b', 'n', 'c'), [LoopGroup('g', 't', ('a', 'b', 'c'))], detector, 2)
        self.assertEqual([o.id for o in detector.seen], ['a', 'b', 'n', 'c'])
        self.assertTrue(all(set(o.payload) == {'text'} for o in detector.seen))
        self.assertEqual(detector.resets, ['t'])

    def test_first_alert_and_following_alerts_each_earn_half_falling_linearly(self):
        group = LoopGroup('g', 't', ('a', 'b', 'c', 'd'))
        obs = records('a', 'b', 'n', 'c', 'd')
        credit = lambda alerts, k: replay(obs, [group], Scripted(dict.fromkeys(alerts, 1.0)), k)['credit']['g']
        # k = 2 owes b, c and d (first alert 1, 2/3, 1/3; following weights 3/6, 2/6, 1/6)
        for alerts, expected in ((['b'], 0.75), (['c'], 0.5), (['d'], 0.25), ([], 0), (['b', 'c', 'd'], 1),
                                 (['c', 'd'], 1 / 3 + 0.25)):
            self.assertAlmostEqual(credit(alerts, 2), expected)
        # a k = 3 rule owes c and d; an alert at b is not late but owes nothing after it
        for alerts, expected in ((['c'], 0.5 + 1 / 3), (['b'], 0.5), (['d'], 0.25 + 1 / 6), (['c', 'd'], 1)):
            self.assertAlmostEqual(credit(alerts, 3), expected)

    def test_precision_counts_alerts_on_repeats_and_originals_are_not_scored(self):
        group = LoopGroup('g', 't', ('a', 'b', 'c'))
        result = replay(records('a', 'b', 'c', 'n1', 'n2'), [group], Scripted({'a': 1, 'b': 1, 'c': 1, 'n1': 1}), 2)
        self.assertEqual((result['alerts'], result['justified_alerts'], result['fp']), (4, 2, 1))
        self.assertAlmostEqual(result['precision'], 2 / 3)
        self.assertEqual((result['recall'], result['original_only_records'], result['negatives']), (1, 1, 2))

    def test_short_group_is_unreachable_for_a_larger_k(self):
        result = replay(records('a', 'b', 'n'), [LoopGroup('g', 't', ('a', 'b'))], Scripted({'b': 0.9}), 3)
        self.assertEqual((result['recall'], result['fp'], result['unreachable_groups']), (0, 0, ['g']))
        self.assertEqual(result['justified_alerts'], 1)

    def test_single_response_group_has_one_detection_point_with_its_companions(self):
        group = LoopGroup('s', 't', (('a', 'b'), 'a', 'a'), mode='single_response')
        self.assertEqual(replay(records('a', 'b', 'n'), [group], Scripted({'b': 1.0}), 2)['recall'], 1)
        short = replay(records('a', 'b'), [group], Scripted({'a': 1.0}), 2, k_inside=4)
        self.assertEqual((short['recall'], short['unreachable_groups']), (0, ['s']))
        with self.assertRaises(ValueError):
            replay(records('a', 'b'), [LoopGroup('s', 't', ('a', 'b'), mode='single_response')], Scripted({}), 2)

    def test_repeats_inside_one_record_take_its_latest_occurrence(self):
        group = LoopGroup('g', 't', ('a', 'a', 'a', 'b'))
        self.assertAlmostEqual(replay(records('a', 'b'), [group], Scripted({'a': 0.9}), 3)['credit']['g'], 0.5 + 1 / 3)

    def test_an_occurrence_spanning_records_is_one_step(self):
        # o2 is a repeated reasoning step r2 and the call t2 it leads to; an alert at either is on time
        group = LoopGroup('g', 't', (('t1', 'r1'), ('t2', 'r2'), 't3'))
        obs = records('r1', 't1', 'r2', 't2', 't3')
        self.assertAlmostEqual(replay(obs, [group], Scripted({'t2': 0.9}), 2)['credit']['g'], 0.5 + 1 / 3)
        self.assertAlmostEqual(replay(obs, [group], Scripted({'t3': 0.9}), 2)['credit']['g'], 0.25 + 1 / 6)

    def test_overlapping_groups_score_separately_with_one_alert(self):
        groups = [LoopGroup('g', 't', ('a', 'c')), LoopGroup('h', 't', ('b', 'c'))]
        result = replay(records('a', 'b', 'c'), groups, Scripted({'c': 0.9}), 2)
        self.assertEqual((result['recall'], result['fp'], result['negatives']), (1, 0, 0))  # each owes one step

    def test_unjudged_records_are_observed_but_not_scored_and_traces_reset(self):
        obs = [Observation('x', 't', {}, judged=False), *records('a', 'b'), *records('n', trace='u')]
        detector = Scripted({'x': 0.9, 'n': 0.9})
        result = replay(obs, [LoopGroup('g', 't', ('a', 'b'))], detector, 2)
        self.assertEqual(result['false_alarms'], ['n'])
        self.assertEqual(detector.resets, ['t', 'u'])
        with self.assertRaises(ValueError):
            replay(obs, [LoopGroup('g', 't', ('x', 'a'))], Scripted({}), 2)

    def test_gate_is_f2_at_least_point_eight(self):
        groups = [LoopGroup('g', 't', ('a', 'b')), LoopGroup('h', 't', ('c', 'd', 'e'))]
        obs = records('a', 'b', 'c', 'd', 'e', 'n1', 'n2')
        one = replay(obs, groups, Scripted({'b': 1, 'e': 1, 'n1': 1}), 2)
        self.assertAlmostEqual(one['recall'], (1 + 0.25 + 1 / 6) / 2)
        self.assertAlmostEqual(one['precision'], 2 / 3)
        self.assertFalse(one['passes_gate'])
        two = replay(obs, groups, Scripted({'b': 1, 'd': 1, 'e': 1, 'n1': 1}), 2)
        self.assertEqual((two['recall'], two['precision']), (1, 0.75))
        self.assertAlmostEqual(two['f2'], 5 * 0.75 / (4 * 0.75 + 1))
        self.assertTrue(two['passes_gate'])

if __name__ == '__main__':
    unittest.main()
