# v0.1.41 升级（rtx3080ti）

2026-10-10，用户允许安装。

## 结论

- rtx3080ti 已升级到 Strata v0.1.41，**通过了短调用链检查**。
  - 2426 个上游文件逐个回读通过。
  - 引擎参数、基础提示和 expert profile 均未改动。
  - 检查经由实际使用的 `bin/qwen-agent` 入口，Claude Code 和 Codex 都覆盖到。
- 本次只是短检查，不代表完整验收，也不继承 v0.1.40.2 的验收结论。
- rtx4070tis 仍离线，版本仍是 v0.1.40.2，恢复后需要同步。
- **已知风险**：上游有一个未关闭的 issue [#1622「Strata v0.1.41 Looping issues」](https://github.com/Niko1221/Strata/issues/1622)，3 位用户反映升级到 v0.1.41 后出现生成循环；还有一个 [#1618](https://github.com/Niko1221/Strata/issues/1618)，同样是无尽思考循环，未注明版本。本次短检查没有出现循环，但规模太小，无法排除。如果实际使用中出现循环，可以用备份回退到 v0.1.40.2，命令见文末。

## 安装

- **来源**：[官方发布](https://github.com/Niko1221/Strata/releases/tag/v0.1.41)，标签提交 `fb58e0dbc8399662c0e47c76578c6e878b14f6cf`。
- **引擎**：137,164,559 字节，SHA256 与官方 digest 一致。
- **源码**：19,149,640 字节，SHA 见[制品清单](../../config/artifacts/strata-v0.1.41.json)。
- **BUILD**：版本 0.1.41，CUDA 13.0，架构包含 86。
- **上游 `AGENTS.md` 有变化**：只新增了「Contributing a change or report」一节，是写给贡献者的说明。审阅后把新文件的 SHA 写进升级 metadata 的 `reviewed_changes`，升级工具只放行这份确切内容。`requirements.txt` 不变。
- **兼容性**（安装前已核对，详见 `docs/plan.md`）：
  - 部署配置用到的 15 个引擎参数都还在。
  - `native_service.py` 打补丁的接口签名不变。
  - 引擎日志中 token 行的格式不变，本次计量正常解析。
- **其他改动**：
  - 工程基线 `config/maintenance-baseline.json` 的版本已改为 0.1.41 并重新部署，21 个文件回读通过。
  - 基础提示安装后的 SHA 与工程一致：startup `5f9efc02…`，compact `3856cb62…`。

## 短检查

只有一个实例，每项跑一次，不取均值，也不算正式评分。Claude Code 2.1.296 使用 `--approval strata`；Codex 0.162.0 使用 `exec` 和只读沙箱。每个阶段是一次独立的 `qwen-agent` 运行，各加载一次模型。

| 阶段 | 内容 | 结果 |
|---|---|---|
| C1 | Bash 写入随机标记（经 qwen-approve 放行）→ Read 读回 → Brave MCP 搜索发布页 | 通过：标记原样读回，URL 正确，两次审批都放行（1.7–2.2 秒） |
| C2 | 同一会话 `/compact`（PreCompact hook 追加工程压缩提示） | 通过：18,686 → 1,821 token，35.1 秒 |
| C3 | 同一会话恢复，不用工具回忆标记和 URL | 通过：输出纯 JSON，两个值都正确，没有调用工具 |
| X1 | Codex 执行 `cat note.txt`，再用托管搜索找发布页 | 通过：命令输出正确，web_search 返回正确 URL |

| 阶段 | 总耗时（秒） | 加载（秒） | 入口请求 | 未缓存输入 | 已缓存输入 | 输出 | 引擎输入 token/s | 引擎输出 token/s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| C1 | 52.474 | 16.320 | 5 | 36200 | 18382 | 650 | 1378.3 | 103.2 |
| C2 | 53.727 | 16.851 | 1 | 20256 | 0 | 1737 | 1047.2 | 110.8 |
| C3 | 37.441 | 16.371 | 1 | 17940 | 0 | 135 | 1032.2 | 103.4 |
| X1 | 38.451 | 16.859 | 2 | 11537 | 9282 | 434 | 828.0 | 109.7 |
| 合计 | 182.093 | 66.401 | 9 | 85933 | 27664 | 2956 | 1117.2 | 108.5 |

- **工作时间**：用总耗时减去加载时间，共 115.692 秒。其中包含停模型和归还租约的时间，所以是上限。
- **任务平均速度**：输入 742.774 token/s，输出 25.551 token/s。
- **计量方式**：token 全部取自引擎日志，每个入口请求对应一个执行段。

**性能**：没有做版本对比。逐个请求对照 2b 中 v0.1.40.2 的同类请求：加载后的第一个请求都约 1000 tok/s（PLE 冷），Claude 的第二个大请求都约 2350 tok/s。看不出退化，也看不出发布说明里所说的 prompt 快 2 倍（#1323）。要下结论，需要另外申请按测量规则做对比。

## 未验证

- **只读文件 MCP**：`qwen-agent` 没有接入，本次没测。
- **审批拒绝路径**：本次只覆盖了放行，拒绝路径见 2b 的 S5。
- **自动压缩**：本次只测了手动 `/compact`，自动压缩见 2b 的 S4。
- **长任务中的循环**：即 #1622 反映的问题，没有覆盖。
- **其他未覆盖范围**：故障和取消后的恢复、Reviewer 兼容、100K 可靠性。

## 回退

如需回退到 v0.1.40.2：

```
python3 -m tools.ops.upgrade_release --host rtx3080ti --rollback .tmp/maintenance-backups/release-backup-20261010-045818-421025 --output .tmp/strata-upgrade-current/out/rollback.json
```

之后还要把 `config/maintenance-baseline.json` 的版本改回 0.1.40.2 并重新部署。备份位于 `.tmp/`，删除后就不能用这个命令回退，只能用 [v0.1.40.2 制品](../../config/artifacts/strata-v0.1.40.2.json)重新安装。

运行明细只保存在 `.tmp/upgrade-0.1.41/`。完整精度数据见 [upgrade.json](upgrade.json)。
