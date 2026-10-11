from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.reviewer.single_scenario_score import summarize


def instance(scenario, score, repetition=1):
    return {'instanceId': f'{scenario}-{repetition}', 'scenarioId': scenario, 'repetition': repetition, 'score': score,
            'cleanAcceptanceRate': 1, 'problemDetectionRate': score}


class SingleScenarioTests(unittest.TestCase):
    def test_one_scenario_is_reported_unfused(self):
        upstream = {'status': 'diagnostic', 'reviewerIds': ['spec-readiness-reviewer'], 'results': [
            {'instances': [instance('artifact-promotion', 0.6), instance('artifact-promotion', 0.8, 2)]}]}
        result = summarize(upstream)
        self.assertEqual((result['status'], result['fused'], result['scenarioId']),
                         ('diagnostic-single-scenario', False, 'artifact-promotion'))
        self.assertAlmostEqual(result['mean_score'], 0.7)

    def test_mixed_scenarios_need_the_fused_upstream_score(self):
        upstream = {'results': [{'instances': [instance('artifact-promotion', 0.6), instance('runtime-migration', 0.8)]}]}
        with self.assertRaisesRegex(ValueError, 'exactly one scenario'):
            summarize(upstream)


if __name__ == '__main__':
    unittest.main()
