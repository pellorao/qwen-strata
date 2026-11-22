import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.strata.reminder_interrupt import classify, classify_instance, deadline_events, error_side

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
    """Rule (user 2026-10-23): a delivered reminder / interrupt exempts the error of every request in flight then."""
    def check(self, rs, records=(DEADLINE,)):
        return classify(rs, deadline_events(list(records)))

    def test_reminder_interrupt_exempted(self):
        r = self.check(rows())
        self.assertEqual((r['errors'], r['relay_errors']), (1, 0))
        self.assertEqual(r['reminder_interrupts'][0]['row'], 12)
        self.assertEqual(r['reminder_interrupts'][0]['ended_minus_attempted'], 0.106)

    def test_late_relay_end_exempted(self):
        # CStd luna-max-a4: the relay noticed the dropped client 3.79 s after the reminder, the resend began at +0.05 s
        r = self.check(rows((1, 'ended_at', AT + 3.79), (2, 'started_at', AT + 0.05)))
        self.assertEqual(r['relay_errors'], 0)

    def test_any_error_of_the_in_flight_request_exempted(self):
        for change in ((1, 'transport_error', 'URLError'), (1, 'status', 502)):
            self.assertEqual(self.check(rows(change))['relay_errors'], 0)

    def test_request_not_in_flight_counts(self):
        self.assertEqual(self.check(rows((1, 'ended_at', AT - 0.5)))['relay_errors'], 1)
        self.assertEqual(self.check(rows((1, 'started_at', AT + 0.05)))['relay_errors'], 1)

    def test_later_error_counts(self):
        later = dict(BROKEN, n=14, started_at=AT + 60, ended_at=AT + 70)
        r = self.check(rows() + [later])
        self.assertEqual((r['errors'], r['relay_errors']), (2, 1))

    def test_reminder_not_delivered_counts(self):
        rec = copy.deepcopy(DEADLINE)
        rec['reminder']['status'] = 'failed'
        self.assertEqual(self.check(rows(), [rec])['relay_errors'], 1)

    def test_hard_stop_interrupt_exempted(self):
        rec = dict(DEADLINE, reminder=None, interrupt={'attempted_at': AT, 'status': 'accepted'})
        self.assertEqual(self.check(rows()[:2], [rec])['relay_errors'], 0)

    def test_error_side(self):
        self.assertEqual([error_side(r) for r in (BROKEN, {'transport_error': 'URLError'}, {'status': 502}, {'status': 200},
                                                  dict(BROKEN, error_side='upstream'))],
                         ['client', 'upstream', 'upstream', None, 'upstream'])

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
            self.assertEqual(classify_instance(run)['relay_errors'], 0)


if __name__ == '__main__':
    unittest.main()
