"""Loop statistics of ARW sessions (sampling dimension, .tmp/load-design-1022/draft-v2.md 1.4): counts only.

G  generation degradation: a reasoning or message item whose last 4000 characters hold a substring of at least 40
   characters repeated at least 4 times in a row.  The cut-off attempt of an output-limit retry is discarded by the
   frontend and never reaches the rollout, so G here sees completed items only; `output limit:` lines of the service
   log are counted per block as the non-natural-ending signal (reported next to G, not merged into it).
T  tool loop: calls with the same name, the same arguments (whitespace normalised) and the same output, at least
   3 in a row.
R  reply repetition: one visible message in which the same line occurs at least 5 times, leaving out lines of at most
   3 non-blank characters, code fences and separator lines (`---`).

    python3 -m tools.tuning.loop_stats --scene .tmp/sampling-dim-1024/run/scenes/<condition> [...]
"""
import argparse
import collections
import json
from pathlib import Path
import re

TAIL, MIN_UNIT, MIN_REPEATS = 4000, 40, 4
TOOL_RUN, LINE_REPEATS, SHORT_LINE = 3, 5, 3


def repeated_tail(text):
    """True when the last TAIL characters end in or contain a MIN_UNIT+ substring repeated MIN_REPEATS+ times in a row."""
    tail = text[-TAIL:]
    n = len(tail)
    if n < MIN_UNIT * MIN_REPEATS:
        return False
    grams = collections.Counter(tail[i:i + MIN_UNIT] for i in range(n - MIN_UNIT + 1))
    if max(grams.values()) < MIN_REPEATS:
        return False
    for period in range(MIN_UNIT, n // MIN_REPEATS + 1):
        run = 0
        for a, b in zip(tail, tail[period:]):
            run = run + 1 if a == b else 0
            if run >= period * (MIN_REPEATS - 1):
                return True
    return False


def repeated_lines(text):
    """True when one counted line occurs LINE_REPEATS+ times in the reply."""
    counts = collections.Counter()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('```'):
            continue
        if len(re.sub(r'\s', '', stripped)) <= SHORT_LINE or re.fullmatch(r'[-=*_#\s]{3,}', stripped):
            continue
        counts[stripped] += 1
    return bool(counts) and max(counts.values()) >= LINE_REPEATS


def tool_loops(calls):
    """Number of runs of TOOL_RUN+ identical (name, arguments, output) calls in a row; calls = [(name, args, output)]."""
    runs, previous, length = 0, None, 0
    for name, arguments, output in calls:
        key = (name, ' '.join(str(arguments).split()), output)
        length = length + 1 if key == previous else 1
        runs += length == TOOL_RUN
        previous = key
    return runs


def rollout_stats(path):
    """Counts of one Codex rollout: requests (token_usage_record rows), G, T, R events and their items."""
    calls, outputs, order = {}, {}, []
    stats = {'requests': 0, 'G': 0, 'T': 0, 'R': 0}
    for line in Path(path).read_text(errors='replace').splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        payload = event.get('payload') or {}
        kind = payload.get('type')
        if event.get('type') == 'token_usage_record':
            stats['requests'] += 1
        elif event.get('type') != 'response_item':
            continue
        elif kind == 'reasoning':
            text = ''.join(part.get('text', '') for part in payload.get('content') or [])
            stats['G'] += repeated_tail(text)
        elif kind == 'message' and payload.get('role') == 'assistant':
            text = ''.join(part.get('text', '') for part in payload.get('content') or [])
            stats['G'] += repeated_tail(text)
            stats['R'] += repeated_lines(text)
        elif kind == 'function_call':
            calls[payload.get('call_id')] = (payload.get('name'), payload.get('arguments'))
            order.append(payload.get('call_id'))
        elif kind == 'function_call_output':
            outputs[payload.get('call_id')] = payload.get('output')
    stats['T'] = tool_loops([(*calls[c], outputs.get(c)) for c in order])
    return stats


def instance_rollout(instance_dir):
    results = json.loads((Path(instance_dir) / 'run/results.json').read_text())
    result = results[0]
    root = (result.get('runtime_result') or {}).get('threadId')
    return next((h['path'] for h in (result.get('cost') or {}).get('histories') or [] if h.get('thread_id') == root), None)


def summarize(rows):
    """Per condition: positive-session ratio and events per 100 requests, 95% upper bound 3/requests when all zero."""
    requests = sum(r['requests'] for r in rows)
    out = {'sessions': len(rows), 'requests': requests}
    for key in 'GTR':
        events = sum(r[key] for r in rows)
        out[key] = {'events': events, 'positive_sessions': sum(bool(r[key]) for r in rows),
                    'per_100_requests': 100 * events / requests if requests else None,
                    **({'upper_95_per_100': 300 / requests} if requests and not events else {})}
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scene', type=Path, action='append', required=True)
    args = parser.parse_args()
    report = {}
    for scene in args.scene:
        rows = []
        for folder in sorted(scene.glob('codex-strata-high-a*')):
            path = instance_rollout(folder)
            rows.append({'instance': folder.name, **(rollout_stats(path) if path and Path(path).is_file()
                                                       else {'requests': 0, 'G': 0, 'T': 0, 'R': 0, 'missing': True})})
        report[scene.name] = {'summary': summarize(rows), 'instances': rows}
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
