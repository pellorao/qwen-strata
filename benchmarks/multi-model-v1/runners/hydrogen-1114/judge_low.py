#!/usr/bin/env python3
"""Hydrogen low (common/hydroeffort): a copy of judge.py on its own base dir .tmp/hydrolow (records from low_records.py). Hydrogen supplement: enumerate, blind-adjudicate, score (plan.md §6-§7). Python 3 stdlib; run with -I.

Every ARW materialization (14 MB per instance) goes to a RAM-backed root (SHM, /dev/shm: no SSD writes) and is deleted
as soon as the step ends; only the small result files (candidates.json, decisions.json, score.json, ...) are kept on
disk under SCORE. At most one instance is materialized at a time (peak ~15 MB under SHM).

  judge.py enumerate [--limit N]       bench_score --enumerate per valid record -> SCORE/<id>/candidates.json
  judge.py score [--provisional lower|upper] [--limit N]   bench_score per valid record -> SCORE/<id>/score.json
  judge.py build [--registry DIR]      views (RAM root) + blind pools of the four scenarios -> ADJ/<pool>/, KEYS/key-<pool>.json
  judge.py judge [--pools P ...] [--parallel N]   Opus high adjudication of every pool without decisions, then split
All steps resume: a record whose result file exists is skipped.

Hydrogen is a new report family: the frozen tools know three. The families are extended in this process only
(bench_records.MODELS, blind_pool.FAMILIES); no frozen file is edited.
"""
import argparse
import concurrent.futures
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
BASE = ROOT / '.tmp/hydrolow'
RECORDS = BASE / 'records.jsonl'
SCORE = BASE / 'score'
SHM = Path('/dev/shm/hydrolow-score')
LOG = BASE / 'judge.log'
ADJ = ROOT / '.tmp/pools'   # neutral path: the adjudicator sees it in the prompt, so it must not name the run
KEYS = BASE / 'keys'
JUDGE = BASE / 'judge'   # streams and results of the adjudication calls
CALLS = BASE / 'judge-calls.jsonl'
EXPECT = BASE / 'judge-expect.json'   # {"pools": n, "expected_calls": n, "cap": 2n}
SCENARIOS = {'ca': 'commit-audit-v3', 'cs': 'code-spec-v5', 'cstd': 'code-standards-v5.1', 'sr': 'spec-readiness-v4.3'}
OPUS = ['--model', 'claude-opus-5-5', '--effort', 'high']   # frozen judge: Opus high, isolated from user config
GUARD = os.path.expanduser('~/.claude/bin/claude-guard')
USAGE = os.path.expanduser('~/.claude/statusline/usage.sh')
LABEL = 'common/hydroeffort:judge'
POOL_USD, POOL_MIN = 3.0, 30   # expectation per pool call; claude-guard stops a call at 2x
SMALL = ('candidates.json', 'pending.json', 'score.json', 'decisions.json', 'score-input.json')  # kept on disk


def log(msg):
    line = f"{time.strftime('%F %T')} {msg}"
    print(line, flush=True)
    with open(LOG, 'a') as f:
        f.write(line + '\n')


def records():
    return [json.loads(l) for l in RECORDS.read_text().splitlines() if l.strip()]


def valid_records():
    return [r for r in records() if r['valid']]


def du(path):
    return sum(p.stat().st_size for p in Path(path).rglob('*') if p.is_file()) if Path(path).exists() else 0


def run_bench_score(rec_id, mode):
    cmd = [sys.executable, '-m', 'tools.reviewer.bench_score', '--id', rec_id, '--records', str(RECORDS), '--root', str(SHM)]
    if mode:
        cmd.extend(mode)
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def step(mode, result_name, limit=None, stage=None):
    """mode: argv list, e.g. ['--enumerate'], [], ['--provisional', 'lower']."""
    done = 0
    for rec in valid_records():
        keep = SCORE / rec['id']
        if (keep / result_name).is_file():
            continue
        if limit is not None and done >= limit:
            break
        work = SHM / rec['id']
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(parents=True)
        for name in SMALL:   # decisions of the blind pools go back under the RAM root for the scorer
            if (keep / name).is_file() and name in ('decisions.json',):
                shutil.copy2(keep / name, work / name)
        t = time.time()
        res = run_bench_score(rec['id'], mode)
        peak = du(SHM)
        keep.mkdir(parents=True, exist_ok=True)
        for name in SMALL:
            if (work / name).is_file():
                shutil.copy2(work / name, keep / name)
        shutil.rmtree(work)
        if res.returncode != 0 or not (keep / result_name).is_file():
            log(f"FAIL {rec['id']} {mode} rc={res.returncode} {res.stderr[-600:]}")
            sys.exit(2)
        log(f"ok {rec['id']} {mode or 'score'} {time.time() - t:.0f}s peak_shm={peak / 1e6:.1f}MB {res.stdout.splitlines()[0][:160]}")
        done += 1
    log(f'{result_name}: {done} new, {sum((SCORE / r["id"] / result_name).is_file() for r in valid_records())}/{len(valid_records())} present')


# ---- blind pools -----------------------------------------------------------------------------------------------------

def tools():
    sys.path.insert(0, str(ROOT))
    from tools.reviewer import bench_records, blind_pool, adjudication_view
    bench_records.MODELS['hydrogen'] = (30, 'hydrogen', 'hydrogen')
    bench_records.EXTRA_CONFIGS[('hydrogen', 'low')] = 36   # low_records.LOW_CONFIG
    blind_pool.FAMILIES = (*blind_pool.FAMILIES, 'hydrogen')
    return blind_pool, adjudication_view


def build(registry=None, suffix='', only=None):
    """suffix / only: a second round after reruns (user 2026-11-15): pools named <scenario><suffix> for the scenarios in `only`, holding just the candidates not decided yet (the stored decisions of the first round are kept)."""
    blind_pool, adjudication_view = tools()
    for key, scenario in SCENARIOS.items():
        if only and key not in only:
            continue
        name = key + suffix
        files = sorted(SCORE.glob(f'antigravity/{scenario}/*/candidates.json'))
        files = [f for f in files if f.parent.name in {Path(r['id']).name for r in valid_records() if r['scenario'] == scenario}]
        if any(re.fullmatch(re.escape(name) + r'(?:-\d+)?', p.stem[4:]) for p in KEYS.glob('key-*.json')):
            log(f'{name}: pools exist, skipped')
            continue
        written = blind_pool.build(scenario, name, ADJ, KEYS, files, registry=registry, root=SCORE)
        plan = json.loads(Path(next(r for r in valid_records() if r['scenario'] == scenario)['plan']).read_text())
        manifest = ROOT / plan['fixed_conditions']['arw_source_manifest']
        work, out = SHM / f'view-{key}', SHM / f'viewout-{key}'
        for d in (work, out):
            shutil.rmtree(d, ignore_errors=True)
        adjudication_view.build(manifest, plan['reviewer'], work, out)
        for w in written:
            for v in blind_pool.views(scenario):   # 'view' directories and, for the code scenarios, change.diff
                if (out / v).is_dir():
                    shutil.copytree(out / v, Path(w['adj']) / v, symlinks=True)
                else:
                    shutil.copy2(out / v, Path(w['adj']) / v)
        (BASE / f'view-binding-{name}.json').write_bytes((out / 'view-binding.json').read_bytes())
        shutil.rmtree(work)
        shutil.rmtree(out)
        for w in written:
            blind_pool.prompt(w['key'])
            log(f"pool {w['pool']}: {w['items']} items ({w['real']} real, {w['controls']} controls) already_decided_skipped={w['already_decided_skipped']}")
    pools = sorted(p.stem[4:] for p in KEYS.glob('key-*.json'))
    EXPECT.write_text(json.dumps({'pools': len(pools), 'expected_calls': len(pools), 'cap': 2 * len(pools), 'names': pools}, indent=1))
    log(f'{len(pools)} pools; expected judge calls {len(pools)}, cap {2 * len(pools)}')


def reserve_call(pool):
    """Atomically reserve a call across threads and concurrent runner processes."""
    cap = json.loads(EXPECT.read_text())['cap']
    with open(CALLS, 'a+') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        count = sum(1 for _ in f)
        if count >= cap:
            raise RuntimeError(f'STOP: {count} judge calls reached the cap {cap}; check the cause before more (usage watch)')
        n = count + 1
        f.write(json.dumps({'pool': pool, 'n': n, 'at': time.strftime('%F %T')}) + '\n')
        f.flush()
    return n


def judge_one(pool):
    blind_pool, _ = tools()
    keypath = KEYS / f'key-{pool}.json'
    key = json.loads(keypath.read_text())
    adj = Path(key['pool_path']).parent
    dec = adj / f'decisions-{pool}.json'
    JUDGE.mkdir(parents=True, exist_ok=True)
    n = reserve_call(pool)
    stream = JUDGE / f'{pool}-{n}.jsonl'
    env = {k: v for k, v in os.environ.items() if k not in ('ANTHROPIC_API_KEY', 'ANTHROPIC_BASE_URL', 'ANTHROPIC_AUTH_TOKEN')}
    t = time.time()
    cmd = [GUARD, '--label', f'{LABEL}:{pool}', '--max-usd', str(POOL_USD), '--max-min', str(POOL_MIN), '--',
           '-p', *OPUS, '--setting-sources', '', '--permission-mode', 'dontAsk', '--allowedTools', 'Read,Write,Grep,Glob,Bash',
           '--output-format', 'stream-json', '--verbose']
    with open(KEYS / f'prompt-{pool}.md') as pin, open(stream, 'w') as out:
        rc = subprocess.call(cmd, cwd=adj, stdin=pin, stdout=out, stderr=subprocess.STDOUT, env=env)
    subprocess.call([USAGE, '--add-stream', str(stream), 'common/hydroeffort:judge', '--effort', 'high'], stdout=subprocess.DEVNULL)
    final = ''
    with open(stream) as events:
        for line in events:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get('type') == 'result':
                final = ev.get('result') or ''
                cost = ev.get('total_cost_usd')
    log(f'{pool}: judge call {n} rc={rc} {time.time() - t:.0f}s cost={locals().get("cost")} decisions={dec.is_file()}')
    if not dec.is_file():
        return {'pool': pool, 'ok': False, 'why': f'no decisions file (rc {rc})'}
    hard = sorted(set(re.findall(rf'\b{re.escape(pool)}-\d{{3}}\b', final)))
    verdict, review, out = blind_pool.split(keypath, dec, root=SCORE, hard=hard)
    shutil.copy2(dec, JUDGE / f'decisions-{pool}.json')
    log(f"{pool}: passed={verdict['passed']} anchors={verdict['anchors']} rate={verdict['anchor_rate']} synthetic_ok={verdict['synthetic_all_right']} "
        f"counts={verdict['decision_counts']} review={verdict['review']}")
    return {'pool': pool, 'ok': verdict['passed'], 'verdict': verdict}


def judge(pools=None, parallel=3):
    pools = pools or json.loads(EXPECT.read_text())['names']
    todo = [p for p in pools if not (JUDGE / f'split-{p}.ok').is_file()]
    log(f'judge: {len(todo)} pools to do, parallel {parallel}')
    JUDGE.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(parallel) as ex:
        futures = {ex.submit(judge_one, p): p for p in todo}
        for future in concurrent.futures.as_completed(futures):
            pool = futures[future]
            try:
                res = future.result()
            except Exception as exc:
                log(f'{pool}: ERROR {type(exc).__name__}: {exc}; no success marker, retry after checking the cause')
                continue
            if res['ok']:
                (JUDGE / f"split-{res['pool']}.ok").write_text('passed\n')
            else:
                # a failed pool is adjudicated again whole (plan 6.2): drop its decisions file and let the next run redo it
                key = json.loads((KEYS / f"key-{res['pool']}.json").read_text())
                (Path(key['pool_path']).parent / f"decisions-{res['pool']}.json").unlink(missing_ok=True)
                log(f"{res['pool']}: NOT passed ({res.get('why') or 'controls failed'}); rerun the whole pool")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['enumerate', 'score', 'build', 'judge'])
    ap.add_argument('--registry', type=Path)
    ap.add_argument('--suffix', default='', help='build: pool name suffix of a later round')
    ap.add_argument('--scenarios', nargs='*', help='build: only these scenario keys (ca cs cstd sr)')
    ap.add_argument('--pools', nargs='*')
    ap.add_argument('--parallel', type=int, default=3)
    ap.add_argument('--provisional', choices=['lower', 'upper'])
    ap.add_argument('--limit', type=int)
    a = ap.parse_args()
    SHM.mkdir(parents=True, exist_ok=True)
    SCORE.mkdir(parents=True, exist_ok=True)
    if a.cmd == 'build':
        build(a.registry, a.suffix, a.scenarios)
    elif a.cmd == 'judge':
        judge(a.pools, a.parallel)
    elif a.cmd == 'enumerate':
        step(['--enumerate'], 'candidates.json', a.limit)
    else:
        step(['--provisional', a.provisional] if a.provisional else [], 'score.json', a.limit)


if __name__ == '__main__':
    main()
