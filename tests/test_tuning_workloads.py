import functools
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

from tools.tuning import codex_workload, sampling_bank, sampling_families, staged_decision, window_bank
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


@functools.cache
def built_bank():
    return json.dumps(sampling_bank.build(7, (1, 1, 1)))


def small_bank():
    """One item per family and tier, built once for the whole test run (logic tier 3 takes up to a minute)."""
    return json.loads(built_bank())


class SamplingBankTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bank = small_bank()

    def test_build_is_deterministic_and_covers_every_cell(self):
        for x in self.bank['items']:  # every item again from its seed (logic tier 3 skipped: slow)
            if (x['family'], x['tier']) != ('logic', 3):
                again = dict(sampling_families.item(x['family'], x['tier'], x['seed']), number=x['number'])
                self.assertEqual(json.dumps(again), json.dumps(x), x['id'])
        cells = {(x['family'], x['tier']) for x in self.bank['items']}
        self.assertEqual(len(cells), len(sampling_bank.FAMILIES) * len(sampling_bank.TIERS))
        self.assertTrue(sampling_bank.self_check(self.bank)['ok'])

    def test_bracelet_counts_match_brute_force_on_small_n(self):  # level 4
        rng = random.Random(2)
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

    def test_residue_counts_match_brute_force_on_small_n(self):  # levels 5-6
        rng = random.Random(3)
        for _ in range(150):
            n, size, q = rng.randint(1, 8), rng.choice([2, 3]), rng.choice([2, 3, 4, 5])
            allowed = [[1] * size for _ in range(size)]
            for x, y in rng.sample([(x, y) for x in range(size) for y in range(x, size)], rng.choice([0, 1, 2])):
                allowed[x][y] = allowed[y][x] = 0
            marked, r = rng.randrange(size), rng.randrange(q)
            factors = {}
            for prime in (2, 3, 5, 7):
                while n % prime ** (factors.get(prime, 0) + 1) == 0:
                    factors[prime] = factors.get(prime, 0) + 1
            words = [w for w in itertools.product(range(size), repeat=n) if w.count(marked) % q == r
                     and all(allowed[w[i]][w[(i + 1) % n]] for i in range(n))]
            rotations = {min(w[i:] + w[:i] for i in range(n)) for w in words}
            turned = {min(min(v[i:] + v[:i] for i in range(n)) for v in (w, w[::-1])) for w in words}
            case = (n, allowed, marked, q, r)
            self.assertEqual(count.residue_necklaces(n, factors, allowed, marked, q, r), len(rotations), case)
            self.assertEqual(count.residue_bracelets(n, factors, allowed, marked, q, r), len(turned), case)

    def test_residue_counts_add_up_on_huge_n(self):
        # summing over the remainders, or q = 1, must give the level 4 count of all bracelets
        for seed in range(3):
            x = count.item(random.Random(f'count-sum/{seed}'), 6)['count']
            n, factors, allowed, marked = x['n'], {int(k): v for k, v in x['factors'].items()}, x['allowed'], x['marked']
            whole = count.huge_bracelets(n, factors, allowed)
            self.assertEqual(count.residue_bracelets(n, factors, allowed, marked, 1, 0), whole)
            parts = sum(count.residue_bracelets(n, factors, allowed, marked, x['q'], r) for r in range(x['q']))
            self.assertEqual(parts % count.PRIME, whole)

    def test_machine_affine_blocks_match_direct_simulation(self):  # levels 5-6
        for m in machine.PRIMES:
            order = 1
            for prime, power in machine.ORDER_FACTORS[m].items():
                order *= prime ** power
            self.assertEqual(order, m * (m - 1) * (m + 1) * (m * m + 1) * (m * m + m + 1))
        p = 998244353  # 3 is a primitive root: x -> 3x has period p - 1, x -> x + 5 has period p
        self.assertEqual(machine.orbit_period([[3, 0], [0, 1]], [1, 1], p), p - 1)
        self.assertEqual(machine.orbit_period([[1, 5], [0, 1]], [7, 1], p), p)
        r = {'tier': 5, 'modulus': 1000000007, 'sub': 'reversed', 'jumps': 'absolute', 'signed': True,
             'shr_flag': True, 'djnz': 'first'}
        body = [('ADD', 'A', 'B'), ('MUL', 'B', 999999999), ('SUB', 'A', 3), ('ADD', 'B', 700000000)]
        original = machine.DIRECT_REP_LIMIT
        for count_ in (1, 2, 7, 1234):
            regs, flag = {'A': 4, 'B': 9}, False
            for _ in range(count_):
                regs['A'] = (regs['A'] + regs['B']) % r['modulus']
                regs['B'] = regs['B'] * 999999999 % r['modulus']
                flag = 3 - regs['A'] < 0
                regs['A'] = (3 - regs['A']) % r['modulus']
                flag = regs['B'] + 700000000 >= r['modulus']
                regs['B'] = (regs['B'] + 700000000) % r['modulus']
            program = [('SET', 'A', 4), ('SET', 'B', 9), ('REP', count_, 4)] + body + [
                ('JF', 9), ('OUT', 'A'), ('OUT', 'B')]
            expected = [regs['B']] if flag else [regs['A'], regs['B']]
            self.assertEqual(machine.run(program, r), expected)
            machine.DIRECT_REP_LIMIT = 0  # the same count through the matrix power
            try:
                self.assertEqual(machine.run(program, r), expected)
            finally:
                machine.DIRECT_REP_LIMIT = original
        rng = random.Random(4)
        for tier in (5, 6):
            for seed in range(4):
                x = machine.item(random.Random(f'machine-small/{tier}/{seed}'), tier)['machine']
                r = x['variant']
                program = [tuple([ins[0], rng.randint(1, 3000)] + ins[2:]) if ins[0] == 'REP' else tuple(ins)
                           for ins in x['program']]
                for w in [r] + machine.misreadings(r):
                    direct = machine.run(program, w)
                    machine.DIRECT_REP_LIMIT = 0
                    try:
                        self.assertEqual(machine.run(program, w), direct, (tier, seed, w))
                    finally:
                        machine.DIRECT_REP_LIMIT = original

    def test_machine_levels_need_more_than_cycle_detection(self):
        for tier in (5, 6):
            x = machine.item(random.Random(f'machine-period/{tier}'), tier)
            info = {}
            machine.run([tuple(ins) for ins in x['machine']['program']], x['machine']['variant'], info)
            self.assertEqual(len(info['orbits']), tier - 4)
            for matrix, vector in info['orbits']:
                self.assertGreater(machine.orbit_period(matrix, vector, x['machine']['variant']['modulus']),
                                   machine.PERIOD_FLOOR)
            self.assertTrue(all(ins[1] >= 10 ** 15 for ins in x['machine']['program'] if ins[0] == 'REP'))
            self.assertNotIn('SHR', x['prompt'])

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
            for level in (4, 5, 6):
                chosen = codec.steps(rng, level)
                self.assertEqual(len(chosen), {4: 9, 5: 8, 6: 9}[level])
                for text in codec.samples(rng, 40):
                    encoded = text
                    for encode, _, _ in chosen:
                        encoded = encode(encoded)
                    for _, decode, _ in reversed(chosen):
                        encoded = decode(encoded)
                    self.assertEqual(encoded, text)

    def test_codec_bwt_and_autokey(self):
        encode, decode, _ = codec.bwt()
        # "|" sorts after letters but before "~": sorted rotations "a~|b", "ba~|", "|ba~", "~|ba"
        self.assertEqual(encode('ba~'), 'b|~a')
        for text in ('', 'a', 'banana', '~~a~', 'Zz 9', 'aaaa   bbbbbbbbbbbb!!'):
            self.assertEqual(decode(encode(text)), text)
        by_input, _, _ = codec.autokey(1, 'input', 0)
        by_output, _, _ = codec.autokey(1, 'output', 1)
        self.assertEqual(by_input('ab c'), 'bb d')   # a+1; b by input a (0); c by input b (1)
        self.assertEqual(by_output('ab c'), 'bd g')  # a+1; b by output b (2); c by output d (4)
        for level in (5, 6):
            prompt = codec.item(random.Random(f'codec-test/{level}'), level)['prompt']
            self.assertIn('before "~" (126)', prompt)
            self.assertIn('without "|"', prompt)

    def test_ledger_rules(self):
        r = {'tier': 4, 'tie': 'descending', 'overdraft': 0, 'fee': 50, 'cap': 1000, 'waiver': 3000, 'rate': 100,
             'charge': 500, 'large': 400, 'fee_bp': 100, 'expiry': 1, 'sweep_max': None, 'sweep_fee': None}
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
        held = dict(r, fee=0, fee_bp=0)
        events = [{'id': 1, 't': 0, 'op': 'open', 'acct': 'a'}, {'id': 2, 't': 1, 'op': 'deposit', 'acct': 'a', 'amount': 1000},
                  {'id': 3, 't': 2, 'op': 'hold', 'acct': 'a', 'amount': 300},
                  {'id': 4, 't': 3, 'op': 'withdraw', 'acct': 'a', 'amount': 800},  # only 700 is available
                  {'id': 5, 't': 4, 'op': 'close', 'acct': 'a'},  # an active hold blocks closing
                  {'id': 6, 't': 5, 'op': 'capture', 'target': 3},
                  {'id': 7, 't': 6, 'op': 'release', 'target': 3}]  # already captured
        self.assertEqual(ledger.settle(events, held), {'balances': {'a': 700}, 'rejected': [4, 5, 7], 'fees': 0})

    def test_ledger_sweeps(self):
        base = {'tie': 'ascending', 'overdraft': 100, 'fee': 0, 'fee_bp': 0, 'cap': 1000, 'waiver': 99999,
                'rate': 100, 'charge': 500, 'large': 5000, 'expiry': 1, 'sweep_max': 300}
        events = [{'id': 1, 't': 0, 'op': 'open', 'acct': 'a'}, {'id': 2, 't': 0, 'op': 'open', 'acct': 'b'},
                  {'id': 3, 't': 1, 'op': 'deposit', 'acct': 'a', 'amount': 100},
                  {'id': 4, 't': 1, 'op': 'deposit', 'acct': 'b', 'amount': 1000},
                  {'id': 5, 't': 2, 'op': 'link', 'acct': 'a', 'backup': 'b'},
                  {'id': 6, 't': 10, 'op': 'withdraw', 'acct': 'a', 'amount': 500},  # sweeps 300 (max), overdraft 100
                  {'id': 7, 't': 11, 'op': 'withdraw', 'acct': 'a', 'amount': 50},   # sweeps 150, a back to 0
                  {'id': 8, 't': 12, 'op': 'freeze', 'acct': 'b'},
                  {'id': 9, 't': 13, 'op': 'withdraw', 'acct': 'a', 'amount': 80},   # frozen backup: overdraft only
                  {'id': 10, 't': 14, 'op': 'withdraw', 'acct': 'a', 'amount': 80},  # -160 < -100
                  {'id': 11, 't': 15, 'op': 'unfreeze', 'acct': 'b'},
                  {'id': 12, 't': 16, 'op': 'reverse', 'target': 6},                 # 500 back to a, sweep stays
                  {'id': 13, 't': 17, 'op': 'link', 'acct': 'a', 'backup': 'a'}]
        self.assertEqual(ledger.settle(list(reversed(events)), dict(base, tier=5, sweep_fee=None)),
                         {'balances': {'a': 420, 'b': 550}, 'rejected': [10, 13], 'fees': 0})
        self.assertEqual(ledger.settle(events, dict(base, tier=4, sweep_max=None, sweep_fee=None))['rejected'],
                         [5, 6, 10, 12, 13])  # level 4 has no links or sweeps
        events = [{'id': 1, 't': 0, 'op': 'open', 'acct': 'a', 'overdraft': 0},
                  {'id': 2, 't': 0, 'op': 'open', 'acct': 'b'}, {'id': 3, 't': 0, 'op': 'open', 'acct': 'c'},
                  {'id': 4, 't': 1, 'op': 'deposit', 'acct': 'b', 'amount': 500},
                  {'id': 5, 't': 2, 'op': 'link', 'acct': 'a', 'backup': 'b'},
                  {'id': 6, 't': 10, 'op': 'transfer', 'from': 'a', 'to': 'c', 'amount': 200},  # sweeps 200, fee 20
                  {'id': 7, 't': 11, 'op': 'transfer', 'from': 'a', 'to': 'b', 'amount': 50},   # to the backup
                  {'id': 8, 't': 12, 'op': 'hold', 'acct': 'a', 'amount': 100},                 # sweeps 100, fee 20
                  {'id': 9, 't': 13, 'op': 'withdraw', 'acct': 'a', 'amount': 200},  # partial 140 is not enough
                  {'id': 10, 't': 14, 'op': 'capture', 'target': 8}]
        self.assertEqual(ledger.settle(events, dict(base, tier=6, sweep_fee=20)),
                         {'balances': {'a': 0, 'b': 160, 'c': 200}, 'rejected': [7, 9], 'fees': 40})

    def test_ledger_money_is_conserved(self):
        rng = random.Random(4)
        for level in (4, 5, 6):  # without interest, money only enters by deposits and leaves by withdrawals,
            r = ledger.rules(rng, level)  # captures and fees (sweeps and their fees move it between accounts)
            for _ in range(30):
                events = [e for e in ledger.events(rng, r) if e['op'] != 'interest']
                result = ledger.settle(events, r)
                self.assertEqual(len(result['rejected']), len(set(result['rejected'])))
                rejected, by_id = set(result['rejected']), {e['id']: e for e in events}
                reversed_ids = {e['target'] for e in events if e['op'] == 'reverse' and e['id'] not in rejected}
                flow = sum((e['amount'] if e['op'] == 'deposit' else -e['amount'])
                           for e in events if e['op'] in ('deposit', 'withdraw') and e['id'] not in rejected
                           and e['id'] not in reversed_ids)
                flow -= sum(by_id[e['target']]['amount'] for e in events
                            if e['op'] == 'capture' and e['id'] not in rejected)
                self.assertEqual(sum(result['balances'].values()) + result['fees'], flow)

    def test_ledger_sweep_rules_matter(self):
        for level in (5, 6):  # most event lists depend on the rules the level adds
            rng = random.Random(f'ledger-test/{level}')
            r = ledger.rules(rng, level)
            lists = [ledger.events(rng, r) for _ in range(40)]
            changed = sum(ledger.settle(e, r) != ledger.settle(e, dict(r, tier=level - 1)) for e in lists)
            self.assertGreaterEqual(changed, 2, level)

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
        rules = ledger.rules(random.Random(f'ledger/3/{code["seed"]}'), 6)
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

    def test_code_problems_show_no_example(self):
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

    def test_logic_items_catch_misreadings(self):
        for x in (i for i in self.bank['items'] if i['family'] == 'logic'):
            traps = list(x['logic']['traps'].values())
            self.assertNotIn('same', traps, x['id'])  # every misread clue is false in the hidden arrangement
            self.assertGreaterEqual(traps.count('other'), logic.SILENT[x['tier']], x['id'])
            self.assertEqual(len(x['answer'].split(',')), sum(len(v) for v in x['logic']['values'].values()))

    def test_policy_misreadings_each_change_some_answer(self):
        from datetime import date
        for x in (i for i in self.bank['items'] if i['family'] == 'policy'):
            r, wrongs = x['policy']['rules'], x['policy']['misreadings']
            cases = [{k: date.fromisoformat(v) if k in ('event', 'application', 'registered', 'born') else v
                      for k, v in c.items()} for c in x['policy']['cases']]
            self.assertEqual(','.join(map(str, policy.fees(cases, r))), x['answer'])
            self.assertEqual(len(cases), policy.SIZE[x['tier']])
            for w in wrongs:
                self.assertNotEqual(','.join(map(str, policy.fees(cases, r, {w}))), x['answer'], (x['id'], w))

    def test_incident_root_is_in_the_log(self):
        for tier in sampling_bank.TIERS:
            for seed in range(6):
                x = incident.item(random.Random(f'incident-test/{tier}/{seed}'), tier)
                meta = x['incident']
                service, code = meta['root']
                self.assertIsNotNone(meta['root_line'], meta['scenario'])
                self.assertEqual(x['answer'], f'{service},{code}'.lower())
                self.assertIn(f'- {code}:', x['prompt'])
                self.assertIn(f' {service} ', x['prompt'].split('```')[1])
                if tier >= 2 and meta['scenario'] not in ('cert', 'surge'):  # by the written timestamps the root
                    # evidence comes after the first symptom and after the secondary fault the outage caused
                    self.assertGreater(meta['root_line'], meta['first_symptom_line'], meta['scenario'])
                    self.assertGreater(meta['root_line'], meta['secondary_line'], meta['scenario'])

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
                           'benchmarks/tuning-workloads-v1/sampling-pilot-plan.json').read_text())
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

    def analyse(self, events):
        with tempfile.NamedTemporaryFile('w', suffix='.jsonl', delete=False) as f:
            f.write(rollout_lines(events))
        try:
            return codex_workload.analyse_session(f.name)
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

    def test_ack_reply_kept_when_no_summary_message_precedes_compaction(self):
        result = self.analyse([user('Batch 01/02. New records:'), assistant('ACK 01'),
                               {'type': 'compacted', 'payload': {'message': 'other', 'replacement_history': []}},
                               user('Batch 02/02. New records:'), assistant('ACK 02')])
        self.assertEqual([r['text'] for r in result['replies']], ['ACK 01', 'ACK 02'])

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

    def test_window_rounds_group_conditions_and_reverse_order(self):
        self.assertEqual(codex_workload.next_round(['a', 'b'], 1, ['a', 'b'], True), ['b', 'b', 'a', 'a'])
        self.assertEqual(codex_workload.next_round(['b', 'a'], 2, ['a', 'b'], True), ['a', 'a', 'b', 'b'])
        self.assertEqual(codex_workload.next_round(['b'], 1, ['a', 'b'], True), ['b', 'b'])

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
        bank = {'items': [{'id': f'{f}{t}{k}', 'family': f, 'tier': t} for f in sampling_bank.FAMILIES
                          for t in sampling_bank.TIERS for k in range(sampling_bank.PER_TIER[t - 1])]}
        ids = sampling_bank.grouped(bank, 10)
        items = [next(x for x in bank['items'] if x['id'] == i) for i in ids]
        groups = codex_workload.groups(items, 10)
        self.assertEqual([len(g) for g in groups], [10] * 8)
        for g in groups:  # at least six directions and every tier in each group, the same time limit
            self.assertGreaterEqual(len({x['family'] for x in g}), 6)
            self.assertEqual(sorted(x['tier'] for x in g), [1] * 3 + [2] * 4 + [3] * 3)
            self.assertEqual(codex_workload.group_seconds_limit(g, 30), 600)
        uneven = codex_workload.groups(items[:76], 10)  # sizes differ by at most one, nothing lost or reordered
        self.assertEqual([len(g) for g in uneven], [10, 10, 10, 10, 9, 9, 9, 9])
        self.assertEqual([x for g in uneven for x in g], items[:76])
        dealt = sampling_bank.grouped({'items': bank['items'][:76]}, 10)  # the dealing matches the driver's cuts
        cut = codex_workload.groups(dealt, 10)
        self.assertEqual(sorted(dealt), sorted(x['id'] for x in bank['items'][:76]))
        self.assertTrue(all(len({i[:-2] for i in g}) >= 5 for g in cut))

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
        bank = small_bank()
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
        bank = small_bank()
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
        bank = small_bank()
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
        root = Path(__file__).resolve().parents[1] / 'benchmarks'
        for name in ('window-load-v1/pilot-plan.json', 'tuning-workloads-v1/sampling-pilot-plan.json'):
            plan, data, conditions = codex_workload.load_plan(root / name)
            authorization = plan.get('authorization', {})
            if authorization.get('approved') is True:  # only with a recorded user approval
                self.assertEqual(authorization.get('approved_by'), 'user')
                self.assertTrue(authorization.get('date') and authorization.get('scope'))
            own = sampling_bank.self_check(data) if plan['workload'] == 'sampling' else window_bank.self_check(data)
            self.assertTrue(own['ok'], own)


if __name__ == '__main__':
    unittest.main()
