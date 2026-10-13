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
