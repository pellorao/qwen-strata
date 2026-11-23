"""STRATA_SM86_PERF speed comparison, A=current (plain deploy, 8 sm_86 switches on) vs B=STRATA_SM86_PERF=0
(deploy --condition), blocks ABBA BAAB ABBA. Reuses the frozen pool-workers driver's workload, block runner and
schedule grouping unchanged; only the conditions and the per-block switch check differ.

Run from the project root: python3 benchmarks/resource-calibration-v1/iq3_xxs-sm86-perf-v024-2026-10-24/run.py [schedule] [out].
Every exit restores the plain deployment.
"""
import importlib.util, json, signal, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BENCH = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location(
    'pool_workers_run', ROOT / 'benchmarks/resource-calibration-v1/iq3_xxs-pool-workers-v024-2026-10-24/run.py')
base = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(base)
from tools.ops.measurement_host import MeasurementHost
from tools.ops.deployment_source import load_condition
from tools.metrics.prompt_policy import compaction_config
from tools.reviewer.wsl_client import save

SCHEDULE = sys.argv[1] if len(sys.argv) > 1 else 'ABBABAABABBA'
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / '.tmp/sm86-perf-1024/run'
CONDITION_FILE = BENCH / 'condition-sm86-perf-0.json'
POOL_WORKERS = 23  # both conditions; run_block checks it on the engine command line
SWITCH_LINE = 'exact speed switches on by default'
SWITCHES_ON = ('strata: sm_86 (Ampere): 8 exact speed switches on by default (STRATA_SM86_PERF=0 turns them off; '
               'a switch you set is kept): ADAPT_NOWAIT CPU_IQ_ALL_EXACT1 SIDE_MIXER ATTN_DAILY GR_UP75 GU_SWIGLU '
               'QSA_ROWS B6_MMVQ_ROWS')


def check_switches(folder, letter):
    """A: the engine announced exactly the 8 switches (ADAPT_LAG is ours); B: it announced none."""
    lines = [l.strip() for l in (folder / 'engine-request-log.txt').read_text(errors='replace').splitlines()
             if SWITCH_LINE in l]
    ok = lines == [SWITCHES_ON] if letter == 'A' else lines == []
    save(folder / 'switch-check.json', {'plan': letter, 'lines': lines, 'ok': ok})
    if not ok:
        raise RuntimeError(f'Block {folder.name}: engine speed switches differ from condition {letter}: {lines}')


def deploy(letter):
    """Plain or condition deploy through tools.ops.deploy; wait while the lease is held, never preempt."""
    cmd = [sys.executable, '-m', 'tools.ops.deploy']
    if letter == 'B':
        cmd += ['--condition', str(CONDITION_FILE)]
    for attempt in range(60):
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        if r.returncode == 0:
            return json.loads(r.stdout)
        if 'lease is held' not in r.stderr:
            raise RuntimeError('deploy failed: ' + r.stderr[-500:])
        print('lease held, waiting', flush=True); time.sleep(60)
    raise RuntimeError('lease stayed held')


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    def terminate(signum, frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, terminate); signal.signal(signal.SIGHUP, terminate)
    data, texts = base.workload()
    compaction_config({}, OUT / 'prompt-binding')
    condition = load_condition(CONDITION_FILE)[0]
    progress = {'schedule': SCHEDULE, 'blocks': [], 'deploys': [], 'status': 'running', 'started_at': time.time()}
    try:
        for g, (letter, numbers) in enumerate(base.groups(SCHEDULE), 1):
            progress['deploys'].append(deploy(letter)); save(OUT / 'progress.json', progress)
            host = MeasurementHost(condition=condition if letter == 'B' else None)
            save(OUT / f'source-verification-{g:02d}.json', host.verify_sources())
            with host.controller(OUT / f'controller-{g:02d}') as owner:
                for number in numbers:
                    progress['active'] = number; save(OUT / 'progress.json', progress)
                    folder = OUT / f'block-{number:02d}-{letter}'
                    progress['blocks'].append(base.run_block(owner, host, number, letter, data, texts, folder, POOL_WORKERS))
                    check_switches(folder, letter)
                    print('BLOCK DONE', number, letter, flush=True)
        progress['status'] = 'complete'
    except BaseException as error:
        progress['status'] = f'stopped: {type(error).__name__}: {error}'
        raise
    finally:
        try:
            progress['final_deploy'] = deploy('A')
        except Exception as error:
            progress['final_deploy'] = f'RESTORE FAILED: {error}'
        progress['finished_at'] = time.time(); progress.pop('active', None)
        save(OUT / 'progress.json', progress)
        print(json.dumps({'status': progress['status'], 'final': str(progress['final_deploy'])[:80]}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
