"""Single-scenario diagnostic score from the unchanged upstream score-completed.

Upstream scores each completed instance on its own but fuses Spec Readiness only when both
sub-scenarios of a repetition are present. Tuning comparisons may need one sub-scenario alone:
this runs the same upstream scoring on the given instances, requires that they all belong to one
scenario, and reports their per-instance scores as diagnostic and unfused. It is never a formal
score and must not be compared with fused scores.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess

THREAD_ID = 'b7635f94-ad60-429b-98e7-3ee5c19ba2bb'  # Main identity bound at upstream preparation


def upstream_score(arw, prepared, scoring_input, adjudication=None):
    arw = Path(arw).resolve()
    command = ['node', str(arw / 'scripts/reviewer-capability-conformance.mjs'), 'score-completed',
               '--prepared', str(Path(prepared).resolve()), '--input', str(Path(scoring_input).resolve())]
    if adjudication:
        command += ['--adjudication', str(Path(adjudication).resolve())]
    return subprocess.run(command, cwd=arw, capture_output=True, text=True,
                          env=dict(os.environ, CODEX_THREAD_ID=os.environ.get('CODEX_THREAD_ID', THREAD_ID)))


def summarize(upstream):
    instances = [i for result in upstream['results'] for i in result['instances']]
    scenarios = {i['scenarioId'] for i in instances}
    if len(scenarios) != 1:
        raise ValueError('Single-scenario scoring needs instances of exactly one scenario; use the fused upstream score')
    rows = [{'instanceId': i['instanceId'], 'repetition': i['repetition'], 'score': i['score'],
             'cleanAcceptanceRate': i['cleanAcceptanceRate'], 'problemDetectionRate': i['problemDetectionRate']}
            for i in instances]
    return {'status': 'diagnostic-single-scenario', 'fused': False, 'scenarioId': scenarios.pop(),
            'reviewerIds': upstream.get('reviewerIds'), 'upstream_status': upstream.get('status'),
            'instances': rows, 'mean_score': statistics.mean(r['score'] for r in rows),
            'note': 'Upstream per-instance scores of one sub-scenario, not fused; not a formal score and '
                    'not comparable with fused scores.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arw', type=Path, required=True, help='materialized frozen ARW used for preparation')
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True, help='upstream score input listing only this scenario')
    parser.add_argument('--adjudication', type=Path, help="Main's matched / not-matched decisions")
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    reply = upstream_score(args.arw, args.prepared, args.input, args.adjudication)
    (args.out / 'upstream.json').write_text(reply.stdout)
    (args.out / 'upstream.err').write_text(reply.stderr)
    if reply.returncode != 0:
        # Pending candidates need Main's adjudication; nothing is summarized before that.
        print(json.dumps({'status': 'upstream-not-final', 'returncode': reply.returncode,
                          'stderr': str(args.out / 'upstream.err')}))
        raise SystemExit(reply.returncode)
    result = summarize(json.loads(reply.stdout))
    result['upstream_output_sha256'] = hashlib.sha256(reply.stdout.encode()).hexdigest()
    (args.out / 'single-scenario.json').write_text(json.dumps(result, indent=1) + '\n')
    print(json.dumps({k: result[k] for k in ('status', 'scenarioId', 'mean_score')}))


if __name__ == '__main__':
    main()
