"""P4 for the OpenAI arm (plan §8, §14, §14.3 draft): beta and G per configuration on the CS / CStd material, the Opus
reference method as in .tmp/bench-anthropic-1019/p4probe.py (1/P = 0; beta = material bytes / input-token difference of
the first response between the material turn and a wrapper-only baseline turn; G = output tokens / request wall of the
response with the most output, a lower bound). T = B * k / (G * beta).

Each turn is one native thread of the benchmark Codex copy through the gate proxy (live passthrough of the ChatGPT
login, rate-limit headers forwarded), with the gate's deny-read list and its own CODEX_HOME holding the login link.

    python3 .tmp/luna-xhigh-1022/run/p4probe.py cs|cstd luna-xhigh luna-max

luna xhigh / max supplement (user 2026-10-22): the v1 probe (cec4e50f + workspace fix) unchanged in method. Its v1 inputs
were deleted on 10-22, so SOURCE is a fresh freeze of the CS scenario manifest (same reviewer-native-policy.mjs sha),
the material is copied from a fresh zero-model prepare of the frozen scenario plans (byte totals 152919 / 142529 as v1)
and the per-configuration plans are written like v1's smoke plans (smoke/plan-<model>-<effort>.json).
"""
import json
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path('/home/pello/projects/qwen_strata')
sys.path.insert(0, str(ROOT))
from tools.reviewer.providers import link_login, release_login  # noqa: E402
from tools.safety import safety_gate as g  # noqa: E402

BASE = Path(__file__).resolve().parent  # .tmp/luna-xhigh-1022/run
SOURCE = BASE / 'arw-source'
K = 2.0755
STAGE = {'cs': (BASE / 'stage-cs', ['governing-spec.md', 'src'], 152919),
         'cstd': (BASE / 'stage-cstd', ['src'], 142529)}
MODELS = {'sol': 'gpt-6.1-sol', 'luna': 'gpt-6-luna'}
INSTRUCTION = ('Do not use any tools. Write a plain-text walkthrough of the material above, one module at a time, '
               'about 2500 words.')


def material(root, parts):
    files = []
    for part in parts:
        p = root / part
        files += [p] if p.is_file() else sorted(f for f in p.rglob('*') if f.is_file())
    size = sum(f.stat().st_size for f in files)
    return '\n\n'.join(f'=== {f.relative_to(root)} ===\n' + f.read_text() for f in files), size


def responses(folder):
    rows = []
    for sse in sorted(folder.glob('requests/response-*.sse'), key=lambda p: int(p.stem.split('-')[1])):
        n = sse.stem.split('-')[1]
        usage, model, tier = None, None, None
        for line in sse.read_text().splitlines():
            if line.startswith('data: '):
                try:
                    e = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                if e.get('type') == 'response.completed':
                    r = e['response']
                    usage, model, tier = r.get('usage'), r.get('model'), r.get('service_tier')
        t = json.loads((folder / f'requests/request-{n}-time.json').read_text())
        rows.append({'n': int(n), 'usage': usage, 'model': model, 'tier': tier, 'low': t['low'],
                     'seconds': t['ended_at'] - t['started_at']})
    return rows


def turn(folder, plan_path, workspace, text):
    plan, api = g.api_plan(plan_path)
    provider = api['provider']
    folder.mkdir(parents=True)
    (folder / 'requests').mkdir()
    cwd = workspace / folder.name
    directory = cwd / 'report'
    directory.mkdir(parents=True)
    report = directory / 'bound-report.jsonl'
    report.write_text('')
    server = ThreadingHTTPServer(('127.0.0.1', 0), g.Proxy)
    server.requests, server.out, server.mode, server.live, server.owner = [], folder / 'requests', 'native', True, g.ApiOwner(provider)
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()
    catalog, session = g.gate_session(folder, None, None, api)
    info = {'repositoryRoot': str(SOURCE), 'installationDirectory': str(folder / 'native-installation'), **session}
    home = folder / 'native-installation/codex-home'
    login = link_login(provider, home)
    info['denyRead'] = g.gate_deny_paths(provider)
    native = g.Native(info, folder)
    try:
        context = {'cwd': str(cwd), 'report': str(report), 'reportDirectory': str(directory),
                   'config': g.config(cwd, report, f'http://127.0.0.1:{server.server_port}/v1', catalog, None,
                                      provider=provider, web_search='disabled'),
                   'instructions': 'Synthetic speed probe. Answer in plain text only; do not use any tools.',
                   'handoff': text}
        started = native.call('start', context)
        snap = g.observe(native, started['threadId'], folder, 900)
        root = next(m for m in snap['members'] if m['threadId'] == started['threadId'])
        return {'thread_id': started['threadId'], 'session': started.get('sessionPath'), 'state': root['state'],
                'login_linked': bool(login), 'responses': responses(folder)}
    finally:
        native.close()
        server.shutdown()
        server.server_close()
        th.join()
        (folder / 'login-release.json').write_text(json.dumps({'status': release_login(provider, home)}) + '\n')


def tool_calls(session):
    n = 0
    for line in Path(session).read_text().splitlines():
        e = json.loads(line)
        if e.get('type') == 'response_item' and e.get('payload', {}).get('type') in ('function_call', 'custom_tool_call'):
            n += 1
    return n


def probe(scenario, cfg):
    m, e = cfg.split('-')
    root, parts, expected = STAGE[scenario]
    text, size = material(root, parts)
    if size != expected:
        raise SystemExit(f'material {size} bytes, expected {expected}')
    out = BASE / f'p4-{scenario}' / cfg
    out.mkdir(parents=True, exist_ok=False)
    plan_path = BASE / f'smoke/plan-{MODELS[m]}-{e}.json'
    workspace = Path('/tmp/qwen-openai-1020') / ('p4-' + str(time.time_ns()))  # under the arms' denyRead base
    workspace.mkdir()
    rows = {}
    for name, body in (('baseline', INSTRUCTION.replace('of the material above', 'of nothing; reply "none"')),
                       ('material', text + '\n\n' + INSTRUCTION)):
        r = turn(out / name, plan_path, workspace, body + '\n')
        r['tool_calls'] = tool_calls(r['session']) if r.get('session') else None
        rows[name] = r
    first = {k: next(x for x in v['responses'] if not x['low']) for k, v in rows.items()}
    mt = first['material']['usage']['input_tokens'] - first['baseline']['usage']['input_tokens']
    beta = size / mt
    big = max((x for x in rows['material']['responses'] if not x['low']), key=lambda x: x['usage']['output_tokens'])
    G = big['usage']['output_tokens'] / big['seconds']
    T = round(size * K / (G * beta))
    result = {'scenario': scenario, 'cfg': cfg, 'material_bytes': size, 'material_tokens': mt, 'beta': beta, 'G': G,
              'G_response': {'output_tokens': big['usage']['output_tokens'], 'seconds': big['seconds']},
              'T_seconds': T, 'tool_calls': {k: v['tool_calls'] for k, v in rows.items()},
              'models': sorted({x['model'] for v in rows.values() for x in v['responses']}),
              'tiers': sorted({str(x['tier']) for v in rows.values() for x in v['responses']}),
              'release': {k: json.loads((out / k / 'login-release.json').read_text())['status'] for k in rows}}
    (out / 'rows.json').write_text(json.dumps(rows, indent=1) + '\n')
    (out / 'result.json').write_text(json.dumps(result, indent=1) + '\n')
    print(json.dumps(result), flush=True)
    return result


if __name__ == '__main__':
    scen = sys.argv[1]
    limits = BASE / f'{scen}-T.json'
    T = json.loads(limits.read_text()) if limits.exists() else {}
    for cfg in sys.argv[2:]:
        T[cfg] = probe(scen, cfg)['T_seconds']
        limits.write_text(json.dumps(T) + '\n')
