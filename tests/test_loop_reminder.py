"""Loop reminders: stateless replay of the request history, one-off notice, per-chain silence."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import loop_reminder

TEXT = ('The validator still fails because the evidence range for record ninety six spans adjacent lines that '
        'should be listed separately according to the gate rules about staged bytes and source coverage')


def chat(calls, output='exit 1: missing ) after argument list'):
    messages = [{'role': 'system', 'content': 'rules'}, {'role': 'user', 'content': 'audit the change'}]
    for n, command in enumerate(calls):
        messages.append({'role': 'assistant', 'content': '', 'tool_calls': [
            {'id': f'c{n}', 'type': 'function', 'function': {'name': 'exec', 'arguments': f'{{"cmd": "{command}"}}'}}]})
        messages.append({'role': 'tool', 'tool_call_id': f'c{n}', 'content': output})
    return {'messages': messages}


def responses(texts):
    items = [{'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': 'audit the change'}]}]
    for n, text in enumerate(texts):
        items += [{'type': 'reasoning', 'summary': [], 'content': [{'type': 'reasoning_text', 'text': text}]},
                  {'type': 'function_call', 'call_id': f'c{n}', 'name': 'exec', 'arguments': f'{{"cmd": "probe {n}"}}'},
                  {'type': 'function_call_output', 'call_id': f'c{n}', 'output': f'result {n}'}]
    return {'input': items}


def messages(calls):
    out = [{'role': 'user', 'content': 'audit the change'}]
    for n, command in enumerate(calls):
        out += [{'role': 'assistant', 'content': [{'type': 'tool_use', 'id': f't{n}', 'name': 'Bash',
                                                    'input': {'command': command}}]},
                {'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': f't{n}', 'content': 'same'}]}]
    return {'messages': out}


class ReminderTests(unittest.TestCase):
    def test_a_repeated_call_with_the_same_result_is_reminded_once_in_chat(self):
        first = chat(['node check.js'])
        self.assertIsNone(loop_reminder.apply('/v1/chat/completions', first, {}))
        body = chat(['node check.js', 'node check.js'])
        notice = loop_reminder.apply('/v1/chat/completions', body, {})
        self.assertIn('step 2', notice)
        self.assertIn('first seen at step 1', notice)
        self.assertEqual(body['messages'][-1], {'role': 'user', 'content': notice})
        self.assertEqual(body['messages'][-2]['role'], 'tool')

    def test_an_already_reminded_chain_is_silent_until_it_recurs_again(self):
        sent = [loop_reminder.apply('/v1/chat/completions', chat(['node check.js'] * n), {}) is not None
                for n in range(1, 7)]
        self.assertEqual(sent, [False, True, False, True, False, True])

    def test_a_different_result_is_not_a_repeat(self):
        body = chat(['node check.js', 'node check.js'])
        body['messages'][-1]['content'] = 'exit 0'
        self.assertIsNone(loop_reminder.apply('/v1/chat/completions', body, {}))

    def test_repeated_reasoning_is_reminded_in_responses(self):
        body = responses(['Reading the request first and listing every requirement of both issues.', TEXT, TEXT])
        notice = loop_reminder.apply('/v1/responses', body, {})
        self.assertIn('step 3', notice)
        self.assertIn('reasoning or text', notice)
        self.assertIn('first seen at step 2', notice)
        self.assertEqual(body['input'][-1]['content'][0]['text'], notice)
        self.assertEqual(body['input'][-2]['type'], 'function_call_output')

    def test_messages_notice_joins_the_last_tool_result_turn(self):
        body = messages(['npm test', 'npm test'])
        notice = loop_reminder.apply('/v1/messages', body, {})
        self.assertIsNotNone(notice)
        last = body['messages'][-1]
        self.assertEqual([p['type'] for p in last['content']], ['tool_result', 'text'])
        self.assertEqual(last['content'][-1]['text'], notice)

    def test_an_input_after_the_step_closes_it(self):
        body = chat(['node check.js', 'node check.js'])
        body['messages'].append({'role': 'user', 'content': 'Summarize the conversation so far.'})
        self.assertIsNone(loop_reminder.apply('/v1/chat/completions', body, {}))
        body = responses(['Reading the request first and listing every requirement of both issues.', TEXT, TEXT])
        body['input'].append({'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': 'go on'}]})
        self.assertIsNone(loop_reminder.apply('/v1/responses', body, {}))

    def test_header_turns_the_reminder_off(self):
        body = chat(['node check.js', 'node check.js'])
        self.assertIsNone(loop_reminder.apply('/v1/chat/completions', body, {'X-Loop-Reminder': 'off'}))
        self.assertEqual(len(body['messages']), 6)

    def test_plain_string_input_has_no_history(self):
        self.assertIsNone(loop_reminder.apply('/v1/responses', {'input': 'hello'}, {}))


if __name__ == '__main__':
    unittest.main()
