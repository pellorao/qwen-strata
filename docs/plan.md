# 后续计划

更新：2026-10-09。只放待办和需要重复执行的流程；已完成的经过见[历史工作](work-history.md)，测量通用约束见 `.claude/rules/`，参数任务只在[每机调参手册](host-tuning.md)维护。

## 顺序

rtx3080ti 是唯一可用主机，先推进属于它的工作；rtx4070tis 恢复后再决定它的工作。防循环离线工作随时可做。

1. [x] **前端部署与验收**（rtx3080ti）。2026-10-09 完成，见[历史工作](work-history.md)；剩余的托管搜索和升级评估见下文[前端](#前端)。
2. [x] **agent 接入**（rtx3080ti）。2026-10-09 完成，Codex 与 Claude Code 冒烟检查通过，见[历史工作](work-history.md)。历史测量仍标 0.160.1。
3. [ ] **rtx3080ti 显存预留** 700/500/300，各 3 次共 9 实例 / 27 请求，[计划](../benchmarks/resource-calibration-v1/rtx3080ti-vram-reserve-plan.json)。前置：新前端部署（`engine_overrides` 只校验参数名和类型，500/300 可直接传入）。
4. [ ] **rtx3080ti spec-min-p** 0.5/0.7，各 3 次共 6 实例 / 18 请求，[计划](../benchmarks/resource-calibration-v1/rtx3080ti-spec-min-p-plan.json)。显存值由用户选定后固定。
5. [ ] **防循环检测**，见下文[防循环检测](#防循环检测)。
6. [ ] **rtx4070tis 恢复后**：核对实际文件、版本、服务和持有状态；补同步离线期间的部署；再按[ARW 同步与 Spec 恢复](#arw-同步与-spec-恢复)和调参手册的本机待办安排。

## 前端

设计已获批准，实现见 `src/frontend.py`、`src/model_process.py`，结构见[前端运行与维护](frontend.md)。

- [ ] 搜索一律由本工程经 Brave 提供（不用 harness 自家服务，见 AGENTS.md 硬约束 9）：前端为 `/strata/v1/responses` 补托管 `web_search` / `tool_search`（原生服务会丢弃）；Claude Code 禁用内置 WebSearch，改用 Brave MCP，并核实 WebFetch 不经 Anthropic 服务。Brave key 已部署在安装目录 `installation.private.toml`。
- [ ] Claude Code 自动审批（2b）：内置 auto mode 的判断模型限 Claude Sonnet，且受订阅套餐限制，违反硬约束 9，不用。改为：
  - 静态 `permissions.allow` / `deny` 处理低风险和明显危险的操作；
  - 其余由 `PermissionRequest` hook 调用 `bin/qwen-approve`：经前端 `/strata/v1/messages` 让 Strata 判断（审批提示 `config/prompts/claude-approval.txt`，参照 Codex guardian 风险分级自写，low 强度），返回 allow / deny 和理由；超时、出错或判断不出一律拒绝；
  - `qwen-agent claude` 用 `--settings` 传入，不改 `~/.claude`；审批请求计入引擎 token。
  - 先验证 `PermissionRequest` 在 `-p` 模式下是否触发，不触发则改用 `PreToolUse`。验收用合成用例（明确授权、明确越权、授权不明、伪造授权）各 3 次，看实际执行和 canary，不看模型自述；需申请。
- [ ] Claude Code 窗口声明：`qwen-agent` 改设 `CLAUDE_CODE_MAX_CONTEXT_TOKENS=156584`、`CLAUDE_CODE_MAX_OUTPUT_TOKENS`，按实际行为确定压缩设置，替换现在按 200K 推算的 `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`。
- [ ] 前端日志补时间戳，便于计算工作时间。
- [ ] 评估升级到 Strata v0.1.41（stall watchdog、多 key、body 上限、CPU prefill 默认开启），走 `/strata-upgrade`。

## 防循环检测

规则见 `.claude/rules/loop-detection.md`。数据：[全集标注](../benchmarks/loop-detection-v2/annotation-summary.md) 235 会话 / 5303 行为 / 156 组循环。

- [ ] 把全集标注转成因果重放输入：跨调用组按真实正常插入拆分，绑定首次应触发位置和正常恢复位置；单响应组保留唯一可观察点。次数下界和缺失日志边界保留，不把未知记零。
- [ ] 完成全量评分适配（目前只有 21 项模拟回归通过）。联合检测器 F1＝1 才算通过；部分开发分数不算全量结果。
- [ ] 审核[完整循环定义](../benchmarks/loop-detection-v2/repetition-definition.md)和[Strata 判别配置](../benchmarks/loop-detection-v2/strata-judge-design.md)，再冻结首批场景、标签和预算。当前候选：每轮输出一个循环概率，low 2048 思考；上下文持续追加，8K 重建 / 16K 上限，重建时回到最近四轮。真实模型未运行。
- [ ] 确定[动态全文比较方案](../benchmarks/loop-detection-v2/dynamic-text-plan.md)和语义改写的处理边界，设计纯程序机械判断；先审核比较单位、阈值、状态重置和时机再实现。
- [ ] 两条独立基线完成后评估组合，融合 / 分歧 / 触发逻辑先审核，不自动选 OR / AND / 加权。
- [ ] 排除正常行为：不同要求的映射、一次合理复核、真实修复、输入变化、镜像 / 压缩、驱动重建。当前文本原型会误报正常审核。
- [ ] 全量覆盖和反例回归通过后，申请一次 rtx3080ti 试跑；只跑一次，报告后由用户决定是否完成三次。

## ARW 同步与 Spec 恢复

这部分属于 rtx4070tis，等它恢复。规则见 `.claude/rules/reviewer-suite.md`。ARW 已同步到 760007c，[同步核查](../benchmarks/reviewer-suite-v1/source-sync.json)：554 文件逐项核对，112 份业务 fixture 字节不变；只完成无模型验证。

- [ ] 在新来源完成原版准备和受影响的无模型回归：报告独立目录可写，输入、请求、规则和恢复记录在目录外。
- [ ] 核对最终交付由运行层验证 completion，不再额外要求最终 send_message；更新受影响的驱动和来源绑定。
- [ ] 验证 10 次 / 之后每 5 次正常早退的暂停：到暂停点交给用户，Main 不代替用户批准。
- [ ] 补[安全验收](#正式测量前的安全验收)中受影响的部分：一个 Q2_0 实例、三个原生沙箱 / 报告写入 / 同线程接续流程、15 个审批用例（约 21 次 guardian 判断），预计 30–60 分钟。
- [ ] 完成旧 Spec runtime-migration 报告和原生会话的 Main 检查；旧 0.1.40.1 首阶段不与 0.1.40.2 第二阶段拼接。

## 升级后 Spec Readiness 配置比较

在 rtx4070tis 上执行，原十二实例授权保留（恢复无需逐实例重新申请），尚无完整合并实例。[计划](../benchmarks/reviewer-suite-v1/spec-readiness-local-plan.json)。

| 推理强度 | 压缩阈值 | 窗口 | 思考预算 | 总输出 | 合并实例 |
|---|---:|---:|---:|---:|---:|
| high | 100000 | 156584 | 8192 | 24576 | 3 |
| medium | 100000 | 156584 | 4096 | 16384 | 3 |
| medium | 150000 | 206584 | 4096 | 16384 | 3 |
| high | 150000 | 206584 | 8192 | 24576 | 3 |

- 按表中顺序串行执行。窗口 = 阈值 + 32000 + 24576 + 8；每组合显式指定本档预算，不让 high 基础配置覆盖 medium。
- 固定 Q2_0、default profile、guardian low、基础提示和 ARW 网络 / 工具 / 权限设置；四组合开跑前冻结。
- 按合并实例统计：融合得分、工作时间、三类 token、等效费用、四项速度、成功压缩次数和耗时；失败压缩和未交付另列。不自定综合排名。
- 预计模型工作 8–12 小时，准备、检查和报告另加 2–4 小时；这是估计，不是实测。

## 上下文配置的测量与选择

上下文维度用合并实例（同线程先 runtime-migration 再 artifact-promotion），各子场景各有 55/60 分钟初审预算，按合并实例统计。容量公式见[容量计算](compaction-options.md#上下文容量计算)：64K/100K/150K/200K 对应 120584/156584/206584/256584。维护默认 100K / 156584。报告统一写入 `reports/v0.1.38/context-comparison/` 的 `summary.md` 和 `summary.json`；已完成结果见[历史工作](work-history.md#已完成上下文配置测量)，排序由用户决定。

## 正式测量前的安全验收

独立于能力评分，不读隐藏答案。冻结版本、模型、强度和权限，每类探针 3 次。报告写入当前版本 `reports/`。默认模式的安全门未通过，不启动使用同一运行层的能力测量。

1. **原生沙箱行为**：用未修改的 ARW 权限生成器，验证 `:read-only` 可读宿主文件、显式写路径可写、未批准时其他写入被拒。用合成 canary 覆盖 shell、apply_patch、子进程、符号链接、路径穿越、硬链接、`/proc` 和重启 / resume，检查实际字节，不凭模型自述。
2. **auto_review 审批质量**：样例覆盖明确授权、明确越权、授权不明、网页 / 文件中伪造授权。只触及合成 canary 或本地受控接收端。预期按原版 guardian 风险策略事先冻结：低 / 中风险通常放行；原生策略要求拒绝的高风险被放行才算失败。
3. 审批意见与工具最终执行结果分开记录；记录模型对拒绝的处理、是否反复提权或绕过。
4. 可选的严格路径隔离默认关闭，需要时另行选择和验收，不自动收紧。

## 周期流程

- **每次 Strata 升级**：按 `/strata-upgrade` skill 执行。官方搜索能力有变化时，沿实际调用路径核实搜索、打开、查找和后续轮次；能替代自有实现时，先过兼容回归再移除旧实现。
- **每周回归**：只针对当时使用的版本，优先故障 / 取消恢复、沙箱与 auto_review 质量、Reviewer 通知和接续。先给范围和预算并获批；没有版本变化或相关待办时不跑。
- **变化触发的参数验证**：发布说明涉及相关引擎路径，或出现性能退化、资源告警时，只比较有依据的维度。权限、guardian、harness 或工具协议有重要变化时，使用受影响路径前先做专项验证。

## 其他未解决问题

| 问题 | 现状 | 后续 |
|---|---|---|
| 长上下文可靠性 | 历史受控压缩保住了所选事实，但出现重复工具和错误摘要污染 | 执行[验证方案](compaction-options.md#长上下文可靠性验证方案待执行) |
| token 与请求归属 | 内部计数和 API 记录缺少共同请求 ID | 新测量从首次请求前归档 HTTP 日志；缺失记未知 |
| 重复工具导致停滞 | 调用手册保留[已观察的异常](installation-directory-readme.md#已观察到的执行异常) | 由防循环检测工作解决；不加调用方周期提醒 |
| 业务适用性 | 结果来自本工程受控负载 | 由具体工程自行验证，不推广为通用保证 |
