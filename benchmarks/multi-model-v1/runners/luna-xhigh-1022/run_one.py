"""One OpenAI-arm instance (benchmark plan #1-6): ARW zero-model prepare -> arw_measure (API provider, ChatGPT login,
shared CODEX_HOME) on the first handoff(s) -> checks -> session inspection extract.

    python3 .tmp/luna-xhigh-1022/run/run_one.py <scenario-plan> <out> <model> <effort> --codex-home H [--handoffs 1]
        [--time-limit-seconds T]

luna xhigh / max supplement (user 2026-10-22): the v1 OpenAI-arm run_one (c70c8a5e) with the post-run SR repository
lookup (scenario_repositories), plus the efforts xhigh and max. TMP_PREP stays the v1 base so prep paths keep their shape.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path('/home/pello/projects/qwen_strata')
sys.path.insert(0, str(ROOT))
from tools.tuning.arw_dimension import prepare  # noqa: E402
from tools.reviewer.bench_records import scenario_repositories, report_directories  # noqa: E402

CATALOG = ROOT / 'benchmarks/multi-model-v1/catalogs/openai-codex-0.163.0.json'
AUTH_HOME = '/home/pello/.codex'
GUARDIAN = 'codex-auto-review'
TMP_PREP = Path('/tmp/qwen-openai-1020')
# Codex 0.163 leaves empty synthetic mount targets in the report directory (stubtest2); Main 2026-10-20, option A.
HARNESS_PATCHES = ('codex-0.163-synthetic-mount-targets',)
HARNESS_REASONS = ('report directory must contain only its exact bound report',)
TIERS_OK = {'default', 'standard', 'not-returned'}


def model_match(returned, bound):
    return returned == bound or re.fullmatch(re.escape(bound) + r'-(\d{4}-\d{2}-\d{2}|\d{8})', returned or '') is not None


NESTED = re.compile(r'tools\.([A-Za-z_][\w]*)\s*\(')


def rollout_facts(path):
    """Tool and limit facts of one rollout. Code-mode counts (§14.3, M6/R4): exec calls, the CommandExecution and
    FileChange items Codex actually ran inside them, and the nested tool names the exec sources call."""
    calls, searches, rate, compactions, execs, commands, changes, errors = 0, 0, None, 0, 0, 0, 0, []
    nested = {}
    for line in Path(path).read_text().splitlines():
        e = json.loads(line)
        p = e.get('payload', {})
        if e.get('type') == 'response_item' and p.get('type') in ('function_call', 'custom_tool_call', 'web_search_call', 'tool_search_call'):
            calls += 1
            searches += p.get('type') == 'web_search_call'
            if p.get('type') == 'custom_tool_call' and p.get('name') == 'exec':
                execs += 1
                for name in NESTED.findall(p.get('input') or ''):
                    nested[name] = nested.get(name, 0) + 1
        if e.get('type') == 'event_msg' and p.get('type') == 'token_count' and p.get('rate_limits'):
            rate = p['rate_limits']
        if e.get('type') == 'event_msg' and p.get('type') == 'item_completed':
            kind = (p.get('item') or {}).get('type')
            commands += kind == 'CommandExecution'
            changes += kind == 'FileChange'
        if e.get('type') == 'event_msg' and p.get('type') in ('error', 'stream_error'):
            errors.append({k: p.get(k) for k in ('type', 'message', 'codex_error_info')})
        if e.get('type') == 'compacted':
            compactions += 1
    return {'tool_calls': calls, 'web_search_calls': searches, 'last_rate_limits': rate, 'compactions': compactions,
            'exec_calls': execs, 'command_executions': commands, 'file_changes': changes, 'nested_tools': nested,
            'errors': errors}


def limit_hit(relay_rows, facts):
    """Quota / rate limit by status code or error type field, never by a substring of a log (M2)."""
    if any(r.get('status') == 429 for r in relay_rows):
        return True
    words = ('usage_limit', 'rate_limit', 'quota')
    return any(any(w in json.dumps(err.get('codex_error_info') or '').lower() for w in words)
               for f in facts.values() for err in f['errors'])


def checks(record, model, relay_rows):
    tiers = (record.get('service_tier_returned') or {})
    models = tiers.get('models') or {}
    bad_models = [m for m in models if not (model_match(m, model) or model_match(m, GUARDIAN))]
    histories = (record.get('cost') or {}).get('histories') or []
    facts = {h['thread_id']: rollout_facts(h['path']) for h in histories}
    out = {
        # Plan §14 / Main 2026-10-20: a run counts when the runtime ended normally with a completion record; the
        # model's own status (ready, incomplete, ...) is a scored outcome, not a reason to rerun.
        'complete': bool(record.get('complete')),
        'completion_status': ((record.get('runtime_result') or {}).get('completion') or {}).get('status'),
        # Same test arw_measure uses to accept a finished Reviewer: a completion and a state past starting/running/
        # working (a finished ARW Reviewer is 'idle'; the earlier 'exited' test never matched, 2026-10-20 07:52).
        'ended_normally': bool((record.get('runtime_result') or {}).get('completion'))
                          and (record.get('runtime_result') or {}).get('state') not in (None, 'starting', 'running', 'working'),
        'completion_reason': ((record.get('runtime_result') or {}).get('completion') or {}).get('reason'),
        'service_tiers': tiers.get('service_tiers'),
        'tier_ok': set((tiers.get('service_tiers') or {'not-returned': 1})) <= TIERS_OK,
        'models_returned': models, 'model_ok': not bad_models and any(model_match(m, model) for m in models),
        'relay_errors': tiers.get('errors'), 'websocket_refused': tiers.get('websocket_refused'),
        'web_search_calls': sum(f['web_search_calls'] for f in facts.values()),
        'startup_off': (record.get('startup_instructions') or {}).get('enabled') is False,
        'tokens_known': record.get('token_consumption') is not None,
        'arw_pause': bool(record.get('arw_pause')), 'user_pause': bool(record.get('user_pause')),
    }
    out['limited'] = limit_hit(relay_rows, facts)
    # ARW's own report binding rejection is a harness failure even though it arrives as an incomplete completion.
    out['harness_rejected'] = any(t in (out['completion_reason'] or '') for t in HARNESS_REASONS)
    out['valid'] = (out['ended_normally'] and not out['harness_rejected'] and out['tier_ok'] and out['model_ok'] and out['web_search_calls'] == 0
                    and out['startup_off'] and not out['arw_pause'] and not out['relay_errors'] and not out['limited'])
    return out, facts


MOUNT_TARGETS = ('.git', '.codex', '.agents', '.aws')
BINDING = 'report directory must contain only its exact bound report'


def descendants(pids):
    rows = [line.split() for line in subprocess.run(['ps', '-eo', 'pid=,ppid=,comm='], capture_output=True, text=True).stdout.splitlines()]
    children, names, found, todo = {}, {}, [], list(pids)
    for row in rows:
        if len(row) >= 3:
            children.setdefault(int(row[1]), []).append(int(row[0])); names[int(row[0])] = row[2]
    while todo:
        pid = todo.pop()
        for child in children.get(pid, []):
            found.append(child); todo.append(child)
    return [{'pid': p, 'comm': names.get(p)} for p in found]


def ancestors():
    pid, seen = os.getpid(), set()
    while pid > 1:
        seen.add(pid)
        pid = int(Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[1])
    return seen


def pgrep(pattern):
    mine = ancestors()
    return [int(x) for x in subprocess.run(['pgrep', '-f', pattern], capture_output=True, text=True).stdout.split()
            if int(x) not in mine]


def ere(path):
    """A path as a literal for pgrep's extended regular expression."""
    return re.sub(r'([.\[\](){}*+?^$|\\])', r'\\\1', str(path))


def live(pid):
    try:
        return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0] != 'Z'
    except OSError:
        return False


def end_leftovers(out, prep):
    """End leftover ARW daemons of this instance with their whole process tree; report what was left after."""
    daemons = pgrep(f'arw_runtime.mjs daemon {out}/run/')
    tree = descendants(daemons)
    pids = daemons + [t['pid'] for t in tree]
    for sig in ('TERM', 'KILL'):
        for pid in pids:
            subprocess.run(['kill', f'-{sig}', str(pid)], capture_output=True)
        if sig == 'TERM' and pids:
            time.sleep(5)
    alive = [p for p in pids if live(p)]
    # Any process still naming this instance's own run or prep directory (codex app-server, bwrap, code-mode host),
    # e.g. a bwrap fs-helper reparented to /init outside the daemon tree (CS sol-high-a5). The run path ends in /run/
    # and the prep path carries a time_ns suffix, so neither matches another instance.
    pattern = f'{ere(out)}/run/|{ere(prep)}'
    named_killed = [p for p in pgrep(pattern) if live(p)]
    for sig in ('TERM', 'KILL'):
        for pid in [p for p in named_killed if live(p)]:
            subprocess.run(['kill', f'-{sig}', str(pid)], capture_output=True)
        if sig == 'TERM' and named_killed:
            time.sleep(5)
    named = [p for p in pgrep(pattern) if live(p)]
    return {'daemons': daemons, 'descendants': tree, 'alive_after': alive, 'named_killed': named_killed,
            'still_named_after': named, 'clean': not alive and not named}


def classify(instance, results, out, prep, handoffs, rc):
    """Patch review M1: with the mount-target patch an impure report directory or a crash without completion is no
    longer an expected harness fault. A report directory holding a name outside the four mount targets is the model's
    result and is scored; any other binding rejection, a crash without completion, a non-empty mount target in the
    copy, or a dirty cleanup halts the schedule for Main."""
    halt, violation = [], False
    if instance.get('s2_paused'):
        instance['halt'], instance['report_dir_model_violation'], instance['valid'] = None, None, False
        return
    log = (out / 'arw_measure.log').read_text() if (out / 'arw_measure.log').exists() else ''
    rejected = BINDING in log or any(BINDING in (h['checks'].get('completion_reason') or '') for h in instance['handoffs'])
    if rejected:
        extras = sorted({n for names in instance['report_directories'].values() for n in names
                         if n != 'review.jsonl' and n not in MOUNT_TARGETS})
        if extras and results and all(h['checks']['ended_normally'] for h in instance['handoffs']):
            violation = extras
        else:
            halt.append(f'report binding rejected under the patch (extras outside the mount targets: {extras})')
    # A quota or rate limit stops the whole schedule anyway and voids the instance (S6); it is not a halt.
    if not instance['limited'] and (instance['recovery_required'] or not all(h['checks']['ended_normally'] for h in instance['handoffs'])):
        halt.append(f"recovery-required: {instance['recovery_required']}; handoffs ended without a completion: "
                    f"{[h['instanceId'] for h in instance['handoffs'] if not h['checks']['ended_normally']]}")
    if not instance['limited'] and len(results) != handoffs:
        halt.append(f'{len(results)} result records for {handoffs} handoff(s)')
    for d in report_directories(scenario_repositories(out / 'prep')):
        for name in MOUNT_TARGETS:
            target = d / name
            if target.is_symlink() or (target.is_dir() and any(target.iterdir())):
                halt.append(f'non-empty or linked mount target in the copy: {target}')
    if not instance['leftover_cleanup']['clean']:
        halt.append('leftover processes after cleanup')
    if not (out / 'prep/harness-patches.json').exists():
        halt.append('harness-patches.json missing')
    instance['report_dir_model_violation'] = violation or None
    if violation:  # scored as the model's result: the binding failure was the model's own extra entry
        instance['valid'] = (rc == 0 and instance['prep_copy_ok'] and all(
            h['checks']['ended_normally'] and h['checks']['tier_ok'] and h['checks']['model_ok']
            and h['checks']['web_search_calls'] == 0 and h['checks']['startup_off'] and not h['checks']['arw_pause']
            and not h['checks']['relay_errors'] and not h['checks']['limited'] for h in instance['handoffs']))
    instance['halt'] = halt or None
    if halt:
        instance['valid'] = False


STOP_CELLS = Path(__file__).parent / 'stop-cells.txt'  # set per scenario in main()
ARW_PAUSE_PREFIX = 'The Reviewer runtime paused this same task after '


def message_text(payload):
    return ''.join(c.get('text', '') for c in payload.get('content', []))


def s2_record(instance, out, codex_home, cell):
    log_text = (out / 'arw_measure.log').read_text() if (out / 'arw_measure.log').exists() else ''
    # Since the user's decision of 2026-10-20 arw_measure answers every pause "continue"; only a pause whose answer
    # ARW refused still stops for the user.
    if 'ARW paused the Reviewer task' in log_text or any(
            json.loads(f.read_text()).get('arw_pause') for f in sorted((out / 'run').glob('*/result.json'))):
        paused = [json.loads(f.read_text()) for f in sorted((out / 'run').glob('*/result.json'))]
        paused = [r for r in paused if r.get('arw_pause')]
        rr = (paused[0].get('runtime_result') or {}) if paused else {}
        thread = rr.get('threadId')
        roll = sorted(Path(codex_home, 'sessions').glob(f'*/*/*/rollout-*{thread}.jsonl')) if thread else []
        says = [message_text(e['payload']) for line in (roll[0].read_text().splitlines() if roll else [])
                for e in [json.loads(line)] if e.get('type') == 'response_item' and e['payload'].get('type') == 'message'
                and e['payload'].get('role') == 'assistant']
        instance.update(s2_paused=True, arw_pause=True, scoring='decided by the user (S2): neither scored nor voided',
                        pause_notification=paused[0]['arw_pause'] if paused else None, last_self_report=says[-1] if says else None,
                        runtime_state={k: rr.get(k) for k in ('state', 'taskState', 'completion', 'turnId')},
                        thread_id=thread, rollout=str(roll[0]) if roll else None)
        if cell not in stopped_cells():
            with STOP_CELLS.open('a') as f:
                f.write(cell + '\n')


def recovered_transport_error(rows):
    """True when the relay saw transport errors and every one was followed by a completed 200 reply (the harness
    retried by itself); None without any. Recorded only: plan L494 (M2) still voids the instance (Main 2026-10-20)."""
    bad = [r for r in rows if r.get('transport_error')]
    if not bad:
        return None
    return all(any(o.get('status') == 200 and o.get('response_status') == 'completed' and o['started_at'] > b['ended_at']
                   for o in rows) for b in bad)


def stopped_cells():
    return set(STOP_CELLS.read_text().split()) if STOP_CELLS.exists() else set()


def watch(proc, out, cell):
    """Wait for arw_measure. Each ARW early-exit pause is answered "continue" inside arw_measure (user 2026-10-20);
    for the operator, ARW_PAUSE_SEEN lists when a new pause text was first seen in the machine log (no cell stops)."""
    machine = out / 'run/machine.jsonl'
    seen = set()
    while proc.poll() is None:
        time.sleep(15)
        if not machine.exists():
            continue
        with machine.open('rb') as f:
            f.seek(max(0, machine.stat().st_size - 65536))
            tail = f.read().decode(errors='replace')
        for text in set(re.findall(re.escape(ARW_PAUSE_PREFIX) + r'(\d+) normally', tail)) - seen:
            seen.add(text)
            with (out / 'ARW_PAUSE_SEEN').open('a') as f:
                f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} after {text} turns\n")
    return proc.returncode


def tree_manifest(root):
    """sha256 of every file below root (symlinks by target), relative paths sorted."""
    out = {}
    for f in sorted(root.rglob('*')):
        rel = str(f.relative_to(root))
        if f.is_symlink():
            out[rel] = 'link:' + os.readlink(f)
        elif f.is_file():
            out[rel] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def clean_instance(out, prep, instance):
    """User rule 2026-10-20 (measurement.md, storage): once the instance is checked, delete its leftovers and keep the
    answers and records. Deleted: the /tmp prep (only after the verified copy), the ARW checkout in the copy, every
    scenario repository copy except its .tmp (bound reports and ARW drafts) and the empty mount-target placeholders.
    Kept: reports, ARW run metadata, run/ (machine.jsonl, logs, state), inspect/, instance.json. The rollout lives in
    the shared CODEX_HOME. A manifest of each deleted repository copy is written first (scenario-copies.json) so a
    re-materialized copy can be compared at scoring."""
    done = {'deleted': [], 'skipped': None}
    if not instance.get('prep_copy_ok') or any('error' in (h.get('inspect') or {'error': 1}) for h in instance['handoffs']):
        done['skipped'] = 'prep copy or session inspection not complete; nothing deleted'
        return done
    copy = out / 'prep'
    repos = scenario_repositories(copy)
    manifest = {str(d.relative_to(copy)): tree_manifest(d) for d in repos}
    (out / 'scenario-copies.json').write_text(json.dumps(manifest, indent=1) + '\n')
    for d in repos:
        for x in d.iterdir():
            if x.name != '.tmp':
                shutil.rmtree(x) if x.is_dir() and not x.is_symlink() else x.unlink()
                done['deleted'].append(str(x))
    for r in report_directories(repos):
        for name in MOUNT_TARGETS:
            t = r / name
            if t.is_dir() and not t.is_symlink() and not any(t.iterdir()):
                t.rmdir()
                done['deleted'].append(str(t))
    for x in (copy / 'arw').iterdir():
        if x.name != '.tmp':
            shutil.rmtree(x) if x.is_dir() and not x.is_symlink() else x.unlink()
            done['deleted'].append(str(x))
    tmp = prep.parent
    if tmp.parent.parent == TMP_PREP and tmp.exists():
        shutil.rmtree(tmp)
        done['deleted'].append(str(tmp))
    done['count'] = len(done['deleted'])
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('plan', type=Path)
    ap.add_argument('out', type=Path)
    ap.add_argument('model')
    ap.add_argument('effort', choices=('low', 'medium', 'high', 'xhigh', 'max'))
    ap.add_argument('--codex-home', type=Path, required=True)
    ap.add_argument('--handoffs', type=int, default=1)
    ap.add_argument('--time-limit-seconds', type=int)
    ap.add_argument('--borrow', type=int, default=1)
    ap.add_argument('--round', type=int)
    a = ap.parse_args()
    out = a.out.resolve()
    out.mkdir(parents=True)
    plan = json.loads(a.plan.read_text())
    started = time.time()
    cell = ('sol' if 'sol' in a.model else 'luna') + '-' + a.effort
    global STOP_CELLS
    STOP_CELLS = Path(__file__).parent / f'stop-cells-{out.parent.name}.txt'
    if cell in stopped_cells():
        # Plan S2: a cell that reached ARW's early-exit pause stops; the scheduler sees arw_pause and stops the cell.
        (out / 'instance.json').write_text(json.dumps({
            'model': a.model, 'effort': a.effort, 'started': started, 'ended': time.time(), 'handoffs': [],
            'refused': f'cell {cell} stopped (S2 ARW pause), see {STOP_CELLS.name}', 'arw_pause': True,
            'limited': False, 'valid': False, 'halt': None, 'mount_targets_ignored': {'count': 0, 'paths': []}}, indent=1) + '\n')
        print(json.dumps({'valid': False, 'refused': cell}))
        return
    # The prepared ARW checkout lives under /tmp (base made by hand, 0700, covered by the Claude Code arms' denyRead;
    # never created here). /tmp did not stop Codex 0.163.0's empty mount targets; the harness patch handles them.
    st = TMP_PREP.lstat() if TMP_PREP.exists() or TMP_PREP.is_symlink() else None
    if st is None or not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o700:
        raise SystemExit(f'{TMP_PREP} must already exist as a 0700 directory of this user; refusing to run')
    prep = TMP_PREP / out.parent.name / f'{out.name}-{time.time_ns()}' / 'prep'
    prepare(plan, None, prep, time_limit_seconds=a.time_limit_seconds, harness_patches=HARNESS_PATCHES)
    location = {'prep': str(prep), 'base': str(TMP_PREP), 'base_inode': st.st_ino, 'base_mtime': st.st_mtime}
    (out / 'prep-location.json').write_text(json.dumps(location, indent=1) + '\n')
    source = json.loads((prep / 'selection-source.json').read_text())
    selection = {'provider': {'id': 'openai', 'auth': 'chatgpt', 'auth_home': AUTH_HOME},
                 'model': a.model, 'effort': a.effort, 'service_tier': 'default', 'web_search': 'disabled',
                 'startup_instructions': False, 'project_compaction_instructions': False,
                 'generation_policy': 'first-delivery-only',
                 'native_cli': source['native_cli'], 'measurement_note': source['measurement_note']}
    for key in ('measurement_note_template', 'review_time_limit_seconds'):
        if key in source:
            selection[key] = source[key]
    (out / 'selection.json').write_text(json.dumps(selection, indent=1) + '\n')
    with (out / 'arw_measure.log').open('w') as log:
        proc = subprocess.Popen([sys.executable, '-m', 'tools.reviewer.arw_measure', '--out', str(out / 'run'),
                             '--selection', str(out / 'selection.json'), '--preparation', str(prep / 'preparation.json'),
                             '--catalog', str(CATALOG), '--limit', str(a.handoffs), '--codex-home', str(a.codex_home)],
                            cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                            env=dict(os.environ, CODEX_THREAD_ID=plan['codex_thread_id']))  # ARW main session identity
        rc = watch(proc, out, cell)
    # arw_measure can exit on an ARW error and leave its runtime daemon behind (seen 2026-10-20); end the daemon's
    # whole process tree, then confirm none of it (codex, bwrap, node) is left (patch review M2).
    cleanup = end_leftovers(out, prep)
    instance = {'borrow': a.borrow, 'round': a.round, 'time_limit_seconds': a.time_limit_seconds, 'leftover_cleanup': cleanup, 'model': a.model, 'effort': a.effort, 'plan': str(a.plan), 'started': started, 'ended': time.time(),
                'arw_measure_exit': rc, 'recovery_required': (out / 'run/recovery-required.json').exists(), 'handoffs': []}
    results = json.loads((out / 'run/results.json').read_text()) if (out / 'run/results.json').exists() else []
    relay_rows = [json.loads(line) for f in sorted((out / 'run/relay').glob('*.jsonl')) for line in f.read_text().splitlines()]
    instance['limited'] = any(r.get('status') == 429 for r in relay_rows)
    for record in results:
        c, facts = checks(record, a.model, relay_rows)
        root = record['runtime_result']['threadId']
        root_path = next((h['path'] for h in record['cost']['histories'] if h['thread_id'] == root), None)
        meas = record.get('measurement') or {}
        h = {'instanceId': record['instanceId'], 'thread_id': root, 'session': root_path, 'checks': c,
             'tokens': record.get('token_consumption'), 'measurement_wall_ms': meas.get('wallClockMs'),
             'reviewer_active_seconds': record['cost'].get('reviewer_active_seconds'),
             'tool_calls': sum(f['tool_calls'] for t, f in facts.items() if t == root),
             'guardian_threads': record['cost'].get('guardian_thread_count'),
             'rate_limits_last': (facts.get(root) or {}).get('last_rate_limits'),
             'compactions': (facts.get(root) or {}).get('compactions'),
             'code_mode': {k: (facts.get(root) or {}).get(k) for k in ('exec_calls', 'command_executions', 'file_changes', 'nested_tools', 'errors')},
             'report': record.get('report'), 'report_sha256': record.get('report_sha256'),
             # User 2026-10-20: every ARW early-exit pause is answered "continue" and counts as one violation (x0.9 at scoring).
             'continue_count': record.get('continue_count', 0), 'arw_pause_events': record.get('arw_pause_events', [])}
        if root_path:
            p = subprocess.run([sys.executable, '-m', 'tools.reviewer.inspect_session', '--session', root_path,
                                '--out', str(out / 'inspect' / record['instanceId'])], cwd=ROOT, capture_output=True, text=True)
            h['inspect'] = json.loads(p.stdout.strip().splitlines()[-1]) if p.returncode == 0 and p.stdout.strip() else {'error': p.stderr[-500:]}
            summary = out / 'inspect' / record['instanceId'] / 'summary.json'
            h['startup'] = json.loads(summary.read_text()).get('startup') if summary.exists() else None
        instance['handoffs'].append(h)
    instance['limited'] = instance['limited'] or any(h['checks']['limited'] for h in instance['handoffs'])
    instance['recovered_transport_error'] = recovered_transport_error(relay_rows)
    # Each ignored mount target is one stderr line of the ARW daemon (harness patch); counted per instance.
    events = [json.loads(line) for f in sorted((out / 'run').glob('*stderr*.log')) for line in f.read_text().splitlines()
              if line.startswith('{"event":"codex-synthetic-mount-target-ignored"')]
    instance['mount_targets_ignored'] = {'count': len(events), 'paths': sorted({e['path'] for e in events})}
    instance['arw_pause'] = any(h['checks']['arw_pause'] for h in instance['handoffs'])
    instance['continue_count'] = sum(h['continue_count'] for h in instance['handoffs'])
    instance['arw_pause_events'] = [dict(e, instanceId=h['instanceId']) for h in instance['handoffs'] for e in h['arw_pause_events']]
    # Plan S2 (Main 2026-10-20): ARW's early-exit pause. arw_measure stops on it, keeps the paused record and leaves
    # the runtime; the cleanup above ends it. The instance is neither scored nor voided (the user decides) and the
    # cell gets no new launches.
    s2_record(instance, out, a.codex_home, cell)
    instance['valid'] = (rc == 0 and not instance['recovery_required'] and len(instance['handoffs']) == a.handoffs
                         and all(h['checks']['valid'] for h in instance['handoffs']))
    # Prep review M1: the whole prep comes back to the project disk after Codex exited; scoring reads only this copy.
    reports = report_directories(scenario_repositories(prep))
    instance['report_directories'] = {str(d): sorted(x.name for x in d.iterdir()) for d in reports}
    shutil.copytree(prep, out / 'prep', symlinks=True)
    copies = {}
    for record in results:
        rep = record.get('report')
        path = rep.get('path') if isinstance(rep, dict) else rep
        if isinstance(path, str) and path.startswith(str(prep)):
            copy = out / 'prep' / Path(path).relative_to(prep)
            got = hashlib.sha256(copy.read_bytes()).hexdigest() if copy.is_file() else None
            copies[record['instanceId']] = {'tmp': path, 'copy': str(copy), 'sha256': got,
                                            'sha_ok': got is not None and got == record.get('report_sha256')}
    location['copied_to'] = str(out / 'prep')
    location['reports'] = copies
    (out / 'prep-location.json').write_text(json.dumps(location, indent=1) + '\n')
    instance['prep_copy_ok'] = all(c['sha_ok'] for c in copies.values()) and len(copies) == len(results)
    instance['valid'] = instance['valid'] and instance['prep_copy_ok']
    classify(instance, results, out, prep, a.handoffs, rc)
    (out / 'instance.json').write_text(json.dumps(instance, indent=1, ensure_ascii=False) + '\n')
    instance['cleanup_after_run'] = clean_instance(out, prep, instance)
    (out / 'instance.json').write_text(json.dumps(instance, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps({'valid': instance['valid'], 'rc': rc}))


if __name__ == '__main__':
    main()
