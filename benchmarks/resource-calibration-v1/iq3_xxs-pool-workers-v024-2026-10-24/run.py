"""Pool-workers speed comparison, A=23 (plain deploy) vs B=15 (deploy --condition), blocks ABBA BAAB ABBA.

Run from the project root: python3 benchmarks/resource-calibration-v1/iq3_xxs-pool-workers-v024-2026-10-24/run.py [schedule] [out]. Every exit restores the plain deployment.
"""
import copy, json, re, signal, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BENCH = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from tools.ops.measurement_host import MeasurementHost
from tools.ops.deployment_source import load_condition
from tools.reviewer.arw_measure import stop_and_capture_engine_log, capture_engine_log
from tools.metrics.prompt_policy import verify_loaded_startup, compaction_config
from tools.metrics.strata_tokens import engine_rates
from tools.metrics import host_telemetry
from tools.tuning.resource_calibration import logical_request
from tools.reviewer.wsl_client import save

SCHEDULE = sys.argv[1] if len(sys.argv) > 1 else 'ABBABAABABBA'
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / '.tmp/pool-workers-1024/run'
SETTLE_SECONDS = 20
LIMIT_SECONDS = 150
MODEL = 'IQ3_XXS'
MAX_CONTEXT = 206584
STARTUP_SHA = '1cae169a1b1ebcafbd6b0562992d377c84a550f4cd8bea7184340cf033cd17f6'
RECORDS = 787
WARMUP_HEADER = 'Warm-up pass {n}; this request is not scored.\n'
CHAT = {'temperature': 0.0, 'top_p': 1.0, 'top_k': 20, 'max_tokens': 24576, 'reasoning_budget_tokens': 8192,
        'min_p': 0.0, 'presence_penalty': 0.0, 'frequency_penalty': 0.0, 'repetition_penalty': 1.0,
        'penalty_last_n': 64, 'reasoning_effort': 'high', 'stream': True}
EXPECTED_SHA = ['d8bd48d07d9d421b2b08af2d9df868d0c10682808a394d185fec53d52fcdc32d',
                '7858b4d8c4ffec4d618a32360ac38ddf3eca502517bbcf75259d526eef67d9ba',
                'fa37bcf24496963a4fc16c7dd3a30ac3c2637a6b65eb4e6db364ee3ad52073ab']


def workload():
    import hashlib, importlib.util
    spec = importlib.util.spec_from_file_location('w', ROOT / 'benchmarks/resource-calibration-v1/workload.py')
    w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)
    data = w.build(RECORDS)
    texts = [data['shared_prefix'] + c['question'] for c in data['cases']]
    if [hashlib.sha256(t.encode()).hexdigest() for t in texts] != EXPECTED_SHA:
        raise RuntimeError('Frozen workload changed')
    return data, texts


def run_block(owner, host, number, letter, data, texts, folder, expected_workers):
    folder.mkdir()
    row = {'block': number, 'plan': letter, 'pool_workers': expected_workers, 'started_at': time.time()}
    time.sleep(SETTLE_SECONDS)
    if owner.call('/model/status')['status'] != 'stopped':
        raise RuntimeError('Model was not stopped before the block')
    offset = host.log_offset(MODEL)
    status, row['load_seconds'] = owner.start(model=MODEL)
    health = status['native_health']
    save(folder / 'start-status.json', {'status': status['status'], 'max_context': health.get('max_context'),
                                         'model_pid': status.get('model_pid'), 'startup': health['startup_instructions']})
    row['model_pid'] = status.get('model_pid')
    if health.get('max_context') != MAX_CONTEXT:
        raise RuntimeError('Loaded capacity differs from the deployed default')
    verify_loaded_startup(health['startup_instructions'], STARTUP_SHA)
    started = re.findall(r'engine started: (.*)', host.log_bytes_since(MODEL, offset).decode(errors='replace'))
    row['engine_args'] = started[-1] if started else None
    if not started or f'--pool-workers {expected_workers}' not in started[-1]:
        raise RuntimeError('Engine pool-workers differs from the condition: ' + str(row['engine_args']))
    telemetry = host_telemetry.start(host, folder); row['telemetry_pid'] = telemetry.get('pid')
    try:
        row['requests'] = []
        for phase in ('warmup', 'measured'):
            for i, (case, text) in enumerate(zip(data['cases'], texts), 1):
                if phase == 'warmup':
                    text = WARMUP_HEADER.format(n=number) + text
                body = copy.deepcopy(CHAT); body['messages'] = [{'role': 'user', 'content': text}]
                req_offset = host.log_offset(MODEL)
                detail = folder / f'{phase}-{i}'
                result = logical_request(owner, body, case['expected'], detail, LIMIT_SECONDS)
                stages, tokens = capture_engine_log(host.installation, MODEL, req_offset, detail, host)
                result.update(phase=phase, id=case['id'], stages=stages, tokens=tokens, **engine_rates(stages))
                row['requests'].append(result)
                print(json.dumps({'block': number, 'plan': letter, 'phase': phase, 'id': case['id'],
                                  'pass': result['pass'], 'work': round(result['work_seconds'], 1),
                                  'out_tps': result['engine_output_tokens_per_second'],
                                  'in_tps': result['engine_input_tokens_per_second']}), flush=True)
                if result.get('timeout') or result.get('deadline_reached'):
                    raise RuntimeError('Request reached its work deadline')
    finally:
        row['telemetry'] = host_telemetry.finish(host, telemetry, folder)
        stopped, stages, tokens = stop_and_capture_engine_log(owner, host.installation, MODEL, offset, folder, host)
        row.update(stop=stopped.get('status'), block_tokens=tokens, block_stages=len(stages))
        row['ended_at'] = time.time(); save(folder / 'result.json', row)
    return row



WORKERS = {'A': 23, 'B': 15}
CONDITION_FILE = BENCH / 'condition-pool-workers-15.json'


def deploy(letter):
    """Plain or condition deploy through tools.ops.deploy; wait while the lease is held, never preempt."""
    cmd = [sys.executable, '-m', 'tools.ops.deploy', '--host', 'rtx3080ti']
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


def groups(schedule):
    out = []
    for i, ch in enumerate(schedule, 1):
        if out and out[-1][0] == ch:
            out[-1][1].append(i)
        else:
            out.append((ch, [i]))
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    def terminate(signum, frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, terminate); signal.signal(signal.SIGHUP, terminate)
    data, texts = workload()
    compaction_config({}, OUT / 'prompt-binding')
    condition = load_condition(CONDITION_FILE)[0]
    progress = {'schedule': SCHEDULE, 'blocks': [], 'deploys': [], 'status': 'running', 'started_at': time.time()}
    try:
        for g, (letter, numbers) in enumerate(groups(SCHEDULE), 1):
            progress['deploys'].append(deploy(letter)); save(OUT / 'progress.json', progress)
            host = MeasurementHost('rtx3080ti', condition=condition if letter == 'B' else None)
            save(OUT / f'source-verification-{g:02d}.json', host.verify_sources())
            with host.controller(OUT / f'controller-{g:02d}') as owner:
                for number in numbers:
                    progress['active'] = number; save(OUT / 'progress.json', progress)
                    progress['blocks'].append(run_block(owner, host, number, letter, data, texts,
                                                        OUT / f'block-{number:02d}-{letter}', WORKERS[letter]))
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
