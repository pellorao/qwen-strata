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


    def test_role_as_system_splits_role_from_user_message(self):
        note = self.base / 'note.md'
        note.write_text('MEASURE NOTE\n')
        import hashlib
        binding = {'path': str(note), 'sha256': hashlib.sha256(note.read_bytes()).hexdigest()}
        handoff = {**self.handoff, 'input': {**self.handoff['input'], 'instructions': f'ROLE in {self.root}\n',
                                             'handoff': 'HANDOFF\n'}}
        old = cs.prompt_text(handoff, binding)
        self.assertIn('ROLE in', old)
        new = cs.prompt_text(handoff, binding, role_as_system=True)
        self.assertEqual(new, 'HANDOFF\n\nMEASURE NOTE\n')
        self.assertNotIn('ROLE', new)
        self.assertTrue(old.endswith('# Handoff (the task)\n\nHANDOFF\n\nMEASURE NOTE\n'))
        work = '/var/tmp/qwen-claude/r/work'
        prompt, info = cs.stage(handoff, f'cwd {self.root}', work, self.base / 'stage', cs.role_text(handoff))
        self.assertEqual(info['system'], f'# Bound Role instructions\n\nROLE in {work}')
        self.assertNotIn(str(self.root), info['system'])

    def test_command_line_backends(self):
        base = ['--plan', 'p.json', '--out', 'o', '--model', 'deepseek-flash', '--effort', 'high', '--label', 'l',
                '--claude', 'c']
        args = cs.arguments(base + ['--backend', 'deepseek'])
        self.assertEqual((args.backend, args.host), ('deepseek', None))
        self.assertEqual(cs.arguments(base).backend, 'anthropic')
        # No flag: the plan decides (plan_role_as_system).
        self.assertIsNone(cs.arguments(base).role_as_system)
        self.assertTrue(cs.arguments(base + ['--role-as-system']).role_as_system)
        self.assertEqual(cs.arguments(base + ['--backend', 'strata', '--host', 'rtx3080ti']).host, 'rtx3080ti')
        for bad in (['--backend', 'strata'], ['--backend', 'openai']):
            with self.assertRaises(SystemExit):
                cs.arguments(base + bad)

    def test_role_placement_follows_the_plan(self):
        v1, v2 = {'fixed_conditions': {}}, {'fixed_conditions': {'claude_role_as_system': True}}
        # v1 plans keep the user-message shape unless asked; v2 plans put the Role in the system prompt by default.
        self.assertEqual((cs.plan_role_as_system(v1), cs.plan_role_as_system(v1, True)), (False, True))
        self.assertEqual((cs.plan_role_as_system(v2), cs.plan_role_as_system(v2, True)), (True, True))
        with self.assertRaisesRegex(ValueError, 'fixes claude_role_as_system'):
            cs.plan_role_as_system(v2, False)

    def test_deepseek_limits_come_from_the_plan_and_must_be_frozen(self):
        limits = {'CLAUDE_CODE_MAX_CONTEXT_TOKENS': 1048576, 'CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE': 1000000,
                  'CLAUDE_CODE_MAX_OUTPUT_TOKENS': 65536}
        plan = {'fixed_conditions': {'deepseek_claude_environment': limits}}
        self.assertEqual(cs.plan_deepseek_limits(plan, 'deepseek'), limits)
        self.assertIsNone(cs.plan_deepseek_limits(plan, 'anthropic'))
        self.assertIsNone(cs.plan_deepseek_limits({'fixed_conditions': {}}, 'deepseek'))
        draft = {'fixed_conditions': {'deepseek_claude_environment': {**limits, 'CLAUDE_CODE_MAX_OUTPUT_TOKENS': None}}}
        with self.assertRaisesRegex(ValueError, 'not frozen yet'):
            cs.plan_deepseek_limits(draft, 'deepseek')

    def test_v2_plans_fix_role_scratch_scoring_and_the_deepseek_window(self):
        root = Path(__file__).resolve().parents[1] / 'benchmarks/multi-model-v2/scenarios'
        names = ('code-spec-v5.1', 'code-standards-v5.1', 'commit-audit-v3.1', 'spec-readiness-v4.5')
        for name in names:
            fixed = json.loads((root / f'{name}.json').read_text())['fixed_conditions']
            self.assertIs(fixed['claude_role_as_system'], True, name)
            self.assertEqual(fixed['scoring'], 'r8.5', name)
            self.assertIn('reviewer-private-scratch', fixed['codex_harness_patches'], name)
            self.assertEqual(fixed['deepseek_claude_environment']['CLAUDE_CODE_MAX_CONTEXT_TOKENS'], 1048576, name)

if __name__ == '__main__':
    unittest.main()
