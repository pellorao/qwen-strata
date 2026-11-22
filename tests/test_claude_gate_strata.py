import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import fast_servers  # noqa: E401,F401
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.safety import claude_gate as gate


class StrataLiveGateTest(unittest.TestCase):
    """G8: the live Strata gate goes through the lease and names the served model."""

    def test_live_strata_needs_no_quota_label_but_api_backends_do(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'label'):
                gate.gate(Path(folder) / 'out', backend='anthropic', live=True)

    def test_live_strata_rejects_another_model_before_taking_the_lease(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'served model'):
                with gate.strata_live(Path(folder), 'qwen3.8-flash-next-q2_0', 'high', Path(folder), Path(folder)):
                    pass


class PlanLimitsTest(unittest.TestCase):
    """The DeepSeek gate takes the scenario plan's Claude Code limits, never a null one, never on another backend."""

    def test_plan_limits_are_read(self):
        with tempfile.TemporaryDirectory() as folder:
            plan = Path(folder) / 'plan.json'
            plan.write_text('{"fixed_conditions": {"deepseek_claude_environment": {"CLAUDE_CODE_MAX_OUTPUT_TOKENS": 128000}}}')
            self.assertEqual(gate.plan_limits(plan)['CLAUDE_CODE_MAX_OUTPUT_TOKENS'], 128000)

    def test_null_limit_and_other_backend_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            plan = Path(folder) / 'plan.json'
            plan.write_text('{"fixed_conditions": {"deepseek_claude_environment": {"CLAUDE_CODE_MAX_OUTPUT_TOKENS": null}}}')
            with self.assertRaisesRegex(ValueError, 'unset'):
                gate.plan_limits(plan)
            with self.assertRaisesRegex(ValueError, 'DeepSeek backend only'):
                gate.gate(Path(folder) / 'out', backend='anthropic', limits={'CLAUDE_CODE_MAX_OUTPUT_TOKENS': 1})


class PairSessionsTest(unittest.TestCase):
    def test_odd_repeat_runs_exactly_that_many_sessions_and_the_last_alone(self):
        ran = []
        fake = lambda run_id, base, project_dir, fresh_config=True: {
            'tmp': Path(run_id), 'secret': {'TMP': run_id, 'PEER': ''}, 'peer_tmp': None}

        def session(out, backend, model, effort, n, base, project, claude, startup, fx):
            ran.append((n, fx['peer_tmp'] is not None))
            return {'n': n}
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(gate, 'fixture', fake), \
                mock.patch.object(gate, 'session', session), mock.patch.object(gate, 'release'):
            records = gate.pair_sessions(Path(folder), 'strata', 'm', 'high', 3, folder, 'claude', True)
        self.assertEqual(sorted(r['n'] for r in records), [1, 2, 3])
        self.assertEqual(dict(ran), {1: True, 2: True, 3: False})

    def test_a_session_thread_error_is_raised_not_a_key_error(self):
        fake = lambda *a, **k: {'tmp': Path('t'), 'secret': {'TMP': 't', 'PEER': ''}, 'peer_tmp': None}

        def session(out, backend, model, effort, n, *rest, **kw):
            if n == 2:
                raise RuntimeError('boom')
            return {'n': n}
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(gate, 'fixture', fake), \
                mock.patch.object(gate, 'session', session), mock.patch.object(gate, 'release'):
            with self.assertRaisesRegex(RuntimeError, 'boom'):
                gate.pair_sessions(Path(folder), 'strata', 'm', 'high', 2, folder, 'claude', True)


class FixtureCleanupTest(unittest.TestCase):
    def test_a_failed_build_removes_what_it_placed_in_shared_places(self):
        with tempfile.TemporaryDirectory() as folder:
            canary = Path(folder) / 'canary.txt'
            directory = Path(folder) / 'dir'

            def build(run_id, base, project_dir, fresh_config, made):
                canary.write_text('x')
                made.append(canary)
                directory.mkdir()
                made.append(directory)
                raise OSError('late failure')
            with mock.patch.object(gate, 'build_fixture', build):
                with self.assertRaises(OSError):
                    gate.fixture('r', folder)
            self.assertFalse(canary.exists() or directory.exists())

    def test_a_probe_that_never_returned_is_not_a_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            fx = gate.fixture(f'unit-{gate.token()}', folder, Path(folder) / 'project')
            try:
                script = [('read_outside', 'read', 'Read', {'file_path': str(fx['outside'] / 'answer.json')})]
                asked = [('Read', {'file_path': str(fx['outside'] / 'answer.json')}, None, False)]
                rows = gate.judge_probes(fx, script, asked, [])
                self.assertTrue(rows['read_outside']['attempted'])
                self.assertFalse(rows['read_outside']['pass'])
                asked = [('Read', asked[0][1], 'denied', True)]
                self.assertTrue(gate.judge_probes(fx, script, asked, [])['read_outside']['pass'])
            finally:
                gate.release(fx)


class MockDisconnectTest(unittest.TestCase):
    def test_client_disconnect_is_silent_and_other_errors_are_printed(self):
        server = gate.serve()
        try:
            for error, printed in ((ConnectionResetError, False), (BrokenPipeError, False), (ValueError, True)):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    try:
                        raise error('x')
                    except error:
                        server.handle_error(None, ('127.0.0.1', 1))
                self.assertEqual(bool(stderr.getvalue()), printed, error)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
