"""logic: a row of houses described by natural-language clues; deduce the whole arrangement.

With a shell, any size of puzzle falls to a backtracking search, so the difficulty is in turning each sentence into
the right constraint.  Clues use indirect references ("the person directly to the left of the tea drinker owns the
cat"), several phrasings of one relation in both directions, distances counted as houses in between, "somewhere
between" in either order, and connectives whose meaning the prompt defines ("A unless B", "A only if B", "either A or
B, but not both", "at least one of").  Every such clue is a trap: it has a listed misreading (direction flipped,
"directly" for "somewhere", distance for houses in between, the order of "between" taken as written, "if" read as
"if and only if", "only if" reversed, "unless" or "at least one" read as exclusive), and the hidden
arrangement violates that misreading, so a misread clue can never give the right answer; the generator also requires
a number of traps whose misreading gives a different single arrangement (a silent wrong answer rather than a puzzle
without a solution).  Clues are added until exactly one arrangement fits, then every clue uniqueness does not need is
dropped.  Tier 1: 5 houses, 4 attributes.  Tier 2: 6 houses, 4 attributes.  Tier 3: 6 houses, 5 attributes, more
connectives and traps.
"""
CATEGORIES = {
    'name': ['Ava', 'Ben', 'Cleo', 'Dev', 'Eli', 'Fern', 'Gus', 'Hana', 'Ivo', 'Jun'],
    'pet': ['cat', 'dog', 'ferret', 'parrot', 'tortoise', 'rabbit', 'goldfish'],
    'drink': ['tea', 'coffee', 'cocoa', 'lemonade', 'milk', 'cider'],
    'job': ['baker', 'nurse', 'pilot', 'tailor', 'welder', 'chemist'],
    'colour': ['red', 'green', 'blue', 'yellow', 'white', 'grey'],
    'music': ['cello', 'drums', 'flute', 'harp', 'piano', 'violin'],
}
SHAPE = {1: (5, 4), 2: (6, 4), 3: (6, 5)}
KINDS = {1: ['same', 'same', 'not-same', 'at', 'next', 'end', 'adjacent', 'adjacent', 'left', 'gap', 'between',
             'if', 'either'],
         2: ['same', 'same', 'not-same', 'next', 'end', 'adjacent', 'adjacent', 'left', 'gap', 'gap', 'between',
             'offset', 'if', 'onlyif', 'unless', 'either', 'or'],
         3: ['same', 'same', 'not-same', 'next', 'adjacent', 'adjacent', 'left', 'gap', 'between', 'offset', 'if',
             'onlyif', 'onlyif', 'unless', 'unless', 'either', 'or']}
SILENT = {1: 1, 2: 2, 3: 2}  # traps whose misreading gives a different single arrangement
CONNECTIVES = {1: 1, 2: 2, 3: 3}  # clues with if / only if / unless / either-or / at least one that must remain
LABEL = {'name': 'names', 'pet': 'pets', 'drink': 'drinks', 'job': 'jobs', 'colour': 'colours',
         'music': 'instruments'}
WORDS = {2: 'two', 3: 'three', 4: 'four'}


def phrase(cat, value):
    return {'name': value, 'pet': f'the {value} owner', 'drink': f'the person who drinks {value}',
            'job': f'the {value}', 'colour': f'the person in the {value} house',
            'music': f'the {value} player'}[cat]


def predicate(cat, value, negated=False):
    if negated:
        return {'name': f'is not {value}', 'pet': f'does not own the {value}', 'drink': f'does not drink {value}',
                'job': f'is not the {value}', 'colour': f'does not live in the {value} house',
                'music': f'does not play the {value}'}[cat]
    return {'name': f'is {value}', 'pet': f'owns the {value}', 'drink': f'drinks {value}', 'job': f'is the {value}',
            'colour': f'lives in the {value} house', 'music': f'plays the {value}'}[cat]


def capital(text):
    return text[0].upper() + text[1:]


# ---------------------------------------------------------------- atoms: (kind, args); truth over positions

def truth(atom, where):
    """`where(cat, value)` -> 0-based house."""
    kind, a = atom
    if kind == 'same':
        return where(*a[0]) == where(*a[1])
    if kind == 'at':
        return where(*a[0]) == a[1]
    if kind == 'left':
        return where(*a[0]) < where(*a[1])
    if kind == 'adjacent':  # a[0] directly to the left of a[1]
        return where(*a[0]) + 1 == where(*a[1])
    if kind == 'next':
        return abs(where(*a[0]) - where(*a[1])) == 1
    if kind == 'gap':  # a[2] = distance in house numbers
        return abs(where(*a[0]) - where(*a[1])) == a[2]
    if kind == 'offset':  # a[0] lives a[2] houses to the right of a[1] (negative: to the left)
        return where(*a[0]) == where(*a[1]) + a[2]
    if kind == 'between':  # strictly between, either order
        x, y, z = where(*a[0]), where(*a[1]), where(*a[2])
        return min(y, z) < x < max(y, z)
    if kind == 'ordered':  # misreading of 'between': in the order written
        return where(*a[1]) < where(*a[0]) < where(*a[2])
    if kind == 'end':
        return where(*a[0]) in (0, a[1] - 1)
    raise ValueError(kind)


def text(atom, negated=False, style=0):
    kind, a = atom
    x = phrase(*a[0])
    lives = 'does not live' if negated else 'lives'
    if kind == 'same':
        return f'{x} {predicate(*a[1], negated)}'
    if kind == 'at':
        return f'{x} {lives} in house {a[1] + 1}'
    if kind == 'left':
        if style == 1 and not negated:
            return f'{phrase(*a[1])} lives in a higher-numbered house than {x}'
        return f'{x} {lives} somewhere to the left of {phrase(*a[1])}'
    if kind == 'adjacent':
        y = phrase(*a[1])
        if negated or style == 0:
            return f'{x} {lives} directly to the left of {y}'
        if style == 1:
            return f'{y} lives directly to the right of {x}'
        if style == 2:
            return f'the person directly to the left of {y} {predicate(*a[0])}'
        return f'the right-hand neighbour of {x} {predicate(*a[1])}'
    if kind == 'next':
        return f'{x} and {phrase(*a[1])} are {"not " if negated else ""}next-door neighbours'
    if kind == 'gap':
        between = a[2] - 1
        houses = 'is exactly one house' if between == 1 else f'are exactly {WORDS[between]} houses'
        return (f'it is not true that there {houses} between {x} and {phrase(*a[1])}' if negated else
                f'there {houses} between {x} and {phrase(*a[1])}')
    if kind == 'offset':
        side = 'right' if a[2] > 0 else 'left'
        if style == 1:
            return (f'the person who lives exactly {WORDS[abs(a[2])]} houses to the {side} of {phrase(*a[1])} '
                    f'{predicate(*a[0])}')
        return f'{x} {lives} exactly {WORDS[abs(a[2])]} houses to the {side} of {phrase(*a[1])}'
    if kind == 'between':
        return f'{x} {lives} somewhere between {phrase(*a[1])} and {phrase(*a[2])}'
    if kind == 'end':
        return f'{x} lives {"in neither end house" if negated else "in one of the two end houses"}'
    raise ValueError(kind)


# ---------------------------------------------------------------- clues
# ('atom', atom, negated, style) | (connective, part, part) with parts ('atom', atom, negated, 0)
# connectives: if (A -> B), onlyif ("A only if B": A -> B), unless ("A unless B": A or B), either (exactly one),
# or (at least one); misreadings add iff, converse (B -> A) and xor.

def holds(clue, where):
    kind = clue[0]
    if kind == 'atom':
        return truth(clue[1], where) != clue[2]
    a, b = holds(clue[1], where), holds(clue[2], where)
    if kind in ('if', 'onlyif'):
        return not a or b
    if kind == 'converse':
        return not b or a
    if kind == 'iff':
        return a == b
    if kind in ('unless', 'or'):
        return a or b
    if kind in ('either', 'xor'):
        return a != b
    raise ValueError(kind)


def sentence(clue):
    kind = clue[0]
    if kind == 'atom':
        return capital(text(clue[1], clue[2], clue[3])) + '.'
    a, b = text(clue[1][1], clue[1][2]), text(clue[2][1], clue[2][2])
    return capital({'if': f'if {a}, then {b}.', 'onlyif': f'{a} only if {b}.', 'unless': f'{a}, unless {b}.',
                    'either': f'either {a} or {b}, but not both.',
                    'or': f'at least one of these is true: {a}; {b}.'}[kind])


def misread(clue):
    """The listed misreading of a clue, or None for a clue with no trap."""
    kind = clue[0]
    if kind == 'either':
        return None  # dropping "but not both" never excludes the hidden arrangement, so it is no trap
    if kind != 'atom':
        return {'if': 'iff', 'onlyif': 'converse', 'unless': 'xor', 'or': 'xor'}[kind], clue[1], clue[2]
    (akind, a), negated, style = clue[1], clue[2], clue[3]
    wrong = {'adjacent': lambda: ('adjacent', (a[1], a[0])),  # direction flipped
             'left': lambda: ('adjacent', a),  # "somewhere" read as "directly"
             'gap': lambda: ('gap', (a[0], a[1], a[2] - 1)),  # houses in between read as the distance
             'offset': lambda: ('offset', (a[0], a[1], -a[2])),  # direction flipped
             'between': lambda: ('ordered', a)}.get(akind)  # "between y and z" read as in that order
    return None if wrong is None else ('atom', wrong(), negated, style)


def refs(clue):
    if clue[0] == 'atom':
        return {x for x in clue[1][1] if isinstance(x, tuple)}
    return refs(clue[1]) | refs(clue[2])


# ---------------------------------------------------------------- search

def solve(n, values, clues, limit=2):
    """Up to `limit` arrangements ({cat: tuple of houses in the order of values[cat]}) satisfying every clue:
    backtracking over (category, value) -> house with forward checking."""
    names = [(c, v) for c in values for v in values[c]]
    on = {x: [] for x in names}
    clue_refs = [refs(c) for c in clues]
    for k, rs in enumerate(clue_refs):
        for x in rs:
            on[x].append(k)
    found, assign = [], {}

    def where(cat, value):
        return assign[(cat, value)]

    def filtered(domains, var):
        """Domains after assigning `var`, or None on a wipe-out."""
        p = assign[var]
        for v in values[var[0]]:
            other = (var[0], v)
            if other != var and other not in assign:
                if p in domains[other]:
                    domains[other] = domains[other] - {p}
                    if not domains[other]:
                        return None
        for k in on[var]:
            open_refs = [x for x in clue_refs[k] if x not in assign]
            if not open_refs:
                if not holds(clues[k], where):
                    return None
            elif len(open_refs) == 1:
                u = open_refs[0]
                keep = set()
                for q in domains[u]:
                    assign[u] = q
                    if holds(clues[k], where):
                        keep.add(q)
                del assign[u]
                if not keep:
                    return None
                domains[u] = keep
        return domains

    def search(domains):
        if len(found) >= limit:
            return
        free = [x for x in names if x not in assign]
        if not free:
            found.append({c: tuple(assign[(c, v)] for v in values[c]) for c in values})
            return
        var = min(free, key=lambda x: (len(domains[x]), x))
        for p in sorted(domains[var]):
            assign[var] = p
            nxt = filtered({**domains, var: {p}}, var)
            if nxt is not None:
                search(nxt)
            del assign[var]
            if len(found) >= limit:
                return

    domains = {x: set(range(n)) for x in names}
    for k, rs in enumerate(clue_refs):  # clues about one value only
        if len(rs) == 1:
            (u,) = rs
            keep = set()
            for q in domains[u]:
                assign[u] = q
                if holds(clues[k], where):
                    keep.add(q)
            del assign[u]
            domains[u] = keep
    search(domains)
    return found


def count(n, values, clues, limit=2):
    return len(solve(n, values, clues, limit))


# ---------------------------------------------------------------- generation

def ref(rng, values, exclude=()):
    cat = rng.choice([c for c in values if c not in exclude])
    return (cat, rng.choice(values[cat]))


def random_atom(rng, n, values, kind):
    x = ref(rng, values)
    if kind in ('same', 'not-same'):
        return ('same', (x, ref(rng, values, exclude=(x[0],))))
    if kind == 'at':
        return ('at', (x, rng.randrange(n)))
    if kind == 'end':
        return ('end', (x, n))
    y = ref(rng, values)
    while y == x:
        y = ref(rng, values)
    if kind == 'gap':
        return ('gap', (x, y, rng.randint(2, min(4, n - 1))))
    if kind == 'offset':
        return ('offset', (x, y, rng.choice([2, 3, -2, -3])))
    if kind == 'between':
        z = ref(rng, values)
        while z in (x, y):
            z = ref(rng, values)
        return ('between', (x, y, z))
    return (kind, (x, y))


def random_clue(rng, n, values, kind, where):
    """A clue of `kind` that is true of the hidden arrangement and whose misreading (if any) is false of it, or
    None."""
    if kind in ('if', 'onlyif', 'unless', 'either', 'or'):
        simple = ['same', 'not-same', 'next', 'left', 'adjacent', 'end', 'at']
        parts = []
        for _ in range(2):
            kind_ = rng.choice(simple)
            parts.append(('atom', random_atom(rng, n, values, kind_.replace('not-', '')), kind_.startswith('not-')
                          or rng.random() < 0.2, 0))
        clue = (kind, *parts)
    else:
        atom = random_atom(rng, n, values, kind.replace('not-', ''))
        style = rng.randrange({'adjacent': 4, 'left': 2, 'offset': 2}.get(atom[0], 1))
        clue = ('atom', atom, kind.startswith('not-'), style)
    wrong = misread(clue)
    if not holds(clue, where) or (wrong is not None and holds(wrong, where)):
        return None
    return clue


def answer_of(values, solution):
    return [v for c in values for v in sorted(values[c], key=lambda v: solution[c][values[c].index(v)])]


def traps(n, values, clues, hidden):
    """Per clue with a misreading: 'none', 'multiple' or 'other' (a different single arrangement) when the clue is
    misread and the others are read right."""
    out = {}
    for k, clue in enumerate(clues):
        wrong = misread(clue)
        if wrong is None:
            continue
        found = solve(n, values, clues[:k] + [wrong] + clues[k + 1:])
        out[k] = 'none' if not found else 'multiple' if len(found) > 1 else \
            'same' if found[0] == hidden else 'other'
    return out


def puzzle(rng, tier):
    n, width = SHAPE[tier]
    cats = ['name'] + rng.sample([c for c in CATEGORIES if c != 'name'], width - 1)
    values = {c: rng.sample(CATEGORIES[c], n) for c in cats}
    hidden = {c: tuple(rng.sample(range(n), n)) for c in cats}

    def where(cat, value):
        return hidden[cat][values[cat].index(value)]

    clues, seen = [], set()
    for _ in range(3000):
        clue = random_clue(rng, n, values, rng.choice(KINDS[tier]), where)
        if clue is None or sentence(clue) in seen:
            continue
        seen.add(sentence(clue))
        clues.append(clue)
        if len(clues) >= 2 * n and count(n, values, clues) == 1:
            break
    else:
        return None
    atoms = [c for c in clues if c[0] == 'atom']
    compounds = [c for c in clues if c[0] != 'atom']
    # drop every clue uniqueness does not need, plain clues first so that connectives tend to stay
    for clue in rng.sample(atoms, len(atoms)) + rng.sample(compounds, len(compounds)):
        rest = [x for x in clues if x is not clue]
        if count(n, values, rest) == 1:
            clues = rest
    return n, values, hidden, clues


def item(rng, tier):
    for _ in range(80):
        made = puzzle(rng, tier)
        if not made:
            continue
        n, values, hidden, clues = made
        if sum(c[0] != 'atom' for c in clues) < CONNECTIVES[tier]:
            continue
        found = traps(n, values, clues, hidden)
        if sum(v == 'other' for v in found.values()) >= SILENT[tier]:
            break
    else:
        raise AssertionError('no logic puzzle met the constraints')
    order = list(range(len(clues)))
    rng.shuffle(order)
    clues = [clues[k] for k in order]
    found = {order.index(k): v for k, v in found.items()}
    lists = '\n'.join(f'- {LABEL[c]}: {", ".join(sorted(values[c]))}' for c in values if c != 'name')
    asked = ', then '.join(f'the {LABEL[c]} in houses 1 to {n}' for c in values)
    prompt = (f'{n} houses stand in a row, numbered 1 to {n} from left to right. One person lives in each house: '
              f'{", ".join(sorted(values["name"]))}. Each person has exactly one item from each list below, and no '
              f'two people share an item:\n\n{lists}\n\nHow to read the clues:\n'
              '- "Left" means a lower house number and "right" a higher one. "Directly to the left of" means in the '
              'house numbered one lower; "somewhere to the left of" means in any lower-numbered house. "Next-door '
              'neighbours" live in houses whose numbers differ by one; the "right-hand neighbour" of someone lives '
              'directly to their right.\n'
              '- "There are exactly k houses between X and Y" means k other houses stand between their two houses. '
              '"X lives exactly k houses to the right of Y" means X\'s house number is Y\'s plus k.\n'
              '- "X lives somewhere between Y and Z" means X\'s house number is strictly between those of Y and Z, '
              'whichever of Y and Z is further left.\n'
              '- "If A, then B" says only that B is true whenever A is true. "A only if B" means: if A is true, '
              'then B is true. "A, unless B" means: if B is false, then A is true (when B is true, A may be true or '
              'false). "Either A or B, but not both" means exactly one of them is true; "at least one of these is '
              'true" allows both.\n'
              '- A person, item or house mentioned in a clue may be the same as one mentioned in another clue, '
              'unless the clues force them apart.\n\nClues:\n\n'
              + '\n'.join(f'{k}. {sentence(c)}' for k, c in enumerate(clues, 1))
              + f'\n\nExactly one arrangement satisfies all the clues.\n\nQuestion: What is the whole arrangement? '
              f'Answer with {n * len(values)} words separated by commas: {asked}, each list in house order (the '
              f'format, not the content, of the start of an answer: {",".join(sorted(values["name"]))},'
              f'{",".join(sorted(values[list(values)[1]])[:2])},...).')
    return {'kind': 'answer', 'prompt': prompt, 'answer': ','.join(answer_of(values, hidden)).lower(),
            'logic': {'values': values, 'hidden': {c: list(p) for c, p in hidden.items()}, 'clues': len(clues),
                      'traps': {str(k + 1): v for k, v in sorted(found.items())}}}
