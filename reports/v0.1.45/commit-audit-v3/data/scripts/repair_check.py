# 临时：Q3 各批与参考运行的报告格式修复检查（只在副本上做）。写 post/repair/summary.json。
import json, subprocess, sys
from pathlib import Path
ROOT = Path('/home/pello/projects/qwen_strata'); M = ROOT / '.tmp/commit-audit/v3formal'; O = M / 'post/repair'
runs = [(b, M / 'q3/runs' / b) for b in sys.argv[1:] if not b.startswith(('opus', 'haiku'))] + [(r, M / 'ref/runs' / r) for r in sys.argv[1:] if r.startswith(('opus', 'haiku'))]
p0 = O / 'summary.json'; out = json.loads(p0.read_text()) if p0.exists() else {}
for name, run in runs:
    prep = json.loads((run / 'preparation.json').read_text())
    hs = prep['handoffs']
    if (run / 'run/results.json').exists():
        done = {x['instanceId'] for x in json.loads((run / 'run/results.json').read_text())}; hs = [h for h in hs if h['instanceId'] in done]
    for h in hs:
        rep = Path(h['input']['reportPath'])
        if not rep.exists() or rep.stat().st_size == 0: out[h['instanceId']] = None; continue
        dst = O / name / h['instanceId'].rsplit('-instance-', 1)[1] / rep.name; dst.parent.mkdir(parents=True, exist_ok=True)
        p = subprocess.run([sys.executable, '-m', 'tools.reviewer.repair_reviewer_report', '--report', str(rep), '--out', str(dst),
                            '--scenario-root', h['scenarioRoot']], cwd=ROOT, capture_output=True, text=True, check=True)
        out[h['instanceId']] = {'run': name, 'report': str(rep), 'changes': json.loads(p.stdout)['changes'], 'record': str(dst) + '.changes.json', 'fixed': dst.exists()}
p0.write_text(json.dumps(out, indent=1))
for iid, v in out.items(): print(iid[-50:], None if v is None else (v['run'], v['changes']))
