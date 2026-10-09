"""Supplement, without replacing, upstream per-round Reviewer measurements."""
import hashlib
import json
from pathlib import Path


TOKEN_KEYS = ('uncached_input', 'cached_input', 'output')


def split_tokens(usage, snake=False):
    keys = ('input_tokens', 'cached_input_tokens', 'output_tokens') if snake else (
        'inputTokens', 'cachedInputTokens', 'outputTokens')
    i, c, o = (usage.get(k) for k in keys)
    valid = lambda n: type(n) is int and n >= 0
    return {'uncached_input': i-c if valid(i) and valid(c) and i >= c else None,
            'cached_input': c if valid(c) and valid(i) and i >= c else None,
            'output': o if valid(o) else None}


def sum_tokens(rows):
    return {k: sum(r[k] for r in rows) if all(r[k] is not None for r in rows) else None
            for k in TOKEN_KEYS}


def collect_cost(record, codex_home):
    """Only inspect this experiment's rollouts and this root's guardian children.

    ARW measurement resets its baseline on followup. Sum its per-round deltas;
    guardian sessions can serve several approvals, so count each last cumulative
    snapshot once. Failed attempts remain in the native histories. Never scan the
    user's global session history or reinterpret upstream score/measurement.
    """
    rounds = [r['measurement'] for r in record.get('revisions', [])] + [record['measurement']]
    root_id = record['runtime_result']['threadId']
    root_seen = False
    faults = []
    guardians = {}
    histories = []
    root_invalid_input = False
    home = Path(codex_home)
    if not (home/'sessions').is_dir():
        faults.append('Experiment sessions directory is missing')
    for path in sorted((home/'sessions').rglob('*.jsonl')):
        try:
            raw = path.read_bytes()
            events = [json.loads(line) for line in raw.splitlines() if line.strip()]
            meta = next(e['payload'] for e in events if e.get('type') == 'session_meta')
        except (OSError, ValueError, StopIteration, KeyError) as exc:
            faults.append(f'{path.name}: {type(exc).__name__}')
            continue
        is_root = meta.get('id') == root_id
        is_guardian = (meta.get('thread_source') == 'guardian_review'
                       and meta.get('parent_thread_id') == root_id)
        if not (is_root or is_guardian):
            continue
        root_seen |= is_root
        contexts = [e['payload'] for e in events if e.get('type') == 'turn_context']
        counts = [e['payload']['info']['total_token_usage'] for e in events
                  if e.get('type') == 'event_msg' and e.get('payload', {}).get('type') == 'token_count'
                  and e['payload'].get('info')]
        calls = [e for e in events if e.get('type') == 'response_item'
                 and e.get('payload', {}).get('type') in ('function_call', 'custom_tool_call',
                                                         'web_search_call', 'tool_search_call')]
        failures = [e for e in events if e.get('type') == 'event_msg'
                    and e.get('payload', {}).get('type') == 'error']
        responses = {e['payload'].get('response_id') for e in events
                     if e.get('type') == 'token_usage_record' and e.get('payload', {}).get('response_id')}
        invalid_input = [e['payload'] for e in events
                         if e.get('type') == 'token_usage_record'
                         and split_tokens(e.get('payload', {}).get('usage', {}), True)['uncached_input'] is None]
        root_invalid_input |= is_root and bool(invalid_input)
        row = {'thread_id': meta.get('id'), 'parent_thread_id': meta.get('parent_thread_id'),
               'guardian': is_guardian, 'provider': meta.get('model_provider'),
               'model': contexts[-1].get('model') if contexts else None,
               'effort': contexts[-1].get('effort') if contexts else None,
               'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
               'raw_cumulative_usage': counts[-1] if counts else None,
               'tokens': split_tokens(counts[-1], True) if counts else dict.fromkeys(TOKEN_KEYS),
               'observed_response_count': len(responses), 'tool_call_count': len(calls),
               'observed_api_errors': failures, 'invalid_input_usage_records': invalid_input}
        if invalid_input:
            # A plausible cumulative snapshot can mask an impossible individual
            # response. Keep raw native usage but never partition that cost.
            row['tokens']['uncached_input'] = row['tokens']['cached_input'] = None
        histories.append(row)
        if is_guardian:
            if row['thread_id'] in guardians:
                faults.append('Duplicate guardian history: ' + str(row['thread_id']))
            guardians[row['thread_id']] = row
    if not root_seen:
        faults.append('Reviewer root history is missing')
    reviewer = sum_tokens([split_tokens(m.get('usage', {})) for m in rounds])
    if root_invalid_input:
        reviewer['uncached_input'] = reviewer['cached_input'] = None
    guardian = sum_tokens([g['tokens'] for g in guardians.values()])
    if faults:
        guardian = dict.fromkeys(TOKEN_KEYS)
    walls = [m.get('wallClockMs') for m in rounds]
    return {'reviewer_rounds': rounds, 'reviewer_tokens': reviewer,
            'guardian_tokens': guardian, 'combined_api_tokens': sum_tokens([reviewer, guardian]),
            'reviewer_active_seconds': sum(walls)/1000 if all(type(w) is int for w in walls) else None,
            'guardian_thread_count': len(guardians), 'histories': histories,
            'unknown_reasons': faults,
            'rpc_failure_count': None,
            'rpc_visibility': 'Original host does not expose every app-server RPC fault to this collector',
            'scope': 'Original Reviewer round deltas plus unique guardian cumulative API usage; engine totals remain separate'}
