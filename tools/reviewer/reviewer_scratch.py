"""Private Reviewer scratch (ARW harness patch reviewer-private-scratch, plan §14.1 F2): its path and per-instance removal.

Each Codex Reviewer gets <root>/<digest> as a writable directory and as TMPDIR of its commands; the common root is
denied to every Reviewer. The digest is the patch's (sha256 of the scenario root and the report directory, NUL-joined,
first 32 hex digits); tests/test_reviewer_scratch.py checks that both sides agree. After an instance, its scratch goes
with the other per-instance residue (measurement.md「存放」):

    python3 -m tools.reviewer.reviewer_scratch --remove <arw_measure out directory>
"""
import argparse
import hashlib
import json
import os
import shutil
import stat
from pathlib import Path

ROOT_VARIABLE = 'ARW_REVIEWER_SCRATCH_ROOT'


def scratch_root(environment=os.environ):
    # Lexical, as node's path.resolve: the patch never resolves links.
    return Path(os.path.abspath(environment.get(ROOT_VARIABLE) or f'/tmp/arw-reviewer-scratch-{os.getuid()}'))


def scratch_path(cwd, write_paths, root=None):
    root = Path(os.path.abspath(root)) if root else scratch_root()
    key = '\0'.join([os.path.abspath(cwd), *(os.path.abspath(p) for p in write_paths)])
    return root / hashlib.sha256(key.encode()).hexdigest()[:32]


def run_scratches(out, root=None):
    """The scratch of every Reviewer an arw_measure run bound (<out>/<instance>/binding.json)."""
    found = []
    for binding in sorted(Path(out).glob('*/binding.json')):
        value = json.loads(binding.read_text())
        if isinstance(value, dict) and 'cwd' in value and 'writePaths' in value:
            found.append(scratch_path(value['cwd'], value['writePaths'], root))
    return list(dict.fromkeys(found))


def remove(path, root=None):
    """Remove one scratch: a real directory directly under the root, owned by this user. Returns whether it existed."""
    path = Path(path)
    root = Path(os.path.abspath(root)) if root else scratch_root()
    if path.parent != root:
        raise ValueError(f'{path} is not directly under the Reviewer scratch root {root}')
    if not os.path.lexists(path):
        return False
    st = path.lstat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid():
        raise ValueError(f'{path} is not this user\'s scratch directory')
    shutil.rmtree(path)
    return True


def remove_run(out, root=None):
    """Remove every scratch of one run; returns {path: existed}."""
    return {str(p): remove(p, root) for p in run_scratches(out, root)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--remove', type=Path, metavar='OUT', help='arw_measure out directory whose scratches to remove')
    parser.add_argument('--list', type=Path, metavar='OUT', help='list the scratches of an arw_measure out directory')
    args = parser.parse_args()
    if args.list:
        print(json.dumps([str(p) for p in run_scratches(args.list)], indent=1))
    if args.remove:
        print(json.dumps(remove_run(args.remove), indent=1))
