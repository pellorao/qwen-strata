# 临时：由 final.json、各来源 score-final.json、metrics、会话检查与一致性结果生成报告用 summary.json 与 markdown 表（tables.md）。
import json, statistics as st
from pathlib import Path
ROOT = Path('/home/pello/projects/qwen_strata'); M = ROOT / '.tmp/commit-audit/measure'; P = M / 'post'
OUT = ROOT / 'reports/v0.1.44.1/commit-audit-v2'; OUT.mkdir(parents=True, exist_ok=True)
fin = json.loads((P / 'final.json').read_text())
E = json.loads((M / 'q3/runs/A/arw/tests/fixtures/reviewer-capability/commit-audit-reviewer/expected.json').read_text())
plan = json.loads((ROOT / 'benchmarks/reviewer-suite-v1/commit-audit-v2-iq3_xxs-2026-10-17-v0.1.44.1/plan.json').read_text())
mc = json.loads((P / 'merge-consistency.json').read_text()); ri = json.loads((P / 'ref-inspect.json').read_text())
r4 = lambda x: round(x, 4)
def sf(src):
    k, n = src.split(':')
    return json.loads(((M / 'q3/post' / n) if k == 'q3' else (P / 'ref' / n)) .joinpath('score-final.json').read_text())
# 逐实例
rows = []
for b in 'AB':
    met = {i['rep']: i for i in json.loads((M / f'q3/post/{b}/metrics.json').read_text())['instances']}
    ins = json.loads((M / f'q3/post/{b}/metrics.json').read_text())['inspect']
    for r in [x for x in fin['rows'] if x['src'] == f'q3:{b}']:
        m = met[str(r['repetition'])]; i = ins[str(r['repetition'])]
        rows.append({'batch': b, 'rep': r['repetition'], 'score': r4(r['score']), 'raw': r4(r['raw']), 'r': r['r'], 'rRepairable': r['rRepairable'], 'T': r['T'],
                     'p': r['p'], 'work_min': m['work_min'], 'read': m['read'], 'reused': m['reused'], 'generated': m['generated'], 'tool_calls': m['tool_calls'],
                     'engine_in_tps': m['engine_in_tps'], 'engine_out_tps': m['engine_out_tps'], 'task_in_tps': m['task_in_tps'], 'task_out_tps': m['task_out_tps'],
                     'compactions': i['compactions'], 'flagged_actions': i['flagged_actions'], 'final': i['final'],
                     'mergeInconsistent': mc[f'q3:{b}#{r["repetition"]}']['inconsistent']})
opus = []
for r in sorted([x for x in fin['rows'] if x['src'].startswith('opus:')], key=lambda x: x['src']):
    n = r['src'].split(':')[1]; m = json.loads((P / 'ref' / n / 'metrics.json').read_text())
    opus.append({'src': r['src'], 'score': r4(r['score']), 'raw': r4(r['raw']), 'r': r['r'], 'T': r['T'], 'wall_min': round(m['wall_s'] / 60, 1),
                 'usage': m['usage'], 'cost_usd': round(m['cost_usd'], 3), 'tool_calls': m['tool_calls'], 'num_turns': m['num_turns'],
                 'mergeInconsistent': mc[f'{r["src"]}#1']['inconsistent'], 'inspect': {k: ri[n][k] for k in ('flagged', 'tool_errors', 'result_subtype')}})
haiku = []
for h in sorted(fin['haiku'], key=lambda x: x['src']):
    n = h['src'].split(':')[1]; m = json.loads((P / 'ref' / n / 'metrics.json').read_text())
    haiku.append({'src': h['src'], 'upper': r4(h['high'][0]['raw']), 'lower': r4(h['low'][0]['raw']), 'r': h['high'][0]['r'], 'T': h['high'][0]['T'],
                  'wall_min': round(m['wall_s'] / 60, 1), 'usage': m['usage'], 'tool_calls': m['tool_calls'], 'mergeInconsistent': mc[f'{h["src"]}#1']['inconsistent']})
q = [x['score'] for x in rows]; o = [x['score'] for x in opus]
agg = {'q3': {'n': len(q), 'mean': r4(st.mean(q)), 'sd': r4(st.stdev(q)), 'rawMean': r4(st.mean(x['raw'] for x in rows))},
       'opus': {'n': len(o), 'mean': r4(st.mean(o)), 'sd': r4(st.stdev(o))}}
agg['ratio'] = round(agg['q3']['mean'] / agg['opus']['mean'], 3); agg['ratioRaw'] = round(agg['q3']['rawMean'] / agg['opus']['mean'], 3)
# 逐用例
def reps(src):
    return [rep['caseScores'] for res in sf(src)['results'] for rep in res['repetitions']]
q3c = reps('q3:A') + reps('q3:B'); opc = [c for s in ('opus:opus-1', 'opus:opus-2', 'opus:opus-3') for c in reps(s)]
cases, n = [], 0
for si, s in enumerate(E['scopes']):
    for i, c in enumerate(s['problemCases']):
        qv = [x['problem'][n] for x in q3c]; ov = [x['problem'][n] for x in opc]
        cases.append({'case': f"G{si+1}#{i}", 'merge': c.get('merge'), 'q3Hits': sum(v > 0 for v in qv), 'q3Mean': round(st.mean(qv), 2),
                      'opusHits': sum(v > 0 for v in ov), 'opusMean': round(st.mean(ov), 2), 'expectation': c.get('expectation') or c.get('requirement') or json.dumps(c, ensure_ascii=False)[:90]}); n += 1
clean = []
for si, s in enumerate(E['scopes']):
    for i, c in enumerate(s['cleanCases']):
        qv = [x['clean'][si][i] for x in q3c]; ov = [x['clean'][si][i] for x in opc]
        clean.append({'case': f"G{si+1}c#{i}", 'merge': c.get('merge'), 'q3Fail': sum(v < 1 for v in qv), 'q3Mean': round(st.mean(qv), 2),
                      'opusFail': sum(v < 1 for v in ov), 'opusMean': round(st.mean(ov), 2), 'expectation': c.get('expectation') or c.get('requirement') or json.dumps(c, ensure_ascii=False)[:90]})
meta = {'scenario': 'Commit Audit v2', 'revision': 23, 'freeze': 'a1ed615', 'plan': 'db03be2', 'scoring': 'r8.3', 'strata': '0.1.44.1', 'codex': '0.162.0',
        'model': 'IQ3_XXS', 'effort': 'high', 'expectedSha256': '0f02cf4372f74d2c9a37ca95834cad7a94456b9355884ebe6efb536d51bfd7bb',
        'tokenSource': {'q3': 'Strata 引擎日志段（本次与下一次派发之间）', 'opus/haiku': 'claude -p stream-json result.usage'}}
(OUT / 'summary.json').write_text(json.dumps({'meta': meta, 'rows': rows, 'opus': opus, 'agg': agg, 'haiku': haiku, 'cases': cases, 'cleanCases': clean,
                                              'mergeConsistency': mc}, ensure_ascii=False, indent=1))
L = ['| 次 | 批 | 分（罚后） | 罚前 | r | T | 分钟 | read | reused | generated | 工具调用 | 引擎入/出 tok/s | 任务入/出 tok/s |', '|---|---|---|---|---|---|---|---|---|---|---|---|---|']
for k, x in enumerate(rows, 1):
    L.append(f"| {k} | {x['batch']}{x['rep']} | {x['score']:.3f} | {x['raw']:.3f} | {x['r']} | {x['T']} | {x['work_min']} | {x['read']:,} | {x['reused']:,} | {x['generated']:,} | {x['tool_calls']} | {x['engine_in_tps']:,.0f} / {x['engine_out_tps']} | {x['task_in_tps']} / {x['task_out_tps']} |")
L += ['', '| 实例 | 分 | r | T | 分钟 | input | cache 写 | cache 读 | output | 工具调用 | 费用 USD |', '|---|---|---|---|---|---|---|---|---|---|---|']
for x in opus:
    u = x['usage']; L.append(f"| {x['src'].split(':')[1]} | {x['score']:.3f} | {x['r']} | {x['T']} | {x['wall_min']} | {u['input_tokens']} | {u['cache_creation_input_tokens']:,} | {u['cache_read_input_tokens']:,} | {u['output_tokens']:,} | {x['tool_calls']} | {x['cost_usd']} |")
L += ['', '| 实例 | 上界 | 下界 | r | T | 分钟 | output | 工具调用 | 合并不一致 |', '|---|---|---|---|---|---|---|---|---|']
for x in haiku:
    L.append(f"| {x['src'].split(':')[1]} | {x['upper']:.3f} | {x['lower']:.3f} | {x['r']} | {x['T']} | {x['wall_min']} | {x['usage']['output_tokens']:,} | {x['tool_calls']} | {x['mergeInconsistent']} |")
L += ['', '| 用例 | 合并 | Q3 命中 | Q3 均分 | Opus 命中 | Opus 均分 | 期望句 |', '|---|---|---|---|---|---|---|']
for c in cases:
    L.append(f"| {c['case']} | {c['merge'] or ''} | {c['q3Hits']}/{len(q3c)} | {c['q3Mean']:.2f} | {c['opusHits']}/{len(opc)} | {c['opusMean']:.2f} | {c['expectation'][:90].replace('|', '/')} |")
L += ['', '| 干净用例 | 合并 | Q3 失分次数 | Q3 均分 | Opus 失分次数 | Opus 均分 | 期望句 |', '|---|---|---|---|---|---|---|']
for c in clean:
    if c['q3Fail'] or c['opusFail']:
        L.append(f"| {c['case']} | {c['merge'] or ''} | {c['q3Fail']}/{len(q3c)} | {c['q3Mean']:.2f} | {c['opusFail']}/{len(opc)} | {c['opusMean']:.2f} | {c['expectation'][:90].replace('|', '/')} |")
(P / 'tables.md').write_text('\n'.join(L) + '\n')
print(json.dumps(agg)); print('\n'.join(L))
