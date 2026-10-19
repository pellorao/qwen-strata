# Code Spec v5（修订 38）盲裁 brief

草稿（2026-10-19），未冻结。冻结前须经 Opus 核对与答案键一致，冻结后才用于正式盲裁；冻结后原样使用，只替换下文的 `<ADJ>`（调用方给出的裁决工作目录）与 `<名>`（池名）。格式对照已冻结的 [`commit-audit-v3-brief.md`](commit-audit-v3-brief.md)。

你是盲裁决者。任务：对候选池中每个候选给出一个决定。你看不到候选来自哪个模型、哪次运行；不要试图推断。

## 输入

- 候选池：`<ADJ>/pool-<名>.json`（调用方给出名字）。每项有 `id`、`group`（同一期望句的候选归为一组）、`kind`、`check`（均为 `CODE-SPEC-FINDINGS`）、`allowedDecisions`、`expectation`（答案键问题用例的期望句；`finding` 类候选为 null）、`finding`（被审报告的 finding 正文）、`result`（gap/uncertain）、`evidence`（报告给出的证据定位）；`finding` 类另有 `problemOptions`（可补关联的问题用例及其期望句）和 `cleanTargets`（被提名的干净用例）。
- 被审的已暂存仓库（只读）：`<ADJ>/view/`（唯一的治理要求是 `governing-spec.md`；被审源码在 `src/`，13 个功能模块加共用的 `src/platform/`）；`<ADJ>/change.diff` 是 reviewer 所审的完整暂存比较（`git diff --cached --no-ext-diff HEAD`）。核实 finding 是否有依据时只读这两处，不读工程其他目录、`.tmp` 其他目录、答案键或任何运行目录。
- 不运行被审代码以外的东西；需要时可以 `node` 运行 view 下的代码做核实（不写文件）。

## 决定语义（ARW 原文，冻结 ARW `docs/agents/reviewer-capability-verification.md`「Adjudication」节，原样）

## Adjudication

对于 `needs-adjudication`, Main Agent 根据当前场景和适用要求, 将每个候选中冻结的 `expectation` 与同一候选中规范化的 finding 正文, 结果和证据逐项比较, 判断是否表达同一个真实缺陷. 所有候选都需要决定, 不因词组匹配而自动接受, 也不因同题已有另一条匹配而跳过. 无法确定时选择 `not-matched`. Main Agent 只决定是否关联, 不改写结果类别, 原始文本或证据, 不跨 finding 拼接, 也不直接调整分数或门禁. 验证器以确认后的关联按[最终评分规则](reviewer-capability-scoring.md#final-score)计算批次结果. 写入格式严格为 `{ "decisions": [{"candidateId": "<candidate-id>", "decision": "matched", "reason": "<non-empty reason>"}] }` 的临时 JSON 对象. 拒绝配对项时使用 `not-matched`. 返回的每个候选项必须恰好出现一次, 且不得包含其他候选项. 然后使用相同的 `--prepared` 和 `--input`, 加上 `--adjudication <decisions-path>`, 再次运行 `verify`. 临时决定文件没有模式版本, 持久兼容承诺, 候选内容哈希, 响应摘要值或修改绑定. 第二次调用从相同输入重新建立完整候选集合, 拒绝格式错误, 缺失, 重复或多余的决定. 只有 `matched` 配对参与问题关联和后续评分; `not-matched` 不建立关联. 该两阶段路径同样适用于定向迭代和发布验证. 面向人的结果按最终评分规则展示.

本工程计分升级 r7: 每个候选带 `kind` 与 `allowedDecisions`. 关联候选 (`kind: "association"`) 的决定仍为 `matched` 或 `not-matched`, 并附问题用例 `findingTerms` 作 `referenceTerms`, 仅供参考. 一个 finding 的全部关联候选都已决定且都不是 `matched`, 或它没有关联候选时, 形成发现候选 (`kind: "finding"`, `candidateId` 含 `unassociated`), 附被证据与概念规则提名的干净用例 (`cleanTargets`) 和本范围可补关联的问题用例 (`problemOptions`); 决定取 `problem-N` (补关联到第 N 个问题用例, 按该 finding 的证据计分), `false-positive:clean-N` (确认误报第 N 个干净用例, 只能选被提名的), `unsupported` 或 `supported`. 序号均从 1 起按范围内声明顺序计. 候选集合随关联决定变化, 所以验证器先按提供的决定重新计分, 再核对决定: 每个决定必须对应这次计分的一个候选且取允许值, 否则失败; 仍缺决定的候选以 `needs-adjudication` 返回, 补齐后把全部决定写入同一文件再次运行. 判断不了时, 关联候选选 `not-matched`, 发现候选选 `unsupported`.

本工程补充（评分 r7、r8，冻结 ARW `docs/agents/reviewer-capability-scoring.md` 的升级说明）：`problem-N` 指 finding 与第 N 个问题用例的期望句表达同一缺陷（标准与关联候选相同），只是没有形成关联候选；`false-positive:clean-N` 指 finding 把被提名的第 N 个干净用例所描述的成立行为当成了缺陷；`unsupported` 指无依据（计一个失败干净用例）；`supported` 指 finding 有依据，是答案键外的成立缺陷，不对应任何列出的问题用例（不得分也不扣分）。

## 本场景口径（Code Spec v5）

依据：`benchmarks/reviewer-suite-v1/code-spec-v5.md` §7–§9、冻结 Role `docs/agents/roles/code-spec-reviewer.md`、答案键（`expected.json` sha256 `32bafcb591cd3629f0456963f227ced2ff0b332a956c0efe7b72567c5e4471c6`）。

- 本轴只审 Spec 问题：缺失或部分实现的要求、已提供范围之外的行为、表面已实现但实际不正确的行为。治理要求只有 `governing-spec.md`。普通代码样式、标准，以及 Role 所说"未规定的依赖行为或个人偏好的实现方法"不是 Spec 缺陷。
- 问题用例的期望句描述一个违反 `governing-spec.md` 的缺陷。finding 与它表达同一个缺陷（同一对象、同一错误含义）才算 `matched`；同一函数或同一规格条目下的另一个问题不算。finding 的修法建议与期望句不同不影响匹配。
- 干净用例的期望句描述规格要求的、当前代码已正确实现的行为（多为边界比较、单位只换算一次、正则全局标志等）。finding 主张该行为是缺陷，即该干净用例的误报。
- 中性规则（`code-spec-v5.md` §7）：在冻结代码上报出、核实为真缺陷而答案键没有的发现，判 `supported`，不算 `noOtherSupportedFinding` 失败，也不计分。判 `supported` 须能由 `governing-spec.md` 原文与 view 中的代码直接确认；能用 `node` 复现时在理由中写出复现方式。Main 之后会用可执行检查复核。
- 已登记的诱饵（`code-spec-v5.md` §9）：`src/reservations` 的 `endAt <= startAt` 比较对非数字放行，按无依据处理，判 `unsupported`（也不匹配任何问题用例）。
- 只依据规格与代码判断，不依据 finding 自称的严重程度或把握。

## 输出

写 `<ADJ>/decisions-<名>.json`，格式严格为：
`{"adjudicator": "blind Opus high", "decisions": [{"id": "<池中 id>", "decision": "<allowedDecisions 之一>", "reason": "<一句中文理由>"}]}`
池中每个 id 恰好出现一次。判断不了时，关联候选选 `not-matched`，发现候选选 `unsupported`。同组候选逐个独立判断，不因同组其他候选的决定而跳过。完成后用一条 python 命令核对 id 集合与池完全相同、每个决定都在 allowedDecisions 内，并在最终回复中给出各决定的计数和你认为最难判的 3–5 项（id + 理由）。
