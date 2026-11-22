"""Run one engine-tuning dimension on ARW Reviewer instances: deploy each scheduled condition, run the instances of its
slot through the pinned ARW (tools.arw), verify the condition took effect.

Each slot: deploy the condition over the host default (stops the model, so the engine starts cold) -> `instances_per_slot`
instances of the plan's scenario with ARW owning the model (tools.arw.measure) -> check the engine log and process
environment against the condition.  `restore` deploys the host default again.  Plans of schema arw-dimension-v1 ran on the
frozen ARW; they stay readable (`check`) but cannot run any more.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

from tools.ops.deployment_source import load_condition, model_configuration

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ('arw-dimension-v1', 'arw-dimension-v2')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def load_plan(path):
    """Plan, its dimensions by id and each condition file with its SHA; refuse an inconsistent plan."""
    path = Path(path)
    plan = json.loads(path.read_text())
    if plan.get('schema') not in SCHEMAS:
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


def run(plan_path, dimension_id, out, work, limit=None):
    from tools.arw import measure, run as arw_run
    from tools.ops.deploy import deploy
    from tools.ops.measurement_host import MeasurementHost
    plan, dimensions, conditions = load_plan(plan_path)
    if plan['schema'] != 'arw-dimension-v2':
        raise ValueError('A v1 plan ran on the frozen ARW; write a v2 plan (scenario, effort) for the pinned ARW')
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
        arw_run.init(work, plan['host'], context_window=checks.get('context_window'))
        deployed = deploy(plan['host'], condition=(condition, digest))
        folder.mkdir(parents=True, exist_ok=True)
        save(folder / 'deploy.json', deployed)
        host = MeasurementHost(plan['host'], condition=condition)
        if 'expert_profile_sha256' in checks and host.profile_sha256(plan['model']) != checks['expert_profile_sha256']:
            raise RuntimeError(name + ': installed expert profile differs from the frozen one')
        offset, service_offset = host.log_offset(plan['model']), host.log_offset()
        started = datetime.now().isoformat(timespec='seconds')
        try:
            measure.run_cell(work, plan['scenario'], folder / 'cell', dimension.get('instances_per_slot', 1),
                             plan.get('effort', arw_run.EFFORT))
            error = None
        except RuntimeError as exc:
            error = str(exc)
        finally:
            arw_run.stop(work)
        log = host.log_bytes_since(plan['model'], offset).decode(errors='replace')
        (folder / 'engine-log-since-deploy.txt').write_text(log)
        service_log = host.log_bytes_since(None, service_offset).decode(errors='replace')
        (folder / 'service-log-since-deploy.txt').write_text(service_log)
        environment = host.engine_environment(condition.get('model_environment', {})) \
            if condition.get('model_environment') else []
        effect = verify_effect(log, environment, condition, host.configuration(plan['model']), checks, service_log)
        records.append({'slot': slot, 'condition': name, 'condition_sha256': digest, 'folder': str(folder),
                        'started': started, 'error': error, 'model_configuration_sha256': deployed['model_configuration_sha256'],
                        'effect': effect})
        save(progress, records)
        if error or not effect['ok']:
            raise RuntimeError(f'Slot {slot + 1} ({name}) needs review: {error}, {effect["problems"]}')
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
    parser.add_argument('command', choices=('check', 'run', 'restore'))
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--dimension')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--work', type=Path, help='run: ARW work directory (isolated HOME), e.g. /tmp/qwen-strata/<task>/work')
    parser.add_argument('--limit', type=int, help='Run at most N further slots of the schedule.')
    args = parser.parse_args()
    if args.command == 'check':
        result = check(args.plan)
    elif args.command == 'run':
        result = run(args.plan, args.dimension, args.out.resolve(), args.work, args.limit)
    else:
        result = restore(args.plan)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
