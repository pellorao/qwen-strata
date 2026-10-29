# 安装与维护

安装路径、前端地址和本机凭据只从 `project.private.toml` 读取；文档不复制这些值。每台机器的当前状态见[rtx3080ti](hosts/rtx3080ti.md)和[rtx4070tis](hosts/rtx4070tis.md)主机说明。日常启动只依赖安装目录。

模型、tokenizer、native pack、MTP、私有 Python 和 CUDA 依赖均保存在 Windows。前端和推理都由 Windows 原生进程执行，WSL 只运行调用方 harness 和维护工具。前端结构、一次性安装和部署见[前端运行与维护](frontend.md)。

## 版本与环境

各机版本、硬件和已验证范围记录在主机说明中。安装和运行使用官方预编译引擎，无需在本机重新编译；Python、CUDA 和私有依赖位于 Windows 安装目录。

每台机器只对外提供一个模型（用户 2026-10-19）。对外模型由 `config/deployments/<host>.json` 的 `models`（恰好一个）决定；安装目录只部署它的 prebuilt 配置和 catalog 条目，前端拒绝启动其他量化。Q2_0、IQ2_XS 权重和 pack 可保留，默认不运行或测试，除非用户提出专门任务。维护基线 = 本机唯一对外模型 + 部署默认值（`installation_defaults` 与该模型的首个上下文档位）；引擎参数与测量依据见[调优记录](tuning.md)和[每机调参目录](host-tuning/README.md)。

## 安装目录

受维护代码、启动／压缩提示、调用手册及每台机器的部署配置，以维护工程为唯一来源。安装目录仅保存部署副本、上游制品的安装结果及运行状态；读取安装文件可用于运行、计量和回读核验，不能反过来作为新配置模板。上游制品的版本、下载地址及SHA由工程保存，native packs／MTP的逐文件绑定见[支持资产清单](../config/artifacts/native-support.json)；用户已决定模型、native packs、MTP及既有离线依赖直接从不可变现有文件传输，传完核对完整性，不先建立额外大缓存或重新下载。该复制不作为从安装代码／配置派生另一台发布输入的许可。

两台机器共用代码及实验条件，各自的路径、端口、CPU线程数及显存相关设置单独维护。`config/deployments/`保存公开硬件／部署来源，私有主机配置提供各自安装路径和服务端口；`tools/ops/deployment_source.py`从工程模板生成目标副本，安装文件只用于回读核验。修改部署集合中的工程源后分别同步登记目标；每台须等待空闲、领取维护key、确认模型停止并关闭前端，回读校验。离线／繁忙／失败的目标记录为待同步，不抢占调用方，也不将部分完成称为两台一致。持有状态、日志、运行临时配置及私有凭据不作为公共同步内容；双机文件部署及回读已完成，rtx3080ti三量化短推理已通过，见[短安装验收](../reports/v0.1.40.1/multi-host-deployment/validation.md)及[文件阶段结果](../reports/v0.1.40.1/multi-host-deployment/summary.md)。

私有配置统一放工程根目录 `project.private.toml`（Git 忽略，权限 0600，不部署、不写入报告），包括各主机的 `installation_path`、`frontend_url` 和 Brave key 等凭据，只由程序解析，不读入会话。安装目录需要的敏感配置将放在安装根目录 `installation.private.toml`，由部署程序从工程私有配置写入；当前前端不需要任何安装凭据，该文件在接入托管搜索时才创建。新增主机时增加一个 `[hosts.<id>]` 分组。配置按 UTF-8 读写。

旧的 `ssh-windows` 连接方式（SSH、`listen_port`／`access_port` 端口映射）已废弃；前端常驻 Windows，监听 `config/deployments/<host>.json` 中该主机的地址和端口。部署和测量工具只处理本机安装（经 `wslpath` 访问）。

| 路径 | 内容 |
|---|---|
| `maintenance/Install-Frontend.ps1` | 一次性防火墙和计划任务设置，调用方不执行 |
| `runtime/Strata/` | 固定源码、`engine/strata.exe`、私有 `.venv` 和默认专家 profile |
| `data/models/` | Q2_0、IQ2_XS、IQ3_XXS 双分片 GGUF（只有对外模型被加载，其余保留） |
| `data/packs/` | 各量化 native pack 与 tokenizer |
| `data/mtp/` | 已核验的原始张量、pack 与 runtime draft |
| `config/` | 对外模型的 prebuilt 配置、`deployment.json`、catalog 及 `installed-release.json`；其他量化的 prebuilt 不部署（部署时备份后删除） |
| `downloads/wheels/` | 重建Windows Python环境所需的离线依赖缓存 |
| `logs/` | 前端、原生服务和引擎日志 |
| `src/` | 前端、模型进程管理、原生服务包装、基础提示加载及文件 MCP |
| 根目录 `README.md` | 调用手册；源文件为工程 `docs/installation-directory-readme.md` |
| `deployment-manifest.json` | 最近一次部署的文件清单与 SHA |
| `.tmp/model/` | 每次模型启动生成的临时运行配置 |

部署和升级备份统一放维护工程`.tmp/maintenance-backups/`，分别使用`deploy-*`、`release-backup-*`子目录；回执中的`backup`给出实际位置，`--rollback`可指定工程内的升级备份。工程.tmp仍为临时目录，删除对应备份后不能再据它直接回滚。

维护工程的reports、benchmarks、tools、tests及主题文档不部署到安装目录。旧版本原始会话／运行明细和旧回滚备份删除后，历史汇总仍保留，但不能重放原会话或直接使用已删除备份回滚。

GGUF 第二分片可在整文件 SHA 一致后按各量化预期名称硬链接复用，不能仅根据文件名判断相同。模型分片和 MTP 的核验范围见[下载清单](downloads.md)。

## 升级、部署与恢复

`tools/ops/upgrade_release.py` 从 WSL 更新已安装的固定源包和官方 NVIDIA 引擎。它校验发布元数据、完整 SHA、源码 ZIP 注释绑定的提交、引擎包（0.2.x 起为 tar.gz）逐文件对照 `engine-component.json`（清单 SHA 取自发布 feed）、版本（发布版本与引擎版本分开核对）和 GPU 架构，用固定在工具里的上游 Ed25519 公钥（key_id `5d1bc23abbeffd0d`，源码自带的 `strata_control/update_keys.json` 必须与之相同）核验 `strata-feed.json` 签名和引擎清单签名，元数据里的引擎包条目必须与签名 feed 中的条目完全相同；拒绝链接、设备文件、越界路径、Windows 保留名和以点或空格结尾的名字，路径比较不分大小写；审查 instructions/requirements 是否变化；内容未变的文件不重写，引擎目录中不属于新包的文件备份后删除。工具自己经前端领取租约（被持有则中止），确认模型停止后关闭前端，替换完成再由计划任务重新启动前端；替换期间没有调用方能启动模型。备份后原子替换并回读，删除旧文件后再复核全部写入文件，失败恢复；回滚逐文件继续、最后汇总失败；`--rollback`可使用对应备份回退。v0.1.38的备份路径与实际回归见[升级报告](../reports/v0.1.38/upgrade.md)。

每次升级先核查GitHub官方发布说明、文件／配置及基础提示，再进行一次短调用链检查、default/no-save确认和当前配置／验证范围记录；目标总耗时15—30分钟。较完整回归按周集中，只验证当时使用版本；参数比较按相关变化、性能退化或资源告警触发，不每次或每周全量扫描。权限、guardian、harness或工具协议重要变化提前专项验证，排程与具体待办见[状态页](../.status/index.html)。普通使用可先于完整回归，明确标记仅通过短检查；正式能力测量所需安全门继续单独核对。训练及完整profile对照保留为可选专项。实际启动／请求参数以本机 `config/deployments/<host>.json` 的唯一模型档位和 `installation_defaults` 为准；历史v0.1.38参数选择及局限见[升级总结](../reports/v0.1.38/upgrade-cycle-20261003/summary.md)。

`config/prompts/startup-instructions.txt`保存服务统一追加的启动提示词全文，由`src/native_service.py`在每次模型进程启动时读取并固定。它覆盖Chat、Responses及Messages请求，调用方指令、权限与输出格式继续保留。更新通过同一部署流程进行；已启动实例不热更新，下一次模型启动使用新文件。状态返回该进程加载的提示词SHA，维护工程保留同名源文件。

托管网页搜索（Brave）随旧协议桥一起移除；是否在前端补回留待新版 Codex 路径重新评估时决定。Brave key 继续只保存在工程私有配置中。

服务文件和调用手册由`tools/ops/deploy.py`部署，流程见[前端运行与维护](frontend.md#部署)。服务部署不替换模型权重、MTP或私有依赖；模型配置由工程模板及每机配置生成并同步，不以安装配置作为模板。重新setup或恢复后核对生成配置和安装副本，不能假定setup保留调参。

恢复链接和 18 个离线 wheel 的清单见[下载与恢复](downloads.md)。`tools/ops/install_offline.py` 是 Windows 离线安装辅助：安装目录由所用 venv 推出，引擎用 `upgrade_release` 已装好的 `runtime/Strata/engine`（版本须等于 `installed-release.json` 的 `engine_version`）；执行前核对下载清单。旧v0.1.37一次性离线升级入口已退出长期工具，当前维护使用`tools/ops/upgrade_release.py`。含 Windows 进程 API 的安装/测量工具须使用 Windows 私有 Python，不能直接由 Linux Python 导入。

单个下载文件不超过 200MB 时助手可下载；超过则提供链接、大小、保存路径及校验信息，由用户下载。不拆分文件绕过限制，不清理用户 Downloads。本次v0.1.40升级的引擎包已由助手下载并校验安装，见[下载清单](downloads.md#strata-v0140下载记录)。

## 维护注意事项

- 模型加载需等待真实 ready 和模型请求，不以窗口出现或 health 成功代替完整验收。
- 停止入口先正常卸载，再核对进程路径并终止本安装进程树；不要按通用 `python.exe` 名称停止进程。繁忙时卸载可能返回 409，强制结束不保证保存专家 profile。
- `engine_silence_s` 当前保留默认 300 秒，长 prefill 自适应延长。错误请求终止后由下一请求重启引擎，不代表自动重做失败任务。
- 既有 pinned large pages 日志出现 error 1314 后退回普通页面；未更改系统权限。终端捕获乱码不等于 UTF-8 文件损坏。
- 完整运行记录放 `.tmp`，长期报告独立保留。清理前确认不再需要故障定位或会话 resume；报告保留与复现方法见[测量工具](../tools/README.md)。

调用方管理 harness、权限、工具和压缩，见 [codex.md](codex.md)。安装项目不创建或修改调用方的 Codex 配置。

## 每机安装默认与校准入口

每机安装默认由`config/deployments/<host>.json`的可选`installation_defaults`单独拥有；缺失该项时保持该机原模板，不继承另一台的性能选择。该项可声明窗口、推理强度／预算、采样及CPU辅助；部署工具生成模型预置，前端在请求省略启动覆盖时使用它，显式请求值优先。当前实际值与回读证据以各机部署配置和主机说明为准。

每台机器的参数选择、覆盖边界和待办遵循[每机调参目录](host-tuning/README.md)，不把该目录变成每次升级的全量固定流程。
