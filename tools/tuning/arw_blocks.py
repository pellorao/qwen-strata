"""Blocks of consecutive ARW instances under one deployed condition (measurement rule 预热与连跑).

A block = one condition deployment and cold load, `warmup` unscored instances, then `scored` scored instances of the
same ARW scenario run in one arw_measure batch (the model stays loaded between instances; every instance is a fresh
ARW Reviewer thread).  A round = one block per condition still sampled, in the order given (the caller reverses it
every round).  After the batch each instance is laid out as a benchmark-style instance directory
(`scenes/<condition>/codex-strata-high-a<N>`, the `strata-codex` layout of tools.reviewer.bench_records) so the
project scorer (bench_records -> bench_score -> blind_pool) takes it without changes.

    python3 -m tools.tuning.arw_blocks round --plan P --out OUT --round 1 --order sampling-greedy,sampling-card,... --scored 3
    python3 -m tools.tuning.arw_blocks restore --plan P
"""
import argparse
from datetime import datetime
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from tools.tuning import arw_dimension as dim
from tools.reviewer.bench_score import file_tree

ROOT = dim.ROOT
PATCHES = ('codex-0.163-synthetic-mount-targets', 'strata-measurement-time-limit', 'reviewer-private-scratch')


def stamp():
    return datetime.now().strftime('%F %T')


def log(out, text):
    with (Path(out) / 'blocks.log').open('a') as stream:
        stream.write(f'{stamp()} {text}\n')
    print(f'{stamp()} {text}', flush=True)


def wait_lease_free(host_id, folder, out, poll=60):
    """Never displace a holder: wait until the frontend lease is free (deploy itself aborts on a held lease)."""
    from tools.ops.measurement_host import MeasurementHost
    controller = MeasurementHost(host_id).controller(folder)
    announced = False
    while True:
        try:
            health = controller.call('/health', timeout=15)
        except OSError as error:  # the frontend restarts during deployments
            health = {'lease': 'unreachable', 'error': str(error)}
        if health.get('lease') == 'free':
            return
        if not announced:
            log(out, f"lease is {health.get('lease')}; waiting, not displacing")
            announced = True
        time.sleep(poll)


def next_attempt(scene):
    """Next a<N> number of a scene directory, counting every directory (void ones keep their number)."""
    numbers = [int(p.name.rsplit('-a', 1)[1]) for p in scene.glob('codex-strata-high-a*')] if scene.is_dir() else []
    return max(numbers, default=0) + 1


def run_block(plan_path, out, round_number, condition_name, scored, warmup=1):
    from tools.ops.deploy import deploy
    from tools.ops.measurement_host import MeasurementHost
    plan, dimensions, conditions = dim.load_plan(plan_path)
    dimension = next(iter(dimensions.values()))
    checks = dimension['conditions'][condition_name]
    condition, digest = conditions[condition_name]
    seconds = dimension['time_limit_seconds']
    total = warmup + scored
    folder = out / 'blocks' / f'r{round_number}-{condition_name}'
    ids = dim.prepare(plan, condition, folder / 'prep', dimension.get('reviewer'), checks.get('context_window'), seconds,
                      PATCHES, preparations=math.ceil(total / 3))
    preparations = sorted((folder / 'prep').glob('preparation*.json'))
    copies = {}
    for path in preparations:
        for handoff in json.loads(path.read_text())['handoffs']:
            copies[handoff['scenarioRoot']] = file_tree(handoff['scenarioRoot'])
    dim.save(folder / 'scenario-copies-all.json', copies)
    wait_lease_free(plan['host'], out / 'controller', out)
    log(out, f'{folder.name}: deploy condition {condition_name} (sha {digest[:12]})')
    deployed = deploy(plan['host'], condition=(condition, digest))
    dim.save(folder / 'deploy.json', deployed)
    dim.preflight(plan, folder / 'prep')
    host = MeasurementHost(plan['host'], condition=condition)
    catalog, catalog_sha = dim.host_catalog(plan['host'], folder, condition)
    offset, service_offset = host.log_offset(plan['model']), host.log_offset()
    started = datetime.now().isoformat(timespec='seconds')
    command = [sys.executable, '-m', 'tools.reviewer.arw_measure', '--host', plan['host'], '--out', str(folder / 'run'),
               '--selection', str(folder / 'prep/preflight/selection.json'), '--catalog', str(catalog), '--limit', str(total)]
    for path in preparations:
        command += ['--preparation', str(path)]
    log(out, f'{folder.name}: arw_measure {total} instances ({warmup} warm-up)')
    measured = subprocess.run(command, cwd=ROOT, env=dict(os.environ, CODEX_THREAD_ID=plan['codex_thread_id']),
                              stdout=(folder / 'arw_measure.out').open('w'), stderr=subprocess.STDOUT)
    engine_log = host.log_bytes_since(plan['model'], offset).decode(errors='replace')
    (folder / 'engine-log-since-deploy.txt').write_text(engine_log)
    service_log = host.log_bytes_since(None, service_offset).decode(errors='replace')
    (folder / 'service-log-since-deploy.txt').write_text(service_log)
    environment = host.engine_environment(condition.get('model_environment', {})) if condition.get('model_environment') else []
    effect = dim.verify_effect(engine_log, environment, condition, host.configuration(plan['model']), checks, service_log)
    subprocess.run([sys.executable, '-m', 'tools.reviewer.reviewer_scratch', '--remove', str(folder / 'run')], cwd=ROOT)
    results = json.loads((folder / 'run/results.json').read_text()) if (folder / 'run/results.json').is_file() else []
    record = {'round': round_number, 'condition': condition_name, 'condition_sha256': digest, 'folder': str(folder),
              'started': started, 'arw_measure_exit': measured.returncode, 'warmup': warmup, 'scored': scored,
              'model_configuration_sha256': deployed['model_configuration_sha256'], 'catalog_sha256': catalog_sha,
              'effect': effect, 'results': len(results)}
    dim.save(folder / 'block.json', record)
    log(out, f'{folder.name}: arw_measure exit {measured.returncode}, {len(results)} results, effect ok={effect["ok"]} {effect["problems"]}')
    if measured.returncode or not effect['ok'] or len(results) != total:
        raise RuntimeError(f'{folder.name} needs review: exit {measured.returncode}, results {len(results)}/{total}, {effect["problems"]}')
    layout(out, folder, record, results, copies)
    return record


def layout(out, folder, record, results, copies):
    """Benchmark-style instance directories for the scored results; the warm-up results stay in the block."""
    scene = out / 'scenes' / record['condition']
    scene.mkdir(parents=True, exist_ok=True)
    reports = {}
    for number, result in enumerate(results):
        if number < record['warmup']:
            continue
        attempt = next_attempt(scene)
        target = scene / f'codex-strata-high-a{attempt}'
        (target / 'run').mkdir(parents=True)
        dim.save(target / 'run/results.json', [result])
        (target / 'prep').symlink_to(folder / 'prep')
        (target / 'report').mkdir()
        report = Path(result['report'])
        if report.is_file():
            shutil.copyfile(report, target / 'report' / report.name)
        dim.save(target / 'scenario-copies.json', {k: v for k, v in copies.items() if k.endswith(result_root(result))} or None)
        dim.save(target / 'origin.json', {'block': folder.name, 'index': number, 'round': record['round'],
                                          'condition': record['condition'], 'instanceId': result['instanceId']})
        with (scene / 'schedule.jsonl').open('a') as stream:
            stream.write(json.dumps({'event': 'done', 'out': target.name, 'kind': 'valid'}) + '\n')
        reports[target.name] = result['instanceId']
    dim.save(folder / 'layout.json', reports)


def result_root(result):
    """The scenario root suffix of a result's instance (`<run uuid>/csp/<n>`), from its instance id."""
    uuid = result['instanceId'].split('-instance-')[0].removeprefix('default-')
    return f"{uuid}/csp/{result['instanceId'].rsplit('-instance-', 1)[1]}"


def run_round(plan_path, out, round_number, order, scored, warmup=1):
    out.mkdir(parents=True, exist_ok=True)
    for name in order:
        marker = out / 'blocks' / f'r{round_number}-{name}' / 'block.json'
        if marker.is_file():
            log(out, f'{marker.parent.name}: done earlier, skipped')
            continue
        run_block(plan_path, out, round_number, name, scored[name] if isinstance(scored, dict) else scored, warmup)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('round', 'restore'))
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--round', type=int)
    parser.add_argument('--order')
    parser.add_argument('--scored', type=int)
    parser.add_argument('--warmup', type=int, default=1)
    args = parser.parse_args()
    if args.command == 'restore':
        print(json.dumps(dim.restore(args.plan), ensure_ascii=False, indent=2))
    else:
        run_round(args.plan, args.out.resolve(), args.round, args.order.split(','), args.scored, args.warmup)


if __name__ == '__main__':
    main()
