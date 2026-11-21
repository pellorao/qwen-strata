import base64
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tools.ops.upgrade_release as upgrade_release

ASSET='strata-engine-0.1.47-windows-x86_64-cuda-cuda13.tar.gz'


def digest(data):return hashlib.sha256(data).hexdigest()


KEY=Ed25519PrivateKey.generate()
PUBLIC=base64.b64encode(KEY.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode()
KEY_ID=hashlib.sha256(base64.b64decode(PUBLIC)).digest()[:8].hex()
UPDATE_KEYS=json.dumps({'schema_version':1,'keys':[{'alg':'ed25519','key_id':KEY_ID,'public':PUBLIC}]})


def signature(payload,key=KEY,key_id=KEY_ID):
    return {'alg':'ed25519','key_id':key_id,'value':base64.b64encode(key.sign(payload)).decode()}


class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.project=self.folder/'maintenance'
        self.root_patch=patch.object(upgrade_release,'ROOT',self.project)
        self.root_patch.start()
        self.key_patch=patch.object(upgrade_release,'TRUSTED_KEYS',{KEY_ID:PUBLIC});self.key_patch.start()
        self.root=self.folder/'installation';runtime=self.root/'runtime/Strata'
        (runtime/'engine').mkdir(parents=True);(self.root/'config').mkdir()
        (runtime/'AGENTS.md').write_text('Instructions')
        (runtime/'requirements.txt').write_text('Dependencies')
        (runtime/'CMakeLists.txt').write_text('VERSION 0.1.45')
        (runtime/'changed.txt').write_text('old bytes')
        (runtime/'same.txt').write_text('same bytes')
        (runtime/'gone.sh').write_text('removed upstream')
        (runtime/'engine/strata.exe').write_text('old engine')
        (runtime/'engine/stale.dll').write_text('old library')
        (self.root/'config/installed-release.json').write_text('{"version":"0.1.45"}')
        self.source=self.folder/'source.zip';self.engine=self.folder/ASSET;self.feed=self.folder/'strata-feed.json'
        self.write_source({'AGENTS.md':'Instructions','requirements.txt':'Dependencies',
            'CMakeLists.txt':'project(strata VERSION 0.1.47 LANGUAGES CXX)','changed.txt':'new bytes',
            'same.txt':'same bytes','new.txt':'new file'})
        self.files={'strata.exe':b'new engine','cublas64_13.dll':b'blas',
                    'BUILD.json':json.dumps({'version':'0.1.47','archs':[75,86,89,120]}).encode()}
        self.metadata={'commit':'fixed','previous_source_paths':['gone.sh'],
            'release':{'tag_name':'v0.2.2','assets':[{'name':ASSET},{'name':'strata-feed.json'}]},
            'engine_package':{'url':ASSET,'version':'0.1.47','build_id':'abc+cuda13.0',
                              'archs':['sm_75','sm_86','sm_89','sm_120','compute_120']}}
        self.write_engine()

    def tearDown(self):
        self.root_patch.stop();self.key_patch.stop()
        self.temp.cleanup()

    def write_source(self,files,comment=b'fixed'):
        files={'strata_control/update_keys.json':UPDATE_KEYS,**files}
        with zipfile.ZipFile(self.source,'w') as z:
            for name,content in files.items():z.writestr('Strata-0.2.2/'+name,content)
            z.comment=comment

    def write_engine(self,manifest=None,extra=(),files=None,sign=True):
        """Write the engine tar.gz and bind it into the metadata and a signed feed the way the release does."""
        files=self.files if files is None else files
        if manifest is None:
            manifest={'schema_version':2,'id':'strata-engine','name':'strata-engine','version':'0.1.47',
                'platform':'windows-x86_64','backend':'cuda','archs':self.metadata['engine_package']['archs'],
                'build_id':'abc+cuda13.0','entrypoint':'strata.exe',
                'files':[{'path':n,'sha256':digest(d),'bytes':len(d)} for n,d in files.items()]}
            if sign:manifest['signature']=signature(upgrade_release.manifest_payload(manifest))
        manifest_bytes=json.dumps(manifest).encode()
        with tarfile.open(self.engine,'w:gz') as t:
            for name,data in [*files.items(),('engine-component.json',manifest_bytes)]:
                info=tarfile.TarInfo(name);info.size=len(data);t.addfile(info,io.BytesIO(data))
            for info in extra:t.addfile(info)
        data=self.engine.read_bytes()
        self.metadata['release']['assets'][0].update(size=len(data),digest='sha256:'+digest(data))
        self.metadata['engine_package'].update(size=len(data),sha256=digest(data),manifest_sha256=digest(manifest_bytes))
        self.write_feed()
        return manifest

    def write_feed(self,package=None,key=KEY):
        feed=json.dumps({'engine':{'packages':[package or self.metadata['engine_package'],
            {'url':'other.tar.gz','platform':'linux-x86_64'}]}}).encode()
        self.feed.write_bytes(feed)
        Path(str(self.feed)+'.sig').write_text(json.dumps(signature(feed,key)))
        self.metadata['release']['assets'][1].update(size=len(feed),digest='sha256:'+digest(feed))

    def run_upgrade(self,cuda_arch=86):
        return upgrade_release.upgrade(self.root,self.metadata,self.source,self.engine,self.feed,cuda_arch=cuda_arch)

    def snapshot(self):
        return {str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def assert_untouched(self,before):
        self.assertEqual(self.snapshot(),before)
        self.assertFalse((self.project/'.tmp').exists())

    def test_upgrade_installs_package_and_explicit_rollback_restores_it(self):
        before=self.snapshot()
        result=self.run_upgrade()
        engine=self.root/'runtime/Strata/engine'
        self.assertEqual(sorted(p.name for p in engine.iterdir()),
                         ['BUILD.json','cublas64_13.dll','engine-component.json','strata.exe'])
        self.assertEqual((self.root/'runtime/Strata/changed.txt').read_text(),'new bytes')
        self.assertFalse((self.root/'runtime/Strata/gone.sh').exists())
        self.assertEqual(json.loads((self.root/'config/installed-release.json').read_text()),
                         {'version':'0.2.2','commit':'fixed','engine_version':'0.1.47'})
        self.assertEqual(result['removed_upstream_files'],
                         ['runtime/Strata/engine/stale.dll','runtime/Strata/gone.sh'])
        self.assertNotIn('runtime/Strata/same.txt',result['written_sha256'])
        self.assertEqual(result['unchanged_files'],3)
        self.assertEqual(result['signatures_verified'],{'feed':KEY_ID,'engine_manifest':KEY_ID})
        self.assertEqual(result['engine_build_id'],'abc+cuda13.0')
        backup=Path(result['backup'])
        self.assertTrue(backup.is_relative_to(self.project/'.tmp/maintenance-backups'))
        self.assertEqual((backup/'files/runtime/Strata/engine/stale.dll').read_text(),'old library')
        upgrade_release.rollback(self.root,backup)
        self.assertEqual(self.snapshot(),before)

    def test_transaction_failure_restores_existing_bytes_and_removes_new_files(self):
        before=self.snapshot()
        original=upgrade_release.atomic
        def fail(path,data):
            if path==self.root/'runtime/Strata/engine/cublas64_13.dll':raise OSError('Injected late write failure')
            original(path,data)
        with patch.object(upgrade_release,'atomic',side_effect=fail):
            with self.assertRaisesRegex(OSError,'Injected late write failure'):self.run_upgrade()
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(len(list((self.project/'.tmp/maintenance-backups').glob('release-backup-*'))),1)

    def test_wrong_engine_checksum_changes_nothing(self):
        before=self.snapshot()
        self.metadata['release']['assets'][0]['digest']='sha256:'+'0'*64
        with self.assertRaisesRegex(RuntimeError,'official release'):self.run_upgrade()
        self.metadata['release']['assets'][0]['digest']='sha256:'+self.metadata['engine_package']['sha256']
        self.metadata['engine_package']['sha256']='0'*64;self.write_feed()
        with self.assertRaisesRegex(RuntimeError,'official release'):self.run_upgrade()
        self.assert_untouched(before)

    def test_manifest_must_match_feed_and_every_member(self):
        before=self.snapshot()
        self.metadata['engine_package']['manifest_sha256']='0'*64;self.write_feed()
        with self.assertRaisesRegex(RuntimeError,'manifest_sha256'):self.run_upgrade()
        # A member the manifest does not list.
        manifest=self.write_engine()
        self.files['extra.dll']=b'x';self.write_engine(manifest=manifest)
        with self.assertRaisesRegex(RuntimeError,'archive members'):self.run_upgrade()
        # A member whose bytes differ from its manifest entry.
        del self.files['extra.dll'];manifest=self.write_engine()
        self.files['strata.exe']=b'tampered';self.write_engine(manifest=manifest)
        with self.assertRaisesRegex(RuntimeError,'manifest size or SHA256'):self.run_upgrade()
        # A manifest built for another build than the feed names.
        self.files['strata.exe']=b'new engine';manifest=self.write_engine();manifest['build_id']='other'
        self.write_engine(manifest=manifest)
        with self.assertRaisesRegex(RuntimeError,'release feed'):self.run_upgrade()
        self.assert_untouched(before)

    def test_engine_archive_links_devices_and_unsafe_paths_are_refused(self):
        before=self.snapshot()
        cases=[]
        for kind in (tarfile.SYMTYPE,tarfile.LNKTYPE,tarfile.CHRTYPE,tarfile.FIFOTYPE):
            info=tarfile.TarInfo('link.dll');info.type=kind;info.linkname='strata.exe';cases.append((info,'Unexpected engine archive entry'))
        for name in ('/abs.dll','../escape.dll','dir/../../escape.dll','C:evil.dll','a\\b.dll'):
            info=tarfile.TarInfo(name);cases.append((info,'Unsafe archive member'))
        cases.append((tarfile.TarInfo('STRATA.EXE'),'Duplicate engine archive entry'))
        for info,message in cases:
            with self.subTest(name=info.name,type=info.type):
                self.write_engine(extra=[info])
                with self.assertRaisesRegex((RuntimeError,ValueError),message):self.run_upgrade()
        self.assert_untouched(before)

    def test_versions_are_split_between_release_and_engine(self):
        before=self.snapshot()
        self.write_source({'AGENTS.md':'Instructions','requirements.txt':'Dependencies','CMakeLists.txt':'VERSION 0.2.2'})
        with self.assertRaisesRegex(RuntimeError,'engine version'):self.run_upgrade()
        self.write_source({'AGENTS.md':'Instructions','requirements.txt':'Dependencies','CMakeLists.txt':'VERSION 0.1.47'})
        self.files['BUILD.json']=json.dumps({'version':'0.2.2','archs':[86]}).encode();self.write_engine()
        with self.assertRaisesRegex(RuntimeError,'GPU architecture'):self.run_upgrade()
        self.files['BUILD.json']=json.dumps({'version':'0.1.47','archs':[86]}).encode();self.write_engine()
        with self.assertRaisesRegex(RuntimeError,'GPU architecture'):self.run_upgrade(cuda_arch=61)
        self.assert_untouched(before)

    def test_engine_reused_from_an_earlier_release_is_named_by_full_url(self):
        self.metadata['engine_package']['url']='https://example.invalid/releases/download/v0.2.14/'+ASSET
        self.write_feed()
        self.assertEqual(self.run_upgrade()['engine_version'],'0.1.47')

    def test_source_cmake_version_may_be_bound_by_metadata(self):
        self.write_source({'AGENTS.md':'Instructions','requirements.txt':'Dependencies','CMakeLists.txt':'VERSION 0.1.49'})
        with self.assertRaisesRegex(RuntimeError,'engine version'):self.run_upgrade()
        self.metadata['source_cmake_version']='0.1.49'
        self.run_upgrade()

    def test_terminal_layout_installs_only_terminal_and_agents(self):
        files={'AGENTS.md':'Instructions','engine/CMakeLists.txt':'project(strata VERSION 0.1.47 LANGUAGES CXX)',
               'engine/src/a.cpp':'engine source','docs/x.md':'docs','app/y.js':'app','tools/z.py':'root tool',
               'terminal/serve/server.py':'server','terminal/requirements.txt':'Dependencies',
               'terminal/strata_control/update_keys.json':UPDATE_KEYS,'terminal/changed.txt':'new bytes'}
        with zipfile.ZipFile(self.source,'w') as z:
            for name,content in files.items():z.writestr('Strata-0.2.2/'+name,content)
            z.comment=b'fixed'
        self.run_upgrade()
        runtime=self.root/'runtime/Strata'
        self.assertEqual((runtime/'serve/server.py').read_text(),'server')
        self.assertEqual((runtime/'changed.txt').read_text(),'new bytes')
        self.assertFalse((runtime/'src').exists() or (runtime/'docs').exists() or (runtime/'tools').exists())
        self.assertEqual((runtime/'engine/strata.exe').read_text(),'new engine')
        self.assertFalse((runtime/'engine/src').exists())

    def write_terminal_source(self):
        files={'AGENTS.md':'Instructions','engine/CMakeLists.txt':'project(strata VERSION 0.1.47 LANGUAGES CXX)',
               'terminal/serve/server.py':'server','terminal/requirements.txt':'Dependencies',
               'terminal/strata_control/update_keys.json':UPDATE_KEYS,'terminal/changed.txt':'new bytes'}
        with zipfile.ZipFile(self.source,'w') as z:
            for name,content in files.items():z.writestr('Strata-0.2.2/'+name,content)
            z.comment=b'fixed'

    def test_layout_switch_removes_old_source_but_keeps_venv_and_cache(self):
        runtime=self.root/'runtime/Strata'
        for name,content in {'src/old.cpp':'engine source','docs/a.md':'docs','serve/old_module.py':'old',
                             '.venv/Lib/site.py':'venv','serve/__pycache__/x.pyc':'cache'}.items():
            (runtime/name).parent.mkdir(parents=True,exist_ok=True);(runtime/name).write_text(content)
        self.metadata['previous_source_paths']=[]
        self.write_terminal_source()
        before=self.snapshot()
        result=self.run_upgrade()
        self.assertEqual(result['removed_upstream_files'],[
            'runtime/Strata/CMakeLists.txt','runtime/Strata/docs/a.md','runtime/Strata/engine/stale.dll',
            'runtime/Strata/gone.sh','runtime/Strata/same.txt','runtime/Strata/serve/old_module.py',
            'runtime/Strata/src/old.cpp'])
        self.assertFalse((runtime/'src/old.cpp').exists() or (runtime/'docs/a.md').exists() or (runtime/'CMakeLists.txt').exists())
        self.assertEqual((runtime/'.venv/Lib/site.py').read_text(),'venv')
        self.assertEqual((runtime/'serve/__pycache__/x.pyc').read_text(),'cache')
        self.assertEqual((runtime/'serve/server.py').read_text(),'server')
        upgrade_release.rollback(self.root,Path(result['backup']))
        self.assertEqual(self.snapshot(),before)

    def test_terminal_layout_without_old_layout_marker_keeps_unlisted_files(self):
        runtime=self.root/'runtime/Strata'
        (runtime/'CMakeLists.txt').unlink()
        self.write_terminal_source()
        self.run_upgrade()
        self.assertEqual((runtime/'same.txt').read_text(),'same bytes')
        self.assertFalse((runtime/'gone.sh').exists())

    def test_tag_archive_comment_must_bind_the_commit(self):
        before=self.snapshot()
        with zipfile.ZipFile(self.source,'a') as z:z.comment=b'other'
        with self.assertRaisesRegex(RuntimeError,'comment'):self.run_upgrade()
        with zipfile.ZipFile(self.source,'a') as z:z.comment=b'fixed';z.writestr('Strata-other/x.txt','x')
        with self.assertRaisesRegex(RuntimeError,'Unexpected source archive entry'):self.run_upgrade()
        self.write_source({'AGENTS.md':'Instructions','requirements.txt':'Dependencies',
                           'CMakeLists.txt':'VERSION 0.1.47','a.txt':'x','A.TXT':'y'})
        with self.assertRaisesRegex(RuntimeError,'Duplicate source archive entry'):self.run_upgrade()
        self.assert_untouched(before)

    def test_changed_instructions_need_review_bound_to_exact_bytes(self):
        self.write_source({'AGENTS.md':'Instructions v2','requirements.txt':'Dependencies','CMakeLists.txt':'VERSION 0.1.47'})
        self.metadata['reviewed_changes']={'AGENTS.md':digest(b'Other text')}
        with self.assertRaisesRegex(RuntimeError,'require review: AGENTS.md'):self.run_upgrade()
        self.assertFalse((self.project/'.tmp').exists())
        self.metadata['reviewed_changes']={'AGENTS.md':digest(b'Instructions v2')}
        result=self.run_upgrade()
        self.assertEqual((self.root/'runtime/Strata/AGENTS.md').read_text(),'Instructions v2')
        self.assertEqual(result['reviewed_changes'],{'AGENTS.md':digest(b'Instructions v2')})
        self.assertFalse(result['dependencies_modified'])

    def test_signatures_bind_feed_package_and_manifest(self):
        before=self.snapshot()
        other=Ed25519PrivateKey.generate()
        self.write_feed(key=other)
        with self.assertRaisesRegex(RuntimeError,'Signature does not match'):self.run_upgrade()
        self.write_feed(package=dict(self.metadata['engine_package'],build_id='other'))
        with self.assertRaisesRegex(RuntimeError,'signed release feed'):self.run_upgrade()
        self.write_feed();self.metadata['release']['assets'][1]['digest']='sha256:'+'0'*64
        with self.assertRaisesRegex(RuntimeError,'Feed differs'):self.run_upgrade()
        self.write_engine(sign=False)
        with self.assertRaisesRegex(RuntimeError,'untrusted key'):self.run_upgrade()
        manifest=self.write_engine();manifest['signature']=signature(b'other payload');self.write_engine(manifest=manifest)
        with self.assertRaisesRegex(RuntimeError,'Signature does not match'):self.run_upgrade()
        self.write_engine()
        self.write_source({'strata_control/update_keys.json':json.dumps({'keys':[]}),'AGENTS.md':'Instructions',
                           'requirements.txt':'Dependencies','CMakeLists.txt':'VERSION 0.1.47'})
        with self.assertRaisesRegex(RuntimeError,'pinned feed key'):self.run_upgrade()
        self.assert_untouched(before)

    def test_windows_unsafe_names_are_refused(self):
        for name in ('CON','dir/nul.txt','com1.dll','lpt9','trailing.','space ','a<b','a|b','a?b','tab\tname'):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError,'Unsafe archive member'):upgrade_release.member(name)
        for name in ('console.py','dir/conf.txt','con1','a.b/c.d'):
            self.assertEqual(upgrade_release.member(name),name)

    def test_source_write_failure_rolls_back(self):
        before=self.snapshot()
        original=upgrade_release.atomic
        def fail(path,data):
            if path==self.root/'runtime/Strata/new.txt':raise OSError('Injected source write failure')
            original(path,data)
        with patch.object(upgrade_release,'atomic',side_effect=fail):
            with self.assertRaisesRegex(OSError,'Injected source write failure'):self.run_upgrade()
        self.assertEqual(self.snapshot(),before)

    def test_removal_failure_rolls_back_including_already_removed_files(self):
        before=self.snapshot()
        original=Path.unlink
        def fail(path,*args,**kwargs):
            if path.name=='stale.dll' and not kwargs.get('missing_ok'):raise PermissionError('Injected unlink failure')
            return original(path,*args,**kwargs)
        with patch.object(Path,'unlink',fail):
            with self.assertRaisesRegex(PermissionError,'Injected unlink failure'):self.run_upgrade()
        self.assertEqual(self.snapshot(),before)

    def test_atomic_failure_leaves_no_stage_file(self):
        class Broken(io.RawIOBase):
            def readable(self):return True
            def readinto(self,buffer):raise OSError('Injected read failure')
        target=self.root/'runtime/Strata/engine/strata.exe'
        with self.assertRaisesRegex(OSError,'Injected read failure'):upgrade_release.atomic(target,Broken())
        self.assertEqual(sorted(p.name for p in target.parent.iterdir()),['stale.dll','strata.exe'])
        self.assertEqual(target.read_text(),'old engine')

    def test_rollback_continues_past_a_failure_and_reports_all(self):
        before=self.snapshot()
        result=self.run_upgrade();backup=Path(result['backup'])
        (backup/'files/runtime/Strata/changed.txt').write_text('corrupted backup')
        with self.assertRaisesRegex(RuntimeError,r'1 file\(s\) unrestored.*changed.txt: backup hash mismatch'):
            upgrade_release.rollback(self.root,backup)
        after=self.snapshot()
        # Every other file was still restored.
        self.assertEqual({k:v for k,v in after.items() if not k.endswith('changed.txt')},
                         {k:v for k,v in before.items() if not k.endswith('changed.txt')})
        self.assertEqual(after['runtime/Strata/changed.txt'],b'new bytes')

    def test_unchanged_engine_file_is_skipped_and_kept(self):
        (self.root/'runtime/Strata/engine/cublas64_13.dll').write_bytes(b'blas')
        result=self.run_upgrade()
        self.assertNotIn('runtime/Strata/engine/cublas64_13.dll',result['written_sha256'])
        self.assertNotIn('runtime/Strata/engine/cublas64_13.dll',result['removed_upstream_files'])
        self.assertEqual((self.root/'runtime/Strata/engine/cublas64_13.dll').read_bytes(),b'blas')
        before=json.loads((Path(result['backup'])/'before.json').read_text())
        self.assertNotIn('runtime/Strata/engine/cublas64_13.dll',before)

    def test_case_variant_of_a_written_file_is_not_removed(self):
        # On the Windows volume Strata.EXE and strata.exe are one file; removing it would remove the new engine.
        (self.root/'runtime/Strata/engine/Strata.EXE').write_text('old engine, other case')
        (self.root/'runtime/Strata/NEW.TXT').write_text('case variant of a written source file')
        self.metadata['previous_source_paths']=['gone.sh','NEW.TXT']
        result=self.run_upgrade()
        self.assertNotIn('runtime/Strata/engine/Strata.EXE',result['removed_upstream_files'])
        self.assertNotIn('runtime/Strata/NEW.TXT',result['removed_upstream_files'])
        self.assertIn('runtime/Strata/engine/stale.dll',result['removed_upstream_files'])

    def test_source_path_traversal_is_rejected_before_backup(self):
        before=self.snapshot()
        with zipfile.ZipFile(self.source,'a') as z:z.writestr('Strata-0.2.2/../../escape.txt','bad')
        with self.assertRaisesRegex(ValueError,'Unsafe archive member'):self.run_upgrade()
        self.assert_untouched(before)


if __name__=='__main__':unittest.main()
