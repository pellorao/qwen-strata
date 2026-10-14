import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tools.ops.upgrade_release as upgrade_release


class UpgradeTests(unittest.TestCase):
    def test_hotfix_reuses_identical_official_engine_without_rewriting_it(self):
        prior=json.loads(json.dumps(self.metadata['release']))
        self.metadata['release']['tag_name']='v0.1.38.1'
        self.metadata['reused_engine_release']=prior
        target=self.root/'runtime/Strata/engine';target.mkdir()
        with zipfile.ZipFile(self.engine) as z:
            for name in z.namelist():(target/name).write_bytes(z.read(name))
        result=upgrade_release.upgrade(self.root,self.metadata,self.source,self.engine)
        self.assertEqual(result['version'],'0.1.38.1')
        self.assertEqual(result['engine_build']['version'],'0.1.38')
        self.assertTrue(result['installed_engine_unchanged'])
        self.assertFalse(any(k.startswith('runtime/Strata/engine/') for k in result['written_sha256']))

    def test_hotfix_reuse_rejects_different_asset_before_writing(self):
        prior=json.loads(json.dumps(self.metadata['release']))
        self.metadata['release']['tag_name']='v0.1.38.1'
        self.metadata['reused_engine_release']=prior
        prior['assets'][0]['digest']='sha256:'+'0'*64
        with self.assertRaisesRegex(RuntimeError,'identical official assets'):
            upgrade_release.upgrade(self.root,self.metadata,self.source,self.engine)
        self.assertFalse((self.project/'.tmp').exists())

    def test_tag_archive_is_accepted_only_when_its_comment_binds_the_commit(self):
        with zipfile.ZipFile(self.source) as old,zipfile.ZipFile(self.folder/'tag.zip','w') as new:
            for name in old.namelist():new.writestr(name.replace('Strata-fixed/','Strata-0.1.38/'),old.read(name))
        with self.assertRaisesRegex(RuntimeError,'Unexpected source archive entry'):
            upgrade_release.upgrade(self.root,self.metadata,self.folder/'tag.zip',self.engine)
        with zipfile.ZipFile(self.folder/'tag.zip','a') as z:z.comment=b'fixed'
        result=upgrade_release.upgrade(self.root,self.metadata,self.folder/'tag.zip',self.engine)
        self.assertEqual((self.root/'runtime/Strata/new.txt').read_text(),'new file')
        self.assertEqual(result['commit'],'fixed')

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.project=self.folder/'maintenance'
        self.root_patch=patch.object(upgrade_release,'ROOT',self.project)
        self.root_patch.start()
        self.root=self.folder/'installation';runtime=self.root/'runtime/Strata'
        runtime.mkdir(parents=True);(self.root/'config').mkdir()
        (runtime/'AGENTS.md').write_text('Instructions')
        (runtime/'requirements.txt').write_text('Dependencies')
        (runtime/'CMakeLists.txt').write_text('VERSION 0.1.37')
        (runtime/'changed.txt').write_text('old bytes')
        (self.root/'config/installed-release.json').write_text('{"version":"0.1.37"}')
        self.source=self.folder/'source.zip';self.engine=self.folder/'engine.zip'
        with zipfile.ZipFile(self.source,'w') as z:
            for name,content in [('AGENTS.md','Instructions'),('requirements.txt','Dependencies'),
                ('CMakeLists.txt','VERSION 0.1.38'),('changed.txt','new bytes'),('new.txt','new file')]:
                z.writestr('Strata-fixed/'+name,content)
        with zipfile.ZipFile(self.engine,'w') as z:
            z.writestr('strata.exe','new engine');z.writestr('strata-vision.exe','new vision')
            z.writestr('BUILD.json',json.dumps({'version':'0.1.38','archs':[89]}))
        self.metadata={'commit':'fixed','release':{'tag_name':'v0.1.38','assets':[
            {'name':'strata-windows-x64.zip','size':self.engine.stat().st_size,
             'digest':'sha256:'+hashlib.sha256(self.engine.read_bytes()).hexdigest()}]}}

    def tearDown(self):
        self.root_patch.stop()
        self.temp.cleanup()

    def test_upgrade_and_explicit_rollback_use_project_backup(self):
        before={str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result=upgrade_release.upgrade(self.root,self.metadata,self.source,self.engine)
        backup=Path(result['backup'])
        self.assertTrue(backup.is_relative_to(self.project/'.tmp/maintenance-backups'))
        self.assertFalse((self.root/'.tmp').exists())
        self.assertEqual((self.root/'runtime/Strata/changed.txt').read_text(),'new bytes')
        self.assertEqual((backup/'files/runtime/Strata/changed.txt').read_text(),'old bytes')
        upgrade_release.rollback(self.root,backup)
        after={str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(after,before)

    def test_transaction_failure_restores_existing_bytes_and_removes_new_files(self):
        before={str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        original=upgrade_release.atomic;failed=False
        def fail_once(path,data):
            nonlocal failed
            if path==self.root/'config/installed-release.json' and not failed:
                failed=True;raise OSError('Injected late write failure')
            original(path,data)
        with patch.object(upgrade_release,'atomic',side_effect=fail_once):
            with self.assertRaisesRegex(OSError,'Injected late write failure'):
                upgrade_release.upgrade(self.root,self.metadata,self.source,self.engine)
        after={str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*')
               if p.is_file() and '.tmp' not in p.relative_to(self.root).parts}
        self.assertEqual(after,before)
        self.assertFalse((self.root/'.tmp').exists())
        self.assertEqual(len(list((self.project/'.tmp/maintenance-backups').glob('release-backup-*'))),1)

    def test_wrong_engine_checksum_changes_nothing(self):
        self.metadata['release']['assets'][0]['digest']='sha256:'+'0'*64
        with self.assertRaisesRegex(RuntimeError,'official release'):
            upgrade_release.upgrade(self.root,self.metadata,self.source,self.engine)
        self.assertFalse((self.root/'.tmp').exists())
        self.assertFalse((self.project/'.tmp').exists())

    def test_changed_instructions_need_review_bound_to_exact_bytes(self):
        with zipfile.ZipFile(self.source,'a') as z:z.writestr('Strata-fixed/AGENTS.md','Instructions v2')
        self.metadata['reviewed_changes']={'AGENTS.md':hashlib.sha256(b'Other text').hexdigest()}
        with self.assertRaisesRegex(RuntimeError,'require review: AGENTS.md'):
            upgrade_release.upgrade(self.root,self.metadata,self.source,self.engine)
        self.assertFalse((self.project/'.tmp').exists())
        digest=hashlib.sha256(b'Instructions v2').hexdigest()
        self.metadata['reviewed_changes']={'AGENTS.md':digest}
        result=upgrade_release.upgrade(self.root,self.metadata,self.source,self.engine)
        self.assertEqual((self.root/'runtime/Strata/AGENTS.md').read_text(),'Instructions v2')
        self.assertEqual(result['reviewed_changes'],{'AGENTS.md':digest})
        self.assertFalse(result['dependencies_modified'])

    def test_engine_zip_may_carry_kquant_library_but_nothing_else(self):
        with zipfile.ZipFile(self.engine,'a') as z:z.writestr('strata_kq.dll','kernels')
        self.metadata['release']['assets'][0].update(size=self.engine.stat().st_size,
            digest='sha256:'+hashlib.sha256(self.engine.read_bytes()).hexdigest())
        upgrade_release.upgrade(self.root,self.metadata,self.source,self.engine)
        self.assertEqual((self.root/'runtime/Strata/engine/strata_kq.dll').read_text(),'kernels')
        with zipfile.ZipFile(self.engine,'a') as z:z.writestr('other.dll','x')
        self.metadata['release']['assets'][0].update(size=self.engine.stat().st_size,
            digest='sha256:'+hashlib.sha256(self.engine.read_bytes()).hexdigest())
        with self.assertRaisesRegex(RuntimeError,'Unexpected engine ZIP'):
            upgrade_release.upgrade(self.root,self.metadata,self.source,self.engine)

    def test_archive_path_traversal_is_rejected_before_backup(self):
        with zipfile.ZipFile(self.source,'a') as z:z.writestr('Strata-fixed/../../escape.txt','bad')
        with self.assertRaisesRegex(ValueError,'Unsafe ZIP'):
            upgrade_release.upgrade(self.root,self.metadata,self.source,self.engine)
        self.assertFalse((self.root/'.tmp').exists())
        self.assertFalse((self.project/'.tmp').exists())


if __name__=='__main__':unittest.main()
