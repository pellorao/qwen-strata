import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.reviewer import bench_records

BJ = timezone(timedelta(hours=8))
IID = 'default-42b4f896-1071-4617-bcba-e1110a1fc457-instance-1'


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value))
    return path


class RecordsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.scene = Path(self.tmp.name)
        self.report = 'finding\n'
        self.sha = hashlib.sha256(self.report.encode()).hexdigest()

    def tearDown(self):
        self.tmp.cleanup()

    def test_openai_layout(self):
        d = self.scene / 'sol-high-a2'
        report = write(d / 'copy/review-result.md', self.report)
        write(d / 'prep/selection-source.json', {'review_time_limit_seconds': 1409})
        write(d / 'prep-location.json', {'reports': {IID: {'copy': str(report)}}})
        write(d / 'instance.json', {'valid': True, 'time_limit_seconds': 1409, 'arw_pause_events': [{'at': 1}],
                                    'continue_count': 1, 'handoffs': [
            {'instanceId': IID, 'report': '/tmp/gone.md', 'report_sha256': self.sha, 'reviewer_active_seconds': 60,
             'tokens': {'uncached_input': 1, 'cached_input': 2, 'output': 3}, 'tool_calls': 4,
             'checks': {'models_returned': ['gpt-6.1-sol'], 'service_tiers': {'default': 2}}}]})
        write(self.scene / 'luna-low-a1/void.json', {'reason': 'relay'})
        (self.scene / 'luna-low-a2').mkdir()
        records = {r['id'].rsplit('/', 1)[1]: r for r in bench_records.scene_records('openai', 'code-spec-v5', self.scene)}
        r = records['sol-high-a2']
        self.assertTrue(r['valid'])
        self.assertEqual((r['config'], r['model_family'], r['style_family']), (3, 'gpt-6.1-sol', 'openai'))
        self.assertEqual(r['time_limit_seconds'], 1409)
        self.assertEqual((r['pause_known'], r['pause_count']), (True, 1))
        self.assertEqual(r['handoffs'][0]['report'], str(report))
        self.assertTrue(r['handoffs'][0]['report_ok'])
        self.assertEqual(r['tokens'], {'uncached_input': 1, 'cached_input': 2, 'output': 3})
        self.assertEqual(r['valid_rank'], 1)
        self.assertEqual(records['luna-low-a1']['validity']['status'], 'void')
        self.assertEqual(records['luna-low-a2']['validity']['status'], 'no-record')
        self.assertIsNone(records['luna-low-a1']['score'])

    def test_luna_xhigh_and_max_supplement_configurations(self):
        for name in ('luna-xhigh-a1', 'luna-max-a3'):
            write(self.scene / name / 'instance.json', {'valid': False, 'handoffs': []})
        records = {r['id'].rsplit('/', 1)[1]: r for r in bench_records.scene_records('openai', 'commit-audit-v3', self.scene)}
        self.assertEqual((records['luna-xhigh-a1']['config'], records['luna-xhigh-a1']['config_label']), (28, 'gpt-6-luna-xhigh'))
        self.assertEqual((records['luna-max-a3']['config'], records['luna-max-a3']['attempt']), (29, 3))
        with self.assertRaises(ValueError):  # xhigh is no configuration of any other model
            bench_records.base('openai', 'commit-audit-v3', self.scene / 'sol-xhigh-a1')

    def test_claude_layout_of_the_old_harness_and_with_a_sandbox_fault(self):
        d = self.scene / 'opus-low-a1'
        write(d / 'h0/outputs/.tmp/reports/review-result.md', self.report)
        write(d / 'instance.json', {'handoffs': [
            {'instanceId': IID, 'staging': {'report': '.tmp/reports/review-result.md'}, 'report_sha256': self.sha,
             'wall_seconds': 30, 'checks': {'valid': True, 'sandbox_failures': 2}}]})
        write(self.scene / 'opus-low-a2/void.json', {'void': True, 'reason': 'x'})
        records = {r['id'].rsplit('/', 1)[1]: r for r in bench_records.scene_records('anthropic', 'code-spec-v5', self.scene)}
        r = records['opus-low-a1']
        self.assertEqual(r['validity']['status'], 'harness-fault')
        self.assertFalse(r['valid'])
        # No handoff continuation: the old harness never continued an early exit, so no pause by construction.
        self.assertEqual((r['pause_known'], r['pause_count'], r['harness_generation']),
                         (True, 0, 'before execute_continued'))
        self.assertIn('by construction', r['pause_basis'])
        self.assertTrue(r['handoffs'][0]['report_ok'])
        self.assertEqual(records['opus-low-a2']['validity']['status'], 'void')

    def test_claude_pauses_recorded_or_without_basis(self):
        write(self.scene / 'opus-low-a3/instance.json', {'arw_pause_events': [{'at': 1}, {'at': 2}], 'handoffs': [
            {'instanceId': IID, 'continuation': {'arw_pause_events': []}, 'checks': {'valid': True, 'sandbox_failures': 0}}]})
        write(self.scene / 'opus-low-a4/instance.json', {'handoffs': [
            {'instanceId': IID, 'continuation': {}, 'checks': {'valid': True, 'sandbox_failures': 0}}]})
        write(self.scene / 'opus-low-a5/instance.json', {'handoffs': [
            {'instanceId': IID, 'checks': {'valid': True, 'sandbox_failures': 0}}]})
        records = bench_records.scene_records('anthropic', 'code-spec-v5', self.scene)
        r = {x['id'].rsplit('/', 1)[1]: x for x in records}
        self.assertEqual((r['opus-low-a3']['pause_known'], r['opus-low-a3']['pause_count']), (True, 2))
        self.assertEqual((r['opus-low-a4']['pause_known'], r['opus-low-a4']['pause_count']), (False, None))
        [note] = bench_records.config_notes(records)
        self.assertEqual(note['config'], 'opus-low')
        self.assertEqual(note['generations'], {'before execute_continued': 1, 'execute_continued': 2})

    def test_b_class_final_status_not_in_arw_form(self):
        def result_line(text, error=False):
            return json.dumps({'type': 'result', 'is_error': error, 'result': text}) + '\n'
        for name, streams in (('opus-low-a6', [result_line('Done.\n\n{"status":"ready"}')]),
                              ('opus-low-a7', [result_line('Done. {"status":"ready"}'), result_line('{"status":"ready"}')]),
                              ('opus-low-a8', [result_line('{"status":"incomplete","reason":"time"}')]),
                              ('opus-low-a9', [result_line('prompt too long', error=True)])):
            d = self.scene / name
            write(d / 'h0/outputs/r.md', self.report)
            for i, text in enumerate(streams):
                write(d / 'h0' / ('stream.jsonl' if i == 0 else f'stream-{i}.jsonl'), text)
            write(d / 'instance.json', {'handoffs': [
                {'instanceId': IID, 'staging': {'report': 'r.md'}, 'report_sha256': self.sha,
                 'checks': {'valid': True, 'sandbox_failures': 0}}]})
        write(self.scene / 'opus-low-a10/instance.json', {'handoffs': [
            {'instanceId': IID, 'checks': {'valid': True, 'sandbox_failures': 0}}]})
        write(self.scene / 'opus-low-a10/h0/stream.jsonl', result_line('ok, {"status":"ready"}'))  # no report: not B
        r = {x['id'].rsplit('/', 1)[1]: x for x in bench_records.scene_records('anthropic', 'code-spec-v5', self.scene)}
        self.assertEqual(r['opus-low-a6']['handoffs'][0]['final_status'], 'not-arw-form')
        self.assertEqual(r['opus-low-a6']['final_status_format_errors'], 1)
        self.assertEqual(r['opus-low-a6']['final_status_basis']['handoffs'], [0])
        for name in ('opus-low-a7', 'opus-low-a8', 'opus-low-a9', 'opus-low-a10'):  # corrected, incomplete, error, no report
            self.assertEqual(r[name]['final_status_format_errors'], 0, name)
        self.assertEqual(r['opus-low-a7']['handoffs'][0]['final_status'], 'ready')
        self.assertEqual(r['opus-low-a8']['handoffs'][0]['final_status'], 'incomplete')
        self.assertIsNone(r['opus-low-a9']['handoffs'][0]['final_status'])

    def openai_instance(self, name, fields, machine=None):
        d = self.scene / name
        write(d / 'instance.json', {'valid': True, 'handoffs': [], **fields})
        if machine is not None:
            write(d / 'run/machine.jsonl', ''.join(json.dumps(line) + '\n' for line in machine))
        return d

    def test_claude_code_tokens_come_from_the_recounted_stream_usage(self):
        def result(usage):
            return json.dumps({'type': 'result', 'is_error': False, 'result': 'x', 'duration_ms': 1, 'num_turns': 1,
                               'total_cost_usd': 0.5, 'usage': usage}) + '\n'
        d = self.scene / 'opus-low-a1'
        write(d / 'h0/stream.jsonl', result({'input_tokens': 10, 'cache_creation_input_tokens': 5,
                                             'cache_read_input_tokens': 100, 'output_tokens': 7}))
        write(d / 'h0/stream-1.jsonl', result({'input_tokens': 1, 'cache_creation_input_tokens': 0,
                                               'cache_read_input_tokens': 200, 'output_tokens': 3}))
        # the archived summary holds the last result only (made before the 2026-10-20 fix): it must not be used
        write(d / 'h0/result.json', {'summary': {'usage': {'input_tokens': 1, 'output_tokens': 3}, 'total_cost_usd': 0.5}})
        write(d / 'instance.json', {'handoffs': [{'instanceId': IID, 'checks': {'valid': True, 'sandbox_failures': 0},
                                                  'engine_tokens': {'uncached_input': 999, 'cached_input': 999, 'output': 999}}]})
        for arm, wanted in (('anthropic', (16, 300, 10)), ('strata-claude', (999, 999, 999))):
            r = bench_records.scene_records(arm, 'code-spec-v5', self.scene)[0]
            self.assertEqual(tuple(r['tokens'][c] for c in ('uncached_input', 'cached_input', 'output')), wanted)
        r = bench_records.scene_records('anthropic', 'code-spec-v5', self.scene)[0]
        self.assertEqual(r['token_source'], 'Claude Code stream result usage')
        # a handoff with no result event has unknown tokens, not zero
        write(d / 'h0/stream.jsonl', '')
        write(d / 'h0/stream-1.jsonl', '')
        r = bench_records.scene_records('anthropic', 'code-spec-v5', self.scene)[0]
        self.assertIsNone(r['tokens']['output'])
        self.assertEqual(bench_records.usage_tokens(None), None)

    def test_claude_code_tool_calls_and_speeds(self):
        use = lambda mid, tid, parent=None: json.dumps({'type': 'assistant', 'parent_tool_use_id': parent, 'message': {
            'id': mid, 'content': [{'type': 'tool_use', 'id': tid, 'name': 'Read', 'input': {}}]}}) + '\n'
        result = lambda api: json.dumps({'type': 'result', 'is_error': False, 'result': 'x', 'duration_ms': 1,
                                         'duration_api_ms': api, 'num_turns': 1, 'usage': {
                                             'input_tokens': 10, 'cache_creation_input_tokens': 10,
                                             'cache_read_input_tokens': 100, 'output_tokens': 100}}) + '\n'
        d = self.scene / 'opus-low-a1'
        # t1 twice (a message repeated per block), t3 a subagent's call; the continued segment adds t4
        write(d / 'h0/stream.jsonl', use('m1', 't1') + use('m1', 't1') + use('m2', 't2') + use('m3', 't3', 'p')
              + result(4000))
        write(d / 'h0/stream-1.jsonl', use('m4', 't4') + result(1000))
        write(d / 'h0/result.json', {'engine_requests': [
            {'input': 1100, 'cached': 100, 'uncached': 1000, 'prompt_ms': 500.0, 'output': 80, 'decode_ms': 1000.0}]})
        write(d / 'instance.json', {'handoffs': [{'instanceId': IID, 'wall_seconds': 20,
                                                  'checks': {'valid': True, 'sandbox_failures': 0},
                                                  'engine_tokens': {'uncached_input': 1000, 'cached_input': 100,
                                                                    'output': 80}}]})
        r = bench_records.scene_records('anthropic', 'code-spec-v5', self.scene)[0]
        self.assertEqual(r['tool_calls'], 3)
        # tokens 40 uncached / 200 output over 20 s; output over 5 s of API time, a lower bound; no input speed
        self.assertEqual(r['speeds'], {'task_input': 2.0, 'task_output': 10.0, 'engine_input': None, 'engine_output': 40.0})
        self.assertEqual(r['speed_lower_bounds'], ['engine_output'])
        import shutil
        shutil.copytree(d, self.scene / 'strata-low-a1')
        s = bench_records.instance_record('strata-claude', 'code-spec-v5', self.scene / 'strata-low-a1')
        self.assertEqual(s['speeds'], {'task_input': 50.0, 'task_output': 4.0, 'engine_input': 2000.0, 'engine_output': 80.0})
        self.assertEqual(s['speed_lower_bounds'], [])
        self.assertEqual(s['speed_parts']['engine_input'], {'tokens': 1000, 'seconds': 0.5})
        # a segment without result: API time unknown, so the output speed is unknown, not a guess
        write(d / 'h0/stream-1.jsonl', use('m4', 't4'))
        r = bench_records.scene_records('anthropic', 'code-spec-v5', self.scene)[0]
        self.assertIsNone(r['speeds']['engine_output'])
        self.assertEqual(r['speed_lower_bounds'], ['task_input', 'task_output'])

    def test_codex_tool_calls_and_speeds(self):
        rollout = write(self.scene / 'rollout.jsonl', ''.join(json.dumps(e) + '\n' for e in [
            {'type': 'response_item', 'payload': {'type': 'function_call'}},
            {'type': 'response_item', 'payload': {'type': 'custom_tool_call'}},
            {'type': 'response_item', 'payload': {'type': 'message'}}]))
        write(self.scene / 'schedule.jsonl', json.dumps({'event': 'done', 'out': 'codex-strata-low-a1', 'kind': 'valid'}) + '\n')
        d = self.scene / 'codex-strata-low-a1'
        write(d / 'run/results.json', [{'instanceId': IID, 'report_sha256': self.sha, 'review_work_seconds': 10,
                                        'arw_pause_events': [], 'continue_count': 0,
                                        'engine_tokens': {'uncached_input': 500, 'cached_input': 0, 'output': 50},
                                        'runtime_result': {'threadId': 'root'},
                                        'cost': {'histories': [{'thread_id': 'g', 'path': str(rollout)},
                                                               {'thread_id': 'root', 'path': str(rollout)}]},
                                        'engine_requests': [{'uncached': 500, 'cached': 0, 'output': 50,
                                                             'prompt_ms': 250.0, 'decode_ms': 500.0}]}])
        r = bench_records.scene_records('strata-codex', 'commit-audit-v3', self.scene)[0]
        self.assertEqual(r['tool_calls'], 2)
        self.assertEqual(r['speeds'], {'task_input': 50.0, 'task_output': 5.0, 'engine_input': 2000.0, 'engine_output': 100.0})
        o = self.scene / 'sol-low-a1'
        write(o / 'instance.json', {'valid': True, 'handoffs': [
            {'instanceId': IID, 'reviewer_active_seconds': 10, 'tool_calls': 4,
             'tokens': {'uncached_input': 100, 'cached_input': 0, 'output': 60}}]})
        write(o / 'run/relay/relay.jsonl', ''.join(json.dumps(x) + '\n' for x in [
            {'started_at': 0, 'ended_at': 0, 'status': 426},
            {'started_at': 1, 'ended_at': 3, 'usage': {'output_tokens': 40}},
            {'started_at': 4, 'ended_at': 5, 'usage': {'output_tokens': 20}}]))
        r = bench_records.instance_record('openai', 'code-spec-v5', o)
        self.assertEqual(r['speeds'], {'task_input': 10.0, 'task_output': 6.0, 'engine_input': None, 'engine_output': 20.0})
        self.assertIn('2 requests', r['speed_basis']['engine'])
        # numerator and denominator kept for pooling: relay output 60 over request seconds 3
        self.assertEqual(r['speed_parts'], {'task_input': {'tokens': 100, 'seconds': 10}, 'task_output': {'tokens': 60, 'seconds': 10},
                                            'engine_input': None, 'engine_output': {'tokens': 60, 'seconds': 3}})
        (o / 'run/relay/relay.jsonl').unlink()
        r = bench_records.instance_record('openai', 'code-spec-v5', o)
        self.assertIsNone(r['speeds']['engine_output'])
        self.assertIsNone(r['speed_parts']['engine_output'])

    def test_codex_api_tokens_lost_at_a_hard_interrupt_come_from_the_relay_as_a_lower_bound(self):
        o = self.scene / 'luna-xhigh-a5'
        write(o / 'instance.json', {'valid': True, 'handoffs': [
            {'instanceId': IID, 'reviewer_active_seconds': 100, 'tool_calls': 4, 'tokens': None}]})
        rows = [{'method': 'GET', 'started_at': 0, 'ended_at': 0, 'status': 426, 'websocket_refused': True},
                {'method': 'POST', 'started_at': 1, 'ended_at': 3,
                 'usage': {'input_tokens': 500, 'input_tokens_details': {'cached_tokens': 400}, 'output_tokens': 40}},
                {'method': 'POST', 'started_at': 4, 'ended_at': 5,
                 'usage': {'input_tokens': 300, 'output_tokens': 10}},
                {'method': 'POST', 'started_at': 6, 'ended_at': 7, 'status': 200}]  # cut by the interrupt
        write(o / 'run/relay/relay.jsonl', ''.join(json.dumps(x) + '\n' for x in rows))
        r = bench_records.instance_record('openai', 'commit-audit-v3', o)
        self.assertEqual(r['tokens'], {'uncached_input': 400, 'cached_input': 400, 'output': 50})
        self.assertEqual(r['token_source'], 'API usage (relay log sum, 2 requests; lower bound: 1 request(s) without usage)')
        self.assertEqual(r['speeds']['task_output'], 0.5)
        self.assertEqual(sorted(r['speed_lower_bounds']), ['engine_output', 'task_input', 'task_output'])
        write(o / 'run/relay/relay.jsonl', ''.join(json.dumps(x) + '\n' for x in rows[:3]))
        self.assertEqual(bench_records.instance_record('openai', 'commit-audit-v3', o)['token_source'],
                         'API usage (relay log sum, 2 requests)')
        # Tokens the handoffs do carry are kept, whatever the relay says.
        write(o / 'instance.json', {'valid': True, 'handoffs': [
            {'instanceId': IID, 'reviewer_active_seconds': 100, 'tokens': {'uncached_input': 1, 'cached_input': 2,
                                                                         'output': 3}}]})
        r = bench_records.instance_record('openai', 'commit-audit-v3', o)
        self.assertEqual((r['tokens']['output'], r['token_source']), (3, 'API usage (relay)'))

    def test_codex_api_largest_response_output_and_incomplete_reasons_from_the_relay(self):
        o = self.scene / 'codex-high-a1'
        write(o / 'instance.json', {'valid': True, 'handoffs': [
            {'instanceId': IID, 'reviewer_active_seconds': 100, 'tool_calls': 4, 'tokens': None}]})
        rows = [{'method': 'POST', 'started_at': 1, 'ended_at': 3, 'response_status': 'completed',
                 'usage': {'input_tokens': 500, 'output_tokens': 7328}},
                {'method': 'POST', 'started_at': 4, 'ended_at': 5, 'response_status': 'incomplete',
                 'incomplete_details': {'reason': 'max_output_tokens'}, 'usage': {'input_tokens': 9, 'output_tokens': 8192}},
                {'method': 'POST', 'started_at': 6, 'ended_at': 7, 'response_status': 'incomplete'}]  # reason not kept
        write(o / 'run/relay/relay.jsonl', ''.join(json.dumps(x) + '\n' for x in rows))
        r = bench_records.instance_record('deepseek-codex', 'commit-audit-v3', o)
        self.assertEqual((r['max_response_output_tokens'], r['incomplete_responses'], r['incomplete_reasons']),
                         (8192, 2, {'max_output_tokens': 1, 'unknown': 1}))
        write(o / 'run/relay/relay.jsonl', json.dumps(rows[0]) + '\n')
        r = bench_records.instance_record('deepseek-codex', 'commit-audit-v3', o)
        self.assertEqual((r['max_response_output_tokens'], r['incomplete_responses'], r['incomplete_reasons']), (7328, 0, {}))
        (o / 'run/relay/relay.jsonl').unlink()
        self.assertIsNone(bench_records.relay_output_limits(o)['incomplete_responses'])  # no log: unknown, not 0

    def test_openai_pauses_rebuilt_from_the_flag_and_the_machine_log(self):
        notice = lambda mid: {'ok': True, 'result': {'notifications': [
            {'type': 'message', 'messageId': mid, 'text': bench_records.ARW_PAUSE_PREFIX + '10 turns.'}]}}
        self.openai_instance('sol-low-a1', {'arw_pause': False}, [{'ok': True, 'result': {}}])
        self.openai_instance('sol-low-a2', {'arw_pause': {'at': 1}}, [notice('m1'), notice('m1')])
        self.openai_instance('sol-low-a3', {'arw_pause': False}, [notice('m1')])  # flag and log disagree
        self.openai_instance('sol-low-a4', {'arw_pause': False})  # no machine log
        self.openai_instance('sol-low-a5', {}, [{'ok': True}])  # no flag
        r = {x['id'].rsplit('/', 1)[1]: x for x in bench_records.scene_records('openai', 'code-spec-v5', self.scene)}
        self.assertEqual((r['sol-low-a1']['pause_known'], r['sol-low-a1']['pause_count']), (True, 0))
        self.assertIn('machine.jsonl 0', r['sol-low-a1']['pause_basis'])
        self.assertEqual((r['sol-low-a2']['pause_known'], r['sol-low-a2']['pause_count']), (True, 1))
        for name in ('sol-low-a3', 'sol-low-a4', 'sol-low-a5'):
            self.assertFalse(r[name]['pause_known'], name)

    def test_spills_are_those_a_tool_call_names(self):
        out = self.scene / 'h0'
        read = write(out / 'session-files/p/s/tool-results/b1.txt', 'diff')
        catted = write(out / 'session-files/p/s/tool-results/b2.txt', 'diff')
        write(out / 'session-files/p/s/tool-results/b3.txt', 'diff')  # only announced, never viewed
        events = [{'message': {'content': [{'type': 'tool_use', 'name': 'Read',
                                            'input': {'file_path': '/v/.claude/projects/p/s/tool-results/b1.txt'}}]}},
                  {'message': {'content': [{'type': 'tool_use', 'name': 'Bash',
                                            'input': {'command': 'cat -n /v/p/s/tool-results/b2.txt | sed -n 1,9p'}}]}},
                  {'message': {'content': [{'type': 'tool_result',
                                            'content': 'Output too large, saved to: /v/p/s/tool-results/b3.txt'}]}}]
        write(out / 'stream.jsonl', ''.join(json.dumps(e) + '\n' for e in events))
        self.assertEqual(bench_records.read_spills(out), [str(read), str(catted)])

    def test_strata_codex_layout(self):
        write(self.scene / 'schedule.jsonl', json.dumps({'event': 'done', 'out': 'codex-strata-low-a1', 'kind': 'valid'}) + '\n')
        d = self.scene / 'codex-strata-low-a1'
        write(d / 'report/1-review.jsonl', self.report)
        write(d / 'run/results.json', [{'instanceId': IID, 'report': str(d / 'gone.jsonl'), 'report_sha256': self.sha,
                                        'review_work_seconds': 10, 'arw_pause_events': [], 'continue_count': 0}])
        (self.scene / 'codex-strata-low-a2').mkdir()
        records = {r['id'].rsplit('/', 1)[1]: r for r in bench_records.scene_records('strata-codex', 'commit-audit-v3', self.scene)}
        r = records['codex-strata-low-a1']
        self.assertTrue(r['valid'])
        self.assertEqual(r['config'], 10)
        self.assertEqual((r['pause_known'], r['pause_count']), (True, 0))
        self.assertTrue(r['handoffs'][0]['report_ok'])
        self.assertIsNone(r['time_limit_seconds'])
        self.assertEqual(records['codex-strata-low-a2']['validity']['status'], 'running')

    def test_strata_codex_pauses_rebuilt_from_the_machine_log(self):
        write(self.scene / 'schedule.jsonl', '')
        for name, machine in (('codex-strata-low-a1', ''), ('codex-strata-low-a2', None)):
            d = self.scene / name
            write(d / 'run/results.json', [{'instanceId': IID, 'report_sha256': self.sha}])
            if machine is not None:
                write(d / 'run/machine.jsonl', machine)
        r = {x['id'].rsplit('/', 1)[1]: x for x in bench_records.scene_records('strata-codex', 'commit-audit-v3', self.scene)}
        self.assertEqual((r['codex-strata-low-a1']['pause_known'], r['codex-strata-low-a1']['pause_count']), (True, 0))
        self.assertFalse(r['codex-strata-low-a2']['pause_known'])


    # Event shapes from real runs (window-dim pilot 2026-10-24, trimmed): a Codex rollout line {"type": "compacted",
    # "payload": {"message", "replacement_history", ...}} and a Claude Code stream line {"type": "system", "subtype":
    # "compact_boundary", "uuid", "session_id", "compact_metadata": {"trigger", "pre_tokens", ...}}.
    def test_codex_compactions_from_the_root_rollout(self):
        compacted = lambda: json.dumps({'type': 'compacted', 'payload': {'message': 'summary', 'replacement_history': []}}) + '\n'
        other = json.dumps({'type': 'response_item', 'payload': {'type': 'message', 'content': 'the word "compacted"'}}) + '\n'
        root = write(self.scene / 'root.jsonl', compacted() + other + compacted())
        guardian = write(self.scene / 'guardian.jsonl', compacted())
        write(self.scene / 'schedule.jsonl', json.dumps({'event': 'done', 'out': 'codex-strata-low-a1', 'kind': 'valid'}) + '\n')
        d = self.scene / 'codex-strata-low-a1'
        entry = lambda path: {'instanceId': IID, 'report_sha256': self.sha, 'review_work_seconds': 10,
                              'runtime_result': {'threadId': 'root'},
                              'cost': {'histories': [{'thread_id': 'g', 'path': str(guardian)},
                                                     {'thread_id': 'root', 'path': str(path)}]}}
        write(d / 'run/results.json', [entry(root), entry(guardian)])
        r = bench_records.scene_records('strata-codex', 'commit-audit-v3', self.scene)[0]
        self.assertEqual([h['compactions'] for h in r['handoffs']], [2, 1])
        self.assertEqual((r['compactions'], r['compactions_source']), (3, 'Codex root rollout compacted events'))
        # one handoff without its rollout: unknown, never 0
        write(d / 'run/results.json', [entry(root), entry(self.scene / 'gone.jsonl')])
        r = bench_records.scene_records('strata-codex', 'commit-audit-v3', self.scene)[0]
        self.assertEqual([h['compactions'] for h in r['handoffs']], [2, None])
        self.assertIsNone(r['compactions'])
        # OpenAI arm: the rollout recorded under the prep is read from the prep copy; else run_one's own count
        o = self.scene / 'sol-low-a1'
        write(o / 'prep/codex/rollout.jsonl', compacted())
        write(o / 'prep-location.json', {'prep': '/nonexistent/prep-x', 'copied_to': str(o / 'prep')})
        hand = {'instanceId': IID, 'reviewer_active_seconds': 10, 'session': '/nonexistent/prep-x/codex/rollout.jsonl',
                'compactions': 5, 'tokens': {'uncached_input': 1, 'cached_input': 0, 'output': 1}}
        write(o / 'instance.json', {'valid': True, 'handoffs': [hand]})
        r = bench_records.instance_record('openai', 'code-spec-v5', o)
        self.assertEqual((r['compactions'], r['handoffs'][0]['compactions_source']), (1, 'Codex root rollout compacted events'))
        (o / 'prep/codex/rollout.jsonl').unlink()
        r = bench_records.instance_record('openai', 'code-spec-v5', o)
        self.assertEqual(r['compactions'], 5)
        self.assertIn('run_one', r['compactions_source'])
        hand.pop('compactions')
        write(o / 'instance.json', {'valid': True, 'handoffs': [hand]})
        r = bench_records.instance_record('openai', 'code-spec-v5', o)
        self.assertIsNone(r['compactions'])
        self.assertEqual(r['compactions_source'], 'no root rollout and no recorded count')

    def test_claude_code_compactions_from_compact_boundary_events(self):
        boundary = lambda uuid, parent=None: json.dumps({
            'type': 'system', 'subtype': 'compact_boundary', 'uuid': uuid, 'session_id': 's', 'parent_tool_use_id': parent,
            'compact_metadata': {'trigger': 'auto', 'pre_tokens': 99368, 'post_tokens': 7227}}) + '\n'
        result = json.dumps({'type': 'result', 'is_error': False, 'result': 'x', 'duration_ms': 1, 'num_turns': 1,
                             'usage': {'input_tokens': 1, 'output_tokens': 1}}) + '\n'
        d = self.scene / 'opus-low-a1'
        # b1 repeated, b3 a subagent's; the continued segment adds b4
        write(d / 'h0/stream.jsonl', boundary('b1') + boundary('b1') + boundary('b2') + boundary('b3', 'p') + result)
        write(d / 'h0/stream-1.jsonl', boundary('b4') + result)
        write(d / 'h1/stream.jsonl', result)
        write(d / 'instance.json', {'handoffs': [{'instanceId': IID, 'checks': {'valid': True, 'sandbox_failures': 0}},
                                                 {'instanceId': IID, 'checks': {'valid': True, 'sandbox_failures': 0}}]})
        r = bench_records.scene_records('anthropic', 'code-spec-v5', self.scene)[0]
        self.assertEqual([h['compactions'] for h in r['handoffs']], [3, 0])
        self.assertEqual((r['compactions'], r['compactions_source']), (3, 'Claude Code stream compact_boundary events'))
        (d / 'h1/stream.jsonl').unlink()  # no stream: unknown, never 0
        r = bench_records.scene_records('anthropic', 'code-spec-v5', self.scene)[0]
        self.assertEqual([h['compactions'] for h in r['handoffs']], [3, None])
        self.assertIsNone(r['compactions'])


class ScenarioRepositoriesTest(unittest.TestCase):
    def test_marker_finds_every_layout_and_its_report_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp) / 'arw/.tmp/codex/sid/_reviewer-cap/runs/r1'
            wanted = [runs / 'ca/1', runs / 'ca/2', runs / 'sr/artifact-promotion/1', runs / 'sr/runtime-migration/3']
            for repo in wanted:
                write(repo / '.prepared', 'x')
                write(repo / '.tmp/codex/s/i/reports/report.md', 'r')
                write(repo / 'nested/.prepared', 'not a repository: below a found one')
            (runs / 'sr/empty-handoff').mkdir(parents=True)
            write(runs / 'ca/stray/AGENTS.md', 'no marker')
            repos = bench_records.scenario_repositories(Path(tmp))
            self.assertEqual(repos, sorted(wanted))
            self.assertEqual(bench_records.report_directories(repos),
                             sorted(r / '.tmp/codex/s/i/reports' for r in wanted))
            # the old fixed-depth glob saw only the shallow layout
            old = [d for d in Path(tmp).glob('arw/.tmp/codex/*/_reviewer-cap/runs/*/*/*') if (d / '.tmp').is_dir()]
            self.assertEqual(sorted(old), wanted[:2])


class CostTest(unittest.TestCase):
    def test_claude_cost_sums_handoffs_and_killed_segment_is_unknown(self):
        record = {'arm': 'anthropic', 'handoffs': [{'cost_usd': 0.25}, {'cost_usd': 0.5}], 'validity': {}}
        self.assertEqual(bench_records.handoff_cost_usd(record), 0.75)
        record['handoffs'][1]['cost_usd'] = None
        self.assertIsNone(bench_records.handoff_cost_usd(record))
        record['handoffs'][1]['cost_usd'] = 0.5
        record['validity'] = {'rejudge': {'handoffs': [{'segments_without_result': 1}]}}
        self.assertIsNone(bench_records.handoff_cost_usd(record))
        self.assertIsNone(bench_records.handoff_cost_usd({**record, 'arm': 'deepseek-claude', 'validity': {}}))

    def test_deepseek_cost_prefers_request_time_price(self):
        event = {'tokens': [1, 2, 3], 'cny': 0.3, 'cny_request_time': 0.2}
        self.assertEqual(bench_records.deepseek_cost({}, event)[0], 0.2)
        self.assertEqual(bench_records.deepseek_cost({}, {'tokens': [1], 'cny': 0.3})[0], 0.3)
        self.assertIsNone(bench_records.deepseek_cost({}, {'tokens': [0], 'cny': 0.3})[0])
        self.assertIsNone(bench_records.deepseek_cost({}, None)[0])

    def test_old_event_is_repriced_per_request_from_the_relay_log(self):
        peak = datetime(2026, 10, 21, 10, 0, tzinfo=BJ).timestamp()
        off = datetime(2026, 10, 21, 21, 0, tzinfo=BJ).timestamp()
        usage = {'input_tokens': 2000000, 'input_tokens_details': {'cached_tokens': 1000000}, 'output_tokens': 100000}
        with tempfile.TemporaryDirectory() as tmp:
            relay = Path(tmp) / 'run/relay/relay.jsonl'
            write(relay, ''.join(json.dumps({'started_at': t, 'usage': usage}) + '\n' for t in (peak, off)) +
                  json.dumps({'started_at': off, 'usage': None}) + '\n')
            event = {'cfg': 'codex-low', 'tokens': [2000000, 2000000, 200000], 'cny': 9.0}
            # peak: 1M x 0.04 + 1M x 2 + 0.1M x 8; off-peak: 1M x 0.02 + 1M x 1 + 0.1M x 4
            wanted = 0.04 + 2.0 + 0.8 + 0.02 + 1.0 + 0.4
            self.assertAlmostEqual(bench_records.request_time_cost(Path(tmp), event), wanted)
            cny, basis = bench_records.deepseek_cost({}, event, Path(tmp))
            self.assertEqual(cny, round(wanted, 4))
            self.assertIn('relay log', basis)

    def test_old_claude_code_event_is_priced_at_start_and_at_peak_across_a_boundary(self):
        end = datetime(2026, 10, 21, 20, 0, tzinfo=BJ)
        event = {'cfg': 'cc-low', 'tokens': [1000000, 1000000, 1000000], 'cny': 9.0, 'wall': 600,
                 't': end.isoformat(), 'abandoned_requests': 0}
        self.assertAlmostEqual(bench_records.request_time_cost(None, event), 0.02 + 1.0 + 4.0)
        crossing = dict(event, t=datetime(2026, 10, 21, 18, 5, tzinfo=BJ).isoformat())  # start 17:55, peak to off-peak
        self.assertAlmostEqual(bench_records.request_time_cost(None, crossing), 0.04 + 2.0 + 8.0)

    def test_old_event_without_relay_keeps_the_old_figure_and_says_so(self):
        event = {'cfg': 'codex-low', 'tokens': [1, 2, 3], 'cny': 0.3}
        cny, basis = bench_records.deepseek_cost({}, event, Path('/nonexistent/x/y'))
        self.assertEqual(cny, 0.3)
        self.assertIn('priced at instance start', basis)

    def test_cost_lower_bound_follows_reminder_interrupts(self):
        classified = {'validity': {'rejudge': {'applied': True, 'reminder_interrupts': [{'row': 3}]}}}
        self.assertTrue(bench_records.cost_lower_bound(classified, {}))
        self.assertFalse(bench_records.cost_lower_bound({'validity': {'rejudge': {'applied': True, 'reminder_interrupts': []}}},
                                                        {'abandoned_requests': 2}))
        self.assertTrue(bench_records.cost_lower_bound({'validity': {}}, {'abandoned_requests': 2}))
        self.assertFalse(bench_records.cost_lower_bound({'validity': {}}, None))

    def test_usd_follows_the_official_price_ratio_not_a_market_rate(self):
        for mix in ([5, 0, 0], [0, 5, 0], [0, 0, 5], [1000000, 20000, 3000]):
            self.assertAlmostEqual(bench_records.usd_per_cny(mix), 0.15)
        self.assertIsNone(bench_records.usd_per_cny([0, 0, 0]))
        peak = datetime(2026, 10, 21, 10, 0, tzinfo=BJ).timestamp()
        usage = {'input_tokens': 2000000, 'input_tokens_details': {'cached_tokens': 1000000}, 'output_tokens': 100000}
        with tempfile.TemporaryDirectory() as tmp:
            write(Path(tmp) / 'run/relay/relay.jsonl', json.dumps({'started_at': peak, 'usage': usage}) + '\n')
            event = {'cfg': 'codex-low', 'tokens': [1000000, 1000000, 100000], 'cny': 9.0}
            usd, basis = bench_records.deepseek_usd(2.84, event, Path(tmp))
            self.assertAlmostEqual(usd, 0.006 + 0.3 + 0.12)  # peak table: 1M x 0.006 + 1M x 0.3 + 0.1M x 1.2
            self.assertIn('USD price table', basis)

    def test_usd_without_a_relay_scales_the_cny_total(self):
        event = {'cfg': 'cc-low', 'tokens': [1000000, 1000000, 1000000]}  # no wall: cannot be priced by request
        usd, basis = bench_records.deepseek_usd(10.0, event)
        self.assertAlmostEqual(usd, 1.5)
        self.assertIn('instance tokens', basis)
        usd, basis = bench_records.deepseek_usd(2.0, {'tokens': [0]}, arm_tokens=[3, 2, 1])
        self.assertAlmostEqual(usd, 0.3)
        self.assertIn('whole DeepSeek arm', basis)
        self.assertIsNone(bench_records.deepseek_usd(2.0, None)[0])
        self.assertIsNone(bench_records.deepseek_usd(None, event)[0])


if __name__ == '__main__':
    unittest.main()
