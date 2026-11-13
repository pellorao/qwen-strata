import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.reviewer import arw_measure
from tools.reviewer.arw_measure import cleanup_step, report_cleanup_failures, run_api

OPENAI = {'id': 'openai', 'auth': 'env_key', 'base_url': 'https://api.openai.com/v1'}
API = {'provider': OPENAI, 'model': 'gpt-6.1-sol', 'effort': 'high'}


class CleanupStepTests(unittest.TestCase):
    def test_a_failing_step_is_recorded_and_the_next_still_runs(self):
        failures, ran = [], []
        with cleanup_step(failures, 'first'):
            raise OSError('x')
        with cleanup_step(failures, 'second'):
            ran.append(1)
        self.assertEqual(ran, [1])
        self.assertEqual(len(failures), 1)
        self.assertTrue(failures[0].startswith('first: '))

    def test_failures_raise_only_without_another_exception_in_flight(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            report_cleanup_failures([], out)
            self.assertFalse((out / 'cleanup-errors.json').exists())
            with self.assertRaisesRegex(RuntimeError, 'Cleanup steps failed'):
                report_cleanup_failures(['a: x'], out)
            self.assertEqual(json.loads((out / 'cleanup-errors.json').read_text()), ['a: x'])
            with self.assertRaisesRegex(KeyError, 'original'):
                try:
                    raise KeyError('original')
                finally:
                    report_cleanup_failures(['b: y'], out)


class RunApiCleanupTests(unittest.TestCase):
    def run_with_failing_daemon_read(self, root):
        daemon = MagicMock(pid=4242)
        messages = iter([{'ready': True, 'providers': {}}])

        def read(stream, process, timeout=60):
            try:
                return next(messages)
            except StopIteration:
                raise RuntimeError('daemon response is uncertain')
        old_path = os.environ.get('PATH', '')
        with patch.dict('os.environ', {'BENCHMARK_OPENAI_API_KEY': 'synthetic'}, clear=True), \
                patch('tools.reviewer.native_cli_binding.verify_native_cli', lambda value: None), \
                patch.object(arw_measure, 'compaction_config'), \
                patch.object(arw_measure, 'api_review_catalog', return_value=root / 'catalog.json'), \
                patch.object(arw_measure, 'prepared_jobs', return_value=([{'preparedPath': 'p'}], root, [])), \
                patch.object(arw_measure, 'spec_repetition_order', lambda jobs: jobs), \
                patch.object(arw_measure, 'credential_deny_paths', return_value=[]), \
                patch.object(arw_measure, 'link_login', return_value=None), \
                patch.object(arw_measure, 'Machine', MagicMock()), \
                patch.object(arw_measure.subprocess, 'Popen', return_value=daemon), \
                patch.object(arw_measure, 'read_daemon_message', read):
            os.environ['PATH'] = old_path
            try:
                return daemon, run_api(root / 'api', API, [], root / 'c.json'), None
            except Exception as error:  # noqa: BLE001
                return daemon, None, error
            finally:
                self.environment_after = dict(os.environ)

    def test_a_failed_daemon_cleanup_read_still_restores_the_environment_and_writes_the_recovery_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            daemon, records, error = self.run_with_failing_daemon_read(root)
            self.assertIsNotNone(error)
            self.assertIn('daemon cleanup', str(error))
            marker = json.loads((root / 'api/recovery-required.json').read_text())
            self.assertEqual(marker['daemon_pid'], 4242)
            self.assertNotIn('QWEN_ARW_RUNTIME_FILE', self.environment_after)
            self.assertNotIn(str(root / 'api/bin'), self.environment_after['PATH'])
            self.assertTrue(json.loads((root / 'api/cleanup-errors.json').read_text())[0].startswith('daemon cleanup'))


if __name__ == '__main__':
    unittest.main()
