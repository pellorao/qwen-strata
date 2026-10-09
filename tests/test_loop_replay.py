"""Intervention replay preserves timing errors, normal logs and independent runs."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.loop.loop_replay import Alert, LoopEpisode, Observation, replay
from tools.loop.loop_reminders import reminder_text


class ScriptedDetector:
    def __init__(self, alerts):
        self.alerts = alerts
        self.seen = []
        self.resets = []

    def observe(self, observation):
        self.seen.append(observation.id)
        return self.alerts.get(observation.id, [])

    def reset(self, trace_id):
        self.resets.append(trace_id)


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.units = [Observation(key, 'root', {'text': key}) for key in ['a1', 'a2', 'a3', 'a4', 'normal']]
        self.episode = LoopEpisode('loop', 'root', ('a1', 'a2', 'a3', 'a4'), 'normal', {'two': 'a2', 'three': 'a3'})

    def run_case(self, when, rule='three', evidence=None):
        detector = ScriptedDetector({when: [Alert(rule, evidence or ('a1', when))]})
        return replay(self.units, [self.episode], detector, [rule]), detector

    def test_on_time_skips_remaining_repeat_and_resumes_normal(self):
        result, detector = self.run_case('a3')
        self.assertEqual((result['tp'], result['fp'], result['fn'], result['f1']), (1, 0, 0, 1))
        self.assertEqual(detector.seen, ['a1', 'a2', 'a3', 'normal'])
        self.assertEqual(result['skips'][0]['skipped_observation_ids'], ['a4'])
        self.assertEqual(detector.resets, ['root', 'root'])

    def test_early_true_repeat_still_skips_but_keeps_fp_and_fn(self):
        result, detector = self.run_case('a2')
        self.assertEqual((result['tp'], result['fp'], result['fn']), (0, 1, 1))
        self.assertEqual(detector.seen, ['a1', 'a2', 'normal'])
        self.assertEqual(result['decisions'][0]['reason'], 'early')

    def test_late_true_repeat_is_not_relabelled_to_tp(self):
        result, detector = self.run_case('a4')
        self.assertEqual((result['tp'], result['fp'], result['fn'], result['f1']), (0, 1, 1, 0))
        self.assertIn('normal', detector.seen)

    def test_late_warning_skips_further_repeats_before_resuming_normal(self):
        units = self.units[:4] + [Observation('a5', 'root', {'text': 'repeat'})] + self.units[4:]
        episode = LoopEpisode('loop', 'root', ('a1', 'a2', 'a3', 'a4', 'a5'), 'normal', {'three': 'a3'})
        detector = ScriptedDetector({'a4': [Alert('three', ('a1', 'a4'))]})
        result = replay(units, [episode], detector, ['three'])
        self.assertEqual((result['tp'], result['fp'], result['fn']), (0, 1, 1))
        self.assertEqual(detector.seen, ['a1', 'a2', 'a3', 'a4', 'normal'])
        self.assertEqual(result['skips'][0]['skipped_observation_ids'], ['a5'])

    def test_different_rules_have_different_targets(self):
        two, _ = self.run_case('a2', 'two')
        three, _ = self.run_case('a3', 'three')
        self.assertEqual(two['f1'], 1)
        self.assertEqual(three['f1'], 1)

    def test_joint_replay_uses_earliest_target_and_does_not_hide_missed_target(self):
        detector = ScriptedDetector({'a3': [Alert('three', ('a1', 'a3'))]})
        result = replay(self.units, [self.episode], detector, ['two', 'three'])
        self.assertEqual((result['tp'], result['fp'], result['fn']), (0, 1, 1))

    def test_semantic_false_positive_does_not_skip_or_reset(self):
        result, detector = self.run_case('a2', evidence=('a1', 'foreign'))
        self.assertEqual(detector.seen, [o.id for o in self.units])
        self.assertEqual(result['skips'], [])
        self.assertEqual(detector.resets, ['root'])
        self.assertFalse(result['decisions'][0]['genuine_loop'])

    def test_future_witness_does_not_license_a_skip(self):
        result, detector = self.run_case('a2', evidence=('a1', 'a4'))
        self.assertEqual(result['skips'], [])
        self.assertEqual(detector.seen, [o.id for o in self.units])

    def test_previous_loop_is_late_without_rewinding_normal_logs(self):
        result, detector = self.run_case('normal', evidence=('a1', 'a3'))
        self.assertEqual(result['skips'], [])
        self.assertEqual(detector.seen.count('normal'), 1)
        self.assertTrue(result['decisions'][0]['genuine_loop'])

    def test_normal_interleaving_requires_corrected_group_boundary(self):
        bad = LoopEpisode('loop', 'root', ('a1', 'a3', 'a4'), 'normal', {'three': 'a3'})
        with self.assertRaisesRegex(ValueError, 'intervening normal'):
            replay(self.units, [bad], ScriptedDetector({}), ['three'])

    def test_end_of_trace_skip_preserves_the_next_trace(self):
        units = self.units[:4] + [Observation('next-trace', 'other', {'text': 'fresh'})]
        episode = LoopEpisode('loop', 'root', ('a1', 'a2', 'a3', 'a4'), None, {'three': 'a3'})
        detector = ScriptedDetector({'a3': [Alert('three', ('a1', 'a3'))]})
        replay(units, [episode], detector, ['three'])
        self.assertEqual(detector.seen, ['a1', 'a2', 'a3', 'next-trace'])

    def test_same_step_duplicate_alerts_are_not_two_true_positives(self):
        detector = ScriptedDetector({'a3': [Alert('three', ('a1', 'a3')), Alert('three', ('a2', 'a3'))]})
        result = replay(self.units, [self.episode], detector, ['three'])
        self.assertEqual((result['tp'], result['fp'], result['fn']), (1, 1, 0))

    def test_empty_positive_scope_is_not_a_perfect_score(self):
        result = replay([self.units[-1]], [], ScriptedDetector({}), ['three'])
        self.assertIsNone(result['f1'])

    def test_detector_never_receives_fixture_answers_or_mutates_future_runs(self):
        payload = {'text': 'actual text', 'label': 'loop', 'targets': {'three': 'now'},
                   'loop_annotations': ['hidden'], 'nested': {'value': 'original'}}
        unit = Observation('visible', 'root', payload)
        class MutatingDetector(ScriptedDetector):
            def observe(self, observation):
                assert 'label' not in observation.payload
                assert 'targets' not in observation.payload
                assert 'loop_annotations' not in observation.payload
                observation.payload['nested']['value'] = 'altered'
                return []
        replay([unit], [], MutatingDetector({}), ['three'])
        self.assertEqual(payload['nested']['value'], 'original')

    def test_independent_rules_do_not_share_skip_cursors(self):
        two, two_detector = self.run_case('a2', 'two')
        three, three_detector = self.run_case('a3', 'three')
        self.assertNotIn('a3', two_detector.seen)
        self.assertIn('a3', three_detector.seen)
        self.assertEqual((two['tp'], three['tp']), (1, 1))

    def internal_case(self):
        units = [Observation('response', 'root', {'text': 'aaa bbb aaa bbb aaa bbb'}),
                 Observation('after', 'root', {'text': 'new work'})]
        episode = LoopEpisode('inside', 'root', ('response',), 'after', {'internal': 'response'},
                              mode='single_response', text_spans=((0, 7), (8, 15), (16, 23)))
        return units, episode

    def test_internal_loop_has_one_point_without_third_versus_fourth_timing(self):
        units, episode = self.internal_case()
        alert = Alert('internal', ('response',), (('response', 0, 7), ('response', 16, 23)))
        detector = ScriptedDetector({'response': [alert]})
        result = replay(units, [episode], detector, ['internal'])
        self.assertEqual((result['tp'], result['fp'], result['fn']), (1, 0, 0))
        self.assertEqual(result['decisions'][0]['reason'], 'single-point-match')
        self.assertEqual(result['skips'], [])
        self.assertEqual(detector.seen, ['response', 'after'])

    def test_internal_detection_needs_two_independent_text_witnesses(self):
        units, episode = self.internal_case()
        alert = Alert('internal', ('response',), (('response', 0, 7), ('response', 1, 6)))
        result = replay(units, [episode], ScriptedDetector({'response': [alert]}), ['internal'])
        self.assertEqual((result['tp'], result['fp'], result['fn']), (0, 1, 1))

    def test_internal_content_misjudgment_is_a_false_positive(self):
        units, episode = self.internal_case()
        alert = Alert('internal', ('response',), (('response', 7, 8), ('response', 15, 16)))
        result = replay(units, [episode], ScriptedDetector({'response': [alert]}), ['internal'])
        self.assertEqual((result['tp'], result['fp'], result['fn']), (0, 1, 1))

    def test_multiple_internal_groups_share_availability_but_have_distinct_spans(self):
        units = [Observation('response', 'root', {'text': 'aaa aaa xxx xxx'}),
                 Observation('after', 'root', {'text': 'new work'})]
        episodes = [LoopEpisode('a', 'root', ('response',), 'after', {'internal': 'response'},
                               'single_response', ((0, 3), (4, 7))),
                    LoopEpisode('x', 'root', ('response',), 'after', {'internal': 'response'},
                               'single_response', ((8, 11), (12, 15)))]
        alerts = [Alert('internal', ('response',), (('response', 0, 3), ('response', 4, 7))),
                  Alert('internal', ('response',), (('response', 8, 11), ('response', 12, 15)))]
        result = replay(units, episodes, ScriptedDetector({'response': alerts}), ['internal'])
        self.assertEqual((result['tp'], result['fp'], result['fn']), (2, 0, 0))

    def test_internal_warning_cannot_skip_later_normal_output(self):
        units, episode = self.internal_case()
        bad = LoopEpisode(episode.id, episode.trace_id, episode.occurrences, None, episode.targets,
                          episode.mode, episode.text_spans)
        with self.assertRaisesRegex(ValueError, 'later normal'):
            replay(units, [bad], ScriptedDetector({}), ['internal'])

    def test_two_warning_texts_are_distinct_and_do_not_supply_case_answers(self):
        self.assertNotEqual(reminder_text('single_response'), reminder_text('cross_call'))
        self.assertIn('completed response', reminder_text('single_response'))
        self.assertIn('original task', reminder_text('single_response'))


if __name__ == '__main__':
    unittest.main()
