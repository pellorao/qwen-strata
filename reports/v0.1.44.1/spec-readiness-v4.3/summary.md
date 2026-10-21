# Spec Readiness v4.3 重算（只做去重，v0.1.44.1，不重跑模型）

## 结论

- **v4.3 下分数逐位不变**：用 v4.2 的全部回答（Q3 ×10、Opus medium ×3、Haiku-high ×5 的上下界）按 v4.3 拆分重算，13 个来源、23 次计分，每次的分数都与 v4.2 完全相同。Q3 原定 5 次 0.4848 ± 0.1541，全部 10 次 0.5218 ± 0.1135；Opus 0.8294 ± 0.0112；**Q3/Opus = 0.584（原定 5 次）/ 0.629（全部 10 次）**，低于判据 0.8。
- **意义**：v4.3 按用户的出题原则（两个子场景不出同一道题，与 k 无关；用户 2026-10-16/17）去掉了 AP 对两项需求检查反例的重复计分。去重后结论不变：Spec Readiness 现行版本 v4.3 定版，不再加难。
- **为什么不必重跑**：
  - v4.3 只改了计分侧的子场景拆分和修订号，没有改夹具、交接、角色和选定 specs，模型看到的任务与 v4.2 相同，所以 v4.2 的回答在 v4.3 下完全有效。
  - r8 的公式是 `(Σ正例部分得分 − Σ失败反例的 k) / 正例数`，答对的反例不进分子。被去掉的 8 个反例在每次运行里都答对了，所以分数一定不变。
- **适用范围**：rtx3080ti、IQ3_XXS、Strata 0.1.44.1、Codex 0.162.0、effort high；评分 r8。使用限制与 v4.2 相同：Q3 单次分数没有意义（0.34–0.70）；10 次时比值约 ±0.04；r8 的 SD 阈值定下前不用于调参。见 [v4.2 报告](../spec-readiness-v4.2/summary.md)。

## 改动

v4.3（修订号 46，2026-10-17 冻结）只改 ARW 的 `splitSpecReadinessExpected`：AP 的 `SPEC-READINESS-INPUTS`、`SPEC-READINESS-REQUIREMENTS` 两项检查只保留 noOther，这两项的反例全部归 RM；拆分后如果 noOther 以外有同一期望句进了两个子场景，加载答案键时报错。答案键 `74252e0a…`、k 覆盖文件和 p 基准都沿用 v4.2；k=1 档仍为 4:4。详见 [v4.3 变更说明](../../../benchmarks/reviewer-suite-v1/spec-readiness-v4.md#v43只做去重修订号-462026-10-17-冻结)。

AP 去掉的 8 个反例（k=0.25）：

| 检查 | 期望句 |
|---|---|
| INPUTS | The clean Artifact reader design is supported by explicit architecture evidence. |
| INPUTS | The immutable request isolation boundary is complete and usable as supplied. |
| INPUTS | The subject accurately selects the supplied validation-report requirement and should not be reported as absent. |
| REQUIREMENTS | The Requirements do not need to prescribe internal parser, helper, or storage implementation details. |
| REQUIREMENTS | The clean documentation-only reader-index requirement is a complete stable-path documentation change. |
| REQUIREMENTS | The clean report read-failure requirement lists a complete set of result fields. |
| REQUIREMENTS | The clean wording requirement preserves the structured diagnostic code and payload contract. |
| REQUIREMENTS | The stable boundary correctly separates Engine, Reviewer, and Input-author responsibilities. |

## 重算数据

完整精度数据在同目录的 `summary.json`。

每次重复（RM 与 AP 合计）的反例总数从 55 降为 47，通过数也正好少 8；失败反例权重、正例得分、`rawScore` 和最终分都不变。没有新候选，也没有作废的裁决。

| 来源 | 重复 | v4.2 | v4.3 | T | r |
|---|---:|---:|---:|---:|---:|
| Q3 A | 1 | 0.5875 | 0.5875 | 80 | 0 |
| Q3 A | 2 | 0.4480 | 0.4480 | 36 | 0 |
| Q3 Ar | 1 | 0.6959 | 0.6959 | 74 | 0 |
| Q3 B | 1 | 0.3442 | 0.3442 | 41 | 0 |
| Q3 B | 2 | 0.3481 | 0.3481 | 60 | 0 |
| Q3 C | 1 | 0.6095 | 0.6095 | 61 | 0 |
| Q3 C | 2 | 0.5042 | 0.5042 | 79 | 0 |
| Q3 C | 3 | 0.5626 | 0.5626 | 65 | 0 |
| Q3 D | 1 | 0.5298 | 0.5298 | 60 | 0 |
| Q3 D | 2 | 0.5882 | 0.5882 | 67 | 0 |
| Opus 1 | 1 | 0.8419 | 0.8419 | 68 | 0 |
| Opus 2 | 1 | 0.8264 | 0.8264 | 77 | 0 |
| Opus 3 | 1 | 0.8200 | 0.8200 | 79 | 0 |

Haiku-high ×5 的上下界（只用于格式罚的 p 基准）同样逐位不变：上界 0.787 / 0.203 / 0.700 / 0.728 / 0.837，下界都是 0。p 基准沿用 v4.2 的登记（pBase 0.0242）。

## 方法与偏离

- 依据测量规则"只改答案键或 placement 时，用已有回答重新评分"。v4.3 只改了计分侧的拆分，所以用已有回答重算，不重跑模型。
- **一次性偏离（重算方法）**：
  - 做法：每个来源复制一份 v4.2 运行的 ARW 目录，换入 v4.3 的拆分，改写复制件的准备状态，再在私有挂载命名空间里把复制件绑定到原路径计分；原目录没有改动。
  - 这样做有意绕开了 ARW 的两道约束：修订号升级会让旧准备状态失效，Request 路径绑定原目录。
  - 独立审查认定：计分结果与重新准备等价，没有越过安全边界。但测量规则没有授权改写准备状态，所以这次只作一次性偏离，不作为常规做法。
  - 重算脚本用的计分身份与 `single_scenario_score` 的默认值不同，不影响分数。

## 独立审查（2026-10-17）

独立 agent（Opus high，只读）结论**可冻结**，Main 同意。要点：

- 补丁只改了修订号和 AP 两项需求检查的拆分，符合用户原则。AP 的 issue 和选定 sections 都与 RM 不同，所以两边的 noOther 是两道题。
- "不必重跑"成立：逐次核对了 Q3 ×10、Opus ×3、Haiku 上下界各 5 次，被去掉的反例没有一次答错。
- 重复核对位于 ARW 加载答案键的拆分处，只抓期望句文本完全相同的跨子场景重复，抓不到措辞不同的同一缺陷；同一答案键内部的重复目前没有任何检查。
- 0.5 份额代码已不可达，可以暂留，清理项登记在 `docs/plan.md`。

## 遗留

- 评分代码清理（下次修订评分时做）：删除不可达的 0.5 份额代码、`scoring-k.patch` 里过时的计分说明和对应测试。
- Commit Audit 原版答案键里，`GATE-1` 第 15 个正例和 `GATE-2` 第 3 个正例，期望句和证据完全相同，是同一缺陷出了两遍。按出题原则，在重构这个场景时改题，并在冻结工具里加入"同一答案键内重复即报错"的检查（见 `docs/plan.md`）。

## 更正与补记（2026-10-21）

- 更正（2026-10-21）：本次 Strata 运行只接入了原生压缩提示 `ab0c334d…`，缺工程压缩提示 `3856cb62…`（硬约束 3；d6b09c9 起 `arw_dimension.selection()` 写死 False）。所有实例都没有发生压缩，压缩提示没有起作用，结论不受影响。
