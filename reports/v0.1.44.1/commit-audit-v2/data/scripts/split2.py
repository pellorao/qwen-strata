# 临时：拆分 p2 盲裁结果。新来源（C/D）→ decisions2.json / key2.json（final.py 用）；锚点 → 与 p1 原判比对；合成负例 → 识别率。写 p2-check.json。
import json, collections
from pathlib import Path
A = Path('/home/pello/projects/qwen_strata/.tmp/commit-audit/measure/adj')
dec = {d['id']: d for d in json.load(open(A / 'decisions-p2.json'))['decisions']}; key = json.load(open(A / 'key-p2.json'))
pool = {x['id']: x for x in json.load(open(A / 'pool-p2.json'))}
assert set(dec) == set(key) == set(pool)
assert all(dec[i]['decision'] in pool[i]['allowedDecisions'] for i in dec)
new = {i: {'src': k['src'], 'candidateId': k['candidateId']} for i, k in key.items() if not k['anchor'] and not k['synthetic']}
(A / 'key2.json').write_text(json.dumps(new, ensure_ascii=False, indent=1))
(A / 'decisions2.json').write_text(json.dumps({'adjudicator': 'blind Opus high (p2)', 'decisions': [dec[i] for i in new]}, ensure_ascii=False, indent=1))
anc = [(i, k['anchor'], k['expected'], dec[i]['decision']) for i, k in key.items() if k['anchor']]
syn = [(i, k['synthetic'], k['expected'], dec[i]['decision']) for i, k in key.items() if k['synthetic']]
dis = [dict(id=i, p1=a, p1Decision=e, p2Decision=d, reason=dec[i]['reason'], src=key[i]['src']) for i, a, e, d in anc if e != d]
miss = [dict(id=i, kind=s, expected=e, got=d, reason=dec[i]['reason']) for i, s, e, d in syn if e != d]
out = {'anchors': len(anc), 'anchorAgree': len(anc) - len(dis), 'anchorDisagree': dis,
       'anchorBySrc': dict(collections.Counter(key[i]['src'].split(':')[0] for i, *_ in anc)),
       'synthetic': len(syn), 'syntheticRecognized': len(syn) - len(miss), 'syntheticMissed': miss,
       'newCounts': dict(collections.Counter(dec[i]['decision'].split('-')[0] if dec[i]['decision'].startswith('problem-') else dec[i]['decision'] for i in new)),
       'newBySrc': dict(collections.Counter(k['src'] for k in new.values()))}
(A / 'p2-check.json').write_text(json.dumps(out, ensure_ascii=False, indent=1))
print(json.dumps(out, ensure_ascii=False, indent=1))
