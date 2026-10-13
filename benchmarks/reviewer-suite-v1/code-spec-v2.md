# Code Spec 能力场景 v2：相对原版的变更说明

v2 以补丁 [`arw-patches/code-spec-v2.patch`](arw-patches/code-spec-v2.patch) 提供，在冻结源 manifest 登记（ARW 760007c 原版 code-spec-reviewer 修订号 11）。它改两处夹具可见内容（各一行）和答案键，并把 `SCENARIO_REVISIONS` 中 code-spec-reviewer 从 11 改为 12；评分规则、角色规则、交接与准备 / 生成 / 评分程序都不改。v2 的分数只与 v2 比较，不与 F6 等原版结果直接比较。

## 起因

按用户 2026-10-13 的决定，四个 reviewer 场景按 Spec Readiness 的同一流程逐个重构。Code Spec 先做静态检查（答案键与 spec 40 条要求行一一对应，未发现必须修改项，只有访问窗口结束边界一处待证据），再做两轮"全新 Opus-high 盲答 + 全新 Opus-high 两阶段审计"（ARW `reviewer-capability-scenarios.md` "Fixture authority"：阶段 1 不看答案键，阶段 2 对照答案键）。

## 改动

| 文件:行 | 改动 | 原因与证据 |
|---|---|---|
| `scenario/candidate/src/reservations/access-policy.mjs:10` | `now() <= reservation.endAt + LATE_ACCESS_MS` 改为 `now() < …` | spec:19 "Time ranges use half-open intervals" 可读作全局规则，此时访问窗口结束时刻放行即违反半开区间；也可读作只管预约窗口，此时 spec:47 对结束时刻无规定。答案键把此处登记为 clean，按 AGENTS.md 上报歧义的 Reviewer 会在 noOtherSupportedFinding（可能还有该 clean 用例）失分。第 1 轮审计阶段 1 独立提出（可选 uncertain），阶段 2 定为主要（R2）。改后两种读法下都无缺陷；clean expectation、行号不变。 |
| `scenario/base/governing-spec.md:42` | 在 "Only reservations in the `held` or `confirmed` state may be canceled" 后补 "; any state other than `held`, `confirmed`, or `canceled` must be rejected." | 问题用例"Cancellation permits every non-canceled state, including states outside held and confirmed"（`hold-policy.mjs:27` `state !== 'canceled'`）。原 spec 只出现三种状态，canceled 已在 `reservation-service.mjs:55` 提前返回，三种状态内黑名单与白名单等价，Input 内找不到失败情形；第 1 轮审计阶段 1 判为不报，阶段 2 定为主要（R1）。改后任何其他状态字符串都是可直接证明的失败情形；expectation 原文仍准确，行号不变，与 spec:43（canceled 原样返回）不矛盾。 |
| `expected.json` 幂等键归一化用例 | 新增 placement，associationEvidence 只含 `reservation-service.mjs:20`（evidence 不变） | `:20` 是缺陷所在与修复点；原有 4 个 placement 都要求两点组合，只引 `:20` 的正确报告关联不上（第 1 轮 R3，次要）。 |
| `expected.json` hold 时长、提前进入时长、进入不要求 confirmed 三个用例 | 由单一关联改为 placements，各新增一个关联点：`hold-policy.mjs:18`、`access-policy.mjs:9`、`reservation-service.mjs:79`（evidence 不变） | 这些行是缺陷的直接证据，原在 evidence 中、不在任何 clean 用例证据中；只引它们的正确报告原本关联不上（第 2 轮 B3/B5，次要）。B5 另三处未加：`reservation-service.mjs:17` 与 clean"超过容量"共用、`availability.mjs:10` 不在原 evidence、`reservation-service.mjs:48` 与 clean"confirmedAt 来自 now()"共用，加了会误关联。只改答案键，不改可见内容，未再做盲审。 |
| `lib/release/reviewer-capability-conformance.mjs` | `SCENARIO_REVISIONS` code-spec-reviewer 11 → 12 | 场景修订号 |

ARW 自带测试 `tests/release/reviewer-capability-conformance.test.mjs` 在打补丁后 69/69 通过。

## 审计与盲答轮次

| 轮次 | 夹具 | 盲答（全新 Opus-high，worker 试裁） | 审计结论（全新 Opus-high，两阶段） |
|---|---|---|---|
| 1 | 原版（修订号 11） | 扣罚前 0.894、扣罚后 0.804（正文简写证据 4 次 `review-evidence-invalid`）；21 个问题用例都有候选，未报访问窗口边界，无答案键外 finding | 无阻断；主要 R1（取消状态用例不可唯一推出）、R2（访问窗口结束边界 clean 有歧义）；次要 R3、R4、R6 |
| 2 | v2（R1–R3 修改后） | 0.953（无诊断）；21 个问题用例都有候选，无答案键外 finding | 无阻断、无主要；次要 B1–B10 |

## 残余（未改）

- 拆分粒度：spec:56 拆成 state 与 expiresAt 两个问题用例；合成一条的报告每个用例原子性约 0.667，合计约少 0.13/21。ARW 规定同一段要求中的不同缺陷分条报告，保留。
- spec:6 "after normalization" 未定义规范化方式及是否以规范化值存储；spec:5 未说查找房间是否用 trim 后的 roomId。
- 改写后的 spec:42 后半句有一定提示性。
- 规则冲突（各 Code Spec 实例共有）：`reviewer.md` Communication 要求 send_message 与运行标识、Role Inputs 要求治理副本 SHA-256，交接不提供；`reviewer.md` Independent runtime 说 Claude Code 原生 Reviewer 执行暂停，而本工程的 Opus 参照在 Claude Code 中按交接盲答（只影响 Opus 参照）。
- 访问"进入不要求 confirmed"用例的关联点只有 `access-policy.mjs:7` 与 `reservation-service.mjs:79`；只引 `:8-10` 的报告关联不上（放宽会与相邻用例证据重叠）。
