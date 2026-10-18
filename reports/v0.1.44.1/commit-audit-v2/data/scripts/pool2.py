# 临时：Commit Audit v2 增量盲裁池 p2（加测 C/D）兼 p1 独立复评。由 pool.py 改。
# 内容：新来源全部候选 + p1 复评锚点（评估第三节：发现候选全部、G11/G21 全部、01:51 两项 p1-158/p1-160、p1-259，另分层随机 15 项）
#       + 10 个合成负例（错配期望句与 finding 7 个；"只排顶层"类 01:51 finding 3 个）。来源、原判与合成标记对裁决者隐藏。
# 写 pool-<名>.json、key-<名>.json（每项 src/candidateId/anchor/synthetic/expected）。final.py 用的 key2.json 由 split2.py 另写（只含新来源）。
import json, random, sys, collections
from pathlib import Path
M = Path('/home/pello/projects/qwen_strata/.tmp/commit-audit/measure'); A = M / 'adj'
name, srcs = sys.argv[1], sys.argv[2:]
def ev(e):
    if not isinstance(e, dict): return str(e)
    if 'command' in e: return f"command (exit {e.get('exitCode')}): {e['command']}"
    return f"{e['filePath']}:{e['line']}" if 'line' in e else f"{e['filePath']}:{e.get('lineStart')}-{e.get('lineEnd')}"
def cands(src):
    kind, r = src.split(':')
    return json.load(open((M / 'q3/post' / r if kind == 'q3' else M / 'post/ref' / r) / 'candidates.json'))
def item(src, c, **meta):
    return dict({'src': src, 'candidateId': c['candidateId'], 'kind': c['kind'], 'check': c['check'], 'expectation': c.get('expectation'),
            'finding': c['finding'], 'result': c.get('result'), 'evidence': [ev(e) for e in c.get('evidence') or []],
            'requirementSource': c.get('requirementSource') or c.get('source'), 'allowedDecisions': c['allowedDecisions'],
            'problemOptions': c.get('problemOptions') or [], 'cleanTargets': c.get('cleanTargets') or []}, **meta)
items = [item(s, c) for s in srcs for c in cands(s)]
p1 = json.load(open(A / 'pool-p1.json')); k1 = json.load(open(A / 'key-p1.json')); P1 = {x['id']: x for x in p1}
d1 = {d['id']: d['decision'] for d in json.load(open(A / 'decisions-p1.json'))['decisions']}
sel = [x['id'] for x in p1 if x['kind'] == 'finding' or x['group'] in ('G11', 'G21')] + ['p1-158', 'p1-160', 'p1-259']
sel = list(dict.fromkeys(sel))
rnd = random.Random(20261018)
rest = [x for x in p1 if x['id'] not in sel and x['kind'] == 'association']; rnd.shuffle(rest)
for kind, n in (('q3', 8), ('opus', 7)):
    seen = set()
    for x in rest:
        if sum(1 for i in sel if k1[i]['src'].startswith(kind) and i in [y['id'] for y in rest]) >= n: break
        if k1[x['id']]['src'].startswith(kind) and x['group'] not in seen: sel.append(x['id']); seen.add(x['group'])
for i in sel:
    k = k1[i]; c = next(c for c in cands(k['src']) if c['candidateId'] == k['candidateId'])
    items.append(item(k['src'], c, anchor=i, expected=d1[i]))
# 合成负例
assoc = [x for x in p1 if x['kind'] == 'association']
byg = collections.defaultdict(list)
for x in assoc: byg[x['group']].append(x)
gs = sorted(byg); rnd.shuffle(gs)
def ident(s): return [t for t in s.split('`')[1::2]]
syn = []
for ga, gb in zip(gs[0::2], gs[1::2]):
    if len(syn) >= 7: break
    a, b = byg[ga][0], byg[gb][0]
    if a['check'] != b['check'] or any(t in a['finding'] for t in ident(b['expectation'])) or a['expectation'] == b['expectation']: continue
    syn.append({'kind': 'association', 'check': b['check'], 'allowedDecisions': ['matched', 'not-matched'], 'expectation': b['expectation'],
                'finding': a['finding'], 'result': a['result'], 'evidence': a['evidence'], 'requirementSource': b.get('requirementSource'),
                'synthetic': f'mismatch: finding of {a["id"]} vs expectation of {gb}', 'expected': 'not-matched'})
E151 = P1['p1-157']['expectation']; RS = P1['p1-157'].get('requirementSource')
top = ["serializePlan wraps the plan in stableTopLevel, whose ownKeys trap sorts only the top-level keys, so nested object keys keep insertion order and the serialized plan is not lexically sorted at every depth.",
       "serializePlan orders keys with String.prototype.localeCompare instead of a code-unit comparison, so the key order depends on locale collation and is not lexical."]
for t in top:
    syn.append({'kind': 'association', 'check': 'COMMIT-AUDIT-GATE-1', 'allowedDecisions': ['matched', 'not-matched'], 'expectation': E151, 'finding': t, 'result': 'gap',
                'evidence': ['src/dispatch/serialize.mjs:1', 'src/dispatch/serialize.mjs:3'], 'requirementSource': RS, 'synthetic': 'top-level-only 01:51', 'expected': 'not-matched'})
syn.append({'kind': 'finding', 'check': 'COMMIT-AUDIT-GATE-1', 'allowedDecisions': ['unsupported', 'supported', 'problem-14'], 'expectation': None,
            'finding': "serializePlan does not sort keys lexically: stableTopLevel only reorders the outermost object, so nested keys such as plan.routes[0].stops keep their original order.",
            'result': 'gap', 'evidence': ['src/dispatch/serialize.mjs:1', 'src/dispatch/serialize.mjs:3'], 'requirementSource': None,
            'problemOptions': [{'decision': 'problem-14', 'expectation': E151}], 'cleanTargets': [], 'synthetic': 'top-level-only 01:51 (finding)', 'expected': 'unsupported'})
for s in syn: items.append(dict({'src': None, 'candidateId': None, 'problemOptions': [], 'cleanTargets': []} | s))
rnd = random.Random(20261018 + len(name)); rnd.shuffle(items)
exps = sorted({i['expectation'] or ('(out-of-key) ' + i['check']) for i in items}); rnd.shuffle(exps)
gid = {e: f'G{n:02d}' for n, e in enumerate(exps, 1)}
gk = lambda i: gid[i['expectation'] or ('(out-of-key) ' + i['check'])]
items.sort(key=gk)
pool, key = [], {}
for n, it in enumerate(items, 1):
    bid = f'{name}-{n:03d}'
    v = {'id': bid, 'group': gk(it), 'kind': it['kind'], 'check': it['check'], 'allowedDecisions': it['allowedDecisions'],
         'expectation': it['expectation'], 'finding': it['finding'], 'result': it['result'], 'evidence': it['evidence']}
    if it['requirementSource']: v['requirementSource'] = it['requirementSource']
    if it['kind'] != 'association': v.update(problemOptions=it['problemOptions'], cleanTargets=it['cleanTargets'])
    pool.append(v); key[bid] = {k: it.get(k) for k in ('src', 'candidateId', 'anchor', 'synthetic', 'expected')}
(A / f'pool-{name}.json').write_text(json.dumps(pool, ensure_ascii=False, indent=1))
(A / f'key-{name}.json').write_text(json.dumps(key, ensure_ascii=False, indent=1))
c = collections.Counter('anchor' if v['anchor'] else 'synthetic' if v['synthetic'] else 'new' for v in key.values())
print(len(pool), 'items;', len(exps), 'groups;', c, collections.Counter(i['kind'] for i in items))
print('anchor srcs', collections.Counter(k1[i]['src'].split(':')[0] for i in sel))
for s in syn: print(s['synthetic'], '|', (s['expectation'] or '')[:80], '|', s['finding'][:80])
