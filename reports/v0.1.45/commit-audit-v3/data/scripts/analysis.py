# 临时：Commit Audit v3 正式测量的逐用例分析。按冻结答案键（expected.json 81796f46…）把用例对到要求行（二部匹配，同 v3cal/d41/hits.py），
# 逐实例算三套分数（全部 29 个正例单位 / 不含 7 个 (a)+(b) 单位 / 再不含孪生干净单位；罚后 = 罚前 × (1 − f)，f 取 final.json 该实例的值）、
# (a)/(b)/保底 命中（单位分 > 0）、M2/M3 核对行（02:30、spec:45、02:31）的失分。argv: [--tag -high] 来源...  写 post/analysis<tag>.json。
import json, sys, statistics as st
from pathlib import Path
M = Path('/home/pello/projects/qwen_strata/.tmp/commit-audit/v3formal'); P = M / 'post'
E = json.loads((M / 'q3/runs/Af/arw/tests/fixtures/reviewer-capability/commit-audit-reviewer/expected.json').read_text())
AROWS = {'01:28', 'spec:41', '01:43', 'spec:53'}; BROWS = {'01:21', '01:32', 'spec:11', 'spec:74'}; FLOOR = {'01:38', 'spec:35'}
TWIN = {'01:22', 'spec:43', '01:39', 'spec:58', 'spec:61', 'spec:70', '02:31', '02:45'}; MCHK = ['02:30', 'spec:45', '02:31']
args = sys.argv[1:]; tag = ''
if args[:1] == ['--tag']: tag, args = args[1], args[2:]
key = lambda ev: tuple(sorted((e['filePath'].split('/')[-1], e['line']) for e in ev))
short = lambda p: {'01-assemble-dispatch-plan.md': '01', '02-publish-dispatch-manifest.md': '02', 'spec.md': 'spec'}.get(p.split('/')[-1], p)
def match(cases, reqs, ok):
    assign = {}
    def try_(i, seen):
        for j, r in enumerate(reqs):
            if j in seen or not ok(cases[i], r): continue
            seen.add(j)
            if j not in assign or try_(assign[j], seen): assign[j] = i; return True
        return False
    for i in range(len(cases)): try_(i, set())
    return {i: j for j, i in assign.items()}
PU, CU = {}, {}  # 单位名 → [(gi, n, 行)]
for gi, scope in enumerate(E['scopes']):
    reqs = [r for rec in E['auditRecords'] if (gi == 0) == ('issues/' in rec['pathSuffix']) for r in rec['requirements']]
    prob = [r for r in reqs if r['result'] != 'satisfied']; sat = [r for r in reqs if r['result'] == 'satisfied']
    pc = scope['problemCases']; allc = scope['cleanCases']; cc = [c for c in allc if not c.get('noOtherSupportedFinding')]
    pm = match(pc, prob, lambda c, r: c['result'] == r['result'] and key(r['evidence']) in [key(p['evidence']) for p in c.get('placements', [c])])
    cm = match(cc, sat, lambda c, r: key(r['evidence']) in [key(c['evidence'])] + [key(a) for a in c.get('evidenceAlternatives', [])])
    assert len(pm) == len(pc) and len(cm) == len(cc)
    for i, c in enumerate(pc):
        r = prob[pm[i]]; row = f"{short(r['source']['filePath'])}:{r['source']['line']}"
        PU.setdefault(c.get('merge') or row, []).append((gi, i, row))
    for i, c in enumerate(allc):
        row = 'noOther' if c.get('noOtherSupportedFinding') else (lambda r: f"{short(r['source']['filePath'])}:{r['source']['line']}")(sat[cm[cc.index(c)]])
        CU.setdefault(c.get('merge') or f'{row}|G{gi + 1}#{i}', []).append((gi, i, row))
assert len(PU) == 29, len(PU)
rowsof = lambda us: {r for _, _, r in us}
NOAB = [u for u, v in PU.items() if not rowsof(v) & (AROWS | BROWS)]; assert len(PU) - len(NOAB) == 7, len(NOAB)
NOTWIN = [u for u, v in CU.items() if not rowsof(v) & TWIN]
fin = {tuple(r['instances']): r for r in json.loads((P / 'final.json').read_text())['rows']} if (P / 'final.json').exists() else {}
def sfpath(src):
    k, n = src.split(':'); return ((M / 'q3/post' / n) if k == 'q3' else (P / 'ref' / n)) / f'score-final{tag}.json'
out = {'units': {'problem': {u: sorted(rowsof(v)) for u, v in PU.items()}, 'noAB': NOAB, 'twinCleanUnits': [u for u in CU if u not in NOTWIN]}, 'instances': {}}
for src in args:
    for inst in json.loads(sfpath(src).read_text())['results'][0]['instances']:
        cs = inst['caseScores']; iid = inst['instanceId']
        pv = {u: min(cs['problem'][gi * 20 + n] for gi, n, _ in v) for u, v in PU.items()}
        cv = {u: max(1 - cs['clean'][gi][n] for gi, n, _ in v) for u, v in CU.items()}
        ex = 0.25 * inst['extraFailedCleanCases']
        sc = lambda ps, cs_: (sum(pv[u] for u in ps) - 0.25 * sum(cv[u] for u in cs_) - ex) / len(ps)
        full = sc(PU, CU); assert abs(full - inst['rawScore']) < 1e-6, (src, iid, full, inst['rawScore'])
        f = next((r.get('f') for k, r in fin.items() if iid in k), None)
        v3 = {'full': full, 'noAB': sc(NOAB, CU), 'noABnoTwin': sc(NOAB, NOTWIN)}
        hit = lambda rows: {u: pv[u] for u, v in PU.items() if rowsof(v) & rows}
        out['instances'][f"{src}#{iid.rsplit('-instance-', 1)[1]}"] = {
            'src': src, 'instanceId': iid, 'f': f, 'pre': {k: round(x, 4) for k, x in v3.items()},
            'post': {k: round(max(0, x) * (1 - f), 4) for k, x in v3.items()} if f is not None else None,
            'a': hit(AROWS), 'b': hit(BROWS), 'floor': hit(FLOOR),
            'mcheck': {r: [round(1 - cs['clean'][gi][n], 2) for u, v in CU.items() for gi, n, rr in v if rr == r] for r in MCHK},
            'problemUnits': pv, 'cleanFails': {u: x for u, x in cv.items() if x > 0}, 'extraFailedCleanCases': inst['extraFailedCleanCases']}
(P / f'analysis{tag}.json').write_text(json.dumps(out, ensure_ascii=False, indent=1))
for k, x in out['instances'].items():
    h = lambda d: f"{sum(v > 0 for v in d.values())}/{len(d)}"
    print(k, 'pre', x['pre'], 'post', x['post'], 'a', h(x['a']), 'b', h(x['b']), 'floor', h(x['floor']), 'M', x['mcheck'])
