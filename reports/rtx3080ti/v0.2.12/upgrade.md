# rtx3080ti 升级到 Strata v0.2.12 (2026-11-08)

结论：Strata v0.2.11（引擎 0.1.57）升到 v0.2.12（Control 与引擎 0.1.58），**通过短检查**。只是一次短调用链检查，不是评分，不继承旧版本的完整验收结论。速度未验证，留给 daily。

## 安装

- 命令：`python3 -m tools.ops.upgrade_release --host rtx3080ti --metadata ... --source artifacts/strata/0.2.12/source.zip --engine artifacts/strata/0.2.12/engine.tar.gz --feed artifacts/strata/0.2.12/strata-feed.json`。
- 标签 `v0.2.12` 提交 `146df3c468739147f520ac3816de806f71232571`（ZIP 注释一致）；源码 ZIP SHA256 `6bee8e4f…17ac`（37,314,704 字节）；引擎（cuda13）SHA256 `3311443b…9f4f`（630,769,464 字节，与 API digest 一致）；feed SHA256 `77bf5e7b…470d`（sequence 122）；feed 与引擎清单签名由 `5d1bc23abbeffd0d` 签发，核验通过；build_id `8a42a9457db6+cuda13.0`，archs 含 sm_86。
- 5657 个文件未变，无上游删除；模型权重、模型配置、依赖未改。`AGENTS.md` 只改版本行（SHA `b0788f3a…50c7` 已在元数据绑定）；`requirements.txt` 不变。
- 备份 `.tmp/maintenance-backups/release-backup-20261108-070726-038730`；回退用 `strata components rollback`（只回引擎）或 `upgrade_release --rollback <备份>`。未用回退。
- 升级后 `schtasks /end` + `/run QwenStrataFrontend`，`/health` 正常，租约 free。

## 核对点

- `MODEL_CARD_SAMPLING`（qwen4exp、qwen35moe、deepseek41 三组）与 v0.2.11 逐字相同，`MODEL_CARD_KEYS` 与 `installation_defaults` 不需改（后者已显式给出 temperature、top_p、top_k、presence_penalty）。
- 新设置 `undeclared_tool_calls`：默认 `text`（行为与旧版一致），配置里没有该键，不需要设；`call` 是可选项，本机不启用。
- 草稿器：本机钉死 MTP；发布说明的调优 DFlash2 对 12 GB 的 UD-IQ4_XS-v31 才由 Auto 启用，对本机 IQ3_XXS + 钉死 MTP 无影响，也不下载 0.34 GB 草稿器。
- 速度口径：发布说明（#5318、#5307、#4006）改了服务报告的速度和时间，短请求的 tok/s 现在把准入时间算进去。下面解码 139 到 149 tok/s 高于 v0.2.11 检查的 86 到 109，**不能直接归为引擎变快**，可能是口径不同（也可能是脚本不同），要在 daily 里同口径复核。
- 与本机相关的修复：#5108（长 CUDA 提示行表越界读，可能崩溃）、#4828 强制 tool_choice、#4832 tool_use_id、#5281 MCP 末段匹配、#5312 Claude Desktop 模型名。未单独验证（本检查走的工具调用路径正常）。

## 短调用链检查（1 实例，每项 1 次，非计分，隔离环境）

脚本 `.tmp/up0212/smoke.py`（v0.2.11 的脚本已不在，重写；Claude Code 2.1.319、Codex 0.167.0，新 `CLAUDE_CONFIG_DIR`／`CODEX_HOME`，工作目录 `/tmp`，`env` 重建）。启动前 `vmrun list` 为 0，无 VM 锁，lease free。速度由引擎日志逐段累加（`strata_tokens.parse_engine_log`），本脚本与 v0.2.11 的脚本可能口径不同。

| 阶段 | 内容 | 退出码 | 耗时 s | 输入 tok/s | 解码 tok/s |
|---|---|---|---|---|---|
| C1 | Claude Code：Bash 写 marker、Read 读回、Brave MCP 搜索 | 0 | 55 | 1844 | 139 |
| C2 | `/compact` | 0 | 32 | 949 | 142 |
| C3 | 同线程恢复，无工具回答 | 0 | 13 | 1866 | 148 |
| X1 | Codex：`cat note.txt` + 托管搜索 | 0 | 28 | 1776 | 149 |
| X2 | Codex `--approve-for-me`：沙箱内 curl 失败后提权 | 0 | 26 | 1693 | 141 |

marker 与 note 内容正确，URL 为 v0.2.12 发布页，压缩后恢复正确，Codex 提权后拿到 HTTP 200。无低于 60 tok/s 的降速。

## 压缩探针

本机 Claude Code 现为 2.1.319（手册核对到 2.1.317）。按部署规则跑了 `tools.ops.claude_compact_probe --repeat 3`，12 格全部通过（149.9K 不压缩，150.1K 压缩，续接正常）。

## 遗留

- 未验证：长上下文持续解码和预填充速度（daily 第 3 项）、故障与取消恢复、审批质量、Reviewer 兼容。
- 手册 `compact_check` 的版本号（本机段落文件中英两份）仍写 2.1.317，要改 2.1.319 并部署；本次未做。源文件已在 `4f51f06` 改为 2.1.319，部署到安装目录另算。
- v0.2.11 升级时没有更新 `config/artifacts/strata-release.json`，本次直接从 0.2.10 改到 0.2.12；`strata-v0.2.11.json` 清单不存在。
- 清理：`artifacts/strata/0.2.9`、`0.2.10` 和 11-06 的升级备份已删（保留 0.2.11 作回退、0.2.12 当前）。
