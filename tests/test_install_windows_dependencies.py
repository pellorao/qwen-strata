import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.ops.install_windows import install_pinned_dependencies


class PinnedWindowsDependencyTests(unittest.TestCase):
    def fixture(self,root):
        wheels=root/'downloads/wheels';wheels.mkdir(parents=True)
        items=[]
        for name in ('core.whl','nvidia_cublas.whl','nvidia_cuda_runtime.whl'):
            data=name.encode();(wheels/name).write_bytes(data)
            items.append({'filename':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        return {'files':items}

    def execute_remote(self,code,args,*,pip_check_ok=True):
        commands=[]
        def invoke(command,**kwargs):
            commands.append(command)
            self.assertEqual(kwargs['env']['PIP_NO_INDEX'],'1')
            return type('Reply',(),{'returncode':0 if pip_check_ok or command[-1]!='check' else 1})()
        output=io.StringIO()
        with patch.object(sys,'argv',['phase',*[str(x) for x in args]]),patch('subprocess.run',side_effect=invoke),contextlib.redirect_stdout(output):
            exec(compile(code,'remote-installer','exec'),{})
        return output.getvalue(),commands

    def test_installs_cuda_extras_even_when_requirements_omit_them(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);binding=self.fixture(root);commands=[]
            def remote(settings,code,args,**kwargs):
                reply,calls=self.execute_remote(code,args);commands.extend(calls);return reply
            with patch('tools.ops.install_windows.remote_python',side_effect=remote):
                result=install_pinned_dependencies({},root,binding)
            self.assertEqual(result['pinned_packages_installed'],3)
            install=commands[0]
            self.assertIn('--no-index',install)
            for item in binding['files']:self.assertIn(str(root/'downloads/wheels'/item['filename']),install)
            self.assertEqual(commands[-1][-2:],['pip','check'])

    def test_modified_cuda_wheel_is_rejected_before_pip(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);binding=self.fixture(root)
            (root/'downloads/wheels/nvidia_cublas.whl').write_bytes(b'changed')
            with patch('tools.ops.install_windows.remote_python',side_effect=lambda settings,code,args,**kwargs:self.execute_remote(code,args)[0]),patch('subprocess.run') as invocation:
                with self.assertRaisesRegex(RuntimeError,'integrity'):
                    install_pinned_dependencies({},root,binding)
                invocation.assert_not_called()

    def test_inconsistent_installed_dependencies_are_not_reported_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);binding=self.fixture(root)
            with patch('tools.ops.install_windows.remote_python',side_effect=lambda settings,code,args,**kwargs:self.execute_remote(code,args,pip_check_ok=False)[0]):
                with self.assertRaisesRegex(RuntimeError,'consistency'):
                    install_pinned_dependencies({},root,binding)


if __name__=='__main__':unittest.main()
