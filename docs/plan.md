# 后续计划

更新：2026-10-19。只放待办和需要重复执行的流程；已完成的经过见[历史工作](work-history.md)，测量通用约束见 `.claude/rules/`，参数任务只在[每机调参手册](host-tuning.md)维护。整个工程的现行决定见 [README](../README.md#现行决定)。

## 待办顺序

这里是真正的工作队列，按优先级排列，做完一项接下一项。状态页 queue 收录全部未完成项（下一版 benchmark 的改进各占一项，排在本表各项之后），默认显示排在最前的 5 项，其余点“另有 N 项”展开；每日检查（三项合为一项，见「周期流程」）单独显示，不占这 5 个位置。顺序有变化时，先改这里，再用 `status.py order` 同步状态页。

1. ~~Commit Audit v3 定稿~~：2026-10-18 定版完成，见 work-history。
2. ~~修正 catalog 上下文窗口~~：2026-10-19 部署到 rtx3080ti，见 work-history。
3. ~~核对写死在代码里的上下文和压缩阈值~~：同上。
4. ~~统一 Codex 与 Claude Code 的上下文档位~~：同上。
5. ~~修好安全门并在 v0.1.45 上重跑~~：2026-10-19 在 WSL 3.0.3、目录授权下通过；单模型对外与隔离修复部署后两次重跑都通过，现行证据 [safety-gate-env-fix](../reports/v0.1.45/safety-gate-env-fix/summary.md)。
6. ~~评分规则遗留~~：两项核实已完成（r7 已实现，69969fa 补测试）；Sonnet 盲裁试点通过（[报告](../reports/v0.1.45/sonnet-adjudication-pilot/summary.md)），但用户 2026-10-19 决定 benchmark 仍用 Opus 裁决（质量优先）。本项完成。
7. ~~多模型 benchmark 方案设计~~、8. ~~执行与报告~~：2026-10-22 两阶段报告发布，见 work-history。
9. ~~Strata 升级到 v0.2.2~~（2026-10-24 已再升到 v0.2.4，下列遗留不变，[报告](../reports/v0.2.4/upgrade.md)）：2026-10-22 完成，短检查通过（[报告](../reports/v0.2.2/upgrade.md)）。遗留（都是速度类或需改部署集合，按需在后续调参时做）：~~0.2.2 引擎建议 `--pool-workers 15`~~（2026-10-24 对照完成，维持 23，[报告](../reports/v0.2.4/pool-workers/summary.md)）；`STRATA_SM86_PERF` 加进 `src/model_process.py` 白名单后做开关 A/B；长提示第 1 问的版本差异来源。安装后再详细检查 0.2.x 新功能有没有能替代或改进本工程适配的部分；新模型暂不考虑（用户 2026-10-22）。
10. ~~电源计划对照~~：2026-10-23 完成，两种计划速度差不到 1%（噪声量级），一直用平衡（[报告](../reports/v0.2.2/power-plan/summary.md)）。
11. ~~零模型 mock 门回归~~：2026-10-22 修好（91bed4d），根因是调用缺 `--directory-probe`；`claude_scenario --backend` 已加 deepseek。
12. ~~Claude Code 路径的提醒改用高优先级消息~~：2026-10-23 实现，见「多模型 benchmark」。
13. **采样与窗口重新测量**：负载设计，见同名一节。前置的 harness 换版已完成（2026-10-24）：版本改由 `tools/reviewer/harness_pins.py` 一处配置，换到 Codex 0.164.0、Claude Code 2.1.309 的 benchmark 副本；单测、两侧 mock 门、compact probe 和第 12 项的 Strata 送达实测 2 例都通过；2.1.309 的工具搜索占位工具由 runner 设 `ENABLE_TOOL_SEARCH=false` 去掉（`qwen-agent` 日常路径未改，待定）。开跑时若已有更新版本，按测量规则再换。
14. **rtx4070tis 上线**（用户 2026-10-22 提出，不急，排在 13 之后）：用户准备让它恢复运行，只有 GPU 不同（4070 Ti SUPER 16GB，sm_89）。开始前先请用户定：对外量化（建议沿用 IQ3_XXS，IQ3_S 以后单独立项）；影响输出的参数（采样、窗口）是否沿用 3080 Ti 结论（建议沿用，只重测与硬件相关的维度）；直接装当时的最新版，不补中间版本。步骤：用户开机并提供连接方式 → 核对实际文件、版本、驱动（cuda13 引擎要求 ≥580.65）、权重、BIOS 微码（14900K 的 Vmin Shift）→ 系统环境对齐 3080 Ti（计划任务 Normal 优先级、锁页内存、页面文件 32768，需要 UAC）→ 补全 `config/deployments/rtx4070tis.json`（地址、端口、context_tiers）→ 用 upgrade_release 或重建安装 0.2.x（注意 `install_offline` 按发布版本拼引擎目录的已知限制）→ 部署（带上离线期间的全部改动）→ 安全门、compact probe、短检查 → 按[调参手册](host-tuning.md)「每机执行方法」对 IQ3_XXS 独立调参：16GB 显存下 prefill 16384、kv-resident 32768、显存预留、专家缓存都要重新测；sm_86 专用的解码开关表不适用；可顺带对照 256584 档在非 int8 KV 下的 200K 检索错误（见「其他未解决问题」）。原「顺序」第 6 条并入本项。
15. ~~v5 题库~~：2026-10-24 用户关闭（采样维 10-22 已改用 ARW），见 work-history。

下一版 benchmark 的改进（输出上限重试、harness 设置对齐、Role 说明、歧义题目、会话检查工具）在下一版 benchmark 立项时一起做，不单独排序。已先做的部分（2026-10-24，b7a4f36 合入）：Claude Code 臂加 `claude_scenario --role-as-system`（Role 说明合进 `--append-system-prompt`，默认关，旧计划不变；mock 已核对请求形态，未用真实 ARW Role 全文测命令行长度）；会话检查对解析失败的 Bash 输入显示原文并标 `bash input not parsed`。歧义题目要改场景原文，会改变 v1 冻结的 SHA 绑定，留到新版目录建立时做。

等外部条件、不参与排序：rtx4070tis 恢复后的各项，包括「顺序」第 6 条、「ARW 同步与 Spec 恢复」「升级后 Spec Readiness 配置比较」「上下文配置的测量与选择」。

待核实是否仍然有效（「IQ3_XXS 遗留事项」）：
- 补测调参只剩第 9 维（窗口），已并入第 8 项；
- 场景修复 F2–F6 针对的是已停用的合并实例；
- "ARW 完整四场景 benchmark"已被多模型 benchmark 取代；
- 「顺序」第 3 条在 rtx3080ti 上随 v0.1.42 已部署，只剩 rtx4070tis。

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

- [x] **方案设计**（开跑前，按 AGENTS.md 硬约束 1 处理测量设计部分）：用户决定已齐（2026-10-19 三轮答复），定稿见[运行计划](../benchmarks/multi-model-v1/plan.md)：27 个配置 × 4 场景 × 5 次，基础提示只给 Strata，搜索全部关闭，OpenAI 用 ChatGPT 套餐登录，DeepSeek 用 `DEEPSEEK_API_KEY`（用户 10-19 设在 `~/.profile`）。代码适配已完成（ChatGPT 登录链接、relay 记录实际 service tier、两个 harness 关闭搜索、Claude Code 的 DeepSeek backend）。盲裁维持单名 Opus（用户 2026-10-19）。阶段 0 进展（2026-10-19）：三份盲裁 brief 已冻结；G7 deny-read 已实施；benchmark 专用 Codex 与 Claude Code 副本已装、compact probe 通过；API 臂压缩提示无残留已核实；G8 Strata live 冒烟通过；汇总层已实现。剩余：冻结 API catalog、汇总适配层、冻结计划（状态见运行计划 §9）。
- [x] **执行与报告**：按场景分批运行。报告给出每个模型的均值 ± 标准差、耗时、token、工具调用数，以及每次的费用。
- [x] **benchmark 结束后：Claude Code 路径的提醒改用高优先级消息**（用户 2026-10-20）：ARW 提醒在 Codex 上是高优先级消息，会立即打断当前生成，确保模型在超时之前收到；Claude Code 路径现在经 PostToolUse hook，要等工具调用结束才送达。先查 Claude Code 无头模式能否中途打断并插入消息（如 stream-json 输入的 interrupt 加新的 user 消息，未核实），再实现并做对照；同时检查 relay 和各臂判定，别把这类主动打断记成故障。
  - 2026-10-22 实验完成（`.tmp/cc-priority-1022/report.md`）：stream-json 输入写 `priority:"now"` 可在 0.1 s 内打断生成；工具执行中改为先 `control_request interrupt` 再写消息；Strata 端 cancel 与计量正常，`--resume` 可续。下一步按报告方案实现（`claude_headless` 改 stream-json 输入、判定放行 `aborted_*`、版本改 2.1.308 重跑 mock 门），再做 1 个真实对照。
  - 2026-10-23 实现：`claude_headless` 改 stream-json 输入（stdin 保持打开），提醒写 `priority:"now"`，工具执行中先 `control_request interrupt`，硬截止 interrupt 后关 stdin、宽限 20 s 再结束进程组，记录写 `deadline-handoff.json`；`reminder_interrupt.stream_exempt` 只放行送达时正在进行的那一轮的 aborted 结果。版本仍用 2.1.303（兼容性已核实，不改版本）。全量单测、5 组 mock 门通过；Strata 实测 2 个实例（长 Bash 中、生成中各 1 次）送达正常，被打断后会话继续、引擎 cancel 与计量一致。
- [ ] **下一版：输出上限重试改进**（用户 2026-10-22）：`src/output_limit.py` 现在只重试 1 次，重试只追加一条通知。strata-codex CStd low-a9 两次都在写同一个 exec_command 时撞 8192，推理 token 都是 2065（输入只多了通知的 95 token），说明通知没有改变模型的做法，多重试几次也不会有效。候选做法：重试时降低 `max_output_tokens`，或者把通知放到更显眼的位置，或者两者结合。改动属于部署设计，先过独立审查，再用撞上限的 mock 和实例对照验证；不追溯本次 benchmark。
- [ ] **下一版 benchmark：对齐各 harness 的窗口与压缩点，并逐实例记录压缩次数**（用户 2026-10-22）：v1 的 DeepSeek 在 Codex 上用 1048576 窗口、实际不压缩，在 Claude Code 上没设 `CLAUDE_CODE_MAX_CONTEXT_TOKENS`、约 162K 压缩（plan §4 第 7 条）。下一版按测量规则「跨 harness 设置尽量一致」逐项对齐（窗口、压缩点、强度、输出上限），保留的差异写明理由；开跑前用 mock 门抓请求核对两边实际生效的压缩点；bench_records 增加每实例压缩次数（Codex rollout 的压缩事件、Claude Code stream 的 compact_boundary），并进 summary 与导出。

## 采样与窗口重新测量（用户 2026-10-12）

采样和窗口两个影响输出的维度，原结论（greedy、156584）在 ARW 上分不出高下，暂时维持现值；需另行设计答案可机械判定、低波动的专用负载，按「评分口径」的分阶段判定重新测量（负载设计属测量设计，按 AGENTS.md 硬约束 1 处理）。
- 设计 v2（`.tmp/load-design-1022/draft-v2.md`）用户决定（2026-10-22）：
  - 先做窗口维（206584 vs 156584），按 v2 §2 设计；打分统一：5 个检查点等权；平手按总工作时间（含压缩）选（用户 2026-10-22 确认）。其余 U 项按 v2 推荐。
  - 采样维改用 ARW（用户 2026-10-22：专用题与 ARW 都难分辨时，用一直维护、更贴近使用的 ARW）。场景选 code-spec-v5（CS）、Codex、IQ3_XXS high：第二阶段 10 次 SD 0.029（低于调参门槛 0.068，其余三场景 0.05–0.15），实例约 9.3 分钟。因此沿用现行规则（双侧、δ=0.05、3/5/7/9/11），不必改判定；按 SD≈0.03 估计 d≈0 时约第 2–3 轮可判等效。前提：0.2.2 上和 card/t06 采样下 SD 要复核（第 1 轮后看实测 SD，若明显变大再交用户）；评分沿用 benchmark 的 rulings 与盲裁（含付费模型费用）；循环率从 ARW 会话统计，按 v2 §1.4 的 G/T/R。
- [x] 采样维：2026-10-24 ARW code-spec-v5 第 1 轮三档分不出、SD 0.072，用户决定维持 greedy 并结束（[报告](../reports/v0.2.2/sampling-dim/summary.md)）。原条目：采样负载设计（同时测循环率）。模型卡（huggingface.co/Qwen/Qwen3.8-Flash-Next，2026-10-12 查）：思考模式推荐 temperature 1.0、top_p 0.95、top_k 20、min_p 0、presence_penalty 0；agent 编程评测用 temp 1.0、top_p 0.95；未提 greedy；重复时可调 presence_penalty 0–2。原生上下文 262,144。
- [ ] 试跑结束后：调参驱动实现加载后预热、分数类参数同条件连跑、速度类参数按块交替（AA BB BB AA）与运行顺序趋势检查、各实例 reused 比例核对（规则见 measurement.md「预热与连跑」，bcceb93）。
- [x] 窗口维：2026-10-24 试跑收尾，负载对模型侧不敏感，按工作时间暂时维持 206584（[报告](../reports/v0.2.2/window-dim/summary.md)，待用户复核）；长上下文验证 v2（[报告](../reports/v0.2.2/longctx-150k/summary.md)）与按用户要求重做的 v3 记忆负载（[报告](../reports/v0.2.2/longctx-retest/summary.md)）跑完，2026-10-24 定为维持 206584（已登记现行决定，待用户复核）。
  - [ ] 低优先级：窗口维负载加入多次更新的 latest 题，两档各跑 1 个 Codex 实例（约 1 小时 GPU），看压缩后答最新值是否有差别；不阻塞现行决定。

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
