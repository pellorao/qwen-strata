"""count: counting problems that need modelling and an idea; the sizes are far beyond enumeration.

Every level uses n around 10^11-10^13 beads and asks for the count modulo a prime, so no enumeration or step-by-step
dynamic programme over the beads can finish; the solver needs Burnside's lemma over the divisors of n with matrix
powers and a modular inverse.  Level 4: bracelets (rotations and reflections identified) under forbidden
neighbouring colours, whose reflection terms depend on the parity of n and on which colours may sit next to
themselves.  Level 5: necklaces (rotations only) under forbidden neighbours where the number of beads of one colour
must leave a given remainder modulo q (n is a multiple of q).  A rotation with g = gcd(n, s) fixes the words of
period g, whose marked count is (n/g) times that of one period, so each divisor g contributes phi(n/g) times the
closed walks of length g on the (colour, count mod q) states whose count c satisfies (n/g)*c = r (mod q); counting
by "c = r" per period, or ignoring the condition in the symmetry terms, gives a different answer.  Level 6: the same
condition for bracelets, where a reflection fixes words whose mirrored beads count twice: paths on the
(colour, count mod q) states with inner beads of weight 2, ends depending on the parity of n and on self-adjacent
colours.  Every formula is checked against brute force on small n in the tests.  (`tier` in this module is the
level.)
"""
PRIME = 1000000007
COLOURS = ['red', 'green', 'blue', 'white', 'black', 'gold']
MAX_DIVISORS = 200  # of n at levels 5-6 (one matrix power each), which bounds the generation time


# ---------------------------------------------------------------- number theory and matrices modulo a prime

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


# ---------------------------------------------------------------- level 4: bracelets under forbidden neighbours

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


# ---------------------------------------------------------------- levels 5-6: a marked-colour count modulo q
# Matrices over (colour, count mod q) are block-circulant in the count, so they are kept as colour x colour
# matrices whose entries are polynomials in z modulo z^q - 1 (lists of q coefficients modulo p).

def cyc_mul(a, b, q, p):
    out = [0] * q
    for u, x in enumerate(a):
        if x:
            for v, y in enumerate(b):
                if y:
                    out[(u + v) % q] += x * y
    return [x % p for x in out]


def cyc_mat_mul(x, y, q, p):
    size = len(x)
    out = [[[0] * q for _ in range(size)] for _ in range(size)]
    for i in range(size):
        for k in range(size):
            if any(x[i][k]):
                for j in range(size):
                    if any(y[k][j]):
                        out[i][j] = [a + b for a, b in zip(out[i][j], cyc_mul(x[i][k], y[k][j], q, p))]
    return [[[a % p for a in entry] for entry in row] for row in out]


def cyc_mat_pow(x, e, q, p):
    size = len(x)
    out = [[[int(i == j)] + [0] * (q - 1) for j in range(size)] for i in range(size)]
    while e:
        if e & 1:
            out = cyc_mat_mul(out, x, q, p)
        x = cyc_mat_mul(x, x, q, p)
        e >>= 1
    return out


def monomial(degree, q, coefficient=1):
    out = [0] * q
    out[degree % q] = coefficient
    return out


def step_matrix(allowed, marked, q, weight):
    """Appending bead y after x: allowed[x][y], adding `weight` to the count when y is marked."""
    size = len(allowed)
    return [[monomial(weight * (y == marked), q, allowed[x][y]) for y in range(size)] for x in range(size)]


def residue_rotations(n, factors, allowed, marked, q, r, p):
    """Sum over the n rotations of the number of fixed cyclic words whose marked count is r modulo q."""
    size, step = len(allowed), step_matrix(allowed, marked, q, 1)
    squares = [step]
    while 1 << len(squares) <= n:
        squares.append(cyc_mat_mul(squares[-1], squares[-1], q, p))
    total = 0
    for g in divisors(factors):
        power = None
        for bit, square in enumerate(squares):
            if g >> bit & 1:
                power = square if power is None else cyc_mat_mul(power, square, q, p)
        t = n // g  # each period of length g occurs t times
        closed = [sum(power[x][x][c] for x in range(size)) for c in range(q)]
        total += phi(t, factors) * sum(closed[c] for c in range(q) if (t * c - r) % q == 0)
    return total % p


def path_ends(start, matrix, end, q, p):
    """sum over x, y of start[x] * matrix[x][y] * end[y] (each a polynomial modulo z^q - 1)."""
    out = [0] * q
    for x in range(len(start)):
        for y in range(len(end)):
            out = [a + b for a, b in zip(out, cyc_mul(cyc_mul(start[x], matrix[x][y], q, p), end[y], q, p))]
    return [a % p for a in out]


def residue_reflections(n, allowed, marked, q, r, p):
    """Sum over the n reflections of the number of fixed cyclic words whose marked count is r modulo q: the beads
    on the axis count once, every other bead stands for itself and its mirror image and counts twice."""
    size = len(allowed)
    single = [monomial(x == marked, q) for x in range(size)]
    double_loop = [monomial(2 * (x == marked), q, allowed[x][x]) for x in range(size)]
    loop = [monomial(0, q, allowed[x][x]) for x in range(size)]
    one = [monomial(0, q)] * size
    doubled = step_matrix(allowed, marked, q, 2)
    if n % 2:  # bead w_0 on the axis, w_1..w_m doubled, w_m next to its own mirror image
        total = n * path_ends(single, cyc_mat_pow(doubled, (n - 1) // 2, q, p), loop, q, p)[r]
    else:
        half = n // 2
        inner = cyc_mat_pow(doubled, half - 1, q, p)
        # axes through beads w_0 and w_half: w_1..w_{half-1} doubled, the last step adds w_half once
        last = cyc_mat_mul(inner, step_matrix(allowed, marked, q, 1), q, p)
        through_beads = path_ends(single, last, one, q, p)[r]
        # axes through two edges: w_0..w_{half-1} doubled, both ends next to their own mirror images
        through_edges = path_ends(double_loop, inner, loop, q, p)[r]
        total = half * (through_beads + through_edges)
    return total % p


def residue_necklaces(n, factors, allowed, marked, q, r, p=PRIME):
    """Necklaces of n beads (rotations identified) under allowed neighbours with marked count = r (mod q), mod p."""
    return residue_rotations(n, factors, allowed, marked, q, r, p) * pow(n, -1, p) % p


def residue_bracelets(n, factors, allowed, marked, q, r, p=PRIME):
    """The same with reflections identified too."""
    total = residue_rotations(n, factors, allowed, marked, q, r, p) + residue_reflections(n, allowed, marked, q, r, p)
    return total % p * pow(2 * n, -1, p) % p


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


def mixed_loops(rng, size):
    """An adjacency where some colour may and some may not touch itself, so both kinds of reflection term matter."""
    for _ in range(100):
        colours = rng.sample(COLOURS, size)
        allowed, words = adjacency(rng, colours)
        if any(allowed[i][i] for i in range(size)) and not all(allowed[i][i] for i in range(size)):
            return colours, allowed, words
    raise AssertionError('no adjacency with mixed self-neighbours')


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


def huge_bracelet_item(rng):
    colours, allowed, words = mixed_loops(rng, rng.choice([3, 4]))
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


def residue_item(rng, tier):
    size = rng.choice([3, 4])
    if tier >= 6:
        colours, allowed, words = mixed_loops(rng, size)
    else:
        colours = rng.sample(COLOURS, size)
        allowed, words = adjacency(rng, colours)
    marked = rng.choice([x for x in range(size) if any(allowed[x])])
    q = rng.choice([3, 4, 5])
    r = rng.randrange(1, q)
    n, factors = huge_n(rng)
    while n % q or len(divisors(factors)) > MAX_DIVISORS:
        n, factors = huge_n(rng)
    answer = (residue_necklaces if tier == 5 else residue_bracelets)(n, factors, allowed, marked, q, r)
    thing = 'necklace' if tier == 5 else 'bracelet'
    same = ('Two necklaces are the same if one can be rotated into the other (turning it over does NOT give the '
            'same necklace).' if tier == 5 else
            'Two bracelets are the same if one can be rotated into the other, or turned over and then rotated into '
            'the other.')
    prompt = (f'A {thing} is a closed loop of n = {n} beads; each bead is {", ".join(colours[:-1])} or '
              f'{colours[-1]}. Around the whole loop (including between the last and the first bead), '
              f'{" and ".join(words)}. The number of {colours[marked]} beads leaves remainder {r} when divided by '
              f'{q}. {same}\n\nQuestion: How many different {thing}s are there, modulo {PRIME}? Answer with an '
              f'integer from 0 to {PRIME - 1}.')
    return {'kind': 'answer', 'prompt': prompt, 'answer': str(answer),
            'count': {'template': f'residue-{thing}s', 'n': n, 'factors': {str(k): v for k, v in factors.items()},
                      'allowed': allowed, 'colours': colours, 'marked': marked, 'q': q, 'r': r}}


def item(rng, tier):
    return huge_bracelet_item(rng) if tier <= 4 else residue_item(rng, tier)
