import inspect
import itertools
import json
import os
import random
import tempfile
import time
import unittest
from pathlib import Path

from tools.tuning import codex_workload, sampling_bank, staged_decision, window_bank


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


class SamplingBankTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bank = sampling_bank.build(7, 1)

    def test_build_is_deterministic_and_covers_every_cell(self):
        again = sampling_bank.build(7, 1)
        self.assertEqual(json.dumps(again['items']), json.dumps(self.bank['items']))
        cells = {(x['family'], x['tier']) for x in self.bank['items']}
        self.assertEqual(len(cells), len(sampling_bank.FAMILIES) * len(sampling_bank.TIERS))
        self.assertTrue(sampling_bank.self_check(self.bank)['ok'])

    def test_count_matches_brute_force(self):
        rng = random.Random(3)
        for _ in range(25):
            n, letters = rng.randint(2, 8), 'abc'[:rng.choice([2, 3])]
            forbidden = sorted({''.join(rng.choice(letters) for _ in range(rng.choice([2, 3]))) for _ in range(2)})
            tally = rng.choice([None, ('a', 'exact', 2), ('b', 'mod', 3, 1)])
            first_last, pairs = rng.choice([None, 'same', 'differ']), rng.choice([None, 1, 2])

            def fits(s):
                if any(f in s for f in forbidden):
                    return False
                if tally and tally[1] == 'exact' and s.count(tally[0]) != tally[2]:
                    return False
                if tally and tally[1] == 'mod' and s.count(tally[0]) % tally[2] != tally[3]:
                    return False
                if first_last and (s[0] == s[-1]) != (first_last == 'same'):
                    return False
                return pairs is None or sum(s[i] == s[i + 1] for i in range(len(s) - 1)) == pairs
            brute = sum(fits(''.join(t)) for t in itertools.product(letters, repeat=n))
            self.assertEqual(sampling_bank.count_strings(n, letters, forbidden, tally, first_last, pairs), brute)

    def test_trace_semantics(self):
        program = [('SET', 'A', 3), ('SET', 'C', 3), ('LABEL', 'L1'), ('SKIP', 'A', 4, 1), ('ADD', 'A', 2),
                   ('SUB', 'A', 1), ('OUT', 'A'), ('DEC', 'C'), ('LOOP', 'C', 'L1')]
        # SKIP fires once A exceeds 4, so ADD runs only while A <= 4; SUB is r - x
        self.assertEqual(sampling_bank.run_trace(program, None, False), [4, 5, 4])
        self.assertEqual(sampling_bank.run_trace([('SET', 'A', 2), ('SUB', 'A', 5), ('OUT', 'A')], 7, True), [3])

    def test_necklaces_match_brute_force(self):
        rng = random.Random(5)
        for _ in range(30):
            n, letters = rng.randint(1, 10), 'abc'[:rng.choice([2, 3])]
            forbidden = sorted({''.join(rng.choice(letters) for _ in range(rng.choice([2, 3]))) for _ in range(2)})
            a = rng.choice([None, rng.randint(0, n)])
            seen = {min(w[i:] + w[:i] for i in range(n)) for w in map(''.join, itertools.product(letters, repeat=n))
                    if sampling_bank.cyclic_ok(w, forbidden) and (a is None or w.count(letters[0]) == a)}
            self.assertEqual(sampling_bank.necklaces(n, letters, forbidden, a), len(seen))

    def test_counted_loop_cycle_detection_matches_plain_run(self):
        body = [('ADD', 'A', 'C'), ('SKIP', 'A', 'B', 1), ('MUL', 'B', 3), ('SUB', 'B', 'A')]
        program = [('SET', 'A', 4), ('SET', 'B', 7), ('SET', 'C', 5000), ('LABEL', 'L1')] + body + \
                  [('DEC', 'C'), ('LOOP', 'C', 'L1'), ('OUT', 'A'), ('OUT', 'B')]
        regs = {'A': 4, 'B': 7}
        plain = []
        c = 5000
        while c:
            # reference semantics with the counter exempt from reduction
            regs['A'] = (regs['A'] + c) % 97
            if not regs['A'] > regs['B']:
                regs['B'] = regs['B'] * 3 % 97
            regs['B'] = (regs['B'] - regs['A']) % 97
            c -= 1
        plain = [regs['A'], regs['B']]
        self.assertEqual(sampling_bank.run_counted_loop({'A': 4, 'B': 7}, body, 'C', 5000, 97, False, ['A', 'B']),
                         plain)

    def test_grid_answers_are_unique_solutions(self):
        for x in self.bank['items']:
            if x['family'] == 'grid' and x['tier'] <= 2:
                self.assertIn('exactly one solution', x['prompt'])
                self.assertEqual(len(x['answer'].split(',')), {1: 3, 2: 4}[x['tier']])

    def test_scoring_answers_and_hidden_tests(self):
        bank = sampling_bank.select(self.bank, [x['id'] for x in self.bank['items']])
        ledger = next(x for x in bank['items'] if x['family'] == 'ledger' and x['tier'] == 5)
        answer = next(x for x in bank['items'] if x['kind'] == 'answer')
        rules = ledger_rules_from(bank, ledger)
        with tempfile.TemporaryDirectory() as tmp:
            sampling_bank.export(bank, tmp)
            (Path(tmp) / 'answers' / (answer['number'] + '.txt')).write_text(' ' + answer['answer'].upper() + '\n')
            reference = inspect.getsource(sampling_bank.settle).replace('def settle(events, r):', 'def _settle(events, r):')
            (Path(tmp) / 'solutions' / (ledger['number'] + '.py')).write_text(
                reference + f'\nRULES = {rules!r}\n\ndef settle(events):\n    return _settle(events, RULES)\n')
            result = sampling_bank.score(bank, tmp)
        rows = {r['number']: r for r in result['rows']}
        self.assertTrue(rows[answer['number']]['correct'])
        self.assertTrue(rows[ledger['number']]['correct'])
        self.assertEqual(result['correct'], 2)

    def test_invertible_strfun_steps_are_injective(self):
        rng = random.Random(5)
        words = {''.join(rng.choice('abzAZu 0 9!') for _ in range(rng.randint(0, 9))) for _ in range(3000)}
        for seed in range(6):
            for op, text, invertible in sampling_bank.strfun_ops(random.Random(seed)):
                if invertible:
                    self.assertEqual(len({op(w) for w in words}), len(words), text)

    def test_hard_code_tiers_show_no_examples(self):
        for x in self.bank['items']:
            if x['kind'] == 'code':
                self.assertEqual('Examples:' in x['prompt'], x['tier'] <= 3, x['id'])
                self.assertEqual(x['entry'], 'decode' if (x['family'], x['tier']) == ('strfun', 5) else
                                 {'strfun': 'transform', 'ledger': 'settle'}[x['family']])

    def test_calibration_scores_the_deadline_snapshot(self):
        import shutil
        bank = sampling_bank.select(self.bank, [x['id'] for x in self.bank['items']])
        answer = next(x for x in bank['items'] if x['kind'] == 'answer')
        with tempfile.TemporaryDirectory() as tmp:
            sampling_bank.calibration_prepare(bank, tmp, 1, 10)
            run = Path(tmp) / 'run-1'
            (run / 'start-epoch').write_text(str(time.time()))
            shutil.copytree(run / 'workspace', run / 'deadline-snapshot')
            (run / 'deadline-snapshot' / 'answers' / (answer['number'] + '.txt')).write_text(answer['answer'])
            (run / 'workspace' / 'answers' / (answer['number'] + '.txt')).write_text('written after the limit')
            result = sampling_bank.calibration_score(bank, tmp)
        self.assertEqual(result['runs'][0]['scored'], 'deadline-snapshot')
        self.assertEqual(next(i for i in result['items'] if i['id'] == answer['id'])['passes'], 1)

    def test_broken_code_scores_zero(self):
        self.assertEqual(sampling_bank.run_tests(b'def f():\n    return 2\n', 'f', [{'args': [], 'expected': 1}]), 0)
        self.assertEqual(sampling_bank.run_tests(b'def f():\n    return 1\n', 'f', [{'args': [], 'expected': 1}]), 1)


def ledger_rules_from(bank, ledger):
    """Recreate the item's rules from its seed exactly as the generator drew them."""
    rng = random.Random(f'ledger/{ledger["tier"]}/{ledger["seed"]}')
    return sampling_bank.ledger_rules(rng, ledger['tier'])


class SandboxProbeTest(unittest.TestCase):
    @unittest.skipUnless(codex_workload.CODEX.exists(), 'native Codex not installed')
    def test_workspace_is_the_only_readable_place(self):
        from tools.tuning import sandbox_probe
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / '.tmp') as tmp:
            result = sandbox_probe.probe(tmp)
        self.assertTrue(result['ok'], result['problems'])


class WindowBankTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workload = window_bank.build(5)

    def test_self_check_and_sizes(self):
        self.assertTrue(window_bank.self_check(self.workload)['ok'])
        l130, l180 = self.workload['lengths']['L130'], self.workload['lengths']['L180']
        self.assertGreater(l130['tokens']['estimated_context_before_questions'], 110000)
        self.assertLess(l130['tokens']['estimated_context_before_questions'], 140000)
        self.assertGreater(l180['tokens']['estimated_context_before_questions'], 160000)
        self.assertGreaterEqual(len(l130['questions']), 30)

    def test_stale_answer_is_wrong(self):
        length = self.workload['lengths']['L130']
        updated = next(q for q in length['questions'] if q['kind'] != 'static')
        reply = f'{updated["id"]}: definitely-not-{updated["answer"]}\nQ99: x'
        result = window_bank.score(length, [reply])
        self.assertEqual(result['correct'], 0)
        self.assertEqual(result['wrong_on_updated'], 1)
        good = window_bank.score(length, [f'**{updated["id"]}:** `{updated["answer"].upper()}`'])
        self.assertEqual(good['correct'], 1)


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

    def test_loaded_startup_sha_excludes_deprecated_loop_block(self):
        import sys
        sys.path.append(str(codex_workload.STARTUP.parents[2] / 'src'))
        from startup_instructions import startup_prompt_bytes
        raw = codex_workload.STARTUP.read_bytes()
        self.assertEqual(codex_workload.loaded_startup_sha(), codex_workload.sha(startup_prompt_bytes(raw, False)))
        self.assertNotEqual(codex_workload.loaded_startup_sha(), codex_workload.sha(raw))

    def analyse(self, events):
        with tempfile.NamedTemporaryFile('w', suffix='.jsonl', delete=False) as f:
            f.write(rollout_lines(events))
        try:
            return codex_workload.analyse_session(f.name)
        finally:
            Path(f.name).unlink()

    def test_session_analysis(self):
        result = self.analyse([user('<environment_context>x</environment_context>'),
                               user('This is a long-context recall test.'), assistant('ACK 00'),
                               user('Batch 01/02. New records:'), assistant('ACK 01'),
                               {'type': 'compacted', 'payload': {}},
                               user('Batch 02/02. New records:'), assistant('ACK 02'),
                               user('Questions about the current state'), call('ls'), call('ls'), call('ls'),
                               assistant('Q01: a\nQ02: b')])
        self.assertEqual(result['compactions'], [{'after_user_turn': 'batch 01'}])
        self.assertEqual([r['turn'] for r in result['replies']], ['opening', 'batch 01', 'batch 02', 'questions'])
        self.assertEqual(result['replies'][-1]['text'], 'Q01: a\nQ02: b')
        self.assertEqual(result['loop']['longest_identical_call_run'], 3)
        spec = {'context_window': 206584}
        self.assertIn('L130 at 206584 compacted 1 times', codex_workload.session_effect('window', spec, 'L130', result))
        self.assertTrue(any('tool calls' in p for p in codex_workload.session_effect('window', spec, 'L180', result)))
        self.assertTrue(codex_workload.session_effect('sampling', spec, None, result))

    def test_escapes(self):
        calls = [{'arguments': json.dumps({'cmd': 'cat /w/problems/P01.md'})},
                 {'arguments': json.dumps({'cmd': 'cat /home/u/qwen_strata/benchmarks/set.json'})},
                 {'arguments': json.dumps({'cmd': 'python3 -c "print(1)" > /dev/null'})},
                 {'arguments': json.dumps({'cmd': 'cat ../x'})}]
        flagged = codex_workload.escapes(calls, '/w')
        self.assertEqual(len(flagged), 2)

    def test_next_round_mirrors_and_alternates(self):
        self.assertEqual(codex_workload.next_round(['a', 'b', 'c'], 1), ['a', 'b', 'c', 'c', 'b', 'a'])
        self.assertEqual(codex_workload.next_round(['a', 'b'], 2), ['b', 'a', 'a', 'b'])

    def test_override_tables_are_toml(self):
        self.assertEqual(codex_workload.toml_value({':minimal': 'read', 'x': ['a']}), '{":minimal" = "read", "x" = ["a"]}')

    def test_hard_limit_kills_the_whole_process_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = 'sleep 60 & echo $! > child.pid; wait'
            with open(Path(tmp) / 'log', 'w') as out:
                code = codex_workload.run_limited(['sh', '-c', script], '', out, tmp, None, 1)
            self.assertEqual(code, 'timeout')
            child = int((Path(tmp) / 'child.pid').read_text())
            for _ in range(50):
                if not Path(f'/proc/{child}').exists() or 'Z' in Path(f'/proc/{child}/stat').read_text().split()[2]:
                    break
                time.sleep(0.1)
            else:
                self.fail('the shell started by the session outlived the hard limit')
            with open(Path(tmp) / 'log', 'w') as out:
                self.assertEqual(codex_workload.run_limited(['sh', '-c', 'read x; exit $x'], '3\n', out, tmp, None, 5), 3)

    def test_timed_out_session_is_scored_on_written_files(self):
        data = sampling_bank.select(sampling_bank.build(7, 1), [x['id'] for x in sampling_bank.build(7, 1)['items']])
        first = next(x for x in data['items'] if x['kind'] == 'answer')
        plan = {'chunk': len(data['items']), 'instance_seconds_limit': 600}
        settled, limits = [], []

        def fake_exec(args, workspace, home, key, prompt, log, timeout, resume=None):
            limits.append(timeout)
            (Path(workspace) / 'answers' / (first['number'] + '.txt')).write_text(first['answer'] + '\n')
            return 'timeout', None, timeout

        original = codex_workload.codex_exec
        codex_workload.codex_exec = fake_exec
        try:
            with tempfile.TemporaryDirectory() as tmp:
                result = codex_workload.run_sampling(plan, data, {'context_window': 156584}, Path(tmp),
                                                     lambda here: [], 'k', lambda: 0, lambda: settled.append(1) or 2.0)
        finally:
            codex_workload.codex_exec = original
        self.assertEqual(limits, [600])
        self.assertEqual(settled, [1])
        session = result['sessions'][0]
        self.assertTrue(session['timed_out'])
        self.assertEqual(session['engine_idle_after_seconds'], 2.0)
        self.assertEqual((result['timed_out_sessions'], result['answered'], result['correct']), (1, 1, 1))
        self.assertGreater(result['score'], 0)

    def test_wait_engine_idle_polls_native_status(self):
        import http.server
        import threading
        states, seen = ['generating', 'reading', 'idle'], []

        class Status(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append((self.path, self.headers.get('Authorization')))
                body = json.dumps({'live': {'state': states.pop(0), 'queued': 0}}).encode()
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

    def test_session_limit_splits_the_instance_limit(self):
        data = {'items': [{}] * 25}
        self.assertEqual(codex_workload.session_limit({'chunk': 5, 'instance_seconds_limit': 600}, data), 120)
        self.assertEqual(codex_workload.session_limit({'pilot': True, 'chunk': 1, 'per_session_seconds_limit': 900},
                                                      data), 900)

    def test_frozen_plans_check_without_model(self):
        folder = Path(__file__).resolve().parents[1] / 'benchmarks/tuning-workloads-v1'
        for name in ('window-plan.json', 'sampling-pilot-plan.json'):
            plan, data, conditions = codex_workload.load_plan(folder / name)
            authorization = plan.get('authorization', {})
            if authorization.get('approved') is True:  # only with a recorded user approval
                self.assertEqual(authorization.get('approved_by'), 'user')
                self.assertTrue(authorization.get('date') and authorization.get('scope'))
            own = sampling_bank.self_check(data) if plan['workload'] == 'sampling' else window_bank.self_check(data)
            self.assertTrue(own['ok'], own)


if __name__ == '__main__':
    unittest.main()
