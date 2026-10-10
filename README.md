# Qwen3.8-Flash-Next / Strata 维护工程

维护本地 Qwen3.8-Flash-Next / Strata 推理服务，并测量它作为 Codex、Claude Code 等 agent 后端的表现。推理在 Windows 原生进程（Python + Strata + CUDA）中运行；调用方经局域网访问常驻前端，领取独占 key 后调用，用完归还。

agent 规则见 [AGENTS.md](AGENTS.md)。

## 主机

| id | 硬件 | 状态 |
|---|---|---|
| `rtx3080ti` | RTX 3080 Ti 12GB，i9-13900 | 可用；本工程所在机 |
| `rtx4070tis` | RTX 4070 Ti SUPER | 离线，短期不启用；原 Spec Readiness 主线在这台 |

rtx3080ti 安装 Strata v0.1.41（2026-10-10，通过短调用链检查）；rtx4070tis 离线，仍为 v0.1.40.2，待同步。模型 Q2_0 / IQ2_XS / IQ3_XXS，未做新版完整验收。

## 文档

| 内容 | 入口 |
|---|---|
| 后续计划与周期流程 | [docs/plan.md](docs/plan.md) |
| 安装目录调用手册（源文件） | [docs/installation-directory-readme.md](docs/installation-directory-readme.md) |
| 安装、升级与下载 | [安装说明](docs/installation.md) · [下载清单](docs/downloads.md) |
| 启停、网络与部署 | [前端运行与维护](docs/frontend.md) |
| 调用方接入 | [docs/codex.md](docs/codex.md) |
| 参数与调优 | [调优记录](docs/tuning.md) · [每机调参手册](docs/host-tuning.md) |
| 上下文压缩 | [docs/compaction-options.md](docs/compaction-options.md) |
| 已验证行为与证据 | [验证汇总](docs/validation.md) · [测量工具](tools/README.md) |
| 已完成工作 | [docs/work-history.md](docs/work-history.md) |

## 主线

- [ ] **rtx3080ti 资源调参**：显存预留已选定 Q2_0 512；spec-min-p 推迟到 temperature 选定之后，见[调参手册](docs/host-tuning.md#rtx3080ti)。
- [ ] **防循环检测**：用两机全部历史案例（235 会话 / 5303 行为 / 156 组循环）改进动态检测，离线进行，见[计划](docs/plan.md#防循环检测)。
- [ ] **rtx4070tis 恢复后**：核对实际状态、补同步部署，再决定 ARW 安全恢复和 Spec Readiness 十二实例。

## 进展

- 2026-10-09 从 Codex 工程迁入：主机改按 GPU 命名；私有配置合并为 `project.private.toml`；tools 按用途分子目录，已关闭路线的脚本和测试删除；规则改写为 `AGENTS.md` + `.claude/rules/` + `.claude/skills/`。
- 维护测量基线：[Q2_0/high/default](config/maintenance-baseline.json)，100K 压缩阈值 / 156584 窗口，8192 思考 / 24576 总输出。历史测量绑定 Codex 0.160.1，换新版 Codex 后的结果单独标注，不改历史标签。
- 2026-10-09 前端重写并部署到 rtx3080ti：常驻 `192.168.60.212:8000`，独占租约 + `/strata/v1/*` 直通原生 Chat / Responses / Messages；WSL 可直连。无模型验收通过。
- 2026-10-09 agent 接入：Codex 0.162.0 与 Claude Code 2.1.295 经 `bin/qwen-agent` 调用本地模型，冒烟检查通过（[记录](docs/work-history.md)）。托管搜索暂缺，见[计划](docs/plan.md#前端)。
- 2026-10-10 2b 模型验收通过（[报告](reports/v0.1.40.2/agent-integration-2b/summary.md)）。搜索三项通过。Claude Code 自写审批（方案 B）优于内置 auto mode。补上了 Claude Code 压缩时的工程压缩提示（PreCompact hook）。SSD 大量读取的原因是每次加载模型都读 36 GB（[探索](reports/v0.1.40.2/resource-calibration/ssd-reads/summary.md)），已改为模型跨租约驻留，相同参数复用不再加载。`qwen-agent` 固定用 `qwen-approve` 审批。
- 2026-10-10 rtx3080ti 升级到 Strata v0.1.41，短调用链检查通过（[报告](reports/v0.1.41/upgrade.md)）。上游有关于 v0.1.41 生成循环的未关闭 issue #1622；用户决定不回退，出现问题就解决。
- 防循环：[CPU 小模型](reports/v0.1.40.2/small-model-decision-30m/summary.md)和 [Strata 判断](reports/v0.1.41/loop-strata-judge/summary.md)两条路线已关闭（Strata 复核在开发集上只把 F1 从 0.612 提到 0.621）。2026-10-10 用户决定只用机械规则，检测到重复只发提醒、不中断；评分合同第 7 版（F2 门槛 0.8，单阈值，按组计分：首次报警与后续报警各占 0.5，线性衰减）。机械规则 r5（窗口 10 条记录）：第一次划分开发集 0.8198、[验证集](reports/v0.1.41/loop-mechanical-gate/summary.md) 0.5409；全部重新随机划分并补齐伴随记录复核后，开发集 0.7586、验证集 0.7841，全量 0.7661。r6 改为连续概率（多处部分相似按 noisy-OR 累加）：开发集 0.8043、验证集 0.7756、全量 0.7974。前端协议桥提醒（`src/loop_reminder.py`）已部署到 rtx3080ti；[真实试跑](reports/v0.1.41/loop-reminder-trial/summary.md) 3 次完成（提醒 7 次，3 次部分有依据、4 次误报；得分 0.699），待审核。
