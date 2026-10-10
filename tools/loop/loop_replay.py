"""Full causal offline replay under scoring contract v4 (benchmarks/loop-detection-v2/scoring-contract.md).

Every record is replayed in order and nothing is skipped. The detector sees only the observations replayed so far
and returns, for each model-behavior record, a probability that it is (or contains) a repetition. Frozen loop groups
are used only here, to score. One occurrence may span several records (a repeated reasoning step and the call or
answer it leads to). A rule that needs k occurrences first owes an alert at the earliest record of the k-th
occurrence (weight 1); the group's other later records share weight 0.5; records with only earlier occurrences are not
scored. Records outside every group are negatives. 0.4 <= p <= 0.6 is wrong either way.
"""
from dataclasses import dataclass

POSITIVE, NEGATIVE = 0.6, 0.4
FIRST_WEIGHT, LATER_WEIGHT = 1.0, 0.5
GATE_F2 = 0.8          # recall weighs more than precision: a detection only sends a reminder
_ANSWER_FIELDS = frozenset(('loop_annotations', 'normal_annotations', 'label', 'loop_case_ids'))


@dataclass(frozen=True)
class Observation:
    id: str
    trace_id: str
    payload: dict
    judged: bool = True  # model behavior; control boundaries, task input and feedback are observed but not judged


@dataclass(frozen=True)
class LoopGroup:
    id: str
    trace_id: str
    occurrences: tuple  # per occurrence, in order: a record id or a tuple of record ids; one record may hold several
    mode: str = 'cross_call'

    def records(self):
        """Record ids of each occurrence, as tuples."""
        return [(o,) if isinstance(o, str) else tuple(o) for o in self.occurrences]


def verdict(p):
    if type(p) is bool:
        p = float(p)
    if type(p) not in (int, float) or not 0 <= p <= 1:
        raise ValueError('Detector must return a probability in [0, 1]')
    return 'positive' if p > POSITIVE else 'negative' if p < NEGATIVE else 'uncertain'


def targets(groups, k, order):
    """{record id: [(group id, 'first' | 'later', weight)]}, neutral record ids, unreachable group ids.

    order maps record id -> replay position, to find the earliest record of an occurrence."""
    owed, neutral, unreachable = {}, set(), []
    for group in groups:
        occurrences = [sorted(o, key=order.__getitem__) for o in group.records()]
        if group.mode == 'single_response':
            if len({o[0] for o in occurrences}) != 1:
                raise ValueError('A single-response group repeats inside one record: ' + group.id)
            first, rest = occurrences[0][0], [r for o in occurrences for r in o]
        elif group.mode != 'cross_call':
            raise ValueError('Unknown loop mode')
        elif len(occurrences) < k:
            unreachable.append(group.id)
            neutral.update(r for o in occurrences for r in o)
            continue
        else:
            first, rest = occurrences[k - 1][0], [r for o in occurrences[k - 1:] for r in o]
            neutral.update(r for o in occurrences[:k - 1] for r in o)
        owed.setdefault(first, []).append((group.id, 'first', FIRST_WEIGHT))
        later = [r for r in dict.fromkeys(rest) if r != first]
        for record in later:
            owed.setdefault(record, []).append((group.id, 'later', LATER_WEIGHT / len(later)))
    return owed, neutral - set(owed), unreachable


def replay(observations, groups, detector, k):
    """detector.observe(observation) -> probability for judged records; detector.reset(trace_id) per trace."""
    if type(k) is not int or k < 2:
        raise ValueError('A cross-call rule needs at least two occurrences')
    observations, groups = list(observations), list(groups)
    ids = [o.id for o in observations]
    if len(set(ids)) != len(ids) or len({g.id for g in groups}) != len(groups):
        raise ValueError('Observation and group identities must be unique')
    judged = {o.id for o in observations if o.judged}
    for group in groups:
        if not {r for o in group.records() for r in o} <= judged:
            raise ValueError('Group occurrences must be judged observations: ' + group.id)
    owed, neutral, unreachable = targets(groups, k, {o.id: n for n, o in enumerate(observations)})
    verdicts, trace = {}, None
    for observation in observations:
        if observation.trace_id != trace:
            trace = observation.trace_id
            detector.reset(trace)
        visible = Observation(observation.id, observation.trace_id,
                              {key: value for key, value in observation.payload.items() if key not in _ANSWER_FIELDS},
                              observation.judged)
        p = detector.observe(visible)
        if observation.judged:
            verdicts[observation.id] = verdict(p)
    tp = fn = fp = 0.0
    first_hit = later_hit = later_total = 0.0
    group_first = {g: False for g in [g.id for g in groups]}
    detail = []
    for record, owed_here in owed.items():
        hit = verdicts[record] == 'positive'
        for group, kind, weight in owed_here:
            tp, fn = (tp + weight, fn) if hit else (tp, fn + weight)
            if kind == 'first':
                first_hit += hit
                group_first[group] = hit
            else:
                later_total += weight
                later_hit += weight * hit
            detail.append({'record': record, 'group': group, 'kind': kind, 'weight': weight,
                           'verdict': verdicts[record]})
    fn += FIRST_WEIGHT * len(unreachable)
    negatives = [r for r in judged if r not in owed and r not in neutral]
    false_alarms = sorted(r for r in negatives if verdicts[r] != 'negative')
    fp = float(len(false_alarms))
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (2 * precision * recall / (precision + recall) if precision and recall else
          0.0 if precision is not None and recall is not None else None)
    f2 = (5 * precision * recall / (4 * precision + recall) if precision and recall else
          0.0 if precision is not None and recall is not None else None)
    firsts = sum(kind == 'first' for owed_here in owed.values() for _, kind, _ in owed_here)
    return {
        'k': k, 'tp': tp, 'fn': fn, 'fp': fp, 'precision': precision, 'recall': recall, 'f1': f1, 'f2': f2,
        'passes_gate': f2 is not None and f2 >= GATE_F2,
        'first_targets': firsts, 'first_hits': int(first_hit), 'unreachable_groups': sorted(unreachable),
        'later_weight': later_total, 'later_hit_weight': later_hit,
        'group_recall': sum(group_first.values()) / len(groups) if groups else None,
        'negatives': len(negatives), 'neutral_records': len(neutral),
        'uncertain_positive_records': sum(verdicts[r] == 'uncertain' for r in owed),
        'uncertain_negative_records': sum(verdicts[r] == 'uncertain' for r in negatives),
        'false_alarms': false_alarms, 'targets': detail,
    }
