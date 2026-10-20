import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.reviewer.freeze_arw_source import HARNESS_PATCHES, apply_harness_patch, materialize

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = ROOT / 'benchmarks/reviewer-suite-v1/source-snapshots/current'


class HarnessPatchTest(unittest.TestCase):
    def test_mount_target_patch_applies_to_every_current_scenario_source(self):
        # The scenario versions the multi-model benchmark binds; all share the patched Reviewer runtime.
        for name in ('commit-audit-v3', 'code-spec-v5', 'code-standards-v5.1', 'spec-readiness-v4.3'):
            manifest = json.loads((MANIFESTS / f'manifest-{name}.json').read_text())
            (ROOT / '.tmp').mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(dir=ROOT / '.tmp', prefix='harness-patch-') as tmp:
                arw = Path(tmp) / 'arw'
                materialize(manifest, MANIFESTS / manifest['snapshot']['file'], arw)
                applied = apply_harness_patch('codex-0.163-synthetic-mount-targets', arw)
                self.assertEqual(applied['result'], HARNESS_PATCHES['codex-0.163-synthetic-mount-targets']['result'])
                with self.assertRaises(ValueError):  # a second application meets a changed base
                    apply_harness_patch('codex-0.163-synthetic-mount-targets', arw)

    def test_time_limit_patch_applies_with_the_mount_patch_and_its_node_test_passes(self):
        name = 'strata-measurement-time-limit'
        for scenario in ('commit-audit-v3', 'code-spec-v5', 'code-standards-v5.1', 'spec-readiness-v4.3'):
            manifest = json.loads((MANIFESTS / f'manifest-{scenario}.json').read_text())
            (ROOT / '.tmp').mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(dir=ROOT / '.tmp', prefix='harness-patch-') as tmp:
                arw = Path(tmp) / 'arw'
                materialize(manifest, MANIFESTS / manifest['snapshot']['file'], arw)
                apply_harness_patch('codex-0.163-synthetic-mount-targets', arw)
                applied = apply_harness_patch(name, arw)
                self.assertEqual(applied['result'], HARNESS_PATCHES[name]['result'])
                with self.assertRaises(ValueError):
                    apply_harness_patch(name, arw)
                if scenario == 'commit-audit-v3' and shutil.which('node'):
                    done = subprocess.run(['node', '--test', 'tests/background-agent/strata-time-limit.test.mjs'], cwd=arw,
                                          capture_output=True, text=True)
                    self.assertEqual(done.returncode, 0, done.stdout[-2000:])


if __name__ == '__main__':
    unittest.main()
