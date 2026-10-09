import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.reviewer.arw_metrics import collect_cost, split_tokens


class ArwMetricsTests(unittest.TestCase):
    def fixture(self, home, name, parent=None, usage=None):
        meta = {'id': name, 'model_provider': 'qwen_strata'}
        if parent:
            meta.update(parent_thread_id=parent, thread_source='guardian_review')
        events = [{'type': 'session_meta', 'payload': meta}]
        for u in usage or []:
            events.append({'type': 'event_msg', 'payload': {'type': 'token_count',
                           'info': {'total_token_usage': u}}})
        (home/'sessions'/f'{name}.jsonl').write_text('\n'.join(map(json.dumps, events)))

    def record(self):
        return {'runtime_result': {'threadId': 'root'},
                'revisions': [{'measurement': {'wallClockMs': 1000, 'usage':
                    {'inputTokens': 100, 'cachedInputTokens': 20, 'outputTokens': 3}}}],
                'measurement': {'wallClockMs': 2000, 'usage':
                    {'inputTokens': 150, 'cachedInputTokens': 100, 'outputTokens': 5}}}

    def test_followup_deltas_and_reused_guardian_only_counted_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp); (home/'sessions').mkdir()
            self.fixture(home, 'root')
            self.fixture(home, 'guardian', 'root', [
                {'input_tokens': 10, 'cached_input_tokens': 0, 'output_tokens': 1},
                {'input_tokens': 30, 'cached_input_tokens': 5, 'output_tokens': 4}])
            self.fixture(home, 'unrelated', 'other-root', [
                {'input_tokens': 99999, 'cached_input_tokens': 0, 'output_tokens': 888}])
            record = self.record(); before = json.dumps(record)
            cost = collect_cost(record, home)
            self.assertEqual(json.dumps(record), before)
            self.assertEqual(cost['reviewer_active_seconds'], 3)
            self.assertEqual(cost['guardian_thread_count'], 1)
            self.assertEqual(cost['combined_api_tokens'],
                             {'uncached_input': 155, 'cached_input': 125, 'output': 12})
            self.assertIsNone(cost['rpc_failure_count'])

    def test_missing_and_invalid_usage_are_unknown_not_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp); (home/'sessions').mkdir()
            self.fixture(home, 'guardian', 'root')
            cost = collect_cost(self.record(), home)
            self.assertTrue(cost['unknown_reasons'])
            self.assertTrue(all(v is None for v in cost['combined_api_tokens'].values()))
        self.assertEqual(split_tokens({'inputTokens': 10, 'cachedInputTokens': 11,
                                      'outputTokens': 3}),
                         {'uncached_input': None, 'cached_input': None, 'output': 3})

    def test_missing_guardian_usage_stays_unknown_with_valid_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp); (home/'sessions').mkdir()
            self.fixture(home, 'root'); self.fixture(home, 'guardian', 'root')
            cost = collect_cost(self.record(), home)
            self.assertTrue(all(v is None for v in cost['guardian_tokens'].values()))

    def test_impossible_individual_cache_is_not_hidden_by_valid_cumulative_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp); (home/'sessions').mkdir()
            self.fixture(home, 'root')
            with (home/'sessions/root.jsonl').open('a') as stream:
                stream.write('\n'+json.dumps({'type': 'token_usage_record', 'payload': {
                    'response_id': 'response-bad', 'usage': {'input_tokens': 10,
                    'cached_input_tokens': 11, 'output_tokens': 2}}}))
            cost = collect_cost(self.record(), home)
            self.assertEqual(cost['combined_api_tokens'],
                             {'uncached_input': None, 'cached_input': None, 'output': 8})
            self.assertEqual(len(cost['histories'][0]['invalid_input_usage_records']), 1)


if __name__ == '__main__':
    unittest.main()
