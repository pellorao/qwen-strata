"""Generated, program-judged question bank for the sampling tuning workload.

Five families (trace, grid, count: one exact answer; strfun, ledger: a function judged by hidden tests), five tiers
each.  Every item is drawn from its own seeded generator with randomized names, mnemonics, rules and parameters, so
the text is new and the answer is computed by a reference implementation here, never written by hand.

    python3 -m tools.tuning.sampling_bank build --seed S --out bank.json         # candidate bank (with answers)
    python3 -m tools.tuning.sampling_bank export --bank bank.json --out DIR      # answer-free workspace
    python3 -m tools.tuning.sampling_bank score --bank bank.json --workspace DIR # instance score
"""
import argparse
from fractions import Fraction
import hashlib
import itertools
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile

FAMILIES = ('trace', 'grid', 'count', 'strfun', 'ledger')
TIERS = (1, 2, 3, 4, 5)
CODE_FAMILIES = {'strfun': 'transform', 'ledger': 'settle'}
CODE_TIMEOUT_SECONDS = 20


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def tokens(rng, count, length=3):
    """Distinct pronounceable made-up words, used as mnemonics and keywords."""
    consonants, vowels, seen = 'BDFGKLMNPRSTVZ', 'AEIOU', set()
    while len(seen) < count:
        seen.add(''.join(rng.choice(consonants if i % 2 == 0 else vowels) for i in range(length)))
    return rng.sample(sorted(seen), count)


# ---------------------------------------------------------------- trace: hand-execute a generated register machine

def trace_item(rng, tier):
    """Redraw until the output is informative (not dominated by repeated or absorbed values)."""
    while True:
        value = trace_attempt(rng, tier)
        output = value['answer'].split(',')
        if len(set(output)) >= max(2, 0.6 * len(output)) and not set(output) <= {'0', '1'}:
            return value


def trace_attempt(rng, tier):
    names = rng.sample('ABDEFGHKMNPRSTVWXYZ', {1: 2, 2: 3, 3: 3, 4: 4, 5: 5}[tier] + (0 if tier < 3 else 2))
    counters = names[-2:] if tier >= 3 else []
    data = [n for n in names if n not in counters]
    modulus = None if tier <= 2 else rng.choice([89, 97, 101, 103, 107, 109])
    swapped_sub = tier >= 2 and rng.random() < 0.5
    mnemonic = dict(zip(['SET', 'ADD', 'SUB', 'MUL', 'OUT', 'DEC', 'LOOP', 'SKIP'], tokens(rng, 8)))

    def operand(readable):
        return rng.choice(readable) if rng.random() < 0.6 else rng.randint(-4 if tier >= 2 else 1, 9)

    def straight(count, readable, mul=True):
        ops = ['ADD', 'SUB'] + (['MUL'] if mul else [])
        return [(rng.choice(ops), rng.choice(data), operand(readable)) for _ in range(count)]

    def with_skip(body, readable):
        if len(body) < 2:
            return body
        at = rng.randrange(len(body) - 1)
        span = rng.randint(1, len(body) - at - 1)
        a, b = rng.sample(readable, 2) if len(readable) > 1 else (readable[0], rng.randint(0, 9))
        return body[:at] + [('SKIP', a, b, span)] + body[at:]

    program = [('SET', r, rng.randint(0, 9)) for r in data]
    if tier <= 2:
        program += straight({1: 4, 2: 8}[tier], data, mul=tier == 2)
        program += [('OUT', r) for r in rng.sample(data, len(data))]
    elif tier == 3:
        c = counters[0]
        program += [('SET', c, rng.randint(4, 6)), ('LABEL', 'L1')] + straight(4, data)
        program += [('OUT', rng.choice(data)), ('DEC', c), ('LOOP', c, 'L1'), ('OUT', rng.choice(data))]
    else:
        outer, inner = counters
        readable = data + ([outer] if tier == 5 else [])
        body = with_skip(straight(3 if tier == 4 else 4, readable), readable)
        program += [('SET', outer, rng.randint(3, 4) if tier == 4 else rng.randint(4, 5)), ('LABEL', 'L1'),
                    ('SET', inner, rng.randint(3, 4) if tier == 4 else rng.randint(3, 5)), ('LABEL', 'L2')]
        program += body + [('DEC', inner), ('LOOP', inner, 'L2'), ('OUT', rng.choice(data))]
        program += straight(1 if tier == 4 else 2, data) + [('DEC', outer), ('LOOP', outer, 'L1')]
        if tier == 5:
            program += [('SET', inner, rng.randint(4, 6)), ('LABEL', 'L3')]
            program += with_skip(straight(3, data + [inner]), data + [inner])
            program += [('DEC', inner), ('LOOP', inner, 'L3')]
        program += [('OUT', r) for r in rng.sample(data, 2)]
    output = run_trace(program, modulus, swapped_sub)

    def render(op):
        if op[0] == 'LABEL':
            return op[1] + ':'
        return '    ' + ' '.join([mnemonic[op[0]]] + [str(x) for x in op[1:]])
    reduce = (f' After every {mnemonic["SET"]}, {mnemonic["ADD"]}, {mnemonic["SUB"]} and {mnemonic["MUL"]} the target '
              f'register is reduced modulo {modulus} into the range 0..{modulus - 1} (for example -3 becomes '
              f'{modulus - 3}).') if modulus else ''
    sub = 'x - r' if swapped_sub else 'r - x'
    table = [f'{mnemonic["SET"]} r x: r = x', f'{mnemonic["ADD"]} r x: r = r + x', f'{mnemonic["SUB"]} r x: r = {sub}',
             f'{mnemonic["MUL"]} r x: r = r * x', f'{mnemonic["OUT"]} r: append the value of r to the output']
    if tier >= 3:
        table += [f'{mnemonic["DEC"]} r: r = r - 1 (never reduced)',
                  f'{mnemonic["LOOP"]} r L: if r is not 0, continue at label L; otherwise go on']
    if tier >= 4:
        table += [f'{mnemonic["SKIP"]} a b n: if a > b, skip the next n instructions (labels are not instructions)']
    prompt = ('A register machine runs the program below. Registers hold integers. In each instruction x is either a '
              'register name or an integer literal; r is a register.' + reduce + '\n\nInstructions:\n'
              + '\n'.join('- ' + t for t in table) + '\n\nProgram:\n```\n' + '\n'.join(map(render, program)) + '\n```\n\n'
              'Question: which values does the program output, in order? '
              'Write them as integers separated by commas, for example `3,-1,7`.')
    return {'kind': 'answer', 'prompt': prompt, 'answer': ','.join(map(str, output))}


def run_trace(program, modulus, swapped_sub, limit=50000):
    labels = {op[1]: i for i, op in enumerate(program) if op[0] == 'LABEL'}
    regs, out, pc, steps = {}, [], 0, 0
    value = lambda x: regs[x] if isinstance(x, str) else x
    while pc < len(program):
        steps += 1
        if steps > limit:
            raise RuntimeError('Trace program does not terminate')
        op = program[pc]
        pc += 1
        if op[0] in ('SET', 'ADD', 'SUB', 'MUL'):
            r, x = op[1], value(op[2])
            result = {'SET': lambda: x, 'ADD': lambda: regs[r] + x, 'MUL': lambda: regs[r] * x,
                      'SUB': lambda: x - regs[r] if swapped_sub else regs[r] - x}[op[0]]()
            regs[r] = result % modulus if modulus else result
        elif op[0] == 'OUT':
            out.append(regs[op[1]])
        elif op[0] == 'DEC':
            regs[op[1]] -= 1
        elif op[0] == 'LOOP' and regs[op[1]] != 0:
            pc = labels[op[2]]
        elif op[0] == 'SKIP' and value(op[1]) > value(op[2]):
            skipped = 0
            while skipped < op[3]:
                skipped += program[pc][0] != 'LABEL'
                pc += 1
    return out


# ---------------------------------------------------------------- grid: logic puzzle with a unique solution

GRID_VALUES = {
    'color': ['amber', 'teal', 'crimson', 'ochre', 'slate', 'ivory', 'jade', 'mauve'],
    'pet': ['ferret', 'ibis', 'gecko', 'lynx', 'otter', 'heron', 'newt', 'marmot'],
    'drink': ['kvass', 'mate', 'lassi', 'cider', 'kefir', 'horchata', 'sbiten', 'ayran'],
    'craft': ['cooper', 'glazier', 'tanner', 'chandler', 'farrier', 'scribe', 'fletcher', 'weaver'],
    'name': ['Ilsa', 'Orrin', 'Pavla', 'Tobin', 'Wenna', 'Caius', 'Mireya', 'Dagny'],
}


def grid_item(rng, tier):
    houses, count = {1: (3, 2), 2: (4, 2), 3: (4, 3), 4: (5, 3), 5: (5, 4)}[tier]
    attributes = rng.sample(sorted(GRID_VALUES), count)
    solution = {a: rng.sample(GRID_VALUES[a], houses) for a in attributes}
    kinds = ['at', 'not_at', 'same', 'not_same', 'left', 'before', 'next']
    if tier >= 4:
        kinds = kinds[1:]
    if tier == 5:
        kinds = ['not_at', 'same', 'not_same', 'left', 'before', 'next', 'next', 'before']

    def where(assign, a, v):
        return assign[a].index(v)

    def holds(clue, assign):
        kind, (a1, v1), second = clue[0], clue[1], clue[2]
        p1 = where(assign, a1, v1)
        if kind in ('at', 'not_at'):
            return (p1 == second) == (kind == 'at')
        p2 = where(assign, *second)
        return {'same': p1 == p2, 'not_same': p1 != p2, 'left': p1 + 1 == p2,
                'before': p1 < p2, 'next': abs(p1 - p2) == 1}[kind]

    def involved(clue):
        return {clue[1][0]} | ({clue[2][0]} if isinstance(clue[2], tuple) else set())

    def solutions(clues, stop=2):
        found = []

        def search(i, assign):
            if len(found) >= stop:
                return
            if i == len(attributes):
                found.append({a: list(p) for a, p in assign.items()})
                return
            a = attributes[i]
            ready = [c for c in clues if a in involved(c) and involved(c) <= set(attributes[:i + 1])]
            for perm in itertools.permutations(GRID_VALUES_SELECTED[a]):
                assign[a] = perm
                if all(holds(c, assign) for c in ready):
                    search(i + 1, assign)
            del assign[a]
        search(0, {})
        return found

    GRID_VALUES_SELECTED = {a: sorted(solution[a]) for a in attributes}

    def random_clue():
        kind = rng.choice(kinds)
        a1 = rng.choice(attributes)
        v1 = rng.choice(solution[a1])
        p1 = solution[a1].index(v1)
        if kind in ('at', 'not_at'):
            positions = [p1] if kind == 'at' else [p for p in range(houses) if p != p1]
            return (kind, (a1, v1), rng.choice(positions))
        a2 = rng.choice([a for a in attributes if a != a1] if kind in ('same', 'not_same') else attributes)
        options = [v for v in solution[a2] if (a2, v) != (a1, v1)]
        options = [v for v in options if holds((kind, (a1, v1), (a2, v)), solution)]
        return (kind, (a1, v1), (a2, rng.choice(options))) if options else None

    clues = []
    while len(solutions(clues)) != 1:
        clue = random_clue()
        if clue and clue not in clues:
            clues.append(clue)
        if len(clues) > 400:
            raise RuntimeError('Grid generator did not converge')
    if tier >= 3:
        rng.shuffle(clues)
        for clue in list(clues):
            trial = [c for c in clues if c != clue]
            if len(solutions(trial)) == 1:
                clues = trial
    rng.shuffle(clues)
    asked = rng.choice(attributes)

    def text(clue):
        kind, (a1, v1), second = clue
        first = f'`{a1}={v1}`'
        if kind == 'at':
            return f'{first} is in house {second + 1}.'
        if kind == 'not_at':
            return f'{first} is not in house {second + 1}.'
        other = f'`{second[0]}={second[1]}`'
        return {'same': f'{first} and {other} are in the same house.',
                'not_same': f'{first} and {other} are in different houses.',
                'left': f'{first} is in the house immediately to the left of {other}.',
                'before': f'{first} is somewhere to the left of {other} (not necessarily adjacent).',
                'next': f'{first} and {other} are in neighbouring houses.'}[kind]
    listing = '\n'.join(f'- {a}: {", ".join(GRID_VALUES_SELECTED[a])}' for a in attributes)
    prompt = (f'{houses} houses stand in a row, numbered 1 to {houses} from left to right. Each house has exactly one '
              f'value of each attribute below, and each value belongs to exactly one house.\n\n{listing}\n\nClues:\n'
              + '\n'.join(f'{i}. {text(c)}' for i, c in enumerate(clues, 1))
              + f'\n\nThe clues have exactly one solution. Question: what is the {asked} of each house, from house 1 '
              f'to house {houses}? Write the values separated by commas, for example `{",".join(GRID_VALUES_SELECTED[asked])}`.')
    return {'kind': 'answer', 'prompt': prompt, 'answer': ','.join(solution[asked])}


# ---------------------------------------------------------------- count: short counting problems needing a DP

def count_strings(n, letters, forbidden, tally=None, first_last=None, equal_pairs=None):
    """Strings of length n over letters avoiding the forbidden substrings (length <= 3).

    tally: (letter, 'exact', j) or (letter, 'mod', m, r); first_last: 'same' or 'differ'; equal_pairs: exact count of
    positions i with s[i] == s[i+1]."""
    def ok(tail):
        return not any(tail.endswith(f) for f in forbidden)
    states = {}
    for c in letters:
        if ok(c):
            key = (c, int(tally is not None and c == tally[0]), 0, c)
            states[key] = states.get(key, 0) + 1
    for _ in range(n - 1):
        following = {}
        for (tail, counted, pairs, first), ways in states.items():
            for c in letters:
                window = (tail + c)[-3:]
                if not ok(window):
                    continue
                c_count = counted + int(tally is not None and c == tally[0])
                if tally and tally[1] == 'mod':
                    c_count %= tally[2]
                elif tally and c_count > tally[2]:
                    continue
                c_pairs = pairs + (tail[-1] == c)
                if equal_pairs is not None and c_pairs > equal_pairs:
                    continue
                key = (window[-2:], c_count, c_pairs, first)
                following[key] = following.get(key, 0) + ways
        states = following
    total = 0
    for (tail, counted, pairs, first), ways in states.items():
        if tally and counted != (tally[2] if tally[1] == 'exact' else tally[3]):
            continue
        if first_last and (first == tail[-1]) != (first_last == 'same'):
            continue
        if equal_pairs is not None and pairs != equal_pairs:
            continue
        total += ways
    return total


def count_item(rng, tier):
    while True:
        k = {1: rng.choice([2, 3]), 2: 3, 3: 3, 4: 3, 5: rng.choice([3, 4])}[tier]
        letters = 'abcd'[:k]
        n = {1: rng.randint(4, 5), 2: rng.randint(6, 7), 3: rng.randint(8, 10), 4: rng.randint(11, 14),
             5: rng.randint(18, 30)}[tier]
        shapes = {1: [2], 2: [2, 2], 3: [2], 4: [3, 2], 5: [3, 3]}[tier]
        forbidden = sorted({''.join(rng.choice(letters) for _ in range(size)) for size in shapes})
        tally = first_last = equal_pairs = None
        if tier == 3:
            tally = (rng.choice(letters), 'exact', rng.randint(2, 4))
        if tier >= 4:
            m = rng.choice([3, 4, 5])
            tally = (rng.choice(letters), 'mod', m, rng.randrange(m))
        if tier == 4:
            first_last = rng.choice(['same', 'differ'])
        if tier == 5:
            equal_pairs = rng.randint(2, 6)
        answer = count_strings(n, letters, forbidden, tally, first_last, equal_pairs)
        if answer > 0:
            break
    rules = ['it never contains ' + ' or '.join(f'`{f}`' for f in forbidden) + ' as a contiguous substring']
    if tally and tally[1] == 'exact':
        rules.append(f'the letter `{tally[0]}` appears exactly {tally[2]} times')
    if tally and tally[1] == 'mod':
        rules.append(f'the number of times the letter `{tally[0]}` appears leaves remainder {tally[3]} when divided '
                     f'by {tally[2]}')
    if first_last:
        rules.append('its first and last letters are ' + ('the same' if first_last == 'same' else 'different'))
    if equal_pairs is not None:
        rules.append(f'exactly {equal_pairs} positions i have s[i] equal to s[i+1]')
    prompt = (f'Consider strings of length {n} over the letters {", ".join(letters)}. Count the strings for which '
              + '; '.join(rules) + '.\n\nQuestion: how many such strings are there? Write one integer.')
    return {'kind': 'answer', 'prompt': prompt, 'answer': str(answer)}


# ---------------------------------------------------------------- strfun: implement a string pipeline (hidden tests)

VOWELS = 'aeiou'


def strfun_ops(rng):
    k, m, a, b, n = rng.randint(1, 5), rng.randint(1, 3), rng.choice([3, 7, 9]), rng.randint(1, 9), rng.randint(2, 4)

    def caesar(s):
        return ''.join(chr((ord(c) - base + k) % 26 + base) if c.isascii() and c.isalpha() else c
                       for c in s for base in [ord('a') if c.islower() else ord('A')])

    def rotate(s):
        return s[k % len(s):] + s[:k % len(s)] if s else s

    def reverse_runs(s):
        return ''.join(part[::-1] if not part.isspace() else part
                       for part in (''.join(g) for _, g in itertools.groupby(s, key=str.isspace)))

    def swap_pairs(s):
        return ''.join(s[i + 1] + s[i] if i + 1 < len(s) else s[i] for i in range(0, len(s), 2))

    def collapse(s):
        return ''.join(''.join(g)[:m] for _, g in itertools.groupby(s))

    def digits(s):
        return ''.join(str((a * int(c) + b) % 10) if c in '0123456789' else c for c in s)

    def drop(s):
        return ''.join(c for i, c in enumerate(s, 1) if i % n)

    def alternate(s):
        out, seen = [], 0
        for c in s:
            if c.isascii() and c.isalpha():
                out.append(c.upper() if seen % 2 == 0 else c.lower())
                seen += 1
            else:
                out.append(c)
        return ''.join(out)

    def vowels(s):
        return ''.join((VOWELS[(VOWELS.index(c.lower()) + 1) % 5].upper() if c.isupper()
                        else VOWELS[(VOWELS.index(c) + 1) % 5]) if c.lower() in VOWELS else c for c in s)

    def mirror(s):
        return s + s[-m - 1:][::-1] if s else s

    return [
        (caesar, f'Shift every ASCII letter {k} places forward in the alphabet, wrapping z to a and Z to A and keeping '
                 'its case; leave other characters unchanged.'),
        (rotate, f'Rotate the whole string left by {k} characters (by {k} modulo the length; the empty string stays '
                 'empty).'),
        (reverse_runs, 'Reverse the characters inside every maximal run of non-whitespace characters; whitespace '
                       'characters stay exactly where they are.'),
        (swap_pairs, 'Swap the characters at positions 0 and 1, 2 and 3, and so on; a final unpaired character stays.'),
        (collapse, f'Shorten every run of one repeated character that is longer than {m} to exactly {m} copies.'),
        (digits, f'Replace every decimal digit d by the digit ({a} * d + {b}) mod 10.'),
        (drop, f'Delete every {n}-th character, counting positions from 1 (positions {n}, {2 * n}, ...).'),
        (alternate, 'Among ASCII letters only, make the 1st, 3rd, 5th, ... letter (counted over letters only) '
                    'uppercase and the 2nd, 4th, ... letter lowercase; leave other characters unchanged.'),
        (vowels, 'Replace each vowel by the next one in the cycle a, e, i, o, u, a, keeping its case (A becomes E, '
                 'u becomes a); y is not a vowel.'),
        (mirror, f'Append the reverse of the last {m + 1} characters (the reverse of the whole string if it is '
                 'shorter); the empty string stays empty.'),
    ]


def strfun_item(rng, tier):
    chosen = rng.sample(strfun_ops(rng), {1: 1, 2: 2, 3: 3, 4: 4, 5: 6}[tier])

    def apply(s):
        for op, _ in chosen:
            s = op(s)
        return s
    alphabet = 'abcdeiouxyzAEIOUQZ0123456789  !?-.'
    samples = ['', 'a', 'Zz 9', 'aaa   bbbb!!', 'Hello World 2024', 'u U y Y']
    while len(samples) < 34:
        length = rng.randint(1, 24)
        word = ''.join(rng.choice(alphabet) for _ in range(length))
        if rng.random() < 0.3:
            word = word.replace(word[0], word[0] * 3, 1)
        samples.append(word)
    cases = [{'args': [s], 'expected': apply(s)} for s in samples]
    visible, hidden = cases[4:6], cases[:4] + cases[6:]
    steps = '\n'.join(f'{i}. {text}' for i, (_, text) in enumerate(chosen, 1))
    prompt = ('Implement `transform(s: str) -> str` that applies these steps in order, each to the result of the '
              f'previous one:\n\n{steps}\n\nExamples:\n'
              + '\n'.join(f'- transform({json.dumps(c["args"][0])}) == {json.dumps(c["expected"])}' for c in visible)
              + '\n\nUse only the Python 3 standard library. Hidden tests call transform on other strings.')
    return {'kind': 'code', 'entry': 'transform', 'prompt': prompt, 'tests': hidden,
            'stub': 'def transform(s: str) -> str:\n    raise NotImplementedError\n'}


# ---------------------------------------------------------------- ledger: implement account settlement (hidden tests)

def ledger_rules(rng, tier):
    words = dict(zip(['deposit', 'withdraw', 'transfer', 'close', 'hold', 'release', 'capture'], tokens(rng, 7, 4)))
    return {'tier': tier, 'words': words, 'fee': rng.randint(1, 5) if tier >= 2 else 0,
            'overdraft': rng.choice([0, 20, 50]) if tier >= 2 else 0, 'xfee': rng.randint(1, 3) if tier >= 3 else 0,
            'rate': rng.choice([5, 10, 25]) if tier >= 4 else 0, 'penalty': rng.randint(2, 6) if tier >= 4 else 0,
            'daily': rng.choice([60, 80, 120]) if tier >= 4 else 0}


def settle(events, r):
    w, tier = r['words'], r['tier']
    balance, rejected, holds, today = {}, 0, {}, {}

    def touch(*accounts):
        for a in accounts:
            balance.setdefault(a, 0)

    def available(a):
        return balance[a] + r['overdraft'] - sum(v for h, (acc, v) in holds.items() if acc == a)
    for line in events:
        parts = line.split()
        op = parts[0]
        ok = True
        if op == w['deposit']:
            touch(parts[1])
            balance[parts[1]] += int(parts[2])
        elif op == w['withdraw']:
            a, amount = parts[1], int(parts[2])
            touch(a)
            ok = amount + r['fee'] <= available(a) and (not r['daily'] or today.get(a, 0) + amount <= r['daily'])
            if ok:
                balance[a] -= amount + r['fee']
                today[a] = today.get(a, 0) + amount
        elif op == w['transfer'] and tier >= 3:
            a, b, amount = parts[1], parts[2], int(parts[3])
            touch(a, b)
            ok = a != b and amount + r['xfee'] <= available(a)
            if ok:
                balance[a] -= amount + r['xfee']
                balance[b] += amount
        elif op == w['close'] and tier >= 4:
            for a in balance:
                if balance[a] > 0:
                    balance[a] += balance[a] * r['rate'] // 1000
                elif balance[a] < 0:
                    balance[a] -= r['penalty']
            today = {}
        elif op == w['hold'] and tier >= 5:
            a, amount, ident = parts[1], int(parts[2]), parts[3]
            touch(a)
            ok = ident not in holds and amount <= available(a)
            if ok:
                holds[ident] = (a, amount)
        elif op in (w['release'], w['capture']) and tier >= 5:
            ok = parts[1] in holds
            if ok:
                a, amount = holds.pop(parts[1])
                if op == w['capture']:
                    balance[a] -= amount
        else:
            raise ValueError('Event outside this tier: ' + line)
        rejected += not ok
    return {**balance, '_rejected': rejected}


def ledger_events(rng, r, shortest=6, longest=30):
    w, tier, accounts = r['words'], r['tier'], rng.sample(['ana', 'bo', 'cy', 'dee', 'eli', 'fay'], 3)
    events, live = [], []
    for _ in range(rng.randint(shortest, longest)):
        roll, a = rng.random(), rng.choice(accounts)
        if tier >= 5 and live and roll < 0.12:
            events.append(f'{rng.choice([w["release"], w["capture"]])} {rng.choice(live + ["h99"])}')
        elif tier >= 5 and roll < 0.25:
            ident = rng.choice(live) if live and rng.random() < 0.2 else f'h{len(events)}'
            live.append(ident)
            events.append(f'{w["hold"]} {a} {rng.randint(5, 90)} {ident}')
        elif tier >= 4 and roll < 0.33:
            events.append(w['close'])
        elif tier >= 3 and roll < 0.5:
            events.append(f'{w["transfer"]} {a} {rng.choice(accounts)} {rng.randint(1, 80)}')
        elif roll < 0.72:
            events.append(f'{w["deposit"]} {a} {rng.randint(1, 120)}')
        else:
            events.append(f'{w["withdraw"]} {a} {rng.randint(1, 120)}')
    return events


def ledger_item(rng, tier):
    r = ledger_rules(rng, tier)
    w = r['words']
    cases = [{'args': [e], 'expected': settle(e, r)} for e in (ledger_events(rng, r) for _ in range(26))]
    # short visible examples keep the problem text short; hidden tests use the full-length lists
    examples = [{'args': [e], 'expected': settle(e, r)} for e in (ledger_events(rng, r, 6, 9) for _ in range(2))]
    rules = [f'`{w["deposit"]} <account> <amount>`: add amount to the account.',
             f'`{w["withdraw"]} <account> <amount>`: subtract amount'
             + (f' plus a fee of {r["fee"]}' if r['fee'] else '') + '.']
    if tier >= 3:
        rules.append(f'`{w["transfer"]} <from> <to> <amount>`: move amount from one account to another; the sender '
                     f'also pays a fee of {r["xfee"]}. A transfer to the same account is rejected.')
    if tier >= 4:
        rules.append(f'`{w["close"]}`: end of day. Every account with a positive balance gains floor(balance * '
                     f'{r["rate"]} / 1000); every account with a negative balance loses {r["penalty"]}. Daily '
                     'withdrawal totals start again from zero.')
    if tier >= 5:
        rules.append(f'`{w["hold"]} <account> <amount> <id>`: reserve amount on the account under hold id. It does '
                     'not change the balance. Rejected if the id is already an active hold.')
        rules.append(f'`{w["release"]} <id>`: remove the active hold. `{w["capture"]} <id>`: remove the active hold '
                     'and subtract its amount from the balance (no fee, no limit). Both are rejected if the id is not '
                     'an active hold.')
    limits = [f'Available funds = balance + {r["overdraft"]} (overdraft allowance)'
              + (' - the sum of the active holds on that account' if tier >= 5 else '') + '.',
              f'A {w["withdraw"]}' + (f' or {w["transfer"]}' if tier >= 3 else '')
              + (f' or {w["hold"]}' if tier >= 5 else '') + ' is rejected when the amount plus its fee (holds have no '
              'fee) exceeds the available funds.']
    if tier >= 4:
        limits.append(f'A {w["withdraw"]} is also rejected when the account\'s successful withdrawal amounts (fees not '
                      f'counted) since the last {w["close"]} would exceed {r["daily"]}.')
    limits.append('A rejected event changes nothing.')
    visible = examples
    prompt = ('Implement `settle(events: list[str]) -> dict` for this ledger. Every account starts at 0 and exists from '
              'the first event that names it (even a rejected one). Amounts are integers.\n\nEvents:\n'
              + '\n'.join('- ' + x for x in rules) + '\n\nLimits:\n' + '\n'.join('- ' + x for x in limits)
              + '\n\nReturn a dict mapping every account name to its final balance, plus the key "_rejected" with the '
              'number of rejected events.\n\nExamples:\n'
              + '\n'.join(f'- settle({json.dumps(c["args"][0])}) == {json.dumps(c["expected"])}' for c in visible)
              + '\n\nUse only the Python 3 standard library. Hidden tests use other event lists.')
    return {'kind': 'code', 'entry': 'settle', 'prompt': prompt, 'tests': cases,
            'stub': 'def settle(events: list[str]) -> dict:\n    raise NotImplementedError\n'}


GENERATORS = {'trace': trace_item, 'grid': grid_item, 'count': count_item, 'strfun': strfun_item, 'ledger': ledger_item}


def item(family, tier, seed):
    rng = random.Random(f'{family}/{tier}/{seed}')
    value = GENERATORS[family](rng, tier)
    return {'id': f'{family}-t{tier}-s{seed}', 'family': family, 'tier': tier, 'seed': seed, **value}


def build(seed, per_cell):
    """Candidate bank: `per_cell` items for every family and tier, seeds seed*1000 + k."""
    items = [item(f, t, seed * 1000 + k) for t in TIERS for f in FAMILIES for k in range(per_cell)]
    items = [dict(x, number=f'C{n:03d}') for n, x in enumerate(items, 1)]
    return {'schema': 'sampling-bank-v1', 'generator_sha256': sha(Path(__file__).read_bytes()), 'seed': seed,
            'per_cell': per_cell, 'items': items}


def select(bank, ids):
    """Frozen set: the given items in the given order, numbered P01.. ."""
    by_id = {i['id']: i for i in bank['items']}
    items = [dict(by_id[x], number=f'P{n:02d}') for n, x in enumerate(ids, 1)]
    return {**bank, 'schema': 'sampling-set-v1', 'items': items}


def interleaved(bank, seed):
    """Set order in which every run of five consecutive items holds one item of each tier (chunks stay balanced)."""
    rng = random.Random(f'order/{seed}')
    tiers = {t: [x['id'] for x in bank['items'] if x['tier'] == t] for t in TIERS}
    for ids in tiers.values():
        rng.shuffle(ids)
    if len({len(v) for v in tiers.values()}) != 1:
        raise ValueError('Every tier needs the same number of items')
    return [tiers[t][k] for k in range(len(tiers[TIERS[0]])) for t in TIERS]


# ---------------------------------------------------------------- workspace and scoring

WORKSPACE_README = '''# Problem set

Each problem is in `problems/<P>.md`. Solve every problem.

- Answer problems (they end with a "Question:"): write only the final answer to `answers/<P>.txt`, one line,
  in the format the problem asks for.
- Code problems (they start with "Implement"): write the requested function in `solutions/<P>.py`
  (a stub is there). Only the Python 3 standard library is available.

You may use the shell and write scratch files anywhere inside this directory. Nothing outside this directory is
needed. Answers are checked automatically after you finish; there is no partial credit inside a problem.
'''


def export(bank, folder, numbers=None):
    """Answer-free workspace for the selected numbers (all by default)."""
    folder = Path(folder)
    for sub in ('problems', 'answers', 'solutions'):
        (folder / sub).mkdir(parents=True, exist_ok=True)
    (folder / 'README.md').write_text(WORKSPACE_README)
    for x in bank['items']:
        if numbers and x['number'] not in numbers:
            continue
        (folder / 'problems' / (x['number'] + '.md')).write_text(f'# {x["number"]}\n\n{x["prompt"]}\n')
        if x['kind'] == 'code':
            (folder / 'solutions' / (x['number'] + '.py')).write_text(x['stub'])
    return folder


def normalize(text):
    return ','.join(part.strip().strip('`').strip().lower() for part in text.strip().strip('`').split(','))


RUNNER = '''import importlib.util, json, sys
spec = importlib.util.spec_from_file_location('solution', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
entry = getattr(module, sys.argv[2])
passed = 0
for case in json.load(open(sys.argv[3])):
    try:
        passed += entry(*case['args']) == case['expected']
    except Exception:
        pass
print(json.dumps({'passed': passed}))
'''


def run_tests(source, entry, tests):
    """Hidden tests in a separate isolated interpreter with a time limit; any failure to run scores zero."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / 'runner.py').write_text(RUNNER)
        (tmp / 'tests.json').write_text(json.dumps(tests))
        (tmp / 'solution.py').write_bytes(source)
        try:
            reply = subprocess.run([sys.executable, '-I', 'runner.py', 'solution.py', entry, 'tests.json'],
                                   cwd=tmp, capture_output=True, text=True, timeout=CODE_TIMEOUT_SECONDS)
            passed = json.loads(reply.stdout.strip().splitlines()[-1])['passed']
        except (subprocess.TimeoutExpired, ValueError, IndexError, KeyError):
            passed = 0
    return passed


def score(bank, workspace):
    """Per item: correct is all-or-nothing; the instance score is the share of correct items."""
    workspace, rows = Path(workspace), []
    for x in bank['items']:
        if x['kind'] == 'answer':
            path = workspace / 'answers' / (x['number'] + '.txt')
            given = path.read_text(errors='replace') if path.is_file() else None
            correct = given is not None and normalize(given) == normalize(x['answer'])
            rows.append({'number': x['number'], 'id': x['id'], 'tier': x['tier'], 'family': x['family'],
                         'answered': given is not None, 'correct': correct})
        else:
            path = workspace / 'solutions' / (x['number'] + '.py')
            source = path.read_bytes() if path.is_file() else b''
            passed = run_tests(source, x['entry'], x['tests']) if source and source != x['stub'].encode() else 0
            rows.append({'number': x['number'], 'id': x['id'], 'tier': x['tier'], 'family': x['family'],
                         'answered': bool(source) and source != x['stub'].encode(), 'correct': passed == len(x['tests']),
                         'tests_passed': passed, 'tests_total': len(x['tests'])})
    by_tier = {t: [r['correct'] for r in rows if r['tier'] == t] for t in TIERS}
    return {'score': sum(r['correct'] for r in rows) / len(rows), 'correct': sum(r['correct'] for r in rows),
            'items': len(rows), 'by_tier': {t: sum(v) / len(v) for t, v in by_tier.items() if v}, 'rows': rows}


def self_check(bank):
    """No-model precheck: reference answers parse, hidden tests are self-consistent, workspaces hold no answers."""
    problems = []
    for x in bank['items']:
        if x['kind'] == 'code':
            if not x['tests'] or any('expected' not in t for t in x['tests']):
                problems.append(x['id'] + ': missing hidden tests')
        elif not x['answer'] or normalize(x['answer']) != x['answer'].lower():
            problems.append(x['id'] + ': answer not in canonical form')
    with tempfile.TemporaryDirectory() as tmp:
        export(bank, tmp)
        text = '\n'.join(p.read_text() for p in Path(tmp).rglob('*') if p.is_file())
        for x in bank['items']:
            if x['kind'] == 'code' and any(json.dumps(t['expected']) in text for t in x['tests']
                                           if len(json.dumps(t['expected'])) > 12):
                problems.append(x['id'] + ': a hidden expected value appears in the workspace')
        blank = score(bank, tmp)
        if blank['correct']:
            problems.append('an empty workspace scored above zero')
    return {'ok': not problems, 'problems': problems, 'items': len(bank['items'])}


# ---------------------------------------------------------------- Opus calibration (run by Main through subagents)

CALIBRATION_PROMPT = """You are solving a timed problem set. Work only inside {workspace}: read README.md there and
follow it. Do not read, list or search any other directory, and do not use the network. Solve every problem as well
as you can within about {minutes} minutes, writing each answer or solution file as soon as it is ready.
When you are done, reply with the single word DONE."""


def calibration_prepare(bank, out, runs, minutes):
    """One fresh answer-free workspace per independent Opus run, plus the exact prompt each run receives."""
    out = Path(out)
    rows = []
    for k in range(1, runs + 1):
        workspace = export(bank, out / f'run-{k}' / 'workspace').resolve()
        prompt = CALIBRATION_PROMPT.format(workspace=workspace, minutes=minutes)
        (out / f'run-{k}' / 'prompt.txt').write_text(prompt)
        rows.append({'run': k, 'workspace': str(workspace), 'prompt_sha256': sha(prompt.encode())})
    manifest = {'bank_sha256': sha(json.dumps(bank, sort_keys=True).encode()), 'runs': rows,
                'timing': 'Main writes run-<k>/timing.json as {"seconds": <wall seconds of the whole set>}'}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=1) + '\n')
    return manifest


def calibration_score(bank, out):
    """Per item: Opus passes out of the runs; per run: score and time.  Items with zero passes must be replaced."""
    out = Path(out)
    manifest = json.loads((out / 'manifest.json').read_text())
    runs, passes = [], {x['id']: 0 for x in bank['items']}
    for row in manifest['runs']:
        result = score(bank, row['workspace'])
        timing = out / f'run-{row["run"]}' / 'timing.json'
        runs.append({'run': row['run'], 'score': result['score'], 'by_tier': result['by_tier'],
                     'seconds': json.loads(timing.read_text())['seconds'] if timing.exists() else None})
        for r in result['rows']:
            passes[r['id']] += r['correct']
    n = len(runs)
    items = [{'id': x['id'], 'number': x['number'], 'tier': x['tier'], 'family': x['family'], 'passes': passes[x['id']],
              'runs': n} for x in bank['items']]
    return {'runs': runs, 'opus_mean_score': sum(r['score'] for r in runs) / n if n else None,
            'opus_full_marks_runs': sum(r['score'] == 1 for r in runs),
            'replace': [i['id'] for i in items if i['passes'] == 0],
            'pass_rate_by_tier': {t: sum(i['passes'] for i in items if i['tier'] == t)
                                  / (n * sum(i['tier'] == t for i in items)) for t in TIERS if n},
            'items': items}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    b = sub.add_parser('build')
    b.add_argument('--seed', type=int, required=True)
    b.add_argument('--per-cell', type=int, default=2)
    b.add_argument('--out', type=Path, required=True)
    s = sub.add_parser('select')
    s.add_argument('--bank', type=Path, required=True)
    s.add_argument('--ids', type=Path, help='JSON list of item ids in set order')
    s.add_argument('--interleave-seed', type=int, help='all items, tiers interleaved (instead of --ids)')
    s.add_argument('--out', type=Path, required=True)
    e = sub.add_parser('export')
    e.add_argument('--bank', type=Path, required=True)
    e.add_argument('--out', type=Path, required=True)
    c = sub.add_parser('score')
    c.add_argument('--bank', type=Path, required=True)
    c.add_argument('--workspace', type=Path, required=True)
    k = sub.add_parser('check')
    k.add_argument('--bank', type=Path, required=True)
    cp = sub.add_parser('calibrate-prepare')
    cp.add_argument('--bank', type=Path, required=True)
    cp.add_argument('--out', type=Path, required=True)
    cp.add_argument('--runs', type=int, default=5)
    cp.add_argument('--minutes', type=int, default=5)
    cs = sub.add_parser('calibrate-score')
    cs.add_argument('--bank', type=Path, required=True)
    cs.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'calibrate-prepare':
        print(json.dumps(calibration_prepare(json.loads(args.bank.read_text()), args.out, args.runs, args.minutes)))
        return
    if args.command == 'calibrate-score':
        result = calibration_score(json.loads(args.bank.read_text()), args.out)
        (args.out / 'calibration.json').write_text(json.dumps(result, indent=1) + '\n')
        print(json.dumps({k: v for k, v in result.items() if k != 'items'}))
        return
    if args.command == 'build':
        args.out.write_text(json.dumps(build(args.seed, args.per_cell), ensure_ascii=False, indent=1) + '\n')
    elif args.command == 'select':
        bank = json.loads(args.bank.read_text())
        ids = json.loads(args.ids.read_text()) if args.ids else interleaved(bank, args.interleave_seed)
        args.out.write_text(json.dumps(select(bank, ids), ensure_ascii=False, indent=1) + '\n')
    elif args.command == 'export':
        export(json.loads(args.bank.read_text()), args.out)
    elif args.command == 'score':
        result = score(json.loads(args.bank.read_text()), args.workspace)
        print(json.dumps({k: v for k, v in result.items() if k != 'rows'}))
    else:
        print(json.dumps(self_check(json.loads(args.bank.read_text()))))


if __name__ == '__main__':
    main()
