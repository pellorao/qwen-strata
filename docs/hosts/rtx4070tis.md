# rtx4070tis 主机说明

RTX 4070 Ti SUPER 16 GB、i9-14900K、64 GB RAM。该机由 Codex 管理；是否为本机当前主机只由该副本的 `project.private.toml` 顶层 `local_host` 决定。

## 当前服务

- 2026-10-28 部署 Strata v0.2.4（Qwen 引擎 0.1.48，CUDA 13，sm_89）。
- 对外模型为 IQ3_XXS；当前参数是初始基线，尚未在本机独立调参。
- 2026-10-30 只读 `/health` 检查时前端在线、租约空闲、未加载模型；实时状态和待办以该机状态页为准。
- 安装路径和 `frontend_url` 只从该副本的 `project.private.toml` 读取。

具体参数与证据入口：

- 部署配置：[config/deployments/rtx4070tis.json](../../config/deployments/rtx4070tis.json)
- 调用手册本机段落：[docs/installation-readme-hosts/rtx4070tis.md](../installation-readme-hosts/rtx4070tis.md)（中文：[rtx4070tis.zh-CN.md](../installation-readme-hosts/rtx4070tis.zh-CN.md)）
- 本机调参：[docs/host-tuning/rtx4070tis.md](../host-tuning/rtx4070tis.md)
- 上线交接：[docs/rtx4070tis-handoff.md](../rtx4070tis-handoff.md)
- 本机后续进度：[docs/work-history/rtx4070tis.md](../work-history/rtx4070tis.md)

## Agent 与额度

- 该机使用 Codex。本机没有 `estimate.sh`、`budget.sh` 或其他额度预检脚本，因此不执行额度预检。
- 启动本地模型工作前仍须检查 Strata 独占 key、租约状态、模型状态和运行计划。

新报告写入 `reports/rtx4070tis/<版本或主题>/`。已有报告保留原路径，不回写历史。
