import json
import tempfile
import unittest
from pathlib import Path

from tools.reviewer import benchmark_export as be
from tools.reviewer import benchmark_summary as bs
from tests.test_benchmark_summary import SCENARIO, full_design, ranked, record


def handoff(k=0, **extra):
    base = {'k': k, 'sub_scenario': 'default', 'seconds': 600.0, 'tokens': {'uncached_input': 900, 'cached_input': 100,
                                                                              'output': 30},
            'tool_calls': 5, 'api_seconds': 100.0, 'final_status': 'ready', 'continuation_stop': None,
            'report': '/home/someone/work/report.md', 'instanceId': 'x', 'session': 's'}
    base.update(extra)
    return base


def synthetic_summary():
    records = full_design()
    for r in records:
        if r['arm'] == 'anthropic':
            r['handoffs'] = [handoff(api_usage={'cache_creation_input_tokens': 50,
                                                'cache_creation': {'ephemeral_1h_input_tokens': 40,
                                                                   'ephemeral_5m_input_tokens': 10}},
                                     cost_usd=0.5)]
        elif r['arm'] == 'deepseek-claude':
            r['handoffs'] = [handoff(cost_usd=0.9)]  # Anthropic-priced harness figure: never a cost
            r['cost_cny'] = 0.2
        elif r['arm'] == 'strata-claude':
            r['handoffs'] = [handoff(cost_usd=2.0)]
    # Strata cell 10: 5 preregistered plus an extra run and a late invalid one (phase-2 material).
    records.append(record(10, 6, 0.4, started=7000.0))
    records.append(record(10, 7, None, valid=False, started=8000.0))
    records = ranked(records)
    for r in records:
        r['score_status'] = 'final' if r['valid'] else None
        r['model_failure_handoffs'] = [0] if r['id'].endswith('deepseek-flash-low-a1') and r['arm'] == 'deepseek-codex' else []
    return bs.compact(bs.summarize(records))


class SafetyTest(unittest.TestCase):
    BAD = {
        'ipv4': 'listen on 192.168.1.20:8000',
        'unix-path': 'see /home/user/x', 'mnt': 'C drive at /mnt/c/Users', 'var': '/var/tmp/run',
        'windows-path': r'C:\Users\someone', 'wsl': r'\\wsl$\Ubuntu',
        'uuid': '3f2a6c1e-9b1d-4c1e-8f00-1234567890ab', 'request-id': 'req_011CXYZabc123456',
        'message-id': 'msg_01ABCDEFGHJK', 'secret': 'sk-abcdefghijklmnop1234', 'bearer': 'Authorization: Bearer abc',
        'assignment': 'api_key = xyz', 'private-file': 'project.private.toml', 'state': 'under .state/ dir',
        'email': 'someone@example.com', 'url': 'https://example.com/x', 'localhost': 'http on localhost',
        'home': 'path ~/x',
    }
    GOOD = ['0.163.0', '2.1.303', 'v0.1.45', 'claude-opus-5-5', 'gpt-6.1-sol', 'deepseek-flash',
            'qwen3.8-flash-next-iq3_xxs', '2026-10-19T16:29:33.967505+00:00', 'high requested as medium, T=344',
            'https://api.deepseek.com/anthropic', 'Claude Code stream result usage', 'API usage (relay)',
            'N / P for N >= 0', 'read-only permissions', 'rtx3080ti', 'IQ3_XXS', '12 GiB', 'x / y = 0.5']

    def test_each_pattern_is_caught(self):
        for name, text in self.BAD.items():
            with self.subTest(name=name):
                self.assertTrue(be.safety_hits({'note': text}, users={'pello'}), text)

    def test_ordinary_values_pass(self):
        for text in self.GOOD:
            with self.subTest(text=text):
                self.assertEqual(be.safety_hits({'note': text}, users={'pello'}), [])

    def test_user_name_and_forbidden_keys(self):
        self.assertTrue(be.safety_hits({'note': 'by pello today'}, users={'pello'}))
        for key in ('report', 'findings', 'sessionId', 'threadId', 'instanceId', 'answerKey', 'dir', 'path'):
            with self.subTest(key=key):
                self.assertTrue(be.safety_hits({'x': [{key: 1}]}, users=set()))
        self.assertEqual(be.safety_hits({'reportConversions': 1, 'pathless': 2}, users=set()), [])

    def test_write_refuses_and_writes_nothing(self):
        summary = synthetic_summary()
        first = summary['scenarios'][SCENARIO]['instances'][0]
        first['validity'] = {'status': 'invalid', 'reasons': ['log at /home/someone/run.log']}
        with tempfile.TemporaryDirectory() as folder:
            src, out = Path(folder) / 'summary.json', Path(folder) / 'out.json'
            src.write_text(json.dumps(summary))
            with self.assertRaises(SystemExit):
                be.write(src, out, diagnostic_path=None)
            self.assertFalse(out.exists())


class BuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = synthetic_summary()
        cls.result = be.build(cls.summary, 'sha', diagnostic={
            f'anthropic/{SCENARIO}/opus-low-a2': 1}, generated='2026-10-22T00:00:00+00:00')
        cls.items = {i['id']: i for i in cls.result['instances']}

    def test_result_is_publishable_and_has_no_aggregates(self):
        self.assertEqual(be.safety_hits(self.result), [])
        text = json.dumps(self.result)
        for key in ('"mean"', '"p_holm"', '"verdict"', '"n_valid"', '"weights"', '"ci95"', 'handoff_metrics'):
            self.assertNotIn(key, text)
        self.assertNotIn('/home/', text)
        self.assertEqual(self.result['meta']['benchmarkVersion'], '2.0')
        self.assertEqual(len(self.result['comparisonDesign']['pairs']), 25)
        self.assertEqual(len(self.result['instances']), 27 * 5 + 2)

    def test_instance_fields(self):
        opus = self.items[f'anthropic/{SCENARIO}/opus-low-a1']
        self.assertEqual(opus['configKey'], 'claude-code/opus/low')
        self.assertEqual(opus['cost'], {'usd': 0.5, 'cny': None, 'lowerBound': False, 'basis': 'anthropic'})
        self.assertEqual(opus['harnessReportedCostUsd'], 0.5)
        self.assertEqual((opus['tokens']['cacheWriteInput'], opus['tokens']['cacheWrite1h']), (50, 40))
        self.assertEqual(opus['handoffs'][0]['finalStatus'], 'ready')
        self.assertTrue(opus['startedAt'].endswith('+00:00'))
        diagnostic = self.items[f'anthropic/{SCENARIO}/opus-low-a2']['scoring']
        self.assertEqual((diagnostic['status'], diagnostic['diagnosticEnvironmentQueries']), ('diagnostic', 1))
        failure = self.items[f'deepseek-codex/{SCENARIO}/deepseek-flash-low-a1']['scoring']
        self.assertEqual(failure['status'], 'modelFailure')
        ds_cc = self.items[f'deepseek-claude/{SCENARIO}/deepseek-flash-low-a1']
        self.assertEqual(ds_cc['cost']['cny'], 0.2)
        self.assertEqual(ds_cc['harnessReportedCostUsd'], 0.9)
        self.assertIsNone(ds_cc['tokens']['cacheWriteInput'])
        strata_cc = self.items[f'strata-claude/{SCENARIO}/strata-iq3_xxs-low-a1']
        self.assertIsNone(strata_cc['cost'])  # local model: no cost, only the harness figure
        self.assertEqual(strata_cc['harnessReportedCostUsd'], 2.0)
        self.assertIsNone(self.items[f'openai/{SCENARIO}/gpt-6.1-sol-low-a1']['cost'])

    def test_stages(self):
        stage = {i['id'].split('-')[-1]: i['selection']['stage'] for i in self.result['instances']
                 if i['configNumber'] == 10}
        self.assertEqual(stage, {'a1': 'preregistered', 'a2': 'preregistered', 'a3': 'preregistered',
                                 'a4': 'preregistered', 'a5': 'preregistered', 'a6': 'extra', 'a7': 'extra'})

    def test_configs_are_descriptive(self):
        keys = {c['key'] for c in self.result['configs']}
        self.assertIn('codex/strata-iq3_xxs/low', keys)
        self.assertIn('claude-code/deepseek-flash/max', keys)
        for c in self.result['configs']:
            self.assertFalse({'n', 'mean', 'n_valid', 'invalid'} & set(c))

    def test_variants_list_only_changed_instances(self):
        changed = json.loads(json.dumps(self.summary))
        row = changed['scenarios'][SCENARIO]['instances'][0]
        row['score'] = 0.123
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'variant.json'
            path.write_text(json.dumps(changed))
            out = be.variants([('A1', path)], self.summary)
            self.assertEqual([(o['id'], o['score']) for o in out[0]['overrides']], [(row['id'], 0.123)])
            row['valid_rank'] = 99
            path.write_text(json.dumps(changed))
            with self.assertRaises(ValueError):
                be.variants([('A1', path)], self.summary)
            with self.assertRaises(ValueError):
                be.variants([('nope', path)], self.summary)


class SummaryFieldsTest(unittest.TestCase):
    def test_handoff_metrics_drop_paths_and_ids(self):
        r = {'arm': 'anthropic', 'model_failure_handoffs': [1],
             'handoffs': [handoff(0, cost_usd=0.2, api_usage={'cache_creation_input_tokens': 7}),
                          handoff(1, cost_usd=0.3)]}
        metrics = bs.handoff_metrics(r)
        self.assertEqual([m['model_failure'] for m in metrics], [False, True])
        self.assertEqual(metrics[0]['cache_write'], {'total': 7, 'ephemeral_1h': None, 'ephemeral_5m': None})
        self.assertNotIn('/home/', json.dumps(metrics))
        self.assertAlmostEqual(bs.harness_reported_cost(r), 0.5)
        r['handoffs'][1].pop('cost_usd')
        self.assertIsNone(bs.harness_reported_cost(r))
        self.assertIsNone(bs.harness_reported_cost({'arm': 'openai', 'handoffs': [handoff()]}))

    def test_attach_scores_keeps_penalty_and_model_failures(self):
        records = ranked([record(1, 1, None)])
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder) / records[0]['id']
            work.mkdir(parents=True)
            (work / 'score.json').write_text(json.dumps({
                'status': 'final', 'final': 0.0, 'rawScore': 0.0, 'f': 0.0, 'rRepairable': 0, 'final_r83': 0.0,
                'scoreBeforePenalty': 0.0, 'overall_deduction': 0.0,
                'handoffs': [{'k': 0, 'scored': 'modelFailure: empty report'}, {'k': 1, 'scored': 'report'}]}))
            bs.attach_scores(records, folder)
        self.assertEqual(records[0]['model_failure_handoffs'], [0])
        self.assertEqual(records[0]['score_before_penalty'], 0.0)


if __name__ == '__main__':
    unittest.main()
