# 多模型 benchmark v2 运行计划（草案，未冻结）

起草 2026-10-24。本稿只做题目、brief 与设置的准备，没有运行任何模型，也没有领取租约。冻结前要按 AGENTS.md 硬约束 1 交独立 agent 审查，并由用户决定第 9 节列出的事项。v1 的目录、冻结件和 SHA 绑定一律不改，v2 的全部文件都在本目录。

## 1. 目的

沿用 [v1 计划 §1](../multi-model-v1/plan.md#1-目的)的问题：Strata 作为 Codex / Claude Code 后端时的 reviewer 能力，与 OpenAI、DeepSeek、Anthropic 模型对照。v2 相对 v1 的改动只有三类：

1. 修正 v1 盲裁中发现的场景文本歧义和 brief 措辞（[歧义清单](../reviewer-suite-v1/next-version-ambiguities.md)）。
2. 对齐两个 harness 的窗口、压缩点、推理强度和输出上限（用户 2026-10-22，测量规则「跨 harness 比较」）。
3. 待用户决定的评分与设计变更（第 6、7 节）。

按测量原则，v2 结果与 v1 不可比；v1 留作历史基线和噪声估计。

## 2. 目录

| 路径 | 内容 |
|---|---|
| `plan.md` | 本计划 |
| `scenarios/<版本>.patch` | v2 对 v1 冻结场景的补丁（只改措辞，行数不变） |
| `scenarios/manifest-<版本>.json` | v2 场景清单：v1 清单 + 上面的补丁 |
| `briefs/<版本>-brief.md` | 四份盲裁 brief 草案，由 v1 冻结件改出 |

未改动的场景（Code Standards v5.1、Spec Readiness v4.3）直接用 v1 的冻结清单，不复制。

## 3. 场景的引用方式

v1 的场景是 ARW 源码快照 + 清单中的补丁序列（`tools.reviewer.freeze_arw_source` 物化）；计分器的 k 档登记、格式基准、judgment 绑定都按 `expected.json` 的 SHA 查找，brief 引用行号。

选"引用加补丁"，不复制整套场景：

- v2 清单 = v1 清单原样 + 末尾一个 v2 补丁；`snapshot.file` 改为指回 v1 的快照（`../../reviewer-suite-v1/source-snapshots/current/…`），所以 v1 的补丁路径照常解析，快照和 v1 补丁不复制。
- v2 补丁只改措辞，每个改动文件的行数不变，`expected.json` 逐字节不变。因此 k 档登记、格式基准、judgment 绑定和 brief 中的行号引用全部继续有效，计分器不用改。
- 单测 `tests/test_multi_model_v2.py` 核对：v2 清单前缀与 v1 清单相同、补丁只改清单声明的文件、行数不变、答案键不变。

复制整套场景的代价是两份 tarball 和十几个补丁要同步维护，而且 SHA 绑定要重新登记，没有好处。

## 4. 歧义题目

逐项对应[歧义清单](../reviewer-suite-v1/next-version-ambiguities.md)。"已改"项的场景改动由 `scenarios/*.patch` 实现，brief 改动在 `briefs/`；brief 的机械核对用 `python3 -m tools.reviewer.check_briefs --suite v2`。

### 4.1 场景原文（a 组）

| 项 | 处理 | 改了什么 | 理由 |
|---|---|---|---|
| A1 | 已改（CS v5.1） | `governing-spec.md:160` 拆成两句："Catalog locale keys are trimmed and lowercased; a blank catalog key stays blank. A member's `locale` is trimmed and lowercased, a missing or blank member locale being `en`." CS brief 补一条说明这一行的读法 | 原句让"空白目录键归 `en`"成为可行读法；新句与代码（空白目录键保留为空）和 v1 裁决先例（不归 `en`）一致，答案键不变 |
| A2 | 已改（CA v3.1） | issue 01 第 30 行（base 和 candidate 两份）"otherwise returns an error result" 改为 "otherwise returns a result whose `ok` is `false`" | v1 两种读法下代码行为相同，可执行检查定不了；新句按答案键的主读法写明形状 |
| A3 | 不改，待用户决定 | — | 经核对不是歧义：政策文档头写明同节后一条覆盖前一条。改写规则 26 会去掉场景有意设计的"规则覆盖"难点，属于改场景难度，不是消歧 |
| A4 | 不改，待用户决定 | — | `promotion-recovery.md:65`、`:85`（及 `:77`）是 MODULES#1 与 DEPENDENCIES-DATA-FLOW#0 问题用例的证据行，改写会动到正例本身；是否真有歧义需要 Opus 按场景流程审计后再定 |
| A5 | 不改，待用户决定 | — | 清单本身标为推测；83 条同类 finding 要逐类确认是模型误读还是文本缺陷，需要数据复核，不能凭推测加排除句（加排除句还会降低难度） |
| A6 | 已改（CA v3.1） | `dispatch-policy.md` 规则 24 改为 "Redaction removes credentials at every depth of the value being redacted, which is the value the citing requirement names." | 原句 "the redacted value" 可读成整个事件；新句写明范围由引用它的要求行决定（02:23、spec:12 写的是 auth 字段），与 v1 裁决一致 |

核对：两个 v2 场景物化成功；ARW 的 `reviewer-capability-conformance` 测试在 v1、v2 副本上失败集合完全相同（各 45 通过 / 25 失败，均为 v1 已有）。ARW 零模型 `prepare` 本轮未跑（需要在副本里 `git init`，起草环境不允许），冻结前在 mock 门里补跑。

### 4.2 brief 与评分措辞（b 组）

| 项 | 处理 | 改了什么 | 理由 |
|---|---|---|---|
| B1 | 已改（四份 brief） | 四份 brief 加一段逐字相同的"multi-model-v2 统一口径"：`supported`（含答案键缺陷挂在别处，不再扣第二次）、`unsupported`（通用句贴多处、两缺陷 finding 未讲到的位置、结论与实际行为相反）、`false-positive:clean-N`（含"修法与未提名干净用例相反判 unsupported"及其与 supported 方向相反的理由）、判断不了时的默认选项。`check_briefs --suite v2` 核对四份逐字相同 | v1 四份措辞不一，SR 另有明文；统一写成裁决先例（用户定 10-21）的结论 |
| B2 | 已改（CA brief） | CA 决策树第 3 步：只说"违背 / 未满足"、没写出代码错在哪的 finding 判 `unsupported` | 裁决先例「CA 只说违背」（用户定 10-21）；v1 brief 没写 |
| B3 | 已改（CA brief） | CA 决策树第 1 步：先看挂载行，已满足行按 r8.1 判该行误报，即使讲的是相邻行的真缺陷；点名孪生干净行 02:30 / spec:45（`orderManifestGroups`）与相邻问题 01:38 | v1 池间不一致 25 条；r8.1 规则本身不变，只把判法写进 brief |
| B4 | 已改（CStd brief） | 原第 33 行改为"重复完全在未改动文件里的情形"判 unsupported，另起一句：新代码照搬仓库已有多份的同构实现算本次变更的问题 | 裁决先例「新代码照搬仓库里已有多份的重复实现」（用户定 10-21） |
| B5 | 已改（SR brief） | 在原样引用的 v4 口径节之外新增一条"未选节"推广：把未选节当审查对象或当要求来源的 finding 一律 `unsupported`，只用作比较证据的照常判 | v1 只写了 RM"委托给未选 Interfaces 节"一种；原样引用节不能改，所以单列 |
| B6 | 已改（SR brief） | 新增 APPLICABILITY / EXEMPTION 分工：主张 `result-summary.md` 不得豁免属 APPLICABILITY，主张 `parser-scan.md` 豁免理由空泛属 EXEMPTION，报在另一项下判 `supported` | 裁决者看不到 placement；写明边界而不是给答案键 placement 表（后者泄露答案键结构） |
| B7 | 不改，待用户决定 | — | 给 CA 需求行加显式编号会改动 handoff 和输出契约（行号是被测能力的一部分）；v1 的修复规则（原文能唯一定位就改挂并计格式错误）已覆盖这类错误 |

### 4.3 答案键与锚点（c 组）

| 项 | 处理 | 理由 |
|---|---|---|
| C1 | 不改，待用户决定 | 把 P13 拆成"重复实现"和"写成 class"两个用例是新增答案键用例，要定 k 档、改 `expected.json`，并让 k 登记和格式基准失效，属于改测量设计；v2 不改答案键时，盲裁锚点按 v1 的修正（a06 matched、另加 cstd-9-130）沿用 |

## 5. harness 设置对齐

### 5.1 现状（v1 实际生效值）

| 配置 | Codex 窗口 / 压缩点 | Claude Code 窗口 / 压缩点 | 推理强度 | 输出上限 |
|---|---|---|---|---|
| Strata | 206584 / 150000 | 206584 / 150000（`CLAUDE_CODE_MAX_CONTEXT_TOKENS`、`CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE`） | 三档 thinking 2048 / 4096 / 8192，两边相同 | 三档 8192 / 16384 / 24576，两边相同；guardian 512 / 1024 只在 Codex |
| DeepSeek | 目录 1048576、有效 95%、`auto_compact` 为空，实际不压缩 | 未设窗口，按默认约 162K 压缩 | 按提供方档位映射 | Codex 走目录值；Claude Code `max_tokens` 32000（v1 SR AP 有 7 次模型失误由此触发） |
| OpenAI | 目录 272000、有效 95%、服务端压缩（`responses_compaction_v2`） | 不在 Claude Code 上跑 | 原生 effort | 原生 |
| Anthropic | 不在 Codex 上跑 | 原生窗口；mock 显示默认 `max_tokens` 32000 | 原生 effort | 原生 |

harness 版本：v1 用 Codex 0.163.0、Claude Code 2.1.303；`tools/reviewer/harness_pins.py` 现为 0.164.0 / 2.1.309。按测量规则，v2 开始时换成当时最新版，固定到结束。

### 5.2 对齐方案

| 维度 | 方案 | 保留的差异与理由 |
|---|---|---|
| Strata 窗口 / 压缩点 | 两边维持 206584 / 150000（已对齐） | 无 |
| Strata 推理强度、输出上限 | 维持三档映射（已对齐） | guardian 只在 Codex：Claude Code 没有对应的审批模型调用，属于 harness 结构差异 |
| DeepSeek 窗口 / 压缩点 | 两边设成同一组值。候选：(a) 两边都用 1M、不压缩（Codex 现状，Claude Code 补 `CLAUDE_CODE_MAX_CONTEXT_TOKENS` 与 `BLOCKING_LIMIT_OVERRIDE`）；(b) 两边都用 Strata 的 206584 / 150000；见第 9 节 | 待用户决定。推荐 (a)：DeepSeek 的原生能力就是 1M 窗口，v1 场景单实例输入远低于 1M，(a) 等于两边都不压缩，最简单；(b) 让压缩成为 DeepSeek 两边共同的负担，但测的是被压低的配置 |
| DeepSeek 输出上限 | Claude Code 把 `CLAUDE_CODE_MAX_OUTPUT_TOKENS` 设成与 Codex 目录相同的值（冻结前在 mock 门核对 Codex 实际请求里的 `max_tokens`） | v1 的 32000 上限造成 7 次模型失误，属 harness 设置而非模型能力；另一个 worker 正在改 `src/output_limit.py` 的重试处理，v2 冻结时以其合入后的版本为准，本稿不改它 |
| OpenAI / Anthropic | 各只在一个 harness 上跑，没有跨 harness 对齐问题；用原生窗口、原生 effort 档位 | 保留原生：没有第二个 harness 可比，按提供方默认最能代表日常使用 |
| Role 说明位置 | Claude Code 默认开启 `--role-as-system`，见 5.4 | — |
| 基础提示 | 维持 v1：两份基础提示只给 Strata（D4） | 用户 2026-10-19 决定 |

### 5.3 开跑前核对实际压缩点（零模型）

1. Claude Code：`python3 -m tools.ops.claude_compact_probe` 现在只覆盖 Strata 设置；扩展到 DeepSeek（以及 Anthropic 如需要）的环境变量组合，用假服务器确认触发压缩的输入 token 在配置值 ±100 内。未设 `CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE` 时 Claude Code 回落到"窗口 − 23000"，探针要覆盖这一情形，证明 v2 的设置不会落入回落值。
2. Codex：没有现成探针。在 mock 门里用假服务器回放递增长度的回合，抓取请求，确认 rollout 里压缩事件出现的位置与目录的有效窗口一致；DeepSeek 设为不压缩时，确认到场景最大输入都不出现压缩事件。实现时优先扩展现有的 mock 门（`tools/safety/`），不新建脚本。
3. 正式运行时，每实例的压缩次数由另一个 worker 正在给 `bench_records` 加的逐实例压缩计数记录；报告按配置汇总压缩次数和最大请求输入，核对与 5.2 的设置相符。本稿不改 `bench_records`。
4. 输出上限：mock 门抓取两边请求里的 `max_tokens` / `max_output_tokens`，与 5.2 表一致才放行。

### 5.4 Role 说明

`tools.ops.claude_scenario --role-as-system`（默认关）把 Role 说明经 `--append-system-prompt` 放进系统提示；默认关时 Role 在用户提示里。Codex 把 Role 放进 developer instructions。

建议 v2 在 Claude Code 上默认开启：Role 在两边都处于高于用户消息的指令层，位置对齐；v2 本来就是新版本，不需要与 v1 保持可比。风险：真实 ARW Role 的长度在命令行上未实测（mock 只核对过请求形状），冻结前在 mock 门里用真实 Role 跑一次，确认系统提示完整到达假服务器。这是默认参数改值，冻结时交独立 agent 审查，并列入第 9 节待用户决定。

## 6. 评分设计问题：SR 缺检查得负分

现行 r8.4：反例只有所属检查存在时才算通过。Spec Readiness 报告缺了某个检查，该检查下的反例全部记失败，实例可以得负分；而模型失误（没有报告）得 0（用户 2026-10-21，理由是负分表示浪费审核时间）。于是"交了一份缺检查的报告"可能低于"什么都没交"。评分口径由用户定，下面只给候选，不决定。

| 方案 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| A 维持 r8.4 | 缺检查的反例记失败 | 不改规则；缺检查确实是报告不完整 | 与"负分 = 浪费审核时间"的理由矛盾：缺失的检查没有内容可读，不浪费时间；部分完成的报告可能低于没有报告 |
| B 缺检查的反例记中性 | 检查缺失时其反例既不通过也不失败，不进分子；正例照常记漏报（得 0）。分母不变 | 与"没有报告得 0"的理由一致：缺失的部分按"没有报告"处理，只损失正例分；全检查缺失时等于什么都不报，得 0 | 缺检查不再受罚：一个只报少数检查、正例命中率高的报告分数偏好；需要另记缺检查数供报告参考 |
| C 缺检查按整体罚 | 反例按 B 处理，同时把缺检查比例计入一项整体扣减（与早退暂停同类，按"整体罚分只扣一次"取最大） | 保留对不完整报告的惩罚，又不会因为缺检查翻成负分 | 新增罚项和系数要定（例如每缺一项扣多少），系数缺少依据；规则更复杂 |

建议 B：它直接沿用用户 2026-10-21 定"没有报告得 0"时的理由（负分只用于浪费审核时间的内容），逻辑一致；C 的系数目前没有依据。待用户决定。

## 7. 其他候选变更（只列出，未实施）

1. 把 B2"只说违背判 unsupported"推广到 CS、CStd、SR 的 brief（v1 先例只针对 CA）。
2. 新场景版本（CS v5.1、CA v3.1）是否要走完整场景流程（Opus 审计、参考基线、10 次组内 SD），还是因为只改措辞、答案键不变而走简化流程（Opus 审计改动行 + mock 门）。
3. 格式基准：答案键不变时按 SHA 自动沿用 v1 基准；措辞改动理论上不影响格式错误率，是否需要重标。
4. Codex 臂是否加私有 scratch 补丁（v1 排除）；另一个 worker 在验证，结论出来后再定。
5. 是否顺带处理 A3、A4、A5、B7、C1（第 4 节，均为待用户决定）。

## 8. 实现待办（冻结前）

- 工具链里写死的 v1 场景名（`bench_records` 的 `SCENARIOS`、`benchmark_export`、`blind_pool`）要改成按套件配置，v2 的场景名才能进统计和导出。`bench_records` 正由另一个 worker 修改，等它合入后再改。
- `tools/tuning/arw_dimension.py` 已为 CA v3.1 登记场景注释；CS v5.1 沿用默认。
- judgment 绑定：答案键 SHA 不变，现有登记自动适用，无需新增。
- ARW 零模型 `prepare` 与 mock 门：两个新场景各跑一次（见 4.1）。
- harness 换最新版后重跑零模型 mock 门、`claude_compact_probe`、Codex 压缩点检查（5.3）和安全验收。
- 第 6 节如改评分，计分器实现、单测和 README「现行决定」同步更新。
- 冻结时按 v1 §14 的做法记录全部 SHA 绑定。

## 9. 待用户决定

| # | 事项 | 建议 | 理由 |
|---|---|---|---|
| 1 | 第 6 节 SR 缺检查得负分的评分口径 | B | 与"没有报告得 0"的既有理由一致 |
| 2 | DeepSeek 两个 harness 的窗口 / 压缩点 | (a) 两边 1M、不压缩 | 原生能力、两边都不压缩、最简单 |
| 3 | Claude Code 默认开启 `--role-as-system` | 开启 | 与 Codex 的指令层对齐；冻结前用真实 Role 核对长度 |
| 4 | A3 规则 26/27 是否改写 | 不改 | 不是歧义，改写会降低设计难度 |
| 5 | A4 SR `promotion-recovery.md:65/77/85` | 先 Opus 审计再定 | 涉及正例证据行 |
| 6 | A5 SR 常见误报是否加排除句 | 先数据复核再定 | 清单本身是推测，加排除句会降难度 |
| 7 | B7 CA 需求行显式编号 | 不改 | 改动输出契约；修复规则已覆盖 |
| 8 | C1 拆分 P13 | 交用户定档（倾向 0.25 档）并经独立审查 | 新增答案键用例属改测量设计 |
| 9 | B2 推广到全部场景（第 7 节 1） | 推广 | 同一判断标准不应只适用于一个场景 |
| 10 | 新场景版本的场景流程（第 7 节 2） | 简化流程：Opus 审计改动行 + mock 门 | 答案键与行号不变，只改措辞 |
| 11 | harness 版本 | 开始时取最新版（不低于 0.164.0 / 2.1.309） | 测量规则（用户 2026-10-23） |
