# rtx3080ti 升级到 Strata v0.2.11 (2026-11-06)

结论：Strata v0.2.10（引擎 0.1.56）升到 v0.2.11（Control 与引擎 0.1.57），**通过短检查**。只是一次短调用链检查加一次长预填充速度复核，不是评分，不继承旧版本的完整验收结论。草稿器仍是 MTP（模板已钉死）。

## 安装

- 命令：`python3 -m tools.ops.upgrade_release --host rtx3080ti --metadata .tmp/up0211/metadata.json --source artifacts/strata/0.2.11/source.zip --engine artifacts/strata/0.2.11/engine.tar.gz --feed artifacts/strata/0.2.11/strata-feed.json --output .tmp/up0211/upgrade-receipt.json`
- 标签 `v0.2.11` 提交 `c3b3f5035506f3e966f1b4b7b188aeaabae92f1d`（ZIP 注释一致）；源码 ZIP SHA256 `a69ef11b…0b14`；引擎（cuda13）SHA256 `0cdf191f…7c0f`（627,812,560 字节，与 API digest 一致）；feed SHA256 `b993f0d9…bc72f`（sequence 121）；feed 与引擎清单签名均由 `5d1bc23abbeffd0d` 签发，核验通过；build_id `0bdcef4682c5+cuda13.0`，archs 含 sm_86。
- 5455 个文件未变，无上游删除；模型权重、模型配置未改。`requirements.txt` 变了（pillow 13.0.0 对 Python ≥3.11，修 GHSA-78g4-xqwv-q3g8；3.10 仍 12.3.0），本次不重装依赖，只影响图片读取，本机文本路径不涉及。`AGENTS.md` 只改版本行。
- `MODEL_CARD_SAMPLING` 与 v0.2.10 逐字相同，`MODEL_CARD_KEYS` 和 `installation_defaults` 不需改。
- 备份 `.tmp/maintenance-backups/release-backup-20261106-150338-352664`；回退用 `strata components rollback`（只回引擎）或 `upgrade_release --rollback <备份>`。未用回退。
- 升级后 `schtasks /end` + `/run QwenStrataFrontend`，`/health` 正常。
- 单元测试全部通过。

## 发布说明中与本机相关的两项（环境变量回退未用到）

- NVIDIA sm_80+ `--prefill auto` 上限 8192→32768：长预填充实测见下，没有变慢，反而更快，不需要 `STRATA_NV_CHUNK=0`。
- 单卡 CPU/上传分担比例跟随实测：解码速度未降，不需要 `STRATA_PCIE_AUTO_SPLIT=0`。
- 其余（Unsloth 新 GGUF、K-quant 提示核、Mac/Radeon 等）本机不适用。

## 短调用链检查（1 实例，每项 1 次，非计分，隔离环境）

脚本 `.tmp/up0211/smoke.py`（由 v0.2.10 版改版本号）。启动前 `vmrun list` 为 0 个 VM，lease free。

| 阶段 | 内容 | 退出码 | 耗时 s | 输入 tok/s | 解码 tok/s |
|---|---|---|---|---|---|
| C1 | Claude Code：Bash 写 marker、Read 读回、Brave MCP 搜索 | 0 | 69 | 1982 | 91 |
| C2 | `/compact` | 0 | 40 | 850 | 98 |
| C3 | 同线程恢复，无工具回答 | 0 | 14 | 1353 | 106 |
| X1 | Codex：`cat note.txt` + 托管搜索 | 0 | 47 | 1586 | 109 |
| X2 | Codex `--approve-for-me`：沙箱内 curl 失败后提权 | 0 | 57 | 1328 | 86 |

marker 与 note 内容正确，URL 为 v0.2.11 发布页，压缩后恢复正确，Codex 提权后拿到 HTTP 200。解码 86 到 109 tok/s，无低于 60 的降速。输入速度比 v0.2.10 同检查（1894 到 2348）略低，但这些是短提示，含冷加载和首个请求的固定开销，不可直接比。

## 速度复核（长提示，实际工作的输入规模）

两次约 16.3 万 token 的单请求（不同内容，避免缓存），`qwen-agent claude -p`：

| | 提示 token | 引擎输入 tok/s | 引擎输出 tok/s |
|---|---|---|---|
| A | 163,127 | 2542 | 86（1 token 输出，不具代表性） |
| B | 164,540 | 2447 | 75（同上） |

对照 v0.2.10 实际工作（ARW loop，6 万到 12 万以上输入）：输入 2040 到 2205 tok/s，输出 90.5 到 93 tok/s。v0.2.11 长预填充输入快约 10 到 15%；解码在多轮短检查里 86 到 109，与 v0.2.10 的 101 到 112 同量级。长上下文下的持续解码速度（ARW loop 的几十轮）本次没有测，需要在下一次 loop 的引擎日志里复核。

## gates

`safety_gate`、`codex_compact_gate`、`safety_native.mjs` 是每次运行时由测量脚本临时拉起的进程，升级时 WSL 与 Windows 侧都没有它们的存活进程，没有可重启对象；`c3e6d71` 已在工程源码里，下次启动即用新代码（测试 `tests/test_gate_http.py` 通过）。

## 遗留

- 未验证：故障与取消恢复、审批质量、Reviewer 兼容、持续多轮解码速度。
- 发布说明提示不同分块大小可能让部分 agent 提示的首个回答与 v0.2.10 不逐位一致。
- 清理：`artifacts/strata/0.2.9/` 按保留规则可删（只留 0.2.10 作回退），旧备份同理，留给 Main。
