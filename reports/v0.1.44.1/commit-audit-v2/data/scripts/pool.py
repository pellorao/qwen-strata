# 临时：Commit Audit v2 盲裁池。argv: 池名(如 p1) 来源...（q3:A opus:opus-1 …）。隐去来源，按期望句分组、组内乱序。
# 写 pool-<名>.json（裁决视图）、key-<名>.json（映射）。没有锚点：v2 之前没有正式裁决，R1–R4 worker 核对不复用。
import json, random, sys
from pathlib import Path
M = Path('/home/pello/projects/qwen_strata/.tmp/commit-audit/measure'); A = M / 'adj'
name, srcs = sys.argv[1], sys.argv[2:]
items = []
def ev(e):
    if not isinstance(e, dict): return str(e)
    if 'command' in e: return f"command (exit {e.get('exitCode')}): {e['command']}"
    return f"{e['filePath']}:{e['line']}" if 'line' in e else f"{e['filePath']}:{e.get('lineStart')}-{e.get('lineEnd')}"
for src in srcs:
    kind, r = src.split(':')
    f = (M / 'q3/post' / r if kind == 'q3' else M / 'post/ref' / r) / 'candidates.json'
    for c in json.load(open(f)):
        items.append({'src': src, 'candidateId': c['candidateId'], 'kind': c['kind'], 'check': c['check'], 'expectation': c.get('expectation'),
                      'finding': c['finding'], 'result': c.get('result'),
                      'evidence': [ev(e) for e in c.get('evidence') or []],
                      'requirementSource': c.get('requirementSource') or c.get('source'), 'allowedDecisions': c['allowedDecisions'],
                      'problemOptions': c.get('problemOptions') or [], 'cleanTargets': c.get('cleanTargets') or []})
rnd = random.Random(20261017 + len(name)); rnd.shuffle(items)
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
    pool.append(v); key[bid] = {'src': it['src'], 'candidateId': it['candidateId']}
(A / f'pool-{name}.json').write_text(json.dumps(pool, ensure_ascii=False, indent=1))
(A / f'key-{name}.json').write_text(json.dumps(key, ensure_ascii=False, indent=1))
import collections
print(len(pool), 'items;', len(exps), 'groups;', collections.Counter(i['kind'] for i in items))
