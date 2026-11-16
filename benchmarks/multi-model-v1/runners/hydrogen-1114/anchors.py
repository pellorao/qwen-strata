#!/usr/bin/env python3
"""New-family anchors after the first blind batch (v1 plan §6.2; plan.md §4/§6). Python 3 stdlib; run with -I.

  anchors.py pick      stratify the family's association decisions by scenario x decision, shuffle each stratum with
                       the fixed seed 20261021 and write the first PER_STRATUM + SPARE of each to PICKS (pool item,
                       blind decision, origin), for Main's executable check
  anchors.py register  read CHECKS (Main's verdict per pick: decision, method, evidence), report the recheck of the
                       first batch (Main vs the blind decision, per scenario) and register every checked pick as an
                       anchor in REGISTRY (a copy of the v1 registry plus the new family; the frozen v1 registry is
                       not edited, because the frozen tools know only three families)

The family is added to blind_pool.FAMILIES in this process only, as judge.py does. A later supplement (Carbon) runs
the same script with its own BASE/FAMILY/MODEL and REGISTRY_IN set to this runner's anchors/ directory, so its pools
carry the Hydrogen anchors too.
"""
import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path('/home/pello/projects/qwen-strata')
HERE = Path(__file__).resolve().parent
BASE = ROOT / '.tmp/hydrobench'                         # run data of this supplement
SCORE = BASE / 'score'                                  # decision stores <record>/decisions.json
POOLS = ROOT / '.tmp/pools'                             # <pool>/pool-<pool>.json (what the adjudicator saw)
FAMILY, MODEL = 'hydrogen', 'hydrogen'
REGISTRY_IN = ROOT / 'benchmarks/multi-model-v1/anchors'   # base registry (v1)
REGISTRY = HERE / 'anchors'                              # v1 registry + this family's anchors
PICKS = HERE / 'anchors/picks.json'
CHECKS = HERE / 'anchors/checks.json'                    # Main's verdicts, written by hand after the checks
SEED = 20261021
PER_STRATUM = 2                                          # anchors to register per scenario x decision
SPARE = 3                                                # extra picks per stratum, used in order when a pick is skipped
SCENARIOS = ('commit-audit-v3', 'code-spec-v5', 'code-standards-v5.1', 'spec-readiness-v4.3')


def load(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=1) + '\n')


def pool_items():
    items = {}
    for path in sorted(POOLS.glob('*/pool-*.json')):
        for item in load(path):
            items[item['id']] = item
    return items


def pick():
    items = pool_items()
    strata = {}
    for store in sorted(SCORE.glob('*/*/*/decisions.json')):
        record = str(store.parent.relative_to(SCORE))
        scenario = record.split('/')[1]
        for stable_id, d in load(store)['decisions'].items():
            if d.get('kind') != 'association' or not d['source'].startswith('pool '):
                continue   # only blind association decisions (no override, no finding kind)
            pool_id = d['source'].split(':', 1)[1]
            strata.setdefault((scenario, d['decision']), []).append(
                {'record': record, 'stable_id': stable_id, 'pool_id': pool_id, 'blind': d['decision'],
                 'blind_reason': d['reason'], 'item': items[pool_id]})
    out = {'seed': SEED, 'per_stratum': PER_STRATUM, 'spare': SPARE, 'strata': {}}
    for scenario in SCENARIOS:
        for decision in ('matched', 'not-matched'):
            rows = sorted(strata.get((scenario, decision), []), key=lambda r: (r['record'], r['stable_id']))
            random.Random(SEED).shuffle(rows)
            out['strata'][f'{scenario}:{decision}'] = {'size': len(rows), 'picks': rows[:PER_STRATUM + SPARE]}
            print(f'{scenario:22} {decision:12} size {len(rows):4}  picks {[r["pool_id"] for r in rows[:PER_STRATUM + SPARE]]}')
    save(PICKS, out)


def register(dry_run=False):
    sys.path.insert(0, str(ROOT))
    from tools.reviewer import blind_pool
    blind_pool.FAMILIES = (*blind_pool.FAMILIES, FAMILY)
    picks, checks = load(PICKS), load(CHECKS)
    summary = {}
    for key, stratum in picks['strata'].items():
        scenario = key.split(':')[0]
        row = summary.setdefault(scenario, {'checked': 0, 'agree': 0, 'skipped': 0, 'registered': [], 'misses': []})
        taken = 0
        for p in stratum['picks']:
            if taken >= PER_STRATUM:
                break
            c = checks.get(p['pool_id'])
            if c is None:
                raise SystemExit(f'{p["pool_id"]}: no verdict in {CHECKS} (check the picks in order)')
            if c['decision'] == 'skip':
                row['skipped'] += 1
                continue
            row['checked'] += 1
            taken += 1
            if c['decision'] == p['blind']:
                row['agree'] += 1
            else:
                row['misses'].append({'pool_id': p['pool_id'], 'blind': p['blind'], 'main': c['decision']})
            row['registered'].append((p, c))
    for scenario, row in summary.items():
        print(f"{scenario:22} checked {row['checked']} agree {row['agree']} skipped {row['skipped']} misses {row['misses']}")
    if dry_run:
        return
    for scenario in SCENARIOS:   # registry copy: base anchors and synthetic items, then this family's anchors
        target = REGISTRY / f'{scenario}.json'
        reg = load(target) if target.is_file() else load(REGISTRY_IN / f'{scenario}.json')
        known = {((a.get('origin') or {}).get('record'), (a.get('origin') or {}).get('stable_id'))
                 for a in reg['anchors']}
        save(target, reg)
        for p, c in summary.get(scenario, {}).get('registered', []):
            identity = (p['record'], p['stable_id'])
            if identity in known:
                continue
            a = blind_pool.anchor_add(scenario, p['item'], c['decision'], FAMILY,
                                      f"Main executable check 11-15 (common/hydrojudge; {c['method']}): {c['evidence']}",
                                      origin={'record': p['record'], 'stable_id': p['stable_id']}, registry=REGISTRY,
                                      model=MODEL)
            known.add(identity)
            print('registered', scenario, a['id'], p['pool_id'], c['decision'])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=['pick', 'register'])
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    pick() if a.cmd == 'pick' else register(a.dry_run)


if __name__ == '__main__':
    main()
