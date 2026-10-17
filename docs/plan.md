# 后续计划

更新：2026-10-15。只放待办和需要重复执行的流程；已完成的经过见[历史工作](work-history.md)，测量通用约束见 `.claude/rules/`，参数任务只在[每机调参手册](host-tuning.md)维护。整个工程的现行决定见 [README](../README.md#现行决定)。

## 调参负载与诊断（用户 2026-10-12 已定）

- [ ] **v4 题库**：v3 试跑 70/75，9 格 100%、machine 档 3 为 0%（同组同机制，正确率两极化），不冻结。v4：新增三个思考型方向（自然语言多步约束推理、规格条文判读、从日志反推根因），可参考网上题库的出题方向，但不用相同或相似题目；现有 5 方向提高难度并复核题面；同组混入不同题型和难度，每组 10–15 题，组时限按组内各题档位动态求和；按题计分、按组估计误差（聚类）；Opus 校验后再申请试跑。用户 2026-10-12 批准 v4 Qwen 试跑（1 实例、72 题 6 组×12、组时限 720 秒、加载 1 次，诊断结束后开跑）。用户 2026-10-12：试跑组时限保持每档 30 秒；单实例上限仍为 10 分钟，是否可用以完整实例的实际测试为准，不按分组分步测试推断。v4 试跑（2026-10-12）68/72（94.4%，聚类 SE 0.041），4 个失分中 3 个是第 6 组超时，logic 题被程序穷举，各档正确率无差别；组末上下文最高 96.8K。
- [ ] **v5 题库**（2026-10-13 用户暂停题库构造，先推进 reviewer 场景重构；恢复时待定：超时怎么处理、作答正确率仍偏高、`choose` 规则修正）（用户 2026-10-12 决定）：拉开正确率靠加难题目本身（不收紧时限，组时限仍为每档 30 秒）——扩大规模使穷举不可行或代价极高，policy、incident 加入需要解读取舍的交叉条款、例外和优先级冲突（优先级在条文中写明，不留真歧义）；每组降到 10 题，单组上下文明显低于 100K。Opus 校验后再申请 Qwen 试跑。进展：v5 已实现并提交（4b2677a：80 题 = 8 方向 × 档 1/2/3 各 3/4/3，蛇形混组 8 × 10，每组 600 秒；set-draft SHA 024055d3…），Opus r5 两次 160/160、无歧义说明（e343d77）；用户 2026-10-13 批准 v5 Qwen 试跑（1 实例、80 题 8 组 × 10、每组 600 秒、加载 1 次；故障修复与受影响组重跑在授权内）。v5 试跑（2026-10-13 00:20–01:33）60/80（75%，聚类 SE 0.085，设计效应 3.05）：作答 64 题答对 60 题，16 个失分是超时未作答（4/8 组撞 600 秒时限），真正答错 4 题（machine 3、policy 1）；组末上下文最高 100.2K，未明显低于 100K；`choose` 因 Opus 80/80 在任何子集都满分而不通过，且把超时未答当作错题。

## Reviewer 场景重构（用户 2026-10-13）

场景流程、判据与停止条件见 `.claude/rules/reviewer-suite.md`「场景流程」。Spec Readiness 已到 v4.1 收尾（经过见[历史记录](work-history.md)「Spec Readiness 重构 v2→v4.1」，[报告](../reports/v0.1.42/spec-readiness-v4/summary.md)）。

- [ ] **Spec Readiness v4.2**（用户 2026-10-15）：在 v4.1 基础上补 A 类正例使正反等数（独立审查 2026-10-15 判定 v4.1 的 A 类为 2 正 4 反，两个 SEAMS 反例有明文规则可核对、归 B，故补 2 个正例成 4:4，最好放在 AP 独有的检查项）；其余用例不变。按场景流程走（设计 → 独立审计与盲答 → 冻结 → Opus 基准与 Q3 测量）。与 v4.1 已有结果不可比（输入变了，B 部分也只能近似对照）；v4.1 的 ×20 加测仍作为旧版基线与噪声估计保留。冻结后必做 Opus ×3（v4.1 不补 Opus，用户 2026-10-15 确认）；Q3 至少 ×10，报告给出比值 SE。额度重置（06:00）后开始。
- [ ] **Spec Readiness 基线重测**（用户 2026-10-14）：已完成场景的 Q3 评分以后作为基线，所以在当前版本 Strata v0.1.44.1 上重测 Spec Readiness v4.1 Q3 ×10（冻结夹具与 v4.1 键不变，Opus 沿用 medium ×3），利用 GPU 空闲与 Code Standards 设计并行；版本、默认上下文档、主机功耗档的差异列入混杂清单。Code Spec v5 已有 v0.1.44.1 上的 Q3 ×10，不需要重测。 优先级低于正式任务（用户 2026-10-14）：正式任务要用 GPU 时创建 `.tmp/gpu-priority/<任务名>`，重测发现后不中途打断，当前实例跑完再停模型、归还租约（防止重测每次都被打断、一次也跑不完），标志清空后再继续。 加测（用户 2026-10-15 01:4x，额度紧张时用 GPU 空闲）：目标定为有效 Q3 共 20 次（再加 10 次），开跑前定下、不按中途结果停；06:00 前只跑模型不做裁决，报告同时给出 10 次与 20 次结果。
- [ ] **评分规则检查与改进**（用户 2026-10-14；审计与 r7 已完成并提交，口径已写入 `.claude/rules/measurement.md` 与 `reviewer-suite.md`「评分」）：剩余待办——多词 `findingTerms` 连续短语匹配是否完成、必选组标为仅供裁决参考是否完成；Sonnet 盲裁试点（在 v5.1 已有池上与 Opus 裁决比一致率，效果好再逐步扩大）。只读分析时不改冻结件。
- [ ] **Commit Audit 场景**：先检查（规则冲突、场景与答案键含义、F6 中 Qwen 5 次都漏的用例），再出一次 Opus 盲答，之后按场景流程升级版本（用户 2026-10-13）。逐个场景进行，见 `.claude/rules/reviewer-suite.md`「场景流程」。按出题原则（一道题只出一次，用户 2026-10-16/17）：原版答案键 `COMMIT-AUDIT-GATE-1` 第 15 个正例与 `GATE-2` 第 3 个正例（从 1 起计）期望句和证据完全相同，只有 `findingTerms` 不同，同一缺陷出了两遍；同时在冻结工具加"同一答案键内期望句或证据相同就报错"的通用检查（2026-10-17 v4.3 独立审查发现）。
  - [ ] v2 草稿修订号 22（用户 2026-10-17：恢复 issue 与 spec 的重复、声明为合并用例，评分 r8.2，测量说明加一句；修订号 22 把 01:49/spec:27、02:47/spec:16 统一证据后合并，评分 r8.3）：实现已完成（[变更说明](../benchmarks/reviewer-suite-v1/commit-audit-v2.md)）；待下一轮 Opus 审计（29 对合并是否同一道题、未合并的 01:52/spec:13、删除的 11 行、连续同结果约束、期望句与裁决口径行号）、新夹具上的 Opus 盲答（用 `measurement_note_path` 指向 Commit Audit 说明，`arw_dimension` 已强制）和独立审查，之后冻结。

## 多模型 benchmark（用户 2026-10-17）

四个 reviewer 场景（Code Spec、Code Standards、Spec Readiness、Commit Audit）全部定稿后开始。参与者：OpenAI 的几个模型、Anthropic 的几个模型、Strata（IQ3_XXS）、DeepSeek 等；每个场景每个模型跑 5 次取平均；得分处同时给耗时、token、工具调用数。

- [ ] **方案设计**（开跑前，按 AGENTS.md 硬约束 1 处理测量设计部分）：
  - 模型清单与推理强度，由用户定。
  - 统一 harness：现有 Q3 测量走 Codex + ARW，Opus 盲答走 Claude Code 无头运行。跨模型比较应使用同一 harness，或者把 harness 列为一个维度；还要核实 Codex 接入 Anthropic、DeepSeek 的可行路径。
  - 凭据：OpenAI、DeepSeek 的 key 由用户配置，agent 不经手。
  - 费用：OpenAI、DeepSeek 按各自账户计费，需用户给出预算；Anthropic 运行和每次的语义裁决占周额度，开跑前按 `estimate.sh` 分批。
  - 规模：模型数 × 4 × 5 次。裁决成本随运行次数线性增长，先评估能否用机械关联加抽样复核来减少 Opus 裁决。
  - 安全验收：每个新 provider 先通过测量规则「正式测量前的安全验收」。
- [ ] **执行与报告**：按场景分批运行。报告给出每个模型的均值 ± 标准差、耗时、token、工具调用数，以及每次的费用。

## 采样与窗口重新测量（用户 2026-10-12）

采样和窗口两个影响输出的维度，原结论（greedy、156584）在 ARW 上分不出高下，暂时维持现值；需另行设计答案可机械判定、低波动的专用负载，按「评分口径」的分阶段判定重新测量（负载设计属测量设计，按 AGENTS.md 硬约束 1 处理）。
- [ ] 采样负载设计（同时测循环率）。模型卡（huggingface.co/Qwen/Qwen3.8-Flash-Next，2026-10-12 查）：思考模式推荐 temperature 1.0、top_p 0.95、top_k 20、min_p 0、presence_penalty 0；agent 编程评测用 temp 1.0、top_p 0.95；未提 greedy；重复时可调 presence_penalty 0–2。原生上下文 262,144。
- [ ] 试跑结束后：调参驱动实现加载后预热、分数类参数同条件连跑、速度类参数按块交替（AA BB BB AA）与运行顺序趋势检查、各实例 reused 比例核对（规则见 measurement.md「预热与连跑」，bcceb93）。
- [ ] 窗口负载设计（跨压缩阈值的长上下文任务，压缩前后事实保持可机械判定）。

## 顺序

rtx3080ti 是唯一可用主机，先推进属于它的工作；rtx4070tis 恢复后再决定它的工作。

3. [ ] **防循环弃用部署**：代码、手册和测试已改（2026-10-11），随 v0.1.42 升级一起部署到 rtx3080ti；rtx4070tis 待同步。
6. [ ] **rtx4070tis 恢复后**：核对实际文件、版本、服务和持有状态；补同步离线期间的部署（rtx3080ti 当前的 Strata 版本、前端、新默认值；它仍为 v0.1.40.2）；再按[ARW 同步与 Spec 恢复](#arw-同步与-spec-恢复)和调参手册的本机待办安排。思考上限沿用 8192/24576，不采用方案 A（用户 2026-10-12 回滚）；guardian 用思考 512 / 总输出 1024。

## IQ3_XXS 遗留事项

  - [ ] ARW 运行环境两项（第 8 维会话检查发现，2026-10-11）：中途消息 `send_message` 被沙箱拒绝；Reviewer 用 `env | grep` 触发"环境身份"违规。结论与用户决定（场景缺陷，测量交接末尾追加说明；上游缺陷记入 [ARW 上游缺陷记录](arw-upstream-issues.md)）见[历史工作](work-history.md)「plan 清理迁入：已完成项与决定性文字」。待做：确认交接追加说明已落实。
  - [ ] **IQ3_XXS 补测调参**（用户 2026-10-11 批准申请一）：按序 0 `STRATA_ADAPT_LAG` 不设置/2（直接完整测）→ 1 `--adapt-swaps` 96/160/48 → 2 `--adapt-every` 4/2/8 → 3 `--adapt-decay` 0.7/0.5/0.9 → 4 `--kv-resident` 20480/32768/12288（0–4 用 32K 资源负载，各 3 次）→ 5 `--spec` 3/4/5/6 → 6 CPU 辅助显式 auto/不设置 → 7 学习型专家档案（用户 2026-10-11 取消：v0.1.37/38 已训练过，没有稳定收益，直接用默认发布档案）（5–6 用 Commit Audit，等修复 F1/F2）→ 8 采样参数 → 9 窗口（用户：窗口和采样必须在 IQ3_XXS 上实测才能纳入默认值，放在最后，先采样后窗口；推理强度保持 high）。每维 Main 与独立复核一致才采用。第 5、6 维按 `tools/tuning/arw_dimension.py` 每个实例部署条件并冷启动（用户 2026-10-11 确认，授权 `deploy --condition` 可多次）。进度：第 0 维完成，2 更快（约 +3–6%），双方一致采用并部署（[报告](../reports/v0.1.42/iq3_xxs-tuning/adapt-lag/summary.md)）；第 1 维完成，160 优势在噪声内（约 +1.4%）、48 偏差，双方一致保持 96（[报告](../reports/v0.1.42/iq3_xxs-tuning/adapt-swaps/summary.md)）；第 2 维完成，三者无可分辨差异（±1.5% 内），双方一致保持 4（[报告](../reports/v0.1.42/iq3_xxs-tuning/adapt-every/summary.md)）；第 3 维完成，0.9 与 0.7 持平、0.5 劣势来自单个离群实例，双方一致保持 0.7（[报告](../reports/v0.1.42/iq3_xxs-tuning/adapt-decay/summary.md)）；第 4 维完成，32768 在短负载上无收益、12288 被引擎抬到 20480 无效，双方一致保持 20480；长上下文 20480/32768 补测待另行申请，测 64K/100K/150K 三个长度（用户 2026-10-11）；对外上下文档位定为阈值 100K/150K/200K、窗口 156584/206584/256584 三档（第一档为默认），用户 2026-10-11 决定先在 IQ3_XXS 上实测再发布 206584/256584 两档（[报告](../reports/v0.1.42/iq3_xxs-tuning/kv-resident/summary.md)）；rtx4070tis 待同步；第 5 维完成，采用 spec 4 并部署（旧口径曾选 spec 3 并部署，2026-10-11 评分口径改为低频格式失误不计分后重算：spec 5 差最高分 0.081 出局，3/4/6 在 0.08 内按引擎输出 tok/s 选 4；Main 与复核一致，用户确认；证据弱），[报告](../reports/v0.1.42/iq3_xxs-tuning/spec/summary.md)。第 6 维完成，显式 auto 与不设置实质等价，双方一致维持 auto（[报告](../reports/v0.1.42/iq3_xxs-tuning/cpu-prefill-share-unset/summary.md)）。第 8 维（采样）完成，greedy 最快、分差在 0.08 内，双方一致维持 0/1/20（[报告](../reports/v0.1.42/iq3_xxs-tuning/sampling/summary.md)）。
  - [ ] **benchmark 场景修复**（用户 2026-10-11 批准申请二）：F1 测量交接追加说明（冻结文本文件，记 SHA）；F2 能力验证和 benchmark 中关闭本工程接续机制，改用 ARW 原版接续与 10/5 次暂停（最大限度还原 ARW，便于与 ARW 自己的结果直接对比）；（进展：F1 已完成；F2 按用户决定改为给 ARW 打本工程接口补丁、由 ARW 持有独占并启动模型，实例间不停模型，补丁、驱动和单元测试已完成，待 F3 实跑验证；F3 合并实例改由 `arw_measure` 在 ARW 持有模型模式下运行：同一重复先 runtime-migration、再在同一线程接续 artifact-promotion，第一份报告接续前核对 SHA，第一阶段未完成则跳过并记录缺口，不再停等 Main 中途决定；本机准备和预检已通过（前端 `/health` 改动已部署）；F3 首次试跑失败（ARW 请求 403）：本工程运行层传入 `nativeSessions` 时 ARW 宿主不创建模型目录，管理器读不到 provider，provider 也只写进了 `native-model-catalog.json` 而非 ARW 读取的 `models.custom.json`；2026-10-11 已修复（运行层与 App Server 共用一个 ARW 目录、provider 写入 codex-home 的 `models.custom.json`，daemon 就绪时回报 ARW 实际读到的 provider，驱动核对后才派发），同时 ARW 补丁改为只传模型和安装目录发布的上下文档位（provider `contextWindow`，默认第一档），窗口和压缩阈值都取自该档位，selection 不再带 `auto_compact_token_limit`；ARW 持有模型模式下每个实例从派发到分段关闭采集主机遥测；ARW 合并后的压缩提示 = 安装目录基础提示（与工程源同 SHA）+ Codex 原生快照 0.160.1，该快照文本完整出现在 0.162.0 二进制中（静态比对，实际压缩路径待试跑确认））F3 第二次试跑（2026-10-11）：ARW 成功领 key、启动模型，runtime-migration 首回合完成（758 秒，报告 ready）；接续 artifact-promotion 时触发 ARW 缺陷（见 `docs/arw-upstream-issues.md` D：原线程卸载后 followup 用新交接的文件系统检查原报告，判"缺失"并连续接续 10 次），驱动收到 `reviewer-busy` 退出，实例无效；已用 ARW 原版中断结束任务、维护接口关闭守护进程归还 key，并停模型；修复需改 ARW 运行层，待用户决定；F3 Spec Readiness 本机无模型准备与回归，再试跑 1 个合并实例；F4 单场景评分工具；F5 已有 Code Spec/Code Standards 两个实例不并入，全部重跑；F6 四场景各 5 次（另行开跑）。
  - [ ] 有余时间时：ARW 完整四场景 benchmark，只用 IQ3_XXS / high，其他参数用调参后的默认值，每场景 5 次取平均（用户 2026-10-11 授权，排在 IQ3_XXS 调参和高优先级任务之后）。

## 前端

设计已获批准，实现见 `src/frontend.py`、`src/model_process.py`，结构见[前端运行与维护](frontend.md)。

- [ ] **Codex 与 Claude Code 参数一致**（用户 2026-10-12 批准）：审批统一 512/1024；参数层面一致、机制差异写入手册。Codex guardian 与 `qwen-approve` 都是 low、思考 512、总输出 1024、不发采样；`qwen-agent` 给 Claude Code 传同一强度（`CLAUDE_CODE_EFFORT_LEVEL`）、同一总输出、100000 压缩阈值（`CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE`，假服务器核对）。Claude Code 不能替换内置压缩提示，作为特例写入手册。已在分支 `agent-parity` 提交，待 Spec 调查结束后合并并部署到 rtx3080ti（rtx4070tis 恢复后同步）。

## ARW 同步与 Spec 恢复

这部分属于 rtx4070tis，等它恢复。规则见 `.claude/rules/reviewer-suite.md`。ARW 已同步到 760007c，[同步核查](../benchmarks/reviewer-suite-v1/source-sync.json)：554 文件逐项核对，112 份业务 fixture 字节不变；只完成无模型验证。

- [ ] 在新来源完成原版准备和受影响的无模型回归：报告独立目录可写，输入、请求、规则和恢复记录在目录外。
- [ ] 核对最终交付由运行层验证 completion，不再额外要求最终 send_message；更新受影响的驱动和来源绑定。
- [ ] 补安全验收（`.claude/rules/reviewer-suite.md`「正式测量前的安全验收」）中受影响的部分：一个 Q2_0 实例、三个原生沙箱 / 报告写入 / 同线程接续流程、15 个审批用例（约 21 次 guardian 判断），预计 30–60 分钟。
- [ ] 完成旧 Spec runtime-migration 报告和原生会话的 Main 检查；旧 0.1.40.1 首阶段不与 0.1.40.2 第二阶段拼接。

## 升级后 Spec Readiness 配置比较

该计划（rtx4070tis 上固定 Q2_0 的合并实例四组合）已失效：合并实例已停用（`.claude/rules/reviewer-suite.md`），IQ3_XXS 已是默认量化，窗口默认已改为 206584／150000。rtx4070tis 恢复后重新制定；旧计划文件 [spec-readiness-local-plan.json](../benchmarks/reviewer-suite-v1/spec-readiness-local-plan.json) 仅作历史。

## 上下文配置的测量与选择

（rtx4070tis 恢复后重定；IQ3_XXS 默认已改为 150K／206584，维护基线仍为 100K／156584。）上下文维度用合并实例（同线程先 runtime-migration 再 artifact-promotion），各子场景各有 55/60 分钟初审预算，按合并实例统计。容量公式见[容量计算](compaction-options.md#上下文容量计算)：64K/100K/150K/200K 对应 120584/156584/206584/256584。维护默认 100K / 156584。报告统一写入 `reports/v0.1.38/context-comparison/` 的 `summary.md` 和 `summary.json`；已完成结果见[历史工作](work-history.md#已完成上下文配置测量)，排序由用户决定。

## 周期流程

- **每日 Strata 更新检查**：流程与排程方式见 `/strata-upgrade` skill「每日检查」；状态页待办里常驻一项，优先级最高。
- **主机稳定性观察**（用户 2026-10-13）：平时只靠 Windows 事件日志和资源采样收集数据；每天一次或每次重启后检查一次 WHEA-Logger（可纠正内存／机器检查错误；开机时信息级 ID 3 记录不算）与意外重启（Kernel-Power 41），不在定时检查里频繁查，不跑内存压力测试。内存 XMP 6600 与 CPU 功耗档 Intel Default Settings 的现状见[历史工作](work-history.md#主机稳定性与-bios用户-2026-10-13-决定)。

## 其他未解决问题

| 问题 | 现状 | 后续 |
|---|---|---|
| 长上下文可靠性 | 历史受控压缩保住了所选事实，但出现重复工具和错误摘要污染 | 执行[验证方案](compaction-options.md#长上下文可靠性验证方案待执行) |
| token 与请求归属 | 内部计数和 API 记录缺少共同请求 ID | 新测量从首次请求前归档 HTTP 日志；缺失记未知 |
| 重复工具导致停滞 | 调用手册保留[已观察的异常](installation-directory-readme.md#已观察到的执行异常) | 防循环功能已弃用；观察中，出现明显重复时交用户决定 |
| 业务适用性 | 结果来自本工程受控负载 | 由具体工程自行验证，不推广为通用保证 |
| 256584 档 200K 检索错误归因 | rtx3080ti IQ3_XXS 200K 下 6 实例同一记录检索错误，全部为 `--kv int8`（[报告](../reports/v0.1.42/iq3_xxs-tuning/kv-resident-long/summary.md)） | 用户 2026-10-12：记录，优先级很低。先无模型估算非 int8 KV 在 200K 的显存可行性，再做对照；答对则考虑档位绑定更高精度 KV，仍错则 IQ3_XXS 止于 206584 |
| Haiku 订阅额度扣减是否与 API 价同比例 | `estimate.sh` 的 K 按 Opus／Sonnet 回溯校准，Haiku 只核对了 API 价（1:0.7:0.05），订阅额度未核对 | 下次跑 Haiku 时记录运行前后 `budget.sh` 的用量变化，差超过约 30% 就改用实测值并更新 `estimate.sh` |
