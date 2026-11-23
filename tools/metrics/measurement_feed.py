"""Offline final step for a closed, scored stress comparison; never contacts a service.

Only the frozen SR n=10 and cold 4/4 speed protocols below are supported. The
caller supplies the measured version and actual completion time; neither is
inferred from a file's mtime or from the currently deployed service.
"""
import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re


BINDING = {
    'baseline_id': 'local-v0.2.12-stress-2026-11-09',
    'host': 'local',
    'configuration': 'local/IQ3_XXS/MTP/DDR5600/route_prior=1.5/adapt_lag=2',
    'intelligence_protocol': 'Spec Readiness v4.3 / Codex 0.164.0 high / scoreBeforePenalty total / blind Opus high',
    'speed_protocols': {tier: f'stress {tier} / decode all requests / cold prefill initial / engine token sums per seconds'
                        for tier in ('125k', '150k')},
}
DEFAULT_OUTPUT = Path.home() / 'projects/.tasks/qwen-strata/measurements.jsonl'


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def completion_time(value):
    if finite_number(value) and value > 0:
        return value
    if isinstance(value, str) and re.search(r'T\d{2}:\d{2}:\d{2}', value):
        try:
            moment = datetime.fromisoformat(value)
            if moment.timestamp() > 0:
                return moment.timestamp()
        except (ValueError, OverflowError, OSError):
            pass
    raise ValueError('ts must be the actual completion time, Unix seconds or full ISO datetime')


def speed_value(text, section, tier, version):
    sections = re.findall(r'^== ' + re.escape(section) + r'\n((?:(?!^== ).*(?:\n|$))*)', text, re.M)
    if len(sections) != 1:
        raise ValueError('Missing or ambiguous frozen speed section: ' + section)
    matches = re.findall(r'^' + re.escape(tier) + r' n=4/4 ' + re.escape(version)
                         + r'=([0-9]+(?:\.[0-9]+)?)(?=\s|$)', sections[0], re.M)
    if len(matches) != 1 or not finite_number(float(matches[0])) or float(matches[0]) <= 0:
        raise ValueError('Missing or invalid complete speed result: ' + tier + '/' + section)
    return float(matches[0])


def finalize(binding, scores_path, speed_path, output=DEFAULT_OUTPUT):
    """Validate the entire closed batch before appending two flat contract rows.

    Bindings are explicit and fail closed. A new host/configuration/protocol needs
    a separately reviewed baseline instead of silently inheriting this one.
    Source hashes refer to the exact bytes parsed, and no raw report is exported.
    """
    if any(binding.get(key) != value for key, value in BINDING.items()):
        raise ValueError('Batch binding differs from the registered baseline')
    version = binding.get('version')
    if not isinstance(version, str) or not version.strip():
        raise ValueError('Measured version is required')
    ts = completion_time(binding.get('ts'))
    score_bytes = Path(scores_path).read_bytes()
    speed_bytes = Path(speed_path).read_bytes()
    scores = json.loads(score_bytes)
    summary = scores.get('summary', {}) if isinstance(scores, dict) else {}
    total = summary.get('total', {}) if isinstance(summary, dict) else {}
    if not isinstance(total, dict):
        raise ValueError('Expected an SR total summary object')
    score = total.get('mean_' + version)
    if total.get('n') != [10, 10] or not finite_number(score) or not 0 <= score <= 1:
        raise ValueError('Expected complete SR n=10 per version and a finite score in [0,1]')
    text = speed_bytes.decode('utf-8')
    rows = []
    for tier, protocol in BINDING['speed_protocols'].items():
        rows.append({key: binding[key] for key in
                     ('baseline_id', 'host', 'version', 'configuration', 'intelligence_protocol')})
        rows[-1].update(ts=ts, context_tier=tier, speed_protocol=protocol,
                        intelligence_score=score,
                        decode_tok_s=speed_value(text, 'decode all requests', tier, version),
                        prefill_tok_s=speed_value(text, 'cold prefill initial', tier, version),
                        score_source_sha256=hashlib.sha256(score_bytes).hexdigest(),
                        speed_source_sha256=hashlib.sha256(speed_bytes).hexdigest())
    payload = ''.join(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n' for row in rows)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('a+b') as stream:
        if stream.tell():
            stream.seek(-1, 2)
            if stream.read(1) != b'\n':
                payload = '\n' + payload
        stream.write(payload.encode('utf-8'))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--binding', type=Path, required=True,
                        help='Public frozen batch bindings plus version and actual completion ts; no credentials')
    parser.add_argument('--scores', type=Path, required=True)
    parser.add_argument('--speed', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    finalize(json.loads(args.binding.read_text(encoding='utf-8')), args.scores, args.speed, args.output)
    print('Appended completed stress measurement: 125k and 150k')


if __name__ == '__main__':
    main()
