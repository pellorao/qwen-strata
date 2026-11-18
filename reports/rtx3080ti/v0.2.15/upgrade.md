# rtx3080ti 升级到 Strata v0.2.15 源码加引擎 0.1.60 (2026-11-18)

结论：v0.2.12（引擎 0.1.58）升到 v0.2.15（引擎 0.1.60），**通过短检查**。只是一次启动加一次请求的检查，不是评分。收益依据见 `.tasks/qwen-strata/up0214-report-1118.md`：冷预填充约快 6-7%，解码与 MTP 接受率不变。

- 命令：`upgrade_release --host rtx3080ti --metadata <up0214 元数据> --source artifacts/strata/0.2.15/source.zip --engine .../engine.tar.gz --feed .../strata-feed.json`；元数据 `source_cmake_version: 0.1.61`。SHA 与签名见 `docs/downloads.md`。
- 备份 `.tmp/maintenance-backups/release-backup-20261118-193039-831437`；回退用 `upgrade_release --rollback <备份>` 或 `strata components rollback`。
- `installed-release.json`：0.2.15 / 引擎 0.1.60；升级后 `schtasks /end` 加 `/run QwenStrataFrontend`。
- `MODEL_CARD_SAMPLING`：qwen4exp、qwen35moe 与 0.2.12 逐字相同，只删了 deepseek41 组（本机不用），`MODEL_CARD_KEYS` 与 `installation_defaults` 不需改。
- 启动日志：`--mtp` 在命令行，`strata mtp: draft layer loaded`，MTP 仍在用，没被 Auto 改选。
- 短检查：冷加载 28.7 s，一次聊天请求回答 "OK 391"（正确），finish_reason stop；`/health` lease free，model null。

## 短调用链检查（1 实例，每项 1 次，非计分，隔离环境）

经 `bin/qwen-agent`（生产默认档）启动，`env -i`，新 `CLAUDE_CONFIG_DIR`／`CODEX_HOME`，`--setting-sources user`，工作目录 `/tmp/strata-smoke-0.2.15/work`（用完删除）。Claude Code 2.1.327。速度由引擎日志逐段累加（`strata_tokens`），短提示含固定开销，不与长上下文数字比。

| 阶段 | 内容 | 退出码 | 耗时 s | 输入 tok/s | 解码 tok/s |
|---|---|---|---|---|---|
| C1 | Claude Code：Bash 写 marker、Read 读回、Brave MCP 搜索 | 0 | 51 | 2133 | 147 |
| C2 | `/compact` | 0 | 31 | 1089 | 157 |
| C3 | 同会话恢复，无工具回答 | 0 | 13 | 2045 | 149 |
| X1 | Codex：`cat note.txt` 加托管搜索 | 0 | 39 | 1903 | 159 |

marker 回读与恢复后回答都正确，搜索给出 v0.2.15 发布页 URL（Claude 与 Codex 各一次），note 内容正确，压缩后恢复正确。未跑 Codex 审批提权（X2）和较完整的回归（留给每周回归）。
