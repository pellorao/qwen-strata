# Code Spec 正式场景（v5）运行计划

依据：
- `docs/plan.md`「Code Spec 正式场景」（用户 2026-10-14）：阅读量档位定为 150K；20 个缺陷全部打散，各模块密度大致均匀、数目不固定，不保留集中的核心；clean 用例也打散。
- 用户 2026-10-14 的口径决定：clean 误报不另设判据，按 ARW 原版计分，目标是 Q3/Opus < 0.8，报告列出全部 clean 失败；clean 保持 28 个加 `noOtherSupportedFinding`。
- 用户 2026-10-14 同意：v5 的全部 Opus 运行改用无头 `claude -p`。

本文件在冻结前写定。2026-10-14 冻结修订 38（code-spec-reviewer 修订号 38），冻结版的条件、补丁与 SHA 以 `code-spec-v5-iq3_xxs-2026-10-14/plan.json` 为准。构造过程、逐题对等说明和已知偏差的完整记录在构造目录的 `design.md`（本文件第 9 节摘要）。

## 1. 目的

测量 Q3（IQ3_XXS）在约 150K 阅读量、缺陷全部打散的代码规范审查上，相对 Opus-high 的能力比值。
- 判据：Q3/Opus（ARW 原版得分的均值比）< 0.8。
- 结论用于 Code Spec 场景的正式结果，适用范围只限 Strata v0.1.44.1、本机、IQ3_XXS。

## 2. 主机与模型

- 本机，IQ3_XXS，Strata 0.1.44.1，Codex 0.162.0，effort high。
- 参考模型：Opus-high，无头 `claude -p`（Claude Code 2.1.299），与 Q3 相同的渲染交接盲答，不占 GPU。
- 无头 Opus 的隔离（2026-10-14 用 haiku 短提示验证）：
  - 选项：`--model opus --effort high --safe-mode --restricted --strict-mcp-config --disable-slash-commands --setting-sources "" --permission-mode dontAsk --permission-prompts none --output-format stream-json --verbose --no-session-persistence`；`--settings` 传入 `autoMemoryEnabled false`、`includeGitInstructions false` 和下面的沙箱设置。验证结果：0 hooks、无 CLAUDE.md、无记忆、无 git 状态。
  - 工作目录是工程外的场景根，结果写到场景根内的 `_out/result.md`，评分前移出；`Edit(//<场景根>/_out/result.md)` 是唯一允许的写入（`Write(...)` 规则不生效）。
  - Bash 沙箱（bwrap）：denyRead `/home /mnt /tmp /etc/claude-code`，allowRead 场景根；denyWrite 逐项列出场景根下已有的条目，allowWrite `_out`；`network.allowedDomains` 为空。已验证：场景根内可运行 node，越界读失败，curl 不能联网，已有材料不能改也不能删。Bash 仍能在场景根新建文件，所以开跑前后比对场景根文件清单和哈希，新建文件计入会话分析，评分前移出。
  - 用量取 stream-json 中 result 事件的 `usage`、`duration_api_ms`；会话分析只用动作序列和可见消息。

## 3. 固定条件

- 引擎默认值、窗口 206584 / 压缩阈值 150000、启动提示与压缩提示接入、native CLI、测量说明时限模板、按 ARW 原版罚分：与 rv3 冻结计划 `code-spec-rv-iq3_xxs-2026-10-14` 相同，开跑前核对实际加载的 SHA 并保存绑定。
- 场景：`code-spec-v3.patch` 之后叠加 `arw-patches/code-spec-v5.patch`（替代 rv3 的 `code-spec-rv.patch`），manifest `source-snapshots/current/manifest-code-spec-v5.json`。v4.7 和 rv3 的 manifest 不变。
- 阅读材料：B = 152,919 字节（spec + 候选代码，全部注入版）。13 个模块（reservations 加 12 个干草堆模块）和共用目录 `src/platform/`。spec 除标题和 Conventions 外按 `##` 节以固定种子（20261014）穿插，干草堆部分是模块节加 5 个跨模块主题节。
- 时限：T 秒 = B ×（1/P + k/G）/ β，k 2.0755、β 3.6591 沿用 rv3 冻结值；每批开跑前速度探针重测 P、G。冻结前四次探针给出的 T_Q3 为 907–949 秒。Q3 用 ARW 原版 `ReviewDeadline` 提醒与中断；Opus 取 1/P = 0，β、G 用开跑前的 Opus 探针，T − 5 分钟提醒，到 T 停止，按结果文件计分。

## 4. 缺陷与用例

- **问题用例 20 个**，与 v4.7 的 20 题一一对应（答案键 `answer-key.json` 写明 P 号 → 用例名、v4.7 原题、模块）。
  - reservations 3 个：amenityDup、historyShared、rescheduleDuration，注入代码与答案键与 v4.7 逐字相同。
  - 干草堆 17 个：rv3 的 11 个搬家题原样保留（去掉 holdUnits_visitors），另有 6 个 v4.7 原样题按对等推理放进干草堆：holdUnits、selfConflict（payments）、durationUnits（audit）、snapEnd（messaging）、accessUntilLarge（exports）、lateFeeState（waitlist）。
  - 分配：reservations 3；干草堆计数多重集 {3,2,2,2,2,1,1,1,1,1,1,0} 用种子 20261015 洗牌分给按字母序排列的模块，之后 snapEnd 从 billing 移到 messaging（billing 1、messaging 2）。偏离的原因是 billing 只能把 snapEnd 做成"对照字面公式"的短题，与 v4.7 的长链不对等。
- **clean 用例 28 个 + `noOtherSupportedFinding`**：reservations 从 v4.7 的 30 个 core clean 里用种子 20261015 抽 4 个；干草堆每模块 2 个。

## 5. 规模

- 正式：Q3 ×5（每次全新 ARW 准备、冷加载），Opus-high ×3，与 Q3 并行。
- 空闲加测：GPU 空闲时 Q3 加测到 10 次。目标事先定为 10，不按中途结果决定；报告同时给前 5 次和全部结果。

## 6. 预计耗时

- 每个 Q3 实例：探针约 1 分钟，运行约 8–12 分钟（冻结前 trial 实测 7.8–11.1 分钟工作时间）。Q3 ×5 约 70 分钟，加测到 10 次再约 70 分钟。
- Opus ×3：每次约 25–40 分钟，与 Q3 并行。
- 评估：机械计分、盲裁、会话检查约 40 分钟。

## 7. 前置条件

- 构造检查（修订 38，冻结补丁 `code-spec-v5.patch` sha256 `231fd10853c3eab9917c5d27565396b22a4549b16457fbb256c0ace983d85b1a`）：verify 20/20（正确版探针全过；每个缺陷单独注入只破坏自己的检查，无重叠；全部注入时恰好 20 个检查失败）；hay 单元测试 171/171；conformance 70/70。
- 审查：两位独立 Opus-high 盲审（修订 35，各命中所负责模块的全部植入缺陷，无 unplanted-real），之后三轮 diff 审查（修订 36、37、38），最后一轮结论为可以冻结。
- 无头 Opus 隔离：`opus-headless.md` 记录的选项（--safe-mode --restricted --strict-mcp-config --disable-slash-commands --setting-sources "" 等）已验证 0 hooks、无 CLAUDE.md、无记忆、无 git 状态。Bash 沙箱（socat 已装）：在场景根运行 node、越界读失败、curl 不能联网均通过；写限制为逐项禁写场景根下的已有条目、`_out` 可写，开跑前后比对场景根文件清单，新建文件计入会话分析。
- 中性规则（沿用 rv3）：正式运行在冻结代码上报出的发现，核实为真缺陷的修正留给下一版，本版计分按中性处理，既不算 `noOtherSupportedFinding` 失败，也不计分；核实由盲化的独立裁决 agent（Opus，effort 不低于 Main）完成，Main 再用可执行检查复核。
- 每实例经前端领租约、冷加载，结束后停模型并归还租约；不抢占。

## 8. 判据、计分与报告

- 判据：Q3 ×5 均分 / Opus ×3 均分 < 0.8，按 ARW 原版得分（命中加 clean）。独立 agent（不低于 Main）给意见后由 Main 判定。
- 命中按 ARW 关联计，盲裁流程与 v4.7、rv3 相同；各次运行的发现合并、分组、打乱后交裁决 agent。
- clean：按 ARW 原版判定，报告列出全部 clean 失败；无依据的发现单列。只有未关联到任何问题的发现能让 clean 失败，所以计分以盲裁关联之后的结果为准，不用第一遍的机械失败数。
- 报告：逐题命中（Q3、Opus），按 v4.7 原题对照；按模块与类别（长链、规则交互、短而隐晦、保底）汇总；误报、中性处理项、时限中断、压缩、阅读顺序与发现写入时间点、运行方式混杂项。

## 9. 与 v4.7、rv3 的差别（混杂清单）

与 v4.7（18K，集中核心）和 rv3（150K，核心 8 题）相比同时变了：
- 缺陷全部打散：核心只剩 3 题，6 题从 reservations 移入干草堆，与 v4.7 原题按推理类型和步数对等；snapEnd、selfConflict 的宿主结构与原题不同（见 design.md 已知偏差）。
- clean 打散，数量 28 + 1（v4.7 是 30 + 1，rv3 是 54 + 1）。
- Opus 运行方式：v4.7、rv3 是 Claude 子 agent；v5 是无头 `claude -p`，系统提示、工具集和权限不同。
- 时限、交接模板、跨模块结构、Strata 0.1.44.1：与 rv3 相同。
- 已知偏差（design.md 记录）：reservations 里留有 6 个新放入题的反向孪生；acceptOffer 先转换后检查的顺序反常；reservations 的 `endAt <= startAt` 对非数字放行（诱饵，按无依据处理）；两张 RULES 表同构。

## 10. 冻结前试跑（不计入）

| 修订 | T（秒） | Q3 命中 | 漏检 | 备注 |
|---|---|---|---|---|
| 35 | 931 | 13/20 | P01、P09、P10、P13、P15、P17、P19 | 读遍全部模块，发现分三次写入 |
| 36 | 907 | 15/20 | P09、P10、P13、P16、P17 | 发现分五次写入 |
| 37 | 949 | 15/20 | P01、P09、P10、P13、P16 | snapEnd（r37 写法）靠"不在分钟边界"的捷径命中，修订 38 已改 |
| 38 | 932 | 14/20 | P01、P09、P10、P13、P15、P17 | 冻结版；14 条发现全部是植入缺陷，0 诊断、0 压缩，9.5 分钟 |
