"""Normalized instance records of the multi-model benchmark v1 (benchmarks/multi-model-v1/plan.md), all arms.

The arms keep their instances in different layouts: the OpenAI arm (Codex + ARW runtime, run_one.py) writes
instance.json with run-level validity, reclassifications and a /tmp prep copied back; the Claude Code arms (Anthropic
and Strata, claude_scenario) write instance.json with per-handoff checks and the report under h<k>/outputs; the Strata
Codex arm (run_codex_strata.py) writes no instance.json, its verdict is the scheduler's `done` event and its handoffs
are ARW's run/results.json. One record per instance directory, with the same fields for every arm:

  id, arm, harness, model, model_family, style_family, effort, config (plan §2 number), config_label, scenario,
  plan, attempt, started, dir; valid and validity {status, reasons}; pause_known, pause_count, pause_events,
  continue_count, pause_note; time_limit_seconds (the T the instance ran with) and its source; handoffs (k, instanceId,
  sub-scenario, report path found by sha, report_sha256, report_ok, seconds, tokens, tool_calls, thread or session);
  identity (the plan's Main identity and the prep's); original_prepared; repository_check (what the Reviewer saw);
  plus the benchmark_summary fields, score fields left null until scored.

An instance without a recorded pause field gets pause_known false (and pause_count null): an old record cannot tell
"no pause" from "not recorded"; pause_note says what the harness of that time would have done.

    python3 -m tools.reviewer.bench_records --all [--out records.jsonl]
    python3 -m tools.reviewer.bench_records --arm openai --scenario code-spec-v5 --dir .tmp/bench-openai-1020/cs
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLANS = ROOT / 'benchmarks/multi-model-v1/scenarios'
SCENARIOS = ('commit-audit-v3', 'code-spec-v5', 'code-standards-v5.1', 'spec-readiness-v4.3')
# Default layout (arm -> run root and scenario -> scene directory); the voided earlier rounds are left out.
LAYOUT = {
    'openai': ('.tmp/bench-openai-1020', {'commit-audit-v3': 'ca', 'code-spec-v5': 'cs', 'code-standards-v5.1': 'cstd',
                                          'spec-readiness-v4.3': 'sr'}),
    'anthropic': ('.tmp/bench-anthropic-1019', {'commit-audit-v3': 'ca-r2', 'code-spec-v5': 'cs-r1',
                                                'code-standards-v5.1': 'cstd-r1', 'spec-readiness-v4.3': 'sr-r1'}),
    'strata-claude': ('.tmp/bench-strata-1019', {'commit-audit-v3': 'ca-r2', 'code-spec-v5': 'cs-r2',
                                                 'code-standards-v5.1': 'cstd-r2', 'spec-readiness-v4.3': 'sr-r2'}),
    'strata-codex': ('.tmp/bench-strata-1019', {'commit-audit-v3': 'ca-codex', 'code-spec-v5': 'cs-codex',
                                                'code-standards-v5.1': 'cstd-codex', 'spec-readiness-v4.3': 'sr-codex'}),
}
HARNESS = {'openai': 'codex', 'strata-codex': 'codex', 'anthropic': 'claude-code', 'strata-claude': 'claude-code'}
# Directory model key -> (plan §2 first configuration of its low/medium/high row, model family, report style family).
MODELS = {'sol': (1, 'gpt-6.1-sol', 'openai'), 'luna': (4, 'gpt-6-luna', 'openai'),
          'codex-strata': (10, 'strata', 'strata'), 'opus': (13, 'opus', 'anthropic'),
          'sonnet': (16, 'sonnet', 'anthropic'), 'haiku': (19, 'haiku', 'anthropic'), 'strata': (25, 'strata', 'strata')}
EFFORTS = ('low', 'medium', 'high')
DIR_NAME = re.compile(r'^(?P<model>[a-z-]+?)-(?P<effort>low|medium|high)-a(?P<attempt>\d+)$')
SUB_SCENARIO = re.compile(r'^(.+)-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-instance-\d+$')
PREPARED = 'prep/arw/.tmp/codex/*/_reviewer-cap/runs/*/prepared.json'
SCORE_FIELDS = {'score': None, 'raw_score': None, 'format_penalty': None, 'repairs': None}


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    path = Path(path)
    return json.loads(path.read_text()) if path.is_file() else None


def sub_scenario(instance_id):
    match = SUB_SCENARIO.match(instance_id or '')
    return match.group(1) if match else None


def void_marker(folder, instance):
    """The void decision of an instance: void.json (any arm) or the `void` field of the OpenAI instance.json."""
    marker = load(folder / 'void.json')
    if marker is None and isinstance(instance, dict) and isinstance(instance.get('void'), dict):
        marker = instance['void']
    if marker is None or marker.get('void') is False:
        return None
    return marker


def time_limit(folder, recorded=None):
    """T as the instance ran (its own prep's selection), cross-checked against an arm's own record of it."""
    selection = load(folder / 'prep/selection-source.json') or {}
    value = selection.get('review_time_limit_seconds')
    if recorded is not None and value is not None and recorded != value:
        raise ValueError(f'{folder}: recorded time limit {recorded} differs from the prep selection {value}')
    if value is not None:
        return value, 'prep/selection-source.json review_time_limit_seconds'
    if recorded is not None:
        return recorded, 'instance.json time_limit_seconds'
    return None, 'no time limit (scenario without T)'


def report_location(expected_sha, *candidates):
    """First existing candidate path whose content has the recorded sha256 (report_ok), else the first that exists."""
    found = None
    for path in candidates:
        if path is None:
            continue
        for one in (sorted(Path(path).parent.glob(Path(path).name)) if any(c in str(path) for c in '*?') else [Path(path)]):
            if one.is_file():
                if expected_sha and sha256_file(one) == expected_sha:
                    return str(one), True
                found = found or str(one)
    return found, False


def tree_differences(recorded, fresh):
    """Files of two scenario repository manifests that differ, .git and .tmp left out (git bytes do not reproduce)."""
    keep = lambda tree: {k: v for k, v in tree.items() if not k.startswith(('.git/', '.tmp/')) and k != '.git'}
    a, b = keep(recorded), keep(fresh)
    return sorted(set(a) ^ set(b)) + sorted(k for k in set(a) & set(b) if a[k] != b[k])


def pause_fields(events, continues, note):
    if events is None:
        return {'pause_known': False, 'pause_count': None, 'pause_events': None, 'continue_count': continues,
                'pause_note': note}
    return {'pause_known': True, 'pause_count': len(events), 'pause_events': events, 'continue_count': continues,
            'pause_note': None}


def base(arm, scenario, folder):
    match = DIR_NAME.match(folder.name)
    if not match or match.group('model') not in MODELS:
        raise ValueError(f'{folder}: not an instance directory name')
    first, family, style = MODELS[match.group('model')]
    effort = match.group('effort')
    plan = PLANS / f'{scenario}.json'
    record = {'id': f'{arm}/{scenario}/{folder.name}', 'arm': arm, 'harness': HARNESS[arm],
              'model_family': family, 'style_family': style, 'effort': effort,
              'config': first + EFFORTS.index(effort), 'config_label': f'{family}-{effort}', 'scenario': scenario,
              'plan': str(plan.relative_to(ROOT)), 'plan_sha256_now': sha256_file(plan),
              'attempt': int(match.group('attempt')), 'dir': str(folder.relative_to(ROOT)) if folder.is_relative_to(ROOT) else str(folder)}
    prep = load(folder / 'prep/preparation.json') or {}
    record['identity'] = {'plan_codex_thread_id': json.loads(plan.read_text())['codex_thread_id'],
                          'prep_session_id': (prep.get('identity') or {}).get('sessionId')}
    originals = sorted(folder.glob(PREPARED))
    record['original_prepared'] = str(originals[0]) if len(originals) == 1 else None
    return record


def validity(status, reasons, source):
    return {'valid': status == 'valid', 'validity': {'status': status, 'reasons': reasons, 'source': source}}


def openai_record(arm, scenario, folder):
    record = base(arm, scenario, folder)
    instance = load(folder / 'instance.json')
    void = void_marker(folder, instance)
    if void is not None:
        record.update(validity('void', [void.get('reason')], 'void.json / instance.json void'))
    elif instance is None:
        record.update(validity('no-record', ['no instance.json (stopped before its record was written)'], 'directory'))
    elif isinstance(instance.get('reclassified'), dict):
        verdict = instance['reclassified']
        record.update(validity('valid' if verdict.get('valid') else 'invalid', [verdict.get('by')],
                               'instance.json reclassified'))
    else:
        reasons = [f"h{k}: {name}" for k, h in enumerate(instance.get('handoffs') or [])
                   for name, value in (h.get('checks') or {}).items() if value is False and name != 'valid']
        record.update(validity('valid' if instance.get('valid') else 'invalid', reasons, 'instance.json valid'))
    instance = instance or {}
    record['started'] = instance.get('started')
    record['time_limit_seconds'], record['time_limit_source'] = time_limit(folder, instance.get('time_limit_seconds'))
    handoff_list = instance.get('handoffs') or []
    if 'arw_pause_events' in instance:
        record.update(pause_fields(instance['arw_pause_events'], instance.get('continue_count'), None))
    elif handoff_list and all('arw_pause_events' in h for h in handoff_list):
        record.update(pause_fields([e for h in handoff_list for e in h['arw_pause_events']],
                                   sum(h.get('continue_count') or 0 for h in handoff_list), None))
    else:
        record.update(pause_fields(None, None, f"run_one before the S2 continue path (arw_pause={instance.get('arw_pause')}, "
                                               f"s2_paused={instance.get('s2_paused')}): "
                                               'a pause left the run waiting (s2_paused), so a completed run had none'))
    location = load(folder / 'prep-location.json') or {}
    copies = location.get('reports') or {}
    manifest = load(folder / 'scenario-copies.json') or {}
    handoffs = []
    for k, h in enumerate(instance.get('handoffs') or []):
        iid = h['instanceId']
        mapped = None
        if location.get('prep') and str(h.get('report', '')).startswith(location['prep']):
            mapped = location['copied_to'] + h['report'][len(location['prep']):]
        path, ok = report_location(h.get('report_sha256'), (copies.get(iid) or {}).get('copy'), mapped, h.get('report'))
        handoffs.append({'k': k, 'instanceId': iid, 'sub_scenario': sub_scenario(iid), 'report': path, 'report_ok': ok,
                         'report_sha256': h.get('report_sha256'), 'seconds': h.get('reviewer_active_seconds'),
                         'tokens': h.get('tokens'), 'tool_calls': h.get('tool_calls'), 'thread_id': h.get('thread_id'),
                         'session': h.get('session'), 'pause_events': h.get('arw_pause_events'),
                         'models_returned': (h.get('checks') or {}).get('models_returned'),
                         'service_tiers': (h.get('checks') or {}).get('service_tiers')})
    record['handoffs'] = handoffs
    record['repository_manifest'] = {'kind': 'scenario-copies.json', 'entries': len(manifest)} if manifest else None
    return record


def claude_record(arm, scenario, folder):
    from tools.reviewer.claude_headless import stream_summary
    record = base(arm, scenario, folder)
    instance = load(folder / 'instance.json')
    void = void_marker(folder, instance)
    handoffs, reasons = [], []
    for k, h in enumerate((instance or {}).get('handoffs') or []):
        checks = h.get('checks') or {}
        out = folder / f'h{k}'
        if checks.get('sandbox_failures') is None:
            # Records before 6038d3a have no sandbox count: recount it from the kept streams (all segments).
            streams = sorted(out.glob('stream*.jsonl'))
            sandbox, sandbox_source = (stream_summary(streams)['sandbox_failures'] if streams else None), 'recounted from streams'
        else:
            sandbox, sandbox_source = checks['sandbox_failures'], 'instance.json checks'
        if checks.get('valid') is not True:
            reasons += [f'h{k}: {name}' for name, value in checks.items() if value is False and name != 'valid'] or [f'h{k}: not valid']
        if sandbox:
            reasons.append(f'h{k}: sandbox_failures {sandbox} ({sandbox_source}; harness fault, plan §14.1 L519-525)')
        staged = (h.get('staging') or {}).get('report')
        path, ok = report_location(h.get('report_sha256'), out / 'outputs' / staged if staged else None)
        result = load(out / 'result.json') or {}
        summary = result.get('summary') or {}
        continuation = h.get('continuation') or {}
        handoffs.append({'k': k, 'instanceId': h['instanceId'], 'sub_scenario': sub_scenario(h['instanceId']),
                         'report': path, 'report_ok': ok, 'report_exists': h.get('report_exists'),
                         'report_sha256': h.get('report_sha256'), 'seconds': h.get('wall_seconds'),
                         'tokens': h.get('engine_tokens'), 'api_usage': summary.get('usage'),
                         'cost_usd': summary.get('total_cost_usd'), 'tool_calls': None,
                         'session': continuation.get('session_id'), 'pause_events': continuation.get('arw_pause_events'),
                         'sandbox_failures': sandbox, 'sandbox_source': sandbox_source,
                         'continuation_stop': checks.get('continuation_stop'),
                         'models_returned': checks.get('models_returned'), 'service_tiers': checks.get('service_tiers'),
                         'files_before': str(out / 'files-before.json') if (out / 'files-before.json').is_file() else None,
                         'spill_files': read_spills(out)})
    if void is not None:
        record.update(validity('void', [void.get('reason')], 'void.json'))
    elif instance is None:
        record.update(validity('no-record', ['no instance.json'], 'directory'))
    else:
        record.update(validity('invalid' if reasons else 'valid', reasons, 'instance.json handoff checks + sandbox count'))
        if any(h['sandbox_failures'] for h in handoffs):
            record['validity']['status'] = 'harness-fault'
    instance = instance or {}
    record['started'] = None
    record['time_limit_seconds'], record['time_limit_source'] = time_limit(folder)
    if 'arw_pause_events' in instance:
        record.update(pause_fields(instance['arw_pause_events'], instance.get('continue_count'), None))
    else:
        record.update(pause_fields(None, None, 'claude_headless before execute_continued: early exits were not '
                                               'continued, so no ARW pause point could be reached'))
    record['handoffs'] = handoffs
    record['repository_manifest'] = {'kind': 'h<k>/files-before.json'} if any(h['files_before'] for h in handoffs) else None
    return record


def read_spills(out):
    """Kept tool-output files Claude Code spilled (large outputs saved under tool-results/) that the session opened with
    its Read tool: only Read shows their line numbers, so only these can be what a report cites (repair (d))."""
    kept = {p.name: p for p in sorted(out.glob('session-files/*/*/tool-results/*')) if p.is_file()}
    opened = set()
    for stream in sorted(out.glob('stream*.jsonl')):
        for line in stream.read_text(errors='replace').splitlines():
            if 'tool-results' not in line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            content = (event.get('message') or {}).get('content')
            for item in content if isinstance(content, list) else []:
                if item.get('type') == 'tool_use' and item.get('name') == 'Read':
                    path = str((item.get('input') or {}).get('file_path', ''))
                    if '/tool-results/' in path:
                        opened.add(path.rsplit('/', 1)[1])
    return [str(kept[name]) for name in sorted(opened) if name in kept]


def strata_codex_record(arm, scenario, folder, done):
    record = base(arm, scenario, folder)
    void = void_marker(folder, None)
    event = done.get(folder.name)
    results = load(folder / 'run/results.json') or []
    if void is not None:
        record.update(validity('void', [void.get('reason')], 'void.json'))
    elif event is None:
        record.update(validity('running', ['no scheduler done event yet'], 'schedule.jsonl'))
    else:
        record.update(validity('valid' if event['kind'] == 'valid' else event['kind'], [] if event['kind'] == 'valid'
                               else [f"scheduler kind {event['kind']}"], 'schedule.jsonl done event'))
    record['started'] = min((r.get('started_at') for r in results if r.get('started_at')), default=None)
    record['time_limit_seconds'], record['time_limit_source'] = time_limit(folder)
    if results and all('arw_pause_events' in r for r in results):
        events = [e for r in results for e in r['arw_pause_events']]
        record.update(pause_fields(events, sum(r.get('continue_count') or 0 for r in results), None))
    else:
        record.update(pause_fields(None, None, 'results.json without arw_pause_events'))
    reports = sorted((folder / 'report').glob('*')) if (folder / 'report').is_dir() else []
    handoffs = []
    for k, r in enumerate(results):
        path, ok = report_location(r.get('report_sha256'), r.get('report'), *reports)
        handoffs.append({'k': k, 'instanceId': r['instanceId'], 'sub_scenario': sub_scenario(r['instanceId']),
                         'report': path, 'report_ok': ok, 'report_sha256': r.get('report_sha256'),
                         'seconds': r.get('review_work_seconds'), 'tokens': r.get('engine_tokens'), 'tool_calls': None,
                         'thread_id': (r.get('runtime_result') or {}).get('threadId'),
                         'pause_events': r.get('arw_pause_events')})
    record['handoffs'] = handoffs
    manifest = load(folder / 'scenario-copies.json')
    record['repository_manifest'] = {'kind': 'scenario-copies.json', 'entries': len(manifest)} if manifest else None
    return record


def summary_fields(record):
    """The benchmark_summary record fields that the instance records give (unknown ones null)."""
    handoffs = record['handoffs']
    seconds = [h.get('seconds') for h in handoffs]
    tokens = [h.get('tokens') for h in handoffs]
    known = handoffs and all(isinstance(t, dict) for t in tokens)
    calls = [h.get('tool_calls') for h in handoffs]
    models = sorted({m for h in handoffs for m in (h.get('models_returned') or [])})
    tiers = {}
    for h in handoffs:
        for tier, n in (h.get('service_tiers') or {}).items():
            tiers[tier] = tiers.get(tier, 0) + n
    return {'instance': record['attempt'],
            'seconds': sum(seconds) if handoffs and None not in seconds else None,
            'tokens': {c: (sum(t.get(c) or 0 for t in tokens) if known else None)
                       for c in ('uncached_input', 'cached_input', 'output')},
            'token_source': None if not known else ('engine log' if record['model_family'] == 'strata' else 'API usage (relay)'),
            'tool_calls': sum(calls) if handoffs and None not in calls else None,
            'cost_usd': None, 'model_ids': models, 'service_tiers': tiers}


def scene_records(arm, scenario, scene):
    scene = Path(scene)
    if not scene.is_dir():
        return []
    done = {}
    if arm == 'strata-codex' and (scene / 'schedule.jsonl').is_file():
        for line in (scene / 'schedule.jsonl').read_text().splitlines():
            event = json.loads(line)
            if event.get('event') == 'done':
                done[event['out']] = event
    out = []
    for folder in sorted(p for p in scene.iterdir() if p.is_dir() and DIR_NAME.match(p.name)):
        if arm == 'openai':
            record = openai_record(arm, scenario, folder)
        elif arm == 'strata-codex':
            record = strata_codex_record(arm, scenario, folder, done)
        else:
            record = claude_record(arm, scenario, folder)
        record.update(SCORE_FIELDS)
        record.update(summary_fields(record))
        out.append(record)
    # Plan §3: Strata's first 5 valid instances are preregistered; rank the valid ones by attempt number.
    ranked = sorted((r for r in out if r['valid']), key=lambda r: (r['config'], r['attempt']))
    counts = {}
    for r in ranked:
        counts[r['config']] = counts.get(r['config'], 0) + 1
        r['valid_rank'] = counts[r['config']]
    return out


def all_records(layout=LAYOUT):
    out = []
    for arm, (root, scenes) in layout.items():
        for scenario, name in scenes.items():
            out += scene_records(arm, scenario, ROOT / root / name)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--all', action='store_true', help='every arm and scenario of LAYOUT')
    parser.add_argument('--arm', choices=sorted(LAYOUT))
    parser.add_argument('--scenario', choices=SCENARIOS)
    parser.add_argument('--dir', type=Path, help='scene directory (default: LAYOUT)')
    parser.add_argument('--out', type=Path, help='JSON Lines output (default: stdout)')
    args = parser.parse_args()
    if args.all:
        records = all_records()
    elif args.arm and args.scenario:
        records = scene_records(args.arm, args.scenario, args.dir or ROOT / LAYOUT[args.arm][0] / LAYOUT[args.arm][1][args.scenario])
    else:
        parser.error('give --all, or --arm and --scenario')
    text = ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records)
    if args.out:
        args.out.write_text(text)
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
