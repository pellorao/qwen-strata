# 本机安装说明

RTX 3080 Ti 12 GB、i9-13900。由 Claude Code 管理，负责现有 benchmark 和测量。

## 当前服务

- 2026-11-23 升级到 Strata v0.2.19 源码加引擎 0.1.65（上游在同架构显卡上测得解码快 13% 到 20%），短检查通过，见[升级报告](../reports/v0.2.19/upgrade.md)；前一版 v0.2.18（引擎 0.1.64）用于回退。同次把已部署安装换成单安装的新代码。实测速度由 qwen-strata/daily 在第一批实际工作后量。
- 2026-11-20 升级到 Strata v0.2.16 源码加引擎 0.1.62（自研引擎），短检查通过，见[升级报告](../reports/v0.2.16/upgrade.md)；前一版 v0.2.15（引擎 0.1.60）用于回退。
- 2026-11-18 升级到 Strata v0.2.15 源码加引擎 0.1.60，短检查通过，见[升级报告](../reports/v0.2.15/upgrade.md)；前一版 v0.2.12（引擎 0.1.58）已于 11-20 删除本地文件。
- 2026-11-08 升级到 Strata v0.2.12（Control 与 Qwen 引擎 0.1.58），短调用链检查通过，见[升级报告](../reports/v0.2.12/upgrade.md)；前一版 v0.2.11（引擎 0.1.57）用于回退（`strata components rollback`，或 `upgrade_release --rollback`）。11-06 升级到 v0.2.11 的记录见[该报告](../reports/v0.2.11/upgrade.md)。
- 草稿器钉死为 MTP（用户 2026-11-03 决定）：三个量化模板（`config/templates/` 下 `iq2_xs`、`iq3_xxs`、`q2_0` 的 `-prebuilt.json`）顶层都带 `"drafting": "mtp"`，引擎参数 `--spec 4 --mtp`，没有 `--parallel`，部署的 `installation_defaults` 也没有 drafter 或 parallel 键。v0.2.10 的服务端对未设 `drafting` 的配置按 Auto 处理，Auto 在本机已有 DFlash2 草稿器文件且单请求时会换成 DFlash2；钉死后即使以后下载了草稿器，启动也不会换。钉死后启动日志不再有 `Drafting: ...` 提示行（该行只在选择无法照办时输出，此前是 `Drafting: MTP (the DFlash2 drafter isn't downloaded yet)`），引擎日志仍有 `strata mtp: draft layer loaded` 和 `MTP windows up to 4 tokens`。DFlash2 与 MTP 的取舍没有评估，要评估另立任务，并同时撤掉该键。
- 对外模型为 IQ3_XXS；参数沿用 v0.1.42 的本机调参结果，未在后续版本（v0.2.4 至 v0.2.19）上重新调参。
- 路由先验 `STRATA_ROUTE_PRIOR=1.5` 为生产默认（用户 2026-11-08 选 B；routeprior3 n=15 判定 open，开组质量点估计低 3%，每实例约快 35%，[报告](../reports/routeprior3/summary.md)）；部署配置 `model_environment`，出现质量问题删该键即可回退。
- 路由尾部跳过 `STRATA_ROUTE_TAIL_SKIP=7` 显式钉在部署配置 `model_environment`（Strata 0.2.17 起上游默认关，不钉会变成 0；2026-11-22 arwtune 在固定 ARW 的 Spec Readiness 上盲裁：tail-7 均值 0.365-0.371，tail-0 0.132，解码 +6%，保留 7，[报告](../reports/arwtune/summary.md)）。
- Q2_0、IQ2_XS 权重保留，但不对外，默认不运行或测试。
- 安装路径和 `frontend_url` 只从 `project.private.toml` 的 `[installation]` 表读取。

具体参数与证据入口：

- 部署配置：[config/installation.json](../config/installation.json)
- 调用手册本机段落：[docs/installation-local-sections.md](installation-local-sections.md)（中文：[installation-local-sections.zh-CN.md](installation-local-sections.zh-CN.md)）
- 本机调参：[docs/calibration/installation.md](calibration/installation.md)
- 本机后续进度：[docs/work-history/recent.md](work-history/recent.md)

## Agent 与额度

- 使用 Claude Code。额度由总层计划决定（`~/.claude/docs/agents.md` Quota check），本工程不做额度判断。
- Strata 的 key、租约和模型状态检查仍按统一流程执行。

新报告写入 `reports/<版本或主题>/`。已有报告保留原路径，不回写历史。
