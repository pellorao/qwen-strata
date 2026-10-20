import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.reviewer import reviewer_scratch
from tools.reviewer.freeze_arw_source import apply_harness_patch, materialize

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = ROOT / 'benchmarks/reviewer-suite-v1/source-snapshots/current'


class ReviewerScratchTest(unittest.TestCase):
    def setUp(self):
        (ROOT / '.tmp').mkdir(exist_ok=True)
        self.tmp = Path(tempfile.mkdtemp(dir=ROOT / '.tmp', prefix='reviewer-scratch-'))
        self.addCleanup(shutil.rmtree, self.tmp)
        self.root = self.tmp / 'root'
        self.root.mkdir(mode=0o700)

    @unittest.skipUnless(shutil.which('node'), 'node is needed to run the patched ARW module')
    def test_the_path_matches_the_patched_arw(self):
        manifest = json.loads((MANIFESTS / 'manifest-commit-audit-v3.json').read_text())
        arw = self.tmp / 'arw'
        materialize(manifest, MANIFESTS / manifest['snapshot']['file'], arw)
        apply_harness_patch('reviewer-private-scratch', arw)
        cwd, reports = '/x/scenario', '/x/scenario/.tmp/a/reports'
        module = (arw / 'lib/reviewer-runtime/reviewer-scratch.mjs').as_uri()
        script = (f'import {{reviewerScratchPath}} from {json.dumps(module)};'
                  f'console.log(reviewerScratchPath({{cwd:{json.dumps(cwd)},writePaths:[{json.dumps(reports)}]}},'
                  f'{json.dumps(str(self.root))}))')
        out = subprocess.run(['node', '--input-type=module', '-e', script], capture_output=True, text=True, check=True)
        self.assertEqual(out.stdout.strip(), str(reviewer_scratch.scratch_path(cwd, [reports], self.root)))

    def test_default_root_and_override(self):
        self.assertEqual(reviewer_scratch.scratch_root({}), Path(f'/tmp/arw-reviewer-scratch-{os.getuid()}'))
        self.assertEqual(reviewer_scratch.scratch_root({reviewer_scratch.ROOT_VARIABLE: str(self.root)}), self.root)

    def test_a_run_removes_the_scratch_of_each_bound_reviewer(self):
        out = self.tmp / 'run'
        bound = []
        for name in ('a-instance-1', 'b-instance-1'):
            (out / name).mkdir(parents=True)
            binding = {'cwd': f'/x/{name}', 'writePaths': [f'/x/{name}/.tmp/reports'], 'reportPath': 'r'}
            (out / name / 'binding.json').write_text(json.dumps(binding))
            bound.append(reviewer_scratch.scratch_path(binding['cwd'], binding['writePaths'], self.root))
        bound[0].mkdir()
        (bound[0] / 'script.sh').write_text('x')
        other = self.root / ('f' * 32)
        other.mkdir()
        self.assertEqual(reviewer_scratch.run_scratches(out, self.root), bound)
        self.assertEqual(reviewer_scratch.remove_run(out, self.root), {str(bound[0]): True, str(bound[1]): False})
        self.assertFalse(bound[0].exists())
        self.assertTrue(other.exists())  # another Reviewer's scratch stays

    def test_remove_refuses_paths_outside_the_root_and_links(self):
        with self.assertRaises(ValueError):
            reviewer_scratch.remove(self.tmp / 'elsewhere', self.root)
        target = self.tmp / 'target'
        target.mkdir()
        link = self.root / ('e' * 32)
        link.symlink_to(target)
        with self.assertRaises(ValueError):
            reviewer_scratch.remove(link, self.root)
        self.assertTrue(target.exists())


if __name__ == '__main__':
    unittest.main()
