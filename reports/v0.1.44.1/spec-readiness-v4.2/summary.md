# Spec Readiness v4.2 正式测量（v0.1.44.1，Q3 ×10）

## 结论

- **评分 r8 下 Q3/Opus 低于 0.8**：Q3 原定 5 次 **0.4847 ± 0.154**，全部 10 次 **0.5218 ± 0.1135**；Opus（medium）×3 **0.8294 ± 0.0112**；Q3/Opus = **0.584**（原定 5 次）/ **0.629**（全部 10 次），都低于 0.8，场景对 Q3 仍有区分空间。
- **暂不宜用于调参（待定）**：原定 5 次 SD 0.154、10 次 SD 0.1135，都远超 r7 尺度下的 0.068 标准（v4.1 报告同一标准）；r8 尺度的 SD 阈值尚待用户定（同时看截断前的 `rawScore`），定下后再复核这一结论。在此之前 v4.2 只用于能力验证和 benchmark。
- **p基准**：Haiku-high ×5 的格式合格数 sumR 0、sumT 414，pBase 0.0241546（floor），bootstrap 90% 区间 [0.01996, 0.03030]；登记在 `benchmarks/reviewer-suite-v1/format-baseline.json`（expected 键 `74252e0a…`），存档 `benchmarks/reviewer-suite-v1/format-baseline/spec-readiness-v4.2/`。
- **区分度来自少数用例**：23 个用例中只有 MD-RATIONALE#2 双方 0 命中，是有效难题（见"逐用例命中"）。Q3 落后主要在 MD-INTERFACES#4、MD-RATIONALE#1（0/10，Opus 2/3、3/3）和 MD-INTERFACES#3、MD-DEPENDENCIES-DATA-FLOW#1、SR-REQUIREMENTS#3、MD-MODULES#0；反过来 MD-INTERFACES#5 是 Q3 6/10、Opus 0/3。
- **Q3 波动大，使用受限**：单次分数没有意义（10 次在 0.344–0.696 之间）；10 次时比值约 ±0.04，每组 10 次只能检出约 0.14 以上的差异；引用结果必须带次数和区间（见"SD 带来的使用限制"）。
- **全部 10 个 Q3 实例有效**：会话检查未发现压缩、早退或禁止来源访问；所有实例的罚分项 r = 0，罚前分等于罚后分。
- **适用范围**：只对 rtx3080ti、IQ3_XXS、Strata 0.1.44.1、Codex 0.162.0、effort high 成立。分数只在 v4.2（修订号 45）内、同为 r8 口径下比较；与 v4.1（r7.1）不直接比分。
- **v4.2 定为 Spec Readiness 定版场景，不再加难**（2026-10-17，Main 与独立审查意见一致，见"独立审查意见"）。这是场景内部的决定，所以登记在 `versions.md`，不写进 README「现行决定」；待用户复核。

## 运行

- 时间：2026-10-16 起跑，10-17 完成后处理与计分。Q3 共 5 批：A（让位前只完成 2 次）、Ar（补 A 让位剩下的 1 次）、B、C、D；原定 5 次为 A、Ar、B（共 5 次），加测 5 次为 C 3 次、D 2 次，目标次数事先写定为 10。
- 条件：rtx3080ti，IQ3_XXS，Strata 0.1.44.1，Codex 0.162.0，effort high；冻结夹具修订 45，答案键 sha256 `74252e0a…`，A 类正反 4:4。计划：`benchmarks/reviewer-suite-v1/spec-readiness-v4.2-iq3_xxs-2026-10-16-v0.1.44.1/plan.json`。每个实例的 RM、AP 各用一个全新根线程。
- 参考：Opus 5.5 medium ×3（Claude Code 无头，每次约 7 分钟）；Haiku 5.5 high ×5，只用于机械区间和 p基准。
- 计分：评分 r8（按 k 分档的统一计分）；候选先经盲裁，Q3 与 Opus 同口径。
- 中途让位：2026-10-16 21:5x 因 Claude Code 重启让位，A 批只完成 2 次，其余按"运行"所述补跑；Opus ×3 在让位前已完成。

## 逐实例

| 次 | 批 | 组 | r8 分 | T | 分钟（RM+AP） | read | reused | generated | 引擎入/出 tok/s | 任务入/出 tok/s |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | A1 | 原定 | 0.588 | 80 | 16.1 | 149,055 | 3,079,072 | 72,052 | 1,517 / 88.0 | 154.0 / 74.5 |
| 2 | A2 | 原定 | 0.448 | 36 | 16.0 | 154,568 | 3,110,496 | 72,551 | 1,505 / 86.9 | 161.5 / 75.8 |
| 3 | Ar1 | 原定 | 0.696 | 74 | 19.7 | 151,017 | 4,326,440 | 88,841 | 1,422 / 86.4 | 127.5 / 75.0 |
| 4 | B1 | 原定 | 0.344 | 41 | 15.1 | 141,426 | 2,881,647 | 68,026 | 1,492 / 88.9 | 155.7 / 74.9 |
| 5 | B2 | 原定 | 0.348 | 60 | 14.8 | 133,723 | 2,875,372 | 70,884 | 1,571 / 90.6 | 150.8 / 79.9 |
| 6 | C1 | 加测 | 0.610 | 61 | 15.9 | 151,592 | 2,954,040 | 70,452 | 1,558 / 87.3 | 159.1 / 74.0 |
| 7 | C2 | 加测 | 0.504 | 79 | 12.7 | 129,096 | 2,587,437 | 57,592 | 1,511 / 87.4 | 169.2 / 75.5 |
| 8 | C3 | 加测 | 0.563 | 65 | 15.0 | 169,300 | 2,732,398 | 68,674 | 1,629 / 88.4 | 188.2 / 76.3 |
| 9 | D1 | 加测 | 0.530 | 60 | 16.5 | 133,292 | 3,322,970 | 73,803 | 1,423 / 87.4 | 135.0 / 74.7 |
| 10 | D2 | 加测 | 0.588 | 67 | 16.9 | 174,710 | 3,693,802 | 77,963 | 1,565 / 88.7 | 172.8 / 77.1 |

T 为格式检查的总数。分钟为 RM 与 AP 合计。引擎速度为模型直接速度，任务速度为用户感知速度。

Opus 参考（medium）：

| 实例 | r8 分 | T |
|---|---|---|
| opus-1 | 0.842 | 68 |
| opus-2 | 0.826 | 77 |
| opus-3 | 0.820 | 79 |

Haiku-high 机械区间（只用于 p基准，不计入 Q3/Opus 比值）：

| 实例 | 上界 | 下界 | T |
|---|---|---|---|
| haiku-1 | 0.787 | 0.000 | 121 |
| haiku-2 | 0.203 | 0.000 | 51 |
| haiku-3 | 0.700 | 0.000 | 91 |
| haiku-4 | 0.728 | 0.000 | 74 |
| haiku-5 | 0.837 | 0.000 | 77 |

## 评估

- 盲裁：单个 Opus-high 盲裁决者，隐去批次、实例和线程。池含 270 个新候选和 12 个锚点（v4.1 已裁、v4.2 未改检查、期望句逐字相同；8 matched、4 not-matched），锚点 12/12 一致。第二轮 r8 补出 9 个候选：8 个 unsupported，1 个（c003）supported。
- 盲裁的局限：锚点只覆盖关联裁决（matched / not-matched），没有覆盖键外候选的 supported / unsupported；第一轮的 14 个 unsupported 和第二轮 9 项都没有锚点校验。这 23 项每项最多影响所在实例 0.25/23 ≈ 0.011，即使全部翻转，比值变化也在 0.02 以内。
- 可复现性的依据是确定性重算加锚点一致：`final.py` 对每个来源连跑两次上游计分并断言输出一致，锚点 12/12；没有第二个裁决者独立复评（规则允许单裁决者）。
- 候选总数（post.py 后）：Q3 A 38、Ar 22、B 28、C 59、D 39，共 186；Opus 参考第一遍 27 / 29 / 28，共 84；两项合计 270，即盲裁池的新候选。
- 会话检查（20 个 Q3 线程）：全部 complete、终态 ready、0 压缩、启动上下文 SHA 同批一致（user@6 按重复序号一致）、交接都在。标记 39 条全部无害：模型拼错 workdir 或越出根，被拒（命令未执行）；写 /tmp，只读文件系统失败（C AP3 #22、D AP2 #22）；D AP2 #23 为 jq 变量误报；C AP3 e132 是跨零点的 environment_context；D AP1 e163 是 ARW 对空报告的续作提醒（上游机制），随后交付了 10 行报告。无禁止来源访问。
- 速度：引擎入 1,422–1,629 tok/s，出 86.4–90.6 tok/s；每实例 12.7–19.7 分钟。没有降速实例。

## 逐用例命中

命中 = 得分 > 0；Q3 为 10 次中的命中数，Opus 为 3 次中的命中数；编号在每个 scope 内从 0 起，与 `expected.json` 的顺序一致。

| 用例 | Q3 | Q3 均分 | Opus |
|---|---|---|---|
| SPEC-READINESS-INPUTS#0 | 10/10 | 0.86 | 3/3 |
| SPEC-READINESS-REQUIREMENTS#0 | 10/10 | 0.97 | 3/3 |
| SPEC-READINESS-REQUIREMENTS#1 | 10/10 | 0.99 | 3/3 |
| SPEC-READINESS-REQUIREMENTS#2 | 10/10 | 0.99 | 3/3 |
| SPEC-READINESS-REQUIREMENTS#3 | 3/10 | 0.28 | 3/3 |
| SPEC-READINESS-RATIONALE#0 | 7/10 | 0.69 | 3/3 |
| SPEC-READINESS-ADR-EVALUATION#0 | 9/10 | 0.86 | 3/3 |
| MODULE-DESIGN-APPLICABILITY#0 | 7/10 | 0.67 | 3/3 |
| MODULE-DESIGN-EXEMPTION#0 | 9/10 | 0.84 | 3/3 |
| MODULE-DESIGN-MODULES#0 | 3/10 | 0.29 | 3/3 |
| MODULE-DESIGN-MODULES#1 | 6/10 | 0.57 | 3/3 |
| MODULE-DESIGN-INTERFACES#0 | 5/10 | 0.45 | 1/3 |
| MODULE-DESIGN-INTERFACES#1 | 6/10 | 0.59 | 3/3 |
| MODULE-DESIGN-INTERFACES#2 | 4/10 | 0.37 | 3/3 |
| MODULE-DESIGN-INTERFACES#3 | 1/10 | 0.09 | 3/3 |
| MODULE-DESIGN-INTERFACES#4 | 0/10 | 0.00 | 2/3 |
| MODULE-DESIGN-INTERFACES#5 | 6/10 | 0.52 | 0/3 |
| MODULE-DESIGN-SEAMS-ADAPTERS#0 | 9/10 | 0.87 | 3/3 |
| MODULE-DESIGN-DEPENDENCIES-DATA-FLOW#0 | 8/10 | 0.79 | 3/3 |
| MODULE-DESIGN-DEPENDENCIES-DATA-FLOW#1 | 2/10 | 0.18 | 3/3 |
| MODULE-DESIGN-RATIONALE#0 | 6/10 | 0.59 | 3/3 |
| MODULE-DESIGN-RATIONALE#1 | 0/10 | 0.00 | 3/3 |
| MODULE-DESIGN-RATIONALE#2 | 0/10 | 0.00 | 0/3 |

本节在 d2715ae 版本中错位了一格：标成 X#k 的数据实际是同一 scope 的 X#(k−1)，每个 scope 的 #0 都显示 0/0，末项丢失，因此误报"11 个双方 0 命中"。原生成脚本是未保存的内联代码，从症状看是把上游 1 起编号（candidateId 中的 `problem-N`）当成了 0 起编号。现按各来源 `score-final.json` 的 `caseScores.problem` 重算，并用每个 scope 的 `earnedProblemPoints` 核对切片；分数字段不受影响（`summary.json` 中 `cases` 以外的字段改前改后逐值相同）。与 v4.1 ×20 的历史一致（v4.1 报告用 1 起编号），例如 SR-REQUIREMENTS#3 3/10 对 v4.1 的 #4 4/20，EXEMPTION 9/10 对 19/20。

- **唯一的双 0：MODULE-DESIGN-RATIONALE#2**（access-review 的 rationale 没有论证 Access Review Module → Policy Evaluation Seam 的依赖方向）。夹具 `access-review.md:63-79` 确实没有论证这一方向，缺陷成立，placement 有 12 个，不算严。v0.1.42 v4 报告已核查同一用例（当时编号 MD-RATIONALE#3）：缺陷有效，漏检是能力原因，不改；v4.2 的夹具改动没有动 rationale 段。结论：有效难题，下一版不改。
- **Q3 0 命中而 Opus 命中**：MODULE-DESIGN-INTERFACES#4（0/10 对 2/3）、MODULE-DESIGN-RATIONALE#1（0/10 对 3/3）。
- **Q3 明显更少**：MODULE-DESIGN-INTERFACES#3（1/10 对 3/3）、MODULE-DESIGN-DEPENDENCIES-DATA-FLOW#1（2/10 对 3/3）、SPEC-READINESS-REQUIREMENTS#3（3/10 对 3/3）、MODULE-DESIGN-MODULES#0（3/10 对 3/3，k = 1）。
- **Q3 反超 Opus**：MODULE-DESIGN-INTERFACES#5 是 Q3 6/10、Opus 0/3（Opus 3 次全漏），MODULE-DESIGN-INTERFACES#0 是 5/10 对 1/3。Q3 能稳定命中 #5，说明它可以从 Input 推出，不是场景缺陷。
- **批次现象**：B 批两次最低（0.344、0.348），其余 8 次在 0.448–0.696；B1 在 SR-RATIONALE、ADR、DATA-FLOW、MD-RATIONALE 四个检查上整段 0 分。两次样本不足以区分批次效应和偶然；原定 5 次恰好包含整个 B 批，这是原定 5 次均值低于 10 次（0.485 对 0.522）的主要原因。不追查。

## SD 带来的使用限制

- **单次分数没有意义**：10 次在 0.344–0.696 之间，单次的 Q3/Opus 可以从约 0.42 到约 0.84。只能用多次均值，并给出次数和标准误。
- **比值精度**：10 次时 Q3 均值标准误约 0.036，比值约 ±0.04（1 个标准误；90% 区间约 0.46–0.58，比值上限约 0.70）；原定 5 次（SD 0.154）约 ±0.08。能回答"Q3 是否明显低于 Opus"这类分级问题，回答不了"0.60 还是 0.65"。
- **对比两个条件**（调参、版本、量化）：每组 10 次时均值差的标准误约 0.051，只能检出约 0.14 以上的差异；要检出 0.1 左右的差异，每组约需 20 次。r8 阈值定下前不用于调参；按现有数据，阈值放宽后大概率也不适合调参。
- **方差来源**：主要是 Module Design 段整检查掉分（如 B1 四个检查整段 0），加上 k = 1 档 8 个二元用例每个影响 1/23 ≈ 0.043。这是 Q3 的真实不稳定（同一输入时有时无地展开审查），不是计分噪声。
- **报告要求**：引用本场景结果（与其他场景、ARW 原版或其他条件对比）时必须带上次数和区间，不只报均值；不用原定 5 次的结果下细结论（5 次与 10 次差 0.04，正是一个标准误的量级）。

## 偏离

1. **post.py 需要 `CODEX_THREAD_ID`**：后处理必须带准备时的身份（`ecacfe6d-…`），与准备绑定一致，否则上游拒绝"prepared path 不属于当前会话"。重启 Claude Code 后若重跑后处理，须带同一值。
2. **r8 第二轮候选**：r8（a8746bb）计分在第一轮盲裁之后还有 9 个待裁候选，经第二轮盲裁后才出正式分。
3. **A 批让位**：见"运行"，Ar 补跑 A 让位剩下的 1 次；原定 5 次为 A、Ar、B。
4. **c003 判 supported（已关闭）**：c003（Q3 B1，AP，检查 MODULE-DESIGN-DEPENDENCIES-DATA-FLOW）指出 Promotion Module 在 persistence 前再次验证 request 和 artifact，而 `persist` 不传 request，校验有两个相互冲突的所有者。这正是答案键 MODULE-DESIGN-MODULES#0（Readiness 与 Promotion 重复校验所有权，关联 `prt:27`）的同一缺陷；MODULES#0 没有 DATA-FLOW placement，所以 c003 不是它的候选，只能在 supported 与 unsupported 之间选。按 ARW 语义 unsupported 指"无依据"，c003 有依据；与裁决 brief m2 的先例相同（答案键内的缺陷报在没有对应 placement 的检查下，判 supported，不得分也不扣分）。独立审查确认判法正确。若改判 unsupported：B1 多一个失败反例，0.3442 → 约 0.3333（−0.25/23 ≈ −0.011）；原定 5 次均值 0.4847 → 0.4825，比值 0.584 → 0.582；10 次均值 0.5218 → 0.5207，比值 0.629 → 0.628；不影响任何结论。

## 独立审查意见

独立 agent（Opus，只读，2026-10-17）结论：分数可信，判据成立（余量远大于任何口径修正）；逐用例命中表错位一格，已按上文修正；c003 判 supported 正确，偏离 4 关闭；建议**冻结 v4.2 为 Spec Readiness 定版场景**，不再加难，修正报告后转下一个待办。理由：Q3/Opus < 0.8 且余量大；Opus 明显高于 Q3（0.83 对 0.52）；只有 1 个双 0 用例且是有效难题；10 次会话全部有效；评分确定、可重算，锚点 12/12。冻结与否的最终决定由 Main 综合后登记到 README「现行决定」。

## 遗留

- **冻结 v4.2**：独立审查建议冻结为定版，等待 Main 综合意见后登记 README「现行决定」，并补记 Main 的意见。
- **待用户复核**（不阻断冻结）：REQUIREMENTS 反例 3、4 由 A 改 B（现在等于 k = 1 改 0.25）；同一 k ≥ 1 用例跨两个子场景按 0.5 份额计分；r8 尺度下的调参 SD 阈值。
- **双 0 用例**：只有 MODULE-DESIGN-RATIONALE#2，沿用 v4 判定：有效难题，不改。
- 可选（v4.2 冻结后不改，留给下一版）：把 brief m2 推广为通用规则（答案键内的缺陷报在没有其 placement 的检查下判 supported）；给 MODULES#0 加 DATA-FLOW placement。

明细：`summary.json`（含逐实例四种速度与 23 个用例的命中和 Q3 均分）。
