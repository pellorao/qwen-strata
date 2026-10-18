# 临时：参考运行（Opus/Haiku 无头）第一遍上游计分 → post/ref/<run>/candidates.json，并统计耗时、token（stream.jsonl result 的 usage）、工具调用数。argv: 运行名...
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path('/home/pello/projects/qwen_strata'); sys.path.insert(0, str(ROOT))
from tools.reviewer.single_scenario_score import upstream_score
M = ROOT / '.tmp/commit-audit/v3formal'
import os; os.environ['CODEX_THREAD_ID'] = json.loads((ROOT / 'benchmarks/reviewer-suite-v1/commit-audit-v3-iq3_xxs-2026-10-18-v0.1.45/plan.json').read_text())['codex_thread_id']
for name in sys.argv[1:]:
    run = M / 'ref/runs' / name; out = M / 'post/ref' / name; out.mkdir(parents=True, exist_ok=True)
    prep = json.loads((run / 'preparation.json').read_text())
    insts = [{'instanceId': h['instanceId'], 'artifactPaths': [h['input']['reportPath']]} for h in prep['handoffs']
             if Path(h['input']['reportPath']).exists() and Path(h['input']['reportPath']).stat().st_size > 0]
    (out / 'score-input.json').write_text(json.dumps({'artifacts': [{'reviewerId': 'commit-audit-reviewer', 'instances': insts}]}, indent=1))
    p = upstream_score(run / 'arw', prep['preparedPath'], out / 'score-input.json')
    raw = p.stdout if p.stdout.strip() else p.stderr
    (out / 'score-1.raw.json').write_text(raw)
    c = json.loads(raw).get('candidates', [])
    (out / 'candidates.json').write_text(json.dumps(c, ensure_ascii=False, indent=1))
    h = run / 'h0'; tools = 0; res = None
    for l in open(h / 'stream.jsonl'):
        x = json.loads(l)
        if x.get('type') == 'assistant':
            tools += sum(1 for b in x['message'].get('content', []) if b.get('type') == 'tool_use')
        if x.get('type') == 'result': res = x
    t0 = datetime.fromisoformat((h / 'started-utc.txt').read_text().strip().replace('Z', '+00:00'))
    t1 = datetime.fromisoformat((h / 'ended-utc.txt').read_text().strip().replace('Z', '+00:00'))
    u = (res or {}).get('usage', {})
    m = {'run': name, 'wall_s': (t1 - t0).total_seconds(), 'duration_ms': (res or {}).get('duration_ms'), 'num_turns': (res or {}).get('num_turns'),
         'tool_calls': tools, 'usage': {k: u.get(k) for k in ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens', 'output_tokens')},
         'cost_usd': (res or {}).get('total_cost_usd'), 'is_error': (res or {}).get('is_error'), 'token_source': 'claude -p stream-json result.usage'}
    (out / 'metrics.json').write_text(json.dumps(m, indent=1))
    print(name, 'rc', p.returncode, 'instances', len(insts), 'candidates', len(c), json.dumps(m))
