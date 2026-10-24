"""Run one engine-tuning dimension on ARW Commit Audit: deploy each scheduled condition, run one instance, verify it took effect.

Each slot: prepare a fresh ARW batch -> deploy the condition over the host default (stops the model, so the
engine starts cold) -> source preflight -> arw_measure --limit 1 with ARW owning the model -> check the engine
log and process environment against the condition.  `restore` deploys the host default again.
"""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from tools.ops.deployment_source import load_condition, model_configuration, source_bytes
from tools.reviewer.harness_pins import codex_binary

ROOT = Path(__file__).resolve().parents[2]
CATALOG = 'config/model-catalog.json'
MEASUREMENT_NOTE = 'benchmarks/reviewer-suite-v1/measurement-note.txt'
# Scenario versions whose handoff needs its own measurement note: (reviewer, source manifest file) -> (plain note,
# time-limit template). Commit Audit v2, v3 and v3.1 (multi-model benchmark v2 draft) declare merged issue/spec
# requirements, which the note explains (user 2026-10-17).
COMMIT_AUDIT_NOTES = ('benchmarks/reviewer-suite-v1/measurement-note-commit-audit.txt',
                      'benchmarks/reviewer-suite-v1/measurement-note-time-limit-commit-audit.txt')
SCENARIO_NOTES = {
    ('commit-audit-reviewer', 'manifest-commit-audit-v2.json'): COMMIT_AUDIT_NOTES,
    ('commit-audit-reviewer', 'manifest-commit-audit-v3.json'): COMMIT_AUDIT_NOTES,
    ('commit-audit-reviewer', 'manifest-commit-audit-v3.1.json'): COMMIT_AUDIT_NOTES,
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def load_plan(path):
    """Plan, its dimensions by id and each condition file with its SHA; refuse an inconsistent plan."""
    path = Path(path)
    plan = json.loads(path.read_text())
    if plan.get('schema') != 'arw-dimension-v1':
        raise ValueError('Not an ARW dimension plan')
    conditions = {}
    for dimension in plan['dimensions']:
        schedule, declared = dimension['schedule'], dimension['conditions']
        if set(schedule) != set(declared) or dimension['default'] not in declared:
            raise ValueError(dimension['id'] + ': schedule, conditions and default disagree')
        if len({schedule.count(c) for c in declared}) != 1:
            raise ValueError(dimension['id'] + ': every condition needs the same number of repetitions')
        for name in declared:
            condition, digest = load_condition(path.parent / 'conditions' / (name + '.json'))
            if condition.get('id') != name or condition.get('model') != plan['model']:
                raise ValueError(name + ': condition file identity differs from the plan')
            conditions[name] = (condition, digest)
    return plan, {d['id']: d for d in plan['dimensions']}, conditions


def flag_values(started):
    """`--flag value` pairs of the logged engine command line (installation paths have no spaces)."""
    words = started.split()
    return {w: words[i + 1] if i + 1 < len(words) and not words[i + 1].startswith('--') else True
            for i, w in enumerate(words) if w.startswith('--')}


def verify_effect(log, environment_rows, condition, configuration, checks, service_log=''):
    """Compare one cold start's engine log and process environment with the deployed condition.

    log_present / log_absent also search the service log, where the native sampling trace lands."""
    problems, started = [], re.findall(r'engine started: (.*)', log)
    if len(started) != 1:
        problems.append(f'expected one engine start in the instance log, found {len(started)}')
    flags = flag_values(started[-1]) if started else {}
    args = configuration['args']
    for key in condition.get('model_overrides', {}):
        flag = '--' + key
        expected = args[args.index(flag) + 1] if flag in args else None
        if flags.get(flag) != expected:
            problems.append(f'{flag}: engine ran with {flags.get(flag)!r}, condition deploys {expected!r}')
    if checks.get('context_window') is not None and flags.get('--max-context') != str(checks['context_window']):
        problems.append(f"--max-context: engine ran with {flags.get('--max-context')!r}, "
                        f"the slot selects tier {checks['context_window']}")
    installed = configuration.get('request_defaults', {})
    for key, value in condition.get('request_defaults', {}).items():
        if installed.get(key) != value:
            problems.append(f'request default {key}: installed {installed.get(key)!r}, condition deploys {value!r}')
    wanted = {k: None if v is None else str(v) for k, v in condition.get('model_environment', {}).items()}
    # an engine ARW already stopped leaves only the log lines as evidence
    if wanted and len(environment_rows) > 1:
        problems.append(f'expected one running engine process, found {len(environment_rows)}')
    # an elevated engine hides its environment from this unelevated reader; the log lines remain
    elif wanted and environment_rows and environment_rows[0]['environment'] is not None \
            and environment_rows[0]['environment'] != wanted:
        problems.append(f'engine environment {environment_rows[0]["environment"]} differs from {wanted}')
    logs = log + '\n' + service_log
    for pattern in checks.get('log_present', []):
        if not re.search(pattern, logs):
            problems.append('missing log line: ' + pattern)
    for pattern in checks.get('log_absent', []):
        if re.search(pattern, logs):
            problems.append('unexpected log line: ' + pattern)
    facts = {name: (re.findall(pattern, log) or [None])[-1] for name, pattern in (
        ('verify_window', r'strata verify: window up to (\d+) tokens'),
        ('profile', r'profile (\S+): \d+ ranked pairs'),
        ('cpu_share', r'(the CPU share is ON by default[^\n]*|the CPU prefill share is not armed[^\n]*|'
                      r'the CPU share is off for this run[^\n]*|WARNING STRATA_PREFILL_CPU_SHARE[^\n]*)'),
        ('commit_left_gib', r'Windows commit: ([\d.]+) GiB left'),
        ('large_pages', r'large pages \((\d+) B\)'))}
    return {'ok': not problems, 'problems': problems, 'engine_started': started[-1] if started else None,
            'environment': environment_rows, 'facts': facts}


def extract_agent_config(manual):
    """The Codex config block of ARW's agent-cli manual, as prepare.sh took it."""
    section = re.search(r'如果使用 Codex(.*?)如果使用 Claude Code', manual, re.S)
    block = section and re.search(r'^```json\n(.*?)^```$', section.group(1), re.S | re.M)
    if not block:
        raise ValueError('agent-cli manual has no Codex config block')
    json.loads(block.group(1))
    return block.group(1)


def time_limited_note(fixed, folder, time_limit_seconds):
    """Render the plan's note template with this batch's review time limit into the batch folder."""
    template = fixed['measurement_note_template']
    raw = (ROOT / template['path']).read_bytes()
    if sha(raw) != template['sha256']:
        raise ValueError('Measurement note template differs from the frozen plan')
    if type(time_limit_seconds) is not int or time_limit_seconds <= 0:
        raise ValueError('A time-limited plan needs a positive whole number of seconds')
    text = raw.decode().replace('{{time_limit_minutes}}', f'{time_limit_seconds / 60:.1f}'.removesuffix('.0'))
    if '{{' in text:
        raise ValueError('Measurement note template has an unrendered placeholder')
    rendered = folder / 'measurement-note.txt'
    rendered.write_text(text)
    # A prep outside the project (OpenAI arm, /tmp) keeps the absolute path; readers join it onto ROOT.
    path = rendered.relative_to(ROOT) if rendered.is_relative_to(ROOT) else rendered
    return ({'path': str(path), 'sha256': sha(text.encode())},
            {'measurement_note_template': template, 'review_time_limit_seconds': time_limit_seconds})


def plain_note(fixed):
    """The plan's frozen measurement note: the common note, or the scenario note the plan names (e.g. Commit Audit
    adds how repeated issue and spec requirements are scored, user 2026-10-17)."""
    path = fixed.get('measurement_note_path', MEASUREMENT_NOTE)
    raw = (ROOT / path).read_bytes()
    if sha(raw) != fixed['measurement_note_sha256']:
        raise ValueError('Measurement note differs from the frozen plan')
    return {'path': path, 'sha256': sha(raw)}


def required_scenario_note(fixed, reviewer):
    """Refuse a plan that would hand a scenario needing its own note (SCENARIO_NOTES) the common note or another one,
    instead of falling back silently."""
    wanted = SCENARIO_NOTES.get((reviewer, Path(fixed['arw_source_manifest']).name))
    if wanted is None:
        return
    limited = 'measurement_note_template' in fixed
    named = fixed['measurement_note_template']['path'] if limited else fixed.get('measurement_note_path')
    if named is None or Path(named) != Path(wanted[limited]):
        raise ValueError(f"{reviewer} on {Path(fixed['arw_source_manifest']).name} needs the measurement note "
                         f"{'template ' if limited else ''}{wanted[limited]}, not {named or 'the common note'}")


def selection(plan, condition, context_window=None, folder=None, time_limit_seconds=None, reviewer=None):
    """The plan binds its own Codex version (`codex`, `native_cli_sha256`): the benchmark copy of that version, so a
    frozen plan keeps the harness it was frozen with after harness_pins moves on (measurement rule "harness 版本")."""
    fixed = plan['fixed_conditions']
    executable = codex_binary(fixed['codex'])
    if not executable.is_file():
        raise ValueError(f"The plan's Codex {fixed['codex']} benchmark copy is missing: {executable}")
    codex = executable.read_bytes()
    required_scenario_note(fixed, reviewer or plan.get('reviewer'))
    if 'measurement_note_template' in fixed:
        note, limit = time_limited_note(fixed, folder, time_limit_seconds)
    else:
        if time_limit_seconds is not None:
            raise ValueError('The plan has no time-limited measurement note')
        note, limit = plain_note(fixed), {}
    if sha(codex) != fixed['native_cli_sha256']:
        raise ValueError('Native CLI differs from the frozen plan')
    return {'model': plan['model'], 'effort': fixed['effort'], 'model_owner': 'arw', 'engine_overrides': {},
            'startup_instructions': True, 'project_compaction_instructions': True,
            'generation_policy': 'first-delivery-only', 'loop_prevention_instructions': False,
            'archive_http': True, 'automatic_continuation': False,
            'native_cli': {'executable': str(executable), 'version': fixed['codex'], 'sha256': sha(codex)},
            'loop_reminder': 'off', 'measurement_note': note, **limit,
            # the multi-model benchmark disables Codex web search on every arm (D5); a plan may bind the same
            **({'web_search': fixed['web_search']} if 'web_search' in fixed else {}),
            'deployment_condition': condition,
            # a published context tier the caller selects; omitted, ARW starts the installation default tier
            **({} if context_window is None else {'context_window': context_window})}


def prepare(plan, condition, folder, reviewer=None, context_window=None, time_limit_seconds=None, harness_patches=(),
            preparations=1):
    """Fresh ARW batch for one slot; only its first handoff(s) run, the others stay deferred. harness_patches: names
    from freeze_arw_source.HARNESS_PATCHES applied to the materialized copy (recorded in harness-patches.json).
    preparations > 1: further ARW preparations in the same checkout (preparation-2.json, ...; one ARW preparation holds
    three handoffs), so a block of more than three instances runs in one arw_measure batch."""
    folder.mkdir(parents=True)
    arw = folder / 'arw'
    subprocess.run([sys.executable, '-m', 'tools.reviewer.freeze_arw_source', '--manifest',
                    plan['fixed_conditions']['arw_source_manifest'], '--out', str(arw)],
                   cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    if harness_patches:
        from tools.reviewer.freeze_arw_source import apply_harness_patch
        save(folder / 'harness-patches.json', [apply_harness_patch(name, arw) for name in harness_patches])
    (arw / 'config.json').write_text(extract_agent_config((arw / 'docs/manuals/agent-cli.md').read_text()))
    save(folder / 'selection-source.json', selection(plan, condition, context_window, folder, time_limit_seconds, reviewer))
    subprocess.run(['git', 'init', '-q'], cwd=arw, check=True)
    env = dict(os.environ, CODEX_THREAD_ID=plan['codex_thread_id'])
    ids = []
    for number in range(1, preparations + 1):
        suffix = '' if number == 1 else f'-{number}'
        with (folder / f'prepare{suffix}.json').open('w') as out, (folder / f'prepare{suffix}.err').open('w') as err:
            subprocess.run(['node', 'scripts/reviewer-capability-conformance.mjs', 'prepare', '--reviewer', reviewer or plan['reviewer']],
                           cwd=arw, env=env, stdout=out, stderr=err, check=True)
        prepared = json.loads((folder / f'prepare{suffix}.json').read_text())
        prepared.update(repositoryRoot=str(arw.resolve()), programDirectory=str(arw.resolve()),
                        identity={'platform': 'codex', 'sessionId': plan['codex_thread_id']})
        save(folder / f'preparation{suffix}.json', prepared)
        ids += [h['instanceId'] for h in prepared['handoffs']]
    return ids


def preflight(plan, folder):
    subprocess.run([sys.executable, '-m', 'tools.ops.measurement_host', '--host', plan['host'],
                    '--selection', str(folder / 'selection-source.json'), '--out', str(folder / 'preflight')],
                   cwd=ROOT, check=True)


def host_catalog(host, folder, condition=None):
    """The model catalog as this host's installation holds it (only the served model, its default tier); the
    project catalog lists every quantization, which the host no longer publishes."""
    raw = source_bytes(CATALOG, host, condition=condition)
    path = folder / 'host-model-catalog.json'
    path.write_bytes(raw)
    return path, sha(raw)


def run(plan_path, dimension_id, out, limit=None):
    from tools.ops.deploy import deploy
    from tools.ops.measurement_host import MeasurementHost
    plan, dimensions, conditions = load_plan(plan_path)
    dimension = dimensions[dimension_id]
    if dimension.get('blocked'):
        raise ValueError(dimension_id + ' is blocked: ' + dimension['blocked'])
    out.mkdir(parents=True, exist_ok=True)
    progress = out / 'progress.json'
    records = json.loads(progress.read_text()) if progress.exists() else []
    if any(r['slot'] != i or r['condition'] != dimension['schedule'][i] for i, r in enumerate(records)):
        raise ValueError('Recorded slots differ from the frozen schedule')
    if records and not records[-1]['effect']['ok']:
        raise RuntimeError('The last slot failed its effect check; decide on the rerun before continuing')
    pending = list(enumerate(dimension['schedule']))[len(records):]
    for slot, name in pending[:limit]:
        condition, digest = conditions[name]
        folder = out / f'{slot + 1:02d}-{name}'
        checks = dimension['conditions'][name]
        prepare(plan, condition, folder, dimension.get('reviewer'), checks.get('context_window'))
        deployed = deploy(plan['host'], condition=(condition, digest))
        save(folder / 'deploy.json', deployed)
        preflight(plan, folder)
        host = MeasurementHost(plan['host'], condition=condition)
        if 'expert_profile_sha256' in dimension['conditions'][name] and \
                host.profile_sha256(plan['model']) != dimension['conditions'][name]['expert_profile_sha256']:
            raise RuntimeError(name + ': installed expert profile differs from the frozen one')
        catalog, catalog_sha = host_catalog(plan['host'], folder, condition)
        offset, service_offset = host.log_offset(plan['model']), host.log_offset()
        started = datetime.now().isoformat(timespec='seconds')
        measured = subprocess.run(
            [sys.executable, '-m', 'tools.reviewer.arw_measure', '--host', plan['host'], '--out', str(folder / 'run'),
             '--selection', str(folder / 'preflight/selection.json'), '--preparation', str(folder / 'preparation.json'),
             '--catalog', str(catalog), '--limit', str(dimension.get('instances_per_slot', 1))],
            cwd=ROOT, env=dict(os.environ, CODEX_THREAD_ID=plan['codex_thread_id']))
        log = host.log_bytes_since(plan['model'], offset).decode(errors='replace')
        (folder / 'engine-log-since-deploy.txt').write_text(log)
        service_log = host.log_bytes_since(None, service_offset).decode(errors='replace')
        (folder / 'service-log-since-deploy.txt').write_text(service_log)
        environment = host.engine_environment(condition.get('model_environment', {})) \
            if condition.get('model_environment') else []
        effect = verify_effect(log, environment, condition, host.configuration(plan['model']), checks, service_log)
        records.append({'slot': slot, 'condition': name, 'condition_sha256': digest, 'folder': str(folder),
                        'started': started, 'arw_measure_exit': measured.returncode,
                        'model_configuration_sha256': deployed['model_configuration_sha256'],
                        'catalog_sha256': catalog_sha, 'effect': effect})
        save(progress, records)
        if measured.returncode or not effect['ok']:
            raise RuntimeError(f'Slot {slot + 1} ({name}) needs review: exit {measured.returncode}, {effect["problems"]}')
    return records


def restore(plan_path):
    """Deploy the host default (after the winner, if any, is committed to the host configuration)."""
    from tools.ops.deploy import deploy
    from tools.ops.measurement_host import MeasurementHost
    plan, _, _ = load_plan(plan_path)
    deployed = deploy(plan['host'])
    return {'deploy': deployed, 'sources': MeasurementHost(plan['host']).verify_sources()['source_sha_verified']}


def check(plan_path):
    """No-model review: each condition rendered over the current host default, and what it changes."""
    plan, dimensions, conditions = load_plan(plan_path)
    default = model_configuration(plan['model'], plan['host'])
    result = {}
    for dimension in dimensions.values():
        for name in dimension['conditions']:
            condition, digest = conditions[name]
            rendered = model_configuration(plan['model'], plan['host'], condition=condition)
            flags = {f: (default['args'][default['args'].index(f) + 1] if f in default['args'] else None,
                         rendered['args'][rendered['args'].index(f) + 1] if f in rendered['args'] else None)
                     for f in ('--' + k for k in condition.get('model_overrides', {}))}
            env = {k: (default.get('engine_environment', {}).get(k), rendered.get('engine_environment', {}).get(k))
                   for k in condition.get('model_environment', {})}
            sampling = {k: (default.get('request_defaults', {}).get(k), rendered.get('request_defaults', {}).get(k))
                        for k in condition.get('request_defaults', {})}
            result[name] = {'sha256': digest, 'flags_default_to_condition': flags,
                            'environment_default_to_condition': env,
                            'request_defaults_default_to_condition': sampling,
                            'changes_default': rendered != default}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('check', 'run', 'restore', 'prepare'))
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--dimension')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--limit', type=int, help='Run at most N further slots of the schedule.')
    parser.add_argument('--reviewer', help='prepare: ARW reviewer of the batch (default: the plan reviewer)')
    parser.add_argument('--context-window', type=int, help='prepare: published context tier the batch selects')
    parser.add_argument('--time-limit-seconds', type=int,
                        help='prepare: review time limit of the batch, rendered into the plan note template')
    args = parser.parse_args()
    if args.command == 'check':
        result = check(args.plan)
    elif args.command == 'prepare':
        # a benchmark batch on the deployed default: fresh ARW preparation and preflight, no deployment
        plan, _, _ = load_plan(args.plan)
        result = prepare(plan, None, args.out.resolve(), args.reviewer, args.context_window, args.time_limit_seconds)
        preflight(plan, args.out.resolve())
    elif args.command == 'run':
        result = run(args.plan, args.dimension, args.out.resolve(), args.limit)
    else:
        result = restore(args.plan)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
