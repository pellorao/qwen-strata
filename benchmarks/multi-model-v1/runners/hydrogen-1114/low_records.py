"""Records of the Hydrogen low instances (common/hydroeffort, 2026-11-15): same producer as hydrogen_records.py, only for hydrogen-low-a* directories.

    python3 -I low_records.py [--out records.jsonl]     -> .tmp/hydrolow/records.jsonl (the base dir of `judge.py --profile low`)

Hydrogen medium / high / xhigh are configs 30-32 of the tool chain; low is not in its CONFIG_TABLE, so it is added to EXTRA_CONFIGS in this
process only (config 36; Carbon uses 33-35), as judge.py extends the families. Every valid instance counts (phase-4 supplement rule)."""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import hydrogen_records as hr  # noqa: E402
from tools.reviewer import bench_records as br, bench_validity  # noqa: E402

LOW_CONFIG = 36
BASE = hr.ROOT / '.tmp/hydrolow'


def register():
    br.EXTRA_CONFIGS[('hydrogen', 'low')] = LOW_CONFIG
    return br.SUPPLEMENT_CONFIGS | {LOW_CONFIG}


def all_records():
    whole = register()
    out = []
    for key in hr.SCEN:
        for folder in sorted((hr.OUT / key).glob('hydrogen-low-a*')) if (hr.OUT / key).is_dir() else []:
            if (folder / 'instance.json').is_file():
                out.append(hr.record(key, folder))
    return bench_validity.rank_cells(out, whole_configs=whole)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, default=BASE / 'records.jsonl')
    a = ap.parse_args()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    rows = all_records()
    a.out.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
    print(len(rows), 'records ->', a.out)
