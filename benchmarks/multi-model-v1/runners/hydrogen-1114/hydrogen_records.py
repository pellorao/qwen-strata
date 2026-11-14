"""Normalized instance records (bench_records shape) of the Hydrogen supplement, for bench_score and the export.

    python3 -I hydrogen_records.py [--out records.jsonl]     every instance directory under .tmp/hydrobench/<ca|cs|cstd|sr>/

One record per instance directory, the fields bench_score reads (the claude_record shape): handoffs with report path,
sha, sub-scenario, `files_before`; validity from the instance checks (drive.classify's rule); pauses from the recorded continuation (execute in agyrun, plan §3); `validity_before_rejudge` present so bench_score accepts it. Ranking: every
valid instance of a Hydrogen cell is in the main statistic (phase-4 supplement, like phase 3).
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path('/home/pello/projects/qwen-strata')
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import drive  # noqa: E402
from tools.reviewer import bench_records as br, bench_validity  # noqa: E402

OUT = ROOT / '.tmp/hydrobench'
SCEN = {'ca': 'commit-audit-v3', 'cs': 'code-spec-v5', 'cstd': 'code-standards-v5.1', 'sr': 'spec-readiness-v4.3'}


AGY_UPGRADE = time.mktime(time.strptime('2026-11-14 14:55', '%Y-%m-%d %H:%M'))   # local time = JST; agy 1.5.8 -> 1.5.9 (binary mtime)


def agy_version(started):
    return '1.5.8' if (started or 0) < AGY_UPGRADE else '1.5.9'


def record(key, folder):
    inst = json.loads((folder / 'instance.json').read_text())
    verdict, reasons = drive.classify(folder)
    started = min((h.get('started_at') for h in inst['handoffs'] if h.get('started_at')), default=None)
    return br.antigravity_record(SCEN[key], folder, verdict, reasons, inst['plan'], agy_version(started))


def all_records():
    out = []
    for key in SCEN:
        for folder in sorted((OUT / key).glob('hydrogen-*-a*')) if (OUT / key).is_dir() else []:
            if (folder / 'instance.json').is_file():
                out.append(record(key, folder))
    return bench_validity.rank_cells(out, whole_configs=br.SUPPLEMENT_CONFIGS)  # phase-4 supplement: every valid instance counts


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, default=OUT / 'records.jsonl')
    a = ap.parse_args()
    rows = all_records()
    a.out.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
    print(len(rows), 'records ->', a.out)
