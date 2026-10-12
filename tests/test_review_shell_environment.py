from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.reviewer.arw_measure import review_shell_environment, review_shell_policy


class ReviewShellEnvironmentTests(unittest.TestCase):
    def test_login_shell_resolves_exact_isolated_entry_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix='review shell ') as directory:
            root=Path(directory)
            shim=root/'bin'
            shim.mkdir()
            entry=shim/'arw'
            entry.write_text('#!/bin/sh\nprintf "isolated-machine-entry\\n"\n')
            entry.chmod(0o755)
            settings=review_shell_environment(root/'runtime.json')
            environment=dict(os.environ,**settings)
            environment['PATH']=str(shim)+os.pathsep+environment['PATH']
            reply=subprocess.run(['/bin/bash','-lc','command -v arw; arw'],
                                 env=environment,capture_output=True,text=True,check=True)
            self.assertEqual(reply.stdout.splitlines(),[str(entry),'isolated-machine-entry'])
            self.assertEqual(settings['QWEN_ARW_RUNTIME_FILE'],str(root/'runtime.json'))
            self.assertTrue((root/'shell-bootstrap.json').exists())

    def test_policy_hides_provider_key_and_keeps_shim(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'bin').mkdir()
            (root/'bin'/'arw').write_text('#!/bin/sh\n')
            policy=review_shell_policy(root/'runtime.json')
            self.assertEqual(policy['exclude'],['STRATA_API_KEY'])
            self.assertEqual(policy['set']['QWEN_ARW_RUNTIME_FILE'],str(root/'runtime.json'))
            self.assertNotIn('STRATA_API_KEY',policy['set'])

    def test_missing_measurement_entry_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                review_shell_environment(Path(directory)/'runtime.json')


if __name__=='__main__':unittest.main()
