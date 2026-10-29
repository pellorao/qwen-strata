import io
import json
from pathlib import Path
import sys
import unittest
from importlib.machinery import SourceFileLoader
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
codex_timers = SourceFileLoader('codex_timers', str(ROOT / 'scripts/wsl/codex-timers')).load_module()


class CodexTimersTests(unittest.TestCase):
    def test_unit_names_are_stable_and_session_scoped(self):
        first = codex_timers.unit_name('thread-a', 'same')
        self.assertEqual(first, codex_timers.unit_name('thread-a', 'same'))
        self.assertNotEqual(first, codex_timers.unit_name('thread-b', 'same'))
        self.assertLessEqual(len(first), 64)

    def test_cleanup_stops_every_matching_timer(self):
        listing = subprocess_result('codex-timer-a.timer loaded active waiting\ncodex-timer-b.timer loaded active waiting\n')
        with patch.object(codex_timers, 'systemctl', side_effect=[listing, subprocess_result()]) as systemctl:
            self.assertEqual(codex_timers.cleanup('thread'), ['codex-timer-a.timer', 'codex-timer-b.timer'])
        systemctl.assert_any_call(
            'list-units', '--all', '--plain', '--no-legend',
            f'codex-timer-{codex_timers.tag("thread")}-*.timer', check=False,
        )
        systemctl.assert_any_call('stop', 'codex-timer-a.timer', 'codex-timer-b.timer')

    def test_session_end_hook_uses_stdin_session_id(self):
        event = json.dumps({'session_id': 'thread-from-hook'})
        with patch.object(sys, 'stdin', io.StringIO(event)), patch.dict('os.environ', {}, clear=True):
            self.assertEqual(codex_timers.hook_session(), 'thread-from-hook')

    def test_schedule_uses_systemd_run_and_queue_targets_the_live_thread(self):
        args = type('Args', (), {
            'session_id': 'thread', 'message': 'check later', 'seconds': 1200, 'at': None, 'every': None,
        })()
        with patch.object(codex_timers.shutil, 'which', return_value='/usr/bin/codex'), \
                patch.object(codex_timers.subprocess, 'run') as run:
            unit = codex_timers.schedule(args)
        command = run.call_args.args[0]
        self.assertIn('systemd-run', command)
        self.assertIn('--on-active=1200', command)
        self.assertNotIn('exec', command)
        self.assertEqual(command[-7:], [
            'wake', '--session-id', 'thread', '--unit', unit, '--message', 'check later',
        ])

    def test_recurring_schedule_uses_an_oncalendar_expression(self):
        args = type('Args', (), {
            'session_id': 'thread', 'message': 'periodic check', 'seconds': None, 'at': None,
            'every': '*-*-* *:00/20:00',
        })()
        with patch.object(codex_timers.shutil, 'which', return_value='/usr/bin/codex'), \
                patch.object(codex_timers.subprocess, 'run') as run:
            codex_timers.schedule(args)
        self.assertIn('--on-calendar=*-*-* *:00/20:00', run.call_args.args[0])

    def test_session_end_template_has_a_three_second_cleanup_hook(self):
        template = json.loads((ROOT / 'docs/codex-cli-scheduling-hooks.json').read_text(encoding='utf-8'))
        hook = template['hooks']['SessionEnd'][0]['hooks'][0]
        self.assertEqual(hook['timeout'], 3)
        self.assertIn('/scripts/wsl/codex-timers', hook['command'])
        self.assertTrue(hook['command'].endswith(' cleanup'))

    def test_failed_queue_removes_its_transient_timer(self):
        with patch.object(codex_timers.shutil, 'which', return_value='/usr/bin/codex'), \
                patch.object(codex_timers.subprocess, 'run', return_value=subprocess_result('', 'no session', 1)), \
                patch.object(codex_timers, 'systemctl') as systemctl:
            with self.assertRaisesRegex(RuntimeError, 'no session'):
                codex_timers.wake('thread', 'codex-timer-unit', 'check')
        systemctl.assert_called_once_with('stop', 'codex-timer-unit.timer', check=False)


def subprocess_result(stdout='', stderr='', returncode=0):
    return type('Result', (), {'stdout': stdout, 'stderr': stderr, 'returncode': returncode})()


if __name__ == '__main__':
    unittest.main()
