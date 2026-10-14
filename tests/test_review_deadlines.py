from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.reviewer.review_deadlines import ReviewDeadline


class Machine:
    def __init__(self, failure=False):
        self.calls = []
        self.failure = failure

    def call(self, operation, value):
        self.calls.append((operation, value))
        if self.failure:
            raise RuntimeError('Transport outcome unknown')
        return {'runId': value['runId'], 'accepted': True,
                'deliveryStatus': 'accepted', 'messageId': 'reminder'}


def observation(turn='one', completed=False):
    return {'runId': 'run', 'threadId': 'root',
        'completion': {'status': 'ready'} if completed else None,
        'snapshot': {'factsComplete': True, 'members': [
            {'threadId': 'root', 'state': 'active', 'turnId': turn}]}}


class ReviewDeadlineTests(unittest.TestCase):
    def test_initial_reminder_then_interrupt_preserve_deadline_and_current_turn(self):
        with tempfile.TemporaryDirectory() as directory:
            now = [3299]
            timer = ReviewDeadline(directory, {'runId': 'run', 'messageId': 'message'},
                0, clock=lambda: now[0])
            machine = Machine()
            timer.advance(machine, observation())
            self.assertEqual(machine.calls, [])
            now[0] = 3300
            timer.advance(machine, observation())
            self.assertEqual(machine.calls[0][0], 'send_message')
            self.assertIn('300秒', machine.calls[0][1]['message'])
            restored = ReviewDeadline(directory, {'runId': 'run', 'messageId': 'message'},
                3000, clock=lambda: now[0])
            restored.advance(machine, observation())
            self.assertEqual(len(machine.calls), 1)
            now[0] = 3600
            restored.advance(machine, observation(turn='current'))
            self.assertEqual(machine.calls[-1], ('interrupt_agent', {'runId': 'run', 'turnId': 'current'}))
            self.assertEqual(restored.facts()['hard_deadline_at'], 3600)

    def test_revision_uses_fifteen_minutes_and_warns_at_ten(self):
        with tempfile.TemporaryDirectory() as directory:
            now = [700]
            timer = ReviewDeadline(directory, {'runId': 'run', 'messageId': 'repair'},
                100, phase='revision', clock=lambda: now[0])
            machine = Machine()
            timer.advance(machine, observation())
            self.assertEqual(machine.calls[0][0], 'send_message')
            now[0] = 1000
            timer.advance(machine, observation())
            self.assertEqual(machine.calls[1][0], 'interrupt_agent')

    def test_finished_task_is_neither_steered_nor_interrupted(self):
        with tempfile.TemporaryDirectory() as directory:
            timer = ReviewDeadline(directory, {'runId': 'run', 'messageId': 'done'},
                0, clock=lambda: 5000)
            machine = Machine()
            timer.advance(machine, observation(completed=True))
            self.assertEqual(machine.calls, [])

    def test_late_attachment_interrupts_without_granting_new_five_minutes(self):
        with tempfile.TemporaryDirectory() as directory:
            timer = ReviewDeadline(directory, {'runId': 'run', 'messageId': 'late'},
                0, clock=lambda: 4000)
            machine = Machine()
            timer.advance(machine, observation())
            self.assertEqual([x[0] for x in machine.calls], ['interrupt_agent'])

    def test_unknown_message_outcome_is_not_automatically_resent(self):
        with tempfile.TemporaryDirectory() as directory:
            accepted = {'runId': 'run', 'messageId': 'unknown'}
            timer = ReviewDeadline(directory, accepted, 0, clock=lambda: 3300)
            machine = Machine(failure=True)
            with self.assertRaises(RuntimeError):
                timer.advance(machine, observation())
            restored = ReviewDeadline(directory, accepted, 0, clock=lambda: 3301)
            restored.advance(machine, observation())
            self.assertEqual(len(machine.calls), 1)
            self.assertEqual(restored.facts()['reminder']['status'], 'unknown')

    def test_malformed_receipt_is_unknown_and_not_claimed_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            timer = ReviewDeadline(directory, {'runId': 'run', 'messageId': 'bad'},
                0, clock=lambda: 3300)
            class BadMachine:
                def call(self, operation, payload):
                    return {'runId': 'someone-else', 'deliveryStatus': 'accepted'}
            with self.assertRaises(RuntimeError):
                timer.advance(BadMachine(), observation())
            self.assertEqual(timer.facts()['reminder']['status'], 'unknown')


    def test_model_offline_time_does_not_consume_reminder_or_cutoff_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            wall=[50000];alive=[3299]
            timer=ReviewDeadline(directory,{'runId':'run','messageId':'alive'},0,
                clock=lambda:wall[0],alive_elapsed=lambda:alive[0])
            machine=Machine();timer.advance(machine,observation())
            self.assertEqual(machine.calls,[])
            wall[0]+=100000;timer.advance(machine,observation())
            self.assertEqual(machine.calls,[])
            alive[0]=3300;timer.advance(machine,observation())
            self.assertEqual(machine.calls[-1][0],'send_message')
            self.assertIn('审核工作时间',machine.calls[-1][1]['message'])
            wall[0]+=10000;alive[0]=3599;timer.advance(machine,observation())
            self.assertEqual(len(machine.calls),1)
            alive[0]=3600;timer.advance(machine,observation())
            self.assertEqual(machine.calls[-1][0],'interrupt_agent')
    def test_selection_limit_keeps_five_minute_lead_and_survives_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            now = [599]
            accepted = {'runId': 'run', 'messageId': 'limited'}
            timer = ReviewDeadline(directory, accepted, 0, clock=lambda: now[0], limit_seconds=900)
            machine = Machine(); timer.advance(machine, observation())
            self.assertEqual(machine.calls, [])
            now[0] = 600; timer.advance(machine, observation())
            self.assertIn('最多5分钟', machine.calls[0][1]['message'])
            restored = ReviewDeadline(directory, accepted, 0, clock=lambda: 900, limit_seconds=900)
            restored.advance(machine, observation())
            self.assertEqual(machine.calls[-1][0], 'interrupt_agent')
            with self.assertRaises(ValueError):
                ReviewDeadline(directory, accepted, 0, limit_seconds=1200)

    def test_short_limit_warns_at_half_and_states_the_real_lead(self):
        with tempfile.TemporaryDirectory() as directory:
            now = [239]
            timer = ReviewDeadline(directory, {'runId': 'run', 'messageId': 'short'},
                0, clock=lambda: now[0], limit_seconds=480)
            machine = Machine(); timer.advance(machine, observation())
            self.assertEqual(machine.calls, [])
            now[0] = 240; timer.advance(machine, observation())
            message = machine.calls[0][1]['message']
            self.assertIn('最多240秒', message); self.assertNotIn('5分钟', message)
            now[0] = 480; timer.advance(machine, observation())
            self.assertEqual(machine.calls[-1][0], 'interrupt_agent')

    def test_invalid_limit_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for bad in (0, -5, '900', True):
                with self.assertRaises(ValueError):
                    ReviewDeadline(directory, {'runId': 'run', 'messageId': 'bad'}, 0, limit_seconds=bad)


if __name__ == '__main__':
    unittest.main()
