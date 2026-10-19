# Sonnet 盲裁试点（2026-10-19）

## 结论

- Sonnet 5.5 medium 盲裁满足事先写定的三条通过线，所以没有再试 high。
- 建议：benchmark 用 Sonnet medium 作主裁决者，另配质控。最终方案归用户定（测量设计）。
- 适用范围：试点规模小。false-positive 类只有 7 项，每个池只跑了 1 次，没有测 Sonnet 自身复跑的一致性。
- 同一工作项的另两项核实结论：
  - 多词 `findingTerms` 按连续短语匹配：评分 r7 已完成（0ff095b）。
  - 必选组仅供裁决参考：评分 r7 已完成，69969fa 补了直接断言。
  - 已定版报告都在 r7 或更新的评分下算出，不需要重算。

## 设计

设计与通过线在开跑前写定，见 `data/design.md`。

**s1，主检验集**：Commit Audit v3 修订号 24，共 92 项。

- 难项层 36 项：p1–p4 中 Opus 原判不是 matched 的候选，以及全部发现候选。
- matched 关联 45 项：r1 锚点 23 项，加分层随机 22 项（种子 20261019）。
- 合成负例 11 项：沿用 r1 的构造。
- brief：冻结件 `commit-audit-v3-brief.md`（`9c36e60b…`）。
- 裁决者可以读被审代码的 view。

**s2，次要集**：Code Standards v5.1 增量池全部 62 项，Opus 原判为 matched 43、not-matched 19（含 12 个锚点）。

- 偏离：这个池当时用的 brief 没有存档，按冻结 ARW Adjudication 原文加 v5.1 变更说明 §10 重建，所以 s2 只作次要证据。

**运行方式**：Claude Code 无头 `claude -p --model sonnet --effort medium`。

- 参数：`--safe-mode --restricted --strict-mcp-config --disable-slash-commands --setting-sources ""`，`--permission-mode dontAsk`。
- Bash 沙箱：只读隔离目录，网络为空。
- 工作目录在工程外。
- 每次运行结束都执行了 `estimate.sh --add-stream`。

**通过线**（三条同时满足）：

1. s1 真实候选一致率 ≥ 95%，且难项层 ≥ 90%；
2. 合成负例 11/11 识别；
3. 按 Sonnet 的决定改判后重算，正式 ×5 的 Q3/Opus 比值 |Δ| ≤ 0.02，"< 0.8"的判定不变。

s2 一致率 ≥ 95% 算作支持。

**作废一次**：s1 第一次运行时，view 是失效的符号链接，裁决者读不到代码，判为作废，改用 `cp -rL` 后重跑。作废的那次保留为"纯文本裁决"诊断结果。

## 结果

| 项目 | s1 Sonnet medium | s1 作废次（读不到代码，诊断） | s2 Sonnet medium |
|---|---|---|---|
| 真实候选一致 | 79/81（97.5%） | 77/81（95.1%） | 61/62（98.4%） |
| 难项层 | 34/36（94.4%） | 32/36（88.9%） | 不适用 |
| matched 层 | 45/45 | 45/45 | 42/43 |
| not-matched | 5/5 | — | 19/19 |
| 锚点 | 23/23 | — | 12/12 |
| 合成负例 | 11/11 | 11/11 | 不适用 |
| 正式 ×5 比值 | 0.7301 → 0.7301（Δ 0） | 0.7301 → 0.7398（Δ 0.0097） | 不适用 |
| ×10 比值 | 0.7064 → 0.7064 | 0.7064 → 0.7113 | 不适用 |
| 耗时、费用 | 1.4 分钟，$0.35 | 1.4 分钟，$0.32 | 0.5 分钟，$0.22 |

s1 按参考决定分类的一致情况：matched 45/45、not-matched 5/5、problem-N 17/17、supported 2/2、unsupported 5/5、false-positive 5/7。

不一致的 3 项：

| 池 id | 来源 | Opus 原判 | Sonnet | 分析 |
|---|---|---|---|---|
| s1-024（p3-075） | Q3 C | false-positive:clean-11 | supported | finding 只引用了另一行的结论。冻结口径规定这种引用不构成理由，Opus 判对了，Sonnet 偏宽松。该行的干净观察已经失败，按"只扣一次"计，分数不变 |
| s1-040（p1-002） | Q3 B-x2 | false-positive:clean-22 | unsupported | 两种判法代价相同 |
| s2-047（c034） | Q3 q3-9 | matched | not-matched | finding 只覆盖了窗口起点的重复，Sonnet 按保守方向处理 |

- 两处 s1 不一致都出在发现候选的 false-positive 类。换到没有"只扣一次"的场景，把 false-positive 误判成 supported 会少扣 k = 0.25。
- 读不到代码时，难项层降到 88.9%。所以 benchmark 裁决必须给裁决者提供 view。
- 费用约 $0.004/项（API 等价）。Opus 裁决的实际花费没有单独记账，所以没有给出精确的价格比。

## 对 benchmark 裁决模型的建议（待用户决定）

| 方案 | 内容 | 代价与风险 |
|---|---|---|
| A | 只用 Sonnet medium。每个池混入 10–15 个 Opus 已裁锚点和合成负例；锚点一致率 < 95% 或漏掉任一合成负例时，整池改由 Opus 重裁 | 费用最低；supported 和 false-positive 类可能出现宽松误判 |
| B（推荐） | A 加 Opus 复核：Sonnet 判为 supported 的发现候选，以及 k = 4 的双裁 | 按 s1 的比例约占 5%，额外的 Opus 量很小 |
| C | 全部用 Opus | 最稳，但费用随"模型数 × 4 × 5"线性增长 |

正式采用前，可以在 Spec Readiness 或 Code Spec 的池上再做一次试点，并测一次 Sonnet 自身复跑的一致性。

## 存档

`data/` 中的文件：

- `design.md`：通过线
- `progress.md`
- 池与参考答案：`pool-s1.json`、`key-s1.json`、`pool-s2.json`、`key-s2.json`
- `brief-cs51-template.md`：s2 重建的 brief
- 脚本：`pool_s1.py`、`pool_s2.py`、`run.sh`、`compare.py`
- `runs/s1-medium/`、`runs/s2-medium/`：有效运行，包括决定、结果、提示、沙箱设置、重算结果（原始 stream 不存档）
- `runs/s1-medium.void1/`：作废诊断

脚本里的路径指向原运行目录 `.tmp/score-leftover-1019/`，重算时要换成 `data/`。
