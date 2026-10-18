# 临时：加测到 10 次的报告数据。在 summary.json 中加 extra10（逐实例 10 行、5/10 次汇总、逐用例命中），写 tables10.md。不改 summary.json 已有字段。
import json, statistics as st
from pathlib import Path
ROOT = Path('/home/pello/projects/qwen_strata'); M = ROOT / '.tmp/commit-audit/measure'; P = M / 'post'
OUT = ROOT / 'reports/v0.1.44.1/commit-audit-v2'
fin = json.loads((P / 'final.json').read_text()); S = json.loads((OUT / 'summary.json').read_text())
E = json.loads((M / 'q3/runs/A/arw/tests/fixtures/reviewer-capability/commit-audit-reviewer/expected.json').read_text())
mc = json.loads((P / 'merge-consistency.json').read_text())
r4 = lambda x: round(x, 4)
def sf(src):
    k, n = src.split(':')
    return json.loads(((M / 'q3/post' / n) if k == 'q3' else (P / 'ref' / n)).joinpath('score-final.json').read_text())
rows = []
for b in 'ABCD':
    md = json.loads((M / f'q3/post/{b}/metrics.json').read_text())
    met = {i['rep']: i for i in md['instances']}; ins = md['inspect']
    for r in sorted([x for x in fin['rows'] if x['src'] == f'q3:{b}'], key=lambda x: x['repetition']):
        m = met[str(r['repetition'])]; i = ins[str(r['repetition'])]
        rows.append({'batch': b, 'rep': r['repetition'], 'extra': b in 'CD', 'score': r4(r['score']), 'raw': r4(r['raw']), 'rawScore': r.get('rawScore'),
                     'r': r['r'], 'rRepairable': r['rRepairable'], 'T': r['T'], 'p': r['p'], 'work_min': m['work_min'], 'read': m['read'], 'reused': m['reused'],
                     'generated': m['generated'], 'tool_calls': m['tool_calls'], 'engine_in_tps': m['engine_in_tps'], 'engine_out_tps': m['engine_out_tps'],
                     'task_in_tps': m['task_in_tps'], 'task_out_tps': m['task_out_tps'], 'compactions': i['compactions'], 'flagged_actions': i['flagged_actions'],
                     'final': i['final'], 'mergeInconsistent': mc[f'q3:{b}#{r["repetition"]}']['inconsistent']})
o = [x['score'] for x in S['opus']]; om = st.mean(o)
def agg(rs):
    q = [x['score'] for x in rs]; raw = [x['raw'] for x in rs]
    return {'n': len(q), 'mean': r4(st.mean(q)), 'sd': r4(st.stdev(q)), 'se': r4(st.stdev(q) / len(q) ** .5), 'rawMean': r4(st.mean(raw)),
            'ratio': round(st.mean(q) / om, 3), 'ratioRaw': round(st.mean(raw) / om, 3), 'minutesMean': round(st.mean(x['work_min'] for x in rs), 1),
            'generatedMean': round(st.mean(x['generated'] for x in rs)), 'toolCallsMean': round(st.mean(x['tool_calls'] for x in rs), 1)}
A = {'formal5': agg([x for x in rows if not x['extra']]), 'extra5': agg([x for x in rows if x['extra']]), 'all10': agg(rows)}
reps = lambda src: [rep['caseScores'] for res in sf(src)['results'] for rep in res['repetitions']]
q3c = [c for b in 'ABCD' for c in reps(f'q3:{b}')]; opc = [c for s in ('opus:opus-1', 'opus:opus-2', 'opus:opus-3') for c in reps(s)]
cases, n = [], 0
for si, s in enumerate(E['scopes']):
    for i, c in enumerate(s['problemCases']):
        qv = [x['problem'][n] for x in q3c]; ov = [x['problem'][n] for x in opc]
        cases.append({'case': f"G{si+1}#{i}", 'merge': c.get('merge'), 'q3Hits': sum(v > 0 for v in qv), 'q3Mean': round(st.mean(qv), 2),
                      'opusHits': sum(v > 0 for v in ov), 'opusMean': round(st.mean(ov), 2), 'expectation': c.get('expectation') or ''}); n += 1
S['extra10'] = {'note': '空闲加测：批 C 3、D 2（2026-10-18），条件与 A/B 相同；正式值仍为 5 次（agg）', 'rows': rows, 'agg': A, 'cases': cases}
(OUT / 'summary.json').write_text(json.dumps(S, ensure_ascii=False, indent=1))
L = ['| 次 | 批 | 分（罚后） | 罚前 | r | T | 分钟 | read | reused | generated | 工具调用 | 引擎入/出 tok/s | 任务入/出 tok/s |', '|---|---|---|---|---|---|---|---|---|---|---|---|---|']
for k, x in enumerate(rows, 1):
    L.append(f"| {k} | {x['batch']}{x['rep']} | {x['score']:.3f} | {x['raw']:.3f} | {x['r']} | {x['T']} | {x['work_min']} | {x['read']:,} | {x['reused']:,} | {x['generated']:,} | {x['tool_calls']} | {x['engine_in_tps']:,.0f} / {x['engine_out_tps']} | {x['task_in_tps']} / {x['task_out_tps']} |")
L += ['', '| 口径 | n | 均值 ± SD | 标准误 | 罚前均值 | Q3/Opus | 罚前比值 | 平均分钟 | 平均 generated | 平均工具调用 |', '|---|---|---|---|---|---|---|---|---|---|']
for k, lab in (('formal5', '正式 5 次（A、B）'), ('extra5', '加测 5 次（C、D）'), ('all10', '全部 10 次')):
    a = A[k]; L.append(f"| {lab} | {a['n']} | {a['mean']:.4f} ± {a['sd']:.4f} | {a['se']:.4f} | {a['rawMean']:.4f} | {a['ratio']:.3f} | {a['ratioRaw']:.3f} | {a['minutesMean']} | {a['generatedMean']:,} | {a['toolCallsMean']} |")
L += ['', '| 用例 | 合并 | Q3 命中（10） | Q3 均分 | Opus 命中 | 期望句 |', '|---|---|---|---|---|---|']
for c in cases:
    if c['q3Hits'] < len(q3c) or c['opusHits'] < len(opc):
        L.append(f"| {c['case']} | {c['merge'] or ''} | {c['q3Hits']}/{len(q3c)} | {c['q3Mean']:.2f} | {c['opusHits']}/{len(opc)} | {c['expectation'][:90].replace('|', '/')} |")
(P / 'tables10.md').write_text('\n'.join(L) + '\n')
print(json.dumps(A)); print('\n'.join(L))
