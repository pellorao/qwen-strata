"""Summarise run/: per-block table, per-condition pooled rates, adjacent-pair ratios (B/A), output identity.
(Copied from the pool-workers analysis, with an output-identity section added.)"""
import json, statistics as st, sys
from pathlib import Path

RUN = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[3] / '.tmp/sm86-perf-1024/run')
blocks = [json.loads(p.read_text()) for p in sorted(RUN.glob('block-*/result.json'))]


def agg(reqs):
    u = sum(r['tokens']['uncached_input'] for r in reqs); c = sum(r['tokens']['cached_input'] for r in reqs)
    o = sum(r['tokens']['output'] for r in reqs)
    ps = sum(r['engine_input_seconds'] for r in reqs); ds = sum(r['engine_decode_seconds'] for r in reqs)
    w = sum(r['work_seconds'] for r in reqs)
    return dict(read=u, reused=c, gen=o, in_tps=u / ps, out_tps=o / ds, task_in=u / w, task_out=o / w, work=w,
                passed=sum(r['pass'] for r in reqs), n=len(reqs))


rows = []
for b in blocks:
    m = [r for r in b['requests'] if r['phase'] == 'measured']
    a = agg(m); t = b.get('telemetry') or {}
    rows.append(dict(block=b['block'], plan=b['plan'], load=b['load_seconds'], **a,
                     req1_in=m[0]['engine_input_tokens_per_second'],
                     min_req_out=min(r['engine_output_tokens_per_second'] for r in m),
                     gpu_max_c=t.get('max_gpu_temperature_c'), min_sm=t.get('min_sm_clock_mhz'),
                     throttle=t.get('throttle_reasons_seen'), stop=b.get('stop'), reqs=m))
print('| 块 | 计划 | 加载秒 | 正确 | 工作秒 | read | reused | generated | 引擎输入 | 引擎输出 | 任务输入 | 任务输出 | 首请求输入 | 最低单请求输出 | GPU 最高°C |')
print('|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|')
for r in rows:
    print(f"| {r['block']} | {r['plan']} | {r['load']:.1f} | {r['passed']}/{r['n']} | {r['work']:.1f} | {r['read']} | {r['reused']} | {r['gen']} | "
          f"{r['in_tps']:.1f} | {r['out_tps']:.1f} | {r['task_in']:.1f} | {r['task_out']:.1f} | {r['req1_in']:.1f} | {r['min_req_out']:.1f} | {r['gpu_max_c']} |")
print()
for p in 'AB':
    rs = [r for r in rows if r['plan'] == p]
    if not rs: continue
    a = agg([q for r in rs for q in r['reqs']])
    sd = lambda k: st.stdev([r[k] for r in rs]) if len(rs) > 1 else float('nan')
    print(p, {k: round(v, 2) if isinstance(v, float) else v for k, v in a.items()},
          'block SD out', round(sd('out_tps'), 2), 'in', round(sd('in_tps'), 2), 'work', round(sd('work'), 2),
          'throttle', sorted({x for r in rs for x in (r['throttle'] or [])}))
# adjacent pairs in schedule order
pairs = [(rows[i], rows[i + 1]) for i in range(0, len(rows) - 1, 2) if rows[i]['plan'] != rows[i + 1]['plan']]
out_r, in_r, blk_out, blk_in, blk_work = [], [], [], [], []
for x, y in pairs:
    a, b = (x, y) if x['plan'] == 'A' else (y, x)
    for qa, qb in zip(a['reqs'], b['reqs']):
        out_r.append(qb['engine_output_tokens_per_second'] / qa['engine_output_tokens_per_second'])
        in_r.append(qb['engine_input_tokens_per_second'] / qa['engine_input_tokens_per_second'])
    blk_out.append(b['out_tps'] / a['out_tps']); blk_in.append(b['in_tps'] / a['in_tps']); blk_work.append(b['work'] / a['work'])
print('pairs', len(pairs))
for name, v in [('req out B/A', out_r), ('req in B/A', in_r), ('block out B/A', blk_out), ('block in B/A', blk_in), ('block work B/A', blk_work)]:
    if v:
        print(name, 'median', round(st.median(v), 4), 'mean', round(st.mean(v), 4),
              'sd', round(st.stdev(v), 4) if len(v) > 1 else None, '>1:', sum(x > 1 for x in v), '/', len(v),
              [round(x, 3) for x in v])

# output identity: SHA of every call's reasoning + content per measured request, compared within and across conditions
import hashlib
def output_text(block, i):
    folder = RUN / f"block-{block['block']:02d}-{block['plan']}" / f'measured-{i}'
    parts = []
    for p in sorted(folder.glob('response-*.json'), key=lambda p: p.name):
        if p.name.endswith('-timing.json'):
            continue
        m = json.loads(p.read_text())['choices'][0]['message']
        parts.append((m.get('reasoning_content') or '') + '\x00' + (m.get('content') or ''))
    return '\x01'.join(parts)
def output_sha(block, i):
    return hashlib.sha256(output_text(block, i).encode()).hexdigest()[:12]
ids = sorted({j for b in blocks for j in range(1, 1 + sum(r['phase'] == 'measured' for r in b['requests']))})
shas = {(b['block'], b['plan']): [output_sha(b, j) for j in ids] for b in blocks}
print()
print('| 块 | 条件 | ' + ' | '.join(f'请求{j} 输出 SHA' for j in ids) + ' |')
print('|---|---|' + '---|' * len(ids))
for (n, p), v in shas.items():
    print(f'| {n} | {p} | ' + ' | '.join(v) + ' |')
for j in range(len(ids)):
    a = {v[j] for (n, p), v in shas.items() if p == 'A'}; b = {v[j] for (n, p), v in shas.items() if p == 'B'}
    print(f'request {j + 1}: distinct A {len(a)}, distinct B {len(b)}, shared {len(a & b)}')
# greedy outputs already differ between loads of one condition, so compare how far outputs agree:
# common prefix (characters) of each block pair, within A, within B and across A-B
import itertools, os
texts = {(b['block'], b['plan']): [output_text(b, j) for j in ids] for b in blocks}
for j in range(len(ids)):
    kinds = {'AA': [], 'BB': [], 'AB': []}
    for (x, tx), (y, ty) in itertools.combinations(texts.items(), 2):
        kinds[''.join(sorted(x[1] + y[1]))].append(len(os.path.commonprefix([tx[j], ty[j]])))
    print(f'request {j + 1} common prefix chars: ' + ', '.join(
        f"{k} median {st.median(v):.0f} min {min(v)} max {max(v)} (n={len(v)})" for k, v in kinds.items() if v))
