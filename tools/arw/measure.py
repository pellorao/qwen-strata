"""A cell of ARW instances on Strata: run until `count` valid instances are saved, with the project's checks around them.

Each instance is one pinned-ARW `run` (tools.arw.run).  After it the small result files are copied to
`<out>/<name>/` (score.json, candidates.json, agent.json, run.json, the report) and the instance directory is removed.
Void instances (`validity.status` void) are kept as `<name>` too, flagged, and do not count; the cell stops when the same
void reason repeats twice (no-completion: three times), as the reviewer-capability Skill says.  The loaded startup prompt is
checked against the project's against /health at the first reading with a model loaded, while the instance runs: a mismatch
stops the instance at once.  The binding is recorded in `<out>/binding.json`.  A cell resumes from an existing
`<out>/records.json`: earlier valid instances count and the new ones are appended.

    python3 -m tools.arw.measure --work DIR --scenario spec-readiness --out OUT --count 3
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import threading

from tools.arw import pin as arw_pin, run as arw_run
from tools import guard_runs

KEEP = ('score.json', 'candidates.json', 'agent.json', 'run.json')
EXPECTED_SECONDS = 3600  # one instance: ARW's model work limit
POLL = 30  # s; /health poll while an instance runs
VOID_STOP = {'no-completion': 3}  # consecutive voids of one reason before stopping; default 2


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def validity(result):
    record = result.get('record') or {}
    return record.get('validity') or {}


def store(instance, target):
    """Copy the files a later scoring needs, then remove the instance directory."""
    target.mkdir(parents=True)
    for name in KEEP:
        if (instance / name).is_file():
            shutil.copyfile(instance / name, target / name)
    run = json.loads((instance / 'run.json').read_text()) if (instance / 'run.json').is_file() else {}
    report = run.get('report')
    if report and Path(report).is_file():
        shutil.copyfile(report, target / ('report' + Path(report).suffix))
    shutil.rmtree(instance, ignore_errors=True)


class StartupWatch(threading.Thread):
    """Poll /health during an instance; the first reading with a model loaded is the startup-prompt binding.
    A mismatch calls `abort` at once, so a stale prompt does not run a whole instance."""

    def __init__(self, expected, read=arw_run.health, abort=None):
        super().__init__(daemon=True)
        self.expected, self.read, self.abort = expected, read, abort
        self.binding, self.stopped = None, threading.Event()

    def run(self):
        while not self.stopped.wait(POLL if self.binding is None else 1e9):
            try:
                binding = arw_run.startup_binding(self.read(), self.expected)
            except OSError:
                continue
            if binding['ok'] is not None:
                self.binding = binding
                if not binding['ok'] and self.abort is not None:
                    self.abort()


def killer(processes):
    """abort callback: stop the process group of the latest instance process.  An abort that arrives before the
    process is registered stays pending; `abort.register` (the instance's `started` callback) then stops it at once."""
    pending = []

    def stop(process):
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except OSError:
            pass

    def abort():
        pending.append(True)
        if processes:
            stop(processes[-1])

    def register(process):
        processes.append(process)
        if pending:
            stop(process)
    abort.register = register
    return abort


def load_records(out):
    path = Path(out) / 'records.json'
    return json.loads(path.read_text()) if path.is_file() else []


def run_cell(work, scenario, out, count, effort=arw_run.EFFORT, first=1, instance=arw_run.run_instance, max_starts=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    expected = arw_run.expected_startup_sha()
    # max_starts: a caller that runs several cells by design (tuning blocks) states its own cap
    guard_runs.rate(f'qwen-strata/arw-cell-{scenario}', max_starts or count * 2 + 2, 6 * 3600)
    session = 'qs-' + arw_run.sha(str(out.resolve()).encode())[:8]  # one session directory per cell
    records = load_records(out)  # resume: earlier instances count and stay in the records
    valid = sum(1 for r in records if r['valid'])
    number = max([first] + [int(r['name'][1:]) + 1 for r in records])
    streak = (None, 0)
    with guard_runs.registered(f'qwen-strata/arw-{scenario}', 'codex', model=arw_run.model_id(), effort=effort):
        while valid < count:
            name = f'a{number}'
            processes = []
            abort = killer(processes)
            watch = StartupWatch(expected, abort=abort)
            watch.start()
            result, path, seconds = instance(work, scenario, name, session=session, effort=effort, started=abort.register)
            watch.stopped.set()
            if watch.binding is not None:
                save(out / 'binding.json', watch.binding)
                if not watch.binding['ok']:
                    raise RuntimeError(f'startup prompt check failed: {watch.binding}')
            status, state = result.get('status'), validity(result)
            reason = None if state.get('valid') else (state.get('notes') or result.get('stage') or status)
            if status == 'succeeded' and path.exists():
                store(path, out / name)
            record = {'name': name, 'status': status, 'valid': bool(state.get('valid')), 'reason': reason,
                      'seconds': round(seconds)}
            records.append(record)
            save(out / f'{name}-result.json', result)
            print(json.dumps(record, ensure_ascii=False), flush=True)
            save(out / 'records.json', records)
            if seconds > 2 * EXPECTED_SECONDS:
                raise RuntimeError(f'{name} took {seconds:.0f} s, over twice the expected {EXPECTED_SECONDS} s; check before continuing')
            number += 1
            if record['valid']:
                valid, streak = valid + 1, (None, 0)
                continue
            word = str(reason).split(':')[0]
            streak = (word, streak[1] + 1 if streak[0] == word else 1)
            if status != 'succeeded' or streak[1] >= VOID_STOP.get(word, 2):
                save(out / 'records.json', records)
                raise RuntimeError(f'stopped at {name}: {status} / {reason} (x{streak[1]}); see {out}')
            if len(records) >= count * 2:
                raise RuntimeError('more than twice the planned instances were needed')
    save(out / 'records.json', records)
    return records


def provisional(work, out, mode, scenario='spec-readiness', runner=subprocess.run):
    """Score every saved valid instance without judging: `lower` counts every undecided candidate as wrong, `upper` as right.
    Writes `<out>/<name>/provisional-<mode>.json` and returns {name: final}.  The true score needs blind judging (`pool`)."""
    checkout = arw_pin.ensure()
    finals = {}
    for folder in sorted(Path(out).glob('a*/')):
        report = next(folder.glob('report.*'), None)
        if report is None:
            continue
        command = ['node', str(checkout / 'scripts/reviewer-capability.mjs'), 'score', str(arw_run.scenario_directory(checkout, scenario)),
                   str(report), '--no-repair', '--agent', str(folder / 'agent.json'), '--instance', folder.name, '--provisional', mode]
        reply = runner(command, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        value = json.loads(reply.stdout)
        save(folder / f'provisional-{mode}.json', value)
        finals[folder.name] = value['scores']['final']
    return finals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--scenario', choices=sorted(arw_run.SCENARIOS), required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--count', type=int)
    parser.add_argument('--provisional', choices=('lower', 'upper'), help='only score the saved instances without judging')
    parser.add_argument('--effort', default=arw_run.EFFORT)
    parser.add_argument('--first', type=int, default=1, help='number of the first instance (a<N>), to resume')
    args = parser.parse_args()
    if args.provisional:
        print(json.dumps(provisional(args.work, args.out, args.provisional, args.scenario)))
        return
    if not args.count:
        parser.error('--count is required to run')
    try:
        run_cell(args.work, args.scenario, args.out, args.count, args.effort, args.first)
    finally:
        arw_run.stop(args.work)


if __name__ == '__main__':
    main()
