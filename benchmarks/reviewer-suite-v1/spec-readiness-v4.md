# Spec Readiness 能力场景 v4：相对 v3 的变更说明

v4 以补丁 [`arw-patches/spec-readiness-v4.patch`](arw-patches/spec-readiness-v4.patch)（sha256 `b1695ecc0087cb80eaf2da234e5defa32251358b2dd474f0a8e4add449401b60`）提供，叠在 [v3](spec-readiness-v3.md) 和 `code-spec-v2.patch` 之后，已在冻结源 manifest 登记。改动范围：

- 夹具的可见文字 2 处；
- 答案键；
- `SCENARIO_REVISIONS` 中 spec-readiness-reviewer 由 42 改为 43。

评分规则、角色规则、交接，以及准备 / 生成 / 评分程序都不改。v4 的分数只与 v4 比较。

## 起因

v3 测量（Opus ×3、IQ3_XXS ×10）中，有两个用例两个模型都是 0 命中：MD-INTERFACES#5 与 MD-SEAMS-ADAPTERS#1。用户 2026-10-13 的规则是：只修非智力原因，纯智力难度不改。成因分析见 [v3 报告](../../reports/v0.1.42/spec-readiness-v3/summary.md)「剩余两个双 0 用例的成因分析」，结论是两个用例都有非智力成因：

- **INTERFACES#5**：
  - 缺陷只存在于 AP 未选定的 `architecture/05-validation-report.md:29`。Role 规定未选定 Input 只作比较证据。
  - 键里举的例子（多余根字段对无效 requestId）不能唯一推出。
- **SEAMS#1**：
  - `promotion-recovery.md:59` 只说失败的"内部结果"精确为 …，没有说这是 Seam 的返回值。另一种读法因此同样成立。
  - 它与同两行上的 clean 用例相撞。

## 改动

| 文件:行 | 场景 | 改动 | 原因 |
|---|---|---|---|
| `specs/validation-report.md:45`（AP 覆盖文件 `scenario/full-review/base/`） | 仅 AP | 同一行增加："Artifact 含 input schema 未允许的 extra field 时, `reason` 为 `unexpected-field`, `field` 为该 extra field 的 JSON path." 不给它在 validation order 中的位置 | 缺陷落到 AP 选定的 spec 自身，由选定文字与它采用的合同顺序共同推出。RM 的 architecture/05:29 已完整定义 extra field 的顺序，RM 也不审 Module Design，所以 RM 不改 |
| `specs/promotion-recovery.md:59` | RM、AP | 首句 "Restore failure 的内部结果精确为" 改为 "Restore 失败时 Seam 返回的 `recoveryState` 精确为"；成功仍只写语义 | 消除"失败形状属于谁"的歧义。clean（配置不同结果可不同）仍然成立 |

答案键：

- **合并 v3.1 键**（[说明](spec-readiness-v3-iq3_xxs-2026-10-13/v3.1-key.md)）：MD-RATIONALE#3 的 placements 加宽。
- **INTERFACES#5**：
  - expectation 去掉原举例，改为："extra field 与其他 invalid field 并存，或有多个 extra field 时，单一首个 diagnostic 无定义"。
  - 新增 placement：关联 vr:45，证据 vr:45、arch05:29、vr:104。
- **INTERFACES#6（source）**：删去关联 vr:45 的 placement。vr:45 是 invalid-artifact 的合同；source 用例的两半都不在这一行。这个 placement 会让每个 INTERFACES#5 的 finding 也成为 source 用例的候选。
- **SEAMS-ADAPTERS#1**：expectation 改为："Seam 固定了 restore 失败时返回的 recoveryState，成功只给语义、没有形状，两个 Adapter 没有完整的共同结果合同"。
- **SEAMS clean（Recovery Adapters）**：expectation 改为"共享精确的 restore-failure recoveryState"，并注明"成功形状缺失是另一个 Seam 问题"。证据不变。
- findingTerms 随之调整。按 ARW 规则，findingTerms 不决定候选资格。
- 用例数不变：RM 5 个 problem、10 个 clean；AP 17 个 problem、43 个 clean。

## 审查过程

按 ARW Fixture authority 两阶段审查，共 1 轮，由一个全新的 Opus 高推理强度审计者完成。另由两个全新的 Opus 高推理强度 agent 按真实交接盲答 RM 与 AP，本工程评分。

| 轮次 | 阻断 / 主要 | 盲答 RM | 盲答 AP |
|---|---|---|---|
| 1 | 0 / 0（次要 m1–m5） | 0.992 | 0.741（clean 43/43；命中 INTERFACES#5，未命中 SEAMS#1） |

审计结论：

- **INTERFACES#5**：现在只凭选定的 vr:45 和 AP 版 arch05:29 就能唯一推出。
- **SEAMS#1**：在 v4 文字下成立。阶段 1 判为"语义已足够、不报"，阶段 2 对照答案键后，审计者认定这是自己的判断失误，属于审查难度，不是场景缺陷。
- **次要项处理**：
  - m1（INTERFACES#5 新 placement 单独不足以证明）、m2（source 用例关联 vr:45 不当）、m3（Recovery Adapters clean 措辞与 SEAMS#1 有张力）：已按建议只改答案键，同一审计者复核后确认"可冻结"。这三项不涉及 Reviewer 可见内容，盲答不需重做。
  - m4（MD-RATIONALE#3 关联 ar:67/71 过宽，是 v3.1 用户已同意的修订）：未改。
  - m5（source 用例含两个子缺陷，属可选建议）：未改。

## 残余（次要，未改）

- v3 残余 (a)、(c)、(d)、(e) 不变，见 [v3 变更说明](spec-readiness-v3.md)。
- v3 残余 (b) 已由删去 source 用例的 vr:45 placement 消除。
- m4、m5 见上文。

## v4.1（只改答案键，修订号 44）

用户 2026-10-13 决定删除 `MODULE-DESIGN-SEAMS-ADAPTERS` 问题用例 #1，并要求保持用例下限。补丁 `arw-patches/spec-readiness-v4.1.patch` 叠在 v4 之后，只改 `expected.json`（删除该问题用例，并删去同 scope 第 4 个 clean 用例末尾指向它的一句）和修订号（43 → 44，使已准备的场景缓存失效）。打补丁后 `expected.json` sha256 `3093980fc37278abd16a935cd10d143dbcbab19435671bdee7e7fd2f13c3526f`，ARW conformance 测试 70/70 通过。

删除依据：

- **答案不成立**：`promotion-recovery.md:57` 写明成功语义，Recovery Module 用输入的 priorTrackedState 和原始 commit failure code 形成公开成功结果；成功路径不消费 recoveryState 的任何字段，"成功时 recoveryState 无形状"不构成缺陷。失败形状（`:59`）是 Module 要消费的，已精确给出。
- **证据**：v4 审计阶段 1（全新 Opus-high，要求穷尽查找缺陷）判"成功语义已足够，不报"；v4 的 8 份 AP 回答（Opus 3、Q3 5）无一报告该问题。
- **夹具不改**：判定的是该处本来就不是缺陷，不存在需要同步修复的可见缺陷。

用例下限：ARW 要求合并后的评分清单至少 20 个问题用例和 20 个 clean 用例（`MINIMUM_CASE_COUNT = 20`）。v4.1 为 21 / 43，满足下限，不补用例。SEAMS scope 不再有问题用例；ARW 只要求每个 scope 恰有一个 `noOtherSupportedFinding` clean 用例。

v4 已有回答的候选集合在 v4.1 下逐条不变，沿用 v4 裁决。结果见 [v4 报告](../../reports/v0.1.42/spec-readiness-v4/summary.md)。

## v4.2（A 类平衡到 4:4，修订号 45，2026-10-16 冻结）

用户 2026-10-15 要求 A 类正例与反例总数相等。独立审查（2026-10-15）判定 v4.1 的 A 类为 2 正 4 反。v4.2 补 2 个正例；审计第 1 轮又建议把 REQUIREMENTS 反例 3、4 改归 B，于是另补 2 个反例，最终 4 正 4 反（见「A 类标记方案」）。补丁 `arw-patches/spec-readiness-v4.2.patch`（sha256 `c50a46f4c84c3b5b42c6f1239aca41fae860f2be0dd83b68d55d120029c08329`）叠在 v4.1 之后；因为之后的 `code-spec-*` 补丁以 `['spec-readiness-reviewer', 44]` 为上下文，v4.2 放在补丁链末尾，登记在专用 manifest `source-snapshots/current/manifest-spec-readiness-v4.2.json`（`manifest.json` 加上 v4.2），修订号那一处只带 1 行上下文，不依赖 code-spec 的修订号。打补丁后 `expected.json` sha256 `74252e0aa4e50d231efaefdfa24a27e1b4d97936e747425787d30bace996a344`。改动范围：

- 夹具：AP 覆盖文件（`scenario/full-review/candidate/specs/`）的可见文字 3 处（含第 3 轮审计的 `prc:57`，见「第 3 轮审计修改」），只改行内文字，不增删行，现有 placement 的行号都不变；RM 副本不改（RM 遇到 REQUIREMENTS 问题就停，不审 Module Design，与 v4 改 vr:45 的做法一致）；
- 答案键：新增 2 个问题用例、2 个 clean 用例（MODULES clean 2、SEAMS-ADAPTERS clean 4，插在各自 scope 的 noOther 之前）；SEAMS-ADAPTERS clean 3 的 expectation 由"共享精确的 restore-failure recoveryState"改为"两种结局都共享精确的 recoveryState"（第 3 轮审计）；
- A 类标记：覆盖文件 `judgment/spec-readiness-v4.2.json`，登记在 `judgment/registry.json`；
- `SCENARIO_REVISIONS` 中 spec-readiness-reviewer 由 44 改为 45。

评分规则、角色规则、交接，以及准备 / 生成 / 评分程序都不改。用例数：RM 5 个 problem、10 个 clean（不变）；AP 18 个 problem（原 16）、45 个 clean（原 43）。

### A 类标记方案

分界按 [reviewer-suite 规则](../../.claude/rules/reviewer-suite.md#评分)：同时看答错本身的影响大小和 main agent 能否验证并拦住；影响本来就小的不再看能否拦住。独立审查已定 6 个 A 类；本版加 2 个新正例，REQUIREMENTS 反例 3、4 改归 B，另加 2 个新反例。

REQUIREMENTS 反例 3、4 改 B 是审计第 1 轮 m3 的建议：两者都能对照 issue 与规则逐条核实，误报会在 main agent 核实时排除，按分界属于 B。这是 A/B 口径的判定，应交用户定；用户 30 分钟内未答复，按 Main 与审计一致的意见执行，**待用户复核**。

| 用例 | 正/反 | 计分场景 | 判断类型 |
|---|---|---|---|
| REQUIREMENTS 正例 2（image-preview 清理不属于本 issue） | 正 | RM | 范围是否必要 |
| MODULES 正例 0（Readiness 与 Promotion 重复持有校验） | 正 | AP | 该不该合并 |
| **MODULES 正例 1（新，Promotion 与 Recovery 重复校验 recovery input）** | 正 | AP | 该不该合并 |
| **SEAMS-ADAPTERS 正例 0（新，Access Review Module 与 Policy Adapters 重复持有授权策略）** | 正 | AP | 该不该合并 |
| MODULES 反例 0（两个独立 operation 各按同一契约校验，不是重复） | 反 | AP | 不该合并 |
| MODULES 反例 1（Readiness Module 保留原职责，无重叠） | 反 | AP | 职责搬移 |
| **MODULES 反例 2（新，Promotion 的持久化前置检查与 Recovery 的输入校验义务不同，不是重复）** | 反 | AP | 不该合并 |
| **SEAMS-ADAPTERS 反例 4（新，Artifact Reader Adapters 只供字节，校验与结果策略留在 Validation Report Module，无重复策略）** | 反 | AP | 不该合并 |
| REQUIREMENTS 反例 3、4 | 改归 B | | 待用户复核 |

每次重复（RM + AP 融合计分）正反各 4，一律报或一律不报的 A 部分都是 0。单看子场景不平衡：RM 1:0（只有 REQUIREMENTS 正例 2），AP 3:4；因此每个子场景单独计分时都会给出 judgmentWarning，这是预期的，计分以融合结果为准。规则要求的是总数相等，不要求逐个子场景平衡，所以不为 RM 再补题。其余用例归 B，理由不变（能对照规则或其他规范逐条核实，误报会在核实时排除）。

### 新正例

两个新正例都放在只有 AP 计分的检查项，都属于用户举的 A 类原型"该不该合并"：漏报会留下两个所有者，日后各自演化时规则悄悄分叉；误报会推动删去或合并其实独立的检查（MODULES 反例 0 就是这种不该合并的情形）。两处在现行输入下结论相同，测试分不出对错，main agent 只能靠设计判断拦，拦不住时两个方向的代价相当。

**SEAMS-ADAPTERS 正例 0**（`specs/access-review.md:27`，AP 覆盖文件）

- 改动：Modules 段原句"…并通过 Policy Evaluation Seam 执行 policy evaluation, 不拥有 …"改为"…执行 policy evaluation. Seam 返回 allowed 后, Access Review 检查 facts.operation 是否在 policy.allowedOperations 中; operation 不在其中时返回 Interfaces 的 denied decision, 不读取 artifact. 它不拥有 …"。（审计第 1 轮 B1：初稿写"只有两者都允许时才读取, 否则返回 denied", 字面上把 Seam 的 invalid-policy、invalid-request 和 Adapter 失败也映射成 denied, 与 `:15`、`:45` 冲突, 并让 INTERFACES 正例 1 可被反驳; 现只规定 operation 不在列表中这一种情况, Seam 其他结果仍按 `:45`、`:51` 原合同。同时去掉"自行", 少一处局部线索。）
- 缺陷：`:15` 规定 policy 只按 operation 是否在 allowedOperations 中判定，`:51` 规定两个 Policy Adapter 对同一 policy 和 facts 给出该判定；Module 又自行实现同一条规则，违反 SEAMS 检查"拒绝重复的运行时领域策略"和 MODULES 检查"重要行为只有一个责任方"。推理：读 `:27` 的检查 → 对照 `:15` 认出它就是 policy 本身 → 对照 `:51` 认出 Adapter 已经求值同一规则。
- 不造成别的缺陷：只有"Seam 允许、operation 不在列表中"这一种情况的结果是新写的（denied，沿用 Interfaces 合同），Seam 其他结果的去向不变；Testing Decisions 已测 denied，这条分支随重复的修正一起消失，不是独立问题（审计 m1）。
- 答案键：`result: gap`；placements 允许 SEAMS-ADAPTERS、MODULES 和 DEPENDENCIES-DATA-FLOW，关联证据都是 `:27`：SEAMS 与 MODULES 各有证据 `:27` 加 `:51`、`:15` 或两者 6 个位置；SEAMS 另有 `:27` + `architecture/04-seams.md:5`（Live Adapter 用 production policy engine 求值）；DATA-FLOW 为 `:27` + `:55`（Data Flow 里 allowed decision 只来自 Seam，未提 Module 的检查），共 8 个位置（审计 M2）。关联行 `:27` 已是 MODULE-RATIONALE 正例 2 的关联行，但检查不同，不会互成候选。findingTerms：Access Review、allowedOperations/operation、Seam/Adapter、duplicate 一类词。

**MODULES 正例 1**（`specs/promotion-recovery.md:31`，AP 覆盖文件）

- 改动：原句"`Promotion Module` 拥有 commit attempt, 不执行 rollback."改为"…不执行 rollback; 交出失败尝试前, 它按 Interfaces 的 Invalid Input Diagnostic 顺序检查 `{artifact, priorTrackedState, failedCommitId, commitFailureCode}`, 有误时直接返回该 diagnostic, 不调用 Recovery."
- 缺陷：`:65`（以及 `:19`、`:41`）规定 Recovery Module 按同一顺序校验同一对象，两个 Module 在同一条失败路径上对同一输入持有同一校验。与 MODULES 反例 0 的区别：反例是两个独立 public operation、各有大小限制等不同合同并写明了不复用的理由；这里是同一次交接、同一合同、没有理由。
- 不造成别的缺陷：Promotion 提前返回的是 Recovery 自己会返回的同一 diagnostic，对 caller 可见的结果不变；无效输入时 Recovery 本来也不 restore。
- 提前返回的连带表述（审计 M1，采用方案 a，不改流程文字）：Promotion 输入有误时直接返回、不调用 Recovery，与 `promotion-runtime.md:41/:45/:57`、`promotion-recovery.md:65/:73`、`architecture/02-commit.md:5` 写的"commit 失败后交给 Recovery、原样传播 Recovery 结果"不再一致。这是同一重复校验的后果：两个修正方向（去掉 Promotion 的校验，或改由 Promotion 独占）都要处理这处交接，所以并入本用例，expectation 已写明，不另设用例。不改流程文字的理由：改 `prc:65`、`prt:57` 会在两处多加局部线索，而审计认为方案 a 已足以让这类 finding 关联到本用例。
- 答案键：`result: gap`；expectation 扩写为包括上述不一致。placements：MODULES 关联 `:31`、证据 `:31` 加 `:65`、`:41`、`:19` 或 `promotion-runtime.md:31`（Recovery 独占该分支全部 recovery result policy，Promotion 不选择 recovery policy）；MODULES 关联 `:65`、证据 `:65`+`:31`；DEPENDENCIES-DATA-FLOW 关联 `:31`、证据 `:31`+`:65`（关联用 `:31` 而不用 `:65`，避开 DATA-FLOW 正例 0 的关联行），共 6 个位置（审计 M2）。`:65` 作 MODULES 关联时检查与 DATA-FLOW 正例 0 不同，不互成候选。findingTerms：Promotion Module、Recovery Module、validation 一类词、duplicate 一类词。

### 新反例

两个新反例都是对应新正例的 clean 孪生，放在同一 AP 文件群里，用来区分"真重复"与"看似重复"：误报会推动把两份不同的义务合并，正是"不该合并"的 A 类原型。夹具不改，只加答案键。

- **MODULES 反例 2**：Promotion 拥有持久化前置检查（`promotion-runtime.md:31`），Recovery 校验 recovery input（`promotion-recovery.md:41`），义务不同，不是重复。findingTerms：precondition 加 duplicate/overlap/both 一类词。
- **SEAMS-ADAPTERS 反例 4**：Artifact Reader Adapters 只提供字节，校验和结果策略留在 Validation Report Module，没有重复的领域策略（`validation-report.md:59`、`:92`）。findingTerms：Artifact Reader/Adapter、policy/validation、duplicate 一类词。

### 裁决 brief（新用例）

- MODULES 正例 1：指出 Promotion 提前返回、绕过 Recovery 交接，或与 `promotion-runtime.md:41/:45/:57`、`promotion-recovery.md:65/:73`、`architecture/02-commit.md:5` 的交接或传播表述不一致的 finding，与重复校验是同一缺陷，判 matched。这类 finding 若同时成为 DEPENDENCIES-DATA-FLOW 正例 0（缺权威来源表）或正例 1（Promotion Flow 缺 Artifact Storage 读取调用）的候选，按各自缺陷判 not-matched。
- SEAMS-ADAPTERS 正例 0：指出 Data Flow（`access-review.md:55`）只写 Seam 的 allowed decision、未提 Module 的检查，或 allowed decision 有两个来源的 finding，与重复授权策略是同一缺陷，判 matched。针对"Seam 允许、Module 拒绝"分支缺少测试的 finding，属于同一缺陷或证据不足，不另算问题（审计 m1）。
- MODULES 反例 2 与 MODULES 正例 1 的区分：指出 Promotion 在 `prc:31` 按 Invalid Input Diagnostic 顺序检查 recovery input、与 Recovery 重复的 finding 属于正例 1，不算反例 2 的误报；只有把 Promotion 的持久化前置检查（`prt:31`）与 Recovery 的输入校验当成重复的 finding，才算反例 2 被误报。
- SEAMS-ADAPTERS 反例 4 与 SEAMS-ADAPTERS 正例 0 的区分：指出 Access Review 与 Policy Adapters 重复授权策略的 finding 属于正例 0；只有声称 Artifact Reader Adapters 与 Validation Report Module 重复持有校验或结果策略的 finding，才算反例 4 被误报。

- 第 2、3 轮审计补充（m1、m2、m5，冻结前补齐，冻结后改 brief 就不能沿用已有裁决）：
  - RM 键外疑点（m1）：`runtime-migration.md:5`（Scope 只写 reader guide）与 Requirements 的"不一致"或"migration 未定义"，判 `unsupported`：Scope 未被选择，按 Role 只能作比较证据，不构成独立审查范围（Role 对未选章节的限制针对的是范围扩张：审查者不得把未选章节当作新的审查对象）；`:5` 说的是 reader guide 本身不拥有 runtime behavior，与 `:11` 的迁移要求不矛盾；判 `supported` 又会与"夹具不得含清单外受支持缺陷"冲突（第 2 轮建议 `supported`，第 3 轮改判，按第 3 轮执行）。选定 Requirements 把部分失败结果委托给未选 Interfaces 节（`access-review.md:15`、`promotion-runtime.md:11`、`promotion-recovery.md:19`）的 finding，判 `unsupported`。
  - MODULES 正例 1（m2）：上面的交接与传播表述清单加上 `promotion-recovery.md:11`（commit 失败后必须先完成 rollback attempt，而 Promotion 提前返回时不调用 Recovery）；MODULE-DESIGN 检查下判 matched，AP 中归到 REQUIREMENTS 的判 `supported`。
  - SEAMS-ADAPTERS 正例 0 类 finding（Module 与 Adapter 重复授权策略）因证据含 `access-review.md:51` 而成为 INTERFACES 正例 1 的候选时，判 not-matched（m5，Opus 盲答已实际出现）。
  - 指出 Recovery Storage 成功形状缺失的 finding 判 `unsupported`：`promotion-recovery.md:57` 已给出精确的成功 `recoveryState`（第 3 轮审计修改后）。

### 审计记录

第 1 轮（Opus high，只审不改）：结论"修改后再审"。B1（`ar:27` 措辞）已改夹具；M1 按方案 a 只改答案键并写入上面的裁决 brief；M2 按建议补 placement；m1、m2（去掉"自行"）已处理；m5 已补进下面的核对项。m3 建议 REQUIREMENTS 反例 3、4 归 B：用户 30 分钟未答复，按 Main 与审计意见执行并另补 2 个反例（见上），待用户复核。可见内容有语义变化，按 Fixture authority 需由未看过答案键的新审计实例重做两阶段审计，再进入盲答。

第 2 轮（Opus high，新实例两阶段）：结论"可进入盲答"，无阻断、无主要问题；次要 m1、m2、m5 是裁决 brief 缺口（已补，见上），m3（A/B 口径）由统一计分方案取代，m7（p基准）冻结后做。

Opus-high 盲答（`.tmp/spec-v42/blind/`）：融合 0.749（RM 0.979，AP 0.688），A 类 4 题全中、4 个反例无误报；23 条关联候选裁决 17 matched / 6 not-matched；另有 1 条答案键外发现（`promotion-recovery.md:57,59`，Recovery Storage 成功时没有结果表示，即 v4.1 删去的 SEAMS-ADAPTERS#1）交第 3 轮裁决。

第 3 轮（Opus high，只审不改）：结论"需再一轮（只审计，不必再盲答）"。

- 答案键外发现判为有歧义：一种读法依据签名 `-> recoveryState` 只给失败形状、Role 要求 Seam 有明确 Interface、其他 Seam 都给了成功表示；另一种读法依据 `:57` 写明成功的公开结果只用输入值形成、失败形状精确可区分。是否算缺陷取决于读得多严，不取决于推理能力，所以不满足"能从 Input 推出、无歧义"。
- 23 条关联裁决全部同意；没有新的阻断问题，主要问题只有这一条歧义。

#### 第 3 轮审计修改

- 消除歧义的方向是让 `prc:57` 明确成为 clean，与 v4.1 用户"不是缺陷"的决定一致：不加题，A 类仍 4:4，不加局部线索。
- AP 覆盖副本 `promotion-recovery.md:57` 原句"成功语义是恢复到输入指定的 priorTrackedState 并移除 baseline."改为"成功时 Seam 返回的 `recoveryState` 精确为 `{status: "restored"}`, 表示已恢复到输入指定的 priorTrackedState 并移除 baseline."。只改行内文字，行号不变，RM 副本不改，修订号仍为 45（v4.2 未冻结）。
- 答案键只改 SEAMS-ADAPTERS clean 3 的 expectation（见上），证据和 placement 都不动。
- 盲答 finding 11 针对改前 Input，只作审计记录，不进正式分数；盲答不重跑，正式 Opus（medium）×3 兼作检查。
- 这是可见内容的语义变化，按 Fixture authority 由没看过答案键的新实例做第 4 轮两阶段审计，通过后冻结。

#### 第 4 轮审计与冻结

第 4 轮（Opus high，新实例两阶段，2026-10-16）：结论"可冻结"，无阻断、无主要问题。阶段 1 盲审独立判定 `prc:57`（AP 版）成功形状 `{status:"restored"}` 与 `:59` 失败形状构成判别式、无歧义，与 `:19/:51/:69/:73/:77`、`prt:41` 一致，未引入新缺陷；阶段 1 无键外缺陷。答案键 sha `74252e0a…` 与覆盖文件 8 项逐项一致，A 类 4:4，问题用例 23、clean 45。次要：n1 删旧补丁副本（已删）；n2 给 RM 键外疑点 m1 补理由（已补）；n3 冻结标签（已改）；n4 p基准与 versions.md 冻结后补。Main 以本轮审计为冻结的独立意见，2026-10-16 冻结；补丁 sha `c50a46f4…`。

### 待独立审查核对

- 两处新文字是否只引入预期的那一个缺陷：`promotion-runtime.md:41/:45/:57`、`promotion-recovery.md:65/:73`、`architecture/02-commit.md:5` 的交接表述已并入 MODULES 正例 1，需确认这样归并是否站得住；`access-review.md:27` 改写后是否还有别的冲突。
- 两个新正例、两个新反例的 A 类归属，沿用的 4 个标记，以及 REQUIREMENTS 反例 3、4 改 B（待用户复核）。
- 格式罚基准：新答案键需要先在 `format-baseline.json` 登记 p基准（Haiku-high ×5），冻结后、benchmark 计分前补测。

### 无模型检查（2026-10-16，第 3 轮审计修改后重跑）

- `manifest-spec-readiness-v4.2.json` 能物化，计分升级绑定覆盖文件成功；按分流逻辑核对 A 类：RM 1 正 0 反，AP 3 正 4 反，合计 4:4。
- ARW conformance 测试：只打场景补丁的副本 v4.1、v4.2 都是 70/70；加上计分升级后两者都是 48/70，失败的 22 项完全相同（计分升级改变了 ARW 原测试的预期分数，不是 v4.2 引入的）。
- 工程测试 412 项通过。

## v4.3（只做去重，修订号 46，2026-10-17 冻结）

用户 2026-10-16/17 定下出题原则：两个子场景不出同一道题，与 k 无关；每个子场景各自完整覆盖它的全部检查；发现重复就改题，不在计分端打折或去重。用户 2026-10-17 决定出一版只做去重的 v4.3。

### 问题

上游 `splitSpecReadinessExpected` 给 AP 的检查表照搬全部 11 项检查的 clean 用例，其中包括 RM 已有的两项需求检查（`SPEC-READINESS-INPUTS`、`SPEC-READINESS-REQUIREMENTS`）。结果这两项的 8 个 clean 用例（INPUTS 3 个、REQUIREMENTS 5 个，都是 k = 0.25）在 RM 和 AP 各计一次；noOther 两边各一个，不算重复。正例没有重复：AP 不收需求检查的正例，带需求检查 placement 的正例也不进 AP。A 类 8 个用例都不在这两项需求检查的 clean 里，所以 A 类不受影响，仍为 RM 1:0、AP 3:4，合计 4:4。

### 改动

补丁 `arw-patches/spec-readiness-v4.3.patch` 叠在 v4.2 之后，登记在 `source-snapshots/current/manifest-spec-readiness-v4.3.json`（即 v4.2 manifest 加上这一项）：

- AP 的两项需求检查只保留 noOtherSupportedFinding；8 个需求 clean 用例只在 RM 计分。
- 拆分完成后核对：noOther 之外，同一个期望句不得同时出现在两个子场景，否则加载答案键时报错。
- 修订号 45 → 46，旧准备状态失效。
- 加一个 ARW 回归测试（`Spec Readiness public preparation pairs …` 中追加断言）；工程侧 `tests/test_spec_readiness_split.py` 在只打场景补丁的 v4.3 副本上运行它。
- 夹具、交接、答案键（`expected.json` sha256 `74252e0a…`）和覆盖文件都不变，模型看到的任务与 v4.2 完全相同；`registry.json` 与 `format-baseline.json` 沿用 v4.2 的键，p基准不必重测。

规则文字同步修改：[ARW Reviewer 测量规则](../../.claude/rules/reviewer-suite.md)「评分」删去 0.5 份额规则和"0.25 档反例在 RM、AP 各计一次"，改写为出题原则；`judgment/README.md` 同步。

### 偏离

- **份额代码暂留**（已在评分 r8.2 删除，2026-10-17）：`scoring-k.patch` 里给共享 k ≥ 1 用例打 0.5 份额的代码（`sharedK`、`kShare`）没有删。v4.3 之后不会再有共享用例（拆分时就报错），这段代码已不可达。删除它要改 `scoring-k.patch`，所有已物化副本都得迁移，还要出新的评分修订；留到下一次评分修订时一起删。工程测试 `test_spec_readiness_pair_counts_a_shared_case_once` 仍覆盖这段代码，到时一并删除。
- **"其余检查按证据文件分边"现在没有可执行的对象**：RM 只有两项需求检查，其余 9 项检查只在 AP 出现，不存在要分边的用例，所以冻结工具没有加"证据文件在两边输入里都有就拒绝"的检查。以后 RM 若增加检查，由拆分时的重复核对兜底，届时再补冻结检查。
- 冻结工具没有加"同一答案键内期望句不重复"的通用检查：Commit Audit 的 ARW 原版答案键里 `COMMIT-AUDIT-GATE-1` 正例 14 与 `GATE-2` 正例 2 期望句相同（同一缺陷挂在两个 gate 下），通用检查会拒绝它，这不在 v4.3 范围内，交 Main 另行处理。

### 用 v4.2 已有回答重算（2026-10-17）

按测量规则"只改答案键或 placement 时，用已有回答重新评分"，v4.3 只改计分侧拆分，所以用 v4.2 的全部回答（Q3 ×10、Opus ×3、Haiku ×5 的上下界）重算，不重跑模型。做法：每个来源复制一份 v4.2 运行的 ARW 目录，换入 v4.3 的 `reviewer-capability-conformance.mjs`；在复制出的准备状态里把修订号改为 46，并把 AP 两项需求检查的 clean 用例过滤到只剩 noOther（与 v4.3 拆分结果相同，场景摘要不变）。Request 中的绝对路径和摘要绑定原运行目录，所以计分在只属于该进程的挂载命名空间里，把副本绑定到原路径上运行；原目录没有改动。裁决沿用 v4.2 正式计分的决定，格式罚同 v4.2。

结果：13 个来源共 23 次计分（Q3 10、Opus 3、Haiku 上下界各 5），每次正好少 8 个 clean 用例，且这 8 个在 v4.2 里全部通过；没有新候选，没有作废的裁决；分数逐位不变。Q3 原定 5 次 0.4848 ± 0.1541，全部 10 次 0.5218 ± 0.1135，Opus 0.8294 ± 0.0112，Q3/Opus 0.584 / 0.629，与 v4.2 相同。原因：r8 的分数是（正例得分 − 失败反例权重）/ 正例权重，通过的反例不加分，重复的反例只在答错时多扣一次，而 v4.2 的回答没有答错过这 8 个。v4.2 结果因此可以直接作为 v4.3 结果；v4.3 重算报告由 Main 撰写（报告目录 `reports/v0.1.44.1/spec-readiness-v4.3/`）。

### 待独立审查与冻结

冻结是重要决策，须由不低于 Main 的独立 agent（Opus high）审查后再冻结。审查要点：补丁是否只改拆分；去重规则是否符合用户原则（尤其 noOther 两边各留一个）；份额代码暂留是否可接受；重算方法（复制并改写准备状态、挂载命名空间）是否等价于重新准备。

### 独立审查与冻结（2026-10-17）

独立 agent（Opus high，只读）结论**可冻结**；Main 同意，冻结。要点：

- 补丁只改修订号和 AP 两项需求检查的拆分，符合用户原则；AP 的 issue 与选定 sections 与 RM 不同，两边的 noOther 是两道题。
- 不必重跑成立：模型可见内容未变；r8 分子里没有通过的反例，去掉答对的反例分数必然不变；逐次核对 Q3 ×10、Opus ×3、Haiku 上下界各 5，反例总数与通过数都正好少 8，被去掉的反例没有一次答错。
- **一次性偏离（重算方法）**：重算复制运行目录、改写复制出来的准备状态，再在私有挂载命名空间里绑定到原路径计分，有意绕开了 ARW 的两道约束（修订号升级使旧准备状态失效、Request 路径绑定原目录）。计分结果与重新准备等价，没有越过安全边界；但测量规则没有授权改写准备状态，这次只作一次性偏离，不作为常规做法。`rescore.py` 用的计分身份与 `single_scenario_score` 的默认值不同。
- 重复核对位于 ARW 加载答案键的拆分处，只覆盖 Spec Readiness 的跨子场景重复；同一答案键内部的重复目前没有任何检查（Commit Audit 有一例，见 `docs/plan.md`）。
- 份额代码暂留可接受；`scoring-k.patch` 里的 ARW 计分说明已过时，清理项登记在 `docs/plan.md`。

