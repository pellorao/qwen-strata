import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.reviewer.reminder_interrupt import classify, classify_instance, deadline_events, rollout_message_ids

# Shapes of DeepSeek CS codex-low-a1 (2026-10-20): the reminder steer at attempted_at, the abandoned stream's
# BrokenPipeError 0.106 s later, the resent request starting before it ended.
AT = 1792502292.1240134
MID = 'ccb65804-7231-454d-86da-4a0cdd649698'
BEFORE = {'n': 11, 'started_at': 1792502269.079175, 'ended_at': 1792502281.9639137, 'method': 'POST', 'path': '/responses',
          'status': 200, 'model': 'deepseek-flash', 'service_tier': 'default', 'response_status': 'completed'}
BROKEN = {'n': 12, 'started_at': 1792502281.9903247, 'ended_at': 1792502292.229658, 'method': 'POST', 'path': '/responses',
          'status': 200, 'transport_error': 'BrokenPipeError'}
NEXT = {'n': 13, 'started_at': 1792502292.1960475, 'ended_at': 1792502295.0567858, 'method': 'POST', 'path': '/responses',
        'status': 200, 'model': 'deepseek-flash', 'service_tier': 'default', 'response_status': 'completed'}
DEADLINE = {'messageId': 'fa98b629-8aff-4fda-8ea3-98b420334b8f', 'phase': 'initial',
            'reminder': {'attempted_at': AT, 'operation': 'send_message', 'status': 'accepted',
                         'receipt': {'messageId': MID, 'deliveryStatus': 'accepted'}},
            'interrupt': None}


def rows(*changes):
    out = [copy.deepcopy(r) for r in (BEFORE, BROKEN, NEXT)]
    for n, key, value in changes:
        out[n][key] = value
    return out


class ReminderInterrupt(unittest.TestCase):
    def check(self, rs, records=(DEADLINE,), ids=(MID,)):
        return classify(rs, deadline_events(list(records)), set(ids))

    def test_reminder_interrupt_exempted(self):
        r = self.check(rows())
        self.assertEqual((r['errors'], r['relay_errors']), (1, 0))
        self.assertEqual(r['reminder_interrupts'][0]['row'], 12)
        self.assertEqual(r['reminder_interrupts'][0]['ended_minus_attempted'], 0.106)

    def test_connection_reset_exempted(self):
        self.assertEqual(self.check(rows((1, 'transport_error', 'ConnectionResetError')))['relay_errors'], 0)

    def test_upstream_urlerror_counts(self):
        self.assertEqual(self.check(rows((1, 'transport_error', 'URLError')))['relay_errors'], 1)

    def test_far_from_attempted_at_counts(self):
        self.assertEqual(self.check(rows((1, 'ended_at', AT + 5)))['relay_errors'], 1)
        self.assertEqual(self.check(rows((1, 'ended_at', AT - 0.5)))['relay_errors'], 1)

    def test_status_not_200_counts(self):
        self.assertEqual(self.check(rows((1, 'status', 502)))['relay_errors'], 1)

    def test_next_request_failing_counts(self):
        self.assertEqual(self.check(rows((2, 'response_status', 'failed')))['relay_errors'], 1)
        self.assertEqual(self.check(rows((2, 'status', 500)))['relay_errors'], 2)
        self.assertEqual(self.check(rows((2, 'started_at', BROKEN['ended_at'] + 2)))['relay_errors'], 1)
        self.assertEqual(self.check(rows()[:2])['relay_errors'], 1)

    def test_second_row_for_one_reminder_counts(self):
        second = dict(BROKEN, n=14, started_at=BROKEN['started_at'] + 1, ended_at=AT + 0.3)
        r = self.check(rows() + [second])
        self.assertEqual((r['errors'], r['relay_errors'], len(r['reminder_interrupts'])), (2, 1, 1))

    def test_reminder_not_accepted_counts(self):
        rec = copy.deepcopy(DEADLINE)
        rec['reminder']['status'] = 'failed'
        self.assertEqual(self.check(rows(), [rec])['relay_errors'], 1)

    def test_message_not_in_rollout_counts(self):
        self.assertEqual(self.check(rows(), ids=())['relay_errors'], 1)

    def test_hard_stop_interrupt_needs_no_next_request(self):
        rec = dict(DEADLINE, reminder=None, interrupt={'attempted_at': AT, 'status': 'accepted'})
        self.assertEqual(self.check(rows()[:2], [rec], ids=())['relay_errors'], 0)

    def test_websocket_refusal_not_an_error(self):
        ws = {'n': 1, 'started_at': 1, 'ended_at': 1, 'status': 426, 'websocket_refused': True}
        self.assertEqual(self.check([ws] + rows())['errors'], 1)

    def test_classify_instance_from_files(self):
        with tempfile.TemporaryDirectory() as d:
            run = Path(d) / 'run'
            (run / 'relay').mkdir(parents=True)
            (run / 'relay/relay.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows()))
            (run / 'inst-1').mkdir()
            (run / 'inst-1/deadline-x.json').write_text(json.dumps(DEADLINE))
            session = Path(d) / 'rollout.jsonl'
            msg = {'type': 'response_item', 'payload': {'type': 'message', 'role': 'user', 'content': [
                {'type': 'input_text', 'text': f'ARW messageId: {MID}\n\n请立即整理已经取得的审查结果'}]}}
            session.write_text(json.dumps(msg) + '\n' + json.dumps({'type': 'event_msg', 'payload': {}}) + '\n')
            self.assertEqual(rollout_message_ids(session.read_text().splitlines()), {MID})
            self.assertEqual(classify_instance(run, [str(session)])['relay_errors'], 0)


if __name__ == '__main__':
    unittest.main()
