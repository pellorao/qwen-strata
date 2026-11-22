"""The pinned ARW checkout: ARW owns the Reviewer scenarios, scoring and `reviewer-capability run`; this project
measures with the commit named in config/arw-pin.json.

The checkout is a git clone, not a `git archive`: `run` reads `git rev-parse HEAD` and `git status` in it and fails
with `provenance-read` in a plain directory.  It lives in `.tmp/arw/<commit>/` and can be recreated at any time.

    python3 -m tools.arw.pin            # make sure the checkout exists and matches the pin; print its path
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PIN_FILE = ROOT / 'config/arw-pin.json'
LOCAL_ARW = Path('~/projects/ARW').expanduser()  # where this machine keeps ARW; GitHub `origin` is the fallback
FIXTURES = 'tests/fixtures/reviewer-capability'


def load(path=PIN_FILE):
    pin = json.loads(Path(path).read_text())
    for key in ('commit', 'fixtureTree', 'origin'):
        if not isinstance(pin.get(key), str) or not pin[key]:
            raise ValueError(f'{path}: {key} must be a non-empty string')
    return pin


def git(*args, cwd=None):
    return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, env=dict(os.environ, GIT_TERMINAL_PROMPT='0')).stdout.strip()


def has_commit(repository, commit):
    return subprocess.run(['git', 'cat-file', '-e', commit + '^{commit}'], cwd=repository,
                          capture_output=True, stdin=subprocess.DEVNULL).returncode == 0


def verify(checkout, pin):
    """Raise unless the checkout is the pinned commit with the pinned fixture tree and no local change."""
    head, tree = git('rev-parse', 'HEAD', cwd=checkout), git('rev-parse', f'HEAD:{FIXTURES}', cwd=checkout)
    if head != pin['commit']:
        raise ValueError(f'{checkout} is at {head}, the pin is {pin["commit"]}')
    if tree != pin['fixtureTree']:
        raise ValueError(f'fixture tree {tree} differs from the pinned {pin["fixtureTree"]}')
    if git('status', '--porcelain', cwd=checkout):
        raise ValueError(f'{checkout} has local changes')


def create(checkout, pin, source):
    """Clone without checkout from the local ARW when it holds the commit (hardlinked objects, no copy), else fetch
    just that commit from GitHub (shallow, about 10 MB)."""
    checkout.parent.mkdir(parents=True, exist_ok=True)
    if source is not None and (Path(source) / '.git').exists() and has_commit(source, pin['commit']):
        git('clone', '-q', '--no-checkout', str(source), str(checkout))
    else:
        checkout.mkdir()
        git('init', '-q', cwd=checkout)
        git('fetch', '-q', '--depth', '1', pin['origin'], pin['commit'], cwd=checkout)
    git('checkout', '-q', '--detach', pin['commit'], cwd=checkout)


def ensure(root=None, pin_file=PIN_FILE, source=LOCAL_ARW):
    """Path of the verified checkout `<root>/<commit>`; created when missing, recreated when it fails verification."""
    pin = load(pin_file)
    checkout = Path(root or ROOT / '.tmp/arw') / pin['commit']
    if checkout.exists():
        try:
            verify(checkout, pin)
            return checkout
        except (ValueError, subprocess.CalledProcessError):
            raise ValueError(f'{checkout} does not match the pin; delete that directory (it is recreated) and retry')
    create(checkout, pin, source)
    verify(checkout, pin)
    return checkout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, help='parent of the <commit> checkout (default .tmp/arw)')
    print(ensure(parser.parse_args().root))


if __name__ == '__main__':
    main()
