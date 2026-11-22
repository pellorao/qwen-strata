"""Engine-log speed summary for a time window; prints aggregates only (no paths, config or host data).

Engine token records carry no timestamp; only the `engine started` lines do. Inside one engine run the n-th token
record is matched to the n-th generation request completed in frontend.log (a timestamped POST /strata/v1/* with
status 200), which gives each record a time. A count difference between the two is reported as `unaligned`.
Times are local, like both logs; timezone-aware input is converted to local time.
"""
import argparse
import hashlib
import re
from datetime import datetime

from tools.metrics.strata_tokens import engine_rates, parse_engine_log, sum_engine_tokens

START = re.compile(r'\[strata\] (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) engine started')
REQUEST = re.compile(r'(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\.\d+ \S+ "POST /strata/v1/\S+ HTTP/[\d.]+" 200')
FORMAT = '%Y-%m-%d %H:%M:%S'


class SummaryError(Exception):
    """Message is fixed text, safe to print."""


def local_time(text):
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        raise SummaryError('Time must be ISO 8601, e.g. 2026-11-09T06:15:00') from None
    return moment.astimezone().replace(tzinfo=None) if moment.tzinfo else moment


def summarize(engine_log, frontend_log, since, until=None, min_context=None, max_context=None):
    """Aggregate engine records whose matched request completed in [since, until].

    min_context/max_context keep only requests whose total input tokens (cached + uncached) lie in that range."""
    until = until or datetime.max
    lines = engine_log.splitlines()
    starts = [(i, datetime.strptime(m.group(1), FORMAT)) for i, line in enumerate(lines)
              if (m := START.match(line))]
    if not starts:
        raise SummaryError('Engine log has no timestamped engine start; it may have been rotated')
    requests = [datetime.strptime(m.group(1), FORMAT) for line in frontend_log.splitlines()
                if (m := REQUEST.match(line))]
    chosen, unaligned, configs = [], 0, set()
    for n, (first, begin) in enumerate(starts):
        end_line, end = (starts[n + 1] if n + 1 < len(starts) else (len(lines), datetime.max))
        if end <= since or begin > until:
            continue
        times = [t for t in requests if begin <= t < end]
        if not any(since <= t <= until for t in times):
            continue
        # Same fingerprint = same start line (arguments) apart from its timestamp; the line itself is never printed.
        configs.add(hashlib.sha256(START.sub('', lines[first], count=1).encode()).hexdigest()[:8])
        records = parse_engine_log('\n'.join(lines[first:end_line]))
        unaligned += abs(len(records) - len(times))
        chosen += [r for r, t in zip(records, times) if since <= t <= until]
    in_window = len(chosen)
    chosen = [r for r in chosen if (min_context is None or r['input'] >= min_context)
              and (max_context is None or r['input'] <= max_context)]
    tokens = sum_engine_tokens(chosen)
    rates = engine_rates(chosen)
    reuse = tokens and tokens['cached_input'] + tokens['uncached_input']
    return {'since': since.isoformat(), 'until': None if until == datetime.max else until.isoformat(),
            'requests': len(chosen), 'requests_in_window': in_window,
            'context_range': [min_context, max_context], 'unaligned': unaligned,
            'engine_configs': sorted(configs),
            'covered_from_start': since >= starts[0][1],
            'uncached_input_tokens': tokens and tokens['uncached_input'],
            'cached_input_tokens': tokens and tokens['cached_input'],
            'output_tokens': tokens and tokens['output'],
            'input_seconds': rates['engine_input_seconds'], 'decode_seconds': rates['engine_decode_seconds'],
            'uncached_input_tok_per_s': rates['engine_input_tokens_per_second'],
            'output_tok_per_s': rates['engine_output_tokens_per_second'],
            'reuse_ratio': reuse and tokens['cached_input'] / reuse}


def render(summary):
    def number(value, digits=1):
        return 'n/a' if value is None else f'{value:.{digits}f}'
    rows = [('window', f"{summary['since']} .. {summary['until'] or 'now'}"),
            ('context range (total input tokens)', '..'.join('any' if v is None else str(v) for v in summary['context_range'])),
            ('requests in window / in context range', f"{summary['requests_in_window']} / {summary['requests']}"),
            ('uncached input tok/s', number(summary['uncached_input_tok_per_s'])),
            ('output tok/s', number(summary['output_tok_per_s'])),
            ('reuse ratio', number(summary['reuse_ratio'], 3)),
            ('tokens uncached/cached/output', '/'.join(str(summary[k]) for k in (
                'uncached_input_tokens', 'cached_input_tokens', 'output_tokens'))),
            ('engine seconds input/decode', f"{number(summary['input_seconds'])}/{number(summary['decode_seconds'])}"),
            ('unaligned records/requests', summary['unaligned']),
            ('engine start fingerprints', ','.join(summary['engine_configs']) or 'none')]
    if not summary['covered_from_start']:
        rows.append(('note', 'window starts before the oldest engine start in the log (rotated?)'))
    return '\n'.join(f'{name}: {value}' for name, value in rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--since', required=True, help='ISO 8601 start of the window')
    parser.add_argument('--min-context', type=int, help='keep requests with at least this many total input tokens')
    parser.add_argument('--max-context', type=int, help='keep requests with at most this many total input tokens')
    parser.add_argument('--until', help='ISO 8601 end of the window (default: now)')
    args = parser.parse_args()
    try:
        since, until = local_time(args.since), args.until and local_time(args.until)
        from tools.ops.measurement_host import MeasurementHost
        host = MeasurementHost()
        engine = host.log_path(host.deployment['models'][0]).read_bytes().decode('utf-8', 'replace')
        frontend = host.frontend_log_path().read_bytes().decode('utf-8', 'replace')
        print(render(summarize(engine, frontend, since, until, args.min_context, args.max_context)))
    except SummaryError as error:
        raise SystemExit(f'engine_speed: {error}')
    except Exception as error:
        # Other messages may carry paths or host data; name only the class.
        raise SystemExit(f'engine_speed: engine log or frontend log unavailable ({type(error).__name__})')


if __name__ == '__main__':
    main()
