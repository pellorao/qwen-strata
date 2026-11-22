"""Validate an explicitly frozen native CLI before taking model ownership."""
import hashlib
from pathlib import Path
import subprocess

from tools.strata.harness_pins import CODEX, CODEX_SHA256, CODEX_VENDOR, CODEX_VERSION  # noqa: F401 (re-exported)

# The native Codex binary of the read-only benchmark copy named in tools.strata.harness_pins (off PATH; the user's
# daily install updates itself and is not used). Gates and ARW runs (native_cli) execute it directly, and its sandbox
# helper re-executes it, so a restricted permission profile must keep this directory readable.


def pinned_codex():
    """Binding of the benchmark copy, checked (SHA, then version) before a gate or run starts it."""
    return verify_native_cli({'executable': str(CODEX), 'version': CODEX_VERSION, 'sha256': CODEX_SHA256})


def file_sha256(path, chunk=1 << 20):
    """SHA-256 of a file read in chunks (the native binary is about a hundred megabytes)."""
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        while block := stream.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def verify_native_cli(binding):
    if binding is None:
        return None
    executable = Path(binding['executable'])
    if not executable.is_absolute() or not executable.is_file():
        raise ValueError('Frozen native CLI must be an existing absolute executable.')
    digest = file_sha256(executable)
    if digest != binding['sha256']:
        raise ValueError('Frozen native CLI executable SHA differs.')
    version = subprocess.check_output([str(executable), '--version'], text=True,
                                     timeout=20).strip()
    if version != 'codex-cli ' + binding['version']:
        raise ValueError('Frozen native CLI version differs.')
    return {**binding, 'observed_version': version}


def selection_native_cli(binding):
    """A selection's explicit binding, or the pinned benchmark copy: ARW's own default (`codex` on PATH) is the user's
    self-updating install, which since Codex 0.163.0 lives under the deny-read ~/.codex."""
    return verify_native_cli(binding) if binding is not None else pinned_codex()
