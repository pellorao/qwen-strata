# rtx3080ti 升级到 Strata v0.2.16 源码加引擎 0.1.62 (2026-11-20)

结论：v0.2.15（引擎 0.1.60）升到 v0.2.16（引擎 0.1.62），**通过短检查**。只是一次启动加几次请求的检查，不是评分。引擎 0.1.62 用 Strata 自研内核（无 ggml/llama.cpp 矩阵内核）。

- 命令：`upgrade_release --host rtx3080ti --metadata <metadata.json> --source artifacts/strata/0.2.16/source.zip --engine .../engine.tar.gz --feed .../strata-feed.json`。SHA 与签名见 `docs/downloads.md`。
- 源码 ZIP 布局改变（`terminal/` 放 Python 运行时，`engine/` 放引擎源码），旧 `upgrade_release` 会把引擎源码写进二进制目录；已改为只装 `terminal/` 到 `runtime/Strata`，并加测试 `test_terminal_layout_installs_only_terminal_and_agents`。
- 备份 `.tmp/maintenance-backups/release-backup-20261120-124134-621860`；回退用 `upgrade_release --rollback <备份>`。0.2.12 制品已删（来源与 SHA 留在 `docs/downloads.md`）。
- `MODEL_CARD_SAMPLING`：qwen4exp、qwen35moe 两组与 0.2.15 相同（现在位于 `terminal/serve/server_parts/http_api.py`），`MODEL_CARD_KEYS` 与 `installation_defaults` 不需改。
- 启动日志：引擎命令行含 `--spec 4 --mtp`，`strata mtp: draft layer loaded`，MTP 仍在用。

## 短调用链检查（1 实例，每项 1 次，非计分，隔离环境）

经安装目录的 `qwen-agent`（生产默认档，IQ3_XXS 206584/150000）启动，`env -i`，新 `CLAUDE_CONFIG_DIR`／`CODEX_HOME`，`--setting-sources user`，工作目录 `/tmp/.../work`（用完删除）。Claude Code 2.1.329。

| 阶段 | 内容 | 退出码 | 耗时 s | 结果 |
|---|---|---|---|---|
| C1 | Claude Code：Bash 写 marker、Read 读回、Brave MCP 搜索 | 0 | 63 | marker 正确，搜索给出 v0.2.16 发布页 URL |
| C2 | `/compact` | 0 | 28 | 完成 |
| C3 | 同会话恢复，无工具回答 | 0 | 13 | 正确答出 `marker-7731` |
| X1 | Codex：`cat note.txt` 加托管搜索 | 0 | 22 | 内容正确，搜索给出发布页 URL |

全部 9 个请求合计：未缓存输入 1995 tok/s，解码 135.5 tok/s（引擎日志，`engine_speed`；短提示含固定开销，不与长上下文数字比）。未跑 Codex 审批提权。
