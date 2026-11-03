"""Attach deadlines to an already running measurement without restarting it."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import time

from tools.reviewer.arw_measure import Machine
from tools.reviewer.review_deadlines import ReviewDeadline, save


def monitor(batch, folder):
    folder.mkdir(parents=True, exist_ok=True)
    lock = (folder / 'monitor.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    runtime = batch / 'runtime.json'
    configuration = json.loads(runtime.read_text())
    machine = Machine(Path(configuration['repositoryRoot']), runtime, folder)
    timers = {}
    metadata = folder / 'status.json'
    save(metadata, {'pid': os.getpid(), 'status': 'running', 'attached_at': time.time(),
                    'batch': str(batch), 'transport': 'original ARW machine API'})
    try:
        while True:
            try:  # a file read while it is being written is retried, not a failure
                schedule = json.loads((batch / 'schedule.json').read_text())
                records = json.loads((batch / 'results.json').read_text())
            except (FileNotFoundError, json.JSONDecodeError):
                time.sleep(1)
                continue
            done = {r['instanceId'] for r in records}
            if len(done) == len(schedule):
                save(metadata, {'pid': os.getpid(), 'status': 'finished',
                                'finished_at': time.time(), 'batch': str(batch)})
                break
            for job in schedule:
                if job['instanceId'] in done:
                    continue
                instance = batch / job['instanceId']
                try:
                    record = json.loads((instance / 'result.json').read_text())
                except (FileNotFoundError, json.JSONDecodeError):
                    continue
                accepted = record.get('accepted')
                if not isinstance(accepted, dict) or 'messageId' not in accepted or 'runId' not in accepted:
                    raise ValueError(f"{job['instanceId']}: result.json holds no accepted run (messageId, runId); cannot attach a deadline")
                identity = accepted['messageId']
                if identity not in timers:
                    phase = 'revision' if record.get('revisions') else 'initial'
                    started = record.get('review_phase_started_at')
                    source = 'harness task submission'
                    if started is None and phase == 'initial':
                        started = record['started_at']
                    elif started is None:
                        # Legacy live processes predate the exact phase marker.
                        # The first observed followup acceptance gives a bounded
                        # polling delay; preserve that limitation explicitly.
                        started, source = time.time(), 'first observed legacy followup acceptance'
                    timers[identity] = ReviewDeadline(instance, accepted, started,
                        phase=phase, start_source=source)
                    print(json.dumps({'instanceId': job['instanceId'], 'phase': phase,
                        'deadline_record': str(timers[identity].path)}), flush=True)
                observation = machine.call('list_agents', {'runId': accepted['runId']})
                timer = timers[identity]
                before = (timer.value['reminder'], timer.value['interrupt'])
                timer.advance(machine, observation)
                after = (timer.value['reminder'], timer.value['interrupt'])
                if before != after:
                    print(json.dumps({'instanceId': job['instanceId'],
                                      'deadline': timer.facts()}, ensure_ascii=False), flush=True)
            time.sleep(2)
    except Exception as error:
        save(metadata, {'pid': os.getpid(), 'status': 'failed', 'at': time.time(),
                        'error': str(error), 'batch': str(batch)})
        raise
    finally:
        machine.close()
        lock.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    monitor(args.batch.resolve(), args.out.resolve())
