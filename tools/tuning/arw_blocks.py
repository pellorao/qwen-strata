"""Blocks of consecutive ARW instances under one deployed condition (measurement rule 预热与连跑).

A block = one condition deployment and cold load, then `warmup + scored` instances of the plan's ARW scenario run in one
tools.arw.measure cell (the model stays loaded between instances; every instance is a fresh ARW Reviewer thread on the
pinned ARW).  The first `warmup` valid instances are flagged warm-up and are not scored.  A round = one block per condition
still sampled, in the order given (the caller reverses it every round).  Results stay in `<out>/blocks/r<N>-<condition>/cell/`
(score.json, candidates.json, report per instance; blind judging and statistics go through ARW `pool` and `summary`).

    python3 -m tools.tuning.arw_blocks round --plan P --out OUT --work W --round 1 --order sampling-greedy,sampling-card,... --scored 3
    python3 -m tools.tuning.arw_blocks restore --plan P
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import time

from tools.tuning import arw_dimension as dim

ROOT = dim.ROOT
BLOCK_STARTS_PER_6H = 12  # one dimension = 4 blocks (ABBA); the usage guard's default cap fits one cell


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


def run_block(plan_path, out, work, round_number, condition_name, scored, warmup=1):
    from tools.arw import measure, run as arw_run
    from tools.ops.deploy import deploy
    from tools.ops.measurement_host import MeasurementHost
    plan, dimensions, conditions = dim.load_plan(plan_path)
    if plan['schema'] != 'arw-dimension-v2':
        raise ValueError('A v1 plan ran on the frozen ARW; write a v2 plan (scenario, effort) for the pinned ARW')
    dimension = next(iter(dimensions.values()))
    checks = dimension['conditions'][condition_name]
    condition, digest = conditions[condition_name]
    folder = out / 'blocks' / f'r{round_number}-{condition_name}'
    folder.mkdir(parents=True)
    arw_run.init(work, plan['host'], context_window=checks.get('context_window'))
    wait_lease_free(plan['host'], out / 'controller', out)
    log(out, f'{folder.name}: deploy condition {condition_name} (sha {digest[:12]})')
    deployed = deploy(plan['host'], condition=(condition, digest))
    dim.save(folder / 'deploy.json', deployed)
    host = MeasurementHost(plan['host'], condition=condition)
    offset, service_offset = host.log_offset(plan['model']), host.log_offset()
    started = datetime.now().isoformat(timespec='seconds')
    total = warmup + scored
    log(out, f'{folder.name}: {total} instances ({warmup} warm-up)')
    error = None
    try:
        cell = measure.run_cell(work, plan['scenario'], folder / 'cell', total, plan.get('effort', arw_run.EFFORT),
                                 max_starts=BLOCK_STARTS_PER_6H)
    except RuntimeError as exc:
        error, cell = str(exc), []
    finally:
        arw_run.stop(work)
    engine_log = host.log_bytes_since(plan['model'], offset).decode(errors='replace')
    (folder / 'engine-log-since-deploy.txt').write_text(engine_log)
    service_log = host.log_bytes_since(None, service_offset).decode(errors='replace')
    (folder / 'service-log-since-deploy.txt').write_text(service_log)
    environment = host.engine_environment(condition.get('model_environment', {})) if condition.get('model_environment') else []
    effect = dim.verify_effect(engine_log, environment, condition, host.configuration(plan['model']), checks, service_log)
    valid = [r['name'] for r in cell if r['valid']]
    record = {'round': round_number, 'condition': condition_name, 'condition_sha256': digest, 'folder': str(folder),
              'started': started, 'warmup': warmup, 'warmup_instances': valid[:warmup], 'scored_instances': valid[warmup:],
              'void_instances': [r['name'] for r in cell if not r['valid']], 'error': error,
              'model_configuration_sha256': deployed['model_configuration_sha256'], 'effect': effect}
    dim.save(folder / 'block.json', record)
    log(out, f'{folder.name}: {len(valid)} valid instances, effect ok={effect["ok"]} {effect["problems"]} {error or ""}')
    if error or not effect['ok'] or len(valid) != total:
        raise RuntimeError(f'{folder.name} needs review: {error}, {len(valid)}/{total} valid, {effect["problems"]}')
    return record


def run_round(plan_path, out, work, round_number, order, scored, warmup=1):
    out.mkdir(parents=True, exist_ok=True)
    for name in order:
        marker = out / 'blocks' / f'r{round_number}-{name}' / 'block.json'
        if marker.is_file():
            log(out, f'{marker.parent.name}: done earlier, skipped')
            continue
        run_block(plan_path, out, work, round_number, name, scored[name] if isinstance(scored, dict) else scored, warmup)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('round', 'restore'))
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--work', type=Path, help='ARW work directory (isolated HOME), e.g. /tmp/qwen-strata/<task>/work')
    parser.add_argument('--round', type=int)
    parser.add_argument('--order')
    parser.add_argument('--scored', type=int)
    parser.add_argument('--warmup', type=int, default=1)
    args = parser.parse_args()
    if args.command == 'restore':
        print(json.dumps(dim.restore(args.plan), ensure_ascii=False, indent=2))
    else:
        run_round(args.plan, args.out.resolve(), args.work, args.round, args.order.split(','), args.scored, args.warmup)


if __name__ == '__main__':
    main()
