# Qwen3.8-Flash-Next / Strata 维护工程

维护本地 Qwen3.8-Flash-Next / Strata 推理服务，并测量它作为 Codex、Claude Code 等 agent 后端的表现。推理在 Windows 原生进程（Python + Strata + CUDA）中运行；调用方经局域网访问常驻前端，领取独占 key 后调用，用完归还。

agent 规则见 [AGENTS.md](AGENTS.md)。

## 主机

| id | 硬件 | 状态 |
|---|---|---|
| `rtx3080ti` | RTX 3080 Ti 12GB，i9-13900 | 可用；本工程所在机 |
| `rtx4070tis` | RTX 4070 Ti SUPER | 离线，短期不启用；原 Spec Readiness 主线在这台 |

rtx3080ti 安装 Strata v0.1.45（2026-10-18，通过短检查），只对外提供 IQ3_XXS，参数沿用 v0.1.42 调参结果（未在新版上重测）；Q2_0、IQ2_XS 权重保留，默认不运行、不测试。rtx4070tis 离线，仍为 v0.1.40.2，对外模型暂定 IQ3_XXS（占位），恢复后核实并同步。

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

## 现行决定

只收对整个工程有影响的决定，每条一行：结论、日期、依据（用户决定的出处，或含 Main 与独立 agent 双方意见的报告）。单个场景或单项测量内部的决定留在各自报告里；被取代的决定移到 [work-history](docs/work-history.md)。agent 的工作规则在 [AGENTS.md](AGENTS.md)。

- 每台机器只对外提供一个模型：rtx3080ti 为 IQ3_XXS（8 维调参结果为默认值，2026-10-11），Q2_0、IQ2_XS 权重保留，默认不再运行或测试，除非用户提出专门针对它们的任务（走部署 `--condition`，结束后普通部署恢复）；维护基线 = 本机唯一对外模型 + 部署默认值，不再单独成文件（B1）（2026-10-19，用户决定 + 独立审查）：[历史工作](docs/work-history.md#每台机器只对外一个模型维护基线退役2026-10-19)、[调参手册](docs/host-tuning.md#iq3_xxs)。
- IQ3_XXS 默认档改为 206584／150000（2026-10-14）：经过见[历史工作](docs/work-history.md)「自主模式（2026-10-14 01:58 起，已结束）」。
- 思考上限三档 low 2048／8192、medium 4096／16384、high 8192／24576，guardian 512／1024（2026-10-12，回滚方案 A）：[历史工作](docs/work-history.md)「Spec Readiness 思考上限诊断」。
- 显存预留 512（2026-10-11）：[调参报告](reports/v0.1.42/iq3_xxs-tuning/vram-reserve/summary.md)。
- 防循环提醒与检测弃用，只留离线复查（2026-10-11）：[历史工作](docs/work-history.md#2026-10-1011-防循环提醒试跑基线与弃用)。
- Claude Code 用自写审批 `qwen-approve`，不用内置 auto mode（2026-10-10）：[验收报告](reports/v0.1.40.2/agent-integration-2b/summary.md)。
- 模型跨租约驻留，相同参数复用不再加载（2026-10-10）：设计见[前端运行与维护](docs/frontend.md)，决定经过见[历史工作](docs/work-history.md)「2026-10-09 迁移决定」。
- 调参默认用可机械判定的专用负载；ARW 场景须 10 次组内 SD ≤ 0.068（罚前、罚后都满足）才考虑用于调参（此值定于 r8 之前的尺度，r8 尺度下待定，新阈值同时看截断前的分，2026-10-16）；影响输出的参数按分阶段判定（2026-10-12／13，用户决定；规则见[测量规则](.claude/rules/measurement.md)）。
- Spec Readiness 停用合并实例，改用独立根线程（2026-10-13）：[审查报告](reports/v0.1.42/spec-rule-audit/summary.md)。
- Reviewer 评分：证据 F2、按 k 分档计分（默认 0.25，难以核实的 1 或 4；分数以什么都不报为 0、满分为 1，取代 F2 总分与 A／B 两类计分，2026-10-16 评分 r8）、格式罚按比例、罚分归属原则、越过停止点算一个失败反例（2026-10-14／15，评分 r7）、Commit Audit 满足行上的误报只扣一次（2026-10-17，评分 r8.1）、答案键声明的合并用例只计一次（取低分，2026-10-17，评分 r8.2；Commit Audit 发现候选不跨行补关联，评分 r8.3）：经过见[历史工作](docs/work-history.md)，现行规则见[评分规则](.claude/rules/reviewer-suite.md#评分)。
- 出题原则：一道题只出一次；意外的重复改题，有意保留的重复在答案键里显式声明为合并用例、评分按声明合并，不靠计分端去重；报告凡给得分处同时给耗时，附 token 数和工具调用数，耗时不进分数（2026-10-16／17，用户决定）：[Reviewer 规则](.claude/rules/reviewer-suite.md)、[Commit Audit v2 变更说明](benchmarks/reviewer-suite-v1/commit-audit-v2.md)。
- 场景能力判定用相对口径 Q3／Opus，目标 < 0.8（2026-10-13；2026-10-15 用户确认维持 Opus 参考）：[Reviewer 规则](.claude/rules/reviewer-suite.md)。
- `qwen-agent` 改按所选量化的默认档启动，Codex 与 Claude Code 同值（IQ3_XXS 206584／150000）；Claude Code 的压缩点依赖未公开的 `CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE`，版本变化后用 `tools.ops.claude_compact_probe` 重新核对（2026-10-19，Main 与独立审查一致，rtx3080ti 已部署，rtx4070tis 补档位后同步）：[报告](reports/v0.1.45/context-tier-unify/summary.md)。
- 报告写授权用专用父目录（目录里只有该报告），绕过 Codex 单文件写授权的 bwrap 故障；安全门与测量同一策略（2026-10-07，用户决定）：[ARW Reviewer 规则](.claude/rules/reviewer-suite.md#正式测量前的安全验收)。
- 多模型 benchmark 的盲裁用 Opus，不用 Sonnet：benchmark 结果影响全部后续工作，质量优先（2026-10-19，用户决定；Sonnet 试点达到通过线也不改，[试点报告](reports/v0.1.45/sonnet-adjudication-pilot/summary.md)）。

## 主线

- [ ] **Reviewer 场景重构**：Spec Readiness 已到 v4.1 收尾；Code Spec v4.7 完成（Q3/Opus 0.744，[报告](reports/v0.1.43.1/code-spec-v4/summary.md)）；阅读量维度完成（150K 档成立，Opus 20/20；Q3 原样题命中 88%→73%，[报告](reports/v0.1.44.1/code-spec-rv/summary.md)）；**Code Spec 正式场景 v5 完成**（修订 38，F2 与按对计分：Q3 ×5 0.625 / Opus ×3 0.847，Q3/Opus 0.738，×10 为 0.693；罚前 0.766，[报告](reports/v0.1.44.1/code-spec-v5/summary.md)）；**Code Standards 收尾**：v5.1 为末版，Q3/Opus 0.90，记为区分度不足（v6 r27 全面加难未拉开差距，用户 2026-10-15 决定按停止条件结束）；下一步 Spec Readiness v4.2、Commit Audit；顺序为 Code Spec → Strata 升级到 v0.1.43.1 与例行检查（2026-10-13 完成）→ Code Standards → Commit Audit（用户 2026-10-13）（[计划](docs/plan.md#reviewer-场景重构用户-2026-10-13)）。
- [ ] **rtx4070tis 恢复后**：核对实际状态、补同步部署，再决定 ARW 安全恢复和 Spec Readiness 十二实例。

## 进展

- 2026-10-09 从 Codex 工程迁入：主机改按 GPU 命名；私有配置合并为 `project.private.toml`；tools 按用途分子目录，已关闭路线的脚本和测试删除；规则改写为 `AGENTS.md` + `.claude/rules/` + `.claude/skills/`。
- 2026-10-09 前端重写并部署到 rtx3080ti：常驻 `192.168.60.212:8000`，独占租约 + `/strata/v1/*` 直通原生 Chat / Responses / Messages；WSL 可直连。无模型验收通过。
- 2026-10-09 agent 接入：Codex 0.162.0 与 Claude Code 2.1.295 经 `bin/qwen-agent` 调用本地模型，冒烟检查通过（[记录](docs/work-history.md)）。托管搜索暂缺，见[计划](docs/plan.md#前端)。
- 2026-10-10 2b 模型验收通过（[报告](reports/v0.1.40.2/agent-integration-2b/summary.md)）。搜索三项通过。Claude Code 自写审批（方案 B）优于内置 auto mode。补上了 Claude Code 压缩时的工程压缩提示（PreCompact hook）。SSD 大量读取的原因是每次加载模型都读 36 GB（[探索](reports/v0.1.40.2/resource-calibration/ssd-reads/summary.md)），已改为模型跨租约驻留，相同参数复用不再加载。`qwen-agent` 固定用 `qwen-approve` 审批。
- 2026-10-10 rtx3080ti 升级到 Strata v0.1.41，短调用链检查通过（[报告](reports/v0.1.41/upgrade.md)）。上游有关于 v0.1.41 生成循环的未关闭 issue #1622；此后已升级到更新版本。
- 2026-10-11 rtx3080ti 升级到 Strata v0.1.42，短检查通过；服务默认模型改为 IQ3_XXS，8 维调参完成并部署（[升级报告](reports/v0.1.42/upgrade.md)、[调参手册](docs/host-tuning.md#iq3_xxs)）。Commit Audit 诊断得分 IQ3_XXS 0.837、Q2_0 0.773。
- 防循环：[CPU 小模型](reports/v0.1.40.2/small-model-decision-30m/summary.md)和 [Strata 判断](reports/v0.1.41/loop-strata-judge/summary.md)两条路线已关闭（Strata 复核在开发集上只把 F1 从 0.612 提到 0.621）。2026-10-10 用户决定只用机械规则，检测到重复只发提醒、不中断；评分合同第 7 版（F2 门槛 0.8，单阈值，按组计分：首次报警与后续报警各占 0.5，线性衰减）。机械规则 r5（窗口 10 条记录）：第一次划分开发集 0.8198、[验证集](reports/v0.1.41/loop-mechanical-gate/summary.md) 0.5409；全部重新随机划分并补齐伴随记录复核后，开发集 0.7586、验证集 0.7841，全量 0.7661。r6 改为连续概率（多处部分相似按 noisy-OR 累加）：开发集 0.8043、验证集 0.7756、全量 0.7974。前端协议桥提醒（`src/loop_reminder.py`）已部署到 rtx3080ti；[真实试跑](reports/v0.1.41/loop-reminder-trial/summary.md)和[无提示无提醒基线](reports/v0.1.41/loop-baseline/summary.md)各 3 次（得分 0.699 对 0.656；Commit Audit 场景里循环少见，防护作用测不出）。2026-10-11 用户决定弃用：提醒默认关闭，启动提示默认不加载防循环段，由用户日后触发删除。
- 2026-10-13 Spec Readiness v4（v4.1 键，删除答案不成立的 SEAMS#1）：Opus 0.774、Q3 ×5 0.593，Q3/Opus 0.766，判据四条成立；Q3 ×10 扣罚后 SD 0.073 超 0.068，不用于调参（[报告](reports/v0.1.42/spec-readiness-v4/summary.md)）。
- 2026-10-13 rtx3080ti 升级到 Strata v0.1.43.1，短检查通过（IQ3_XXS 引擎输出 95.9 tok/s，短负载、只跑一次，不作版本对比）；计量解析器适配新的 #2090 分块日志行；新版显存检查在 2/13 个请求上告警（剩余 128–276 MiB），待观察（[升级报告](reports/v0.1.43.1/upgrade.md)）。
- 2026-10-14 rtx3080ti 升级到 Strata v0.1.44.1，短检查通过（[升级报告](reports/v0.1.44.1/upgrade.md)）；调参结论来自旧版本，没有在本版上重新测量。
- 2026-10-17 Spec Readiness v4.2 正式测量完成（评分 r8）：Q3/Opus 0.584（原定 5 次）/ 0.629（10 次），r8 SD 阈值定下前不用于调参；c003 判 supported（已关闭）；v4.2 定为定版、不再加难（Main 与独立审查一致，用户已同意；[报告](reports/v0.1.44.1/spec-readiness-v4.2/summary.md)）。
- 2026-10-18 rtx3080ti 升级到 Strata v0.1.45，短检查通过（含 Codex guardian 子会话，[升级报告](reports/v0.1.45/upgrade.md)）；上游称答案逐字节相同，但 0.1.44.1 在本机参数下 greedy 本身不可复现，逐字比对无法核实，0.1.44.1 上的 Q3 基线沿用与否待定；调参结论来自旧版本，没有在本版上重新测量。

- 2026-10-18 Commit Audit v3 修订号 24 冻结（按难度因素加难，(a) 已确认、(b) 判为无效构造；新题型命中率 14/21 压在 2/3 线上，比值 0.735；Main 与独立审查一致：有条件冻结，条件已落实，用户已知悉）。同日**定版**：Q3 ×5 0.616 / Opus medium ×3 0.843，Q3/Opus 0.730（×10 为 0.706），第二裁决者复评 38/38 一致、11/11 负例识别；区分度主要来自非因素题，(b) 无效；独立意见有条件定版，条件已满足，用户已知悉（[报告](reports/v0.1.45/commit-audit-v3/summary.md)）：[v3 变更说明](benchmarks/reviewer-suite-v1/commit-audit-v3.md#审计校准与冻结2026-10-18)、[设计说明](benchmarks/reviewer-suite-v1/commit-audit-v3-design.md#11-方向停止条件与核对冻结前2026-10-18)、[versions](benchmarks/reviewer-suite-v1/versions.md)。
- 2026-10-19 benchmark 前置：catalog 窗口改取部署档位、去掉写死的窗口与阈值、qwen-agent 统一用默认档，部署到 rtx3080ti，隔离冒烟通过；安全门零模型探针修好，实跑待用户定口径（[报告](reports/v0.1.45/context-tier-unify/summary.md)）。Sonnet 盲裁试点通过三条通过线（[报告](reports/v0.1.45/sonnet-adjudication-pilot/summary.md)），benchmark 裁决模型待用户定。
