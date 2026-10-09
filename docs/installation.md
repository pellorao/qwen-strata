# 安装与维护

安装目录：rtx3080ti 为 `C:\Users\pello\AppData\Local\Programs\qwen-3.8-flash-next`（WSL `/mnt/c/Users/pello/AppData/Local/Programs/qwen-3.8-flash-next`）；rtx4070tis 为 `C:\Users\Pello\AppData\Local\Programs\qwen-3.8-flash-next`。维护工程位于 `/home/pello/projects/qwen_strata`；日常启动只依赖安装目录。

模型、tokenizer、native pack、MTP、私有 Python 和 CUDA 依赖均保存在 Windows。WSL 运行服务入口和调用方 harness，推理由 Windows 原生进程执行。日常命令、API 地址及网络设置见 [WSL 运行说明](wsl-running.md)。

## 版本与环境

当前双机安装Strata v0.1.40.2，提交`e8ca9afd03d839d4f8dbbe82dffce7f8a3bafd7a`，源包及官方NVIDIA引擎均更新，架构86／89已核对；各机2264个上游文件及26个部署文件回读通过。每机一个有效短观测、12个入口请求／13个内部段通过生成、工具往返、实际搜索引用、MCP、无害审批、短压缩及同线程恢复；rtx3080ti一次路径读取恢复与额外加载保留。见[升级与快速验证](../reports/v0.1.40.2/upgrade.md)。现有Q2/high/default及各机参数沿用，模型／依赖未改，完整安全质量、真实100K可靠性及正式Reviewer验收仍未完成；旧版本经过见[历史工作](work-history.md)。

rtx3080ti 为 i9-13900、RTX 3080 Ti 12 GB。rtx4070tis 为 i9-14900K、64 GB RAM、RTX 4070 Ti SUPER 16 GB、NVMe。CPU 支持 AVX2/FMA/F16C，无 AVX-512。Windows 私有环境由 `C:\Python314\python.exe` 3.14.7 创建，依赖检查通过；历史Linux Codex验收版本为0.160.0，当前原生回归使用0.160.1。当前使用官方预编译引擎，无需安装编译工具或重新编译。

默认加载 Q2_0，IQ2_XS、IQ3_XXS 均已安装。引擎参数与测量依据见[调优记录](tuning.md)。当前运行起点按用户决定使用Q2_0/high/default，思考8192、总输出24576，100000压缩阈值及156584引擎/harness窗口；具体启动和生成选项见[运行基线](../config/maintenance-baseline.json)。这是用户选择，当前版本完整推理验收和新增调参仍待执行；所选容量通过启动参数显式覆盖，安装原始配置保留250000。调用方须同步自己的harness及模型catalog，不自动改写其他工程配置。

## 安装目录

受维护代码、启动／压缩提示、调用手册、公共运行基线及每台机器的部署配置，以维护工程为唯一来源。安装目录仅保存部署副本、上游制品的安装结果及运行状态；读取安装文件可用于运行、计量和回读核验，不能反过来作为新配置模板。上游制品的版本、下载地址及SHA由工程保存，native packs／MTP的逐文件绑定见[支持资产清单](../config/artifacts/native-support.json)；用户已决定模型、native packs、MTP及既有离线依赖直接从不可变现有文件传输，传完核对完整性，不先建立额外大缓存或重新下载。该复制不作为从安装代码／配置派生另一台发布输入的许可。

两台机器共用代码及实验条件，各自的路径、端口、CPU线程数及显存相关设置单独维护。`config/deployments/`保存公开硬件／部署来源，私有主机配置提供各自安装路径和服务端口；`tools/ops/deployment_source.py`从工程模板生成目标副本，安装文件只用于回读核验。修改部署集合中的工程源后分别同步登记目标；每台须等待空闲、领取维护key、确认模型停止并持有启动互斥，回读校验。离线／繁忙／失败的目标记录为待同步，不抢占调用方，也不将部分完成称为两台一致。持有状态、日志、运行临时配置及私有凭据不作为公共同步内容；双机文件部署及回读已完成，rtx3080ti三量化短推理已通过，见[短安装验收](../reports/v0.1.40.1/multi-host-deployment/validation.md)及[文件阶段结果](../reports/v0.1.40.1/multi-host-deployment/summary.md)。

私有配置统一放工程根目录 `project.private.toml`（Git 忽略，权限 0600，不部署、不写入报告），包括各主机的 `installation_path`、`frontend_url` 和 Brave key 等凭据，只由程序解析，不读入会话。新增主机时增加一个 `[hosts.<id>]` 分组。配置按 UTF-8 读写。

旧的 `ssh-windows` 连接方式（SSH、`listen_port`／`access_port` 端口映射）随前端重写一起废弃；新方式是前端常驻在 Windows、监听局域网固定端口（rtx3080ti 为 `192.168.60.212:8000`），见[计划](plan.md#前端)。rtx4070tis 离线，连接字段留空。

| 路径 | 内容 |
|---|---|
| 根目录 `Run-Strata-Controller.sh`／`Run-Strata-Controller.ps1` | 旧控制器入口，前端重写后删除 |
| `maintenance/` | 安装维护者使用的一次性网络设置，调用方不执行 |
| `runtime/Strata/` | 固定源码、`engine/strata.exe`、私有 `.venv` 和默认专家 profile |
| `data/models/` | Q2_0、IQ2_XS、IQ3_XXS 双分片 GGUF |
| `data/packs/` | 各量化 native pack 与 tokenizer |
| `data/mtp/` | 已核验的原始张量、pack 与 runtime draft |
| `config/` | 模型配置及 `installed-release.json` |
| `downloads/wheels/` | 重建Windows Python环境所需的离线依赖缓存 |
| `logs/` | 宿主服务、桥及相关运行日志 |
| `src/` | 私有模型生命周期、API鉴权、控制器、协议桥及文件 MCP 实现 |
| `.state/` | 持有状态及内部维护凭据；不属于调用方接口或报告 |
| 根目录 `README.md` | 独占控制、接口、参数和异常说明；源文件在维护工程docs中 |
| `.tmp/controller-model/` | 模型启动所需的临时参数配置；继续由独立安装服务生成 |

部署和升级备份统一放维护工程`.tmp/maintenance-backups/`，分别使用`wsl-deploy-*`、`release-backup-*`子目录；成功或失败回执中的`backup`给出实际位置，`--rollback`可指定工程内的升级备份。模型启动配置继续留在安装目录`.tmp/controller-model/`，本次只调整维护备份位置，不改变其清理行为；既有备份不自动迁移。工程.tmp仍为临时目录，删除对应备份后不能再据它直接回滚。

维护工程的reports、benchmarks、tools、tests及主题文档不部署到安装目录。旧版本原始会话／运行明细和旧回滚备份删除后，历史汇总仍保留，但不能重放原会话或直接使用已删除备份回滚。

GGUF 第二分片可在整文件 SHA 一致后按各量化预期名称硬链接复用，不能仅根据文件名判断相同。模型分片和 MTP 的核验范围见[下载清单](downloads.md)。

## 升级、部署与恢复

`tools/ops/upgrade_release.py` 从 WSL 更新已安装的固定源包和官方 NVIDIA 引擎。它校验发布元数据、完整 SHA、ZIP 成员、版本和 GPU 架构，审查 instructions/requirements 是否变化。维护者先通过控制器取得独占key，以进程环境变量`STRATA_API_KEY`提供给升级工具；模型及原生服务必须停止，控制器可以常驻。替换阶段再次鉴权并持有Windows启动互斥锁，不绕过持有者或抢占模型。凭据经私有标准输入传递，不放在命令参数、提示词或报告中。备份后原子替换并回读，失败恢复；`--rollback`可使用对应备份回退。完成后归还key。v0.1.38的备份路径与实际回归见[升级报告](../reports/v0.1.38/upgrade.md)。

每次升级先核查GitHub官方发布说明、文件／配置及基础提示，再进行一次短调用链检查、default/no-save确认和当前配置／验证范围记录；目标总耗时15—30分钟。较完整回归按周集中，只验证当时使用版本；参数比较按相关变化、性能退化或资源告警触发，不每次或每周全量扫描。权限、guardian、harness或工具协议重要变化提前专项验证，统一见[混合维护流程](plan.md#周期流程)。普通使用可先于完整回归，明确标记仅通过短检查；正式能力测量所需安全门继续单独核对。训练及完整profile对照保留为可选专项。实际启动／请求参数以[运行基线](../config/maintenance-baseline.json)为准，历史v0.1.38参数选择及局限见[升级总结](../reports/v0.1.38/upgrade-cycle-20261003/summary.md)。

`config/prompts/startup-instructions.txt`保存服务统一追加的启动提示词全文，由`src/native_service.py`在每次模型进程启动时读取并固定。它覆盖Chat、Responses及服务内工具后续轮次，调用方指令、权限与输出格式继续保留。更新通过同一维护独占及启动互斥部署流程进行；已启动实例不热更新，下一次模型启动使用新文件。状态返回该进程加载的提示词SHA，维护工程保留同名源文件。

Brave搜索由安装Responses桥执行。维护者将API key单独一行保存在工程Git忽略的私有`.state/brave-api-key.txt`（0600），再按各机维护独占／启动互斥部署为安装同名私有文件并私下回读。首次已获用户明确授权，从rtx4070tis既有安装一次迁入工程私有来源并部署rtx3080ti；以后安装文件只作目标，不反向作为新key来源。安装文件限制安装账户及系统维护账户读取，不加入配置快照、提示词、Git或报告，公共26文件部署工具不复制或覆盖key；key改变时单独同步各使用该凭据的登记安装。更新key无需改调用方或重启模型。历史及逐轮计量位于`.state/search/`，按持有者隔离，旧key归还且会话无需恢复后可清理。具体调用语义、索引摘要与live正文的区别见[调用手册](installation-directory-readme.md#网页搜索)。

服务入口和说明由`tools/ops/deploy_wsl.py`部署，运行文件替换同样要求维护者的`STRATA_API_KEY`及模型停止，并在启动互斥锁内执行；`--docs-only`仅同步说明、已完成的汇总报告并清理已归档的旧用例和测量明细，不需要key。具体入口见[WSL运行说明](wsl-running.md)。服务部署不替换模型权重、MTP或私有依赖；模型配置由工程模板及每机配置生成并同步，不以安装配置作为模板。重新setup或恢复后核对生成配置和安装副本，不能假定setup保留调参。

恢复链接和 18 个离线 wheel 的清单见[下载与恢复](downloads.md)。`tools/ops/install_offline.py` 是 Windows 离线安装辅助；执行前须核对其固定版本、目录和下载清单。旧v0.1.37一次性离线升级入口已退出长期工具，当前维护使用`tools/ops/upgrade_release.py`。含 Windows 进程 API 的安装/测量工具须使用 Windows 私有 Python，不能直接由 Linux Python 导入。

单个下载文件不超过 200MB 时助手可下载；超过则提供链接、大小、保存路径及校验信息，由用户下载。不拆分文件绕过限制，不清理用户 Downloads。本次v0.1.40升级的引擎包已由助手下载并校验安装，见[下载清单](downloads.md#strata-v0140下载记录)。

## 维护注意事项

- 模型加载需等待真实 ready 和模型请求，不以窗口出现或 health 成功代替完整验收。
- 停止入口先正常卸载，再核对进程路径并终止本安装进程树；不要按通用 `python.exe` 名称停止进程。繁忙时卸载可能返回 409，强制结束不保证保存专家 profile。
- `engine_silence_s` 当前保留默认 300 秒，长 prefill 自适应延长。错误请求终止后由下一请求重启引擎，不代表自动重做失败任务。
- 既有 pinned large pages 日志出现 error 1314 后退回普通页面；未更改系统权限。终端捕获乱码不等于 UTF-8 文件损坏。
- 完整运行记录放 `.tmp`，长期报告独立保留。清理前确认不再需要故障定位或会话 resume；报告保留与复现方法见[测量工具](../tools/README.md)。

调用方管理 harness、权限、工具和压缩，见 [codex.md](codex.md)。安装项目不创建或修改调用方的 Codex 配置。

## 每机安装默认与校准入口

每机安装默认由`config/deployments/<host>.json`的可选`installation_defaults`单独拥有；缺失该项时保持该机原模板，不能从公共维护起点静默继承另一台性能选择。该项可声明窗口、推理强度／预算、采样及CPU辅助，部署工具生成模型预置，控制器在省略启动覆盖时使用它，显式调用值优先。rtx3080ti当前156584／high／8192／24576及auto已渲染并回读，rtx4070tis预置没有迁入rtx3080ti选择。已核对范围和忙碌目标待同步见[默认核查](../reports/v0.1.40.1/installation-defaults.json)。

已有rtx3080ti全部参数选择、rtx4070tis覆盖及新主机独立校准遵循[每机调参手册](host-tuning.md)，不把该手册变成每次升级的全量固定流程。
