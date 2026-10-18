# 临时：Commit Audit v3 正式测量报告数据。由 final.json、analysis.json、各批 metrics、会话检查与合并一致性生成 summary.json 与 tables.md（报告目录）。
# 正式 Q3 = Af1–3、B1、Bf1；加测 = C、D 的有效实例（补充）；A-x1、B-x2 = 挂载点竞态的无效实例（补充，看分前定）。
import json, statistics as st, sys
from pathlib import Path
ROOT = Path('/home/pello/projects/qwen_strata'); M = ROOT / '.tmp/commit-audit/v3formal'; P = M / 'post'
OUT = ROOT / 'reports/v0.1.45/commit-audit-v3'; OUT.mkdir(parents=True, exist_ok=True)
FORMAL = ['Af', 'B', 'Bf']; ADD = [b for b in ('C', 'D') if (M / f'q3/post/{b}/metrics.json').exists()]; SUPP = ['A-x1', 'B-x2']
fin = json.loads((P / 'final.json').read_text()); an = json.loads((P / 'analysis.json').read_text())['instances']
mc = json.loads((P / 'merge-consistency.json').read_text()); ri = json.loads((P / 'ref-inspect.json').read_text())
r4 = lambda x: round(x, 4)
def frow(src, iid):
    return next(r for r in fin['rows'] if r['src'] == src and any(i.endswith('-instance-' + iid) for i in r['instances']))
rows = []
for b in FORMAL + ADD + SUPP:
    src = f'q3:{b}'; keys = [k for k in an if k.startswith(src + '#')]
    met = {i['rep']: i for i in json.loads((M / f'q3/post/{b}/metrics.json').read_text())['instances']} if b not in SUPP else {}
    ins = json.loads((M / f'q3/post/{b}/metrics.json').read_text())['inspect'] if b not in SUPP else {}
    for k in sorted(keys):
        n = k.split('#')[1]; r = frow(src, n); a = an[k]; m = met.get(n, {}); i = ins.get(n, {})
        rows.append({'batch': b, 'rep': n, 'set': 'formal' if b in FORMAL else ('add' if b in ADD else 'invalid'), 'score': r4(r['score']), 'raw': r4(r['raw']),
                     'r': r['r'], 'rRepairable': r['rRepairable'], 'T': r['T'], 'p': r['p'], 'f': r['f'], 'variants': {'pre': a['pre'], 'post': a['post']},
                     'a': a['a'], 'b': a['b'], 'floor': a['floor'], 'mcheck': a['mcheck'],
                     **{x: m.get(x) for x in ('work_min', 'read', 'reused', 'generated', 'tool_calls', 'engine_in_tps', 'engine_out_tps', 'task_in_tps', 'task_out_tps')},
                     'compactions': i.get('compactions'), 'flagged_actions': i.get('flagged_actions'), 'final': i.get('final'),
                     'merge': mc.get(k)})
opus = []
for k in sorted(x for x in an if x.startswith('opus:')):
    src = k.split('#')[0]; n = src.split(':')[1]; r = frow(src, '1'); m = json.loads((P / 'ref' / n / 'metrics.json').read_text()); a = an[k]
    opus.append({'src': src, 'score': r4(r['score']), 'raw': r4(r['raw']), 'r': r['r'], 'T': r['T'], 'p': r['p'], 'f': r['f'], 'variants': {'pre': a['pre'], 'post': a['post']},
                 'a': a['a'], 'b': a['b'], 'floor': a['floor'], 'mcheck': a['mcheck'], 'wall_min': round(m['wall_s'] / 60, 1), 'usage': m['usage'],
                 'cost_usd': round(m['cost_usd'], 3), 'tool_calls': m['tool_calls'], 'num_turns': m['num_turns'], 'merge': mc.get(k),
                 'inspect': {x: ri[n][x] for x in ('flagged', 'tool_errors', 'result_subtype')}})
haiku = []
for h in sorted(fin['haiku'], key=lambda x: x['src']):
    n = h['src'].split(':')[1]; m = json.loads((P / 'ref' / n / 'metrics.json').read_text())
    haiku.append({'src': h['src'], 'upper': r4(h['high'][0]['raw']), 'lower': r4(h['low'][0]['raw']), 'r': h['high'][0]['r'], 'T': h['high'][0]['T'],
                  'wall_min': round(m['wall_s'] / 60, 1), 'usage': m['usage'], 'cost_usd': round(m['cost_usd'], 3), 'tool_calls': m['tool_calls'], 'merge': mc.get(f'{h["src"]}#1')})
def agg(xs):
    d = {'n': len(xs)}
    for part in ('pre', 'post'):
        for v in ('full', 'noAB', 'noABnoTwin'):
            vals = [x['variants'][part][v] for x in xs]; d[f'{part}.{v}'] = {'mean': r4(st.mean(vals)), 'sd': r4(st.stdev(vals)) if len(vals) > 1 else None}
    for t in ('a', 'b', 'floor'):
        d[f'hits.{t}'] = f"{sum(v > 0 for x in xs for v in x[t].values())}/{sum(len(x[t]) for x in xs)}"
    for c in ('work_min', 'tool_calls', 'generated'):
        vals = [x[c] for x in xs if x.get(c) is not None]
        if vals: d[c] = {'mean': round(st.mean(vals), 1), 'max': max(vals)}
    return d
fq = [x for x in rows if x['set'] == 'formal']; aq = [x for x in rows if x['set'] in ('formal', 'add')]
A = {'q3Formal': agg(fq), 'q3FormalPlusAdd': agg(aq), 'q3Invalid': agg([x for x in rows if x['set'] == 'invalid']), 'opus': agg(opus)}
for g in ('q3Formal', 'q3FormalPlusAdd'):
    A[f'ratio.{g}'] = {k: round(A[g][k]['mean'] / A['opus'][k]['mean'], 3) for k in A['opus'] if k.startswith(('pre.', 'post.'))}
# 逐单位命中
units = json.loads((P / 'analysis.json').read_text())['units']['problem']
cases = []
for u, rs in units.items():
    qv = [an[f"q3:{x['batch']}#{x['rep']}"]['problemUnits'][u] for x in fq]; ov = [an[f"{x['src']}#1"]['problemUnits'][u] for x in opus]
    av = [an[f"q3:{x['batch']}#{x['rep']}"]['problemUnits'][u] for x in aq]
    cases.append({'unit': u, 'rows': rs, 'q3Hits': f'{sum(v > 0 for v in qv)}/{len(qv)}', 'q3Mean': round(st.mean(qv), 2),
                  'q3AllHits': f'{sum(v > 0 for v in av)}/{len(av)}', 'opusHits': f'{sum(v > 0 for v in ov)}/{len(ov)}', 'opusMean': round(st.mean(ov), 2)})
cleanf = {}
for x in fq + opus:
    k = f"q3:{x['batch']}#{x['rep']}" if 'batch' in x else f"{x['src']}#1"
    for u, v in an[k]['cleanFails'].items(): cleanf.setdefault(u, {'q3': [], 'opus': []})['q3' if 'batch' in x else 'opus'].append(round(v, 2))
plan = json.loads((ROOT / 'benchmarks/reviewer-suite-v1/commit-audit-v3-iq3_xxs-2026-10-18-v0.1.45/plan.json').read_text())
meta = {'scenario': 'Commit Audit v3', 'revision': 24, 'freeze': '6162f58', 'scoring': 'r8.3', 'strata': '0.1.45', 'model': 'IQ3_XXS', 'effort': 'high',
        'expectedSha256': '81796f467cc54bde5c1c1f1dbe9a9e1819eca11fbeae59bb650c95b5aff00108', 'plan': plan.get('id'),
        'tokenSource': {'q3': 'Strata 引擎日志段（本次与下一次派发之间）', 'opus/haiku': 'claude -p stream-json result.usage'}}
(OUT / 'summary.json').write_text(json.dumps({'meta': meta, 'agg': A, 'q3': rows, 'opus': opus, 'haiku': haiku, 'units': cases, 'cleanFails': cleanf}, ensure_ascii=False, indent=1))
print(json.dumps(A, ensure_ascii=False, indent=1))
