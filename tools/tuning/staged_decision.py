"""Staged score decision for output-affecting tuning: O'Brien-Fleming bounds, early exit of trailing candidates
and an equivalence stop.

Rules (.claude/rules/measurement.md, 评分口径): samples 3/5/7/9/11 per remaining candidate; each round compares every
remaining candidate with the current leader, SE = sqrt(s1²/n1 + s2²/n2).  A candidate leaves when the leader is ahead
by more than c·SE, c = c_final(k)·sqrt(5/round) (FINAL_BOUNDS; k is the number of candidates at the start, so the
bound does not loosen as candidates leave).  A candidate within |d| + 2·SE < δ (0.05) of the leader is tied and stops
being sampled; the leader and all tied candidates are finally chosen among by speed.
"""
import math
import random
import statistics

SIZES = (3, 5, 7, 9, 11)
DELTA = 0.05
# Final-round bound by number of candidates at the start, calibrated by `simulate` (equal candidates, SD 0.04,
# 3000 runs) so that the chance of eliminating anyone when all are equal stays near the two-candidate 5-6 %.
# Comparing with the observed leader (the maximum of k noisy means) needs more than a Bonferroni correction.
FINAL_BOUNDS = {2: 2.25, 3: 2.6, 4: 3.0, 5: 3.3, 6: 3.4}


def final_bound(candidates):
    return FINAL_BOUNDS[candidates]


def bound(round_number, candidates=2):
    return final_bound(candidates) * math.sqrt(5 / round_number)


def judge_many(scores, candidates, delta=DELTA):
    """One round over the candidates still being sampled (equal counts at 3/5/7/9/11).

    Each candidate is compared with the current leader: it leaves when the leader is ahead by more than c·SE; it is
    tied when |d| + 2·SE < δ and then stops being sampled (it joins the tie group, chosen among by speed at the end);
    otherwise it stays open.  The leader and open candidates get +2 next round.  Decision: 'winner' (no open and no
    tied candidate), 'equivalent' (no open candidate, some tied), 'undecided' (11 reached with open candidates) or
    'continue'."""
    sizes = {len(v) for v in scores.values()}
    if len(sizes) != 1 or next(iter(sizes)) not in SIZES or len(scores) < 2:
        raise ValueError('Every sampled candidate needs the same staged sample size')
    n = next(iter(sizes))
    round_number = SIZES.index(n) + 1
    means = {k: statistics.fmean(v) for k, v in scores.items()}
    leader = max(means, key=means.get)
    c = bound(round_number, candidates)
    rows = {}
    for k, v in scores.items():
        if k == leader:
            continue
        d = means[leader] - means[k]
        se = math.sqrt(statistics.variance(scores[leader]) / n + statistics.variance(v) / n)
        state = 'leaves' if d > c * se else 'tied' if abs(d) + 2 * se < delta else 'open'
        rows[k] = {'d': d, 'se': se, 'bound': c * se, 'state': state}
    open_ = [k for k, r in rows.items() if r['state'] == 'open']
    tied = [k for k, r in rows.items() if r['state'] == 'tied']
    if not open_:
        decision = 'equivalent' if tied else 'winner'
    elif n == SIZES[-1]:
        decision = 'undecided'
    else:
        decision = 'continue'
    return {'n': n, 'round': round_number, 'c': c, 'means': means, 'leader': leader, 'comparisons': rows,
            'leaving': [k for k, r in rows.items() if r['state'] == 'leaves'], 'tied': tied,
            'sampled_next': [leader] + open_ if decision == 'continue' else [], 'decision': decision}


def simulate(means, sd, runs=20000, seed=1, delta=DELTA):
    """Monte Carlo of the staged rule with normal instance scores clipped to [0, 1]; `means` per candidate."""
    rng = random.Random(seed)
    draw = lambda m: min(1.0, max(0.0, rng.gauss(m, sd)))
    best = max(means)
    outcomes, total, best_lost, wrong_exit = {}, 0, 0, 0
    for _ in range(runs):
        sampled, tied = list(range(len(means))), []
        scores = {k: [] for k in sampled}
        for n in SIZES:
            for k in sampled:
                while len(scores[k]) < n:
                    scores[k].append(draw(means[k]))
                    total += 1
            result = judge_many({k: scores[k] for k in sampled}, len(means), delta)
            tied += result['tied']
            alive = [result['leader']] + tied + [k for k, r in result['comparisons'].items() if r['state'] == 'open']
            sampled = result['sampled_next']
            if result['decision'] != 'continue':
                break
        outcomes[result['decision']] = outcomes.get(result['decision'], 0) + 1
        best_lost += all(means[k] < best for k in alive)
        wrong_exit += any(means[k] == best for k in range(len(means)) if k not in alive)
    return {'instances_mean': total / runs, 'all_best_eliminated': best_lost / runs,
            'some_best_eliminated': wrong_exit / runs,
            **{k: v / runs for k, v in sorted(outcomes.items())}}
