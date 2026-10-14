# Code Standards 正式场景（v5）运行计划

依据：
- `docs/plan.md`「Code Standards 正式场景 v5」（用户 2026-10-14）：阅读量 B 计入整个仓库；方案 A（Code Spec v5 无缺陷版仓库作 base、新写餐饮子系统作被审变更、`src/AGENTS.md` 改写为仓库自身满足的规则）；加难方向 A（规则网络题约占一半以内，其余守住复用/归属、同形异质、writing.md 结构问题、语言语义）；重复与相似类题约 1/3 或更多，配外形相似但不应合并的 clean 孪生；接受与 ARW 原版、F6 不可比；接受与 Code Spec 共用同一个仓库。
- 用户 2026-10-15：两类计分（`.claude/rules/measurement.md`），A 类正反例必须等数，不平衡就补题。

本文件在冻结时写定。2026-10-15 冻结修订 24（code-standards-reviewer 修订号 24），条件、补丁与 SHA 以 `code-standards-v5-iq3_xxs-2026-10-15/plan.json` 为准。逐题设计、A/B 归类理由、修订历史和已知偏差的完整记录在构造目录的 `design.md`。

## 1. 目的

测量 Q3（IQ3_XXS）在约 140K 阅读量、以规则网络和仓库内重复为主的代码规范审查上，相对 Opus-high 的能力比值。
- 判据：Q3/Opus（两类计分总分的均值比）< 0.8。
- 适用范围只限 Strata v0.1.44.1、rtx3080ti、IQ3_XXS。

## 2. 主机与模型

与 Code Spec v5 相同（`code-spec-v5.md` §2）：rtx3080ti，IQ3_XXS，Strata 0.1.44.1，Codex 0.162.0，effort high；参考模型 Opus-high 用无头 `claude -p`，隔离选项与 Bash 沙箱照 Code Spec v5。

## 3. 固定条件

- 引擎默认值、窗口 206584 / 压缩阈值 150000、启动提示与压缩提示接入、native CLI、测量说明时限模板：与 Code Spec v5 冻结计划相同，开跑前核对实际加载的 SHA 并保存绑定。
- 场景：`current/manifest.json` 栈（末位 `code-spec-v4.patch`）之后叠加 `arw-patches/code-standards-v5.patch`（sha256 `fc195527ed0dec1c980d4dcfe1c3df5203ba7ae44547b9b4083d1246ed5f42f9`），manifest `source-snapshots/current/manifest-code-standards-v5.json`。
- 阅读材料：B = 142,529 字节（变更后 `src` 全部 + `src/AGENTS.md`）。
- 时限：T 秒 = B ×（1/P + k/G）/ β，k 2.0755、β 3.6591 沿用 Code Spec v5；每批开跑前在本场景材料上用速度探针重测 P、G。冻结前 trial 的 T_Q3 为 887–952 秒。Opus 的时限做法同 Code Spec v5。

## 4. 题目与用例

- **问题用例 26 个**（S01–S26）：保底 2（默认导出、`Date.now`）；规则网络 7（rule 模块的内置 import 与 catch、藏在上下文对象或柯里化 helper 里的 `now`、store 记录原地修改、跨 feature 引 service 模块、store 吞错）；语言语义与质量、设计 8（未冻结、`new Error(msg, error)`、原地 sort、浅拷贝 push、class、纯转发、再导出模块、投机选项）；重复与相似 9（与仓库已有函数或设置同一规则/事实，写法不同，全部未达逐字线）。
- **clean 用例 35 个 + `noOtherSupportedFinding`**：重复类孪生 T1–T8、规则网络例外、冻结、复用、入口契约等。
- **A 类判断题 10:10**（答案键 `judgment: true`）：正例为重复与相似 9 题加投机选项 S26；反例为 T1–T8、`cancellationFeeDistinct`、`invoiceEntryContract`。其余归 B：规则网络、语言语义、纯转发等误报一核实即可排除。
- 答案键 sha256 `217798004f35e19bc24a8badc522a9a80d538be71c008dd1203ba7f32883cbd2`，在 `judgment/registry.json` 登记为 in-key。

## 5. 规模

- 正式：Q3 ×5（每次全新 ARW 准备、冷加载），Opus-high ×3，与 Q3 并行。
- 空闲加测：GPU 空闲时 Q3 加测到 10 次。目标事先定为 10，不按中途结果决定；报告同时给前 5 次和全部结果。

## 6. 预计耗时

- 每个 Q3 实例：探针约 1 分钟，运行约 9–16 分钟（冻结前 trial 实测 9.0–9.6 分钟工作时间）。Q3 ×5 约 70 分钟，加测到 10 次再约 70 分钟。
- Opus ×3：每次约 25–40 分钟，与 Q3 并行。
- 评估：机械计分、盲裁、会话检查约 40 分钟。

## 7. 前置条件

- 构造检查（修订 24）：54 个变体（all、none、26 个单项修正、26 个单项保留）上 verify、规则 lint 与餐饮测试全过，每题的修正只翻转自己；重复题等价性证明 S17–S25 成立；similarity 9 题未达逐字线（最高 0.61）；base 与全部修正版 lint 为空；干草堆单元测试 171/171、Code Spec 探针 89/89；两类计分补丁下 conformance 70/70。
- 审查：修订 15、18、20、22 各一次独立 Opus-high 盲审；修订 22 盲审 25/26（漏 S20，判为真实难度），所提 I1–I4 在修订 23 修正，复审补修 1 项（修订 24）后结论为可以冻结。
- 中性规则：正式运行在冻结代码上报出的答案键外发现，核实为真缺陷的修正留给下一版，本版按中性处理，既不算 `noOtherSupportedFinding` 失败，也不计分；核实由盲化的独立裁决 agent（Opus，effort 不低于 Main）完成，Main 再用可执行检查复核。
- 每实例经前端领租约、冷加载，结束后停模型并归还租约；不抢占。

## 8. 判据、计分与报告

- 判据：Q3 ×5 均分 / Opus ×3 均分 < 0.8，按两类计分总分。独立 agent（不低于 Main）给意见后由 Main 判定。
- 命中按 ARW 关联计，盲裁流程与 Code Spec v5 相同。
- 报告：总分、A 部分、B 部分（召回与 clean 通过率）；逐题命中（Q3、Opus）；按类别（保底、规则网络、语言语义与设计、重复与相似）与 A/B 汇总；全部 clean 失败、中性处理项、时限中断、压缩、运行方式混杂项。

## 9. 已知偏差（design.md 记录）

- 设计异味与重复题的成立依赖判断，答案键外发现按中性规则处理。
- 仓库本身仍有不在变更范围内的既有重复（`normalizeMemberId` 等）；role 规定历史问题不扩展为 finding。
- `catering-service.mjs` 集中了 9 题；S11 与孪生 `menuFor` 相邻；T4 紧挨 S20。均已登记，审查未发现新的结构线索。
- 变更修改了 3 个已有文件，整个文件属于审查范围。
