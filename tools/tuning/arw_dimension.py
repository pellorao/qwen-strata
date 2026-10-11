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

from tools.ops.deployment_source import load_condition, model_configuration

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / 'config/model-catalog.json'
CODEX = Path.home() / ('.local/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/'
                       'vendor/x86_64-unknown-linux-musl/bin/codex')
MEASUREMENT_NOTE = 'benchmarks/reviewer-suite-v1/measurement-note.txt'


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


def verify_effect(log, environment_rows, condition, configuration, checks):
    """Compare one cold start's engine log and process environment with the deployed condition."""
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
    wanted = {k: None if v is None else str(v) for k, v in condition.get('model_environment', {}).items()}
    # an engine ARW already stopped leaves only the log lines as evidence
    if wanted and len(environment_rows) > 1:
        problems.append(f'expected one running engine process, found {len(environment_rows)}')
    elif wanted and environment_rows and environment_rows[0]['environment'] != wanted:
        problems.append(f'engine environment {environment_rows[0]["environment"]} differs from {wanted}')
    for pattern in checks.get('log_present', []):
        if not re.search(pattern, log):
            problems.append('missing log line: ' + pattern)
    for pattern in checks.get('log_absent', []):
        if re.search(pattern, log):
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


def selection(plan, condition):
    note = (ROOT / MEASUREMENT_NOTE).read_bytes()
    codex = CODEX.read_bytes()
    fixed = plan['fixed_conditions']
    if sha(note) != fixed['measurement_note_sha256'] or sha(codex) != fixed['native_cli_sha256']:
        raise ValueError('Measurement note or native CLI differs from the frozen plan')
    return {'model': plan['model'], 'effort': fixed['effort'], 'model_owner': 'arw', 'engine_overrides': {},
            'startup_instructions': True, 'project_compaction_instructions': False,
            'generation_policy': 'first-delivery-only', 'loop_prevention_instructions': False,
            'archive_http': True, 'automatic_continuation': False,
            'native_cli': {'executable': str(CODEX), 'version': fixed['codex'], 'sha256': sha(codex)},
            'loop_reminder': 'off', 'measurement_note': {'path': MEASUREMENT_NOTE, 'sha256': sha(note)},
            'deployment_condition': condition}


def prepare(plan, condition, folder):
    """Fresh ARW batch for one slot; only its first handoff runs, the others stay deferred."""
    folder.mkdir(parents=True)
    arw = folder / 'arw'
    subprocess.run([sys.executable, '-m', 'tools.reviewer.freeze_arw_source', '--manifest',
                    plan['fixed_conditions']['arw_source_manifest'], '--out', str(arw)],
                   cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    (arw / 'config.json').write_text(extract_agent_config((arw / 'docs/manuals/agent-cli.md').read_text()))
    save(folder / 'selection-source.json', selection(plan, condition))
    subprocess.run(['git', 'init', '-q'], cwd=arw, check=True)
    env = dict(os.environ, CODEX_THREAD_ID=plan['codex_thread_id'])
    with (folder / 'prepare.json').open('w') as out, (folder / 'prepare.err').open('w') as err:
        subprocess.run(['node', 'scripts/reviewer-capability-conformance.mjs', 'prepare', '--reviewer', plan['reviewer']],
                       cwd=arw, env=env, stdout=out, stderr=err, check=True)
    prepared = json.loads((folder / 'prepare.json').read_text())
    prepared.update(repositoryRoot=str(arw.resolve()), programDirectory=str(arw.resolve()),
                    identity={'platform': 'codex', 'sessionId': plan['codex_thread_id']})
    save(folder / 'preparation.json', prepared)
    return [h['instanceId'] for h in prepared['handoffs']]


def preflight(plan, folder):
    subprocess.run([sys.executable, '-m', 'tools.ops.measurement_host', '--host', plan['host'],
                    '--selection', str(folder / 'selection-source.json'), '--out', str(folder / 'preflight')],
                   cwd=ROOT, check=True)


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
        prepare(plan, condition, folder)
        deployed = deploy(plan['host'], condition=(condition, digest))
        save(folder / 'deploy.json', deployed)
        preflight(plan, folder)
        host = MeasurementHost(plan['host'], condition=condition)
        if 'expert_profile_sha256' in dimension['conditions'][name] and \
                host.profile_sha256(plan['model']) != dimension['conditions'][name]['expert_profile_sha256']:
            raise RuntimeError(name + ': installed expert profile differs from the frozen one')
        offset = host.log_offset(plan['model'])
        started = datetime.now().isoformat(timespec='seconds')
        measured = subprocess.run(
            [sys.executable, '-m', 'tools.reviewer.arw_measure', '--host', plan['host'], '--out', str(folder / 'run'),
             '--selection', str(folder / 'preflight/selection.json'), '--preparation', str(folder / 'preparation.json'),
             '--catalog', str(CATALOG), '--limit', '1'],
            cwd=ROOT, env=dict(os.environ, CODEX_THREAD_ID=plan['codex_thread_id']))
        log = host.log_bytes_since(plan['model'], offset).decode(errors='replace')
        (folder / 'engine-log-since-deploy.txt').write_text(log)
        environment = host.engine_environment(condition.get('model_environment', {})) \
            if condition.get('model_environment') else []
        effect = verify_effect(log, environment, condition, host.configuration(plan['model']),
                               dimension['conditions'][name])
        records.append({'slot': slot, 'condition': name, 'condition_sha256': digest, 'folder': str(folder),
                        'started': started, 'arw_measure_exit': measured.returncode,
                        'model_configuration_sha256': deployed['model_configuration_sha256'], 'effect': effect})
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
            result[name] = {'sha256': digest, 'flags_default_to_condition': flags,
                            'environment_default_to_condition': env,
                            'changes_default': rendered != default}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('check', 'run', 'restore'))
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--dimension')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--limit', type=int, help='Run at most N further slots of the schedule.')
    args = parser.parse_args()
    if args.command == 'check':
        result = check(args.plan)
    elif args.command == 'run':
        result = run(args.plan, args.dimension, args.out.resolve(), args.limit)
    else:
        result = restore(args.plan)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
