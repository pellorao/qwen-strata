import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tools.reviewer import bench_records, bench_validity

IID = 'default-42b4f896-1071-4617-bcba-e1110a1fc457-instance-1'
CC_CHECKS = {'models_returned': ['deepseek-flash'], 'model_match': True, 'service_tiers': {'standard': 3}, 'tier_ok': True,
             'server_web_requests': None, 'completed': False, 'startup_prompt_off': True, 'continuation_stop': 'hard_limit',
             'ended_normally': True, 'sandbox_failures': 0, 'valid': False}
CODEX_CHECKS = {'ended_normally': True, 'harness_rejected': False, 'tier_ok': True, 'model_ok': True,
                'web_search_calls': 0, 'startup_off': True, 'arw_pause': False, 'limited': False, 'relay_errors': 1}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value))
    return path


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat().replace('+00:00', 'Z')


def assistant(content, usage=None, mid='m1'):
    return json.dumps({'type': 'assistant', 'message': {'id': mid, 'content': content, 'usage': usage or {}}}) + '\n'


class ValidityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.scene = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def cc(self, name, stream, checks=None, result=None):
        d = self.scene / name
        write(d / 'instance.json', {'handoffs': [{'instanceId': IID, 'checks': {**CC_CHECKS, **(checks or {})},
                                                  'continuation': {'arw_pause_events': []}}],
                                    'arw_pause_events': []})
        write(d / 'h0/stream.jsonl', stream)
        write(d / 'h0/result.json', result or {'hard_interrupt': True, 'started_at': 100.0, 'summary': {
            'result_event': False, 'segments': 1, 'segments_without_result': 1}})
        return d

    def records(self, arm='deepseek-claude', scenario='code-spec-v5'):
        return {r['id'].rsplit('/', 1)[1]: r for r in bench_records.scene_records(arm, scenario, self.scene)}

    def test_hard_limit_kill_without_result_and_server_tool_use_is_valid(self):
        self.cc('cc-max-a4', assistant([{'type': 'tool_use', 'name': 'Read'}]))
        r = self.records()['cc-max-a4']
        self.assertTrue(r['valid'])
        self.assertFalse(r['validity_before_rejudge']['valid'])
        self.assertEqual((r['config'], r['effective_effort']), (24, 'max'))
        self.assertFalse(r['handoffs'][0]['tokens_known'])
        self.assertIn('balance', r['handoffs'][0]['cost_basis'])
        self.assertEqual(r['started'], 100.0)

    def test_server_tool_use_in_the_killed_stream_stays_invalid(self):
        self.cc('cc-max-a1', assistant([{'type': 'server_tool_use', 'name': 'web_search'}]))
        self.cc('cc-max-a2', assistant([], {'server_tool_use': {'web_search_requests': 2}}))
        self.cc('cc-max-a3', assistant([]), checks={'model_match': False})
        r = self.records()
        for name in ('cc-max-a1', 'cc-max-a2', 'cc-max-a3'):
            self.assertFalse(r[name]['valid'], name)
        self.assertIn('server_web_requests', r['cc-max-a1']['validity']['reasons'][0])
        self.assertIn('model_match', r['cc-max-a3']['validity']['reasons'][0])

    def test_valid_handoff_with_a_killed_segment_is_scanned(self):
        result = {'hard_interrupt': True, 'started_at': 5.0, 'summary': {'result_event': True, 'segments': 2,
                                                                          'segments_without_result': 1}}
        d = self.cc('cc-low-a1', json.dumps({'type': 'result'}) + '\n',
                    checks={'server_web_requests': 0, 'valid': True}, result=result)
        write(d / 'h0/stream-1.jsonl', assistant([{'type': 'server_tool_use'}]))
        self.cc('cc-low-a2', json.dumps({'type': 'result'}) + '\n', checks={'server_web_requests': 0, 'valid': True},
                result=result)
        r = self.records()
        self.assertFalse(r['cc-low-a1']['valid'])
        self.assertTrue(r['cc-low-a2']['valid'])

    def codex(self, name, relay, rollout, instance=None, started=1.0):
        d = self.scene / name
        session = write(d / 'run/rollout.jsonl', ''.join(json.dumps({'timestamp': iso(t), 'type': a,
                                                                     'payload': {'type': b}}) + '\n'
                                                           for t, a, b in rollout))
        write(d / 'run/relay/relay.jsonl', ''.join(json.dumps(r) + '\n' for r in relay))
        write(d / 'instance.json', {'valid': False, 'started': started, 'arw_measure_exit': 0, 'prep_copy_ok': True,
                                    'arw_pause_events': [], 'continue_count': 0, **(instance or {}),
                                    'handoffs': [{'instanceId': IID, 'session': str(session), 'reviewer_active_seconds': 100.0,
                                                  'checks': CODEX_CHECKS}]})
        return d

    CUT = [{'n': 1, 'started_at': 1000.0, 'ended_at': 1010.0, 'path': '/responses', 'status': 200,
            'response_status': 'completed', 'usage': {'input_tokens': 5}},
           {'n': 2, 'started_at': 1010.1, 'ended_at': 1018.0, 'path': '/responses', 'status': 200,
            'transport_error': 'IncompleteRead'},
           {'n': 3, 'started_at': 1018.2, 'ended_at': 1030.0, 'path': '/responses', 'status': 200,
            'response_status': 'completed', 'usage': {'input_tokens': 6}}]
    ROLLOUT = [(999.0, 'response_item', 'message'), (1018.05, 'event_msg', 'token_count'),
               (1025.0, 'response_item', 'reasoning')]

    def test_stream_cut_retry_valid_and_time_excluded(self):
        self.codex('codex-max-a4', self.CUT, self.ROLLOUT)
        r = self.records('deepseek-codex', 'spec-readiness-v4.3')['codex-max-a4']
        self.assertTrue(r['valid'])
        self.assertEqual(r['handoffs'][0]['seconds'], round(100.0 - 8.1, 3))
        self.assertEqual(r['seconds_adjustment'], {'h0': -8.1})
        self.assertEqual(r['seconds'], round(100.0 - 8.1, 3))

    def test_cut_stream_written_into_the_rollout_or_other_failure_stays_invalid(self):
        self.codex('codex-low-a1', self.CUT, self.ROLLOUT + [(1012.0, 'response_item', 'reasoning')])
        self.codex('codex-low-a2', self.CUT, self.ROLLOUT, instance={'halt': ['x']})
        r = self.records('deepseek-codex', 'spec-readiness-v4.3')
        self.assertFalse(r['codex-low-a1']['valid'])
        self.assertIn('relay errors 1', ' '.join(r['codex-low-a1']['validity']['reasons']))
        self.assertFalse(r['codex-low-a2']['valid'])
        self.assertIn('halt', r['codex-low-a2']['validity']['reasons'])

    def test_cut_row_with_usage_is_an_error(self):
        relay = [dict(r) for r in self.CUT]
        relay[1]['usage'] = {'input_tokens': 9}
        self.codex('codex-max-a1', relay, self.ROLLOUT)
        with self.assertRaises(ValueError):
            self.records('deepseek-codex', 'spec-readiness-v4.3')

    def test_reclassified_verdict_kept(self):
        self.codex('sol-high-a1', [], [(999.0, 'response_item', 'message')],
                   instance={'reclassified': {'valid': True, 'by': 'Main'}, 'halt': ['x']})
        r = self.records('openai', 'code-spec-v5')['sol-high-a1']
        self.assertTrue(r['valid'])
        self.assertIn('note', r['validity']['rejudge'])

    def test_first_five_by_start_time_and_merged_cells(self):
        recs = []
        for i, (start, valid) in enumerate([(50, True), (10, True), (30, False), (20, True), (40, True), (60, True),
                                            (70, True)], 1):
            recs.append({'id': f'a{i}', 'arm': 'x', 'scenario': 's', 'config': 1, 'attempt': i, 'started': start,
                         'valid': valid})
        recs.append({'id': 'p1', 'arm': 'x', 'scenario': 's', 'config': 2, 'attempt': 1, 'started': 1, 'valid': True,
                     'pooled': True})
        recs += [{'id': f'q{i}', 'arm': 'x', 'scenario': 's', 'config': 2, 'attempt': i, 'started': 10 + i,
                  'valid': True} for i in range(1, 6)]
        bench_validity.rank_cells(recs)
        by = {r['id']: r for r in recs}
        self.assertEqual([r['id'] for r in recs if r['config'] == 1 and r['main_statistic']], ['a1', 'a2', 'a4', 'a5', 'a6'])
        self.assertFalse(by['a7']['main_statistic'])
        self.assertEqual(by['a2']['valid_rank'], 1)
        self.assertIsNone(by['a3']['valid_rank'])
        self.assertTrue(all(r['main_statistic'] for r in recs if r['config'] == 2))  # merged: every valid one
        self.assertFalse(by['q5']['first_n'])
        self.assertTrue(by['p1']['first_n'])

    def test_balance_cost(self):
        readings = [(0, 10.0), (5, 9.9), (20, 9.0), (30, 8.5)]
        runs = {'a': (1, 12, 0.3), 't': (6, 15, None), 'b': (21, 29, 0.4)}
        out = bench_validity.balance_cost(readings, runs, 't')
        self.assertEqual(out['others'], ['a'])
        self.assertAlmostEqual(out['cost'], 10.0 - 9.0 - 0.3)
        self.assertIsNone(bench_validity.balance_cost(readings, {**runs, 'a': (1, 12, None)}, 't'))


if __name__ == '__main__':
    unittest.main()
