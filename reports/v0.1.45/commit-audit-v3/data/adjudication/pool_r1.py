# 临时：Commit Audit v3 第二裁决者复评池 r1（锚点 + 合成负例；来源、原判、合成标记对复评者隐藏）。见 pass-criteria.md。
# 写 pool-r1.json（复评视图）、key-r1.json（每项 orig 池 id / src / candidateId / anchor / synthetic / expected）。
import json, random, collections
from pathlib import Path
M = Path('/home/pello/projects/qwen_strata/.tmp/commit-audit/v3formal'); A = M / 'adj'; R = M / 'readj'
P, K, D = {}, {}, {}
for n in ['p1', 'p2', 'p3', 'p4']:
    P |= {x['id']: x for x in json.load(open(A / f'pool-{n}.json'))}; K |= json.load(open(A / f'key-{n}.json'))
    D |= {d['id']: d['decision'] for d in json.load(open(A / f'decisions-{n}.json'))['decisions']}
inst = lambda i: K[i]['src'] + '#' + K[i]['candidateId'].split(':')[1].rsplit('-instance-', 1)[1]
rnd = random.Random(20261018)
req = ['p1-263', 'p2-026', 'p1-052', 'p2-004', 'p2-005', 'p2-006', 'p2-019', 'p2-020', 'p2-021', 'p2-022', 'p2-024', 'p1-004', 'p1-053']
sel = list(req); used = set()
ids = list(P); rnd.shuffle(ids)
for run in ['opus:opus-1', 'opus:opus-2', 'opus:opus-3']:  # Opus matched：每次 5 项，期望组互不重复
    n = 0
    for i in ids:
        if n < 5 and K[i]['src'] == run and D[i] == 'matched' and P[i]['kind'] == 'association' and P[i]['expectation'] not in used:
            sel.append(i); used.add(P[i]['expectation']); n += 1
formal = {'q3:Af', 'q3:B', 'q3:Bf'}; n = 0
for i in ids:  # Q3 正式样本 matched 5 项
    if n < 5 and K[i]['src'] in formal and D[i] == 'matched' and i not in sel and P[i]['kind'] == 'association':
        sel.append(i); n += 1
other = [i for i in ids if K[i]['src'] not in formal and K[i]['src'].startswith('q3:') and i not in sel]
sel += [i for i in other if D[i] != 'matched'][:2] + [i for i in other if D[i] == 'matched'][:3]
items = [dict(P[i], _key={'orig': i, 'src': K[i]['src'], 'instance': inst(i), 'candidateId': K[i]['candidateId'], 'anchor': True, 'synthetic': False, 'expected': D[i]}) for i in sel]
# 合成负例
exp = {}
for x in P.values():
    if x['kind'] == 'association': exp.setdefault(x['expectation'], x)
byg = lambda pre: next(e for e in exp if e.startswith(pre))
def mis(fpre, epre):  # 真实 finding（按其期望句前缀定位一项 matched）配另一组期望句
    src = next(x for x in P.values() if x['kind'] == 'association' and x['expectation'].startswith(fpre) and D[x['id']] == 'matched')
    e = byg(epre); assert exp[e]['check'] == src['check']
    return dict(src, expectation=e, _key={'synthetic': True, 'anchor': False, 'type': 'mismatch', 'expected': 'not-matched', 'findingFrom': src['id']})
syn = [mis('`stopsForDriver`', '`buildManifest`'), mis('`publishManifest`', '`chooseDeparture`'), mis('`hasDuplicateRouteKeys`', '`withinVehicleCapacity`'),
       mis('Route duration', '`nextDispatchTime`'), mis('`authorizeRouteBatch`', 'Manifest-event redaction'), mis('Delivery notices', 'A failure marked')]
def rule(epre, text):  # 按裁决口径明确不匹配的写法，证据取该组真实候选
    e = byg(epre); t = exp[e]
    return dict(t, finding=text, result='gap', _key={'synthetic': True, 'anchor': False, 'type': 'rule', 'expected': 'not-matched', 'template': t['id']})
syn += [rule('`parseRetryCount`', '`parseRetryCount` accepts a retry count of 3, but the retry count must stay below 3, so the upper bound check should reject 3.'),
        rule('The stop comparator', 'The stop comparator does not place stops that have no `sequence` field after the equal-priority stops that do have one.'),
        rule('`effectiveScopes` drops', '`effectiveScopes` never checks whether the actor is suspended, so a suspended actor keeps its permissions.')]
def fake(tid, text, ev):  # 事实错误的发现候选
    t = P[tid]
    return dict(t, finding=text, evidence=ev, _key={'synthetic': True, 'anchor': False, 'type': 'false-fact', 'expected': 'unsupported', 'template': tid})
syn += [fake('p2-007', '`retry.mjs` passes the server-provided `retryAfter` text to `eval`, so a crafted retry header executes arbitrary code in the dispatcher.', ['src/dispatch/retry.mjs:8']),
        fake('p3-071', '`writePlanAtomically` writes the plan bytes directly with `fs.writeFileSync` and never calls the store, so the plan store contract is bypassed.', ['src/dispatch/storage.mjs:7-11'])]
items += syn; rnd.shuffle(items)
exps = sorted({i['expectation'] or ('(out-of-key) ' + i['check']) for i in items}); rnd.shuffle(exps)
gid = {e: f'G{n:02d}' for n, e in enumerate(exps, 1)}; gk = lambda i: gid[i['expectation'] or ('(out-of-key) ' + i['check'])]
items.sort(key=gk); pool, key = [], {}
for n, it in enumerate(items, 1):
    bid = f'r1-{n:03d}'
    v = {k: it[k] for k in ('kind', 'check', 'allowedDecisions', 'expectation', 'finding', 'result', 'evidence')}
    v = {'id': bid, 'group': gk(it), **v}
    if it.get('requirementSource'): v['requirementSource'] = it['requirementSource']
    if it['kind'] != 'association': v.update(problemOptions=it['problemOptions'], cleanTargets=it['cleanTargets'])
    pool.append(v); key[bid] = it['_key']
(R / 'pool-r1.json').write_text(json.dumps(pool, ensure_ascii=False, indent=1)); (R / 'key-r1.json').write_text(json.dumps(key, ensure_ascii=False, indent=1))
c = collections.Counter(('syn:' + k['type']) if k['synthetic'] else (k['src'].split(':')[0] + ('-formal' if k['src'] in formal else '')) for k in key.values())
print(len(pool), 'items', len(exps), 'groups', dict(c), 'opus groups', len(used))
