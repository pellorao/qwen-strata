"""OpenAI-arm scheduler for one scenario: 6 configs x N valid instances, rounds alternate with reversed order,
<= slots parallel in one shared CODEX_HOME (user 2026-10-20; plan §14.3).

luna xhigh / max supplement (user 2026-10-22, docs/plan.md 9a): the v1 scheduler (ccc49394) with CONFIGS = luna xhigh,
max; at most MAX_PARALLEL = 3 instances; the credits baseline is the first balance seen in this loan (credits0.txt)
instead of the v1 constant; --round-group N lets N consecutive rounds share one barrier (1 = v1, 0 = no barrier).

- The login link enters the shared home once before the first launch and is released once at the end, only after no
  benchmark Codex process of this home is left (M5), also when the scheduler itself fails.
- slots.txt (a number) is re-read before every launch; WSL benchmark Claude Code + Codex processes stay < PROC_LIMIT.
- STOP file: no new launches. No launch after NO_NEW; instances still running at HARD_END are killed and voided.
- Plan usage (M1), read every loop from the newest token_count.rate_limits in the shared sessions: weekly used_percent
  >= the cap (usage_cap.txt, default USED_CAP) stops new launches; any credits balance below CREDITS0 kills every running
  instance (voided) and stops, until the user authorises spending credits.
- Invalid instances are retried at the end of the queue (MAX_ATTEMPTS per cell). An ARW early-exit pause (S2) stops that
  cell for the user. A quota / rate-limit end (429 or error type, S6) stops all and is not counted as an attempt (M2).
- Shared-home checks (M4): models_cache.json and config.toml keep the bytes first seen; each config's startup context
  SHA stays the same; memories stage1_outputs is empty at the end. A change stops all.

    python3 .tmp/luna-xhigh-1022/run/schedule.py <scenario-key> [--n 5] [--time-limits T.json] [--round-group N]
"""
import argparse
import datetime as dt
import hashlib
import json
import re
import os
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path

ROOT = Path('/home/pello/projects/qwen_strata')
BASE = Path(__file__).resolve().parent  # .tmp/luna-xhigh-1022/run
HOME = BASE / 'codex-home'
TMP_PREP = Path('/tmp/qwen-openai-1020')
sys.path.insert(0, str(ROOT))
from tools.reviewer.providers import link_login, release_login  # noqa: E402

# Tunables
PROVIDER = {'auth': 'chatgpt', 'auth_home': '/home/pello/.codex'}
SCENARIOS = {'ca': ('commit-audit-v3', 1), 'cs': ('code-spec-v5', 1), 'cstd': ('code-standards-v5.1', 1),
             'sr': ('spec-readiness-v4.3', 2)}
CONFIGS = [('gpt-6-luna', 'xhigh'), ('gpt-6-luna', 'max')]
MAX_PARALLEL = 3  # user 2026-10-22: at most 3 instances at once, whatever slots.txt says
MAX_ATTEMPTS = 8
PROC_LIMIT = 5  # plan §14: benchmark Claude Code + Codex processes in WSL, all arms together
USED_CAP = 100.0  # weekly used_percent: no cap (user 2026-10-20); a credits fall still stops all
CREDITS0_FILE = 'credits0.txt'  # first credits balance seen in this loan; a lower balance later stops all (v1 rule)
TODAY = dt.date.today()
# Since the user's 2026-10-20 extension the loan has no clock end; RETURN (below) ends it. --no-new-after still caps.
NO_NEW = HARD_END = LAST_END = float('inf')
RETURN_GRACE = 24 * 60  # RETURN file: no new launches at once; running instances get this long, then are voided
# ("用户收回 Codex", not an attempt), so that the login is back within 30 minutes of the trigger (Main 2026-10-20).  # Main: running instances end by themselves before
CUTOFF_MARGIN = 120                                                   # 10:58; T + 2 min margin before 10:55
BORROW = 1  # the 2026-10-22 evening loan
CODEX_BIN = Path.home() / '.local/share/qwen-bench/codex-0.163.0/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex'


def log(path, **event):
    event['t'] = time.strftime('%H:%M:%S')
    with path.open('a') as f:
        f.write(json.dumps(event, ensure_ascii=False) + '\n')
    print(json.dumps(event, ensure_ascii=False), flush=True)


LAUNCH_GAP = 15  # seconds between any two launches on the shared home, across this arm's schedulers (Main 2026-10-20)


def launch_gap_passed():
    """True (and the launch is claimed) when LAUNCH_GAP has passed since this arm's last launch: CStd luna-low-a2 failed
    at start beside three other starts on the same home within 5 s (ARW: native member facts incomplete)."""
    import fcntl
    stamp = BASE / 'last-launch'
    with (BASE / 'last-launch.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if stamp.exists() and time.time() - stamp.stat().st_mtime < LAUNCH_GAP:
            return False
        stamp.touch()
        return True


def number(name, default):
    try:
        return type(default)((BASE / name).read_text().strip())
    except (OSError, ValueError):
        return default


def argv_of(pid):
    try:
        return (Path('/proc') / pid / 'cmdline').read_bytes().split(b'\0')
    except OSError:
        return None


def bench_processes():
    """Same count as the Strata arm's scheduler: pinned benchmark Claude Code (-p) and native Codex processes."""
    n = 0
    for p in Path('/proc').iterdir():
        argv = argv_of(p.name) if p.name.isdigit() else None
        if not argv:
            continue
        exe = argv[0].decode(errors='replace')
        if ('qwen-bench/claude-code' in exe and b'-p' in argv) or ('qwen-bench/codex' in exe and exe.endswith('/codex')):
            n += 1
    return n


def home_codex_pids():
    """Benchmark Codex processes running on this shared home (CODEX_HOME in their environment; only that name is kept)."""
    pids, want = [], b'CODEX_HOME=' + str(HOME).encode()
    for p in Path('/proc').iterdir():
        argv = argv_of(p.name) if p.name.isdigit() else None
        if not argv or 'qwen-bench/codex' not in argv[0].decode(errors='replace'):
            continue
        try:
            if want in (p / 'environ').read_bytes().split(b'\0'):
                pids.append(int(p.name))
        except OSError:
            continue
    return pids


def latest_rate():
    """Newest rate_limits with a weekly used_percent in the shared sessions (tails of rollouts written in 30 minutes)."""
    best = None
    for f in (HOME / 'sessions').glob('*/*/*/rollout-*.jsonl'):
        try:
            if time.time() - f.stat().st_mtime > 1800:
                continue
            with f.open('rb') as h:
                h.seek(max(0, f.stat().st_size - 262144))
                lines = h.read().decode(errors='replace').splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            if '"rate_limits"' not in line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            rl = (e.get('payload') or {}).get('rate_limits') or {}
            if (rl.get('primary') or {}).get('used_percent') is not None:
                if best is None or e.get('timestamp', '') > best[0]:
                    best = (e.get('timestamp', ''), rl)
                break
    return best


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def memories():
    db = HOME / 'memories_1.sqlite'
    if not db.exists():
        return 0
    c = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    try:
        return c.execute('select count(*) from stage1_outputs').fetchone()[0]
    finally:
        c.close()


def startup_key(startup):
    """Startup hashes compared within a cell; the ARW messageId differs per handoff by design."""
    return {k: v for k, v in (startup or {}).items() if k != 'messageId'}


def handoff_role(handoff):
    """The handoff (role) a root thread served: its ARW instanceId minus the run UUID and instance suffix.
    SR runs two handoffs (runtime-migration, artifact-promotion) with different handoff texts by design, so
    startup contexts are compared per (cell, handoff), never across handoffs (fix 2026-10-20 10:45)."""
    return re.sub(r'-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-instance-\d+$', '', handoff.get('instanceId') or '')


def credits_baseline(credits, logf):
    """The loan's credits baseline: credits0.txt, written from the first balance any scheduler of this loan sees."""
    path = BASE / CREDITS0_FILE
    if not path.exists() and credits is not None:
        path.write_text(f'{credits}\n')
        log(logf, event='credits_baseline', credits=credits)
    try:
        return Decimal(path.read_text().strip())
    except (OSError, ArithmeticError):
        return None


def label(model, effort):
    return ('sol' if 'sol' in model else 'luna') + '-' + effort


def end_instance_leftovers(folder):
    """run_one's own cleanup of a killed instance's ARW daemon tree and processes naming its run/prep directory."""
    import importlib.util
    spec = importlib.util.spec_from_file_location('run_one', BASE / 'run_one.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    loc = folder / 'prep-location.json'
    prep = Path(json.loads(loc.read_text())['prep']) if loc.exists() else Path('/nonexistent/prep')
    (folder / 'leftover-cleanup-on-return.json').write_text(json.dumps(mod.end_leftovers(folder.resolve(), prep)) + '\n')


def kill(proc):
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(60)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
    except ProcessLookupError:
        proc.wait()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('scenario', choices=SCENARIOS)
    ap.add_argument('--n', type=int, default=5)
    ap.add_argument('--slots', type=int, default=MAX_PARALLEL)
    # A second scheduler of this arm (e.g. CA refills beside CStd) reads its own cap; slotctl's reserve.txt keeps
    # the arm's total within MAX.
    ap.add_argument('--slots-file', default='slots.txt')
    ap.add_argument('--no-new-after', help='HH:MM, earlier than 10:40 (a refill scheduler ends before the main one)')
    ap.add_argument('--time-limits', type=Path, help='JSON {label: seconds} for CS/CStd')
    ap.add_argument('--keep-login', action='store_true',
                    help='keep the login linked after the queue ends (more work follows in the same loan); RETURN still releases it')
    ap.add_argument('--round-group', type=int, default=1,
                    help='rounds sharing one barrier: 1 = v1 (a round finishes before the next starts), 0 = no barrier')
    a = ap.parse_args()
    global NO_NEW
    if a.no_new_after:
        NO_NEW = min(NO_NEW, dt.datetime.combine(TODAY, dt.time(*map(int, a.no_new_after.split(':')))).timestamp())
    name, handoffs = SCENARIOS[a.scenario]
    plan = ROOT / f'benchmarks/multi-model-v1/scenarios/{name}.json'
    out = BASE / a.scenario
    out.mkdir(exist_ok=True)
    logf = out / 'schedule.jsonl'
    limits = json.loads(a.time_limits.read_text()) if a.time_limits else {}
    # Queue entries are (round, cell). Main 2026-10-20: a round's 6 configurations all finish before the next round
    # starts; a rerun joins the last round. Each configuration stops launching at min(NO_NEW, LAST_END - T - margin)
    # so every running instance ends by itself before the hard end.
    queue = []
    for r in range(a.n):
        queue += [(r, c) for c in (CONFIGS if r % 2 == 0 else CONFIGS[::-1])]
    round_of = {}
    cutoff = {c: min(NO_NEW, LAST_END - limits.get(label(*c), 0) - CUTOFF_MARGIN) for c in CONFIGS}
    attempts, seq, valid, running, startups, stopped_cells = {}, {}, {}, {}, {}, set()
    # Resume: instances already in the scenario folder keep their numbering, attempts and validity (a reclassified
    # verdict, added by Main's decision beside the original one, wins); each valid one takes its cell off the queue.
    by_label = {label(*c): c for c in CONFIGS}
    # A folder without instance.json (killed, voided) keeps its number but is not an attempt (§14 voids).
    for d in sorted(x for x in out.iterdir() if x.is_dir() and x.name.rsplit('-a', 1)[0] in by_label):
        seq[by_label[d.name.rsplit('-a', 1)[0]]] = max(seq.get(by_label[d.name.rsplit('-a', 1)[0]], 0), int(d.name.rsplit('-a', 1)[1]))
    for f in sorted(out.glob('*-a*/instance.json')):
        cell = by_label[f.parent.name.rsplit('-a', 1)[0]]
        inst = json.loads(f.read_text())
        if inst.get('refused') or (inst.get('void') or {}).get('attempt_counted') is False:
            continue  # a refused launch, or a void Main excluded from the attempts (CA S2 a3/a4, user 2026-10-20)
        attempts[cell] = attempts.get(cell, 0) + 1
        if (inst.get('reclassified') or {}).get('valid', inst.get('valid')):
            valid[cell] = valid.get(cell, 0) + 1
            queue.remove(next(q for q in queue if q[1] == cell))
            recheck = (inst.get('startup_recheck') or {}).get('startup') or [h.get('startup') for h in inst['handoffs']]
            for h, st in zip(inst['handoffs'], recheck):
                if startups.setdefault((cell, handoff_role(h)), startup_key(st)) != startup_key(st):
                    raise SystemExit(f'startup context differs within {label(*cell)} already ({f.parent.name})')
    # Cells stopped by S2 (ARW early-exit pause, run_one writes stop-cells.txt) get no launches on resume either.
    stops = BASE / f'stop-cells-{a.scenario}.txt'  # per scenario, written by run_one
    stopped_cells |= {by_label[x] for x in (stops.read_text().split() if stops.exists() else [])}
    queue = [q for q in queue if q[1] not in stopped_cells]
    home_sha = {}
    st = TMP_PREP.lstat() if TMP_PREP.exists() else None
    if st is None or not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o700:
        raise SystemExit(f'{TMP_PREP} must exist as a 0700 directory of this user before any Claude Code instance starts')
    HOME.mkdir(mode=0o700, exist_ok=True)
    if not os.path.lexists(HOME / 'auth.json'):
        log(logf, event='login_linked', link=link_login(PROVIDER, HOME))
    log(logf, event='start_scenario', scenario=name, n=a.n, limits=limits, used_cap=number('usage_cap.txt', USED_CAP),
        resumed_valid={label(*c): n for c, n in valid.items()}, queue=[label(*q[1]) for q in queue],
        borrow=BORROW, round_group=a.round_group, max_parallel=MAX_PARALLEL, cutoff={label(*c): None if t == float('inf') else time.strftime('%H:%M:%S', time.localtime(t)) for c, t in cutoff.items()},
        limits_sha256=sha(a.time_limits) if a.time_limits else None, codex_sha256=sha(CODEX_BIN), run_one_sha256=sha(BASE / 'run_one.py'))
    stop_all, last_rate, return_at = None, None, None

    def void_all(reason):
        for key, (proc, folder, cell) in list(running.items()):
            kill(proc)
            log(logf, event='killed', run=folder.name, reason=reason)
            running.pop(key)

    try:
        while queue or running:
            for key, (proc, folder, cell) in list(running.items()):
                if proc.poll() is None:
                    if return_at is not None and time.time() >= return_at + RETURN_GRACE:
                        kill(proc)
                        end_instance_leftovers(folder)
                        (folder / 'void.json').write_text(json.dumps({'reason': '用户收回 Codex', 'attempt_counted': False,
                            'at': time.strftime('%Y-%m-%dT%H:%M:%S'), 'return_requested_at': return_at}) + '\n')
                        log(logf, event='killed_on_return', run=folder.name)
                        running.pop(key)
                        continue
                    if time.time() >= HARD_END:
                        kill(proc)
                        log(logf, event='killed_at_deadline', run=folder.name)
                        running.pop(key)
                    continue
                running.pop(key)
                inst = json.loads((folder / 'instance.json').read_text()) if (folder / 'instance.json').exists() else {}
                ok = bool(inst.get('valid'))
                hs = inst.get('handoffs', [])
                log(logf, event='end', run=folder.name, valid=ok, rc=proc.returncode, limited=inst.get('limited'),
                    arw_pause=inst.get('arw_pause'), running=len(running),
                    checks=[h['checks'] for h in hs], tokens=[h['tokens'] for h in hs],
                    code_mode=[h.get('code_mode') for h in hs],
                    rate=[(h.get('rate_limits_last') or {}).get('primary') for h in hs],
                    credits=[((h.get('rate_limits_last') or {}).get('credits') or {}).get('balance') for h in hs])
                for h in hs:
                    now = startup_key(h.get('startup'))
                    first = startups.setdefault((cell, handoff_role(h)), now)
                    if now != first:
                        stop_all = f'startup context differs within {label(*cell)} {handoff_role(h)} ({folder.name})'
                # Patch review: every instance must show returned models and tiers and the applied harness patch;
                # an instance halt (M1) or a missing record stops all launches and leaves the cell for Main.
                anomaly = inst.get('halt') or ([] if inst else ['no instance.json'])
                if inst and not inst.get('halt') and not inst.get('limited'):
                    if not all(h['checks'].get('models_returned') for h in hs):
                        anomaly = ['no returned model recorded']
                    elif not all(set(h['checks'].get('service_tiers') or {}) - {'not-returned'} for h in hs):
                        anomaly = ['no returned service tier recorded']
                    elif 'mount_targets_ignored' not in inst:
                        anomaly = ['mount_targets_ignored missing']
                log(logf, event='instance_facts', run=folder.name, halt=anomaly or None,
                    mount_targets_ignored=inst.get('mount_targets_ignored'), cleanup=inst.get('leftover_cleanup'),
                    report_dir_model_violation=inst.get('report_dir_model_violation'))
                if anomaly:
                    stop_all = stop_all or f'halt {folder.name}: {anomaly}'
                    stopped_cells.add(cell)
                    log(logf, event='halt', run=folder.name, reasons=anomaly)
                elif ok:
                    valid[cell] = valid.get(cell, 0) + 1
                elif inst.get('limited'):
                    attempts[cell] -= 1  # §14: a quota end is not an attempt
                    queue.append((queue[-1][0] if queue else round_of.get(folder.name, 0), cell))
                    stop_all = stop_all or 'quota or rate limit (S6)'
                elif inst.get('arw_pause'):
                    stopped_cells.add(cell)
                    log(logf, event='cell_stopped_arw_pause', cell=label(*cell), run=folder.name)
                elif attempts[cell] < MAX_ATTEMPTS:
                    queue.append((queue[-1][0] if queue else round_of.get(folder.name, 0), cell))
            queue = [q for q in queue if q[1] not in stopped_cells]
            rate = latest_rate()
            if rate and rate != last_rate:
                last_rate = rate
                rl = rate[1]
                used, credits = rl['primary']['used_percent'], (rl.get('credits') or {}).get('balance')
                log(logf, event='rate', used_percent=used, credits=credits, at=rate[0], running=len(running))
                base = credits_baseline(credits, logf)
                if credits is not None and base is not None and Decimal(str(credits)) < base:
                    stop_all = f'credits balance fell to {credits}'
                    void_all('credits spent: voided until the user authorises credits')
                elif used >= number('usage_cap.txt', USED_CAP):
                    stop_all = stop_all or f'weekly used_percent {used} reached the cap'
            for f in ('models_cache.json', 'config.toml'):
                now = sha(HOME / f)
                if now and home_sha.setdefault(f, now) != now:
                    stop_all = f'shared {f} changed'
                    void_all(f'shared {f} changed')
            if return_at is None and (BASE / 'RETURN').exists():
                return_at = time.time()
                log(logf, event='return_requested', running=[k for k in running],
                    kill_at=time.strftime('%H:%M:%S', time.localtime(return_at + RETURN_GRACE)))
                stop_all = stop_all or 'RETURN: the user takes Codex back'
            if stop_all and 'startup' in stop_all and running:
                void_all(stop_all)
            if stop_all or (BASE / 'STOP').exists() or time.time() >= NO_NEW:
                if queue:
                    log(logf, event='no_new_launches', reason=stop_all or ('STOP' if (BASE / 'STOP').exists() else 'deadline'),
                        left=[label(*q[1]) for q in queue])
                    queue = []
            late = [q for q in queue if time.time() >= cutoff[q[1]]]
            if late:
                log(logf, event='config_cutoff', left=[f'{label(*q[1])}@r{q[0]}' for q in late])
                queue = [q for q in queue if q not in late]
            if queue and attempts.get(queue[0][1], 0) >= MAX_ATTEMPTS:
                # v1 counted attempts only at launch, so entries queued before a cell's last invalid ends could still
                # launch past MAX_ATTEMPTS (dry run 2026-10-22: 10 of 8); the cap now holds at launch.
                log(logf, event='attempt_cap', cell=label(*queue[0][1]), round=queue[0][0])
                queue.pop(0)
                continue
            barrier = bool(queue) and a.round_group > 0 and any(
                round_of.get(k, 0) // a.round_group < queue[0][0] // a.round_group for k in running)
            slots = min(number(a.slots_file, a.slots), MAX_PARALLEL)
            if queue and not barrier and len(running) < slots and bench_processes() < PROC_LIMIT:
                if not launch_gap_passed():
                    time.sleep(2)
                    continue
                rnd, cell = queue.pop(0)
                attempts[cell] = attempts.get(cell, 0) + 1
                seq[cell] = seq.get(cell, 0) + 1
                folder = out / f'{label(*cell)}-a{seq[cell]}'
                cmd = [sys.executable, str(BASE / 'run_one.py'), str(plan), str(folder), cell[0], cell[1],
                       '--codex-home', str(HOME), '--handoffs', str(handoffs), '--borrow', str(BORROW), '--round', str(rnd)]
                if label(*cell) in limits:
                    cmd += ['--time-limit-seconds', str(limits[label(*cell)])]
                proc = subprocess.Popen(cmd, cwd=ROOT, stdout=(out / f'{folder.name}.out').open('w'),
                                        stderr=subprocess.STDOUT, start_new_session=True)
                running[folder.name] = (proc, folder, cell)
                round_of[folder.name] = rnd
                log(logf, event='start', run=folder.name, round=rnd, borrow=BORROW, slots=slots, running=len(running),
                    bench_processes=bench_processes())
                time.sleep(5)
                continue
            time.sleep(10)
    finally:
        void_all('scheduler exit')
        # Another scheduler of this arm may still run instances on the shared home (CA refills beside CStd): then the
        # home's Codex processes and the login are its, not ours (2026-10-20: CA luna-high-a8 lost the login).
        others = [pid for pid in (int(x) for x in subprocess.run(['pgrep', '-f', str(BASE / 'schedule.py')],
                  capture_output=True, text=True).stdout.split()) if pid != os.getpid()
                  and [x.rsplit(b'/', 1)[-1] for x in (argv_of(str(pid)) or [])[:2]][:1] == [b'python3']
                  and (argv_of(str(pid)) or [b'', b''])[1].endswith(b'schedule.py')]
        deadline = time.time() + (30 if return_at is not None else 120)
        while not others and home_codex_pids() and time.time() < deadline:
            time.sleep(2)
        for pid in ([] if others else home_codex_pids()):
            os.kill(pid, signal.SIGKILL)
        time.sleep(2)
        left = home_codex_pids()
        log(logf, event='codex_processes_before_release', left=left, other_schedulers=others)
        if others:
            log(logf, event='login_not_released', reason=f'another scheduler of this arm is running: {others}')
        elif a.keep_login and return_at is None:
            log(logf, event='login_not_released', reason='--keep-login: more work follows in this loan')
        elif not left:
            log(logf, event='login_released', status=release_login(PROVIDER, HOME))
        else:
            log(logf, event='login_not_released', reason='Codex processes still on the shared home')
        # /tmp prep copies go once their project-disk copy is verified (prep review), listed first, then removed.
        gone = []
        for loc in sorted(out.glob('*/prep-location.json')):
            d = json.loads(loc.read_text())
            tmp = Path(d['prep']).parent
            if tmp.exists() and Path(d.get('copied_to', '/nonexistent')).is_dir() and all(r['sha_ok'] for r in d.get('reports', {}).values()):
                gone.append(str(tmp))
        log(logf, event='tmp_prep_delete_list', paths=gone)
        for g in gone:
            if Path(g).parent.parent == TMP_PREP:
                shutil.rmtree(g)
        log(logf, event='tmp_prep_deleted', count=len(gone))
        log(logf, event='done', stop=stop_all, memories_stage1_outputs=memories(), home_sha=home_sha,
            valid={label(*c): n for c, n in valid.items()}, attempts={label(*c): n for c, n in attempts.items()},
            stopped_cells=[label(*c) for c in stopped_cells])


if __name__ == '__main__':
    main()
