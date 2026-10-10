"""Scoring contract v3: full replay, probability thresholds, rule-relative first target and weights."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.loop.loop_replay import LoopGroup, Observation, replay, verdict


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
    def test_thresholds_and_uncertain_band(self):
        self.assertEqual([verdict(p) for p in (0.61, 0.6, 0.5, 0.4, 0.39, True, False)],
                         ['positive', 'uncertain', 'uncertain', 'uncertain', 'negative', 'positive', 'negative'])
        with self.assertRaises(ValueError):
            verdict(1.2)

    def test_everything_is_replayed_and_answers_are_hidden(self):
        detector = Scripted({'b': 0.9})
        replay(records('a', 'b', 'n', 'c'), [LoopGroup('g', 't', ('a', 'b', 'c'))], detector, 2)
        self.assertEqual([o.id for o in detector.seen], ['a', 'b', 'n', 'c'])
        self.assertTrue(all(set(o.payload) == {'text'} for o in detector.seen))
        self.assertEqual(detector.resets, ['t'])

    def test_first_target_follows_the_rule_and_later_records_share_half(self):
        group = LoopGroup('g', 't', ('a', 'b', 'c', 'd'))
        obs = records('a', 'b', 'n', 'c', 'd')
        two = replay(obs, [group], Scripted({'b': 0.9, 'c': 0.9, 'd': 0.9}), 2)
        self.assertEqual((two['tp'], two['fn'], two['fp']), (1.5, 0.0, 0.0))
        self.assertEqual(two['f1'], 1.0)
        # a k = 3 rule owes its first alert at c; b is neutral, a later miss at d costs only 0.5
        three = replay(obs, [group], Scripted({'b': 0.9, 'c': 0.9}), 3)
        self.assertEqual((three['tp'], three['fn'], three['fp'], three['neutral_records']), (1.0, 0.5, 0.0, 2))
        self.assertEqual(three['first_hits'], 1)

    def test_missing_the_first_costs_more_than_missing_later(self):
        group = LoopGroup('g', 't', ('a', 'b', 'c', 'd'))
        late = replay(records('a', 'b', 'c', 'd'), [group], Scripted({'c': 0.9, 'd': 0.9}), 2)
        self.assertEqual((late['tp'], late['fn']), (0.5, 1.0))
        self.assertEqual(late['group_recall'], 0.0)

    def test_uncertain_counts_as_wrong_on_both_sides(self):
        result = replay(records('a', 'b', 'n'), [LoopGroup('g', 't', ('a', 'b'))], Scripted({'b': 0.5, 'n': 0.45}), 2)
        self.assertEqual((result['tp'], result['fn'], result['fp']), (0.0, 1.0, 1.0))
        self.assertEqual((result['uncertain_positive_records'], result['uncertain_negative_records']), (1, 1))
        self.assertEqual(result['false_alarms'], ['n'])

    def test_short_group_is_unreachable_for_a_larger_k(self):
        result = replay(records('a', 'b', 'n'), [LoopGroup('g', 't', ('a', 'b'))], Scripted({'b': 0.9}), 3)
        self.assertEqual((result['tp'], result['fn'], result['fp']), (0.0, 1.0, 0.0))
        self.assertEqual(result['unreachable_groups'], ['g'])

    def test_single_response_group_has_one_detection_point(self):
        group = LoopGroup('s', 't', ('a', 'a', 'a'), mode='single_response')
        result = replay(records('a', 'n'), [group], Scripted({'a': 1.0}), 3)
        self.assertEqual((result['tp'], result['fn'], result['fp']), (1.0, 0.0, 0.0))
        with self.assertRaises(ValueError):
            replay(records('a', 'b'), [LoopGroup('s', 't', ('a', 'b'), mode='single_response')], Scripted({}), 2)

    def test_repeats_inside_the_first_record_put_the_target_there(self):
        group = LoopGroup('g', 't', ('a', 'a', 'a', 'b'))
        result = replay(records('a', 'b'), [group], Scripted({'a': 0.9}), 3)
        self.assertEqual((result['tp'], result['fn']), (1.0, 0.5))

    def test_an_occurrence_spanning_records_owes_its_earliest_record(self):
        # o2 is a repeated reasoning step r2 and the call t2 it leads to; o1's companion r1 stays neutral
        group = LoopGroup('g', 't', (('t1', 'r1'), ('t2', 'r2'), 't3'))
        obs = records('r1', 't1', 'r2', 't2', 't3')
        result = replay(obs, [group], Scripted({'r2': 0.9, 't3': 0.9}), 2)
        self.assertEqual((result['tp'], result['fn'], result['fp'], result['neutral_records']), (1.25, 0.25, 0.0, 2))
        self.assertEqual(result['first_hits'], 1)
        side = LoopGroup('s', 't', (('a', 'b'), 'a'), mode='single_response')
        result = replay(records('a', 'b'), [side], Scripted({'a': 0.9, 'b': 0.9}), 2)
        self.assertEqual((result['tp'], result['fn']), (1.5, 0.0))

    def test_overlapping_groups_score_separately_with_one_verdict(self):
        groups = [LoopGroup('g', 't', ('a', 'c')), LoopGroup('h', 't', ('b', 'c'))]
        result = replay(records('a', 'b', 'c'), groups, Scripted({'c': 0.9}), 2)
        self.assertEqual((result['tp'], result['fp'], result['negatives']), (2.0, 0.0, 0))

    def test_unjudged_records_are_observed_but_not_scored_and_traces_reset(self):
        obs = [Observation('x', 't', {}, judged=False), *records('a', 'b'), *records('n', trace='u')]
        detector = Scripted({'x': 0.9, 'n': 0.9})
        result = replay(obs, [LoopGroup('g', 't', ('a', 'b'))], detector, 2)
        self.assertEqual(result['false_alarms'], ['n'])
        self.assertEqual(detector.resets, ['t', 'u'])
        with self.assertRaises(ValueError):
            replay(obs, [LoopGroup('g', 't', ('x', 'a'))], Scripted({}), 2)

    def test_gate_is_weighted_f1_at_least_point_eight(self):
        group = LoopGroup('g', 't', ('a', 'b', 'c'))
        result = replay(records('a', 'b', 'c', 'n1', 'n2'), [group], Scripted({'b': 0.9, 'c': 0.9, 'n1': 0.9}), 2)
        self.assertAlmostEqual(result['f1'], 0.75)
        self.assertFalse(result['passes_gate'])


if __name__ == '__main__':
    unittest.main()
