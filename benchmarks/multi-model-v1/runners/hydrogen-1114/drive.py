"""Sequential driver for the Hydrogen supplement (plan.md §3 排程): effort-major (high, medium, xhigh), scenarios CA, CS, CStd,
SR, five valid instances per cell, at most 8 attempts per cell (quota hits do not count), stops when the Gemini 5h window has under 3 % left or the weekly window under 10 % (user 2026-11-14: use the quota up, then wait for the next 5 h).
Idempotent: instance directories already holding instance.json are classified, not rerun.

    python3 -I drive.py plan|status|run [--efforts high medium xhigh] [--scenarios ca cs cstd sr] [--n 5] [--max-minutes M]
Ledger: .tmp/hydrobench/drive.jsonl (one event per line). A STOP file at .tmp/hydrobench/STOP halts before the next instance.
T for cs / cstd comes from .tmp/hydrobench/p4/<scenario>-T.json (p4probe.py).
"""
import argparse
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path('/home/pello/projects/qwen-strata')
HERE = Path(__file__).resolve().parent
OUT = ROOT / '.tmp/hydrobench'
CARRY = OUT / 'carryover.json'
STOP_NAME = os.environ.get('HYDRO_STOP', 'STOP')   # parallel lanes (hydroeffort run.py) use their own stop file name
LIMITS_READINGS = Path(os.path.expanduser('~/.claude/statusline/agy-readings.jsonl'))
MIN_REMAIN_5H = 3.0     # stop line: remaining percent of the 5h window
MIN_REMAIN_WEEK = 10.0  # stop line: remaining percent of the weekly window (keeps quota for translation etc.)
MAX_ATTEMPTS = 8
MAX_GEMINI = 3   # most Gemini runs at once across every task (registry entries with harness agy-gemini; user 2026-11-15)
LABEL = 'common/hydroeffort'
GUARD_LABEL = LABEL + (':' + os.environ['HYDRO_LANE'] if os.environ.get('HYDRO_LANE') else '')   # one usage-guard ledger per parallel lane
TURNS_PER_START = 2.2   # expected agy turns per instance start (CA/CS/CStd 1 handoff, SR 2; reminder and continuation turns add some)
T_MIN, T_MAX = 900, 3600   # s: the formula T of cs / cstd is clamped to this range (user 2026-11-15)
T_RERUN = 3600             # s: a cell holding a timed-out instance reruns at T_MAX; timing out there too stops the driver (Main decides)
SEARCH_STOP = 0.30  # plan §3: voided for search / sub-agent use over this share of attempts
sys.path.insert(0, str(HERE))
import agyrun  # noqa: E402
sys.path.insert(0, os.path.expanduser('~/.claude/lib'))
import usage_guard as ug  # noqa: E402


def log(**event):
    event['at'] = time.strftime('%F %T')
    with (OUT / 'drive.jsonl').open('a') as f:
        f.write(json.dumps(event, ensure_ascii=False) + '\n')
    print(json.dumps(event, ensure_ascii=False), flush=True)


def acquire_slot(effort):
    """Register this instance as a running Gemini (agy-gemini) run once fewer than MAX_GEMINI are registered in all (user 2026-11-15: at most 3 Gemini
    runs at once across every task); waits otherwise. Count and registration happen under one file lock so parallel lanes cannot both take the last
    slot (same lock file as the Carbon driver's: .tmp/carbonbench/slot.lock). None when the stop file appears while waiting."""
    lock = ROOT / '.tmp/carbonbench/slot.lock'
    while True:
        with open(lock, 'w') as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            if sum(1 for r in ug.live_runs() if r.get('harness') == 'agy-gemini') < MAX_GEMINI:
                return ug.register(LABEL, 'agy-gemini', model='Hydrogen', effort=effort, source='agy-gemini')   # one registration per instance, its real effort
        if (OUT / STOP_NAME).exists():
            return None
        time.sleep(30)


def agy_identity():
    """(real path, size, mtime) of the agy binary: a change between instances means agy updated itself (plan section 3: stop)."""
    p = os.path.realpath(agyrun.AGY)
    st = os.stat(p)
    return [p, st.st_size, int(st.st_mtime)]


def safe_remaining():
    try:
        return agyrun.remaining()
    except RuntimeError:
        return None


def projected_5h(rem):
    """The 5h remaining percent now, not at the last limits reading: that reading is up to ~30 min old (07:34 showed 6.8 % left, the
    quota was gone at 07:40), so subtract the burn since then at the rate between the last two readings of the same window."""
    try:
        at = json.loads(agyrun.LIMITS.read_text())['at']
        rows = [json.loads(l) for l in LIMITS_READINGS.read_text().splitlines()[-2:]]
        a, b = [next(w for w in r['groups']['antigravity-gemini'] if w['name'] == '5h') for r in rows]
        if len(rows) < 2 or a['resets_at'] != b['resets_at'] or rows[1]['at'] <= rows[0]['at']:
            return rem['5h']
        rate = max(0.0, (b['used_pct'] - a['used_pct']) / ((rows[1]['at'] - rows[0]['at']) / 60))
        return rem['5h'] - rate * max(0.0, time.time() - at) / 60
    except (OSError, ValueError, KeyError, StopIteration):
        return rem['5h']


def classify(folder):
    """valid | invalid | void (quota) for an instance directory, with the reasons."""
    inst = json.loads((folder / 'instance.json').read_text()) if (folder / 'instance.json').is_file() else None
    if inst is None or not inst['handoffs']:
        return 'void', ['no instance.json']
    handoffs = inst['handoffs']
    n = {'ca': 1, 'cs': 1, 'cstd': 1, 'sr': 2}[folder.parent.name]
    if any(h.get('privacy_hits') for h in handoffs):
        return 'void', ['privacy hits: nothing sent']
    if len(handoffs) < n:
        return 'invalid', ['fewer handoffs than the scenario has']
    reasons, quota = [], False
    for h in handoffs:
        c = h.get('checks') or {}
        quota |= bool(c.get('quota_hit'))
        if not c.get('valid'):
            reasons += [f"h{h['k']}: {name}" for name in ('model_match', 'ended_normally')
                        if c.get(name) is False] + ([f"h{h['k']}: forbidden_tools {c['forbidden_tools']}"] if c.get('forbidden_tools') else []) \
                + ([f"h{h['k']}: denied_actions"] if c.get('denied_actions') else []) + ([f"h{h['k']}: status {c.get('status')} {c.get('error')}"]
                                                                                           if not c.get('ended_normally') else [])
    if quota:
        return 'void', ['quota hit'] + reasons
    if folder.parent.name in ('cs', 'cstd') and not reasons and any((h.get('checks') or {}).get('hard_stop') for h in handoffs):
        return 'timeout', [f"hard stop at T={inst.get('T')} s"]   # interrupted at T: voided, rerun (user 2026-11-15)
    return ('invalid', reasons or ['not valid']) if reasons else ('valid', [])


def cells(efforts, scenarios):
    return [(e, s) for e in efforts for s in scenarios]


def cell_state(effort, key):
    folder = OUT / key
    valid, invalid, void, search, timeout, capped = [], [], [], 0, [], []
    for d in sorted(folder.glob(f'hydrogen-{effort}-a*')) if folder.is_dir() else []:
        verdict, reasons = classify(d)
        {'valid': valid, 'invalid': invalid, 'void': void, 'timeout': timeout}[verdict].append(d.name)
        if verdict == 'timeout' and (json.loads((d / 'instance.json').read_text()).get('T') or 0) >= T_RERUN:
            capped.append(d.name)   # timed out even at the cap: no more reruns
        search += any('forbidden_tools' in r or 'denied_actions' in r for r in reasons)
    attempts = [int(d.name.rsplit('-a', 1)[1]) for d in (sorted(folder.glob(f'hydrogen-{effort}-a*')) if folder.is_dir() else [])]
    # instances of the first run whose directories are gone (kept in the exported records): CARRY[<effort>/<key>] = {valid, timeout, attempts}
    carry = json.loads(CARRY.read_text()).get(f'{effort}/{key}', {}) if CARRY.is_file() else {}
    valid += [f'carried-{i}' for i in range(carry.get('valid', 0))]
    timeout += [f'carried-timeout-{i}' for i in range(carry.get('timeout', 0))]
    attempts.append(carry.get('attempts', 0))
    return {'valid': valid, 'invalid': invalid, 'void': void, 'search_voided': search, 'timeout': timeout, 'timeout_at_cap': capped,
            'next_attempt': max(attempts, default=0) + 1, 'counted_attempts': len(valid) + len(invalid)}


def limit_for(key, effort):
    if key not in ('cs', 'cstd'):
        return None
    if cell_state(effort, key)['timeout']:
        return T_RERUN
    f = OUT / 'p4' / f'{ {"cs": "cs", "cstd": "cstd"}[key] }-T.json'
    return min(T_MAX, max(T_MIN, json.loads(f.read_text())[effort])) if f.is_file() else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=('plan', 'status', 'run'))
    ap.add_argument('--efforts', nargs='+', default=['high', 'medium', 'xhigh'], choices=('low', 'medium', 'high', 'xhigh'))
    ap.add_argument('--scenarios', nargs='+', default=['ca', 'cs', 'cstd', 'sr'])
    ap.add_argument('--n', type=int, default=5)
    ap.add_argument('--max-starts', type=int, default=None,
                    help='hard cap on instance starts in this invocation (default: 1.3 x the valid instances still missing + 3)')
    ap.add_argument('--max-minutes', type=float, default=None,
                    help='do not start a new instance after this many minutes (use 100 under a 2 h background cap; one instance takes up to ~17 min)')
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.cmd in ('plan', 'status'):
        for e, k in cells(a.efforts, a.scenarios):
            s = cell_state(e, k)
            print(e, k, f"valid {len(s['valid'])}/{a.n} invalid {len(s['invalid'])} void {len(s['void'])} search-voided {s['search_voided']} "
                        f"next a{s['next_attempt']} T {limit_for(k, e)}")
        return
    missing = sum(max(0, a.n - len(cell_state(e, k)['valid'])) for e, k in cells(a.efforts, a.scenarios))
    max_starts = a.max_starts or int(missing * 1.3) + 3
    # Usage watch (worker-rules): expected agy turns for the missing instances; the guard stops at 2x. agyrun.turn counts every turn (child processes join via env).
    guard = ug.Guard.start(GUARD_LABEL, calls=int(max_starts * TURNS_PER_START), secs=((a.max_minutes or 600) + 25) * 60)
    guard.export_env()
    os.environ['HYDROGEN_REGISTERED'] = '1'   # the instance is registered once here (acquire_slot), not per turn
    agy_id = agy_identity()
    log(event='run_start', agy=agy_id, missing_valid=missing, max_starts=max_starts, expected_turns=int(max_starts * TURNS_PER_START))
    streak, last, starts = 0, None, 0
    t_start = time.time()
    for effort, key in cells(a.efforts, a.scenarios):
        while True:
            s = cell_state(effort, key)
            if len(s['valid']) >= a.n:
                break
            if s['counted_attempts'] >= MAX_ATTEMPTS:
                log(event='cell_attempt_cap', effort=effort, scenario=key, **{k: s[k] for k in ('valid', 'invalid')})
                break
            if s['timeout_at_cap']:
                log(event='timeout_at_cap', effort=effort, scenario=key, instances=s['timeout_at_cap']); return
            if (OUT / STOP_NAME).exists():
                log(event='stop_file'); return
            if a.max_minutes and time.time() - t_start > a.max_minutes * 60:
                log(event='time_stop', minutes=a.max_minutes, before=f'{effort}/{key}'); return
            if agy_identity() != agy_id:
                log(event='agy_changed', before=agy_id, now=agy_identity()); return
            if starts >= max_starts:
                log(event='max_starts_stop', starts=starts); return
            try:
                guard.check()
                rem = agyrun.remaining()
            except ug.Stopped as e:
                log(event='guard_stop', reason=str(e)); return
            except RuntimeError as e:
                log(event='limits_stale', reason=str(e)); return
            proj = projected_5h(rem)
            if proj < MIN_REMAIN_5H or rem['\u5468'] < MIN_REMAIN_WEEK:
                log(event='quota_stop', remaining={**rem, '5h': round(proj, 1)}, read_5h=rem['5h'], before=f'{effort}/{key}'); return
            T = limit_for(key, effort)
            if key in ('cs', 'cstd') and T is None:
                log(event='no_T', effort=effort, scenario=key); return
            attempt = s['next_attempt']
            cmd = [sys.executable, '-I', str(HERE / 'run_one.py'), key, effort, str(attempt)] + (['--T', str(T)] if T else [])
            run = acquire_slot(effort)
            if run is None:
                log(event='stop_file'); return
            started = time.time()
            starts += 1
            try:
                r = subprocess.run(cmd, capture_output=True, text=True)
            finally:
                run.close()
            folder = OUT / key / f'hydrogen-{effort}-a{attempt}'
            if r.returncode != 0:
                (OUT / key).mkdir(exist_ok=True)
                (OUT / f'fail-{key}-{effort}-a{attempt}.err').write_text(r.stdout[-3000:] + r.stderr[-6000:])
                log(event='run_one_failed', effort=effort, scenario=key, attempt=attempt, rc=r.returncode, tail=r.stderr[-300:])
                streak = streak + 1 if last == 'fail' else 1
                last = 'fail'
                if streak >= 3:
                    log(event='stop_three_failures'); return
                if folder.exists() and not (folder / 'instance.json').exists():
                    shutil.rmtree(folder)  # prepare failed before anything was sent; the attempt number is reused
                continue
            verdict, reasons = classify(folder)
            log(event='instance', effort=effort, scenario=key, attempt=attempt, verdict=verdict, reasons=reasons,
                wall=round(time.time() - started), remaining=safe_remaining())
            if verdict == 'void' and 'quota hit' in reasons:
                # The service says the quota is used up (the limits file lags by up to ~30 min, so the stop line did not fire first):
                # stop this lane as a quota stop with the reset time from the message, not as a streak of identical failures.
                m = re.search(r'Resets in (?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?', ' '.join(reasons))
                reset_s = (int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)) if m else None
                log(event='quota_stop', remaining=safe_remaining() or {}, reset_s=reset_s, cause='quota hit', before=f'{effort}/{key}'); return
            tag = f'{verdict}:{sorted(reasons)[:1]}'
            streak = streak + 1 if (verdict != 'valid' and last == tag) else (1 if verdict != 'valid' else 0)
            last = tag if verdict != 'valid' else None
            if streak >= 3:
                log(event='stop_three_same_invalid', reason=tag); return
            # search / sub-agent voids over 30 % of the attempts: the configuration cannot be measured without search
            total = sum(cell_state(e, k)['counted_attempts'] for e, k in cells([effort], a.scenarios))
            searched = sum(cell_state(e, k)['search_voided'] for e, k in cells([effort], a.scenarios))
            if total >= 6 and searched / total > SEARCH_STOP:
                log(event='stop_search_share', effort=effort, searched=searched, attempts=total); return
    log(event='driver_finished')


if __name__ == '__main__':
    main()
