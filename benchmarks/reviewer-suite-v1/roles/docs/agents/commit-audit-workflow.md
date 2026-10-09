<!-- arw:managed:start -->
# Commit Audit 工作流

准备或执行本工作流前, 满足 [提交工作流的仓库排他规则](commits.md#exclusive-commit-audit). 该规则拥有开始条件, 允许的审计产物写入及结束边界.

## Commit Audit Reviewer thread reuse

Commit Audit Reviewer 线程身份由两部分组成:

- `spawn_agent` 请求中的 `input.role` 字段固定为 `commit-audit-reviewer`.
- `authorizingIssueIds` 中经过完整排序的 issue ID 集合.

与用户沟通的 Main Agent 按 [启动与控制 Reviewer 的操作步骤](reviewer.md#machine-operations) 提供完整的任务信息, 运行入口读取两级 Reviewer 用户配置, 通过独立 Codex App Server 启动审核. 首次启动不继承作者对话. 具有相同身份的后续调用必须复用其可靠 Reviewer 线程, 读取完整的当前输入, 并返回完整的替代结果. 只有 issue ID 集合发生变化, 现有线程不可用或无法恢复, 或者用户明确要求时, 才创建新线程作为替代. 候选字节, 摘要值, 文件哈希, 治理语义, 问题或结论本身的变化不要求创建新线程.

## Authorization scope and Gate 1 applicability

每次提交只包含一个 effort. Main Agent 只把当前 effort 的改动放入 Git 索引. `authorizingIssueIds` 是已暂存实施的完整 issue 授权范围, 可以包含该 effort 的多个 issue. Commit Audit Request 中的 Gate 1 范围只是本次提交实际适用的终态转换子集, 不要求与授权列表一一对应.

未完成的实施 issue 可以授权中间代码提交. 它出现在 `authorizingIssueIds` 中, 但不出现在 `gate1` 中, 因为其尚未完成的验收标准不得过早成为提交阻断项.

终态转换必须获得授权, 且必须具有 Gate 1, 包括 issue 新进入 `completed` 或 `wontfix`. ARW Engine 根据已暂存候选内容推导机械可见的终态转换, 并拒绝以下情况:

- 遗漏授权.
- 缺少适用的 Gate 1 项.
- 存在未授权的 Gate 1 项.
- 存在重复或冲突记录.

独立 Reviewer 判断 Git 无法证明的代码到 issue 关系, 包括只包含代码的候选内容和重新打开后再次完成的历史.

Gate 1 覆盖 `## What to build` 中每条非空, 非标题, 非围栏代码块的正文行, 每条验收标准, 以及每条仍然有效的评论或替代说明. 每项要求都具有精确的正数 issue 来源行, 简短要求, 证据, 以及 `satisfied`, `gap` 或 `uncertain` 结果. 结果为 `satisfied` 的要求必须具有证据且没有问题. 其他结果必须具有可采取行动的问题说明.

## Gate 2 scope

Gate 2 是 effort 级 Spec Audit, 不是 issue 审计. 当当前 effort 中的每个实施 issue 都处于终态时适用. ARW Engine 根据已经接受的授权 issue 和完整的已暂存 effort 清单推导适用性.

`.scratch/<NNNN>-<effort-slug>/spec-audit.json` 中的 `documents` 和要求, 是本批次已经接受的授权 issue 中有效 `## Spec Requirement` 引用的并集. 不得仅因 effort 把相关背景文档或长期规范作为输出更改, 就把它们加入其中. 每项独立的规范性要求都使用精确的治理来源行, 简短要求, 定向证据和结果. 审核范围和来源行数量下限遵循 [Gate 2 规则](roles/commit-audit-reviewer/gate-2.md).

如果适用 Gate 2 effort 的治理要求并集为空, 停止并取得用户明确确认. 只有包含具体 `reason` 和 UTC 秒级 `confirmedAt` 的批次例外才能产生完整的 `not-applicable` 记录. 空数组本身不构成确认.

## Independent Reviewer boundary

Main Agent 负责实施工作, 暂存, Request 目录, Engine 调用, Reviewer 协调, 正式文件提升和 Git 写入. `commit-audit-reviewer` 负责 Gate 1 和 Gate 2 的独立语义判断, 审查输入只接收 Request 的准确绝对路径. 该 Reviewer 必须亲自将完整审核报告写入 Request 指定的 `review.jsonl`, 并只返回完成状态. Reviewer 按 [单 Agent 执行规则](reviewer.md#single-agent-execution) 独自完成 Gate 1 和 Gate 2 审核, 不扩大审计证据或候选范围. Main Agent 不提供独立的 Gate 1 或 Gate 2 判断, Reviewer 不调用 Engine, 不生成正式 audit, 也不修改 Git 索引.

Main Agent 在仓库 `.tmp/` 下为本次审核建立独立目录, 并写入固定名称 `input.json`. 该对象只包含同一 effort 的完整排序 `authorizingIssueIds`, 以及适用时的单个 `gate2Exception`. 然后调用:

```text
arw commit-audit prepare --input <absolute-input-path>
```

`input.json` 的父目录就是本次 Request 目录. `prepare` 在该目录创建固定名称 `request.json`, 并在独立的 `reports/` 子目录中创建空 `review.jsonl`, 然后只返回 Request 的绝对路径. `reports/` 是本次审核唯一获授权的报告目录, `input.json`, `request.json` 和后续 Engine 正式结果保持在该目录之外. 除本次 `input.json` 外, 任何受管理文件碰撞都会使准备失败且不覆盖现有内容. 不同 Request 使用独立目录, 可以保留多轮记录, 但当前仓库的执行遵循上述排他规则, 不依赖全局当前 Request.

与用户沟通的 Main Agent 将准确的 Request 路径放入 `handoff`, 将 Request 指定的 `draftPath` 作为 `reportPath`, 并按上述操作步骤提供完整的角色指令和允许读写的范围, 运行入口统一读取 Reviewer 用户配置.

Commit Audit 开始后, Main Agent 保持完整暂存候选不变. Reviewer 可以逐项写入和修订绑定草稿, Main Agent 可以按需读取以核对和讨论, 但不能把中间稿作为完整结果. Reviewer 返回 `ready` 后, Main Agent 调用:

```text
arw commit-audit generate --request <absolute-request-path>
```

Engine 依次检查 `request`, `candidate-preconditions`, `review-syntax`, `requirement-coverage`, `evidence` 和 `output-plan`, 并只报告最早失败阶段中能够安全确定的全部诊断. `review-output-invalid` 由 Main Agent 完整转交同一 Reviewer 修订绑定草稿; `request-invalid`, `candidate-invalid`, `output-write-failed` 和 `generation-failed` 由 Main Agent 处理. 每次重试仍消费完整 JSONL.

成功时 Engine 在 Request 主目录中平铺生成 `03.audit.json`, `04.audit.json` 或 `spec-audit.json` 等适用文件, 并返回按 `targetPath` 排序的完整 `files` 映射. 每项 `sourcePath` 和 `targetPath` 都相对于仓库根目录, 且来源和目标各自唯一. Main Agent 只把映射指定的准确来源字节提升到对应目标并暂存. 任何结果为 `gap` 或 `uncertain` 都会阻止整批提升.

现有 Issue Audit, Spec Audit 和 Spec Readiness 记录不能作为证据或结论. 生成或验证这些记录的代码, 测试和文档仍可接受审查.

ARW Engine 从 Git 索引准备完整审核范围, 严格验证绑定 JSONL, 推导适用目标, 规范化证据和派生结果, 并只在完整成功时返回可提升的输出映射. 写入失败不返回映射, 尽力恢复已经写入的临时文件; 恢复失败的残留没有提升资格, 由后续完整重试覆盖. 正式 Gate 1 与 Gate 2 JSON 不使用 `schemaVersion`.

## Audit lifetime

Gate 1 和 Gate 2 只存在于提交准备阶段. implementation issue 可以进入 `completed`, Application Source Issue 可以镜像 `completed | wontfix`, Wayfinder issue 可以进入 `resolved`, 而无需审计伴随文件. `Full Issue Audit` 不是当前工作流.

已经提升的 Gate 1 或 Gate 2 记录只对经过审计和验证的已批准实施候选内容有效. 实施候选内容或审计结论的任何变化都要求建立新的 Request. 精确映射指定的正式记录是冻结后唯一允许加入 Git 索引的内容. 其他索引变化使 Main Agent 放弃当前 Request 并重新准备. 正式记录提升后到 `verify` 完成前不再改变索引.

`arw commit-audit verify` 只读取当前暂存终态变化所需的 Gate 1 和 Gate 2 记录. 仓库中的其他 audit 文件仅作为历史记录保留, 不参与当前候选验证.

## Gate 3

提交工作流使用 `code-review` 的有效结果, 或在需要时完成独立审查. 它可以与就绪审核并行, 但进入 Commit Audit 前必须完成适用的就绪检查, 实施验证和完整有效的双轴结果. `code-review` Skill Package 唯一拥有比较准备与过滤, 各轴输入, 结论复用, 完成记录例外, Reviewer 身份与线程复用, 重审, 失败和报告规则. 按该技能完成审计前收尾后, 冻结包括完成记录在内的完整实施候选. Commit Audit 只接受这组最终字节, 后续只能增加其精确生成的审计输出, 不得更改任何已冻结实施字节.
<!-- arw:managed:end -->
<!-- arw:repository-owned:start -->
None.
<!-- arw:repository-owned:end -->
