# 本机升级到 Strata v0.2.10 (2026-11-03)

结论：Strata v0.2.9（引擎 0.1.55）升到 v0.2.10（Control 与引擎 0.1.56），**通过短检查**。这只是一次短调用链检查，不继承旧版本的完整验收结论，也不是评分。草稿器仍是 MTP，未启用也未测 DFlash2，速度基线沿用 v0.2.9 的 MTP 配置。

## 安装

- 命令：`python3 -m tools.ops.upgrade_release --metadata .tmp/up0210/metadata.json --source artifacts/strata/0.2.10/source.zip --engine artifacts/strata/0.2.10/engine.tar.gz --feed artifacts/strata/0.2.10/strata-feed.json --output .tmp/up0210/upgrade-receipt.json`
- 标签 `v0.2.10`（标签对象 `db0500a5`）提交 `ffa80d73133ea5c548aefe57889a16e8085a938f`，ZIP 注释绑定该提交；源码 ZIP SHA256 `f00cfe9a…0eb3`（36,598,440 字节）。
- 引擎 SHA256 `5336671c…66ec`（627,806,827 字节）与 API digest 一致；feed SHA256 `bb421243…134d`（sequence 120）；feed 与引擎清单签名都由 `5d1bc23abbeffd0d` 签发，核验通过；build_id `06698c674673+cuda13.0`，archs 含 sm_86。
- 写入 804 个文件（含引擎目录），4885 个未变，没有删除（`previous_source_paths` 为空）；模型权重、模型配置、依赖（`requirements.txt` 未变）均未改。`AGENTS.md` 只改了版本行，SHA `83bb196c…fafd` 已绑定进元数据审查。
- 备份 `.tmp/maintenance-backups/release-backup-20261103-100435-850754`（419 MB）；回滚：`--rollback <该目录>`（或 Strata 自带的 `strata components rollback`，只回引擎，不回源码）。未用回退。
- 元数据脚本的一个小坑：从 v0.2.9 的 `mkmeta.py` 改来的版本把 `source_cmake_version` 写成了 `null`，`upgrade_release` 要求该键不存在才用引擎版本，已在 `metadata.json` 里删掉该键后重跑（第一次在写盘前报错退出，没有改动安装）。
- 前端经计划任务自动重启。

## 实际下载与写盘量

下载 664 MB（引擎 628 + 源码 37 + feed 16 KB），备份 419 MB，引擎和源码写入约 1.0 GB（引擎 970 MB 加源码），另有报告和清单的少量文本，合计约 2.1 GB，在 Main 批准的约 2.0 GB 附近。DFlash2 的 1.2 GB 下载没有发生（见下）。下载 1 次成功，没有重试。

## 发布说明结论（v0.2.10，只列与本机相关的）

| 项 | 结论 |
|---|---|
| DFlash2 成为 Qwen3.8 默认草稿器（Auto） | 见下节。本机仍是 MTP；sm_86 在 DFlash2 的支持列表里，但发布说明没有 3080Ti 数据，不应假定提速（RTX PRO 5000 等测到 +1% 到 +8%，Intel Arc 慢 2.6%）；评估另立任务 |
| Windows 计划任务启动的引擎低磁盘优先级修复（#4733） | 直接相关：前端由计划任务启动。本次冷加载与 v0.2.9 同量级，没有对照数据，不作结论 |
| 工具调用与协议（#4663、#4700、#4751、#4701、#4838） | 已用过的工具在 Anthropic 与 Responses 路线也视为已声明；`tools.write` 之类写法解析成声明工具；`/v1/messages` 上下文溢出改为 Anthropic 原文开头（影响 Claude Code 压缩相关测量，此后的压缩类测量不要与旧版直接比较）。短检查里 Claude Code 的 Bash／Read／MCP 与 Codex 的命令和托管搜索都正常，没有按文本返回的工具调用 |
| Qwen 惩罚项只统计回复 token（#4590） | 采样路径变化，`presence_penalty` 非 0 的请求结果可能不同；本机部署默认 `presence_penalty` 为 0，影响小，未单独验证 |
| 会话停放修复（#4677） | 默认开启，`STRATA_SERVE_STOP_BOUND=0` 可关；对本机会话缓存路径有关，未单独验证 |
| 全卡拆分引擎、8GB 卡 128K、DeepSeek/ISTA-DAS、Mac、AMD、Intel | 本机是 Windows 单卡 NVIDIA，不适用 |

只读了发布说明正文，未逐条跟进上游 PR 和 Issue。

## 核对安装与默认值

- `MODEL_CARD_SAMPLING`：用 v0.2.10 标签的 `serve/server.py` 与 v0.2.9 源码 ZIP 里的同名常量逐字比较，完全相同（`qwen4exp`、`qwen35moe`、`deepseek41` 的键没有变化），所以 `tests/test_deployment_source.py` 的 `MODEL_CARD_KEYS` 和主机 `installation_defaults` 不需要改。
- 草稿器与 `--parallel`：本机 `installation_defaults` 里没有 drafter 或 parallel 键，`config/templates/iq3_xxs-prebuilt.json` 的引擎参数是 `--spec 4 --mtp <层目录> --spec-min-p …`，没有 `--parallel`（主机覆盖 `spec-min-p` 为 0.9）。但启动走 Strata 自带的 `serve/server.py`，它读配置的 `drafting` 键（缺省即 Auto）；Auto 在本机已有 DFlash2 草稿器文件且单请求时会换成 DFlash2，**启动不下载**。本次实测启动日志：`Drafting: MTP (the DFlash2 drafter isn't downloaded yet)`，随后加载 MTP 层（837 MiB 显存），`--lookup-max-t 12: MTP windows up to 4 tokens`，安装目录里只有 DFlash2 源码，没有草稿器权重。因此本机实际仍是 MTP，调参结论（`spec 4`、`spec-min-p 0.9`）仍然对应 MTP；DFlash2 与 MTP 的取舍没有做。
- 风险：谁用 `strata launch` 或应用在本机下载过 DFlash2 草稿器，下次启动就会悄悄换成 DFlash2。这次没有改，留给 Main 决定。
- 启动提示：`/health` 报告 SHA `1cae169a…`、源 `5f9efc02…`、防循环段关闭，与 v0.2.9 一致。
- `claude --version` 仍是 2.1.316，与上次升级时跑过 `claude_compact_probe` 的版本相同，没有重跑；调用手册 `compact_check` 记的版本号（本机段落文件）仍是旧值，上次升级已留给 Main，这次也没改、没部署。
- 单元测试 `python3 -m unittest discover -s tests -p 'test_*.py'`：827 项通过。

## 短调用链检查（1 个实例，每项 1 次，非计分）

隔离环境运行（`env` 重建，新 `CLAUDE_CONFIG_DIR`／`CODEX_HOME`，`--setting-sources user --strict-mcp-config`）。脚本由 v0.2.9 的 `smoke.py` 改版本号而来，只在 `.tmp/up0210/`。启动前 `vmrun list` 为 0 个 VM。模型冷加载 1 次。

| 阶段 | 内容 | 退出码 | 耗时 s | 引擎请求段 | 引擎输入 tok/s | 引擎解码 tok/s |
|---|---|---|---|---|---|---|
| C1 | Claude Code：Bash 写 marker、Read 读回、Brave MCP 搜索 | 0 | 92 | 6 | 2348 | 103 |
| C2 | `/compact` | 0 | 53 | 1 | 1027 | 104 |
| C3 | 同线程恢复，无工具回答 marker 和 URL | 0 | 14 | 1 | 2066 | 110 |
| X1 | Codex：`cat note.txt` 加托管搜索 | 0 | 37 | 3 | 1977 | 112 |
| X2 | Codex `--approve-for-me`：沙箱内 curl 失败后提权重试 | 0 | 37 | 3 | 1894 | 101 |

- C1 耗时含冷加载（约 40 s 专家载入）。marker 文件内容与随机值一致，找到并给出 `https://github.com/Niko1221/Strata/releases/tag/v0.2.10`。C3 回答的 marker 和 URL 与 C1 一致，压缩后恢复正确。
- X1：note 内容正确，托管搜索先搜索再 `open_page`，URL 正确。X2：提权后返回 HTTP 200，审批路径正常。
- 解码 101 到 112 tok/s（v0.2.9 同一套检查为 69 到 128），没有低于 60 tok/s 的降速；这不是对旧版的对照，只说明没有明显退化。
- 摘要原始数据：`smoke-summary.json`（本目录）。

## 偏离与遗留

- 未验证：长上下文、故障与取消恢复、审批质量、Reviewer 兼容、速度对照、DFlash2 在 3080Ti 上的收益；调参结论（采样、窗口、`--pool-workers`、缓存、`spec`）仍是在更早引擎上做的 MTP 结论。
- 工具调用解析与 `/v1/messages` 溢出报错又变了一次，此后的 agent 类和 Claude Code 压缩类测量不要与 v0.2.9 及之前直接比较。
- 清理：`artifacts/strata/0.2.4/`（约 600 MB）和 `.tmp/maintenance-backups/release-backup-20261102-130733-888639`（354 MB，v0.2.9 升级备份）按保留规则应删除，本会话的删除命令被权限分类器拒绝，没有删，留给 Main 清理；`docs/downloads.md` 的 v0.2.4 小节在清理后需补一句"文件已删除"。`artifacts/strata/0.2.9/` 保留作回退。
- 调用手册 Claude Code 核对版本号、README「现行决定」、状态页由 Main 处理。
- 结束时模型已经 `/model/stop` 停止（`clean_unload`），租约已归还，`/health` 的 `lease` 为 `free`，`model` 为空。
