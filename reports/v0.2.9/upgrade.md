# 本机升级到 Strata v0.2.9 (2026-11-02)

结论：Strata v0.2.4（引擎 0.1.48）升到 v0.2.9（Control 与引擎 0.1.55），**通过短检查**。这只是一次短调用链检查，不继承旧版本的完整验收结论，也不是评分。

## 安装

- 命令：`python3 -m tools.ops.upgrade_release --metadata .tmp/up029/metadata.json --source artifacts/strata/0.2.9/source.zip --engine artifacts/strata/0.2.9/engine.tar.gz --feed artifacts/strata/0.2.9/strata-feed.json --output .tmp/up029/upgrade-receipt.json`
- 标签 `v0.2.9` 提交 `c62d5e3a15b40ea51c96aae9e8d36928965f53ab`，ZIP 注释绑定该提交；源码 ZIP SHA256 `4c5f3c00…1e6f`（34,878,231 字节）。
- 引擎 SHA256 `34f399a0…67df`（621,585,315 字节）与 API digest 一致；feed SHA256 `05cc1b22…4014`；feed 与引擎清单签名都由 `5d1bc23abbeffd0d` 签发，核验通过；build_id `99866a47a2b8+cuda13.0`，archs 含 sm_86。
- 写入 982 个文件（含引擎目录），4345 个未变，没有删除（`previous_source_paths` 为空）；`config/installed-release.json` 已读回为 0.2.9／`c62d5e3a`／0.1.55。模型权重、模型配置、依赖（`requirements.txt` 未变）均未改。
- `AGENTS.md` 变化是文档改写，SHA `ba70683a…7a69` 已绑定进元数据审查。
- 备份 `.tmp/maintenance-backups/release-backup-20261102-130733-888639`（354 MB）；回滚：`--rollback <该目录>`。旧的 0.2.4 升级备份已删除，只保留最新一份。
- 前端经计划任务自动重启。

## 实际写盘量

下载 656 MB（引擎 622 + 源码 35 + feed），备份 354 MB，引擎和源码写入约 1.0 GB，另有报告和清单的少量文本，合计约 2.0 GB，在用户批准的 1.7 到 2.5 GB 范围内。`artifacts/strata/0.2.2/`（584 MB）已删除。

## 发布说明结论（v0.2.5 到 v0.2.9，只列与本机相关的）

| 项 | 结论 |
|---|---|
| 引擎 0.1.48 到 0.1.55 | 本机包为 cuda13，sm_86 在 archs 中。Windows 与单卡路径的速度变化，发布说明没有给出 3080Ti 数据；短检查解码约 100 到 128 tok/s，高于 60 tok/s 降速线，但这不是对旧版的对照 |
| 工具调用（v0.2.8、v0.2.9） | 代码围栏和缩进块里的调用不再执行（#4702、#4703）；已用过的工具视为已声明（#4663）；默认开启。短检查里 Claude Code 的 Bash／Read／MCP 和 Codex 的命令与托管搜索都正常，日志里没有按文本返回的记录。agent 类测量不要与旧版结果直接比较 |
| 路由偏置（v0.2.7 开、v0.2.8 改回默认关） | 默认关，无影响 |
| Linux NVIDIA 并行、GDN 内核 | 只限 Linux，本机是 Windows 原生，不适用 |
| Strix Halo、Intel Arc、DeepSeek、Unsloth 1-bit 选项 | 不相关 |
| 引擎编译含机器上全部 NVIDIA 架构（#4662） | 对本机无影响（单卡） |
| 聊天空请求返回 400（v0.2.6） | 对我们的路径无影响，未单独验证 |

未逐条跟进上游 PR 和 Issue，只读了发布说明正文。

## 核对安装

- `MODEL_CARD_SAMPLING`：与 v0.2.4 完全相同（`qwen4exp`、`qwen35moe`、`deepseek41` 的键没有变化），所以 `tests/test_deployment_source.py` 的 `MODEL_CARD_KEYS` 和主机 `installation_defaults` 不需要改。
- 启动提示：`/health` 报告 SHA `1cae169a…`、源 `5f9efc02…`、防循环段关闭，与 v0.2.4 一致。
- `claude --version` 现为 2.1.316，调用手册记的核对版本是 2.1.310。已按部署规则先跑 `claude_compact_probe --repeat 3`：206584／150000 档 12 格全部通过。**手册里的版本号（`docs/installation-local-sections.md` 的 `compact_check`）还没改，也没部署**，留给 Main。
- 单元测试 `python3 -m unittest discover -s tests -p 'test_*.py'` 通过。

## 短调用链检查（1 个实例，每项 1 次，非计分）

隔离环境运行（`env` 重建，新 `CLAUDE_CONFIG_DIR`／`CODEX_HOME`，`--setting-sources user --strict-mcp-config`）。模型冷加载 1 次。脚本由 v0.2.4 的 `smoke.py` 改版本号而来，只在 `.tmp/up029/`。

| 阶段 | 内容 | 退出码 | 耗时 s | 引擎请求段 | 引擎输入 tok/s | 引擎解码 tok/s |
|---|---|---|---|---|---|---|
| C1 | Claude Code：Bash 写 marker、Read 读回、Brave MCP 搜索 | 0 | 65 | 5 | 2262 | 103 |
| C2 | `/compact` | 0 | 35 | 1 | 1139 | 111 |
| C3 | 同线程恢复，无工具回答 marker 和 URL | 0 | 13 | 1 | 1865 | 110 |
| X1 | Codex：`cat note.txt` 加托管搜索 | 0 | 37 | 3 | 1958 | 128 |
| X2 | Codex `--approve-for-me`：沙箱内 curl 失败后提权重试 | 0 | 37 | 4 | 1825 | 69 |

- C1：marker 文件内容与随机值一致，找到并给出 `https://github.com/Niko1221/Strata/releases/tag/v0.2.9`。C3 回答的 marker 和 URL 与 C1 一致，压缩后恢复正确。
- X1：note 内容正确，托管搜索先搜索再 `open_page`，URL 正确。X2：沙箱内 curl 退出码 6，提权后返回 HTTP 200，审批路径正常。
- 解码最低 69 tok/s（X2，输出里含较多思考），没有低于 60 tok/s 的降速。
- 摘要原始数据：`smoke-summary.json`（本目录）。

## 偏离与遗留

- 未验证：长上下文、故障与取消恢复、审批质量、Reviewer 兼容、速度对照（没有与 0.1.48 的同条件对比）；调参结论（采样、窗口、`--pool-workers`、缓存）都是在 0.1.48 上做的，需要时重新验证。
- 工具调用解析又变了一次，此后的 agent 类测量不要与 v0.2.4 及之前的结果直接比较（与 v0.2.2 的同类记录一致）。
- 调用手册 Claude Code 核对版本号待改为 2.1.316 并部署；README「现行决定」、状态页由 Main 处理。
- 结束时模型已经 `/model/stop` 停止，租约已归还，`/health` 的 `lease` 为 `free`。
