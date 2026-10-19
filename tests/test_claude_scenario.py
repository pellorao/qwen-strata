import json
import tempfile
import unittest
from pathlib import Path

from tools.reviewer import claude_scenario as cs


class ClaudeScenarioTest(unittest.TestCase):
    """Zero-model checks of the Claude Code scenario driver: staging, path rewriting and validity checks."""
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.root = self.base / 'arw/.tmp/codex/t/_reviewer-cap/runs/u/ca/1'
        cap = self.root / '.tmp/codex/t/_commit-audit-capability'
        (cap / 'reports').mkdir(parents=True)
        self.report = cap / 'reports/review.jsonl'
        (cap / 'request.json').write_text(json.dumps({'draftPath': str(self.report)}))
        (self.root / 'src').mkdir()
        self.handoff = {'scenarioRoot': str(self.root), 'input': {'reportPath': str(self.report)}}

    def test_stage_rewrites_root_and_requests(self):
        work = '/var/tmp/qwen-claude/r/work'
        prompt = f'Request {self.root}/.tmp/codex/t/_commit-audit-capability/request.json in cwd {self.root}.'
        out, info = cs.stage(self.handoff, prompt, work, self.base / 'stage')
        self.assertNotIn(str(self.root), out)
        self.assertIn(work, out)
        self.assertEqual(info['rewritten_requests'], ['.tmp/codex/t/_commit-audit-capability/request.json'])
        request = json.loads((self.base / 'stage/.tmp/codex/t/_commit-audit-capability/request.json').read_text())
        self.assertTrue(request['draftPath'].startswith(work))
        self.assertEqual(info['report'], '.tmp/codex/t/_commit-audit-capability/reports/review.jsonl')
        with self.assertRaises(ValueError):
            cs.stage(self.handoff, 'no root here', work, self.base / 'stage2')

    def test_checks_match_rule_tiers_and_search(self):
        result = {'exit': 0, 'hard_interrupt': False,
                  'summary': {'result_event': True, 'is_error': False, 'init': {'model': 'claude-opus-5-5'},
                              'modelUsage': {'claude-opus-5-5-20261001': {}}, 'service_tiers': {'standard': 3},
                              'server_web_requests': 0}}
        self.assertTrue(cs.checks(result, 'claude-opus-5-5', False)['valid'])
        result['summary']['modelUsage'] = {'claude-opus-5-5': {}, 'claude-haiku-5-5': {}}
        self.assertFalse(cs.checks(result, 'claude-opus-5-5', False)['model_match'])
        result['summary']['modelUsage'] = {'claude-opus-5-5': {}}
        result['summary']['service_tiers'] = {'priority': 1}
        self.assertFalse(cs.checks(result, 'claude-opus-5-5', False)['valid'])
        result['summary']['service_tiers'] = {'not-returned': 2}
        result['summary']['server_web_requests'] = 1
        self.assertFalse(cs.checks(result, 'claude-opus-5-5', False)['valid'])


if __name__ == '__main__':
    unittest.main()
