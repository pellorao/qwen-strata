"""Measurement telemetry must not discard completed model responses."""
import io
import json
import sys
import tempfile
import urllib.error
from pathlib import Path
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.ops import release_orphan_lease
from tools.ops.controller_client import Controller, usage_counts


class UsageCountsTest(unittest.TestCase):
    def test_split_phase_cache_can_exceed_original_request_input(self):
        # Real training encountered this shape: the reused thinking prefix is
        # longer than the original user input. These counters cannot be mixed.
        raw = {'prompt_tokens': 16535,
               'prompt_tokens_details': {'cached_tokens': 20631},
               'completion_tokens': 16367}
        counts = usage_counts(raw)
        self.assertIsNone(counts['uncached_input'])
        self.assertIsNone(counts['cached_input'])
        self.assertEqual(counts['output'], 16367)
        self.assertIn('exceeds', counts['reason'])
        self.assertEqual(raw['prompt_tokens_details']['cached_tokens'], 20631)

    def test_valid_response_keeps_three_token_categories(self):
        self.assertEqual(usage_counts({
            'input_tokens': 100, 'input_tokens_details': {'cached_tokens': 60},
            'output_tokens': 7}),
            {'uncached_input': 40, 'cached_input': 60, 'output': 7})


class OrphanLeaseTest(unittest.TestCase):
    KEY = 'secret-key-value'

    def release(self, replies):
        calls, lines = [], []

        def call(owner, path, body=None, timeout=900):
            calls.append((path, owner.key))
            reply = replies[path]
            if isinstance(reply, Exception):
                raise reply
            return reply

        with tempfile.TemporaryDirectory() as tmp:
            credential = Path(tmp) / 'controller-key.private.json'
            credential.write_text(json.dumps({'base_url': 'http://frontend:8000', 'key': self.KEY}))
            with mock.patch.object(Controller, 'call', call):
                done = release_orphan_lease.release(tmp, lines.append)
            return done, calls, lines, credential.exists()

    def test_stops_the_model_returns_the_key_and_deletes_the_file(self):
        done, calls, lines, left = self.release({'/model/status': {'status': 'running'},
                                                 '/model/stop': {'status': 'stopped'},
                                                 '/lease/release': {'lease': 'free'}})
        self.assertTrue(done)
        self.assertFalse(left)
        self.assertEqual(calls, [(p, self.KEY) for p in ('/model/status', '/model/stop', '/lease/release')])
        self.assertNotIn(self.KEY, '\n'.join(lines))

    def test_a_stopped_model_is_not_stopped_again(self):
        done, calls, _, left = self.release({'/model/status': {'status': 'stopped'},
                                             '/lease/release': {'lease': 'free'}})
        self.assertTrue(done and not left)
        self.assertEqual([p for p, _ in calls], ['/model/status', '/lease/release'])

    def test_a_refused_key_touches_nothing(self):
        refused = urllib.error.HTTPError('http://frontend:8000/model/status', 403, 'Forbidden', {}, io.BytesIO())
        done, calls, lines, left = self.release({'/model/status': refused})
        self.assertFalse(done)
        self.assertTrue(left)
        self.assertEqual([p for p, _ in calls], ['/model/status'])
        self.assertNotIn(self.KEY, '\n'.join(lines))


if __name__ == '__main__':
    unittest.main()
