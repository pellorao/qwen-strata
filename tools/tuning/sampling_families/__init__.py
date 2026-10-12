"""Item generators of the sampling question bank v5: eight directions, three tiers (see each module's docstring).

Five directions carried over from v3 (ledger, machine, count, codec, debug) are written as module levels 4-6: v5
tier 1 is level 4 (v4's hardest), tiers 2 and 3 are levels 5 and 6, made so that enumeration or plain simulation
cannot finish.  Three directions are new and meant
to be solved by reasoning rather than by writing a program: logic (multi-step constraint reasoning over clues in
prose), policy (applying a written regulation's definitions, exceptions and precedence) and incident (root cause
from interleaved service logs).  Every item comes from its own seeded generator; answers and hidden tests are
computed by reference code here, never written by hand.
"""
import random

from tools.tuning.sampling_families import codec, count, debug, incident, ledger, logic, machine, policy

FAMILIES = ('ledger', 'machine', 'count', 'codec', 'debug', 'logic', 'policy', 'incident')
TIERS = (1, 2, 3)
SHIFTED = ('ledger', 'machine', 'count', 'codec', 'debug')  # v5 tier t = module level t + 3


def item(family, tier, seed):
    rng = random.Random(f'{family}/{tier}/{seed}')
    level = tier + 3 if family in SHIFTED else tier
    if family == 'debug':
        value = debug.item(rng, level, seed)
    else:
        value = {'ledger': ledger, 'machine': machine, 'count': count, 'codec': codec, 'logic': logic,
                 'policy': policy, 'incident': incident}[family].item(rng, level)
    return {'id': f'{family}-t{tier}-s{seed}', 'family': family, 'tier': tier, 'level': level, 'seed': seed, **value}
