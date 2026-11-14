"""P4 for Hydrogen (plan.md §3, §9 step 3): beta and G per effort on the CS / CStd material, the luna-supplement method
(runners/luna-xhigh-1022/p4probe.py): 1/P = 0; beta = material bytes / (input-token difference of the material turn and a
wrapper-only baseline turn); G = output tokens / wall of the response with the most output (per-response `duration_seconds`
from the agy stream; thinking tokens count as output, as in every other arm; a lower bound). T = round(B * k / (G * beta)).

    python3 -I p4probe.py cs|cstd <effort> [<effort> ...]       results: .tmp/hydrobench/p4/<scenario>-<effort>.json, <scenario>-T.json
The material is the scenario's frozen root as run_one stages it (CS: governing-spec.md + src = 152919 B, CStd: src = 142529 B).
"""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path('/home/pello/projects/qwen-strata')
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import agyrun  # noqa: E402
import run_one as r  # noqa: E402
from tools.reviewer import claude_scenario as cs  # noqa: E402
from tools.tuning.arw_dimension import load_plan, prepare  # noqa: E402

K = 2.0755
PARTS = {'cs': (['governing-spec.md', 'src'], 152919), 'cstd': (['src'], 142529)}
INSTRUCTION = ('Do not use any tools. Write a plain-text walkthrough of the material above, one module at a time, '
               'about 2500 words.')
BASELINE = INSTRUCTION.replace('of the material above', 'of nothing; reply "none"')
OUT = ROOT / '.tmp/hydrobench/p4'
TIMEOUT = 1500


def material(key):
    scenario = r.SCENARIOS[key][0]
    plan = load_plan(r.PLANS / f'{scenario}.json')[0]
    base = Path('/tmp/hydrobench/p4-src') / key
    shutil.rmtree(base, ignore_errors=True)
    prepare(plan, None, base / 'prep', time_limit_seconds=600)
    prepared = json.loads((base / 'prep/preparation.json').read_text())
    root = Path(prepared['handoffs'][0]['scenarioRoot'])
    parts, expected = PARTS[key]
    files = []
    for part in parts:
        p = root / part
        files += [p] if p.is_file() else sorted(f for f in p.rglob('*') if f.is_file())
    size = sum(f.stat().st_size for f in files)
    if size != expected:
        raise SystemExit(f'material {size} bytes, expected {expected}')
    return '\n\n'.join(f'=== {f.relative_to(root)} ===\n' + f.read_text() for f in files), size


def probe(key, effort):
    text, size = material(key)
    work = Path('/tmp/hydrobench/p4-work') / f'{key}-{effort}-{time.time_ns()}'
    work.mkdir(parents=True)
    subprocess.run(['git', 'init', '-q'], cwd=work, check=True)
    model = f'gemini-4-hydrogen-{effort}'
    rows = {}
    for name, body in (('baseline', BASELINE), ('material', text + '\n\n' + INSTRUCTION)):
        rows[name] = agyrun.turn(OUT / f'{key}-{effort}' / name, work, body + '\n', model, effort, TIMEOUT)
        rows[name].pop('response_text', None)
    first = {k: v['responses'][0]['usage'] for k, v in rows.items()}
    inp = lambda u: (u.get('input_tokens') or 0) + (u.get('cache_read_tokens') or 0)
    mt = inp(first['material']) - inp(first['baseline'])
    beta = size / mt
    big = max(rows['material']['responses'], key=lambda x: x['usage']['output_tokens'])
    G = big['usage']['output_tokens'] / big['seconds']
    T = round(size * K / (G * beta))
    result = {'scenario': key, 'effort': effort, 'material_bytes': size, 'material_tokens': mt, 'beta': beta, 'G': G,
              'G_response': {'output_tokens': big['usage']['output_tokens'], 'thinking_tokens': big['usage']['thinking_tokens'],
                             'seconds': big['seconds']}, 'T_seconds': T,
              'tools': {k: v['tools'] for k, v in rows.items()}, 'status': {k: v['status'] for k, v in rows.items()},
              'models': {k: v['model_echo'] for k, v in rows.items()}, 'wall': {k: v['wall_seconds'] for k, v in rows.items()},
              'baseline_usage': first['baseline'], 'thinking_tokens_material_turn': rows['material']['usage_sum']['thinking_tokens']}
    (OUT / f'{key}-{effort}.json').write_text(json.dumps(result, indent=1) + '\n')
    shutil.rmtree(work, ignore_errors=True)
    shutil.rmtree(Path('/tmp/hydrobench/p4-src') / key, ignore_errors=True)
    print(json.dumps(result), flush=True)
    return result


if __name__ == '__main__':
    key = sys.argv[1]
    OUT.mkdir(parents=True, exist_ok=True)
    limits = OUT / f'{key}-T.json'
    T = json.loads(limits.read_text()) if limits.exists() else {}
    for effort in sys.argv[2:]:
        rem = agyrun.remaining()
        if min(rem.values()) < 30:
            raise SystemExit(f'quota {rem} below 30% - stop')
        T[effort] = probe(key, effort)['T_seconds']
        limits.write_text(json.dumps(T) + '\n')
