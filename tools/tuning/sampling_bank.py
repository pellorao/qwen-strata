"""Generated, program-judged question bank for the sampling tuning workload.

Five families (trace, grid, count: one exact answer; strfun, ledger: a function judged by hidden tests), five tiers
each.  Every item is drawn from its own seeded generator with randomized names, mnemonics, rules and parameters, so
the text is new and the answer is computed by a reference implementation here, never written by hand.

The solver may use a shell, so difficulty cannot come from hand computation (calibration r1: Opus solved every item of
the first version by writing interpreters and brute force).  Higher tiers instead need an idea that brute force does
not replace (cycle detection over 10^12 loop iterations, Burnside counting of necklaces), carry easy-to-misread
clauses (counter registers exempt from reduction, gap and exclusive-or clues, cyclic forbidden patterns), or give no
worked examples to check an implementation against (code tiers 4-5, tier 5 asks for the inverse of an encoder).

    python3 -m tools.tuning.sampling_bank build --seed S --out bank.json         # candidate bank (with answers)
    python3 -m tools.tuning.sampling_bank export --bank bank.json --out DIR      # answer-free workspace
    python3 -m tools.tuning.sampling_bank score --bank bank.json --workspace DIR # instance score
"""
import argparse
from fractions import Fraction
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import tempfile

FAMILIES = ('trace', 'grid', 'count', 'strfun', 'ledger')
TIERS = (1, 2, 3, 4, 5)
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
    if tier >= 4:
        return long_loop_attempt(rng, tier)
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


def long_loop_attempt(rng, tier):
    """One counted loop run N times (thousands at tier 4, ~10^12 at tier 5); the body reads the counter's exact value,
    data registers are reduced modulo p, the counter never is.  Tier 5 is only feasible by noticing the state
    (data registers, counter mod p) repeats."""
    names = rng.sample('ABDEFGHKMNPRSTVWXYZ', 4 if tier == 4 else 5)
    counter, data = names[0], names[1:]
    modulus = rng.choice([89, 97, 101, 103, 107, 109])
    swapped_sub = rng.random() < 0.5
    mnemonic = dict(zip(['SET', 'ADD', 'SUB', 'MUL', 'OUT', 'DEC', 'LOOP', 'SKIP'], tokens(rng, 8)))
    count = rng.randint(2000, 9000) if tier == 4 else rng.randint(10 ** 11, 10 ** 13)
    readable = data + [counter]
    body = []
    for _ in range(5 if tier == 4 else 6):
        op = rng.choice(['ADD', 'SUB', 'MUL', 'ADD'])
        x = rng.choice(readable) if rng.random() < 0.7 else rng.randint(-4, 9)
        body.append((op, rng.choice(data), x))
    at = rng.randrange(len(body) - 1)
    a, b = rng.sample(data, 2)
    body.insert(at, ('SKIP', a, b, rng.randint(1, min(2, len(body) - at - 1))))
    start = {r: rng.randint(0, 9) for r in data}
    program = [('SET', r, v) for r, v in start.items()] + [('SET', counter, count), ('LABEL', 'L1')] + body
    program += [('DEC', counter), ('LOOP', counter, 'L1')] + [('OUT', r) for r in rng.sample(data, len(data))]
    output = run_counted_loop(start, body, counter, count, modulus, swapped_sub, [op[1] for op in program[-len(data):]])

    def render(op):
        if op[0] == 'LABEL':
            return op[1] + ':'
        return '    ' + ' '.join([mnemonic[op[0]]] + [str(x) for x in op[1:]])
    sub = 'x - r' if swapped_sub else 'r - x'
    table = [f'{mnemonic["SET"]} r x: r = x', f'{mnemonic["ADD"]} r x: r = r + x', f'{mnemonic["SUB"]} r x: r = {sub}',
             f'{mnemonic["MUL"]} r x: r = r * x', f'{mnemonic["OUT"]} r: append the value of r to the output',
             f'{mnemonic["DEC"]} r: r = r - 1',
             f'{mnemonic["LOOP"]} r L: if r is not 0, continue at label L; otherwise go on',
             f'{mnemonic["SKIP"]} a b n: if a > b, skip the next n instructions (labels are not instructions)']
    prompt = ('A register machine runs the program below. Registers hold integers. In each instruction x is either a '
              f'register name or an integer literal; r is a register. After every {mnemonic["SET"]}, '
              f'{mnemonic["ADD"]}, {mnemonic["SUB"]} and {mnemonic["MUL"]} the target register is reduced modulo '
              f'{modulus} into the range 0..{modulus - 1} (for example -3 becomes {modulus - 3}), except when the '
              f'target is register {counter}: {counter} is never reduced and always holds its exact value, also when '
              'another instruction reads it.\n\nInstructions:\n' + '\n'.join('- ' + t for t in table)
              + '\n\nProgram:\n```\n' + '\n'.join(map(render, program)) + '\n```\n\n'
              'Question: which values does the program output, in order? '
              'Write them as integers separated by commas, for example `3,1,7`.')
    return {'kind': 'answer', 'prompt': prompt, 'answer': ','.join(map(str, output))}


def run_counted_loop(start, body, counter, count, modulus, swapped_sub, outputs):
    """Reference for long_loop_attempt: iterate the body with cycle detection on (registers, counter mod p)."""
    def step(regs, c):
        regs, pc = dict(regs), 0
        value = lambda x: c if x == counter else regs[x] if isinstance(x, str) else x
        while pc < len(body):
            op = body[pc]
            pc += 1
            if op[0] == 'SKIP':
                if value(op[1]) > value(op[2]):
                    pc += op[3]
                continue
            r, x = op[1], value(op[2])
            result = {'ADD': lambda: regs[r] + x, 'MUL': lambda: regs[r] * x,
                      'SUB': lambda: x - regs[r] if swapped_sub else regs[r] - x}[op[0]]()
            regs[r] = result % modulus
        return regs
    regs, c, seen, done = {r: v % modulus for r, v in start.items()}, count, {}, 0
    while done < count:
        key = (tuple(sorted(regs.items())), c % modulus)
        if key in seen:
            period = done - seen[key]
            skip = (count - done) // period * period
            done, c = done + skip, c - skip
            seen = {}
            if done == count:
                break
        seen[key] = done
        regs = step(regs, c)
        c -= 1
        done += 1
    return [regs[r] for r in outputs]


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
        kinds = ['not_at', 'same', 'not_same', 'left', 'before', 'next', 'gap', 'xor', 'xor']

    def where(assign, a, v):
        return assign[a].index(v)

    def holds(clue, assign):
        if clue[0] == 'xor':
            return holds(clue[1], assign) != holds(clue[2], assign)
        kind, (a1, v1), second = clue[0], clue[1], clue[2]
        p1 = where(assign, a1, v1)
        if kind in ('at', 'not_at'):
            return (p1 == second) == (kind == 'at')
        p2 = where(assign, *second)
        if kind == 'gap':
            return abs(p1 - p2) == clue[3] + 1
        return {'same': p1 == p2, 'not_same': p1 != p2, 'left': p1 + 1 == p2,
                'before': p1 < p2, 'next': abs(p1 - p2) == 1}[kind]

    def involved(clue):
        if clue[0] == 'xor':
            return involved(clue[1]) | involved(clue[2])
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

    def random_clue(kind=None, truth=True):
        """A clue that is true of the solution (or false, for one half of an exclusive-or clue)."""
        kind = kind or rng.choice(kinds)
        if kind == 'xor':
            simple = [k for k in kinds if k not in ('xor', 'gap')]
            parts = [random_clue(rng.choice(simple)), random_clue(rng.choice(simple), truth=False)]
            if None in parts or parts[0][1:] == parts[1][1:]:
                return None
            rng.shuffle(parts)
            return ('xor', *parts)
        a1 = rng.choice(attributes)
        v1 = rng.choice(solution[a1])
        p1 = solution[a1].index(v1)
        if kind in ('at', 'not_at'):
            positions = [p for p in range(houses) if ((p == p1) == (kind == 'at')) == truth]
            return (kind, (a1, v1), rng.choice(positions))
        a2 = rng.choice([a for a in attributes if a != a1] if kind in ('same', 'not_same') else attributes)
        extra = (rng.randint(1, houses - 2),) if kind == 'gap' else ()
        options = [v for v in solution[a2] if (a2, v) != (a1, v1)]
        options = [v for v in options if holds((kind, (a1, v1), (a2, v), *extra), solution) == truth]
        return (kind, (a1, v1), (a2, rng.choice(options)), *extra) if options else None

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
        if clue[0] == 'xor':
            one, two = (text(c).rstrip('.') for c in clue[1:])
            return f'Exactly one of these two statements is true: ({one}) / ({two}).'
        kind, (a1, v1), second = clue[:3]
        first = f'`{a1}={v1}`'
        if kind == 'at':
            return f'{first} is in house {second + 1}.'
        if kind == 'not_at':
            return f'{first} is not in house {second + 1}.'
        other = f'`{second[0]}={second[1]}`'
        if kind == 'gap':
            return f'Exactly {clue[3]} house{"s" if clue[3] > 1 else ""} stand{"" if clue[3] > 1 else "s"} between {first} and {other}.'
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


def cyclic_ok(word, forbidden):
    """No forbidden pattern occurs in the infinite periodic repetition of `word` (so also across the wrap)."""
    longest = max(map(len, forbidden))
    text = word * (longest // len(word) + 2)
    return not any(f in text[:len(word) + longest - 1] for f in forbidden)


def necklaces(n, letters, forbidden, a_count=None):
    """Necklaces (strings up to rotation) of length n avoiding the forbidden patterns cyclically, optionally with
    exactly a_count copies of letters[0].  Burnside: (1/n) * sum over d | n of phi(n/d) * W(d), where W(d) counts
    periodic words of period d; W(d) by brute force for small d, else by closed walks over the last two letters."""
    first = letters[0]

    def words(d):
        if a_count is not None and (a_count * d) % n:
            return 0
        need = None if a_count is None else a_count * d // n
        if d <= 8:
            return sum(cyclic_ok(''.join(w), forbidden) and (need is None or w.count(first) == need)
                       for w in itertools.product(letters, repeat=d))
        if max(map(len, forbidden)) > 3:
            raise ValueError('Closed walks assume patterns of length at most 3')
        states = [''.join(p) for p in itertools.product(letters, repeat=2)]
        total = 0
        for s0 in states:
            # walk d letters starting after state s0; the walk must end in state s0
            ways = {(s0, 0): 1}
            for _ in range(d):
                following = {}
                for (state, counted), w in ways.items():
                    for c in letters:
                        window = state + c
                        if any(window.endswith(f) for f in forbidden):
                            continue
                        key = (window[1:], counted + (c == first))
                        if need is not None and key[1] > need:
                            continue
                        following[key] = following.get(key, 0) + w
                ways = following
            total += sum(w for (state, counted), w in ways.items()
                         if state == s0 and (need is None or counted == need))
        return total

    def phi(m):
        return sum(1 for k in range(1, m + 1) if math.gcd(k, m) == 1)
    total = sum(phi(n // d) * words(d) for d in range(1, n + 1) if n % d == 0)
    if total % n:
        raise ArithmeticError('Burnside sum not divisible by n')
    return total // n


def count_item(rng, tier):
    """Tiers 1-2 brute-forceable strings; tier 3 long strings (needs a DP); tier 4 necklaces small enough to
    enumerate but with rotation and wrap-around to get right; tier 5 necklaces far too many to enumerate."""
    while True:
        k = {1: rng.choice([2, 3]), 2: 3, 3: 3, 4: rng.choice([2, 3]), 5: 3}[tier]
        letters = 'abcd'[:k]
        shapes = {1: [2], 2: [2, 2], 3: [3, 2], 4: [3, 2], 5: [3, 3, 2]}[tier]
        forbidden = sorted({''.join(rng.choice(letters) for _ in range(size)) for size in shapes})
        if any(f == f[0] * len(f) for f in forbidden) and tier >= 4 and rng.random() < 0.5:
            continue
        tally = first_last = a_count = None
        if tier <= 3:
            n = {1: rng.randint(5, 6), 2: rng.randint(8, 10), 3: rng.randint(40, 70)}[tier]
            if tier >= 2:
                m = rng.choice([3, 4, 5])
                tally = (rng.choice(letters), 'exact', rng.randint(2, 4)) if tier == 2 else \
                    (rng.choice(letters), 'mod', m, rng.randrange(m))
            if tier == 3:
                first_last = rng.choice(['same', 'differ'])
            answer = count_strings(n, letters, forbidden, tally, first_last)
        else:
            n = rng.randint(10, 13) if tier == 4 else rng.choice([30, 32, 36, 40, 42, 45, 48])
            if tier == 5:
                a_count = rng.choice([d for d in range(n // 6, n // 2) if math.gcd(d, n) > 1])
            answer = necklaces(n, letters, forbidden, a_count)
        if answer > 1:
            break
    rules = ['it never contains ' + ' or '.join(f'`{f}`' for f in forbidden) + ' as a contiguous substring']
    if tally and tally[1] == 'exact':
        rules.append(f'the letter `{tally[0]}` appears exactly {tally[2]} times')
    if tally and tally[1] == 'mod':
        rules.append(f'the number of times the letter `{tally[0]}` appears leaves remainder {tally[3]} when divided '
                     f'by {tally[2]}')
    if first_last:
        rules.append('its first and last letters are ' + ('the same' if first_last == 'same' else 'different'))
    if tier <= 3:
        prompt = (f'Consider strings of length {n} over the letters {", ".join(letters)}. Count the strings for which '
                  + '; '.join(rules) + '.\n\nQuestion: how many such strings are there? Write one integer.')
    else:
        rules[0] = ('reading around the circle (so also across the point where the last bead meets the first), it '
                    'never shows ' + ' or '.join(f'`{f}`' for f in forbidden) + ' as consecutive beads')
        if a_count is not None:
            rules.append(f'exactly {a_count} beads are `{letters[0]}`')
        prompt = (f'A necklace has {n} beads on a circle, each bead one of the colours {", ".join(letters)}. Two '
                  'necklaces are the same when one is a rotation of the other (turning it over is not allowed). '
                  'Count the different necklaces for which ' + '; '.join(rules)
                  + '.\n\nQuestion: how many different necklaces are there? Write one integer (exact, no modulus).')
    return {'kind': 'answer', 'prompt': prompt, 'answer': str(answer)}


# ---------------------------------------------------------------- strfun: implement a string pipeline (hidden tests)

VOWELS = 'aeiou'
ORDINAL = {2: 'second', 3: 'third', 4: 'fourth'}


def strfun_ops(rng):
    """(function, text, invertible).  Invertible steps are bijections on strings, so a pipeline of them has an
    inverse; the hardest tier asks for that inverse."""
    k, m, a, b, n = rng.randint(1, 5), rng.randint(1, 3), rng.choice([3, 7, 9]), rng.randint(1, 9), rng.randint(2, 4)

    def shift(c, by):
        base = ord('a') if c.islower() else ord('A')
        return chr((ord(c) - base + by) % 26 + base)

    def letter(c):
        return c.isascii() and c.isalpha()

    def caesar(s):
        return ''.join(shift(c, k) if letter(c) else c for c in s)

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
            if letter(c):
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

    def interleave(s):
        return s[0::2] + s[1::2]

    def progressive(s):
        out, seen = [], 0
        for c in s:
            if letter(c):
                out.append(shift(c, k + seen))
                seen += 1
            else:
                out.append(c)
        return ''.join(out)

    return [
        (caesar, f'Shift every ASCII letter {k} place' + ('s' if k > 1 else '') + ' forward in the alphabet, wrapping z to a and Z to A and keeping '
                 'its case; leave other characters unchanged.', True),
        (rotate, f'Rotate the whole string left by {k} position' + ('s' if k > 1 else '') + f' (by {k} modulo the length; the '
                 'empty string stays empty).', True),
        (reverse_runs, 'Reverse the characters inside every maximal run of non-whitespace characters; whitespace '
                       'characters stay exactly where they are.', True),
        (swap_pairs, 'Swap the characters at positions 0 and 1, 2 and 3, and so on; a final unpaired character stays.',
         True),
        (collapse, f'Shorten every run of one repeated character that is longer than {m} to exactly {m} copies.', False),
        (digits, f'Replace every decimal digit d by the digit ({a} * d + {b}) mod 10.', True),
        (drop, f'Delete every {ORDINAL[n]} character, counting positions from 1 (positions {n}, {2 * n}, ...).',
         False),
        (alternate, 'Among ASCII letters only, make the 1st, 3rd, 5th, ... letter (counted over letters only) '
                    'uppercase and the 2nd, 4th, ... letter lowercase; leave other characters unchanged.', False),
        (vowels, 'Replace each vowel by the next one in the cycle a, e, i, o, u, a, keeping its case (A becomes E, '
                 'u becomes a); y is not a vowel.', True),
        (mirror, f'Append the reverse of the last {m + 1} characters (the reverse of the whole string if it is '
                 'shorter); the empty string stays empty.', False),
        (interleave, 'Write the characters at even positions (0, 2, 4, ...) in order, followed by the characters at '
                     'odd positions (1, 3, 5, ...) in order.', True),
        (progressive, f'Shift the ASCII letters forward in the alphabet by a growing number of places, keeping case '
                      f'and wrapping as usual: the first letter by {k}, the second letter by {k + 1}, the third by '
                      f'{k + 2}, and so on (letters only are counted); leave other characters unchanged.', True),
    ]


STRFUN_STEPS = {1: 1, 2: 2, 3: 3, 4: 4, 5: 6}
STRFUN_EXAMPLES = (1, 2, 3)  # tiers that show examples; from tier 4 on the specification alone must be followed


def strfun_samples(rng):
    alphabet = 'abcdeiouxyzAEIOUQZ0123456789  !?-.'
    samples = ['', 'a', 'Zz 9', 'aaa   bbbb!!', 'Hello World 2024', 'u U y Y']
    while len(samples) < 34:
        length = rng.randint(1, 24)
        word = ''.join(rng.choice(alphabet) for _ in range(length))
        if rng.random() < 0.3:
            word = word.replace(word[0], word[0] * 3, 1)
        samples.append(word)
    return samples


def strfun_item(rng, tier):
    ops = strfun_ops(rng)
    decode = tier == 5
    chosen = rng.sample([o for o in ops if o[2]] if decode else ops, STRFUN_STEPS[tier])

    def apply(s):
        for op, _, _ in chosen:
            s = op(s)
        return s
    samples = strfun_samples(rng)
    steps = '\n'.join(f'{i}. {text}' for i, (_, text, _) in enumerate(chosen, 1))
    if decode:
        samples = samples[:4] + samples[6:]  # 4 and 5 are shown as transform examples in lower tiers
        encoded = [apply(s) for s in samples]
        if len(set(encoded)) != len(encoded):
            raise AssertionError('strfun decode pipeline is not injective')
        cases = [{'args': [e], 'expected': s} for s, e in zip(samples, encoded)]
        prompt = ('An encoder applies these steps in order, each to the result of the previous one:\n\n'
                  f'{steps}\n\nImplement `decode(s: str) -> str`, the exact inverse of this encoder: for every string '
                  't, decode(encoder(t)) == t. No examples are given; follow the steps exactly as written. Use only the '
                  'Python 3 standard library. Hidden tests call decode on encoded strings.')
        return {'kind': 'code', 'entry': 'decode', 'prompt': prompt, 'tests': cases,
                'stub': 'def decode(s: str) -> str:\n    raise NotImplementedError\n'}
    cases = [{'args': [s], 'expected': apply(s)} for s in samples]
    if tier in STRFUN_EXAMPLES:
        visible, hidden = cases[4:6], cases[:4] + cases[6:]
        shown = ('Examples:\n' + '\n'.join(f'- transform({json.dumps(c["args"][0])}) == {json.dumps(c["expected"])}'
                                            for c in visible) + '\n\n')
    else:
        hidden, shown = cases, 'No examples are given; follow the steps exactly as written.\n\n'
    prompt = ('Implement `transform(s: str) -> str` that applies these steps in order, each to the result of the '
              f'previous one:\n\n{steps}\n\n{shown}'
              'Use only the Python 3 standard library. Hidden tests call transform on other strings.')
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
    # short visible examples keep the problem text short; hidden tests use the full-length lists.  From tier 4 on
    # there are none: the rules alone must be followed.
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
                     'and subtract its amount from the balance (no fee, no limit, not counted as a withdrawal). Both are rejected if the id is not '
                     'an active hold.')
    limits = [f'Available funds = balance + {r["overdraft"]} (overdraft allowance)'
              + (' - the sum of the active holds on that account' if tier >= 5 else '') + '.',
              f'A {w["withdraw"]}' + (f' or {w["transfer"]}' if tier >= 3 else '')
              + (f' or {w["hold"]}' if tier >= 5 else '') + ' is rejected when the amount plus its fee' + (' (holds have no fee)' if tier >= 5 else '')
              + ' exceeds the available funds.']
    if tier >= 4:
        limits.append(f'A {w["withdraw"]} is also rejected when the account\'s successful withdrawal amounts (fees not '
                      f'counted) since the last {w["close"]} would exceed {r["daily"]}.')
    limits.append('A rejected event changes nothing.')
    visible = examples if tier < 4 else []
    prompt = ('Implement `settle(events: list[str]) -> dict` for this ledger. Every account starts at 0 and exists from '
              'the first event that names it (even a rejected one). Amounts are integers.\n\nEvents:\n'
              + '\n'.join('- ' + x for x in rules) + '\n\nLimits:\n' + '\n'.join('- ' + x for x in limits)
              + '\n\nReturn a dict mapping every account name to its final balance, plus the key "_rejected" with the '
              'number of rejected events.\n\n'
              + ('Examples:\n' + '\n'.join(f'- settle({json.dumps(c["args"][0])}) == {json.dumps(c["expected"])}'
                                            for c in visible) if visible else
                 'No examples are given; follow the rules exactly as written.')
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


def interleaved(bank, seed, key='family'):
    """Fixed set order: items grouped by `key` (family or tier), shuffled within the group by `seed`, then dealt round
    robin so consecutive items cycle through the groups."""
    rng = random.Random(f'order/{seed}')
    groups = {}
    for x in bank['items']:
        groups.setdefault(x[key], []).append(x['id'])
    for name in sorted(groups):
        rng.shuffle(groups[name])
    return [groups[g][k] for k in range(max(map(len, groups.values()))) for g in sorted(groups) if k < len(groups[g])]


# ---------------------------------------------------------------- workspace and scoring

WORKSPACE_README = '''# Problem

Problems come one at a time. This directory holds only the current one, `problems/<P>.md`; the message that gave it
to you names it. Solve it, then write the result:

- Answer problems (they end with a "Question:"): write only the final answer to `answers/<P>.txt`, one line,
  in the format the problem asks for.
- Code problems (they ask you to implement or fix code): write the requested function in `solutions/<P>.py` (a stub
  is there), or, when the problem's files are under `solutions/<P>/`, fix those files in place. Only the Python 3
  standard library is available.

You may use the shell and write scratch files anywhere inside this directory. Paths outside it, including /tmp,
are not available. Nothing outside this directory is needed. Answers are checked automatically after you finish;
there is no partial credit inside a problem.

When your turn ends, the problem and everything you wrote here are removed and cannot be seen again; the next
problem, if any, comes in a new message. Each problem has a hard time limit: when it is reached you are stopped
without warning and only the files already written are scored, so write the answer or solution file as soon as you
have it (you may still improve it before ending the turn).
'''

CALIBRATION_README = '''# Problem set

Each problem is in `problems/<P>.md`. Solve every problem.

- Answer problems (they end with a "Question:"): write only the final answer to `answers/<P>.txt`, one line,
  in the format the problem asks for.
- Code problems (they ask you to implement or fix code): write the requested function in `solutions/<P>.py` (a stub
  is there), or, when the problem's files are under `solutions/<P>/`, fix those files in place. Only the Python 3
  standard library is available.

You may use the shell and write scratch files anywhere inside this directory. Paths outside it, including /tmp,
are not available. Nothing outside this directory is needed. Answers are checked automatically after you finish;
there is no partial credit inside a problem.

There is a hard time limit. When it is reached you are stopped without warning and only the files already written
are scored; a problem with no written answer or solution scores zero. So write each answer or solution file as soon
as that problem is done, before moving to the next one, and do the problems you are surest of first.
'''


def export(bank, folder, numbers=None, readme=WORKSPACE_README):
    """Answer-free workspace for the selected numbers (all by default)."""
    folder = Path(folder)
    for sub in ('problems', 'answers', 'solutions'):
        (folder / sub).mkdir(parents=True, exist_ok=True)
    (folder / 'README.md').write_text(readme)
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


def points_of(bank):
    """Per-item points of a frozen set (all items carry `points`), or None for an unweighted draft or pilot set."""
    given = [x.get('points') for x in bank['items']]
    if all(p is None for p in given):
        return None
    if any(p is None or p <= 0 for p in given):
        raise ValueError('Either every item has positive points or none has')
    return {x['id']: x['points'] for x in bank['items']}


def score(bank, workspace):
    """Per item: correct is all-or-nothing.  Instance score = points of correct items / all points (each item one
    point in an unweighted set); per-tier rates are reported unweighted."""
    workspace, rows = Path(workspace), []
    points = points_of(bank)
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
        rows[-1]['points'] = points[x['id']] if points else 1
    return weighted(rows)


def weighted(rows):
    by_tier = {t: [r['correct'] for r in rows if r['tier'] == t] for t in TIERS}
    total = sum(r['points'] for r in rows)
    return {'score': sum(r['points'] for r in rows if r['correct']) / total, 'points_total': total,
            'correct': sum(r['correct'] for r in rows), 'items': len(rows),
            'by_tier': {t: sum(v) / len(v) for t, v in by_tier.items() if v}, 'rows': rows}


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
as you can. The hard limit is {minutes} minutes: at the limit the files are taken as they are and you are stopped, so
write each answer or solution file as soon as that problem is done.
When you are done, reply with the single word DONE."""


def calibration_prepare(bank, out, runs, minutes):
    """One fresh answer-free workspace per independent Opus run, plus the exact prompt each run receives."""
    out = Path(out)
    rows = []
    for k in range(1, runs + 1):
        workspace = export(bank, out / f'run-{k}' / 'workspace', readme=CALIBRATION_README).resolve()
        prompt = CALIBRATION_PROMPT.format(workspace=workspace, minutes=minutes)
        (out / f'run-{k}' / 'prompt.txt').write_text(prompt)
        rows.append({'run': k, 'workspace': str(workspace), 'prompt_sha256': sha(prompt.encode())})
    manifest = {'bank_sha256': sha(json.dumps(bank, sort_keys=True).encode()), 'runs': rows, 'minutes': minutes,
                'timing': 'Main writes run-<k>/start-epoch before the run and run-<k>/timing.json as '
                          '{"seconds": <wall seconds of the whole set>}; at the hard limit it copies the workspace to '
                          'run-<k>/deadline-snapshot, which is then scored instead of the workspace'}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=1) + '\n')
    return manifest


def write_intervals(bank, workspace, started):
    """Rough per-item Opus time: gap between consecutive answer/solution writes (first gap from the start).
    Only a relative cost signal; Qwen's own per-item time comes from the pilot run."""
    workspace, stamps = Path(workspace), []
    for x in bank['items']:
        path = workspace / ('answers' if x['kind'] == 'answer' else 'solutions') / (x['number'] + ('.txt' if x['kind'] == 'answer' else '.py'))
        if path.is_file() and (x['kind'] == 'answer' or path.read_text(errors='replace') != x['stub']):
            stamps.append((path.stat().st_mtime, x['id']))
    stamps.sort()
    previous, result = started, {}
    for stamp, item_id in stamps:
        result[item_id] = max(0.0, stamp - previous)
        previous = stamp
    return result


def calibration_score(bank, out):
    """Per item: Opus passes out of the runs; per run: score and time.  Items with zero passes must be replaced."""
    out = Path(out)
    manifest = json.loads((out / 'manifest.json').read_text())
    runs, passed, seconds = [], {x['id']: [] for x in bank['items']}, {x['id']: [] for x in bank['items']}
    for row in manifest['runs']:
        here = out / f'run-{row["run"]}'
        snapshot = here / 'deadline-snapshot'
        workspace = snapshot if snapshot.is_dir() else Path(row['workspace'])  # the hard limit: files at the deadline
        start = here / 'start-epoch' if (here / 'start-epoch').exists() else out / 'start-epoch'
        result = score(bank, workspace)
        timing = out / f'run-{row["run"]}' / 'timing.json'
        runs.append({'run': row['run'], 'score': result['score'], 'by_tier': result['by_tier'],
                     'seconds': json.loads(timing.read_text())['seconds'] if timing.exists() else None,
                     'scored': 'deadline-snapshot' if snapshot.is_dir() else 'workspace'})
        for r in result['rows']:
            if r['correct']:
                passed[r['id']].append(row['run'])
        if start.exists():
            for item_id, spent in write_intervals(bank, workspace, float(start.read_text())).items():
                seconds[item_id].append(spent)
    passes = {k: len(v) for k, v in passed.items()}
    n = len(runs)
    items = [{'id': x['id'], 'number': x['number'], 'tier': x['tier'], 'family': x['family'], 'passes': passes[x['id']],
              'passed_runs': passed[x['id']], 'runs': n,
              'opus_seconds': sorted(seconds[x['id']])[len(seconds[x['id']]) // 2] if seconds[x['id']] else None}
             for x in bank['items']]
    return {'runs': runs, 'opus_mean_score': sum(r['score'] for r in runs) / n if n else None,
            'opus_full_marks_runs': sum(r['score'] == 1 for r in runs),
            'replace': [i['id'] for i in items if i['passes'] == 0],
            'pass_rate_by_tier': {t: sum(i['passes'] for i in items if i['tier'] == t)
                                  / (n * sum(i['tier'] == t for i in items)) for t in TIERS if n},
            'items': items}


# ---------------------------------------------------------------- fixed formal set (after Opus calibration and Qwen pilot)

def choose(bank, calibration, pilot, count, low=0.3, high=0.7):
    """Proposal for the fixed formal set (every instance runs the same items; nothing is drawn at random).

    Eligible: Opus solved the item at least once, and the Qwen pilot ran it in a session without compaction.  Each
    family gets an equal share of `count`; within a family the items Qwen got right and wrong are mixed so the whole
    set's pilot accuracy lands at the middle of [low, high], shortest pilot time first.  The instance time is
    estimated as the sum of the chosen items' pilot turn times (a timed-out item counts its limit, a lower bound),
    and is reported for the user to weigh against the per-instance limit.  Proposed points = the item's tier (to be
    confirmed).  Opus must not get full marks on the subset in any calibration run.
    """
    turns = {t['id']: t for t in pilot['turns']}
    affected = sorted(i for i, t in turns.items() if t.get('compacted_session'))
    if affected:
        return {'ok': False, 'problems': [f'items in a compacted pilot session must be rerun: {affected}']}
    opus = {i['id']: i for i in calibration['items']}
    families = sorted({x['family'] for x in bank['items']})
    eligible = {f: sorted((x['id'] for x in bank['items'] if x['family'] == f and x['id'] in turns
                           and opus[x['id']]['passes'] > 0), key=lambda i: (turns[i]['seconds'], i)) for f in families}
    right_target = round(count * (low + high) / 2)
    chosen, problems = [], []
    for n, f in enumerate(families):
        share = count // len(families) + (n < count % len(families))
        want_right = round(right_target * share / count)
        right = [i for i in eligible[f] if turns[i]['correct']]
        wrong = [i for i in eligible[f] if not turns[i]['correct']]
        take_right = min(len(right), max(want_right, share - len(wrong)))
        picked = right[:take_right] + wrong[:share - take_right]
        if len(picked) < share:
            problems.append(f'{f}: only {len(picked)} eligible items for a share of {share}')
        chosen += picked
    accuracy = sum(turns[i]['correct'] for i in chosen) / len(chosen) if chosen else None
    if accuracy is not None and not low <= accuracy <= high:
        problems.append(f'pilot accuracy {accuracy:.2f} outside [{low}, {high}]')
    points = {i: bank_tier(bank, i) for i in chosen}
    total = sum(points.values())
    run_scores = {r['run']: sum(points[i] for i in chosen if r['run'] in opus[i]['passed_runs']) / total
                  for r in calibration['runs']} if total else {}
    problems += [f'Opus run {r} gets full marks on the subset' for r, v in run_scores.items() if v == 1]
    seconds = sorted(turns[i]['seconds'] for i in chosen)
    growth = {}
    for i in chosen:
        t = turns[i]
        growth[str(bank_tier(bank, i))] = max(growth.get(str(bank_tier(bank, i)), 0),
                                              t['context_after'] - t['context_before'])
    return {'ok': not problems, 'problems': problems, 'count': len(chosen), 'ids': chosen, 'points': points,
            'pilot_accuracy': accuracy, 'band': [low, high],
            'by_family': {f: sum(bank_family(bank, i) == f for i in chosen) for f in families},
            'by_tier': {t: sum(bank_tier(bank, i) == t for i in chosen) for t in sorted({bank_tier(bank, i) for i in chosen})},
            'expected_instance_seconds': round(sum(seconds), 1),
            'expected_is_lower_bound': any(turns[i]['timed_out'] for i in chosen),
            'item_seconds': {'median': seconds[len(seconds) // 2], 'max': seconds[-1]} if seconds else None,
            'max_context_growth_by_tier': growth, 'opus_subset_scores': run_scores,
            'excluded_opus_zero': [x['id'] for x in bank['items'] if opus[x['id']]['passes'] == 0]}


def bank_tier(bank, item_id):
    return next(x['tier'] for x in bank['items'] if x['id'] == item_id)


def bank_family(bank, item_id):
    return next(x['family'] for x in bank['items'] if x['id'] == item_id)


def freeze(bank, proposal, seed):
    """Fixed formal set from an approved proposal: the chosen items, families interleaved, points attached."""
    chosen = {**bank, 'items': [dict(x, points=proposal['points'][x['id']]) for x in bank['items']
                                if x['id'] in proposal['points']]}
    return {**select(chosen, interleaved(chosen, seed)),
            'design': {k: proposal[k] for k in ('count', 'pilot_accuracy', 'expected_instance_seconds')}}


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
    s.add_argument('--interleave-seed', type=int, help='all items, families interleaved (instead of --ids)')
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
    d = sub.add_parser('choose', help='propose the fixed formal set from Opus calibration and the Qwen pilot')
    d.add_argument('--bank', type=Path, required=True)
    d.add_argument('--calibration', type=Path, required=True)
    d.add_argument('--pilot', type=Path, required=True, help="the pilot instance's result.json")
    d.add_argument('--count', type=int, default=20)
    d.add_argument('--low', type=float, default=0.3)
    d.add_argument('--high', type=float, default=0.7)
    d.add_argument('--out', type=Path, required=True)
    f = sub.add_parser('freeze', help='fixed formal set from an approved choose proposal')
    f.add_argument('--bank', type=Path, required=True)
    f.add_argument('--design', type=Path, required=True)
    f.add_argument('--interleave-seed', type=int, required=True)
    f.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'choose':
        result = choose(json.loads(args.bank.read_text()), json.loads(args.calibration.read_text()),
                        json.loads(args.pilot.read_text()), args.count, args.low, args.high)
        args.out.write_text(json.dumps(result, indent=1) + '\n')
        print(json.dumps({k: v for k, v in result.items() if k not in ('ids', 'points')}))
        return
    if args.command == 'freeze':
        result = freeze(json.loads(args.bank.read_text()), json.loads(args.design.read_text()), args.interleave_seed)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n')
        return
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
