import concurrent.futures
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from service_access import Ownership, AccessError, authorize


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)/'access.json'
        self.backend = Mock()
        self.backend.stopped.return_value = True
        self.ownership = Ownership(self.path, self.backend)

    def tearDown(self):
        self.directory.cleanup()

    def test_only_one_concurrent_caller_receives_key_even_with_stopped_model(self):
        def acquire(_):
            try: return self.ownership.acquire()['key']
            except AccessError: return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            keys = [key for key in pool.map(acquire, range(30)) if key]
        self.assertEqual(len(keys), 1)
        self.assertTrue(authorize(self.path, keys[0]))
        self.assertNotIn(keys[0], self.path.read_text())

    def test_no_key_issued_while_model_process_exists(self):
        self.backend.stopped.return_value = False
        with self.assertRaises(AccessError): self.ownership.acquire()
        self.assertEqual(json.loads(self.path.read_text())['phase'], 'free')

    def test_wrong_key_cannot_start_stop_query_or_return(self):
        self.ownership.acquire()
        for operation in (lambda:self.ownership.start('wrong', {'model':'IQ3_XXS'}),
                          lambda:self.ownership.stop('wrong'),lambda:self.ownership.status('wrong'),
                          lambda:self.ownership.release('wrong')):
            with self.assertRaises(AccessError): operation()
        self.backend.start.assert_not_called();self.backend.stop.assert_not_called()
        self.backend.status.assert_not_called()

    def test_return_revokes_before_cleanup_and_new_key_does_not_reuse_old_key(self):
        first = self.ownership.acquire()['key']
        self.backend.stop.side_effect = lambda: self.assertFalse(authorize(self.path, first)) or {'status':'stopped'}
        self.ownership.release(first)
        with self.assertRaises(AccessError): self.ownership.start(first, {})
        second = self.ownership.acquire()['key']
        self.assertNotEqual(first, second)
        self.assertFalse(authorize(self.path, first));self.assertTrue(authorize(self.path, second))

    def test_cleanup_failure_revokes_and_blocks_grant_until_cleanup_succeeds(self):
        key = self.ownership.acquire()['key']
        self.backend.stop.side_effect = RuntimeError('busy')
        with self.assertRaises(AccessError): self.ownership.release(key)
        self.assertFalse(authorize(self.path, key))
        restarted = Ownership(self.path, self.backend)
        with self.assertRaises(AccessError): restarted.acquire()
        self.backend.stop.side_effect = None
        self.backend.stopped.return_value = True
        replacement = restarted.acquire()['key']
        self.assertNotEqual(key, replacement)

    def test_controller_restart_preserves_holder_and_stop_does_not_release_key(self):
        key = self.ownership.acquire()['key']
        restarted = Ownership(self.path, self.backend)
        restarted.stop(key)
        self.assertTrue(authorize(self.path, key))
        with self.assertRaises(AccessError): restarted.acquire()

    def test_corrupt_state_cannot_be_reinitialized_as_available(self):
        self.path.write_text('{"phase":"unknown","key_sha256":"bad"}')
        with self.assertRaises(AccessError): Ownership(self.path, self.backend)
        self.assertFalse(authorize(self.path, 'bad'))


if __name__ == '__main__': unittest.main()
