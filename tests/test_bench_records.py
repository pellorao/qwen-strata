import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.reviewer import bench_records

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


if __name__ == '__main__':
    unittest.main()
