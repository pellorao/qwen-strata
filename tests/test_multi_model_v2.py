"""Multi-model benchmark v2 draft: scenario patches over the frozen v1 scenarios and the draft briefs."""
import json
from pathlib import Path
import tempfile
import unittest

from tools.reviewer import check_briefs
from tools.reviewer.freeze_arw_source import materialize

ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / 'benchmarks/reviewer-suite-v1/source-snapshots/current'
V2 = ROOT / 'benchmarks/multi-model-v2/scenarios'
FIXTURES = Path('tests/fixtures/reviewer-capability')
# v2 version -> (v1 version, reviewer)
VERSIONS = {'code-spec-v5.1': ('code-spec-v5', 'code-spec-reviewer'),
            'commit-audit-v3.1': ('commit-audit-v3', 'commit-audit-reviewer'),
            'spec-readiness-v4.5': ('spec-readiness-v4.3', 'spec-readiness-reviewer')}


def build(manifest_path, destination):
    manifest = json.loads(manifest_path.read_text())
    materialize(manifest, manifest_path.parent / manifest['snapshot']['file'], destination)
    return manifest


def files(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


class MultiModelV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.work = Path(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_v2_patch_only_rewords_lines_and_keeps_the_answer_key(self):
        """The v2 scenario = the frozen v1 manifest plus the v2 patches (SR v4.5 stacks on v4.4); each changed file keeps
        its line count and the answer key stays byte for byte the same, so the k registry, the format baseline and the
        brief citations bind."""
        for new, (old, reviewer) in VERSIONS.items():
            with self.subTest(new):
                v1 = json.loads((V1 / f'manifest-{old}.json').read_text())
                v2 = build(V2 / f'manifest-{new}.json', self.work / new)
                v2_patches = v2['patches'][len(v1['patches']):]
                self.assertEqual(v2['patches'][:len(v1['patches'])], v1['patches'])
                self.assertTrue(v2_patches)
                self.assertEqual({k: v for k, v in v2['snapshot'].items() if k != 'file'},
                                 {k: v for k, v in v1['snapshot'].items() if k != 'file'})
                build(V1 / f'manifest-{old}.json', self.work / old)
                before, after = files(self.work / old / FIXTURES / reviewer), files(self.work / new / FIXTURES / reviewer)
                self.assertEqual(before.keys(), after.keys())
                changed = sorted(name for name in before if before[name] != after[name])
                self.assertEqual(changed, sorted(Path(name).relative_to(FIXTURES / reviewer).as_posix()
                                                 for name in {n for entry in v2_patches for n in entry['result']}))
                self.assertNotIn('expected.json', changed)
                for name in changed:
                    self.assertEqual(before[name].count(b'\n'), after[name].count(b'\n'), name)

    def test_v2_briefs_pass_the_mechanical_check(self):
        results = check_briefs.check(self.work / 'briefs', 'v2')
        self.assertTrue(results)
        self.assertEqual([message for ok, message in results if not ok], [])
        self.assertIn('v2: common paragraph identical in all briefs', [message for _, message in results])


if __name__ == '__main__':
    unittest.main()
