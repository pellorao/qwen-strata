"""Observe the full cleaned corpus with unchanged experimental guard code.

This nonintervening discovery pass collects alert evidence before causal gold
boundaries and first-trigger targets are finalized. It is not an F1 evaluator.
Gold labels are never passed to either detector.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

from tools.loop.progress_guard import initial_state, observe_commands
from tools.loop.reasoning_loop_guard import observe_model_text


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def observation_id(fact: dict) -> str:
    return fact['trace_id'] + ':' + str(fact['source_events'][0]) + ':' + fact['kind']


def detector_input(fact: dict) -> dict:
    """Explicit allowlist; do not forward initial seed labels or gold overlay."""
    common = dict(threadId=fact['trace_id'], turnId=fact.get('turn_id'), itemId=fact['item_id'])
    if fact['kind'] in ('reasoning', 'assistant'):
        return common | {'text': fact['text']}
    arguments = fact.get('arguments', {})
    return common | dict(command=arguments.get('cmd', '') if isinstance(arguments, dict) else '',
                         cwd=fact.get('cwd_sha256') or (arguments.get('workdir') if isinstance(arguments, dict) else None),
                         exitCode=fact.get('exit_code'), output=fact.get('output'),
                         outputDigest=fact.get('output_sha256'))


def run(corpus: Path) -> dict:
    blob = (corpus/'behavior.jsonl.gz').read_bytes()
    manifest = json.loads((corpus/'behavior-manifest.json').read_text(encoding='utf-8'))
    if sha(blob) != manifest['behavior_sha256']:
        raise ValueError('Frozen behavior digest changed')
    facts = [json.loads(line) for line in gzip.decompress(blob).splitlines()]
    states = {}
    identities = {}
    hints = []
    counts = Counter()
    source_by_identity = {}
    for fact in facts:
        kind = fact['kind']
        counts[kind] += 1
        if kind not in ('reasoning', 'assistant', 'tool'):
            continue
        trace = fact['trace_id']
        state = states.setdefault(trace, initial_state([trace, 'offline-full-discovery']))
        identity = (trace, fact.get('turn_id'), fact['item_id'])
        source_by_identity[identity] = observation_id(fact)
        identities[observation_id(fact)] = dict(trace_id=trace,source_events=fact['source_events'],kind=kind,
             evidence_sha256=fact.get('text_sha256',fact.get('source_arguments_sha256')))
        value = detector_input(fact)
        if kind in ('reasoning','assistant'):
            observed = observe_model_text(state,[value],trace)
        elif fact.get('name') == 'exec_command':
            counts['command_observations'] += 1
            if type(value['exitCode']) is int and value['outputDigest'] is not None:
                counts['known_command_results'] += 1
            observed = observe_commands(state,[value],trace)
        else:
            # No substitute command is inferred for generic tools or an exec wrapper.
            observed = []
        for hint in observed:
            evidence = []
            for witness in hint.get('evidence_ids',[]):
                if isinstance(witness,list) and len(witness)==2:
                    key = (trace,*witness)
                    if key in source_by_identity:
                        evidence.append(source_by_identity[key])
            spans = []
            for witness,start,end in hint.get('evidence_spans',[]):
                key = (trace,*witness)
                if key in source_by_identity:
                    spans.append([source_by_identity[key],start,end])
            # Copy immediately: the prototype holds literal-line witnesses in a mutable list.
            snapshot = json.loads(json.dumps(hint,ensure_ascii=False))
            hints.append(dict(trace_id=trace,observation_id=observation_id(fact),
                source_event=fact['source_events'][0],rule_id=hint['kind'],evidence_observation_ids=evidence,
                evidence_observation_spans=spans,hint=snapshot))
    return dict(schema_version=1,status='full-discovery-pass-not-causal-f1',behavior_sha256=sha(blob),
        traces_observed=len({f['trace_id'] for f in facts}),traces_with_model_tool_behavior=len(states),
        facts_observed=len(facts),counts=dict(counts),
        hints_by_rule=dict(Counter(h['rule_id'] for h in hints)),hint_count=len(hints),
        alerts=hints,observation_bindings=identities,
        implementation_sha256={name:sha((Path(__file__).parent/name).read_bytes()) for name in
            ('reasoning_loop_guard.py','progress_guard.py','replay_model_behavior.py')},
        f1=None,detector_rule_changes=0,model_runs=0,model_requests=0,
        limitations=['All original observations are retained; no intervention skips in this discovery pass.',
             'No artifact state or runtime input version is invented from model claims; delivery-stall and non-SyntaxError context rules lack trusted state observations in this corpus.',
             'No first-trigger or skip-target score until causal-unit annotations are validated.',
             'Generic tools and exec wrappers are preserved as facts but are not fabricated into completed shell commands.'])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus',type=Path,default=Path('benchmarks/loop-detection-v2'))
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    result = run(args.corpus)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('alerts','observation_bindings')},ensure_ascii=False))


if __name__ == '__main__':
    main()
