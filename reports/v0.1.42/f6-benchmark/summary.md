# F6 ARW Reviewer benchmark（本机，Strata 0.1.42，IQ3_XXS 默认部署）

日期 2026-10-12。四个场景各跑 5 个有效实例，顺序为 Commit Audit → Code Spec → Code Standards → Spec Readiness。每个场景分两批：批 a 跑 3 个，批 b 跑 2 个（Spec Readiness 批 b 用 `--limit 4`，即 2 个合并实例）。逐实例数据见 [summary.json](summary.json)。

## 结论

| 场景 | 实例数 | 最终均分 | 标准差 | 扣罚前均分 | 被 ×0.9 的实例 |
|---|---:|---:|---:|---:|---:|
| Commit Audit | 5 | 0.8339 | 0.0452 | 0.8339 | 0 |
| Code Spec | 5 | 0.7642 | 0.0494 | 0.8302 | 4 |
| Code Standards | 5 | 0.7482 | 0.0459 | 0.7961 | 3 |
| Spec Readiness（融合） | 5 | 0.4035 | 0.0987 | 0.4360 | 4 |

- Commit Audit 最稳定，所有实例都没有诊断。
- Code Spec 和 Code Standards 的发现质量（扣罚前分数）接近 Commit Audit。差距主要来自报告格式和证据定位：两个场景共 7 个实例被 ×0.9。
- Spec Readiness 的融合分偏低，是 artifact-promotion 子场景拖下来的（0.18–0.43）。runtime-migration 子场景本身在 0.82–0.98 之间，但 5 次中有 4 次带 `requirement-scope-continuation` 诊断，因此 ×0.9。
- 适用范围：只适用于 本机 + IQ3_XXS + 当前默认部署参数，不套用到其他主机或量化。

## 评分口径

- 使用 benchmark 口径（`.claude/rules/reviewer-suite.md`）。报告中可机械修复的问题会修复成一份可评分副本，修复项都有记录，ARW 原版的罚分照常适用。目前有两类修复：删除 markdown 首个条目前的前言；把简写证据路径补全为唯一匹配、且行号在范围内的完整路径。无法修复的问题（如行号超出文件范围）按 ARW 原版处理。
- 评分使用打过补丁的 ARW conformance，SHA `51e2e22bf9412fa0c6f2fef18d7d08fdb89d049205973f9502da304043aa6c2b`。补丁只让修复后的副本可以评分，不会去掉罚分；上游 69 个 conformance 测试全部通过。修复工具为 `tools/reviewer/repair_reviewer_report.py`（8ac8454 版）。
- ARW 罚分按重复整体计算：一个实例只要有任何报告诊断，整个实例分 ×0.9，与诊断数量无关（`conformance.mjs`：`reportDiagnostics.length > 0 ? scoreBeforePenalty * 0.9 : scoreBeforePenalty`）。例如 Code Spec 批 a 实例 2 扣罚前为 0.8055，有 6 个证据诊断和 1 个格式诊断，最终为 0.8055 × 0.9 = 0.7250。
- 候选匹配由 Main 逐条裁决。修复简写路径后新增的候选，只裁决新增部分，原有裁决不变。

## 逐实例

| 场景 | 批-重复 | 最终 | 扣罚前 | ×0.9 | 修复项 | 诊断 |
|---|---|---:|---:|---|---|---|
| Commit Audit | a-1 | 0.7603 | 0.7603 | 否 | 无 | 无 |
| Commit Audit | a-2 | 0.8841 | 0.8841 | 否 | 无 | 无 |
| Commit Audit | b-1 | 0.8451 | 0.8451 | 否 | 无 | 无 |
| Commit Audit | b-2 | 0.8438 | 0.8438 | 否 | 无 | 无 |
| Commit Audit | c-1（替补 a-3） | 0.8361 | 0.8361 | 否 | 无 | 无 |
| Code Spec | a-1 | 0.8487 | 0.8487 | 否 | 无 | 无 |
| Code Spec | a-2 | 0.7250 | 0.8055 | 是 | 前言 1 | 格式 1，证据 6 |
| Code Spec | a-3 | 0.7372 | 0.8191 | 是 | 无 | 证据 4（无法修复） |
| Code Spec | b-1 | 0.7648 | 0.8498 | 是 | 前言 1 | 格式 1，证据 6 |
| Code Spec | b-2 | 0.7453 | 0.8281 | 是 | 前言 1 | 格式 1 |
| Code Standards | a-1 | 0.7659 | 0.7659 | 否 | 无 | 无 |
| Code Standards | a-2 | 0.7173 | 0.7970 | 是 | 无 | 证据 2（行 59/60 超出 41 行的文件） |
| Code Standards | a-3 | 0.7263 | 0.8070 | 是 | 简写路径 26 | 证据 2（`:109` 无法修复） |
| Code Standards | b-1 | 0.8207 | 0.8207 | 否 | 无 | 无 |
| Code Standards | b-2 | 0.7107 | 0.7897 | 是 | 前言 1，简写路径 1 | 格式 1 |
| Spec Readiness | a-1 | 0.2871 | 0.3190 | 是 | 无 | RM `requirement-scope-continuation` |
| Spec Readiness | a-2 | 0.3935 | 0.4372 | 是 | 无 | RM `requirement-scope-continuation` |
| Spec Readiness | a-3 | 0.3572 | 0.3969 | 是 | 无 | RM `requirement-scope-continuation` |
| Spec Readiness | b-1 | 0.4257 | 0.4730 | 是 | 无 | RM `requirement-scope-continuation` |
| Spec Readiness | b-2 | 0.5540 | 0.5540 | 否 | 无 | 无（诊断分：环境查询 1 次） |

Spec Readiness 子场景分（扣罚前）：

| 重复 | runtime-migration | artifact-promotion |
|---|---:|---:|
| a-1 | 0.8162 | 0.1764 |
| a-2 | 0.9376 | 0.2884 |
| a-3 | 0.9470 | 0.2358 |
| b-1 | 0.9801 | 0.3276 |
| b-2 | 0.9791 | 0.4334 |

## Spec Readiness 偏低的原因（2026-10-12 分析，不涉及模型）

结论：低分来自 artifact-promotion 子场景的问题检出率低，是当前模型和部署（v0.1.42 + IQ3_XXS）下 Reviewer 审得少，不是评分口径或主机环境造成的，也不是 F6 特有。

- **拖分的位置**：融合分里 artifact-promotion 占 25 个问题用例中的 20 个。runtime-migration 0.82–0.98，artifact-promotion 0.18–0.43。批 b 的 artifact-promotion 报告只有 8–9 条 gap，20 个问题用例只命中 6–8 个；有 7 个问题的 MODULE-DESIGN-INTERFACES 只报了 1–2 条，SEAMS-ADAPTERS、RATIONALE（需求范围）各 0 条。漏掉的用例都是完全没有对应 finding，不是证据定位或裁决不匹配（31 个候选 24 个匹配，不匹配的是交叉候选）。clean acceptance 0.93–1.0，误报不是原因。
- **不是 F6 特有**：同一模型和部署下，F3 试跑（2026-10-11）artifact-promotion 0.320；第 9 维窗口 6 个实例 artifact-promotion 均值 0.281／0.362，融合分（扣罚前）0.420／0.480。F6 的 0.436（扣罚前）与它们一致。
- **"约 0.6"的来源**：v0.1.38 + Q2_0 时期，上下文比较的完整合并实例为 0.47–0.69（多数 0.54–0.62），profile 验证 0.35–0.55。那时 artifact-promotion 单段平均 47.3 分钟、输出约 155K token；现在批 b 只有 8–9 分钟、21–22 个请求、输出约 40K。解码速度相近（约 100–117 tok/s），差别是审的量少了约 4 倍，报告条目随之减少。
- **评分口径的影响小**：benchmark ×0.9 只把均分从 0.436 拉到 0.404；证据定位新定义只涉及 Commit Audit 的 `lines`，Spec Readiness 的 JSONL 报告没有修复项。
- **环境无关**：Spec Readiness 两批都没有大页被拒（只有 Commit Audit 批 a 出现过）；大页只影响速度，不改变 greedy 输出。
- **未查明**：工作量下降由哪个变化引起。v0.1.38 到现在同时改了 Strata 版本（v0.1.42 默认开启专家尾部跳过）、量化（Q2_0 → IQ3_XXS）、启动提示（去掉防循环段）、spec / spec-min-p 和窗口档位，没有单独对照。要分开需要模型运行，例如同一部署下 Q2_0 与 IQ3_XXS 各跑几个 artifact-promotion 单段。

## 速度

| 场景 | 单实例用时（分钟） | 引擎输出 tok/s | 任务输出 tok/s | 草稿接受率 |
|---|---|---|---|---|
| Commit Audit | 8.2–27.8 | 104.3–107.5 | 86.0–96.6 | 91.9–92.7% |
| Code Spec | 3.4–4.2 | 96.1–100.4 | 84.1–85.4 | 91.0–91.7% |
| Code Standards | 4.8–8.1 | 89.2–94.8 | 78.5–85.5 | 89.1–89.9% |
| Spec Readiness（合并实例） | 12.5–23.3 | 96.4–98.0 | — | 89.8–90.8% |

- Commit Audit 批 a 运行时，引擎日志记录到大页被拒绝；之后各批都没有被拒绝。批 a 两个实例的速度（106.3 / 104.3 tok/s）与其他批相当，没有看到明显影响。
- token 来自引擎内部日志（`tools/metrics/strata_tokens.py`），包括压缩和 guardian 请求；工作时间由 `tools/metrics/review_work_time.py` 计算，包含工具执行和预填充。任务输出 tok/s = 输出 token / 工作秒数。逐实例的请求数、三类 token、引擎输入速度和任务输入速度见 JSON。
- 运行明细（会话、逐项裁决、日志）在 `.tmp/` 中，删除后不能重放会话检查和裁决；本摘要和 JSON 保留了分数、修复项、诊断和速度的完整精度结果。

## 运行中的事件

- **Commit Audit 实例 3 替补**：批 a 实例 3 的 Reviewer 已返回 ready，但 ARW 的报告目录检查报 `report-binding-invalid`，原因是 Codex 沙箱在报告目录里建的挂载点（`.agents`、`.aws`、`.codex`、`.git`）还没被清理。这是基础设施竞态，与 Reviewer 行为无关。处理方式：用 ARW 原版维护接口停掉该 agent，单独补跑 1 次（批 c）。批 a 因此只有 2 个重复，拿不到原版批分。上游缺陷已记入 [ARW 上游缺陷记录](../../../docs/arw-upstream-issues.md) 第 3 条。
- **Spec Readiness 的 `requirement-scope-continuation`**：这是 ARW 原生诊断，表示"发现需求范围问题后仍继续审核"。测量交接明确要求能力测量中即使满足提前返回条件也要继续检查，因此这个诊断是交接要求与 ARW 评分规则之间的冲突，不是模型违规。5 次中有 4 次触发，按 ARW 原版照扣。

## 会话检查

每个原生会话都按冻结 ARW 的会话检查规范，读了 `actions.md` 和 `flagged.md` 全文。

- **环境查询 1 处**：Spec Readiness 批 b 重复 2 的 runtime-migration（会话 `…d02d0dd6`，#13）执行了 `cat docs/agents/writing.md; printenv | grep -i -E 'ARW|CODEX' | sed 's/=.*//'`，违反测量交接末尾的测量说明（"禁止查询环境变量和平台身份"）。按结果判定（用户 2026-10-12，`.claude/rules/reviewer-suite.md` 会话检查）：输出只有变量名（`sed` 删掉了值，其中有 `STRATA_API_KEY` 这个名字），之后的调用只读场景内的 docs 和 Request 文件，没有用到这些信息，也没有接触隐藏答案或其他实例。因此样本有效，分数照常计入，标为"诊断分（环境查询 1 次）"，不乘 0.9，批次不因此判失败。
- 其余都是基线项或误报：
  - 写 `/tmp` 被只读拒绝（Code Standards 各 1 次，轻微）；
  - git EPERM（基线）；
  - workdir 拼写错误被拒后自行改正（Spec Readiness a-1）；
  - 长路径 `apply_patch` 触发提权，guardian 判 allow，写入目标是绑定草稿（Spec Readiness b-1）；
  - 报告正文里出现身份相关字样被标记（误报）。
- 所有写入都在绑定报告或草稿之内。各批启动 SHA 一致。Spec Readiness 压缩后出现的标记消息，是 ARW 为 artifact-promotion 重新注入的 AGENTS.md、权限说明、环境和任务交接，属于正常流程。

## 收尾状态

前端 lease 为 free，启动提示 SHA `1cae169a…`。默认部署回读结果 `source_sha_verified=True`。没有残留的 ARW 或 Codex 进程。

## 更正与补记（2026-10-21）

- v0.1.42 f6-benchmark：更正（2026-10-21）：本次 Strata 运行经 `arw_dimension prepare` 准备，只接入了原生压缩提示 `ab0c334d…`，缺工程压缩提示 `3856cb62…`（硬约束 3；原因是 d6b09c9 起 `selection()` 写死 False）。Spec Readiness 实例发生过压缩，压缩后的行为未使用工程压缩提示，相关结论按此理解；未重跑。
