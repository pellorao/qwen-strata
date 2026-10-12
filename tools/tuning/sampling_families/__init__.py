"""Item generators of the sampling question bank v3: five directions, three tiers (see each module's docstring).

Every item comes from its own seeded generator; answers and hidden tests are computed by reference code here,
never written by hand.
"""
import random

from tools.tuning.sampling_families import codec, count, debug, ledger, machine

FAMILIES = ('ledger', 'machine', 'count', 'codec', 'debug')
TIERS = (1, 2, 3)


def item(family, tier, seed):
    rng = random.Random(f'{family}/{tier}/{seed}')
    if family == 'debug':
        value = debug.item(rng, tier, seed)
    else:
        value = {'ledger': ledger, 'machine': machine, 'count': count, 'codec': codec}[family].item(rng, tier)
    return {'id': f'{family}-t{tier}-s{seed}', 'family': family, 'tier': tier, 'seed': seed, **value}
