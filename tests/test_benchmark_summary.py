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
    return bench_validity.rank_cells(records, whole_configs=bench_records.PHASE3_CONFIGS)


def full_design(score=lambda config, attempt: 0.5 + 0.01 * attempt):
    """Every preregistered configuration of the scenario with 5 valid instances."""
    return [record(config, i, score(config, i)) for config in sorted(bs.PREREGISTERED_CONFIGS) for i in range(1, 6)]


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
        self.assertEqual(len(bs.PREREGISTERED_CONFIGS), 27)
        self.assertEqual(sorted(bs.PHASE3_CONFIGS), [28, 29])
        self.assertEqual([bs.CONFIGS[c]['effort'] for c in (7, 8, 9, 22, 23, 24)], ['low', 'high', 'max'] * 2)

    def test_every_configuration_bench_records_numbers_is_in_the_summary_table(self):
        """One table (user 2026-10-23): every number bench_records can give a record is a summary configuration with
        the same harness, model and effort."""
        produced = {}
        for key, (first, family, vendor) in bench_records.MODELS.items():
            for i, effort in enumerate(bench_records.MODEL_EFFORTS.get(key, bench_records.EFFORTS)):
                produced[first + i] = (vendor, effort)
        for (key, effort), number in bench_records.EXTRA_CONFIGS.items():
            produced[number] = (bench_records.MODELS[key][2], effort)
        self.assertEqual(set(produced), set(bs.CONFIGS))
        for number, (vendor, effort) in produced.items():
            self.assertEqual((bs.CONFIGS[number]['vendor'], bs.CONFIGS[number]['effort']), (vendor, effort), number)
        self.assertEqual(bs.CONFIGS[28], {'harness': 'codex', 'model': 'gpt-6-luna', 'vendor': 'openai', 'effort': 'xhigh'})
        self.assertEqual(bs.CONFIGS[29]['effort'], 'max')

    def test_a_configuration_outside_the_table_stops_the_summary(self):
        records = ranked(full_design() + [dict(record(4, 9, 0.5), config=30, id='openai/x/gpt-6-luna-ultra-a1')])
        with self.assertRaisesRegex(ValueError, 'not in tools.reviewer.bench_records.CONFIG_TABLE'):
            bs.summarize(records, 3)

    def test_phase3_supplement_is_tabled_never_compared_and_only_in_phase_3(self):
        base = ranked(full_design())
        extra = ranked([record(c, i, 0.9) for c in (28, 29) for i in range(1, 7)])
        with self.assertRaisesRegex(ValueError, 'phase-3 supplement'):
            bs.summarize(base + extra, 2)
        three, two = bs.summarize(base + extra, 3), bs.summarize(ranked(full_design()), 2)
        rows = three['scenarios'][SCENARIO]['configs']
        supplement = [c for c in rows if c['config'] in (28, 29)]
        # Every valid instance, no first-5 cut and no consistency row (user 2026-10-23).
        self.assertEqual([(c['config'], c['kind'], c['n']) for c in supplement], [(28, 'phase3', 6), (29, 'phase3', 6)])
        self.assertEqual(three['scenarios'][SCENARIO]['comparisons'], two['scenarios'][SCENARIO]['comparisons'])
        self.assertEqual([c for c in rows if c['config'] not in (28, 29)], two['scenarios'][SCENARIO]['configs'])
        self.assertEqual(three['holm_family_size'], 25)
        sixth = [r for r in three['scenarios'][SCENARIO]['instances'] if r['config'] == 28 and r['attempt'] == 6]
        self.assertTrue(sixth[0]['in_main'])
        self.assertFalse(sixth[0]['first_n'])  # still the plain fact valid_rank <= 5

    def test_phase3_records_ranked_with_the_first_5_cut_are_refused(self):
        stale = bench_validity.rank_cells(full_design() + [record(28, i, 0.9) for i in range(1, 7)])
        with self.assertRaisesRegex(ValueError, 'rebuild them'):
            bs.summarize(stale, 3)

    def test_phase_1_and_2_keep_the_first_5_cut(self):
        # whole_configs touches only the phase-3 supplement: a luna high cell with 7 valid keeps 5 in the main statistic.
        records = ranked(full_design() + [record(6, i, 0.5) for i in (6, 7)])
        for phase in (1, 2):
            rows = [c for c in bs.summarize([dict(r) for r in records], phase)['scenarios'][SCENARIO]['configs']
                    if c['config'] == 6]
            self.assertEqual([(c['kind'], c['n']) for c in rows], [('main', 5)])

    def test_v2_family_is_the_47_same_harness_same_effort_pairs_and_v1_stays_25(self):
        """Plan v2 §10 row 13: every two configurations of a harness and effort (Codex 15, Claude Code 26) plus the 6
        harness pairs; v1 keeps its 25."""
        pairs = bs.comparisons('v2')
        self.assertEqual(len(pairs), 47)
        self.assertEqual(len({(a, b) for _, a, b in pairs}), 47)
        counts = {}
        for g, _, _ in pairs:
            counts[g] = counts.get(g, 0) + 1
        self.assertEqual(counts, {'codex low': 6, 'codex medium': 3, 'codex high': 6, 'claude-code low': 10,
                                  'claude-code medium': 6, 'claude-code high': 10, 'harness': 6})
        for g, first, second in pairs:
            a, b = bs.CONFIGS[first], bs.CONFIGS[second]
            self.assertLess(first, second)
            self.assertEqual(a['effort'], b['effort'])
            if g == 'harness':
                self.assertEqual((a['harness'], b['harness'], a['vendor']), ('codex', 'claude-code', b['vendor']))
            else:
                self.assertEqual((a['harness'], a['effort']), tuple(g.split()))
                self.assertEqual(b['harness'], a['harness'])
        self.assertEqual(sorted(p for p in pairs if p[0] == 'harness'),
                         sorted(p for p in bs.comparisons() if p[0] == 'harness'))
        self.assertEqual(len(bs.comparisons('v1')), 25)
        self.assertEqual(bs.comparisons(), bs.comparisons('v1'))
        with self.assertRaises(ValueError):
            bs.comparisons('v3')

    def test_v2_summary_has_47_comparisons_with_asymmetric_n_and_no_ranking(self):
        """Strata alone has extra instances (phase 2): a pair of Strata (10) against sol (1) reads n 5 / 8 ... first is the
        lower number, so (1, 10) shows 5 / 8; Holm family size is 47; the v1 summary is untouched."""
        records = full_design() + [record(10, i, 0.7 + 0.01 * i, started=7000.0 + i) for i in (6, 7, 8)]
        records = ranked(records)
        for r in records:
            r['score_status'] = 'final' if r['valid'] else None
        summary = bs.summarize(records, 2, 'v2')
        self.assertEqual((summary['suite'], summary['holm_family_size']), ('v2', 47))
        result = summary['scenarios'][SCENARIO]
        self.assertEqual(len(result['comparisons']), 47)
        rows = {(r['first'], r['second']): r for r in result['comparisons']}
        self.assertEqual((rows[(1, 10)]['n_first'], rows[(1, 10)]['n_second']), (5, 8))
        self.assertEqual(rows[(1, 10)]['group'], 'codex low')
        self.assertEqual(rows[(7, 10)]['group'], 'codex low')  # DeepSeek and Strata: both low, neither is the reference
        self.assertTrue(all(0 <= r['p_holm'] <= 1 for r in rows.values()))
        text = bs.markdown(summary)
        self.assertIn('# 多模型 benchmark v2 汇总', text)
        self.assertIn('每个场景 47 个预登记比较', text)
        self.assertIn('codex low', text)
        v1 = bs.summarize(records, 2)
        self.assertEqual((v1['suite'], v1['holm_family_size'], len(v1['scenarios'][SCENARIO]['comparisons'])), ('v1', 25, 25))

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


class CostTest(unittest.TestCase):
    def test_deepseek_cost_is_cny_and_unknown_stays_unknown(self):
        rows = [record(7, i, 0.5, cost_usd=0.03, cost_cny=0.2) for i in (1, 2)]
        stat = bs.statistics(7, rows, 'main', None, rows, 2)
        self.assertAlmostEqual(stat['cost_cny_total'], 0.4)
        self.assertAlmostEqual(stat['cost_usd_total'], 0.06)
        self.assertEqual(bs.cost_text(rows[0]), '0.030（¥0.200）')
        rows.append(record(7, 3, 0.5, cost_usd=None, cost_cny=None))
        stat = bs.statistics(7, rows, 'main', None, rows, 3)
        self.assertIsNone(stat['cost_cny_total'])
        self.assertIsNone(stat['cost_usd_total'])
        self.assertEqual(bs.cost_text(rows[2]), '未知')

    def test_lower_bound_cost_gets_a_floor_mark(self):
        rows = [record(7, i, 0.5, cost_usd=0.03, cost_cny=0.2, cost_lower_bound=i == 2) for i in (1, 2)]
        self.assertEqual(bs.cost_text(rows[0]), '0.030（¥0.200）')
        self.assertEqual(bs.cost_text(rows[1]), '≥0.030（¥0.200）')
        stat = bs.statistics(7, rows, 'main', None, rows, 2)
        self.assertTrue(stat['cost_lower_bound'])
        self.assertEqual(bs.config_cost_text(stat), '≥0.060（¥0.400）')
        unknown = record(7, 3, 0.5, cost_usd=None, cost_cny=None, cost_lower_bound=True)
        self.assertEqual(bs.cost_text(unknown), '未知')
        usd = record(13, 1, 0.5, cost_lower_bound=True)
        self.assertEqual(bs.cost_text(usd), '≥' + bs.usd(0.5))

    def test_reconciliation_table_reports_deviation_and_ratio(self):
        window = {'balance': [10.0, 6.0], 'balance_difference': 4.0, 'instances': 3, 'instances_without_cost': 0,
                  'token_sum': 3.8, 'deviation': 0.2, 'deviation_ratio': 0.05}
        text = '\n'.join(bs.reconciliation_lines({**window, 'by_date': {'2026-10-21': window}}))
        self.assertIn('| 全部 | 10.00 → 6.00 | ¥4.00 | 3 | 0 | ¥3.8000 | ¥0.2000 | 5.00% |', text)
        self.assertIn('| 2026-10-21 |', text)
        self.assertEqual(bs.reconciliation_lines(None), [])

    def test_anthropic_without_cost_is_unknown(self):
        self.assertEqual(bs.cost_text(record(13, 1, 0.5, cost_usd=None)), '未知')


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

    def test_r8_4_negative_scores_and_the_r8_3_sensitivity_columns(self):
        """Config 25 against 13 (Claude Code low): both negative under r8.4, both 0 under r8.3, so r8.3 cannot tell them
        apart and the verdict changes."""
        records = [r for r in full_design() if r['config'] not in (13, 25)]
        records += [record(25, i, -0.6 - 0.01 * i) for i in range(1, 6)]
        records += [record(13, i, -0.1 - 0.01 * i) for i in range(1, 6)]
        for r in records:
            r['score_r83'] = max(0.0, r['score'])
        result = bs.summarize(ranked(records))['scenarios'][SCENARIO]
        configs = {c['config']: c for c in result['configs'] if c['kind'] == 'main'}
        self.assertEqual((configs[25]['n_negative'], configs[1]['n_negative']), (5, 0))
        self.assertAlmostEqual(configs[25]['min'], -0.65)
        self.assertAlmostEqual(configs[25]['median'], -0.63)
        self.assertEqual(configs[25]['mean_r83'], 0)
        self.assertAlmostEqual(configs[1]['mean_r83'], configs[1]['mean'])
        rows = {(r['first'], r['second']): r for r in result['comparisons']}
        self.assertEqual((rows[(25, 13)]['verdict'], rows[(25, 13)]['verdict_r83']), ('低于', '未分出'))
        self.assertTrue(rows[(25, 13)]['verdict_changed'])
        self.assertFalse(rows[(10, 1)]['verdict_changed'])
        text = bs.markdown(bs.summarize(ranked(records)))
        self.assertIn('r8.3 结论', text)
        self.assertIn('| 是 |', text)
        # Without r8.3 scores the sensitivity columns are unknown, not guessed.
        for r in records:
            r.pop('score_r83')
        result = bs.summarize(ranked(records))['scenarios'][SCENARIO]
        self.assertIsNone(result['comparisons'][0]['verdict_r83'])
        self.assertIsNone(next(c for c in result['configs'] if c['config'] == 25)['mean_r83'])

    def test_median(self):
        self.assertEqual((bs.median([3, 1, 2]), bs.median([4, 1, 2, 3]), bs.median([])), (2, 2.5, None))

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
                                                             'f': 0.02, 'rRepairable': 1, 'final_r83': value + 1}))
            bs.attach_scores(records, folder)
        self.assertEqual([r['score'] for r in records], [0.4, 0.6])
        self.assertEqual([r['score_r83'] for r in records], [1.4, 1.6])
        cell = bs.summarize(records)['scenarios'][SCENARIO]['configs'][0]
        self.assertAlmostEqual(cell['mean'], 0.5)
        self.assertEqual(cell['repairs_total'], 2)

    def test_scores_from_several_roots_but_never_two_for_one_record(self):
        records = ranked([record(1, 1, None), record(1, 2, None)])
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            for root, r in ((a, records[0]), (b, records[1])):
                (Path(root) / r['id']).mkdir(parents=True)
                (Path(root) / r['id'] / 'score.json').write_text(json.dumps({'status': 'final', 'final': 0.3}))
            bs.attach_scores(records, [a, b])
            self.assertEqual([r['score'] for r in records], [0.3, 0.3])
            (Path(a) / records[1]['id']).mkdir(parents=True)
            (Path(a) / records[1]['id'] / 'score.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'several score roots'):
                bs.attach_scores(ranked([record(1, 2, None)]), [a, b])

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
        self.assertEqual(data['generator']['tool'], 'tools.reviewer.benchmark_summary')
        self.assertEqual(data['generator']['phase'], 2)
        self.assertEqual(len(data['generator']['sha256']), 64)
        for line in text.splitlines():
            self.assertFalse(line.startswith(' |'))

    def test_pooled_speeds_are_total_tokens_over_total_seconds(self):
        # Two instances with different speeds and durations: task input 100 / 10 s = 10 and 900 / 30 s = 30 tok/s pool
        # to 1000 / 40 = 25, not the arithmetic mean 20.
        a = record(13, 1, 0.5, seconds=10.0, tokens={'uncached_input': 100, 'cached_input': 0, 'output': 50},
                   speeds={'task_input': 10.0, 'task_output': 5.0, 'engine_input': None, 'engine_output': 25.0},
                   handoffs=[{'api_seconds': 2.0}], speed_lower_bounds=['engine_output'])
        b = record(13, 2, 0.5, seconds=30.0, tokens={'uncached_input': 900, 'cached_input': 0, 'output': 60},
                   speeds={'task_input': 30.0, 'task_output': 2.0, 'engine_input': None, 'engine_output': 6.0},
                   handoffs=[{'api_seconds': 10.0}], speed_lower_bounds=['engine_output'])
        cell = bs.summarize(ranked([a, b]))['scenarios'][SCENARIO]['configs'][0]
        self.assertEqual(cell['speeds_mean'], {'engine_input': None, 'engine_output': 110 / 12, 'task_input': 1000 / 40,
                                               'task_output': 110 / 40})
        self.assertNotEqual(cell['speeds_mean']['task_input'], (10.0 + 30.0) / 2)
        self.assertEqual(cell['speed_totals']['task_input'], {'tokens': 1000, 'seconds': 40.0})
        self.assertEqual(cell['speeds_lower_bound'], ['engine_output'])
        # Strata parts from the handoff engine stages; one unknown part makes the row unknown.
        s1 = record(10, 1, 0.5, seconds=10.0, speeds={'task_input': 100.0, 'task_output': 30.0, 'engine_input': 500.0,
                                                      'engine_output': 50.0},
                    handoff_metrics=[{'engine_read': 1000, 'engine_input_seconds': 2.0, 'engine_generated': 300,
                                      'engine_decode_seconds': 6.0}])
        s2 = record(10, 2, 0.5, seconds=20.0, speeds={'task_input': 50.0, 'task_output': 15.0, 'engine_input': 100.0,
                                                      'engine_output': 75.0},
                    handoff_metrics=[{'engine_read': 1000, 'engine_input_seconds': 10.0, 'engine_generated': 300,
                                      'engine_decode_seconds': 4.0}])
        self.assertEqual(bs.pooled_speeds([s1, s2]), {'engine_input': 2000 / 12, 'engine_output': 60.0,
                                                      'task_input': 2000 / 30, 'task_output': 600 / 30})
        s2['speeds']['engine_input'] = None
        self.assertIsNone(bs.pooled_speeds([s1, s2])['engine_input'])
        # Codex API engine output without stored relay parts: approximated as output / (output / speed) and marked
        # (option (b), user 2026-10-22), also when the record's stored speed_parts left it unknown.
        c = record(1, 1, 0.5, seconds=10.0, speeds={'task_input': 100.0, 'task_output': 30.0, 'engine_input': None,
                                                    'engine_output': 40.0})
        self.assertEqual(bs.speed_parts(c)['engine_output'], {'tokens': 300, 'seconds': 7.5, 'approximate': True})
        stored = dict(c, speed_parts={**bs.speed_parts(c), 'engine_output': None})
        self.assertEqual(bs.speed_parts(stored)['engine_output'], {'tokens': 300, 'seconds': 7.5, 'approximate': True})
        c2 = dict(c, tokens=dict(c['tokens'], output=100), speeds=dict(c['speeds'], engine_output=20.0, task_output=10.0))
        self.assertEqual(bs.pooled_speeds([c, c2])['engine_output'], 400 / 12.5)
        self.assertEqual(bs.speed_totals([c, c2])['engine_output'], {'tokens': 400, 'seconds': 12.5, 'approximate': True})
        self.assertEqual(bs.pooled_speeds([c])['task_output'], 30.0)
        self.assertNotIn('approximate', bs.speed_totals([c])['task_output'])
        # A rebuilt part has to reproduce the recorded speed.
        with self.assertRaises(ValueError):
            bs.speed_parts(dict(c, speeds=dict(c['speeds'], task_output=31.0)))

    def test_speeds_column_and_rejections(self):
        parts = lambda **v: {k: {'tokens': t, 'seconds': sec} for k, (t, sec) in v.items()}
        records = ranked([record(10, i, 0.5, speeds={'engine_input': 900.0, 'engine_output': 70.2, 'task_input': 5.0,
                                                     'task_output': 1.1},
                                 speed_parts=parts(engine_input=(900, 1), engine_output=(702, 10), task_input=(50, 10),
                                                   task_output=(11, 10))) for i in range(1, 3)])
        text = bs.markdown(bs.summarize(records))
        self.assertIn('引擎输出 tok/s', text)
        self.assertIn('70.2', text)
        lower = ranked([record(13, i, 0.5, speeds={'engine_input': None, 'engine_output': 40.0, 'task_input': 5.0,
                                                   'task_output': 1.0}, speed_lower_bounds=['engine_output'],
                               speed_parts={**parts(engine_output=(400, 10), task_input=(50, 10), task_output=(10, 10)),
                                            'engine_input': None})
                        for i in range(1, 3)])
        summary = bs.summarize(lower)
        cell = summary['scenarios'][SCENARIO]['configs'][0]
        self.assertEqual((cell['speeds_mean']['engine_output'], cell['speeds_mean']['engine_input']), (40.0, None))
        self.assertEqual(cell['speeds_lower_bound'], ['engine_output'])
        self.assertIn('| 未知 | ≥40.0 | 5.0 | 1.0 |', bs.markdown(summary))
        self.assertIn('总 token ÷ 总耗时', bs.markdown(summary))
        self.assertEqual(bs.usd(0.0001), '<0.001')
        self.assertEqual(bs.usd(0.0), '0.000')
        with self.assertRaises(ValueError):
            bs.summarize(records + [records[0]])
        with self.assertRaises(ValueError):
            bad = record(1, 1, 0.5)
            bad['config'] = 30
            bs.summarize(ranked([bad]))
        with self.assertRaises(ValueError):
            bs.summarize(ranked([record(1, 1, 0.5, tokens={'output': 1})]))
        with self.assertRaises(ValueError):
            bs.summarize([record(1, 1, 0.5)])  # not ranked by bench_validity
        with self.assertRaises(ValueError):
            bs.summarize(records, phase=4)


if __name__ == '__main__':
    unittest.main()
