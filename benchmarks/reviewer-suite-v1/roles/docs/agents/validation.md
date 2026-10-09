<!-- arw:managed:start -->
# 验证规则

更改行为, 添加或修改测试, 或运行验证前, 阅读本文件. 根据活动 issue 和下方的 Repository-owned 命令确定验证内容. 实施期间使用最小的定向检查, 然后在完成前运行全部必要的测试套件.

不得将通过的命令当作它并未实际检验的要求的证据. 为每条验收标准记录具体证据.

在报告任何实施或文档 issue 完成前:

- 运行并通过 `arw text check`.
- 运行并通过 `arw terms check --include .scratch/<NNNN>-<effort-slug>/`. 将占位符替换为当前 issue 实际的仓库相对 effort 目录.
- 如果 Repository Profile 配置了 Code Map, 运行并通过 `arw code-map verify`.

这些检查补充 Repository-owned 测试套件, 不替代其中的测试, 构建或其他验证.

每次运行 `arw terms check` 后, 消费 `arw.config.json` 中已配置的语言检查结果. 默认输出保留每项检查的名称, 语言, 生效阈值和统计, 并列出未达到阈值及无法判断的文档. 需要全部文档时使用 `--verbose`. 不在流程中重新推断语言或定义阈值.

未达到阈值的文档需要修正或取得用户批准. 未配置, 未覆盖, 没有选中文档或无法判断均不代表通过, 应向用户报告并取得处理决定. 配置错误必须修复后重跑.

语言结果不改变命令退出码, 因此退出码 `0` 不能替代这些结果的处理. 每次流程调用都重新判断. 用户批准只在当前 session 有效, 可以覆盖当前 session 中满足用户所述文件范围和比例条件的后续调用, 但不得把该条件写入 Repository.

将 `arw code-map verify` 视为结构覆盖证据. 它证明适用目录具有有效的 Code Map README 文件, 但不能证明每个代码文件都有自己的 README 章节, 也不能证明每项描述在语义上完整. 如果 issue 更改了相应代码或目录责任, 检查这些描述.

## Risk-driven coverage

避免只能重复实现逻辑的同义反复测试. 同义反复测试的例子: 为一条文档规则新增测试, 仅断言文档包含该规则的某个句子. 验证文档中的供机器读取的固定格式属于例外情形.

普通测试采用最少充分覆盖. 根据要求, 测试边界和实际回归风险, 选择能够证明行为的最小测试集合. 参数差异只有在产生不同的可观察结果, 失败影响或恢复结果时才需要独立覆盖. 新增测试前先确认现有测试不能证明相应的独立风险. 多个测试证明同一行为且不覆盖独立风险时, 保留运行和维护成本较低且失败原因清晰的测试.

常规测试不得使用网络. 可行时, 将文件系统, 进程和在线服务行为隔离在仓库现有公开边界后面. 实施期间使用定向验证, 然后在完成前运行完整的 Repository-owned 测试套件.

仓库特有的运行器, 构建命令, 浏览器检查和在线验证命令属于 Repository-owned 区域. 不得从来源项目推断它们, 也不得添加仓库未选择的工具.

## New test approval

添加每个测试案例前, 向用户说明该案例的作用, 并取得用户同意. 同时有多个案例需要审批时, 在同一个回复中逐项说明并一起请求审批.

原则上不添加真实的端到端测试, 因为日常工作已经在执行这些完整流程. 只有日常工作几乎不会覆盖的情境才可申请添加; 申请时充分说明测试所覆盖的情境, 日常工作为何几乎不会覆盖, 以及添加该测试的必要性.

## Test case duration

创建测试用例, 对其进行语义变更, 或以降低现有测试套件耗时为目标时, 阅读并遵循 [测试性能优化流程](test-performance-optimization.md).

## Batch operation tests

对于按 [仓库写作规则](writing.md#batch-operations) 应批量处理的操作, 比较不同的输入规模, 验证全部输入和必要语义得到保留, 且可合并操作的调用次数不会按数据项逐项增加. 批量写入还必须验证授权范围, 失败影响, 重试, 恢复和事务结果.

如果独立事实需要独立操作, 不得断言固定的调用总数, 也不得将实际耗时作为自动失败条件.

## End-to-end outcome validation

如果权威设计经过多个实现层产生可观察结果, 直接根据最终结果验证该设计. 不得仅为了声称覆盖完整链路, 就把每个中间表示, 内部调用或实施阶段设为独立的通过条件. 只有当中间值本身属于公开合同, 持久证据, 授权边界或安全边界, 或者最终结果无法证明受治理的属性时, 才单独要求该中间值.

## Documentation validation

对于已更改的投射工作流文档, 检查:

- 路径, 标题, 精确命令和跟踪器字段.
- 内部链接.
- 没有 BOM 的 UTF-8 和 LF 行尾.
- `docs/agents/writing.md` 规定的文档语言, 并确认同一文档的普通自然语言没有混用中文和英文.

对 Agent 责任内的已跟踪内容, 使用明确的变更路径列表运行 `git diff --check`, 并单独检查未跟踪内容. 纯文档工作要记录这些检查, 不得编造无法实际检验该变更的行为测试.

对于任何纯文档变更, 验证文档结构, 编码, 链接, 命令和固定字段. 对每个实施或文档 issue, 记录验收标准证据, 指明支持结果的精确测试, 命令, 文件或检查.
<!-- arw:managed:end -->
<!-- arw:repository-owned:start -->
# Source Checkout 验证

更改或运行 Source Checkout 验证前, 阅读适用的详细文档:

- 对于确定性测试覆盖和 Source Checkout 验证命令, 阅读 [Source Checkout 确定性验证](source-checkout-validation.md).
- 对于定向或发布 Reviewer Capability Conformance, 阅读 [Reviewer Capability 验证](reviewer-capability-validation.md).
- 对于 Source Checkout 发布流程或共享虚拟机交接, 阅读 [Source Checkout 发布验证](source-checkout-release-validation.md).

## Source Checkout language scope

作为 Baseline 例外, 非发布流程不判断 `distribution/**` 中分发副本的语言结果. 发布流程仍检查候选分发文档.
<!-- arw:repository-owned:end -->
