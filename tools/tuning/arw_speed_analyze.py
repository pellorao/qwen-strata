"""Per-block engine speed from engine-log-since-deploy.txt; usage: python3 -m tools.tuning.arw_speed_analyze OUTDIR (contains blocks/rN-cond)."""
import sys, json, re, statistics as st
from pathlib import Path
from tools.metrics.strata_tokens import parse_engine_log
out = Path(sys.argv[1]); rows = []
for b in sorted((out / 'blocks').glob('r*-*')):
    log = (b / 'engine-log-since-deploy.txt').read_text(errors='replace')
    rec = parse_engine_log(log)
    half = rec[len(rec) // 2:]
    def rates(rs):
        pre = [r['uncached'] / (r['prompt_ms'] / 1000) for r in rs if r['uncached'] >= 2000 and r['prompt_ms'] > 0]
        dec = [r['output'] / (r['decode_ms'] / 1000) for r in rs if r['output'] >= 50 and r['decode_ms'] > 0]
        return (round(st.median(pre), 1) if pre else None, len(pre), round(st.median(dec), 1) if dec else None, len(dec),
                round(sum(r['output'] for r in rs) / (sum(r['decode_ms'] for r in rs) / 1000), 1) if rs else None)
    warn = sorted({re.sub(r'\d+', 'N', l.strip())[:110] for l in log.splitlines() if re.search(r'not enough RAM|read from file|WARNING|warn', l, re.I)})
    big=[x for x in rec if x['uncached']>=2000]
    agg=round(sum(x['uncached'] for x in big)/(sum(x['prompt_ms'] for x in big)/1000)) if big else None
    rows.append((b.name, len(rec), rates(rec), rates(half), warn, agg))
for n, c, a, h, w, agg in rows:
    print(f'{n}: requests={c} all[prefill med/n, decode med/n, decode agg]={a} second-half={h} PREFILL_AGG={agg}')
    for x in w[:6]: print('    ', x)
