import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.reviewer.arw_measure import generate_original, commit_audit_generated


class OriginalGenerationTests(unittest.TestCase):
    def test_commit_audit_native_file_mapping_is_success_without_status_field(self):
        self.assertTrue(commit_audit_generated({'exit_code': 0, 'result': {'files': [
            {'sourcePath': '.tmp/audit.json', 'targetPath': '.scratch/issue.audit.json'}]}}))
        for result in (
            {'exit_code': 0, 'result': {'status': 'failed', 'diagnostics': []}},
            {'exit_code': 1, 'result': {'files': [
                {'sourcePath': '.tmp/audit.json', 'targetPath': '.scratch/issue.audit.json'}]}},
            {'exit_code': 0, 'result': {'files': []}},
            {'exit_code': 0, 'result': {'status': 'succeeded'}},
        ):
            with self.subTest(result=result):
                self.assertFalse(commit_audit_generated(result))

    def test_original_cli_returns_path_and_keeps_raw_output(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            artifact = folder / 'artifacts' / 'artifact.json'
            artifact.parent.mkdir()
            artifact.write_text(json.dumps({'schemaVersion': 1}))
            preparation = {'generations': [{'instanceId': 'one',
                'command': 'arw spec-readiness generate request.json',
                'workdir': str(folder)}]}
            stdout = str(artifact) + '\n'
            completed = subprocess.CompletedProcess([], 0, stdout, '')
            with patch('tools.reviewer.arw_measure.subprocess.run', return_value=completed):
                result = generate_original(folder, preparation, {'instanceId': 'one'}, folder)
            self.assertEqual(result['artifactPaths'], [str(artifact)])
            self.assertEqual(result['exit_code'], 0)
            self.assertEqual((folder / 'generation-stdout.txt').read_text(), stdout)

    def test_original_cli_failure_retains_evidence_and_does_not_promote_stdout(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            preparation = {'generations': [{'instanceId': 'one',
                'command': 'arw spec-readiness generate request.json',
                'workdir': str(folder)}]}
            completed = subprocess.CompletedProcess([], 1, 'partial output\n',
                'Configuration file not found: config.json.\n')
            with patch('tools.reviewer.arw_measure.subprocess.run', return_value=completed):
                result = generate_original(folder, preparation, {'instanceId': 'one'}, folder)
            self.assertEqual(result['artifactPaths'], [])
            self.assertEqual(result['exit_code'], 1)
            self.assertEqual((folder / 'generation-stderr.txt').read_text(), completed.stderr)


if __name__ == '__main__':
    unittest.main()
