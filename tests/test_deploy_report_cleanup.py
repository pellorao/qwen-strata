from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tools.ops.deploy_wsl as deploy_wsl


class ReportCleanupTests(unittest.TestCase):
    def test_documentation_deployment_backs_up_retired_details_and_preserves_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            install, source = folder / 'install', folder / 'source'
            runtime = install / 'runtime/Strata/.venv/Scripts/python.exe'
            runtime.parent.mkdir(parents=True)
            runtime.write_bytes(b'unchanged runtime')
            release = install / 'config/installed-release.json'
            release.parent.mkdir()
            release.write_text('{}')
            source.mkdir()
            (source / 'summary.md').write_text('completed summary')
            retired = install / 'reports/v0.1.38/code-review-fixture/src/fixture.mjs'
            retired.parent.mkdir(parents=True)
            retired.write_bytes(b'old measurement input')
            unrelated = install / 'reports/v0.1.38/controller.md'
            unrelated.write_text('completed summary belongs in the maintenance project')
            with patch.object(deploy_wsl, 'ROOT', source), patch.object(deploy_wsl, 'FILES',
                    {'README.md': 'summary.md'}), patch.object(deploy_wsl, 'OBSOLETE', ()):
                result = deploy_wsl.deploy_locked(install, docs_only=True)
            self.assertFalse(retired.exists())
            self.assertFalse((install / 'reports/v0.1.38/code-review-fixture').exists())
            self.assertEqual((Path(result['backup']) / retired.relative_to(install)).read_bytes(),
                b'old measurement input')
            self.assertEqual(runtime.read_bytes(), b'unchanged runtime')
            self.assertFalse(unrelated.exists())
            self.assertEqual((Path(result['backup'])/unrelated.relative_to(install)).read_text(),
                             'completed summary belongs in the maintenance project')
            self.assertFalse(result['client_catalog_modified'])
            self.assertTrue(Path(result['backup']).is_relative_to(source/'.tmp/maintenance-backups'))
            self.assertFalse((install/'.tmp').exists())

    def test_failed_deployment_restores_bytes_from_project_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);install=root/'install';source=root/'project'
            python=install/'runtime/Strata/.venv/Scripts/python.exe'
            python.parent.mkdir(parents=True);python.write_bytes(b'unchanged runtime')
            release=install/'config/installed-release.json';release.parent.mkdir();release.write_text('{}')
            source.mkdir();(source/'caller.md').write_text('new caller guide')
            (install/'README.md').write_text('original caller guide')
            original=deploy_wsl.os.replace
            def fail_install(stage,target):
                if target == install/'README.md':raise OSError('Injected deployment write failure')
                original(stage,target)
            with patch.object(deploy_wsl,'ROOT',source),patch.object(deploy_wsl,'FILES',{'README.md':'caller.md'}),\
                    patch.object(deploy_wsl,'OBSOLETE',()),patch.object(deploy_wsl.os,'replace',side_effect=fail_install):
                with self.assertRaisesRegex(OSError,'Injected deployment'):
                    deploy_wsl.deploy_locked(install,docs_only=True)
            self.assertEqual((install/'README.md').read_text(),'original caller guide')
            self.assertFalse((install/'.tmp').exists())
            backups=list((source/'.tmp/maintenance-backups').glob('wsl-deploy-*'))
            self.assertEqual(len(backups),1)
            self.assertEqual((backups[0]/'README.md').read_text(),'original caller guide')

    def test_cleanup_inventory_removes_all_installation_reports_and_ignores_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            install = Path(directory)
            names = ['reports/v0.1.38/code-review.json',
                'reports/v0.1.38/code-review.md',
                'reports/v0.1.38/code-review-expected.json',
                'benchmarks/code-standards-v1/expected.json',
                'runtime/Strata/benchmarks/code-standards-v1/expected.json']
            for name in names:
                p = install / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('preserve or remove by exact location')
            removed = set(deploy_wsl.obsolete_entries(install, docs_only=True))
            self.assertIn(names[2], removed)
            self.assertIn(names[3], removed)
            for name in (names[0], names[1]):
                self.assertIn(name, removed)
            self.assertNotIn(names[4], removed)

    def test_service_deployment_never_reinstalls_maintenance_artifacts(self):
        self.assertEqual(deploy_wsl.FILES['README.md'], 'docs/installation-directory-readme.md')
        for target in deploy_wsl.FILES:
            self.assertFalse(target.startswith(('docs/','reports/','benchmarks/','tools/','tests/')), target)
        for name in ('windows_host.py','wsl_launcher.py','controller_backend.py','brave_search.py'):
            self.assertIn('src/'+name, deploy_wsl.FILES)


if __name__ == '__main__':
    unittest.main()
