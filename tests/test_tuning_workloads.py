import inspect
import itertools
import json
import os
import random
import re
import tempfile
import time
import unittest
from pathlib import Path

from tools.tuning import codex_workload, sampling_bank, staged_decision, window_bank
from tools.tuning.sampling_families import codec, count, debug, incident, ledger, logic, machine, policy


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

    def test_bead_counts_match_brute_force(self):
        rng = random.Random(1)
        for _ in range(120):
            size, n = rng.choice([2, 3]), rng.randint(1, 8)
            allowed = [[1] * size for _ in range(size)]
            for x, y in rng.sample([(x, y) for x in range(size) for y in range(x, size)], rng.choice([0, 1, 2])):
                allowed[x][y] = allowed[y][x] = 0
            marked, k = rng.randrange(size), rng.randint(0, n)
            words = [w for w in itertools.product(range(size), repeat=n) if w.count(marked) == k
                     and all(allowed[w[i]][w[(i + 1) % n]] for i in range(n))]
            rotations = {min(w[i:] + w[:i] for i in range(n)) for w in words}
            turned = {min(min(v[i:] + v[:i] for i in range(n)) for v in (w, w[::-1])) for w in words}
            self.assertEqual(count.necklaces(n, allowed, marked, k), len(rotations))
            self.assertEqual(count.bracelets(n, allowed, marked, k), len(turned))

    def test_huge_counts_match_brute_force_on_small_n(self):
        rng = random.Random(2)
        for _ in range(60):
            n = rng.randint(2, 9)
            forbidden = sorted({''.join(rng.choice('abc') for _ in range(rng.choice([2, 3]))) for _ in range(2)})
            factors = {}
            for prime in (2, 3, 5, 7):
                while n % prime ** (factors.get(prime, 0) + 1) == 0:
                    factors[prime] = factors.get(prime, 0) + 1
            words = [''.join(w) for w in itertools.product('abc', repeat=n)]
            cyclic = {min(w[i:] + w[:i] for i in range(n)) for w in words
                      if not any(f in (w * 3)[i:i + len(f)] for i in range(n) for f in forbidden)}
            self.assertEqual(count.huge_necklaces(n, factors, 'abc', forbidden), len(cyclic))
            parity = rng.choice('abc')
            linear = sum(1 for w in words if not any(f in w for f in forbidden) and w.count(parity) % 2 == 0)
            self.assertEqual(count.huge_linear(n, 'abc', forbidden, parity), linear)
        for _ in range(30):
            n, size = rng.randint(1, 8), rng.choice([2, 3])
            allowed = [[1] * size for _ in range(size)]
            for x, y in rng.sample([(x, y) for x in range(size) for y in range(x, size)], rng.choice([1, 2])):
                allowed[x][y] = allowed[y][x] = 0
            factors = {}
            for prime in (2, 3, 5, 7):
                while n % prime ** (factors.get(prime, 0) + 1) == 0:
                    factors[prime] = factors.get(prime, 0) + 1
            words = [w for w in itertools.product(range(size), repeat=n)
                     if all(allowed[w[i]][w[(i + 1) % n]] for i in range(n))]
            turned = {min(min(v[i:] + v[:i] for i in range(n)) for v in (w, w[::-1])) for w in words}
            self.assertEqual(count.huge_bracelets(n, factors, allowed), len(turned), (n, allowed))

    def test_machine_semantics_and_cycle_skip(self):
        r = {'tier': 2, 'modulus': 100, 'sub': 'reversed', 'jumps': 'absolute', 'signed': True, 'shr_flag': True,
             'djnz': 'first'}
        program = [('SET', 'A', 5), ('SUB', 'A', 3), ('OUT', 'A'), ('SHR', 'A'), ('JF', 6), ('OUT', 'A'),
                   ('SET', 'C', 0), ('ADD', 'B', 1), ('DJNZ', 'C', 7), ('OUT', 'B'), ('SET', 'D', 60),
                   ('JLT', 'D', 1, 13), ('HALT',), ('OUT', 'D')]
        # SUB is 3 - 5 = 98; SHR of 98 leaves F false; DJNZ from 0 runs 100 times; 60 is negative when signed
        self.assertEqual(machine.run(program, r), [98, 49, 0, 60])
        self.assertEqual(machine.run(program, dict(r, signed=False)), [98, 49, 0])
        body = [('ADD', 'A', 'B'), ('MUL', 'B', 7), ('SUB', 'A', 3), ('SHR', 'B')]
        for count_ in (7, 1234, 99999):
            direct = machine.run([('SET', 'A', 4), ('SET', 'B', 9), ('REP', count_, 4)] + body
                                 + [('OUT', 'A'), ('OUT', 'B')], r)
            regs, flag = {'A': 4, 'B': 9}, False
            for _ in range(count_):
                regs['A'] = (regs['A'] + regs['B']) % 100
                regs['B'] = regs['B'] * 7 % 100
                regs['A'] = (3 - regs['A']) % 100
                regs['B'] //= 2
            self.assertEqual(direct, [regs['A'], regs['B']])
        original = machine.DIRECT_REP_LIMIT
        machine.DIRECT_REP_LIMIT = 10  # the same counts through cycle detection
        try:
            skipped = machine.run([('SET', 'A', 4), ('SET', 'B', 9), ('REP', 99999, 4)] + body
                                  + [('OUT', 'A'), ('OUT', 'B')], r)
        finally:
            machine.DIRECT_REP_LIMIT = original
        self.assertEqual(skipped, direct)

    def test_codec_steps_round_trip(self):
        for seed in range(80):
            rng = random.Random(seed)
            for level in (1, 2, 3, 4):
                chosen = codec.steps(rng, level)
                for text in codec.samples(rng, 40):
                    encoded = text
                    for encode, _, _ in chosen:
                        encoded = encode(encoded)
                    for _, decode, _ in reversed(chosen):
                        encoded = decode(encoded)
                    self.assertEqual(encoded, text)

    def test_ledger_rules(self):
        r = {'tier': 3, 'tie': 'descending', 'overdraft': 0, 'fee': 50, 'cap': 1000, 'waiver': 3000, 'rate': 100,
             'charge': 500, 'large': 400, 'fee_bp': 100}
        events = [{'id': 1, 't': 0, 'op': 'open', 'acct': 'a'}, {'id': 2, 't': 0, 'op': 'open', 'acct': 'b'},
                  {'id': 3, 't': 5, 'op': 'deposit', 'acct': 'a', 'amount': 4000},
                  {'id': 4, 't': 6, 'op': 'withdraw', 'acct': 'a', 'amount': 450},  # waived, counts 900 to the cap
                  {'id': 5, 't': 7, 'op': 'transfer', 'from': 'a', 'to': 'b', 'amount': 200},  # 1100 > cap
                  {'id': 6, 't': 86400, 'op': 'withdraw', 'acct': 'a', 'amount': 3000},  # fee max(50, 30), cap 6000
                  {'id': 7, 't': 86400, 'op': 'transfer', 'from': 'a', 'to': 'b', 'amount': 100},  # id 7 first
                  {'id': 8, 't': 86401, 'op': 'reverse', 'target': 4},
                  {'id': 9, 't': 86402, 'op': 'close', 'acct': 'b'},
                  {'id': 10, 't': 86403, 'op': 'interest'},
                  {'id': 11, 't': 86404, 'op': 'deposit', 'acct': 'b', 'amount': '5'}]
        result = ledger.settle(list(reversed(events)), r)
        # day 1: id 7 runs before id 6 and moves 100; id 6 counts 6000 > cap; reversing 4 gives back 450 (a 3900);
        # b (100) cannot close; interest adds 39 and 1
        self.assertEqual(result, {'balances': {'a': 3939, 'b': 101}, 'rejected': [5, 6, 9, 11], 'fees': 0})
        held = dict(r, tier=4, expiry=1, fee=0, fee_bp=0)
        events = [{'id': 1, 't': 0, 'op': 'open', 'acct': 'a'}, {'id': 2, 't': 1, 'op': 'deposit', 'acct': 'a', 'amount': 1000},
                  {'id': 3, 't': 2, 'op': 'hold', 'acct': 'a', 'amount': 300},
                  {'id': 4, 't': 3, 'op': 'withdraw', 'acct': 'a', 'amount': 800},  # only 700 is available
                  {'id': 5, 't': 4, 'op': 'close', 'acct': 'a'},  # an active hold blocks closing
                  {'id': 6, 't': 5, 'op': 'capture', 'target': 3},
                  {'id': 7, 't': 6, 'op': 'release', 'target': 3}]  # already captured
        self.assertEqual(ledger.settle(events, held), {'balances': {'a': 700}, 'rejected': [4, 5, 7], 'fees': 0})
        rng = random.Random(4)
        for level in (1, 2, 3, 4):  # money is conserved apart from deposits, withdrawals, fees and interest
            r = ledger.rules(rng, level)
            for _ in range(30):
                events = ledger.events(rng, r)
                result = ledger.settle(events, r)
                self.assertEqual(len(result['rejected']), len(set(result['rejected'])))
                if level < 3:
                    rejected = set(result['rejected'])
                    reversed_ids = {e['target'] for e in events if e['op'] == 'reverse' and e['id'] not in rejected}
                    flow = sum((e['amount'] if e['op'] == 'deposit' else -e['amount'])
                               for e in events if e['op'] in ('deposit', 'withdraw') and e['id'] not in rejected
                               and e['id'] not in reversed_ids)
                    self.assertEqual(sum(result['balances'].values()) + result['fees'], flow)

    def test_debug_packages_reference_passes_and_each_bug_fails(self):
        for name, package in debug.PACKAGES.items():
            files = dict(package['files'])
            for key, value in (package['setup'](random.Random(1)).items() if 'setup' in package else []):
                files = {n: t.replace(key, value) for n, t in files.items()}
            args = package['args'](random.Random(2), 40)
            reference = debug.call(files, package['module'], package['entry'], args)
            self.assertGreater(sum('value' in r for r in reference), 30, name)
            for bug in package['bugs']:
                broken = debug.call(debug.inject(files, [bug]), package['module'], package['entry'], args)
                self.assertNotEqual(broken, reference, (name, bug[3]))

    def test_scoring_answers_code_and_packages(self):
        bank = sampling_bank.select(self.bank, [x['id'] for x in self.bank['items']])
        answer = next(x for x in bank['items'] if x['kind'] == 'answer')
        package = next(x for x in bank['items'] if x['kind'] == 'package')
        code = next(x for x in bank['items'] if x['family'] == 'ledger' and x['tier'] == 3)
        rules = ledger.rules(random.Random(f'ledger/3/{code["seed"]}'), 4)
        with tempfile.TemporaryDirectory() as tmp:
            sampling_bank.export(bank, tmp)
            self.assertIn(f'solutions/{package["number"]}/', (Path(tmp) / 'problems' / (package['number'] + '.md')).read_text())
            (Path(tmp) / 'answers' / (answer['number'] + '.txt')).write_text(' ' + answer['answer'].upper() + '\n')
            reference = inspect.getsource(ledger).replace('def settle(events, r):', 'def _settle(events, r):')
            (Path(tmp) / 'solutions' / (code['number'] + '.py')).write_text(
                reference + f'\nRULES = {rules!r}\n\ndef settle(events):\n    return _settle(events, RULES)\n')
            for name, raw in sampling_bank.reference_files(package).items():
                (Path(tmp) / 'solutions' / package['number'] / name).write_bytes(raw)
            result = sampling_bank.score(bank, tmp)
        rows = {r['number']: r for r in result['rows']}
        self.assertTrue(rows[answer['number']]['correct'])
        self.assertTrue(rows[code['number']]['correct'])
        self.assertTrue(rows[package['number']]['correct'])
        self.assertEqual(result['correct'], 3)

    def test_code_problems_show_no_example(self):  # v4 tier 1 is the v3 level 2, which already had none
        for x in self.bank['items']:
            if x['family'] in ('ledger', 'codec'):
                self.assertNotIn('xample', x['prompt'].split('No examples')[0], x['id'])

    def test_logic_puzzles_have_exactly_one_arrangement(self):
        for tier in sampling_bank.TIERS:
            for seed in range(2):
                rng = random.Random(f'logic-test/{tier}/{seed}')
                n, values, hidden, clues = logic.puzzle(rng, tier) or self.fail('no puzzle')
                self.assertEqual(logic.count(n, values, clues), 1)
                where = lambda cat, value: hidden[cat][values[cat].index(value)]
                self.assertTrue(all(logic.holds(c, where) for c in clues))
                for k in range(len(clues)):  # every clue is needed
                    self.assertEqual(logic.count(n, values, clues[:k] + clues[k + 1:]), 2)

    def test_policy_misreadings_each_change_some_answer(self):
        from datetime import date
        for x in (i for i in self.bank['items'] if i['family'] == 'policy'):
            r, wrongs = x['policy']['rules'], x['policy']['misreadings']
            cases = [{k: date.fromisoformat(v) if k in ('event', 'application', 'registered', 'born') else v
                      for k, v in c.items()} for c in x['policy']['cases']]
            self.assertEqual(','.join(str(policy.fee(c, r)) for c in cases), x['answer'])
            self.assertEqual(len({c['name'] for c in cases}), len(cases))
            for w in wrongs:
                self.assertNotEqual(','.join(str(policy.fee(c, r, {w})) for c in cases), x['answer'], (x['id'], w))

    def test_incident_root_is_in_the_log(self):
        for tier in sampling_bank.TIERS:
            for seed in range(6):
                x = incident.item(random.Random(f'incident-test/{tier}/{seed}'), tier)
                service, code = x['incident']['root']
                self.assertIsNotNone(x['incident']['root_line'], x['incident']['scenario'])
                self.assertEqual(x['answer'], f'{service},{code}'.lower())
                self.assertIn(f'- {code}:', x['prompt'])
                self.assertIn(f' {service} ', x['prompt'].split('```')[1])

    def test_calibration_scores_the_deadline_snapshot(self):
        import shutil
        bank = sampling_bank.select(self.bank, [x['id'] for x in self.bank['items']])
        answer = next(x for x in bank['items'] if x['kind'] == 'answer')
        with tempfile.TemporaryDirectory() as tmp:
            manifest = sampling_bank.calibration_prepare(bank, tmp, 1, 10, 5)
            groups = sampling_bank.chunks(bank['items'], 5)
            self.assertEqual(len(manifest['jobs']), len(groups))
            g = next(k for k, group in enumerate(groups, 1) if answer in group)
            job = Path(tmp) / 'run-1' / f'group-{g:02d}'
            self.assertEqual(len(list((job / 'workspace' / 'problems').glob('*.md'))), len(groups[g - 1]))
            (job / 'start-epoch').write_text(str(time.time()))
            shutil.copytree(job / 'workspace', job / 'deadline-snapshot')
            (job / 'deadline-snapshot' / 'answers' / (answer['number'] + '.txt')).write_text(answer['answer'])
            (job / 'workspace' / 'answers' / (answer['number'] + '.txt')).write_text('written after the limit')
            result = sampling_bank.calibration_score(bank, tmp)
        self.assertEqual(result['runs'][0]['scored'][f'group-{g:02d}'], 'deadline-snapshot')
        self.assertEqual(next(i for i in result['items'] if i['id'] == answer['id'])['passes'], 1)

    def test_broken_code_scores_zero(self):
        self.assertEqual(sampling_bank.run_tests({'s.py': b'def f():\n    return 2\n'}, 's', 'f',
                                                 [{'args': [], 'expected': 1}]), 0)
        self.assertEqual(sampling_bank.run_tests({'s.py': b'def f():\n    return 1\n'}, 's', 'f',
                                                 [{'args': [], 'expected': 1}]), 1)

    def test_choose_mixes_right_and_wrong_items_per_family(self):
        families = ['a', 'b']
        items = [{'id': f'{f}{k}', 'number': f'{f}{k}', 'family': f, 'tier': 1 + k % 2}
                 for f in families for k in range(6)]
        bank = {'items': items}
        calibration = {'runs': [{'run': 1}, {'run': 2}],
                       'items': [{'id': x['id'], 'passes': 0 if x['id'] == 'a0' else 1,
                                  'passed_runs': [] if x['id'] == 'a0' else [2 if x['family'] == 'b' else 1]}
                                 for x in items]}
        rows = [{'id': x['id'], 'correct': int(x['id'][1]) % 2 == 0, 'approx_seconds': 10 + int(x['id'][1]),
                 'group_timed_out': False} for x in items]
        groups = [{'items': [x['number'] for x in items if x['family'] == f], 'valid': True, 'compactions': 0,
                   'context_after': 30000} for f in families]
        result = sampling_bank.choose(bank, calibration, {'items': rows, 'groups': groups}, 4)
        self.assertTrue(result['ok'], result)
        # a0 is excluded (Opus never solved it); per family one right and one wrong, shortest first
        self.assertEqual(result['ids'], ['a2', 'a1', 'b0', 'b1'])
        self.assertEqual((result['pilot_accuracy'], result['expected_instance_seconds']), (0.5, 44))
        self.assertEqual(result['max_group_context'], 30000)
        groups[0]['compactions'] = 1
        self.assertFalse(sampling_bank.choose(bank, calibration, {'items': rows, 'groups': groups}, 4)['ok'])


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
        self.assertIn('L130 at 206584 compacted 1 times', codex_workload.window_effect(spec, 'L130', result))
        self.assertTrue(any('tool calls' in p for p in codex_workload.window_effect(spec, 'L180', result)))

    def test_escapes(self):
        calls = [{'arguments': json.dumps({'cmd': 'cat /w/problems/P01.md'})},
                 {'arguments': json.dumps({'cmd': 'cat /home/u/qwen_strata/benchmarks/set.json'})},
                 {'arguments': json.dumps({'cmd': 'python3 -c "print(1)" > /dev/null'})},
                 {'arguments': json.dumps({'cmd': 'cat ../x'})}]
        flagged = codex_workload.escapes(calls, '/w')
        self.assertEqual(len(flagged), 2)

    def test_escapes_ignore_code_and_sed_scripts(self):
        # pilot run3: integer division, sed scripts and arithmetic were flagged as paths
        harmless = ['python3 - <<EOF\nprint(7 // 2, n /1000)\nEOF', "sed -i 's/if op/if le/g' scratch.py",
                    "sed -i '/ns = trans(s0, x0)/d' s.py", 'print("...")', 'cat /w/ws/solutions/P01.py']
        risky = ['cat > /tmp/sim.py <<EOF\nx = 1\nEOF', 'rg -l TIDA /home/u/qwen_strata', 'ls ~/.codex',
                 'cat ../codex-home/sessions/x.jsonl', 'echo $CODEX_HOME']
        calls = lambda texts: [{'arguments': json.dumps({'cmd': t})} for t in texts]
        self.assertEqual(codex_workload.escapes(calls(harmless), '/w/ws'), [])
        self.assertEqual(len(codex_workload.escapes(calls(risky), '/w/ws')), len(risky))

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

    def test_groups_mix_directions_and_tiers(self):
        bank = {'items': [{'id': f'{f}{t}{k}', 'family': f, 'tier': t}
                          for f in sampling_bank.FAMILIES for t in sampling_bank.TIERS for k in range(3)]}
        ids = sampling_bank.grouped(bank, 12)
        items = [next(x for x in bank['items'] if x['id'] == i) for i in ids]
        groups = codex_workload.groups(items, 12)
        self.assertEqual([len(g) for g in groups], [12] * 6)
        for g in groups:  # every direction and every tier in each group, the same time limit
            self.assertEqual({x['family'] for x in g}, set(sampling_bank.FAMILIES))
            self.assertEqual(sorted(x['tier'] for x in g), [1] * 4 + [2] * 4 + [3] * 4)
            self.assertEqual(codex_workload.group_seconds_limit(g, 30), 720)
        uneven = codex_workload.groups(items[:70], 12)  # sizes differ by at most one, nothing lost or reordered
        self.assertEqual([len(g) for g in uneven], [12, 12, 12, 12, 11, 11])
        self.assertEqual([x for g in uneven for x in g], items[:70])

    def test_cluster_se_treats_groups_as_clusters(self):
        rows = [{'group': g, 'points': 1, 'correct': c} for g, cs in enumerate([[1, 1, 1], [0, 0, 0], [1, 1, 1],
                                                                              [0, 0, 0]]) for c in cs]
        result = sampling_bank.cluster_se(rows)
        # group totals 3, 0, 3, 0 around 1.5 each: 4/3 * 4 * 2.25 / 144 = 1/12; independent 12 * 0.25 / 144
        self.assertEqual((result['score'], result['clusters']), (0.5, 4))
        self.assertAlmostEqual(result['se'], (1 / 12) ** 0.5)
        self.assertAlmostEqual(result['design_effect'], 4)
        self.assertIsNone(sampling_bank.cluster_se(rows[:3])['se'])

    def test_sampling_recovery_runs_only_the_chosen_groups_with_full_set_numbering(self):
        self.assertEqual(codex_workload.parse_groups('7-10'), [7, 8, 9, 10])
        self.assertEqual(codex_workload.parse_groups('2,5,7-8'), [2, 5, 7, 8])
        bank = sampling_bank.build(7, 1)
        data = sampling_bank.select(bank, sampling_bank.grouped(bank, 2))
        plan = {'group_size': 2, 'group_seconds_per_tier': 30, 'only_groups': [3, 4]}
        everything = codex_workload.groups(data['items'], 2)
        seen = []

        def fake_exec(args, workspace, home, key, prompt, log, timeout, resume=None):
            seen.append(sorted(p.stem for p in (Path(workspace) / 'problems').glob('*.md')))
            path = Path(home) / 'sessions/2026/10/12/rollout-a.jsonl'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('')
            return 0, 'thread', 1.0

        original = codex_workload.codex_exec
        codex_workload.codex_exec = fake_exec
        try:
            with tempfile.TemporaryDirectory() as tmp:
                result = codex_workload.run_sampling(plan, data, {'context_window': 156584}, Path(tmp),
                                                     lambda here: [], 'k', lambda: 0, lambda: 0)
                folders = sorted(p.name for p in Path(tmp).iterdir())
                saved = json.loads((Path(tmp) / 'group-04-1/group.json').read_text())
        finally:
            codex_workload.codex_exec = original
        self.assertEqual((saved['group'], saved['log_bytes']), (4, [0, 0]))
        self.assertIn('score', saved)
        self.assertEqual(seen, [sorted(x['number'] for x in everything[i]) for i in (2, 3)])
        self.assertEqual(folders, ['group-03-1', 'group-04-1'])
        self.assertEqual([r['group'] for r in result['groups']], [3, 4])
        self.assertEqual(len(result['items']), len(everything[2]) + len(everything[3]))

    def test_sampling_runs_groups_with_limits_and_reruns_compacted_groups(self):
        bank = sampling_bank.build(7, 1)
        data = sampling_bank.select(bank, sampling_bank.grouped(bank, 2))
        everything = codex_workload.groups(data['items'], 2)
        first, second = everything[:2]
        third = next(g for g in everything[2:] if g[0]['kind'] == 'answer')
        plan = {'group_size': 2, 'group_seconds_per_tier': 30}
        seen, settled = [], []

        def fake_exec(args, workspace, home, key, prompt, log, timeout, resume=None):
            problems = sorted(p.stem for p in (Path(workspace) / 'problems').glob('*.md'))
            seen.append((problems, timeout, resume))
            group = [x for x in data['items'] if x['number'] in problems]
            path = Path(home) / 'sessions/2026/10/12/rollout-a.jsonl'
            path.parent.mkdir(parents=True, exist_ok=True)
            events = [{'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {
                'last_token_usage': {'total_tokens': 20000}}}}]
            # group 1 compacts once; group 2 compacts every time
            if group == second or (group == first and sum(s[0] == problems for s in seen) == 1):
                events.append({'type': 'compacted', 'payload': {}})
            path.write_text(''.join(json.dumps(e) + '\n' for e in events))
            if group[0]['kind'] == 'answer':
                (Path(workspace) / 'answers' / (group[0]['number'] + '.txt')).write_text(group[0]['answer'])
            if group == third:  # one answer written, then the hard limit
                return 'timeout', None, timeout
            return 0, 'thread', 1.5

        original = codex_workload.codex_exec
        codex_workload.codex_exec = fake_exec
        try:
            with tempfile.TemporaryDirectory() as tmp:
                result = codex_workload.run_sampling(plan, data, {'context_window': 156584}, Path(tmp),
                                                     lambda here: [], 'k', lambda: 0, lambda: settled.append(1) or 2.0)
                folders = sorted(p.name for p in Path(tmp).iterdir())
        finally:
            codex_workload.codex_exec = original
        numbers = lambda xs: [x['number'] for x in xs]
        # each session sees only its group, one fresh session per group (never resumed), limit = sum of tiers x 30
        limit = lambda g: 30 * sum(x['tier'] for x in g)
        self.assertEqual(seen[0], (sorted(numbers(first)), limit(first), None))
        self.assertEqual(seen[1], (sorted(numbers(first)), limit(first), None))
        self.assertEqual([s[0] for s in seen[2:4]], [sorted(numbers(second))] * 2)
        self.assertIn((sorted(numbers(third)), limit(third), None), seen[4:])
        self.assertEqual(len(seen), len(codex_workload.groups(data['items'], 2)) + 2)
        self.assertEqual(folders[:4], ['group-01-1', 'group-01-2', 'group-02-1', 'group-02-2'])
        runs = result['groups']
        self.assertEqual([(r['group'], r['attempt'], r['valid']) for r in runs[:4]],
                         [(1, 1, False), (1, 2, True), (2, 1, False), (2, 2, True)])
        self.assertEqual(runs[1]['effect_problems'], [])
        self.assertEqual(runs[3]['effect_problems'], ['group 2 compacted in all 2 attempts'])
        self.assertEqual(result['compacted_attempts'], 2)
        # the timed-out group is settled and scored on what it wrote
        timed = next(r for r in runs if r['timed_out'])
        self.assertEqual((timed['items'], timed['engine_idle_after_seconds']), (numbers(third), 2.0))
        self.assertEqual((settled, result['timed_out_groups']), ([1], 1))
        rows = {r['number']: r for r in result['items']}
        self.assertTrue(rows[third[0]['number']]['correct'])
        self.assertFalse(rows[third[1]['number']]['answered'])
        self.assertTrue(rows[third[1]['number']]['approx_from_remainder'])
        self.assertEqual(len(result['items']), len(data['items']))

    def test_sampling_trace_is_checked_in_the_service_log(self):
        spec = json.loads((Path(codex_workload.ROOT) / 'benchmarks/tuning-workloads-v1/sampling-pilot-plan.json')
                          .read_text())['conditions']['sampling-greedy']
        trace = 'missing log line: \\[native-sampling-trace\\][^\\n]*top_k=20'
        args = ('engine lines only\n', {}, spec, None, {'args': []})
        self.assertIn(trace, codex_workload.engine_effect(*args)[0])
        problems = codex_workload.engine_effect(*args, '[native-sampling-trace] top_k=20\n')[0]
        self.assertFalse([p for p in problems if 'native-sampling-trace' in p])
        problems = codex_workload.engine_effect(*args, '[native-sampling-trace] temperature=0.6 top_k=20\n')[0]
        self.assertTrue([p for p in problems if 'native-sampling-trace' in p])

    def test_free_commit_gate_waits_outside_group_time_and_gives_up(self):
        clock, slept, lines = [0.0], [], []
        readings = iter([5.0, 7.9, 12.0])

        def sleep(seconds):
            slept.append(seconds)
            clock[0] += seconds

        waited = codex_workload.wait_for_free_commit(lambda: next(readings), 8, lines.append, sleep,
                                                     lambda: clock[0])
        self.assertEqual((waited, slept, len(lines)), (60.0, [30, 30], 2))
        self.assertIn('5.0 GiB < 8 GiB', lines[0])
        self.assertEqual(codex_workload.wait_for_free_commit(lambda: 8.0, 8, lines.append, sleep, lambda: 0.0), 0.0)
        clock[0] = 0.0
        with self.assertRaisesRegex(RuntimeError, 'below 8 GiB for 600 s'):
            codex_workload.wait_for_free_commit(lambda: 2.0, 8, lambda line: None, sleep, lambda: clock[0])
        self.assertEqual(clock[0], codex_workload.COMMIT_WAIT_LIMIT_SECONDS)

    def test_sampling_gate_runs_before_each_group_and_its_failure_stops_the_run(self):
        bank = sampling_bank.build(7, 1)
        data = sampling_bank.select(bank, sampling_bank.grouped(bank, 2))
        plan = {'group_size': 2, 'group_seconds_per_tier': 30, 'only_groups': [1, 2, 3]}
        events = []

        def fake_exec(args, workspace, home, key, prompt, log, timeout, resume=None):
            events.append('exec')
            path = Path(home) / 'sessions/2026/10/12/rollout-a.jsonl'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('')
            return 0, 'thread', 1.0

        def gate():
            events.append('gate')
            if events.count('gate') == 3:
                raise RuntimeError('commit exhausted')
            return 12.5

        original = codex_workload.codex_exec
        codex_workload.codex_exec = fake_exec
        try:
            with tempfile.TemporaryDirectory() as tmp:
                result = codex_workload.run_sampling({**plan, 'only_groups': [1]}, data, {'context_window': 156584},
                                                     Path(tmp) / 'a', lambda here: [], 'k', lambda: 0, lambda: 0,
                                                     gate)
                with self.assertRaisesRegex(RuntimeError, 'commit exhausted'):
                    codex_workload.run_sampling(plan, data, {'context_window': 156584}, Path(tmp) / 'b',
                                                lambda here: [], 'k', lambda: 0, lambda: 0, gate)
        finally:
            codex_workload.codex_exec = original
        self.assertEqual(events, ['gate', 'exec', 'gate', 'exec', 'gate'])
        self.assertEqual((result['groups'][0]['commit_wait_seconds'], result['groups'][0]['seconds']), (12.5, 1.0))

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
