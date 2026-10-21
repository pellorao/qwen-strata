import json
import tempfile
import unittest
from pathlib import Path

from tools.reviewer import bench_records, bench_validity
from tools.reviewer import benchmark_summary as bs

ARMS = {('codex', 'openai'): 'openai', ('codex', 'deepseek'): 'deepseek-codex', ('codex', 'strata'): 'strata-codex',
        ('claude-code', 'anthropic'): 'anthropic', ('claude-code', 'deepseek'): 'deepseek-claude',
        ('claude-code', 'strata'): 'strata-claude'}
SCENARIO = 'commit-audit-v3'


def record(config, attempt, score, valid=True, started=None, name=None, scenario=SCENARIO, **extra):
    c = bs.CONFIGS[config]
    effort = extra.pop('dir_effort', c['effort'])
    base = {'id': f"{ARMS[c['harness'], c['vendor']]}/{scenario}/{name or c['model']}-{effort}-a{attempt}",
            'arm': ARMS[c['harness'], c['vendor']], 'scenario': scenario, 'config': config, 'attempt': attempt,
            'instance': attempt, 'started': 1000.0 * attempt if started is None else started, 'valid': valid,
            'validity': {'status': 'valid' if valid else 'invalid'}, 'pooled': False, 'supplementary': False,
            'supplementary_label': None, 'score': score if valid else None,
            'raw_score': None if score is None else score + 0.01, 'format_penalty': 0.0, 'repairs': 0,
            'seconds': 600.0 + attempt, 'time_limit_seconds': 1200.0,
            'tokens': {'uncached_input': 1000, 'cached_input': 20000, 'output': 300}, 'token_source': 'API usage',
            'tool_calls': 12, 'cost_usd': 0.5, 'model_ids': ['m'], 'service_tiers': {'default': 3}}
    base.update(extra)
    return base


def ranked(records):
    return bench_validity.rank_cells(records)


def full_design(score=lambda config, attempt: 0.5 + 0.01 * attempt):
    """Every configuration of the scenario with 5 valid instances."""
    return [record(config, i, score(config, i)) for config in bs.CONFIGS for i in range(1, 6)]


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


class DesignTest(unittest.TestCase):
    def test_configurations_match_bench_records(self):
        for key, (first, _, _) in bench_records.MODELS.items():
            for i, effort in enumerate(bench_records.MODEL_EFFORTS.get(key, bench_records.EFFORTS)):
                self.assertEqual(bs.CONFIGS[first + i]['effort'], effort, key)
        self.assertEqual(len(bs.CONFIGS), 27)
        self.assertEqual([bs.CONFIGS[c]['effort'] for c in (7, 8, 9, 22, 23, 24)], ['low', 'high', 'max'] * 2)

    def test_family_is_the_25_preregistered_pairs(self):
        """Plan §5 (2026-10-21): Codex 8, Claude Code 11, harness 6."""
        pairs = bs.comparisons()
        expected = ([('codex', 10, 1), ('codex', 10, 4), ('codex', 10, 7), ('codex', 11, 2), ('codex', 11, 5),
                     ('codex', 12, 3), ('codex', 12, 6), ('codex', 12, 8)]
                    + [('claude-code', 25 + i, a + i) for i in range(3) for a in (13, 16, 19)]
                    + [('claude-code', 25, 22), ('claude-code', 27, 23)]
                    + [('harness', 10, 25), ('harness', 11, 26), ('harness', 12, 27), ('harness', 7, 22),
                       ('harness', 8, 23), ('harness', 9, 24)])
        self.assertEqual(sorted(pairs), sorted(expected))
        self.assertEqual(len(pairs), 25)
        self.assertEqual(len(set(pairs)), 25)
        counts = {g: sum(1 for p in pairs if p[0] == g) for g in ('codex', 'claude-code', 'harness')}
        self.assertEqual(counts, {'codex': 8, 'claude-code': 11, 'harness': 6})
        for _, first, second in pairs:
            a, b = bs.CONFIGS[first], bs.CONFIGS[second]
            self.assertEqual(a['effort'], b['effort'])
            if a['harness'] == b['harness']:
                self.assertEqual(a['vendor'], 'strata')
            else:
                self.assertEqual(a['vendor'], b['vendor'])
                self.assertIn(a['vendor'], ('strata', 'deepseek'))
        # DeepSeek max is in the family only as its harness comparison; Strata never meets a max or DeepSeek medium.
        self.assertIn(('harness', 9, 24), pairs)
        self.assertFalse([p for p in pairs if bs.CONFIGS[p[1]]['vendor'] == 'strata' and p[2] in (9, 24)])


class SelectionTest(unittest.TestCase):
    def test_merged_cell_uses_every_valid_instance_with_a_consistency_row(self):
        records = [r for r in full_design() if r['config'] != 8]
        # DeepSeek Codex high (C'): 4 medium instances pooled into high plus 4 high; started interleaved.
        records += [record(8, i, 0.9, started=100.0 + 10 * i, dir_effort='medium', pooled=True,
                           requested_effort='medium') for i in range(1, 5)]
        records += [record(8, i, 0.1, started=105.0 + 10 * i) for i in range(1, 5)]
        result = bs.summarize(ranked(records))['scenarios'][SCENARIO]
        rows = [c for c in result['configs'] if c['config'] == 8]
        self.assertEqual([c['kind'] for c in rows], ['main', 'consistency'])
        main, first5 = rows
        self.assertEqual((main['n_valid'], main['n'], first5['n']), (8, 8, 5))
        self.assertAlmostEqual(main['mean'], 0.5)
        # By start time: medium-a1, high-a1, medium-a2, high-a2, medium-a3.
        self.assertAlmostEqual(first5['mean'], (3 * 0.9 + 2 * 0.1) / 5)
        test = next(t for t in result['comparisons'] if (t['first'], t['second']) == (12, 8))
        self.assertEqual(test['n_second'], 8)

    def test_unmerged_cell_takes_the_first_five_by_start_time(self):
        records = [r for r in full_design() if r['config'] != 1]
        # A rerun (attempt 6) started before attempt 5: first 5 by start time, attempt 5 left out.
        records += [record(1, i, 0.5, started=1000.0 * i) for i in range(1, 5)]
        records += [record(1, 5, 0.0, started=9000.0), record(1, 6, 0.5, started=4500.0)]
        result = bs.summarize(ranked(records))['scenarios'][SCENARIO]
        rows = [c for c in result['configs'] if c['config'] == 1]
        self.assertEqual([c['kind'] for c in rows], ['main'])
        self.assertEqual(rows[0]['n'], 5)
        self.assertAlmostEqual(rows[0]['mean'], 0.5)
        self.assertNotIn(f'openai/{SCENARIO}/gpt-6.1-sol-low-a5', rows[0]['ids'])

    def test_phase_one_and_two_strata_selection(self):
        records = [r for r in full_design() if r['config'] not in (12, 26)]
        records += [record(12, i, 0.5 if i <= 5 else 0.99) for i in range(1, 11)]  # 5 preregistered + 5 extra
        records += [record(12, 11, 0.0, valid=False)]
        records += [record(26, i, 0.6 if i <= 5 else 0.7) for i in range(1, 9)]   # extras stopped at 8 valid
        one = bs.summarize(ranked([dict(r) for r in records]), phase=1)['scenarios'][SCENARIO]
        two = bs.summarize(ranked([dict(r) for r in records]), phase=2)['scenarios'][SCENARIO]
        rows1 = {(c['config'], c['kind']): c for c in one['configs']}
        rows2 = {(c['config'], c['kind']): c for c in two['configs']}
        self.assertEqual(rows1[12, 'main']['n'], 5)
        self.assertNotIn((12, 'consistency'), rows1)
        self.assertAlmostEqual(rows1[12, 'main']['mean'], 0.5)
        self.assertEqual((rows2[12, 'main']['n'], rows2[12, 'consistency']['n']), (10, 5))
        self.assertAlmostEqual(rows2[12, 'consistency']['mean'], 0.5)
        self.assertEqual(rows2[26, 'main']['n'], 8)  # fewer than 10: actual n
        self.assertEqual(rows2[12, 'main']['invalid'], 1)
        t1 = {(t['first'], t['second']): t for t in one['comparisons']}
        t2 = {(t['first'], t['second']): t for t in two['comparisons']}
        self.assertEqual((t1[12, 3]['n_first'], t2[12, 3]['n_first']), (5, 10))
        self.assertEqual(t2[11, 26]['n_second'], 8)
        # Non-Strata cells are the same in both phases.
        self.assertEqual(rows1[3, 'main']['ids'], rows2[3, 'main']['ids'])
        # Phase 2 with a 12th valid Strata instance: still at most 10.
        more = records + [record(12, 12, 0.99), record(12, 13, 0.99)]
        rows = {(c['config'], c['kind']): c for c in bs.summarize(ranked(more), 2)['scenarios'][SCENARIO]['configs']}
        self.assertEqual(rows[12, 'main']['n'], 10)

    def test_supplementary_rows_are_tabled_but_never_compared(self):
        records = full_design()
        label = 'high requested as medium, T=344'
        records += [record(8, i, 0.99, dir_effort='medium', supplementary=True, supplementary_label=label,
                           requested_effort='medium') for i in range(1, 6)]
        result = bs.summarize(ranked(records))['scenarios'][SCENARIO]
        rows = [c for c in result['configs'] if c['config'] == 8]
        self.assertEqual([c['kind'] for c in rows], ['main', 'supplementary', 'sensitivity'])
        self.assertEqual(rows[0]['n'], 5)
        self.assertAlmostEqual(rows[0]['mean'], 0.53)
        self.assertEqual(rows[1]['label'], label)
        self.assertEqual(rows[2]['n'], 10)
        supplementary_ids = set(rows[1]['ids'])
        test = next(t for t in result['comparisons'] if (t['first'], t['second']) == (12, 8))
        self.assertEqual(test['n_second'], 5)
        self.assertAlmostEqual(test['d'], 0.0)
        self.assertEqual(len(result['comparisons']), 25)
        self.assertFalse(supplementary_ids & {i for c in result['configs'] if c['kind'] == 'main' for i in c['ids']})

    def test_deepseek_max_present_and_compared_across_harnesses(self):
        records = [r for r in full_design() if r['config'] != 24]
        records += [record(24, i, 0.95 + 0.001 * i) for i in range(1, 6)]
        result = bs.summarize(ranked(records))['scenarios'][SCENARIO]
        configs = {c['config']: c for c in result['configs'] if c['kind'] == 'main'}
        self.assertEqual(configs[9]['effort'], 'max')
        self.assertEqual(configs[24]['n'], 5)
        test = next(t for t in result['comparisons'] if (t['first'], t['second']) == (9, 24))
        self.assertEqual(test['verdict'], '低于')
        self.assertIn('9 codex deepseek-flash max', bs.markdown(bs.summarize(ranked(records))))


class SummaryTest(unittest.TestCase):
    def synthetic(self):
        records = full_design()
        records = [r for r in records if r['config'] != 25]
        records += [record(25, i, 0.9 + 0.001 * i) for i in range(1, 6)]
        records.append(record(25, 6, None, valid=False))
        records = [r for r in records if not (r['config'] == 13 and r['attempt'] == 1)]
        records.append(record(13, 1, 0.51, tokens={'uncached_input': 10, 'cached_input': 20, 'output': None}))
        return ranked(records)

    def test_summary_tables_and_comparisons(self):
        summary = bs.summarize(self.synthetic())
        self.assertEqual(summary['phase'], 1)
        self.assertTrue(summary['complete'])
        result = summary['scenarios'][SCENARIO]
        configs = {c['config']: c for c in result['configs'] if c['kind'] == 'main'}
        rows = {(r['first'], r['second']): r for r in result['comparisons']}
        self.assertEqual(rows[(25, 13)]['verdict'], '高于')
        self.assertEqual(rows[(10, 1)]['verdict'], '未分出')
        self.assertEqual(configs[25]['invalid'], 1)
        self.assertIsNone(configs[13]['tokens_mean']['output'])
        self.assertIsNone(configs[1]['cost_usd_total'])  # OpenAI: tokens only
        self.assertAlmostEqual(configs[13]['anthropic_quota_percent'], 2.5 * bs.QUOTA_PER_USD)
        self.assertAlmostEqual(configs[10]['cost_usd_total'], 5 * (1000 * 0.15 + 20000 * 0.016 + 300 * 0.47) / 1e6)
        self.assertEqual(configs[1]['service_tiers'], ['default'])
        self.assertEqual(len(result['instances']), 27 * 5 + 1)

    def test_unscored_instances_mark_the_comparison(self):
        records = self.synthetic()
        for r in records:
            if r['config'] == 10 and r['attempt'] == 2:
                r['score'] = None
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'scores'
            work = root / f'strata-codex/{SCENARIO}/strata-iq3_xxs-low-a2'
            work.mkdir(parents=True)
            (work / 'score.json').write_text(json.dumps({'status': 'needs-adjudication', 'pending': 3}))
            bs.attach_scores(records, root)
        summary = bs.summarize(records)
        self.assertFalse(summary['complete'])
        result = summary['scenarios'][SCENARIO]
        rows = {(r['first'], r['second']): r for r in result['comparisons']}
        self.assertEqual(rows[(10, 1)]['verdict'], '未计分完')
        self.assertEqual(rows[(10, 1)]['scored_first'], 4)
        cell = next(c for c in result['configs'] if c['config'] == 10)
        self.assertEqual((cell['n_selected'], cell['n']), (5, 4))
        self.assertIn('needs-adjudication', bs.markdown(summary))

    def test_scores_come_from_score_json(self):
        records = ranked([record(1, 1, None), record(1, 2, None)])
        with tempfile.TemporaryDirectory() as folder:
            for r, value in zip(records, (0.4, 0.6)):
                work = Path(folder) / r['id']
                work.mkdir(parents=True)
                (work / 'score.json').write_text(json.dumps({'status': 'final', 'final': value, 'rawScore': 0.7,
                                                             'f': 0.02, 'rRepairable': 1}))
            bs.attach_scores(records, folder)
        self.assertEqual([r['score'] for r in records], [0.4, 0.6])
        cell = bs.summarize(records)['scenarios'][SCENARIO]['configs'][0]
        self.assertAlmostEqual(cell['mean'], 0.5)
        self.assertEqual(cell['repairs_total'], 2)

    def test_markdown_and_json_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'records.jsonl'
            path.write_text(''.join(json.dumps(r) + '\n' for r in self.synthetic()))
            bs.write(Path(folder) / 'out', records_path=path, phase=2)
            text = (Path(folder) / 'out/summary.md').read_text()
            data = json.loads((Path(folder) / 'out/summary.json').read_text())
        self.assertIn(f'## {SCENARIO}', text)
        self.assertIn('第二阶段', text)
        self.assertIn('| 否 |', text)
        self.assertIn('未知', text)
        self.assertIn('只报 token', text)
        self.assertNotIn('引擎输出 tok/s', text)
        self.assertEqual(data['holm_family_size'], 25)
        self.assertEqual(data['phase'], 2)
        for line in text.splitlines():
            self.assertFalse(line.startswith(' |'))

    def test_speeds_column_and_rejections(self):
        records = ranked([record(10, i, 0.5, speeds={'engine_input': 900.0, 'engine_output': 70.2, 'task_input': 5.0,
                                                     'task_output': 1.1}) for i in range(1, 3)])
        text = bs.markdown(bs.summarize(records))
        self.assertIn('引擎输出 tok/s', text)
        self.assertIn('70.2', text)
        self.assertEqual(bs.usd(0.0001), '<0.001')
        self.assertEqual(bs.usd(0.0), '0.000')
        with self.assertRaises(ValueError):
            bs.summarize(records + [records[0]])
        with self.assertRaises(ValueError):
            bad = record(1, 1, 0.5)
            bad['config'] = 28
            bs.summarize(ranked([bad]))
        with self.assertRaises(ValueError):
            bs.summarize(ranked([record(1, 1, 0.5, tokens={'output': 1})]))
        with self.assertRaises(ValueError):
            bs.summarize([record(1, 1, 0.5)])  # not ranked by bench_validity
        with self.assertRaises(ValueError):
            bs.summarize(records, phase=3)


if __name__ == '__main__':
    unittest.main()
