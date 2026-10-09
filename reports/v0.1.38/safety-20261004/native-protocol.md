# 原生审批及搜索声明兼容修正

2026-10-04。Strata v0.1.38，Codex 0.160.0；依据该Codex版本固定提交的原生协议实现修正安装桥和本工程harness，不修改ARW场景、评分、权限或Reviewer算法。

桥现在把`additional_tools`输入转换为工具声明，不注入系统指令；兼容相同声明再次出现，冲突别名明确拒绝。Hosted搜索接受`search_content_types=["text"]`，图像声明仍明确拒绝。所选模型catalog如实声明文本搜索，并把guardian override设为同一本地模型；catalog在app-server启动时加载，避免仅在线程配置中传入而未更新已加载模型目录。

82项本地回归通过（8.847秒），Python编译、JS语法及diff格式检查通过。维护部署时持有独占key、确认模型停止、持启动互斥锁并保留鉴权状态，部署后模型停止；实际安装桥/Brave/Hosted搜索三文件SHA与源码相同。新批次实际原生guardian 6次成功，本地provider、Qwen模型和low强度在自身会话中确认。此前失败不覆盖，见[审批预检](approval-quality-preflight.md)。

完整原版Reviewer host组合的网络、MCP及恢复还需实际验收；兼容回归和native sessions成功不代表正式能力或完整安全门通过。源码快照、原版协议来源、完整测试输出、部署记录和SHA见[结构化证据](native-protocol.json)及`../../../.tmp/measurement-details/v0.1.38/safety-20261004/native-protocol-evidence/`。
