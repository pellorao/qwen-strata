import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.reviewer.stream_cut import classify, classify_instance, rollout_entries

# Shapes of DeepSeek SR codex-max-a4 h0 (2026-10-21): n28 cut after 200 (IncompleteRead), n29 resent 0.23 s later.
PREV = {'n': 27, 'started_at': 1792540672.560967, 'ended_at': 1792540712.1395853, 'path': '/responses', 'status': 200,
        'response_status': 'completed'}
CUT = {'n': 28, 'started_at': 1792540712.2024486, 'ended_at': 1792540720.435319, 'path': '/responses', 'status': 200,
       'transport_error': 'IncompleteRead'}
NEXT = {'n': 29, 'started_at': 1792540720.6604033, 'ended_at': 1792540731.4929523, 'path': '/responses', 'status': 200,
        'response_status': 'completed'}


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat().replace('+00:00', 'Z')


def line(t, kind, ptype):
    return json.dumps({'timestamp': iso(t), 'type': kind, 'payload': {'type': ptype}})


# rollout: previous response's items just before the cut started, a token_count when it broke, the retry's items after
LINES = [line(CUT['started_at'] - 0.06, 'response_item', 'function_call'),
         line(CUT['started_at'] - 0.01, 'response_item', 'function_call_output'),
         line(CUT['ended_at'] + 0.02, 'event_msg', 'token_count'),
         line(NEXT['started_at'] + 18, 'response_item', 'reasoning')]


def rows(*changes):
    out = [copy.deepcopy(r) for r in (PREV, CUT, NEXT)]
    for n, key, value in changes:
        out[n][key] = value
    return out


class StreamCut(unittest.TestCase):
    def check(self, rs, lines=LINES, skip=()):
        return classify(rs, rollout_entries(lines), skip)

    def test_transparent_retry_exempted(self):
        r = self.check(rows())
        self.assertEqual([x['row'] for x in r['stream_cut_retries']], [28])
        self.assertEqual(r['stream_cut_retries'][0]['excluded_seconds'], 8.458)
        self.assertEqual(r['rejected'], [])

    def test_partial_output_in_rollout_rejected(self):
        # SR codex-low-a1 n49: the cut stream had completed a reasoning item, written 2 s after the start
        lines = LINES + [line(CUT['started_at'] + 2.0, 'response_item', 'reasoning'),
                         line(CUT['started_at'] + 2.0, 'event_msg', 'item_completed')]
        r = self.check(rows(), lines)
        self.assertEqual(r['stream_cut_retries'], [])
        self.assertEqual(r['rejected'][0]['written'], ['event_msg/item_completed', 'response_item/reasoning'])

    def test_no_http_status_counts(self):
        # RemoteDisconnected before any status (SR codex-low-a1 n571): not a cut after 200
        r = self.check(rows((1, 'status', None), (1, 'transport_error', 'RemoteDisconnected')))
        self.assertEqual((r['stream_cut_retries'], r['rejected']), ([], []))

    def test_client_side_errors_left_to_reminder_classifier(self):
        for err in ('BrokenPipeError', 'ConnectionResetError'):
            r = self.check(rows((1, 'transport_error', err)))
            self.assertEqual((r['stream_cut_retries'], r['rejected']), ([], []))

    def test_late_or_failed_retry_rejected(self):
        self.assertEqual(self.check(rows((2, 'started_at', CUT['ended_at'] + 6)))['stream_cut_retries'], [])
        self.assertEqual(self.check(rows((2, 'response_status', 'incomplete')))['stream_cut_retries'], [])
        self.assertEqual(self.check(rows()[:2])['rejected'][0]['next_row'], None)

    def test_skip_rows(self):
        self.assertEqual(self.check(rows(), skip={28})['stream_cut_retries'], [])

    def test_classify_instance_reads_relay_and_rollouts(self):
        with tempfile.TemporaryDirectory() as d:
            run = Path(d) / 'run'
            (run / 'relay').mkdir(parents=True)
            (run / 'relay/relay.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows()))
            roll = Path(d) / 'rollout.jsonl'
            roll.write_text('\n'.join(LINES) + '\n')
            r = classify_instance(run, [str(roll), None, str(Path(d) / 'missing.jsonl')])
            self.assertEqual([x['row'] for x in r['stream_cut_retries']], [28])


if __name__ == '__main__':
    unittest.main()
