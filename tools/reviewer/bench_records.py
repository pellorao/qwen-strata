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

Pauses (plan S2) of an instance without a recorded pause field are rebuilt mechanically, per arm, with the basis
in pause_basis: OpenAI from instance.json `arw_pause` and the distinct ARW pause notices ("The Reviewer runtime paused
this same task after ...") in run/machine.jsonl; Strata Codex from run/machine.jsonl; a Claude Code handoff of the
harness before execute_continued (no `continuation`) could not continue an early exit, so it never reached a pause point
(0 by construction). Where no basis exists the record keeps pause_known false and the scorer refuses it. Claude Code
records carry harness_generation; config_notes names a configuration that mixes both generations.

    python3 -m tools.reviewer.bench_records --all [--out records.jsonl]
    python3 -m tools.reviewer.bench_records --arm openai --scenario code-spec-v5 --dir .tmp/bench-openai-1020/cs
"""
import argparse
import hashlib
import json
import os
import re
import sys
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
ARW_PAUSE_PREFIX = 'The Reviewer runtime paused this same task after '  # tools/reviewer/arw_measure.py


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


def scenario_repositories(copy):
    """The scenario repository copies of an ARW prep (copy holds arw/), found by ARW's `.prepared` marker instead of a
    fixed depth: most scenarios sit at runs/<run>/<scenario>/<rep>, Spec Readiness one level deeper at
    runs/<run>/sr/<handoff>/<rep>, which the old `runs/*/*/*` glob missed. Nothing below a found repository is searched."""
    found = []
    for folder, dirs, files in os.walk(Path(copy) / 'arw/.tmp/codex'):
        if '.prepared' in files:
            found.append(Path(folder))
            dirs[:] = []
    return sorted(found)


def report_directories(repositories):
    """The bound report directories (.tmp/codex/<session>/<id>/reports) of scenario repository copies."""
    return sorted(r for d in repositories for r in Path(d).glob('.tmp/codex/*/*/reports'))


def tree_differences(recorded, fresh):
    """Files of two scenario repository manifests that differ, .git and .tmp left out (git bytes do not reproduce)."""
    keep = lambda tree: {k: v for k, v in tree.items() if not k.startswith(('.git/', '.tmp/')) and k != '.git'}
    a, b = keep(recorded), keep(fresh)
    return sorted(set(a) ^ set(b)) + sorted(k for k in set(a) & set(b) if a[k] != b[k])


def pause_fields(events, continues, note):
    if events is None:
        return {'pause_known': False, 'pause_count': None, 'pause_events': None, 'continue_count': continues,
                'pause_basis': None, 'pause_note': note}
    return {'pause_known': True, 'pause_count': len(events), 'pause_events': events, 'continue_count': continues,
            'pause_basis': 'recorded arw_pause_events', 'pause_note': None}


def rebuilt_pause(count, basis):
    """Pause fields rebuilt from a run's own logs (no arw_pause_events recorded)."""
    return {'pause_known': True, 'pause_count': count, 'pause_events': None, 'continue_count': None,
            'pause_basis': basis, 'pause_note': None}


def machine_pauses(path):
    """Distinct ARW pause notices (messageId, else sequence) in an ARW machine log, or None without the log."""
    path = Path(path)
    if not path.is_file():
        return None
    seen = set()

    def walk(value):
        if isinstance(value, dict):
            if value.get('type') == 'message' and str(value.get('text', '')).startswith(ARW_PAUSE_PREFIX):
                seen.add(value.get('messageId') or f"sequence-{value.get('sequence')}")
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    for line in path.read_text(errors='replace').splitlines():
        if ARW_PAUSE_PREFIX not in line:
            continue
        try:
            walk(json.loads(line))
        except ValueError:
            return None  # a pause line that does not parse: the count cannot be established
    return len(seen)


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
        count = machine_pauses(folder / 'run/machine.jsonl')
        flag = instance.get('arw_pause')
        if 'arw_pause' in instance and count is not None and bool(flag) == (count > 0):
            record.update(rebuilt_pause(count, f'run_one before the S2 continue path: instance.json arw_pause={bool(flag)}, '
                                               f'run/machine.jsonl {count} distinct ARW pause notice(s)'))
        else:
            record.update(pause_fields(None, None, f"no pause basis: arw_pause={flag!r} "
                                                   f"({'present' if 'arw_pause' in instance else 'absent'}), "
                                                   f'run/machine.jsonl pause notices {count}'))
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
                         'service_tiers': (h.get('checks') or {}).get('service_tiers'),
                         'final_status': (h.get('checks') or {}).get('completion_status'),
                         'final_status_source': 'instance.json checks.completion_status (ARW completion: its final '
                                                'status form by construction)'})
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
                         'spill_files': read_spills(out),
                         **dict(zip(('final_status', 'final_status_source'), claude_final_status(out)))})
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
    continued = [('continuation' in h) for h in instance.get('handoffs') or []]
    record['harness_generation'] = ('execute_continued' if continued and all(continued) else
                                    'before execute_continued' if continued and not any(continued) else
                                    'mixed' if continued else None)
    if 'arw_pause_events' in instance:
        record.update(pause_fields(instance['arw_pause_events'], instance.get('continue_count'), None))
    elif record['harness_generation'] == 'before execute_continued':
        record.update(rebuilt_pause(0, 'claude_headless before execute_continued (no handoff continuation): an early '
                                       'exit was not continued, so no ARW pause point could be reached; 0 by construction'))
    else:
        record.update(pause_fields(None, None, f"no pause basis (harness {record['harness_generation']}, "
                                               'no arw_pause_events)'))
    record['handoffs'] = handoffs
    record['repository_manifest'] = {'kind': 'h<k>/files-before.json'} if any(h['files_before'] for h in handoffs) else None
    return record


def read_spills(out):
    """Kept tool-output files Claude Code spilled for the handoff (large outputs saved under tool-results/) that a tool
    call of the session names (Read, or Bash such as cat -n / grep -n / sed -n / nl / awk on that path): the model can
    only have taken line numbers from a spill it viewed. Repair (d) converts a locator only through a unique,
    content-checked reading of these."""
    kept = {p.name: p for p in sorted(out.glob('session-files/*/*/tool-results/*')) if p.is_file()}
    named = set()
    for stream in sorted(out.glob('stream*.jsonl')):
        for line in stream.read_text(errors='replace').splitlines():
            if 'tool_use' not in line or not any(name in line for name in kept):
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            content = (event.get('message') or {}).get('content')
            for item in content if isinstance(content, list) else []:
                if isinstance(item, dict) and item.get('type') == 'tool_use':
                    text = json.dumps(item.get('input'), ensure_ascii=False)
                    named.update(name for name in kept if name in text)
    return [str(kept[name]) for name in sorted(named)]


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
        count = machine_pauses(folder / 'run/machine.jsonl')
        if count is not None and results:
            record.update(rebuilt_pause(count, f'results.json without arw_pause_events: run/machine.jsonl {count} '
                                               'distinct ARW pause notice(s)'))
        else:
            record.update(pause_fields(None, None, 'results.json without arw_pause_events and no run/machine.jsonl'))
    reports = sorted((folder / 'report').glob('*')) if (folder / 'report').is_dir() else []
    handoffs = []
    for k, r in enumerate(results):
        path, ok = report_location(r.get('report_sha256'), r.get('report'), *reports)
        handoffs.append({'k': k, 'instanceId': r['instanceId'], 'sub_scenario': sub_scenario(r['instanceId']),
                         'report': path, 'report_ok': ok, 'report_sha256': r.get('report_sha256'),
                         'seconds': r.get('review_work_seconds'), 'tokens': r.get('engine_tokens'), 'tool_calls': None,
                         'thread_id': (r.get('runtime_result') or {}).get('threadId'),
                         'pause_events': r.get('arw_pause_events'),
                         'final_status': ((r.get('runtime_result') or {}).get('completion') or {}).get('status'),
                         'final_status_source': 'run/results.json runtime_result.completion (ARW completion: its final '
                                                'status form by construction)'})
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


FINAL_STATUS_FORMS = ('ready', 'incomplete')


def claude_final_status(out):
    """ARW final status of a Claude Code handoff's last answer (last segment with a result event)."""
    from tools.reviewer.claude_headless import accounting_stream, final_status, segment_end, segment_streams
    streams = [s for s in segment_streams(out) if s.is_file()]
    if not streams:
        return None, 'no stream'
    stream = accounting_stream(streams)
    result = segment_end(stream)[1]
    if result is None:
        return None, f'{stream.name}: no result event'
    if result.get('is_error'):
        return None, f'{stream.name}: result is_error ({result.get("subtype")}), not a final status message'
    return final_status(result.get('result')) or 'not-arw-form', f'{stream.name}: final result text'


def final_status_error(record):
    """B class (user 2026-10-20, reviewer-suite 「可机械修复」): report written, the last final message not exactly ARW's
    status form and not corrected by a continuation -> scored as delivered, 1 format error in r per instance."""
    hits = [h['k'] for h in record['handoffs'] if h.get('final_status') == 'not-arw-form' and h.get('report_ok')]
    record['final_status_format_errors'] = 1 if hits else 0
    record['final_status_basis'] = ({'handoffs': hits, 'rule': 'report written, last final message not ARW form'} if hits
                                    else 'every handoff ended in ARW form, wrote no report, or has no final message')
    return record


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
        final_status_error(record)
        out.append(record)
    # Plan §3: Strata's first 5 valid instances are preregistered; rank the valid ones by attempt number.
    ranked = sorted((r for r in out if r['valid']), key=lambda r: (r['config'], r['attempt']))
    counts = {}
    for r in ranked:
        counts[r['config']] = counts.get(r['config'], 0) + 1
        r['valid_rank'] = counts[r['config']]
    return out


def config_notes(records):
    """A note for each arm/scenario/configuration whose instances come from both Claude Code harness generations."""
    groups = {}
    for r in records:
        if r.get('harness_generation'):
            groups.setdefault((r['arm'], r['scenario'], r['config_label']), {}).setdefault(r['harness_generation'], []).append(r['id'])
    return [{'arm': arm, 'scenario': scenario, 'config': label,
             'note': 'instances from both harness generations (before / with execute_continued): pauses of the older '
                     'ones are 0 by construction, the newer ones continue early exits and record pauses',
             'generations': {g: len(ids) for g, ids in sorted(by.items())}}
            for (arm, scenario, label), by in sorted(groups.items()) if len(by) > 1]


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
    for note in config_notes(records):
        print(json.dumps(note, ensure_ascii=False), file=sys.stderr)
    text = ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records)
    if args.out:
        args.out.write_text(text)
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
