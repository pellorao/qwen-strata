"""logic: a row of houses described by natural-language clues; deduce who lives where (multi-step constraint reasoning).

Every clue is a sentence about people, pets, drinks and so on, never a formula; the solver has to turn each into a
constraint and chain the deductions.  The generator draws a hidden arrangement, adds true clues until a complete
search finds exactly one arrangement, then drops every clue the uniqueness does not need, so no clue is redundant.
Tier 1: 4 houses, 3 attributes, direct clues.  Tier 2: 5 houses, 3 attributes, adds negations, distances, "either
... or" and the row ends.  Tier 3: 5 houses, 4 attributes, adds "exactly one of these is true" and "if ... then"
clues, with fewer clues that pin a house directly.
"""
from itertools import permutations

CATEGORIES = {
    'name': ['Ava', 'Ben', 'Cleo', 'Dev', 'Eli', 'Fern', 'Gus', 'Hana', 'Ivo', 'Jun'],
    'pet': ['cat', 'dog', 'ferret', 'parrot', 'tortoise', 'rabbit', 'goldfish'],
    'drink': ['tea', 'coffee', 'cocoa', 'lemonade', 'milk', 'cider'],
    'job': ['baker', 'nurse', 'pilot', 'tailor', 'welder', 'chemist'],
    'colour': ['red', 'green', 'blue', 'yellow', 'white', 'grey'],
    'music': ['cello', 'drums', 'flute', 'harp', 'piano', 'violin'],
}
SHAPE = {1: (4, 3), 2: (5, 3), 3: (5, 4)}
KINDS = {1: ['same', 'same', 'at', 'adjacent', 'next', 'left', 'not-same'],
         2: ['same', 'same', 'at', 'adjacent', 'next', 'left', 'not-same', 'not-next', 'gap', 'either', 'end',
             'not-at'],
         3: ['same', 'same', 'adjacent', 'next', 'left', 'not-same', 'not-next', 'gap', 'either', 'not-at',
             'one-of', 'one-of', 'if', 'if']}


def phrase(cat, value):
    return {'name': value, 'pet': f'the {value} owner', 'drink': f'the person who drinks {value}',
            'job': f'the {value}', 'colour': f'the person in the {value} house',
            'music': f'the {value} player'}[cat]


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
    if kind == 'adjacent':
        return where(*a[0]) + 1 == where(*a[1])
    if kind == 'next':
        return abs(where(*a[0]) - where(*a[1])) == 1
    if kind == 'gap':
        return abs(where(*a[0]) - where(*a[1])) == a[2]
    if kind == 'end':
        return where(*a[0]) in (0, a[1] - 1)
    raise ValueError(kind)


def text(atom, negated=False):
    kind, a = atom
    x = phrase(*a[0])
    if kind == 'same':
        y = phrase(*a[1])
        return f'{x} is {"not " if negated else ""}{y}' if a[1][0] in ('name', 'job') else \
            f'{x} {"does not live" if negated else "lives"} in the same house as {y}'
    if kind == 'at':
        return f'{x} {"does not live" if negated else "lives"} in house {a[1] + 1}'
    if kind == 'left':
        return f'{x} {"does not live" if negated else "lives"} somewhere to the left of {phrase(*a[1])}'
    if kind == 'adjacent':
        return f'{x} {"does not live" if negated else "lives"} directly to the left of {phrase(*a[1])}'
    if kind == 'next':
        return f'{x} {"does not live" if negated else "lives"} next door to {phrase(*a[1])}'
    if kind == 'gap':
        between = a[2] - 1
        houses = 'is exactly one house' if between == 1 else f'are exactly {between} houses'
        return f'there {houses} between {x} and {phrase(*a[1])}' if not negated else \
            f'it is not true that there {houses} between {x} and {phrase(*a[1])}'
    if kind == 'end':
        return f'{x} lives {"in neither end house" if negated else "in one of the two end houses"}'
    raise ValueError(kind)


# ---------------------------------------------------------------- clues: ('atom', atom, negated) | compound

def holds(clue, where):
    kind = clue[0]
    if kind == 'atom':
        return truth(clue[1], where) != clue[2]
    if kind == 'either':  # x is (in the same house as) y or z, y and z of one category
        return (truth(clue[1], where) + truth(clue[2], where)) == 1
    if kind == 'one-of':
        return (holds(clue[1], where) + holds(clue[2], where)) == 1
    if kind == 'if':
        return not holds(clue[1], where) or holds(clue[2], where)
    raise ValueError(kind)


def sentence(clue):
    kind = clue[0]
    if kind == 'atom':
        return capital(text(clue[1], clue[2])) + '.'
    if kind == 'either':
        (_, (x, y)), (_, (_, z)) = clue[1], clue[2]
        if y[0] in ('name', 'job'):
            return capital(f'{phrase(*x)} is either {phrase(*y)} or {phrase(*z)}, but not both.')
        return capital(f'{phrase(*x)} lives in the same house as either {phrase(*y)} or {phrase(*z)}.')
    if kind == 'one-of':
        return (f'Exactly one of these two statements is true: {text(clue[1][1], clue[1][2])}; '
                f'{text(clue[2][1], clue[2][2])}.')
    return capital(f'if {text(clue[1][1], clue[1][2])}, then {text(clue[2][1], clue[2][2])}.')


def cats_of(clue):
    if clue[0] == 'atom':
        return {x[0] for x in clue[1][1] if isinstance(x, tuple)}
    if clue[0] == 'either':
        return cats_of(('atom', clue[1], False)) | cats_of(('atom', clue[2], False))
    return cats_of(clue[1]) | cats_of(clue[2])


# ---------------------------------------------------------------- search

def count(n, values, clues, limit=2):
    """Number of arrangements (up to `limit`) satisfying every clue; categories are filled one at a time and a clue
    is checked as soon as all its categories are placed."""
    cats = sorted(values, key=lambda c: -sum(c in cats_of(x) for x in clues))
    due = []
    for k, cat in enumerate(cats):
        placed = set(cats[:k + 1])
        due.append([x for x in clues if cat in cats_of(x) and cats_of(x) <= placed])
    perms = list(permutations(range(n)))
    houses = {}

    def where(cat, value):
        return houses[cat][values[cat].index(value)]

    found = 0

    def search(k):
        nonlocal found
        if k == len(cats):
            found += 1
            return
        for p in perms:
            houses[cats[k]] = p
            if all(holds(x, where) for x in due[k]):
                search(k + 1)
                if found >= limit:
                    return
        del houses[cats[k]]

    search(0)
    return found


# ---------------------------------------------------------------- generation

def random_atom(rng, n, values, kind):
    cats = list(values)

    def ref(exclude=None):
        cat = rng.choice([c for c in cats if c != exclude])
        return (cat, rng.choice(values[cat]))
    x = ref()
    if kind in ('same', 'not-same', 'either'):
        return ('same', (x, ref(exclude=x[0])))
    if kind in ('at', 'not-at'):
        return ('at', (x, rng.randrange(n)))
    if kind == 'end':
        return ('end', (x, n))
    y = ref()
    while y == x:
        y = ref()
    if kind == 'gap':
        return ('gap', (x, y, rng.randint(2, n - 1)))
    return ({'left': 'left', 'adjacent': 'adjacent', 'next': 'next', 'not-next': 'next'}[kind], (x, y))


def random_clue(rng, n, values, kind, where):
    """A clue of `kind` that is true of the hidden arrangement, or None."""
    if kind == 'either':
        first = random_atom(rng, n, values, 'same')
        x, y = first[1]
        z = (y[0], rng.choice([v for v in values[y[0]] if v != y[1]]))
        second = ('same', (x, z))
        clue = ('either', first, second) if rng.random() < 0.5 else ('either', second, first)
        return clue if holds(clue, where) else None
    if kind in ('one-of', 'if'):
        simple = [k for k in KINDS[2] if k not in ('either', 'at')]
        parts = []
        for _ in range(2):
            atom = random_atom(rng, n, values, rng.choice(simple))
            parts.append(('atom', atom, rng.random() < 0.3))
        clue = (kind, *parts)
        if kind == 'if' and not holds(parts[0], where):
            return None  # a vacuous "if" teaches nothing about the hidden arrangement's own truth
        return clue if holds(clue, where) else None
    atom = random_atom(rng, n, values, kind)
    negated = kind.startswith('not-')
    if truth(atom, where) == negated:
        return None
    return ('atom', atom, negated)


def puzzle(rng, tier):
    n, width = SHAPE[tier]
    cats = ['name'] + rng.sample([c for c in CATEGORIES if c != 'name'], width - 1)
    values = {c: rng.sample(CATEGORIES[c], n) for c in cats}
    hidden = {c: tuple(rng.sample(range(n), n)) for c in cats}

    def where(cat, value):
        return hidden[cat][values[cat].index(value)]

    clues, seen = [], set()
    for _ in range(400):
        clue = random_clue(rng, n, values, rng.choice(KINDS[tier]), where)
        if clue is None or sentence(clue) in seen:
            continue
        seen.add(sentence(clue))
        clues.append(clue)
        if len(clues) >= 6 and count(n, values, clues) == 1:
            break
    else:
        return None
    for clue in rng.sample(clues, len(clues)):  # drop every clue uniqueness does not need
        rest = [x for x in clues if x is not clue]
        if count(n, values, rest) == 1:
            clues = rest
    return n, values, hidden, clues


def item(rng, tier):
    for _ in range(50):
        made = puzzle(rng, tier)
        if made and len(made[3]) >= {1: 5, 2: 7, 3: 8}[tier]:
            break
    else:
        raise AssertionError('no logic puzzle met the constraints')
    n, values, hidden, clues = made
    rng.shuffle(clues)
    asked = rng.choice([c for c in values if c != 'name'] + ['name'])
    order = sorted(values[asked], key=lambda v: hidden[asked][values[asked].index(v)])
    lists = '\n'.join(f'- {c}: {", ".join(sorted(values[c]))}' for c in values if c != 'name')
    prompt = (f'{n} houses stand in a row, numbered 1 to {n} from left to right. One person lives in each house: '
              f'{", ".join(sorted(values["name"]))}. Each person has exactly one item from each list below, and no '
              f'two people share an item:\n\n{lists}\n\n"Next door" means in a neighbouring house; "directly to the '
              'left of" means in the house with the number one lower.\n\nClues:\n\n'
              + '\n'.join(f'{k}. {sentence(c)}' for k, c in enumerate(clues, 1))
              + '\n\nExactly one arrangement satisfies all the clues.\n\nQuestion: '
              + ('Who lives in houses 1 to ' + str(n) + ', in order?' if asked == 'name' else
                 f'Which {asked} goes with each of houses 1 to {n}, in order?')
              + f' Answer with the {n} words separated by commas (for example {", ".join(sorted(values[asked]))}).')
    return {'kind': 'answer', 'prompt': prompt, 'answer': ','.join(order).lower(),
            'logic': {'values': values, 'hidden': {c: list(p) for c, p in hidden.items()}, 'clues': len(clues),
                      'asked': asked}}
