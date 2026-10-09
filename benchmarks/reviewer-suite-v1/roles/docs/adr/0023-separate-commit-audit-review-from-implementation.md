# 分离 Commit Audit 审核与实现责任

Commit Audit 的 Gate 1 和 Gate 2 曾由 Main Agent 同时编写实现, 判断验收结论并调用 Engine 写入. 这让同一个个体同时成为实现者和验收者. 这些责任会长期影响提交流程, Reviewer Role, 平台配置和审计文件的权威关系, 因此需要独立的决定记录.

## Decision

Gate 1 和 Gate 2 在通用提交工作流判定 Commit Audit 适用后运行; 准确调用条件只由[提交工作流](../agents/commits.md#implementation-issue-commit-workflow)拥有. Main Agent 准备完整的候选范围, 按 `code-review` Skill Package 的有效性规则复用已有完整 Gate 3 结果, 或完成必要的 Standards 与 Spec 双轴审核. 就绪审核与代码审核按[公共版本规则](../agents/reviewer.md#review-versions-and-concurrency)并行, 有效就绪结果的检查时点由[设计就绪工作流](../agents/spec-readiness.md#authorization-timing)拥有. 审查候选不包含本次 Gate 1 或 Gate 2 输出.

需要新审核时, Reviewer 一旦核实问题就写入结果文件. Main Agent 可按需读取并独立核对, 并处理已授权修复或请求必要决定; 两个审核轴仍各自返回完整结果. Main Agent 按 [ADR 0013](0013-use-main-agent-single-writer-orchestration.md) 协调实现和修复, 负责暂存, Reviewer 调用, 结论检查和文件提升, 但不负责独立审核结论.

Gate 3 获得完整有效的通过结果后, Main Agent 按 `code-review` 唯一拥有的完成记录例外核对并完成收尾. 随后验证文档变化, 冻结最终完整候选的路径集合, 已暂存 blob 身份和树. 该例外只作用于 Commit Audit 开始前, 不排除 issue 完成记录的审计责任.

Commit Audit 适用时, Main Agent 先满足[当前仓库的审计排他规则](../agents/commits.md#exclusive-commit-audit), 再为本次唯一 effort 提供完整排序的 `authorizingIssueIds`, 准备独立 Reviewer Request, 并调用 `commit-audit-reviewer`. 审计开始后, 只有这组最终实施字节有效, 且只能原样加入 Engine 成功映射的准确审计输出.

`authorizingIssueIds` 表示已暂存实现的完整 issue 授权范围. `gate1` 只表示本次提交实际适用 Gate 1 的子集. 未完成 issue 可以授权中间提交而不进入 Gate 1. Engine 从实时已暂存索引推导机械可见终态转换并拒绝授权或 Gate 1 遗漏, Reviewer 复核 Git 无法证明的仅代码候选, 重新打开后再次完成的历史, 以及任意代码与 issue 的语义关系.

Main Agent 在仓库 `.tmp/` 下为每次审核建立独立目录, 写入只含 `authorizingIssueIds` 和适用空要求确认的 `input.json`, 再调用 `arw commit-audit prepare --input <absolute-input-path>`. Engine 在同一目录物化完整 `request.json` 和绑定的空 `review.jsonl`, 并只返回准确 Request 绝对路径. 每个 Request 目录独立, 不需要全局当前指针, 锁或摘要. 内部参与者按工作流约束互相信任, 因而临时 Request 和一次性正式记录不增加模式版本或密码学身份.

Reviewer 只接收 Request 路径, 读取 Git 索引中的冻结候选, 并在绑定的 JSONL 中逐项形成和修订判断. Main Agent 可读取中间状态以核对和讨论, 但不把它当作完整审计结果. 全部适用检查完成后, Reviewer 只返回 `ready`; 未完成或写入失败时返回带原因的 `incomplete`. Main Agent 随后调用 `arw commit-audit generate --request <absolute-request-path>`. Engine 严格验证 Request, 当前候选前置条件, JSONL 语法, 要求覆盖, 证据和输出计划, 并只在完整成功时返回可提升的输出映射. 失败不返回映射, 尽力恢复已完成写入; 恢复失败的残留临时文件没有提升资格, 由后续完整重试覆盖.

Reviewer 在进行语义判断前, 先列出完整的 Gate 1, Gate 2 要求集合和已暂存证据范围. 当该清单大到无法在一次处理中可靠审核时, Reviewer 把工作拆分为多个步骤, 每次处理一小部分, 同时保持完整覆盖. 每个 JSONL 行对应一项独立要求, 使用精确单行来源, 语义判断和按文件分组的准确行区域证据. 词元匹配, 行范围启发式, 文件类别映射, 批量转换结果和重复的通用问题都不能替代实际语义判断.

Main Agent 可以读取并质疑 Reviewer 结论, 但不能代替 Reviewer 改变语义判断. Engine 返回 `review-output-invalid` 时, Main Agent 把完整机械诊断交给同一 Reviewer 修订绑定 JSONL, 再重新调用生成入口. 只有整批适用结果都是 `satisfied` 时, Main Agent 才按返回的仓库相对来源与目标映射原样提升并暂存全部文件. 任一 `gap` 或 `uncertain` 阻止整批提升. Reviewer 启动后的实现范围变化使 Request 失效; 随后暂存准确映射的审计文件属于预期提升步骤. 提升后运行 `arw commit-audit verify`, 再运行输入包含审计输出的最终机械检查, 并确认获准实现的路径和 blob 身份未变, 且只增加了准确的审计目标.

Reviewer 按[共同交接规则](../agents/reviewer.md#review-handoff)逐项写入和更新同一草稿. Main Agent 可以按需读取以核对和讨论, 但在最终完整结果前不修改候选. Reviewer 的最终消息只返回状态, 正式文件路径只来自 Main Agent 调用 Engine 后取得的映射. 这样无需同时维护消息和文件两份报告, 仍可尽早核对问题, 并避免同一次审计的前后判断落在不同候选字节上.

`arw commit-audit verify` 失败时按原因回退. 冻结实施字节未变且问题只在准确提升或暂存时, 只重做该步骤并重新验证. 冻结实施字节未变但 Reviewer JSONL 无效时, 同一个 Commit Audit Reviewer 读取完整诊断并修订完整绑定草稿, 不重跑 Gate 3. Commit Audit 开始后任一冻结的实现, issue, spec 或测试字节改变时, 丢弃 Request 和审计输出, 重新执行受影响的就绪检查与验证, 再让 Gate 3 双轴在完整替代候选上收敛. 如果就绪输入改变, 按就绪工作流刷新最终版本的完整结果, 不以旧结论满足新的完成或提交授权. 审计前的候选变化由 `code-review` 的有效性和完成记录规则判断, 不把该例外用于保留已失效的 Commit Audit.

Commit Audit Reviewer 审查线程身份是 `spawn_agent` 首次调用或 `followup_task` 后续调用的 `input.role: "commit-audit-reviewer"` 与完整排序 `authorizingIssueIds` 的组合; 运行设置由统一 Reviewer 配置提供, 不依赖平台角色种子. 首次审核使用无 Main Agent 对话上下文的全新审查线程. 同一身份的后续调用必须复用可靠审查线程, 读取完整当前 Request 和暂存候选并返回完整状态. 候选内容或治理语义变化本身不创建新审查线程. 只有 issue ID 集合改变, 原审查线程不可用或不可恢复, 或用户明确要求时才能创建全新替代审查线程. Gate 3 对每个审核轴使用相同规则, 但 `input.role` 不同使两个审核轴仍保持独立审查线程.

Gate 2 是 effort 级 Spec Audit. 它的文档和要求只来自本批次接受 issue 的有效 `## Spec Requirement` 并集, 不从相关性或作为输出修改的长期 Spec 扩大. 空并集仍需要显式用户确认的具体理由和 UTC 秒级时间, 才能生成 `not-applicable`.

用户请求 Git 提交后, Main Agent 从准确的已暂存路径集合选择纯规划或实现路线. 每个提交只包含一个 effort. 纯规划路线只接受该 effort 中跟踪器内部的 `spec.md`, `map.md`, 可以被 ARW 解析的 Wayfinder issue, 未在当前变更中进入 `completed` 或 `wontfix` 的实施 issue, 以及 `research/**` 和 `prototype/**` 下任意扩展名的安全普通文件. 它允许新增, 更新和删除. 辅助文件不要求由 map, issue, spec 或其他文件引用.

纯规划路线只做机械验证. Main Agent 冻结准确的已暂存路径, 状态, 普通文件模式和 blob 标识, 检查安全路径, ARW Artifact 基本格式, 实施 issue 是否进入终态, 适用文本格式和限定范围的已暂存空白字符, 并在提交前确认候选不变. 它不验证规划内容的意义, 完整性或价值, 不检查阻塞项, 生命周期完成状态, 链接, 覆盖范围, 跨文件关系或删除后的剩余状态. 任一失败停止提交, 修正后从路径清单重新开始.

纯规划路线不运行 Spec Readiness 记录, Commit Audit, Gate 1, Gate 2, `arw commit-audit verify`, Gate 3, Code Review 或独立 Reviewer. 它接受没有独立语义审核的限制, 因为规划记录不声称证明未来实现的符合性. 后续实现仍经过完整独立审核.

只要已暂存候选包含任何不属于纯规划分类的内容, 完整候选就使用实现提交流程. 同一 effort 和实现授权范围内的规划记录可以留在该候选中, 不因文件类别强制拆分原子变更. 不在该授权范围内的规划记录仍须先取得自己的适用授权.

## Consequences

实现 issue 可以没有 Gate 1 辅助文件就进入 `completed`, Wayfinder issue 可以没有 Gate 1 辅助文件就进入 `resolved`; `Full Issue Audit` 不再属于当前流程. 实现提交工作流必须先让 Gate 3 在完整实现候选上收敛. 通用提交工作流判定 Commit Audit 适用时, 再执行独立审核, `commit-audit verify` 和依赖审计输出的机械检查. 纯规划提交流程只执行上面定义的已暂存范围和机械验证.

固定完整审核版本使就绪与代码审核能够和已授权实施并行, 同时保持每条结论的准确归属. Commit Audit 仍读取当前精确索引和正式生成内容, 因而其排他顺序由提交工作流协调, 不在原生运行层增加互斥机制. 适用的 Commit Audit 位于完整有效的 Gate 3 结果和完成记录收尾之后. 普通 Code Review 经常发现需要修改实现的问题, 因此先完成双轴修复循环再准备完整审计. 结论复用减少相同内容的重复审核, 窄范围收尾例外避免记录审核结果本身触发再次审核; 代价是 Main Agent 必须检查完成记录的精确差异. 进入 Commit Audit 的完整候选仍由独立 Reviewer 判断. 不按修复看似只影响部分要求而复用旧 Request, 因为审计判断针对完整的冻结实施候选, 当前 Verifier 不能证明任意实施变化与旧结论无关.

Reviewer Role 可以写绑定的临时 JSONL, 但不能调用 Engine, 写仓库中已跟踪的文件或修改索引. 既有 Issue Audit, Spec Audit 和 Spec Readiness 记录不能成为它的证据或既有结论. Reviewer 角色指令的变更仍须经过既有用户批准关卡; 用户正常修改自己的统一 Reviewer 运行配置不因此增加批准步骤. Engine 不取得 Reviewer 编排责任.

ADR 0013 中由 Main Agent 完成 Gate 1 和 Gate 2 语义审核的部分由本决定取代. Commit Audit 的准确调用条件由通用提交工作流拥有. ADR 0016 的统一 Reviewer 配置, 精确角色身份和用户批准边界保持有效. JSON 是 Issue Audit, Spec Audit 和 Spec Readiness 的正式成功格式; Commit Audit 的 Reviewer 草稿使用 JSONL.
