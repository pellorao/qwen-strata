# Spec Readiness 规则、场景与评分审查（rtx3080ti，Strata v0.1.42）

日期 2026-10-13。用户 2026-10-13 决定 Spec Readiness 不再做 Qwen 模型测试，转为只读分析：先检查规则冲突，再分析场景与标准答案，然后逐案例复评；并用 Opus（effort medium）完整跑 3 次作为每个评分项的对照。前置调查见 [低分主因调查](../spec-cause-investigation/summary.md)。

## 结论

1. **Qwen 低分不是评分或裁决造成的，原因是 artifact-promotion（AP）漏检多。**
   - 按 ARW 原版评分加本工程的格式修复和裁决，独立重算了 8 个 IQ3_XXS 实例（medium ×3、方案 A 诊断 ×3、F6 批 b ×2），融合分逐个与原值完全一致。
   - 121 个候选逐条复核，判定无一改变。
   - 敏感性检查：把 SEAM2、IF7 移出分母，再恢复 AP 全部 noOther 洁净用例，分数最多只升 +0.05。
   - 本工程改动的评分口径（格式修复补丁、repair 工具）在这些批次里都没有作用到 Spec Readiness。
2. **Opus 对照（3 次，同规则、同交接、同评分）明显高于 Qwen，但也有一批用例同样全漏。**
   - 融合分 0.638（0.619 / 0.624 / 0.673），没有扣罚；Qwen IQ3 各批扣罚前 0.418–0.511。
   - AP 单段 0.551，Qwen 0.26–0.39。
   - 同样全漏的有 7 个：RATIONALE、IF7、SEAM2、DEP2、MR2、MR3、MR4。
   - 差距分两部分：IF3、IF5、IF6、IF4、IF2、APPLICABILITY 等 Opus 稳定检出、Qwen 多半漏掉，是模型能力问题；上面 7 个双方都漏的用例，更像标准答案或场景设计偏严、有歧义，或与"同一缺陷不跨检查复制"的角色规则冲突。
3. **RM 的 ×0.9 扣罚是 Qwen 的行为问题，不是规则冲突。** Opus 三次 runtime-migration（RM）都在 REQUIREMENTS 缺口后按规则停下，没有 `requirement-scope-continuation`；Qwen 多数实例越界继续审 Module Design。
4. **最大的规则偏差是"合并实例"（C1）。** 同一线程先审 RM 再审 AP，偏离了 ARW 准备规则（每个实例用全新根线程，看不到其他实例的结果）。原授权只覆盖上下文维度，后来成了 Spec Readiness 的通用做法；有跨实例污染的证据。
5. **场景里有未登记的真实缺陷**，会让 noOther 洁净用例失败、拉低 CAR（见场景分析）。

## 一、规则冲突清单

| 编号 | 严重度 | 内容 | 影响 |
|---|---|---|---|
| C1 | 重 | 合并实例：RM→AP 同一线程连跑（reviewer-suite.md 定义）。ARW preparation 第 27 行要求"每个 instanceId 对应一个独立线程和一次审核"，第 13 行要求实例互不可见。compaction-options.md:83 写明这个授权"不扩展到其他批次"，现在却是通用规则 | 结果不能与 ARW 基线直接比较；AP 受 RM 上下文污染 |
| C2 | 轻 | measurement.md「评分口径」写 Spec Readiness 证据"以 Input 完整 filePath 开头"，但 findings.md 允许同一文件后续片段省略路径 | 只是文档不准，工具不受影响 |
| C3 | 轻 | format-normalized-scoring.patch 接受格式修正，并放宽 markdown 的 `review-evidence-invalid`，是对 ARW 的偏离 | 这些批次的 Spec Readiness 归一都是 `changes: {}`，没有生效 |
| C4 | 无 | 裁决方式：先按 placement 和 associationEvidence 过滤，再由 Main 判定，不用 findingTerms | 与 ARW 定义一致；建议理由写实质依据，不用模板句 |
| C5 | 中 | 角色规则说"同一缺陷从另一端…修订既有行，不跨检查复制"，但答案键把同一根因拆成 IF2（INTERFACES）和 SEAM2（SEAMS）两个用例 | 遵守角色规则的模型最多拿到其中一个 |

C1 的污染证据（Qwen）：

- medium AP1 的 findings 照搬 RM1 后段的 findings。
- AP 的 REQUIREMENTS 里出现 runtime-migration 冲突（该规格在 AP 中没被选定）：medium AP2 [0]、AP3 [1][2]，诊断 AP2 [0][1]。这些 finding 导致 REQ 的 noOther 失败。
- 诊断 AP1 引用了"固定的 restore-failed 码"，这个约定只存在于 RM 版 promotion-recovery。
- Opus 三次 AP 都没把 RM 内容带进来，但也主动比对了 RM 与 AP 的 request JSON（两个场景根都允许读）。

没有发现明文引导"每个检查只报一条"的措辞，规则要求的是完整清点。问题出在 C5，以及 MODULE-DESIGN-RATIONALE"逐文档清点"的要求很严（MR2–MR4）。

## 二、场景分析（标准答案可疑项）

逐个读了 RM、AP 的 Inputs、交接和 expected 用例。

| 用例 | 判断 | 理由 |
|---|---|---|
| SEAM2（Policy Evaluation 通用失败契约） | 可疑：与 IF2 重叠 | 根因与 IF2（Policy Adapter 失败结果缺失）相同，只允许放在 SEAMS，associationEvidence 是 access-review:51。按 C5，模型应只写一条，常见写法放在 INTERFACES。Qwen 0/8，Opus 0/3（三次都只报 IF2） |
| IF7（诊断 path 如何从 source 取得） | 可疑：依赖 IF6 | 把 source 定义为路径（IF6）就同时解决了 IF7。模型都报了 IF6（Opus 3/3），没有人另报 IF7。Qwen 0/8，Opus 0/3 |
| RATIONALE（access-review 通用 rationale 缺行为替代方案） | 偏严 | access-review:19 有 rationale，只是没写替代方案；模型容易把精力放到 Module Design 的 Boundary Alternative（MR1）。Qwen 1/8，Opus 0/3 |
| MR2（policy authority 选择） | 偏严，可辩护 | context/02 已经确定了 authority，模型倾向于认为不需要再论证。双方 0 |
| MR3（AR→Policy Seam 方向） | 偏严，可辩护 | 双方 0 |
| MR4（promotion-runtime:61） | 偏严 | 理由在另一份文档（promotion-recovery:83）里有，角色要求逐文档清点，严格但说得通。双方 0 |
| DEP2（Promotion Flow 缺 Artifact Storage 读取调用） | 有效 | 能从 Inputs 推出；双方 0，难度高 |
| SEAM1（Recovery Storage 成功形状） | 有效 | Opus 1/3，Qwen 0/8 |
| DEP1（缺权威来源表） | 有效 | Opus 1/3，Qwen 2/8 |

未登记缺陷（ARW 要求 fixture 不得含有未列出、但能成立的缺陷）：

- **(a) retention 策略执行方矛盾**：promotion-runtime:15 写 Reviewer 执行，45/57/67 写 Readiness 执行。Qwen 在 ≥6 条 finding 里报过，Opus AP3 也报了。基本可以确定是真实歧义。
- **(b) 原始提交失败码没有传入 Recovery 的输入**：输入是 `{artifact, priorTrackedState, failedCommitId}`。Qwen（F6b AP1 [7]、诊断 AP1）和 Opus AP1、AP2 都报了。很可能是真实缺陷。
- **(c) AP 版 rules/02** 写"External retention policy 适用于本次 artifact promotion 与 access review"，但 access-review.md:5 说不修改 retention policy，也没有任何落实。Opus AP1、AP3 报了。可能是故意设置的干扰项，需要上游确认。
- 较弱：persist 失败字段"上述完整结果字段"含义不清；diagnostic-wording 与 promotion-runtime 对非法 inputPath 的描述不一致（Opus AP3 [11] 也报了）。

另外，AP 的 request 把没被选定的 runtime-migration.md 标成 "governing-spec" 提供给模型，会诱导模型产生 REQ finding。

## 三、逐实例复评

方法：ARW 原版评分 + 格式修复（实际没有修改）+ 独立复核全部候选。

| 实例 | 原融合分（扣罚前） | 复评 | 差异 |
|---|---|---|---|
| medium 1 | 0.3382 | 0.3382 | 0 |
| medium 2 | 0.4784 | 0.4784 | 0 |
| medium 3 | 0.4385 | 0.4385 | 0 |
| 诊断 1 | 0.4786 | 0.4786 | 0 |
| 诊断 2 | 0.6193 | 0.6193 | 0 |
| 诊断 3 | 0.4338 | 0.4338 | 0 |
| F6 b 1 | 0.4730 | 0.4730 | 0 |
| F6 b 2 | 0.5540 | 0.5540 | 0 |

- 候选裁决：medium 40、诊断 50、F6 b 31，共 121 个，全部同意原判定。判为不匹配的都是同一 finding 落到另一个用例的交叉候选。
- 敏感性：只去掉 SEAM2、IF7，+0.03–0.05；只恢复 AP noOther 洁净用例，≤ +0.006；两项一起最多 +0.05。原因是 AP 的 PDR 只有 0.14–0.47，CAR 已在 0.86–1.00，决定分数的是漏检。
- F6 批 a 的原始 draft 已删除，未复评。

## 四、Opus 对照

条件：

- 新准备的冻结 ARW 批次，工作区内没有 expected 或评分文件。
- 交给 Opus 的材料与 Qwen 相同：角色文档、交接、测量说明、输出格式。每个 agent 在同一会话里先审 RM 再审 AP，模拟合并实例；按 2+1 分两批运行。
- 与 Qwen 的差异：没有接入项目启动提示和压缩提示；运行环境是 Claude Code，不是 Codex。

隔离核查：逐条检查了三个会话的全部工具调用。只读了两份说明、两个场景根内的 `AGENTS.md`、`docs/agents/*` 和 request JSON；只写了各自绑定的 draft；没有读 expected、评分代码、旧报告或其他运行。三次全部有效。

评分：流程与 Qwen 相同（完整评分 [opus-score.json](opus-score.json)，逐候选裁决 [opus-adjudication.json](opus-adjudication.json)）。RM 经 ARW generate 生成 artifact（三次都成功，说明没有越界继续审），AP 直接用 draft。72 个候选，47 个匹配、25 个不匹配，逐条裁决并写了实质理由。

| 次 | 融合（扣罚前 = ARW 原版） | RM | AP | AP PDR | AP CAR | 用时 | 请求 | 输出 token |
|---|---|---|---|---|---|---|---|---|
| 1 | 0.6187 | 0.970 | 0.519 | 0.467 | 0.930 | 5.2 分 | 12 | 26.6K |
| 2 | 0.6240 | 0.970 | 0.525 | 0.472 | 0.953 | 4.4 分 | 15 | 20.9K |
| 3 | 0.6726 | 0.908 | 0.609 | 0.565 | 0.884 | 5.4 分 | 17 | 无法核实 |
| 均值 | 0.638 | 0.949 | 0.551 | 0.501 | 0.922 | 5.0 分 | | |

- RM3 为 0.908：export-retention 用例写成了 `gap`，标准是 `uncertain`。
- 对照：Qwen F6 扣罚前 0.436 / ARW 原版 0.404，AP 0.292；方案 A 0.511 / 0.459，AP 0.392；medium 0.418 / 0.391，AP 0.262。

逐用例检出（AP；Qwen 为复评的 8 个实例）：

| 用例 | Qwen | Opus | 解读 |
|---|---|---|---|
| RATIONALE | 1/8 | 0/3 | 双方都漏，答案偏严或位置不显眼 |
| ADR | 7/8 | 3/3 | — |
| APPLICABILITY | 5/8 | 3/3 | 能力 |
| EXEMPTION | 8/8 | 3/3 | — |
| MODULES | 6/8 | 3/3 | — |
| IF1 已验证主体 | 2/8 | 1/3 | 难 |
| IF2 Policy Adapter 失败 | 5/8 | 3/3 | 能力 |
| IF3 failureCode 取值 | 2/8 | 3/3 | 能力 |
| IF4 回滚失败测试 | 5/8 | 3/3 | 能力 |
| IF5 unexpected-field 顺序 | 1/8 | 3/3 | 能力 |
| IF6 source 类型 | 1/8 | 3/3 | 能力 |
| IF7 诊断 path | 0/8 | 0/3 | 答案可疑（依赖 IF6） |
| SEAM1 | 0/8 | 1/3 | 难，有效 |
| SEAM2 | 0/8 | 0/3 | 答案可疑（与 IF2 重叠，C5） |
| DEP1 | 2/8 | 1/3 | 难 |
| DEP2 | 0/8 | 0/3 | 双方都漏，有效但难 |
| MR1 | 5/8 | 2/3 | — |
| MR2 / MR3 / MR4 | 0/8 | 0/3 | 双方都漏，逐文档清点要求过严或不显眼 |

- 后段检查表（SEAMS、DEPS、RATIONALE）：Opus 也基本漏检，这一段的低检出不能只归因于 Qwen 能力。
- INTERFACES：Opus 7 个里检出 5–6 个，Qwen 平均约 2 个，这一段差距主要是能力。
- 洁净用例失败：Opus 也失败在 REQ、MODULES、INTERFACES、DEPS 的 noOther 上，起因是未登记缺陷 (a)(b)(c) 以及 Opus 额外报出的缺陷。

## 五、建议

1. 单独测一次全新线程的 AP（不带 RM 上下文），量化 C1 的污染影响；在 reviewer-suite.md 写清合并实例与 ARW 的差异和适用范围，或者恢复为独立线程。
2. 修正 measurement.md 中 Spec Readiness 证据定位的描述，补上同一文件后续片段可以省略路径（C2）。
3. 裁决理由写实质依据，不用模板句（C4）。
4. 向 ARW 上游报告：SEAM2 与 IF2 重叠；IF7 依赖 IF6；未登记缺陷 (a)(b)(c)；AP request 把没被选定的 runtime-migration 标成 governing-spec；MR2–MR4、RATIONALE 偏严。
5. 调参或评估时以 Opus 对照为参考上限（AP PDR 约 0.50，融合约 0.64）；答案键修好之前，不要把高 AP 阈值当作 Qwen 的目标。

## 未验证项

- Opus 对照没有接入项目启动提示和压缩提示，运行在 Claude Code 而不是 Codex，与 Qwen 条件不完全相同。
- Opus 只有 3 次，SEAM1、DEP1、IF1 这类 1/3 的检出率不稳定。
- Opus 也用合并实例，不能用它分离污染效应。
- 第 3 次 Opus 的输出 token 无法从会话记录核实（harness 统计的子 agent token 为 151.7K / 134.9K / 144.2K）。
- 未登记缺陷 (a)(b)(c) 是审查者和两个模型的判断，ARW 作者没有确认。
- 用例与检查类别的对应按评分输出中 scope 的顺序推定。
