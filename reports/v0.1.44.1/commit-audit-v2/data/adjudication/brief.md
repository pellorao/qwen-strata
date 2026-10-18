# Commit Audit v2（修订号 23）盲裁 brief

你是盲裁决者。任务：对候选池中每个候选给出一个决定。你看不到候选来自哪个模型、哪次运行；不要试图推断。

## 输入

- 候选池：`/home/pello/projects/qwen_strata/.tmp/commit-audit/measure/adj/pool-<名>.json`（调用方给出名字）。每项有 `id`、`group`（同一期望句的候选归为一组）、`kind`、`check`（Gate）、`allowedDecisions`、`expectation`（答案键问题用例的期望句；`finding` 类候选为 null）、`finding`（被审报告的 finding 正文）、`result`（gap/uncertain）、`evidence`（报告给出的证据定位或命令）、`requirementSource`（若有：该 finding 所在的要求行）；`finding` 类另有 `problemOptions`（可补关联的问题用例及其期望句）和 `cleanTargets`（被提名的干净用例）。
- 被审的已暂存代码与文档（只读）：`/home/pello/projects/qwen_strata/.tmp/commit-audit/measure/adj/view/`（issues 与 spec 在 `.scratch/0001-dispatch-control/`，源码在 `src/dispatch/`，测试在 `tests/dispatch/`，存储合同在 `docs/dispatch/storage-contract.md`）。核实 finding 是否有依据时只读这里，不读工程其他目录、`.tmp` 其他目录、答案键或任何运行目录。
- 不运行被审代码以外的东西；需要时可以 `node` 运行 view 下的代码做核实（不写文件）。

## 决定语义（ARW 原文，冻结 ARW `docs/agents/reviewer-capability-verification.md`「Adjudication」节，原样）

## Adjudication

对于 `needs-adjudication`, Main Agent 根据当前场景和适用要求, 将每个候选中冻结的 `expectation` 与同一候选中规范化的 finding 正文, 结果和证据逐项比较, 判断是否表达同一个真实缺陷. 所有候选都需要决定, 不因词组匹配而自动接受, 也不因同题已有另一条匹配而跳过. 无法确定时选择 `not-matched`. Main Agent 只决定是否关联, 不改写结果类别, 原始文本或证据, 不跨 finding 拼接, 也不直接调整分数或门禁. 验证器以确认后的关联按[最终评分规则](reviewer-capability-scoring.md#final-score)计算批次结果. 写入格式严格为 `{ "decisions": [{"candidateId": "<candidate-id>", "decision": "matched", "reason": "<non-empty reason>"}] }` 的临时 JSON 对象. 拒绝配对项时使用 `not-matched`. 返回的每个候选项必须恰好出现一次, 且不得包含其他候选项. 然后使用相同的 `--prepared` 和 `--input`, 加上 `--adjudication <decisions-path>`, 再次运行 `verify`. 临时决定文件没有模式版本, 持久兼容承诺, 候选内容哈希, 响应摘要值或修改绑定. 第二次调用从相同输入重新建立完整候选集合, 拒绝格式错误, 缺失, 重复或多余的决定. 只有 `matched` 配对参与问题关联和后续评分; `not-matched` 不建立关联. 该两阶段路径同样适用于定向迭代和发布验证. 面向人的结果按最终评分规则展示.

本工程计分升级 r7: 每个候选带 `kind` 与 `allowedDecisions`. 关联候选 (`kind: "association"`) 的决定仍为 `matched` 或 `not-matched`, 并附问题用例 `findingTerms` 作 `referenceTerms`, 仅供参考. 一个 finding 的全部关联候选都已决定且都不是 `matched`, 或它没有关联候选时, 形成发现候选 (`kind: "finding"`, `candidateId` 含 `unassociated`), 附被证据与概念规则提名的干净用例 (`cleanTargets`) 和本范围可补关联的问题用例 (`problemOptions`); 决定取 `problem-N` (补关联到第 N 个问题用例, 按该 finding 的证据计分), `false-positive:clean-N` (确认误报第 N 个干净用例, 只能选被提名的), `unsupported` 或 `supported`. 序号均从 1 起按范围内声明顺序计. 候选集合随关联决定变化, 所以验证器先按提供的决定重新计分, 再核对决定: 每个决定必须对应这次计分的一个候选且取允许值, 否则失败; 仍缺决定的候选以 `needs-adjudication` 返回, 补齐后把全部决定写入同一文件再次运行. 判断不了时, 关联候选选 `not-matched`, 发现候选选 `unsupported`.

本工程补充（评分 r8.1、r8.3）：Commit Audit 的 finding 落在答案键判为 satisfied 的要求行上时，计分器直接提名该行干净用例（`cleanTargets`）；`problemOptions` 只列同一要求行的问题用例。`supported` 指 finding 有依据但不对应任何列出的问题用例（不得分也不扣分）；`unsupported` 指无依据（计一个失败反例）；`false-positive:clean-N` 只能选被提名的干净用例。

## 裁决口径（`benchmarks/reviewer-suite-v1/commit-audit-v2.md`「裁决口径」一段，原样；sha256 d70bf9463660ecff34a8cd066f4898eeab5eab034d95c853fa5f4f20f6eda90b）

裁决口径（判定候选是否与用例匹配时使用，随答案键一起冻结，正式盲裁的 brief 原样带上本段并记录其 sha256；行号为修订号 23 夹具行号；issue 行号与修订号 21、22 相同，spec 第 14 行起比修订号 21、22 小 1）：

- 把令牌字段置为 `undefined` 算移除（JSON 序列化后不出现）；
- `localeCompare` 视为字典序；
- spec:11（"Stable JSON sorts keys recursively at every object depth."，Gate 2 正例 `toStableJson` 只排顶层）：finding 指出只排顶层、嵌套对象顺序不变即匹配，不必写出"递归"；
- 01:51（"`serializePlan` sorts keys lexically, uses two-space JSON, and ends with one LF."，Gate 1 正例：格式模式导致缺末尾 LF）：finding 必须指出缺末尾 LF；只以"只排顶层"或 `localeCompare` 为理由的 finding 不匹配，裁为 `unsupported`。
- 引用已审行（第 3 轮审计）：finding 只引用已审行（如 "Same as spec:27"）并照抄结论与证据时，按被引行的 finding 文本裁决。被引行与本用例同属一个合并用例时，本行裁决与被引行相同；不在同一合并用例时（例如 spec:8 引 02:31），引用本身不构成理由，按本行自身的期望句裁决。
- 合并用例的候选与两侧任一期望句描述的是同一缺陷即算匹配（例如 01:49+spec:26 一侧只谈 `withinVehicleCapacity` 的严格小于，另一侧期望句点名 `canAssignAllPackages`，仍算匹配）。

## 输出

写 `/home/pello/projects/qwen_strata/.tmp/commit-audit/measure/adj/decisions-<名>.json`，格式严格为：
`{"adjudicator": "blind Opus high", "decisions": [{"id": "<池中 id>", "decision": "<allowedDecisions 之一>", "reason": "<一句中文理由>"}]}`
池中每个 id 恰好出现一次。判断不了时，关联候选选 `not-matched`，发现候选选 `unsupported`。同组候选逐个独立判断，不因同组其他候选的决定而跳过。完成后用一条 python 命令核对 id 集合与池完全相同、每个决定都在 allowedDecisions 内，并在最终回复中给出各决定的计数和你认为最难判的 3–5 项（id + 理由）。
