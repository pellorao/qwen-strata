# Qwen3.8-Flash-Next / Strata 维护工程

维护本地 Qwen3.8-Flash-Next / Strata 推理服务，并测量它作为 Codex、Claude Code 等 agent 后端的表现。推理在 Windows 原生进程（Python + Strata + CUDA）中运行；调用方经局域网访问常驻前端，领取独占 key 后调用，用完归还。

agent 规则见 [AGENTS.md](AGENTS.md)。

## 主机

| id | 硬件 | 状态 |
|---|---|---|
| `rtx3080ti` | RTX 3080 Ti 12GB，i9-13900 | 可用；本工程所在机 |
| `rtx4070tis` | RTX 4070 Ti SUPER | 离线，短期不启用；原 Spec Readiness 主线在这台 |

两台均安装 Strata v0.1.40.2，模型 Q2_0 / IQ2_XS / IQ3_XXS，只通过限定短调用链检查，未做新版完整验收。

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

- [ ] **agent 接入**：WSL 安装最新版 Codex CLI，写 Codex 与 Claude Code 接入说明和启动脚本，做一次冒烟检查（需申请）。
- [ ] **rtx3080ti 资源调参**：显存预留 700/500/300，然后 spec-min-p 0.5/0.7，见[调参手册](docs/host-tuning.md#rtx3080ti)。
- [ ] **防循环检测**：用两机全部历史案例（235 会话 / 5303 行为 / 156 组循环）改进动态检测，离线进行，见[计划](docs/plan.md#防循环检测)。
- [ ] **rtx4070tis 恢复后**：核对实际状态、补同步部署，再决定 ARW 安全恢复和 Spec Readiness 十二实例。

## 进展

- 2026-10-09 从 Codex 工程迁入：主机改按 GPU 命名；私有配置合并为 `project.private.toml`；tools 按用途分子目录，已关闭路线的脚本和测试删除；规则改写为 `AGENTS.md` + `.claude/rules/` + `.claude/skills/`。
- 维护测量基线：[Q2_0/high/default](config/maintenance-baseline.json)，100K 压缩阈值 / 156584 窗口，8192 思考 / 24576 总输出。历史测量绑定 Codex 0.160.1，换新版 Codex 后的结果单独标注，不改历史标签。
- 2026-10-09 前端重写并部署到 rtx3080ti：常驻 `192.168.60.212:8000`，独占租约 + `/strata/v1/*` 直通原生 Chat / Responses / Messages；WSL 可直连。无模型验收通过，模型经前端的实际运行尚未验证。托管搜索暂缺，见[计划](docs/plan.md#前端)。
- 防循环：[CPU 小模型路线已关闭](reports/v0.1.40.2/small-model-decision-30m/summary.md)；下一步是 [Strata 判别](benchmarks/loop-detection-v2/strata-judge-design.md)、纯程序机械判断及两者组合三条路线，判别配置等待审核。
