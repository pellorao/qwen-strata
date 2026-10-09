"""Canonical behaviors retain real repeats and exclude context and mirrors."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.loop.build_model_behavior_corpus import normalize, scrub, safe_value


class BehaviorCorpusTests(unittest.TestCase):
    def export(self, rows):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'native.jsonl'
            raw = '\n'.join(json.dumps(row) for row in rows).encode() + b'\n'
            path.write_bytes(raw)
            return normalize(path, {'thread_id': 'root', 'sha256': hashlib.sha256(raw).hexdigest()})

    def test_context_and_mirror_are_removed_but_two_real_equal_items_survive(self):
        meta = {'type': 'session_meta', 'payload': {'id': 'root', 'base_instructions': 'context-secret'}}
        context = {'type': 'turn_context', 'payload': {'turn_id': 'turn', 'developer_instructions': 'context-secret'}}
        model = {'type': 'response_item', 'payload': {'type': 'reasoning', 'summary': [{'text': 'same actual thought'}]}}
        mirror = {'type': 'event_msg', 'payload': {'type': 'item_completed', 'thread_id': 'root', 'turn_id': 'turn',
            'item': {'id': 'model-one', 'type': 'Reasoning', 'summary_text': ['same actual thought']}}}
        metadata, facts = self.export([meta, context, model, mirror, model, mirror])
        self.assertEqual(len(facts), 2)
        self.assertEqual(facts[0]['source_events'], [2, 3])
        self.assertEqual(facts[1]['source_events'], [4, 5])
        self.assertNotIn('context-secret', json.dumps([metadata, facts]))

    def test_custom_patch_and_tool_discovery_keep_their_results_once(self):
        rows = [{'type': 'session_meta', 'payload': {'id': 'root'}}]
        rows += [{'type': 'response_item', 'payload': x} for x in [
            {'type': 'custom_tool_call', 'call_id': 'patch', 'name': 'apply_patch', 'input': '*** Begin Patch'},
            {'type': 'custom_tool_call_output', 'call_id': 'patch', 'output': 'success'},
            {'type': 'tool_search_call', 'call_id': 'search', 'arguments': {'query': 'clock'}},
            {'type': 'tool_search_output', 'call_id': 'search', 'tools': [{'name': 'clock'}]}]]
        _, facts = self.export(rows)
        self.assertEqual(len(facts), 2)
        self.assertEqual(facts[0]['output'], 'success')
        self.assertEqual(facts[1]['output'], [{'name': 'clock'}])

    def test_initial_handoff_is_context_but_later_feedback_is_behavior(self):
        rows = [{'type': 'session_meta', 'payload': {'id': 'root'}}]
        rows += [{'type': 'response_item', 'payload': {'type': 'message', 'role': role,
                 'content': [{'text': text}]}} for role, text in [
                     ('user', 'complete initial role'), ('assistant', 'working'),
                     ('user', '<environment_context>irrelevant context</environment_context> driver cleared the draft; restore it')]]
        metadata, facts = self.export(rows)
        self.assertEqual([f['kind'] for f in facts], ['task', 'assistant', 'feedback'])
        self.assertEqual(facts[0]['text'], 'complete initial role')
        self.assertIn('restore', facts[2]['text'])
        self.assertNotIn('irrelevant context', facts[2]['text'])
        self.assertNotIn('text', metadata['initial_task_inputs'][0])

    def test_reused_tool_id_in_two_turns_keeps_two_distinct_outputs(self):
        rows = [{'type': 'session_meta', 'payload': {'id': 'root'}}]
        for turn, output in [('first', 'error'), ('second', 'repaired')]:
            rows += [{'type': 'turn_context', 'payload': {'turn_id': turn}},
                     {'type': 'response_item', 'payload': {'type': 'function_call', 'call_id': 'same-id',
                        'name': 'exec_command', 'arguments': '{"cmd":"read"}'}},
                     {'type': 'response_item', 'payload': {'type': 'function_call_output',
                        'call_id': 'same-id', 'output': output}}]
        _, facts = self.export(rows)
        self.assertEqual([f['output'] for f in facts], ['error', 'repaired'])

    def test_feedback_after_a_tool_only_model_step_is_not_initial_context(self):
        rows = [{'type': 'session_meta', 'payload': {'id': 'root'}},
                {'type': 'response_item', 'payload': {'type': 'function_call', 'call_id': 'cmd',
                    'name': 'exec_command', 'arguments': '{"cmd":"read"}'}},
                {'type': 'response_item', 'payload': {'type': 'message', 'role': 'user',
                    'content': [{'text': 'That response was refused; continue this task.'}]}}]
        _, facts = self.export(rows)
        self.assertEqual([f['kind'] for f in facts], ['tool', 'feedback'])

    def test_credentials_are_removed_from_json_shell_and_bearer_without_value_in_edits(self):
        secrets = ['long-private-key', 'short', 'another-private-key']
        text = '"api_key": "long-private-key" password=short Authorization: Bearer another-private-key'
        clean, edits = scrub(text)
        self.assertEqual(len(edits), 3)
        for secret in secrets:
            self.assertNotIn(secret, clean)
            self.assertNotIn(secret, json.dumps(edits))
        self.assertEqual(safe_value({'STRATA_API_KEY': 'long-private-key'})['STRATA_API_KEY'], '<redacted>')


if __name__ == '__main__':
    unittest.main()
