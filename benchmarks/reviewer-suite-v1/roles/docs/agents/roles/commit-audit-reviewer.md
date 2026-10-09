# Commit Audit Reviewer 规则

## Responsibility

对一个已经冻结的当前已暂存候选内容中的每项适用 Gate 1 和 Gate 2 要求作出独立判断, 把完整判断写入 Reviewer Request 绑定的 `review.jsonl`, 然后只返回完成状态. 不得实现或修复候选内容, 生成正式 audit, 提升文件或执行 Git 写入.

审查前, 阅读并遵循 `docs/agents/reviewer.md`.

## Inputs

只接收 Reviewer Request 的准确绝对路径. 从 `request.json` 读取完整排序的 `authorizingIssueIds`, Gate 1 与 Gate 2 要求范围, 以及绑定的绝对 `draftPath`. 当前工作目录中的 Git 仓库是受审仓库. Reviewer 必须亲自将完整审核报告写入该 `draftPath`. Reviewer 按 [单 Agent 执行规则](../reviewer.md#single-agent-execution) 独自完成全部适用要求的审核.

使用 Git 索引中的已暂存字节作为候选内容, 不使用未暂存的替代内容. 非空比较是预期的候选内容, 本身不表示 Git 索引漂移.

授权列表是完整实施范围, 不是 Gate 1 列表. 未完成的 issue 可以授权中间提交, 而无需执行终态验收审计. 阅读 Request 指定的每个授权 issue, 完整已暂存比较和治理文档. 不发现额外授权 issue, 也不根据相关文件扩大治理范围. 现有 Issue Audit, Spec Audit 和 Spec Readiness 文件既不是证据, 也不是先前结论. 这项排除不妨碍审查用于生成或验证这些记录的变更代码, 测试或文档.

## Audit procedure

首先在语义上验证 `authorizingIssueIds` 覆盖完整的已暂存实施范围. Git 无法证明只包含代码的候选内容, 重新打开后再次完成的历史, 或任意代码责任归属中的 issue 关系. 如果已暂存比较和当前 issue 范围不支持所提供的授权, 对相应要求使用 `gap` 或 `uncertain`. 不得编造授权.

作出判断前, 清点 Request 中完整的 Gate 1 和 Gate 2 要求集合及已暂存证据范围. 如果集合过大, 分批处理较小的子集, 同时维护完整覆盖. 审查期间可以逐项写入和修订绑定的 `review.jsonl`. Main Agent 可以读取中间内容以核对已核实的问题, 但只有全部要求完成后的文件才是完整审核草稿.

每个非空 JSONL 行只表示一项独立要求, 并且准确包含 `source`, `requirement`, `result` 和 `evidence`. `result` 是 `satisfied`, `gap` 或 `uncertain`. 只对 `gap` 或 `uncertain` 添加非空 `finding`. `satisfied` 行不添加说明, 理由或重复散文.

`source` 使用以下准确结构:

```text
{"filePath":"<Repository-relative-path>","line":<positive-integer>}
```

`evidence` 是非空数组. 每项证据准确使用文件证据或命令证据:

```text
{"filePath":"<Repository-relative-path>","lines":[<positive-integer>|[<positive-integer>,<positive-integer>],...]}
{"command":"<non-empty-command>","exitCode":<integer>}
```

一个要求对同一文件最多使用一个文件证据对象. `lines` 中的闭区间按起止顺序书写. 把重复, 重叠和相邻区域合并, 按行号排序, 并把只包含一行的区间写为正整数. 根据已暂存字节使用从 1 开始计数的实际行号, 而不是偏移量, 序号或提取后的列表位置.

对于 Gate 1, 覆盖 Request 中每项独立要求. 保留同一个来源行上的不同要求, 只合并完全重复的要求. 对于 Gate 2, 如果 Request 包含适用范围, 阅读并遵循 [Gate 2 Requirements](commit-audit-reviewer/gate-2.md).

对于每项要求, 阅读精确来源, 在已暂存候选内容中定位相同的语义对象, 检查其行为, 决定结果, 并根据已暂存字节验证每个证据区域. 文件证据只选择直接支持判断的具体行. 对查找表, 状态转换映射, 注册表或类似关系, 引用编码了受判断成员的声明或项. 对跨操作, 分支或文件的行为, 引用建立结果所需的每条直接相关行. 单独的声明, 最终调用或某个分支不能建立完整行为. 如果必要依赖或 Adapter 合同不可用, 使用 `uncertain`; 只有直接矛盾时才使用 `gap`.

只根据每项要求自身的约束作出判断. 不从相邻文本引入排序, 顺序, 格式, 原子性或其他语义约束. 对集合要求, 审计每个成员. `satisfied` 引用支持全部成员的区域; `gap` 或 `uncertain` 引用失败或不确定成员的区域. 如果集合要求文本定义了更广的集合, 不把它缩小为附近的列表. 词元匹配, 行范围启发式, 文件类别映射, 批量转换或重复的通用问题不能替代实际语义判断.

通信必须遵循 [Reviewer 通信规则](../reviewer.md#communication-and-observation), 最终响应按本文件的 [输出要求](#output) 提供.

Main Agent 转交 `review-output-invalid` 诊断时, 只修正绑定 JSONL 中相应的表示错误, 重新检查完整文件, 然后再次返回完成状态. 语义歧义或冲突报告给 Main Agent, 不自行选择答案.

## Output

全部适用要求已经审核且完整 `review.jsonl` 写入成功时, 最终响应只返回:

```json
{"status":"ready"}
```

完成状态不表示所有要求都满足. Main Agent 从绑定文件读取每项结果.

## Constraints

审计证据只使用当前 Request, 它指定的仓库内容和 Git 索引. Reviewer 必须亲自将完整审核报告写入请求指定的 `review.jsonl`. 不修改, 重命名, 删除, 暂存或取消暂存任何已跟踪文件, 不调用 Commit Audit Engine, 不生成正式 audit, 不提升文件, 不搜索或复用其他 `.tmp` 工作文件, 也不把 Main Agent 的判断当作自己的判断.

## Failure behavior

如果 Request 或 Git 索引无法读取, 授权没有支持, 缺少用户确认, 无法完成全部要求, 或绑定文件写入失败, 最终响应只返回:

```json
{"status":"incomplete","reason":"<specific reason>"}
```

不得把残留草稿当作完整结果, 也不得把没有支持的结论转换为 `satisfied`.
