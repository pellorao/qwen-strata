"""count: counting problems that need modelling and an idea; the sizes are far beyond enumeration.

Tier 1: necklaces (rotations identified) with forbidden neighbouring colours and an exact count of one colour
(weighted Burnside).  Tier 2: the same as bracelets (reflections identified too), where the reflection terms
depend on the parity of n.  Tier 3: n around 10^11-10^13, answer modulo a prime: necklaces under forbidden
neighbours or forbidden runs of three (Burnside over divisors with matrix powers and a modular inverse), or linear
strings with a parity condition (matrix power).  Level 4: the same huge sizes for bracelets (reflections identified
too) under forbidden neighbours, whose reflection terms depend on the parity of n and on which colours may sit next
to themselves.  Every formula is checked against brute force on small n in the tests.  (`tier` in this module is the
level.)
"""
from math import gcd

PRIME = 1000000007
COLOURS = ['red', 'green', 'blue', 'white', 'black', 'gold']


# ---------------------------------------------------------------- polynomial matrices (exact, degree-truncated)

def poly_mul(p, q, cap):
    out = [0] * (cap + 1)
    for i, a in enumerate(p):
        if a:
            for j, b in enumerate(q[:cap + 1 - i]):
                out[i + j] += a * b
    return out


def poly_add(p, q):
    return [a + b for a, b in zip(p, q)]


def mat_mul(x, y, cap):
    size = len(x)
    out = [[[0] * (cap + 1) for _ in range(size)] for _ in range(size)]
    for i in range(size):
        for k in range(size):
            if any(x[i][k]):
                for j in range(size):
                    out[i][j] = poly_add(out[i][j], poly_mul(x[i][k], y[k][j], cap))
    return out


def weighted(allowed, size, marked, cap, factor=1):
    """W[x][y] = allowed(x, y) * z^(factor * [y is the marked colour])."""
    out = []
    for x in range(size):
        row = []
        for y in range(size):
            p = [0] * (cap + 1)
            degree = factor * (y == marked)
            if allowed[x][y] and degree <= cap:
                p[degree] = 1
            row.append(p)
        out.append(row)
    return out


def coefficient(p, k):
    return p[k] if 0 <= k < len(p) else 0


def rotation_sum(n, allowed, marked, k):
    """Sum over the n rotations of the number of cyclic words fixed by it with exactly k marked letters."""
    size, total = len(allowed), 0
    w = weighted(allowed, size, marked, k)
    power, powers = w, {1: w}
    for g in range(2, n + 1):
        power = mat_mul(power, w, k)
        powers[g] = power
    for s in range(n):
        g = gcd(n, s) if s else n
        if (k * g) % n:
            continue
        trace = [0] * (k + 1)
        for i in range(size):
            trace = poly_add(trace, powers[g][i][i])
        total += coefficient(trace, k * g // n)
    return total


def path_sum(length, allowed, marked, k, ends):
    """Paths w_0..w_length: w_0 weighted by `ends[0]`, inner letters by 2, the last by `ends[1]`; a
    `self` end needs that letter to be allowed next to itself.  Returns the coefficient of z^k."""
    size = len(allowed)
    first, last = ends
    vector = [[0] * (k + 1) for _ in range(size)]
    for x in range(size):
        degree = first['factor'] * (x == marked)
        if degree <= k and (not first['self'] or allowed[x][x]):
            vector[x][degree] = 1
    for step in range(1, length + 1):
        factor = last['factor'] if step == length else 2
        nxt = [[0] * (k + 1) for _ in range(size)]
        for x in range(size):
            for y in range(size):
                if allowed[x][y]:
                    shifted = [0] * (factor * (y == marked)) + vector[x]
                    nxt[y] = poly_add(nxt[y], shifted[:k + 1])
        vector = nxt
    return sum(coefficient(vector[y], k) for y in range(size) if not last['self'] or allowed[y][y])


def reflection_sum(n, allowed, marked, k):
    """Sum over the n reflections of the cycle of the number of fixed cyclic words with exactly k marked letters."""
    if n == 1:
        return sum(1 for x in range(len(allowed)) if allowed[x][x] and (x == marked) == (k == 1) and k <= 1)
    if n == 2:  # axes through both beads (1) and through both edges (1)
        size = len(allowed)
        vertex = sum(allowed[x][y] for x in range(size) for y in range(size)
                     if (x == marked) + (y == marked) == k)
        edge = sum(allowed[x][x] for x in range(size) if 2 * (x == marked) == k)
        return vertex + edge
    if n % 2:
        m = (n - 1) // 2
        return n * path_sum(m, allowed, marked, k, ({'factor': 1, 'self': False}, {'factor': 2, 'self': True}))
    half = n // 2
    vertex = path_sum(half, allowed, marked, k, ({'factor': 1, 'self': False}, {'factor': 1, 'self': False}))
    edge = path_sum(half - 1, allowed, marked, k, ({'factor': 2, 'self': True}, {'factor': 2, 'self': True}))
    return half * vertex + half * edge


def necklaces(n, allowed, marked, k):
    total = rotation_sum(n, allowed, marked, k)
    assert total % n == 0
    return total // n


def bracelets(n, allowed, marked, k):
    total = rotation_sum(n, allowed, marked, k) + reflection_sum(n, allowed, marked, k)
    assert total % (2 * n) == 0
    return total // (2 * n)


# ---------------------------------------------------------------- huge n modulo a prime

def mod_mat_mul(x, y, p=PRIME):
    size = len(x)
    return [[sum(x[i][k] * y[k][j] for k in range(size)) % p for j in range(size)] for i in range(size)]


def mod_mat_pow(m, e, p=PRIME):
    size = len(m)
    out = [[int(i == j) for j in range(size)] for i in range(size)]
    while e:
        if e & 1:
            out = mod_mat_mul(out, m, p)
        m = mod_mat_mul(m, m, p)
        e >>= 1
    return out


def divisors(factors):
    out = [1]
    for prime, power in factors.items():
        out = [d * prime ** e for d in out for e in range(power + 1)]
    return sorted(out)


def phi(d, factors):
    out = d
    for prime in factors:
        if d % prime == 0:
            out = out // prime * (prime - 1)
    return out


def transfer(letters, forbidden):
    """States are the last two letters; a step appends a letter unless the new window ends with a forbidden word
    (of length 2 or 3)."""
    states = [a + b for a in letters for b in letters]
    index = {s: i for i, s in enumerate(states)}
    m = [[0] * len(states) for _ in states]
    for s in states:
        for c in letters:
            window = s + c
            if not any(window.endswith(f) for f in forbidden):
                m[index[s]][index[s[1] + c]] = 1
    return m


def huge_necklaces(n, factors, letters, forbidden, p=PRIME):
    """Necklaces of length n (rotations identified) with no forbidden word in any cyclic window, modulo p."""
    m = transfer(letters, forbidden)
    total = 0
    for d in divisors(factors):
        power = mod_mat_pow(m, d, p)
        total += phi(n // d, factors) * sum(power[i][i] for i in range(len(m)))
    return total % p * pow(n, -1, p) % p


def huge_linear(n, letters, forbidden, parity_letter, p=PRIME):
    """Linear words of length n >= 2 with no forbidden window and an even number of `parity_letter`, modulo p."""
    m = transfer(letters, forbidden)
    states = [a + b for a in letters for b in letters]
    size = len(states)
    doubled = [[0] * (2 * size) for _ in range(2 * size)]
    for i in range(size):
        for j in range(size):
            if m[i][j]:
                flip = states[j][1] == parity_letter
                for parity in (0, 1):
                    doubled[parity * size + i][(parity ^ flip) * size + j] = 1
    start = [0] * (2 * size)
    for i, s in enumerate(states):
        if not any(f == s for f in forbidden):
            start[(s.count(parity_letter) % 2) * size + i] += 1
    power = mod_mat_pow(doubled, n - 2, p)
    return sum(start[i] * power[i][j] for i in range(2 * size) for j in range(size)) % p


def huge_bracelets(n, factors, allowed, p=PRIME):
    """Bracelets of n beads (rotations and reflections identified) where neighbours x, y need allowed[x][y]
    (symmetric), modulo p: Burnside over the dihedral group."""
    size = len(allowed)
    rotations = 0
    for d in divisors(factors):
        power = mod_mat_pow(allowed, d, p)
        rotations += phi(n // d, factors) * sum(power[i][i] for i in range(size))
    loops = [allowed[i][i] for i in range(size)]
    if n % 2:  # each axis through a bead and the opposite edge, whose two beads are mirror images
        power = mod_mat_pow(allowed, (n - 1) // 2, p)
        reflections = n * sum(power[i][j] * loops[j] for i in range(size) for j in range(size))
    else:  # n/2 axes through two beads, n/2 through two edges
        through_beads = sum(sum(row) for row in mod_mat_pow(allowed, n // 2, p))
        power = mod_mat_pow(allowed, n // 2 - 1, p)
        through_edges = sum(loops[i] * power[i][j] * loops[j] for i in range(size) for j in range(size))
        reflections = n // 2 * (through_beads + through_edges)
    return (rotations + reflections) % p * pow(2 * n, -1, p) % p


def huge_bracelet_item(rng):
    for _ in range(100):
        size = rng.choice([3, 4])
        colours = rng.sample(COLOURS, size)
        allowed, words = adjacency(rng, colours)
        if any(allowed[i][i] for i in range(size)) and not all(allowed[i][i] for i in range(size)):
            break  # some colour may and some may not touch itself: both kinds of reflection term matter
    n, factors = huge_n(rng)
    answer = huge_bracelets(n, factors, allowed)
    prompt = (f'A bracelet is a closed loop of n = {n} beads; each bead is {", ".join(colours[:-1])} or '
              f'{colours[-1]}. Around the whole loop (including between the last and the first bead), '
              f'{" and ".join(words)}. Two bracelets are the same if one can be rotated into the other, or turned '
              f'over and then rotated into the other.\n\nQuestion: How many different bracelets are there, modulo '
              f'{PRIME}? Answer with an integer from 0 to {PRIME - 1}.')
    return {'kind': 'answer', 'prompt': prompt, 'answer': str(answer),
            'count': {'template': 'bracelets', 'n': n, 'factors': {str(k): v for k, v in factors.items()},
                      'allowed': allowed, 'colours': colours}}


# ---------------------------------------------------------------- items

def adjacency(rng, colours):
    """Symmetric allowed-neighbour matrix with one or two forbidden colour pairs (possibly a colour with itself)."""
    size = len(colours)
    pairs = [(x, y) for x in range(size) for y in range(x, size)]
    banned = rng.sample(pairs, rng.choice([1, 2]))
    allowed = [[1] * size for _ in range(size)]
    for x, y in banned:
        allowed[x][y] = allowed[y][x] = 0
    words = [(f'two {colours[x]} beads are never next to each other' if x == y else
              f'a {colours[x]} bead is never next to a {colours[y]} bead') for x, y in banned]
    return allowed, words


def small_item(rng, tier):
    for _ in range(200):
        size = rng.choice([3, 4])
        n = rng.randint(24, 40) if size == 3 else rng.randint(18, 28)
        colours = rng.sample(COLOURS, size)
        allowed, words = adjacency(rng, colours)
        marked = rng.randrange(size)
        k = rng.randint(n // 5, n // 2)
        answer = (necklaces if tier == 1 else bracelets)(n, allowed, marked, k)
        if answer > 10 ** 4:
            break
    same = ('Two necklaces are the same if one can be rotated into the other (turning it over does NOT give the '
            'same necklace).' if tier == 1 else
            'Two bracelets are the same if one can be rotated into the other, or turned over and then rotated into '
            'the other.')
    thing = 'necklace' if tier == 1 else 'bracelet'
    prompt = (f'A {thing} is a closed loop of {n} beads; each bead is {", ".join(colours[:-1])} or {colours[-1]}. '
              f'Around the whole loop (including between the last and the first bead), {" and ".join(words)}. '
              f'Exactly {k} beads are {colours[marked]}. {same}\n\n'
              f'Question: How many different {thing}s are there? Answer with the exact integer.')
    return {'kind': 'answer', 'prompt': prompt, 'answer': str(answer),
            'count': {'n': n, 'allowed': allowed, 'marked': marked, 'k': k, 'symmetry': thing}}


def huge_n(rng):
    while True:
        factors = {}
        for prime in rng.sample([2, 3, 5, 7, 11, 13, 17, 19, 23], rng.randint(3, 5)):
            factors[prime] = rng.randint(1, 6)
        n = 1
        for prime, power in factors.items():
            n *= prime ** power
        if 10 ** 11 <= n <= 10 ** 13 and n % PRIME:
            return n, factors


def huge_item(rng):
    letters = ''.join(rng.sample('abcdeuxyz', 3))
    template = rng.choice(['pairs', 'triples', 'linear'])
    while True:
        if template == 'pairs':
            forbidden = sorted({''.join(rng.sample(letters, 2)) for _ in range(2)} | {rng.choice(letters) * 2})
        else:
            forbidden = sorted({''.join(rng.choice(letters) for _ in range(3)) for _ in range(rng.randint(2, 3))})
        if len(set(forbidden)) >= 2:
            break
    n, factors = huge_n(rng)
    listed = ', '.join(f'"{f}"' for f in forbidden)
    if template == 'linear':
        parity = rng.choice(letters)
        answer = huge_linear(n, letters, forbidden, parity)
        text = (f'Count the strings of length n = {n} over the letters {", ".join(letters)} that contain none of '
                f'{listed} as a contiguous substring and contain the letter {parity} an even number of times '
                '(zero counts as even).')
    else:
        answer = huge_necklaces(n, factors, letters, forbidden)
        text = (f'A circular word of length n = {n} over the letters {", ".join(letters)} is read around a circle, '
                f'so it has n windows of each length, including the windows that wrap from the end to the start. '
                f'Count the circular words in which none of {listed} occurs in any window. Two circular words are '
                'the same if one is a rotation of the other (reversal does NOT make two words the same).')
    return {'kind': 'answer', 'answer': str(answer),
            'prompt': f'{text}\n\nQuestion: What is the count modulo {PRIME}? Answer with an integer from 0 to '
                      f'{PRIME - 1}.',
            'count': {'template': template, 'n': n, 'factors': {str(k): v for k, v in factors.items()},
                      'letters': letters, 'forbidden': forbidden,
                      **({'parity': parity} if template == 'linear' else {})}}


def item(rng, tier):
    return small_item(rng, tier) if tier <= 2 else huge_item(rng) if tier == 3 else huge_bracelet_item(rng)
