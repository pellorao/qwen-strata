"""Spec Readiness v4.3: the requirements and full-review scenarios never score the same case
(user 2026-10-16/17). Runs the ARW regression test that the v4.3 patch adds, on the frozen v4.3
source with the scenario patches only (the project scoring upgrade changes the expected scores of
that ARW test, so it is left out here)."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from tools.reviewer import freeze_arw_source

SNAPSHOTS = Path(__file__).resolve().parents[1] / 'benchmarks/reviewer-suite-v1/source-snapshots/current'


class SpecReadinessSplitTests(unittest.TestCase):
    def test_full_review_keeps_only_no_other_of_the_requirement_checks(self):
        manifest = json.loads((SNAPSHOTS / 'manifest-spec-readiness-v4.3.json').read_text())
        self.assertEqual(manifest['patches'][-1]['file'], '../../arw-patches/spec-readiness-v4.3.patch')
        with tempfile.TemporaryDirectory() as directory:
            arw = Path(directory) / 'arw'
            with mock.patch.object(freeze_arw_source, 'upgrade_scoring'):
                freeze_arw_source.materialize(manifest, SNAPSHOTS / manifest['snapshot']['file'], arw)
            run = subprocess.run(['node', '--test', '--test-name-pattern=public preparation pairs complete',
                                  'tests/release/reviewer-capability-conformance.test.mjs'],
                                 cwd=arw, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout[-2000:] + run.stderr[-2000:])
            self.assertIn('# pass 1', run.stdout.replace('ℹ', '#'))


if __name__ == '__main__':
    unittest.main()
