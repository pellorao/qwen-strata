"""Public result file of the multi-model benchmark v1 for the Reviewer Model Benchmark page (v2.0).

Input: a benchmark_summary summary.json (phase 1, 2 or 3; it must carry the benchmark_summary `generator` marker or be
a published summary listed in LEGACY_SUMMARIES, and every instance must have its work seconds, speeds and speed_parts),
optional sensitivity-variant summaries of the same instances
(each a benchmark_summary run over another score root), and the session-check diagnostic list. Output: one JSON file with
per-instance detail only (user 2026-10-22): no aggregate statistics and no comparison results, but every field and
design rule needed to recompute them (which instances enter a cell, the preregistered pairs per scenario (25 in v1, 47 in v2), alpha, Holm
family, the test). The format is documented in benchmarks/multi-model-v1/export-format.md.

The file is published, so it carries no network detail beyond host names, no local paths, user names, session or
request ids, credentials, report text, answer keys or hidden cases. Fields are copied by whitelist, never wholesale, and
`safety_hits` scans the whole result before it is written; any hit stops the export.

    python3 -m tools.reviewer.benchmark_export --summary reports/.../summary.json --out <file>
        [--variant A1=<summary.json> ...] [--diagnostic benchmarks/multi-model-v1/session-diagnostic.json]
"""
import argparse
import getpass
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from tools.reviewer import benchmark_summary as bs

ROOT = Path(__file__).resolve().parents[2]

# ---- tunables ------------------------------------------------------------------------------------------------------
BENCHMARK_NAME = 'Reviewer Model Benchmark'
BENCHMARK_VERSION = '2.0'
SCHEMA_VERSION = 1
SCORING_VERSION = 'r8.4'
CODEX_VERSION = '0.163.0'
CLAUDE_CODE_VERSION = '2.1.303'
STRATA_VERSION = 'v0.1.45'
STRATA_HOST = 'rtx3080ti'
STRATA_QUANT = 'IQ3_XXS'
STRATA_MODEL_ID = 'qwen3.8-flash-next-iq3_xxs'
DIAGNOSTIC = ROOT / 'benchmarks/multi-model-v1/session-diagnostic.json'
# Report conversions that are not costs (benchmark_summary): the measurement-rule equivalent cost of Strata and the
# Anthropic weekly-quota share per API-equivalent USD.
STRATA_EQUIVALENT_USD_PER_M = {'uncachedInput': 0.15, 'cachedInput': 0.016, 'output': 0.47}
# Published reports pointed to from later files (paths relative to the project root).
PHASE1_SUMMARY_MD = 'reports/v0.1.45/multi-model-benchmark/phase1/summary.md'
PHASE1_SUMMARY_JSON = 'reports/v0.1.45/multi-model-benchmark/phase1/summary.json'
PHASE2_SUMMARY_MD = 'reports/v0.1.45/multi-model-benchmark/phase2/summary.md'
PHASE2_SUMMARY_JSON = 'reports/v0.1.45/multi-model-benchmark/phase2/summary.json'
# Published summaries written before the generator marker (user 2026-10-23), accepted by sha256 only: the phase-2
# summary.json (benchmark_summary output with speeds_approximate filled in place; regenerating it gives the same
# content with that key in another position, so the committed file is kept). The phase-1 summary.json has no
# per-instance speed_parts and is not exportable.
LEGACY_SUMMARIES = {'df67a68e7a7f06f3258bebfc2d44a47a1fc7ac1a711964ee4f74f8efda4fff51': 2}
# Periods (UTC) when other compute (nice 19) ran on the Strata host beside the phase-2 extra runs: id, start, end, zh, en.
PARALLEL_WINDOWS = [
    ('W1', '2026-10-21T16:50:00+00:00', '2026-10-21T17:30:00+00:00', '第一阶段补数据 worker 计算（nice 19，1–2 进程）',
     'phase-1 data-completion worker (nice 19, 1-2 processes)'),
    ('W2', '2026-10-21T17:20:00+00:00', '2026-10-21T17:59:59+00:00',
     '第一阶段全量重算（nice 19，并发 ≤2；运行记录为 02:2x–02:5x JST，按整段取）',
     'phase-1 full rescoring (nice 19, at most 2 at once; logged as 02:2x-02:5x JST, taken whole)'),
    ('W3', '2026-10-21T22:41:00+00:00', '2026-10-21T22:42:59+00:00', '第二阶段 CStd 枚举与计分（nice 19，并发 ≤2）',
     'phase-2 CStd enumeration and scoring (nice 19, at most 2 at once)'),
    ('W4', '2026-10-21T23:37:00+00:00', '2026-10-21T23:38:59+00:00', '第二阶段 CStd 枚举与计分（nice 19，并发 ≤2）',
     'phase-2 CStd enumeration and scoring (nice 19, at most 2 at once)'),
    ('W5', '2026-10-22T00:31:43+00:00', '2026-10-22T00:35:02+00:00', 'SR 计分准备：建 record、枚举、manifest、扫描（nice 19）',
     'SR scoring preparation: records, enumeration, manifest, scan (nice 19)')]

SCENARIOS = {
    # id: reviewer, version, revision, sub-scenarios, P (positive cases), sum k of negatives, time-limit rule, texts
    'code-spec-v5': {
        'reviewerId': 'code-spec-reviewer', 'name': 'Code Spec', 'version': 'v5', 'revision': 38,
        'subScenarios': ['default'], 'positives': 20, 'negativeKSum': 7.25, 'timeLimit': 'reading-volume',
        'zh': '检查改动是否落实已给出的要求。', 'en': 'Checks whether a change implements the stated requirements.'},
    'code-standards-v5.1': {
        'reviewerId': 'code-standards-reviewer', 'name': 'Code Standards', 'version': 'v5.1', 'revision': 25,
        'subScenarios': ['default'], 'positives': 26, 'negativeKSum': 16.25, 'timeLimit': 'reading-volume',
        'zh': '对照仓库指令与实现质量标准审查代码。',
        'en': 'Reviews code against repository instructions and implementation quality standards.'},
    'commit-audit-v3': {
        'reviewerId': 'commit-audit-reviewer', 'name': 'Commit Audit', 'version': 'v3', 'revision': 24,
        'subScenarios': ['default'], 'positives': 29, 'negativeKSum': 12.5, 'timeLimit': 'arw',
        'zh': '审计暂存的提交候选及必要检查。', 'en': 'Audits a staged commit candidate and its required checks.'},
    'spec-readiness-v4.3': {
        'reviewerId': 'spec-readiness-reviewer', 'name': 'Spec Readiness', 'version': 'v4.3', 'revision': 46,
        'subScenarios': ['runtime-migration', 'artifact-promotion'], 'positives': 23, 'negativeKSum': 14.75,
        'timeLimit': 'arw',
        'zh': '实施前检查要求的完整性与可实现性；每个实例含两个独立根线程（runtime-migration、artifact-promotion），合并计一个分数。',
        'en': 'Checks requirements for completeness and feasibility before implementation; each instance has two '
              'independent root threads (runtime-migration, artifact-promotion) scored together as one.'},
}
TIME_LIMITS = {
    'reading-volume': {
        'zh': '阅读量时限 T = B ×（1/P + k/G）/ β，P、G、β 取每个配置自己短探针测出的速度；到 T 硬中断，按已写出的报告计分。实例的 T 见 timeLimitSeconds。',
        'en': 'Reading-volume limit T = B x (1/P + k/G) / beta with P, G, beta measured per configuration by a short '
              'probe; hard stop at T, scored from the report written. Per-instance T in timeLimitSeconds.'},
    'arw': {
        'zh': 'ARW 原版：累计工作 55 分钟提醒、60 分钟中断（每个根线程）。',
        'en': 'ARW original: reminder at 55 minutes and interrupt at 60 minutes of accumulated work (per root thread).'},
}
# Sensitivity variants: id -> (base, zh, en). The base is what the variant is compared with in the phase-1 report.
VARIANTS = {
    'A1': ('formal', '歧义清单 A1 的另一读法：Code Spec 一处要求的另一读法，相关 finding 判 supported（只动 Code Spec）。',
           'Ambiguity list A1, alternative reading of one Code Spec requirement: the affected findings judged '
           'supported (Code Spec only).'),
    'A2E_min': ('formal', '歧义清单 A2 的另一读法（min）：Commit Audit 一处要求措辞的另一读法，只改主读法下必须改的 finding。',
                'Ambiguity list A2, alternative reading of one Commit Audit requirement (min: only the findings the '
                'reading forces).'),
    'A2E_full': ('formal', '歧义清单 A2 的另一读法（full）：同上，所有可按该读法改判的 finding 都改。',
                 'Ambiguity list A2 (full): every finding the reading can change.'),
    'A6': ('formal', '歧义清单 A6 的另一读法：Commit Audit 规则 24 的"redacted value"指整个事件，相关 2 条 finding 判 supported（只动 CA，第二阶段加测实例）。',
           'Ambiguity list A6, alternative reading of Commit Audit rule 24 ("redacted value" as the whole event): '
           'the 2 affected findings judged supported (Commit Audit only, phase-2 extra instances).'),
    'preGap': (None, '补裁缺口前的计分（9 个实例当时待裁、未计分完）；历史状态。',
               'Scoring before the gap adjudication (9 instances pending, unscored); historical state.'),
    'gapsLower': ('preGap', '缺口下界：待裁候选全部按 not-matched / unsupported 暂定。',
                  'Gap lower bound: pending candidates provisionally not-matched / unsupported.'),
    'gapsUpper': ('preGap', '缺口上界：待裁候选全部按 matched / supported 暂定。',
                  'Gap upper bound: pending candidates provisionally matched / supported.'),
    'preLineShift': ('preGap', '缺口补裁后、Commit Audit 第 2 关行号整体错位修复（N1）前的计分。',
                     'Scoring after the gap adjudication, before the Commit Audit gate-2 line-shift repair (N1).'),
}
VARIANT_FIELDS = (('score', 'score'), ('scoreStatus', 'score_status'), ('rawScore', 'raw_score'),
                  ('formatPenalty', 'format_penalty'), ('repairs', 'repairs'), ('scoreR83', 'score_r83'))

HARNESS_NAMES = {'codex': 'Codex', 'claude-code': 'Claude Code'}
VENDOR_NAMES = {'openai': 'OpenAI', 'deepseek': 'DeepSeek', 'strata': 'Strata (local)', 'anthropic': 'Anthropic'}
MODEL_NAMES = {'gpt-6.1-sol': 'gpt-6.1-sol', 'gpt-6-luna': 'gpt-6-luna', 'deepseek-flash': 'DeepSeek V4.1 Flash',
               'strata-iq3_xxs': 'Qwen3.8-Flash-Next IQ3_XXS (Strata)', 'opus': 'Claude Opus', 'sonnet': 'Claude Sonnet',
               'haiku': 'Claude Haiku'}
TOKEN_SOURCE = {
    'openai': {'zh': 'API usage，由本机回环 relay 从流式回复记录（只记 usage、模型、tier，不记头和正文）；未缓存输入 = input − cached。',
               'en': 'API usage recorded from the streamed replies by a local loopback relay (usage, model and tier '
                     'only, no headers or bodies); uncached input = input - cached.'},
    'deepseek-codex': {'zh': '同 OpenAI 的 relay 口径（DeepSeek 官方 OpenAI 格式端点）。',
                       'en': 'Same relay basis as OpenAI (DeepSeek official OpenAI-format endpoint).'},
    'anthropic': {'zh': 'Claude Code stream result usage：未缓存输入 = input_tokens + cache_creation_input_tokens（缓存写入单列于 cacheWriteInput）；缓存 = cache_read_input_tokens；输出含思考。',
                  'en': 'Claude Code stream result usage: uncached input = input_tokens + '
                        'cache_creation_input_tokens (cache writes also given in cacheWriteInput); cached = '
                        'cache_read_input_tokens; output includes thinking.'},
    'deepseek-claude': {'zh': '同 Anthropic 的 Claude Code result usage 口径（DeepSeek 官方 Anthropic 格式端点）。',
                        'en': 'Same Claude Code result usage basis as Anthropic (DeepSeek official '
                              'Anthropic-format endpoint).'},
    'strata-codex': {'zh': 'Strata 引擎内部日志：read（未缓存输入）、reused（已缓存输入）、generated（输出），含 guardian 请求。',
                     'en': 'Strata engine log: read (uncached input), reused (cached input), generated (output), '
                           'guardian requests included.'},
    'strata-claude': {'zh': 'Strata 引擎内部日志（同上；Claude Code 路径没有 guardian）。',
                      'en': 'Strata engine log (as above; no guardian on the Claude Code path).'},
}
ARMS = {('codex', 'openai'): 'openai', ('codex', 'deepseek'): 'deepseek-codex', ('codex', 'strata'): 'strata-codex',
        ('claude-code', 'anthropic'): 'anthropic', ('claude-code', 'deepseek'): 'deepseek-claude',
        ('claude-code', 'strata'): 'strata-claude'}
DURATION_BASIS = {
    'codex': {'zh': 'ARW Reviewer 的累计工作秒数（各根线程相加），从首个请求进入模型起算，不含部署、加载与准备。',
              'en': 'ARW Reviewer accumulated work seconds (root threads summed), from the first model request, '
                    'excluding deployment, loading and preparation.'},
    'claude-code': {'zh': '各根线程 claude -p 会话（含接续段）的墙钟秒数相加，不含准备。',
                    'en': 'Wall seconds of the claude -p sessions of each root thread (continuations included), '
                          'summed; preparation excluded.'},
}

COST_BASIS = {
    'anthropic': {'zh': 'Claude Code 报告的 total_cost_usd：按 Anthropic 价目的 API 等价美元；本 benchmark 用订阅运行，不是实际账单。',
                  'en': "Claude Code's reported total_cost_usd: API-equivalent USD at Anthropic list prices; the "
                        'benchmark ran on a subscription, so this is not an actual bill.'},
    'deepseek': {'zh': '按 DeepSeek 官方价目逐请求重算（高峰 / 低谷按请求时刻）；美元按官方美元价目表；lowerBound 表示有被提醒中断丢弃的请求未计入。',
                 'en': 'Recomputed from the DeepSeek official price list per request (peak / off-peak by request '
                       'time); USD from the official USD table; lowerBound means requests abandoned by a reminder '
                       'interrupt are missing.'},
}


PHASE3_CAVEAT = (
    'phase3-supplement',
    '第三阶段只是补充（用户 2026-10-22）：gpt-6-luna xhigh（配置 28）、max（配置 29）在 Codex 上 4 个场景各格取全部有效实例'
    '（不截取前 5 个：并行调度多出的有效实例不是因分数加跑，与预登记实例效力相同，用户 2026-10-23），只给逐实例结果，不进预登记比较和 Holm 族，本工程也不拿它与其他配置比较。运行于 2026-10-23（JST 02:20–07:12），'
    '借用 ChatGPT 登录，条件与 v1 相同（同一 Codex 副本、场景冻结源、harness 补丁、搜索关闭、凭据 deny-read）；'
    '与前两阶段相隔一天，服务端模型或路由可能已有变化。',
    'Phase 3 is a supplement only (user 2026-10-22): gpt-6-luna xhigh (configuration 28) and max (29) on Codex, every '
    'valid instance of each cell in the 4 scenarios (no first-5 cut: the valid instances that parallel scheduling added '
    'were not run because of scores and count the same as preregistered ones, user 2026-10-23), per-instance results '
    'only, never in a preregistered comparison or the '
    'Holm family, and not compared with other configurations by this project. Run on 2026-10-23 (JST 02:20-07:12) on a '
    'borrowed ChatGPT login under the v1 conditions (same Codex copy, frozen scenario sources, harness patches, search '
    'off, credential deny-read); a day after the first two phases, so the served model or routing may have changed.')


def caveats(phase=2):
    """Limitations, zh / en. D7 is stated as this project's own rule, not a restriction on the reader (user 10-22)."""
    items = [
        ('d7', '本工程的报告只给分场景结果，不算综合分、不排名（D7）。本文件只提供实例数据，不含任何权重或综合分。',
         "This project's own reports give per-scenario results only, with no combined score and no ranking (D7). "
         'This file provides instance data only and carries no weights or combined scores.'),
        ('negative-scores', '分数可为负（评分 r8.4 不在 0 处截断）：N ≥ 0 时分数 = N ÷ P，N < 0 时分数 = N ÷ Σk，正负两侧单位不同；不设下限，可低于 −1。模型失误（没有报告）记 0。',
         'Scores can be negative (scoring r8.4 does not cut at 0): N / P for N >= 0, N / sum k for N < 0, so the '
         'two sides have different units; no lower bound (can fall below -1). A model failure (no report) scores 0.'),
        ('strata-local', 'Strata 是本地模型（单机 RTX 3080 Ti 12 GB、IQ3_XXS），没有 API 费用；任何按 token 算的费用都只是比较代理。',
         'Strata is a local model (one RTX 3080 Ti 12 GB, IQ3_XXS) with no API cost; any token-priced cost is only '
         'a comparison proxy.'),
        ('harness-reported-cost', 'Claude Code 对非 Anthropic 后端（DeepSeek、Strata）报的 total_cost_usd 按 Anthropic 价目算，不是实际费用；本文件只把它放在 harnessReportedCostUsd，不能当费用用。',
         "Claude Code's total_cost_usd for non-Anthropic backends (DeepSeek, Strata) is priced at Anthropic rates and "
         'is not an actual cost; it appears only as harnessReportedCostUsd and must not be used as a cost.'),
        ('chatgpt-plan', 'OpenAI 模型经 ChatGPT 套餐登录运行，只报 token、不报金额；套餐的限速或路由可能与 API 不同。',
         'OpenAI models ran on a ChatGPT plan login: tokens only, no amounts; plan rate limits or routing may '
         'differ from the API.'),
        ('opus-calibration', '场景按 Opus 标定，答案键经 Opus 审计，Opus 同时是唯一的盲裁者，所以 Opus 的位置可能偏高。',
         'Scenarios were calibrated on Opus, answer keys audited by Opus, and Opus is the only blind adjudicator, so '
         "Opus's position may be inflated."),
        ('vendor-harness', '厂商与 harness 部分绑定：OpenAI 只在 Codex 上，Anthropic 只在 Claude Code 上；只有 Strata 和 DeepSeek 两边都跑。',
         'Vendor and harness are partly bound: OpenAI only on Codex, Anthropic only on Claude Code; only Strata and '
         'DeepSeek run on both.'),
        ('effort', '"强度"含义因厂商而异；DeepSeek 测 low / high / max，Strata 没有 max。DeepSeek medium 请求按端点映射为 high：部分并入 high，部分作补充配置（时限 T 与 high 不同）。',
         'Effort means different things per vendor; DeepSeek runs low / high / max, Strata has no max. DeepSeek '
         'medium requests map to high at the endpoint: some are pooled into high, others are a supplementary '
         'configuration (their time limit T differs from high).'),
        ('conditions', '基础提示（启动提示、压缩提示）只给 Strata；所有模型都关闭搜索；guardian、窗口与压缩、时限提醒送达方式各臂不同。',
         'Base prompts (startup, compaction) go to Strata only; search is off for every model; guardian, context '
         'window and compaction, and time-limit reminder delivery differ between arms.'),
        ('time-limits', 'Code Spec 与 Code Standards 的时限按各配置自己的速度算，API 模型的速度含网络和首 token 延迟。',
         "Code Spec and Code Standards limits follow each configuration's own speed; API model speeds include "
         'network and first-token latency.'),
        ('speeds', 'API 模型分不出输入处理时间：引擎输入速度未知，引擎输出速度按 API 请求时间算，是下限。多个实例的速度按总 token ÷ 总耗时汇总，不取各实例速度的算术平均（用户 2026-10-22）；Codex 上 API 模型的引擎输出按 relay 日志的 output token ÷ 请求秒数计算，请求秒数没有保存、原始日志已删除，所以汇总是近似值（用户 2026-10-22）：Σ`tokens.output` ÷ Σ(`tokens.output` ÷ `speeds.engineOutput`)，即用各实例的速度反推请求秒数，仍是下限。Codex 的 code mode 一次 exec 记 1 次工具调用，gpt-6.1-sol / gpt-6-luna 的工具调用数与其他臂不完全同义。',
         'API models give no input-processing time: engine input speed is unknown and engine output speed, timed by '
         'API request, is a lower bound. Speeds over several instances pool as total tokens / total seconds, never the '
         'arithmetic mean of instance speeds (user 2026-10-22); the engine output of API models on Codex is relay '
         'output tokens / request seconds; the request seconds were not kept (the raw logs are deleted), so its pooled '
         'value is approximate (user 2026-10-22): sum(tokens.output) / sum(tokens.output / speeds.engineOutput), the '
         'request seconds recovered from each instance speed, still a lower bound. A Codex code-mode exec counts as one tool '
         'call, so gpt-6.1-sol / gpt-6-luna tool-call counts are not fully comparable with other arms.'),
        ('unknown-not-zero', 'null 表示未知或不适用，不是 0。',
         'null means unknown or not applicable, never zero.'),
        ('resolution', '每格预登记 5 个实例；5 对 5 时能分辨的分差约 0.3。',
         'Five preregistered instances per cell; with 5 against 5 the resolvable difference is about 0.3.'),
        ('single-host', 'Strata 结果只适用于单机单量化（rtx3080ti、IQ3_XXS，参数来自 v0.1.42 调参）。',
         'Strata results hold for one host and one quantization only (rtx3080ti, IQ3_XXS, parameters from the '
         'v0.1.42 tuning).'),
    ]
    if phase >= 3:
        items.append(PHASE3_CAVEAT)
    return [{'id': i, 'zh': zh, 'en': en} for i, zh, en in items]


# ---- helpers -------------------------------------------------------------------------------------------------------

def iso(ts):
    return None if ts is None else datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec='microseconds')


def config_key(config, supplementary=None):
    c = bs.CONFIGS[config]
    effort = 'medium' if supplementary else c['effort']
    return f"{c['harness']}/{c['model']}/{effort}"


def tokens(t):
    t = t if isinstance(t, dict) else {}
    return {'uncachedInput': t.get('uncached_input'), 'cachedInput': t.get('cached_input'), 'output': t.get('output')}


def summed_cache_write(handoffs):
    writes = [h.get('cache_write') for h in handoffs]
    if not handoffs or any(w is None for w in writes):
        return {'cacheWriteInput': None, 'cacheWrite1h': None, 'cacheWrite5m': None}
    part = lambda key: None if any(w.get(key) is None for w in writes) else sum(w[key] for w in writes)
    return {'cacheWriteInput': part('total'), 'cacheWrite1h': part('ephemeral_1h'), 'cacheWrite5m': part('ephemeral_5m')}


def git_commit():
    try:
        head = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], capture_output=True, text=True,
                              check=True).stdout.strip()
        dirty = bool(subprocess.run(['git', '-C', str(ROOT), 'status', '--porcelain', '--untracked-files=no'],
                                    capture_output=True, text=True, check=True).stdout.strip())
        return head, dirty
    except (OSError, subprocess.CalledProcessError):
        return None, None


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---- sections ------------------------------------------------------------------------------------------------------

def stage(row, first_started):
    """preregistered: part of the preregistered design (the first 5 valid by start, their invalid predecessors,
    DeepSeek pooled cells); extra: Strata extra instances (plan §3, phase 2): valid rank above 5, or invalid and started
    after the 5th valid instance of the cell; phase3: every instance of a phase-3 supplement configuration (all valid
    ones in the main statistic, no first-5 cut, user 2026-10-23); surplus: any other valid instance beyond the first 5,
    never in a main statistic."""
    if row['config'] in bs.PHASE3_CONFIGS:
        return 'phase3'
    strata = bs.CONFIGS[row['config']]['vendor'] == 'strata'
    designed = 'preregistered'
    if row['valid']:
        if row['first_n'] or row['cell_pooled']:
            return designed
        return 'extra' if strata else 'surplus'
    fifth = first_started.get((row['config'], row.get('supplementary_label') or ''))
    late = fifth is not None and row['started'] is not None and row['started'] > fifth
    return 'extra' if strata and late else designed


def instance(row, phase, diagnostic):
    c = bs.CONFIGS[row['config']]
    handoffs = row.get('handoff_metrics') or []
    claude = c['harness'] == 'claude-code'
    failed = row.get('model_failure_handoffs') or []
    sub = {h.get('k'): h.get('sub_scenario') for h in handoffs}
    status = row.get('score_status')
    rejudge = (row.get('validity') or {}).get('rejudge') or {}
    cost = None
    if c['vendor'] in ('anthropic', 'deepseek') and (row.get('cost_usd') is not None or row.get('cost_cny') is not None):
        cost = {'usd': row.get('cost_usd'), 'cny': row.get('cost_cny') if c['vendor'] == 'deepseek' else None,
                'lowerBound': bool(row.get('cost_lower_bound')), 'basis': c['vendor']}
    adjust = row.get('seconds_adjustment')
    return {
        'id': row['id'], 'scenario': row['scenario'], 'configKey': config_key(row['config'], row.get('supplementary_label')),
        'configNumber': row['config'], 'arm': row['arm'], 'attempt': row['attempt'],
        'supplementaryNote': row.get('supplementary_label'),
        'requestedEffort': row.get('requested_effort'), 'effectiveEffort': row.get('effective_effort'),
        'pooledIntoHigh': bool(row.get('pooled')),
        'startedAt': iso(row.get('started')),
        'validity': {'valid': row['valid'], 'status': (row.get('validity') or {}).get('status'),
                     'notes': list((row.get('validity') or {}).get('reasons') or []),
                     'reminderInterrupts': len(rejudge.get('reminder_interrupts') or []),
                     'streamCutRetries': len(rejudge.get('stream_cut_retries') or [])},
        'selection': {'validRank': row.get('valid_rank'), 'firstN': row.get('first_n'),
                      'mainStatistic': row.get('main_statistic'), 'cellPooled': row.get('cell_pooled'),
                      'inMain': bool(row.get('in_main')), 'stage': None},
        'scoring': {'status': ('diagnostic' if status == 'final' and row['id'] in diagnostic else
                               'modelFailure' if status == 'final' and failed else status),
                    'score': row.get('score'), 'scoreR83': row.get('score_r83'), 'rawScore': row.get('raw_score'),
                    'scoreBeforePenalty': row.get('score_before_penalty'), 'formatPenalty': row.get('format_penalty'),
                    'repairs': row.get('repairs'), 'overallDeduction': row.get('overall_deduction'),
                    'modelFailureSubScenarios': [sub.get(k) for k in failed],
                    'diagnosticEnvironmentQueries': diagnostic.get(row['id'])},
        'time': {'durationSeconds': row.get('seconds'), 'timeLimitSeconds': row.get('time_limit_seconds'),
                 'durationAdjustmentSeconds': sum(adjust.values()) if isinstance(adjust, dict) and adjust else None},
        'tokens': {**tokens(row.get('tokens')),
                   **(summed_cache_write(handoffs) if claude and c['vendor'] != 'strata'
                      else {'cacheWriteInput': None, 'cacheWrite1h': None, 'cacheWrite5m': None}),
                   'source': row.get('token_source'),
                   'lowerBound': bool(row.get('token_source') and 'lower bound' in row['token_source'])},
        'speeds': {'engineInput': (row.get('speeds') or {}).get('engine_input'),
                   'engineOutput': (row.get('speeds') or {}).get('engine_output'),
                   'taskInput': (row.get('speeds') or {}).get('task_input'),
                   'taskOutput': (row.get('speeds') or {}).get('task_output'),
                   'lowerBounds': [{'engine_input': 'engineInput', 'engine_output': 'engineOutput',
                                    'task_input': 'taskInput', 'task_output': 'taskOutput'}[k]
                                   for k in row.get('speed_lower_bounds') or []],
                   'basis': row.get('speed_basis')},
        'toolCalls': row.get('tool_calls'),
        'compactions': row.get('compactions'),
        'pauses': {'known': row.get('pause_known'), 'count': row.get('pause_count'),
                   'continueCount': row.get('continue_count')},
        'cost': cost,
        'harnessReportedCostUsd': row.get('harness_reported_cost_usd') if claude else None,
        'modelIdsReturned': list(row.get('model_ids') or []),
        'serviceTiers': dict(row.get('service_tiers') or {}) if isinstance(row.get('service_tiers'), dict) else {},
        'handoffs': [{'subScenario': h.get('sub_scenario'), 'durationSeconds': h.get('seconds'),
                      'tokens': tokens(h.get('tokens')) if h.get('tokens') else None,
                      'tokensLowerBound': bool(h.get('tokens_lower_bound')),
                      'cacheWriteInput': (h.get('cache_write') or {}).get('total'),
                      'toolCalls': h.get('tool_calls'), 'apiSeconds': h.get('api_seconds'),
                      'compactions': h.get('compactions'),
                      'engine': {'read': h.get('engine_read'), 'generated': h.get('engine_generated'),
                                 'inputSeconds': h.get('engine_input_seconds'),
                                 'decodeSeconds': h.get('engine_decode_seconds')},
                      'modelFailure': bool(h.get('model_failure')),
                      'finalStatus': h.get('final_status'), 'continuationStop': h.get('continuation_stop'),
                      'harnessReportedCostUsd': h.get('harness_reported_cost_usd') if claude else None}
                     for h in handoffs],
    }


def parallel_window(row):
    """{'kind': 'start' | 'overlap', 'windows': [...]} when the instance started in, or only ran during, a
    PARALLEL_WINDOWS period (startedAt + work seconds); None otherwise."""
    if row.get('started') is None:
        return None
    start, end = row['started'], row['started'] + (row.get('seconds') or 0)
    spans = [(n, datetime.fromisoformat(a).timestamp(), datetime.fromisoformat(b).timestamp())
             for n, a, b, _, _ in PARALLEL_WINDOWS]
    began = [n for n, a, b in spans if a <= start <= b]
    if began:
        return {'kind': 'start', 'windows': began}
    ran = [n for n, a, b in spans if start < b and end > a]
    return {'kind': 'overlap', 'windows': ran} if ran else None


def instances(summary, diagnostic):
    out = []
    for scenario, result in summary['scenarios'].items():
        rows = result['instances']
        fifth = {}
        for r in rows:
            if r['valid'] and r.get('valid_rank') == bs.PREREGISTERED_N:
                fifth[(r['config'], r.get('supplementary_label') or '')] = r['started']
        for r in rows:
            item = instance(r, summary['phase'], diagnostic)
            item['selection']['stage'] = stage(r, fifth)
            item['parallelWindow'] = parallel_window(r)
            out.append(item)
    return out


def configs(summary):
    """Descriptive configuration table: the 27 of plan §2 plus the supplementary DeepSeek medium-requested cells, and in
    a phase-3 file the supplement configurations 28 / 29 (kind phase3, never in a comparison)."""
    observed = {}
    supplementary = set()
    for result in summary['scenarios'].values():
        for r in result['instances']:
            observed.setdefault(r['config'], set()).update(r.get('model_ids') or [])
            if r.get('supplementary_label'):
                supplementary.add(r['config'])
    out = []
    for number, c in sorted(bs.CONFIGS.items()):
        if number in bs.PHASE3_CONFIGS and summary['phase'] < 3:
            continue
        for supp in ([False, True] if number in supplementary else [False]):
            arm = ARMS[c['harness'], c['vendor']]
            out.append({
                'key': config_key(number, supp), 'configNumber': number, 'harness': c['harness'],
                'harnessName': HARNESS_NAMES[c['harness']],
                'harnessVersion': CODEX_VERSION if c['harness'] == 'codex' else CLAUDE_CODE_VERSION,
                'model': c['model'], 'modelName': MODEL_NAMES[c['model']],
                'modelId': STRATA_MODEL_ID if c['vendor'] == 'strata' else None,
                'modelIdsReturned': sorted(observed.get(number, ())),
                'vendor': c['vendor'], 'vendorName': VENDOR_NAMES[c['vendor']],
                'effort': 'medium' if supp else c['effort'], 'effectiveEffort': c['effort'],
                'kind': ('supplementary' if supp else 'phase3' if number in bs.PHASE3_CONFIGS else 'main'),
                'local': c['vendor'] == 'strata',
                'arm': arm, 'tokenSource': TOKEN_SOURCE[arm], 'durationBasis': c['harness'],
                'costBasis': c['vendor'] if c['vendor'] in COST_BASIS else None,
                'inComparisons': not supp and number in bs.PREREGISTERED_CONFIGS})
    return out


def comparison_design(summary):
    pairs = [{'group': g, 'first': config_key(a), 'second': config_key(b), 'firstNumber': a, 'secondNumber': b}
             for g, a, b in bs.comparisons(summary.get('suite', 'v1'))]
    return {
        'familyPerScenario': True, 'familySize': len(pairs), 'alpha': bs.ALPHA, 'sides': 2,
        'test': 'Welch t test, Welch-Satterthwaite df',
        'correction': f'Holm step-down within each scenario ({len(pairs)} comparisons)',
        'sample': {'zh': '每个配置取 inMain 为 true 的实例（补充配置不参加）；d = 前者均值 − 后者均值。',
                   'en': 'Each configuration contributes its instances with inMain true (supplementary configurations '
                         'never take part); d = mean(first) - mean(second).'},
        'incomplete': {'zh': '任一侧有未计分实例（score 为 null）时该比较"未计分完"，在 Holm 中按 p = 1 占位；一侧少于 2 个实例时 p 未知，同样按 1 占位。两侧方差都为 0 时 p = 1（均值相等）或 0。',
                       'en': 'A comparison with an unscored instance (score null) on either side is incomplete and '
                             'holds p = 1 in the Holm family; fewer than 2 instances on a side gives no p, also 1. '
                             'Zero variance on both sides gives p = 1 for equal means, else 0.'},
        'decisionRule': {'zh': 'Holm p < alpha 时按 d 的符号判"高于 / 低于"，否则"未分出"。',
                    'en': 'Holm p < alpha: higher / lower by the sign of d; otherwise not separated.'},
        'r83': {'zh': 'r8.3 对照：同一批实例用 scoreR83 重做同一族的检验与 Holm。',
                'en': 'r8.3 check: the same family recomputed on scoreR83 of the same instances.'},
        'pairs': pairs}


def selection_rules(summary):
    return {
        'phase': summary['phase'], 'preregisteredN': summary['preregistered_n'],
        'strataExtraTarget': summary['strata_phase2_max'],
        'zh': ('有效实例按开始时刻排序得到 validRank。phase 1：未合并的格取 validRank ≤ 5（firstN）；DeepSeek 合并格（cellPooled，'
               'medium 请求并入 high）取全部有效实例。phase 2：Strata 的格取 validRank ≤ 10，其余同 phase 1。'
               + ('phase 3：同 phase 2，另加补充配置 28、29（gpt-6-luna xhigh、max），各格取全部有效实例（mainStatistic 为 true，'
                  '不截取前 5 个，用户 2026-10-23），只给实例、不进比较，也没有一致性行。'
                  if summary['phase'] >= 3 else '') + 'inMain 是本文件阶段的结果；'
               '主统计多于前 5 个的格另有一致性行（firstN 为 true 的实例）。'),
        'en': ('Valid instances ordered by start give validRank. Phase 1: cells not pooled take validRank <= 5 (firstN); '
               'pooled DeepSeek cells (cellPooled, medium requests pooled into high) take every valid instance. '
               'Phase 2: Strata cells take validRank <= 10, others as in phase 1. '
               + ('Phase 3: as phase 2, plus the supplement configurations 28 / 29 (gpt-6-luna xhigh / max), every '
                  'valid instance per cell (mainStatistic true, no first-5 cut, user 2026-10-23), instances only, never '
                  'in a comparison and without a consistency row. ' if summary['phase'] >= 3 else '')
               + 'inMain is the result for the phase '
               'of this file; a cell whose main statistic holds more than its first 5 also has a consistency row '
               '(the instances with firstN true).')}


def environment():
    deployment = json.loads((ROOT / f'config/deployments/{STRATA_HOST}.json').read_text())
    hardware = deployment.get('hardware') or {}
    tier = (deployment.get('context_tiers') or {}).get(STRATA_QUANT, [{}])[0]
    defaults = deployment.get('installation_defaults') or {}
    return {
        'harnesses': {
            'codex': {'version': CODEX_VERSION, 'notes': {
                'zh': 'benchmark 专用副本，固定 SHA；ARW Reviewer 运行层；read-only 权限加报告目录写授权，凭据路径 deny-read；搜索关闭；service tier default。',
                'en': 'Dedicated pinned copy; ARW Reviewer runtime; read-only permissions plus a report-directory '
                      'write grant, credential paths deny-read; search disabled; service tier default.'}},
            'claude-code': {'version': CLAUDE_CODE_VERSION, 'notes': {
                'zh': 'benchmark 专用副本，无头 claude -p，不加载任何设置源，dontAsk，Bash 沙箱只读工作目录且无网络，搜索工具禁用。早退接续由 harness 模拟 ARW。',
                'en': 'Dedicated copy, headless claude -p, no setting sources, dontAsk, Bash sandbox read-only on the '
                      'work directory without network, search tools disabled. Early-exit continuation emulates ARW.'}}},
        'strata': {
            'version': STRATA_VERSION, 'host': STRATA_HOST, 'quantization': STRATA_QUANT, 'modelId': STRATA_MODEL_ID,
            'hardware': {'gpu': hardware.get('gpu'), 'vramGiB': hardware.get('vram_gib'), 'cpu': hardware.get('cpu'),
                         'ramGiB': hardware.get('ram_gib')},
            'contextWindow': tier.get('context_window'), 'autoCompactTokenLimit': tier.get('auto_compact_token_limit'),
            'sampling': {k: defaults.get(k) for k in ('temperature', 'top_p', 'top_k')},
            'effortBudgets': {'low': {'thinking': 2048, 'maxOutput': 8192},
                              'medium': {'thinking': 4096, 'maxOutput': 16384},
                              'high': {'thinking': 8192, 'maxOutput': 24576}},
            'guardian': {'thinking': 512, 'maxOutput': 1024, 'harness': 'codex'},
            'notes': {'zh': 'Windows 原生推理进程，单实例串行；启动提示与压缩提示只给 Strata；参数沿用 v0.1.42 调参。',
                      'en': 'Native Windows inference process, one instance at a time; startup and compaction prompts '
                            'only for Strata; parameters from the v0.1.42 tuning.'}},
        'deepseek': {'modelId': 'deepseek-flash', 'modelVersion': 'DeepSeek-V4.1-Flash-1017', 'notes': {
            'zh': 'Codex 上走 DeepSeek 官方 OpenAI 格式端点（Responses），请求经本机回环 relay 原样转发，relay 只记录 usage、模型和 tier；Claude Code 上直连官方 Anthropic 格式端点，token 取 Claude Code stream result。只在低谷时段运行。',
            'en': 'On Codex: DeepSeek official OpenAI-format endpoint (Responses), requests forwarded unchanged by a '
                  'local loopback relay that records only usage, model and tier. On Claude Code: the official '
                  'Anthropic-format endpoint directly, tokens from the Claude Code stream result. Run off-peak only.'}},
        'openai': {'notes': {'zh': 'Codex 内置 openai provider（ChatGPT 套餐登录），经同一 relay 记录 usage；guardian 为原生 codex-auto-review。',
                             'en': 'Codex built-in openai provider (ChatGPT plan login), usage via the same relay; '
                                   'guardian is the native codex-auto-review.'}},
        'anthropic': {'notes': {'zh': 'Claude Code 订阅登录，别名在开跑前解析为具体模型 ID。',
                                'en': 'Claude Code subscription login; aliases resolved to concrete model IDs before the run.'}},
        'durationBasis': DURATION_BASIS, 'costBasis': COST_BASIS}


def variants(paths, base_rows):
    """Per variant: the instances whose scoring fields differ from this file's (the rest are identical)."""
    every = {r['id']: r for result in base_rows['scenarios'].values() for r in result['instances']}
    out = []
    for name, path in paths:
        if name not in VARIANTS:
            raise ValueError(f'Unknown sensitivity variant {name} (known: {", ".join(VARIANTS)})')
        data = json.loads(Path(path).read_text())
        rows = {r['id']: r for result in data['scenarios'].values() for r in result['instances']}
        base = every
        if base_rows['phase'] >= 3 and data.get('phase', 0) < 3:
            # A phase-2 variant in the phase-3 file: the supplement instances are not part of it.
            base = {i: r for i, r in every.items() if r['config'] not in bs.PHASE3_CONFIGS}
        if set(rows) != set(base):
            raise ValueError(f'Variant {name}: instance set differs from the summary')
        for key in ('valid', 'in_main', 'valid_rank', 'first_n', 'config', 'supplementary_label'):
            if any(rows[i].get(key) != base[i].get(key) for i in base):
                raise ValueError(f'Variant {name}: {key} differs from the summary (only scores may differ)')
        overrides = []
        for i in sorted(base):
            if any(rows[i].get(src) != base[i].get(src) for _, src in VARIANT_FIELDS if src in rows[i]):
                overrides.append({'id': i, **{dst: rows[i].get(src) for dst, src in VARIANT_FIELDS if src in rows[i]}})
        compared, zh, en = VARIANTS[name]
        out.append({'id': name, 'comparedWith': compared, 'zh': zh, 'en': en, 'complete': data.get('complete'),
                    'overrides': overrides})
    return out


def published(md, js):
    return {'summaryMd': md, 'summaryMdSha256': sha256(ROOT / md), 'summaryJson': js, 'summaryJsonSha256': sha256(ROOT / js)}


def phase_meta(summary):
    phase = summary['phase']
    texts = {
        1: ('第一阶段：只用预登记实例（Strata 每格前 5 个有效实例）；第二阶段（Strata 加测到 10 个进主统计）完成后另出正式文件。',
            'Phase 1: preregistered instances only (first 5 valid per Strata cell); the formal file follows phase 2 '
            '(Strata extra instances up to 10 in the main statistic).'),
        2: ('第二阶段：按计划的全样本分析，Strata 各格取全部有效实例（至多 10 个），其余配置同第一阶段。',
            'Phase 2: the planned full-sample analysis; Strata cells use every valid instance (up to 10), other '
            'configurations as in phase 1.'),
        3: ('第三阶段补充（三阶段合一）：第二阶段的全部实例与选取不变，另加 gpt-6-luna xhigh（配置 28）、max（配置 29）的补充实例'
            '（Codex，每格全部有效实例、不截取前 5 个，stage 为 phase3）；补充配置不进任何比较，见 caveats 的 phase3-supplement。',
            'Phase 3 supplement (all three phases in one file): every phase-2 instance and selection unchanged, plus the '
            'gpt-6-luna xhigh (configuration 28) and max (29) supplement instances (Codex, every valid instance per cell, no '
            'first-5 cut, stage phase3); the supplement configurations never enter a comparison, see the phase3-supplement caveat.')}
    out = {'number': phase, 'complete': summary['complete'], 'final': False if phase == 1 else summary['complete'],
           'zh': texts[phase][0], 'en': texts[phase][1]}
    if phase >= 2:
        out['phase1'] = {**published(PHASE1_SUMMARY_MD, PHASE1_SUMMARY_JSON),
                         'zh': '用 selection.mainStatistic 可重算第一阶段全部统计；第一阶段敏感性变体只适用于第一阶段实例集，见第一阶段报告，本文件不带。',
                         'en': 'selection.mainStatistic recomputes every phase-1 statistic; the phase-1 sensitivity '
                               'variants apply to the phase-1 instance set only and are in the phase-1 report, not '
                               'in this file.'}
    if phase >= 3:
        out['phase2'] = {**published(PHASE2_SUMMARY_MD, PHASE2_SUMMARY_JSON),
                         'zh': '去掉 configNumber 28、29 的实例即为第二阶段文件的实例集；inMain 与第二阶段相同。',
                         'en': 'Without the configNumber 28 / 29 instances this is the phase-2 instance set; inMain as in '
                               'phase 2.'}
    return out


def check_source(summary, summary_sha):
    """Refuse a summary that benchmark_summary did not write (user 2026-10-23): it must carry the generator marker
    of its phase, or be a published legacy summary by sha256; every instance must have work seconds (valid ones a
    number) and speeds / speed_parts with the four speeds, as benchmark_summary writes them."""
    marker = summary.get('generator') or {}
    if marker:
        if marker.get('tool') != bs.GENERATOR or marker.get('phase') != summary.get('phase') or not marker.get('sha256'):
            raise ValueError(f'summary generator marker is not benchmark_summary of phase {summary.get("phase")}: {marker}')
    elif LEGACY_SUMMARIES.get(summary_sha) != summary.get('phase'):
        raise ValueError('summary.json lacks the benchmark_summary generator marker (regenerate it with '
                         'tools.reviewer.benchmark_summary; hand-written summaries are not exported)')
    problems = []
    for result in summary['scenarios'].values():
        for r in result['instances']:
            if 'seconds' not in r or (r.get('valid') and not isinstance(r['seconds'], (int, float))):
                problems.append(f"{r.get('id')}: no work seconds")
            for key in ('speeds', 'speed_parts'):
                if not isinstance(r.get(key), dict) or set(r[key]) != set(bs.SPEEDS):
                    problems.append(f"{r.get('id')}: {key} lacks the four speeds")
    if problems:
        raise ValueError(f'{len(problems)} instance(s) without the benchmark_summary fields: ' + '; '.join(problems[:10]))


def build(summary, summary_sha, variant_paths=(), diagnostic=None, generated=None):
    diagnostic = diagnostic or {}
    commit, dirty = git_commit()
    return {
        'meta': {
            'benchmarkName': BENCHMARK_NAME, 'benchmarkVersion': BENCHMARK_VERSION, 'schemaVersion': SCHEMA_VERSION,
            'generatedAt': generated or datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'source': {'project': 'qwen_strata', 'commit': commit, 'treeDirty': dirty, 'summarySha256': summary_sha},
            'scoring': {'version': SCORING_VERSION,
                        'zh': '评分 r8.4：按 k 分档计分，不在 0 处截断（N ≥ 0 时 N ÷ P，N < 0 时 N ÷ Σk），整体扣减 max(暂停 0.1, 格式罚 f, ARW 残余 0.1) 只扣一次：最终分 = s − d·|s|；模型失误记 0。',
                        'en': 'Scoring r8.4: k-tier scoring without the cut at 0 (N / P for N >= 0, N / sum k for N < 0); '
                              'one overall deduction d = max(pause 0.1, format penalty f, ARW residual 0.1): '
                              'final = s - d |s|; a model failure scores 0.'},
            'phase': phase_meta(summary),
            'parallelWindows': {
                'zh': 'Strata 加测期间，同一台主机上另有计算进程（nice 19）运行的时段。实例的 parallelWindow 标出开始于某时段（start）或运行中与某时段重叠（overlap）；时段只可能影响速度和用时，不影响分数。',
                'en': 'Periods when other compute (nice 19) ran on the Strata host during the extra runs. An '
                      "instance's parallelWindow marks a start in a period (start) or a run during one (overlap); a "
                      'period can only affect speed and duration, not scores.',
                'windows': [{'id': n, 'start': a, 'end': b, 'zh': zh, 'en': en}
                            for n, a, b, zh, en in PARALLEL_WINDOWS]},
            'statistics': {'alpha': summary['alpha'], 'holmFamilySize': summary['holm_family_size'],
                           'preregisteredN': summary['preregistered_n'], 'strataExtraTarget': summary['strata_phase2_max']},
            'userDecisions': [
                {'zh': '本文件只提供到每个实例的细节，不提供任何汇总统计，也不提供比较结果；重现所需的设计信息（实例有效性、是否进主统计、前 N 个的选取、阶段、比较设计）照常提供（用户 2026-10-22）。',
                 'en': 'This file gives per-instance detail only: no aggregate statistics and no comparison results; the '
                       'design information needed to reproduce them (validity, main-statistic membership, first-N '
                       'selection, stage, comparison design) is included (user 2026-10-22).'},
                {'zh': '本工程的报告只给分场景结果，不算综合分、不排名（D7）；本文件不含权重或综合分（用户 2026-10-22）。',
                 'en': "This project's reports give per-scenario results only, with no combined score and no ranking "
                       '(D7); this file carries no weights or combined scores (user 2026-10-22).'}],
            'units': {'time': 'seconds', 'tokens': 'count', 'speeds': 'tokens per second', 'cost': 'USD (cny: CNY)',
                      'timestamps': 'ISO 8601, UTC'},
            'reportConversions': {
                'strataEquivalentCostUsdPerMillion': STRATA_EQUIVALENT_USD_PER_M,
                'anthropicWeeklyQuotaPercentPerUsd': bs.QUOTA_PER_USD,
                'zh': '本工程报告里的两项换算（都不是费用）：Strata 的测量规则等效费用 =（未缓存×0.15 + 缓存×0.016 + 输出×0.47）/ 1e6 美元；Anthropic 周额度百分比 = 等价美元 × 0.086。',
                'en': "Two conversions of this project's reports (neither is a cost): the Strata measurement-rule "
                      'equivalent = (uncached x 0.15 + cached x 0.016 + output x 0.47) / 1e6 USD; Anthropic weekly '
                      'quota percent = API-equivalent USD x 0.086.'}},
        'scenarios': [{'id': sid, **{k: v for k, v in s.items() if k not in ('zh', 'en', 'timeLimit')},
                       'description': {'zh': s['zh'], 'en': s['en']},
                       'timeLimit': {'rule': s['timeLimit'], **TIME_LIMITS[s['timeLimit']]}}
                      for sid, s in SCENARIOS.items() if sid in summary['scenarios']],
        'environment': environment(),
        'configs': configs(summary),
        'selection': selection_rules(summary),
        'comparisonDesign': comparison_design(summary),
        'instances': instances(summary, diagnostic),
        'sensitivityVariants': variants(variant_paths, summary),
        'caveats': caveats(summary['phase']),
    }


# ---- publication safety ---------------------------------------------------------------------------------------------

ALLOWED_URL_HOSTS = ('api.deepseek.com', 'api-docs.deepseek.com')
FORBIDDEN_KEYS = {'report', 'reports', 'findings', 'finding', 'answer', 'answerkey', 'expected', 'decisions',
                  'session', 'sessionid', 'thread', 'threadid', 'instanceid', 'requestid', 'messageid', 'dir', 'path',
                  'prompt', 'reasoning', 'password', 'apikey', 'token_value', 'credentials'}


def safety_patterns(users=None):
    users = users if users is not None else {getpass.getuser(), Path.home().name}
    patterns = [
        ('ipv4', r'(?<![\w.])(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?![\w.])'),
        ('ipv6', r'(?i)(?<![\w:])(?:[0-9a-f]{1,4}:){3,7}[0-9a-f]{1,4}(?![\w:])'),
        ('localhost', r'(?i)\blocalhost\b'),
        ('unix-path', r'(?<![\w.])/(?:home|mnt|var|tmp|root|usr|etc|opt|proc|Users|media|srv|run)\b'),
        ('home-path', r'~/'),
        ('windows-path', r'(?i)(?<![\w])[a-z]:[\\/]|\\\\wsl'),
        ('uuid', r'(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b'),
        ('request-id', r'\b(?:req|msg|resp|chatcmpl|toolu|call|sess)[_-][A-Za-z0-9]{8,}'),
        ('secret', r'(?i)\b(?:sk|pk|rk)-[A-Za-z0-9_-]{12,}|\bBearer\s+\S|-----BEGIN|\beyJ[A-Za-z0-9_-]{10,}'),
        ('assignment', r'(?i)\b(?:api[_-]?key|password|passwd|secret|auth[_-]?token|access[_-]?token)\s*[:=]'),
        ('private-file', r'(?i)private\.toml|\.state/|\.credentials|\.claude\.json|\.profile\b|\.env\b'),
        ('email', r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'),
        ('url', r'(?i)\b(?:https?|wss?)://(?!(?:' + '|'.join(re.escape(h) for h in ALLOWED_URL_HOSTS) + r')(?:[/:]|$))\S+'),
    ]
    patterns += [(f'user-name', r'(?i)(?<![A-Za-z0-9])' + re.escape(u) + r'(?![A-Za-z0-9])') for u in sorted(users) if u]
    return [(name, re.compile(rx)) for name, rx in patterns]


def safety_hits(value, users=None):
    """(json path, pattern name, excerpt) for every string or key of `value` matching a publication-safety pattern,
    and every forbidden key name."""
    patterns = safety_patterns(users)
    hits = []

    def text(s, where):
        for name, rx in patterns:
            m = rx.search(s)
            if m:
                hits.append((where, name, s[max(0, m.start() - 20):m.end() + 20]))

    def walk(v, where):
        if isinstance(v, dict):
            for k, item in v.items():
                if re.sub(r'[^a-z_]', '', str(k).lower()).replace('_', '') in FORBIDDEN_KEYS:
                    hits.append((f'{where}.{k}', 'forbidden-key', str(k)))
                text(str(k), f'{where}.{k}')
                walk(item, f'{where}.{k}')
        elif isinstance(v, list):
            for i, item in enumerate(v):
                walk(item, f'{where}[{i}]')
        elif isinstance(v, str):
            text(v, where)
    walk(value, '$')
    return hits


def write(summary_path, out, variant_paths=(), diagnostic_path=DIAGNOSTIC):
    summary = json.loads(Path(summary_path).read_text())
    check_source(summary, sha256(summary_path))
    diagnostic = json.loads(Path(diagnostic_path).read_text())['instances'] if diagnostic_path else {}
    result = build(summary, sha256(summary_path), variant_paths, diagnostic)
    hits = safety_hits(result)
    if hits:
        for where, name, excerpt in hits[:50]:
            print(f'safety: {name} at {where}: {excerpt!r}', file=sys.stderr)
        raise SystemExit(f'refused: {len(hits)} publication-safety hit(s); nothing written')
    Path(out).write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--summary', type=Path, required=True, help='benchmark_summary summary.json')
    parser.add_argument('--out', type=Path, required=True, help='output JSON file')
    parser.add_argument('--variant', action='append', default=[], metavar='ID=SUMMARY',
                        help=f'sensitivity variant summary ({", ".join(VARIANTS)}); repeatable')
    parser.add_argument('--diagnostic', type=Path, default=DIAGNOSTIC, help='session-check diagnostic list')
    args = parser.parse_args()
    pairs = []
    for item in args.variant:
        name, sep, path = item.partition('=')
        if not sep:
            parser.error('--variant takes ID=SUMMARY')
        pairs.append((name, path))
    result = write(args.summary, args.out, pairs, args.diagnostic)
    print(json.dumps({'instances': len(result['instances']), 'configs': len(result['configs']),
                      'variants': [v['id'] for v in result['sensitivityVariants']]}))


if __name__ == '__main__':
    main()
