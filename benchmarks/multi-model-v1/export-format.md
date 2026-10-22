# 多模型 benchmark v1 公开结果文件格式（Reviewer Model Benchmark v2.0）

`tools/reviewer/benchmark_export.py` 把 `benchmark_summary` 的 `summary.json` 转成一份公开的 JSON 结果文件，给页面工程（Reviewer Model Benchmark v2.0）读取。本文说明文件里的每个字段，以及怎样只用这份文件重算本工程报告里的全部统计量。

## 决定

- **只给实例层细节**（用户 2026-10-22）：文件里没有任何汇总统计（均值、SD、区间、配置表计数），也没有比较结果（d、SE、p、Holm p、判定、r8.3 是否改变结论）。重现所需的设计信息照常提供：每个实例的有效性、是否进主统计、前 N 个的选取标记、阶段，以及比较设计本身（每场景 25 对、α、Holm 族大小、Welch t）。配置表只有描述性字段。
- **D7**（用户 2026-10-22 定措辞）：本工程的报告只给分场景结果，不算综合分、不排名。文件里没有权重和综合分；这条写在 `caveats` 里，是对本工程自己报告的陈述，不是对使用方的限制。
- **费用**：只在有计费依据时给 `cost`。DeepSeek 按官方价目逐请求重算；Anthropic 给 Claude Code 报的 API 等价美元，并注明是订阅运行、不是账单。Strata（本地模型）和 OpenAI（ChatGPT 套餐）没有 `cost`。Claude Code 对任何后端报的 `total_cost_usd` 都只放在 `harnessReportedCostUsd`，对非 Anthropic 后端它不是费用。

## 生成

```
python3 -m tools.reviewer.benchmark_export --summary <summary.json> --out <file> \
    [--variant A1=<summary.json> ...] [--diagnostic benchmarks/multi-model-v1/session-diagnostic.json]
```

- `--summary` 是 `benchmark_summary` 用当前代码生成的 `summary.json`。导出要用到 `handoff_metrics`、`score_r83`、`model_failure_handoffs` 等扩展字段，所以旧版 summary 要先用同一份 records 和计分根重新生成。
- `--variant` 是同一批实例在另一计分根上生成的 summary，只有计分字段可以不同（有效性、排名、选取、配置不同时报错）。可用的 id 见下文「敏感性变体」。
- `--diagnostic` 是会话检查后记诊断分的实例清单（`session-diagnostic.json`，实例 id → 环境查询次数）。第二阶段的 4 个已补入（共 16 个）。
- **发布安全自检**：输出前扫描整份结果的所有键和字符串，发现 IPv4/IPv6、localhost、本机路径（`/home`、`/mnt`、`/var`、`/tmp` 等，`~/`，Windows 盘符，`\\wsl`）、当前用户名、邮箱、UUID、请求或消息 id（`req_`、`msg_`、`toolu_`、`chatcmpl` 等）、密钥形态（`sk-`、Bearer、JWT、PEM）、`api_key=` 一类赋值、私有文件名（`private.toml`、`.state/`、`.credentials`、`.env`）、白名单之外的 URL，或者禁用键名（report、findings、answer、expected、decisions、session、thread、instanceId、dir、path、prompt 等），就报错退出，什么都不写。字段一律按白名单逐个复制，不整体搬运记录。

## 顶层结构

| 键 | 内容 |
|---|---|
| `meta` | 名称、版本、生成信息、计分版本、阶段、统计常数、用户决定、单位、报告换算常数 |
| `scenarios` | 4 个场景：reviewerId、版本、修订号、子场景、P、Σk、说明、时限规则 |
| `environment` | harness 版本与设置、Strata 主机与模型参数、DeepSeek / OpenAI / Anthropic 的接入方式、耗时与费用口径 |
| `configs` | 29 个配置（27 个预登记配置，加 2 个 DeepSeek medium 请求补充配置），只有描述性字段 |
| `selection` | 实例选取规则（validRank、前 N、合并格、阶段） |
| `comparisonDesign` | 比较设计：25 对、Welch、Holm、α、判定规则、未计分完的处理 |
| `instances` | 全部实例（含无效、未进主统计和第二阶段加测） |
| `sensitivityVariants` | 敏感性变体：与本文件分数不同的实例及其计分字段 |
| `caveats` | 局限说明（中英文） |

约定：时间单位为秒；token 为计数；速度为 token/s；费用为美元（`cny` 为人民币）；时间戳为 ISO 8601、UTC、微秒精度。`null` 一律表示未知或不适用，不是 0。中英文成对的说明都放在 `zh`、`en` 两个键下。

## meta

- `benchmarkName` 固定为 "Reviewer Model Benchmark"，`benchmarkVersion` 为 "2.0"，`schemaVersion` 是本格式的版本号（当前为 1，字段改名或删除时加 1）。
- `generatedAt`：生成时刻（UTC）。`source`：`commit`（本工程 HEAD）、`treeDirty`（已跟踪文件是否有未提交改动）、`summarySha256`（输入 summary.json 的 sha256）。
- `scoring`：计分版本 r8.4 及说明。N = Σ正例得分 − Σ失败反例 k；N ≥ 0 时分数 = N ÷ P，N < 0 时分数 = N ÷ Σk；整体扣减 d = max(暂停 0.1, 格式罚 f, ARW 残余 0.1) 只扣一次，最终分 = s − d·|s|；模型失误（没有报告）记 0。
- `phase`：`number`（1 或 2）、`complete`（主统计实例是否都已计分）、`final`（第一阶段恒为 false；第二阶段计分完成后为 true）。第二阶段文件另有 `phase1`：已发布的第一阶段报告与 summary.json 的路径（相对工程根）和 sha256（`summaryMd`、`summaryMdSha256`、`summaryJson`、`summaryJsonSha256`），并说明用 `selection.mainStatistic` 可重算第一阶段全部统计，第一阶段敏感性变体只适用于第一阶段实例集，不在第二阶段文件里。
- `parallelWindows`：Strata 加测期间同一主机上另有计算进程（nice 19）运行的时段 W1–W5，每项 `id`、`start`、`end`（UTC）和说明；实例的 `parallelWindow` 据此标记（见 instances）。
- `statistics`：`alpha` 0.05、`holmFamilySize` 25、`preregisteredN` 5、`strataExtraTarget` 10。
- `userDecisions`：上文两条用户决定。
- `reportConversions`：本工程报告用的两个换算常数，都不是费用：Strata 的测量规则等效费用（每百万 token 的美元数：未缓存 0.15、缓存 0.016、输出 0.47），以及 Anthropic 周额度百分比 = API 等价美元 × 0.086。

## scenarios

| 字段 | 含义 |
|---|---|
| `id` | 场景 id（`code-spec-v5`、`code-standards-v5.1`、`commit-audit-v3`、`spec-readiness-v4.3`） |
| `reviewerId`、`name`、`version`、`revision` | ARW reviewer id、显示名、场景版本、冻结修订号 |
| `subScenarios` | 子场景。SR 有 `runtime-migration`、`artifact-promotion` 两个独立根线程，合并计一个分数；其余场景只有 `default` |
| `positives` | P，正例数（分数正半轴的分母） |
| `negativeKSum` | Σk，答案键全部反例的 k 之和（负半轴的分母） |
| `timeLimit.rule` | `reading-volume`：CS、CStd 按各配置自己的速度算 T，到 T 硬中断，实例的 T 在 `time.timeLimitSeconds`；`arw`：SR、CA 用 ARW 原版，55 分钟提醒、60 分钟中断，`timeLimitSeconds` 为 null |

P 是答案键正例（problemCases）数，合并用例计一个；Σk 是全部反例的 k 之和（noOther 按 0.25，合并用例计一次）。两者（CS 20 / 7.25、CStd 26 / 16.25、SR 23 / 14.75、CA 29 / 12.5）已从冻结答案键重算确认：答案键由 ARW 快照叠加 arw-patches/ 重建，sha256 与 judgment/registry.json 登记一致（10-22）。

## configs

每个配置一行，只有描述性字段：

| 字段 | 含义 |
|---|---|
| `key` | `<harness>/<model>/<effort>`，例如 `codex/gpt-6.1-sol/low`；补充配置为 `.../medium`（如 `codex/deepseek-flash/medium`） |
| `configNumber` | plan §2 的配置号 1–27；补充配置与它所在的 high 配置同号 |
| `harness`、`harnessName`、`harnessVersion` | `codex` / `claude-code`，显示名，版本（Codex 0.163.0、Claude Code 2.1.303） |
| `model`、`modelName`、`modelId`、`modelIdsReturned` | 本工程的模型名，显示名，Strata 的固定模型 ID，以及该配置实例实际返回过的模型 ID |
| `vendor`、`vendorName`、`local` | `openai` / `deepseek` / `strata` / `anthropic`；`local` 只对 Strata 为 true |
| `effort`、`effectiveEffort` | 请求的强度与实际生效的强度（DeepSeek medium 请求在端点映射为 high） |
| `kind` | `main`（预登记配置）或 `supplementary`（DeepSeek medium 请求、时限 T 与 high 不同的补充配置） |
| `arm`、`tokenSource`、`durationBasis`、`costBasis` | 臂名；token、耗时、费用的口径（口径文字在 `environment`） |
| `inComparisons` | 是否参加预登记比较（补充配置为 false） |

## instances

每个实例一项。`id` 形如 `<arm>/<scenario>/<名字>-a<尝试号>`，不含本机路径或会话 id。

| 字段 | 含义 |
|---|---|
| `scenario`、`configKey`、`configNumber`、`arm`、`attempt` | 所属场景、配置、臂、尝试号 |
| `supplementaryNote` | 补充配置实例的标签（如 `high requested as medium, T=344`），其余为 null。实例所在的格 = (`configNumber`, `supplementaryNote`) |
| `requestedEffort`、`effectiveEffort`、`pooledIntoHigh` | 请求与生效的强度；DeepSeek medium 请求的实例并入 high 格时为 true |
| `startedAt` | 开始时刻（首个请求进入模型）。无效实例可以为 null |
| `validity` | `valid`、`status`（`valid`、`invalid`、`no-record`、`void` 等）、`notes`（判定理由）、`reminderInterrupts`、`streamCutRetries`（重判时处理的提醒中断和断流重试次数） |
| `selection` | `validRank`（格内有效实例按开始时刻的序号，无效为 null）、`firstN`（validRank ≤ 5）、`mainStatistic`（第一阶段是否进主统计）、`cellPooled`（所在格是否是 DeepSeek 合并格）、`inMain`（本文件阶段是否进主统计）、`stage`（见下） |
| `scoring` | 见下 |
| `time` | `durationSeconds`（工作秒数，口径见 `environment.durationBasis`）、`timeLimitSeconds`（T，ARW 时限场景为 null）、`durationAdjustmentSeconds`（重判扣除的秒数） |
| `tokens` | `uncachedInput`、`cachedInput`、`output`；Claude Code 的 Anthropic 和 DeepSeek 臂另有 `cacheWriteInput`、`cacheWrite1h`、`cacheWrite5m`（缓存写入已包含在 `uncachedInput` 里，单列只为按价目计费）；`source`；`lowerBound`（有段没有 result，是下限） |
| `speeds` | `engineInput`、`engineOutput`（模型直接速度）、`taskInput`、`taskOutput`（用户感知速度 = 未缓存输入、输出 ÷ 工作秒数）；`lowerBounds` 列出是下限的项；`basis` 为口径文字。API 模型的 `engineInput` 恒为 null |
| `toolCalls` | 工具调用数（Codex 从 rollout 根线程计，不含 guardian；Claude Code 从主会话 tool_use 计） |
| `pauses` | `known`、`count`（暂停次数）、`continueCount`（Claude Code 早退接续次数） |
| `cost` | 只对 Anthropic 和 DeepSeek：`usd`、`cny`（只有 DeepSeek）、`lowerBound`（有被提醒中断丢弃的请求未计入）、`basis`。其余臂为 null |
| `harnessReportedCostUsd` | Claude Code 三个臂各段 `total_cost_usd` 之和（按 Anthropic 价目，非 Anthropic 后端不能当费用）；Codex 臂为 null |
| `modelIdsReturned`、`serviceTiers` | 实际返回的模型 ID；service tier → 请求数（按记录顺序） |
| `parallelWindow` | 实例与 `meta.parallelWindows` 的关系：`{kind, windows}`，`kind` 为 `start`（`startedAt` 落在某时段内）或 `overlap`（开始于时段外，但 `startedAt` 到 `startedAt + durationSeconds` 与某时段重叠），`windows` 为时段 id；都不沾为 null。只影响速度和用时的解读，不影响分数 |
| `handoffs` | 每个根线程一项：`subScenario`、`durationSeconds`、`tokens`、`tokensLowerBound`、`cacheWriteInput`、`toolCalls`、`apiSeconds`、`engine`（Strata 的 read、generated、输入处理秒数、解码秒数）、`modelFailure`、`finalStatus`（ARW 完成状态或 Claude Code 结果形式：`ready`、`incomplete`、`not-arw-form`）、`continuationStop`（Claude Code 接续循环停止原因：`delivered`、`model_error`、`hard_limit`）、`harnessReportedCostUsd` |

`scoring`：

| 字段 | 含义 |
|---|---|
| `status` | `final`（已计分）；`diagnostic`（已计分，会话检查发现环境查询但未接触隐藏材料，分数照常计入）；`modelFailure`（已计分，至少一个子场景没有报告，按 0 计）；`unscored`（有效但未计分，如第一阶段文件里的第二阶段加测）；null（无效实例）。前三种都算已计分 |
| `score` | r8.4 最终分；未计分或无效为 null |
| `scoreR83` | 同一实例的 r8.3 分（截到 [0, 1]）；正分实例与 `score` 逐位相同 |
| `rawScore`、`scoreBeforePenalty`、`formatPenalty`、`overallDeduction`、`repairs` | N ÷ P（诊断用）、扣减前分数 s、格式罚 f、整体扣减 d、可修复格式错误数 |
| `modelFailureSubScenarios` | 记为模型失误的子场景 |
| `diagnosticEnvironmentQueries` | 诊断分实例的环境查询次数，其余为 null |

`stage`：`preregistered` 是预登记设计内的实例（格内前 5 个有效实例、它们之前的无效实例、DeepSeek 合并格的全部实例）；`extra` 是 Strata 加测（validRank > 5 的有效实例，或开始于第 5 个有效实例之后的无效实例）；`surplus` 是其他配置多出的有效实例（validRank > 5），不进任何主统计。

## 重算规则

以下规则与 `benchmark_summary` 相同；按这些规则只用本文件即可重算本工程报告里的全部统计量（检查结果见文末）。

### 实例选取

- 格 = 场景内的 (`configNumber`, `supplementaryNote`)。格内有效实例按 `validRank` 排序。
- 主统计样本：第一阶段取 `valid` 且 `selection.mainStatistic` 为 true 的实例，即未合并的格取 validRank ≤ 5，DeepSeek 合并格取全部有效实例。第二阶段的 Strata 格取 validRank ≤ `strataExtraTarget`（10），其余同第一阶段。本文件阶段的结果就是 `selection.inMain`。
- 一致性行：主统计的实例集合与 `firstN` 为 true 的集合不同时，另用 `firstN` 实例算一行。
- 补充配置自己算一行（主统计规则同上），不进比较；另有一行描述性的"high + medium 合并"行，样本是同号 high 格的主统计实例加补充格的主统计实例，这一行的"有效"为样本数，"无效"为 0。
- 只用已计分实例（`score` 非 null）算分数统计；格内有未计分实例时该行不完整（`complete` 为 false）。

### 一行的统计量

- n = 已计分实例数；均值；SD 用 n − 1；SE = SD ÷ √n；95% 区间 = 均值 ± t(0.975, n − 1) × SE（t 分布，n < 2 时未知）；中位数（偶数个取中间两数的平均）；最小值；负分实例数。
- r8.3 均值 = `scoreR83` 的均值；`rawScore`、f 的均值只在已计分实例都有值时给出；修复总数只在行完整时给出。
- 耗时、三类 token、工具调用、四项速度都是样本内各实例的算术平均，任一实例缺值即为未知（不补 0）；速度有任一实例是下限，均值就标下限。占时限 = 各实例 `durationSeconds ÷ timeLimitSeconds` 的平均（ARW 时限场景没有）。
- 无效数 = 格内 `valid` 为 false 的实例数（所有尝试，不限阶段）。
- 费用：DeepSeek、Anthropic 取 `cost.usd` 之和（任一未知即未知），均值 = 总和 ÷ 样本数；DeepSeek 另有人民币。OpenAI 只报 token。Strata 在报告里用 `meta.reportConversions` 的等效费用公式按实例的三类 token 计算（只作比较代理）。Anthropic 周额度 = 美元总和 × 0.086（%）。任一实例 `cost.lowerBound` 为 true 时总和是下限。
- 模型 ID、service tier = 样本内各实例取值的并集。

### 比较

- `comparisonDesign.pairs` 列出每场景的 25 对（first、second 为配置号）：同一 harness 内 Strata 对同强度的每个其他配置（Codex 8 对、Claude Code 11 对），以及 Strata、DeepSeek 各自的 Codex 对 Claude Code（6 对）。每对的样本是两侧主配置的主统计实例（补充配置不参加）。
- 两侧都有实例且全部已计分时做 Welch t 检验：d = 前者均值 − 后者均值，SE = √(s₁²/n₁ + s₂²/n₂)，自由度用 Welch–Satterthwaite，p 为双侧。两侧方差都为 0 时 p 为 1（均值相等）或 0。任一侧少于 2 个实例时 p 未知。
- Holm 校正在每个场景的 25 个比较内做；未计分完或 p 未知的比较按 p = 1 占位。判定：Holm p < α（0.05）时按 d 的符号判"高于 / 低于"，否则"未分出"；未计分完的比较判"未计分完"。
- r8.3 对照：同一批实例用 `scoreR83` 重做同一族的检验和 Holm；"结论改变"比较 r8.4 与 r8.3 的判定。

### 报告里的其他数

- 逐实例表按 (配置号, 补充标签, `startedAt`, id) 排序，没有开始时刻的无效实例排在前面。费用一列：第一阶段报告的逐实例表里 Strata 的"费用"是 Claude Code 报的 `harnessReportedCostUsd`（Strata-Codex 为未知），不是等效费用（第一阶段报告已加更正）；第二阶段报告起与配置表一致，Strata 为按实例三类 token 算的等效费用（`meta.reportConversions`）。
- 速度与用时的两轮拆分（第二阶段报告）：Strata 两臂进主统计的有效实例按 `stage` 和 `parallelWindow` 分三组：第一轮（`preregistered`）、加测（`extra` 且 `parallelWindow` 为 null）、加测并行（`extra` 且不为 null）；各组的速度、耗时取算术平均，SD 用 n − 1。
- 墙钟表：按 (臂, 场景, 是否 `extra`) 分组，只用有 `startedAt` 的实例；首个开始 = 最早的 `startedAt`；末个结束 = 各实例 `startedAt + durationSeconds` 的最大值（缺耗时按 0）；时刻按 JST 显示到分钟（截断）。"实例数（含无效）"是组内有开始时刻的实例数；加测表的"有效实例"是组内有效实例数。
- 第一阶段实例数 = `stage` 为 `preregistered` 的有效实例数（557）。

### 敏感性变体

`sensitivityVariants` 每项有 `id`、`comparedWith`（报告里与之对照的基准：`formal` 是本文件，`preGap` 是另一个变体）、`complete`、说明，以及 `overrides`：分数与本文件不同的实例，每项给出该变体下的 `score`、`scoreStatus`、`rawScore`、`formatPenalty`、`repairs`，有记录时还有 `scoreR83`。重算某个变体时，把 overrides 覆盖到实例上，其余实例和全部设计字段不变，再按上面的规则计算。

| id | 内容 | 对照基准 |
|---|---|---|
| `A1` | 歧义清单 A1 另一读法（只动 CS） | `formal` |
| `A2E_min`、`A2E_full` | 歧义清单 A2 另一读法的 min / full 两版（只动 CA） | `formal` |
| `preGap` | 补裁缺口前（9 个实例未计分完） | — |
| `gapsLower`、`gapsUpper` | 缺口下界 / 上界 | `preGap` |
| `preLineShift` | 缺口补裁后、CA 第 2 关行号修复（N1）前 | `preGap`；本文件（正式）以它为基准 |
| `A6` | 歧义清单 A6 另一读法（CA 规则 24 "redacted value" 指整个事件；只动 CA 的第二阶段加测实例） | `formal` |

第二阶段文件只带 `A6`。`A1`、`A2E_*` 和缺口、行号相关的变体只适用于第一阶段实例集，在第一阶段文件和报告里；第二阶段加测实例中没有 A1、A2 同类 finding（按 finding 原文和决定理由逐条查过），所以第二阶段没有对应变体。

`preGap`、`gapsLower`、`gapsUpper`、`preLineShift` 的汇总在记录 `score_r83` 之前生成，overrides 里没有 `scoreR83`，这四个变体的 r8.3 列不可重算（报告也没有用到）。

## 不在本文件里的数

以下是过程或输入数据，不是实例统计，本文件不提供，也不能从实例层重算：盲裁、复核、会话检查的调用数和费用；CStd 格式罚基准 p基准（18 / 224）；A1 改动的 finding 条数（15 条，属于裁决明细）；Claude Code 接续段数（如 haiku-low-a7 的 46 段）；DeepSeek 批次余额对账（含账户余额）；盲裁与计分各阶段的时间线。

## 与 v1 statistics.json 的主要差别

- v1 是配置数组，每个配置带固定 3 次重复的分数和观测；v2 是实例数组，每格实例数不固定（无效、加测都在），每个实例自带配置键、有效性、选取标记和阶段。
- v1 的分数在 0–1 之间；v2 的 r8.4 分数可以为负、可低于 −1（`caveats` 的 negative-scores 条）。
- v1 有固定权重的综合分；v2 没有权重和综合分（D7），也没有任何汇总统计。
- v1 的强度是固定的 low / medium / high；v2 的 DeepSeek 为 low / high / max，另有 medium 请求的补充配置。
- v1 的 SR 取 artifact-promotion 子场景的耗时和 token；v2 实例层给合计，`handoffs` 给每个子场景的耗时、token、工具调用。
- v1 只有 input、cachedInput、output；v2 另有缓存写入（Anthropic）、四项速度、工具调用、暂停、费用口径和 harness 报价。

## 检查结果（第一阶段，2026-10-22）

用一个只读导出文件、不导入本工程代码的重算脚本（`python3 -I`，自带 t 分布、Welch、Holm），从实例层重算后逐项比对：正式 `summary.json` 的全部配置行和比较、每个实例字段，7 个变体汇总（A1、A2 min、A2 full 全部字段；其余四个比对计分字段和比较），报告的全部表格（4 个场景的配置表、比较表、逐实例表，r8.3 表，负分表，两张墙钟表）逐格比对显示值，以及报告正文里的数（结论分布与按对手归并、|d| 区间个数、N1、A1 / A2 / 缺口各项、诊断分、模型失误、缺数据实例等）。浮点允许 1e-9 相对误差。结果为 87952 / 87952 项一致。

比对中发现报告正文一处有误：敏感性一节写"A2 min 只动 luna-high-a10……它不在主统计，p 不变"，而 summary.json 和 A2 min 变体汇总都表明 luna-high-a10 是 CA 配置 6（Codex gpt-6-luna high）的 validRank 5，在主统计；A2 min 使 CA 12 对 6 的未校正 p 由 0.1341 变为 0.1350，Holm p 仍为 1，结论不变。检查脚本按汇总的实际值核对。另外，报告墙钟一节写"末个结束 = 最晚的开始 + 该实例工作秒数"，表中的数实际是各实例"开始 + 工作秒数"的最大值（上文按实际算法写）。

## 检查结果（第二阶段，2026-10-22）

用只读第二阶段导出文件、不导入本工程代码的重算脚本（`python3 -I`，自带 t 分布、Welch、Holm），从实例层重算后与第二阶段 `summary.json` 逐项比对：主统计行、补充行和一致性行（26 行，含 CA 的 2 个 DeepSeek 合并格）的 n、均值、SD、SE、95% 区间、中位数、最小值、负分数、r8.3 均值、rawScore 与 f 均值、耗时、三类 token、工具调用、四项速度和 Strata 等效费用；100 个比较的配对、d、SE、df、p、Holm p、判定和 r8.3 的 Holm p 与判定；A6 变体（按 overrides 覆盖后）的 d、Holm p 和判定；按 `stage` 与 `parallelWindow` 拆分的 Strata 引擎输出速度（n、均值、SD、最小、最大）与报告一致。浮点允许 1e-9 相对误差。结果为 4149 / 4149 项一致。
