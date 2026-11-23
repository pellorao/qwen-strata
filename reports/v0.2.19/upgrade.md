# 本机升级到 Strata v0.2.19 源码加引擎 0.1.65 (2026-11-23)

结论：v0.2.18（引擎 0.1.64）升到 v0.2.19（引擎 0.1.65），**通过短检查**。只是一次启动加几次请求的检查，不是评分。

- 发布说明：对本机有用的是 Qwen3.8 引擎提速（sm_86/89/120，零环境变量）；上游在 RTX 3090 与 2x A4000（同为 sm_86）上测得提示读取 +12% 到 +26%、解码 +13% 到 +20%，答案逐位相同。本机 3080 Ti 的 IQ3_XXS 没有直接数据，实测速度由 qwen-strata/daily 在第一批实际工作后量。Inkling 2 Mini、AMD、macOS、Linux 部分与本机无关。
- 命令：`python3 -m tools.ops.upgrade_release --metadata <metadata.json> --source artifacts/strata/0.2.19/source.zip --engine .../engine.tar.gz --feed .../strata-feed.json --output <receipt.json>`。元数据的 `engine_package` 取 feed 里 cuda13 的那一项（URL 是相对文件名）；`AGENTS.md` 只有版本文字变化，用 `reviewed_changes` 绑定其 SHA，`requirements.txt` 不变。SHA 与签名见 `docs/downloads.md`。
- 下载约 537 MB（引擎 490,092,153 B、源码 ZIP 47,068,207 B、feed 与签名）；Control zip 不需要，没有下。
- 备份 `.tmp/maintenance-backups/release-backup-20261123-093254-803562`；回退用 `python3 -m tools.ops.upgrade_release --rollback <备份> --output <receipt.json>`。
- 随后做了完整重部署（`python3 -m tools.ops.deploy`，24 个文件回读校验一致，备份 `deploy-20261123-093317-206989`）：已部署的安装此前是单安装改名（rm4070）之前的旧代码、旧 `deployment.json` 与旧手册，这次一并换新；前端由计划任务重启，`/health` 通。
- `MODEL_CARD_SAMPLING`：`http_api.py` 与 0.2.18 逐字相同，`MODEL_CARD_KEYS` 与 `installation_defaults` 不需改；启动日志 `sampling defaults from the config: temperature=0.0, top_p=1.0, top_k=20, presence_penalty=0.0`。
- 启动日志：`STRATA_ROUTE_TAIL_SKIP=7 is ON`（显式钉在 `model_environment`，没有靠默认值），引擎命令行 `--spec 4 --mtp`，`strata mtp: draft layer loaded`，`MTP windows up to 4 tokens`，MTP 仍在用。
- Claude Code 2.1.330：压缩阈值零模型探测（3 次，两种方式）通过，手册里的核对版本已加 2.1.330。

## 短调用链检查（1 实例，每项 1 次，非计分，隔离环境）

经安装目录的 `qwen-agent`（生产默认档 206584/150000），`env -i` 式最小环境，新 `CLAUDE_CONFIG_DIR`／`CODEX_HOME`，`--setting-sources user`，工作目录 `/tmp/qwen-strata/up0219/smoke/work`（`/tmp` 下，已删除）。

| 阶段 | 内容 | 退出码 | 耗时 s | 结果 |
|---|---|---|---|---|
| C1 | Claude Code：Bash 写 marker、Read 读回、Brave MCP 搜索 | 0 | 82（含加载模型） | marker 正确，搜索给出 v0.2.19 发布页 URL |
| C2 | `/compact` | 0 | 34 | 完成（压缩请求发出，无报错） |
| C3 | 同会话恢复，无工具回答 | 0 | 14 | 正确答出 `marker-7731` |
| X1 | Codex：`cat note.txt` 加托管搜索 | 0 | 27 | 内容正确，搜索给出发布页 URL |

引擎日志里两个较长请求：9241 token 提示 1000 tok/s、生成 125.5 tok/s（接受草稿 110/117）；12571 token 提示（复用 9236）读 1114 tok/s、生成 112.2 tok/s。样本小且混有短请求，不与长上下文基线比。

## 遗留
- `AGENTS.md` 没有"版本行"可改（工程 `AGENTS.md` 不记 Strata 版本），版本记在 `docs/local-installation.md` 和 `docs/downloads.md`。
- 0.2.18 的升级当时没有登记 `docs/downloads.md`，这次补了 0.2.18 的来源、大小、SHA。
- 未测：不含 Reviewer、审批提权、故障取消恢复，按周集中回归另排。
