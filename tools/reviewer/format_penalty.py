"""Benchmark format penalty of a scored repetition (project scoring upgrade r7, user 2026-10-15).

Replaces the flat x0.9 for format errors, which are errors of the whole report (user 2026-10-15). For each repetition:
  p = r / T, f = 0.1 * min(1, p / (2 * pBase)), final = raw - f * |raw| (r8.4, user 2026-10-21: raw is no longer cut
  at 0 and f takes f of its size, so a negative score falls too)
r counts every format error in scorer units (so `a:1,5` is two): the repairable ones found by
`repair_reviewer_report` (from the repair record; a Commit Audit row moved to the requirement line it quotes counts once; a locator converted from a spilled tool output counts once per
locator part), those left in the scored report (`unrepairableFormatErrors` of
the upgraded scorer: report lines that are not findings, invalid JSON lines, rows that cannot be assigned to a
requirement) and the line ranges the scorer cut back to the end of their file (`overrunLocators`). T is the number of
locators the scorer read (`locatorCount`). Errors that belong to one case (invalid evidence, a missing or invalid
requirement row) are not counted here: the scorer charges them inside that case. raw is the repetition score before
the format penalty (ARW `score`, which keeps ARW's 0.9 cut only for report diagnostics outside the project's
REPORT_DIAGNOSTIC_TREATMENT). The benchmark score (tools.reviewer.bench_score) starts from scoreBeforePenalty and
takes f, the pause cut and that residual cut as one overall deduction, the largest (user 2026-10-20).

Every instance must declare its repair: a repair record, or explicitly none; an undeclared instance is an error,
since a repaired copy carries no trace of its repair.

pBase is registered per frozen answer key (reviewer and expected.json sha256) in the suite's registry
(REGISTRIES: v1 benchmarks/reviewer-suite-v1/format-baseline.json, v2 benchmarks/multi-model-v2/format-baseline.json): the pooled sum(r) / sum(T) of Haiku-high x5 on that
key, at least 2 errors per report (2 / mean T). An unregistered key is an error. Each registered run binds its
archived reports and repair records (benchmarks/reviewer-suite-v1/format-baseline/) by sha256, so r, T and pBase can
be recomputed after the run directories are gone.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[2]
# One registry per benchmark suite (tools.reviewer.bench_suite names the suites): v2 re-labels the scenarios whose wording
# changed on answer keys v1 already registered, so a v2 baseline must never share v1's table. A v2 entry for a scenario
# whose text did not change says {"inheritsFrom": "v1"} instead of copying the v1 baseline.
REGISTRIES = {'v1': ROOT / 'benchmarks/reviewer-suite-v1/format-baseline.json',
              'v2': ROOT / 'benchmarks/multi-model-v2/format-baseline.json'}
REGISTRY = REGISTRIES['v1']
ARCHIVE = REGISTRY.parent / 'format-baseline'
CAP = 0.1


def repairable_count(changes):
    """Repairable errors of one repair record (`<report>.changes.json`) in scorer units."""
    count = 0
    for change in changes.get('details', []):
        if change['kind'] == 'short-evidence-path':
            # `name.mjs:3,7-9` is completed once but the scorer reads one locator per comma part.
            count += len(change['before'].strip('`').rsplit(':', 1)[1].split(','))
        elif change['kind'] == 'spill-locator':
            # Every converted comma part is one locator the scorer reads.
            count += len(change['converted'])
        elif change['kind'] in ('markdown-preamble', 'markdown-stray-lines', 'scalar-lines', 'requirement-line'):
            # markdown-stray-lines: every line outside a finding of one report, once (ARW's one review-format-invalid).
            count += 1
        else:
            raise ValueError(f"unknown repair kind {change['kind']}")
    return count


def pooled_baseline(runs):
    """pBase from (r, T) of each baseline report: pooled sum(r) / sum(T), at least 2 errors per report."""
    if not runs or any(t <= 0 for _, t in runs):
        raise ValueError('baseline needs reports with locators')
    total_r, total_t = sum(r for r, _ in runs), sum(t for _, t in runs)
    floor = 2 / (total_t / len(runs))
    return {'reports': len(runs), 'sumR': total_r, 'sumT': total_t, 'pooled': total_r / total_t,
            'floor': floor, 'pBase': max(total_r / total_t, floor)}


def bootstrap_interval(runs, resamples=10000, seed=0):
    """90% bootstrap interval of pBase, resampling the baseline reports with replacement."""
    rng = random.Random(seed)
    values = sorted(pooled_baseline([rng.choice(runs) for _ in runs])['pBase'] for _ in range(resamples))
    return [values[int(0.05 * resamples)], values[int(0.95 * resamples) - 1]]


def suite_registry(suite):
    if suite not in REGISTRIES:
        raise ValueError(f'unknown benchmark suite {suite!r}')
    return REGISTRIES[suite]


def registered_entry(reviewer, expected_sha256, registry=REGISTRY):
    entry = json.loads(Path(registry).read_text()).get(reviewer, {}).get(expected_sha256)
    if isinstance(entry, dict) and entry.get('inheritsFrom') == 'v1':
        entry = json.loads(REGISTRIES['v1'].read_text()).get(reviewer, {}).get(expected_sha256)
    if not isinstance(entry, dict) or not isinstance(entry.get('runs'), list):
        raise ValueError(f'format baseline of {reviewer} answer key {expected_sha256} is not registered')
    return entry


def registered_baseline(reviewer, expected_sha256, registry=REGISTRY):
    entry = registered_entry(reviewer, expected_sha256, registry)
    # The registered pBase is a readable copy; the value used is recomputed from the registered runs.
    if any(run['r'] != run['rRepairable'] + run['rUnrepairable'] + run['rOverrun'] for run in entry['runs']):
        raise ValueError(f'format baseline of {reviewer} answer key {expected_sha256} does not match its runs')
    baseline = pooled_baseline([(run['r'], run['T']) for run in entry['runs']])
    if abs(baseline['pBase'] - entry.get('pBase', -1)) > 1e-6:
        raise ValueError(f'format baseline of {reviewer} answer key {expected_sha256} does not match its runs')
    return baseline['pBase']


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_archive(entry, archive=ARCHIVE):
    """Check a registry entry against its archived reports and repair records: every file matches its sha256 and the
    repair records give each run's repairable count. Returns the number of files checked."""
    checked = 0
    for run in entry['runs']:
        repairable = 0
        for item in run['reports']:
            if sha256_file(archive / item['report']) != item['reportSha256']:
                raise ValueError(f"archived report {item['report']} differs from its registration")
            checked += 1
            if item.get('changes') is not None:
                if sha256_file(archive / item['changes']) != item['changesSha256']:
                    raise ValueError(f"archived repair record {item['changes']} differs from its registration")
                record = json.loads((archive / item['changes']).read_text())
                if record.get('original_sha256') != item['reportSha256']:
                    raise ValueError(f"repair record {item['changes']} was made from another report")
                repairable += repairable_count(record)
                checked += 1
        if repairable != run['rRepairable']:
            raise ValueError(f"run {run['run']} repairable count differs from its archived repair records")
    return checked


def penalty(r, t, p_base):
    p = r / t if t > 0 else (0.0 if r == 0 else 1.0)
    return p, CAP * min(1.0, p / (2 * p_base))


def final_score(raw, f):
    # raw - f|raw|, per sign so raw >= 0 keeps exactly the r8.3 value raw x (1 - f).
    return raw * (1 - f) if raw >= 0 else raw * (1 + f)


def instance_errors(instance, repairs):
    """(repairable, unrepairable, overrun) format errors of one scored instance. repairs maps every instanceId to its
    repair record, or to None when nothing was repaired; an instance missing from it is an error."""
    instance_id = instance['instanceId']
    if instance_id not in repairs:
        raise ValueError(f'instance {instance_id} declares no repair; give its repair record or declare none')
    record = repairs[instance_id]
    if instance.get('modelFailure') is not None:
        # No report: nothing to repair, no format error and no locator (scoring-k.patch zeroCapabilityScore gives
        # locatorCount 0 and no overrunLocators). A Spec Readiness repetition whose other instance has a report is
        # scored on that report's errors alone (user 2026-10-21: a model failure is the same as reporting nothing).
        if record is not None or instance.get('locatorCount') != 0 or instance.get('unrepairableFormatErrors', 0) != 0:
            raise ValueError(f'model failure {instance_id} declares a repair, locators or format errors')
        return 0, 0, 0
    if record is None and instance.get('formatCorrection') is not None:
        raise ValueError(f'instance {instance_id} was scored through a format correction but declares no repair')
    if 'unrepairableFormatErrors' not in instance or 'overrunLocators' not in instance:
        raise ValueError(f'instance {instance_id} was not scored by the current scoring upgrade (no format error counts)')
    return (repairable_count(record) if record is not None else 0), instance['unrepairableFormatErrors'], instance['overrunLocators']


def score_repetitions(upstream, repairs, registry=REGISTRY, extra_errors=0):
    """Final scores of every repetition of an upstream score-completed output.

    repairs maps every instanceId to its repair record, or to None when nothing was repaired. extra_errors adds format
    errors the reports do not show to each repetition's r (B class: a final status message not in ARW's form, 1 per
    instance; user 2026-10-20)."""
    rows = []
    for result in upstream['results']:
        for repetition in result.get('repetitions', []):
            instances = repetition['instances']
            keys = {(result['reviewerId'], i['judgmentBinding']['expectedSha256']) for i in instances}
            bases = {registered_baseline(reviewer, sha, registry) for reviewer, sha in keys}
            if len(bases) != 1:
                raise ValueError('instances of one repetition have different format baselines')
            parts = [sum(values) for values in zip(*(instance_errors(i, repairs) for i in instances))]
            r = sum(parts) + extra_errors
            t = sum(i['locatorCount'] for i in instances)
            p, f = penalty(r, t, bases.pop())
            rows.append({'reviewerId': result['reviewerId'], 'repetition': repetition['repetition'],
                         'instances': [i['instanceId'] for i in instances], 'raw': repetition['score'],
                         'r': r, 'rRepairable': parts[0], 'rUnrepairable': parts[1], 'rOverrun': parts[2],
                         'rFinalStatus': extra_errors,
                         'T': t, 'p': p, 'f': f, 'score': final_score(repetition['score'], f)})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--upstream', type=Path, required=True, help='upstream score-completed output (final, adjudicated)')
    parser.add_argument('--repair', action='append', default=[], metavar='INSTANCE_ID=CHANGES_JSON',
                        help='repair record of a repaired instance; repeat for each')
    parser.add_argument('--no-repair', action='append', default=[], metavar='INSTANCE_ID',
                        help='an instance scored from its original report; every instance needs --repair or --no-repair')
    parser.add_argument('--suite', choices=sorted(REGISTRIES), default='v1', help='benchmark suite whose baselines apply')
    args = parser.parse_args()
    repairs = {instance: None for instance in args.no_repair}
    for item in args.repair:
        instance, path = item.split('=', 1)
        if instance in repairs:
            parser.error(f'instance {instance} is declared twice')
        repairs[instance] = json.loads(Path(path).read_text())
    try:
        rows = score_repetitions(json.loads(args.upstream.read_text()), repairs, suite_registry(args.suite))
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(rows, indent=1))


if __name__ == '__main__':
    main()
