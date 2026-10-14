"""The project's ARW scoring upgrade: evidence F2 instead of F3 (user 2026-10-14)."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.reviewer.freeze_arw_source import PATCHES, SCORING_UPGRADE, git_apply, materialize, upgrade_scoring

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = ROOT / 'benchmarks/reviewer-suite-v1/source-snapshots/current'
CONFORMANCE = 'lib/release/reviewer-capability-conformance.mjs'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ScoringUpgradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.arw = Path(cls.tmp.name) / 'arw'
        manifest = json.loads((SNAPSHOTS / 'manifest-code-spec-v5.json').read_text())
        materialize(manifest, SNAPSHOTS / manifest['snapshot']['file'], cls.arw)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_materialized_copy_scores_evidence_with_f2(self):
        source = (self.arw / 'lib/release/reviewer-capability-scoring.mjs').read_text()
        self.assertIn('fBetaScore({beta: 2, precision, recall: coverage})', source)
        self.assertNotIn('beta: 3', source)
        self.assertEqual(upgrade_scoring(self.arw), {'applied': False, 'migrated_from': None})

    def test_copies_left_by_superseded_drafts_migrate(self):
        conformance = digest(self.arw / CONFORMANCE)
        for name, _ in SCORING_UPGRADE['superseded'].values():
            with self.subTest(name):
                git_apply(PATCHES / SCORING_UPGRADE['file'], self.arw, '--reverse')
                git_apply(PATCHES / name, self.arw)
                (self.arw / 'reviewer-pairs').mkdir()
                self.assertNotEqual(digest(self.arw / CONFORMANCE), conformance)
                self.assertEqual(upgrade_scoring(self.arw), {'applied': True, 'migrated_from': name})
                self.assertEqual(digest(self.arw / CONFORMANCE), conformance)
                self.assertFalse((self.arw / 'reviewer-pairs').exists())
                for member, (_, upgraded) in SCORING_UPGRADE['members'].items():
                    self.assertEqual(digest(self.arw / member), upgraded, member)


if __name__ == '__main__':
    unittest.main()
