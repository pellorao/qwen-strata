# Strata v0.1.38 升级与基础回归

2026-10-03 已升级至[官方 v0.1.38](https://github.com/Niko1221/Strata/releases/tag/v0.1.38)，
源提交固定为 99f3dbd0b21d1401b3769e0c0d963913607f380b。
用户下载的 Windows 引擎包为 124,279,645 字节，官方 SHA256 校验通过。
固定提交的源包约 13.6MB，由本工程下载；其 SHA 为本地计算值，未冒称
官方公布的源包摘要。完整文件摘要、版本与回退备份见
[installation.json](installation.json)。

升级使用原生启动互斥锁，确认服务停止后备份并原子替换文件。权重、模型
配置、依赖及原 Windows 工程均未改；上游 requirements 和 AGENTS 字节
与此前版本相同。存在可恢复备份；部分写入失败的恢复、错误包摘要拒绝、
ZIP 路径越界拒绝已分别通过测试。

真实 WSL 回归通过：中文 MCP 文件读取、越界 MCP 拒绝、一次性工程副本
修复、实际 shell/apply_patch、独立 unittest、取消与 resume 的凭证保留。
详细原始结果见 [wsl-workflow.json](wsl-workflow.json)。模型仍在 Windows
原生运行，WSL harness 直接连接 NAT 宿主地址；各工程自行管理 harness。

v0.1.37 的历史报告保留，不将旧版工具历史压缩的失败记录改写为新版通过。
本次 Code Standards 完整20+20测量按执行模式、模型、推理强度逐维完成，
每条件三次，18个不同正式实例，见[评分表](code-review.md)。推荐
sandbox + Q2_0 + medium；独立无害审批开销与范围限制分别见
[审批诊断](approval-cost.md)和[权限报告](sandbox.md)。评审能力结论
来自实际报告与逐项语义裁决，没有由基础回归推导。
