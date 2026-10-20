"""Reminder interrupts in relay rows (benchmark plan §14 M2; reviewer rule 执行, user 2026-10-20).

A reminder or hard-stop interrupt is a high-priority message: the harness abandoning the stream it is receiving to deliver
it (Codex drops the in-flight /responses stream and resends with the message) is expected and never fails or voids a
review. Such a row shows up in the relay as a write error towards the client. `classify` separates it from real
transport errors; a relay error row is a `reminder_interrupt` (not a relay error) when all hold:

 (a) transport_error BrokenPipeError or ConnectionResetError, status 200;
 (b) the deadline record's reminder (or interrupt) status is accepted;
 (c) the request was in flight when the event was sent (started_at < attempted_at <= ended_at) and ended within
     30 s of it (Codex drops the stream at its next stream event, which for a request still in prefill comes later);
 (d) at most one row is exempted per reminder / interrupt;
 (e) for a reminder, the next /responses request starts after attempted_at and within 1 s (either side) of the
     row's end, and is 200 completed;
 (g) the rollout has a user message whose ARW messageId equals the event's receipt.messageId (an interrupt without a
     receipt is exempt from this).
Condition (f), every other validity check passing, belongs to the caller. The abandoned request's tokens are not in the
relay usage, so cost goes by the account's balance delta.

`errors` counts error rows as api_relay.tier_summary does (a transport error or status >= 400; the WebSocket refusal is
not an error), so `relay_errors = len(errors) - len(reminder_interrupts)`."""
import json
from pathlib import Path

CLIENT_ERRORS = ('BrokenPipeError', 'ConnectionResetError')
IN_FLIGHT_MAX, NEXT_WITHIN = 30.0, 1.0


def error_rows(rows):
    return [r for r in rows if not r.get('websocket_refused')
            and (r.get('transport_error') or (r.get('status') or 0) >= 400)]


def deadline_events(records):
    """(kind, event) for every attempted reminder / interrupt of the deadline records (review_deadlines JSON)."""
    return [(kind, record[kind]) for record in records for kind in ('reminder', 'interrupt')
            if record.get(kind) and record[kind].get('attempted_at') is not None]


def rollout_message_ids(lines):
    """ARW messageIds of the user messages in a Codex rollout (JSONL lines)."""
    ids = set()
    for line in lines:
        payload = json.loads(line).get('payload') or {}
        if payload.get('type') == 'message' and payload.get('role') == 'user':
            for part in payload.get('content') or []:
                text = part.get('text') or ''
                if text.startswith('ARW messageId: '):
                    ids.add(text.split('\n', 1)[0].split(': ', 1)[1].strip())
    return ids


def classify(rows, events, message_ids):
    """{'errors', 'reminder_interrupts', 'relay_errors'} for relay `rows`, deadline `events` and rollout message ids."""
    rows = sorted(rows, key=lambda r: r['started_at'])
    errors = error_rows(rows)
    exempt, used = [], set()
    for kind, event in events:
        if event.get('status') != 'accepted':  # (b)
            continue
        receipt = (event.get('receipt') or {}).get('messageId')
        if (kind == 'reminder' or receipt) and receipt not in message_ids:  # (g)
            continue
        at = event['attempted_at']
        for row in errors:
            if id(row) in used:
                continue
            if row.get('transport_error') not in CLIENT_ERRORS or row.get('status') != 200:  # (a)
                continue
            if not (row['started_at'] < at <= row['ended_at'] <= at + IN_FLIGHT_MAX):  # (c)
                continue
            if kind == 'reminder':  # (e)
                nxt = next((o for o in rows if o['started_at'] > row['started_at'] and o is not row
                            and o.get('path') == '/responses'), None)
                if not (nxt and nxt['started_at'] > at and abs(nxt['started_at'] - row['ended_at']) <= NEXT_WITHIN
                        and nxt.get('status') == 200
                        and nxt.get('response_status') == 'completed'):
                    continue
            used.add(id(row))  # (d)
            exempt.append({'event': kind, 'attempted_at': at, 'row': row.get('n'), 'error': row['transport_error'],
                           'ended_minus_attempted': round(row['ended_at'] - at, 3), 'receipt_messageId': receipt})
            break
    return {'errors': len(errors), 'reminder_interrupts': exempt, 'relay_errors': len(errors) - len(exempt)}


def classify_instance(run_dir, sessions):
    """classify() from an arw_measure run directory (relay/*.jsonl, */deadline-*.json) and the rollout paths."""
    run_dir = Path(run_dir)
    rows = [json.loads(line) for f in sorted((run_dir / 'relay').glob('*.jsonl')) for line in f.read_text().splitlines()]
    records = [json.loads(f.read_text()) for f in sorted(run_dir.glob('*/deadline-*.json'))]
    ids = set()
    for s in sessions:
        if s and Path(s).exists():
            ids |= rollout_message_ids(Path(s).read_text().splitlines())
    return classify(rows, deadline_events(records), ids)
