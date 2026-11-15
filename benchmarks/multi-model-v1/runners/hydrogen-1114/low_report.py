"""Four-tier table (Hydrogen low / medium / high / xhigh) of the four reviewer scenarios, for common/hydroeffort report.md.

    python3 -I low_report.py     -> Markdown on stdout
Low from .tmp/hydrolow (records.jsonl + score/<id>/score.json); medium / high / xhigh from results/phase4/benchmark-results.json (the exported main statistic)."""
import json
import statistics as st
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOW = HERE.parents[3] / '.tmp/hydrolow'
SC = [('spec-readiness-v4.3', 'SR'), ('code-spec-v5', 'CS'), ('code-standards-v5.1', 'CStd'), ('commit-audit-v3', 'CA')]
EFFORTS = ['low', 'medium', 'high', 'xhigh']


def rows():
    out = {}
    for l in open(LOW / 'records.jsonl'):
        r = json.loads(l)
        if not r['valid']:
            continue
        sc = json.loads((LOW / 'score' / r['id'] / 'score.json').read_text())
        h = r['handoffs']
        out.setdefault(('low', r['scenario']), []).append(dict(
            score=sc['final'], sec=sum(x['seconds'] or 0 for x in h), out=sum(x['tokens']['output'] or 0 for x in h),
            think=sum(x['thinking_tokens'] or 0 for x in h), tools=sum(x['tool_calls'] or 0 for x in h), limit=r.get('time_limit_seconds')))
    d = json.load(open(HERE / 'results/phase4/benchmark-results.json'))
    for i in d['instances']:
        if not (i['selection'] or {}).get('mainStatistic') or not i['validity']['valid']:
            continue
        out.setdefault((i['requestedEffort'], i['scenario']), []).append(dict(
            score=i['scoring']['score'], sec=i['time']['durationSeconds'], out=i['tokens']['output'], think=i['tokens']['thinking'],
            tools=i['toolCalls'], limit=i['time']['timeLimitSeconds']))
    return out


def ms(v, nd=3):
    return f'{st.mean(v):.{nd}f} ± {st.stdev(v):.{nd}f}' if len(v) > 1 else f'{v[0]:.{nd}f}'


def main():
    R = rows()
    print('均值 ± 标准差（n=每格有效实例数）。分数为 benchmark r8.4 分数；耗时为实例总耗时（分钟）；输出 token 含思考。\n')
    print('| 场景 | 档 | n | 分数 | 耗时（分钟） | 输出 token | 思考 token | 工具调用 | 时限（秒） |\n|---|---|---|---|---|---|---|---|---|')
    for scn, name in SC:
        for e in EFFORTS:
            v = R.get((e, scn), [])
            if not v:
                print(f'| {name} | {e} | 0 | | | | | | |'); continue
            lim = sorted({x['limit'] for x in v if x['limit']})
            print(f"| {name} | {e} | {len(v)} | {ms([x['score'] for x in v])} | {ms([x['sec'] / 60 for x in v], 1)} | {ms([x['out'] for x in v], 0)} | "
                  f"{ms([x['think'] or 0 for x in v], 0)} | {ms([x['tools'] or 0 for x in v], 1)} | {'/'.join(map(str, lim)) or '3600'} |")
    print('\n每格分数明细：\n')
    print('| 场景 | 档 | 各实例分数 |\n|---|---|---|')
    for scn, name in SC:
        for e in EFFORTS:
            print(f"| {name} | {e} | {', '.join(f'{x['score']:.3f}' for x in R.get((e, scn), []))} |")


main()
