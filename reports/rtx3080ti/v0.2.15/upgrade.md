# rtx3080ti 升级到 Strata v0.2.15 源码加引擎 0.1.60 (2026-11-18)

结论：v0.2.12（引擎 0.1.58）升到 v0.2.15（引擎 0.1.60），**通过短检查**。只是一次启动加一次请求的检查，不是评分。收益依据见 `.tasks/qwen-strata/up0214-report-1118.md`：冷预填充约快 6-7%，解码与 MTP 接受率不变。

- 命令：`upgrade_release --host rtx3080ti --metadata <up0214 元数据> --source artifacts/strata/0.2.15/source.zip --engine .../engine.tar.gz --feed .../strata-feed.json`；元数据 `source_cmake_version: 0.1.61`。SHA 与签名见 `docs/downloads.md`。
- 备份 `.tmp/maintenance-backups/release-backup-20261118-193039-831437`；回退用 `upgrade_release --rollback <备份>` 或 `strata components rollback`。
- `installed-release.json`：0.2.15 / 引擎 0.1.60；升级后 `schtasks /end` 加 `/run QwenStrataFrontend`。
- `MODEL_CARD_SAMPLING`：qwen4exp、qwen35moe 与 0.2.12 逐字相同，只删了 deepseek41 组（本机不用），`MODEL_CARD_KEYS` 与 `installation_defaults` 不需改。
- 启动日志：`--mtp` 在命令行，`strata mtp: draft layer loaded`，MTP 仍在用，没被 Auto 改选。
- 短检查：冷加载 28.7 s，一次聊天请求回答 "OK 391"（正确），finish_reason stop；`/health` lease free，model null。未做工具调用、MCP、压缩的短链检查（up0214 评估已用 0.2.15 源码跑过 16 个实例的长上下文请求）。
