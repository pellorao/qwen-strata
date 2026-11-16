#!/usr/bin/env python3
"""Generate Hydrogen phase-4 statistics and export through the shared toolchain.

Run with -I. Inputs default to .tmp/hydrobench/records.jsonl and its score/.
Writes summary.json, summary.md and hydrogen-results.json to --out (default:
this runner's results/). Published results are replaced only after export passes
all source and publication-safety checks. No model or network calls are made.
"""
import argparse
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.reviewer import benchmark_export, benchmark_summary  # noqa: E402

BASE = ROOT / '.tmp/hydrobench'
OUT = Path(__file__).resolve().parent / 'results'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--records', type=Path, default=BASE / 'records.jsonl')
    parser.add_argument('--score-root', type=Path, action='append', help='repeat for multiple scoring roots')
    parser.add_argument('--out', type=Path, default=OUT)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    # benchmark_summary requires a fresh directory. Stage both artifacts so a
    # rejected export cannot replace the previous successful summary.
    with tempfile.TemporaryDirectory(prefix='.summary-', dir=args.out) as work:
        stage = Path(work) / 'phase4'
        benchmark_summary.write(stage, records_path=args.records,
                                score_root=args.score_root or [BASE / 'score'], phase=4)
        benchmark_export.write(stage / 'summary.json', stage / 'hydrogen-results.json', diagnostic_path=None)
        for name in ('summary.json', 'summary.md', 'hydrogen-results.json'):
            shutil.copy2(stage / name, args.out / name)
    print('phase-4 summary and export written to', args.out)


if __name__ == '__main__':
    main()
