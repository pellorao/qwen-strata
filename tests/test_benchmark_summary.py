import json
import tempfile
import unittest
from pathlib import Path

from tools.reviewer import benchmark_summary as bs


def record(config, instance, score, scenario='code-standards-v5.1', valid=True, **extra):
    base = {'scenario': scenario, 'config': config, 'instance': instance, 'valid': valid, 'score': score,
            'raw_score': None if score is None else score + 0.01, 'format_penalty': 0.0, 'repairs': 0, 'seconds': 600.0 + instance,
            'time_limit_seconds': 1200.0, 'tokens': {'uncached_input': 1000, 'cached_input': 20000, 'output': 300},
            'token_source': 'api-usage', 'tool_calls': 12, 'cost_usd': 0.5, 'model_ids': ['m'],
            'service_tiers': ['default']}
    base.update(extra)
    return base


class StatisticsTest(unittest.TestCase):
    def test_t_distribution_matches_reference_values(self):
        self.assertAlmostEqual(bs.t_two_sided_p(2.0, 10), 0.073388, places=5)
        self.assertAlmostEqual(bs.t_quantile(0.975, 4), 2.776445, places=5)
        self.assertAlmostEqual(bs.t_quantile(0.975, 30), 2.042272, places=5)

    def test_welch_reference(self):
        # Welch on [1..5] vs [2,4,6,8,10]: d -3, se sqrt(0.5 + 2) = 1.5811, df 5.882.
        test = bs.welch([1, 2, 3, 4, 5], [2, 4, 6, 8, 10])
        self.assertAlmostEqual(test['se'], 1.581139, places=5)
        self.assertAlmostEqual(test['df'], 5.882353, places=5)
        self.assertAlmostEqual(test['p'], bs.t_two_sided_p(3 / 1.581139, 5.882353), places=5)
        self.assertEqual(bs.welch([1, 1], [1, 1])['p'], 1.0)
        self.assertEqual(bs.welch([1, 1], [0, 0])['p'], 0.0)
        self.assertIsNone(bs.welch([1], [0, 1]))

    def test_holm_is_monotone_step_down(self):
        self.assertEqual(bs.holm([0.01, 0.04, 0.03, 0.5]), [0.04, 0.09, 0.09, 0.5])

    def test_family_is_the_27_preregistered_pairs(self):
        pairs = bs.comparisons()
        self.assertEqual(len(pairs), 27)
        self.assertEqual(len(set(pairs)), 27)
        for first, second in pairs:
            a, b = bs.CONFIGS[first], bs.CONFIGS[second]
            self.assertEqual(a['effort'], b['effort'])
            if a['harness'] == b['harness']:
                self.assertEqual(a['vendor'], 'strata')
            else:
                self.assertEqual(a['model'], b['model'])
                self.assertIn(a['vendor'], ('strata', 'deepseek'))


class SummaryTest(unittest.TestCase):
    def synthetic(self):
        records = []
        for config in bs.CONFIGS:
            for i in range(1, 6):
                records.append(record(config, i, 0.5 + 0.01 * i))
        # Strata Codex high: 10 instances, the last 5 far higher; only the first 5 enter comparisons.
        records += [record(12, i, 0.99) for i in range(6, 11)]
        # A clearly higher Strata Claude Code low, one invalid instance, unknown output tokens on another.
        records = [r for r in records if r['config'] != 25]
        records += [record(25, i, 0.9 + 0.001 * i) for i in range(1, 6)]
        records.append(record(25, 6, None, valid=False))
        records = [r for r in records if not (r['config'] == 13 and r['instance'] == 1)]
        records.append(record(13, 1, 0.51, tokens={'uncached_input': 10, 'cached_input': 20, 'output': None}))
        return records

    def test_summary_tables_and_comparisons(self):
        summary = bs.summarize(self.synthetic())
        result = summary['scenarios']['code-standards-v5.1']
        configs = {c['config']: c for c in result['configs']}
        self.assertEqual(configs[12]['n'], 10)
        rows = {(r['first'], r['second']): r for r in result['comparisons']}
        self.assertEqual(rows[(12, 3)]['n_first'], 5)
        self.assertAlmostEqual(rows[(12, 3)]['d'], 0.0)
        self.assertEqual(rows[(25, 13)]['verdict'], '高于')
        self.assertEqual(rows[(10, 1)]['verdict'], '未分出')
        self.assertEqual(configs[25]['invalid'], 1)
        self.assertIsNone(configs[13]['tokens_mean']['output'])
        self.assertIsNone(configs[1]['cost_usd_total'])  # OpenAI: tokens only
        self.assertAlmostEqual(configs[13]['anthropic_quota_percent'], 2.5 * bs.QUOTA_PER_USD)
        self.assertAlmostEqual(configs[10]['cost_usd_total'], 5 * (1000 * 0.15 + 20000 * 0.016 + 300 * 0.47) / 1e6)
        self.assertEqual(len(result['instances']), 27 * 5 + 5 + 1)

    def test_markdown_keeps_every_instance_and_unknowns(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'records.jsonl'
            path.write_text(''.join(json.dumps(r) + '\n' for r in self.synthetic()))
            bs.write(path, Path(folder) / 'out')
            text = (Path(folder) / 'out/summary.md').read_text()
            data = json.loads((Path(folder) / 'out/summary.json').read_text())
        self.assertIn('## code-standards-v5.1', text)
        instance_rows = [l for l in text.splitlines() if l.startswith('| 25 claude-code strata-iq3_xxs low | ')]
        self.assertEqual(len(instance_rows), 11)  # configuration row, 4 comparisons it leads, 6 instance rows
        self.assertIn('| 否 |', text)
        self.assertIn('未知', text)
        self.assertIn('只报 token', text)
        self.assertNotIn('引擎输出 tok/s', text)
        self.assertEqual(data['holm_family_size'], 27)
        for line in text.splitlines():
            self.assertFalse(line.startswith(' |'))

    def test_speeds_column_and_rejections(self):
        records = [record(10, i, 0.5, speeds={'engine_input': 900.0, 'engine_output': 70.2, 'task_input': 5.0,
                                              'task_output': 1.1}) for i in range(1, 3)]
        text = bs.markdown(bs.summarize(records))
        self.assertIn('引擎输出 tok/s', text)
        self.assertIn('70.2', text)
        self.assertEqual(bs.usd(0.0001), '<0.001')
        self.assertEqual(bs.usd(0.0), '0.000')
        with self.assertRaises(ValueError):
            bs.summarize(records + [records[0]])
        with self.assertRaises(ValueError):
            bs.summarize([record(28, 1, 0.5)])
        with self.assertRaises(ValueError):
            bs.summarize([record(1, 1, 0.5, tokens={'output': 1})])
        with self.assertRaises(ValueError):
            bs.summarize([record(1, 1, None)])


if __name__ == '__main__':
    unittest.main()
