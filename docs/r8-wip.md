# r8 实现笔记（WIP，完成前删除或并入规则）

## 口径（用户 2026-10-15/16 + 审查采纳项）
- S′ = (Σ 正例得分 − Σ 失败 clean 的 k) ÷ 正例数，截到 [0,1]。
  - 正例：k=0.25 档得 c（ARW 部分得分）；k≥1 档关联即 1、否则 0（R6 无证据门槛）。
  - clean：k=0.25 档按 (1 − 得分) 计失败；k≥1 档得分 >0 才算对。
  - noOther 与额外失败 clean（R3b、越过停止点、Commit Audit 范围外行）一律 k=0.25。
  - clean（含 noOther）只在所属检查存在时才算通过。
  - 份额：Spec Readiness 两个子场景都计分的 k≥1 用例沿用 judgmentShare 0.5，作用于正例数和 k（待用户复核，审查 B2 未定）。
- 平衡：每个 k≥1 档，正例份额和 = k × 反例份额和；k=0.25 不要求。
- 格式罚乘在 S′ 上，不变。
- 迁移：答案键 `judgment: true` 与覆盖文件里未写 k 的用例按 k=1。

## 实现要点
- 字段：用例 `k`（1 或 4）；计分结果 `kProblemWeight`、`kEarnedProblemPoints`、`kFailedCleanWeight`、`kTiers`；删去 two-part 字段。
- 补丁：新文件 `scoring-k.patch`（从 ARW 原版生成），r7 补丁移入 superseded。
