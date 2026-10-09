"""Verify a stopped native runtime before isolating future prepared instances."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from tools.reviewer.wsl_client import save


def verify_stopped_runtime(out, source, new_install, records, pending_ids):
    out, source, new_install = map(lambda p: Path(p).resolve(), (out, source, new_install))
    if new_install.parent != out or not new_install.name.startswith('arw-installation-'):
        raise ValueError('Recovery installation must be a new isolated directory in this batch.')
    if new_install.exists():
        raise ValueError('Recovery installation already exists; do not reuse uncertain state.')
    if (out / 'controller-key.private.json').exists():
        raise ValueError('Recovery cannot bypass retained model ownership.')
    old_runtime = json.loads((out / 'runtime.json').read_text())
    if Path(old_runtime['repositoryRoot']).resolve() != source:
        raise ValueError('Recovery cannot change the frozen upstream repository.')
    if any((out / identifier).exists() for identifier in pending_ids):
        raise ValueError('An unrecorded instance has run artifacts; recover that task first.')
    for record in records:
        result = record.get('runtime_result', {})
        if (result.get('state') not in ('idle', 'exited')
                or result.get('completion', {}).get('status') not in ('ready', 'incomplete')
                or not isinstance(record.get('finished_at'), (int, float))):
            raise ValueError('Every submitted instance must have a native terminal observation.')
    recovery_file = out / 'recovery-required.json'
    recovery = json.loads(recovery_file.read_text()) if recovery_file.exists() else {}
    old_daemon = recovery.get('daemon_pid')
    if old_daemon and Path(f'/proc/{old_daemon}').exists():
        raise ValueError('Previous daemon PID still exists; verify it before recovery.')
    needles = [str(out / 'runtime.json').encode(), old_runtime['installationDirectory'].encode()]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            args = (proc / 'cmdline').read_bytes().split(b'\0')
        except FileNotFoundError:
            continue
        except (PermissionError, ProcessLookupError) as exc:
            raise ValueError('Cannot verify the old runtime process boundary.') from exc
        if args and Path(os.fsdecode(args[0])).name in ('node', 'codex', 'python3'):
            if any(needle in arg for needle in needles for arg in args):
                raise ValueError('A process still references the previous native runtime.')
    script = ('const {readAppServerProcessIdentity}=await import(process.argv[1]);'
              'console.log(JSON.stringify(await readAppServerProcessIdentity('
              '{runtimeDirectory:process.argv[2]})));')
    observation = json.loads(subprocess.check_output([
        'node', '--input-type=module', '-e', script,
        (source / 'lib/background-agent/process-identity.mjs').as_uri(),
        old_runtime['runtimeDirectory']], text=True, timeout=20))
    if observation.get('state') != 'ended' or not observation.get('identity'):
        raise ValueError('The original ARW OS process identity must confirm native exit.')
    return {'verified_at': time.time(), 'old_runtime': old_runtime,
            'new_installation': str(new_install), 'app_server': observation,
            'previous_daemon_pid': old_daemon, 'previous_daemon_absent': True,
            'submitted_instances': [r['instanceId'] for r in records],
            'pending_instances': list(pending_ids),
            'evidence_sha256': {name: hashlib.sha256((out / name).read_bytes()).hexdigest()
                               for name in ('runtime.json', 'arw-cleanup.json', 'results.json')},
            'scope': 'Fresh state for never-started isolated instances; preserve old busy state and all closed results.'}


def archive_recovery(out, proof):
    folder = Path(out) / 'recovery-history' / str(time.time_ns())
    folder.mkdir(parents=True, exist_ok=False)
    for name in ('runtime.json', 'arw-cleanup.json', 'results.json', 'recovery-required.json'):
        path = Path(out) / name
        if path.exists():
            (folder / name).write_bytes(path.read_bytes())
    save(folder / 'verified-recovery.json', proof)
    return folder
