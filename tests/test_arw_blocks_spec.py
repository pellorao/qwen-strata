import json
import tempfile
import unittest
from pathlib import Path

from tools.reviewer.arw_measure import spec_repetition_order
from tools.tuning import arw_blocks


def job(preparation, scenario, number):
    return ({'preparedPath': preparation}, {'scenarioId': scenario, 'instanceId': f'{scenario}-{preparation}-instance-{number}'}, None)


class SpecBlockTests(unittest.TestCase):
    def test_repetitions_of_two_preparations_pair_within_their_preparation(self):
        jobs = [job(p, s, n) for p in ('p1', 'p2') for s in ('runtime-migration', 'artifact-promotion') for n in (1, 2)]
        order = [(h['instanceId']) for _, h, _ in spec_repetition_order(jobs)]
        self.assertEqual(order, [f'{s}-{p}-instance-{n}' for p in ('p1', 'p2') for n in (1, 2)
                                 for s in ('runtime-migration', 'artifact-promotion')])

    def test_result_root_for_spec_readiness_and_single_scenarios(self):
        self.assertEqual(arw_blocks.result_root({'instanceId': 'artifact-promotion-u-1-instance-3'}), 'u-1/sr/artifact-promotion/3')
        self.assertEqual(arw_blocks.result_root({'instanceId': 'default-u-instance-2'}), 'u/csp/2')

    def test_layout_groups_a_repetition_and_keeps_both_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            results = []
            for n in (1, 2):
                for s in ('runtime-migration', 'artifact-promotion'):
                    report = tmp / f'{s}{n}' / 'review-result.md'
                    report.parent.mkdir()
                    report.write_text(f'{s} {n}')
                    results.append({'instanceId': f'{s}-u-instance-{n}', 'report': str(report)})
            folder = tmp / 'block'
            folder.mkdir()
            arw_blocks.layout(tmp / 'out', folder, {'condition': 'c', 'warmup': 1, 'round': 1}, results, {}, 2)
            scene = tmp / 'out/scenes/c'
            self.assertEqual([p.name for p in scene.glob('codex-strata-high-a*')], ['codex-strata-high-a1'])
            instance = scene / 'codex-strata-high-a1'
            self.assertEqual([r['instanceId'] for r in json.loads((instance / 'run/results.json').read_text())],
                             ['runtime-migration-u-instance-2', 'artifact-promotion-u-instance-2'])
            self.assertEqual(sorted(p.name for p in (instance / 'report').iterdir()),
                             ['artifact-promotion--review-result.md', 'runtime-migration--review-result.md'])


if __name__ == '__main__':
    unittest.main()
