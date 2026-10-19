# 临时：Sonnet 试点对照与改判重算。argv: 池名 强度。读 runs/<池>-<强度>/decisions-<池>.json，写 runs/<池>-<强度>/result.json。
# s1：一致率（分层、分来源、混淆矩阵）、合成负例识别；不一致的真实候选按 Sonnet 改判后，重算受影响来源（候选集合变化按两种方向机械补齐，
# 同 Commit Audit v3 复评 rescore.py），给出正式 ×5 与 ×10 的 Q3/Opus。s2：一致率与混淆矩阵（不重算）。
import json, os, sys, collections, statistics as st
from pathlib import Path
ROOT = Path('/home/pello/projects/qwen_strata'); sys.path.insert(0, str(ROOT))
F = ROOT / '.tmp/score-leftover-1019'; name, effort = sys.argv[1], sys.argv[2]; RUN = F / 'runs' / f'{name}-{effort}'
pool = {x['id']: x for x in json.loads((F / f'pool-{name}.json').read_text())}; key = json.loads((F / f'key-{name}.json').read_text())
dec = {d['id']: d for d in json.loads((RUN / f'decisions-{name}.json').read_text())['decisions']}
assert set(dec) == set(key) == set(pool), (len(dec), len(key))
assert all(dec[i]['decision'] in pool[i]['allowedDecisions'] for i in dec)
cls = lambda d: 'problem-N' if d.startswith('problem-') else d.split(':')[0]
out = {'pool': name, 'effort': effort, 'items': len(pool)}
real = {i: k for i, k in key.items() if not k['synthetic']}; syn = {i: k for i, k in key.items() if k['synthetic']}
agree = lambda ids: sum(dec[i]['decision'] == key[i]['expected'] for i in ids)
def rate(ids):
    ids = list(ids); return {'n': len(ids), 'agree': agree(ids), 'rate': round(agree(ids) / len(ids), 4) if ids else None}
out['real'] = rate(real)
out['byStratum'] = {s: rate(i for i in real if key[i]['stratum'] == s) for s in sorted({k['stratum'] for k in real.values()})}
srcgrp = lambda k: k['src'].split(':')[0] if ':' in k['src'] else k['src'].split('-')[0]
out['bySource'] = {s: rate(i for i in real if srcgrp(key[i]) == s) for s in sorted({srcgrp(k) for k in real.values()})}
out['byReferenceClass'] = {c: rate(i for i in real if cls(key[i]['expected']) == c) for c in sorted({cls(k['expected']) for k in real.values()})}
conf = collections.Counter((cls(key[i]['expected']), cls(dec[i]['decision'])) for i in real)
out['confusion'] = [{'reference': a, 'sonnet': b, 'n': n} for (a, b), n in sorted(conf.items())]
diff = [i for i in real if dec[i]['decision'] != key[i]['expected']]
out['disagreements'] = [{'id': i, 'orig': key[i]['orig'], 'src': key[i]['src'], 'stratum': key[i]['stratum'], 'opus': key[i]['expected'],
                         'opusSecond': key[i].get('r1second'), 'sonnet': dec[i]['decision'], 'reason': dec[i]['reason'],
                         'expectation': pool[i].get('expectation'), 'finding': pool[i]['finding'][:600]} for i in diff]
if syn:
    out['synthetic'] = {'n': len(syn), 'identified': sum(dec[i]['decision'] == syn[i]['expected'] for i in syn),
                        'missed': [{'id': i, 'type': syn[i]['type'], 'expected': syn[i]['expected'], 'sonnet': dec[i]['decision'], 'reason': dec[i]['reason']}
                                   for i in syn if dec[i]['decision'] != syn[i]['expected']]}
if name == 's1':
    from tools.reviewer.single_scenario_score import upstream_score
    M = ROOT / '.tmp/commit-audit/v3formal'; A = ROOT / 'reports/v0.1.45/commit-audit-v3/data/adjudication'
    os.environ['CODEX_THREAD_ID'] = json.loads((ROOT / 'benchmarks/reviewer-suite-v1/commit-audit-v3-iq3_xxs-2026-10-18-v0.1.45/plan.json').read_text())['codex_thread_id']
    D0, K0 = {}, {}
    for n in ['p1', 'p2', 'p3', 'p4']:
        K0 |= json.loads((A / f'key-{n}.json').read_text()); D0 |= {d['id']: d for d in json.loads((A / f'decisions-{n}.json').read_text())['decisions']}
    over = {key[i]['candidateId']: dec[i]['decision'] for i in diff}
    base = {}
    for r in json.loads((M / 'post/final.json').read_text())['rows']: base.setdefault(r['src'], []).append(r['score'])
    def paths(src):
        k, n = src.split(':'); return (M / 'q3/runs' / n, M / 'q3/post' / n) if k == 'q3' else (M / 'ref/runs' / n, M / 'post/ref' / n)
    def fill(c, good):
        return {'candidateId': c['candidateId'], 'decision': ('matched' if 'matched' in c['allowedDecisions'] else 'supported') if good
                else ('not-matched' if 'matched' in c['allowedDecisions'] else 'unsupported'), 'reason': 'mechanical fill'}
    filled = collections.Counter()
    def rescore(src, mode):
        # 按 ARW 两阶段流程逐轮补决定：验证器每轮只列出尚未决定的候选；想要的决定（Sonnet 改判，否则原判）不在该候选的
        # allowedDecisions 内或候选是新出现的，按方向机械补齐并计数。
        run, post = paths(src); prep = json.loads((run / 'preparation.json').read_text())
        want = {k['candidateId']: over.get(k['candidateId'], D0[b]['decision']) for b, k in K0.items() if k['src'] == src}
        good = (mode == 'q3fav') == src.startswith('q3:'); adj = RUN / f'rescore-{src.replace(":", "_")}-{mode}.json'
        ds = {}
        for _ in range(10):
            adj.write_text(json.dumps({'decisions': list(ds.values())}, ensure_ascii=False))
            p = upstream_score(run / 'arw', prep['preparedPath'], post / 'score-input.json', adj)
            if p.stdout.strip():
                up = json.loads(p.stdout); return [rep['score'] for res in up['results'] for rep in res['repetitions']]
            err = json.loads(p.stderr); cs = err.get('candidates', [])
            if not cs: raise RuntimeError((src, p.stderr[-800:]))
            nds = dict(ds)  # 验证器只列出尚未决定的候选
            for c in cs:
                w = want.get(c['candidateId'])
                if w is not None and w in c['allowedDecisions']: nds[c['candidateId']] = {'candidateId': c['candidateId'], 'decision': w, 'reason': 'r'}
                else: nds[c['candidateId']] = fill(c, good); filled[(src, mode)] += 1
            if nds == ds: raise RuntimeError((src, 'stuck', p.stderr[-800:]))
            ds = nds
        raise RuntimeError('no convergence')
    aff = sorted({key[i]['src'] for i in diff})
    FORMAL = ['q3:Af', 'q3:B', 'q3:Bf']; TEN = FORMAL + ['q3:C', 'q3:D']; OPUS = ['opus:opus-1', 'opus:opus-2', 'opus:opus-3']
    def summary(sc):
        o = st.mean(x for s in OPUS for x in sc[s]); r = {}
        for lab, srcs in (('x5', FORMAL), ('x10', TEN)):
            q = st.mean(x for s in srcs for x in sc[s]); r[lab] = {'q3Mean': round(q, 4), 'opusMean': round(o, 4), 'ratio': round(q / o, 4)}
        return r
    res = {'original': summary(base)}
    for mode in ('q3fav', 'q3unf'):
        sc = {s: (rescore(s, mode) if s in aff else base[s]) for s in TEN + OPUS}
        res[mode] = {**summary(sc), 'perSource': {s: [round(x, 4) for x in sc[s]] for s in aff if s in sc}}
    res['affectedSources'] = aff; res['filled'] = {f'{s}/{m}': n for (s, m), n in filled.items()}
    res['delta'] = {lab: max(abs(res[m][lab]['ratio'] - res['original'][lab]['ratio']) for m in ('q3fav', 'q3unf')) for lab in ('x5', 'x10')}
    out['rescore'] = res
    hard = out['byStratum'].get('hard', {}).get('rate')
    out['pass'] = {'real>=95%': out['real']['rate'] >= 0.95, 'hard>=90%': hard is not None and hard >= 0.90,
                   'syntheticAll': out['synthetic']['identified'] == out['synthetic']['n'],
                   'ratioDelta<=0.02': res['delta']['x5'] <= 0.02,
                   'verdictUnchanged': all(res[m]['x5']['ratio'] < 0.8 for m in ('q3fav', 'q3unf'))}
else:
    out['pass'] = {'real>=95%': out['real']['rate'] >= 0.95}
(RUN / 'result.json').write_text(json.dumps(out, ensure_ascii=False, indent=1))
print(json.dumps({k: v for k, v in out.items() if k not in ('disagreements',)}, ensure_ascii=False, indent=1))
for d in out['disagreements']: print(d['id'], d['src'], d['stratum'], 'opus=', d['opus'], 'sonnet=', d['sonnet'], '|', d['reason'][:200])
