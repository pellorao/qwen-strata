import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import fast_servers  # noqa: E401,F401
import json
import sys
import os
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path

from tools.tuning import codex_workload, staged_decision, window_bank


class StagedDecisionTest(unittest.TestCase):
    def test_bounds_follow_obrien_fleming(self):
        self.assertEqual([round(staged_decision.bound(r), 2) for r in range(1, 6)], [5.03, 3.56, 2.9, 2.52, 2.25])
        self.assertGreater(staged_decision.bound(5, 5), staged_decision.bound(5, 2))

    def test_two_candidates(self):
        judge = lambda a, b: staged_decision.judge_many({'a': a, 'b': b}, 2)
        self.assertEqual(judge([0.9, 0.91, 0.9], [0.5, 0.52, 0.5])['decision'], 'winner')
        self.assertEqual(judge([0.80, 0.81, 0.80], [0.80, 0.80, 0.81])['decision'], 'equivalent')
        self.assertEqual(judge([0.7, 0.9, 0.8], [0.6, 0.85, 0.75])['decision'], 'continue')
        spread = [0.6, 0.9] * 5 + [0.75]
        self.assertEqual(judge(spread, [s - 0.03 for s in spread[::-1]])['decision'], 'undecided')
        with self.assertRaises(ValueError):
            judge([0.5] * 4, [0.5] * 4)

    def test_many_candidates_exit_and_tie(self):
        result = staged_decision.judge_many({'a': [0.80, 0.81, 0.80], 'b': [0.80, 0.80, 0.81],
                                             'c': [0.2, 0.21, 0.2], 'd': [0.7, 0.9, 0.8]}, 4)
        self.assertEqual(result['leaving'], ['c'])
        self.assertEqual(result['tied'], ['b'])
        self.assertEqual(result['sampled_next'], ['a', 'd'])


class SandboxProbeTest(unittest.TestCase):
    @unittest.skipUnless(codex_workload.CODEX.exists(), 'native Codex not installed')
    @unittest.skipIf(Path(__file__).resolve().is_relative_to('/tmp'), 'a checkout under /tmp makes the workspace itself global-tmp readable')
    def test_workspace_is_the_only_readable_place(self):
        from tools.tuning import sandbox_probe
        overrides = codex_workload.codex_overrides

        def quick(*args, **kwargs):
            # Without this Codex waits 10 s at exit to flush analytics it cannot send; unrelated to the sandbox.
            return [*overrides(*args, **kwargs), '-c', 'analytics.enabled=false']
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / '.tmp') as tmp, \
                mock.patch.object(codex_workload, 'codex_overrides', quick):
            result = sandbox_probe.probe(tmp)
        self.assertTrue(result['ok'], result['problems'])


class WindowBankTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workload = window_bank.build(5)  # chars/2.4 estimate instead of the tokenizer
        cls.frozen = json.loads((Path(__file__).resolve().parents[1] /
                                 'benchmarks/window-load-v1/window-v2-seed1.json').read_text())

    def test_self_check_and_composition(self):
        for workload in (self.workload, self.frozen):
            check = window_bank.self_check(workload)
            self.assertTrue(check['ok'], check)
            self.assertEqual(len(workload['questions']), 60)
            for n in range(1, 6):
                kinds = [q['type'] for q in workload['questions'] if q['checkpoint'] == n]
                self.assertEqual(len(kinds), 12)
        self.assertEqual(self.frozen['schema'], window_bank.SCHEMA)

    def test_each_fact_asked_once_and_never_mentioned_after(self):
        seen = set()
        for q in self.frozen['questions']:
            key = (q['record'], q['field'])
            self.assertNotIn(key, seen)
            seen.add(key)

    def test_stale_answer_is_wrong_and_formatting_is_tolerated(self):
        updated = next(q for q in self.frozen['questions'] if q.get('stale_values'))
        reply = f'{updated["id"]}: {updated["stale_values"][0]}\nQ99: x'
        result = window_bank.score(self.frozen, [reply])
        self.assertEqual(result['correct'], 0)
        self.assertEqual(result['stale_answers'], 1)
        good = window_bank.score(self.frozen, [f'**{updated["id"]}:** `{str(updated["answer"]).upper()}`'])
        self.assertEqual(good['correct'], 1)

    def test_summary_retention_checks_current_values_of_pending_facts(self):
        w = self.frozen
        after = 'batch 30'  # after the K updates (batch 21)
        keys, state = window_bank.state_through(w, after)
        everything = ' '.join(f'{k}={v}' for k, v in keys.items()) + ' ' + ' '.join(
            f'{r}:{f}={v}' for r, fields in state.items() for f, v in fields.items())
        full = window_bank.summary_retention(w, after, everything)
        self.assertEqual((full['pending_K_kept'], full['pending_U_kept']), (full['pending_K'], full['pending_U']))
        self.assertGreater(full['pending_K'], 0)
        self.assertEqual(full['all_K_marked_kept'] + full['all_K_unmarked_kept'], 16)
        empty = window_bank.summary_retention(w, after, 'nothing kept')
        self.assertEqual((empty['pending_K_kept'], empty['all_K_marked_kept']), (0, 0))
        updated = next(q for q in w['questions'] if q['type'] == 'K' and q['updated'] and q['checkpoint'] >= 4)
        stale = window_bank.summary_retention(w, after, ' '.join(updated['stale_values']))
        self.assertFalse(next(r for r in stale['rows'] if r['id'] == updated['id'])['kept'])

    def test_fact_in_text_needs_the_current_value_line(self):
        b = {'type': 'B', 'record': 'HM-1269', 'field': 'qty', 'answer': '57'}
        k = {'type': 'K', 'record': 'K02', 'field': 'audit ticket', 'answer': 'VEGI-7359'}
        self.assertTrue(window_bank.fact_in_text(b, ['x\nHM-1269 | owner=A B | site=S-1 | qty=57 | status=open | tag=t']))
        self.assertTrue(window_bank.fact_in_text(b, ['UPDATE HM-1269 qty=57']))
        self.assertFalse(window_bank.fact_in_text(b, ['UPDATE HM-1269 qty=570', 'UPDATE XHM-1269 qty=57']))
        self.assertFalse(window_bank.fact_in_text(b, ['HM-1269 | owner=A B | site=S-1 | q']))  # truncated
        self.assertTrue(window_bank.fact_in_text(k, ['K02 | audit ticket = VEGI-7359 [mark]']))
        self.assertTrue(window_bank.fact_in_text(k, ['UPDATE K02 = VEGI-7359']))
        self.assertFalse(window_bank.fact_in_text(k, ['K02 | audit ticket = VEGI-73590']))

    def test_timeline_split_and_equal_weights_give_raw_accuracy(self):
        w = self.frozen
        labels = [x['label'] for x in w['sequence']]
        replies, timeline = [], []
        for n in range(1, 6):
            qs = [q for q in w['questions'] if q['checkpoint'] == n]
            replies.append('\n'.join(f'{q["id"]}: {q["answer"] if i % 3 else "wrong"}' for i, q in enumerate(qs)))
            here = labels.index(f'questions {n}')
            timeline.append({'raw': labels[max(0, here - 12):here + 1], 'compactions_after': [labels[here - 13]],
                             'context_tokens': 90000 + 20000 * n})
        result = window_bank.score(w, replies, timeline)
        self.assertAlmostEqual(result['score'], result['raw_score'])
        self.assertEqual(sum(c['n'] for c in result['C1'].values()) + sum(c['n'] for c in result['C2'].values()), 60)
        self.assertAlmostEqual(result['in_text_share'], sum(c['n'] for c in result['C1'].values()) / 60)
        self.assertEqual(set(result['C1']) - {'<100K', '100-150K', '>=150K'}, set())


def rollout_lines(events):
    return '\n'.join(json.dumps(e) for e in events)


def user(text):
    return {'type': 'response_item', 'payload': {'type': 'message', 'role': 'user',
                                                 'content': [{'type': 'input_text', 'text': text}]}}


def assistant(text):
    return {'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant',
                                                 'content': [{'type': 'output_text', 'text': text}]}}


def call(cmd):
    return {'type': 'response_item', 'payload': {'type': 'function_call', 'name': 'exec_command',
                                                 'arguments': json.dumps({'cmd': cmd})}}


class CodexWorkloadTest(unittest.TestCase):
    def test_overrides_turn_off_plugin_marketplace_clone(self):
        plan = json.loads((Path(__file__).resolve().parents[1] /
                           'benchmarks/window-load-v1/pilot-plan.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            args = codex_workload.codex_overrides(plan, {'context_window': 156584, 'threshold': 100000},
                                                  Path(tmp), 'http://127.0.0.1:1/v1')
        self.assertIn('features.plugins=false', args)

    def test_codex_home_is_absolute_for_relative_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / 'codex'
            fake.write_text('#!/bin/sh\necho "{\\"home\\": \\"$CODEX_HOME\\"}"\n')
            fake.chmod(0o755)
            workspace = Path(tmp) / 'ws'
            workspace.mkdir()
            original = codex_workload.CODEX
            codex_workload.CODEX = fake
            try:
                relative = Path(os.path.relpath(Path(tmp) / 'home'))
                codex_workload.codex_exec([], workspace, relative, 'k', '', Path(tmp) / 'log.jsonl', 30)
            finally:
                codex_workload.CODEX = original
            home = json.loads((Path(tmp) / 'log.jsonl').read_text().splitlines()[0])['home']
            self.assertTrue(Path(home).is_absolute())
            self.assertEqual(Path(home), (Path(tmp) / 'home').resolve())

    def test_session_records_never_split_a_line(self):
        line = ('strata serve: prompt {} tokens = 0 reused + {} read in 10 ms (1.0 tok/s), '
                '5 generated in 50 ms (100.0 tok/s), drafts accepted 1 of 1, 1 checkpoints\n')
        log = 'boot\n' + line.format(100, 100) + line.format(200, 200) + line.format(300, 300)
        offset = 1000
        # a mark taken while the 200 line was being written: that request finished in the first session
        first_end = offset + len('boot\n') + len(line.format(100, 100)) + 7
        sessions = [{'log_bytes': [offset, first_end]}, {'log_bytes': [first_end, offset + len(log.encode())]}]
        grouped = codex_workload.session_records(log, sessions, offset)
        self.assertEqual([[r['input'] for r in g] for g in grouped], [[100, 200], [300]])

    def test_loaded_startup_sha_excludes_deprecated_loop_block(self):
        import sys
        sys.path.append(str(codex_workload.STARTUP.parents[2] / 'src'))
        from startup_instructions import startup_prompt_bytes
        raw = codex_workload.STARTUP.read_bytes()
        self.assertEqual(codex_workload.loaded_startup_sha(), codex_workload.sha(startup_prompt_bytes(raw, False)))
        self.assertNotEqual(codex_workload.loaded_startup_sha(), codex_workload.sha(raw))

    def analyse(self, events, in_text=None):
        with tempfile.NamedTemporaryFile('w', suffix='.jsonl', delete=False) as f:
            f.write(rollout_lines(events))
        try:
            return codex_workload.analyse_session(f.name, in_text)
        finally:
            Path(f.name).unlink()

    def test_session_analysis(self):
        summary = 'Another language model started to solve this problem: summary'
        result = self.analyse([user('<environment_context>x</environment_context>'),
                               user('This is a long-context recall test.'), assistant('ACK 00'),
                               user('Batch 01/02. New records:'), assistant('ACK 01'),
                               assistant(summary),  # the compaction summary, recorded inside the running turn
                               {'type': 'compacted', 'payload': {'message': summary, 'replacement_history': [
                                   user('Batch 01/02. New records:')['payload'], user(summary)['payload']]}},
                               user('Batch 02/02. New records:'), assistant('ACK 02'),
                               user('Checkpoint 1 of 5. Questions about the current state'), call('ls'), call('ls'),
                               call('ls'), assistant('Q01: a\nQ02: b')])
        self.assertEqual(result['compactions'], [{'after_user_turn': 'batch 01', 'kept_raw': ['batch 01'],
                                                  'summary': summary}])
        self.assertEqual([r['turn'] for r in result['replies']], ['opening', 'batch 01', 'batch 02', 'questions 1'])
        self.assertEqual(result['replies'][1]['text'], 'ACK 01')
        self.assertEqual(codex_workload.ack_problems(result), [])
        self.assertEqual(result['replies'][-1]['text'], 'Q01: a\nQ02: b')
        self.assertEqual(result['timeline'][0]['raw'], ['batch 01', 'batch 02', 'questions 1'])
        self.assertEqual(result['timeline'][0]['compactions_after'], ['batch 01'])
        self.assertEqual(result['loop']['longest_identical_call_run'], 3)
        self.assertIn('206584 compacted 1 times, fewer than 2',
                      codex_workload.window_effect({'context_window': 206584}, result, {206584: 2}))
        self.assertIn('156584 compacted 1 times, fewer than 2',
                      codex_workload.window_effect({'context_window': 156584}, result))
        self.assertTrue(any('tool calls' in p for p in codex_workload.window_effect({'context_window': 206584}, result)))

    def test_in_text_follows_the_truncated_kept_text(self):
        full = 'Batch 01/02. New records:\nAA-1111 | owner=x | site=y | qty=5 | status=open | tag=t\nBB-2222 | qty=7'
        cut = 'Batch 01/02. New records:\nAA-1111 | own'  # Codex shortened the oldest kept message
        summary = 'Another language model started to solve this problem: summary'
        events = [user(full), assistant('ACK 01'),
                  {'type': 'compacted', 'payload': {'message': summary, 'replacement_history': [
                      user(cut)['payload'], user(summary)['payload']]}},
                  user('Checkpoint 1 of 5. Questions'), assistant('Q01: 5')]
        qs = [{'id': 'Q01', 'checkpoint': 1, 'type': 'B', 'record': 'AA-1111', 'field': 'qty', 'answer': '5'}]
        result = self.analyse(events, window_bank.finder({'questions': qs}))
        self.assertEqual(result['timeline'][0]['raw'], ['batch 01', 'questions 1'])
        self.assertEqual(result['timeline'][0]['in_text_ids'], [])
        result = self.analyse(events[:2] + events[3:], window_bank.finder({'questions': qs}))
        self.assertEqual(result['timeline'][0]['in_text_ids'], ['Q01'])

    def test_ack_reply_kept_when_no_summary_message_precedes_compaction(self):
        result = self.analyse([user('Batch 01/02. New records:'), assistant('ACK 01'),
                               {'type': 'compacted', 'payload': {'message': 'other', 'replacement_history': []}},
                               user('Batch 02/02. New records:'), assistant('ACK 02')])
        self.assertEqual([r['text'] for r in result['replies']], ['ACK 01', 'ACK 02'])

    def test_window_rounds_group_conditions_and_reverse_order(self):
        self.assertEqual(codex_workload.next_round(['a', 'b'], 1, ['a', 'b']), ['b', 'b', 'a', 'a'])
        self.assertEqual(codex_workload.next_round(['b', 'a'], 2, ['a', 'b']), ['a', 'a', 'b', 'b'])
        self.assertEqual(codex_workload.next_round(['b'], 1, ['a', 'b']), ['b', 'b'])

    def test_over_verified_requests_are_listed_by_kind(self):
        from unittest import mock
        rows = [{'input': 150000, 'output': 19}, {'input': 152545, 'output': 19}, {'input': 150935, 'output': 5325},
                {'input': 156029, 'output': 600}]
        with mock.patch('tools.metrics.strata_tokens.parse_engine_log', return_value=rows):
            result = codex_workload.over_verified_requests('log', 151000)
        self.assertEqual(result['max_request_input'], 156029)
        self.assertEqual([r['kind'] for r in result['over_verified']], ['ack', 'questions'])

    def test_override_tables_are_toml(self):
        self.assertEqual(codex_workload.toml_value({':minimal': 'read', 'x': ['a']}), '{":minimal" = "read", "x" = ["a"]}')

    def test_hard_limit_kills_the_whole_process_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = 'sleep 60 & echo $! > child.pid; wait'
            with open(Path(tmp) / 'log', 'w') as out:
                code = codex_workload.run_limited(['sh', '-c', script], '', out, tmp, None, 0.4)
            self.assertEqual(code, 'timeout')
            child = int((Path(tmp) / 'child.pid').read_text())
            for _ in range(500):
                if not Path(f'/proc/{child}').exists() or 'Z' in Path(f'/proc/{child}/stat').read_text().split()[2]:
                    break
                time.sleep(0.01)
            else:
                self.fail('the shell started by the session outlived the hard limit')
            with open(Path(tmp) / 'log', 'w') as out:
                self.assertEqual(codex_workload.run_limited(['sh', '-c', 'read x; exit $x'], '3\n', out, tmp, None, 5), 3)

    def test_codex_turn_is_registered_and_start_rate_is_capped(self):
        for k in ('USAGE_GUARD_RUNS', 'USAGE_GUARD_DIR'):
            self.addCleanup(os.environ.pop, k, None)
        with tempfile.TemporaryDirectory() as tmp:
            os.environ['USAGE_GUARD_RUNS'], os.environ['USAGE_GUARD_DIR'] = tmp + '/runs', tmp + '/ug'
            lib = os.path.expanduser('~/.claude/lib')
            script = f"import sys,json;sys.path.insert(0,{lib!r});import usage_guard;print(json.dumps([[r['harness'],r['label']] for r in usage_guard.live_runs()]))"
            with open(Path(tmp) / 'log', 'w') as out:
                self.assertEqual(codex_workload.run_limited([sys.executable, '-c', script], '', out, tmp, None, 20), 0)
            self.assertEqual((Path(tmp) / 'log').read_text().strip(), '[["codex-local", "qwen-strata:codex_workload"]]')
            self.addCleanup(setattr, codex_workload, 'START_CAP', codex_workload.START_CAP)
            codex_workload.START_CAP = (1, 3600)   # one start was counted above
            with open(Path(tmp) / 'log', 'w') as out, self.assertRaises(codex_workload.guard_runs.Stopped):
                codex_workload.run_limited(['true'], '', out, tmp, None, 5)

    def test_wait_engine_idle_polls_native_status(self):
        import http.server
        import threading
        states, seen = [2, 1, 0], []

        class Status(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append((self.path, self.headers.get('Authorization')))
                body = json.dumps({'activity': {'requests': 9, 'in_flight': states.pop(0)}}).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(('127.0.0.1', 0), Status)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        original = codex_workload.time.sleep
        codex_workload.time.sleep = lambda seconds: None
        try:
            codex_workload.wait_engine_idle(f'http://127.0.0.1:{server.server_port}/strata', 'lease-key')
        finally:
            codex_workload.time.sleep = original
            server.shutdown()
            server.server_close()
        self.assertEqual(seen, [('/strata/v1/status', 'Bearer lease-key')] * 3)

    def test_frozen_plans_check_without_model(self):
        root = Path(__file__).resolve().parents[1] / 'benchmarks'
        for name in ('window-load-v1/pilot-plan.json',):
            plan, data = codex_workload.load_plan(root / name)
            authorization = plan.get('authorization', {})
            if authorization.get('approved') is True:  # only with a recorded user approval
                self.assertEqual(authorization.get('approved_by'), 'user')
                self.assertTrue(authorization.get('date') and authorization.get('scope'))
            own = window_bank.self_check(data)
            self.assertTrue(own['ok'], own)


if __name__ == '__main__':
    unittest.main()
