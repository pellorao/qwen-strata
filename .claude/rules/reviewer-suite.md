---
paths:
  - "benchmarks/reviewer-suite-v1/**"
  - "tools/reviewer/**"
  - "tools/safety/**"
---

# ARW Reviewer 测量规则

## 合同
- 直接使用冻结 ARW 的原场景、完整规则、准备 / 生成 / 评分入口和 Reviewer 运行层。不裁剪用例，不另设评分。确实需要改变合同时，先列出差异并取得同意。
- 权限沿用原生设置：`:read-only` 加显式写路径，审批走 on-request / auto_review；网络、搜索、MCP 保持原生。不额外收紧，不启用可选的严格隔离。
- 正式能力测量之前，先确认所需的安全证据（原生沙箱行为、auto_review 审批质量）。见 `docs/plan.md`。

## 执行
- 时限按累计工作时间计：初审 55 分钟提醒、60 分钟中断；同线程后续沟通 10 分钟提醒、15 分钟中断。提醒和中断使用原版 ARW 接口。
- 模型正常早停而任务未完成时，在原线程发继续指示，直到完成或超时；预算不重置。到达上游 10 / 5 次早退暂停点时，停下交给用户决定。
- 报告的机械格式问题，由主会话在绑定原实例的副本中修复，不改变检查结论、finding 或证据。原始失败保留。
- Spec Readiness 合并实例的定义：同一线程先跑 runtime-migration，再跑 artifact-promotion，两份报告分别绑定，按原版融合评分。

## 会话检查
- 按冻结 ARW 的 `docs/agents/reviewer-capability-session-inspection.md`，完整检查每个原生会话：准备项、线程身份、启动上下文、全部消息和工具调用、读写范围、报告和终态，并排查隐藏答案、其他实例等禁止来源。
- 自动评分、token 对账、关键词搜索都不能代替这项检查。检查完成前不清理原始记录。
