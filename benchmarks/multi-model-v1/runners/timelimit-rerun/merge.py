import json, sys, copy
sys.path.insert(0, '/home/pello/projects/qwen-strata')
from tools.reviewer import benchmark_export as be
OLD = 'reports/v0.1.45/multi-model-benchmark/benchmark-results.json'
d = json.load(open(OLD))
new = be.instances(json.load(open('.tmp/oldrerun/sum/summary.json')), {})
by = {i['id']: i for i in d['instances']}
def void(i, why):
    i['validity'].update(valid=False, status='timeout', notes=[why])
    i['selection'].update(validRank=None, firstN=None, mainStatistic=None, inMain=False)
    i['scoring'].update({k: None for k in ('status','score','scoreR83','rawScore','scoreBeforePenalty','formatPenalty','repairs','overallDeduction','diagnosticEnvironmentQueries')})
    i['scoring']['modelFailureSubScenarios'] = []
for k in ('anthropic/code-spec-v5/haiku-low-a7', 'anthropic/code-spec-v5/haiku-low-a8', 'deepseek-claude/code-spec-v5/cc-max-a4'):
    i = by[k]; void(i, f"hard stop at T={i['time']['timeLimitSeconds']} s")
# DeepSeek: a5 becomes rank 4; a6 (valid, never scored, run directory gone) stays outside the main statistic
a5 = by['deepseek-claude/code-spec-v5/cc-max-a5']; a5['selection']['validRank'] = 4
a6 = by['deepseek-claude/code-spec-v5/cc-max-a6']; a6['selection'].update(validRank=5, firstN=False, mainStatistic=False, inMain=False)
rank = {'anthropic/code-spec-v5/haiku-low-a10': 4, 'anthropic/code-spec-v5/haiku-low-a9': 5}
for n in new:
    n['selection'].update(validRank=rank[n['id']], firstN=True, mainStatistic=True, cellPooled=False, inMain=True, stage='preregistered')
    n.pop('compactions', None)
    d['instances'].append(n)
for s in d['scenarios']:
    s['timeLimit'].update(be.TIME_LIMITS[s['timeLimit']['rule']])
d['caveats'].append({'id': 'time-limit-rerun',
 'zh': 'Code Spec / Code Standards 的时限 T 限制在 15–60 分钟（用户 2026-11-15）；到 T 被硬中断的实例作废、不计分，并以 60 分钟时限重跑。本文件里 3 个这样的实例（haiku low a7、a8；deepseek-flash max a4）标为 timeout。haiku low 补跑 a9、a10（Claude Code 2.1.310，其余实例为 2.1.303，时限 3600 s，均在约 6 分钟内正常交付）并取代 a7、a8 进入主统计，它们的盲裁是事后补做的单池（Opus high，同一冻结 brief 和锚点），并非与前 3 个实例同一批裁决。deepseek-flash max 的补跑因 DeepSeek 密钥返回 401 无法进行，该格主统计只有 4 个实例（a1、a2、a3、a5）；a6 有效但当时未计分、运行目录已不在，无法补评，留在主统计之外。',
 'en': 'The Code Spec / Code Standards limit T is clamped to 15-60 minutes (user 2026-11-15); an instance hard-stopped at T is voided, never scored, and rerun with a 60-minute limit. Three such instances in this file (haiku low a7, a8; deepseek-flash max a4) are marked timeout. Haiku low reruns a9 and a10 (Claude Code 2.1.310, the other instances ran 2.1.303; limit 3600 s; both delivered normally in about 6 minutes) replace a7 and a8 in the main statistic; their blind adjudication was done afterwards as a single pool (Opus high, same frozen brief and anchors), not in the same batch as the first three instances. The deepseek-flash max rerun could not run (the DeepSeek key returned 401), so that cell has 4 instances in the main statistic (a1, a2, a3, a5); a6 is valid but was never scored and its run directory is gone, so it stays outside the main statistic.'})
json.dump(d, open('.tmp/oldrerun/benchmark-results.new.json', 'w'), ensure_ascii=False, indent=1)
print(len(d['instances']))
