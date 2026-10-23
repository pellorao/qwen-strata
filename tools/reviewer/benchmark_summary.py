"""Cross-model summary of the multi-model benchmark v1 (benchmarks/multi-model-v1/plan.md §5, §14.1, §14.4).

Input: the normalized instance records of tools.reviewer.bench_records (validity rejudged by
tools.reviewer.bench_validity, which also ranks each cell: valid_rank, main_statistic, first_n, cell_pooled), either
built from the run directories under --data-root or read from a JSON Lines file (--records). Scores come from the
records themselves when filled in, otherwise from bench_score's <score root>/<record id>/score.json (status final, or
no-report with final 0); anything else leaves the instance unscored. Output: summary.json and summary.md in a fresh
directory, per scenario:
- per cell (scenario, configuration, supplementary label): n valid, n in the main statistic and n scored, mean ± SD,
  SE and t 95% interval, raw score, format penalty and repairs, minutes and share of the time limit, the three token
  classes and their source, tool calls, cost, returned model IDs and service tiers;
- a consistency row (the first 5 valid by start time) for every cell whose main statistic holds more: merged DeepSeek
  cells (C', plan §14.4) and, in phase 2, Strata cells with extra instances (never for the phase-3 supplement);
- supplementary rows (DeepSeek medium not merged, `supplementary_label`) and their descriptive high+medium row; they
  never enter a comparison;
- the 25 preregistered comparisons (plan §5): Welch t with Welch-Satterthwaite df, Holm within the scenario,
  two-sided alpha 0.05. A comparison without two fully scored sides of n >= 2 keeps its place in the family with p 1;
- the per-instance table, invalid instances included and marked (measurement rule).
No ratios, combined scores or ranks (D7).

Scoring r8.4 (user 2026-10-21) no longer cuts scores at 0, so each cell also gives its negative instances, minimum and
median, and every score keeps its r8.3 counterpart (bench_score final_r83: cut at 0, deduction multiplied) for the
sensitivity table of plan §14.1: the r8.3 cell mean and, per comparison, the r8.3 Holm p and verdict, marked where the
verdict differs. A score taken from the record itself carries its own score_r83 or none.

Scoring phases (plan §14.1, user 2026-10-21): phase 1 uses only the preregistered instances, the main statistic of
bench_validity.rank_cells (cells not merged: the first 5 valid by start time; merged cells: every valid one). Phase 2
adds the Strata extra instances: a Strata cell's main statistic is its valid instances up to rank 10 (the extra-run
target), with the first 5 as a consistency row; a cell with fewer uses its actual n.

Phase 3 (user 2026-10-22): phase 2 unchanged plus the supplement configurations 28 / 29 (gpt-6-luna xhigh / max on
Codex, PHASE3_CONFIGS): their rows (kind phase3) and instances only, never in a comparison or the Holm family. A
supplement row takes every valid instance of its cell, with no first-5 cut and no consistency row (measurement rule
失败与重跑, user 2026-10-23: extra runs not triggered by scores count the same as preregistered ones); records ranked
before that rule are refused. Configurations come from tools.reviewer.bench_records.CONFIG_TABLE; a record outside it stops the
summary. summary.json carries a `generator` marker (tool, its sha256, phase) that benchmark_export requires.

    python3 -m tools.reviewer.benchmark_summary --data-root <checkout> --out <fresh dir> [--phase 1|2|3]
        [--records records.jsonl ...] [--score-root <dir> ...] [--reconciliation-from <summary.json>]
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from tools.metrics.measurement_format import equivalent_cost_usd, minutes
from tools.reviewer.bench_records import CONFIG_TABLE, PHASE3_CONFIGS

# Configurations from the one table of tools.reviewer.bench_records (user 2026-10-23: no copy of it here). Rows of plan
# §2 have kind main; PHASE3_CONFIGS are the phase-3 supplement (gpt-6-luna xhigh / max), only in phase 3, never in a
# comparison or the Holm family.
CONFIG_ROWS = [(first, harness, model, vendor, efforts)
               for first, _, harness, _, model, vendor, efforts, _ in CONFIG_TABLE]
CONFIGS = {first + i: {'harness': h, 'model': m, 'vendor': v, 'effort': e}
           for first, h, m, v, efforts in CONFIG_ROWS for i, e in enumerate(efforts)}
PREREGISTERED_CONFIGS = frozenset(CONFIGS) - PHASE3_CONFIGS
RECORD_FIELDS = ('id', 'scenario', 'config', 'valid', 'valid_rank', 'main_statistic', 'first_n', 'score', 'raw_score',
                 'format_penalty', 'repairs', 'seconds', 'time_limit_seconds', 'tokens', 'token_source', 'tool_calls',
                 'cost_usd', 'model_ids', 'service_tiers')
TOKEN_CLASSES = ('uncached_input', 'cached_input', 'output')
SPEEDS = ('engine_input', 'engine_output', 'task_input', 'task_output')
PREREGISTERED_N = 5      # first 5 valid by start time (plan §3, §14.1)
STRATA_PHASE2_MAX = 10   # Strata extra-run target per cell (plan §14.1, 2026-10-21 09:14)
PHASES = (1, 2, 3)
GENERATOR = 'tools.reviewer.benchmark_summary'  # summary.json source marker, required by benchmark_export
ALPHA = 0.05
QUOTA_PER_USD = 0.086  # % of the Anthropic weekly quota per API-equivalent USD (estimate.sh calibration)
SCORED_STATUSES = ('final', 'no-report')  # bench_score statuses with a final score
SPEED_POOL_NOTE = ('速度汇总口径（用户 2026-10-22）：多个实例的速度（summary.json 各行的 speeds_mean）是总 token ÷ 总耗时'
                   '（各实例 speed_parts 的分子之和 ÷ 分母之和，speed_totals 给出两者），不是各实例速度的算术平均；'
                   '任一实例该项未知，汇总即未知；任一实例该项是下限，汇总也是下限。Codex 上的 API 模型（gpt-6.1-sol、'
                   'gpt-6-luna、DeepSeek）的引擎输出按 relay 日志的 output token ÷ 请求秒数计算，v1 的记录没有保存请求秒数，'
                   '原始 relay 日志已删除，所以这一项按用户 10-22 的选择近似汇总：分子取实例的输出 token（同样来自 relay usage），'
                   '分母取 输出 token ÷ 逐实例引擎输出速度 反推的请求秒数；汇总标为近似（speeds_approximate，表中写"≥≈"），仍是下限。')


def comparisons():
    """The 25 preregistered pairs per scenario (plan §5, 2026-10-21) as (group, first, second): within a harness,
    Strata against every other configuration of the same effort (Codex 8: GPT 2 x 3 and DeepSeek low, high; Claude
    Code 11: Anthropic 3 x 3 and DeepSeek low, high; Strata has no max and DeepSeek no medium, so those efforts are not
    paired with Strata); then, for the two models on both harnesses (DeepSeek, Strata), Codex against Claude Code at
    each of their efforts (6: Strata low/medium/high, DeepSeek low/high/max)."""
    pairs = []
    configs = {c: x for c, x in CONFIGS.items() if c in PREREGISTERED_CONFIGS}  # the phase-3 supplement never pairs
    for harness in ('codex', 'claude-code'):
        strata = [c for c, x in configs.items() if x['harness'] == harness and x['vendor'] == 'strata']
        for s in strata:
            pairs += [(harness, s, c) for c, x in configs.items() if x['harness'] == harness
                      and x['vendor'] != 'strata' and x['effort'] == configs[s]['effort']]
    for vendor in ('strata', 'deepseek'):
        for c, x in configs.items():
            if x['harness'] == 'codex' and x['vendor'] == vendor:
                other = [d for d, y in configs.items() if y['harness'] == 'claude-code' and y['vendor'] == vendor
                         and y['effort'] == x['effort']]
                pairs += [('harness', c, d) for d in other]
    return pairs


# Student t distribution from the regularized incomplete beta function (continued fraction).
def _betacf(a, b, x):
    tiny, qab, qap, qam = 1e-300, a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    d = 1 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        for aa in (m * (b - m) * x / ((qam + m2) * (a + m2)), -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))):
            d = 1 + aa * d
            d = 1 / (d if abs(d) > tiny else tiny)
            c = 1 + aa / c
            c = c if abs(c) > tiny else tiny
            h *= d * c
        if abs(d * c - 1) < 1e-15:
            break
    return h


def betainc(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x))
    if x < (a + 1) / (a + b + 2):
        return front * _betacf(a, b, x) / a
    return 1 - front * _betacf(b, a, 1 - x) / b


def t_two_sided_p(t, df):
    return betainc(df / 2, 0.5, df / (df + t * t))


def t_quantile(p, df):
    """Upper quantile: P(T <= q) = p, for p > 0.5, by bisection."""
    lo, hi = 0.0, 1e3
    for _ in range(200):
        mid = (lo + hi) / 2
        if 1 - t_two_sided_p(mid, df) / 2 < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def mean(values):
    return sum(values) / len(values) if values else None


def sd(values):
    if len(values) < 2:
        return None
    m = mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def median(values):
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def r83_scores(rows):
    """The r8.3 scores of scored rows, or None when any of them lacks one."""
    values = [r.get('score_r83') for r in rows if r['score'] is not None]
    return None if any(v is None for v in values) else values


def welch(a, b):
    """Welch t test; identical-valued sides (SE 0) give p 1 for equal means and 0 otherwise."""
    if len(a) < 2 or len(b) < 2:
        return None
    va, vb = sd(a) ** 2 / len(a), sd(b) ** 2 / len(b)
    d = mean(a) - mean(b)
    se = math.sqrt(va + vb)
    if se == 0:
        return {'d': d, 'se': 0.0, 't': None, 'df': None, 'p': 1.0 if d == 0 else 0.0}
    df = (va + vb) ** 2 / (va ** 2 / (len(a) - 1) + vb ** 2 / (len(b) - 1))
    return {'d': d, 'se': se, 't': d / se, 'df': df, 'p': t_two_sided_p(d / se, df)}


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    adjusted, running = [None] * len(ps), 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(ps) - rank) * ps[i]))
        adjusted[i] = running
    return adjusted


# ---- records ------------------------------------------------------------------------------------------------------

def validate(record, phase=3):
    """Fail fast (user 2026-10-23): a record outside the configuration table, or a phase-3 supplement record in phase
    1 or 2, stops the summary instead of being dropped."""
    missing = [f for f in RECORD_FIELDS if f not in record]
    if missing:
        raise ValueError(f'Record {record.get("id")} lacks {missing} (build it with tools.reviewer.bench_records)')
    if record['config'] not in CONFIGS:
        raise ValueError(f'{record.get("id")}: configuration {record["config"]!r} is not in '
                         'tools.reviewer.bench_records.CONFIG_TABLE')
    if record['config'] in PHASE3_CONFIGS and phase < 3:
        raise ValueError(f'{record["id"]}: configuration {record["config"]} is the phase-3 supplement (use --phase 3)')
    if set(record['tokens']) != set(TOKEN_CLASSES):
        raise ValueError('Tokens must state ' + ', '.join(TOKEN_CLASSES))
    if record['valid'] and record['valid_rank'] is None:
        raise ValueError(f'{record["id"]}: a valid instance without valid_rank (bench_validity.rank_cells)')
    if record['config'] in PHASE3_CONFIGS and record['valid'] and not record['main_statistic']:
        raise ValueError(f'{record["id"]}: a valid phase-3 supplement instance outside the main statistic (records '
                         'ranked with the first-5 cut; rebuild them with tools.reviewer.bench_records)')
    if not record['valid'] and record['score'] is not None:
        raise ValueError(f'{record["id"]}: an invalid instance with a score')


def score_file(score_roots, record_id):
    """<root>/<record id>/score.json in the one score root that holds it; None in none, ValueError in several."""
    roots = [score_roots] if isinstance(score_roots, (str, Path)) else list(score_roots or [])
    found = [Path(root) / record_id / 'score.json' for root in roots if (Path(root) / record_id / 'score.json').is_file()]
    if len(found) > 1:
        raise ValueError(f'{record_id}: score.json in several score roots: {[str(f) for f in found]}')
    return found[0] if found else None


def attach_scores(records, score_root):
    """Fill the score fields of valid records from bench_score's score.json (one root, or a list of roots of which at
    most one may hold a record's score); the score status goes in score_status."""
    for r in records:
        if not r['valid']:
            r['score_status'] = None
            continue
        if r['score'] is not None:
            r.setdefault('score_status', 'record')
            continue
        path = score_file(score_root, r['id'])
        result = json.loads(path.read_text()) if path else None
        status = (result or {}).get('status') or 'unscored'
        r['score_status'] = status
        if status in SCORED_STATUSES:
            r['score'] = result['final']
            r['raw_score'] = result.get('rawScore')
            r['format_penalty'] = result.get('f')
            r['repairs'] = result.get('rRepairable')
            r['score_r83'] = result.get('final_r83')
            r['score_before_penalty'] = result.get('scoreBeforePenalty')
            r['overall_deduction'] = result.get('overall_deduction')
            # Handoffs scored as ARW's explicit modelFailure (no report, or an empty report Main confirmed).
            r['model_failure_handoffs'] = [h.get('k') for h in result.get('handoffs') or []
                                           if str(h.get('scored') or '').startswith('modelFailure')]
    return records


def vendor(record):
    return CONFIGS[record['config']]['vendor']


def in_main(record, phase):
    """Whether a record is in its cell's main statistic in this scoring phase (rank from bench_validity)."""
    if not record['valid']:
        return False
    if phase >= 2 and vendor(record) == 'strata':
        return record['valid_rank'] <= STRATA_PHASE2_MAX
    return bool(record['main_statistic'])


def cell_key(record):
    return (record['config'], record.get('supplementary_label') or '')


def tiers(record):
    value = record['service_tiers']
    return sorted(value) if isinstance(value, (dict, list)) else []


def cost(record):
    """Strata: the measurement-rule equivalent cost; OpenAI: none (ChatGPT plan, tokens only); others as recorded."""
    if vendor(record) == 'strata':
        value = equivalent_cost_usd(record['tokens'])
        return None if value is None else float(value)
    if vendor(record) == 'openai':
        return None
    return record['cost_usd']


def cost_cny(record):
    """DeepSeek: the per-token cost in CNY, shown beside the USD figure; others none."""
    return record.get('cost_cny') if vendor(record) == 'deepseek' else None


FLOOR = '≥'  # prefix of a cost that is a lower bound (a reminder interrupt abandoned requests: plan 14.4)


def both_currencies(dollars, yuan):
    """DeepSeek cost: USD by the official USD / CNY price ratio (user 2026-10-21), the CNY figure in brackets."""
    if dollars is None:
        return '未知'
    return usd(dollars) + ('' if yuan is None else f'（¥{usd(yuan)}）')


def cost_text(record):
    if vendor(record) == 'openai':
        return '只报 token'
    text = both_currencies(cost(record), cost_cny(record)) if vendor(record) == 'deepseek' else usd(cost(record))
    return FLOOR + text if record.get('cost_lower_bound') and text != '未知' else text


def config_cost_text(c):
    if c['vendor'] == 'openai':
        return '只报 token'
    text = (both_currencies(c['cost_usd_total'], c['cost_cny_total']) if c['vendor'] == 'deepseek'
            else usd(c['cost_usd_total']))
    return FLOOR + text if c['cost_lower_bound'] and text != '未知' else text


def total(values):
    """Sum when every value is known; otherwise unknown (no zero filling)."""
    return None if not values or any(v is None for v in values) else sum(values)


# ---- speeds -------------------------------------------------------------------------------------------------------

CLAUDE_API_ARMS = ('anthropic', 'deepseek-claude')


def codex_relay_parts(record):
    """engine_output parts of a Codex API instance (openai, deepseek-codex) whose record predates the stored relay
    parts. The exact numerator (the relay log's output tokens over requests with usage and start/end times) and the
    request seconds were not stored and the v1 relay logs are deleted, so the part is approximated (option (b), user
    2026-10-22): the instance's output tokens, which come from the same relay usage, over output / engine_output, the
    request seconds that would give the recorded speed. Marked approximate; still a lower bound like the speed."""
    output, speed = (record.get('tokens') or {}).get('output'), (record.get('speeds') or {}).get('engine_output')
    if not output or not speed:
        return None
    return {'tokens': output, 'seconds': output / speed, 'approximate': True}


def speed_parts(record):
    """Numerator and denominator of each speed ({'tokens', 'seconds'}, None when the speed is unknown): the record's own
    speed_parts (bench_records.speed_fields) or, for a record without them, rebuilt from the fields the speed was
    computed from (tokens and work seconds; Strata handoff engine read / generated and their seconds; Claude Code API
    output tokens and handoff api_seconds; Codex API: codex_relay_parts). A rebuilt part must reproduce the recorded
    speed, otherwise ValueError."""
    speeds, tokens = record.get('speeds') or {}, record.get('tokens') or {}
    arm = record.get('arm') or ''
    codex_api = not arm.startswith('strata') and arm not in CLAUDE_API_ARMS
    if record.get('speed_parts') is not None:
        stored = record['speed_parts']
        if codex_api and stored.get('engine_output') is None and speeds.get('engine_output') is not None:
            stored = dict(stored, engine_output=codex_relay_parts(record))
        return stored
    handoffs = record.get('handoffs') or record.get('handoff_metrics') or []

    def summed(key):
        values = [h.get(key) for h in handoffs]
        return sum(values) if handoffs and None not in values else None

    def part(k, amount, seconds):
        if speeds.get(k) is None:
            return None
        if amount is None or not seconds or not math.isclose(amount / seconds, speeds[k], rel_tol=1e-12):
            raise ValueError(f"{record.get('id')}: {k} parts {amount} / {seconds} do not give {speeds[k]}")
        return {'tokens': amount, 'seconds': seconds}
    out = {'task_input': part('task_input', tokens.get('uncached_input'), record.get('seconds')),
           'task_output': part('task_output', tokens.get('output'), record.get('seconds')),
           'engine_input': None, 'engine_output': None}
    if arm.startswith('strata'):
        out['engine_input'] = part('engine_input', summed('engine_read'), summed('engine_input_seconds'))
        out['engine_output'] = part('engine_output', summed('engine_generated'), summed('engine_decode_seconds'))
    elif arm in CLAUDE_API_ARMS:
        out['engine_output'] = part('engine_output', tokens.get('output'), summed('api_seconds'))
    elif speeds.get('engine_output') is not None:
        out['engine_output'] = codex_relay_parts(record)
    return out


def speed_totals(rows):
    """Per speed, the summed tokens and seconds over rows when every row has the part; otherwise None."""
    out = {}
    for k in SPEEDS:
        parts = [speed_parts(r)[k] for r in rows]
        out[k] = ({'tokens': sum(p['tokens'] for p in parts), 'seconds': sum(p['seconds'] for p in parts),
                   **({'approximate': True} if any(p.get('approximate') for p in parts) else {})}
                  if rows and None not in parts else None)
    return out


def pooled_speeds(rows):
    """Pooled throughput per speed (user 2026-10-22): total tokens / total seconds over rows, never the arithmetic
    mean of the instance speeds. Unknown (None) when any row's part is unknown (no zero filling, as before)."""
    return {k: (t['tokens'] / t['seconds'] if t and t['seconds'] else None) for k, t in speed_totals(rows).items()}


# ---- statistics ---------------------------------------------------------------------------------------------------

def statistics(config, rows, kind, label, records_in_cell, n_valid):
    """One table row over `rows` (the instances it summarizes). Statistics only over scored instances; a row with an
    unscored instance is incomplete."""
    scored = [r for r in rows if r['score'] is not None]
    scores = [r['score'] for r in scored]
    n = len(scores)
    s = sd(scores)
    se = s / math.sqrt(n) if s is not None else None
    half = t_quantile(0.975, n - 1) * se if se is not None else None
    mean_of = lambda key: mean([r[key] for r in rows]) if rows and all(r[key] is not None for r in rows) else None
    shares = [r['seconds'] / r['time_limit_seconds'] for r in rows
              if r['seconds'] is not None and r['time_limit_seconds']]
    summed = total([cost(r) for r in rows])
    summed_cny = total([cost_cny(r) for r in rows]) if CONFIGS[config]['vendor'] == 'deepseek' else None
    return {'config': config, **CONFIGS[config], 'kind': kind, 'label': label, 'n_valid': n_valid,
            'n_selected': len(rows), 'n': n, 'complete': n == len(rows),
            'invalid': sum(1 for r in records_in_cell if not r['valid']),
            'ids': [r['id'] for r in rows], 'mean': mean(scores), 'sd': s, 'se': se,
            'ci95': None if half is None else [mean(scores) - half, mean(scores) + half],
            'n_negative': sum(1 for v in scores if v < 0), 'min': min(scores) if scores else None,
            'median': median(scores),
            'mean_r83': mean(r83_scores(scored)) if scored and r83_scores(scored) is not None else None,
            'raw_score_mean': mean([r['raw_score'] for r in scored]) if scored and all(
                r['raw_score'] is not None for r in scored) else None,
            'format_penalty_mean': mean([r['format_penalty'] for r in scored]) if scored and all(
                r['format_penalty'] is not None for r in scored) else None,
            'repairs_total': total([r['repairs'] for r in scored]) if n == len(rows) else None,
            'seconds_mean': mean_of('seconds'),
            'time_share_mean': mean(shares) if rows and len(shares) == len(rows) else None,
            'tokens_mean': {k: (mean([r['tokens'][k] for r in rows])
                                if rows and all(r['tokens'][k] is not None for r in rows) else None)
                            for k in TOKEN_CLASSES},
            'token_sources': sorted({r['token_source'] for r in rows if r['token_source']}),
            'tool_calls_mean': mean_of('tool_calls'),
            # Pooled throughput (user 2026-10-22): total tokens / total seconds over the row's instances, not the
            # arithmetic mean of their speeds; the name speeds_mean is kept for the readers.
            'speeds_mean': pooled_speeds(rows),
            'speed_totals': speed_totals(rows),
            'speeds_lower_bound': sorted({k for r in rows for k in r.get('speed_lower_bounds') or []}),
            'speeds_approximate': sorted(k for k, v in speed_totals(rows).items() if v and v.get('approximate')),
            'cost_usd_total': summed, 'cost_usd_mean': None if summed is None else summed / len(rows),
            'cost_lower_bound': any(r.get('cost_lower_bound') for r in rows),
            'cost_cny_total': summed_cny, 'cost_cny_mean': None if summed_cny is None else summed_cny / len(rows),
            'anthropic_quota_percent': (summed * QUOTA_PER_USD if CONFIGS[config]['vendor'] == 'anthropic'
                                        and summed is not None else None),
            'model_ids': sorted({m for r in rows for m in r['model_ids']}),
            'service_tiers': sorted({t for r in rows for t in tiers(r)})}


def by_start(rows):
    return sorted(rows, key=lambda r: r['valid_rank'])


def scenario_summary(records, phase):
    cells = {}
    for r in records:
        cells.setdefault(cell_key(r), []).append(r)
    rows, samples = [], {}
    for (config, supplementary), group in sorted(cells.items()):
        valid = by_start([r for r in group if r['valid']])
        main = [r for r in valid if in_main(r, phase)]
        first = [r for r in valid if r['first_n']]
        kind = 'supplementary' if supplementary else 'phase3' if config in PHASE3_CONFIGS else 'main'
        rows.append(statistics(config, main, kind, supplementary, group, len(valid)))
        if kind != 'phase3' and {r['id'] for r in first} != {r['id'] for r in main}:
            rows.append(statistics(config, first, 'consistency', supplementary or '', group, len(valid)))
        if kind == 'main':
            samples[config] = main
    # Plan §14.4: each supplementary cell also gets a descriptive high+medium row (its own main statistic with the
    # main statistic of the high cell it was requested beside); never in a comparison.
    for (config, supplementary), group in sorted(cells.items()):
        if supplementary:
            extra = [r for r in by_start([r for r in group if r['valid']]) if in_main(r, phase)]
            rows.append(statistics(config, samples.get(config, []) + extra, 'sensitivity',
                                   f'high+medium 合并（描述性，{supplementary}）', [], len(samples.get(config, []) + extra)))
    order = {'main': 0, 'phase3': 0, 'consistency': 1, 'supplementary': 2, 'sensitivity': 3}
    rows.sort(key=lambda c: (c['config'], order[c['kind']], c['label']))

    tests = []
    for group_name, first, second in comparisons():
        a, b = samples.get(first, []), samples.get(second, [])
        complete = bool(a) and bool(b) and all(r['score'] is not None for r in a + b)
        test = welch([r['score'] for r in a], [r['score'] for r in b]) if complete else None
        old_a, old_b = (r83_scores(a), r83_scores(b)) if complete else (None, None)
        old = welch(old_a, old_b) if old_a is not None and old_b is not None else None
        tests.append({'group': group_name, 'first': first, 'second': second, 'n_first': len(a), 'n_second': len(b),
                      'scored_first': sum(r['score'] is not None for r in a),
                      'scored_second': sum(r['score'] is not None for r in b), 'complete': complete,
                      **(test or {'d': None, 'se': None, 't': None, 'df': None, 'p': None}),
                      'r83_known': old_a is not None and old_b is not None,
                      'd_r83': (old or {}).get('d'), 'p_r83': (old or {}).get('p')})
    adjusted = holm([1.0 if t['p'] is None else t['p'] for t in tests])
    adjusted_r83 = holm([1.0 if t['p_r83'] is None else t['p_r83'] for t in tests])
    verdict = lambda complete, d, p, p_holm: ('未计分完' if not complete else '未分出' if p is None or p_holm >= ALPHA
                                              else '高于' if d > 0 else '低于')
    known = all(t['r83_known'] for t in tests if t['complete'])
    for t, p, p_old in zip(tests, adjusted, adjusted_r83):
        t['p_holm'] = p
        t['verdict'] = verdict(t['complete'], t['d'], t['p'], p)
        # r8.3 Holm over the same family; unknown when any complete comparison lacks r8.3 scores.
        t['p_holm_r83'] = p_old if known else None
        t['verdict_r83'] = verdict(t['complete'], t['d_r83'], t['p_r83'], p_old) if known else None
        t['verdict_changed'] = None if t['verdict_r83'] is None else t['verdict'] != t['verdict_r83']
    for r in records:
        r['in_main'] = in_main(r, phase)
    return {'configs': rows, 'comparisons': tests,
            'instances': sorted(records, key=lambda r: (r['config'], r.get('supplementary_label') or '',
                                                        r['valid_rank'] or 99, r['id']))}


def summarize(records, phase=1):
    if phase not in PHASES:
        raise ValueError(f'phase must be one of {PHASES}')
    for record in records:
        validate(record, phase)
    ids = [r['id'] for r in records]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate record id')
    scenarios = sorted({r['scenario'] for r in records})
    out = {s: scenario_summary([r for r in records if r['scenario'] == s], phase) for s in scenarios}
    complete = all(c['complete'] for s in out.values() for c in s['configs'] if c['kind'] in ('main', 'phase3'))
    return {'phase': phase, 'alpha': ALPHA, 'holm_family_size': len(comparisons()),
            'preregistered_n': PREREGISTERED_N, 'strata_phase2_max': STRATA_PHASE2_MAX, 'complete': complete,
            'scenarios': out}


# ---- output -------------------------------------------------------------------------------------------------------

def fmt(value, digits=3):
    return '未知' if value is None else format(value, f'.{digits}f')


def usd(value):
    """Three decimals (measurement rule); a nonzero amount never shows as zero."""
    if value is not None and 0 < abs(value) < 0.0005:
        return '<0.001'
    return fmt(value)


def count(value):
    return '未知' if value is None else format(round(value), ',')


def label(config):
    c = CONFIGS[config]
    return f"{config} {c['harness']} {c['model']} {c['effort']}"


KIND_LABEL = {'main': '主统计', 'consistency': '一致性行（前 5）', 'supplementary': '补充行', 'sensitivity': '敏感性行',
              'phase3': '第三阶段补充（不比较）'}


def phase_text(summary):
    if summary['phase'] == 1:
        return ('第一阶段：只用预登记实例（未合并的格取按开始时刻的前 5 个有效实例，DeepSeek 合并格取全部有效实例）。')
    text = (f"第二阶段：Strata 各格取全部有效实例（至多 {summary['strata_phase2_max']} 个，不足按实际 n），"
            '其余同第一阶段。')
    if summary['phase'] == 2:
        return text
    return ('第三阶段补充：第二阶段的全部实例与统计不变，另加 gpt-6-luna xhigh（配置 28）、max（配置 29）'
            '两个补充配置（Codex，各格取全部有效实例，不截取前 5 个，也没有一致性行：用户 2026-10-23，非因分数加跑的有效实例'
            '与预登记实例效力相同）；它们只给配置行和逐实例结果，不进预登记比较和 Holm 族。'
            + text)


def markdown(summary):
    lines = ['# 多模型 benchmark v1 汇总', '', phase_text(summary), '',
             f"每个场景 {summary['holm_family_size']} 个预登记比较，Holm 校正，双侧 α = {summary['alpha']}，"
             'Welch t 检验（Welch–Satterthwaite 自由度）。主统计多于前 5 个的格另给一致性行（按开始时刻的前 5 个'
             + ('；第三阶段补充配置不给' if summary['phase'] >= 3 else '') + '）；'
             '补充行和敏感性行不进比较。不给比值、综合分和排名。', '']
    if not summary['complete']:
        lines += ['**未计分完**：有主统计实例还没有最终分数，相关比较标"未计分完"。', '']
    for scenario, result in summary['scenarios'].items():
        lines += [f'## {scenario}', '', '### 配置', '',
                  '| 配置 | 行 | 有效 | 选入 n | 已计分 | 无效 | 均值 ± SD | SE | 95% 区间 | 负分数 | 最小 | 中位数 | r8.3 均值 | rawScore | f | 修复 | 耗时（分钟） | 占时限 | 未缓存 | 缓存 | 输出 | token 来源 | 工具调用 | 费用（美元；DeepSeek 括号内为人民币 ¥） | 周额度 | 模型 ID | service tier |',
                  '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
        for c in result['configs']:
            t = c['tokens_mean']
            ci = '未知' if c['ci95'] is None else f"{fmt(c['ci95'][0])}–{fmt(c['ci95'][1])}"
            kind = KIND_LABEL[c['kind']] + (f"（{c['label']}）" if c['label'] and c['kind'] != 'sensitivity' else '')
            if c['kind'] == 'sensitivity':
                kind = KIND_LABEL['sensitivity'] + f"：{c['label']}"
            lines.append('| ' + ' | '.join([
                label(c['config']), kind, str(c['n_valid']), str(c['n_selected']), str(c['n']),
                str(c['invalid']) if c['kind'] in ('main', 'supplementary') else '', f"{fmt(c['mean'])} ± {fmt(c['sd'])}",
                fmt(c['se']), ci, str(c['n_negative']), fmt(c['min']), fmt(c['median']), fmt(c['mean_r83']),
                fmt(c['raw_score_mean']), fmt(c['format_penalty_mean']), count(c['repairs_total']),
                minutes(c['seconds_mean']), fmt(c['time_share_mean'], 2), count(t['uncached_input']),
                count(t['cached_input']), count(t['output']), '、'.join(c['token_sources']) or '未知',
                fmt(c['tool_calls_mean'], 1),
                config_cost_text(c),
                '' if c['anthropic_quota_percent'] is None else fmt(c['anthropic_quota_percent'], 2) + '%',
                '、'.join(c['model_ids']) or '未知', '、'.join(c['service_tiers']) or '未知']) + ' |')
        lines += ['', '### 预登记比较', '', 'r8.3 列：同一批实例按 r8.3（截到 0、整体扣减相乘）计分的对照（plan §14.1）。', '',
                  '| 组 | 前者 | 后者 | n | 差值 | SE | t | 自由度 | p | Holm p | 结论 | r8.3 差值 | r8.3 Holm p | r8.3 结论 | 结论改变 |',
                  '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
        for r in result['comparisons']:
            n = f"{r['n_first']} / {r['n_second']}"
            if not r['complete']:
                n += f"（已计分 {r['scored_first']} / {r['scored_second']}）"
            lines.append('| ' + ' | '.join([
                r['group'], label(r['first']), label(r['second']), n, fmt(r['d']), fmt(r['se']),
                fmt(r['t'], 2), fmt(r['df'], 1), fmt(r['p'], 4), fmt(r['p_holm'], 4), r['verdict'],
                fmt(r['d_r83']), fmt(r['p_holm_r83'], 4), r['verdict_r83'] or '未知',
                '未知' if r['verdict_changed'] is None else '是' if r['verdict_changed'] else '否']) + ' |')
        speeds = any(r.get('speeds') for r in result['instances'])
        head = ['配置', '实例', '补充', '有效', '序', '主统计', '分数', 'r8.3 分数', 'rawScore', 'f', '修复', '耗时（分钟）', '占时限',
                '未缓存', '缓存', '输出', '工具调用', '费用（美元；DeepSeek 括号内为人民币 ¥）', '模型 ID', 'service tier']
        if speeds:
            head += ['引擎输入 tok/s', '引擎输出 tok/s', '任务平均输入 tok/s', '任务平均输出 tok/s']
        note = (['速度：引擎输入、引擎输出是模型直接速度，任务平均输入、输出是用户感知速度（未缓存输入、输出 ÷ 工作秒数）。'
                 'API 模型分不出输入处理时间，引擎输入记未知；引擎输出按 API 请求时间算，含首 token 延迟和输入处理，'
                 '是下限（≥）。', '', SPEED_POOL_NOTE, ''] if speeds else [])
        lines += ['', '### 逐实例', '', *note, '| ' + ' | '.join(head) + ' |', '|' + '---|' * len(head)]
        for r in result['instances']:
            share = (r['seconds'] / r['time_limit_seconds']
                     if r['seconds'] is not None and r['time_limit_seconds'] else None)
            score = fmt(r['score']) if r['score'] is not None or not r['valid'] else (r.get('score_status') or 'unscored')
            row = [label(r['config']), r['id'].split('/')[-1], r.get('supplementary_label') or '',
                   '是' if r['valid'] else '否', '' if r['valid_rank'] is None else str(r['valid_rank']),
                   '是' if r['in_main'] else '', score, fmt(r.get('score_r83')) if r['score'] is not None else '',
                   fmt(r['raw_score']), fmt(r['format_penalty']),
                   count(r['repairs']), minutes(r['seconds']), fmt(share, 2),
                   *(count(r['tokens'][k]) for k in TOKEN_CLASSES), count(r['tool_calls']),
                   cost_text(r),
                   '、'.join(r['model_ids']) or '未知', '、'.join(tiers(r)) or '未知']
            if speeds:
                row += [speed_text((r.get('speeds') or {}).get(k), k in (r.get('speed_lower_bounds') or []))
                        for k in SPEEDS]
            lines.append('| ' + ' | '.join(row) + ' |')
        lines.append('')
    lines += reconciliation_lines(summary.get('deepseek_reconciliation'))
    return '\n'.join(lines)


def speed_text(value, lower):
    """A speed (token/s, one decimal); a lower bound is marked with ≥, an unknown one says so."""
    return '未知' if value is None else ('≥' if lower else '') + fmt(value, 1)


def reconciliation_lines(rec):
    """DeepSeek batch reconciliation (plan 14.4): balance difference against the per-token sum, report only."""
    if not rec:
        return []
    lines = ['## DeepSeek 批次对账', '',
             '余额差取自 schedule.jsonl 每次启动前读到的余额（只用已落盘记录，不调余额接口），窗口两端都是没有实例在跑的读数；'
             '计价合计是窗口内启动并结束的实例按请求时刻计的人民币。偏差 = 余额差 − 计价合计，只报告，不调整任何实例的费用'
             '（计划 14.4 没有规定处理）；窗口内实例之外的花费（定价核对、探测）也落在偏差里，被弃请求的 token 不进计价合计。',
             '', '| 窗口 | 余额（起 → 止） | 余额差 | 实例数 | 无费用 | 计价合计 | 偏差 | 偏差占余额差 |',
             '|---|---|---|---|---|---|---|---|']

    def row(name, w):
        ratio = '未知' if w['deviation_ratio'] is None else f"{w['deviation_ratio'] * 100:.2f}%"
        return (f"| {name} | {w['balance'][0]:.2f} → {w['balance'][1]:.2f} | ¥{w['balance_difference']:.2f} | "
                f"{w['instances']} | {w['instances_without_cost']} | ¥{w['token_sum']:.4f} | "
                f"¥{w['deviation']:.4f} | {ratio} |")

    lines.append(row('全部', rec))
    lines += [row(day, w) for day, w in rec['by_date'].items()]
    return lines + ['']


SUMMARY_RECORD_FIELDS = ('id', 'arm', 'scenario', 'config', 'supplementary_label', 'attempt', 'started', 'valid',
                         'validity', 'valid_rank', 'first_n', 'main_statistic', 'cell_pooled', 'in_main',
                         'score_status', 'score', 'raw_score', 'format_penalty', 'repairs', 'seconds',
                         'time_limit_seconds', 'tokens', 'token_source', 'tool_calls', 'cost_usd', 'cost_cny', 'cost_basis', 'cost_lower_bound',
                         'model_ids', 'service_tiers', 'speeds', 'speed_parts', 'speed_basis', 'speed_lower_bounds',
                         # Fields for tools.reviewer.benchmark_export (scoring details, pauses, effort, handoffs).
                         'score_r83', 'score_before_penalty', 'overall_deduction', 'model_failure_handoffs',
                         'requested_effort', 'effective_effort', 'pooled', 'pause_known', 'pause_count',
                         'continue_count', 'seconds_adjustment', 'harness_generation', 'harness_reported_cost_usd',
                         'handoff_metrics')
CLAUDE_USAGE_ARMS = ('anthropic', 'deepseek-claude', 'strata-claude')


def cache_write(usage):
    """Claude Code result usage cache writes (counted inside uncached_input by bench_records.usage_tokens), with the
    1-hour / 5-minute split when the usage gives it; None without usage."""
    if not isinstance(usage, dict):
        return None
    split = usage.get('cache_creation') if isinstance(usage.get('cache_creation'), dict) else {}
    return {'total': usage.get('cache_creation_input_tokens') or 0,
            'ephemeral_1h': split.get('ephemeral_1h_input_tokens'), 'ephemeral_5m': split.get('ephemeral_5m_input_tokens')}


def handoff_metrics(record):
    """Per-handoff metrics of a record (Spec Readiness has two: runtime-migration, artifact-promotion) without paths,
    ids or report content; [] for a record without handoffs."""
    failures = set(record.get('model_failure_handoffs') or [])
    out = []
    for h in record.get('handoffs') or []:
        api = record.get('arm') in CLAUDE_USAGE_ARMS and record.get('arm') != 'strata-claude'
        out.append({'k': h.get('k'), 'sub_scenario': h.get('sub_scenario'), 'seconds': h.get('seconds'),
                    'tokens': h.get('tokens') if isinstance(h.get('tokens'), dict) else None,
                    'tokens_lower_bound': bool(h.get('tokens_lower_bound')),
                    'cache_write': cache_write(h.get('api_usage')) if api else None,
                    'tool_calls': h.get('tool_calls'), 'api_seconds': h.get('api_seconds'),
                    'engine_read': h.get('engine_read'), 'engine_generated': h.get('engine_generated'),
                    'engine_input_seconds': h.get('engine_input_seconds'),
                    'engine_decode_seconds': h.get('engine_decode_seconds'),
                    'model_failure': h.get('k') in failures,
                    # Status enumerations only: final_status (ARW completion or the Claude Code result form) and,
                    # on Claude Code, why the continuation loop stopped (delivered, model_error, hard_limit).
                    'final_status': h.get('final_status'), 'continuation_stop': h.get('continuation_stop'),
                    'harness_reported_cost_usd': h.get('cost_usd') if record.get('arm') in CLAUDE_USAGE_ARMS else None})
    return out


def harness_reported_cost(record):
    """Claude Code result total_cost_usd over the handoffs (any Claude Code arm, Anthropic price list whatever the
    backend), None unless every handoff has one."""
    if record.get('arm') not in CLAUDE_USAGE_ARMS or not record.get('handoffs'):
        return None
    costs = [h.get('cost_usd') for h in record['handoffs']]
    return None if None in costs else sum(costs)


def compact(summary):
    """summary.json keeps the summary fields of each instance, not the whole run record."""
    out = dict(summary, scenarios={})
    for name, result in summary['scenarios'].items():
        rows = []
        for r in result['instances']:
            row = {k: r.get(k) for k in SUMMARY_RECORD_FIELDS}
            row['handoff_metrics'] = handoff_metrics(r)
            row['speed_parts'] = speed_parts(r)
            row['harness_reported_cost_usd'] = harness_reported_cost(r)
            rows.append(row)
        out['scenarios'][name] = dict(result, instances=rows)
    return out


def deepseek_reconciliation(records, data_root=None):
    """bench_validity.deepseek_batch_reconciliation over the arm's schedule.jsonl with the records' per-token costs;
    None when the arm has no schedule or no records."""
    from tools.reviewer import bench_records, bench_validity
    root = Path(data_root or bench_records.ROOT) / bench_records.LAYOUT['deepseek-codex'][0]
    costs = {'/'.join(Path(r['dir']).parts[-2:]): r['cost_cny'] for r in records
             if r['arm'].startswith('deepseek') and r.get('cost_cny') is not None}
    if not costs or not (root / 'schedule.jsonl').is_file():
        return None
    return bench_validity.deepseek_batch_reconciliation(root, costs)


def load_records(records_path=None, data_root=None):
    """Records from one JSON Lines file or a list of them (phase 3: the phase-2 records plus the supplement), or built
    from the run directories."""
    if records_path:
        paths = [records_path] if isinstance(records_path, (str, Path)) else list(records_path)
        return [json.loads(line) for p in paths for line in Path(p).read_text().splitlines() if line.strip()]
    from tools.reviewer import bench_records
    return bench_records.all_records(data_root=data_root)


def generator(phase):
    """The source marker of summary.json (user 2026-10-23: summaries come from this tool only; benchmark_export
    refuses a summary without it)."""
    return {'tool': GENERATOR, 'sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'phase': phase}


def write(out, records_path=None, data_root=None, score_root=None, phase=1, reconciliation_from=None):
    """reconciliation_from: a published summary.json whose deepseek_reconciliation is kept when the DeepSeek
    schedule.jsonl it was computed from is gone (the phase-2 and phase-3 summaries read records.jsonl)."""
    records = load_records(records_path, data_root)
    attach_scores(records, score_root)
    summary = summarize(records, phase)
    summary['deepseek_reconciliation'] = deepseek_reconciliation(records, data_root)
    if reconciliation_from and summary['deepseek_reconciliation'] is None:
        summary['deepseek_reconciliation'] = json.loads(Path(reconciliation_from).read_text())['deepseek_reconciliation']
    summary['generator'] = generator(phase)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    (out / 'summary.json').write_text(json.dumps(compact(summary), ensure_ascii=False, indent=1) + '\n')
    (out / 'summary.md').write_text(markdown(summary))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--data-root', type=Path, help='checkout holding .tmp (default: this one)')
    parser.add_argument('--records', type=Path, action='append',
                        help='bench_records JSON Lines instead of reading the run directories; repeatable (phase 3: '
                             'the phase-2 records, then the supplement records)')
    parser.add_argument('--score-root', type=Path, action='append',
                        help='bench_score work root (default: <data root>/.tmp/bench-score); repeatable, a record\'s '
                             'score.json may be in one root only')
    parser.add_argument('--reconciliation-from', type=Path,
                        help='summary.json whose deepseek_reconciliation is kept when it cannot be recomputed')
    parser.add_argument('--phase', type=int, choices=PHASES, default=1, help='scoring phase (plan §14.1; default 1)')
    parser.add_argument('--out', type=Path, required=True, help='fresh output directory')
    args = parser.parse_args()
    if args.score_root is None:
        from tools.reviewer import bench_records
        args.score_root = [Path(args.data_root or bench_records.ROOT) / '.tmp/bench-score']
    result = write(args.out, args.records, args.data_root, args.score_root, args.phase, args.reconciliation_from)
    print(json.dumps({s: {'instances': len(v['instances']), 'comparisons': len(v['comparisons'])}
                      for s, v in result['scenarios'].items()}))
