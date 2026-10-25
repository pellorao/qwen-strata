import json
import tempfile
import unittest
from pathlib import Path

from tools.reviewer import bench_bindings, bench_suite


class DifferencesTest(unittest.TestCase):
    def test_equal_changed_and_added(self):
        recorded = {'files': {'a': '1' * 64, 'b': '2' * 64}, 'prompts': {'x': 1}}
        self.assertEqual(bench_bindings.differences(recorded, recorded), [])
        actual = {'files': {'a': '1' * 64, 'b': '3' * 64, 'c': '4' * 64}, 'prompts': {'x': 2}}
        lines = bench_bindings.differences(recorded, actual)
        self.assertEqual(len(lines), 3)
        self.assertTrue(any(line.startswith('files b:') for line in lines))
        self.assertTrue(any(line.startswith('files c:') for line in lines))
        self.assertTrue(any(line.startswith('prompts:') for line in lines))

    def test_removed_file_is_a_difference(self):
        lines = bench_bindings.differences({'files': {'a': '1' * 64, 'b': '2' * 64}}, {'files': {'a': '1' * 64}})
        self.assertEqual(len(lines), 1)

    def test_section_not_recomputed_is_skipped(self):
        self.assertEqual(bench_bindings.differences({'roles': {'x': 1}}, {'files': {}}), [])


class CollectFilesTest(unittest.TestCase):
    def test_v2_files_and_consistency(self):
        problems = []
        files = bench_bindings.collect_files('v2', problems)
        self.assertEqual(problems, [])
        for scenario in bench_suite.suite('v2')['scenarios']:
            self.assertIn(bench_suite.plan_path('v2', scenario).relative_to(bench_bindings.ROOT).as_posix(), files)
            self.assertIn(bench_suite.brief_path('v2', scenario).relative_to(bench_bindings.ROOT).as_posix(), files)
        self.assertIn('benchmarks/multi-model-v2/arw-patches/scoring-r8.5.patch', files)
        self.assertTrue(all(len(v) == 64 for v in files.values()))

    def test_plan_claiming_a_wrong_sha_is_reported(self):
        plan = json.loads(bench_suite.plan_path('v2', 'code-spec-v5.1').read_text())
        plan['fixed_conditions']['arw_source_manifest_sha256'] = '0' * 64
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'plan.json'
            path.write_text(json.dumps(plan))
            problems = []
            bench_bindings.plan_files(path, problems)
        self.assertTrue(any('manifest sha256 00000000' in p for p in problems), problems)


if __name__ == '__main__':
    unittest.main()
