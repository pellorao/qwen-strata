# 临时：合并用例两侧判断（result）不一致的对数。merge 名形如 01:7+spec:27（issue 01 第 7 行与 spec 第 27 行）。argv: 来源...
import json, sys
from pathlib import Path
M = Path('/home/pello/projects/qwen_strata/.tmp/commit-audit/v3formal')
E = json.loads((M / 'q3/runs/A/arw/tests/fixtures/reviewer-capability/commit-audit-reviewer/expected.json').read_text())
names = sorted({c['merge'] for s in E['scopes'] for k in ('problemCases', 'cleanCases') for c in s[k] if c.get('merge')})
F = {'01': '.scratch/0001-dispatch-control/issues/01-assemble-dispatch-plan.md', '02': '.scratch/0001-dispatch-control/issues/02-publish-dispatch-manifest.md', 'spec': '.scratch/0001-dispatch-control/spec.md'}
side = lambda x: (F[x.split(':')[0]], int(x.split(':')[1]))
out = {}
for src in sys.argv[1:]:
    kind, r = src.split(':')
    run = M / ('q3/runs' if kind == 'q3' else 'ref/runs') / r
    prep = json.loads((run / 'preparation.json').read_text())
    hs = prep['handoffs']
    if '-x' in r:  # 补充样本（竞态无效实例）：只取该实例
        hs = [h for h in hs if h['instanceId'].endswith('-instance-' + r.split('-x')[1])]
    elif (run / 'run/results.json').exists():
        done = {x['instanceId'] for x in json.loads((run / 'run/results.json').read_text())}; hs = [h for h in hs if h['instanceId'] in done]
    for h in hs:
        rows = {}
        for l in Path(h['input']['reportPath']).read_text().splitlines():
            if not l.strip(): continue
            try: x = json.loads(l)
            except Exception: continue
            rows.setdefault((x['source']['filePath'], x['source']['line']), []).append(x['result'])
        diff, missing = [], []
        for n in names:
            a, b = (rows.get(side(p)) for p in n.split('+'))
            if not a or not b: missing.append(n)
            elif a[0] != b[0]: diff.append(f"{n} {a[0]}/{b[0]}")
        key = f"{src}#{h['instanceId'].rsplit('-instance-', 1)[1]}"
        out[key] = {'pairs': len(names), 'inconsistent': len(diff), 'detail': diff, 'missing': missing}
        print(key, len(names), 'inconsistent', len(diff), diff, 'missing', missing)
(M / 'post/merge-consistency.json').write_text(json.dumps(out, indent=1))
