"""Random development / validation split of the loop corpus that keeps one initial task on one side.

Unit = traces sharing an initial task text (connected components). For each seed in the range, random.Random(seed)
puts each unit (sorted by smallest trace id) into validation with probability SHARE; the chosen seed minimizes
4 x squared deviation from SHARE of cross-call groups, single-response groups and behavior facts, plus the mean squared
deviation from SHARE of facts in each source batch over BATCH_FACTS facts.
"""
import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

CORPUS = Path(__file__).resolve().parents[2] / 'benchmarks/loop-detection-v2'
SHARE = 0.25
BATCH_FACTS = 300


def units(traces):
    parent = {t['trace_id']: t['trace_id'] for t in traces}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    owner = {}
    for trace in traces:
        for task in trace['initial_task_inputs']:
            other = owner.setdefault(task['source_text_sha256'], trace['trace_id'])
            parent[find(trace['trace_id'])] = find(other)
    groups = defaultdict(list)
    for trace in traces:
        groups[find(trace['trace_id'])].append(trace['trace_id'])
    return sorted((sorted(g) for g in groups.values()), key=lambda g: g[0])


def split(first_seed, seeds, corpus=CORPUS):
    manifest = json.loads((corpus / 'behavior-manifest.json').read_text())
    overlay = json.loads((corpus / 'main-annotations.json').read_text())
    traces = {t['trace_id']: t for t in manifest['traces']}
    loops = Counter((loop['trace_id'], loop['mode']) for loop in overlay['loops'])
    weight = {t: Counter({'cross_call': loops[(t, 'cross_call')], 'single_response': loops[(t, 'single_response')],
                          'facts': traces[t]['behavior_fact_count'], 'batch:' + traces[t]['source_batch']:
                          traces[t]['behavior_fact_count']}) for t in traces}
    total = sum(weight.values(), Counter())
    batches = [key for key in total if key.startswith('batch:') and total[key] > BATCH_FACTS]
    parts = units(list(traces.values()))
    best = None
    for seed in range(first_seed, first_seed + seeds):
        rng = random.Random(seed)
        held = [t for unit in parts if rng.random() < SHARE for t in unit]
        got = sum((weight[t] for t in held), Counter())
        share = lambda key: got[key] / total[key] - SHARE
        score = (4 * sum(share(key) ** 2 for key in ('cross_call', 'single_response', 'facts'))
                 + sum(share(key) ** 2 for key in batches) / len(batches))
        if best is None or score < best[0]:
            best = score, seed, set(held)
    score, seed, held = best
    sides = {'development': sorted(set(traces) - held), 'validation': sorted(held)}
    stats = {name: {'traces': len(ids), 'behavior_facts': sum(weight[t]['facts'] for t in ids),
                    'loop_groups': sum(weight[t]['cross_call'] + weight[t]['single_response'] for t in ids),
                    'cross_call': sum(weight[t]['cross_call'] for t in ids),
                    'single_response': sum(weight[t]['single_response'] for t in ids)}
             for name, ids in sides.items()}
    return {'schema_version': 1, 'behavior_sha256': manifest['behavior_sha256'],
            'annotation_revision': overlay.get('annotation_revision'), 'method': __doc__.strip(),
            'seeds': [first_seed, first_seed + seeds - 1], 'seed': seed, 'score': score, 'stats': stats, **sides}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--first-seed', type=int, required=True)
    parser.add_argument('--seeds', type=int, default=20000)
    parser.add_argument('--created', required=True)
    parser.add_argument('--purpose', required=True)
    args = parser.parse_args()
    result = split(args.first_seed, args.seeds)
    result = {'schema_version': 1, 'created': args.created, 'purpose': args.purpose, **result}
    (CORPUS / 'split.json').write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({k: result[k] for k in ('seed', 'score', 'stats')}))


if __name__ == '__main__':
    main()
