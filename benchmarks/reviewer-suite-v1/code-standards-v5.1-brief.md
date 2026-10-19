# Code Standards v5.1（修订 25）盲裁 brief

冻结件（2026-10-19），正式盲裁原样使用，只替换下文的 `<ADJ>`（调用方给出的裁决工作目录）与 `<名>`（池名）。

你是盲裁决者。任务：对候选池中每个候选给出一个决定。你看不到候选来自哪个模型、哪次运行；不要试图推断。

## 输入

- 候选池：`<ADJ>/pool-<名>.json`（调用方给出名字）。每项有 `id`、`group`（同一期望句的候选归为一组）、`kind`、`check`（均为 `CODE-STANDARDS-FINDINGS`）、`allowedDecisions`、`expectation`（答案键问题用例的期望句；`finding` 类候选为 null）、`finding`（被审报告的 finding 正文）、`result`（gap/uncertain）、`evidence`（报告给出的证据定位）；`finding` 类另有 `problemOptions`（可补关联的问题用例及其期望句）和 `cleanTargets`（被提名的干净用例）。
- 被审的已暂存仓库（只读）：`<ADJ>/view/`（规则在 `src/AGENTS.md`；被审变更是新写的餐饮子系统 `src/catering/`，另修改了 3 个已有文件 `src/platform/site-settings.mjs`、`src/billing/invoice-service.mjs`、`src/billing/line-items.mjs`；仓库其余部分是已有实现）；`<ADJ>/change.diff` 是 reviewer 所审的完整暂存比较（`git diff --cached --no-ext-diff HEAD`）。核实 finding 是否有依据时只读这两处，不读工程其他目录、`.tmp` 其他目录、答案键或任何运行目录。
- 不运行被审代码以外的东西；需要时可以 `node` 运行 view 下的代码做核实（不写文件）。唯一例外是「输出」一节要求的那条 python 核对命令。

## 决定语义（ARW 原文，冻结 ARW `docs/agents/reviewer-capability-verification.md`「Adjudication」节，原样）

## Adjudication

对于 `needs-adjudication`, Main Agent 根据当前场景和适用要求, 将每个候选中冻结的 `expectation` 与同一候选中规范化的 finding 正文, 结果和证据逐项比较, 判断是否表达同一个真实缺陷. 所有候选都需要决定, 不因词组匹配而自动接受, 也不因同题已有另一条匹配而跳过. 无法确定时选择 `not-matched`. Main Agent 只决定是否关联, 不改写结果类别, 原始文本或证据, 不跨 finding 拼接, 也不直接调整分数或门禁. 验证器以确认后的关联按[最终评分规则](reviewer-capability-scoring.md#final-score)计算批次结果. 写入格式严格为 `{ "decisions": [{"candidateId": "<candidate-id>", "decision": "matched", "reason": "<non-empty reason>"}] }` 的临时 JSON 对象. 拒绝配对项时使用 `not-matched`. 返回的每个候选项必须恰好出现一次, 且不得包含其他候选项. 然后使用相同的 `--prepared` 和 `--input`, 加上 `--adjudication <decisions-path>`, 再次运行 `verify`. 临时决定文件没有模式版本, 持久兼容承诺, 候选内容哈希, 响应摘要值或修改绑定. 第二次调用从相同输入重新建立完整候选集合, 拒绝格式错误, 缺失, 重复或多余的决定. 只有 `matched` 配对参与问题关联和后续评分; `not-matched` 不建立关联. 该两阶段路径同样适用于定向迭代和发布验证. 面向人的结果按最终评分规则展示.

本工程计分升级 r7: 每个候选带 `kind` 与 `allowedDecisions`. 关联候选 (`kind: "association"`) 的决定仍为 `matched` 或 `not-matched`, 并附问题用例 `findingTerms` 作 `referenceTerms`, 仅供参考. 一个 finding 的全部关联候选都已决定且都不是 `matched`, 或它没有关联候选时, 形成发现候选 (`kind: "finding"`, `candidateId` 含 `unassociated`), 附被证据与概念规则提名的干净用例 (`cleanTargets`) 和本范围可补关联的问题用例 (`problemOptions`); 决定取 `problem-N` (补关联到第 N 个问题用例, 按该 finding 的证据计分), `false-positive:clean-N` (确认误报第 N 个干净用例, 只能选被提名的), `unsupported` 或 `supported`. 序号均从 1 起按范围内声明顺序计. 候选集合随关联决定变化, 所以验证器先按提供的决定重新计分, 再核对决定: 每个决定必须对应这次计分的一个候选且取允许值, 否则失败; 仍缺决定的候选以 `needs-adjudication` 返回, 补齐后把全部决定写入同一文件再次运行. 判断不了时, 关联候选选 `not-matched`, 发现候选选 `unsupported`.

本工程补充（评分 r7、r8，冻结 ARW `docs/agents/reviewer-capability-scoring.md` 的升级说明）：`problem-N` 指 finding 与第 N 个问题用例的期望句表达同一缺陷（标准与关联候选相同），只是没有形成关联候选；`false-positive:clean-N` 指 finding 把被提名的第 N 个干净用例所描述的成立做法当成了问题；`unsupported` 指无依据（计一个失败干净用例）；`supported` 指 finding 有依据，是答案键外的成立问题，不对应任何列出的问题用例（不得分也不扣分）。

## 本场景口径（Code Standards v5.1）

依据：`benchmarks/reviewer-suite-v1/code-standards-v5.md` §7–§10、冻结 Role `docs/agents/roles/code-standards-reviewer.md`、答案键（`expected.json` sha256 `3950875c7c223af3beee58265c1fb9eb3ff48cf21cbd4b94ffa43a124a0d0b66`）。

- 本轴只审 Standards 问题：违反 `src/AGENTS.md` 的规则，或 Role 列出的实施质量问题（含重复代码、纯转发、投机选项等设计检查）。Role 规定不判断变更是否实现产品或 issue 要求，不添加 Spec 轴问题；关联实现只作为判断当前变更的证据，不把其中独立存在的历史问题扩展为本次 finding。
- 问题用例的期望句描述一个真实问题。finding 与它表达同一个问题（同一对象、同一错误含义）才算 `matched`；同一文件或同一规则下的另一个问题不算。finding 的结果类别（gap/uncertain）与期望不同，但所说的缺陷相同时仍算匹配，结果分由评分规则处理；裁决者不因结果类别改判。
- 重复/近似代码类题（期望句说变更端与已有的另一处代码重复同一规则、常量或逻辑）：finding 只要指出变更端，并写出对端（符号名、文件基名或行号任一即可）且所说的对端与期望句一致，即可匹配；对端不必写行号（v5.1 改动一，用户 2026-10-15 确认）。只说变更端"可以抽取 helper"而没有指出对端的，不匹配。
- 干净孪生：一部分干净用例的期望句说某处与仓库另一处看似相同、但规则或事实不同，不应合并（或不应复用）。finding 主张它们重复、要求合并或复用，即该干净用例的误报。
- `extraCharges` 诱饵（答案键两个干净用例）：`buildLineItems` 的新参数 `extraCharges`（`src/billing/line-items.mjs:26`）由唯一调用方 `draftFor`（`src/billing/invoice-service.mjs`）传入；`previewInvoice`、`issueInvoice` 的 `extraCharges` 入口参数（`src/billing/invoice-service.mjs:22`、`src/billing/invoice-service.mjs:32`）与其他 service 入口一样由仓库外调用，餐饮入口 `memberInvoiceCharges`（`src/catering/catering-service.mjs:148`）用 `invoiceCharges`（`src/catering/catering-pricing.mjs:30`）构造这个输入。finding 主张 `extraCharges` 是投机选项、未被使用、没有调用方或应删除，即对应干净用例的误报：该干净用例在 `cleanTargets` 中被提名时判 `false-positive:clean-N`，未被提名时判 `unsupported`。
- `memberId` 诱饵：`buildLineItems` 对 `extraCharges` 的每项去掉 `memberId`（`src/billing/line-items.mjs:32`）。`memberId` 只供 `isBilled` 按会员过滤，过滤后去掉，使附加项与经 `lineItemFor` 构造、同样不含 `memberId` 的预订行项字段一致；发票本身另记 `memberId`。finding 称这里丢失会员信息、行项不一致或应保留 `memberId`，没有依据，判 `unsupported`。
- 中性规则（`code-standards-v5.md` §7）：被审变更范围内（`src/catering/` 的新文件，以及被修改的 3 个已有文件的全部内容）违反 `src/AGENTS.md` 或 Role 质量标准、核实成立而答案键没有的问题，判 `supported`，不算 `noOtherSupportedFinding` 失败，也不计分。只存在于未改动文件的既有问题（例如仓库已有的 `normalizeMemberId` 一类既有重复），按 Role 不扩展为 finding，判 `unsupported`；修法与某个干净用例所描述的成立做法相反的 finding：该干净用例在 `cleanTargets` 中被提名时判对应的 `false-positive:clean-N`，未被提名时判 `unsupported`。Main 之后会用可执行检查复核 `supported`。
- 只依据规则、Role 与代码判断，不依据 finding 自称的严重程度或把握。

## 输出

写 `<ADJ>/decisions-<名>.json`，格式严格为：
`{"adjudicator": "blind Opus high", "decisions": [{"id": "<池中 id>", "decision": "<allowedDecisions 之一>", "reason": "<一句中文理由>"}]}`
池中每个 id 恰好出现一次。判断不了时，关联候选选 `not-matched`，发现候选选 `unsupported`。同组候选逐个独立判断，不因同组其他候选的决定而跳过。完成后用一条 python 命令核对 id 集合与池完全相同、每个决定都在 allowedDecisions 内，并在最终回复中给出各决定的计数和你认为最难判的 3–5 项（id + 理由）。
