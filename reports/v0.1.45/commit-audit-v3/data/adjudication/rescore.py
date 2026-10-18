# 临时：复评对照与改判重算。比对 decisions-r1 与原判（锚点一致率、合成负例识别），把不一致锚点按复评改判后重算受影响来源的正式分。
# 候选集合随关联决定变化：新出现的候选按两种方向机械补齐（q3fav：Q3 一侧 matched/supported、Opus 一侧 not-matched/unsupported；q3unf：相反）；
# 因改判而消失的候选，其原决定删去。所有正式样本 r=0、f=0，罚后=罚前。写 readj/result.json。
import json, os, sys, statistics as st
from pathlib import Path
ROOT = Path('/home/pello/projects/qwen_strata'); sys.path.insert(0, str(ROOT))
M = ROOT / '.tmp/commit-audit/v3formal'; A = M / 'adj'; R = M / 'readj'
os.environ['CODEX_THREAD_ID'] = json.loads((ROOT / 'benchmarks/reviewer-suite-v1/commit-audit-v3-iq3_xxs-2026-10-18-v0.1.45/plan.json').read_text())['codex_thread_id']
from tools.reviewer.single_scenario_score import upstream_score
key = json.loads((R / 'key-r1.json').read_text()); pool = {x['id']: x for x in json.loads((R / 'pool-r1.json').read_text())}
dec = {d['id']: d for d in json.loads((R / 'decisions-r1.json').read_text())['decisions']}
assert set(dec) == set(key) == set(pool) and all(dec[i]['decision'] in pool[i]['allowedDecisions'] for i in dec)
anc = {i: k for i, k in key.items() if k['anchor']}; syn = {i: k for i, k in key.items() if k['synthetic']}
agree = [i for i in anc if dec[i]['decision'] == anc[i]['expected']]; diff = [i for i in anc if i not in agree]
synok = [i for i in syn if dec[i]['decision'] == syn[i]['expected']]
out = {'anchors': len(anc), 'agree': len(agree), 'agreeRate': round(len(agree) / len(anc), 4),
       'disagreements': [{'id': i, 'orig': anc[i]['orig'], 'src': anc[i]['src'], 'instance': anc[i]['instance'], 'original': anc[i]['expected'], 'second': dec[i]['decision'], 'reason': dec[i]['reason']} for i in diff],
       'synthetic': len(syn), 'syntheticIdentified': len(synok),
       'syntheticMissed': [{'id': i, 'type': syn[i]['type'], 'expected': syn[i]['expected'], 'second': dec[i]['decision'], 'reason': dec[i]['reason']} for i in syn if i not in synok]}
# 原判（全部池）按来源
D0, K0 = {}, {}
for n in ['p1', 'p2', 'p3', 'p4']:
    K0 |= json.loads((A / f'key-{n}.json').read_text()); D0 |= {d['id']: d for d in json.loads((A / f'decisions-{n}.json').read_text())['decisions']}
over = {anc[i]['candidateId']: dec[i]['decision'] for i in diff}
fin = json.loads((M / 'post/final.json').read_text())
base = {}
for r in fin['rows']: base.setdefault(r['src'], []).append(r['raw'])
def paths(src):
    k, n = src.split(':'); return (M / 'q3/runs' / n, M / 'q3/post' / n) if k == 'q3' else (M / 'ref/runs' / n, M / 'post/ref' / n)
def fill(c, good):
    return {'candidateId': c['candidateId'], 'decision': ('matched' if 'matched' in c['allowedDecisions'] else 'supported') if good else ('not-matched' if 'matched' in c['allowedDecisions'] else 'unsupported'), 'reason': 'mechanical fill after re-adjudication'}
def rescore(src, mode):
    run, post = paths(src); prep = json.loads((run / 'preparation.json').read_text())
    ds = {k['candidateId']: {'candidateId': k['candidateId'], 'decision': over.get(k['candidateId'], D0[b]['decision']), 'reason': D0[b]['reason']} for b, k in K0.items() if k['src'] == src}
    good = (mode == 'q3fav') == src.startswith('q3:'); adj = R / f'rescore-{src.replace(":", "_")}-{mode}.json'
    for _ in range(8):
        adj.write_text(json.dumps({'decisions': list(ds.values())}, ensure_ascii=False))
        p = upstream_score(run / 'arw', prep['preparedPath'], post / 'score-input.json', adj)
        if p.stdout.strip():
            up = json.loads(p.stdout); return [rep['score'] for res in up['results'] for rep in res['repetitions']]
        err = json.loads(p.stderr); cs = {c['candidateId']: c for c in err.get('candidates', [])}
        if cs:
            pend = [c for c in cs.values() if c['candidateId'] not in ds]
            stale = [c for c in ds if c not in cs]
            if not pend and not stale: raise RuntimeError((src, p.stderr[-800:]))
            for c in stale: ds.pop(c)
            for c in pend: ds[c['candidateId']] = fill(c, good)
        else: raise RuntimeError((src, p.stderr[-800:]))
    raise RuntimeError('no convergence')
aff = sorted({anc[i]['src'] for i in diff})
FORMAL = ['q3:Af', 'q3:B', 'q3:Bf']; OPUS = ['opus:opus-1', 'opus:opus-2', 'opus:opus-3']
res = {}
for mode in ('q3fav', 'q3unf'):
    sc = {s: (rescore(s, mode) if s in aff else base[s]) for s in FORMAL + OPUS}
    q = [x for s in FORMAL for x in sc[s]]; o = [x for s in OPUS for x in sc[s]]
    res[mode] = {'perSource': sc, 'q3Mean': round(st.mean(q), 4), 'opusMean': round(st.mean(o), 4), 'ratio': round(st.mean(q) / st.mean(o), 4)}
q = [x for s in FORMAL for x in base[s]]; o = [x for s in OPUS for x in base[s]]
out['original'] = {'q3Mean': round(st.mean(q), 4), 'opusMean': round(st.mean(o), 4), 'ratio': round(st.mean(q) / st.mean(o), 4)}
out['rescore'] = res; out['affectedSources'] = aff
out['pass'] = {'agree>=95%': out['agreeRate'] >= 0.95, 'syntheticAll': len(synok) == len(syn), 'ratio<0.8': all(v['ratio'] < 0.8 for v in res.values())}
(R / 'result.json').write_text(json.dumps(out, ensure_ascii=False, indent=1)); print(json.dumps(out, ensure_ascii=False, indent=1))
