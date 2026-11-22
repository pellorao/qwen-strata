"""Analyse routeprior2 rep/speed driver output. usage: python3 -I an2.py rep|speed OUTDIR"""
import json, re, sys, statistics as st
from pathlib import Path
mode, OUT = sys.argv[1], Path(sys.argv[2])
loads = sorted(p for p in OUT.glob('load*') if (p / 'done.json').exists())

def toks(t):
    return re.findall(r'[A-Za-z0-9_]+|[一-鿿]|[^\sA-Za-z0-9_]', t)

def rep(text, n=8):
    w = toks(text)
    g = [tuple(w[i:i + n]) for i in range(len(w) - n + 1)]
    r = 1 - len(set(g)) / len(g) if g else 0
    lines = [l.strip() for l in text.split('\n') if len(l.strip()) > 3]
    run = best = 1
    for a, b in zip(lines, lines[1:]):
        run = run + 1 if a == b else 1
        best = max(best, run)
    seen, blk = set(), 0
    s = re.sub(r'\s+', ' ', text)
    for i in range(0, max(0, len(s) - 120), 40):
        h = s[i:i + 120]
        if h in seen: blk += 1
        seen.add(h)
    return r, best, blk, len(w)

def mean(x):
    x = [v for v in x if v is not None]
    return (st.fmean(x), min(x), max(x)) if x else None

if mode == 'rep':
    rows = []
    for L in loads:
        meta = json.loads((L / 'done.json').read_text())
        for o in json.loads((L / 'rep.json').read_text()) if (L / 'rep.json').exists() else []:
            c, rs = o.get('content', ''), o.get('reasoning', '')
            r, run, blk, n = rep(c)
            rr = rep(rs)[0] if len(rs) > 400 else None
            gen = sum(x['gen'] for x in o['records'])
            tps = (sum(x['gen'] for x in o['records']) / sum(x['gen_ms'] for x in o['records']) * 1000) if o['records'] else None
            rows.append(dict(arm=meta['arm'], load=L.name, task=o['tag'], rep8=r, run=run, blk=blk, chars=len(c), gen=gen, finish=o.get('finish'),
                             reas_rep8=rr, tps=tps, err=o.get('error')))
    for r in rows: print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()}))
    print('== per arm')
    for arm in 'CR':
        it = [r for r in rows if r['arm'] == arm]
        if not it: continue
        print(arm, 'n', len(it), 'rep8 mean %.3f max %.3f' % (st.fmean(i['rep8'] for i in it), max(i['rep8'] for i in it)), 'maxrun', max(i['run'] for i in it),
              'runs>=4:', sum(1 for i in it if i['run'] >= 4), 'blk_sum', sum(i['blk'] for i in it), 'blk>0:', sum(1 for i in it if i['blk'] > 0),
              'finish=length', sum(1 for i in it if i['finish'] == 'length'), 'errors', sum(1 for i in it if i['err']),
              'reas_rep8', mean([i['reas_rep8'] for i in it]), 'gen_tokens', sum(i['gen'] for i in it), 'tps', mean([i['tps'] for i in it]))
else:
    tags = ['short-story-1', 'short-code-1', 'short-story-2', 'short-code-2', 'M', 'L1', 'L2', 'L3']
    data = {}
    for L in loads:
        meta = json.loads((L / 'done.json').read_text()); arm = meta['arm']
        for o in json.loads((L / 'decode.json').read_text()):
            recs = o['records']
            if not recs: continue
            gen = sum(r['gen'] for r in recs); ms = sum(r['gen_ms'] for r in recs)
            rd = sum(r['read'] for r in recs); rms = sum(r['read_ms'] for r in recs)
            acc = sum(r['acc'] for r in recs); dr = sum(r['drafts'] for r in recs)
            data.setdefault((o['tag'], arm), []).append((L.name, gen / ms * 1000, rd / rms * 1000 if rd > 2000 else None, acc / dr if dr else None, recs[0]['prompt'], meta.get('max_ram_pct')))
    for t in tags:
        for arm in 'CR':
            v = data.get((t, arm), [])
            if v: print(t, arm, 'n', len(v), 'dec %.1f (%.1f-%.1f)' % mean([x[1] for x in v]), 'read', mean([x[2] for x in v]) and '%.0f' % mean([x[2] for x in v])[0], 'acc', mean([x[3] for x in v]) and '%.2f' % mean([x[3] for x in v])[0], 'prompt', v[0][4], [round(x[1], 1) for x in v])
    L = {a: [x[1] for t in ('L1', 'L2', 'L3') for x in data.get((t, a), [])] for a in 'CR'}
    for a in 'CR':
        if L[a]: print('L pooled', a, len(L[a]), 'mean %.1f sd %.1f' % (st.fmean(L[a]), st.pstdev(L[a])), 'median %.1f' % st.median(L[a]))
    for L_ in loads:
        m = json.loads((L_ / 'done.json').read_text()); print(L_.name, 'load_s', m.get('load_s'), 'vram', m.get('vram_after_load_mib'), m.get('max_vram_mib'), 'ram%', m.get('max_ram_pct'), m.get('fatal'))
