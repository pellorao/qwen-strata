import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.reviewer.native_cli_binding import verify_native_cli


class NativeCliBindingTests(unittest.TestCase):
    def test_no_binding_keeps_existing_entrypoint(self):
        self.assertIsNone(verify_native_cli(None))

    def test_digest_drift_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'codex'
            path.write_bytes(b'changed')
            with patch('tools.reviewer.native_cli_binding.subprocess.check_output') as run:
                with self.assertRaisesRegex(ValueError, 'SHA differs'):
                    verify_native_cli(dict(executable=str(path), sha256='old', version='0.160.1'))
                run.assert_not_called()

    def test_version_is_bound_even_when_digest_matches(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'codex'
            path.write_bytes(b'cached binary')
            binding = dict(executable=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                           version='0.160.1')
            with patch('tools.reviewer.native_cli_binding.subprocess.check_output', return_value='codex-cli 0.161.0\n'):
                with self.assertRaisesRegex(ValueError, 'version differs'):
                    verify_native_cli(binding)
            with patch('tools.reviewer.native_cli_binding.subprocess.check_output', return_value='codex-cli 0.160.1\n') as run:
                self.assertEqual(verify_native_cli(binding)['observed_version'], 'codex-cli 0.160.1')
                run.assert_called_once_with([str(path), '--version'], text=True, timeout=20)


if __name__ == '__main__':
    unittest.main()
