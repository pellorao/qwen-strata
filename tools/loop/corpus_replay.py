"""Full-corpus replay input for scoring contract v3, and a scoring CLI for registered detectors.

Observations come from behavior.jsonl.gz in native order (one per normalized record); loop groups come from the
SHA-bound Main annotation overlay, each evidence mark being one occurrence. Labels stay on the scoring side.
split.json fixes which traces are for development and which are held out for the final gate confirmation.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

from tools.loop.loop_replay import LoopGroup, Observation, replay

CORPUS = Path(__file__).resolve().parents[2] / 'benchmarks/loop-detection-v2'
JUDGED = ('reasoning', 'assistant', 'tool')
INPUT_FIELDS = {'reasoning': ('text',), 'assistant': ('text',), 'tool': ('name', 'arguments', 'output', 'result_present'),
                'task': ('text',), 'feedback': ('text',), 'boundary': ('event',)}


def record_id(fact):
    return fact['trace_id'] + ':' + ','.join(map(str, fact['source_events']))


def load(split='development', corpus=CORPUS):
    """split: 'development', 'validation' (final gate only) or None for the whole corpus."""
    packed = (corpus / 'behavior.jsonl.gz').read_bytes()
    overlay = json.loads((corpus / 'main-annotations.json').read_text())
    sha = hashlib.sha256(packed).hexdigest()
    if overlay['behavior_sha256'] != sha:
        raise ValueError('Annotation overlay is bound to different behavior data')
    facts = [json.loads(line) for line in gzip.decompress(packed).splitlines()]
    if split is not None:
        division = json.loads((corpus / 'split.json').read_text())
        if division['behavior_sha256'] != sha:
            raise ValueError('Split is bound to different behavior data')
        keep = set(division[split])
        facts = [fact for fact in facts if fact['trace_id'] in keep]
    observations, by_event, position = [], {}, {}
    traces = {fact['trace_id'] for fact in facts}
    for fact in facts:
        rid = record_id(fact)
        payload = {'kind': fact['kind'], 'turn_id': fact.get('turn_id'),
                   **{k: fact[k] for k in INPUT_FIELDS.get(fact['kind'], ()) if k in fact}}
        position[rid] = len(observations)
        observations.append(Observation(rid, fact['trace_id'], payload, fact['kind'] in JUDGED))
        for event in fact['source_events']:
            by_event[(fact['trace_id'], event)] = rid
    groups = []
    for loop in overlay['loops']:
        if loop['trace_id'] not in traces:
            continue
        marks = sorted(loop['evidence_marks'],
                       key=lambda m: (position[by_event[(loop['trace_id'], m['event'])]], m.get('start', 0)))
        occurrences = tuple(by_event[(loop['trace_id'], m['event'])] for m in marks)
        groups.append(LoopGroup(loop['case_id'], loop['trace_id'], occurrences, loop['mode']))
    return observations, groups, {'behavior_sha256': sha, 'annotation_revision': overlay.get('annotation_revision'),
                                  'split': split}


class Silent:
    """Never alerts: the floor every real detector is compared against."""
    def reset(self, trace):
        pass

    def observe(self, observation):
        return 0.0


DETECTORS = {'silent': Silent}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--detector', choices=sorted(DETECTORS), required=True)
    parser.add_argument('--k', type=int, required=True, help="the detector contract's occurrences before a repeat")
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--split', choices=('development', 'validation'), default='development',
                        help='validation is only for the final gate confirmation')
    args = parser.parse_args()
    observations, groups, binding = load(args.split)
    result = replay(observations, groups, DETECTORS[args.detector](), args.k)
    result.update(binding, detector=args.detector, observations=len(observations),
                  judged=sum(o.judged for o in observations), groups=len(groups))
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({k: result[k] for k in ('detector', 'k', 'judged', 'groups', 'tp', 'fn', 'fp', 'f1',
                                             'first_targets', 'neutral_records', 'negatives')}))


if __name__ == '__main__':
    main()
