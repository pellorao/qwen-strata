# Spec Readiness 能力场景 v3：相对 v2 的变更说明

v3 以补丁 [`arw-patches/spec-readiness-v3.patch`](arw-patches/spec-readiness-v3.patch) 提供，叠在 [v2](spec-readiness-v2.md) 之后，在冻结源 manifest 登记。它改夹具可见文字和答案键，并把 `SCENARIO_REVISIONS` 从 41 改为 42；评分规则、角色规则、交接与准备 / 生成 / 评分程序都不改。v3 的分数只与 v3 比较。

## 起因

v2 测量（Opus ×3、IQ3_XXS ×10）后的第 7 轮审计指出：

- `specs/validation-report.md:31` 有两种都成立的读法：Validation Report Module 重复了 Parser Module `parseArtifact` 的校验责任，或二者是共用架构合同的两个独立 operation。v2 把它当 clean，v2.1（[只改键的重评分](spec-readiness-v2-iq3_xxs-2026-10-13/v2.1-key.md)）把它当问题；两套分数是歧义的两端。
- `specs/runtime-migration.md:15` 引用一个没有 Input 提供的"已批准 access policy"，`:45` 又测试 promotion 并不评估的 denied authorization。
- AP 中未选定、但作为 Input 提供的 runtime-migration.md 的 `:23` 与已选定的公开结果合同字段冲突，误导 AP 报 REQUIREMENTS。
- `specs/validation-report.md:100` 没有给 source invalid-input 写"不需要新 ADR"的结论。

## 改动

| 文件:行 | 场景 | 改动 | 原因 |
|---|---|---|---|
| `specs/validation-report.md:31` | RM、AP | 写明 `renderReport` 与 `parseArtifact` 是两个独立 operation，各自引用 architecture 的 Invalid Artifact Contract 校验，`renderReport` 不适用 Parser 大小限制，因而不调用 `parseArtifact` | 消除上述歧义，使其确为 clean；不声明新权威（第 2 轮审计指出"只以…为权威"会构成未登记的 DEPS 缺陷） |
| `specs/validation-report.md:90` | RM、AP | 追加不复用 `parseArtifact` 的取舍、拒绝理由与成本 | 避免该选择被报为 MODULE-DESIGN-RATIONALE 缺陷 |
| `specs/validation-report.md:100` | RM、AP | 追加：source invalid-input 只给出 path 与 message、不持久化、不改变 failure authority，因而不需要新 ADR | 与 `promotion-recovery.md:91` 的写法对齐 |
| `specs/validation-report.md:11` | 仅 RM | "diagnostic 的 path 精确等于 source 的值" | 原文与同句字面量 `path: "source"` 冲突 |
| `specs/runtime-migration.md:15` | RM、AP | 只接受已完成 access control 的内部请求；可信身份来自 security authority Input；promotion 不评估或选择授权 policy | 与 `promotion-runtime.md:5` 同口径，去掉无 Input 支撑的 policy 引用 |
| `specs/runtime-migration.md:45` | RM、AP | 删去 "denied authorization" | 与 `:15` 一致 |
| `specs/runtime-migration.md:23`、`:41`（AP 覆盖文件 `scenario/full-review/candidate/specs/runtime-migration.md`） | 仅 AP | 成功结果加 `summary`，失败结果加 `operation`；`:41` 点名复用 Promotion Runtime、Result Summary、Promotion Recovery 的公开合同 | AP 未选定该文件，不应引出 finding；RM 的 REQ#1/#2 依赖这一冲突，所以只改 AP 副本 |
| `specs/promotion-runtime.md:11` | RM、AP | "Readiness 在调用 Promotion Persistence Interface 前确认 …" | 与 Module 章节 `:45`、`:57` 对应；`:27` 的重复校验缺陷（MODULES#1）仍独立成立 |

答案键：

- `MODULE-DESIGN-MODULES` clean C0（vr:31）保留，expectation 改为"两个独立 operation 各自按 Invalid Artifact Contract 校验，既非重复责任也非未声明依赖"。
- `MODULE-DESIGN-INTERFACES` source 用例收窄为：source 的输入类型（非字符串、空）与 artifact-read-failed diagnostic path 的来源（invalid-artifact path 已由 `architecture/05:29` 定义）。
- `MODULE-DESIGN-SEAMS-ADAPTERS#1` 改为 placements，增加 `promotion-recovery.md:57+59` 证据组合；其 clean C3 改为"不同配置可得出不同结果，不是缺陷"。
- REQUIREMENTS clean C0 / C1 / C2 的 expectation 措辞改准（wording requirement；complete set of result fields；documentation-only reader-index requirement）。
- 用例数与 v2 相同。不对 AP 专属缺陷加 REQ/INPUTS placement：ARW 拆分时，带 REQ/INPUTS placement 的用例会被移出 AP。

## 审查过程

按 ARW Fixture authority 两阶段审查共 3 轮，每轮一个全新的 Opus 高推理强度审计者（阶段 1 只看可见内容，阶段 2 对照键），另由全新 Opus agent 按真实交接盲答 RM 与 AP，本工程评分：

| 轮次 | 阻断 / 主要 | 盲答 RM | 盲答 AP |
|---|---|---|---|
| 1 | 0 / 1（vr:31 歧义） | 0.968 | 0.604 |
| 2 | 0 / 1（vr:31 新句声明了未登记权威） | 0.992 | 0.686 |
| 3 | 0 / 0 | 0.986 | 0.739（clean 43/43） |

第 3 轮阶段 1 列出的 RM 5 条、AP 12 条应报缺陷全部对应键中用例；键中阶段 1 漏掉的两条（Access Review Interface 缺 verified-principal 输入、Policy Evaluation Seam 依赖方向缺理由）复核后判成立。

## 残余（次要，未改）

- RM 中 `access-review.md:15`、`promotion-runtime.md:11`、`promotion-recovery.md:19` 选定的 `#requirements` 把失败结果交给同文档未选的 Interfaces 节；`promotion-runtime.md:11` 与未选的 `:27` 有张力。严格的 Reviewer 可能据此报 REQUIREMENTS，键中无对应用例，按语义裁决。
- `vr:45` 处 INTERFACES 两个用例（unexpected-field 顺序、source 输入）共享关联点，同一 finding 会对两者都成为候选，靠裁决区分。
- MODULES#1 未加 DEPENDENCIES-DATA-FLOW placement；APPLICABILITY#1 只按 APPLICABILITY 计（Role 规定格式错误只归此检查）。
- `access-review.md:93` 未覆盖 policy 与 facts 同时无效的结果。
- ar:45 request 额外字段的结果未定义（第 1 轮 U1，低概率）。
