"""Staged score decision for output-affecting tuning: O'Brien-Fleming bounds plus an equivalence stop.

Rules (.claude/rules/measurement.md, 评分口径): samples 3/5/7/9/11 per condition, SE = sqrt(s1²/n1 + s2²/n2),
decide when |d| > c·SE with c = 2.25·sqrt(5/round), call equivalent when |d| + 2·SE < δ (0.05).
"""
import math
import random
import statistics

SIZES = (3, 5, 7, 9, 11)
DELTA = 0.05


def bound(round_number):
    return 2.25 * math.sqrt(5 / round_number)


def judge(a, b, delta=DELTA):
    """One round for two conditions' instance scores (equal counts); 'a', 'b', 'equivalent' or 'continue'."""
    if len(a) != len(b) or len(a) not in SIZES:
        raise ValueError('Both conditions need the same staged sample size')
    round_number = SIZES.index(len(a)) + 1
    d = statistics.fmean(a) - statistics.fmean(b)
    se = math.sqrt(statistics.variance(a) / len(a) + statistics.variance(b) / len(b))
    c = bound(round_number)
    if abs(d) > c * se:
        decision = 'a' if d > 0 else 'b'
    elif abs(d) + 2 * se < delta:
        decision = 'equivalent'
    elif len(a) == SIZES[-1]:
        decision = 'undecided'
    else:
        decision = 'continue'
    return {'n': len(a), 'round': round_number, 'd': d, 'se': se, 'bound': c * se, 'decision': decision}


def simulate(mean_a, mean_b, sd_a, sd_b, runs=20000, seed=1, delta=DELTA):
    """Monte Carlo of the staged rule with normal instance scores clipped to [0, 1]."""
    rng = random.Random(seed)
    draw = lambda m, s: min(1.0, max(0.0, rng.gauss(m, s)))
    outcomes, total = {}, 0
    for _ in range(runs):
        a, b = [], []
        for n in SIZES:
            while len(a) < n:
                a.append(draw(mean_a, sd_a))
                b.append(draw(mean_b, sd_b))
            result = judge(a, b, delta)
            if result['decision'] != 'continue':
                break
        outcomes[result['decision']] = outcomes.get(result['decision'], 0) + 1
        total += 2 * len(a)
    return {'instances_mean': total / runs, **{k: v / runs for k, v in sorted(outcomes.items())}}
