# 临时：挂载点竞态实例（无 results 记录，看分前定为补充样本）的后处理：第一遍计分、会话检查、工具调用数。由 v3cal/d3/post_A.py 改。argv: 批名 实例序号 输出名
import json, os, sys, subprocess, glob, collections
from pathlib import Path
ROOT = Path('/home/pello/projects/qwen_strata'); sys.path.insert(0, str(ROOT))
N = ROOT / '.tmp/commit-audit/v3formal/q3'
os.environ['CODEX_THREAD_ID'] = json.loads((ROOT / 'benchmarks/reviewer-suite-v1/commit-audit-v3-iq3_xxs-2026-10-18-v0.1.45/plan.json').read_text())['codex_thread_id']
from tools.reviewer.single_scenario_score import upstream_score
b, k, name = sys.argv[1], sys.argv[2], sys.argv[3]
run = N / 'runs' / b; out = N / 'post' / name; out.mkdir(parents=True, exist_ok=True)
prep = json.loads((run / 'preparation.json').read_text()); h = [x for x in prep['handoffs'] if x['instanceId'].endswith('-instance-' + k)][0]
rs = json.loads((ROOT / '.tmp/commit-audit/v3formal/post/repair/summary.json').read_text()); rec = rs.get(h['instanceId'])
assert rec is not None and not rec['changes'], 'repair needed: handle explicitly'
inst = {'instanceId': h['instanceId'], 'artifactPaths': [h['input']['reportPath']]}
(out / 'score-input.json').write_text(json.dumps({'artifacts': [{'reviewerId': 'commit-audit-reviewer', 'instances': [inst]}]}, indent=1))
p = upstream_score(run / 'arw', prep['preparedPath'], out / 'score-input.json')
raw = p.stdout if p.stdout.strip() else p.stderr
(out / 'score-1.raw.json').write_text(raw)
c = json.loads(raw).get('candidates', []); (out / 'candidates.json').write_text(json.dumps(c, ensure_ascii=False, indent=1))
root = h['scenarioRoot'] if 'scenarioRoot' in h else None
for s in glob.glob(str(run / 'run/arw-installation/codex-home/sessions/*/*/*/rollout-*.jsonl')):
    meta = json.loads(open(s).readline())['payload']
    if isinstance(meta.get('source'), dict) or not meta.get('cwd', '').rstrip('/').endswith('/' + k): continue
    d = out / 'inspect' / k
    if not d.exists():
        subprocess.run([sys.executable, '-m', 'tools.reviewer.inspect_session', '--session', s, '--root', meta['cwd'], '--out', str(d)], cwd=ROOT, check=True, capture_output=True)
    T = {'function_call', 'custom_tool_call', 'local_shell_call', 'web_search_call'}; calls = collections.Counter()
    for l in open(s):
        x = json.loads(l)
        if x.get('type') == 'response_item' and x['payload'].get('type') in T: calls[x['payload']['type']] += 1
    sm = json.loads((d / 'summary.json').read_text())
    print(name, 'rc', p.returncode, 'cands', len(c), 'tool calls', sum(calls.values()), 'compactions', sm.get('compactions'), 'final', sm.get('final'), 'flagged', len(sm.get('flagged_actions', [])), len(sm.get('flagged_messages', [])))
