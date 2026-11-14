"""Sequential driver for the Carbon supplement (plan.md §3 排程): effort-major (high, medium, low), scenarios CA, CS, CStd,
SR, five valid instances per cell, at most 8 attempts per cell (quota hits do not count), stops when the Gemini 5h window has under 3 % left or the weekly window under 10 % (user 2026-11-14: use the quota up, then wait for the next 5 h).
Idempotent: instance directories already holding instance.json are classified, not rerun.

    python3 -I drive.py plan|status|run [--efforts high medium low] [--scenarios ca cs cstd sr] [--n 5] [--max-minutes M] [--max-starts S] [--pace K]
Ledger: .tmp/carbonbench/drive.jsonl (one event per line). A STOP file at .tmp/carbonbench/STOP halts before the next instance.
T for cs / cstd is T_CS (3600 s).
"""
import argparse
import json
import os
import shutil
import subprocess
import tempfile
import sys
import time
from pathlib import Path

ROOT = Path('/home/pello/projects/qwen-strata')
HERE = Path(__file__).resolve().parent
OUT = ROOT / '.tmp/carbonbench'
MIN_REMAIN_5H = 3.0     # stop line: remaining percent of the 5h window
MIN_REMAIN_WEEK = 10.0  # stop line: remaining percent of the weekly window (keeps quota for translation etc.)
STOP_NAME = os.environ.get('CARBON_STOP', 'STOP')   # parallel lanes (run5.py) use their own stop file name
MAX_ATTEMPTS = 8
MAX_GEMINI = 3   # most Gemini runs at once across every task (registry entries with harness agy-gemini)
T_CS = 3600   # s: CS / CStd instance limit for Carbon (user 2026-11-15: every scenario at the 3600 s cap of clamp(formula, 900, 3600)); a timed-out instance is void and rerun
SAMPLE = 30  # s between samples of the other registered agy runs (overlap with Hydrogen)
SEARCH_STOP = 0.30  # plan §3: voided for search / sub-agent use over this share of attempts
sys.path.insert(0, str(HERE))
sys.path.insert(0, os.path.expanduser('~/.claude/lib'))
import agyrun  # noqa: E402
import usage_guard as ug  # noqa: E402

LABEL = 'common/carbonbench'
GUARD_LABEL = LABEL + (':' + os.environ['CARBON_LANE'] if os.environ.get('CARBON_LANE') else '')   # one usage-guard ledger per parallel lane (run5.py)
TURNS_PER_START = 2.2   # expected agy turns per instance start (CA/CS/CStd 1 handoff, SR 2; reminder and continuation turns add some)


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


def acquire_slot(effort):
    """Register this instance as a running Gemini (agy-gemini) run once fewer than MAX_GEMINI are registered in all (user 2026-11-15: at most 3 Gemini runs at
    once across every task); waits otherwise. The count and the registration happen under one file lock so parallel lanes cannot both take the last slot.
    None when the stop file appears while waiting."""
    import fcntl
    while True:
        with open(OUT / 'slot.lock', 'w') as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            if sum(1 for r in ug.live_runs() if r.get('harness') == 'agy-gemini') < MAX_GEMINI:
                return ug.register(LABEL, 'agy-gemini', model='Carbon', effort=effort, source='agy-gemini')   # one registration per instance, its real effort
        if (OUT / STOP_NAME).exists():
            return None
        time.sleep(30)


def agy_identity():
    """(real path, size, mtime) of the agy binary: a change between instances means agy updated itself (plan §0: stop)."""
    p = os.path.realpath(agyrun.AGY)
    st = os.stat(p)
    return [p, st.st_size, int(st.st_mtime)]


def run_sampled(cmd):
    """Run one instance and, every SAMPLE s, note the other registered Antigravity runs alive at that moment (Hydrogen's drivers, agy-run.py calls, ...):
    {"<label> <model> <effort>": samples}. The ledger carries it per instance (overlap with Hydrogen in the report)."""
    seen = {}
    with tempfile.TemporaryFile('w+') as out, tempfile.TemporaryFile('w+') as err:
        p = subprocess.Popen(cmd, stdout=out, stderr=err, text=True)
        while True:
            try:
                p.wait(timeout=SAMPLE)
                break
            except subprocess.TimeoutExpired:
                pass
            for rec in ug.live_runs():
                if rec['pid'] != os.getpid() and str(rec.get('harness', '')).startswith('agy-') and rec.get('label') != LABEL:
                    key = f"{rec.get('label')} {rec.get('model')} {rec.get('effort')}"
                    seen[key] = seen.get(key, 0) + 1
        out.seek(0)
        err.seek(0)
        return subprocess.CompletedProcess(cmd, p.returncode, out.read(), err.read()), seen


def safe_remaining():
    try:
        return agyrun.remaining()
    except RuntimeError:
        return None


def pace_wait(seconds):
    """The 'off' window of the interference check: do nothing for `seconds` (the length of the instance just run), ending early on STOP."""
    log(event='pace_off_start', seconds=round(seconds))
    end = time.time() + seconds
    while time.time() < end and not (OUT / STOP_NAME).exists():
        time.sleep(5)
    log(event='pace_off_end')


def cells(efforts, scenarios):
    return [(e, s) for e in efforts for s in scenarios]


def cell_state(effort, key):
    folder = OUT / key
    valid, invalid, void, search, timeout, capped = [], [], [], 0, [], []
    for d in sorted(folder.glob(f'carbon-{effort}-a*')) if folder.is_dir() else []:
        verdict, reasons = classify(d)
        {'valid': valid, 'invalid': invalid, 'void': void, 'timeout': timeout}[verdict].append(d.name)
        if verdict == 'timeout' and (json.loads((d / 'instance.json').read_text()).get('T') or 0) >= T_CS:
            capped.append(d.name)   # timed out even at the cap: stop and report, no more reruns
        search += any('forbidden_tools' in r or 'denied_actions' in r for r in reasons)
    attempts = [int(d.name.rsplit('-a', 1)[1]) for d in (sorted(folder.glob(f'carbon-{effort}-a*')) if folder.is_dir() else [])]
    return {'valid': valid, 'invalid': invalid, 'void': void, 'search_voided': search, 'timeout': timeout, 'timeout_at_cap': capped, 'next_attempt': max(attempts, default=0) + 1,
            'counted_attempts': len(valid) + len(invalid)}


def limit_for(key, effort):
    if key not in ('cs', 'cstd'):
        return None
    return T_CS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=('plan', 'status', 'run'))
    ap.add_argument('--efforts', nargs='+', default=['high', 'medium', 'low'])
    ap.add_argument('--scenarios', nargs='+', default=['ca', 'cs', 'cstd', 'sr'])
    ap.add_argument('--n', type=int, default=5)
    ap.add_argument('--max-minutes', type=float, default=None,
                    help='do not start a new instance after this many minutes (only for a run under the 2 h cap of a Bash background command; CA and SR instances can take up to 1 h per handoff, so the formal run is a setsid nohup driver with no cap)')
    ap.add_argument('--max-starts', type=int, default=None,
                    help='hard cap on instance starts in this invocation (default: 1.3 x the valid instances still missing + 3)')
    ap.add_argument('--pace', type=int, default=0,
                    help='(the run ends after the K-th wait) interference check (Carbon with Hydrogen): after each of the first K instance starts of this invocation, wait as long as that '
                         'instance took before the next start (on / off windows); the ledger events carry t0 / t1')
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
    agy_id = agy_identity()
    agy_sha = __import__('hashlib').sha256(Path(agy_id[0]).read_bytes()).hexdigest()
    log(event='run_start', agy=agy_id, agy_sha256=agy_sha, missing_valid=missing, max_starts=max_starts, expected_turns=int(max_starts * TURNS_PER_START), pace=a.pace)
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
            if rem['5h'] < MIN_REMAIN_5H or rem['\u5468'] < MIN_REMAIN_WEEK:
                log(event='quota_stop', remaining=rem, before=f'{effort}/{key}'); return
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
                r, overlap = run_sampled(cmd)
            finally:
                run.close()
            ended = time.time()
            folder = OUT / key / f'carbon-{effort}-a{attempt}'
            if r.returncode != 0:
                (OUT / key).mkdir(exist_ok=True)
                (OUT / f'fail-{key}-{effort}-a{attempt}.err').write_text(r.stdout[-3000:] + r.stderr[-6000:])
                log(event='run_one_failed', effort=effort, scenario=key, attempt=attempt, rc=r.returncode, tail=r.stderr[-300:],
                    t0=round(started), t1=round(ended), overlap=overlap)
                streak = streak + 1 if last == 'fail' else 1
                last = 'fail'
                if streak >= 3:
                    log(event='stop_three_failures'); return
                if folder.exists() and not (folder / 'instance.json').exists():
                    if any(folder.glob('h*/stream*.jsonl')):   # something was sent: keep the evidence, out of the attempt count
                        (OUT / 'void').mkdir(exist_ok=True)
                        dest = OUT / 'void' / f'{key}-carbon-{effort}-a{attempt}-failed-{time.strftime("%H%M%S")}'
                        shutil.move(str(folder), str(dest))
                        log(event='void_instance', moved_to=str(dest))
                    else:
                        shutil.rmtree(folder)  # prepare failed before anything was sent; the attempt number is reused
                if starts <= a.pace:
                    pace_wait(ended - started)
                    if starts == a.pace:
                        log(event='pace_done'); return
                continue
            verdict, reasons = classify(folder)
            log(event='instance', effort=effort, scenario=key, attempt=attempt, verdict=verdict, reasons=reasons,
                wall=round(ended - started), t0=round(started), t1=round(ended), overlap=overlap, remaining=safe_remaining())
            if starts <= a.pace:
                pace_wait(ended - started)
                if starts == a.pace:
                    log(event='pace_done'); return
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
