<!-- arw:managed:start -->
# 提交工作流

只有在用户要求 Git 提交后才使用该工作流. 完成或解决 issue 本身不会启动 Commit Audit, 暂存, 已暂存审查或提交验证.

## Select the commit workflow

选择工作流前, 检查精确的已暂存路径集合, 然后按以下条件选择:

- 每个提交只包含一个 effort. Main Agent 只暂存该 effort 的内容. 共享文件中的改动按其实际语义归属判断, 不根据路径猜测.

- 只有每个已暂存项都满足完整的符合条件内容分类器时, 才使用非实施提交工作流.
- 任何一项属于当前仓库的实施工作时, 对完整候选内容使用实施 issue 工作流.
- 某项不满足任何分类时, 在选择工作流前停止并解决其责任归属. 不得推断未分类项都是实施工作.

如果同一项实施授权覆盖完整候选内容, 符合条件的非实施内容可以与实施工作保留在一起. 不得仅因一项原子实施变更同时更新规划记录或仓库状态而拆分它. 授权范围外的内容必须先获得自己的适用授权, 才能加入候选内容.

## Exclusive Commit Audit

Commit Audit 在当前 Git 仓库内排他. 从本次审计准备开始, 到完整审计结果生成, 必要产物提升与验证结束, 或 Main Agent 明确终止该审计流程为止, 只允许只读工作和本次审计必需的产物写入. 这些例外包括 Request, 绑定 Reviewer 报告, Engine 生成内容, 准确映射的正式审计产物及其提升和暂存. 不允许同时修改代码, 测试, 文档或其他候选内容, 也不运行该仓库中的其他 Reviewer. 排他范围不扩展到其他 Git 仓库.

开始前, 与用户沟通的 Main Agent 确认该仓库的代码及候选写入已经停止, 等待其他 Reviewer 完整结束, 并按 [设计就绪规则](spec-readiness.md#authorization-timing)取得当前有效结果. 无法确认这些前提时等待, 不把暂时没有输出当作已经停止. 该顺序由工作流协调, 不新增原生互斥锁或全局运行协议.

审计所需 Input 与执行规则在启动前完整固定, 当前已暂存候选仍按 Commit Audit 的准确索引合同核对. 源内容或索引出现例外范围之外的写入时, 停止该审计流程并按下方失效边界处理. 修复需要修改实施候选时, 先结束当前审计, 再恢复已授权修复与后续新审查, 不在进行中的审计内修改候选.

## Implementation issue commit workflow

1. 确定已授权的提交范围及其完整排序的 `authorizingIssueIds`. 检查仓库状态, 并暂存完整的实施候选内容, 其中不包含本次提交操作产生的 Gate 1 或 Gate 2 输出.
2. 安排每份适用的 Spec Readiness 记录检查和必要的实施验证. 就绪失效时准备完整替代工作流, 可按 [公共 Reviewer 规则](reviewer.md#review-versions-and-concurrency)与第 3 步并行; 待完成的检查不提供通过事实. 记录本轮精确的实施路径集合和已暂存 blob 对象身份.
3. 使用 `code-review` Skill Package 判断已有完整结果是否仍然有效. 可复用时直接使用; 否则按照该技能完成适用的独立审查和修复循环. 它是结论复用, 完成记录例外, 失效和重审规则的唯一来源. 只有每个适用轴都有完整有效的通过结果, 且没有未解决的问题时才继续.
4. 取得当前有效的就绪结果并完成必要实施验证后, 按 `code-review` 的完成记录规则检查并写入收尾内容, 运行受影响的文档验证. 收尾后冻结最终完整候选的实施路径集合, 已暂存 blob 对象身份和树对象. 完成记录包含在该候选内.
5. 根据 `HEAD` 和当前已暂存候选判断是否有 implementation issue 新进入 `completed` 或 `wontfix`.
6. 没有终态转换时, 不准备 Commit Audit Request, 不调用 Commit Audit Reviewer, 不生成或提升 Gate 1 或 Gate 2 记录, 也不运行 `arw commit-audit verify`. 以机械方式确认冻结的实施路径集合, blob 对象身份和树对象都未更改, 然后继续第 10 步.
7. 存在终态转换时, 先满足 [仓库排他规则](#exclusive-commit-audit), 再按 [Commit Audit Workflow](commit-audit-workflow.md)准备独立 Request, 解析或创建 Reviewer 线程, 并只把 Request 的准确绝对路径交给它.
8. Reviewer 在绑定的 `review.jsonl` 中完成全部语义判断并只返回状态. Main Agent 调用 `arw commit-audit generate --request <absolute-request-path>`. `review-output-invalid` 交回同一 Reviewer 修订完整草稿, 其他失败由 Main Agent 按工作流处理.
9. 只有完整生成结果存在, 且每项适用的 Gate 1 和 Gate 2 结果都是 `satisfied` 时才继续. 按返回的 `sourcePath` 和 `targetPath` 映射原样提升准确字节, 将所有目标作为一个批次暂存, 再运行 `arw commit-audit verify` 和以审计输出为输入的最终检查. 最后以机械方式确认每条已批准实施路径和 blob 对象身份都未更改, 且已暂存路径集合只增加了 Engine 映射指定的审计目标.
10. 按 [就绪授权时点](spec-readiness.md#authorization-timing)重新验证当前结果. 只有适用分支的全部验证成功且已批准实施字节保持不变时, 才执行提交.

终态转换分支中的 Commit Audit 开始前, 按 `code-review` 判断候选变化是否使审查结果失效.

Commit Audit 开始后, 冻结实施范围内的任何 Git 索引变更都会使该审查结果和后续每个 Commit Audit 批次失效, 完成记录也不例外. 丢弃审计输出, 对替代候选重新执行受影响的就绪检查和验证, 然后重新运行完整 Gate 3.

冻结的实施路径集合和 blob 对象身份保持不变时, 审计产物错误按以下方式处理. 两种情况都不重新运行 Gate 3:

- `arw commit-audit verify` 失败, 但冻结的实施路径集合和 blob 对象身份保持不变时, 只修正精确字节的提升或暂存错误.
- JSONL 审核输出无效时, 把完整诊断交给同一个 Commit Audit Reviewer 修订完整草稿并重新生成.

## Non-implementation commit workflow

只有在用户要求 Git 提交, 且精确的已暂存候选内容仅包含已经由适用的初始规划记录, issue, map 或仓库工作流授权的符合条件内容时, 才使用该工作流.

候选内容只属于一个 effort, 可以添加或更新符合条件的项. 它可以删除该 effort 的辅助文件, 但必须保留每个已经提交且已注册的 ARW Artifact 身份. 保持相同类型和编号的路径重命名属于身份保留, 不是删除.

只有采用以下形式之一的项才符合条件:

- `.scratch/<NNNN>-<effort-slug>/spec.md`.
- `.scratch/<NNNN>-<effort-slug>/map.md`.
- ARW 解析为实施, Application Source 或 Wayfinder issue 的 `.scratch/<NNNN>-<effort-slug>/issues/<NN>-<issue-slug>.md`.
- `.scratch/<NNNN>-<effort-slug>/research/**` 或 `.scratch/<NNNN>-<effort-slug>/prototype/**` 下的任何安全普通文件.
- 任何安全的 `gitlink`.

`gitlink` 把所引用的子模块提交记录为当前仓库中的仓库状态. 它不是该仓库的实施产物. 它是否符合条件不取决于 Application 配置, 自身路径或其他已暂存项.

只有在已暂存候选内容不会使实施 issue 进入 `completed` 或 `wontfix` 时, 它才继续符合条件. 新的终态 issue, 从非终态发生的转换, 或从另一个终态发生的转换, 都不符合非实施提交工作流. 已经在 `HEAD` 中处于相同终态的 issue, 不会仅因其他字节发生变化而再次进入该状态.

研究和原型文件可以使用任何扩展名, 且不要求 map, issue, spec 或其他文件提供链接. 该工作流不检查阻断项是否已经解决, 不要求 map 决定指针, 不验证链接或跨文件关系, 不评估含义或完整性, 也不增加删除后果检查. `gitlink` 不需要伴随 Application Source Issue 或其他规划记录, 但 Main Agent 仍要按实际语义把它归入本次唯一 effort.

运行以下完整顺序:

1. 运行 `git diff --cached --name-status`, 并使用 Git 检查已暂存项. 冻结非空路径集合, 状态, 项模式和对象身份. 拒绝不安全路径, 符号链接, 目录项, 不受支持的项, 或完整符合条件内容分类器以外的任何项.
2. 确认每个已暂存项都没有未暂存的替代内容. 使用已暂存状态和 `HEAD` 项对添加, 更新, 重命名和删除操作分类, 保留每个已经提交的 `issue:<NNNN>:<NN>`, `map:<NNNN>` 和 `spec:<NNNN>` 身份, 并检测进入 `completed` 或 `wontfix` 的实施 issue. 只有类型和编号保持不变时, 才允许重命名描述性 slug. 对当前存在于 `gitlink` 工作树中的项, 要求其当前子模块 `HEAD` 等于已暂存对象身份. 嵌套的未提交文件内容不能替代该 `gitlink` 身份.
3. 对每个新增或更新的已注册 ARW Artifact, 只有在证明 `arw print <canonical-id>` 会读取已暂存字节后才运行该命令. 要求基础解析成功, ARW Artifact 身份符合预期, 且记录类型正确. 不得运行关系, 阻断项, 生命周期完成, 链接, 覆盖或语义检查. 保留身份的重命名操作中, 旧路径已无剩余字节可供解析.
4. 根据适用的机械文本规则检查精确的已暂存普通文件字节, 包括没有 BOM 的 UTF-8 和 LF 行尾. `gitlink` 没有普通文件字节可供检查. 不得评估散文含义, 完整性, 引用, 值或与其他文件的一致性. 对精确候选内容运行 `git diff --cached --check -- <path>...`.
5. 再次读取已暂存路径集合, 状态, 模式和对象身份. 任何变化都会使工作流从第 1 步重新开始.
6. 只有每项机械检查都成功后才执行提交. 失败会在提交前停止工作. 修复候选内容并重新开始. 只有完整候选内容包含实施工作时, 才把它送入实施 issue 工作流.

该非实施提交工作流不运行 Spec Readiness, 不创建或验证就绪记录, 不运行 Commit Audit, 不创建 Gate 1 或 Gate 2 记录, 不运行 `arw commit-audit verify`, 不调用 Gate 3 或 Code Review, 也不使用任何独立 Reviewer.

## Commit Audit workflow

只有 `Implementation issue commit workflow` 的第 5 步识别到终态转换后, 才对实施 issue 提交执行 Gate 1, Gate 2, 独立 Reviewer 和审计有效期工作. 开始这些工作或 Gate 3 前, 阅读 [Commit Audit Workflow](commit-audit-workflow.md).

## Commit messages

遵循 Conventional Commits 1.0.0. 使用标题 `<type>[optional scope][!]: <description>`. 对用户可见功能使用 `feat`, 对缺陷使用 `fix`. 常用的辅助类型是 `docs`, `test`, `refactor`, `style`, `build`, `ci`, `perf` 和 `chore`.

在冒号前紧接着使用 `!`, 或使用 `BREAKING CHANGE: <description>` 尾注标记破坏性变更. 描述保持简短并使用祈使语气. 只有在理由, 迁移说明或取舍不明显时才添加正文.

## Failure behavior

如果任何关卡失败, 必要的 Input 不可用, 结论是 `gap` 或 `uncertain`, 或 `code-review` 返回 `incomplete`, 则在提交前停止. 不得提升不完整的审计批次. Commit Audit 前的候选变化按 `code-review` 的有效性和完成记录规则处理. 审计开始后的候选变化或审计产物错误, 按实施提交工作流的失效边界回退.
<!-- arw:managed:end -->
<!-- arw:repository-owned:start -->
None.
<!-- arw:repository-owned:end -->
