# 临时：Commit Audit v2 正式计分（评分 r8.3）。由 spec-v42/post2/final.py 改。
# Q3/Opus：把盲裁拆回各来源，调用上游 score-completed --adjudication（连跑两次核对一致），再按格式罚出最终分。
# Haiku：不盲裁，给机械区间（关联全 matched / 全 not-matched；键外全 supported / 全 unsupported）。
# argv: [--no-penalty] 来源...（q3:A q3:B opus:opus-1 haiku:haiku-1 …）。--no-penalty：p基准登记前只出罚前分与 r、T。写 post/final.json（合并已有）。
import json, statistics, sys
from pathlib import Path
ROOT = Path('/home/pello/projects/qwen_strata'); sys.path.insert(0, str(ROOT))
import os
os.environ['CODEX_THREAD_ID'] = json.loads((ROOT / 'benchmarks/reviewer-suite-v1/commit-audit-v2-iq3_xxs-2026-10-17-v0.1.44.1/plan.json').read_text())['codex_thread_id']
from tools.reviewer.single_scenario_score import upstream_score
from tools.reviewer.format_penalty import score_repetitions, instance_errors
M = ROOT / '.tmp/commit-audit/measure'; P = M / 'post'; A = M / 'adj'
args = sys.argv[1:]; nopen = '--no-penalty' in args; mech = '--mech' in args; args = [a for a in args if a not in ('--no-penalty', '--mech')]
dec, key = {}, {}
for n in ('', '2', '3'):
    if (A / f'decisions{n}.json').exists():
        dec |= {d['id']: d for d in json.loads((A / f'decisions{n}.json').read_text())['decisions']}
        key |= json.loads((A / f'key{n}.json').read_text())
repair = json.loads((P / 'repair/summary.json').read_text())

def paths(src):
    kind, name = src.split(':')
    return (M / 'q3/runs' / name, M / 'q3/post' / name) if kind == 'q3' else (M / 'ref/runs' / name, P / 'ref' / name)

def score(src, run, post, ds, tag, policy=None):
    cands = json.loads((post / 'candidates.json').read_text())
    assert {c['candidateId'] for c in cands} <= {d['candidateId'] for d in ds}, (src, 'first-pass candidates not all decided')
    prep = json.loads((run / 'preparation.json').read_text())
    adj = post / f'adjudication{tag}.json'
    for _ in range(6):
        adj.write_text(json.dumps({'decisions': ds}, ensure_ascii=False, indent=1))
        outs = [upstream_score(run / 'arw', prep['preparedPath'], post / 'score-input.json', adj) for _ in (1, 2)]
        assert (outs[0].stdout, outs[0].stderr) == (outs[1].stdout, outs[1].stderr), f'{src}: scoring not repeatable'
        if outs[0].stdout.strip():
            break
        pend = [c for c in json.loads(outs[0].stderr).get('candidates', []) if c['candidateId'] not in {d['candidateId'] for d in ds}]
        assert pend, (src, outs[0].stderr[-500:])
        if policy is None:
            (post / f'pending{tag}.json').write_text(json.dumps(pend, ensure_ascii=False, indent=1))
            return None
        ds = ds + policy(pend)
    else:
        raise RuntimeError(f'{src}: adjudication did not converge')
    (post / f'score-final{tag}.json').write_text(outs[0].stdout)
    up = json.loads(outs[0].stdout)
    reps = {}
    for r in up['results']:
        for i in r['instances']:
            rec = repair.get(i['instanceId'])
            reps[i['instanceId']] = json.loads(Path(rec['record']).read_text()) if rec and rec['changes'] else None
    rows = []
    for r in up['results']:
        for rep in r.get('repetitions', []):
            insts = rep['instances']
            e = [sum(v) for v in zip(*(instance_errors(i, reps) for i in insts))]
            rows.append({'src': src, 'repetition': rep['repetition'], 'instances': [i['instanceId'] for i in insts], 'raw': rep['score'],
                         'rawScore': rep.get('rawScore'), 'r': sum(e), 'rRepairable': e[0], 'rUnrepairable': e[1], 'rOverrun': e[2],
                         'T': sum(i['locatorCount'] for i in insts), 'kTiers': rep.get('kTiers')})
    if not nopen:
        fin = {tuple(x['instances']): x for x in score_repetitions(up, reps)}
        for row in rows:
            x = fin[tuple(row['instances'])]; row.update(p=x['p'], f=x['f'], score=x['score'])
    return rows

hp = lambda xs: [{'candidateId': c['candidateId'], 'decision': 'matched' if 'matched' in c['allowedDecisions'] else 'supported', 'reason': 'mechanical high'} for c in xs]
lp = lambda xs: [{'candidateId': c['candidateId'], 'decision': 'not-matched' if 'matched' in c['allowedDecisions'] else 'unsupported', 'reason': 'mechanical low'} for c in xs]
fp = P / ('mech.json' if mech else 'final.json'); out = json.loads(fp.read_text()) if fp.exists() else {'rows': [], 'haiku': []}
for src in args:
    run, post = paths(src)
    out['rows'] = [r for r in out['rows'] if r['src'] != src]; out['haiku'] = [h for h in out['haiku'] if h['src'] != src]
    if src.startswith('haiku:') or mech:
        cands = json.loads((post / 'candidates.json').read_text())
        out['haiku'].append({'src': src, 'high': score(src, run, post, hp(cands), '-high', hp), 'low': score(src, run, post, lp(cands), '-low', lp)})
        continue
    ds = [{'candidateId': k['candidateId'], 'decision': dec[bid]['decision'], 'reason': dec[bid]['reason']} for bid, k in key.items() if k['src'] == src]
    rows = score(src, run, post, ds, '')
    if rows is None:
        out.setdefault('pending', []); out['pending'] = sorted(set(out['pending']) | {src}); continue
    out['pending'] = [p for p in out.get('pending', []) if p != src]
    out['rows'] += rows
fp.write_text(json.dumps(out, ensure_ascii=False, indent=1))
for r in out['rows']:
    print(r['src'], r['repetition'], 'raw', round(r['raw'], 4), 'final', round(r.get('score', float('nan')), 4), 'r', r['r'], 'T', r['T'])
for h in out['haiku']:
    print(h['src'], 'high', [(round(r['raw'], 4), r['r'], r['T']) for r in h['high']], 'low', [round(r['raw'], 4) for r in h['low']])
if out.get('pending'): print('pending second-round candidates:', out['pending'])
