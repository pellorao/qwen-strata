"""The Claude Code Role gate's judgement (plan v2 F9): what counts as the Role reaching the model whole."""
import unittest

from tools.safety import claude_role_gate as gate

ROLE = 'You are the Reviewer.\nDo the review.'
TOOLS = [{'name': 'Bash'}]


def body(system, messages=None, tools=TOOLS):
    return {'system': system, 'messages': messages or [{'role': 'user', 'content': 'handoff'}], 'tools': tools}


class JudgeTests(unittest.TestCase):
    def test_role_once_at_the_tail_after_claudes_prompt_passes(self):
        system = [{'type': 'text', 'text': 'Claude Code prompt.'}, {'type': 'text', 'text': ROLE}]
        rows, ok = gate.judge([body(system), body('Claude Code prompt.\n' + ROLE)], ROLE)
        self.assertTrue(ok)
        self.assertEqual(len(rows), 2)

    def test_missing_duplicated_misplaced_or_leaked_role_fails(self):
        for bad in (body('Claude Code prompt.'),
                    body('Claude Code prompt.\n' + ROLE + '\n' + ROLE),
                    body(ROLE),
                    body('Claude Code prompt.\n' + ROLE + '\nMore.'),
                    body('Claude Code prompt.\n' + ROLE, [{'role': 'user', 'content': ROLE}])):
            self.assertFalse(gate.judge([bad], ROLE)[1], bad)

    def test_requests_without_the_main_tools_are_not_judged(self):
        rows, ok = gate.judge([body('side call', tools=[])], ROLE)
        self.assertEqual(rows, [])
        self.assertFalse(ok)


if __name__ == '__main__':
    unittest.main()
