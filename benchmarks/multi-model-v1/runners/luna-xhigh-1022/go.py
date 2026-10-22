"""One command for the gpt-6-luna xhigh / max supplement (user 2026-10-22, docs/plan.md 9a), run after the user lends
the ChatGPT login:  nohup python3 .tmp/luna-xhigh-1022/run/go.py > .tmp/luna-xhigh-1022/run/go.out 2>&1 &

Steps, each logged to go.jsonl; RETURN or STOP in this directory ends the chain before the next step (a running
scheduler handles RETURN itself: no new launches, running instances up to 24 min, then the login is released):
  1. bindings (zero-model): Codex sha, catalog sha, scenario plans, script shas, /tmp prep base, login link target present
     (existence only, never opened), no RETURN / STOP, no other benchmark process;
  2. plan §7 short smoke per configuration (safety_gate --provider-run, smoke plan), xhigh then max; all must pass;
  3. P4 (v1 p4probe) for CS and CStd, xhigh and max -> cs-T.json, cstd-T.json; a T outside 1/3-3x of v1 luna-high
     (CS 612 s, CStd 606 s) is probed once more, then stops the chain for Main;
  4. scenarios one after another, ORDER below, --keep-login except the last; a scheduler that ends with a stop reason
     (halt, credits, RETURN, STOP) ends the chain; a cell short of N valid after 8 attempts is logged and the chain goes on;
  5. at the end the shared home's login link is released once no Codex process is left on it.
"""
import hashlib
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = Path('/home/pello/projects/qwen_strata')
sys.path.insert(0, str(ROOT))
from tools.reviewer.providers import release_login  # noqa: E402

# Tunables
ORDER = ['cs', 'cstd', 'ca', 'sr']
N = 5
# 1 = v1 barrier (a round finishes before the next starts: with 2 configurations at most 2 run at once); 2 = rounds
# r, r+1 share one barrier (2 xhigh + 2 max per window, up to 3 at once); 0 = no barrier. Main confirms (report).
ROUND_GROUP = 2
EFFORTS = ['xhigh', 'max']
V1_LUNA_HIGH_T = {'cs': 612, 'cstd': 606}
TMP_PREP = Path('/tmp/qwen-openai-1020')
AUTH = Path('/home/pello/.codex/auth.json')
EXPECT = {
    'codex': '399ff69c431c066e40de318fba45c2b07f45a76b19939d247ee4828fc70c4215',
    'catalog': '40484bebf682d155afb8622fdef062d08478c4e6efd4c59f5a353fe56fb89bb3',
    'commit-audit-v3': '6de471d9', 'code-spec-v5': '990e9363', 'code-standards-v5.1': '89b604c9',
    'spec-readiness-v4.3': 'f1ad28d1',
}
CODEX = Path.home() / ('.local/share/qwen-bench/codex-0.163.0/node_modules/@openai/codex/node_modules/@openai/'
                       'codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex')
CATALOG = ROOT / 'benchmarks/multi-model-v1/catalogs/openai-codex-0.163.0.json'
LOG = BASE / 'go.jsonl'


def log(**event):
    event['t'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    line = json.dumps(event, ensure_ascii=False)
    with LOG.open('a') as f:
        f.write(line + '\n')
    print(line, flush=True)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stop_requested():
    return next((n for n in ('RETURN', 'STOP') if (BASE / n).exists()), None)


def halt(reason):
    log(event='chain_stopped', reason=reason)
    release_shared_login()
    raise SystemExit(1)


def bindings():
    import schedule as s
    plans = {p.stem: sha(p) for p in sorted((ROOT / 'benchmarks/multi-model-v1/scenarios').glob('*.json'))}
    got = {'codex': sha(CODEX), 'catalog': sha(CATALOG), **{k: plans[k][:8] for k in EXPECT if k in plans}}
    bad = {k: got.get(k) for k, v in EXPECT.items() if got.get(k) != v}
    scripts = {n: sha(BASE / n) for n in ('run_one.py', 'schedule.py', 'p4probe.py', 'go.py')}
    st = TMP_PREP.lstat() if TMP_PREP.exists() else None
    if st is None:
        TMP_PREP.mkdir(mode=0o700)
        TMP_PREP.chmod(0o700)
        st = TMP_PREP.lstat()
    prep_ok = stat.S_ISDIR(st.st_mode) and st.st_uid == os.getuid() and stat.S_IMODE(st.st_mode) == 0o700
    others = s.bench_processes()
    log(event='bindings', got=got, scenario_plans=plans, scripts=scripts, mismatched=bad or None, tmp_prep_ok=prep_ok,
        login_present=os.path.lexists(AUTH), other_benchmark_processes=others, stop=stop_requested())
    if bad or not prep_ok or not os.path.lexists(AUTH) or others or stop_requested():
        halt('bindings not as expected (see the bindings event)')


def smoke():
    for effort in EFFORTS:
        if stop_requested():
            halt(stop_requested())
        out = BASE / f'smoke/gpt-6-luna-{effort}'
        if (out / 'result.json').exists() and json.loads((out / 'result.json').read_text()).get('all_observed_pass'):
            log(event='smoke_already_passed', effort=effort)
            continue
        started = time.time()
        with (BASE / f'smoke/gpt-6-luna-{effort}.log').open('w') as f:
            rc = subprocess.run([sys.executable, '-m', 'tools.safety.safety_gate', '--source', str(BASE / 'arw-source'),
                                 '--provider-run', str(out), '--plan', str(BASE / f'smoke/plan-gpt-6-luna-{effort}.json')],
                                cwd=ROOT, stdout=f, stderr=subprocess.STDOUT).returncode
        result = json.loads((out / 'result.json').read_text()) if (out / 'result.json').exists() else {}
        tokens = json.loads((out / 'tokens.json').read_text()) if (out / 'tokens.json').exists() else None
        log(event='smoke', effort=effort, rc=rc, seconds=round(time.time() - started),
            all_observed_pass=result.get('all_observed_pass'), rows=len(result.get('rows') or []), tokens=tokens,
            plan_usage=last_rate(out))
        if rc or not result.get('all_observed_pass'):
            halt(f'smoke {effort} did not pass')


def last_rate(folder):
    """Newest rate_limits (weekly used_percent, credits) in the rollouts below folder, for the quota check."""
    best = None
    for f in Path(folder).rglob('rollout-*.jsonl'):
        for line in f.read_text(errors='replace').splitlines():
            if '"rate_limits"' not in line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            rl = (e.get('payload') or {}).get('rate_limits') or {}
            if rl.get('primary') and (best is None or e.get('timestamp', '') > best['at']):
                best = {'at': e.get('timestamp', ''), 'used_percent': rl['primary'].get('used_percent'),
                        'credits': (rl.get('credits') or {}).get('balance')}
    return best


def p4():
    for scen in ('cs', 'cstd'):
        limits = BASE / f'{scen}-T.json'
        for effort in EFFORTS:
            cfg = f'luna-{effort}'
            if limits.exists() and cfg in json.loads(limits.read_text()):
                log(event='p4_already_measured', scenario=scen, cfg=cfg)
                continue
            for attempt in (1, 2):
                if stop_requested():
                    halt(stop_requested())
                folder = BASE / f'p4-{scen}' / cfg
                if folder.exists():
                    folder.rename(folder.with_name(f'{cfg}-attempt{attempt - 1}-{time.time_ns()}'))
                started = time.time()
                with (BASE / f'p4-{scen}-{cfg}.log').open('a') as f:
                    rc = subprocess.run([sys.executable, str(BASE / 'p4probe.py'), scen, cfg], cwd=ROOT, stdout=f,
                                        stderr=subprocess.STDOUT).returncode
                T = json.loads(limits.read_text()).get(cfg) if limits.exists() else None
                result = json.loads((folder / 'result.json').read_text()) if (folder / 'result.json').exists() else {}
                ratio = T / V1_LUNA_HIGH_T[scen] if T else None
                ok = (rc == 0 and isinstance(T, int) and T > 0 and 1 / 3 <= ratio <= 3 and result.get('models')
                      and all(m.startswith('gpt-6-luna') or m.startswith('codex-auto-review') for m in result['models'])
                      and result.get('tiers') == ['default'] and not any((result.get('tool_calls') or {}).values()))
                log(event='p4', scenario=scen, cfg=cfg, attempt=attempt, rc=rc, seconds=round(time.time() - started),
                    T=T, ratio_to_v1_luna_high=ratio and round(ratio, 3), beta=result.get('beta'), G=result.get('G'),
                    models=result.get('models'), tiers=result.get('tiers'), tool_calls=result.get('tool_calls'),
                    release=result.get('release'), ok=bool(ok))
                if ok:
                    break
                if attempt == 2:
                    halt(f'P4 {scen} {cfg} failed twice or is outside 1/3-3x of v1 luna-high')
                if limits.exists():  # the failed value must not reach the scheduler
                    kept = json.loads(limits.read_text())
                    kept.pop(cfg, None)
                    limits.write_text(json.dumps(kept) + '\n')


def scenario(scen, last):
    if stop_requested():
        halt(stop_requested())
    cmd = [sys.executable, str(BASE / 'schedule.py'), scen, '--n', str(N), '--round-group', str(ROUND_GROUP)]
    if scen in V1_LUNA_HIGH_T:
        cmd += ['--time-limits', str(BASE / f'{scen}-T.json')]
    if not last:
        cmd += ['--keep-login']
    log(event='scenario_start', scenario=scen, cmd=cmd[1:])
    with (BASE / f'schedule-{scen}.out').open('a') as f:
        rc = subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT).returncode
    done = [json.loads(line) for line in (BASE / scen / 'schedule.jsonl').read_text().splitlines()
            if '"event": "done"' in line]
    done = done[-1] if done else {}
    short = {f'luna-{e}': (done.get('valid') or {}).get(f'luna-{e}', 0) for e in EFFORTS}
    log(event='scenario_done', scenario=scen, rc=rc, stop=done.get('stop'), valid=short, attempts=done.get('attempts'))
    if rc or done.get('stop'):
        halt(f'{scen} ended with rc {rc}, stop {done.get("stop")!r}, valid {short}')
    if any(v < N for v in short.values()):  # a cell used up MAX_ATTEMPTS: reported, the loan goes on
        log(event='scenario_short', scenario=scen, valid=short)


def release_shared_login():
    """The chain's last schedulers keep the login (--keep-login); release it once no Codex process is on the home."""
    import schedule as s
    if not os.path.lexists(s.HOME / 'auth.json'):
        log(event='shared_login', status='not linked')
        return
    deadline = time.time() + 120
    while s.home_codex_pids() and time.time() < deadline:
        time.sleep(2)
    left = s.home_codex_pids()
    if left:
        log(event='shared_login', status='NOT released: Codex processes still on the shared home', pids=left)
        return
    log(event='shared_login', status=release_login(s.PROVIDER, s.HOME))


def main():
    os.chdir(ROOT)
    sys.path.insert(0, str(BASE))
    log(event='chain_start', order=ORDER, n=N, round_group=ROUND_GROUP, pid=os.getpid())
    bindings()
    smoke()
    p4()
    for i, scen in enumerate(ORDER):
        scenario(scen, i == len(ORDER) - 1)
    release_shared_login()
    log(event='chain_done')


if __name__ == '__main__':
    main()
