"""machine: give the output of a program for a register machine whose semantics are easy to misread.

Running the program is easy with a shell; the difficulty is reading the semantics right: reversed SUB operands, a
flag that SHR sets from the bit shifted out, DJNZ that decrements before testing (0 wraps), signed comparisons, jump
numbering.  An item is kept only when every listed misreading gives a different answer.  Tier 3 repeats a block
10^11-10^13 times, which only cycle detection over the (registers, flag) state can finish.
"""
REGISTERS = 'ABDGKMNPRSTVXZ'
MODULI = (100, 128, 200, 256, 1000)
STEP_LIMIT = 200000
DIRECT_REP_LIMIT = 100000


def variant(rng, tier):
    return {'tier': tier, 'modulus': rng.choice(MODULI), 'sub': rng.choice(['reversed', 'normal']),
            'jumps': rng.choice(['absolute', 'relative']), 'signed': tier >= 2, 'shr_flag': True, 'djnz': 'first'}


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

    while 0 <= pc < len(program):
        steps += 1
        if steps > STEP_LIMIT:
            raise OverflowError('program runs too long')
        ins = program[pc]
        op = ins[0]
        if op == 'REP':
            count, body = ins[1], program[pc + 1:pc + 1 + ins[2]]
            names = sorted(set(regs) | {b[1] for b in body})
            seen, k = {}, 0
            while k < count:
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
    wrong = [dict(r, sub='normal' if r['sub'] == 'reversed' else 'reversed'), dict(r, shr_flag=False),
             dict(r, djnz='test')]
    if r['signed']:
        wrong.append(dict(r, signed=False))
    return wrong


def operand(rng, regs, m, literal_share=0.5):
    return rng.randint(1, m - 1) if rng.random() < literal_share else rng.choice(regs)


def ops(rng, regs, m, count, targets=None, allowed=('ADD', 'SUB', 'MUL', 'SHR'), units=False):
    """Random arithmetic lines; with `units`, MUL only by a literal coprime to every modulus."""
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


def attempt(rng, tier, r):
    """Program with symbolic labels ('@name') for jump targets."""
    m = r['modulus']
    regs = rng.sample(REGISTERS, 3 if tier == 1 else 4)
    data, counter = regs[:-1], regs[-1]
    p = [('SET', x, rng.randint(0, m - 1)) for x in data]
    if tier == 1:
        p += ops(rng, data, m, 2)
        p += [('SET', counter, rng.randint(3, 9)), ('LABEL', 'loop')]
        p += ops(rng, regs, m, 2, data)
        p += [('SHR', rng.choice(data)), ('JF', '@skip')] + ops(rng, regs, m, 1, data) + [('LABEL', 'skip')]
        p += [('OUT', rng.choice(data)), ('DJNZ', counter, '@loop')]
        p += [('OUT', x) for x in rng.sample(data, 2)]
    elif tier == 2:
        wrap = rng.random() < 0.4
        p += [('SET', counter, 0 if wrap else rng.randint(3, 7)), ('LABEL', 'loop')]
        body = ops(rng, regs, m, rng.randint(2, 3), data)
        p += [('REP', rng.randint(3, 25), len(body))] + body
        p += [('JLT', data[0], operand(rng, data[1:], m), '@skip')] + ops(rng, regs, m, 2, data) + [('LABEL', 'skip')]
        if not wrap:
            p += [('OUT', rng.choice(data))]
        p += [('DJNZ', counter, '@loop')]
        p += [('SHR', rng.choice(data)), ('JF', '@odd'), ('OUT', data[0]), ('HALT',), ('LABEL', 'odd')]
        p += [('OUT', x) for x in rng.sample(data, 2)]
    else:
        # mostly permutations of the state (ADD, SUB, MUL by a unit), so the repeated block cycles instead of
        # collapsing to a fixed point
        body = ops(rng, data, m, rng.randint(4, 6), allowed=('ADD', 'SUB', 'ADD', 'SUB', 'MUL', 'SHR'), units=True)
        p += [('REP', rng.randint(10 ** 11, 10 ** 13), len(body))] + body
        p += [('JF', '@carry'), ('OUT', data[0]), ('LABEL', 'carry')]
        p += [('SET', counter, rng.randint(3, 6)), ('LABEL', 'loop')]
        p += [('JLT', data[1], operand(rng, data, m), '@skip')] + ops(rng, regs, m, 1, data) + [('LABEL', 'skip')]
        p += ops(rng, regs, m, 1, data) + [('OUT', rng.choice(data)), ('DJNZ', counter, '@loop')]
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
        'SHR R: R := floor(R / 2). F := whether the bit shifted out was 1 (the old R was odd).',
        f'JF n: jump if F is true; {jump}.',
        f'JLT R x n: jump if R < x; {jump}.'
        + (f' The comparison is signed: a value v of {m // 2} or more counts as v - {m}.' if r['signed'] else ''),
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
        cycles = tier < 3 or min(info.get('cycles', [0])) >= 5
        if 3 <= len(answer) <= 24 and lively and cycles and all(w != answer for w in wrong):
            break
    else:
        raise AssertionError('no machine program met the constraints')
    prompt = (f'A register machine works as follows.\n\n{describe(r)}\n\nProgram:\n\n{listing(program, r)}\n\n'
              'Question: What values does the program output, in order? Answer with the values separated by commas '
              '(for example 3,0,17).')
    return {'kind': 'answer', 'prompt': prompt, 'answer': ','.join(map(str, answer)),
            'machine': {'variant': r, 'program': [list(x) for x in program]}}
