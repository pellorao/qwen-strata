"""tools.guard_runs: the run registry and the start-rate net for scripts that start a model process."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

from tools import guard_runs


def _agy_rate_missing():
    sys.path.insert(0, os.path.expanduser('~/.claude/lib'))
    try:
        import agy_rate  # noqa: F401
    except ModuleNotFoundError:
        return True
    return False


NO_AGY = unittest.skipIf(_agy_rate_missing(), 'agy_rate not importable: Antigravity was removed on this machine')


class GuardRunsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for k, v in (('USAGE_GUARD_RUNS', 'runs'), ('USAGE_GUARD_DIR', 'ug')):
            self.addCleanup(os.environ.pop, k, None)
            os.environ[k] = str(Path(self.tmp.name) / v)

    def live(self):
        sys.path.insert(0, os.path.expanduser('~/.claude/lib'))
        import usage_guard
        return usage_guard.live_runs()

    def test_registered_run_is_live_inside_and_gone_after(self):
        with guard_runs.registered('qs:t', 'claude', model='sonnet', effort='high', source='claude-sub'):
            runs = self.live()
            self.assertEqual([(r['label'], r['harness'], r['model'], r['source']) for r in runs], [('qs:t', 'claude', 'sonnet', 'claude-sub')])
        self.assertEqual(self.live(), [])

    def test_rate_stops_the_start_over_the_cap_and_blocks_until_acked(self):
        guard_runs.rate('qs:t', 2, 3600)
        guard_runs.rate('qs:t', 2, 3600)
        with self.assertRaises(guard_runs.Stopped):
            guard_runs.rate('qs:t', 2, 3600)
        with self.assertRaises(guard_runs.Stopped):   # the marker stays until an agent acks it
            guard_runs.rate('qs:t', 2, 3600)

    @NO_AGY
    def test_agy_run_harness_follows_the_model_group(self):
        with guard_runs.agy('qs:g', 'gemini-4-hydrogen-medium', 'medium'):
            with guard_runs.agy('qs:c', 'claude-opus-5-5', 'high'):
                got = sorted((r['label'], r['harness'], r['source'], r['model'], r['effort']) for r in self.live())
        self.assertEqual(got, [('qs:c', 'agy-claude', 'agy-claude', 'Opus 5.5', 'high'),
                               ('qs:g', 'agy-gemini', 'agy-gemini', 'Hydrogen', 'medium')])

    def test_missing_library_is_a_no_op(self):
        saved = guard_runs.LIB
        self.addCleanup(setattr, guard_runs, 'LIB', saved)
        guard_runs.LIB = '/nonexistent'
        guard_runs._ug = None
        guard_runs.rate('x', 1, 1)
        guard_runs.rate('x', 1, 1)
        with guard_runs.registered('x', 'claude'):
            pass


class UnitTestsDoNotTouchRealStateTest(unittest.TestCase):
    """Without the USAGE_GUARD_* overrides a unit test must not write the real usageguard/ or runs/ (2026-11-14: a full run tripped a real stop marker)."""
    LABEL = 'qs:isolation-probe'

    def real(self):
        base = Path(os.path.expanduser('~/.claude/statusline'))
        ug = sorted(p.name for p in (base / 'usageguard').glob('*isolation-probe*'))
        runs = sorted(p.name for p in (base / 'runs').glob('*.json') if self.LABEL in p.read_text(errors='replace'))
        return ug, runs

    def test_rate_and_registration_leave_real_state_alone(self):
        for k in ('USAGE_GUARD_RUNS', 'USAGE_GUARD_DIR'):
            if k in os.environ:
                self.addCleanup(os.environ.__setitem__, k, os.environ[k])
                del os.environ[k]
        before = self.real()
        try:
            guard_runs.rate(self.LABEL, 100, 3600)
            with guard_runs.registered(self.LABEL, 'claude'):
                self.assertEqual(self.real()[1], before[1])
            self.assertEqual(self.real(), before)
        finally:   # remove what a failing run left in the real directories
            for name in set(self.real()[0]) - set(before[0]):
                os.remove(os.path.expanduser('~/.claude/statusline/usageguard/') + name)
            for name in set(self.real()[1]) - set(before[1]):
                os.remove(os.path.expanduser('~/.claude/statusline/runs/') + name)


if __name__ == '__main__':
    unittest.main()
