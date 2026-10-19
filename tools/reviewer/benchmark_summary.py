"""Cross-model summary of the multi-model benchmark v1 (benchmarks/multi-model-v1/plan.md §5).

Input: JSON Lines, one normalized record per instance (fields in RECORD_FIELDS; `tokens` holds uncached_input,
cached_input and output, any of them null when unknown; `speeds` is optional and holds the four measurement-rule
speeds). Output: summary.json and summary.md in a fresh directory, per scenario:
- per configuration: n, mean ± SD, SE and t 95% interval, raw score, format penalty and repairs, minutes and share of
  the time limit, the three token classes and their source, tool calls, cost, returned model IDs and service tiers;
- the per-instance table, invalid instances included and marked (measurement rule; G4: Code Standards had none);
- the 27 preregistered comparisons: Welch t with Welch-Satterthwaite df, Holm within the scenario, two-sided
  alpha 0.05; Strata contributes its first 5 valid instances. A comparison without two scored sides of n >= 2 keeps
  its place in the family with p = 1. No ratios, combined scores or ranks (D7).

    python3 -m tools.reviewer.benchmark_summary --records <records.jsonl> --out reports/<run>/
"""
import argparse
import json
import math
from pathlib import Path

from tools.metrics.measurement_format import equivalent_cost_usd, minutes

EFFORTS = ('low', 'medium', 'high')
HARNESS_MODELS = [('codex', 'gpt-6.1-sol', 'openai'), ('codex', 'gpt-6-luna', 'openai'),
                  ('codex', 'deepseek-flash', 'deepseek'), ('codex', 'strata-iq3_xxs', 'strata'),
                  ('claude-code', 'opus', 'anthropic'), ('claude-code', 'sonnet', 'anthropic'),
                  ('claude-code', 'haiku', 'anthropic'), ('claude-code', 'deepseek-flash', 'deepseek'),
                  ('claude-code', 'strata-iq3_xxs', 'strata')]
# Plan §2: configurations 1-27, three efforts per harness-model row.
CONFIGS = {3 * row + i + 1: {'harness': h, 'model': m, 'vendor': v, 'effort': e}
           for row, (h, m, v) in enumerate(HARNESS_MODELS) for i, e in enumerate(EFFORTS)}
RECORD_FIELDS = ('scenario', 'config', 'instance', 'valid', 'score', 'raw_score', 'format_penalty', 'repairs',
                 'seconds', 'time_limit_seconds', 'tokens', 'token_source', 'tool_calls', 'cost_usd', 'model_ids',
                 'service_tiers')
TOKEN_CLASSES = ('uncached_input', 'cached_input', 'output')
SPEEDS = ('engine_input', 'engine_output', 'task_input', 'task_output')
STRATA_PREREGISTERED = 5
ALPHA = 0.05
QUOTA_PER_USD = 0.086  # % of the Anthropic weekly quota per API-equivalent USD (estimate.sh calibration)


def comparisons():
    """The 27 preregistered pairs (first, second): Strata against every other configuration of its harness and
    effort, then DeepSeek's and Strata's Codex configuration against their Claude Code one."""
    pairs = []
    for i in range(3):
        pairs += [(10 + i, other + i) for other in (1, 4, 7)]
        pairs += [(25 + i, other + i) for other in (13, 16, 19, 22)]
        pairs += [(7 + i, 22 + i), (10 + i, 25 + i)]
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


def validate(record):
    missing = [f for f in RECORD_FIELDS if f not in record]
    if missing:
        raise ValueError(f'Record {record.get("scenario")}/{record.get("config")}/{record.get("instance")} lacks {missing}')
    if record['config'] not in CONFIGS:
        raise ValueError('Unknown configuration ' + repr(record['config']))
    if set(record['tokens']) != set(TOKEN_CLASSES):
        raise ValueError('Tokens must state ' + ', '.join(TOKEN_CLASSES))
    if record['valid'] and record['score'] is None:
        raise ValueError('A valid instance needs its score')


def cost(record):
    """Strata: the measurement-rule equivalent cost; OpenAI: none (ChatGPT plan, tokens only); others as recorded."""
    vendor = CONFIGS[record['config']]['vendor']
    if vendor == 'strata':
        value = equivalent_cost_usd(record['tokens'])
        return None if value is None else float(value)
    if vendor == 'openai':
        return None
    return record['cost_usd']


def total(values):
    """Sum when every value is known; otherwise unknown (no zero filling)."""
    return None if not values or any(v is None for v in values) else sum(values)


def config_summary(config, records):
    valid = sorted((r for r in records if r['valid']), key=lambda r: r['instance'])
    scores = [r['score'] for r in valid]
    n = len(scores)
    s = sd(scores)
    se = s / math.sqrt(n) if s is not None else None
    half = t_quantile(0.975, n - 1) * se if se is not None else None
    mean_of = lambda key: mean([r[key] for r in valid]) if valid and all(r[key] is not None for r in valid) else None
    shares = [r['seconds'] / r['time_limit_seconds'] for r in valid
              if r['seconds'] is not None and r['time_limit_seconds']]
    costs = [cost(r) for r in valid]
    vendor = CONFIGS[config]['vendor']
    summed = total(costs)
    return {'config': config, **CONFIGS[config], 'n': n, 'invalid': len(records) - n, 'mean': mean(scores), 'sd': s,
            'se': se, 'ci95': None if half is None else [mean(scores) - half, mean(scores) + half],
            'raw_score_mean': mean_of('raw_score'), 'format_penalty_mean': mean_of('format_penalty'),
            'repairs_total': total([r['repairs'] for r in valid]), 'seconds_mean': mean_of('seconds'),
            'time_share_mean': mean(shares) if len(shares) == n and n else None,
            'tokens_mean': {k: (mean([r['tokens'][k] for r in valid])
                                if valid and all(r['tokens'][k] is not None for r in valid) else None)
                            for k in TOKEN_CLASSES},
            'token_sources': sorted({r['token_source'] for r in valid}), 'tool_calls_mean': mean_of('tool_calls'),
            'cost_usd_total': summed, 'cost_usd_mean': None if summed is None else summed / n,
            'anthropic_quota_percent': summed * QUOTA_PER_USD if vendor == 'anthropic' and summed is not None else None,
            'model_ids': sorted({m for r in valid for m in r['model_ids']}),
            'service_tiers': sorted({t for r in valid for t in r['service_tiers']})}


def scenario_summary(records):
    by_config = {c: [r for r in records if r['config'] == c] for c in sorted({r['config'] for r in records})}
    configs = [config_summary(c, rs) for c, rs in by_config.items()]

    def sample(config):
        valid = sorted((r for r in by_config.get(config, []) if r['valid']), key=lambda r: r['instance'])
        if CONFIGS[config]['vendor'] == 'strata':
            valid = valid[:STRATA_PREREGISTERED]
        return [r['score'] for r in valid]

    rows = []
    for first, second in comparisons():
        a, b = sample(first), sample(second)
        test = welch(a, b)
        rows.append({'first': first, 'second': second, 'n_first': len(a), 'n_second': len(b),
                     **(test or {'d': None, 'se': None, 't': None, 'df': None, 'p': None})})
    adjusted = holm([1.0 if r['p'] is None else r['p'] for r in rows])
    for row, p in zip(rows, adjusted):
        row['p_holm'] = p
        row['verdict'] = ('未分出' if row['p'] is None or p >= ALPHA else '高于' if row['d'] > 0 else '低于')
    return {'configs': configs, 'comparisons': rows,
            'instances': sorted(records, key=lambda r: (r['config'], r['instance']))}


def summarize(records):
    for record in records:
        validate(record)
    keys = [(r['scenario'], r['config'], r['instance']) for r in records]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate scenario/config/instance record')
    scenarios = sorted({r['scenario'] for r in records})
    return {'alpha': ALPHA, 'holm_family_size': len(comparisons()), 'strata_preregistered': STRATA_PREREGISTERED,
            'scenarios': {s: scenario_summary([r for r in records if r['scenario'] == s]) for s in scenarios}}


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


def markdown(summary):
    lines = ['# 多模型 benchmark v1 汇总', '',
             f"每个场景 {summary['holm_family_size']} 个预登记比较，Holm 校正，双侧 α = {summary['alpha']}，"
             f"Welch t 检验（Welch–Satterthwaite 自由度）；Strata 只用前 {summary['strata_preregistered']} 个有效实例。"
             '不给比值、综合分和排名。', '']
    for scenario, result in summary['scenarios'].items():
        lines += [f'## {scenario}', '', '### 配置', '',
                  '| 配置 | n | 无效 | 均值 ± SD | SE | 95% 区间 | rawScore | f | 修复 | 耗时（分钟） | 占时限 | 未缓存 | 缓存 | 输出 | token 来源 | 工具调用 | 费用（美元） | 周额度 | 模型 ID | service tier |',
                  '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
        for c in result['configs']:
            t = c['tokens_mean']
            ci = '未知' if c['ci95'] is None else f"{fmt(c['ci95'][0])}–{fmt(c['ci95'][1])}"
            lines.append('| ' + ' | '.join([
                label(c['config']), str(c['n']), str(c['invalid']), f"{fmt(c['mean'])} ± {fmt(c['sd'])}", fmt(c['se']),
                ci, fmt(c['raw_score_mean']), fmt(c['format_penalty_mean']), count(c['repairs_total']),
                minutes(c['seconds_mean']), fmt(c['time_share_mean'], 2), count(t['uncached_input']),
                count(t['cached_input']), count(t['output']), '、'.join(c['token_sources']) or '未知',
                fmt(c['tool_calls_mean'], 1),
                '只报 token' if c['vendor'] == 'openai' else usd(c['cost_usd_total']),
                '' if c['anthropic_quota_percent'] is None else fmt(c['anthropic_quota_percent'], 2) + '%',
                '、'.join(c['model_ids']) or '未知', '、'.join(c['service_tiers']) or '未知']) + ' |')
        lines += ['', '### 预登记比较', '', '| 前者 | 后者 | n | 差值 | SE | t | 自由度 | p | Holm p | 结论 |',
                  '|---|---|---|---|---|---|---|---|---|---|']
        for r in result['comparisons']:
            lines.append('| ' + ' | '.join([
                label(r['first']), label(r['second']), f"{r['n_first']} / {r['n_second']}", fmt(r['d']), fmt(r['se']),
                fmt(r['t'], 2), fmt(r['df'], 1), fmt(r['p'], 4), fmt(r['p_holm'], 4), r['verdict']]) + ' |')
        speeds = any(r.get('speeds') for r in result['instances'])
        head = ['配置', '实例', '有效', '分数', 'rawScore', 'f', '修复', '耗时（分钟）', '占时限', '未缓存', '缓存', '输出',
                '工具调用', '费用（美元）', '模型 ID', 'service tier']
        if speeds:
            head += ['引擎输入 tok/s', '引擎输出 tok/s', '任务平均输入 tok/s', '任务平均输出 tok/s']
        lines += ['', '### 逐实例', '', '| ' + ' | '.join(head) + ' |', '|' + '---|' * len(head)]
        for r in result['instances']:
            share = (r['seconds'] / r['time_limit_seconds']
                     if r['seconds'] is not None and r['time_limit_seconds'] else None)
            row = [label(r['config']), str(r['instance']), '是' if r['valid'] else '否', fmt(r['score']),
                   fmt(r['raw_score']), fmt(r['format_penalty']), count(r['repairs']), minutes(r['seconds']),
                   fmt(share, 2), *(count(r['tokens'][k]) for k in TOKEN_CLASSES), count(r['tool_calls']),
                   '只报 token' if CONFIGS[r['config']]['vendor'] == 'openai' else usd(cost(r)),
                   '、'.join(r['model_ids']) or '未知', '、'.join(r['service_tiers']) or '未知']
            if speeds:
                row += [fmt((r.get('speeds') or {}).get(k), 1) for k in SPEEDS]
            lines.append('| ' + ' | '.join(row) + ' |')
        lines.append('')
    return '\n'.join(lines)


def write(records_path, out):
    records = [json.loads(line) for line in Path(records_path).read_text().splitlines() if line.strip()]
    summary = summarize(records)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1) + '\n')
    (out / 'summary.md').write_text(markdown(summary))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--records', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True, help='fresh output directory')
    args = parser.parse_args()
    result = write(args.records, args.out)
    print(json.dumps({s: len(v['instances']) for s, v in result['scenarios'].items()}))
