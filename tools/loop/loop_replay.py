"""Full causal offline replay under scoring contract v5 (benchmarks/loop-detection-v2/scoring-contract.md).

Every record is replayed in order and nothing is skipped. The detector sees only the observations replayed so far
and returns, for each model-behavior record, a probability that it is (or contains) a repetition; p >= 0.5 is an
alert. Frozen loop groups are used only here, to score. One occurrence may span several records (a repeated reasoning
step and the call or answer it leads to). A rule that needs k occurrences owes its alert by the k-th occurrence: an
alert there or earlier earns the group 1, each later occurrence halves it. A repeat inside one response has a single
detection point (the response and its companions). Recall is the mean group credit; precision is the share of alerts
that fall on repeated occurrences. Records with only an original occurrence are not scored.
"""
from dataclasses import dataclass

ALERT = 0.5            # p >= ALERT is an alert
DECAY = 0.5            # credit kept per occurrence an alert comes late
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


def alert(p):
    if type(p) is bool:
        p = float(p)
    if type(p) not in (int, float) or not 0 <= p <= 1:
        raise ValueError('Detector must return a probability in [0, 1]')
    return p >= ALERT


def credits(groups, k, k_inside):
    """{group id: {record id: credit an alert there earns}}, repeated record ids, original-only record ids, unreachable."""
    owed, repeated, original, unreachable = {}, set(), set(), []
    for group in groups:
        occurrences = group.records()
        if group.mode == 'single_response':
            if len({o[0] for o in occurrences}) != 1:
                raise ValueError('A single-response group repeats inside one record: ' + group.id)
            here = {r: 1.0 for o in occurrences for r in o}
            need = k_inside
        elif group.mode == 'cross_call':
            here = {}
            for n, occurrence in enumerate(occurrences[1:], 1):
                for r in occurrence:
                    here.setdefault(r, DECAY ** max(0, n - (k - 1)))
            need = k
        else:
            raise ValueError('Unknown loop mode')
        repeated.update(here)
        original.update(occurrences[0])
        if len(occurrences) < need:
            unreachable.append(group.id)
            here = {}
        owed[group.id] = here
    return owed, repeated, original - repeated, unreachable


def replay(observations, groups, detector, k, k_inside=2):
    """detector.observe(observation) -> probability for judged records; detector.reset(trace_id) per trace."""
    if type(k) is not int or k < 2 or type(k_inside) is not int or k_inside < 2:
        raise ValueError('A rule needs at least two occurrences')
    observations, groups = list(observations), list(groups)
    ids = [o.id for o in observations]
    if len(set(ids)) != len(ids) or len({g.id for g in groups}) != len(groups):
        raise ValueError('Observation and group identities must be unique')
    judged = {o.id for o in observations if o.judged}
    for group in groups:
        if not {r for o in group.records() for r in o} <= judged:
            raise ValueError('Group occurrences must be judged observations: ' + group.id)
    owed, repeated, original, unreachable = credits(groups, k, k_inside)
    alerts, trace = set(), None
    for observation in observations:
        if observation.trace_id != trace:
            trace = observation.trace_id
            detector.reset(trace)
        visible = Observation(observation.id, observation.trace_id,
                              {key: value for key, value in observation.payload.items() if key not in _ANSWER_FIELDS},
                              observation.judged)
        p = detector.observe(visible)
        if observation.judged and alert(p):
            alerts.add(observation.id)
    credit = {g: max([c for r, c in here.items() if r in alerts] or [0.0]) for g, here in owed.items()}
    negatives = judged - repeated - original
    false_alarms = sorted(alerts & negatives)
    justified = len(alerts & repeated)
    recall = sum(credit.values()) / len(groups) if groups else None
    precision = justified / (justified + len(false_alarms)) if justified + len(false_alarms) else None
    f1 = (2 * precision * recall / (precision + recall) if precision and recall else
          0.0 if precision is not None and recall is not None else None)
    f2 = (5 * precision * recall / (4 * precision + recall) if precision and recall else
          0.0 if precision is not None and recall is not None else None)
    return {
        'k': k, 'k_inside': k_inside, 'precision': precision, 'recall': recall, 'f1': f1, 'f2': f2,
        'passes_gate': f2 is not None and f2 >= GATE_F2,
        'on_time_groups': sum(c == 1 for c in credit.values()),
        'late_groups': sum(0 < c < 1 for c in credit.values()),
        'missed_groups': sorted(g for g, c in credit.items() if c == 0), 'unreachable_groups': sorted(unreachable),
        'alerts': len(alerts), 'justified_alerts': justified, 'fp': len(false_alarms),
        'original_only_records': len(original), 'negatives': len(negatives),
        'false_alarms': false_alarms, 'credit': credit,
    }
