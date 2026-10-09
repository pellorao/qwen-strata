import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.loop.progress_guard import (initial_state, observe_commands, observe_artifact,
                            observe_incomplete_end, failure_fact)
from tools.loop.native_command_evidence import NativeCommandEvidence
from tools.loop.command_loop_guard import artifact_observation, observe_command_loops, progress_continuation_feedback


def fact(number, command='read a', output='unchanged', **more):
    return {'threadId': 'root', 'turnId': 'turn', 'itemId': str(number), 'position': number,
            'command': command, 'cwd': '/repo', 'exitCode': 1, 'output': output,
            'outputDigest': hashlib.sha256(output.encode()).hexdigest(), **more}


def syntax(number, label='check', value=5, **more):
    line = f'console.log("{label}", fn({value});'
    command = f"node --input-type=module -e '\n{line}\nconsole.log({number});\n'"
    output = f'file:///repo/[eval1]:2\n{line}\n    ^\n\nSyntaxError: missing ) after argument list\nNode.js v24.20.0\n'
    return fact(number, command, output, **more)


class ProgressGuardTests(unittest.TestCase):
    def setUp(self):
        self.state = initial_state(['task', 'initial'])

    def test_modified_scripts_same_error_context_trigger_once_with_specific_feedback(self):
        self.assertEqual(observe_commands(self.state, [syntax(1)], 'root'), [])
        hints = observe_commands(self.state, [syntax(1), syntax(2, label='changed')], 'root')
        self.assertEqual(hints[0]['kind'], 'same-failure')
        self.assertIn('minimal probe', hints[0]['instruction'])
        self.assertIn('fn(', hints[0]['instruction'])
        self.assertEqual(observe_commands(self.state, [syntax(3, label='third')], 'root'), [])

    def test_changed_actual_literal_is_not_merged_as_same_failure(self):
        self.assertEqual(observe_commands(self.state, [syntax(1, value=5), syntax(2, value=6)], 'root'), [])

    def test_changed_error_expression_and_error_type_are_new_evidence(self):
        a = syntax(1)
        b = syntax(2)
        b['command'] = b['command'].replace('fn(', 'other(')
        b['output'] = b['output'].replace('fn(', 'other(')
        c = syntax(3)
        c['output'] = c['output'].replace('SyntaxError:', 'ReferenceError:')
        self.assertEqual(observe_commands(self.state, [a, b, c], 'root'), [])

    def test_runtime_errors_require_harness_input_version(self):
        f = fact(1, "python3 -c 'a=[0]; print(a[2])'",
                 'Traceback (most recent call last):\n  File "<stdin>", line 1, in <module>\nIndexError: list index out of range\n')
        self.assertIsNone(failure_fact(f))
        self.assertIsNotNone(failure_fact(f | {'inputVersion': 'verified-input-sha'}))

    def test_digest_only_facts_keep_exact_three_repeat_rule(self):
        facts = [fact(i) for i in range(3)]
        for f in facts:
            del f['output']
        hints = observe_commands(self.state, facts, 'root')
        self.assertEqual([h['kind'] for h in hints], ['same-command-window'])

    def test_nonconsecutive_repetition_within_window_is_detected(self):
        facts = [fact(1), fact(2, 'other'), fact(3), fact(4, 'another'), fact(5)]
        hints = observe_commands(self.state, facts, 'root')
        self.assertEqual(len(hints), 1)
        self.assertEqual(len(hints[0]['evidence_ids']), 3)

    def test_old_repetitions_outside_window_do_not_trigger(self):
        facts = [fact(1), fact(2)] + [fact(i, f'new-{i}') for i in range(3, 11)] + [fact(11)]
        self.assertEqual(observe_commands(self.state, facts, 'root'), [])

    def test_periodic_expected_failures_and_other_threads_are_excluded(self):
        fs = [syntax(1, periodic=True), syntax(2, expectedFailure=True), syntax(3, threadId='foreign')]
        self.assertEqual(observe_commands(self.state, fs, 'root'), [])

    def test_unavailable_output_or_exit_is_not_counted_as_equal(self):
        fs = [fact(i, exitCode=None) for i in range(4)]
        self.assertEqual(observe_commands(self.state, fs, 'root'), [])
        self.assertEqual(observe_commands(self.state, [fact(10), fact(11),
            fact(12, exitCode=None), fact(13)], 'root'), [])

    def test_mirrors_and_restore_do_not_replay_hints(self):
        fs = [syntax(1), syntax(2)]
        self.assertEqual(len(observe_commands(self.state, fs, 'root')), 1)
        restored = json.loads(json.dumps(self.state))
        self.assertEqual(observe_commands(restored, fs, 'root'), [])

    def test_unknown_artifact_does_not_mean_empty_and_changed_artifact_is_progress(self):
        self.assertEqual(observe_incomplete_end(self.state, 'one', {'known': False}), [])
        a = {'known': True, 'exists': True, 'content_sha256': 'old'}
        self.assertEqual(observe_incomplete_end(self.state, 'one', a), [])
        self.assertEqual(observe_incomplete_end(self.state, 'two', a | {'content_sha256': 'new'}), [])

    def test_two_incomplete_turns_same_artifact_feedback_once_and_no_wake(self):
        a = {'known': True, 'exists': True, 'content_sha256': 'same', 'bytes': 0}
        observe_artifact(self.state, a)
        self.assertEqual(observe_incomplete_end(self.state, 'one', a), [])
        self.assertEqual(observe_incomplete_end(self.state, 'one', a), [])
        hints = observe_incomplete_end(self.state, 'two', a)
        self.assertEqual(hints[0]['kind'], 'delivery-stall')
        self.assertEqual(observe_incomplete_end(self.state, 'three', a), [])

    def test_harness_report_reset_is_not_model_progress(self):
        a = {'known': True, 'exists': True, 'content_sha256': 'draft', 'bytes': 40000}
        empty = a | {'content_sha256': 'empty', 'bytes': 0}
        observe_artifact(self.state, empty)
        self.assertEqual(observe_incomplete_end(self.state, 'empty-first', empty), [])
        self.assertEqual(observe_incomplete_end(self.state, 'one', a), [])
        observe_artifact(self.state, empty, external_reset=True)
        self.assertEqual(observe_incomplete_end(self.state, 'two', empty), [])
        self.assertEqual(self.state['stalled_ends'], 1)

    def test_progress_already_seen_while_active_is_not_counted_as_a_stalled_end(self):
        empty = {'known': True, 'exists': True, 'content_sha256': 'empty', 'bytes': 0}
        draft = empty | {'content_sha256': 'draft', 'bytes': 100}
        observe_artifact(self.state, empty)
        observe_incomplete_end(self.state, 'first', empty)
        observe_artifact(self.state, draft)
        self.assertEqual(observe_incomplete_end(self.state, 'progressed', draft), [])
        self.assertEqual(self.state['stalled_ends'], 0)
        self.assertEqual(observe_incomplete_end(self.state, 'unchanged-once', draft), [])
        self.assertEqual(observe_incomplete_end(self.state, 'unchanged-twice', draft)[0]['kind'], 'delivery-stall')

    def test_first_observation_of_nonempty_draft_does_not_prove_stalling(self):
        draft = {'known': True, 'exists': True, 'content_sha256': 'draft', 'bytes': 100}
        self.assertEqual(observe_incomplete_end(self.state, 'first', draft), [])
        self.assertEqual(self.state['stalled_ends'], 0)

    def test_required_restoration_after_external_clear_counts_as_delivery_progress(self):
        draft = {'known': True, 'exists': True, 'content_sha256': 'draft', 'bytes': 100}
        empty = draft | {'content_sha256': 'empty', 'bytes': 0}
        observe_incomplete_end(self.state, 'first', draft)
        observe_artifact(self.state, empty, external_reset=True)
        self.assertEqual(observe_incomplete_end(self.state, 'restored', draft), [])
        self.assertEqual(self.state['stalled_ends'], 0)

    def test_real_artifact_change_allows_a_new_episode(self):
        a = {'known': True, 'exists': True, 'content_sha256': 'old'}
        observe_artifact(self.state, a)
        self.assertEqual(len(observe_commands(self.state, [syntax(1), syntax(2)], 'root')), 1)
        observe_artifact(self.state, a | {'content_sha256': 'new'})
        self.assertEqual(len(observe_commands(self.state, [syntax(3), syntax(4)], 'root')), 1)

    def test_literal_values_are_not_copied_into_feedback(self):
        f = syntax(1)
        f['output'] = f['output'].replace('fn(5)', 'fn("private-sentinel")')
        f['command'] = f['command'].replace('fn(5)', 'fn("private-sentinel")')
        hints = observe_commands(self.state, [f, f | {'itemId': '2'}], 'root')
        self.assertNotIn('private-sentinel', json.dumps(hints))


class NativeEvidenceTests(unittest.TestCase):
    def test_incremental_reader_binds_thread_turn_and_output_digest(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'native.jsonl'
            meta = {'type': 'session_meta', 'payload': {'id': 'root'}}
            event = {'type': 'event_msg', 'payload': {'type': 'item_completed', 'thread_id': 'root',
                'turn_id': 'turn', 'item': {'type': 'CommandExecution', 'id': '1', 'aggregated_output': 'body'}}}
            p.write_text(json.dumps(meta) + '\n' + json.dumps(event)[:-1])
            reader = NativeCommandEvidence(p, 'root')
            f = fact(1, output='body')
            f.pop('output')
            self.assertNotIn('output', reader.enrich([f])[0])
            with p.open('a') as stream:
                stream.write('}\n')
            self.assertEqual(reader.enrich([f])[0]['output'], 'body')
            self.assertNotIn('output', reader.enrich([f | {'turnId': 'other'}])[0])
            self.assertNotIn('output', reader.enrich([f | {'outputDigest': 'wrong'}])[0])
            p.write_text('')
            with self.assertRaises(ValueError):
                reader.refresh()

    def test_foreign_native_record_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'native.jsonl'
            p.write_text(json.dumps({'type': 'session_meta', 'payload': {'id': 'foreign'}}) + '\n')
            with self.assertRaises(ValueError):
                NativeCommandEvidence(p, 'root').refresh()

    def test_format_only_changes_are_not_artifact_progress(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'report.jsonl'
            p.write_text('{"x":1,"y":2}\n')
            before = artifact_observation(p)
            p.write_text('{ "y": 2, "x": 1 }\n')
            self.assertEqual(before['content_sha256'], artifact_observation(p)['content_sha256'])

    def test_progress_transport_and_idle_feedback_use_existing_owner(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report = root / 'report.jsonl'
            report.write_text('')
            class Machine:
                def __init__(self):
                    self.calls = []
                def call(self, op, args):
                    self.calls.append((op, args))
                    return {'deliveryStatus': 'accepted', 'messageId': 'admission-only'}
            machine = Machine()
            record = {'instanceId': 'case', 'started_at': 1, 'report': str(report),
                      'accepted': {'runId': 'run'}, 'selection': {'command_loop_guard':
                      {'enabled': True, 'algorithm': 'project-progress-guard-v1'}}}
            result = {'threadId': 'root', 'turnId': 'turn', 'snapshot': {
                'members': [{'threadId': 'root', 'state': 'active'}], 'commandFacts': [syntax(1), syntax(2)]}}
            observe_command_loops(machine, record, result, root / 'out')
            self.assertEqual(machine.calls[0][0], 'send_message')
            events = json.loads((root / 'out/progress-guard/events.jsonl').read_text())
            self.assertFalse(events['model_receipt_verified'])
            self.assertEqual(progress_continuation_feedback(record, result, root / 'out'), '')
            text = progress_continuation_feedback(record, result | {'turnId': 'next'}, root / 'out')
            self.assertIn('Two normal incomplete', text)
            self.assertEqual(len(machine.calls), 1)


if __name__ == '__main__':
    unittest.main()
