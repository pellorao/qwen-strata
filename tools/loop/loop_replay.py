"""Causal offline replay with oracle-only skips and rule-specific alert targets.

The detector receives observations only. Frozen annotations are used by the
test driver for scoring and skipping, never by a live model or detector.
"""
from dataclasses import dataclass
from copy import deepcopy
from tools.loop.loop_reminders import reminder_text


@dataclass(frozen=True)
class Observation:
    id: str
    trace_id: str
    payload: dict


@dataclass(frozen=True)
class LoopEpisode:
    id: str
    trace_id: str
    occurrences: tuple[str, ...]
    resume_id: str | None
    targets: dict[str, str]
    mode: str = 'cross_call'
    text_spans: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class Alert:
    rule_id: str
    evidence_ids: tuple[str, ...]
    evidence_spans: tuple[tuple[str, int, int], ...] = ()


_ANSWER_FIELDS = frozenset(('loop_annotations', 'normal_annotations', 'label',
                           'targets', 'resume_id', 'expected_trigger', 'expected_position',
                           'mode', 'text_spans'))


def matches_single_response(episode, alert, observation):
    """Independent spans, not a self-declared group ID, establish the match."""
    if tuple(alert.evidence_ids) != episode.occurrences or observation.id != episode.occurrences[0]:
        return False
    text = observation.payload.get('text', '')
    spans = list(alert.evidence_spans)
    if len(spans) < 2 or any(key != observation.id or not 0 <= a < b <= len(text) for key, a, b in spans):
        return False
    matched = [{j for j, (start, end) in enumerate(episode.text_spans)
                if start <= a < b <= end} for _, a, b in spans]
    return any((left[2] <= right[1] or right[2] <= left[1])
               and any(a != b for a in matched[i] for b in matched[j])
               for i, left in enumerate(spans) for j, right in enumerate(spans) if j > i)


def replay(observations, episodes, detector, rule_ids):
    """A detector supplies observe(observation) and reset(trace_id).

    reset clears repetition history; other task context is managed separately.
    One selected rule gives its independent score; multiple rules give the
    joint score, whose target is the earliest applicable per-rule target.
    Loops need exact, nonoverlapping bounds before intervention replay.
    """
    observations = list(observations)
    episodes = list(episodes)
    selected = frozenset(rule_ids)
    if not selected:
        raise ValueError('Select at least one rule')
    if len({episode.id for episode in episodes}) != len(episodes):
        raise ValueError('Loop episode identities must be unique')
    positions = {o.id: i for i, o in enumerate(observations)}
    if len(positions) != len(observations):
        raise ValueError('Observation identities must be unique')
    indexed = []
    expected = {}
    occupied = set()
    for episode in episodes:
        if episode.mode not in ('cross_call', 'single_response'):
            raise ValueError('Unknown loop mode')
        single = episode.mode == 'single_response'
        if single and len(episode.occurrences) != 1:
            raise ValueError('Single-response loop must have exactly one detection point')
        if not single and len(set(episode.occurrences)) < 2:
            raise ValueError('A confirmed loop needs independent occurrences')
        if any(key not in positions for key in episode.occurrences):
            raise ValueError('Missing loop occurrence')
        indices = [positions[key] for key in episode.occurrences]
        if indices != sorted(indices):
            raise ValueError('Loop occurrences must be ordered')
        start = indices[0]
        if single:
            text = observations[start].payload.get('text', '')
            spans = episode.text_spans
            if (len(spans) < 2 or any(not 0 <= a < b <= len(text) for a, b in spans)
                    or spans != tuple(sorted(spans))
                    or any(a[1] > b[0] for a, b in zip(spans, spans[1:]))):
                raise ValueError('Single-response loop needs nonoverlapping repeated text evidence')
        stop = (positions[episode.resume_id] if episode.resume_id is not None else
                next((j for j in range(start + 1, len(observations))
                      if observations[j].trace_id != episode.trace_id), len(observations)))
        if stop <= indices[-1]:
            raise ValueError('Resume must follow the loop')
        if single and stop != start + 1:
            raise ValueError('A completed response cannot license skipping later normal records')
        region = set(range(start, stop))
        if not single and occupied & region:
            raise ValueError('Resolve overlapping loop boundaries before replay')
        if not single:
            occupied |= region
        if any(observations[i].trace_id != episode.trace_id for i in region):
            raise ValueError('A loop cannot cross trace boundaries')
        # No hidden normal observation may be dropped inside this region.
        if region != set(indices):
            raise ValueError('Split loops around intervening normal observations')
        if episode.resume_id is not None and observations[stop].trace_id != episode.trace_id:
            raise ValueError('Resume must be bound to the same trace')
        if any(key not in episode.occurrences for key in episode.targets.values()):
            raise ValueError('Rule target must be an occurrence of this loop')
        eligible = {rule: positions[key] for rule, key in episode.targets.items() if rule in selected}
        if eligible:
            expected[episode.id] = min(eligible.values())
        indexed.append((episode, start, stop, eligible))
    matched = set()
    decisions = []
    skips = []
    fp = 0
    i = 0
    previous_trace = None
    while i < len(observations):
        observation = observations[i]
        if observation.trace_id != previous_trace:
            detector.reset(observation.trace_id)
            previous_trace = observation.trace_id
        visible = Observation(observation.id, observation.trace_id,
                              deepcopy({k: v for k, v in observation.payload.items() if k not in _ANSWER_FIELDS}))
        alerts = list(detector.observe(visible))
        next_i = i + 1
        for alert in alerts:
            if alert.rule_id not in selected:
                raise ValueError('Detector emitted an unselected rule')
            witnesses = set(alert.evidence_ids)
            candidates = []
            if len(witnesses) >= 2 and all(key in positions and positions[key] <= i for key in witnesses):
                candidates = [row for row in indexed
                              if row[0].trace_id == observation.trace_id
                              and row[0].mode == 'cross_call'
                              and witnesses <= set(row[0].occurrences)]
            candidates += [row for row in indexed if row[0].mode == 'single_response'
                           and row[0].trace_id == observation.trace_id
                           and matches_single_response(row[0], alert, observation)]
            row = candidates[0] if len(candidates) == 1 else None
            genuine = row is not None
            episode_id = row[0].id if row else None
            target = expected.get(episode_id)
            rule_target = row[3].get(alert.rule_id) if row else None
            timely = (genuine and i == target and i == rule_target and episode_id not in matched)
            if timely:
                matched.add(episode_id)
                classification = 'TP'
            else:
                fp += 1
                classification = 'FP'
            decisions.append({'observation_id': observation.id, 'rule_id': alert.rule_id,
                'episode_id': episode_id, 'genuine_loop': genuine,
                'classification': classification,
                'reason': ('single-point-match' if timely and row[0].mode == 'single_response' else 'on-time') if timely else 'semantic-false-positive' if not genuine else
                    'duplicate' if episode_id in matched else 'early' if target is not None and i < target else 'late-or-ineligible'})
            if genuine:
                decisions[-1]['reminder_kind'] = row[0].mode
                decisions[-1]['reminder_text'] = reminder_text(row[0].mode)
            # A genuine early/late warning also suppresses the remaining loop.
            # Score it first; the skip never creates TP or removes an existing FN.
            if genuine and row[2] > next_i:
                next_i = row[2]
                skips.append({'episode_id': episode_id, 'after_observation_id': observation.id,
                              'resume_id': row[0].resume_id,
                              'skipped_observation_ids': [o.id for o in observations[i + 1:next_i]]})
        if next_i > i + 1:
            detector.reset(observation.trace_id)
        i = next_i
    tp = len(matched)
    fn = len(expected.keys() - matched)
    return {'tp': tp, 'fp': fp, 'fn': fn,
            'precision': tp / (tp + fp) if tp + fp else None,
            'recall': tp / (tp + fn) if tp + fn else None,
            'f1': 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
            'decisions': decisions, 'skips': skips, 'model_runs': 0, 'model_requests': 0}
