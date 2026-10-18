# 临时：无头参考运行（claude -p）的会话检查。argv: 运行名...
# 逐个 tool_use 看路径是否在隔离仓库内、是否触及禁止来源（答案键、judgment、凭据、.state、工程目录），统计被拒/出错的工具结果、文件改动、结果状态。
import json, re, sys
from pathlib import Path
M = Path('/home/pello/projects/qwen_strata/.tmp/commit-audit/measure')
BAD = re.compile(r'expected[^/]*\.json|judgment|project\.private|installation\.private|\.credentials|/\.state\b|qwen_strata|/\.claude')
out = {}
for name in sys.argv[1:]:
    h = M / 'ref/runs' / name / 'h0'; iso = json.loads((h / 'isolate.out').read_text().strip().splitlines()[-1]) if (h / 'isolate.out').exists() else {}
    tools, flags, errs, res, texts = [], [], [], None, 0
    for l in open(h / 'stream.jsonl'):
        x = json.loads(l)
        if x.get('type') == 'assistant':
            for b in x['message'].get('content', []):
                if b.get('type') == 'tool_use':
                    s = json.dumps(b['input'], ensure_ascii=False); tools.append((b['name'], s[:160]))
                    if BAD.search(s): flags.append(f"{b['name']}: {s[:200]}")
        if x.get('type') == 'user':
            for b in x['message'].get('content', []) if isinstance(x['message'].get('content'), list) else []:
                if b.get('type') == 'tool_result' and b.get('is_error'):
                    c = b.get('content'); errs.append((c if isinstance(c, str) else json.dumps(c, ensure_ascii=False))[:200])
        if x.get('type') == 'result': res = x
    diff = [l for l in (h / 'files.diff').read_text().splitlines() if l[:1] in '<>']
    out[name] = {'tool_calls': len(tools), 'by_tool': {t: sum(1 for n, _ in tools if n == t) for t in sorted({n for n, _ in tools})},
                 'flagged': flags, 'tool_errors': errs, 'files_diff': diff, 'isolation_check': (h / 'isolation-check.txt').read_text().strip(),
                 'result_subtype': (res or {}).get('subtype'), 'is_error': (res or {}).get('is_error'), 'num_turns': (res or {}).get('num_turns'),
                 'run': json.loads((h / 'haiku-run.json').read_text())}
    print(name, json.dumps(out[name], ensure_ascii=False, indent=1))
p = M / 'post/ref-inspect.json'; old = json.loads(p.read_text()) if p.exists() else {}
p.write_text(json.dumps(old | out, ensure_ascii=False, indent=1))
