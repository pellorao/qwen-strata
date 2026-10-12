# Spec Readiness 能力场景 v2：相对 ARW 原版的变更说明

本文说明 `spec-readiness-reviewer` 能力场景 v2 与冻结 ARW 原版的差异。原版是 `source-snapshots/current/manifest.json` 所列源码加本工程既有补丁。

改动以补丁 [`arw-patches/spec-readiness-v2.patch`](arw-patches/spec-readiness-v2.patch) 提供，保持 ARW 的文件格式与目录约定，只改三处：

- 夹具 `tests/fixtures/reviewer-capability/spec-readiness-reviewer/`：可见场景（`scenario/`）和答案键 `expected.json`。
- `lib/release/reviewer-capability-conformance.mjs`：只把 spec-readiness 的 `SCENARIO_REVISIONS` 从 40 改为 41。
- `tests/release/reviewer-capability-conformance.test.mjs`：删去用例后，一个分数断言改为浮点容差比较。

以下内容都不改：

- 评分规则 `docs/agents/reviewer-capability-scoring.md`、场景规则 `docs/agents/reviewer-capability-scenarios.md`；
- 角色规则、交接、准备、生成与评分程序。

所以评分口径完全由 ARW 自己的文档定义，不依赖本工程的其他规则。v2 的分数只与 v2 比较，不与原版（修订号 40）的分数混合。

## 依据与审查过程

- 起点：[规则、场景与评分审查](../../reports/v0.1.42/spec-rule-audit/summary.md)（下称"v1 审查"）。它指出了三类问题：
  - 重叠用例：SEAM2 与 IF2 是同一根因，与角色规则"不跨检查复制"冲突（C5）；
  - 依赖用例：IF7 依赖 IF6；
  - 未登记缺陷 (a)(b)(c)，以及 AP 请求把未选定的 runtime-migration 标成 governing spec 的疑点。
- 之后按 ARW `reviewer-capability-scenarios.md` 的 Fixture authority 两阶段审查迭代，共 6 轮：
  - 每轮由一个全新的高推理强度独立审计者（Opus high）先只读可见场景，列出所有能成立的缺陷、clean 候选和场景问题（阶段 1）；
  - 再在同一线程读答案键和补丁，逐条对照（阶段 2）；
  - 同时由未见答案的独立 Reviewer（Opus）盲答 RM 或 AP。盲答会话都经工具调用检查：只读场景根，只写绑定草稿。
  - 可见内容有语义变化时，开新一轮并换新的审计者。
- 原则：
  - 盲答漏检本身不是删改理由。只有审查确认某个用例"从 Inputs 推不出"或"有歧义"时，才改或删。
  - 难但能推出、归属清楚的用例保留。
  - 只为消除"正确 Reviewer 会报、答案键却没有登记"的受支持缺陷，才改可见夹具；能只改答案键（补 placement）解决的，不改夹具。

| 轮 | 审计结论 | 盲答（Opus） |
|---|---|---|
| 1 | 阻断 1、主要 10、次要 14（allowed 结果不含 bytes、retention 无法实现、rollback failure 结果无责任方、Policy Seam 与 Module 独占冲突等） | AP 命中 11/18，额外 1 条（rollback failure 结果无责任方） |
| 2 | 阶段 1 无阻断；阶段 2：DF-a 无 Input 依据，DF1/DF2/SE2 未登记，MO2 有歧义 | AP 10/18，额外 1 条（persist 失败路径） |
| 3 | 26 个用例全部有效；未登记 7 项（委托结果、retention 核对路径、清洁流程分支、失败码枚举、recovery 额外字段首错、两处 ADR 结论、artifact 来源理由），5 个 placement 偏窄 | RM 5/5，AP 11/18，均无额外 finding |
| 4 | 23 个用例和 43 个 clean 全部有效；主要 1 项：RM 版 Invalid Artifact Contract 的 extra field 与 result 循环（原版文字） | AP 10/18，无额外 finding |
| 5 | 无阻断；主要 1 项：AP 版 Invalid Artifact Contract 缺 entry-object 步骤（原版文字）；8 个 placement 偏窄 | RM 5/5，无额外 finding |
| 6 | 无阻断；主要 2 项：第 5 轮新加的 vr:31 括号文字反而明写了两套实现；temporary baseline 理由用例在不同轮审计间结论相反，本轮判推不出 | AP 11/18，无额外 finding |

第 6 轮之后只做收尾修改：删去 vr:31 的括号，给 temporary baseline 补完整理由并删除该用例，补 placement。修改由第 6 轮审计者在同一线程确认。

## 改动清单

### 答案键

用例数：原版 25 个问题用例、43 个 clean 用例，v2 为 22 个问题用例、43 个 clean 用例。

| 用例 | 改动 | 原因与证据 |
|---|---|---|
| IF2 + SEAM2 | 合并为一个用例，可放在 INTERFACES 或 SEAMS-ADAPTERS（多个 placement），删去"not both"措辞 | v1 审查 C5：同一根因，遵守"不跨检查复制"的 Reviewer 最多得一个 |
| IF6 + IF7 | 合并为"renderReport 需要 source，却没定义输入类型，也没定义 invalid-artifact 和 artifact-read-failed 诊断的 path 怎样得到" | v1 审查：IF7 依赖 IF6；原 expectation 预设了修法（第 1 轮 M5） |
| SPEC-READINESS-RATIONALE | expectation 改为 per-read evaluation 的取舍 | 夹具把共用行为改为"每次读取重新评估"这一非显然选择，原取舍不再成立 |
| MR2（policy 权威） | 改为"部署配置还是 request 提供的 policy"这一选择缺理由；加 :59 placement | 原 expectation 在夹具中没有对应选择（第 1 轮 M4、M10） |
| MR1（边界备选） | 只保留 caller-side 备选；加 :67+:71 placement | :79 已比较过 Artifact Reader 备选（第 1 轮 M9） |
| MR4（temporary baseline 理由） | 删除 | 第 4 轮判有效但有歧义，第 6 轮判推不出：`context/04:5` 与 ADR 0001 已规定 baseline 的角色，`promotion-recovery:83` 也给了理由。夹具同时补上完整理由，报与不报都不失分 |
| REQUIREMENTS clean（vr:19） | 改用 read-failure requirement，expectation 限定为字段集合完整，path 来源归 renderReport 用例 | AP 的 vr:11 带有 source 缺陷，不能作 clean 证据（第 1 轮 S2、第 4 轮） |
| export-retention | 结果改为 uncertain，expectation 改为"是否适用取决于新 target 是否为 generated artifact，Inputs 未说明"；位置可在 REQUIREMENTS 或 INPUTS | 原版条件不成立（第 1 轮 M6） |
| MODULES / REQUIREMENTS clean | 措辞随夹具调整：Readiness 只拥有 promotion ordering；vr:31 不再提 request validation | 第 1 轮 M2，第 2 轮 MO2 |
| IF4 | expectation 说明 promote 的测试不覆盖 recoverPromotion | 第 1 轮 S4 |
| IF6 / unexpected-field | expectation 补"多个 extra field 时报告哪一个" | 第 5 轮 |
| placement 补充 | IF1（data flow :55，:11）、IF3（Seam :59，:15）、DEP2（:51，MDR :79）、MR3（:55）、DF-a（:77）、IF5（vr:45）、ADR（加 `architecture/02-commit.md:5`）、image 与 export（subject 选择行）、request-consistency（REQUIREMENTS）、MODULES（:11）、IF6（vr:19、vr:49） | 第 3–6 轮审计列出的合理关联位置。AP 用例不加 REQUIREMENTS 或 INPUTS placement，因为加了会让该用例整体划给 runtime-migration |

### 可见场景

每项修改都保持文件行数不变，原版其他行号不受影响。

| 文件 | 改动 | 原因 |
|---|---|---|
| `specs/access-review.md` | 共用理由改为 per-read evaluation；allowed 结果为 `{allowed:true, policyId, bytes}`，Seam 只返回 decision，Access Review 授权后再读 bytes；boundary 只交 verified principal，operation 取自不可变 request；Module 拥有 decision、经 Seam 评估；"Runtime 选择 Adapter，不选择 policy"；Artifact Reader 是既有 Seam，resourceId 是 artifact source path，不新增定位职责；policy 权威写成"Input author 的部署配置"；Requirements 的其余结果委托给 Interfaces 的 Other Results | 第 1 轮阻断 A1，主要 M4、M5、M10；第 3 轮 R-R5 |
| `specs/promotion-runtime.md` | Readiness 统一应用 ADR 0005 的 retention，写明对象、起点与期限；Readiness 组装 Successful Result；persist 把 commit failure 交给 Recovery，并把 Recovery 的结果返回 Readiness；failure code 与 operation 逐项枚举；retention 和 request binding 通过源码审查核对；ADR 结论改写；权威转换理由不再涉及 baseline，另补 baseline 只作 recovery evidence 的完整理由 | v1 审查 (a)；第 1 轮 M1、M3、M7；第 2 轮 DF1；第 3 轮 A-R1、A-IF6、A-ADR2；第 6 轮 |
| `specs/promotion-recovery.md` | 输入加入 `commitFailureCode`；Recovery 拥有 commit-failure 分支的全部结果；输入校验依次为对象、额外字段（键名升序第一个）、字段顺序，并写明 path；restore 失败报告实际的 `baselineStatus`；补 artifact 来源理由和 invalid-input 的 ADR 结论 | v1 审查 (b)；第 2 轮 MO3、DF2；第 3 轮 A-IF8、A-ADR3、A-MR3 |
| `specs/validation-report.md`（两份 base） | Readiness 只拥有 artifact generation 和 promotion ordering；Module 独占 report validation，不拥有 Parser Module 的 `parseArtifact`；引用 `architecture/05` 的 invalid-artifact-contract 与 production-adapter；清洁 Report Flow 写全全部分支 | 第 1 轮 M2、S12；第 2 轮 MO2；第 3 轮 A-D3；第 5、6 轮 |
| `specs/parser-scan.md` | Parser Module 继续独占 `parseArtifact` 的 parsing responsibility | 第 2 轮 MO2：两个 Module 都声称拥有 parsing |
| `specs/runtime-migration.md` | :11 写明 operation 先验证 artifact，再写 temporary baseline，最后 commit | 第 3 轮 RM-R5：顺序有两种读法 |
| `specs/export-retention.md` | :5 改为条件式：新 target 是 generated artifact 时适用，人工维护文档时不适用 | 第 1 轮 M6 |
| `docs/adr/0005-external-policy.md` | 只有 Readiness Module 应用 retention，Reviewer 和其他 Module 都不创建 | v1 审查 (a) |
| `rules/02-external-policy.md`（AP） | external retention policy 只适用于 artifact promotion | v1 审查 (c)：原文也覆盖 access review，却没有任何落实 |
| `rules/05-ordering.md` | 改为权威来源表规则：每份完整 Module Design 的治理 spec 都要在 Dependencies and Data Flow 中用 Source/Authority 表列出全部权威来源 | 第 2 轮：DF-a（recovery 缺表）原本没有 Input 依据 |
| `architecture/04-seams.md` | 使用 Seam 的 allowed decision；Live 与 deterministic Adapter 的措辞；"Runtime environment 选择 Adapter，不选择 policy" | 第 1 轮 M4 |
| `architecture/05-validation-report.md` | RM 版 entry 校验改为先查 object，再查 `check`、`result`，然后按该 result 允许的字段查 extra fields；AP 版补 entry-object 步骤（AP 版有意保留 unexpected-field 缺位，即已登记的用例）；Current Invalid Input Diagnostic 标明是 Diagnostic Wording change 之前的状态 | 第 4、5 轮（原版文字的缺陷）；第 5 轮 S10 |
| Issue（两份 base） | Acceptance criteria 补"promotion 的 request binding 和 retentionDays 应用通过源码审查核对" | 第 3 轮 A-R1：内部应用缺少核对途径 |

第 0 轮曾按 v1 审查的疑点，把未选定的 runtime-migration 从 AP Inputs 中过滤掉。第 1 轮审计（M8）认定这与 scenarios.md 的"未选择章节范围边界"对照冲突，已撤回。AP Inputs 与原版一致，仍含全部 `specs/`。

## 上游备注（未改动，审计判断不会让正确的 Reviewer 失分，或只是次要风险）

- 选定章节的写法：
  - RM 选定的 `#requirements` 用文档内引用委托到未选定的 Interfaces（如 promotion-runtime:11 → :41）。答案键按"文档内引用视为纳入"处理，规则没有明文。
  - AP 用 `#scope`、`#design-rationale`、`#adr-evaluation` 等锚点选中整份文档，与"只提供辅助信息的选择是 gap"字面上有张力。
  - `### ADR Evaluation` 嵌在 `## Module Design` 下，靠 `#module-design` 才被选中。
- "Interface 变化"的口径：只改取值（diagnostic-wording）算不算，`domain.md` 没有定义。答案键把 result-summary 新增字段算作变化，diagnostic-wording 不算。
- 语言：`Not required:` 段落是英文、正文是中文，违反 `writing.md`，但不属于 Spec Readiness 检查。`promotion-recovery` 的 L42-44 连续三个空行来自原版；删掉会让后面所有行号前移，未改。
- `rules/05` 的场景规则与角色规则对权威表的适用范围（"长期规范"与"每份完整 Module Design 的 spec"）不一致。本场景由 `rules/05` 补齐。
- AP 的组装约束：带 REQUIREMENTS 或 INPUTS placement 的用例会整体划给 runtime-migration。因此 AP 中位于 Requirements 小节的缺陷（vr:11、rec:15）只能登记在 INTERFACES。按角色规则，选定的完整 Module Design 由 INTERFACES 负责，误归为 Reviewer 自身失误。
- 残余的次要误报风险（第 6 轮审计，均未改）：
  - vr:100 没有评估 source invalid-input 结果合同；
  - runtime-migration:5 的 Scope 写的是 reader guide；
  - `rules/01:5` 写"传 requested operation"，而 operation 实际取自 request；
  - promotion-runtime:11 的"architecture contract 定义的 canonical JSON result"可能被读成旧形状；
  - access-review:93 中"相同配置比较 decision"的含义；
  - persist 怎样消费 `retentionDays`；
  - request binding 不匹配时的结果。
  - 这些都只可能产生少量未关联 finding，审计判为次要。
