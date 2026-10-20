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

    def test_claude_layout_without_pause_record_and_with_a_sandbox_fault(self):
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
        self.assertFalse(r['pause_known'])
        self.assertTrue(r['handoffs'][0]['report_ok'])
        self.assertEqual(records['opus-low-a2']['validity']['status'], 'void')

    def test_spills_are_those_the_session_read(self):
        out = self.scene / 'h0'
        kept = write(out / 'session-files/p/s/tool-results/b1.txt', 'diff')
        write(out / 'session-files/p/s/tool-results/b2.txt', 'diff')
        read = {'message': {'content': [{'type': 'tool_use', 'name': 'Read',
                                         'input': {'file_path': '/var/home/.claude/projects/p/s/tool-results/b1.txt'}}]}}
        write(out / 'stream.jsonl', json.dumps(read) + '\n')
        self.assertEqual(bench_records.read_spills(out), [str(kept)])

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


if __name__ == '__main__':
    unittest.main()
