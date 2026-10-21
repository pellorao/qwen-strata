"""Unified validity rejudge of the multi-model benchmark v1 instances (rulings in benchmarks/reviewer-suite-v1/rulings.md).

Applied by tools.reviewer.bench_records to every record, so formal scoring (bench_score refuses invalid records) and
the summaries use it, not per-arm scripts. Read-only: the run records under .tmp are never rewritten; the rejudged
verdict and its basis go into the record (`validity.rejudge`, `validity_before_rejudge`).

1. Claude Code killed at the hard limit (ruling 2026-10-21, rule): a run stopped at the hard limit is valid (plan §14).
   A handoff whose stream has no result event has no `server_web_requests` count; it is taken from the streams of every
   segment (assistant `server_tool_use` content blocks and usage.server_tool_use counts, once per message id). With
   none, the handoff counts 0 network requests and is valid when every other check passes; its tokens are unknown
   (not filled in) and its cost comes from the relay or the balance difference (`cost_basis`). A segment killed
   without a result is scanned the same way in an otherwise valid handoff (the result-based count leaves it out).
2. Upstream stream cut with a transparent harness retry (ruling 2026-10-21, user): relay error rows of the Codex arms
   are classified by tools.reviewer.reminder_interrupt, then tools.reviewer.stream_cut; an instance whose only failure
   is relay errors that are all reminder interrupts or stream-cut retries is valid. The cut request's time (its start to
   the retry's start, `excluded_seconds`) is taken out of the handoff whose rollout spans it, its tokens are not in the
   relay usage (checked: a cut row with usage is an error), and cost goes per completed request.

Verdict precedence: void and no-record stay; a Main reclassification (`reclassified`) keeps its verdict and only gains
the classification. A rejudged invalid instance names the failing checks.
"""
import json
from datetime import datetime
from pathlib import Path

from tools.reviewer import reminder_interrupt, stream_cut

CODEX_HANDOFF_OK = ('ended_normally', 'tier_ok', 'model_ok', 'startup_off')
CODEX_HANDOFF_NOT = ('harness_rejected', 'arw_pause', 'limited')


# ---- Claude Code --------------------------------------------------------------------------------------------------

def server_tool_uses(streams):
    """Server-side tool uses (web search / fetch) in Claude Code stream-json files, result events or not: assistant
    content blocks of type server_tool_use, or the larger usage.server_tool_use count of a message (once per id)."""
    blocks, counted = 0, {}
    for stream in streams:
        try:
            lines = Path(stream).read_text(errors='replace').splitlines()
        except OSError:
            continue
        for line in lines:
            if 'server_tool_use' not in line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            message = event.get('message') if isinstance(event.get('message'), dict) else {}
            if event.get('type') != 'assistant':
                continue
            for block in message.get('content') or []:
                if isinstance(block, dict) and block.get('type') == 'server_tool_use':
                    blocks += 1
            usage = (message.get('usage') or {}).get('server_tool_use') or {}
            n = sum(v for v in usage.values() if isinstance(v, (int, float)) and not isinstance(v, bool))
            mid = message.get('id') or f'line-{len(counted)}'
            counted[mid] = max(counted.get(mid, 0), n)
    return max(blocks, sum(counted.values()))


def claude_other_checks(checks):
    """Every Claude Code validity check other than the network count (claude_scenario.checks)."""
    failed = [name for name in ('model_match', 'tier_ok', 'ended_normally') if checks.get(name) is not True]
    if checks.get('sandbox_failures'):
        failed.append('sandbox_failures')
    if 'prompts_ok' in checks or 'output_limits_ok' in checks:
        failed += [n for n in ('prompts_ok', 'output_limits_ok') if checks.get(n) is not True]
    elif checks.get('startup_prompt_off') is not True:
        failed.append('startup_prompt_off')
    return failed


def claude_handoff(checks, result, streams):
    """(valid, basis) of one Claude Code handoff under ruling 1."""
    summary = (result or {}).get('summary') or {}
    killed = bool((result or {}).get('hard_interrupt')) or checks.get('continuation_stop') == 'hard_limit'
    without = summary.get('segments_without_result') or 0
    original = checks.get('valid') is True
    basis = {'original_valid': original, 'hard_limit': killed, 'segments_without_result': without}
    if killed or without or checks.get('server_web_requests') is None:
        basis['stream_server_tool_uses'] = server_tool_uses(streams)
    if original:
        if basis.get('stream_server_tool_uses'):
            return False, {**basis, 'rule': 'server tool use in a segment without result (ruling 2026-10-21)'}
        return True, basis
    failed = claude_other_checks(checks)
    if (checks.get('server_web_requests') is None and killed and not summary.get('result_event')
            and basis.get('stream_server_tool_uses') == 0 and not failed):
        return True, {**basis, 'rule': 'hard-limit kill without result event, no server_tool_use: 0 network requests, '
                                        'valid (ruling 2026-10-21); tokens unknown, cost from relay or balance'}
    if checks.get('server_web_requests') not in (0, None):
        failed.append('server_web_requests')
    elif checks.get('server_web_requests') is None and basis.get('stream_server_tool_uses') != 0:
        failed.append('server_web_requests')
    return False, {**basis, 'failed': failed or ['checks.valid false']}


def claude_rejudge(folder, instance):
    """Per-handoff ruling-1 verdicts of a Claude Code instance; None without handoffs."""
    from tools.reviewer.claude_headless import segment_streams
    out = []
    for k, h in enumerate((instance or {}).get('handoffs') or []):
        hdir = Path(folder) / f'h{k}'
        result = json.loads((hdir / 'result.json').read_text()) if (hdir / 'result.json').is_file() else {}
        valid, basis = claude_handoff(h.get('checks') or {}, result, [s for s in segment_streams(hdir) if s.is_file()])
        no_result = not ((result.get('summary') or {}).get('result_event'))
        out.append({'k': k, 'valid': valid, **basis, 'tokens_known': not no_result,
                    'cost_basis': ('no result event: cost from relay or balance difference (ruling 2026-10-21)'
                                   if no_result else 'stream result total_cost_usd'
                                   + (' (lower bound: a segment without result)' if basis['segments_without_result'] else ''))})
    return out or None


# ---- Codex --------------------------------------------------------------------------------------------------------

def rollout_span(session):
    """(first, last) epoch seconds of a Codex rollout, or None."""
    if not session or not Path(session).is_file():
        return None
    times = []
    for line in Path(session).read_text(errors='replace').splitlines():
        try:
            stamp = json.loads(line).get('timestamp')
        except ValueError:
            continue
        if stamp:
            times.append(datetime.fromisoformat(stamp.replace('Z', '+00:00')).timestamp())
    return (min(times), max(times)) if times else None


def codex_other_checks(instance):
    """Every Codex validity check other than relay errors (steer.py / run_one.checks), failing names."""
    failed = []
    if instance.get('arw_measure_exit') != 0:
        failed.append('arw_measure_exit')
    for name in ('recovery_required', 'halt', 'limited', 's2_paused'):
        if instance.get(name):
            failed.append(name)
    if not instance.get('prep_copy_ok'):
        failed.append('prep_copy_ok')
    handoffs = instance.get('handoffs') or []
    if not handoffs:
        failed.append('no handoffs')
    for k, h in enumerate(handoffs):
        c = h.get('checks') or {}
        failed += [f'h{k}: {n}' for n in CODEX_HANDOFF_OK if c.get(n) is not True]
        failed += [f'h{k}: {n}' for n in CODEX_HANDOFF_NOT if c.get(n)]
        if c.get('web_search_calls') != 0:
            failed.append(f'h{k}: web_search_calls')
    return failed


def codex_rejudge(folder, instance):
    """Ruling-2 classification of a Codex instance with a relay log; None without one (the Strata Codex arm talks to
    Strata directly)."""
    run = Path(folder) / 'run'
    if not (run / 'relay').is_dir() or not instance:
        return None
    sessions = [h.get('session') for h in instance.get('handoffs') or []]
    ri = reminder_interrupt.classify_instance(run, sessions)
    exempt = ri['reminder_interrupts']
    sc = stream_cut.classify_instance(run, sessions, skip={x['row'] for x in exempt})
    cuts = sc['stream_cut_retries']
    rows = {}
    for f in sorted((run / 'relay').glob('*.jsonl')):
        for line in f.read_text().splitlines():
            row = json.loads(line)
            rows[row.get('n')] = row
    for cut in cuts:
        if (rows.get(cut['row']) or {}).get('usage'):
            raise ValueError(f'{folder}: stream-cut row {cut["row"]} carries usage; its tokens would be counted')
    recorded = sum((h.get('checks') or {}).get('relay_errors') or 0 for h in instance.get('handoffs') or [])
    residual = ri['relay_errors'] - len(cuts)
    failed = codex_other_checks(instance)
    if recorded != ri['errors']:
        failed.append(f'relay errors recorded {recorded} differ from the relay log {ri["errors"]}')
    if residual:
        failed.append(f'relay errors {residual} (not reminder interrupts or stream-cut retries)')
    spans = [rollout_span(s) for s in sessions]
    excluded = {}
    for cut in cuts:
        start = rows[cut['row']]['started_at']
        ks = [k for k, span in enumerate(spans) if span and span[0] - 1 <= start <= span[1] + 1]
        if len(ks) != 1:
            raise ValueError(f'{folder}: stream-cut row {cut["row"]} lies in {len(ks)} handoff rollouts')
        excluded[ks[0]] = round(excluded.get(ks[0], 0) + cut['excluded_seconds'], 3)
    return {'errors': ri['errors'], 'reminder_interrupts': exempt, 'stream_cut_retries': cuts,
            'stream_cut_rejected': sc['rejected'], 'relay_errors_after': residual, 'failed': failed,
            'valid': not failed, 'excluded_seconds': excluded}


# ---- record update ------------------------------------------------------------------------------------------------

def apply(record, folder, instance):
    """Rejudge a bench_records record in place (read-only on disk). Returns the record."""
    status = record['validity']['status']
    before = {'valid': record['valid'], 'status': status, 'source': record['validity'].get('source'),
              'reasons': record['validity'].get('reasons')}
    record['validity_before_rejudge'] = before
    record['seconds_adjustment'] = None
    if status in ('void', 'no-record', 'running'):
        record['validity']['rejudge'] = {'applied': False, 'why': status}
        return record
    if record['harness'] == 'claude-code':
        verdicts = claude_rejudge(folder, instance)
        if verdicts is None:
            record['validity']['rejudge'] = {'applied': False, 'why': 'no handoffs'}
            return record
        fault = status == 'harness-fault'
        valid = all(v['valid'] for v in verdicts) and not fault
        record['validity']['rejudge'] = {'applied': True, 'rule': 'Claude Code hard-limit kill (ruling 2026-10-21)',
                                         'handoffs': verdicts}
        for v, h in zip(verdicts, record['handoffs']):
            h['tokens_known'] = v['tokens_known']
            h['cost_basis'] = v['cost_basis']
        if fault:
            return record
        if not valid:  # the rejudge's failing checks (the earlier list named every false check)
            record['validity']['reasons'] = [f"h{v['k']}: {', '.join(v.get('failed') or [v.get('rule', '')])}"
                                             for v in verdicts if not v['valid']]
        if valid != record['valid']:
            record['valid'] = valid
            record['validity'].update(status='valid' if valid else 'invalid',
                                      reasons=[] if valid else record['validity']['reasons'],
                                      source='bench_validity rejudge (Claude Code hard limit, ruling 2026-10-21)')
        return record
    verdict = codex_rejudge(folder, instance)
    if verdict is None:
        record['validity']['rejudge'] = {'applied': False, 'why': 'no relay log'}
        return record
    record['validity']['rejudge'] = {'applied': True, 'rule': 'reminder interrupt + stream-cut retry (rulings '
                                     '2026-10-20, 2026-10-21)', **verdict}
    for k, seconds in verdict['excluded_seconds'].items():
        h = record['handoffs'][k]
        if h.get('seconds') is not None:
            h['seconds_before_rejudge'] = h['seconds']
            h['seconds'] = round(h['seconds'] - seconds, 3)
            h['excluded_seconds'] = seconds
    if verdict['excluded_seconds']:
        record['seconds_adjustment'] = {f'h{k}': -s for k, s in verdict['excluded_seconds'].items()}
    if status != 'invalid' and status != 'valid':
        return record
    reclassified = before['source'] == 'instance.json reclassified'
    if not reclassified and not verdict['valid']:
        record['validity']['reasons'] = verdict['failed']
    if reclassified or verdict['valid'] == record['valid']:
        if reclassified and verdict['valid'] != record['valid']:
            record['validity']['rejudge']['note'] = 'Main reclassification kept; the mechanical rejudge differs'
        return record
    record['valid'] = verdict['valid']
    record['validity'].update(status='valid' if verdict['valid'] else 'invalid', reasons=verdict['failed'],
                              source='bench_validity rejudge (reminder interrupt / stream-cut retry)')
    return record


# ---- cells and the main statistic ---------------------------------------------------------------------------------

def rank_cells(records, main_n=5):
    """Per cell (arm, scenario, config, supplementary label): valid instances ranked by start time (attempt number
    when the start is unknown). Not merged cells: the first main_n valid ones form the main statistic (later ones,
    reruns included, are supplementary rows). Merged cells (DeepSeek C': medium pooled into high): every valid
    instance is in the main statistic, the first main_n form the consistency row."""
    cells = {}
    for r in records:
        r['valid_rank'] = r['main_statistic'] = r['first_n'] = None
        if r['valid']:
            cells.setdefault(cell_key(r), []).append(r)
    for key, group in cells.items():
        group.sort(key=lambda r: (r.get('started') is None, r.get('started') or 0, r['attempt']))
        pooled = any(r.get('pooled') for r in group)
        for i, r in enumerate(group, 1):
            r['valid_rank'] = i
            r['first_n'] = i <= main_n
            r['main_statistic'] = pooled or i <= main_n
            r['cell'] = '/'.join(str(x) for x in key)
            r['cell_pooled'] = pooled
    return records


def cell_key(record):
    return (record['arm'], record['scenario'], record['config'], record.get('supplementary_label') or '')


def first_n(records, valid_of, main_n=5):
    """{cell: [ids of the first main_n valid instances by start time]} under the verdict valid_of(record)."""
    cells = {}
    for r in records:
        if valid_of(r):
            cells.setdefault('/'.join(str(x) for x in cell_key(r)), []).append(r)
    return {cell: [r['id'] for r in sorted(group, key=lambda r: (r.get('started') is None, r.get('started') or 0,
                                                                  r['attempt']))[:main_n]]
            for cell, group in cells.items()}


# ---- cost by balance difference -----------------------------------------------------------------------------------

def stamp(text):
    return datetime.fromisoformat(text).timestamp()


def balance_cost(readings, runs, target):
    """Cost of `target` from account balance readings [(t, balance)] and runs {name: (start, end, cost or None)}: the
    smallest window between two readings that holds the target and every run overlapping the window whole, minus the
    known cost of the other runs in it. None when another run in the window has no known cost or no window exists."""
    readings = sorted(readings)
    start, end = runs[target][:2]
    members = {target}
    while True:
        before = [r for r in readings if r[0] <= start]
        after = [r for r in readings if r[0] >= end]
        if not before or not after:
            return None
        t0, t1 = before[-1][0], after[0][0]
        inside = {n for n, (s, e, _) in runs.items() if s < t1 and e > t0}
        if inside <= members:
            break
        members |= inside
        start = min(runs[n][0] for n in members)
        end = max(runs[n][1] for n in members)
    others = [runs[n][2] for n in members if n != target]
    if any(c is None for c in others):
        return None
    return {'cost': round(before[-1][1] - after[0][1] - sum(others), 4), 'window': [t0, t1],
            'balance': [before[-1][1], after[0][1]], 'others': sorted(members - {target})}


def deepseek_balance_cost(scene_name, instance_name, root=None):
    """balance_cost() of one DeepSeek instance from the arm's schedule.jsonl launches / done events (CNY at request
    time) and the balance read before each launch."""
    root = Path(root or Path(__file__).resolve().parents[2] / '.tmp/bench-deepseek-1020/r1')
    events = [json.loads(line) for line in (root / 'schedule.jsonl').read_text().splitlines()]
    starts, runs, readings = {}, {}, []
    for e in events:
        key = f"{e.get('scen')}/{e.get('out')}"
        if e.get('event') == 'launch':
            starts[key] = stamp(e['t'])
            if e.get('balance') is not None:
                readings.append((stamp(e['t']), e['balance']))
        elif e.get('event') == 'done' and key in starts:
            known = e.get('cny_request_time') if sum(e.get('tokens') or [0]) else None
            runs[key] = (starts[key], stamp(e['t']), known)
    target = f'{scene_name}/{instance_name}'
    if target not in runs:
        return None
    runs[target] = (*runs[target][:2], None)
    out = balance_cost(readings, runs, target)
    return out and {**out, 'currency': 'CNY', 'basis': 'balance read before each launch (schedule.jsonl), minus '
                                                        'the per-request cost of the other instances in the window'}


def main():
    import argparse
    from tools.reviewer import bench_records
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=Path, required=True, help='JSON result (validity / time changes, first-5 sets)')
    parser.add_argument('--records', type=Path, help='also write the rejudged records (JSON Lines)')
    parser.add_argument('--data-root', type=Path, help='checkout holding .tmp (default: this one)')
    args = parser.parse_args()
    records = bench_records.all_records(data_root=args.data_root)
    changed, timed = [], []
    for r in records:
        before = r['validity_before_rejudge']
        if before['valid'] != r['valid']:
            row = {'id': r['id'], 'before': before, 'after': {'valid': r['valid'], 'status': r['validity']['status'],
                                                              'source': r['validity'].get('source')},
                   'rejudge': r['validity'].get('rejudge'), 'started': r.get('started')}
            if r['arm'] == 'deepseek-claude':
                row['cost_balance_difference'] = deepseek_balance_cost(
                    *r['dir'].split('/')[-2:], root=Path(args.data_root or bench_records.ROOT) / bench_records.LAYOUT[r['arm']][0])
            changed.append(row)
        if r.get('seconds_adjustment'):
            timed.append({'id': r['id'], 'valid': r['valid'], 'seconds_adjustment': r['seconds_adjustment'],
                          'seconds_after': r['seconds']})
    old = first_n(records, lambda r: r['validity_before_rejudge']['valid'])
    new = first_n(records, lambda r: r['valid'])
    cells = [{'cell': c, 'before': old.get(c, []), 'after': new.get(c, [])}
             for c in sorted(set(old) | set(new)) if old.get(c, []) != new.get(c, [])]
    by_attempt = {}
    for r in records:
        if r['valid']:
            by_attempt.setdefault(r['cell'], []).append(r)
    order_differs = [{'cell': c, 'by_attempt': [x['id'] for x in sorted(g, key=lambda x: x['attempt'])][:5],
                      'by_start': new.get(c, [])}
                     for c, g in sorted(by_attempt.items())
                     if [x['id'] for x in sorted(g, key=lambda x: x['attempt'])][:5] != new.get(c, [])]
    rejudged = [r for r in records if (r['validity'].get('rejudge') or {}).get('applied')]
    killed = [{'id': r['id'], 'k': h['k'], 'valid': h['valid'], 'original_valid': h['original_valid'],
               'segments_without_result': h['segments_without_result'],
               'stream_server_tool_uses': h.get('stream_server_tool_uses')}
              for r in rejudged if r['harness'] == 'claude-code' for h in r['validity']['rejudge']['handoffs']
              if h['hard_limit'] or h['segments_without_result']]
    cuts = [{'id': r['id'], 'valid': r['valid'], 'stream_cut_retries': r['validity']['rejudge']['stream_cut_retries'],
             'stream_cut_rejected': r['validity']['rejudge']['stream_cut_rejected'],
             'reminder_interrupts': len(r['validity']['rejudge']['reminder_interrupts'])}
            for r in rejudged if r['harness'] == 'codex' and (r['validity']['rejudge']['stream_cut_retries']
                                                              or r['validity']['rejudge']['stream_cut_rejected'])]
    notes = [{'id': r['id'], 'note': r['validity']['rejudge']['note'], 'failed': r['validity']['rejudge']['failed']}
             for r in rejudged if r['validity']['rejudge'].get('note')]
    by_arm = {}
    for r in records:
        a = by_arm.setdefault(r['arm'], {'instances': 0, 'rejudged': 0, 'valid_before': 0, 'valid_after': 0})
        a['instances'] += 1
        a['rejudged'] += bool((r['validity'].get('rejudge') or {}).get('applied'))
        a['valid_before'] += bool(r['validity_before_rejudge']['valid'])
        a['valid_after'] += bool(r['valid'])
    result = {'by_arm': by_arm, 'validity_changed': changed, 'time_changed': timed, 'first5_changed': cells,
              'first5_attempt_vs_start_order_differs': order_differs, 'hard_limit_handoffs': killed,
              'stream_cuts': cuts, 'reclassification_kept_against_rejudge': notes,
              'rule': 'bench_validity: rulings 2026-10-21 (Claude Code hard limit; stream-cut retry) and 2026-10-20 '
                      '(reminder interrupt); first 5 = valid instances by start time per cell'}
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n')
    if args.records:
        args.records.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records))
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in result.items() if k != 'rule'},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
