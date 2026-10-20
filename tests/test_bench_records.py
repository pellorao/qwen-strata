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

    def test_spills_are_every_kept_tool_output(self):
        out = self.scene / 'h0'
        first = write(out / 'session-files/p/s/tool-results/b1.txt', 'diff')
        second = write(out / 'session-files/p/s/tool-results/b2.txt', 'diff')
        write(out / 'session-files/p/s/other/b3.txt', 'not a spill')
        self.assertEqual(bench_records.read_spills(out), [str(first), str(second)])

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


if __name__ == '__main__':
    unittest.main()
