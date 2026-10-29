# rtx3080ti 主机说明

RTX 3080 Ti 12 GB、i9-13900。该机由 Claude Code 管理，负责现有 benchmark 和主要历史测量；是否为本机当前主机只由该副本的 `project.private.toml` 顶层 `local_host` 决定。

## 当前服务

- 2026-10-24 安装 Strata v0.2.4（Qwen 引擎 0.1.48），短调用链检查通过。
- 对外模型为 IQ3_XXS；参数沿用 v0.1.42 的本机调参结果，未在 v0.2.4 上重新调参。
- Q2_0、IQ2_XS 权重保留，但不对外，默认不运行或测试。
- 安装路径和前端地址只从该副本的 `project.private.toml` 读取。

具体参数与证据入口：

- 部署配置：[config/deployments/rtx3080ti.json](../../config/deployments/rtx3080ti.json)
- 调用手册本机段落：[docs/installation-readme-hosts/rtx3080ti.md](../installation-readme-hosts/rtx3080ti.md)
- 本机调参：[docs/host-tuning/rtx3080ti.md](../host-tuning/rtx3080ti.md)
- 本机后续进度：[docs/work-history/rtx3080ti.md](../work-history/rtx3080ti.md)

## Agent 与额度

- 该机使用 Claude Code。额度预检只在这里执行：按用户级规则调用 `~/.claude/statusline/estimate.sh --can-start`，决定是否开始可能消耗 Anthropic 额度的长工作。
- Strata 的 key、租约和模型状态检查仍按统一流程执行。

新报告写入 `reports/rtx3080ti/<版本或主题>/`。已有报告保留原路径，不回写历史。
