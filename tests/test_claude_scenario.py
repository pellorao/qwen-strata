import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.reviewer import claude_scenario as cs


class ClaudeScenarioTest(unittest.TestCase):
    """Zero-model checks of the Claude Code scenario driver: staging, path rewriting and validity checks."""
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.base, True)
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
        result['summary']['server_web_requests'] = 0
        self.assertTrue(cs.checks(result, 'claude-opus-5-5', False)['valid'])
        stopped = dict(result, exit=-15, hard_interrupt=True, summary=dict(result['summary'], result_event=False))
        self.assertTrue(cs.checks(stopped, 'claude-opus-5-5', False)['valid'])
        changed = dict(result, changed_files=['r/review.jsonl', 'package.json', '.env.local', '.git/info/exclude', 'src/x.js'])
        self.assertEqual(cs.checks(changed, 'claude-opus-5-5', False, 'r')['unexpected_changes'], ['src/x.js'])
        failed = dict(result, exit=1)
        self.assertFalse(cs.checks(failed, 'claude-opus-5-5', False)['valid'])
        broken = dict(result, summary=dict(result['summary'], sandbox_failures=3))
        self.assertEqual(cs.checks(broken, 'claude-opus-5-5', False)['sandbox_failures'], 3)
        self.assertFalse(cs.checks(broken, 'claude-opus-5-5', False)['valid'])

    def test_strata_checks_loaded_prompts_and_output_limits(self):
        from tools.reviewer import claude_headless as ch
        log = ('[strata] thinking: 53 of budget 2048 (max 8192) tokens, 66.2 tok/s, 5 s\n'
               '[strata] writing a tool call: Read: 1466 of max 8192 tokens, 86.1 tok/s, 21 s\n'
               '[strata] answering: 334 of max 8192 tokens, 91.6 tok/s, 4 s\n')
        self.assertEqual(ch.output_limits(log), {'thinking_budgets': [2048], 'max_tokens': [8192]})
        expected = cs.strata_expected('low')
        self.assertEqual((expected['thinking_budget'], expected['max_tokens']), (2048, 8192))
        self.assertEqual(cs.strata_expected('high')['max_tokens'], 24576)
        result = {'exit': 0, 'hard_interrupt': False, 'output_limits': ch.output_limits(log),
                  'summary': {'result_event': True, 'is_error': False, 'init': {'model': 'qwen3.8-flash-next-iq3_xxs'},
                              'modelUsage': {'qwen3.8-flash-next-iq3_xxs': {}}, 'service_tiers': {'not-returned': 4},
                              'server_web_requests': 0}}
        binding = {'startup_instructions': {'sha256': expected['startup_sha256']},
                   'compact_prompt_sha256': expected['compact_sha256']}
        out = cs.checks(result, 'qwen3.8-flash-next-iq3_xxs', True, None, expected, binding)
        self.assertTrue(out['valid'])
        self.assertNotIn('startup_prompt_off', out)
        self.assertFalse(cs.checks(result, 'qwen3.8-flash-next-iq3_xxs', True, None, cs.strata_expected('medium'),
                                   binding)['valid'])
        wrong = dict(binding, compact_prompt_sha256='0' * 64)
        self.assertFalse(cs.checks(result, 'qwen3.8-flash-next-iq3_xxs', True, None, expected, wrong)['valid'])
        # Without the Strata expectation a run that loaded the startup prompt stays invalid (the API arms' rule).
        self.assertFalse(cs.checks(result, 'qwen3.8-flash-next-iq3_xxs', True)['valid'])


if __name__ == '__main__':
    unittest.main()
