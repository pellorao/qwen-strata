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

Compactions (docs/plan.md, next benchmark, user 2026-10-22) are counted per handoff and summed per instance
(`compactions`, None unless every handoff is known, never 0 for a missing source): Codex from the `compacted` events
of the root Reviewer thread's rollout (guardian threads left out), else the count run_one recorded from that same
rollout; Claude Code from the distinct `system` / `compact_boundary` events of the main session in the kept segment
streams.

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
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.reviewer import bench_suite, bench_validity

ROOT = Path(__file__).resolve().parents[2]
# The v1 suite (tools.reviewer.bench_suite); other suites pass suite= down to base().
PLANS = bench_suite.SUITES['v1']['plans']
SCENARIOS = bench_suite.SUITES['v1']['scenarios']
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
    # Both DeepSeek harnesses share one scene directory; the directory model key (codex-, cc-) tells them apart.
    'deepseek-codex': ('.tmp/bench-deepseek-1020/r1', {'commit-audit-v3': 'ca', 'code-spec-v5': 'cs',
                                                       'code-standards-v5.1': 'cstd', 'spec-readiness-v4.3': 'sr'}),
    'deepseek-claude': ('.tmp/bench-deepseek-1020/r1', {'commit-audit-v3': 'ca', 'code-spec-v5': 'cs',
                                                        'code-standards-v5.1': 'cstd', 'spec-readiness-v4.3': 'sr'}),
}
HARNESS = {'openai': 'codex', 'strata-codex': 'codex', 'anthropic': 'claude-code', 'strata-claude': 'claude-code',
           'deepseek-codex': 'codex', 'deepseek-claude': 'claude-code'}
# Arm -> the directory model keys of its instances (None: every key of MODELS).
ARM_MODELS = {'deepseek-codex': ('codex',), 'deepseek-claude': ('cc',)}
EFFORTS = ('low', 'medium', 'high')
DEEPSEEK_EFFORTS = ('low', 'high', 'max')
# The one configuration table of the benchmark (user 2026-10-23: bench_records, benchmark_summary and benchmark_export
# all read it, none keeps its own copy). Rows: (first configuration, directory model key, harness, model family,
# summary model name, vendor, efforts, kind); configuration = first + effort index.
# - kind 'main': the 27 configurations of plan §2. DeepSeek rows are low / high / max (plan §2 / §14.4, user
#   2026-10-21); a medium instance takes the configuration of its effective effort (high) and is either pooled into it
#   (C') or a supplementary row (instance.json fields).
# - kind 'phase3': the phase-3 supplement (user 2026-10-22, docs/plan.md 9a): gpt-6-luna xhigh / max on Codex,
#   numbered after the 27; reported per instance only, never in a comparison.
CONFIG_TABLE = [
    (1, 'sol', 'codex', 'gpt-6.1-sol', 'gpt-6.1-sol', 'openai', EFFORTS, 'main'),
    (4, 'luna', 'codex', 'gpt-6-luna', 'gpt-6-luna', 'openai', EFFORTS, 'main'),
    (7, 'codex', 'codex', 'deepseek-flash', 'deepseek-flash', 'deepseek', DEEPSEEK_EFFORTS, 'main'),
    (10, 'codex-strata', 'codex', 'strata', 'strata-iq3_xxs', 'strata', EFFORTS, 'main'),
    (13, 'opus', 'claude-code', 'opus', 'opus', 'anthropic', EFFORTS, 'main'),
    (16, 'sonnet', 'claude-code', 'sonnet', 'sonnet', 'anthropic', EFFORTS, 'main'),
    (19, 'haiku', 'claude-code', 'haiku', 'haiku', 'anthropic', EFFORTS, 'main'),
    (22, 'cc', 'claude-code', 'deepseek-flash', 'deepseek-flash', 'deepseek', DEEPSEEK_EFFORTS, 'main'),
    (25, 'strata', 'claude-code', 'strata', 'strata-iq3_xxs', 'strata', EFFORTS, 'main'),
    (28, 'luna', 'codex', 'gpt-6-luna', 'gpt-6-luna', 'openai', ('xhigh', 'max'), 'phase3'),
]
# Configurations of the phase-3 supplement: every valid instance counts, no first-5 cut (measurement rule 失败与重跑,
# user 2026-10-23: extra runs not triggered by scores count the same as preregistered ones).
PHASE3_CONFIGS = frozenset(first + i for first, _, _, _, _, _, efforts, kind in CONFIG_TABLE if kind == 'phase3'
                           for i in range(len(efforts)))
# Directory model key -> (first configuration of its main row, model family, report style family = vendor).
MODELS = {key: (first, family, vendor) for first, key, _, family, _, vendor, _, kind in CONFIG_TABLE if kind == 'main'}
MODEL_EFFORTS = {key: efforts for _, key, _, _, _, _, efforts, kind in CONFIG_TABLE if kind == 'main'}
# (directory model key, effort) -> configuration outside the main rows.
EXTRA_CONFIGS = {(key, e): first + i for first, key, _, _, _, _, efforts, kind in CONFIG_TABLE if kind != 'main'
                 for i, e in enumerate(efforts)}
DIR_NAME = re.compile(r'^(?P<model>[a-z-]+?)-(?P<effort>low|medium|high|xhigh|max)-a(?P<attempt>\d+)$')
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


def base(arm, scenario, folder, suite='v1'):
    match = DIR_NAME.match(folder.name)
    if not match or match.group('model') not in MODELS:
        raise ValueError(f'{folder}: not an instance directory name')
    first, family, style = MODELS[match.group('model')]
    effort = match.group('effort')
    instance = load(folder / 'instance.json') or {}
    effective = instance.get('effective_effort') or effort
    efforts = MODEL_EFFORTS.get(match.group('model'), EFFORTS)
    config = EXTRA_CONFIGS.get((match.group('model'), effective))
    if config is None and effective not in efforts:
        raise ValueError(f'{folder}: effort {effective} is not a configuration of {family}')
    plan = bench_suite.plan_path(suite, scenario)
    # v1 records keep their v1 fields; other suites name theirs.
    record = {'id': f'{arm}/{scenario}/{folder.name}', **({} if suite == 'v1' else {'suite': suite}), 'arm': arm, 'harness': HARNESS[arm],
              'model_family': family, 'style_family': style, 'effort': effort,
              'requested_effort': instance.get('requested_effort', effort), 'effective_effort': effective,
              'pooled': bool(instance.get('pooled')), 'supplementary': bool(instance.get('supplementary')),
              'supplementary_label': instance.get('supplementary_label') if instance.get('supplementary') else None,
              'config': config or first + efforts.index(effective), 'config_label': f'{family}-{effective}', 'scenario': scenario,
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


def openai_record(arm, scenario, folder, suite='v1'):
    record = base(arm, scenario, folder, suite)
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
        session = h.get('session')
        moved = (location['copied_to'] + session[len(location['prep']):] if location.get('prep') and location.get('copied_to')
                 and isinstance(session, str) and session.startswith(location['prep']) else None)
        handoffs.append({'k': k, 'instanceId': iid, 'sub_scenario': sub_scenario(iid), 'report': path, 'report_ok': ok,
                         'report_sha256': h.get('report_sha256'), 'seconds': h.get('reviewer_active_seconds'),
                         'tokens': h.get('tokens'), 'tool_calls': h.get('tool_calls'), 'thread_id': h.get('thread_id'),
                         'session': h.get('session'), 'pause_events': h.get('arw_pause_events'),
                         'models_returned': (h.get('checks') or {}).get('models_returned'),
                         'service_tiers': (h.get('checks') or {}).get('service_tiers'),
                         'final_status': (h.get('checks') or {}).get('completion_status'),
                         'final_status_source': 'instance.json checks.completion_status (ARW completion: its final '
                                                'status form by construction)',
                         **codex_compactions(h.get('compactions'), moved, session)})
    record['handoffs'] = handoffs
    record['repository_manifest'] = {'kind': 'scenario-copies.json', 'entries': len(manifest)} if manifest else None
    return record


API_TOKEN_ARMS = ('anthropic', 'deepseek-claude')  # plan 5: Claude Code tokens come from the stream result usage


def usage_tokens(usage):
    """The three token classes from Claude Code result usage, as schedule.jsonl counts them for DeepSeek and as the
    OpenAI arm splits input: uncached input = input_tokens + cache_creation_input_tokens (a cache write is input the
    cache did not hold), cached input = cache_read_input_tokens, output = output_tokens. None without usage."""
    if not isinstance(usage, dict):
        return None
    return {'uncached_input': (usage.get('input_tokens') or 0) + (usage.get('cache_creation_input_tokens') or 0),
            'cached_input': usage.get('cache_read_input_tokens') or 0, 'output': usage.get('output_tokens') or 0}


def claude_record(arm, scenario, folder, suite='v1'):
    from tools.reviewer.claude_headless import segment_streams, stream_summary
    record = base(arm, scenario, folder, suite)
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
        # Recounted from the kept streams, never from the archived summary (before 2026-10-20 it holds only the last
        # result; strata-1019 ca-r2 strata-medium-a2 h0 is such a summary).
        files = [f for f in segment_streams(out) if f.is_file()]
        recount = stream_summary(files) if files else {}
        usage = recount.get('usage') if recount.get('result_event') else None
        continuation = h.get('continuation') or {}
        handoffs.append({'k': k, 'instanceId': h['instanceId'], 'sub_scenario': sub_scenario(h['instanceId']),
                         'report': path, 'report_ok': ok, 'report_exists': h.get('report_exists'),
                         'report_sha256': h.get('report_sha256'), 'seconds': h.get('wall_seconds'),
                         'tokens': usage_tokens(usage) if arm in API_TOKEN_ARMS else h.get('engine_tokens'),
                         'tokens_lower_bound': bool(usage) and recount.get('usage_bound') == 'lower',
                         'api_usage': usage,
                         'cost_usd': summary.get('total_cost_usd'), 'tool_calls': claude_tool_calls(files),
                         'api_seconds': (recount['duration_api_ms'] / 1000 if recount.get('duration_api_ms') is not None
                                         and not recount.get('segments_without_result') else None),
                         **engine_stage_seconds(result.get('engine_requests') if arm == 'strata-claude' else None),
                         'session': continuation.get('session_id'), 'pause_events': continuation.get('arw_pause_events'),
                         'sandbox_failures': sandbox, 'sandbox_source': sandbox_source,
                         'continuation_stop': checks.get('continuation_stop'),
                         'models_returned': checks.get('models_returned'), 'service_tiers': checks.get('service_tiers'),
                         'files_before': str(out / 'files-before.json') if (out / 'files-before.json').is_file() else None,
                         'spill_files': read_spills(out),
                         'compactions': stream_compactions(files),
                         'compactions_source': 'Claude Code stream compact_boundary events' if files else 'no stream',
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
    starts = [(load(folder / f'h{k}/result.json') or {}).get('started_at') for k in range(len(handoffs))]
    record['started'] = min((s for s in starts if s), default=None)
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


def strata_codex_record(arm, scenario, folder, done, suite='v1'):
    record = base(arm, scenario, folder, suite)
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
                         'seconds': r.get('review_work_seconds'), 'tokens': r.get('engine_tokens'),
                         'tool_calls': root_rollout_tool_calls(r), **engine_stage_seconds(r.get('engine_requests')),
                         'thread_id': (r.get('runtime_result') or {}).get('threadId'),
                         'pause_events': r.get('arw_pause_events'),
                         'final_status': ((r.get('runtime_result') or {}).get('completion') or {}).get('status'),
                         'final_status_source': 'run/results.json runtime_result.completion (ARW completion: its final '
                                                'status form by construction)',
                         **codex_compactions(None, root_rollout_path(r))})
    record['handoffs'] = handoffs
    manifest = load(folder / 'scenario-copies.json')
    record['repository_manifest'] = {'kind': 'scenario-copies.json', 'entries': len(manifest)} if manifest else None
    return record


def claude_tool_calls(files):
    """Tool calls of a Claude Code handoff from its kept segment streams: distinct tool_use blocks of the main session's
    assistant messages (stream-json repeats an assistant message once per content block, so a block counts once by id;
    a subagent's messages, parent_tool_use_id set, are left out). None without a stream."""
    if not files:
        return None
    seen = set()
    for stream in files:
        for number, line in enumerate(Path(stream).read_text(errors='replace').splitlines()):
            if '"tool_use"' not in line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get('type') != 'assistant' or event.get('parent_tool_use_id'):
                continue
            content = (event.get('message') or {}).get('content')
            for i, block in enumerate(content if isinstance(content, list) else []):
                if isinstance(block, dict) and block.get('type') == 'tool_use':
                    seen.add(block.get('id') or (str(stream), number, i))
    return len(seen)


ROLLOUT_TOOL_TYPES = ('function_call', 'custom_tool_call', 'web_search_call', 'tool_search_call')  # as run_one counts


def rollout_tool_calls(path):
    """Tool call items of one Codex rollout (the OpenAI arm's run_one count: function, custom-tool, web-search and
    tool-search calls; a code-mode exec counts once). None without the rollout."""
    path = Path(path) if path else None
    if path is None or not path.is_file():
        return None
    calls = 0
    for line in path.read_text(errors='replace').splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        payload = event.get('payload') or {}
        calls += event.get('type') == 'response_item' and payload.get('type') in ROLLOUT_TOOL_TYPES
    return calls


def root_rollout_path(result):
    """The rollout of the root Reviewer thread of an ARW results.json entry (cost.histories), or None."""
    root = (result.get('runtime_result') or {}).get('threadId')
    if not root:
        return None
    return next((h.get('path') for h in (result.get('cost') or {}).get('histories') or [] if h.get('thread_id') == root),
                None)


def root_rollout_tool_calls(result):
    """Tool calls of the root Reviewer thread of an ARW results.json entry (guardian threads left out), from its
    rollout in cost.histories."""
    path = root_rollout_path(result)
    return rollout_tool_calls(path) if path else None


def rollout_compactions(path):
    """Compactions of one Codex rollout: its `compacted` lines (one per compaction, the line that carries the
    replacement history; run_one counts the same). None without the rollout, or when a line naming `compacted` does
    not parse (the count cannot be established)."""
    path = Path(path) if path else None
    if path is None or not path.is_file():
        return None
    count = 0
    for line in path.read_text(errors='replace').splitlines():
        if '"compacted"' not in line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            return None
        count += isinstance(event, dict) and event.get('type') == 'compacted'
    return count


def codex_compactions(recorded, *paths):
    """(compactions, compactions_source) of a Codex handoff: recounted from the first root rollout found among
    `paths`, else the count the runner recorded from that rollout, else unknown."""
    for path in paths:
        count = rollout_compactions(path)
        if count is not None:
            return {'compactions': count, 'compactions_source': 'Codex root rollout compacted events'}
    if isinstance(recorded, int):
        return {'compactions': recorded,
                'compactions_source': 'instance.json handoff compactions (run_one, root rollout compacted events)'}
    return {'compactions': None, 'compactions_source': 'no root rollout and no recorded count'}


def stream_compactions(files):
    """Compactions of a Claude Code handoff: distinct `system` / `compact_boundary` events (by uuid) of the main session
    over its kept segment streams (a subagent's, parent_tool_use_id set, left out). None without a stream, or when a line
    naming compact_boundary does not parse."""
    if not files:
        return None
    seen = set()
    for stream in files:
        for number, line in enumerate(Path(stream).read_text(errors='replace').splitlines()):
            if 'compact_boundary' not in line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                return None
            if (isinstance(event, dict) and event.get('type') == 'system' and event.get('subtype') == 'compact_boundary'
                    and not event.get('parent_tool_use_id')):
                seen.add(event.get('uuid') or (str(stream), number))
    return len(seen)


def engine_stage_seconds(requests):
    """Read and generated tokens of a handoff's engine log requests with their input-processing and decode seconds
    (tools.metrics.strata_tokens records); all None without requests."""
    if not requests:
        return {'engine_read': None, 'engine_generated': None, 'engine_input_seconds': None, 'engine_decode_seconds': None}
    from tools.metrics.strata_tokens import engine_rates, sum_engine_tokens
    tokens, rates = sum_engine_tokens(requests), engine_rates(requests)
    return {'engine_read': tokens['uncached_input'], 'engine_generated': tokens['output'],
            'engine_input_seconds': rates['engine_input_seconds'], 'engine_decode_seconds': rates['engine_decode_seconds']}


def relay_output_seconds(folder):
    """(output tokens, request seconds, requests) over the relay log of a Codex API instance: every request whose
    reply carries usage, timed from its arrival at the relay to the end of the streamed reply. None without a log."""
    files = sorted((Path(folder) / 'run/relay').glob('*.jsonl'))
    if not files:
        return None
    output, seconds, requests = 0, 0.0, 0
    for f in files:
        for line in f.read_text(errors='replace').splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            usage = row.get('usage') or {}
            if usage.get('output_tokens') is None or row.get('ended_at') is None or row.get('started_at') is None:
                continue
            output += usage['output_tokens']
            seconds += row['ended_at'] - row['started_at']
            requests += 1
    return (output, seconds, requests) if requests else None


def relay_tokens(folder):
    """(tokens, requests with usage, POST requests without usage) summed over the relay log of a Codex API instance, in
    the classes of the instance record (uncached input = input - cached); None without a log or any usage. The relay
    sums equal the ARW handoff tokens wherever both exist (luna xhigh / max supplement, 50 of 50)."""
    files = sorted((Path(folder) / 'run/relay').glob('*.jsonl'))
    out, used, missing = {'uncached_input': 0, 'cached_input': 0, 'output': 0}, 0, 0
    for f in files:
        for line in f.read_text(errors='replace').splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            usage = row.get('usage') or {}
            if usage.get('input_tokens') is None or usage.get('output_tokens') is None:
                missing += row.get('method') == 'POST'
                continue
            cached = (usage.get('input_tokens_details') or {}).get('cached_tokens') or 0
            out['uncached_input'] += usage['input_tokens'] - cached
            out['cached_input'] += cached
            out['output'] += usage['output_tokens']
            used += 1
    return (out, used, missing) if used else None


def relay_output_limits(folder):
    """Per-response output of a Codex API instance from its relay log (F15 suggestion 1: Codex sends no output limit,
    the endpoint applies its own): the largest single-response output_tokens, and the responses the provider marked
    incomplete with their incomplete_details reasons. All None without a relay log; a reason the relay did not keep is
    'unknown'."""
    files = sorted((Path(folder) / 'run/relay').glob('*.jsonl'))
    outputs, reasons = [], {}
    for f in files:
        for line in f.read_text(errors='replace').splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            output = (row.get('usage') or {}).get('output_tokens')
            if output is not None:
                outputs.append(output)
            if row.get('response_status') == 'incomplete' or row.get('incomplete_details'):
                reason = (row.get('incomplete_details') or {}).get('reason') or 'unknown'
                reasons[reason] = reasons.get(reason, 0) + 1
    if not files:
        return {'max_response_output_tokens': None, 'incomplete_responses': None, 'incomplete_reasons': None}
    return {'max_response_output_tokens': max(outputs) if outputs else None,
            'incomplete_responses': sum(reasons.values()), 'incomplete_reasons': reasons}


def relay_token_fallback(record, folder):
    """A Codex API record whose handoffs carry no tokens (ARW lost them at a hard interrupt) takes the relay log sums;
    POST requests without usage (cut by the interrupt) make them a lower bound, stated in token_source."""
    if record['arm'] not in ('openai', 'deepseek-codex') or any(v is not None for v in record['tokens'].values()):
        return
    relay = relay_tokens(folder)
    if relay is None:
        return
    record['tokens'] = relay[0]
    record['token_source'] = (f'API usage (relay log sum, {relay[1]} requests'
                              + (f'; lower bound: {relay[2]} request(s) without usage)' if relay[2] else ')'))


def ratio(amount, seconds):
    return amount / seconds if amount is not None and seconds else None


def speed_fields(record, folder=None):
    """The four speeds of the measurement rule (token/s) with their basis and parts. User-perceived (task_input,
    task_output): uncached input and output over the instance's work seconds, every arm. Model direct (engine_input,
    engine_output): Strata from the engine log stages (read / input-processing seconds, generated / decode seconds); API
    models have no input-processing time, so engine_input is unknown, and engine_output is a lower bound (time to first
    token and input processing included): Claude Code output tokens over the result events' duration_api_ms, Codex the
    relay's output tokens over its request durations. Unknown where a part is missing, never zero. speed_parts keeps
    each speed's numerator and denominator ({'tokens', 'seconds'}, None when unknown) so that several instances pool
    as total tokens / total seconds (benchmark_summary.pooled_speeds, user 2026-10-22)."""
    handoffs, tokens, seconds = record['handoffs'], record.get('tokens') or {}, record.get('seconds')
    lower = bool(record.get('token_source') and 'lower bound' in record['token_source'])
    parts = {'task_input': (tokens.get('uncached_input'), seconds), 'task_output': (tokens.get('output'), seconds),
             'engine_input': (None, None), 'engine_output': (None, None)}
    basis = {'task': (f"{record.get('token_source') or 'unknown tokens'} over the instance work seconds"
                      + (' (lower bound: tokens are)' if lower else ''))}
    bounds = ['task_input', 'task_output'] if lower else []

    def summed(key):
        values = [h.get(key) for h in handoffs]
        return sum(values) if handoffs and None not in values else None
    if record['model_family'] == 'strata':
        parts['engine_input'] = (summed('engine_read'), summed('engine_input_seconds'))
        parts['engine_output'] = (summed('engine_generated'), summed('engine_decode_seconds'))
        basis['engine'] = 'engine log requests: read / input-processing seconds, generated / decode seconds'
    elif record['harness'] == 'claude-code':
        parts['engine_output'] = (tokens.get('output'), summed('api_seconds'))
        basis['engine'] = ('API model: input unknown (no input-processing time); output = stream result output tokens / '
                           'duration_api_ms, a lower bound (first-token latency and input processing included)')
        bounds.append('engine_output')
    else:
        relay = relay_output_seconds(folder or ROOT / record['dir'])
        parts['engine_output'] = (relay[0], relay[1]) if relay else (None, None)
        basis['engine'] = ('API model: input unknown (no input-processing time); output = relay output tokens / request '
                           'seconds, a lower bound (first-token latency and input processing included)'
                           + (f', {relay[2]} requests' if relay else ', no relay log'))
        bounds.append('engine_output')
    speeds = {k: ratio(*v) for k, v in parts.items()}
    speed_parts = {k: ({'tokens': v[0], 'seconds': v[1]} if speeds[k] is not None else None) for k, v in parts.items()}
    return {'speeds': speeds, 'speed_parts': speed_parts, 'speed_basis': basis,
            'speed_lower_bounds': [k for k in bounds if speeds[k] is not None]}


def summary_fields(record):
    """The benchmark_summary record fields that the instance records give (unknown ones null)."""
    handoffs = record['handoffs']
    seconds = [h.get('seconds') for h in handoffs]
    tokens = [h.get('tokens') for h in handoffs]
    known = handoffs and all(isinstance(t, dict) for t in tokens)
    calls = [h.get('tool_calls') for h in handoffs]
    compactions = [h.get('compactions') for h in handoffs]
    models = sorted({m for h in handoffs for m in (h.get('models_returned') or [])})
    tiers = {}
    for h in handoffs:
        for tier, n in (h.get('service_tiers') or {}).items():
            tiers[tier] = tiers.get(tier, 0) + n
    return {'instance': record['attempt'],
            'seconds': sum(seconds) if handoffs and None not in seconds else None,
            'tokens': {c: (sum(t.get(c) or 0 for t in tokens) if known else None)
                       for c in ('uncached_input', 'cached_input', 'output')},
            'token_source': None if not known else (
                'engine log' if record['model_family'] == 'strata' else
                'Claude Code stream result usage' if record['arm'] in API_TOKEN_ARMS else 'API usage (relay)')
            + (' (lower bound: a segment without result)' if known and any(h.get('tokens_lower_bound') for h in handoffs) else ''),
            'tool_calls': sum(calls) if handoffs and None not in calls else None,
            'compactions': sum(compactions) if handoffs and None not in compactions else None,
            'compactions_source': '; '.join(sorted({h.get('compactions_source') or 'unknown' for h in handoffs})) or None,
            'cost_usd': handoff_cost_usd(record), 'cost_cny': None, 'cost_basis': None,
            'model_ids': models, 'service_tiers': tiers}


def handoff_cost_usd(record):
    """Claude Code result total_cost_usd summed over the handoffs; None unless every handoff has one (a segment killed at
    the hard limit has no result event: ruling 2026-10-21, no relay or balance source for the Anthropic plan, so
    unknown, never guessed). DeepSeek runs through Claude Code report Claude prices, so they are not used."""
    if record['arm'] not in ('anthropic', 'strata-claude'):
        return None
    rejudged = ((record.get('validity') or {}).get('rejudge') or {}).get('handoffs') or []
    if any(h.get('segments_without_result') for h in rejudged):
        return None  # the cost of the killed segment is missing: what remains is a lower bound
    costs = [h.get('cost_usd') for h in record['handoffs']]
    return sum(costs) if costs and None not in costs else None


# DeepSeek flash prices, CNY per 1M tokens: (cache hit, miss, output); peak = Beijing weekdays 9-12 and 14-18 (plan 14.4;
# the same table and rule as schedule.py of the run).
DEEPSEEK_PRICE = {'offpeak': (0.02, 1.0, 4.0), 'peak': (0.04, 2.0, 8.0)}
# The same table in USD, DeepSeek-V4.1-Flash-1017 (deepseek-flash), official English pricing page
# https://api-docs.deepseek.com/quick_start/pricing (page sha256 b856a6e93fa4793ecc8f3fd03a01bb7d8f7572f78a4739da8ce6dbdb09328d66,
# fetched 2026-10-20). Every item is exactly 0.15 USD per CNY, peak and off-peak alike, so the
# conversion by price ratio (user 2026-10-21, not a market exchange rate) is one number whatever the token mix.
DEEPSEEK_PRICE_USD = {'offpeak': (0.003, 0.15, 0.6), 'peak': (0.006, 0.3, 1.2)}
BEIJING = timezone(timedelta(hours=8))


def deepseek_period(ts):
    bj = datetime.fromtimestamp(ts, BEIJING)
    return 'peak' if bj.weekday() < 5 and (9 <= bj.hour < 12 or 14 <= bj.hour < 18) else 'offpeak'


def deepseek_price_cost(hit, miss, output, period, prices=DEEPSEEK_PRICE):
    p = prices[period]
    return (hit * p[0] + miss * p[1] + output * p[2]) / 1e6


def request_time_cost(folder, event, prices=DEEPSEEK_PRICE):
    """Plan 14.4 per-request-time CNY of a DeepSeek instance (schedule.py request_cost): a Codex instance reprices every
    request of its relay log at the request's own start time; a Claude Code instance only has stream-result totals, so
    it is priced at its start time, the whole instance at the peak price when it crosses a price boundary. None when
    the inputs are missing."""
    tokens = event.get('tokens') or [0]
    if not sum(tokens):
        return None
    if event.get('cfg', '').startswith('codex'):
        files = sorted((Path(folder) / 'run/relay').glob('*.jsonl')) if folder is not None else []
        if not files:
            return None
        total = 0.0
        for f in files:
            for line in f.read_text().splitlines():
                row = json.loads(line)
                u = row.get('usage') or {}
                cached = (u.get('input_tokens_details') or {}).get('cached_tokens') or 0
                total += deepseek_price_cost(cached, (u.get('input_tokens') or 0) - cached,
                                             u.get('output_tokens') or 0, deepseek_period(row['started_at']), prices)
        return total
    if event.get('wall') is None:
        return None
    end = bench_validity.stamp(event['t'])
    start = end - event['wall']
    period = 'peak' if deepseek_period(start) != deepseek_period(end) else deepseek_period(start)
    return deepseek_price_cost(*tokens, period, prices)


def deepseek_cost(record, event, folder=None):
    """(CNY, basis) of a DeepSeek instance from its schedule.jsonl done event (plan 14.4: per-token cost, each request
    at its own peak / off-peak price). Older events only carry `cny`, priced at the instance start; those are repriced
    per request from the relay log (request_time_cost) and keep the old figure, named so, when that is impossible.
    (None, why) without an event or tokens, except a balance difference where the arm has a schedule. Batch totals by
    balance difference: bench_validity.deepseek_batch_reconciliation."""
    if not event or not sum(event.get('tokens') or [0]):
        if folder is not None and (folder.parent.parent / 'schedule.jsonl').is_file():
            balance = bench_validity.deepseek_balance_cost(folder.parent.name, folder.name, root=folder.parent.parent)
            if balance:
                return balance['cost'], f"balance difference over window {balance['window']} (bench_validity)"
        return None, 'no done event with tokens in schedule.jsonl, no balance window'
    if event.get('cny_request_time') is not None:
        return event['cny_request_time'], 'schedule.jsonl cny_request_time (per request, CNY)'
    recomputed = request_time_cost(folder, event)
    if recomputed is not None:
        how = ('relay log, each request at its own start time' if event.get('cfg', '').startswith('codex') else
               'stream-result totals at instance start, the whole instance at peak price across a boundary')
        return round(recomputed, 4), f'recomputed from {how} (CNY); schedule.jsonl cny was priced at instance start'
    return event.get('cny'), 'schedule.jsonl cny (priced at instance start, CNY; no per-request record to reprice)'


def usd_per_cny(tokens):
    """USD/CNY ratio of the official price items weighted by a token mix (cache hit, miss, output) at off-peak prices
    (peak is the same ratio); None for an empty mix."""
    cny = deepseek_price_cost(*tokens, 'offpeak')
    return deepseek_price_cost(*tokens, 'offpeak', DEEPSEEK_PRICE_USD) / cny if cny else None


def deepseek_usd(cny, event, folder=None, arm_tokens=None):
    """(USD, basis) next to the CNY figure (user 2026-10-21: one unit across arms, by the official USD / CNY price
    ratio, never a market rate). An instance that can be priced by token takes the USD table at the same per-request
    periods as the CNY; otherwise its CNY total is scaled by the ratio of its own tokens, or by the ratio weighted by the
    token mix of the whole arm (`arm_tokens`) when it has none; nothing without a CNY figure."""
    if cny is None:
        return None, 'unknown: no CNY cost'
    tokens = (event or {}).get('tokens') or [0]
    if sum(tokens):
        priced = request_time_cost(folder, event, DEEPSEEK_PRICE_USD)
        if priced is not None:
            return round(priced, 6), 'USD from the official USD price table, each request at its own period'
        ratio = usd_per_cny(tokens)
        if ratio is not None:
            return round(cny * ratio, 6), 'CNY x USD/CNY official price ratio of the instance tokens'
    ratio = usd_per_cny(arm_tokens) if arm_tokens and sum(arm_tokens) else None
    if ratio is None:
        return None, 'unknown: no token mix for the price ratio'
    return round(cny * ratio, 6), 'CNY x USD/CNY official price ratio weighted by the token mix of the whole DeepSeek arm'


def cost_lower_bound(record, event):
    """True when the cost is a floor: a reminder interrupt abandons a request whose tokens never reach the relay usage
    (plan 14.4 'offpeak low' note). The rejudge list when classified, else abandoned_requests of the done event."""
    rejudge = (record.get('validity') or {}).get('rejudge') or {}
    if rejudge.get('applied'):
        return bool(rejudge.get('reminder_interrupts'))
    return bool((event or {}).get('abandoned_requests'))


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


def scene_records(arm, scenario, scene, suite='v1'):
    scene = Path(scene)
    if not scene.is_dir():
        return []
    done, arm_tokens = {}, None
    if arm.startswith('deepseek'):
        # One schedule.jsonl for all scenes of the round, in the directory above the scene directories.
        schedule, scen = scene.parent / 'schedule.jsonl', scene.name
    else:
        schedule, scen = scene / 'schedule.jsonl', None
    if (arm == 'strata-codex' or scen) and schedule.is_file():
        arm_tokens = [0, 0, 0]
        for line in schedule.read_text().splitlines():
            event = json.loads(line)
            if event.get('event') == 'done' and event.get('scen', scen) == scen:
                done[event['out']] = event
            if scen and event.get('event') == 'done' and len(event.get('tokens') or []) == 3:
                arm_tokens = [a + b for a, b in zip(arm_tokens, event['tokens'])]  # the token mix of the whole arm
    out = []
    for folder in sorted(p for p in scene.iterdir() if p.is_dir() and arm_instance(arm, p.name)):
        out.append(instance_record(arm, scenario, folder, done, arm_tokens, suite))
    # Plan §3, §14.1 L256, §14.4 and ruling 2026-10-21: not merged cells take their first 5 valid instances by start
    # time for the main statistic; merged cells (DeepSeek C') take every valid one; so do the phase-3 supplement cells
    # (user 2026-10-23).
    return bench_validity.rank_cells(out, whole_configs=PHASE3_CONFIGS)


def arm_instance(arm, name):
    match = DIR_NAME.match(name)
    return bool(match) and match.group('model') in (ARM_MODELS.get(arm) or MODELS)


def instance_record(arm, scenario, folder, done=None, arm_tokens=None, suite='v1'):
    """The normalized record of one instance directory, validity rejudged (bench_validity) before the summary fields."""
    if arm in ('openai', 'deepseek-codex'):
        record = openai_record(arm, scenario, folder, suite)
    elif arm == 'strata-codex':
        record = strata_codex_record(arm, scenario, folder, done or {}, suite)
    else:
        record = claude_record(arm, scenario, folder, suite)
    bench_validity.apply(record, folder, load(folder / 'instance.json'))
    record.update(SCORE_FIELDS)
    record.update(summary_fields(record))
    relay_token_fallback(record, folder)
    if arm in ('openai', 'deepseek-codex'):
        record.update(relay_output_limits(folder))
    record.update(speed_fields(record, folder))
    if arm.startswith('deepseek'):
        event = (done or {}).get(folder.name)
        record['cost_cny'], record['cost_basis'] = deepseek_cost(record, event, folder)
        record['cost_usd'], usd_basis = deepseek_usd(record['cost_cny'], event, folder, arm_tokens)
        record['cost_basis'] += '; ' + usd_basis
    elif record['cost_usd'] is None and arm in ('anthropic', 'strata-claude'):
        record['cost_basis'] = 'unknown: a segment has no result event (killed at the hard limit); no relay or balance source'
    has_cost = record.get('cost_usd') is not None or record.get('cost_cny') is not None
    record['cost_lower_bound'] = has_cost and cost_lower_bound(record, (done or {}).get(folder.name))
    final_status_error(record)
    return record


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


# Run layout per suite; v2 is filled in when its runs exist (benchmarks/multi-model-v2/plan.md).
LAYOUTS = {'v1': LAYOUT, 'v2': {}}


def all_records(layout=None, data_root=None, suite='v1'):
    """Every record of the layout (default: the suite's); data_root is the checkout holding .tmp (default: this one)."""
    out = []
    for arm, (root, scenes) in (LAYOUTS[suite] if layout is None else layout).items():
        for scenario, name in scenes.items():
            out += scene_records(arm, scenario, Path(data_root or ROOT) / root / name, suite)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--suite', choices=sorted(bench_suite.SUITES), default=bench_suite.DEFAULT)
    parser.add_argument('--all', action='store_true', help='every arm and scenario of the suite layout')
    parser.add_argument('--arm', choices=sorted(HARNESS))
    parser.add_argument('--scenario', choices=bench_suite.all_scenarios())
    parser.add_argument('--dir', type=Path, help='scene directory (default: the suite layout)')
    parser.add_argument('--out', type=Path, help='JSON Lines output (default: stdout)')
    args = parser.parse_args()
    layout = LAYOUTS[args.suite]
    if args.all:
        records = all_records(suite=args.suite)
    elif args.arm and args.scenario:
        bench_suite.check_scenario(args.suite, args.scenario)
        if args.dir is None and args.arm not in layout:
            parser.error(f'suite {args.suite} has no layout for {args.arm}; give --dir')
        records = scene_records(args.arm, args.scenario, args.dir or ROOT / layout[args.arm][0] / layout[args.arm][1][args.scenario],
                                args.suite)
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
