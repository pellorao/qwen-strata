# rtx3080ti 主机说明

RTX 3080 Ti 12 GB、i9-13900。该机由 Claude Code 管理，负责现有 benchmark 和主要历史测量；是否为本机当前主机只由该副本的 `project.private.toml` 顶层 `local_host` 决定。

## 当前服务

- 2026-11-06 升级到 Strata v0.2.11（Control 与 Qwen 引擎 0.1.57），短调用链检查通过，见[升级报告](../../reports/rtx3080ti/v0.2.11/upgrade.md)；前一版 v0.2.10（引擎 0.1.56）用于回退（`strata components rollback`，或 `upgrade_release --rollback`）。11-03 升级到 v0.2.10 的记录见[该报告](../../reports/rtx3080ti/v0.2.10/upgrade.md)。
- 草稿器钉死为 MTP（用户 2026-11-03 决定）：三个量化模板（`config/templates/` 下 `iq2_xs`、`iq3_xxs`、`q2_0` 的 `-prebuilt.json`）顶层都带 `"drafting": "mtp"`，引擎参数 `--spec 4 --mtp`，没有 `--parallel`，部署的 `installation_defaults` 也没有 drafter 或 parallel 键。v0.2.10 的服务端对未设 `drafting` 的配置按 Auto 处理，Auto 在本机已有 DFlash2 草稿器文件且单请求时会换成 DFlash2；钉死后即使以后下载了草稿器，启动也不会换。钉死后启动日志不再有 `Drafting: ...` 提示行（该行只在选择无法照办时输出，此前是 `Drafting: MTP (the DFlash2 drafter isn't downloaded yet)`），引擎日志仍有 `strata mtp: draft layer loaded` 和 `MTP windows up to 4 tokens`。DFlash2 与 MTP 的取舍没有评估，要评估另立任务，并同时撤掉该键。
- 对外模型为 IQ3_XXS；参数沿用 v0.1.42 的本机调参结果，未在后续版本（v0.2.4 至 v0.2.11）上重新调参。
- Q2_0、IQ2_XS 权重保留，但不对外，默认不运行或测试。
- 安装路径和前端地址只从该副本的 `project.private.toml` 读取。

具体参数与证据入口：

- 部署配置：[config/deployments/rtx3080ti.json](../../config/deployments/rtx3080ti.json)
- 调用手册本机段落：[docs/installation-readme-hosts/rtx3080ti.md](../installation-readme-hosts/rtx3080ti.md)（中文：[rtx3080ti.zh-CN.md](../installation-readme-hosts/rtx3080ti.zh-CN.md)）
- 本机调参：[docs/host-tuning/rtx3080ti.md](../host-tuning/rtx3080ti.md)
- 本机后续进度：[docs/work-history/rtx3080ti.md](../work-history/rtx3080ti.md)

## Agent 与额度

- 该机使用 Claude Code。额度由总层计划决定（`~/.claude/docs/agents.md` Quota check），本工程不做额度判断。
- Strata 的 key、租约和模型状态检查仍按统一流程执行。

新报告写入 `reports/rtx3080ti/<版本或主题>/`。已有报告保留原路径，不回写历史。
