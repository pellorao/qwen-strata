"""Validate an explicitly frozen native CLI before taking model ownership."""
import hashlib
from pathlib import Path
import subprocess


def verify_native_cli(binding):
    if binding is None:
        return None
    executable = Path(binding['executable'])
    if not executable.is_absolute() or not executable.is_file():
        raise ValueError('Frozen native CLI must be an existing absolute executable.')
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    if digest != binding['sha256']:
        raise ValueError('Frozen native CLI executable SHA differs.')
    version = subprocess.check_output([str(executable), '--version'], text=True,
                                     timeout=20).strip()
    if version != 'codex-cli ' + binding['version']:
        raise ValueError('Frozen native CLI version differs.')
    return {**binding, 'observed_version': version}
