"""Reminder interrupts in relay rows (benchmark plan §14 M2; reviewer rule 执行, user 2026-10-20, rule simplified 2026-10-23).

A reminder or hard-stop interrupt is a high-priority message we send: the harness abandoning the stream it is receiving
to deliver it (Codex drops the in-flight /responses stream and resends with the message) is expected and never fails or
voids a review. Rule (user 2026-10-23): when a reminder / interrupt is delivered (status accepted), the error row of any
request in flight at that moment (started_at < attempted_at <= ended_at) is the interrupt's, not a relay error. The
abandoned request's outcome never reaches the model, so nothing else about it is checked. The relay notices the dropped
client only at its next write, so the row's ended_at may lag the resend by seconds (CStd luna-max-a4: 3.7 s).
The abandoned request's tokens are not in the relay usage, so cost goes by the account's balance delta.

`errors` counts error rows as api_relay.tier_summary does (a transport error or status >= 400; the WebSocket refusal is
not an error), so `relay_errors = len(errors) - len(reminder_interrupts)`."""
import json
from pathlib import Path

CLIENT_ERRORS = ('BrokenPipeError', 'ConnectionResetError')


def error_side(row):
    """'client' or 'upstream' for an error row; None when the row is not an error.

    api_relay writes `error_side` on every error row. Older rows lack it: a transport error is then client-side exactly
    when it is BrokenPipeError / ConnectionResetError, otherwise upstream; a status >= 400 without a transport error is
    upstream."""
    if row.get('error_side'):
        return row['error_side']
    if row.get('transport_error'):
        return 'client' if row['transport_error'] in CLIENT_ERRORS else 'upstream'
    return 'upstream' if (row.get('status') or 0) >= 400 else None


def error_rows(rows):
    return [r for r in rows if not r.get('websocket_refused')
            and (r.get('transport_error') or (r.get('status') or 0) >= 400)]


def deadline_events(records):
    """(kind, event) for every attempted reminder / interrupt of the deadline records (review_deadlines JSON)."""
    return [(kind, record[kind]) for record in records for kind in ('reminder', 'interrupt')
            if record.get(kind) and record[kind].get('attempted_at') is not None]


def classify(rows, events):
    """{'errors', 'reminder_interrupts', 'relay_errors'} for relay `rows` and deadline `events`."""
    errors = sorted(error_rows(rows), key=lambda r: r['started_at'])
    exempt, used = [], set()
    for kind, event in events:
        if event.get('status') != 'accepted':
            continue
        at = event['attempted_at']
        receipt = (event.get('receipt') or {}).get('messageId')
        for row in errors:
            if id(row) not in used and row['started_at'] < at <= row['ended_at']:
                used.add(id(row))
                exempt.append({'event': kind, 'attempted_at': at, 'row': row.get('n'),
                               'error': row.get('transport_error') or row.get('status'),
                               'ended_minus_attempted': round(row['ended_at'] - at, 3), 'receipt_messageId': receipt})
    return {'errors': len(errors), 'reminder_interrupts': exempt, 'relay_errors': len(errors) - len(exempt)}


def classify_instance(run_dir):
    """classify() from an arw_measure run directory (relay/*.jsonl, */deadline-*.json)."""
    run_dir = Path(run_dir)
    rows = [json.loads(line) for f in sorted((run_dir / 'relay').glob('*.jsonl')) for line in f.read_text().splitlines()]
    records = [json.loads(f.read_text()) for f in sorted(run_dir.glob('*/deadline-*.json'))]
    return classify(rows, deadline_events(records))
