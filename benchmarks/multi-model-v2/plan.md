# 多模型 benchmark v2 运行计划（草案，未冻结）

起草 2026-10-24。本稿只做题目、brief 与设置的准备，没有运行任何模型，也没有领取租约。冻结前要按 AGENTS.md 硬约束 1 交独立 agent 审查，并由用户决定第 9 节列出的事项。v1 的目录、冻结件和 SHA 绑定一律不改，v2 的全部文件都在本目录。

## 1. 目的

所有参与的模型（Strata、OpenAI、DeepSeek、Anthropic 等）在各自的 harness 上作为 reviewer 被测量，地位相同；不以 Strata 为中心，不写成「Strata 与其他模型对照」（用户 2026-10-24）。benchmark 不做组间比较，只输出数据；比较由看结果页面的人自己做（用户 2026-10-25，第 10 节第 13 行）。v2 相对 v1 的改动只有三类：

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
| `scenarios/<版本>.json` | 四个场景的 v2 运行计划（`arw-dimension-v1`，草案）：评分版本、Codex harness 补丁、Role 位置、DeepSeek 的 Claude Code 窗口与上限 |
| `arw-patches/scoring-r8.5.patch` | 评分 r8.5，叠在 v1 的 `scoring-k.patch`（r8.4）之上，只由 v2 计划选用（第 6.1 节） |

未改动的场景（Code Standards v5.1）直接用 v1 的冻结清单，不复制。Spec Readiness 因 A4 出了 v4.4，又因 A5（[F1 审计](audit-f1-2026-10-25.md) M2）出了 v4.5，与 CS、CA 一样建 v2 清单和补丁；v4.5 的清单 = v1 清单 + `spec-readiness-v4.4.patch` + `spec-readiness-v4.5.patch`，v4.4 的清单已由 v4.5 取代。

## 3. 场景的引用方式

v1 的场景是 ARW 源码快照 + 清单中的补丁序列（`tools.reviewer.freeze_arw_source` 物化）；计分器的 k 档登记、格式基准、judgment 绑定都按 `expected.json` 的 SHA 查找，brief 引用行号。

选"引用加补丁"，不复制整套场景：

- v2 清单 = v1 清单原样 + 末尾一个 v2 补丁；`snapshot.file` 改为指回 v1 的快照（`../../reviewer-suite-v1/source-snapshots/current/…`），所以 v1 的补丁路径照常解析，快照和 v1 补丁不复制。
- v2 补丁只改措辞，每个改动文件的行数不变，`expected.json` 逐字节不变。因此 k 档登记、格式基准、judgment 绑定和 brief 中的行号引用全部继续有效，计分器不用改。
- 单测 `tests/test_multi_model_v2.py` 核对：v2 清单前缀与 v1 清单相同、v2 补丁（SR 两个）只改清单声明的文件、行数不变、答案键不变。

复制整套场景的代价是两份 tarball 和十几个补丁要同步维护，而且 SHA 绑定要重新登记，没有好处。

## 4. 歧义题目

逐项对应[歧义清单](../reviewer-suite-v1/next-version-ambiguities.md)。"已改"项的场景改动由 `scenarios/*.patch` 实现，brief 改动在 `briefs/`；brief 的机械核对用 `python3 -m tools.reviewer.check_briefs --suite v2`。

### 4.1 场景原文（a 组）

| 项 | 处理 | 改了什么 | 理由 |
|---|---|---|---|
| A1 | 已改（CS v5.1） | `governing-spec.md:160` 拆成两句："Catalog locale keys are trimmed and lowercased; a blank catalog key stays blank. A member's `locale` is trimmed and lowercased, a missing or blank member locale being `en`." CS brief 补一条说明这一行的读法 | 原句让"空白目录键归 `en`"成为可行读法；新句与代码（空白目录键保留为空）和 v1 裁决先例（不归 `en`）一致，答案键不变 |
| A2 | 已改（CA v3.1） | issue 01 第 30 行（base 和 candidate 两份）"otherwise returns an error result" 改为 "otherwise returns a result whose `ok` is `false`" | v1 两种读法下代码行为相同，可执行检查定不了；新句按答案键的主读法写明形状 |
| A3 | 不改（第 9 节第 4 项） | — | 经核对不是歧义：政策文档头写明同节后一条覆盖前一条。改写规则 26 会去掉场景有意设计的"规则覆盖"难点，属于改场景难度，不是消歧 |
| A4 | 已改（SR v4.4，第 9 节第 5 项） | `promotion-recovery.md:65` 的"不从 caller 自报替代"改为"不由 promote 的 caller 自报替代"，`:85` 两处"caller 自报"改为"promote caller 自报"；RM 与 AP 两份 view 的该文件这两行相同，一并改。SR brief 的依据行注明 v4.4 只改这两行 | 独立审查核对：`:85` 不是任何用例的证据行，`:65` 作证据行时依赖的事实与"caller"指谁无关，答案键也没有针对这一读法的干净用例，所以改措辞不动正例；"caller"原有两种站得住的读法，参考模型 Opus-low 也误读。行数、答案键不变 |
| A5 | 不加排除句；「binding 失配结果」子类已改（SR v4.5，第 9 节第 6 项，[F1 审计](audit-f1-2026-10-25.md) M2） | `promotion-runtime.md:11` 的"Promotion 信任此前置条件, 不增加 public 参数" 改为 "…不增加 public 参数或失败分支"，与 `:45` 对 retentionDays 的写法一致；RM 与 AP 两份 view 的该文件这一行相同，一并改。SR brief 加一条 binding 失配的判法 | 原清单标为推测，83 条同类 finding 不凭推测加排除句（会降低难度）。F1 审计核对「binding 失配结果」子类：文本证据偏向文本缺陷（`:45` 对同构的内部参数写明不增加失败分支，`:11` 没写；INTERFACES 正例 5 把同构的结果缺失算缺陷），而清单外的受支持缺陷与"夹具不得含清单外受支持缺陷"冲突。改 `:11` 使 binding 成为没有失败分支的内部前置条件，与 `:97` 一致。行数、答案键不变，ARW conformance 与 v4.4 相同 |
| A6 | 已改（CA v3.1） | `dispatch-policy.md` 规则 24 改为 "Redaction removes credentials at every depth of the value being redacted, which is the value the citing requirement names." | 原句 "the redacted value" 可读成整个事件；新句写明范围由引用它的要求行决定（02:23、spec:12 写的是 auth 字段），与 v1 裁决一致 |

核对：三个 v2 场景物化成功；ARW 的 `reviewer-capability-conformance` 测试在 v1、v2 副本上失败集合完全相同（各 45 通过 / 25 失败，均为 v1 已有；SR v4.4 于 10-24 补测，结果相同；SR v4.5 于 10-25 在 r8.4、r8.5 两种副本上各补测，45 / 25，失败名单与 v4.4 相同）。ARW 零模型 `prepare` 已于 10-24 用四个 v2 计划跑通（见第 11 节 F4）。

### 4.2 brief 与评分措辞（b 组）

| 项 | 处理 | 改了什么 | 理由 |
|---|---|---|---|
| B1 | 已改（四份 brief） | 四份 brief 加一段逐字相同的"multi-model-v2 统一口径"：`supported`（含答案键缺陷挂在别处，不再扣第二次）、`unsupported`（通用句贴多处、两缺陷 finding 未讲到的位置、结论与实际行为相反）、`false-positive:clean-N`（含"修法与未提名干净用例相反判 unsupported"及其与 supported 方向相反的理由）、判断不了时的默认选项。第 9 节第 12 项补全 [rulings.md](../reviewer-suite-v1/rulings.md):14 第 (2)–(4) 款：个别措辞写反、机制自相矛盾但复现属实、把答案键缺陷背后的错误意图当成正确要求，三种都判 `supported`（后两种不对应该问题用例）；第 8 项加 `matched` 一条：一条 finding 写出多个具体缺陷时，其中一个与期望句是同一问题即 matched，其余缺陷不影响该关联（rulings.md:16）。`check_briefs --suite v2` 核对四份逐字相同，并核对这些款项都在 | v1 四份措辞不一，SR 另有明文；统一写成裁决先例（用户定 10-21）的结论。10-25 按 [F1 审计](audit-f1-2026-10-25.md) 收回到 v1 和 rulings 的原意：`false-positive:clean-N` 款改以 finding 主张的问题为判据（主张的问题就是未提名干净用例的成立内容才判 unsupported，问题属实只是修法欠妥的按问题本身判，M5）；两缺陷 finding 没讲到的位置补上 rulings.md:16 的"不适用挂在别的位置"，模板句与照贴副本的关联候选判 not-matched（S2）；第 (2) 款写明按所讲缺陷照常判（M4，原裁决 ds-ca-4-149 判 supported 是因为所讲缺陷不是该行问题用例） |
| B2 | 已改（CA brief） | CA 决策树第 3 步：只说"违背 / 未满足"、没写出代码错在哪的 finding 判 `unsupported` | 裁决先例「CA 只说违背」（用户定 10-21）；v1 brief 没写 |
| B3 | 已改（CA brief） | CA 决策树第 1 步：先看挂载行，已满足行按 r8.1 判该行误报，即使讲的是相邻行的真缺陷；点名孪生干净行 02:30 / spec:45（`orderManifestGroups`）与相邻问题 01:38 | v1 池间不一致 25 条；r8.1 规则本身不变，只把判法写进 brief |
| B4 | 已改（CStd brief） | 原第 33 行改为"重复完全在未改动文件里的情形"判 unsupported，另起一句：新代码照搬仓库已有多份的同构实现算本次变更的问题 | 裁决先例「新代码照搬仓库里已有多份的重复实现」（用户定 10-21） |
| B5 | 已改（SR brief；10-25 按 [F1 审计](audit-f1-2026-10-25.md) M1 收窄） | 在原样引用的 v4 口径节之外新增一条"未选节"推广：主张选定章节因委托或引用未选节而不完整的，或把未选节本身当审查对象的 finding，一律 `unsupported`；例外：选定章节经引用采用的未选节合同可以用来核对选定章节之间的冲突，照常判 | v1 只写了 RM"委托给未选 Interfaces 节"一种；原样引用节不能改，所以单列。初稿把"依据未选节的内容"也一律判 unsupported，与 RM REQUIREMENTS 正例（证据含经引用采用的 Interfaces 字段）矛盾，收回到 v1 m1 的窄义 |
| B6 | 已改（SR brief） | 新增 APPLICABILITY / EXEMPTION 分工：主张 `result-summary.md` 不得豁免属 APPLICABILITY，主张 `parser-scan.md` 豁免理由空泛属 EXEMPTION，报在另一项下判 `supported` | 裁决者看不到 placement；写明边界而不是给答案键 placement 表（后者泄露答案键结构） |
| B7 | 不改（第 9 节第 7 项） | — | 给 CA 需求行加显式编号会改动 handoff 和输出契约（行号是被测能力的一部分）；v1 的修复规则（原文能唯一定位就改挂并计格式错误）已覆盖这类错误 |

### 4.3 答案键与锚点（c 组）

| 项 | 处理 | 理由 |
|---|---|---|
| C1 | 不拆 P13，改 brief（第 9 节第 8 项） | 把 P13 拆成"重复实现"和"写成 class"两个用例是新增答案键用例，要定 k 档、改 `expected.json`，并让 k 登记和格式基准失效，属于改测量设计；v2 不改答案键时，盲裁锚点按 v1 的修正（a06 matched、另加 cstd-9-130）沿用 |

## 5. harness 设置对齐

### 5.1 现状（v1 实际生效值）

| 配置 | Codex 窗口 / 压缩点 | Claude Code 窗口 / 压缩点 | 推理强度 | 输出上限 |
|---|---|---|---|---|
| Strata | 206584 / 150000 | 206584 / 150000（`CLAUDE_CODE_MAX_CONTEXT_TOKENS`、`CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE`） | 三档 thinking 2048 / 4096 / 8192，两边相同 | 三档 8192 / 16384 / 24576，两边相同；guardian 512 / 1024 只在 Codex |
| DeepSeek | 目录 1048576、有效 95%、`auto_compact` 为空，实际不压缩 | 未设窗口，按默认约 162K 压缩 | 按提供方档位映射 | Codex 走目录值；Claude Code `max_tokens` 32000（v1 SR AP 有 7 次模型失误由此触发） |
| OpenAI | 目录 272000、有效 95%、服务端压缩（`responses_compaction_v2`） | 不在 Claude Code 上跑 | 原生 effort | 原生 |
| Anthropic | 不在 Codex 上跑 | 原生窗口；mock 显示默认 `max_tokens` 32000 | 原生 effort | 原生 |

harness 版本：v1 用 Codex 0.163.0、Claude Code 2.1.303；`tools/reviewer/harness_pins.py` 现为 0.164.0 / 2.1.310（2026-10-25 F12 换版，Codex 仍是最新版 0.164.0）。按测量规则，v2 开始时换成当时最新版，固定到结束。

### 5.2 对齐方案

| 维度 | 方案 | 保留的差异与理由 |
|---|---|---|
| Strata 窗口 / 压缩点 | 两边维持 206584 / 150000（已对齐） | 无 |
| Strata 推理强度、输出上限 | 维持三档映射（已对齐） | guardian 只在 Codex：Claude Code 没有对应的审批模型调用，属于 harness 结构差异 |
| DeepSeek 窗口 / 压缩点 | **已决定（第 9 节第 2 项）：两边都用 1M、不压缩。** Codex 沿用目录 1048576（`auto_compact` 为空）；Claude Code 设 `CLAUDE_CODE_MAX_CONTEXT_TOKENS=1048576`，`CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE` 的值由压缩点探针定（第 11 节 F6），保证到场景最大输入都不压缩 | 无。场景单实例输入远低于 1M，两边等于都不压缩 |
| DeepSeek 输出上限 | Claude Code 把 `CLAUDE_CODE_MAX_OUTPUT_TOKENS` 设成与 Codex 实际请求相同的值；端点上限和 Codex 请求里的值冻结前核实（第 11 节 F5、F8） | v1 的 32000 上限造成 7 次模型失误，属 harness 设置而非模型能力；`src/output_limit.py` 的重试改动冻结时以合入后的版本为准，本稿不改它 |

实现：四个 v2 计划的 `fixed_conditions.deepseek_claude_environment` 写着这三个变量，`claude_scenario --backend deepseek` 读取后经 `claude_headless.deepseek_environment(limits=…)` 交给 Claude Code，并记进 `binding.json` 的 `deepseek_limits`。冻结前值为 `null` 的两项让 DeepSeek 的 Claude Code 运行直接报错，不会用默认值误跑。
| OpenAI / Anthropic | 各只在一个 harness 上跑，没有跨 harness 对齐问题；用原生窗口、原生 effort 档位 | 保留原生：没有第二个 harness 可比，按提供方默认最能代表日常使用 |
| Role 说明位置 | Claude Code 默认开启 `--role-as-system`，见 5.4 | — |
| 基础提示 | 维持 v1：两份基础提示只给 Strata（D4） | 用户 2026-10-19 决定 |

### 5.3 开跑前核对实际压缩点（零模型）

1. Claude Code：`python3 -m tools.ops.claude_compact_probe` 现在只覆盖 Strata 设置；扩展到 DeepSeek（以及 Anthropic 如需要）的环境变量组合，用假服务器确认触发压缩的输入 token 在配置值 ±100 内。未设 `CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE` 时 Claude Code 回落到"窗口 − 23000"，探针要覆盖这一情形，证明 v2 的设置不会落入回落值。
2. Codex：没有现成探针。在 mock 门里用假服务器回放递增长度的回合，抓取请求，确认 rollout 里压缩事件出现的位置与目录的有效窗口一致；DeepSeek 设为不压缩时，确认到场景最大输入都不出现压缩事件。实现时优先扩展现有的 mock 门（`tools/safety/`），不新建脚本。
3. 正式运行时，每实例的压缩次数由另一个 worker 正在给 `bench_records` 加的逐实例压缩计数记录；报告按配置汇总压缩次数和最大请求输入，核对与 5.2 的设置相符。本稿不改 `bench_records`。
4. 输出上限：mock 门抓取两边请求里的 `max_tokens` / `max_output_tokens`，与 5.2 表一致才放行。

### 5.4 Role 说明

`tools.reviewer.claude_scenario` 可把 Role 说明经 `--append-system-prompt` 放进系统提示，否则 Role 在用户提示里。Codex 把 Role 放进 developer instructions。

**已决定开启（第 9 节第 3 项），并已实现为 v2 的默认**：四个 v2 计划写 `fixed_conditions.claude_role_as_system: true`，`claude_scenario` 以计划为准，不传 `--role-as-system` 也开启；命令行与计划矛盾时报错。v1 计划没有这个字段，行为不变。零模型 dry-run（SR v4.4，两段）确认 Role 进系统提示：系统提示 36,656 字节（sha256 `01feceab…`），在 Linux 单个命令行参数上限 131,072 字节以内；真实 Role 经假服务器完整到达的核对见第 11 节 F9。

原建议：Role 在两边都处于高于用户消息的指令层，位置对齐；v2 本来就是新版本，不需要与 v1 保持可比。风险：真实 ARW Role 的长度在命令行上未实测（mock 只核对过请求形状），冻结前在 mock 门里用真实 Role 跑一次，确认系统提示完整到达假服务器。这是默认参数改值，冻结时交独立 agent 审查，并列入第 9 节待用户决定。

## 6. 评分设计问题：SR 缺检查得负分

现行 r8.4：反例只有所属检查存在时才算通过。Spec Readiness 报告缺了某个检查，该检查下的反例全部记失败，实例可以得负分；而模型失误（没有报告）得 0（用户 2026-10-21，理由是负分表示浪费审核时间）。于是"交了一份缺检查的报告"可能低于"什么都没交"。评分口径由用户定，下面只给候选，不决定。

| 方案 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| A 维持 r8.4 | 缺检查的反例记失败 | 不改规则；缺检查确实是报告不完整 | 与"负分 = 浪费审核时间"的理由矛盾：缺失的检查没有内容可读，不浪费时间；部分完成的报告可能低于没有报告 |
| B 缺检查的反例记中性 | 检查缺失时其反例既不通过也不失败，不进分子；正例照常记漏报（得 0）。分母不变 | 与"没有报告得 0"的理由一致：缺失的部分按"没有报告"处理，只损失正例分；全检查缺失时等于什么都不报，得 0 | 缺检查不再受罚：一个只报少数检查、正例命中率高的报告分数偏好；需要另记缺检查数供报告参考 |
| C 缺检查按整体罚 | 反例按 B 处理，同时把缺检查比例计入一项整体扣减（与早退暂停同类，按"整体罚分只扣一次"取最大） | 保留对不完整报告的惩罚，又不会因为缺检查翻成负分 | 新增罚项和系数要定（例如每缺一项扣多少），系数缺少依据；规则更复杂 |

建议 B：它直接沿用用户 2026-10-21 定"没有报告得 0"时的理由（负分只用于浪费审核时间的内容），逻辑一致；C 的系数目前没有依据。已决定 B（第 9 节第 1 项）。

### 6.1 r8.5 的实现

- 补丁 `arw-patches/scoring-r8.5.patch` 叠在 `scoring-k.patch`（r8.4）之上。`freeze_arw_source --scoring r8.5`（`upgrade_scoring`）按成员 SHA 应用并核对；不传版本时保持 r8.4，v1 的计分路径和结果不变。v2 计划写 `fixed_conditions.scoring: "r8.5"`，`arw_dimension.prepare` 据此物化；`bench_score` 按计划核对计分输出与版本相符（r8.5 必须带缺检查数，r8.4 必须不带），并把 `scoring_version` 写进结果。
- 规则：检查缺失时，其下反例（含 noOther）记中性，失败权重为 0，不进 `kFailedCleanWeight`；分母 Σk 不变；该检查的正例照常记漏报。计分输出新增 `missingChecks`（缺失的检查数）和 `neutralCleanCases`（记中性的反例数），SR 两个子场景相加；`bench_score` 逐实例写出。
- 第 9.2 节两点：越过停止点被忽略的检查本来就不进 RM 的答案键，不会算成缺检查；SR 一个子场景有报告、另一个是模型失误时，沿用现有实现，失误的子场景按 `zeroCapabilityScore`（正例全记 0、反例不失败）与另一个子场景合并，缺检查数只来自有报告的子场景。
- **合并用例一侧检查缺失**（2026-10-25 补全定义，独立审查后 Main 决定，待用户复核，[审查](review-2026-10-25.md)）：存在一侧照常计分。依据是现有规则的组合：r8.5 下缺失一侧的干净用例失败权重为 0，r8.2 合并单位取两侧较差者，所以合并单位的失败权重就是存在一侧的；问题用例一侧缺失记漏报，r8.2 取较小值，合并单位得 0。已实现（2026-10-25）：`scoring-r8.5.patch` 去掉了报错，`neutralCleanCases` 按合并单位计，只在两侧都缺失时计为中性；`tests/test_scoring_r85.py` 覆盖单侧缺失时存在一侧不误报（失败权重 0）和误报（失败权重 0.25）、两侧都缺失、r8.4 对照。ARW 一致性测试 r8.4 与 r8.5 都是 45 通过 / 25 失败，通过与失败的名单相同。现有场景不会触发。
- 零模型核对：SR v4.4 的 r8.4 副本与 r8.5 副本上，ARW `reviewer-capability-conformance` 都是 45 通过 / 25 失败，失败的测试相同；去掉新增的两个计数后，失败输出只差随机生成的实例 ID，`missingChecks` 全为 0。

## 7. 其他候选变更（只列出，未实施）

1. 把 B2"只说违背判 unsupported"推广到 CS、CStd、SR 的 brief（v1 先例只针对 CA）。已按第 9 节第 9 项落实。
2. 新场景版本（CS v5.1、CA v3.1，以及后来的 SR v4.4、v4.5）是否要走完整场景流程（Opus 审计、参考基线、10 次组内 SD），还是因为只改措辞、答案键不变而走简化流程（Opus 审计改动行 + mock 门）。
3. 格式基准：答案键不变时按 SHA 自动沿用 v1 基准；措辞改动理论上不影响格式错误率，是否需要重标。
4. Codex 臂是否加私有 scratch 补丁（v1 排除）。已决定启用（第 9.1 节第 13 项），见第 10 节。
5. 是否顺带处理 A3、A4、A5、B7、C1（第 4 节）。已在第 9 节决定：A4 改，其余不改。

## 8. 实现待办（冻结前）

- [x] 套件化（10-24）：新增 `tools/reviewer/bench_suite.py`（v1、v2 两个套件的场景、计划、brief、锚点、计分目录、模型失误表）；`bench_records`、`bench_score`、`blind_pool` 加 `--suite`，默认 v1，v1 的输出不变。v2 的 `bench_records` 运行目录布局（`LAYOUTS['v2']`）开跑时填。
- [~] `benchmark_summary --suite v2`、`benchmark_export` 的 v2 路径（2026-10-25，用户决定不做组间比较）：组内统计和逐实例表复用 v1 代码，`comparisons` 为空，summary.json 没有 `alpha`、`holm_family_size`，markdown 没有比较表，export 没有 `comparisonDesign`；v1 路径不变，合成数据单测覆盖三点（组内与 v1 同口径、无比较字段、v1 仍 25 个）。仍待：配置表沿用 v1 的 27 个配置编号（v2 的配置集相同时可直接用），场景元数据（`benchmark_export.SCENARIOS`）和 v2 的公开文件还是 v1 内容，等 v2 运行目录布局和场景版本确定后改（F11）。
- [x] `format_penalty` 按套件取登记表（2026-10-25，F2）：`REGISTRIES = {v1, v2}`，v2 用 `benchmarks/multi-model-v2/format-baseline.json`（F3 重标时创建）；v2 登记里答案键不变的场景可写 `{"inheritsFrom": "v1"}`，不在 v2 登记里的键报错，不静默回落到 v1。v1 行为不变。
- `tools/tuning/arw_dimension.py` 已为 CA v3.1 登记场景注释；CS v5.1、SR v4.5 沿用默认。
- judgment 绑定：答案键 SHA 不变，现有登记自动适用，无需新增。
- [x] ARW 零模型 `prepare` 与 mock 门（10-24，第 11 节 F4）。
- [x] 第 6 节评分改动：r8.5 已实现并有单测（第 6.1 节）；README「现行决定」在冻结时登记。
- 冻结时按 v1 §14 的做法记录全部 SHA 绑定（第 11 节 F16）。

## 9. 决定（2026-10-24，待用户复核）

用户 30 分钟没有答复，按 AGENTS.md 硬约束 1，先请独立审查（Opus high，只读）给意见，再由 Main 综合决定。审查意见全文见 [review-2026-10-24.md](review-2026-10-24.md)。用户的答复一律优先。

| # | 事项 | 起草者 | 独立审查 | 决定 |
|---|---|---|---|---|
| 1 | SR 缺检查得负分 | B | B，另加两个条件 | **B**，记为 r8.5，只用于 v2（v1 重算不变）；逐实例记缺检查数；分母 Σk 不变 |
| 2 | DeepSeek 窗口 | 两边都用 1M | 同意；冻结前核实端点上限 | **两边都用 1M、不压缩**；冻结前核实 Anthropic 格式端点的上下文和输出上限，并从 v1 记录确认 >200K 请求能被接受 |
| 3 | `--role-as-system` | 开启 | 开启 | **开启**；mock 里用真实 Role 跑一次，核对追加顺序并绑定系统提示 SHA |
| 4 | A3 | 不改 | 不改 | **不改** |
| 5 | A4 | 先 Opus 审计 | v2 就改，只改措辞 | **v2 就改**：`:65` 改为"不由 promote 的 caller 自报替代"，`:85` 两处改为"promote caller 自报"；行数不变，纳入第 10 项审计。**已落实**（SR v4.4，见 4.1）；第 10 项审计未做 |
| 6 | A5 | 先数据复核 | 不加排除句；只核对 binding 失配子类 | **不加排除句**；"binding 失配结果"子类交第 10 项审计判定，要在 brief 冻结前出结论。**结论（2026-10-25，[F1 审计](audit-f1-2026-10-25.md) M2，Main 采用审计的优先方案，待用户复核）**：这类 finding 指向的是文本缺陷，改场景消除：SR v4.5 把 `promotion-runtime.md:11` 改为"Promotion 信任此前置条件, 不增加 public 参数或失败分支"（RM、AP 两份，行数、答案键不变），并写进 SR brief。改后按路径：**P1**（inputPath 与已绑定路径不一致，`:41` 只定义 missing、non-string、empty）和 **P2**（artifact.requestId 与 request.requestId 不一致，`:51`、architecture `05-validation-report.md:29` 的诊断没有 binding）：binding 是 Readiness 确认、Promotion 信任的内部前置条件，明文没有失败分支，主张缺失败结果或诊断的 finding 判 `unsupported`；**P3**（Promotion 在 `prt:27` 再次验证 request）：指出与 Readiness 重复校验的，按 MODULES 正例 0 照常判（报在别的检查下按"挂在别的位置"判 `supported`）；要求补失配结果、让再次验证做得成的，按 rulings.md:14 第 (4) 款判 `supported`、不对应该问题用例；**P4**（RM：`prt:11` 是选定节，Failure Results 是未选节）：`:11` 本身写明没有失败分支，主张选定 Requirements 缺 binding 失败结果、或因委托给未选 Failure Results 而不完整的，判 `unsupported`（与收窄后的"未选节"条一致）；P5（测试侧）原本已由 `prt:97`、issue `01:61` 排除，不变 |
| 7 | B7 | 不改 | 不改 | **不改** |
| 8 | C1 | 拆分，交用户定档 | 不拆；改 brief | **不拆 P13**；统一口径加一句"一条 finding 写出多个具体缺陷时，其中一个与期望句是同一问题即 matched"（依据 rulings.md:16）。**已落实**：统一口径加 `matched` 一条；CS、CStd、SR brief 中"同一对象、同一错误含义才算 matched；同一 X 下的另一个问题不算"一句改为"只讲同一 X 下另一个问题的 finding 不算"，并注明 finding 另写的缺陷不影响已对上的那一个 |
| 9 | B2 推广 | 推广 | 有条件推广 | **推广**，只用于发现候选的 unsupported 判定，按各场景 Role 原文措辞写。**已落实**：CS 按 Role:31（证明失败情境）、CStd 按 Role:48（设计异味名称只提供方向，要证明维护负担或错误后果）、SR 按 findings.md:15（解释具体缺陷、缺失内容或冲突合同；缺失类写明缺了什么即可）各加一条，`check_briefs` 核对引文在所引行 |
| 10 | 场景流程 | 简化 | 简化，补三点 | **简化流程**，并做到三点：审计范围扩大到改动行、引用这些行的全部答案键用例、第 5、6 项改动；CS v5.1、CA v3.1 重跑 Haiku-high ×5 格式基准；ARW 零模型 prepare 和 mock 门跑通 |
| 11 | harness 版本 | 取最新版 | 同意（测量规则本就要求） | **开始时两个 harness 同一时刻取最新版**，写进 harness_pins，换版后重跑 mock 门和 compact probe |

Main 采纳审查的 5、6、8：审查核对了答案键的证据行和先例，起草者的顾虑在原文里不成立。

### 9.1 审查新提出的事项（用户 2026-10-24 已定）

| # | 事项 | 用户决定 |
|---|---|---|
| 12 | B1 统一口径：「修法与未提名干净用例相反判 unsupported」从只用于 CStd 推广到四个场景；口径段只写了 rulings.md:14 第 (1) 款 | 推广；同时补全第 (2)–(4) 款（措辞个别写反、复现属实、意图错误判 supported），避免偏向判 unsupported。**已落实**（见 4.2 B1） |
| 13 | v2 的 Codex 各臂启用私有 scratch（[验证报告](../../reports/v0.2.4/scratch-verify.md)） | 启用；报告里列为与 v1 的条件差异 |
| 14 | 运行设计（配置矩阵、每格 n、预算、停止点） | 默认沿用 v1，改动须有充分理由，例如 v2 改了规则 A，而规则 A 影响规则 B，所以 B 也要改；逐项写明改动和理由 |

第 1–11 项用户看过完整说明，没有提出异议，按第 9 节执行。

### 9.2 冻结前补充检查（审查提出，Main 采纳）

- 决定库和"盲裁只裁有变化的部分"的沿用逻辑按 brief SHA 或套件隔离，不把 v1 决定自动套到 v2；v1 锚点在 v2 brief 下逐个复核，答案变了的锚点要替换。**已实现**：`blind_pool`、`bench_score` 拒绝其他套件的决定库；v2 的每条决定记下做出它时的 brief sha256，brief 改过的决定不沿用，`split` 在 brief 变化后拒收旧 key。锚点复核见第 11 节 F10。
- SR 子场景一个有报告、另一个是模型失误时，r8.5 下的合并计分写明；"越过停止点"被忽略的检查不按缺检查处理。**已写明**（第 6.1 节）。
- v2 报告的混杂项列出：harness 版本不同于 v1；Claude Code 时限提醒从 10-23 起改为高优先级送达。

## 10. 运行设计（默认沿用 v1，逐项列出）

按测量规则「新版沿用上一版」和第 9.1 节第 14 项：下表逐项列出 v1 的运行设计（出处为 v1 计划的节号）。没有写理由的项原样沿用；改动的项写明「因为改了 A，A 影响 B，所以改 B」。harness 换最新版（第 9 节第 11 项）是测量规则本身的要求，不算设计改动。

| # | 项 | v1 做法（出处） | v2 |
|---|---|---|---|
| 1 | 配置矩阵 | 27 个配置：OpenAI 6、DeepSeek 两个 harness 各 low / high / max、Strata 两个 harness 各三档、Anthropic 9（§2，§14.4） | 沿用 |
| 2 | 场景与每格次数 | 4 个场景 × 每格 5 个有效实例，共 540；SR 每实例 RM、AP 两个根线程（§2） | 沿用；场景换成 CS v5.1、CStd v5.1、CA v3.1、SR v4.5 |
| 3 | 空闲加测 | Strata 在 GPU 空闲时加测到 10，每格尝试上限 13；加测与前 5 个同等进主统计，前 5 个另作一致性行（§3 排程，§14.1 10-21） | 沿用 |
| 4 | 尝试与重跑 | 每格最多尝试 8 次，无效实例排到队尾重跑；harness 故障、撞额度、用户收回登录不计尝试（§14.1、§14.3） | 沿用 |
| 5 | 排程 | 同一场景内配置按块交替、每轮反转；Strata 同一配置连跑，换配置冷加载并预热，每批从冷加载开始（§3 排程） | 沿用 |
| 6 | 场景顺序 | CA → CS → CStd → SR，每个场景尽量 48 小时内跑完，场景之间不并行（§9 阶段 2） | 沿用 |
| 7 | 并发 | Anthropic 最多 4 个 `claude -p`；与 Strata 同时运行时 WSL 内 Claude Code、Codex 进程合计不超过 5；OpenAI 串行（同一登录）（§3 凭据，§14 并发） | 沿用 |
| 8 | 时限 | SR、CA 用 ARW 原版 55 / 60 分钟；CS、CStd 用阅读量公式 T，P、G、β 由每个配置的 P4 探针测得（§3 时限，§8 P4） | 沿用 |
| 9 | 早退暂停 S2 | 答复继续，实例照常跑完，有暂停的实例整体扣 0.1（§14.1 10-20） | 沿用 |
| 10 | 停止点 | S1–S7 与完成条件（§10） | 沿用 |
| 11 | 探针 | P0–P6（§8） | 沿用，按 v1 做法重跑 |
| 12 | 安全验收 | 每种 harness 一次完整门，每个配置一次短冒烟（27 次）（§7） | 沿用 |
| 13 | 统计与预登记比较 | 逐场景、逐配置报告 n、均值 ± SD、SE、95% 区间等；不给比值、综合分和排名；预登记族为「同一 harness、同一强度下 Strata 对其他每个配置」加两个 harness 之间的对照，每场景 25 个比较，Holm 校正，双侧 α = 0.05，Welch t 检验（§5） | **改**（用户 2026-10-25）：v2 不做组间比较：没有预登记比较族、Holm、显著性检验、组间差值、「高于 / 低于 / 未分出」和排名。条件完全相同（同一场景、模型、harness、强度）的组内统计全部照旧，与 v1 同一份代码：n、均值、SD、SE、95% 区间、平均耗时、平均 token、速度（总 token ÷ 总耗时）等，选入统计的实例规则也沿用 v1；另给逐实例的详细结果。数据供外部工具做成图表页面，比较由看页面的人自己做。理由：用户重新定了 benchmark 的目的，所以 v1 的比较族不再适用（同日更早按「所有模型互相比较」设的 47 个比较族随之作废，[审查](review-2026-10-25.md)问题 1 已被取代）。跟着改的：可分辨差按比较族估计的部分不再需要，「Strata 用全部有效实例」与 n 不对称仍按 v1 规则，只是不再进比较；`benchmark_summary --suite v2`、`benchmark_export` 去掉比较部分 |
| 14 | 盲裁 | 单名 Opus high，冻结 brief；每池最多 150 项（CStd、SR 210），每池 12 个锚点加全部合成项，门槛锚点一致率 ≥ 90% 且合成项全对；沿用已有决定只按内容指纹（§6.2，§14.1 10-21） | 裁决方式、池大小、锚点数、门槛沿用。**改**：因为 v2 改了四份 brief（第 4.2 节），而 v1 的决定和锚点是在旧 brief 下作出的，所以决定库按套件和 brief SHA 隔离，v1 决定不沿用到 v2，锚点注册表改为 `benchmarks/multi-model-v2/anchors/`，v1 锚点在 v2 brief 下逐个复核后才登记（第 9.2 节，第 11 节 F10） |
| 15 | 评分 | r8.4，全部跑完后按最终规则统一重评（§3 场景与评分） | **改为 r8.5**：因为第 9 节第 1 项决定 SR 缺检查的反例记中性，所以评分版本从 r8.4 改为 r8.5（第 6.1 节）；统一重评沿用 |
| 16 | 格式罚基准 | 按答案键 SHA 登记的 Haiku-high ×5 基准（§3） | **CS v5.1、CA v3.1、SR v4.5 重标**：因为第 9 节第 10 项定为重跑格式基准，SR v4.4、v4.5 也改了场景措辞，同一理由适用，所以三个改过措辞的场景都重标；CStd v5.1 没改，沿用 v1 登记 |
| 17 | 基础提示 | 只给 Strata（D4，§3） | 沿用 |
| 18 | 搜索、service tier、guardian、权限 | 全部关闭搜索（D5）；tier 一律 default（D14）；guardian 按 D6；G7 凭据 deny-read（§3） | 沿用 |
| 19 | DeepSeek 的 Claude Code 窗口与输出上限 | 未设窗口，约 162K 压缩；`max_tokens` 32000（§4 第 7 条，§5.1） | **改**：因为测量规则「跨 harness 比较」要求两边设置一致，且第 9 节第 2 项决定两边都用 1M、不压缩，所以 Claude Code 设 1M 窗口和不触发压缩的阈值，输出上限与 Codex 一致（第 5.2 节） |
| 20 | Role 位置（Claude Code） | 在用户消息里（§14.1 10-18 参考运行形状） | **改为系统提示**：因为第 9 节第 3 项决定开启 `--role-as-system`，所以 v2 计划把它写成默认（第 5.4 节） |
| 21 | Codex 私有 scratch | v1 所有 Codex 臂都不选，以免前后不一致（reviewer-suite 规则「私有 scratch」） | **改为启用**：因为第 9.1 节第 13 项决定启用，所以四个 v2 计划的 `codex_harness_patches` 加 `reviewer-private-scratch`；`arw_dimension.prepare` 拒绝漏掉计划声明补丁的调用；实例结束后照规则用 `reviewer_scratch --remove` 删除；报告列为与 v1 的条件差异 |
| 22 | 会话检查 | 便宜模型读过滤后的 `actions.md`、`flagged.md`，被标记项由 Main 复核（D9，§5） | 沿用 |
| 23 | 两阶段计分 | 第一阶段只用预登记实例完成计分、审查和报告，加测结果第二阶段补入（§14.1 10-21） | 沿用 |
| 24 | DeepSeek 时段 | 只在低谷时段调用（§3） | 沿用 |
| 25 | 预算 | GPU 约 22–25 小时，另加测约 22 小时；Anthropic 中值约 $680，占周额度约 58%（§6.1，§9） | 沿用估算方法：配置和实例数不变，冻结时用 v1 实测费用重算 |

Codex 臂另有两个 harness 补丁沿用 v1：`codex-0.163-synthetic-mount-targets` 和 `strata-measurement-time-limit`（CS、CStd 的阅读量时限），v2 计划把它们和 scratch 补丁一起写进 `codex_harness_patches`。

## 11. 冻结前检查清单

每项写明做法、所用模型和预计成本。「已做」项是 10-24 用零模型方式完成的；其余冻结前做。费用为按 v1 同类工作的量级估计，未实测。用付费模型前先跑 `estimate.sh --can-start`。

| # | 检查 | 做法或命令 | 模型 | 预计成本 | 状态 |
|---|---|---|---|---|---|
| F1 | 场景审计（第 9 节第 5、6、10 项） | Opus 审计，范围：三个场景的改动行（CS `governing-spec.md:160`；CA issue 01 第 30 行两份、`dispatch-policy.md` 规则 24；SR `promotion-recovery.md:65`、`:85`，RM 与 AP 两份 view）、引用这些行的全部答案键用例、A4 改动，以及 A5 的「binding 失配结果」子类（判定 v1 中这类 finding 是模型误读还是文本缺陷）。A5 子类的结论要在 brief 冻结前出来 | Opus high（Claude Code 无头，`--setting-sources ""`） | 每场景约 $3–5 周额度，合计约 $10–15 | **已做（2026-10-25）**：[F1 审计](audit-f1-2026-10-25.md)，必须修 M1–M5、建议修 S1–S4 已按文末「Main 的处理」落实（四份 brief、SR v4.5、本计划 4.1–4.3、第 9 节第 6 项、F3）；M4 查到原裁决后按原意写明（ds-ca-4-149 原判 `supported`，所讲缺陷不是该行问题用例） |
| F2 | 格式基准按套件登记（工具前置） | 让 `tools/reviewer/format_penalty.py` 按套件取登记表和存档目录（v2 用 `benchmarks/multi-model-v2/format-baseline.json` 与同名目录），v1 登记不动；补单测 | 无 | 0 | 已做（2026-10-25）：`format_penalty` 与 `bench_score.repetition_score` 按套件取登记表（`--suite`，记录里的 `suite` 字段传入）；v2 登记文件由 F3 创建，答案键不变的场景可用 `inheritsFrom: v1`，其余键必须在 v2 登记里，不静默回落；`tests/test_format_penalty.py` 加 2 个单测（各套件独立、v2 重标不撞 v1 键、v1 不变） |
| F3 | 格式基准重标（第 9 节第 10 项，加 SR） | **依赖 F1 和 [F1 审计](audit-f1-2026-10-25.md) M2（SR v4.5），场景文本冻结后再跑**：格式基准按 reviewer 加 `expected.json` 的 SHA 登记，改措辞时答案键 SHA 不变，在旧文本上跑出的基准会被静默沿用（M3）。SR v4.5 改了场景文本，所以 F4、F9（在 v4.4 文本上做的）要重跑，F16 按 v4.5 重新绑定；此后场景文本再有任何改动，F3、F4、F9 都重跑，F16 重新绑定。CS v5.1、CA v3.1、SR v4.5 各 Haiku-high ×5：`python3 -m tools.reviewer.claude_scenario --plan benchmarks/multi-model-v2/scenarios/<场景>.json --out .tmp/v2-format/<场景>-<i> --model <Haiku 具体 ID> --effort high --label format --no-startup-prompt --no-compact-prompt`（SR 加 `--handoffs 2`），再按 `format_penalty` 登记 Σr/ΣT、下限和 bootstrap 区间。依赖 F2 | Haiku high | 15 个实例约 $4–8 | 未做 |
| F4 | ARW 零模型 prepare 与 mock 门 | 四个 v2 计划逐个 `arw_dimension.prepare`（带计划声明的三个 harness 补丁）；Codex mock 门 `python3 -m tools.safety.safety_gate --source <prep>/arw --mock-report-write <out> --directory-probe --read-probe --scratch-probe`；Claude Code mock 门 `python3 -m tools.safety.claude_gate --out <out> --backend {deepseek,anthropic} --model <id> --repeat 1`；SR v4.4 dry-run `claude_scenario --dry-run --handoffs 2` | 无 | 0 | **已做，通过**（见表下，SR 为 v4.4 文本）；**SR v4.5 重跑（2026-10-25，零模型）：ARW prepare 与 Codex mock 门通过**，结果见表下「F4 重跑」，与 10-24 一致；harness 换版后按 F12 重跑 |
| F5 | DeepSeek 端点上限 | 核实 Anthropic 格式端点（`https://api.deepseek.com/anthropic`）的上下文上限和输出上限（官方文档，必要时 1 个带 key 的短请求）；从 v1 的 DeepSeek 记录确认 >200K 输入的请求被接受；据此和 F8 的 Codex 实际值填 `CLAUDE_CODE_MAX_OUTPUT_TOKENS`。要联网和凭据，本轮未做 | 无，或 DeepSeek 1 个请求 | < $0.01 | 部分（2026-10-25，待 Main 决定，值未填）：官方定价/模型页（api-docs.deepseek.com/quick_start/pricing）：deepseek-v4-flash、deepseek-v4-pro 上下文 1M、最大输出 384K，默认输出未写明。Anthropic 格式页（api-docs.deepseek.com/guides/anthropic_api）：`max_tokens` 完全支持但未给上限；`model` 不透传（claude-opus* 映射到 v4-pro，其余 claude* 映射到 flash）；`cache_control`、`budget_tokens` 被忽略。未发带 key 的请求（未核实实测上限）；v1 记录里 >200K 输入未核。对齐方案三选一：**A（Claude Code 贴近 Codex 的实际行为）**压缩点 945000：Codex 不改（0.164.0 默认约窗口 90%，F7 实测 945000 后压缩），Claude Code `CLAUDE_CODE_MAX_CONTEXT_TOKENS=1048576`、`CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE=945000`；输出上限：Codex 请求不带上限（F8），只能走端点默认，Claude Code 的 `CLAUDE_CODE_MAX_OUTPUT_TOKENS` 须设成端点默认值，该值官方未写，需 1 个带 key 的请求或去掉上限实测，核实前不可定；利：不改 Codex，改动最小；弊：输出对齐依赖未知的端点默认值。**B（两边都显式 384000 输出）**Codex 侧需让请求带 `max_output_tokens`，Codex 配置/目录没有已知的键，要靠补丁或前端代理注入（待查）；Claude Code `CLAUDE_CODE_MAX_OUTPUT_TOKENS=384000`，压缩点同 A 为 945000；利：两边明示、输出不再成为 v1 式失误来源；弊：Codex 要补丁，违背「Codex 不改」，且 Claude Code 对超大 max_tokens 的处理未验证。**C（两边显式较小共同值，如 64000，压缩点显式 900000）**Codex 在目录设 `auto_compact_token_limit=900000`（低于默认点，Codex 允许），输出同 B 需注入；Claude Code `BLOCKING_LIMIT_OVERRIDE=900000`、`MAX_OUTPUT_TOKENS=64000`；利：压缩点两边都显式、不依赖 Codex 默认比例，64000 远高于 v1 的 32000；弊：偏离「1M 不压缩」精神，输出仍需 Codex 注入，64000 为任选值无依据。共同点：无论哪案，压缩点 945000 远高于场景最大输入，实际两边都不触发，差别主要在写进计划的可核性；**两条事实（2026-10-25，已实测，值仍未填）**：（1）端点默认输出上限**未能测出**。Anthropic 格式（`/anthropic/v1/messages`，`deepseek-v4-flash`，输入 36 token）带 `max_tokens=384000`：HTTP 200，`stop_reason=end_turn`，usage 输入 36 / 输出 18，即 384000 不被拒绝。Responses 格式（`/responses`，`deepseek-flash`，流式，不带 `max_output_tokens`）要求数到 100000：两次都 HTTP 200、`response.completed`、`incomplete_details` 为空，模型自己在 734 和 7328 输出 token（几乎全是 reasoning，正文仅约 100 字符）就收尾，没有碰到上限，所以只知道默认上限 ≥ 7328，未得到数值（再逼模型长输出需要换题，且超出本次 3 个请求的预算）。三个请求合计输出约 8K token，花费远低于 0.01 美元。（2）Codex 0.164.0 没有能让请求带 `max_output_tokens` 的键：二进制里的 `max_output_tokens` 只出现在 exec/code-mode 工具参数（工具输出截断）、auto-review 的 `conversation_history_max_output_tokens`、MCP sampling 的 `max_tokens`；provider 配置只有 `query_params`、`http_headers`、`env_http_headers`、`request_max_retries`、`stream_max_retries`、`stream_idle_timeout_ms` 等，无请求体附加字段；模型目录条目也没有输出上限字段；F8 的 mock 门抓到 Strata、DeepSeek 两臂的请求键都不含 `max_output_tokens`。因此没有可核实的 Codex 设置，两臂行为一致（都不带）。**可行性**：B 不可行（Codex 无键，要靠改二进制或在 Codex 与端点之间加改请求体的回环代理，违背「Codex 不改」，且 Strata 臂也要同样处理）；C 的输出一半同样不可行，只有「压缩点 900000」一半可行（目录 `auto_compact_token_limit`）；A 可行：Codex 不改，Claude Code 的 `CLAUDE_CODE_MAX_OUTPUT_TOKENS` 要填的值只能来自端点默认，现仍未知；已知 384000（文档最大输出）可被端点接受，若默认值低于它，两边输出上限就不相等，取值交 Main 或用户。 **Main 决定（2026-10-25，按方案 A，待冻结前独立审查 F15 一并复核）**：压缩点两边都是 945000——Codex 不改，用 0.164.0 默认点（F7 实测）；Claude Code 设 `CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE=945000`、`CLAUDE_CODE_MAX_CONTEXT_TOKENS=1048576`。输出上限：Codex 没有可设的键，请求不带上限，由端点按自身上限处理；Claude Code 设 `CLAUDE_CODE_MAX_OUTPUT_TOKENS=384000`，即端点文档的最大输出（实测接受）。两边实际都是「端点允许的最大输出」，只差在 Codex 侧的端点默认值没测到数值（≥7328），残余差异写进报告的条件差异。四个场景计划已填值；F6、F8 要按新值重跑 **更正（2026-10-25，Main）**：固定的 Claude Code 2.1.309 把 `max_tokens` 截到 128000（F6/F8 实测，384000 设不进去），所以 `CLAUDE_CODE_MAX_OUTPUT_TOKENS` 改为 128000，即这个版本能发出的最大值；四个计划已改。两臂输出上限因此不同（Codex 不带上限，由端点按 ≤384K 处理；Claude Code 128000），这是 harness 本身的限制，写进报告的条件差异。场景输出远低于 128000，实际不受影响。按此值，F6/F8 实测的 `max_tokens`=128000 与计划相符，Claude 一侧改判通过 |
| F6 | Claude Code 压缩点探针（DeepSeek） | 扩展 `tools.ops.claude_compact_probe` 支持 DeepSeek 的环境组合（`CLAUDE_CODE_MAX_CONTEXT_TOKENS=1048576` 加候选阈值），用假服务器确认压缩点，并覆盖不设阈值时回落到「窗口 − 23000」的情形；据此填 `CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE` | 无 | 0 | 工具已做，值待 F5（2026-10-25）：`claude_compact_probe --plan` 读计划里的 DeepSeek 三个上限；任一为 null 时只写「待 F5 填值」并退出码 2，不用默认值代替（当前 SR v4.4 计划实测为此结果）。三个都有值时跑两遍（覆盖值 ±100 处压缩；不设覆盖时回落到「窗口 − 23000」±100 处压缩），并核对请求的 `max_tokens`。用固定的 Claude Code 2.1.309 和试填值（覆盖 1040000、输出 32000，计划副本不入库）跑通：压缩点正好在覆盖值，回落点 1025576 属实，真实请求的 `max_tokens` 等于环境值。`tests/test_claude_compact_probe.py` 加 5 个单测。F5 填值后重跑一次；**按新值重跑（2026-10-25）：压缩点通过，输出上限不通过**。四个计划（code-spec-v5.1、code-standards-v5.1、commit-audit-v3.1、spec-readiness-v4.4）各跑 `claude_compact_probe --plan`（固定的 Claude Code 2.1.309，两种方式：两回合、回合内；覆盖值 945000 ±100，回落点 1025576 ±100），结果相同：压缩点正好落在 945000（944900 不压缩、945100 压缩后续跑）；不设覆盖时回落点 1025576（1048576 − 23000，1025476 不压缩、1025676 压缩），与工具预期一致；所有 cell 退出码 0、ok。**异常：探针总判定为不通过（退出码 1），因为真实请求的 `max_tokens` 全是 128000，不是 384000。** 2.1.309 对 `CLAUDE_CODE_MAX_OUTPUT_TOKENS` 做上限截断：未知模型的上限是 128000，连模型目录覆盖的输出上限也只接受 ≤128000，所以 384000 在这个版本发不出去。需 Main 决定：Claude Code 输出上限改成 128000（Codex 不带上限，端点最大 384K），或接受两臂输出上限不同并写进条件差异；四个计划里的 384000 暂未改 |
| F7 | Codex 压缩点探针 | 扩展 `tools/safety/` 的 mock 门，回放递增长度的回合，确认 DeepSeek 目录设置下到场景最大输入都不出现压缩事件（第 5.3 节第 2 条） | 无 | 0 | 已做（2026-10-25）：新增 `tools/safety/codex_compact_gate.py`（回环 Responses mock，用 usage 声称的输入量驱动 Codex 自己的记账，经 app-server 跑一个回合）。对照：Strata 档（窗口 206584，限 150000）在声称 151000 之后压缩，通过。DeepSeek 目录（v1 的 `deepseek-codex-0.163.0.json`）到 800000 都没有压缩，通过；**但继续往上，Codex 0.164.0 在声称 945000 之后压缩**（约为窗口 1048576 的 90%，Codex 的默认点），不是「不压缩」。第 5.2 节的「auto_compact 为空，实际不压缩」需要改写，或在目录里设 `auto_compact_token_limit`；两个 harness 的压缩点是否一致由 Main 或用户决定，见 F8。`tests/test_codex_compact_gate.py` 2 个单测 |
| F8 | 输出上限核对 | mock 门抓取两边请求里的 `max_tokens` / `max_output_tokens`，与第 5.2 节一致才放行（第 5.3 节第 4 条）。依赖 F5、F6 填值 | 无 | 0 | 部分（2026-10-25）：Claude 一侧已核对，真实 Claude Code 请求的 `max_tokens` 等于 `CLAUDE_CODE_MAX_OUTPUT_TOKENS`（探针 `output_limit_ok`），值待 F5。**Codex 一侧的请求不带输出上限**：mock 门抓到 Strata 与 DeepSeek 两个案例的请求键都没有 `max_output_tokens`（请求键：client_metadata, include, input, model, parallel_tool_calls, prompt_cache_key, reasoning, store, stream, text, tool_choice, tools）。所以「Claude Code 输出上限设成与 Codex 实际请求相同的值」没有 Codex 的数可抄，Claude Code 的输出上限取值是 F5 的待决问题（交 Main 或用户）；**按新值重跑（2026-10-25）：Claude 一侧不通过，Codex 一侧通过**。Claude Code 臂（2.1.309，四个计划）：真实请求的 `max_tokens` 为 128000，不等于 384000（见 F6 异常，Claude Code 内部上限 128000）。Codex 0.164.0（`codex_compact_gate` 重跑）：Strata 与 DeepSeek 两案例的请求都不带 `max_output_tokens`，请求键与前次相同（client_metadata, include, input, model, parallel_tool_calls, prompt_cache_key, reasoning, store, stream, text, tool_choice, tools），仍不带输出上限；DeepSeek 案例 945000 之后压缩，与 F7 一致。放行条件（两边输出上限与第 5.2 节一致）暂不满足，等 Main 对 F6 异常的决定 **更正（2026-10-25，Main）**：固定的 Claude Code 2.1.309 把 `max_tokens` 截到 128000（F6/F8 实测，384000 设不进去），所以 `CLAUDE_CODE_MAX_OUTPUT_TOKENS` 改为 128000，即这个版本能发出的最大值；四个计划已改。两臂输出上限因此不同（Codex 不带上限，由端点按 ≤384K 处理；Claude Code 128000），这是 harness 本身的限制，写进报告的条件差异。场景输出远低于 128000，实际不受影响。按此值，F6/F8 实测的 `max_tokens`=128000 与计划相符，Claude 一侧改判通过 |
| F9 | 真实 Role 到达假服务器 | 用 v2 计划的真实 Role（SR 36,656 字节）经 `claude_headless` 对假服务器跑一次，核对系统提示完整到达、追加顺序正确，绑定系统提示 SHA。`claude_gate` 目前不带 Role，需加一个选项或用 mock 服务器直接跑 `claude_headless.run` | 无 | 0 | 已做（2026-10-25）：新增 `tools/safety/claude_role_gate.py`，用不改动的 `claude_scenario.run`（后端 deepseek）、固定的 Claude Code 2.1.309、回环 Messages mock、假 key、只有回环的网络命名空间，对四个 v2 计划各跑一次（SR 两个交接），按 mock 收到的请求判定：Role 在每个主循环请求的 `system` 里恰好一次、在 Claude 自己的提示之后且是末尾、不在 messages 里；`system-h<k>.md` 的 sha256 等于绑定的 `system_sha256`；绑定的端点等于 mock 地址。四个计划全部通过（Role 27,861 / 29,540 / 30,172 / 36,656 字节，SR 两个交接是同一个 Role）。DeepSeek 上限仍为 null 的计划用占位上限，Role 检查与之无关。`claude_headless.run`、`claude_scenario.run` 加了 `deepseek_base` 参数（默认不变）。`tests/test_claude_role_gate.py` 3 个单测。**SR v4.5 重跑（2026-10-25）：四个计划（SR 为 `spec-readiness-v4.5.json`）全部通过**，同一工具、同一固定的 Claude Code 2.1.309（sha256 `4d704a8a…`）；Role 字节数与系统提示 SHA 与上次完全相同（27,861 / 29,540 / 30,172 / 36,656；SR 两个交接同一 Role，系统提示 sha256 `01feceab…`，与 v4.4 dry-run 相同，即 SR v4.5 没有改 Role 文本）；每个主循环请求（CS、CStd、CA 各 59 个，SR 每交接 118 个）Role 在 `system` 里恰好一次、在 Claude 自己的提示之后且是末尾、不在 messages 里；绑定的 `system_sha256` 等于文件、端点等于 mock 地址；DeepSeek 上限已填，没有用占位上限（上次记录写的是 null 的计划用占位上限，现在四个计划都已填值） |
| F10 | 决定库隔离与锚点复核 | 隔离已由代码与单测保证（`tests/test_blind_pool.py`、`tests/test_bench_score.py`）；v1 锚点在 v2 brief 下逐个复核（Main 可执行检查，按 v1 §6.2 挑选规则），答案变了的替换，通过的用 `blind_pool anchor-add --suite v2` 登记到 `benchmarks/multi-model-v2/anchors/` | Main | Main 时间约 1 小时 | 隔离已做；锚点复核已做（2026-10-25，零模型，worker）：105 个锚点保留 104 个、剔除 1 个，已登记；54 个合成题保留 53 个、剔除 1 个，合成题已由 Main 照 v1 的做法直接写进注册表的 `synthetic`（逐字取自 v1，另加 `confirmed_by` 复核说明），不另加命令；见下文「F10 结果」 |
| F11 | 工具链的 v1 场景名 | `bench_records`、`bench_score`、`blind_pool` 已套件化；`benchmark_summary`、`benchmark_export` 按第 10 节第 13 项（不做比较）改；v2 的 `bench_records` 运行目录布局和 `benchmarks/multi-model-v2/model-failures.json` 开跑后建立 | 无 | 0 | 部分（2026-10-25）：`benchmark_summary --suite v2`、`benchmark_export` 的 v2 路径（组内统计照旧，不做组间比较）已做并有合成数据单测（见第 8 节）；v2 的 `bench_records` 运行目录布局、`model-failures.json` 和 v2 场景元数据开跑后建立 |
| F12 | harness 换最新版后的零模型检查 | 冻结时两个 harness 同时取最新版写进 `harness_pins.py`，四个计划的 `codex`、`native_cli_sha256` 同步；重跑 F4 的 mock 门、`python3 -m tools.ops.claude_compact_probe --repeat 3`、`verify_codex_compact_prompt` | 无 | 0 | **已做，全部通过（2026-10-25，零模型）**：Claude Code 换到 2.1.310（Codex 仍是最新的 0.164.0，不换），结果见表下「F12 重跑」；冻结时若又出新版，再按流程重做一次 |
| F13 | 安全验收 | 按 v1 §7：Codex 完整门（Strata）、Claude Code 完整门（Haiku high ×3 加 Opus 抽查）、27 个配置短冒烟；Codex 臂的门带 scratch 补丁 | Strata、Haiku、Opus、DeepSeek、OpenAI | Anthropic 约 $10–20；Strata GPU 约 2 小时 | 未做 |
| F14 | 输出上限重试改动 | 确认 `src/output_limit.py` 的重试改动是否已合入并部署，冻结时以部署版本为准 | 无 | 0 | 已核实（2026-10-25）：提交 1e0fd58 在 master（fc43611）上，`src/output_limit.py`、`src/frontend.py` 与 rtx3080ti 安装目录里的同名文件 sha256 相同（`4903c6ef…`、`475d3035…`）。范围：重试只作用于 Strata 前端上流式的 Responses 请求（Codex 臂），Claude Code 的 Messages 请求没有，DeepSeek 与 API 臂不经前端；所以 v2 里只影响 Strata 的 Codex 配置，是条件差异，报告里写明。冻结时再核一次安装目录 |
| F15 | 冻结审查 | 冻结属重要决策：智能与推理强度不低于 Main 的独立 agent 审查本计划、四个计划文件与 brief | Opus high | 约 $5–10 | 未做 |
| F16 | SHA 绑定 | 按 v1 §14 记录全部绑定：场景清单、补丁（含 `scoring-r8.5.patch` sha256 `c40856cc…`）、brief、测量说明、harness 副本、catalog；四个计划改 `status`、`authorization` | 无 | 0 | 未做（随冻结） |

F4 结果（10-24，零模型，worktree 内）：

- `arw_dimension.prepare`：四个计划都成功，handoff 数 CS、CStd、CA 各 3，SR 6；三个 harness 补丁都已应用，r8.5 成员 SHA 生效，`native_cli` 为 0.164.0；CS、CStd 的 T = 1800 测量说明正常渲染。
- Codex mock 门（SR v4.4 副本，`--directory-probe --read-probe --scratch-probe`）：`passed`。写边界 8 类全部拒绝，`new_sibling` 按批准策略允许；凭据 deny-read 全部 `denied`，`shell_env_key absent`；scratch：TMPDIR 指向自己的 scratch，脚本、复制修改执行、临时文件可用，兄弟 scratch 和公共根的读、列、写全部拒绝，实例结束后两份 scratch 都删除。这个门没有传 `--web-search disabled`，请求里有 2 个搜索工具，与 v1 §7 记录的 Strata 零模型模式相同；正式门按 v1 写 `web_search: disabled`。
- Claude Code mock 门（2.1.309 副本）：deepseek（`deepseek-v4-flash`）与 anthropic（Haiku）各 1 次，隔离通过，失败探针 0，搜索工具 0。这个门不读场景计划，没有覆盖 DeepSeek 的 1M 窗口设置（留给 F6、F8）。
- SR v4.4 `claude_scenario --dry-run --handoffs 2`：Role 进系统提示，两段系统提示 SHA 相同（`01feceab…`）。

F4 重跑（2026-10-25，零模型，SR 为 v4.5；harness 仍是 `harness_pins.py` 固定的 Codex 0.164.0，sha256 `b93f6811…`）：

- `arw_dimension prepare`（`tools.tuning.arw_dimension prepare`，CS、CStd 带 `--time-limit-seconds 1800`）：四个计划都成功，handoff 数 CS、CStd、CA 各 3，SR 6，与上次相同；三个 harness 补丁（`codex-0.163-synthetic-mount-targets`、`strata-measurement-time-limit`、`reviewer-private-scratch`）都已应用；r8.5 成员 SHA 由 `freeze_arw_source --scoring r8.5` 核对通过，`scoring-r8.5.patch` sha256 仍是 `c40856cc…`；`native_cli` 为 0.164.0；CS、CStd 的 T = 1800 测量说明正常渲染（sha256 `9d6c6da7…`），CA 用 `measurement-note-commit-audit.txt`，SR 用 `measurement-note.txt`（`0bf509f0…`）。命令末尾的 `preflight` 一步对基准臂必败（计划 `host` 是 `none (benchmark arms…)`，不是本机），与 prepare 无关，上次同样不用它。
- Codex mock 门（`--directory-probe --read-probe --scratch-probe --web-search disabled`，**四个计划都跑**，上次只跑 SR 副本）：四个都 `passed`。写边界 8 类全部拒绝，`new_sibling` 为 `allowed-extra-scope`（批准策略），共享根 `/var/tmp`、`/run/lock` 拒绝、`/dev/shm` 可写（与上次相同）；凭据 deny-read 四项（Claude 凭据、Codex auth、Codex home、私有主机文件）全部 `denied`，`shell_env_key absent`，`fake_key_exposed` 为假；scratch：TMPDIR 指向自己的 scratch，脚本、复制修改执行、临时文件可用，兄弟 scratch 和公共根的读、列、写全部拒绝，实例结束后两份 scratch 都删除；真实模型请求 0。**与上次的差别**：这次传了 `--web-search disabled`，请求里的搜索工具为 0（上次 2 个）。
- SR v4.5 `claude_scenario --dry-run --handoffs 2`（deepseek 后端）：两个交接都是 Role 进系统提示，系统提示 sha256 相同，仍是 `01feceab…`。Claude Code mock 门（`claude_gate`）不读场景计划，本轮未重跑。

F12 重跑（2026-10-25，零模型，运行目录 `.tmp/v2-f12/`）：Claude Code 从 2.1.309 换到 2.1.310；Codex 0.164.0 不变。

- 副本：`~/.local/share/qwen-bench/claude-code-2.1.310/claude`（从日常安装复制，只读），sha256 `b7367643…47df56`，与官方 manifest（linux-x64）checksum 一致。`harness_pins.py` 已更新；四个 v2 场景计划里的 `native_cli_sha256` 是 Codex 的值，不含 Claude Code 版本，无需改。
- Claude Code mock 门（`claude_gate --repeat 1`）：deepseek（`deepseek-v4-flash`）与 anthropic（`haiku`）各通过，隔离通过，失败探针 0，搜索工具 0，与 2.1.309 一致（`ENABLE_TOOL_SEARCH=false` 仍有效，没有占位工具问题）。
- 压缩点与输出上限（`claude_compact_probe --plan ... --repeat 3`，四个计划都跑，副本 `--claude`）：每个计划 24 格全部 ok，判定 pass。压缩点仍在 945000（944900 不压缩，945100 压缩后续跑，两回合与回合内两种方式一致）；不设覆盖的回落点仍是 1025576（1025476 不压缩，1025676 压缩）；真实请求的 `max_tokens` 全是 128000，等于计划值。
- 2.1.310 的输出上限仍截在 128000：临时计划副本（不入库）把 `CLAUDE_CODE_MAX_OUTPUT_TOKENS` 设为 384000，实际发出的 `max_tokens` 仍是 128000（探针按预期判不通过，这是设计中的对照）。
- Role 到达（`claude_role_gate`，四个计划）：全部通过。Role 字节数 27,861 / 29,540 / 30,172 / 36,656，与 2.1.309 相同；SR 两个交接同一 Role，系统提示 sha256 仍是 `01feceab…`。每个请求 Role 在 `system` 里恰好一次、在末尾、不在 messages 里。主循环请求数 CS 58（上次 59）、CStd 59、CA 59、SR 每交接 118；CS 少 1 个是 2.1.310 的请求数差异，不影响判定。
- Codex 侧（版本不变，只确认）：`verify_codex_compact_prompt` 通过，原生压缩提示 426 字节，sha256 `ab0c334d…` 与快照一致；Codex mock 门（SR v4.5 的 prepare 源，`--directory-probe --read-probe --scratch-probe --web-search disabled`）通过，边界、凭据、scratch 与 F4 重跑一致，搜索工具 0。
- 与 2.1.309 的差异：除 CS 请求数 58 对 59 外，没有发现行为差异。

F10 结果（2026-10-25，零模型，worker；运行明细 `.tmp/v2-f10/`）：v1 的 4 个注册表共 105 个锚点、54 个合成题，逐个对照 v2 brief（统一口径、CS「只说违背」与 `:160` 款、CStd 重复类与「只说违背」、CA 决策树、SR caller 款、binding 款、未选节款）和 v2 物化场景文本（`check_briefs --suite v2`）核对。v1 的三个可执行检查在 v2 物化 view 上重跑（CS、CA 用 candidate；CStd 用 base 与 candidate 合并的 `src`），输出与 v1 记录相同。

| 场景 | 锚点保留 | 改期望 | 剔除 | 登记数（其中 not-matched） | 锚点来源 family | 合成题保留 / 剔除 |
|---|---|---|---|---|---|---|
| code-spec-v5.1 | 24 | 0 | 0 | 24（7） | openai、anthropic、strata | 13 / 0 |
| code-standards-v5.1 | 24 | 0 | 0 | 24（6） | 只有 strata | 14 / 0 |
| commit-audit-v3.1 | 28 | 0 | 1 | 28（5） | openai、anthropic、strata | 17 / 1 |
| spec-readiness-v4.5 | 28 | 0 | 0 | 28（10） | anthropic、strata | 9 / 0 |

- 登记：保留的锚点用 `blind_pool anchor-add --suite v2` 逐个登记到 `benchmarks/multi-model-v2/anchors/`，item 与 v1 逐字相同，`confirmed_by` 写明 v1 编号、复核理由和 v1 原依据。新编号按 v1 顺序重排，只有 CA 从 v1 a06 起前移一位（v1 a06→v2 a05 … v1 a29→v2 a28）。四个场景都超过每池 12 个（`build` 每池抽 12 个），注册表里都有 not-matched，满足 §6.2 的 10–15 个且至少 1 个 not-matched。
- 剔除（锚点）CA v1 a05：所挂要求行 issue 01:30 在 v3.1 改了措辞（"otherwise returns an error result" 改成 "returns a result whose `ok` is `false`"），item 的 `requirementSource` 仍引 v1 原文。判法本身（`Number()` 接受非十进制文本，判 matched）不受影响，按「依赖的文本已改」剔除。
- 剔除（合成题）CA v1 s04（near-miss，挂 01:30）：理由同上，期望 not-matched 本身不变。
- 改期望：无。
- 涉及改动行、但判法不变而保留的：CA a09（finding 转述规则 24 的 "at every depth"，v3.1 只把范围限定为所引要求点名的值，spec:12 点名 authentication data）；SR a10、a15、a23（证据含 `prt:11`，所讲分别是 Flow 缺 readArtifact、operation 字段冲突、Readiness 与 Promotion 重复校验，不涉及 binding 失配，也不就"或失败分支"立论）；SR a21（证据含 `prc:65`，所讲是重复校验，v2 caller 款写明照常判）；SR a07（用 RM 未选的 Interfaces 字段定义核对选定 Requirements 的冲突，属未选节款的例外）。CS 没有锚点或合成题引用 `governing-spec.md:160`。
- 合成题未登记：`blind_pool` 没有登记合成题的命令（v1 注册表的 `synthetic` 是直接写入的）。保留的 53 个按场景整理在 `.tmp/v2-f10/synthetic-<场景>.json`，待 Main 决定登记方式。在登记之前，`split` 因为"合成项必须存在"这一条，任何 v2 池都不会判通过。
- 缺口（沿用 v1，不是 v2 新出现的）：CStd 锚点全来自 strata，SR 没有 openai 锚点，按 family 报告一致率时这些 family 没有数据。按任务约束没有从 benchmark 输出另挑新题（v2 还没有输出）。
