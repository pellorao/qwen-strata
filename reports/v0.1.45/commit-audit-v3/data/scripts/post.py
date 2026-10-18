# 临时：Commit Audit v2 一批的后处理（由 spec-v42/q3/post.py 改：一个实例一个交接）。argv: 批名。
# 第一遍上游计分（已完成实例）→ post/<批>/candidates.json；每个会话 inspect_session → post/<批>/inspect/<序号>；
# 逐实例工作时间、token（引擎日志段，arw_measure token_consumption）、工具调用数（rollout 的 function/custom/local_shell/web_search 调用）、速度 → metrics.json。
import collections, glob, json, os, subprocess, sys
from pathlib import Path
ROOT = Path('/home/pello/projects/qwen_strata'); sys.path.insert(0, str(ROOT))
from tools.reviewer.single_scenario_score import upstream_score
PLAN = ROOT / 'benchmarks/reviewer-suite-v1/commit-audit-v3-iq3_xxs-2026-10-18-v0.1.45/plan.json'
os.environ['CODEX_THREAD_ID'] = json.loads(PLAN.read_text())['codex_thread_id']
b = sys.argv[1]; N = ROOT / '.tmp/commit-audit/v3formal/q3'; run = N / 'runs' / b; out = N / 'post' / b; out.mkdir(parents=True, exist_ok=True)
recs = json.loads((run / 'run/results.json').read_text())
rep = lambda iid: iid.rsplit('-instance-', 1)[1]
done = {rep(x['instanceId']): x for x in recs if x['runtime_result'].get('state') in ('idle', 'exited')}
inp = {'artifacts': [{'reviewerId': 'commit-audit-reviewer', 'instances': [
    {'instanceId': v['instanceId'], 'artifactPaths': [v['report']]} for k, v in sorted(done.items())]}]}
# 可机械修复的实例：修复副本放到同一实例 .tmp 报告目录（ARW formatCorrection 要求），原件不改
rs = N.parent / 'post/repair/summary.json'; rsum = json.loads(rs.read_text()) if rs.exists() else {}
import shutil
for a in inp['artifacts'][0]['instances']:
    rec = rsum.get(a['instanceId'])
    if rec and rec['changes']:
        orig = Path(a['artifactPaths'][0]); fixed = Path(rec['record'][:-len('.changes.json')])
        dst = orig.with_name(orig.stem + '.format-corrected' + orig.suffix); shutil.copyfile(fixed, dst)
        a.update(artifactPaths=None, formatCorrection={'originalReportPath': str(orig), 'correctedReportPath': str(dst)})
(out / 'score-input.json').write_text(json.dumps(inp, indent=1))
prep = json.loads((run / 'preparation.json').read_text())
p = upstream_score(run / 'arw', prep['preparedPath'], out / 'score-input.json')
raw = p.stdout if p.stdout.strip() else p.stderr
(out / 'score-1.raw.json').write_text(raw)
cands = json.loads(raw).get('candidates', [])
(out / 'candidates.json').write_text(json.dumps(cands, ensure_ascii=False, indent=1))
TOOLS = {'function_call', 'custom_tool_call', 'local_shell_call', 'web_search_call'}
insp = {}
for s in sorted(glob.glob(str(run / 'run/arw-installation/codex-home/sessions/*/*/*/rollout-*.jsonl'))):
    meta = json.loads(open(s).readline())['payload']; cwd = meta.get('cwd', '')
    if isinstance(meta.get('source'), dict): continue  # guardian 等子 agent 会话（D1 起出现）不是 reviewer 会话
    r_ = next((k for k, v in done.items() if f"/{k}" in cwd.rstrip('/')[-6:] or cwd.rstrip('/').endswith('/' + k)), None)
    if r_ is None: continue
    d = out / 'inspect' / r_
    if not d.exists():
        subprocess.run([sys.executable, '-m', 'tools.reviewer.inspect_session', '--session', s, '--root', cwd, '--out', str(d)],
                       cwd=ROOT, check=True, capture_output=True)
    sm = json.loads((d / 'summary.json').read_text())
    calls = collections.Counter()
    for l in open(s):
        x = json.loads(l)
        if x.get('type') == 'response_item' and x['payload'].get('type') in TOOLS: calls[x['payload']['type']] += 1
    insp[r_] = {'session': Path(s).name, 'root': cwd, 'compactions': sm.get('compactions'), 'handoff_found': sm.get('handoff_found'),
                'flagged_actions': len(sm.get('flagged_actions', [])), 'flagged_messages': len(sm.get('flagged_messages', [])),
                'startup': sm.get('startup'), 'final': sm.get('final'), 'tool_calls': sum(calls.values()), 'tool_call_types': calls}
m = []
for k, x in sorted(done.items()):
    rates = json.loads((run / 'run' / x['instanceId'] / 'engine-rates.json').read_text())
    tok = x['token_consumption']; ws = x['review_work_seconds']
    m.append({'batch': b, 'rep': k, 'instanceId': x['instanceId'], 'complete': x['complete'], 'state': x['runtime_result'].get('state'),
              'generation_exit': (x.get('generation') or {}).get('exit_code'), 'deadlines': [d.get('interrupt') for d in x.get('deadlines', [])],
              'work_s': ws, 'work_min': round(ws / 60, 1), 'read': tok['uncached_input'], 'reused': tok['cached_input'], 'generated': tok['output'],
              'token_source': x.get('token_consumption_source'), 'tool_calls': insp.get(k, {}).get('tool_calls'),
              'engine_in_tps': round(rates['engine_input_tokens_per_second'], 0), 'engine_out_tps': round(rates['engine_output_tokens_per_second'], 1),
              'task_in_tps': round(tok['uncached_input'] / ws, 1), 'task_out_tps': round(tok['output'] / ws, 1)})
(out / 'metrics.json').write_text(json.dumps({'instances': m, 'inspect': insp, 'candidates': len(cands), 'score_rc': p.returncode}, indent=1, default=dict))
for r in m: print(r['batch'], r['rep'], r['work_min'], r['read'], r['reused'], r['generated'], r['tool_calls'], r['engine_in_tps'], r['engine_out_tps'], r['task_in_tps'], r['task_out_tps'])
print('candidates', len(cands), 'score_rc', p.returncode); print(json.dumps(insp, default=dict)[:3000])
