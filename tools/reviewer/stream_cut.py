"""Upstream stream cuts retried transparently by the harness (ruling 2026-10-21, benchmarks/reviewer-suite-v1/rulings.md).

A cut is the server's fault and the retry only reconnects; when the model saw the same input the instance stays valid.
A relay error row is a `stream_cut_retry` (not a relay error) when all hold:

 (a) status 200 and an upstream-side transport error (not BrokenPipeError / ConnectionResetError, which are the
     client dropping the stream and belong to tools.reviewer.reminder_interrupt);
 (b) the cut stream wrote nothing into the rollout: between the row's start and the retry's start the rollouts have no
     entry other than an event_msg token_count (no response_item, user message, turn_context or item event);
 (c) the next /responses request starts within NEXT_WITHIN seconds of the row's end and is 200 completed.
Every other validity check passing belongs to the caller, as do rows already exempted as reminder interrupts.

The relay keeps no request bodies, so "the same request" is shown by (b): the retry is built from an unchanged history.
For scoring, the cut request's time (its start to the retry's start, `excluded_seconds`) and its tokens are left out;
cost goes per completed request (the cut row has no usage)."""
import json
from datetime import datetime
from pathlib import Path

from tools.reviewer.reminder_interrupt import CLIENT_ERRORS, error_rows

NEXT_WITHIN = 5.0
ALLOWED = {('event_msg', 'token_count')}


def rollout_entries(lines):
    """(epoch seconds, type, payload type) of every timestamped rollout line."""
    out = []
    for line in lines:
        o = json.loads(line)
        if o.get('timestamp'):
            t = datetime.fromisoformat(o['timestamp'].replace('Z', '+00:00')).timestamp()
            out.append((t, o.get('type'), (o.get('payload') or {}).get('type')))
    return out


def classify(rows, entries, skip=()):
    """{'stream_cut_retries': [...], 'rejected': [...]} for relay `rows`, rollout `entries` and row numbers to skip."""
    rows = sorted(rows, key=lambda r: r['started_at'])
    retries, rejected = [], []
    for row in error_rows(rows):
        if row.get('n') in skip:
            continue
        if row.get('status') != 200 or not row.get('transport_error') or row['transport_error'] in CLIENT_ERRORS:  # (a)
            continue
        nxt = next((o for o in rows if o['started_at'] > row['started_at'] and o is not row
                    and o.get('path') == row.get('path')), None)
        info = {'row': row.get('n'), 'error': row['transport_error'], 'next_row': nxt and nxt.get('n')}
        if not (nxt and 0 <= nxt['started_at'] - row['ended_at'] <= NEXT_WITHIN and nxt.get('status') == 200
                and nxt.get('response_status') == 'completed'):  # (c)
            rejected.append({**info, 'reason': 'no prompt 200 completed retry'})
            continue
        written = sorted({f'{a}/{b}' for t, a, b in entries
                          if row['started_at'] < t < nxt['started_at'] and (a, b) not in ALLOWED})
        if written:  # (b)
            rejected.append({**info, 'reason': 'cut stream wrote into the rollout', 'written': written})
            continue
        retries.append({**info, 'excluded_seconds': round(nxt['started_at'] - row['started_at'], 3),
                        'retry_gap': round(nxt['started_at'] - row['ended_at'], 3)})
    return {'stream_cut_retries': retries, 'rejected': rejected}


def classify_instance(run_dir, sessions, skip=()):
    """classify() from an arw_measure run directory (relay/*.jsonl) and the rollout paths."""
    run_dir = Path(run_dir)
    rows = [json.loads(line) for f in sorted((run_dir / 'relay').glob('*.jsonl')) for line in f.read_text().splitlines()]
    entries = []
    for s in sessions:
        if s and Path(s).exists():
            entries += rollout_entries(Path(s).read_text().splitlines())
    return classify(rows, entries, skip)
