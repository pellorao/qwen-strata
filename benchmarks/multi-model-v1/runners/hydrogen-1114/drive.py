"""Sequential driver for the Hydrogen supplement (plan.md §3 排程): effort-major (high, medium, xhigh), scenarios CA, CS, CStd,
SR, five valid instances per cell, at most 8 attempts per cell (quota hits do not count), stops when the Gemini 5h window has under 3 % left or the weekly window under 10 % (user 2026-11-14: use the quota up, then wait for the next 5 h).
Idempotent: instance directories already holding instance.json are classified, not rerun.

    python3 -I drive.py plan|status|run [--efforts high medium xhigh] [--scenarios ca cs cstd sr] [--n 5] [--max-minutes M]
Ledger: .tmp/hydrobench/drive.jsonl (one event per line). A STOP file at .tmp/hydrobench/STOP halts before the next instance.
T for cs / cstd comes from .tmp/hydrobench/p4/<scenario>-T.json (p4probe.py).
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path('/home/pello/projects/qwen-strata')
HERE = Path(__file__).resolve().parent
OUT = ROOT / '.tmp/hydrobench'
CARRY = OUT / 'carryover.json'
MIN_REMAIN_5H = 3.0     # stop line: remaining percent of the 5h window
MIN_REMAIN_WEEK = 10.0  # stop line: remaining percent of the weekly window (keeps quota for translation etc.)
MAX_ATTEMPTS = 8
T_MIN, T_MAX = 900, 3600   # s: the formula T of cs / cstd is clamped to this range (user 2026-11-15)
T_RERUN = 3600             # s: a cell holding a timed-out instance reruns at T_MAX; timing out there too stops the driver (Main decides)
SEARCH_STOP = 0.30  # plan §3: voided for search / sub-agent use over this share of attempts
sys.path.insert(0, str(HERE))
import agyrun  # noqa: E402


def log(**event):
    event['at'] = time.strftime('%F %T')
    with (OUT / 'drive.jsonl').open('a') as f:
        f.write(json.dumps(event, ensure_ascii=False) + '\n')
    print(json.dumps(event, ensure_ascii=False), flush=True)


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
    ap.add_argument('--efforts', nargs='+', default=['high', 'medium', 'xhigh'])
    ap.add_argument('--scenarios', nargs='+', default=['ca', 'cs', 'cstd', 'sr'])
    ap.add_argument('--n', type=int, default=5)
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
    streak, last = 0, None
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
            if (OUT / 'STOP').exists():
                log(event='stop_file'); return
            if a.max_minutes and time.time() - t_start > a.max_minutes * 60:
                log(event='time_stop', minutes=a.max_minutes, before=f'{effort}/{key}'); return
            rem = agyrun.remaining()
            if rem['5h'] < MIN_REMAIN_5H or rem['\u5468'] < MIN_REMAIN_WEEK:
                log(event='quota_stop', remaining=rem, before=f'{effort}/{key}'); return
            T = limit_for(key, effort)
            if key in ('cs', 'cstd') and T is None:
                log(event='no_T', effort=effort, scenario=key); return
            attempt = s['next_attempt']
            cmd = [sys.executable, '-I', str(HERE / 'run_one.py'), key, effort, str(attempt)] + (['--T', str(T)] if T else [])
            started = time.time()
            r = subprocess.run(cmd, capture_output=True, text=True)
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
                wall=round(time.time() - started), remaining=agyrun.remaining())
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
