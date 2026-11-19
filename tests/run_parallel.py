"""Run the whole suite with one process per test file, at most 8 at a time (like `node --test`).

    python3 tests/run_parallel.py [-j N] [file_glob ...]      (from the project root; default glob test_*.py)

A file that fails prints its own unittest output; the exit code is 1 if any file failed.  Every file's tests are
independent of the other files (own temp dirs, port 0), so the order and the overlap do not matter."""
import argparse
import concurrent.futures
import fnmatch
import os
import re
from pathlib import Path
import subprocess
import sys
import time

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
# Files known to take longest start first, so the last files do not leave the other workers idle.
SLOW = ('test_spec_readiness_split', 'test_bench_score', 'test_claude_continuation', 'test_harness_patches',
        'test_multi_model_v2', 'test_tuning_workloads', 'test_claude_headless', 'test_corpus_replay')


def run(name):
    started = time.monotonic()
    done = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', str(TESTS), '-p', name + '.py'],
                          cwd=ROOT, capture_output=True, text=True, errors='replace')
    return name, done.returncode, done.stderr + done.stdout, time.monotonic() - started


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('-j', type=int, default=min(os.cpu_count() or 1, 8))
    parser.add_argument('patterns', nargs='*', default=['test_*.py'])
    args = parser.parse_args()
    if args.j < 1:
        parser.error('-j must be at least 1')
    (ROOT / '.tmp').mkdir(exist_ok=True)  # several tests put their temp dirs here; create it before the workers race
    names = sorted(p.stem for p in TESTS.glob('test_*.py') if any(fnmatch.fnmatch(p.name, g) for g in args.patterns))
    if not names:
        parser.error('no test file matches ' + ' '.join(args.patterns))
    names.sort(key=lambda n: n not in SLOW)
    started, failed, ran = time.monotonic(), [], 0
    with concurrent.futures.ThreadPoolExecutor(args.j) as pool:
        for name, code, output, _ in pool.map(run, names):
            tail = output.strip().splitlines()
            ran += sum(int(l.split()[1]) for l in tail[-6:] if re.match(r'Ran \d+ tests? in ', l))
            if code:
                failed.append(name)
                print(f'==== {name} FAILED (exit {code})\n{output}', file=sys.stderr)
    print(f'Ran {ran} tests in {len(names)} files in {time.monotonic() - started:.1f}s: '
          + ('FAILED ' + ', '.join(failed) if failed else 'OK'))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
