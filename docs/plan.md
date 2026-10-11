# 后续计划

更新：2026-10-11。只放待办和需要重复执行的流程；已完成的经过见[历史工作](work-history.md)，测量通用约束见 `.claude/rules/`，参数任务只在[每机调参手册](host-tuning.md)维护。

## 待你决定

需要用户决定的事项只记在这里，处理后删除。

- F3 修复（用户 2026-10-11 同意）：已完成无模型修补。新增 ARW 补丁 `arw-patches/reviewer-followup-original-scope.patch`：重开条目时先在原工作目录检查原报告，接受新任务后再切换到新目录；附复现测试，修复前失败、修复后通过。驱动遇到 `reviewer-busy` 时等待原任务到终态后重发 followup；遇到 ARW 早退暂停则交给用户决定。PLE 测量已取消。F3 第 3 次试跑（2026-10-11 18:48–19:07，大页生效、Normal 优先级）通过：1 个合并实例，runtime-migration 与 artifact-promotion 在同一线程各 1 个回合完成，followup 在原作用域找到报告，没有出现 `reviewer-busy`、早退接续或停顿；两阶段各发生 1 次压缩，ARW 实际用的压缩提示是安装目录基础提示加 Codex 0.160.1 原生快照（与工程源同 SHA）；结束后 key 已归还、模型已停。runtime-migration 报告未通过 ARW `generate` 格式校验（要求 SPEC-READINESS-REQUIREMENTS 有问题时在需求范围检查后停止），属于模型输出质量，不是交接故障。明细在 `.tmp/arw4/sr-a/`。

## 顺序

rtx3080ti 是唯一可用主机，先推进属于它的工作；rtx4070tis 恢复后再决定它的工作。

1. [x] **前端部署与验收**（rtx3080ti）。2026-10-09 完成，见[历史工作](work-history.md)；剩余的托管搜索和升级评估见下文[前端](#前端)。
2. [x] **agent 接入**（rtx3080ti）。2026-10-09 完成，Codex 与 Claude Code 冒烟检查通过，见[历史工作](work-history.md)。历史测量仍标 0.160.1。
3. [ ] **防循环弃用部署**：代码、手册和测试已改（2026-10-11），随 v0.1.42 升级一起部署到 rtx3080ti；rtx4070tis 待同步。
4. [x] **Strata v0.1.42 + 默认改 IQ3_XXS + IQ3_XXS 调参**（rtx3080ti）：2026-10-11 完成，见[升级报告](../reports/v0.1.42/upgrade.md)，见下文[v0.1.42 与 IQ3_XXS](#v0142-与-iq3_xxs)。用户 2026-10-11 批准全部模型运行（申请二）。
5. [x] **rtx3080ti Q2_0 spec-min-p**：取消。用户 2026-10-11：Q2_0 只作 IQ3_XXS 的基线对比，不做详细调参。
6. [ ] **rtx4070tis 恢复后**：核对实际文件、版本、服务和持有状态；补同步离线期间的部署（v0.1.42、前端、新默认值）；再按[ARW 同步与 Spec 恢复](#arw-同步与-spec-恢复)和调参手册的本机待办安排。

## v0.1.42 与 IQ3_XXS

用户 2026-10-11 决定：升级 Strata v0.1.42，默认模型改为 IQ3_XXS，绝大部分参数在本机重新调，调参优先级高。

- **影响要点**（发布说明）：
  - CUDA 默认开启专家尾部跳过（`STRATA_ROUTE_TAIL_SKIP=7`，解码约 +13–16%，回答略有变化）；保持上游默认。
  - i-quant 在没有 `--pcie-frac` 时按 CPU 实测设定 PCIe 分担（3060 + IQ3_XXS 再快 +30%）；我们的 IQ3_XXS 模板写死 `--pcie-frac 0.00`，会挡住它，由调参第 1 维决定。
  - PLE 探测可能把 `--ple-io direct` 改为 `mmap`；CPU prompt 分担在内存不足时自动跳过。两项都要看日志。
  - 有用的修复：取消后保留会话缓存（#1620）、工具集顺序稳定（#1624）。#1622（v0.1.41 生成循环）仍未关闭。
  - 回答有变化，v0.1.42 的结果不与 v0.1.41 直接比较。
- **步骤**：
  - [x] 升级并部署弃用改动（2026-10-11）；升级报告等 Q2_0 短检查后一起写。
  - [x] S2：默认切到 IQ3_XXS 后短检查，量冷加载、复用、SSD 读取、内存和日志中的自动调整。
  - [x] IQ3_XXS 全部参数调参（用户 2026-10-11：先把 IQ3_XXS 所有参数测完、定好默认值，再处理 Q2_0，之后继续任务列表）。逐维进行，每条件 3 次，每维沿用上一维胜者：
    1. `pcie-frac`：实测自动 / 0.00 —— 完成，采用实测（[报告](../reports/v0.1.42/iq3_xxs-tuning/pcie-frac/summary.md)）
    2. CPU 核心分配：auto / all —— 完成，保持 all（[报告](../reports/v0.1.42/iq3_xxs-tuning/pool-affinity/summary.md)）
    3. CPU 专家线程数：23 / 15 / 12 —— 完成，保持 23（[报告](../reports/v0.1.42/iq3_xxs-tuning/pool-workers/summary.md)）
    4. PLE 读取：自动探测 / 强制 direct —— 完成，采用 direct（[报告](../reports/v0.1.42/iq3_xxs-tuning/ple-io/summary.md)）
    5. `prefill`：8192 / 16384 —— 完成，16384 被引擎降回 8192，保持 8192（[报告](../reports/v0.1.42/iq3_xxs-tuning/prefill/summary.md)）
    6. CPU 辅助短输入：0 / auto —— 完成，保持 auto（[报告](../reports/v0.1.42/iq3_xxs-tuning/cpu-prefill-share/summary.md)）；待办（用户 2026-10-11 同意排入计划）：显式 auto 与不设置在 1–3K 分块上的对照（显式 auto 上限 3072、不设置 1024）
    7. 显存预留：512 / 768 / 1024 —— 完成，采用 512（[报告](../reports/v0.1.42/iq3_xxs-tuning/vram-reserve/summary.md)）
    8. `spec-min-p`：0.3 / 0.5 / 0.7 / 0.9 —— 完成，采用 0.9（[报告](../reports/v0.1.42/iq3_xxs-tuning/spec-min-p/summary.md)）
    第 1–7 维用 32K 资源负载（`benchmarks/resource-calibration-v1/`），第 8 维用完整 Commit Audit。胜者只写入 rtx3080ti 的 IQ3_XXS（`model_overrides`）。
  - [x] Q2_0：v0.1.42 上的 Commit Audit 对照（3 次）和升级短检查（S1），然后写 v0.1.42 升级报告。—— 完成（2026-10-11）：S1 通过；Q2_0 诊断得分 0.773 对 IQ3_XXS 0.837，见[升级报告](../reports/v0.1.42/upgrade.md)。用户 2026-10-11：Q2_0 只作 IQ3_XXS 的基线对比，不做详细调参（第 5 项 Q2_0 spec-min-p 不再进行）。
  - [ ] ARW 运行环境两项（第 8 维会话检查发现，2026-10-11）：① 中途消息 `send_message` 连接本地 socket 被沙箱拒绝（`connect EPERM 127.0.0.1:…`），未送达；② Reviewer 为找 `ARW_BACKGROUND_AGENT_RUN_ID` 用 `env | grep` 宽泛查询，触发"环境身份"违规（IQ3 p090 与 Q2_0 对照各 1 次；Q2_0 那次还两次提权调用 `arw background-agent list_agents`，触发 guardian 子线程）。先无模型调查原版是否已有直接提供运行标识的方式；如需改 Role 或交接（ARW 合同变化），先列出差异取得同意。
    - 无模型调查结论（2026-10-11，ARW 760007c 原版代码与规格）：两项都是原版合同下的模型行为，不是本工程部署错误。
      - ①：原版 Reviewer 权限是 `:read-only` 加显式读写路径（`lib/reviewer-runtime/reviewer-native-policy.mjs`），没有命令网络；规格写明管理进程的 127.0.0.1 控制连接"不决定 Agent 的模型网络权限"，网络沿用原生 `on-request` + `auto_review`。所以不提权的 `send_message` 必然 EPERM；要送达就得提权，每次触发一个 guardian 子线程（Q2_0 那次约 13K 未缓存输入/次）。
      - ②：原版只通过环境变量 `ARW_BACKGROUND_AGENT_RUN_ID` 提供运行标识（`codex-app-server.mjs` 写入 `shell_environment_policy.set`），没有别的入口；Role 只写"运行环境提供的 `ARW_BACKGROUND_AGENT_RUN_ID`"，没说它是环境变量、可直接读取，模型于是用 `env | grep` 去找。检查规范允许使用这个变量本身，宽泛 `env` 查询才算违规。
      - 中途消息不是 Commit Audit 得分的一部分，最终结果由运行层 `completion` 交付。
    - 用户决定（2026-10-11）：两项都是场景缺陷。中途消息在能力验证和 benchmark 中没有意义，测量交接末尾追加"能力测量中不发送中途消息，不需要运行标识，禁止查询环境变量和平台身份"；上游缺陷记入 [ARW 上游缺陷记录](arw-upstream-issues.md)，由用户定期转交 ARW。
  - [ ] **IQ3_XXS 补测调参**（用户 2026-10-11 批准申请一）：按序 0 `STRATA_ADAPT_LAG` 不设置/2（直接完整测）→ 1 `--adapt-swaps` 96/160/48 → 2 `--adapt-every` 4/2/8 → 3 `--adapt-decay` 0.7/0.5/0.9 → 4 `--kv-resident` 20480/32768/12288（0–4 用 32K 资源负载，各 3 次）→ 5 `--spec` 3/4/5/6 → 6 CPU 辅助显式 auto/不设置 → 7 学习型专家档案（5–7 用 Commit Audit，等修复 F1/F2）→ 8 采样参数 → 9 窗口（用户：窗口和采样必须在 IQ3_XXS 上实测才能纳入默认值，放在最后，先采样后窗口；推理强度保持 high）。每维 Main 与独立复核一致才采用。进度：第 0 维完成，2 更快（约 +3–6%），双方一致采用并部署（[报告](../reports/v0.1.42/iq3_xxs-tuning/adapt-lag/summary.md)）；第 1 维完成，160 优势在噪声内（约 +1.4%）、48 偏差，双方一致保持 96（[报告](../reports/v0.1.42/iq3_xxs-tuning/adapt-swaps/summary.md)）；第 2 维完成，三者无可分辨差异（±1.5% 内），双方一致保持 4（[报告](../reports/v0.1.42/iq3_xxs-tuning/adapt-every/summary.md)）；第 3 维完成，0.9 与 0.7 持平、0.5 劣势来自单个离群实例，双方一致保持 0.7（[报告](../reports/v0.1.42/iq3_xxs-tuning/adapt-decay/summary.md)）；第 4 维完成，32768 在短负载上无收益、12288 被引擎抬到 20480 无效，双方一致保持 20480；长上下文 20480/32768 补测待另行申请，测 64K/100K/150K 三个长度（用户 2026-10-11）；对外上下文档位定为阈值 100K/150K/200K、窗口 156584/206584/256584 三档（第一档为默认），用户 2026-10-11 决定先在 IQ3_XXS 上实测再发布 206584/256584 两档（[报告](../reports/v0.1.42/iq3_xxs-tuning/kv-resident/summary.md)）；rtx4070tis 待同步。
  - [ ] **benchmark 场景修复**（用户 2026-10-11 批准申请二）：F1 测量交接追加说明（冻结文本文件，记 SHA）；F2 能力验证和 benchmark 中关闭本工程接续机制，改用 ARW 原版接续与 10/5 次暂停（最大限度还原 ARW，便于与 ARW 自己的结果直接对比）；（进展：F1 已完成；F2 按用户决定改为给 ARW 打本工程接口补丁、由 ARW 持有独占并启动模型，实例间不停模型，补丁、驱动和单元测试已完成，待 F3 实跑验证；F3 合并实例改由 `arw_measure` 在 ARW 持有模型模式下运行：同一重复先 runtime-migration、再在同一线程接续 artifact-promotion，第一份报告接续前核对 SHA，第一阶段未完成则跳过并记录缺口，不再停等 Main 中途决定；本机准备和预检已通过（前端 `/health` 改动已部署）；F3 首次试跑失败（ARW 请求 403）：本工程运行层传入 `nativeSessions` 时 ARW 宿主不创建模型目录，管理器读不到 provider，provider 也只写进了 `native-model-catalog.json` 而非 ARW 读取的 `models.custom.json`；2026-10-11 已修复（运行层与 App Server 共用一个 ARW 目录、provider 写入 codex-home 的 `models.custom.json`，daemon 就绪时回报 ARW 实际读到的 provider，驱动核对后才派发），同时 ARW 补丁改为只传模型和安装目录发布的上下文档位（provider `contextWindow`，默认第一档），窗口和压缩阈值都取自该档位，selection 不再带 `auto_compact_token_limit`；ARW 持有模型模式下每个实例从派发到分段关闭采集主机遥测；ARW 合并后的压缩提示 = 安装目录基础提示（与工程源同 SHA）+ Codex 原生快照 0.160.1，该快照文本完整出现在 0.162.0 二进制中（静态比对，实际压缩路径待试跑确认））F3 第二次试跑（2026-10-11）：ARW 成功领 key、启动模型，runtime-migration 首回合完成（758 秒，报告 ready）；接续 artifact-promotion 时触发 ARW 缺陷（见 `docs/arw-upstream-issues.md` D：原线程卸载后 followup 用新交接的文件系统检查原报告，判"缺失"并连续接续 10 次），驱动收到 `reviewer-busy` 退出，实例无效；已用 ARW 原版中断结束任务、维护接口关闭守护进程归还 key，并停模型；修复需改 ARW 运行层，待用户决定；F3 Spec Readiness 本机无模型准备与回归，再试跑 1 个合并实例；F4 单场景评分工具；F5 已有 Code Spec/Code Standards 两个实例不并入，全部重跑；F6 四场景各 5 次（另行开跑）。
  - [ ] 有余时间时：ARW 完整四场景 benchmark，只用 IQ3_XXS / high，其他参数用调参后的默认值，每场景 5 次取平均（用户 2026-10-11 授权，排在 IQ3_XXS 调参和高优先级任务之后）。
    - 自主模式决策（2026-10-11 10:10）：Main 判断与独立复核一致，选"只跑已能验证运行路径的部分、全部按诊断口径"，Spec Readiness 延后到用户回来（新来源上的同线程合并实例、报告目录、completion 交付和 10/5 次早退暂停都未验证，5 次约需 4 小时以上）。分歧：Main 原想复用第 8 维 p090 的 3 个 Commit Audit 实例再补 2 个，复核建议 5 次全部新跑以保持样本独立；采纳复核意见。顺序：Code Spec 先跑 1 个并完整检查会话，通过后补到 5 次；Code Standards 同样处理；最后 Commit Audit 5 次。停止条件：早退续跑累计 10 次；首个实例暴露驱动或来源问题且修不好；env 查询以外的安全违规；报错、崩溃、卡顿或输出低于 60 tok/s；用户回来或 key 被需要（当前实例结束后归还）。结果不算"四场景完成"，也不是正式分数。
    - 进度（2026-10-11 约 10:40，额度用尽暂停）：Code Spec 第 1 个实例完成（`.tmp/arw4/cs-a/`，ready，诊断分 0.807，clean 21/21，Main 已裁决 20/32 matched）；之前两次 spawn 前失败（驱动缺陷已修复并提交；漏设 `CODEX_THREAD_ID`），未产生 Reviewer 活动，租约已归还。会话检查 agent 被 API 安全过滤中断，**会话检查未完成**，需重做。Code Standards 第 1 个实例（`.tmp/arw4/cst-a/`）在后台运行中，结束后驱动自行归还租约；若留下 `run/recovery-required.json`，按 `.tmp/arw4/release.py` 的方式核对后归还。剩余：两个首实例的会话检查 → 各补到 5 次（第二批用 `.tmp/arw4/prepare.sh <tag> <reviewer>` 再 prepare，`--limit 2`）→ Commit Audit 5 次 → 汇总报告。驱动命令须带 `CODEX_THREAD_ID=b7635f94-ad60-429b-98e7-3ee5c19ba2bb`。 之后 Code Standards 第 1 个实例完成（ready，未评分、未做会话检查），租约已归还。2026-10-11 用户停止自主模式，benchmark 暂停在此，后续按用户决定。
- **用户决定（2026-10-11 上午，自主模式结束后）**：显存预留维持 512；所有任务默认用 IQ3_XXS，除非有特殊理由；ARW 运行环境两项按"有缺陷就修复、没有缺陷就禁止查询"处理；Spec Readiness 要在本机修好并按要求跑完两个子场景，同时提供单场景评分能力供调参使用；Reviewer 网络规则与 Codex 默认一致（允许 web_search，不允许脚本访问网络）。先确认调参是否已做完，再修 benchmark 场景，之后决定重跑还是纳入已有两个实例。
- **用户的夜间决定**（2026-10-11）：
  - S2 首次探测（2026-10-11）：冷加载 18.4 秒，解码 77–95 tok/s，生成期间只读 0.6 GB SSD；约 40 GiB 专家锁定在物理内存，物理可用内存最低 7.4 GB，页面文件几乎未用。但提交额度（内存 + 4 GB 自动页面文件）只剩 0.5 GiB，引擎因此跳过会话暂存（Windows 上按物理可用与剩余额度取较小值），并警告可能无提示退出。用户把页面文件改为固定 16384 MB 并重启。复测：提交额度剩 15.6 GiB / 79.8 GiB，没有警告；会话暂存恢复（每次约 45 ms）；解码 80–97 tok/s；物理可用内存最低 7.8 GB。PLE 探测把 `--ple-io direct` 改为 `mmap`（11680 行/秒）。
  - IQ3_XXS 模型 75.8 GB 大于 64 GB 内存：记录读量和内存，照常调参；只有出现错误、崩溃、系统明显卡顿，或输出低于 60 tok/s 时停下等用户。所以 IQ3_XXS 尽早测。
  - 胜者规则：各条件全部正确完成、批次得分差在 0.08 以内时，按引擎输出 tok/s 和工作时间选；差距更大时按得分选。
  - 采用：Main 与独立 agent 意见一致就在夜间写入 rtx3080ti 的 IQ3_XXS 默认值并部署；不一致保留原值，记录待用户决定。

## 前端

设计已获批准，实现见 `src/frontend.py`、`src/model_process.py`，结构见[前端运行与维护](frontend.md)。

- [x] **2b 模型验收**：2026-10-10 审核通过。`qwen-agent` 删除 `--approval`，Claude Code 固定用 `qwen-approve` 审批。
- [x] **rtx3080ti SSD 读取**：2026-10-10 按用户决定实现模型跨租约驻留并部署；实测复用启动 0.06 秒（冷加载 18.3 秒）。同时修复停模型时 `/unload` 未带内部 key、一直没能正常卸载的问题。
- [ ] **Strata v0.1.41**：2026-10-10 已安装到 rtx3080ti，并通过短调用链检查，见[升级报告](../reports/v0.1.41/upgrade.md)。还需要：
  - 关注上游 [#1622](https://github.com/Niko1221/Strata/issues/1622)：有用户反映 v0.1.41 出现生成循环，未关闭。用户决定不回退，出现问题就解决。
  - rtx4070tis 恢复后同步安装。
  - 发布说明称 prompt 处理约快 2 倍，尚未验证；需要时另行申请版本对比。

## 防循环检测（已弃用）

用户 2026-10-11 决定：提醒默认关闭、启动提示默认不加载防循环段，两者标为已弃用，经过见[历史工作](work-history.md#2026-10-1011-防循环提醒试跑基线与弃用)。没有待办；观察到没有明显重复后，由用户触发删除（提醒、检测器、防循环提示段、旧关键词守卫工具和测试一起删）。

## Spec Readiness 单场景评分

- [ ] 原版高层 `score-completed` 要求两个子场景配对，单独 artifact-promotion 会被拒绝。需要先无模型调查原版是否有可单独评分的入口；若需改变评分合同，先列出差异并取得同意。
  - 无模型调查（2026-10-11，ARW 760007c，只读代码和原版测试，没有用实际 Spec 报告执行）：当前原版 `score-completed`（局部评分）**不再拒绝**未配对的输入。`selectCompletedRepetitions(allowEmpty)` 接受只含 artifact-promotion 的实例；每个实例照常评分，`instances[]` 里有该实例自己的 `score`、clean/problem 比率和候选，状态为 `diagnostic`；但 `summarizeCapabilityScores` 只对两个子场景齐全的重复算重复分和总分，单场景时 `score` 为空（"Incomplete repetition set."）。原版测试 `reviewer-capability-conformance.test.mjs` 的局部评分用例覆盖了这一行为（以 Code Spec 为例）。早先"会被拒绝"的结论来自旧版 ARW。
  - 含义：不改评分合同就能拿到 artifact-promotion 的单实例诊断分（同一 F2 公式，只是不与 runtime-migration 融合），可以作同场景条件之间的比较；它不是原版正式分数，也不能和融合分混比。正式分数仍需两个子场景配对。
  - F4 工具：`python3 -m tools.reviewer.single_scenario_score --arw <冻结 ARW> --prepared <prepared.json> --input <只含一个子场景的评分输入> [--adjudication <裁决>] --out <目录>`，调用原版 `score-completed`，只汇总单一子场景的逐实例分（标为 `diagnostic-single-scenario`、未融合），混入两个子场景时拒绝。已用 Code Spec 试跑报告核对，结果与原版一致（0.807）；artifact-promotion 的实际报告已用 F3 第 3 次试跑核对：上游返回 8 个待裁决候选，裁决 6 个匹配、2 个不匹配后得到诊断分 0.320（clean acceptance 0.907，problem detection 0.275），工具流程正常。用户已决定提供这项能力供调参使用（2026-10-11）。

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
| 重复工具导致停滞 | 调用手册保留[已观察的异常](installation-directory-readme.md#已观察到的执行异常) | 防循环功能已弃用；观察中，出现明显重复时交用户决定 |
| 业务适用性 | 结果来自本工程受控负载 | 由具体工程自行验证，不推广为通用保证 |
