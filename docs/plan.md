# 后续计划

更新：2026-10-19。只放待办和需要重复执行的流程；已完成的经过见[历史工作](work-history.md)，测量通用约束见 `.claude/rules/`，参数任务只在[每机调参手册](host-tuning.md)维护。整个工程的现行决定见 [README](../README.md#现行决定)。

## 待办顺序

这里是真正的工作队列，按优先级排列，做完一项接下一项。状态页 queue 只显示排在最前的 5 项，每日检查（三项合为一项，见「周期流程」）单独显示，不占这 5 个位置。顺序有变化时，先改这里，再用 `status.py order` 同步状态页。

1. ~~Commit Audit v3 定稿~~：2026-10-18 定版完成，见 work-history。
2. ~~修正 catalog 上下文窗口~~：2026-10-19 部署到 rtx3080ti，见 work-history。
3. ~~核对写死在代码里的上下文和压缩阈值~~：同上。
4. ~~统一 Codex 与 Claude Code 的上下文档位~~：同上。
5. ~~修好安全门并在 v0.1.45 上重跑~~：2026-10-19 在 WSL 3.0.3、目录授权下通过；单模型对外与隔离修复部署后两次重跑都通过，现行证据 [safety-gate-env-fix](../reports/v0.1.45/safety-gate-env-fix/summary.md)。
6. ~~评分规则遗留~~：两项核实已完成（r7 已实现，69969fa 补测试）；Sonnet 盲裁试点通过（[报告](../reports/v0.1.45/sonnet-adjudication-pilot/summary.md)），但用户 2026-10-19 决定 benchmark 仍用 Opus 裁决（质量优先）。本项完成。
7. **多模型 benchmark 方案设计**：用户决定已齐，代码适配完成，[运行计划](../benchmarks/multi-model-v1/plan.md)已定稿、待冻结；三份盲裁 brief 已冻结（2026-10-19）。见「多模型 benchmark」。
8. **多模型 benchmark 执行与报告**：同上。
9. **采样与窗口重新测量**：负载设计，见同名一节。
10. **v5 题库**：用户 2026-10-13 暂停，何时恢复由用户定。

等外部条件、不参与排序：rtx4070tis 恢复后的各项，包括「顺序」第 6 条、「ARW 同步与 Spec 恢复」「升级后 Spec Readiness 配置比较」「上下文配置的测量与选择」。

待核实是否仍然有效（「IQ3_XXS 遗留事项」）：
- 补测调参只剩第 9 维（窗口），已并入第 8 项；
- 场景修复 F2–F6 针对的是已停用的合并实例；
- "ARW 完整四场景 benchmark"已被多模型 benchmark 取代；
- 「顺序」第 3 条在 rtx3080ti 上随 v0.1.42 已部署，只剩 rtx4070tis。

## 调参负载与诊断（用户 2026-10-12 已定）

- [ ] **v4 题库**：v3 试跑 70/75，9 格 100%、machine 档 3 为 0%（同组同机制，正确率两极化），不冻结。v4：新增三个思考型方向（自然语言多步约束推理、规格条文判读、从日志反推根因），可参考网上题库的出题方向，但不用相同或相似题目；现有 5 方向提高难度并复核题面；同组混入不同题型和难度，每组 10–15 题，组时限按组内各题档位动态求和；按题计分、按组估计误差（聚类）；Opus 校验后再申请试跑。用户 2026-10-12 批准 v4 Qwen 试跑（1 实例、72 题 6 组×12、组时限 720 秒、加载 1 次，诊断结束后开跑）。用户 2026-10-12：试跑组时限保持每档 30 秒；单实例上限仍为 10 分钟，是否可用以完整实例的实际测试为准，不按分组分步测试推断。v4 试跑（2026-10-12）68/72（94.4%，聚类 SE 0.041），4 个失分中 3 个是第 6 组超时，logic 题被程序穷举，各档正确率无差别；组末上下文最高 96.8K。
- [ ] **v5 题库**（2026-10-13 用户暂停题库构造，先推进 reviewer 场景重构；恢复时待定：超时怎么处理、作答正确率仍偏高、`choose` 规则修正）（用户 2026-10-12 决定）：拉开正确率靠加难题目本身（不收紧时限，组时限仍为每档 30 秒）——扩大规模使穷举不可行或代价极高，policy、incident 加入需要解读取舍的交叉条款、例外和优先级冲突（优先级在条文中写明，不留真歧义）；每组降到 10 题，单组上下文明显低于 100K。Opus 校验后再申请 Qwen 试跑。进展：v5 已实现并提交（4b2677a：80 题 = 8 方向 × 档 1/2/3 各 3/4/3，蛇形混组 8 × 10，每组 600 秒；set-draft SHA 024055d3…），Opus r5 两次 160/160、无歧义说明（e343d77）；用户 2026-10-13 批准 v5 Qwen 试跑（1 实例、80 题 8 组 × 10、每组 600 秒、加载 1 次；故障修复与受影响组重跑在授权内）。v5 试跑（2026-10-13 00:20–01:33）60/80（75%，聚类 SE 0.085，设计效应 3.05）：作答 64 题答对 60 题，16 个失分是超时未作答（4/8 组撞 600 秒时限），真正答错 4 题（machine 3、policy 1）；组末上下文最高 100.2K，未明显低于 100K；`choose` 因 Opus 80/80 在任何子集都满分而不通过，且把超时未答当作错题。

## Reviewer 场景重构（用户 2026-10-13）

场景流程、判据与停止条件见 `.claude/rules/reviewer-suite.md`「场景流程」。Spec Readiness 已到 v4.1 收尾（经过见[历史记录](work-history.md)「Spec Readiness 重构 v2→v4.1」，[报告](../reports/v0.1.42/spec-readiness-v4/summary.md)）。

- [x] **评分规则检查与改进**（2026-10-19 完成，同待办第 6 项；用户 2026-10-14；审计与 r7 已完成并提交，口径已写入 `.claude/rules/measurement.md` 与 `reviewer-suite.md`「评分」）：剩余待办——多词 `findingTerms` 连续短语匹配是否完成、必选组标为仅供裁决参考是否完成；Sonnet 盲裁试点（在 v5.1 已有池上与 Opus 裁决比一致率，效果好再逐步扩大）。只读分析时不改冻结件。
- [x] **Commit Audit 场景**：v2 已完成（修订号 23，Q3 ×10 比值 0.880，[报告](../reports/v0.1.44.1/commit-audit-v2/summary.md)），加难版 v3（修订号 24）2026-10-18 冻结并定版（[报告](../reports/v0.1.45/commit-audit-v3/summary.md)）。按场景流程推进（`.claude/rules/reviewer-suite.md`「场景流程」）。

## benchmark 前置工作（用户 2026-10-18）

多模型 benchmark 开跑前必须完成。每项都已核对过会影响 benchmark 的结果、费用或可比性（2026-10-18 排查）。

- [x] **评分规则遗留**（2026-10-19 完成，同待办第 6 项）：先核实两项是否已完成——多词 `findingTerms` 是否按连续短语匹配，必选组是否标为仅供裁决参考；没有完成就补上并重算受影响的场景。再做 Sonnet 盲裁试点（在已有裁决池上与 Opus 裁决比一致率）。benchmark 的裁决量是模型数 × 4 场景 × 5 次，裁决模型决定费用，所以试点结果要在方案设计前出来。

以下遗留经核对不挡 benchmark，记入方案的混杂清单：
- IQ3_XXS 参数来自 v0.1.42 调参，不另行在 v0.1.45 上重测：benchmark 本身就在当前版本上跑，数据随之得到（用户 2026-10-18）；
- 已完成场景的 Q3 基线在 v0.1.44.1 上，benchmark 会在当前版本上重跑全部场景；
- Haiku 订阅额度扣减比例未核对：第一次跑 Haiku 时记录 `budget.sh` 前后用量，并修正 `estimate.sh`（见「其他未解决问题」）；
- r8 尺度下的 SD 阈值只用于调参，与 benchmark 无关。

## 多模型 benchmark（用户 2026-10-17）

四个 reviewer 场景（Code Spec、Code Standards、Spec Readiness、Commit Audit）全部定稿，且「benchmark 前置工作」全部完成后开始。参与者：OpenAI 的几个模型、Anthropic 的几个模型、Strata（IQ3_XXS）、DeepSeek 等；每个场景每个模型跑 5 次取平均；得分处同时给耗时、token、工具调用数。

- [ ] **方案设计**（开跑前，按 AGENTS.md 硬约束 1 处理测量设计部分）：用户决定已齐（2026-10-19 三轮答复），定稿见[运行计划](../benchmarks/multi-model-v1/plan.md)：27 个配置 × 4 场景 × 5 次，基础提示只给 Strata，搜索全部关闭，OpenAI 用 ChatGPT 套餐登录，DeepSeek 用 `DEEPSEEK_API_KEY`（用户 10-19 设在 `~/.profile`）。代码适配已完成（ChatGPT 登录链接、relay 记录实际 service tier、两个 harness 关闭搜索、Claude Code 的 DeepSeek backend）。盲裁维持单名 Opus（用户 2026-10-19）。阶段 0 进展（2026-10-19）：三份盲裁 brief 已冻结；G7 deny-read 已实施；benchmark 专用 Codex 与 Claude Code 副本已装、compact probe 通过；API 臂压缩提示无残留已核实；G8 Strata live 冒烟通过；汇总层已实现。剩余：冻结 API catalog、汇总适配层、冻结计划（状态见运行计划 §9）。
- [ ] **执行与报告**：按场景分批运行。报告给出每个模型的均值 ± 标准差、耗时、token、工具调用数，以及每次的费用。
- [ ] **benchmark 结束后：Claude Code 路径的提醒改用高优先级消息**（用户 2026-10-20）：ARW 提醒在 Codex 上是高优先级消息，会立即打断当前生成，确保模型在超时之前收到；Claude Code 路径现在经 PostToolUse hook，要等工具调用结束才送达。先查 Claude Code 无头模式能否中途打断并插入消息（如 stream-json 输入的 interrupt 加新的 user 消息，未核实），再实现并做对照；同时检查 relay 和各臂判定，别把这类主动打断记成故障。
- [ ] **下一版：输出上限重试改进**（用户 2026-10-22）：`src/output_limit.py` 现在只重试 1 次，重试只追加一条通知。strata-codex CStd low-a9 两次都在写同一个 exec_command 时撞 8192，推理 token 都是 2065（输入只多了通知的 95 token），说明通知没有改变模型的做法，多重试几次也不会有效。候选做法：重试时降低 `max_output_tokens`，或者把通知放到更显眼的位置，或者两者结合。改动属于部署设计，先过独立审查，再用撞上限的 mock 和实例对照验证；不追溯本次 benchmark。

## 采样与窗口重新测量（用户 2026-10-12）

采样和窗口两个影响输出的维度，原结论（greedy、156584）在 ARW 上分不出高下，暂时维持现值；需另行设计答案可机械判定、低波动的专用负载，按「评分口径」的分阶段判定重新测量（负载设计属测量设计，按 AGENTS.md 硬约束 1 处理）。
- [ ] 采样负载设计（同时测循环率）。模型卡（huggingface.co/Qwen/Qwen3.8-Flash-Next，2026-10-12 查）：思考模式推荐 temperature 1.0、top_p 0.95、top_k 20、min_p 0、presence_penalty 0；agent 编程评测用 temp 1.0、top_p 0.95；未提 greedy；重复时可调 presence_penalty 0–2。原生上下文 262,144。
- [ ] 试跑结束后：调参驱动实现加载后预热、分数类参数同条件连跑、速度类参数按块交替（AA BB BB AA）与运行顺序趋势检查、各实例 reused 比例核对（规则见 measurement.md「预热与连跑」，bcceb93）。
- [ ] 窗口负载设计（跨压缩阈值的长上下文任务，压缩前后事实保持可机械判定）。

## 顺序

rtx3080ti 是唯一可用主机，先推进属于它的工作；rtx4070tis 恢复后再决定它的工作。

3. [ ] **防循环弃用部署**：代码、手册和测试已改（2026-10-11），随 v0.1.42 升级一起部署到 rtx3080ti；rtx4070tis 待同步。
6. [ ] **rtx4070tis 恢复后**：核对实际文件、版本、服务和持有状态；补同步离线期间的部署（`config/deployments/rtx4070tis.json` 的 `models` 暂定 `["IQ3_XXS"]` 是占位（每台机器只对外一个模型，用户 2026-10-19）：先核对该机实际装有哪些权重、确认对外模型，再补该模型的 `context_tiers`，否则渲染 catalog 会失败停下；部署会备份并删除安装目录里不对外量化的 prebuilt 和已退役的 `config/maintenance-baseline.json`；rtx3080ti 当前的 Strata 版本、前端、新默认值；它仍为 v0.1.40.2）；再按[ARW 同步与 Spec 恢复](#arw-同步与-spec-恢复)和调参手册的本机待办安排。思考上限沿用 8192/24576，不采用方案 A（用户 2026-10-12 回滚）；guardian 用思考 512 / 总输出 1024。

## IQ3_XXS 遗留事项

  - [ ] **IQ3_XXS 补测调参**（用户 2026-10-11 批准申请一）：按序 0 `STRATA_ADAPT_LAG` 不设置/2（直接完整测）→ 1 `--adapt-swaps` 96/160/48 → 2 `--adapt-every` 4/2/8 → 3 `--adapt-decay` 0.7/0.5/0.9 → 4 `--kv-resident` 20480/32768/12288（0–4 用 32K 资源负载，各 3 次）→ 5 `--spec` 3/4/5/6 → 6 CPU 辅助显式 auto/不设置 → 7 学习型专家档案（用户 2026-10-11 取消：v0.1.37/38 已训练过，没有稳定收益，直接用默认发布档案）（5–6 用 Commit Audit，等修复 F1/F2）→ 8 采样参数 → 9 窗口（用户：窗口和采样必须在 IQ3_XXS 上实测才能纳入默认值，放在最后，先采样后窗口；推理强度保持 high）。每维 Main 与独立复核一致才采用。第 5、6 维按 `tools/tuning/arw_dimension.py` 每个实例部署条件并冷启动（用户 2026-10-11 确认，授权 `deploy --condition` 可多次）。进度：第 0 维完成，2 更快（约 +3–6%），双方一致采用并部署（[报告](../reports/v0.1.42/iq3_xxs-tuning/adapt-lag/summary.md)）；第 1 维完成，160 优势在噪声内（约 +1.4%）、48 偏差，双方一致保持 96（[报告](../reports/v0.1.42/iq3_xxs-tuning/adapt-swaps/summary.md)）；第 2 维完成，三者无可分辨差异（±1.5% 内），双方一致保持 4（[报告](../reports/v0.1.42/iq3_xxs-tuning/adapt-every/summary.md)）；第 3 维完成，0.9 与 0.7 持平、0.5 劣势来自单个离群实例，双方一致保持 0.7（[报告](../reports/v0.1.42/iq3_xxs-tuning/adapt-decay/summary.md)）；第 4 维完成，32768 在短负载上无收益、12288 被引擎抬到 20480 无效，双方一致保持 20480；长上下文 20480/32768 补测待另行申请，测 64K/100K/150K 三个长度（用户 2026-10-11）；对外上下文档位定为阈值 100K/150K/200K、窗口 156584/206584/256584 三档（第一档为默认），用户 2026-10-11 决定先在 IQ3_XXS 上实测再发布 206584/256584 两档（[报告](../reports/v0.1.42/iq3_xxs-tuning/kv-resident/summary.md)）；rtx4070tis 待同步；第 5 维完成，采用 spec 4 并部署（旧口径曾选 spec 3 并部署，2026-10-11 评分口径改为低频格式失误不计分后重算：spec 5 差最高分 0.081 出局，3/4/6 在 0.08 内按引擎输出 tok/s 选 4；Main 与复核一致，用户确认；证据弱），[报告](../reports/v0.1.42/iq3_xxs-tuning/spec/summary.md)。第 6 维完成，显式 auto 与不设置实质等价，双方一致维持 auto（[报告](../reports/v0.1.42/iq3_xxs-tuning/cpu-prefill-share-unset/summary.md)）。第 8 维（采样）完成，greedy 最快、分差在 0.08 内，双方一致维持 0/1/20（[报告](../reports/v0.1.42/iq3_xxs-tuning/sampling/summary.md)）。
  - [ ] **benchmark 场景修复**（用户 2026-10-11 批准申请二）：F1 测量交接追加说明（冻结文本文件，记 SHA）；F2 能力验证和 benchmark 中关闭本工程接续机制，改用 ARW 原版接续与 10/5 次暂停（最大限度还原 ARW，便于与 ARW 自己的结果直接对比）；（进展：F1 已完成；F2 按用户决定改为给 ARW 打本工程接口补丁、由 ARW 持有独占并启动模型，实例间不停模型，补丁、驱动和单元测试已完成，待 F3 实跑验证；F3 合并实例改由 `arw_measure` 在 ARW 持有模型模式下运行：同一重复先 runtime-migration、再在同一线程接续 artifact-promotion，第一份报告接续前核对 SHA，第一阶段未完成则跳过并记录缺口，不再停等 Main 中途决定；本机准备和预检已通过（前端 `/health` 改动已部署）；F3 首次试跑失败（ARW 请求 403）：本工程运行层传入 `nativeSessions` 时 ARW 宿主不创建模型目录，管理器读不到 provider，provider 也只写进了 `native-model-catalog.json` 而非 ARW 读取的 `models.custom.json`；2026-10-11 已修复（运行层与 App Server 共用一个 ARW 目录、provider 写入 codex-home 的 `models.custom.json`，daemon 就绪时回报 ARW 实际读到的 provider，驱动核对后才派发），同时 ARW 补丁改为只传模型和安装目录发布的上下文档位（provider `contextWindow`，默认第一档），窗口和压缩阈值都取自该档位，selection 不再带 `auto_compact_token_limit`；ARW 持有模型模式下每个实例从派发到分段关闭采集主机遥测；ARW 合并后的压缩提示 = 安装目录基础提示（与工程源同 SHA）+ Codex 原生快照 0.160.1，该快照文本完整出现在 0.162.0 二进制中（静态比对，实际压缩路径待试跑确认））F3 第二次试跑（2026-10-11）：ARW 成功领 key、启动模型，runtime-migration 首回合完成（758 秒，报告 ready）；接续 artifact-promotion 时触发 ARW 缺陷（见 `docs/arw-upstream-issues.md` D：原线程卸载后 followup 用新交接的文件系统检查原报告，判"缺失"并连续接续 10 次），驱动收到 `reviewer-busy` 退出，实例无效；已用 ARW 原版中断结束任务、维护接口关闭守护进程归还 key，并停模型；修复需改 ARW 运行层，待用户决定；F3 Spec Readiness 本机无模型准备与回归，再试跑 1 个合并实例；F4 单场景评分工具；F5 已有 Code Spec/Code Standards 两个实例不并入，全部重跑；F6 四场景各 5 次（另行开跑）。
  - [ ] 有余时间时：ARW 完整四场景 benchmark，只用 IQ3_XXS / high，其他参数用调参后的默认值，每场景 5 次取平均（用户 2026-10-11 授权，排在 IQ3_XXS 调参和高优先级任务之后）。

## ARW 同步与 Spec 恢复

这部分属于 rtx4070tis，等它恢复。规则见 `.claude/rules/reviewer-suite.md`。ARW 已同步到 760007c，[同步核查](../benchmarks/reviewer-suite-v1/source-sync.json)：554 文件逐项核对，112 份业务 fixture 字节不变；只完成无模型验证。

- [ ] 在新来源完成原版准备和受影响的无模型回归：报告独立目录可写，输入、请求、规则和恢复记录在目录外。
- [ ] 核对最终交付由运行层验证 completion，不再额外要求最终 send_message；更新受影响的驱动和来源绑定。
- [ ] 补安全验收（`.claude/rules/reviewer-suite.md`「正式测量前的安全验收」）中受影响的部分：一个该机对外模型的实例（原计划为 Q2_0；2026-10-19 起每台机器只对外一个模型）、三个原生沙箱 / 报告写入 / 同线程接续流程、15 个审批用例（约 21 次 guardian 判断），预计 30–60 分钟。
- [ ] 完成旧 Spec runtime-migration 报告和原生会话的 Main 检查；旧 0.1.40.1 首阶段不与 0.1.40.2 第二阶段拼接。

## 升级后 Spec Readiness 配置比较

该计划（rtx4070tis 上固定 Q2_0 的合并实例四组合）已失效：合并实例已停用（`.claude/rules/reviewer-suite.md`），IQ3_XXS 已是默认量化，窗口默认已改为 206584／150000。rtx4070tis 恢复后重新制定；旧计划文件 [spec-readiness-local-plan.json](../benchmarks/reviewer-suite-v1/spec-readiness-local-plan.json) 仅作历史。

## 上下文配置的测量与选择

（rtx4070tis 恢复后重定；IQ3_XXS 默认已改为 150K／206584；维护基线 = 本机唯一对外模型 + 部署默认值，原 Q2_0 100K／156584 基线 2026-10-19 退役。）上下文维度用合并实例（同线程先 runtime-migration 再 artifact-promotion），各子场景各有 55/60 分钟初审预算，按合并实例统计。容量公式见[容量计算](compaction-options.md#上下文容量计算)：64K/100K/150K/200K 对应 120584/156584/206584/256584。下面的 100K / 156584 默认是当时的设定。报告统一写入 `reports/v0.1.38/context-comparison/` 的 `summary.md` 和 `summary.json`；已完成结果见[历史工作](work-history.md#已完成上下文配置测量)，排序由用户决定。

## 周期流程

- **每日 Strata 更新检查**：流程见 `/strata-upgrade` skill「每日检查」。
- **每日检查统一时间**（用户 2026-10-18）：Strata 更新、额度规则优化、主机稳定性三项都在每天 11:13（JST）之后一起做。11:13 是 Strata 发布最少的窗口，见 `/strata-upgrade` skill「每日检查」。触发方式：后台工作期间由 20 分钟检查发现；会话空闲时，在 11:13 后的第一个回合补做；当前工作项做完、挑下一项时也要看一次。到点后先做，不按 queue 排序。三项在状态页 queue 合为一项「每日检查（日期）」，id 为 `daily-MMDD`（如 `daily-1019`），每个检查是其中一个子项；这一项单独标为「日」显示，不占前 5 个位置。子项做完就标记完成；三项都做完后，当天一项移到 done，并在 queue 建第二天的一项。
- **主机稳定性观察**（用户 2026-10-13）：平时只靠 Windows 事件日志和资源采样收集数据；每天一次（与其他每日检查同在 11:13 后；意外重启本身会留下 Kernel-Power 41，所以不另设重启后检查，2026-10-18）检查 WHEA-Logger（可纠正内存／机器检查错误；开机时信息级 ID 3 记录不算）与意外重启（Kernel-Power 41），不在定时检查里频繁查，不跑内存压力测试。内存 XMP 6600 与 CPU 功耗档 Intel Default Settings 的现状见[历史工作](work-history.md#主机稳定性与-bios用户-2026-10-13-决定)。

## 其他未解决问题

| 问题 | 现状 | 后续 |
|---|---|---|
| 长上下文可靠性 | 历史受控压缩保住了所选事实，但出现重复工具和错误摘要污染 | 执行[验证方案](compaction-options.md#长上下文可靠性验证方案待执行) |
| token 与请求归属 | 内部计数和 API 记录缺少共同请求 ID | 新测量从首次请求前归档 HTTP 日志；缺失记未知 |
| 重复工具导致停滞 | 调用手册保留[已观察的异常](installation-directory-readme.md#已观察到的执行异常) | 防循环功能已弃用；观察中，出现明显重复时交用户决定 |
| 业务适用性 | 结果来自本工程受控负载 | 由具体工程自行验证，不推广为通用保证 |
| 256584 档 200K 检索错误归因 | rtx3080ti IQ3_XXS 200K 下 6 实例同一记录检索错误，全部为 `--kv int8`（[报告](../reports/v0.1.42/iq3_xxs-tuning/kv-resident-long/summary.md)） | 用户 2026-10-12：记录，优先级很低。先无模型估算非 int8 KV 在 200K 的显存可行性，再做对照；答对则考虑档位绑定更高精度 KV，仍错则 IQ3_XXS 止于 206584 |
| Haiku 订阅额度扣减是否与 API 价同比例 | `estimate.sh` 的 K 按 Opus／Sonnet 回溯校准，Haiku 只核对了 API 价（1:0.7:0.05），订阅额度未核对 | 下次跑 Haiku 时记录运行前后 `budget.sh` 的用量变化，差超过约 30% 就改用实测值并更新 `estimate.sh` |
