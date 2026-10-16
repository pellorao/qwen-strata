# Spec Readiness v4.2 正式测量（v0.1.44.1，Q3 ×10）

## 结论

- **评分 r8 下 Q3/Opus 低于 0.8**：Q3 原定 5 次 **0.4847 ± 0.154**，全部 10 次 **0.5218 ± 0.1135**；Opus（medium）×3 **0.8294 ± 0.0112**；Q3/Opus = **0.584**（原定 5 次）/ **0.629**（全部 10 次），都低于 0.8，场景对 Q3 仍有区分空间。
- **不能用于调参**：原定 5 次 SD 0.154、10 次 SD 0.1135，都超过 0.068 的标准（v4.1 报告同一标准）；v4.2 只用于能力验证和 benchmark。
- **p基准**：Haiku-high ×5 的格式合格数 sumR 0、sumT 414，pBase 0.0241546（floor），bootstrap 90% 区间 [0.01996, 0.03030]；登记在 `benchmarks/reviewer-suite-v1/format-baseline.json`（expected 键 `74252e0a…`），存档 `benchmarks/reviewer-suite-v1/format-baseline/spec-readiness-v4.2/`。
- **全部 10 个 Q3 实例有效**：会话检查未发现压缩、早退或禁止来源访问；所有实例的罚分项 r = 0，罚前分等于罚后分。
- **适用范围**：只对 rtx3080ti、IQ3_XXS、Strata 0.1.44.1、Codex 0.162.0、effort high 成立。分数只在 v4.2（修订号 45）内、同为 r8 口径下比较；与 v4.1（r7.1）不直接比分。
- **冻结，还是转下一个场景，属于重要决策**，本报告不下结论：需由智能水平和推理强度不低于 Main 的独立 agent 给出意见，Main 综合后执行（见"遗留"）。

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
- 候选总数（post.py 后）：Q3 A 38、Ar 22、B 28、C 59、D 39，共 186；Opus 参考第一遍 27 / 29 / 28，共 84；两项合计 270，即盲裁池的新候选。
- 会话检查（20 个 Q3 线程）：全部 complete、终态 ready、0 压缩、启动上下文 SHA 同批一致（user@6 按重复序号一致）、交接都在。标记 39 条全部无害：模型拼错 workdir 或越出根，被拒（命令未执行）；写 /tmp，只读文件系统失败（C AP3 #22、D AP2 #22）；D AP2 #23 为 jq 变量误报；C AP3 e132 是跨零点的 environment_context；D AP1 e163 是 ARW 对空报告的续作提醒（上游机制），随后交付了 10 行报告。无禁止来源访问。
- 速度：引擎入 1,422–1,629 tok/s，出 86.4–90.6 tok/s；每实例 12.7–19.7 分钟。没有降速实例。

## 逐用例命中（命中 = 得分 > 0；Q3 为 10 次中的命中数，Opus 为 3 次中的命中数）

| 用例 | Q3 | Opus |
|---|---|---|
| SPEC-READINESS-INPUTS#0 | 0/10 | 0/3 |
| SPEC-READINESS-REQUIREMENTS#0 | 0/10 | 0/3 |
| SPEC-READINESS-REQUIREMENTS#1 | 10/10 | 3/3 |
| SPEC-READINESS-REQUIREMENTS#2 | 10/10 | 3/3 |
| SPEC-READINESS-REQUIREMENTS#3 | 10/10 | 3/3 |
| SPEC-READINESS-RATIONALE#0 | 0/10 | 0/3 |
| SPEC-READINESS-ADR-EVALUATION#0 | 0/10 | 0/3 |
| MODULE-DESIGN-APPLICABILITY#0 | 0/10 | 0/3 |
| MODULE-DESIGN-EXEMPTION#0 | 0/10 | 0/3 |
| MODULE-DESIGN-MODULES#0 | 0/10 | 0/3 |
| MODULE-DESIGN-MODULES#1 | 3/10 | 3/3 |
| MODULE-DESIGN-INTERFACES#0 | 0/10 | 0/3 |
| MODULE-DESIGN-INTERFACES#1 | 5/10 | 1/3 |
| MODULE-DESIGN-INTERFACES#2 | 6/10 | 3/3 |
| MODULE-DESIGN-INTERFACES#3 | 4/10 | 3/3 |
| MODULE-DESIGN-INTERFACES#4 | 1/10 | 3/3 |
| MODULE-DESIGN-INTERFACES#5 | 0/10 | 2/3 |
| MODULE-DESIGN-SEAMS-ADAPTERS#0 | 0/10 | 0/3 |
| MODULE-DESIGN-DEPENDENCIES-DATA-FLOW#0 | 0/10 | 0/3 |
| MODULE-DESIGN-DEPENDENCIES-DATA-FLOW#1 | 8/10 | 3/3 |
| MODULE-DESIGN-RATIONALE#0 | 0/10 | 0/3 |
| MODULE-DESIGN-RATIONALE#1 | 6/10 | 3/3 |
| MODULE-DESIGN-RATIONALE#2 | 0/10 | 3/3 |

- 23 个用例中 11 个双方 0 命中，其中大多为 Module Design 的 Applicability、Exemption、Modules#0、Interfaces#0、Seams-Adapters、Dependencies-Data-Flow#0、Rationale#0，以及 SR 的 Inputs、Requirements#0、Rationale、ADR-Evaluation。原因（题过难或答案键过严）本报告未区分。
- Opus 命中而 Q3 不中或明显更少：MODULE-DESIGN-INTERFACES#5（0/10 对 2/3）、MODULE-DESIGN-RATIONALE#2（0/10 对 3/3）、MODULE-DESIGN-INTERFACES#4（1/10 对 3/3）。
- Q3 命中不弱于 Opus：SPEC-READINESS-REQUIREMENTS#1–3 为 10/10 对 3/3，MODULE-DESIGN-DEPENDENCIES-DATA-FLOW#1（8/10 对 3/3）。

## 偏离

1. **post.py 需要 `CODEX_THREAD_ID`**：后处理必须带准备时的身份（`ecacfe6d-…`），与准备绑定一致，否则上游拒绝"prepared path 不属于当前会话"。重启 Claude Code 后若重跑后处理，须带同一值。
2. **r8 第二轮候选**：r8（a8746bb）计分在第一轮盲裁之后还有 9 个待裁候选，经第二轮盲裁后才出正式分。
3. **A 批让位**：见"运行"，Ar 补跑 A 让位剩下的 1 次；原定 5 次为 A、Ar、B。
4. **c003 判 supported，口径有疑问**：第二轮 9 个候选中 c003 被判 supported，其余 8 个 unsupported。这一判法的口径有疑问，未经用户或独立 agent 复核；对分数的影响未单独量化，列为待复核。

## 遗留

- **c003 口径待复核**（上述偏离 4）：核对该候选的 supported 判定是否符合 r8 的归属原则，确认后若改判，重新计分。
- **冻结，还是转下一个场景**：重要决策，先由独立 agent 给出意见，再由 Main 综合；结论和双方意见补进本报告，并登记 README「现行决定」。
- 11 个用例双方 0 命中，是否需要改题或改答案键，未判断。

明细：`summary.json`（含逐实例四种速度与 23 个用例命中）。
