#!/usr/bin/env python3
"""Hydrogen supplement: cell statistics, paired tier differences, v1 comparison table, export (plan.md §5, §7). Python 3 stdlib; run with -I.

  summarize.py            writes OUT/summary.json, OUT/summary.md, OUT/hydrogen-results.json (instance-level export)
Inputs: .tmp/hydrobench/records.jsonl (valid flag, seconds, tokens), .tmp/hydrobench/score/<record id>/score.json (r8.4 final),
the published v1 file reports/v0.1.45/multi-model-benchmark/benchmark-results.json (read only).
"""
import json
import math
import re
import sys
import time
from pathlib import Path

ROOT = Path('/home/pello/projects/qwen-strata')
sys.path.insert(0, str(ROOT))
from tools.reviewer.benchmark_summary import mean, median, sd, t_quantile  # noqa: E402

BASE = ROOT / '.tmp/hydrobench'
SCORE = BASE / 'score'
V1 = ROOT / 'reports/v0.1.45/multi-model-benchmark/benchmark-results.json'
OUT = Path(__file__).resolve().parent / 'results'
EFFORTS = ('medium', 'high', 'xhigh')
CONFIG = {'medium': 30, 'high': 31, 'xhigh': 32}
SCEN = {'ca': 'commit-audit-v3', 'cs': 'code-spec-v5', 'cstd': 'code-standards-v5.1', 'sr': 'spec-readiness-v4.3'}
SHORT = {v: k for k, v in SCEN.items()}
NAME = {'ca': 'Commit Audit', 'cs': 'Code Spec', 'cstd': 'Code Standards', 'sr': 'Spec Readiness'}
AGY_UPGRADE = time.mktime(time.strptime('2026-11-14 14:55', '%Y-%m-%d %H:%M'))   # local time = JST; agy 1.5.8 -> 1.5.9 (binary mtime)
EPS = 1e-9


def ci(values):
    n = len(values)
    if n < 2:
        return None
    half = t_quantile(0.975, n - 1) * sd(values) / math.sqrt(n)
    return [mean(values) - half, mean(values) + half]


def stat(values):
    if not values:
        return {'n': 0}
    return {'n': len(values), 'mean': mean(values), 'sd': sd(values), 'ci95': ci(values), 'min': min(values), 'median': median(values),
            'negative': sum(v < 0 for v in values)}


def pair(a, b):
    """Paired difference b - a over the instances in rank order (same index in both cells)."""
    n = min(len(a), len(b))
    d = [b[i] - a[i] for i in range(n)]
    return {'n': n, 'mean_diff': mean(d), 'sd_diff': sd(d), 'ci95': ci(d), 'wins_b': sum(x > EPS for x in d),
            'ties': sum(abs(x) <= EPS for x in d), 'wins_a': sum(x < -EPS for x in d), 'diffs': d}


def load():
    rows = [json.loads(l) for l in (BASE / 'records.jsonl').read_text().splitlines() if l.strip()]
    for r in rows:
        r['short'] = SHORT[r['scenario']]
        p = SCORE / r['id'] / 'score.json'
        r['score_json'] = json.loads(p.read_text()) if p.is_file() else None
    return rows


def cells(rows):
    out = {}
    for e in EFFORTS:
        for s in SCEN:
            sel = [r for r in rows if r['effort'] == e and r['short'] == s and r['valid']]
            sel.sort(key=lambda r: (r['valid_rank'] or 0))
            out[(e, s)] = sel
    return out


def final(r):
    sj = r['score_json']
    return sj['final'] if sj and sj.get('status') == 'final' else None


def agy_version(r):
    return '1.5.8' if (r['started'] or 0) < AGY_UPGRADE else '1.5.9'


def cell_row(sel, invalid):
    scores = [final(r) for r in sel]
    if any(x is None for x in scores):
        return {'scored': False, 'n_valid': len(sel)}
    secs = [r['seconds'] for r in sel]
    out = {'scored': True, 'n_valid': len(sel), 'n_invalid': invalid, 'score': stat(scores)}
    out['raw'] = stat([r['score_json'].get('rawScore') for r in sel if r['score_json'].get('rawScore') is not None])
    out['wall_s'] = {'mean': mean(secs), 'sd': sd(secs), 'min': min(secs), 'max': max(secs)}
    lim = [r['time_limit_seconds'] for r in sel if r['time_limit_seconds']]
    if lim:
        out['share_of_T'] = {'mean': mean([r['seconds'] / r['time_limit_seconds'] for r in sel]), 'T': sorted(set(lim)),
                             'hard_stops': sum(any(h.get('hard_stop') for h in r['handoffs']) for r in sel)}
    toks = [sum((h['tokens'].get('output') or 0) for h in r['handoffs']) for r in sel]
    think = [sum((h.get('thinking_tokens') or 0) for h in r['handoffs']) for r in sel]
    uncached = [sum((h['tokens'].get('uncached_input') or 0) for h in r['handoffs']) for r in sel]
    cached = [sum((h['tokens'].get('cached_input') or 0) for h in r['handoffs']) for r in sel]
    calls = [sum((h.get('tool_calls') or 0) for h in r['handoffs']) for r in sel]
    out['tokens'] = {'output_mean': mean(toks), 'output_sd': sd(toks), 'thinking_mean': mean(think), 'uncached_input_mean': mean(uncached),
                     'cached_input_mean': mean(cached)}
    out['tool_calls'] = {'mean': mean(calls), 'sd': sd(calls)}
    out['format_penalty_nonzero'] = sum(1 for r in sel if (r['score_json'].get('f') or 0) > 0)
    out['paused'] = sum(1 for r in sel if r['score_json'].get('paused'))
    out['repairs_total'] = sum(r['score_json'].get('rRepairable') or 0 for r in sel)
    out['agy_version'] = {v: sum(agy_version(r) == v for r in sel) for v in ('1.5.8', '1.5.9')}
    return out


def v1_table():
    d = json.loads(V1.read_text())
    cfg = {c['key']: c for c in d['configs']}
    acc = {}
    for i in d['instances']:
        if not (i['selection']['mainStatistic'] and i['validity']['valid'] and i['scoring']['score'] is not None):
            continue
        acc.setdefault((i['configKey'], SHORT[i['scenario']]), []).append((i['scoring']['score'], i['time']['durationSeconds']))
    rows = []
    for key, c in cfg.items():
        row = {'key': key, 'config': c['configNumber'], 'kind': c['kind'], 'cells': {}}
        for s in SCEN:
            v = acc.get((key, s))
            if v:
                sc = [x[0] for x in v]
                w = [x[1] for x in v if x[1] is not None]
                row['cells'][s] = {'n': len(sc), 'mean': mean(sc), 'sd': sd(sc), 'wall_min': mean(w) / 60 if w else None}
        rows.append(row)
    return rows


def fmt(x, nd=3):
    return '—' if x is None else f'{x:.{nd}f}'


def ms(st):
    return f"{fmt(st['mean'])} ± {fmt(st['sd'])}" if st.get('n', 0) > 1 else fmt(st.get('mean'))


def write_md(S):
    L = ['# Hydrogen（Antigravity）v1 冻结场景补测：结果（自动生成）', '']
    L += ['## 各格成绩（r8.4 最终分；均值 ± 标准差，n = 有效实例数；括号内 95% t 区间）', '',
          '| 场景 | 强度 | n（无效） | 最终分 | 95% 区间 | 最小 | 负分数 | 墙钟（分钟，均值 ± SD） | 占 T | 撞 T | 输出 token（含思考） | 工具调用 | 格式罚>0 | agy 1.5.8/1.5.9 |', '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for s in SCEN:
        for e in EFFORTS:
            c = S['cells'][f'{e}/{s}']
            sc = c['score']
            T = c.get('share_of_T')
            L.append(f"| {NAME[s]} | {e} | {c['n_valid']}（{c['n_invalid']}） | {ms(sc)} | [{fmt(sc['ci95'][0])}, {fmt(sc['ci95'][1])}] | {fmt(sc['min'])} | {sc['negative']} | "
                     f"{c['wall_s']['mean'] / 60:.1f} ± {c['wall_s']['sd'] / 60:.1f} | {('%.0f%%' % (T['mean'] * 100)) if T else '—'} | {T['hard_stops'] if T else '—'} | "
                     f"{c['tokens']['output_mean']:.0f} | {c['tool_calls']['mean']:.1f} | {c['format_penalty_nonzero']} | {c['agy_version']['1.5.8']}/{c['agy_version']['1.5.9']} |")
    L += ['', '## 三档按实例配对的差值（同场景，第 i 个有效实例对第 i 个；差 = 后者减前者，n = 5 对）', '',
          '| 场景 | 比较 | 差值均值 | 差值 SD | 95% 区间（t，df = 4） | 后者高 / 持平 / 前者高 |', '|---|---|---|---|---|---|']
    for s in SCEN:
        for a, b in (('medium', 'high'), ('high', 'xhigh'), ('medium', 'xhigh')):
            p = S['paired'][f'{b}-{a}/{s}']
            L.append(f"| {NAME[s]} | {b} − {a} | {p['mean_diff']:+.3f} | {fmt(p['sd_diff'])} | [{p['ci95'][0]:+.3f}, {p['ci95'][1]:+.3f}] | {p['wins_b']} / {p['ties']} / {p['wins_a']} |")
    L += ['', '## 去掉“撞 T 且无报告记 0”的实例后的各格（敏感性，不是主统计）', '', '| 格 | n | 最终分均值 ± SD |', '|---|---|---|']
    for k, st in S['without_model_failures'].items():
        L.append(f"| {k} | {st['n']} | {ms(st)} |")
    L += ['', '## v1 页面各配置（主统计实例，均值 ± SD，n；括号为平均墙钟分钟）与 Hydrogen', '',
          '| # | 配置 | ' + ' | '.join(NAME[s] for s in SCEN) + ' |', '|---|---|---|---|---|---|']
    for r in S['v1']:
        cells = []
        for s in SCEN:
            c = r['cells'].get(s)
            cells.append('—' if not c else f"{c['mean']:.3f} ± {c['sd']:.3f}, n={c['n']}" + (f" ({c['wall_min']:.1f})" if c['wall_min'] is not None else '') if c['sd'] is not None else f"{c['mean']:.3f}, n={c['n']}")
        L.append(f"| {r['config']}{'*' if r['kind'] != 'main' else ''} | {r['key']} | " + ' | '.join(cells) + ' |')
    for e in EFFORTS:
        cells = []
        for s in SCEN:
            c = S['cells'][f'{e}/{s}']
            cells.append(f"{c['score']['mean']:.3f} ± {c['score']['sd']:.3f}, n={c['score']['n']} ({c['wall_s']['mean'] / 60:.1f})")
        L.append(f"| {CONFIG[e]}† | antigravity/hydrogen/{e} | " + ' | '.join(cells) + ' |')
    L += ['', '* 补充配置；† 本补测（agy 1.5.8/1.5.9，另一 harness）。D7：不排名、不给综合分。']
    (OUT / 'summary.md').write_text('\n'.join(L) + '\n')


FORBIDDEN = re.compile(r'/home|/mnt|/tmp|/var/|~/|[A-Za-z]:\\\\|localhost|127\.0\.0\.1|\bsk-|Bearer|@[A-Za-z0-9.-]+\.[a-z]{2,}|private\.toml|\.credentials|\.state/|pello|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')


def write_export(rows):
    insts = []
    for r in sorted(rows, key=lambda r: (r['short'], EFFORTS.index(r['effort']), r['attempt'])):
        sj = r['score_json'] or {}
        insts.append({
            'id': 'antigravity/' + r['scenario'] + '/' + r['id'].split('/')[-1], 'scenario': r['scenario'], 'configKey': f"antigravity/hydrogen/{r['effort']}",
            'configNumber': CONFIG[r['effort']], 'arm': 'antigravity', 'attempt': r['attempt'], 'requestedEffort': r['effort'], 'agyVersion': agy_version(r),
            'startedAt': time.strftime('%Y-%m-%dT%H:%M:%S+09:00', time.localtime(r['started'])) if r['started'] else None,
            'validity': {'valid': r['valid'], 'status': r['validity']['status'], 'notes': [re.sub(r'[\w.-]+\.googleapis\.com\S*|read tcp \S+', '<network detail>', x) for x in r['validity']['reasons']]},
            'selection': {'validRank': r['valid_rank'], 'mainStatistic': bool(r['main_statistic']), 'stage': 'phase4'},
            'scoring': ({'status': sj.get('status'), 'score': sj.get('final'), 'rawScore': sj.get('rawScore'), 'scoreBeforePenalty': sj.get('scoreBeforePenalty'),
                         'formatPenalty': sj.get('f'), 'repairs': sj.get('rRepairable'), 'overallDeduction': sj.get('overall_deduction'),
                         'modelFailure': any(str(h.get('scored') or '').startswith('modelFailure') for h in sj.get('handoffs') or [])} if r['valid'] else None),
            'time': {'durationSeconds': r['seconds'], 'timeLimitSeconds': r['time_limit_seconds'], 'hardStop': any(h.get('hard_stop') for h in r['handoffs']),
                     'durationBasis': 'agy process wall time summed over the segments of the instance; each segment counts --print-timeout from its process start (7 s start-up included)'},
            'tokens': {'uncachedInput': sum(h['tokens'].get('uncached_input') or 0 for h in r['handoffs']), 'cachedInput': sum(h['tokens'].get('cached_input') or 0 for h in r['handoffs']),
                       'output': sum(h['tokens'].get('output') or 0 for h in r['handoffs']), 'thinking': sum(h.get('thinking_tokens') or 0 for h in r['handoffs']),
                       'source': 'agy stream usage'},
            'toolCalls': sum(h.get('tool_calls') or 0 for h in r['handoffs']), 'cost': None,
            'pauses': {'known': True, 'count': r['pause_count']}, 'modelIdsReturned': sorted({m for h in r['handoffs'] for m in h['models_returned']}),
        })
    out = {'meta': {'name': 'Hydrogen supplement (phase 4) on the frozen Reviewer Model Benchmark v1 scenarios', 'scoring': 'r8.4', 'generator': 'runners/hydrogen-1114/summarize.py (not the frozen bench_export toolchain; kept apart from the page data)',
                    'configs': {'30': 'antigravity/hydrogen/medium', '31': 'antigravity/hydrogen/high', '32': 'antigravity/hydrogen/xhigh'}, 'unit': 'seconds, tokens; cost null = unknown'},
           'instances': insts}
    text = json.dumps(out, indent=1, ensure_ascii=False)
    bad = sorted(set(m.group(0) for m in FORBIDDEN.finditer(text)))
    if bad:
        raise SystemExit(f'export safety check failed: {bad}')
    (OUT / 'hydrogen-results.json').write_text(text + '\n')


def main():
    OUT.mkdir(exist_ok=True)
    rows = load()
    cl = cells(rows)
    invalid = {(e, s): sum(1 for r in rows if r['effort'] == e and r['short'] == s and not r['valid']) for e in EFFORTS for s in SCEN}
    summary = {'cells': {}, 'paired': {}}
    for (e, s), sel in cl.items():
        summary['cells'][f'{e}/{s}'] = cell_row(sel, invalid[(e, s)])
    for s in SCEN:
        for a, b in (('medium', 'high'), ('high', 'xhigh'), ('medium', 'xhigh')):
            xa, xb = [final(r) for r in cl[(a, s)]], [final(r) for r in cl[(b, s)]]
            if None in xa or None in xb or not xa or not xb:
                continue
            summary['paired'][f'{b}-{a}/{s}'] = pair(xa, xb)
    summary['v1'] = v1_table()
    # sensitivity: instances scored 0 by the frozen rule "hard stop, no report" (model failure)
    summary['model_failure_instances'] = [r['id'].split('/')[-1] + '/' + r['short'] for r in rows if r['valid'] and r['score_json']
                                         and any(str(h.get('scored') or '').startswith('modelFailure') for h in r['score_json'].get('handoffs') or [])]
    sens = {}
    for (e, s_), sel in cl.items():
        keep = [final(r) for r in sel if not any(str(h.get('scored') or '').startswith('modelFailure') for h in r['score_json'].get('handoffs') or [])]
        if len(keep) != len(sel):
            sens[f'{e}/{s_}'] = stat(keep)
    summary['without_model_failures'] = sens
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=1, ensure_ascii=False))
    write_md(summary)
    write_export(rows)
    print('summary.json written;', sum(c.get('scored', False) for c in summary['cells'].values()), '/ 12 cells scored')


if __name__ == '__main__':
    main()
