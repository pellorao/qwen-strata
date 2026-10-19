# 临时：Sonnet 盲裁试点池 s1（Commit Audit v3）。见 design.md。写 pool-s1.json（裁决视图）与 key-s1.json（参考答案与来源）。
import json, random, collections
from pathlib import Path
ROOT = Path('/home/pello/projects/qwen_strata'); A = ROOT / 'reports/v0.1.45/commit-audit-v3/data/adjudication'
OUT = ROOT / '.tmp/score-leftover-1019'
P, K, D = {}, {}, {}
for n in ['p1', 'p2', 'p3', 'p4']:
    P |= {x['id']: x for x in json.load(open(A / f'pool-{n}.json'))}; K |= json.load(open(A / f'key-{n}.json'))
    D |= {d['id']: d['decision'] for d in json.load(open(A / f'decisions-{n}.json'))['decisions']}
r1pool = {x['id']: x for x in json.load(open(A / 'pool-r1.json'))}; r1key = json.load(open(A / 'key-r1.json'))
r1dec = {d['id']: d['decision'] for d in json.load(open(A / 'decisions-r1.json'))['decisions']}
FORMAL = {'q3:Af', 'q3:B', 'q3:Bf'}
hard = [i for i in P if D[i] != 'matched' or P[i]['kind'] == 'finding']
r1anc = {k['orig']: rid for rid, k in r1key.items() if k['anchor']}
sel = list(hard) + [i for i in r1anc if i not in hard]
assert all(D[i] == 'matched' for i in r1anc if i not in hard)
rnd = random.Random(20261019)
ids = sorted(P); rnd.shuffle(ids)
covered = {P[i]['expectation'] for i in sel}
def stratum(i):
    s = K[i]['src']; return 'opus' if s.startswith('opus:') else ('q3f' if s in FORMAL else 'q3x')
quota = {'opus': 7, 'q3f': 8, 'q3x': 7}
for prefer_new in (True, False):
    for i in ids:
        st = stratum(i)
        if quota[st] and i not in sel and D[i] == 'matched' and P[i]['kind'] == 'association' and (not prefer_new or P[i]['expectation'] not in covered):
            sel.append(i); covered.add(P[i]['expectation']); quota[st] -= 1
assert not any(quota.values())
FIELDS = ('kind', 'check', 'allowedDecisions', 'expectation', 'finding', 'result', 'evidence')
items = []
for i in sel:
    it = {k: P[i][k] for k in FIELDS}
    for k in ('requirementSource', 'problemOptions', 'cleanTargets'):
        if k in P[i]: it[k] = P[i][k]
    meta = {'orig': i, 'src': K[i]['src'], 'candidateId': K[i]['candidateId'], 'synthetic': False, 'expected': D[i],
            'stratum': 'hard' if i in hard else 'matched', 'r1': r1anc.get(i), 'r1second': r1dec.get(r1anc.get(i))}
    items.append((it, meta))
for rid, k in r1key.items():
    if k['synthetic']:
        x = r1pool[rid]; it = {f: x[f] for f in FIELDS}
        for f in ('requirementSource', 'problemOptions', 'cleanTargets'):
            if f in x: it[f] = x[f]
        items.append((it, {'orig': rid, 'src': 'synthetic', 'synthetic': True, 'type': k['type'], 'expected': k['expected'], 'stratum': 'synthetic'}))
rnd.shuffle(items)
gname = lambda it: it['expectation'] or ('(out-of-key) ' + it['check'])
exps = sorted({gname(it) for it, _ in items}); rnd.shuffle(exps)
gid = {e: f'G{n:02d}' for n, e in enumerate(exps, 1)}
items.sort(key=lambda p: gid[gname(p[0])])
pool, key = [], {}
for n, (it, meta) in enumerate(items, 1):
    pid = f's1-{n:03d}'
    pool.append({'id': pid, 'group': gid[gname(it)], **it}); key[pid] = meta
(OUT / 'pool-s1.json').write_text(json.dumps(pool, ensure_ascii=False, indent=1))
(OUT / 'key-s1.json').write_text(json.dumps(key, ensure_ascii=False, indent=1))
print(len(pool), 'items', len(exps), 'groups', collections.Counter(m['stratum'] for m in key.values()),
      collections.Counter(m['src'] for m in key.values()))
