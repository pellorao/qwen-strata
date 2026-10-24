"""Zero-model check that the real Role reaches the model whole (multi-model v2 plan §5.4 and §9 item 3, F9).

The v2 plans put the scenario Role into Claude Code's system prompt (`claude_role_as_system`, one --append-system-prompt).
This runs `tools.reviewer.claude_scenario.run` unchanged (real plan, real prepared handoffs, the pinned Claude Code, the
DeepSeek backend's environment shape) against the loopback Messages mock of tools.safety.claude_gate, in a fresh network
namespace with loopback only, and judges the requests the mock received, not the runner's own account:
- the Role text (`system-h<k>.md`, as staged) is in the `system` field of every main-loop request, once, byte for byte;
- it comes after Claude Code's own system prompt, and the appended part is exactly the Role (no startup prompt in this
  arm), so its sha256 equals the `system_sha256` the runner bound;
- it is absent from the messages (the user prompt carries the handoff and the note only).
A plan whose DeepSeek limits are still null (F5) is run with placeholder limits, recorded as such: the Role check does not
depend on them.

    python3 -m tools.safety.claude_role_gate --out .tmp/<work>/role-gate [--plan <scenario plan> ...]

The fake key replaces the real one in this process only; nothing leaves the host.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

from tools.reviewer import claude_headless as ch
from tools.reviewer import claude_scenario
from tools.reviewer.wsl_client import save
from tools.safety import claude_gate

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = ROOT / 'benchmarks/multi-model-v2/scenarios'
# Plan -> handoffs to run (Spec Readiness has two different Roles, RM and AP; the others share one per plan).
PLANS = {'commit-audit-v3.1': 1, 'code-spec-v5.1': 1, 'code-standards-v5.1': 1, 'spec-readiness-v4.5': 2}
PLACEHOLDER = {'CLAUDE_CODE_MAX_CONTEXT_TOKENS': 1048576, 'CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE': 1040000,
               'CLAUDE_CODE_MAX_OUTPUT_TOKENS': 32000}
MODEL = 'deepseek-v4-flash'
FAKE_KEY = 'FAKE-ROLE-GATE-KEY'
NETNS_FLAG = claude_gate.NETNS_FLAG
LIMIT = 30  # seconds per handoff: the mock never writes a report, so the continuation loop runs to this hard limit


def system_text(body):
    system = body.get('system')
    if isinstance(system, str):
        return system
    return '\n'.join(block.get('text', '') for block in system or [] if isinstance(block, dict))


def judge(requests, role):
    """Per main-loop request: the Role count in `system`, its position, whether the appended tail is exactly the Role, and
    whether it leaked into the messages."""
    rows = []
    for body in requests:
        if not claude_gate.main_loop(body):
            continue
        system = system_text(body)
        messages = json.dumps(body.get('messages', []), ensure_ascii=False)
        index = system.find(role)
        rows.append({'role_in_system': system.count(role), 'preceded_by_claude_prompt': index > 0,
                     'role_is_tail': system.rstrip().endswith(role),
                     'role_in_messages': json.dumps(role, ensure_ascii=False)[1:-1] in messages,
                     'role_bytes': len(role.encode())})
    ok = bool(rows) and all(r['role_in_system'] == 1 and r['preceded_by_claude_prompt'] and r['role_is_tail']
                            and not r['role_in_messages'] for r in rows)
    return rows, ok


def prepare_plan(name, out):
    """The v2 plan as is, or (limits still null) a copy with placeholder limits; returns (path, placeholder?)."""
    path = SCENARIOS / f'{name}.json'
    plan = json.loads(path.read_text())
    limits = plan['fixed_conditions']['deepseek_claude_environment']
    if all(v is not None for v in limits.values()):
        return path, False
    plan['fixed_conditions']['deepseek_claude_environment'] = dict(PLACEHOLDER)
    copy = out / f'{name}-placeholder-limits.json'
    copy.write_text(json.dumps(plan, indent=1))
    return copy, True


def check_plan(out, name, handoffs, claude=ch.CLAUDE):
    out = Path(out).resolve()
    (out / 'requests').mkdir(parents=True)
    server = claude_gate.serve(out / 'requests')
    server.script = lambda: []  # no probes: every main-loop request is answered with a closing text
    base = f'http://127.0.0.1:{server.server_address[1]}'
    plan, placeholder = prepare_plan(name, out)
    saved = os.environ.get(ch.DEEPSEEK_KEY)
    os.environ[ch.DEEPSEEK_KEY] = FAKE_KEY
    timed = 'measurement_note_template' in json.loads(plan.read_text())['fixed_conditions']
    try:
        records = claude_scenario.run(plan, out / 'run', MODEL, 'high', f'role-gate {name}', claude, handoffs, LIMIT,
                                      time_limit=LIMIT if timed else None, backend='deepseek', deepseek_base=base)
    finally:
        server.shutdown()
        if saved is None:
            os.environ.pop(ch.DEEPSEEK_KEY, None)
        else:
            os.environ[ch.DEEPSEEK_KEY] = saved
    rows, ok = [], True
    for record in records:
        k = record['k']
        role = (out / 'run' / f'system-h{k}.md').read_text().strip()
        sha_ok = hashlib.sha256((out / 'run' / f'system-h{k}.md').read_bytes()).hexdigest() == record['system_sha256']
        bound = json.loads((out / 'run' / f'h{k}' / 'binding.json').read_text())
        bound_ok = bound['system_prompt_sha256'] == record['system_sha256'] and bound['endpoint'] == base
        marks = [json.dumps(b, ensure_ascii=False) for b in server.requests]
        mine = [b for b, text in zip(server.requests, marks) if role in text or record['instanceId'] in text]
        judged, judged_ok = judge(mine or server.requests, role)
        ok = ok and judged_ok and sha_ok and bound_ok
        rows.append({'handoff': k, 'instanceId': record['instanceId'], 'role_bytes': len(role.encode()),
                     'system_sha256': record['system_sha256'], 'binding_matches_file': sha_ok, 'binding_ok': bound_ok,
                     'requests_judged': len(judged), 'requests': judged, 'pass': judged_ok and sha_ok and bound_ok})
    summary = {'plan': name, 'limits_placeholder': placeholder, 'handoffs': rows, 'pass': ok and bool(rows)}
    save(out / 'summary.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--plan', action='append', choices=sorted(PLANS), help='default: all four')
    args = parser.parse_args()
    if args.out.exists():
        parser.error(f'{args.out} exists')
    if os.environ.get(NETNS_FLAG) != '1':
        raise SystemExit(claude_gate.in_network_namespace([sys.executable, '-m', 'tools.safety.claude_role_gate',
                                                           *sys.argv[1:]]))
    args.out.mkdir(parents=True)
    before = set(ch.WORK_BASE.iterdir()) if ch.WORK_BASE.exists() else set()
    summaries = []
    for name in args.plan or sorted(PLANS):
        summaries.append(check_plan(args.out / name, name, PLANS[name]))
        print(json.dumps({k: summaries[-1][k] for k in ('plan', 'limits_placeholder', 'pass')}), flush=True)
    result = {'claude': ch.binary(ch.CLAUDE) if hasattr(ch, 'binary') else None, 'plans': summaries,
              'pass': all(s['pass'] for s in summaries)}
    save(args.out / 'summary.json', result)
    for leftover in set(ch.WORK_BASE.iterdir()) - before:  # this run's isolated working directories
        shutil.rmtree(leftover, ignore_errors=True)
    raise SystemExit(0 if result['pass'] else 1)


if __name__ == '__main__':
    main()
