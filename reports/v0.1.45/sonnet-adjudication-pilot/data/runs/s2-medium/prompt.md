# Code Standards v5.1（修订 25）盲裁 brief（Sonnet 试点重建，2026-10-19）

原池（`.tmp/code-standards-v5/v51/pool.json`）当时的裁决 brief 没有存档；本 brief 由冻结 ARW 的 Adjudication 原文与 Code Standards v5.1 变更说明（`benchmarks/reviewer-suite-v1/code-standards-v5.md` §10）重建，只替换 `/home/pello/arw-opus/sadj-s2-medium`（裁决工作目录）与 `s2`（池名）。

你是盲裁决者。任务：对候选池中每个候选给出一个决定。你看不到候选来自哪个模型、哪次运行；不要试图推断。

## 输入

- 候选池：`/home/pello/arw-opus/sadj-s2-medium/pool-s2.json`。每项有 `id`、`group`（同一期望句的候选归为一组）、`kind`（均为 `association`）、`allowedDecisions`（`matched` 或 `not-matched`）、`expectation`（答案键问题用例的期望句）、`finding`（被审 Code Standards 报告的一条 finding 原文，含其证据定位）。
- 只依据池中文字判断；不读工作目录以外的任何文件。

## 决定语义（ARW 原文，冻结 ARW `docs/agents/reviewer-capability-verification.md`「Adjudication」节第一段，原样）

对于 `needs-adjudication`, Main Agent 根据当前场景和适用要求, 将每个候选中冻结的 `expectation` 与同一候选中规范化的 finding 正文, 结果和证据逐项比较, 判断是否表达同一个真实缺陷. 所有候选都需要决定, 不因词组匹配而自动接受, 也不因同题已有另一条匹配而跳过. 无法确定时选择 `not-matched`. Main Agent 只决定是否关联, 不改写结果类别, 原始文本或证据, 不跨 finding 拼接, 也不直接调整分数或门禁. 验证器以确认后的关联按[最终评分规则](reviewer-capability-scoring.md#final-score)计算批次结果. 写入格式严格为 `{ "decisions": [{"candidateId": "<candidate-id>", "decision": "matched", "reason": "<non-empty reason>"}] }` 的临时 JSON 对象. 拒绝配对项时使用 `not-matched`. 返回的每个候选项必须恰好出现一次, 且不得包含其他候选项. 然后使用相同的 `--prepared` 和 `--input`, 加上 `--adjudication <decisions-path>`, 再次运行 `verify`. 临时决定文件没有模式版本, 持久兼容承诺, 候选内容哈希, 响应摘要值或修改绑定. 第二次调用从相同输入重新建立完整候选集合, 拒绝格式错误, 缺失, 重复或多余的决定. 只有 `matched` 配对参与问题关联和后续评分; `not-matched` 不建立关联. 该两阶段路径同样适用于定向迭代和发布验证. 面向人的结果按最终评分规则展示.

## 本场景口径（Code Standards v5.1）

- 被审变更是餐饮子系统 `src/catering/`，规则在 `src/AGENTS.md`。期望句描述一个真实缺陷；finding 与它表达同一个缺陷（同一对象、同一错误含义）才算 `matched`。同一文件或同一规则下的另一个问题不算。
- 重复/近似代码类题（期望句说变更端与已有的另一处代码重复同一规则、常量或逻辑）：finding 只要指出变更端，并写出对端（符号名、文件基名或行号任一即可）且所说的对端与期望句一致，即可匹配；对端不必写行号。

## 输出

写 `/home/pello/arw-opus/sadj-s2-medium/decisions-s2.json`，格式严格为：
`{"adjudicator": "blind", "decisions": [{"id": "<池中 id>", "decision": "<allowedDecisions 之一>", "reason": "<一句中文理由>"}]}`
池中每个 id 恰好出现一次。判断不了时选 `not-matched`。同组候选逐个独立判断，不因同组其他候选的决定而跳过。完成后用一条 python 命令核对 id 集合与池完全相同、每个决定都在 allowedDecisions 内，并在最终回复中给出各决定的计数和你认为最难判的 3–5 项（id + 理由）。
