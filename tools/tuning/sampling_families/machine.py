"""machine: give the output of a program for a register machine whose semantics are easy to misread.

The traps are in the semantics: reversed SUB operands, a flag set from the true (unreduced) result, DJNZ that
decrements before testing (0 wraps), signed comparisons, jump numbering.  An item is kept only when every listed
misreading gives a different answer.  Every level repeats blocks far more often than a program can step through.

Level 4 (small moduli, SHR in the blocks): one block repeated 10^11-10^13 times, a flag test, a second such block
and a signed-comparison loop; only cycle detection over the (registers, flag) state finishes it.  Level 5: the
registers live modulo a large prime (998244353, 10^9+7 or 2^31-1) and the repeated block only adds literals or
registers, subtracts and multiplies by literals, so it is an affine map; it runs about 10^15 times and the exact
orbit period of the register vector (computed from the factorised order of the 4x4 matrix group) must exceed
10^12, so cycle detection is out of reach even in compiled code.  The block has to be raised to a matrix power,
and because the flag after the block comes from the final repetition, the solver must stop the power at count - 1
and simulate the last repetition; a flag test and a signed-comparison loop follow.  Level 6 has two such blocks
around flag tests, as level 4 does.  (`tier` in this module is the level.)
"""
REGISTERS = 'ABDGKMNPRSTVXZ'
MODULI = (100, 128, 200, 256, 1000)
PRIMES = (2147483647, 1000000007, 998244353)
# p * (p-1) * (p+1) * (p^2+1) * (p^2+p+1), factorised: a multiple of the order of every invertible 4x4 matrix over
# Z_p, so the exact orbit period of an affine map on three registers is one of its divisors
ORDER_FACTORS = {
    2147483647: {2: 33, 3: 3, 5: 1, 7: 1, 11: 1, 31: 1, 151: 1, 331: 1, 733: 1, 1709: 1, 529510939: 1,
                 2147483647: 1, 2903110321: 1, 368140581013: 1},
    1000000007: {2: 5, 3: 2, 5: 2, 7: 1, 109: 2, 167: 1, 6067: 1, 58699937: 1, 340715873: 1, 500000003: 1,
                 1000000007: 1, 164826110927971: 1},
    998244353: {2: 25, 3: 1, 5: 1, 7: 1, 17: 1, 1481: 1, 1601: 1, 3643: 1, 112339: 1, 2255437: 1, 27596353: 1,
                998244353: 1, 273536038785241: 1},
}
STEP_LIMIT = 200000
DIRECT_REP_LIMIT = 100000
PERIOD_FLOOR = 10 ** 12


def variant(rng, tier):
    return {'tier': tier, 'modulus': rng.choice(MODULI if tier <= 4 else PRIMES),
            'sub': rng.choice(['reversed', 'normal']), 'jumps': rng.choice(['absolute', 'relative']),
            'signed': True, 'shr_flag': True, 'djnz': 'first'}


# ---------------------------------------------------------------- affine blocks modulo a prime

def mat_mul(x, y, m):
    return [[sum(a * b for a, b in zip(row, col)) % m for col in zip(*y)] for row in x]


def mat_pow(x, e, m):
    out = [[int(i == j) for j in range(len(x))] for i in range(len(x))]
    while e:
        if e & 1:
            out = mat_mul(out, x, m)
        x = mat_mul(x, x, m)
        e >>= 1
    return out


def apply(x, vector, m):
    return [sum(a * b for a, b in zip(row, vector)) % m for row in x]


def affine(body, names, r):
    """Homogeneous matrix of one pass of `body` on the vector (registers `names`..., 1)."""
    m, size = r['modulus'], len(names) + 1
    rows = {n: [int(i == j) for j in range(size)] for i, n in enumerate(names)}
    for op, reg, x in body:
        here = rows[reg]
        other = rows[x] if isinstance(x, str) else [0] * (size - 1) + [x]
        if op == 'ADD':
            new = [a + b for a, b in zip(here, other)]
        elif op == 'SUB':
            new = [b - a for a, b in zip(here, other)] if r['sub'] == 'reversed' else \
                [a - b for a, b in zip(here, other)]
        elif op == 'MUL' and not isinstance(x, str):
            new = [a * x for a in here]
        else:
            raise ValueError(f'{op} {reg} {x} is not affine')
        rows[reg] = [v % m for v in new]
    return [rows[n] for n in names] + [[0] * (size - 1) + [1]]


def orbit_period(matrix, vector, m):
    """Smallest t >= 1 with matrix^t vector = vector (the matrix must be invertible)."""
    t = 1
    for prime, power in ORDER_FACTORS[m].items():
        t *= prime ** power
    assert apply(mat_pow(matrix, t, m), vector, m) == vector
    for prime, power in ORDER_FACTORS[m].items():
        for _ in range(power):
            if apply(mat_pow(matrix, t // prime, m), vector, m) != vector:
                break
            t //= prime
    return t


# ---------------------------------------------------------------- interpreter

def run(program, r, info=None):
    """Outputs of `program` (list of tuples, jump targets as 0-based line indexes) under the semantics `r`."""
    m, regs, flag, pc, out, steps = r['modulus'], {}, False, 0, [], 0

    def val(x):
        return regs.get(x, 0) if isinstance(x, str) else x

    def signed(v):
        return v - m if r['signed'] and v >= m // 2 else v

    def alu(ins):
        nonlocal flag
        op, reg = ins[0], ins[1]
        here = regs.get(reg, 0)
        if op == 'SET':
            regs[reg] = ins[2] % m
            return
        if op == 'SHR':
            if r['shr_flag']:
                flag = here % 2 == 1
            regs[reg] = here // 2
            return
        x = val(ins[2])
        total = {'ADD': here + x, 'MUL': here * x,
                 'SUB': x - here if r['sub'] == 'reversed' else here - x}[op]
        flag = total < 0 if op == 'SUB' else total >= m
        regs[reg] = total % m

    def repeat(count, body):
        """Cycle detection over the (registers, flag) state; direct for small counts."""
        names = sorted(set(regs) | {b[1] for b in body})
        seen, k, executed = {}, 0, 0
        while k < count:
            executed += 1
            if executed > STEP_LIMIT:
                raise OverflowError('no cycle found in a long REP block')
            state = (tuple(regs.get(n, 0) for n in names), flag)
            if count > DIRECT_REP_LIMIT and state in seen:
                if info is not None:
                    info.setdefault('cycles', []).append(k - seen[state])
                k = count - (count - k) % (k - seen[state])
                seen = {}
                if k >= count:
                    break
            seen[state] = k
            for b in body:
                alu(b)
            k += 1

    def power(count, body):
        """count - 1 passes as a matrix power, then the last pass step by step for the flag."""
        names = sorted({b[1] for b in body} | {b[2] for b in body if isinstance(b[2], str)})
        matrix, vector = affine(body, names, r), [regs.get(n, 0) for n in names] + [1]
        if info is not None:
            info.setdefault('orbits', []).append((matrix, vector))
        regs.update(zip(names, apply(mat_pow(matrix, count - 1, m), vector, m)))
        for b in body:
            alu(b)

    while 0 <= pc < len(program):
        steps += 1
        if steps > STEP_LIMIT:
            raise OverflowError('program runs too long')
        ins = program[pc]
        op = ins[0]
        if op == 'REP':
            body = program[pc + 1:pc + 1 + ins[2]]
            (power if r['tier'] >= 5 and ins[1] > DIRECT_REP_LIMIT else repeat)(ins[1], body)
            pc += 1 + ins[2]
            continue
        target = None
        if op in ('SET', 'ADD', 'SUB', 'MUL', 'SHR'):
            alu(ins)
        elif op == 'OUT':
            out.append(regs.get(ins[1], 0))
        elif op == 'HALT':
            break
        elif op == 'JF':
            target = ins[1] if flag else None
        elif op == 'JLT':
            target = ins[3] if signed(regs.get(ins[1], 0)) < signed(val(ins[2])) else None
        elif op == 'DJNZ':
            if r['djnz'] == 'first':
                regs[ins[1]] = (regs.get(ins[1], 0) - 1) % m
                target = ins[2] if regs[ins[1]] != 0 else None
            else:  # misreading: test, then decrement
                target = ins[2] if regs.get(ins[1], 0) != 0 else None
                regs[ins[1]] = (regs.get(ins[1], 0) - 1) % m
        pc = target if target is not None else pc + 1
    return out


def misreadings(r):
    wrong = [dict(r, sub='normal' if r['sub'] == 'reversed' else 'reversed'), dict(r, djnz='test'),
             dict(r, signed=False)]
    if r['tier'] <= 4:
        wrong.append(dict(r, shr_flag=False))
    return wrong


# ---------------------------------------------------------------- program shapes

def operand(rng, regs, m, literal_share=0.5):
    return rng.randint(1, m - 1) if rng.random() < literal_share else rng.choice(regs)


def ops(rng, regs, m, count, targets=None, allowed=('ADD', 'SUB', 'MUL', 'SHR'), units=False):
    """Random arithmetic lines; with `units`, MUL only by a literal coprime to every small modulus."""
    out = []
    for _ in range(count):
        op = rng.choice(allowed)
        reg = rng.choice(targets or regs)
        if op == 'SHR':
            out.append(('SHR', reg))
        elif op == 'MUL':
            factor = rng.choice([3, 7, 9, 11, 13]) if units or rng.random() < 0.7 else rng.choice(regs)
            out.append(('MUL', reg, factor))
        else:
            out.append((op, reg, operand(rng, regs, m)))
    return out


def affine_body(rng, data, m):
    """4-6 lines of ADD/SUB (literal or another register) and MUL by a literal, touching every data register."""
    while True:
        body = []
        for _ in range(rng.randint(4, 6)):
            op, reg = rng.choice(('ADD', 'ADD', 'SUB', 'SUB', 'MUL')), rng.choice(data)
            if op == 'MUL':
                body.append(('MUL', reg, rng.randint(2, m - 1)))
            else:
                body.append((op, reg, rng.choice([x for x in data if x != reg]) if rng.random() < 0.5
                             else rng.randint(1, m - 1)))
        if ({b[0] for b in body} == {'ADD', 'SUB', 'MUL'} and {b[1] for b in body} == set(data)
                and any(isinstance(b[2], str) for b in body)):
            return body


def attempt(rng, tier, r):
    """Program with symbolic labels ('@name') for jump targets."""
    m = r['modulus']
    regs = rng.sample(REGISTERS, 4)
    data, counter = regs[:-1], regs[-1]
    p = [('SET', x, rng.randint(0, m - 1)) for x in data]
    if tier <= 4:
        # mostly permutations of the state (ADD, SUB, MUL by a unit), so the repeated block cycles instead of
        # collapsing to a fixed point
        blocks = [ops(rng, data, m, rng.randint(4, 6), allowed=('ADD', 'SUB', 'ADD', 'SUB', 'MUL', 'SHR'),
                      units=True),
                  ops(rng, data, m, rng.randint(3, 5), allowed=('ADD', 'SUB', 'MUL', 'SHR'), units=True)]
        counts = [rng.randint(10 ** 11, 10 ** 13) for _ in blocks]
        loop_ops = ('ADD', 'SUB', 'MUL', 'SHR')
    else:
        blocks = [affine_body(rng, data, m) for _ in range(2 if tier >= 6 else 1)]
        counts = [rng.randint(10 ** 15, 9 * 10 ** 15) for _ in blocks]
        loop_ops = ('ADD', 'SUB', 'MUL')
    p += [('REP', counts[0], len(blocks[0]))] + blocks[0]
    p += [('JF', '@carry'), ('OUT', data[0]), ('LABEL', 'carry')]
    if len(blocks) > 1:
        p += [('OUT', data[2]), ('REP', counts[1], len(blocks[1]))] + blocks[1]
        p += [('JF', '@flag2'), ('OUT', data[1]), ('LABEL', 'flag2')]
    p += [('SET', counter, rng.randint(3, 6)), ('LABEL', 'loop')]
    p += [('JLT', data[1], operand(rng, data, m), '@skip')] + ops(rng, regs, m, 1, data, loop_ops)
    p += [('LABEL', 'skip')] + ops(rng, regs, m, 1, data, loop_ops)
    p += [('OUT', rng.choice(data)), ('DJNZ', counter, '@loop')]
    p += [('OUT', x) for x in data]
    return p


def resolve(symbolic):
    """Drop labels and replace '@label' by the 0-based index of the line that follows the label."""
    lines, labels = [], {}
    for ins in symbolic:
        if ins[0] == 'LABEL':
            labels[ins[1]] = len(lines)
        else:
            lines.append(ins)
    return [tuple(labels[x[1:]] if isinstance(x, str) and x.startswith('@') else x for x in ins) for ins in lines]


def listing(program, r):
    rows = []
    for i, ins in enumerate(program):
        parts = list(ins)
        jump_at = {'JF': 1, 'JLT': 3, 'DJNZ': 2}.get(ins[0])
        if jump_at is not None:
            target = ins[jump_at]
            parts[jump_at] = target + 1 if r['jumps'] == 'absolute' else f'{target - i:+d}'
        rows.append(f'{i + 1}: ' + ' '.join(str(x) for x in parts))
    return '\n'.join(rows)


def describe(r):
    m = r['modulus']
    jump = ('`n` is a line number; lines are numbered from 1' if r['jumps'] == 'absolute' else
            '`n` is an offset relative to the jump instruction itself: +1 is the next line, -2 is two lines back')
    sub = 'R := x - R (note the order)' if r['sub'] == 'reversed' else 'R := R - x'
    rules = [
        f'Registers hold integers 0..{m - 1} and all start at 0. There is also a flag F, initially false. An operand '
        '`x` is a register name or a literal integer.',
        f'Arithmetic results are taken modulo {m} (always into 0..{m - 1}).',
        'SET R v: R := v. F unchanged.',
        f'ADD R x: R := R + x. F := whether the true sum (before the modulo) is {m} or more.',
        f'MUL R x: R := R * x. F := whether the true product (before the modulo) is {m} or more.',
        f'SUB R x: {sub}. F := whether the true difference (before the modulo) is negative.',
        *(['SHR R: R := floor(R / 2). F := whether the bit shifted out was 1 (the old R was odd).']
          if r['tier'] <= 4 else []),
        f'JF n: jump if F is true; {jump}.',
        f'JLT R x n: jump if R < x; {jump}.'
        + (f' The comparison is signed: both sides, R and x (whether x is a register or a literal), are first read as '
           f'signed numbers, where a value v of {m // 2} or more counts as v - {m} (so {m - 1} counts as -1).'
           if r['signed'] else ' The comparison uses the plain values.'),
        f'DJNZ R n: first R := R - 1 (modulo {m}, so 0 becomes {m - 1}; F unchanged), then jump if R is not 0; '
        f'{jump}.',
        'REP k n: execute the n lines after this one k times in a row, then continue after them. Those n lines never '
        'contain jumps, OUT, HALT or REP; F carries over between repetitions.',
        'OUT R: output the value of R. HALT: stop.',
        'After a line that does not jump, execution continues with the next line. The program stops after its last '
        'line, at HALT, or when a jump goes to a line that does not exist.',
    ]
    return '\n'.join('- ' + x for x in rules)


def item(rng, tier):
    r = variant(rng, tier)
    for _ in range(500):
        program = resolve(attempt(rng, tier, r))
        info = {}
        try:
            answer = run(program, r, info)
            wrong = [run(program, w) for w in misreadings(r)]
        except OverflowError:
            continue
        lively = 3 * answer.count(0) <= len(answer) and len(set(answer)) >= max(3, len(answer) // 2)
        if not (3 <= len(answer) <= 24 and lively and all(w != answer for w in wrong)):
            continue
        if (min(info.get('cycles', [0])) >= 5 if tier <= 4 else
                all(orbit_period(x, v, r['modulus']) > PERIOD_FLOOR for x, v in info['orbits'])):
            break
    else:
        raise AssertionError('no machine program met the constraints')
    prompt = (f'A register machine works as follows.\n\n{describe(r)}\n\nProgram:\n\n{listing(program, r)}\n\n'
              'Question: What values does the program output, in order? Answer with the values separated by commas '
              '(for example 3,0,17).')
    return {'kind': 'answer', 'prompt': prompt, 'answer': ','.join(map(str, answer)),
            'machine': {'variant': r, 'program': [list(x) for x in program]}}
