# Qwen3.8-Flash-Next / Strata 维护工程

维护本地 Qwen3.8-Flash-Next / Strata 推理服务，并测量它作为 Codex、Claude Code 等 agent 后端的表现。推理在 Windows 原生进程（Python + Strata + CUDA）中运行；调用方经局域网访问常驻前端，领取独占 key 后调用，用完归还。

agent 规则见 [AGENTS.md](AGENTS.md)。

## 主机

| id | 硬件 | 状态 |
|---|---|---|
| `rtx3080ti` | RTX 3080 Ti 12GB，i9-13900 | 可用；本工程所在机 |
| `rtx4070tis` | RTX 4070 Ti SUPER | 离线，短期不启用；原 Spec Readiness 主线在这台 |

rtx3080ti 安装 Strata v0.2.2（引擎 0.1.47，2026-10-22，通过短检查），只对外提供 IQ3_XXS，参数沿用 v0.1.42 调参结果（未在新版上重测）；Q2_0、IQ2_XS 权重保留，默认不运行、不测试。rtx4070tis 离线，仍为 v0.1.40.2，对外模型暂定 IQ3_XXS（占位），恢复后核实并同步。

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

- Strata 0.2.x 不用官方安装程序和 `install.ps1`，继续“标签源码 ZIP + 预编译引擎（cuda13 tar.gz）”，由 `upgrade_release` 核验 feed 与引擎清单的 Ed25519 签名；0.2.2 起工具调用解析与 sm_86 解码开关表行为有变，此后的测量不与 0.1.45 结果直接比较（2026-10-22，Main 与独立审查一致）：[升级报告](reports/v0.2.2/upgrade.md)。
- 每台机器只对外提供一个模型：rtx3080ti 为 IQ3_XXS（8 维调参结果为默认值，2026-10-11），Q2_0、IQ2_XS 权重保留，默认不再运行或测试，除非用户提出专门针对它们的任务（走部署 `--condition`，结束后普通部署恢复）；维护基线 = 本机唯一对外模型 + 部署默认值，不再单独成文件（B1）（2026-10-19，用户决定 + 独立审查，rtx3080ti 已部署，安全门按新源重跑通过）：[报告](reports/v0.1.45/single-model/summary.md)、[历史工作](docs/work-history.md#每台机器只对外一个模型维护基线退役2026-10-19)、[调参手册](docs/host-tuning.md#iq3_xxs)。
- IQ3_XXS 默认档改为 206584／150000（2026-10-14）：经过见[历史工作](docs/work-history.md)「自主模式（2026-10-14 01:58 起，已结束）」。
- 思考上限三档 low 2048／8192、medium 4096／16384、high 8192／24576，guardian 512／1024（2026-10-12，回滚方案 A）：[历史工作](docs/work-history.md)「Spec Readiness 思考上限诊断」。
- 显存预留 512（2026-10-11）：[调参报告](reports/v0.1.42/iq3_xxs-tuning/vram-reserve/summary.md)。
- 防循环提醒与检测弃用，只留离线复查（2026-10-11）：[历史工作](docs/work-history.md#2026-10-1011-防循环提醒试跑基线与弃用)。
- Claude Code 用自写审批 `qwen-approve`，不用内置 auto mode（2026-10-10）：[验收报告](reports/v0.1.40.2/agent-integration-2b/summary.md)。
- 模型跨租约驻留，相同参数复用不再加载（2026-10-10）：设计见[前端运行与维护](docs/frontend.md)，决定经过见[历史工作](docs/work-history.md)「2026-10-09 迁移决定」。
- 调参默认用可机械判定的专用负载；ARW 场景须 10 次组内 SD ≤ 0.068（罚前、罚后都满足）才考虑用于调参（此值定于 r8 之前的尺度，r8 尺度下待定，新阈值同时看 `rawScore`，2026-10-16；评分 r8.4 起分数不再截断）；影响输出的参数按分阶段判定（2026-10-12／13，用户决定；规则见[测量规则](.claude/rules/measurement.md)）。
- Spec Readiness 停用合并实例，改用独立根线程（2026-10-13）：[审查报告](reports/v0.1.42/spec-rule-audit/summary.md)。
- Reviewer 评分：证据 F2、按 k 分档计分（默认 0.25，难以核实的 1 或 4；分数以什么都不报为 0、满分为 1，取代 F2 总分与 A／B 两类计分，2026-10-16 评分 r8）、格式罚按比例、罚分归属原则、越过停止点算一个失败反例（2026-10-14／15，评分 r7）、Commit Audit 满足行上的误报只扣一次（2026-10-17，评分 r8.1）、答案键声明的合并用例只计一次（取低分，2026-10-17，评分 r8.2；Commit Audit 发现候选不跨行补关联，评分 r8.3）：经过见[历史工作](docs/work-history.md)，现行规则见[评分规则](.claude/rules/reviewer-suite.md#评分)。
- Reviewer 评分 r8.4：取消分数截到 0 的下限（N < 0 时按答案键全部反例的 k 之和归一，可低于 −1；原始分 ≥ 0 时与 r8.3 逐位相同），整体扣减改为 s − d·|s|；模型失误（没有报告）得 0，与什么都不报相同（用户 2026-10-21 定；负分表示浪费审核时间，没有报告就没有这种浪费）（2026-10-21，用户决定，独立审查有条件实施）：[benchmark 计划 §14.1](benchmarks/multi-model-v1/plan.md#141-冻结后的偏离)、[Reviewer 规则](.claude/rules/reviewer-suite.md)。
- 出题原则：一道题只出一次；意外的重复改题，有意保留的重复在答案键里显式声明为合并用例、评分按声明合并，不靠计分端去重；报告凡给得分处同时给耗时，附 token 数和工具调用数，耗时不进分数（2026-10-16／17，用户决定）：[Reviewer 规则](.claude/rules/reviewer-suite.md)、[Commit Audit v2 变更说明](benchmarks/reviewer-suite-v1/commit-audit-v2.md)。
- 场景能力判定用相对口径 Q3／Opus，目标 < 0.8（2026-10-13；2026-10-15 用户确认维持 Opus 参考）：[Reviewer 规则](.claude/rules/reviewer-suite.md)。
- `qwen-agent` 改按所选量化的默认档启动，Codex 与 Claude Code 同值（IQ3_XXS 206584／150000）；Claude Code 的压缩点依赖未公开的 `CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE`，版本变化后用 `tools.ops.claude_compact_probe` 重新核对（2026-10-19，Main 与独立审查一致，rtx3080ti 已部署，rtx4070tis 补档位后同步）：[报告](reports/v0.1.45/context-tier-unify/summary.md)。
- 所有 Codex Reviewer 臂（含 Strata）对用户登录（`~/.claude/.credentials.json`、`~/.codex` 整个目录，含默认位置的 ChatGPT 登录）和 `project.private.toml` deny-read，偏离 reviewer-suite「不额外收紧」（2026-10-19，Main 按硬约束 4 决定，三种 mock 门用合成文件验证通过，待用户复核）：[ARW Reviewer 规则](.claude/rules/reviewer-suite.md#合同)、[benchmark 计划 §3](benchmarks/multi-model-v1/plan.md#3-固定条件)。
- 报告写授权用专用父目录（目录里只有该报告），绕过 Codex 单文件写授权的 bwrap 故障；安全门与测量同一策略（2026-10-07，用户决定）：[ARW Reviewer 规则](.claude/rules/reviewer-suite.md#正式测量前的安全验收)。
- 多模型 benchmark 的 DeepSeek 改测 low / high / max；已跑的 medium 按方案 C′ 部分并入 high，其余作补充行，Holm 族改为每场景 25 个比较（2026-10-21，用户决定改档，Main 经独立审查定并入方案，待用户复核）：[计划 §14.4](benchmarks/multi-model-v1/plan.md)。
- 多模型 benchmark 的有效性判据：时限提醒或中断送达时正在进行的请求，它的 relay 错误不算错误，实例有效；只此一条（2026-10-23 用户定，取代 10-20 Main 定的 7 条）：[计划 §14 M2](benchmarks/multi-model-v1/plan.md)。
- 多跑的有效实例只要不是按分数加跑，全部进最终实例集合，不截取前 n 个（2026-10-23 用户定，第三阶段起）：[测量规则](.claude/rules/measurement.md)。
- Codex、Claude Code 等 harness 不长期钉旧版：每项工作开始时用当时的最新版，工作期间固定，换版先重跑 mock 门（2026-10-23，用户定）：[测量规则](.claude/rules/measurement.md)。
- rtx3080ti / IQ3_XXS 采样维持 greedy（0/1/20）：ARW code-spec-v5 第 1 轮 greedy、模型卡推荐值、t06 三档分不出，实测 SD 0.072 远大于假设，用户决定不再继续（2026-10-24，用户）：[报告](reports/v0.2.2/sampling-dim/summary.md)。
- rtx3080ti / IQ3_XXS 对外窗口默认维持 206584（压缩阈值约 150000）：窗口维负载对模型侧不敏感、206584 工作时间更短且压缩丢失更少；长上下文记忆重测在 100K–190K 未见断崖，latest 题的弱点在 100K 同样存在、与窗口档无关（2026-10-24，Main 与独立审查一致，待用户复核）：[窗口维](reports/v0.2.2/window-dim/summary.md)、[重测](reports/v0.2.2/longctx-retest/summary.md)。
- `qwen-agent` 关闭 Claude Code 工具搜索（`ENABLE_TOOL_SEARCH=false`）：Strata 不实现延迟加载，工具搜索在 Strata 上不可用（2026-10-24，Main 与独立审查一致，rtx3080ti 已部署）：[报告](reports/v0.2.2/toolsearch-off/summary.md)。
- rtx3080ti 一直用平衡电源计划：高性能的 Strata 速度差不到 1%（2026-10-23）：[报告](reports/v0.2.2/power-plan/summary.md)。
- 多模型 benchmark（2026-10-19，用户决定；方案定稿待冻结，[计划](benchmarks/multi-model-v1/plan.md)）：27 个配置（Codex：gpt-6.1-sol、gpt-6-luna、deepseek-flash、Strata；Claude Code：Opus、Sonnet、Haiku、deepseek-flash、Strata；均 low／medium／high）× 4 场景 × 5 次；只报分场景原始分，不算比值和综合分；两份基础提示只给 Strata（硬约束 3 例外）；搜索全部关闭（2026-10-11 搜索规则在 benchmark 期间豁免）；service tier 一律 default 并记录实际返回值；OpenAI 用 ChatGPT 套餐登录、只报 token。盲裁维持单名 Opus 全量裁（加锚点和合成负例）：按用户的 20% 规则盲裁占 benchmark 的 Anthropic 总消耗中值约 24%，但双裁只省约 $55–58，用户按例外处理、质量优先（2026-10-19，用户决定；计划 §6），"盲裁用 Opus，不用 Sonnet"继续有效。
- 跨 harness 比较以设置一致为目标，不以“各用原生设置”为目标；保留差异须有充分理由并写进计划（2026-10-22，用户决定）：[测量规则](.claude/rules/measurement.md)。

## 主线

- [ ] **多模型 benchmark**：四个 reviewer 场景都已冻结并测完（评分 r8 起的 Q3/Opus：Code Spec v5 0.733（×5，r8 重算）、Code Standards v5.1 0.936（×10，r8 重算；区分度不足的末版）、Spec Readiness v4.3 0.584（×5）、Commit Audit v3 0.730（×5，r8.3）），benchmark 前置工作完成；四个臂已跑完；第一阶段（预登记实例）与第二阶段（Strata 加测进主统计，全样本）都已出报告，公开结果文件已生成（[运行计划](benchmarks/multi-model-v1/plan.md)、[第一阶段报告](reports/v0.1.45/multi-model-benchmark/phase1/summary.md)、[第二阶段报告](reports/v0.1.45/multi-model-benchmark/phase2/summary.md)、[待办](docs/plan.md#多模型-benchmark用户-2026-10-17)）。
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
- 2026-10-19 benchmark 前置：catalog 窗口改取部署档位、去掉写死的窗口与阈值、qwen-agent 统一用默认档，部署到 rtx3080ti，隔离冒烟通过；安全门零模型探针修好（[报告](reports/v0.1.45/context-tier-unify/summary.md)）。安全门按新源重跑通过（[报告](reports/v0.1.45/safety-gate-env-fix/summary.md)）。Sonnet 盲裁试点通过三条通过线（[报告](reports/v0.1.45/sonnet-adjudication-pilot/summary.md)），用户当时决定 benchmark 盲裁仍用 Opus，后按 20% 规则暂定改为双裁（见现行决定）。
- 2026-10-22 多模型 benchmark 第一阶段报告：557 个预登记实例按评分 r8.4 正式计分、会话检查全部完成；100 个预登记比较里低于 21、高于 10、未分出 69，r8.3 对照只改变 1 个结论，A1、A2 敏感性不改结论（[报告](reports/v0.1.45/multi-model-benchmark/phase1/summary.md)）。
- 2026-10-22 多模型 benchmark 第二阶段报告：Strata 两臂各格加到 10 个有效实例并进主统计（120 个加测实例另批盲裁、复核和会话检查）；100 个比较里低于 34、高于 13、未分出 53，相对第一阶段改变 16 个，都是从未分出变为有结论，没有反向变化；A6 变体与 r8.3 对照都不改结论；同时生成 Reviewer Model Benchmark v2.0 用的公开结果文件（[报告](reports/v0.1.45/multi-model-benchmark/phase2/summary.md)）。
- 2026-10-22 rtx3080ti 升级到 Strata v0.2.2（引擎 0.1.47），短检查通过（C1–C3、X1–X2，引擎输出 105.9 tok/s）；greedy 对比本来就不可复现，长提示一问 0.2.2 四次一致答错，只作记录；引擎新提示 `--pool-workers 15`，未验证（[升级报告](reports/v0.2.2/upgrade.md)）。
