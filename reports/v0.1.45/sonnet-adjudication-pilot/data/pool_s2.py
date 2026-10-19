# 临时：Sonnet 盲裁试点池 s2（Code Standards v5.1 增量池 v51/pool.json 全部 62 项，重新编号与乱序）。见 design.md。
import json, random, collections
from pathlib import Path
ROOT = Path('/home/pello/projects/qwen_strata'); V = ROOT / '.tmp/code-standards-v5/v51'; OUT = ROOT / '.tmp/score-leftover-1019'
P = json.load(open(V / 'pool.json')); K = json.load(open(V / 'key.json'))
D = {d['id']: d['decision'] for d in json.load(open(V / 'decisions.json'))['decisions']}
rnd = random.Random(20261019); items = list(P); rnd.shuffle(items)
exps = sorted({x['expectation'] for x in items}); rnd.shuffle(exps); gid = {e: f'E{n:02d}' for n, e in enumerate(exps, 1)}
items.sort(key=lambda x: gid[x['expectation']])
pool, key = [], {}
for n, x in enumerate(items, 1):
    pid = f's2-{n:03d}'
    pool.append({'id': pid, 'group': gid[x['expectation']], 'kind': 'association', 'allowedDecisions': ['matched', 'not-matched'],
                 'expectation': x['expectation'], 'finding': x['finding']})
    key[pid] = {'orig': x['id'], 'src': K[x['id']]['source'], 'candidateId': K[x['id']]['candidateId'], 'expected': D[x['id']],
                'stratum': 'anchor' if K[x['id']]['source'] == 'anchor' else 'new', 'synthetic': False}
(OUT / 'pool-s2.json').write_text(json.dumps(pool, ensure_ascii=False, indent=1))
(OUT / 'key-s2.json').write_text(json.dumps(key, ensure_ascii=False, indent=1))
print(len(pool), collections.Counter(k['expected'] for k in key.values()))
