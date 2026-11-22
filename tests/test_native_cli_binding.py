import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.strata.native_cli_binding import (CODEX, CODEX_SHA256, CODEX_VERSION, selection_native_cli,
                                               file_sha256, verify_native_cli)


class NativeCliBindingTests(unittest.TestCase):
    def test_no_binding_keeps_existing_entrypoint(self):
        self.assertIsNone(verify_native_cli(None))

    def test_chunked_hash_equals_the_whole_file_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'codex'
            path.write_bytes(b'0123456789' * 5)
            self.assertEqual(file_sha256(path, chunk=7), hashlib.sha256(path.read_bytes()).hexdigest())

    def test_digest_drift_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'codex'
            path.write_bytes(b'changed')
            with patch('tools.strata.native_cli_binding.subprocess.check_output') as run:
                with self.assertRaisesRegex(ValueError, 'SHA differs'):
                    verify_native_cli(dict(executable=str(path), sha256='old', version='0.160.1'))
                run.assert_not_called()

    def test_version_is_bound_even_when_digest_matches(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'codex'
            path.write_bytes(b'cached binary')
            binding = dict(executable=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                           version='0.160.1')
            with patch('tools.strata.native_cli_binding.subprocess.check_output', return_value='codex-cli 0.161.0\n'):
                with self.assertRaisesRegex(ValueError, 'version differs'):
                    verify_native_cli(binding)
            with patch('tools.strata.native_cli_binding.subprocess.check_output', return_value='codex-cli 0.160.1\n') as run:
                self.assertEqual(verify_native_cli(binding)['observed_version'], 'codex-cli 0.160.1')
                run.assert_called_once_with([str(path), '--version'], text=True, timeout=20)

    def test_unbound_selection_runs_the_pinned_benchmark_copy(self):
        self.assertIn(f'/.local/share/qwen-bench/codex-{CODEX_VERSION}/', str(CODEX))
        with patch('tools.strata.native_cli_binding.verify_native_cli', side_effect=lambda b: b) as verify:
            self.assertEqual(selection_native_cli(None),
                             {'executable': str(CODEX), 'version': CODEX_VERSION, 'sha256': CODEX_SHA256})
            self.assertEqual(selection_native_cli({'executable': '/x'}), {'executable': '/x'})
            self.assertEqual(verify.call_count, 2)


if __name__ == '__main__':
    unittest.main()
