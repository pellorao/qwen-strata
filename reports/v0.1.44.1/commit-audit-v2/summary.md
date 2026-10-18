# Commit Audit v2 正式测量（修订号 23，v0.1.44.1，Q3 ×5，加测到 ×10）

## 结论

- **Q3/Opus = 0.830，高于判据 0.8**：Q3（IQ3_XXS）×5 罚后 **0.7233 ± 0.1458**（罚前 0.7394，比值 0.849；平均 11.7 分钟累计工作时间、generated 60,735、工具调用 29.8 次）；Opus 5.5 medium ×3 **0.8714 ± 0.0390**（平均 2.5 分钟墙钟、output 16,875、工具调用 6.3 次）。两边时间口径不同：Q3 为累计工作时间，Opus 为墙钟。按场景规则，比值 ≥ 0.8 先按"一切正常"判据评估，再决定是否加难，不当成场景缺陷（见"第 4 步判据初评"与"独立评估"）。加测到 10 次的补充结果见"加测到 10 次"。
- **差距主要来自一次异常实例**：A2 只有 0.480，原因是它对 25 个 Request 范围外的 source 写了审查行，上游计分器对每条报 `requirement-source-unexpected`（共 25 条），并把每条记为多出的失败干净用例（`extraFailedCleanCases` 25，`cleanAcceptanceRate` 0.589）。25 条里只有 7 条在 issue 内：01:3 Status、01:11 Governing requirements、01:13 暂存文件范围、01:57 / 02:52 blockers、01:61 / 02:56 validation evidence。另 18 条的 source 是 `src/dispatch/*.mjs`（15 个）和 `tests/dispatch/*.mjs`（3 个）文件本身，内容是逐个文件写"在 issue 授权范围内"。也就是说，Q3 把提交授权范围检查当成了要审查的要求。其余 4 次在 0.727–0.847；去掉 A2，Q3 均值 0.784（平均 11.6 分钟、generated 59,442、工具调用 31.8 次），比值约 0.90。这是 Q3 自身的行为，不是计分噪声，正式分不剔除。
- **区分度来自少数用例**：40 个问题用例中没有 Q3 与 Opus 都 0 命中的用例。Q3 落后集中在 G1#7（provider.load 合同不确定，Q3 0/5、Opus 1/3）、合并用例 02:23+spec:12（redactManifestEvent，2/5 对 3/3）、G2#16（formatRouteToken，3/5 对 3/3）和 01:43+spec:53（restore 合同，4/5 对 3/3）。其余 34 个（按 Gate 分别计）双方都是全部命中。
- **SD 大，单次分数没有意义**：Q3 5 次 SD 0.146（0.480–0.847），均值标准误约 0.065，比值约 ±0.08；回答不了"0.80 还是 0.85"。不满足调参 SD 标准（≤ 0.068，r8 尺度阈值待用户定）。
- **5 个 Q3 实例全部有效**：complete、终态 ready、0 压缩、启动上下文 SHA 一致；会话检查 6 条标记全部无害。Opus 3 次会话也无异常。加测的 5 次同样全部有效。
- **加测到 10 次（补充，不取代正式值）**：Q3 ×10 罚后 **0.7670 ± 0.1102**，Q3/Opus **0.880**（平均 11.6 分钟、generated 59,618、工具调用 32.3 次）。新增 5 次是 0.8108 ± 0.0362，没有出现 A2 那样的范围外审查行。比值在 0.8–0.9 之间，结论不变，见"加测到 10 次"。
- **v2 是去重版，不是加难版**："加难最多两版"的配额已用 0/2。按独立评估与 Main 的综合意见，下一步出加难版 v3，v2 不定稿（见"独立评估"）。
- **适用范围**：只对 rtx3080ti、IQ3_XXS、Strata 0.1.44.1、Codex 0.162.0、effort high、评分 r8.3、修订号 23（答案键 `0f02cf43…`）成立。分数不与 Commit Audit v1 或其他场景直接比较。

## 运行

- 冻结：a1ed615（修订号 23）；计划与 p基准：db03be2，计划 `benchmarks/reviewer-suite-v1/commit-audit-v2-iq3_xxs-2026-10-17-v0.1.44.1/plan.json`，运行计划正文存档 `data/run-plan.md`。
- Q3：2026-10-17 12:10–13:11，批 A 3 次、批 B 2 次（每批一次 prepare、一次冷加载），ARW/Codex 运行层，测量说明 `measurement-note-commit-audit.txt`（不限时），启动提示与压缩提示按计划核对 SHA。
- 参考：Opus 5.5 medium ×3（2026-10-18 09:13–09:21）、Haiku 5.5 high ×5（2026-10-17），都用 Claude Code 无头 `claude -p`（safe-mode/restricted、Bash 沙箱、工作目录在工程外），与 Q3 同一份测量说明。
- 计分：评分 r8.3。Q3 与 Opus 的候选先经盲裁，再由 `final.py` 调用上游 `score-completed --adjudication`；Haiku 不盲裁，只给机械区间并用于 p基准。

## 逐实例

Q3（token 来源：Strata 引擎日志中本次派发到下一次派发之间的一段；API usage 只作诊断。分钟为累计工作时间。工具调用数来自会话记录）：

| 次 | 批 | 分（罚后） | 罚前 | r | T | 分钟 | read | reused | generated | 工具调用 | 引擎入/出 tok/s | 任务入/出 tok/s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | A1 | 0.847 | 0.847 | 0 | 177 | 13.6 | 47,306 | 1,482,264 | 69,672 | 26 | 1,352 / 94.0 | 58.0 / 85.4 |
| 2 | A2 | 0.480 | 0.480 | 0 | 176 | 12.1 | 62,900 | 1,251,353 | 65,906 | 22 | 1,688 / 97.2 | 86.7 / 90.9 |
| 3 | A3 | 0.727 | 0.808 | 76 | 156 | 12.1 | 68,279 | 1,851,443 | 62,536 | 34 | 1,482 / 93.1 | 93.7 / 85.9 |
| 4 | B1 | 0.739 | 0.739 | 0 | 115 | 9.7 | 58,088 | 1,382,893 | 47,619 | 30 | 1,464 / 94.4 | 99.7 / 81.8 |
| 5 | B2 | 0.824 | 0.824 | 0 | 136 | 11.1 | 55,244 | 2,020,085 | 57,941 | 37 | 1,284 / 94.7 | 83.0 / 87.1 |

r 为格式罚计数（A3 的 76 处是 `lines` 写成标量，按可修复项修复后计分并罚分）；T 为计分器读到的定位数。A3 的 r 口径：采用修复记录的修复处数 76（每个 evidence 对象一处），不用计分器的 71（`review-row-invalid` 按报告行计，一行可有多个标量 evidence）。理由：格式罚规则把 r 定义为全部格式错误数，可修复项按修复处计入（`format_penalty.instance_errors` 的口径）。两种口径的 p 都远超 2·p基准，f 都在 0.1 封顶，罚后分相同。

Opus medium 参考（token 来源：`claude -p` stream-json 的 `result.usage`；分钟为墙钟时间；工具调用数为 stream 中的 `tool_use` 块数）：

| 实例 | 分 | r | T | 分钟 | input | cache 写 | cache 读 | output | 工具调用 | 费用 USD |
|---|---|---|---|---|---|---|---|---|---|---|
| opus-1 | 0.837 | 0 | 128 | 2.2 | 14 | 61,778 | 211,588 | 15,559 | 6 | 0.848 |
| opus-2 | 0.914 | 0 | 161 | 2.7 | 14 | 55,775 | 245,073 | 16,742 | 6 | 0.83 |
| opus-3 | 0.863 | 0 | 161 | 2.6 | 16 | 61,003 | 277,417 | 18,324 | 7 | 0.91 |

Haiku-high 机械区间（只用于 p基准和参考，不计入比值；上界 = 关联全 matched、键外全 supported，下界 = 全 not-matched/unsupported；token 来源同 Opus）：

| 实例 | 上界 | 下界 | r | T | 分钟 | output | 工具调用 | 合并不一致 |
|---|---|---|---|---|---|---|---|---|
| haiku-1 | 0.810 | 0.000 | 0 | 152 | 5.7 | 88,156 | 19 | 1 |
| haiku-2 | 0.821 | 0.000 | 0 | 156 | 5.6 | 76,712 | 15 | 1 |
| haiku-3 | 0.885 | 0.000 | 0 | 144 | 5.8 | 82,028 | 17 | 0 |
| haiku-4 | 0.856 | 0.000 | 0 | 151 | 6.6 | 90,555 | 25 | 1 |
| haiku-5 | 0.860 | 0.000 | 0 | 160 | 4.6 | 62,792 | 15 | 0 |

## 评估

### 盲裁

- 单个 Opus high 盲裁决者（无模型身份、批次和分数信息），只读 brief（sha256 `14bf444d…`，内含裁决口径原文 sha256 `d70bf946…`）、候选池和只读视图。池 p1 共 303 项（41 组）：关联候选 279 项，发现候选 24 项；来源为 Q3 A、B 和 Opus 1–3。第一轮决定后没有第二轮候选。
- 结果：279 项关联候选全部 `matched`；24 项发现候选全部补关联到所列的唯一问题用例（`problem-N`），0 项 `unsupported`、`supported`、`false-positive`。决定文件 sha256 `32a1cd12…`，存档 `data/adjudication/`。
- 盲裁员自报的难判项：G21 全组（期望句为 uncertain 类 "No available contract establishes cleanup behavior when `renameTemporary` fails"，finding 都直接判 gap；按 ARW 语义裁决只看是否同一缺陷，结果类别由计分处理，判 matched）；G11 中以 uncertain 报 `redactManifestEvent` 的 4 项和以"`auth.driver.token` 残留"角度报的 4 项（同一根因，判 matched，其中 p1-073 最勉强）；01:51 的两项附带提到只排顶层与 `localeCompare`，但都写明缺末尾 LF（按口径判 matched）；p1-259 对返回值描述不准，但核心缺陷正确。
- **matched 先验为什么高**：关联候选是计分器按要求行预筛出来的。finding 落在某个问题用例的要求行（或合并用例的任一侧）上，才成为该用例的关联候选，所以绝大多数本来就该 matched。这一点是从池结构推断的（同组候选都落在同一要求行），没有查计分器代码确认。
- **p1 的局限**：没有锚点，也没有第二个裁决者；全部 matched 本身证明不了裁决者会判 not-matched。每翻转 1 项，所在实例最多变动约 0.045；Opus 一侧的翻转只会让比值更高。
- **复评方案（采用独立评估第三节建议）**：加测的增量盲裁池 p2 同时作 p1 的独立复评。派一名新的 Opus high 盲裁决者，使用同一 brief（`14bf444d…`）；池中新候选、锚点和合成负例混在一起，按期望句分组乱序，来源、原判和合成标记都对裁决者隐藏。锚点 58 项，全部取自 p1：24 项发现候选全部；G11（10 项）、G21（7 项）全部；01:51 的两项 p1-158、p1-160；p1-259（已在发现候选内）；另在其余关联候选中分层随机抽 15 项（Q3 8、Opus 7，各取不同组）。锚点来源合计 Q3 40、Opus 18。合成负例 10 个：7 个错配（把一条真实 finding 配上另一组同 Gate 的期望句，且期望句的标识符不出现在 finding 中，预期 not-matched）；3 个 01:51 "只排顶层 / localeCompare" 类 finding，不提缺末尾 LF（2 个为关联候选，预期 not-matched；1 个为发现候选，预期 unsupported）。合成负例不进入任何实例的计分。
- **复评结果**：锚点 **58/58 与 p1 原判一致**（含 G11、G21 和发现候选全部）；合成负例 **10/10 识别**（7 个错配全部 not-matched，3 个只排顶层类分别为 not-matched、not-matched、unsupported）。复评裁决者自报的难判项与 p1 相同：G21 类（uncertain 期望句、finding 判 gap）、G11 类（`auth.driver.token` 残留角度），并说明了按"同一缺陷、结果类别交计分"判 matched 的理由。p2 池共 255 项，sha256 `c5d8c4af…`；决定文件 sha256 `dcad9e96…`，存档在 `data/adjudication/`，锚点与负例核对见 `p2-check.json`。

### 合并用例两侧一致性

29 对合并用例（同一缺陷在 issue 与 spec 两侧各一行）两侧结论不一致的对数：Q3 5 次全部 0（加测 5 次也全部 0）；Opus 3 次全部 0；Haiku 5 次中 3 次各 1 对（都是 01:30+spec:59，gap/satisfied）。

### 会话检查

- Q3（5 个实例的会话记录）：全部 complete、state idle、终态 `{"status":"ready"}`、0 压缩，启动上下文（base_instructions、developer@2、user@3、user@6）SHA 5 次一致，交接都在。标记 6 条全部无害：A1 #17/#18/#20 为 `node` 探测被误标为环境查询；A3 #28、B1 #27、B2 #28 为 `node` 子进程 spawn `git` 被沙箱以 EPERM 拒绝（命令未越界执行）。B1 交接后有 2 条中间 assistant 文本，不影响交付，也不算违反测量说明的 "Do not send any mid-task message"。这些文本是 Codex 回合内的进度说明：不结束回合、不等待回复，ARW 只取回合终态消息交给 Main。测量说明禁止的是中途向 Main 发消息、等待回复后再继续。这是按运行层机制作的判断；ARW 运行层是否把这类文本交给 Main，没有另做探针。没有越界写入或禁止来源访问。
- Opus 与 Haiku（无头运行，`data/ref-inspect.json`）：隔离检查清洁（隔离副本中无答案键、judgment、凭据、`.state`）；工具调用参数中无工程目录、答案键或凭据路径；文件改动只有报告文件一处；结果都是 `success`。Opus 3 次无工具错误；Haiku 有 4 个无害的工具错误（haiku-1 多传 `workdir` 参数、自检脚本非零退出；haiku-3、haiku-4 读不存在的文件）。

### 格式罚与 p基准

- p基准（Haiku-high ×5，已在 db03be2 登记于 `benchmarks/reviewer-suite-v1/format-baseline.json`，存档 `format-baseline/commit-audit-v2/`）：sumR 0、sumT 763，pBase 0.0131062（floor），bootstrap 90% 区间 [0.01277, 0.01346]。
- Q3 只有 A3 被罚：76 处 `lines` 写成标量（可机械修复），修复副本计分 0.808，罚后 0.727。r 口径见"逐实例"表注（采用修复处数 76，计分器按行计为 71，两者罚后分相同）。其余 Q3 与 Opus 的 r 都是 0，罚前分等于罚后分；加测 5 次的 r 也都是 0。

## 逐用例命中

由 `data/scripts/report_data.py` 从各来源 `score-final.json` 的 `caseScores` 生成（命中 = 得分 > 0；Q3 为 5 次、Opus 为 3 次；编号 G1/G2 为 Gate 1/2 的 scope，用例序号按 `expected.json` 从 0 起；合并用例在两个 Gate 各出现一次）：

| 用例 | 合并 | Q3 命中 | Q3 均分 | Opus 命中 | Opus 均分 | 期望句 |
|---|---|---|---|---|---|---|
| G1#0 | 01:7+spec:27 | 5/5 | 0.89 | 3/3 | 0.96 | The public dispatch entry omits the executor surface. |
| G1#1 |  | 5/5 | 0.94 | 3/3 | 0.98 | The capacity test covers only a value below the limit and omits the equality boundary. |
| G1#2 |  | 5/5 | 0.95 | 3/3 | 0.95 | `chooseDeparture` reads the host-local hour instead of the UTC hour. |
| G1#3 | 01:28+spec:41 | 5/5 | 0.90 | 3/3 | 0.96 | `emitPlanCreated` emits before the storage operation completes. |
| G1#4 |  | 5/5 | 0.95 | 3/3 | 0.93 | Duplicate detection trims raw keys but does not apply `normalizeRouteKey` (NFKC and upperc |
| G1#5 | 01:30+spec:59 | 5/5 | 0.90 | 3/3 | 0.91 | parseRetryCount treats the retry maximum as a count of allowed values and rejects the requ |
| G1#6 |  | 5/5 | 0.86 | 3/3 | 0.92 | `createDispatchPlan` sorts the caller-owned stop list in place. |
| G1#7 |  | 0/5 | 0.00 | 1/3 | 0.30 | No available provider contract establishes that `provider.load()` returns the configured a |
| G1#8 | 01:20+spec:55 | 5/5 | 0.85 | 3/3 | 0.97 | executeAuthorizedPlan invokes dispatch before checking authorization. |
| G1#9 | 01:43+spec:53 | 4/5 | 0.73 | 3/3 | 1.00 | No available contract establishes what `restore` returns after a partial write. |
| G1#10 | 01:49+spec:26 | 5/5 | 0.95 | 3/3 | 1.00 | `withinVehicleCapacity` uses a strict less-than comparison and rejects the inclusive limit |
| G1#11 |  | 5/5 | 0.95 | 3/3 | 1.00 | `canPlanRoute` accepts either scope or ownership instead of requiring both. |
| G1#12 |  | 5/5 | 0.98 | 3/3 | 0.96 | `serializePlan` selects a formatter mode that leaves the JSON document without the require |
| G1#13 | 02:22+spec:17 | 5/5 | 0.86 | 3/3 | 0.95 | The announcement failure branch returns without removing the already stored manifest. |
| G1#14 | 02:23+spec:12 | 2/5 | 0.39 | 3/3 | 0.73 | `redactManifestEvent` reuses token redaction and leaves other nested authentication creden |
| G1#15 | 02:29+spec:46 | 5/5 | 0.97 | 3/3 | 1.00 | `serializeManifestRecords` joins records with LF but omits the terminal LF. |
| G1#16 | 02:30+spec:45 | 5/5 | 0.97 | 3/3 | 1.00 | `orderManifestGroups` sorts destinations in descending order. |
| G1#17 |  | 5/5 | 0.79 | 3/3 | 0.93 | `publishManifest` stores the manifest before validating its entries. |
| G1#18 | 02:46+spec:71 | 5/5 | 0.91 | 3/3 | 0.90 | `retryPublication` retries every thrown error without checking whether it is transient. |
| G1#19 | 02:48+spec:22 | 5/5 | 0.95 | 3/3 | 0.94 | `coalescePackages` deduplicates each group independently and retains duplicates across gro |
| G2#0 | 01:49+spec:26 | 5/5 | 0.90 | 3/3 | 0.96 | canAssignAllPackages delegates the equality boundary to a strict capacity predicate and re |
| G2#1 |  | 5/5 | 0.94 | 3/3 | 0.98 | `toStableJson` sorts only top-level keys and leaves nested object order unchanged. |
| G2#2 | 02:23+spec:12 | 2/5 | 0.39 | 3/3 | 0.73 | `redactManifestEvent` reuses token redaction and leaves other nested authentication creden |
| G2#3 | 01:20+spec:55 | 5/5 | 0.86 | 3/3 | 0.97 | Authorized execution invokes dispatch before it can reject the caller. |
| G2#4 | 02:22+spec:17 | 5/5 | 0.91 | 3/3 | 0.95 | The failure branch does not remove the stored manifest. |
| G2#5 | 02:48+spec:22 | 5/5 | 0.96 | 3/3 | 0.94 | `coalescePackages` deduplicates only within each group. |
| G2#6 |  | 5/5 | 0.44 | 3/3 | 0.51 | No available contract establishes cleanup behavior when `renameTemporary` fails. |
| G2#7 | 01:7+spec:27 | 5/5 | 0.89 | 3/3 | 0.96 | The public entry does not export `executor.mjs`. |
| G2#8 |  | 5/5 | 0.92 | 3/3 | 0.92 | `partitionUrgentStops` removes elements from the supplied list with `splice`. |
| G2#9 | 01:28+spec:41 | 5/5 | 0.90 | 3/3 | 0.96 | `emitPlanCreated` emits before awaiting storage. |
| G2#10 | 02:30+spec:45 | 5/5 | 0.99 | 3/3 | 1.00 | `orderManifestGroups` orders destinations descending. |
| G2#11 | 02:29+spec:46 | 5/5 | 0.99 | 3/3 | 1.00 | `serializeManifestRecords` omits the final LF. |
| G2#12 |  | 5/5 | 0.83 | 3/3 | 0.92 | `authorizeRouteBatch` computes every route ownership result but returns only the first res |
| G2#13 | 01:43+spec:53 | 4/5 | 0.73 | 3/3 | 1.00 | The available adapter contract does not define the result returned by `restore`. |
| G2#14 |  | 5/5 | 0.94 | 3/3 | 0.89 | The publication test imports the public operation but executes the internal publisher dire |
| G2#15 | 01:30+spec:59 | 5/5 | 0.90 | 3/3 | 0.91 | parseRetryCount derives only three allowed values from the inclusive maximum and rejects t |
| G2#16 |  | 3/5 | 0.53 | 3/3 | 0.90 | formatRouteToken bypasses the route-key normalizer while using the destination normalizer. |
| G2#17 | 02:46+spec:71 | 5/5 | 0.91 | 3/3 | 0.87 | `retryPublication` does not inspect the transient marker before retrying. |
| G2#18 |  | 5/5 | 0.96 | 3/3 | 1.00 | `scopeAllowsPlan` uses prefix matching and accepts scopes such as `routes:plan-admin`. |
| G2#19 |  | 5/5 | 0.97 | 3/3 | 1.00 | `retryAfterDelay` enforces a minimum of 2000 milliseconds instead of a maximum. |

干净用例中得分 < 1 的（含部分扣分；下表"失分次数"是得分 < 1 的次数）：

| 干净用例 | 合并 | Q3 失分次数 | Q3 均分 | Opus 失分次数 | Opus 均分 | 期望句 |
|---|---|---|---|---|---|---|
| G1c#0 | 01:40+spec:16 | 5/5 | 0.71 | 3/3 | 0.88 | The implementation satisfies: savePlan validates a plan before the first persistent write. |
| G1c#5 | 01:33+spec:29 | 3/5 | 0.90 | 0/3 | 1.00 | The implementation satisfies: `previewPlan` returns a dry-run result without invoking stor |
| G1c#7 |  | 5/5 | 0.75 | 3/3 | 0.77 | The implementation satisfies: The invalid-storage test asserts that validation failure per |
| G1c#12 |  | 1/5 | 0.91 | 1/3 | 0.85 | The implementation satisfies: `selectActiveClaims` excludes claims before their start and  |
| G1c#13 |  | 1/5 | 0.97 | 3/3 | 0.79 | The implementation satisfies: `checksumPlan` hashes the bytes returned by the plan seriali |
| G1c#14 |  | 5/5 | 0.35 | 3/3 | 0.33 | The implementation satisfies: Connect dispatch manifest publication through the public dis |
| G1c#18 | 02:27+spec:67 | 5/5 | 0.81 | 3/3 | 0.96 | The implementation satisfies: `chunkManifest` limits every non-empty chunk to the configur |
| G1c#19 |  | 5/5 | 0.77 | 1/3 | 0.97 | The implementation satisfies: Under the Manifest Store contract, `publishWithAnnouncement` |
| G1c#21 | 02:35+spec:56 | 1/5 | 0.93 | 0/3 | 1.00 | The implementation satisfies: `publicationResult` returns structured success and failure v |
| G1c#24 |  | 2/5 | 0.93 | 0/3 | 1.00 | The implementation satisfies: `publicationRetryBudget` is two attempts. |
| G1c#26 | 02:44+spec:51 | 5/5 | 0.65 | 3/3 | 0.88 | The implementation satisfies: `groupByDestination` groups records using normalized destina |
| G1c#28 | 02:47+spec:15 | 1/5 | 0.91 | 0/3 | 1.00 | The implementation satisfies: `preserveManifestDriver` trims driver labels without changin |
| G2c#0 |  | 2/5 | 0.82 | 0/3 | 1.00 | The implementation satisfies: Stop ordering uses descending priority followed by ascending |
| G2c#1 |  | 5/5 | 0.59 | 3/3 | 0.77 | The implementation satisfies: Publication audit records include action, actor, and timesta |
| G2c#5 | 02:47+spec:15 | 2/5 | 0.82 | 2/3 | 0.70 | The implementation satisfies: Driver labels are trimmed without changing their letter case |
| G2c#7 |  | 5/5 | 0.83 | 3/3 | 0.89 | The implementation satisfies: Under the Manifest Store contract, valid manifest publicatio |
| G2c#9 |  | 3/5 | 0.88 | 3/3 | 0.71 | The implementation satisfies: Window membership includes both the declared start and end h |
| G2c#11 | 01:33+spec:29 | 1/5 | 0.97 | 2/3 | 0.89 | The implementation satisfies: Plan previews return without touching persistent storage. |
| G2c#21 |  | 2/5 | 0.96 | 1/3 | 0.97 | The implementation satisfies: `toStableJson` uses two-space indentation and one terminal L |
| G2c#23 | 02:44+spec:51 | 5/5 | 0.62 | 3/3 | 0.83 | The implementation satisfies: Destination grouping uses normalized keys and copied records |
| G2c#25 | 01:40+spec:16 | 5/5 | 0.71 | 3/3 | 0.88 | The implementation satisfies: Plan persistence completes validation before any write. |
| G2c#26 | 02:35+spec:56 | 1/5 | 0.93 | 0/3 | 1.00 | The implementation satisfies: Successful publication results and failed publication result |
| G2c#28 |  | 5/5 | 0.57 | 3/3 | 0.71 | The implementation satisfies: Serialized plan parsing returns structured success or failur |
| G2c#31 |  | 5/5 | 0.50 | 3/3 | 0.62 | The implementation satisfies: Stops at the vehicle weight limit remain in the accepted par |
| G2c#32 | 02:27+spec:67 | 5/5 | 0.81 | 3/3 | 0.96 | The implementation satisfies: Manifest chunks never exceed their configured maximum size. |
| G2c#36 |  | 5/5 | 0.56 | 3/3 | 0.56 | The implementation satisfies: Route keys are normalized with NFKC before trimming and uppe |

- 干净用例的部分分多数来自证据覆盖：模型判 satisfied 但只引用了期望证据的一部分，不是误报。例如 G1c#14（Q3 均分 0.35、Opus 0.33）：A1 引全了期望集合，得 0.893；其余 7 次只引了 `index.mjs` 与 `publisher.mjs` 中的部分行，得 0.208–0.400。A2 的 25 个多出失败干净用例不在本表（它们不是答案键内的用例）。
- **没有双 0 用例**。最低的 G1#7（"No available provider contract establishes that `provider.load()` returns the configured …"）Q3 0/5、Opus 1/3，属于 uncertain 类（需要指出合同缺失）；Opus 能命中，说明可以从 Input 推出。

## 偏离

1. **Q3 A 首次启动失败**：队列脚本预先建了 run 目录，`arw_measure` 拒绝已存在的目录；当时未加载模型、租约 free。修脚本后重开，失败目录保留为 `A-failed-mkdir`，不计入样本。
2. **安全验收沿用 rtx3080ti 现有证据**（`reports/v0.1.40.1/current-safety-gate/report-directory-workaround/summary.md`：原生沙箱 8 类外部写入拒绝、15 个审批用例符合预期）。v2 补丁只改夹具、答案键与 conformance 断言，不改运行层和权限生成器，与 Spec Readiness v4.2、Code Spec v5 的做法相同；本次没有重跑安全探针。
3. **运行层不同**：Opus、Haiku 走 Claude Code 无头运行，Q3 走 ARW/Codex。两者用同一份冻结测量说明和同一夹具，但工具集、系统提示和交接方式不同，比值包含运行层差异。
4. **A3 格式修复**：A3 的 76 处标量 `lines` 按修复规则在副本中补成数组后计分，并计入 r = 76 罚分（修复记录 `data/runs/A/review-3.jsonl.changes.json`）。
5. **Q3 A2 的 token 记录**：记录脚本在 results.json 写入 token 字段前读取，得到空值；按引擎日志段补算（read 62,900 / reused 1,251,353 / generated 65,906）。
6. **Opus 跑在 Q3 之后约 20 小时**：Q3 完成时额度判定为"不建议"，Opus ×3 到 2026-10-18 才运行；夹具、测量说明与计分版本不变。

## 未验证项

- 评分可复现：除确定性重算外（`final.py` 对每个来源连跑两次上游计分并断言一致），已由 p2 第二裁决者复评（锚点 58/58、负例 10/10）。复评仍只有一名裁决者，使用同一 brief、同一模型档。p1 中的 not-matched 能力只靠合成负例检验，因为 p1 原判里没有 not-matched 可作锚点。
- 本次没有重跑安全探针（见偏离 2）。
- 判定按原定 5 次进行；10 次结果只作补充（见"加测到 10 次"）。
- A2 口径敏感性表中后两种口径是按计分公式手算的（失败反例权重和格式罚公式），没有用计分器重跑。

## 第 4 步"一切正常"判据初评

本节是收尾 worker 的初步评估，2026-10-18 按独立评估修订：第一条改为成立；第四条按 p2 复评结果改为成立。最终意见见"独立评估"。

| 判据 | 初评 | 依据 |
|---|---|---|
| Opus 基准明显高于 Q3 | 成立 | Opus 0.871 对 Q3 0.723，差 0.148，约 2.3 个 Q3 标准误。15 个 Opus×Q3 配对中 Opus 高 14 对（只有 A1 0.847 高于 opus-1 0.837），秩和精确单侧 p ≈ 2/56 ≈ 0.036；10 次时 30 对中 Opus 高 28 对。比值 0.830 ≥ 0.8 是区分度问题，不影响本条。 |
| 没有 Opus 与 Q3 都 0 命中且可疑的用例 | 成立 | 40 个问题用例无双 0；最低的 G1#7 Opus 1/3。干净用例的低分来自证据覆盖，不是双方一致误报。 |
| Q3 5 次会话全部有效 | 成立 | 全部 complete/ready、0 压缩、启动 SHA 一致、标记无害、引擎输出 93.1–97.2 tok/s（≥ 60）。A2 的范围外审查行是有效会话中的能力表现。 |
| 评分可复现（独立复评一致） | 成立（以 p2 复评为准） | 确定性重算一致；第二名 Opus high 盲裁决者复评 p1 锚点 58/58 一致，合成负例 10/10 识别（见"盲裁"）。复评只有一名裁决者，局限见"未验证项"。 |

初步看法：场景本身未见缺陷（无双 0、合并对一致、会话有效），但 Q3/Opus = 0.830 ≥ 0.8，按"加难最多两版"的规则需要决定是否加难；Q3 的主要失分模式（范围外审查行、uncertain 类合同用例、嵌套凭据脱敏）可作为加难方向的参考。

## 加测到 10 次

**目的与计划**：按测量规则「空闲时加测」，GPU 空闲时把 Q3 有效实例从 5 次加到 10 次，降低均值和 SD 的随机性。目标 10 次在看到加测结果前写定，见 `data/run-plan.md`「加测计划」。判定仍按原定 5 次，本节只作补充。

**运行**：2026-10-18 09:31–10:32，批 C 3 次、批 D 2 次，每批一次 prepare、一次冷加载。条件与 A/B 完全相同：同一 plan.json 和脚本，Strata 0.1.44.1，effort high；服务日志中 `budget 8192 (max 24576)` 生效、无 `budget 4096`；启动提示、压缩提示与测量说明的 SHA 已核对；C 批 preflight 与 A 批逐项相同（只差路径和 ID）。5 次全部有效，没有补跑。队列结束时停模型、归还租约（health free/null）。

**结果**（token 来源与 A/B 相同：引擎日志中本次派发到下一次派发之间的一段；分钟为累计工作时间）：

| 次 | 批 | 分（罚后） | 罚前 | r | T | 分钟 | read | reused | generated | 工具调用 | 引擎入/出 tok/s | 任务入/出 tok/s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | A1 | 0.847 | 0.847 | 0 | 177 | 13.6 | 47,306 | 1,482,264 | 69,672 | 26 | 1,352 / 94.0 | 58.0 / 85.4 |
| 2 | A2 | 0.480 | 0.480 | 0 | 176 | 12.1 | 62,900 | 1,251,353 | 65,906 | 22 | 1,688 / 97.2 | 86.7 / 90.9 |
| 3 | A3 | 0.727 | 0.808 | 76 | 156 | 12.1 | 68,279 | 1,851,443 | 62,536 | 34 | 1,482 / 93.1 | 93.7 / 85.9 |
| 4 | B1 | 0.739 | 0.739 | 0 | 115 | 9.7 | 58,088 | 1,382,893 | 47,619 | 30 | 1,464 / 94.4 | 99.7 / 81.8 |
| 5 | B2 | 0.824 | 0.824 | 0 | 136 | 11.1 | 55,244 | 2,020,085 | 57,941 | 37 | 1,284 / 94.7 | 83.0 / 87.1 |
| 6 | C1 | 0.759 | 0.759 | 0 | 187 | 11.2 | 81,234 | 1,627,654 | 53,760 | 36 | 1,592 / 93.1 | 121.0 / 80.1 |
| 7 | C2 | 0.820 | 0.820 | 0 | 146 | 12.2 | 49,335 | 2,208,918 | 64,032 | 35 | 1,123 / 94.3 | 67.2 / 87.2 |
| 8 | C3 | 0.792 | 0.792 | 0 | 136 | 11.0 | 63,734 | 2,483,845 | 55,293 | 36 | 1,260 / 92.7 | 96.7 / 83.9 |
| 9 | D1 | 0.834 | 0.834 | 0 | 128 | 10.6 | 64,827 | 1,632,646 | 52,626 | 28 | 1,342 / 96.0 | 102.0 / 82.8 |
| 10 | D2 | 0.850 | 0.850 | 0 | 134 | 12.6 | 50,416 | 2,164,445 | 66,793 | 39 | 1,236 / 94.8 | 66.7 / 88.4 |

| 口径 | n | 均值 ± SD | 标准误 | 罚前均值 | Q3/Opus | 罚前比值 | 平均分钟 | 平均 generated | 平均工具调用 |
|---|---|---|---|---|---|---|---|---|---|
| 正式 5 次（A、B） | 5 | 0.7233 ± 0.1458 | 0.0652 | 0.7394 | 0.830 | 0.849 | 11.7 | 60,735 | 29.8 |
| 加测 5 次（C、D） | 5 | 0.8108 ± 0.0362 | 0.0162 | 0.8108 | 0.930 | 0.930 | 11.5 | 58,501 | 34.8 |
| 全部 10 次 | 10 | 0.7670 ± 0.1102 | 0.0349 | 0.7751 | 0.880 | 0.889 | 11.6 | 59,618 | 32.3 |

- 新增 5 次在 0.759–0.850 之间，r 都是 0，`extraFailedCleanCases` 都是 0：没有出现 A2 的范围外审查行。加测 5 次与正式 5 次的均值差（0.811 对 0.723）主要来自 A2；正式 5 次去掉 A2 是 0.784。
- 10 次 Q3/Opus = 0.880，在 0.8–0.9 之间。按独立评估的处理规则（10 次比值明显低于 0.8，例如 < 0.78，才把"停止加难、以 v2 定版"交用户复核），结论不变：仍出 v3 加难版。
- 10 次 SD 0.110，仍不满足调参 SD 标准（≤ 0.068）。
- 速度：新增 5 次引擎输出 92.7–96.0 tok/s，全部 ≥ 60。已缓存输入比例 0.952–0.978，与 A/B（0.952–0.973）一致；分数与批内次序没有趋势。
- 10 次中仍未全部命中的问题用例（其余 34 个 Q3 10/10、Opus 3/3）：

| 用例 | 合并 | Q3 命中（10） | Q3 均分 | Opus 命中 | 期望句 |
|---|---|---|---|---|---|
| G1#7 |  | 0/10 | 0.00 | 1/3 | No available provider contract establishes that `provider.load()` returns the configured a |
| G1#9 | 01:43+spec:53 | 9/10 | 0.84 | 3/3 | No available contract establishes what `restore` returns after a partial write. |
| G1#14 | 02:23+spec:12 | 3/10 | 0.29 | 3/3 | `redactManifestEvent` reuses token redaction and leaves other nested authentication creden |
| G2#2 | 02:23+spec:12 | 3/10 | 0.30 | 3/3 | `redactManifestEvent` reuses token redaction and leaves other nested authentication creden |
| G2#13 | 01:43+spec:53 | 9/10 | 0.84 | 3/3 | The available adapter contract does not define the result returned by `restore`. |
| G2#16 |  | 6/10 | 0.53 | 3/3 | formatRouteToken bypasses the route-key normalizer while using the destination normalizer. |

**盲裁**：新 5 次共 187 个候选（C 110、D 77），在 p2 中与锚点、合成负例一起裁决（见"盲裁"）。关联候选全部 matched；发现候选中 8 项补关联到问题用例，C1 有 1 项裁为 `false-positive:clean-8`，D2 有 1 项裁为 `supported`（canPlanRoute 的 `||` 缺陷是真的，但该 finding 落在 spec:37 的要求行上，不对应本行用例），没有 unsupported。p1 决定沿用（锚点复评 58/58 一致）；加入新来源后，A/B/Opus 的计分逐项不变。没有第二轮候选。

**会话检查**（`inspect_session`，C/D 5 个会话的 actions.md、flagged.md 全文已读）：
- 5 次全部 complete、state idle、终态 `{"status":"ready"}`、0 压缩；启动上下文 SHA 与 A/B 一致。
- 标记共 10 条，全部无害：
  - C2 有 4 条、C3 有 1 条：`workdir` 路径拼错（重复了一段目录），命令因目录不存在被拒绝，没有执行；随后用正确目录重跑。
  - C2 另有 3 条：自检脚本中的 `'..'` 字符串字面量。
  - D1、D2 各 1 条：`node` 子进程 spawn 被沙箱以 EPERM 拒绝。
- 未标记但单列一项：C1 #29 的 python 自检脚本把 `cwd` 误算成根目录的上一级（`ca/`），在那里运行 `node` 探针。结果只记 exit code，没有显示输出；下一步自行改正。没有读到根外内容。
- D1 首次出现 guardian 子会话：auto_review 审批 1 次，guardian 在根内执行 `ls` 后放行。按原生设置这属于正常审批流程。
- C1、D1 交接后有中间 assistant 文本，判断同 B1。
- 没有越界写入，也没有访问禁止来源。

**偏离**：
1. `q3/post.py` 原来按 cwd 把会话对应到实例，D1 的 guardian 子会话 cwd 相同，覆盖了主会话的工具调用数（一度记为 1）。已改为跳过子 agent 会话，D 重新后处理，工具调用数改为 28。A/B/C 没有子会话，不受影响。token 按引擎日志段计算，已含 guardian 请求，不受影响。
2. 盲裁池按独立评估建议扩大，兼作复评（原计划为 12 个锚点）。

## 独立评估

### 评估结论（独立 Opus high 评估者，2026-10-18）

- "一切正常"基本成立：前三条判据成立；第四条"评分可复现"在评估时只部分成立（确定性重算一致，没有独立复评）。场景本身没有发现缺陷，不需要修。第四条现按 p2 复评结果改为成立（锚点 58/58、负例 10/10）。
- 建议出加难版 v3，v2 不定稿，也不记为区分度不足。理由如下：
  - v2 是去重版，"加难最多两版"的配额还一次没用。
  - 比值 0.830 ≥ 0.8，按规则下一步就是加难。Code Standards 是做过全面加难仍拉不开才停的，先例不适用。
  - 区分度弱的根源是内容太容易：40 个问题用例中 34 个 Q3 5/5 全中，检出率 0.80–0.89。比值低于 0.90 主要靠 A2 一次异常拉下来。
- A2 的 25 条范围外行，按现行规则每条计一个 0.25 的额外失败反例，不是重复计分，也没有叠加格式罚。这 25 条约扣 0.223；不算它们，A2 为 0.694。这是真实的能力差异（误读 Request 范围），不是噪声。
- 评估者提出两处口径可交用户定：
  - (a) 同源误读按 25 次扣分，与 r8.1"只扣一次"的思路是否一致；
  - (b) 18 条代码源行是否改计格式罚。
- 对报告提了 8 条修改：A2 描述、得分处补耗时、A3 的 r 口径、G1c#14 说明、存档对 `.tmp` 的依赖、敏感性分析、加难配额、盲裁预筛与复评方案。本次已全部改入，其中复评方案已经执行，就是 p2。

### Main 的综合意见

- 同意出 **v3 加难版**；**v2 不定稿**；加难配额已用 **0/2**。v3 的设计另行进行。
- A2 口径：**用户 10-18 定：维持现行**。范围外审查行每行计 0.25，各自计分，同源误读不合并。规则见 `.claude/rules/reviewer-suite.md`（提交 521f47d）：r8.1"只扣一次"只适用于同一行上的同一个错误被两条计分途径重复计入。v2 不做事后改分。
- 下表是 A2 三种口径的敏感性分析，只作参考。后两种口径按计分公式手算，未用计分器重跑：第 2 行把 18 条代码源行移出失败反例，计入格式罚 r = 18（T 176，f 在 0.1 封顶）；第 3 行把 25 条合计按 1 个失败反例计。

| 口径 | A2 | Q3 均值（5 次） | 比值（5 次） | Q3 均值（10 次） | 比值（10 次） |
|---|---|---|---|---|---|
| 现行（每行 0.25，用户 10-18 定维持） | 0.480 | 0.723 | 0.830 | 0.767 | 0.880 |
| 18 条代码源行改计格式罚 | 0.576 | 0.743 | 0.852 | 0.777 | 0.891 |
| 25 条合计按 1 个失败反例 | 0.694 | 0.766 | 0.879 | 0.788 | 0.905 |

三种口径下比值都 ≥ 0.8，不改变加难决定。

## 存档

`data/` 下存有本报告所需的数据。分数、裁决和逐实例明细不依赖 `.tmp/`。但重算需要冻结答案键与 ARW 物化副本，这一点并不完全独立：`data/scripts/` 中的脚本和 `score-input.json`、修复记录里的路径指向原 `.tmp/commit-audit/measure/` 运行目录。重建方法：用 `python3 -m tools.tuning.arw_dimension prepare --plan benchmarks/reviewer-suite-v1/commit-audit-v2-iq3_xxs-2026-10-17-v0.1.44.1/plan.json --out <目录>` 从冻结 manifest `manifest-commit-audit-v2.json`（含 `arw-patches/commit-audit-v2.patch`）重新物化，答案键在 `<目录>/arw/tests/fixtures/reviewer-capability/commit-audit-reviewer/expected.json`（sha256 `0f02cf43…`）；再把脚本和输入文件中的 `.tmp/.../q3/runs/<批>/arw` 换成该目录，报告路径按 `data/index.json` 换成 `data/runs/`。

- `data/runs/<A|B|C|D|opus-N>/`：Q3 与 Opus 的报告（`review-N.jsonl`，A3 附修复记录）、`score-final.json`、`candidates.json`、`score-input.json`、`metrics.json`；`data/index.json` 为实例 → 报告映射。
- `data/adjudication/`：brief、池 p1/p2、来源映射 key（p2 含锚点与合成负例标记）、盲裁决定、`p2-check.json`（锚点一致率与负例识别率）。
- `data/session-check/`：Q3 会话检查摘要与标记全文；`data/ref-inspect.json`：无头参考运行检查。
- `data/final.json`（正式分与 Haiku 区间）、`data/merge-consistency.json`、`data/run-plan.md`、`data/scripts/`（生成本报告的后处理脚本，原在 `.tmp/commit-audit/measure/`）。
- Haiku 报告与修复记录随 p基准存档在 `benchmarks/reviewer-suite-v1/format-baseline/commit-audit-v2/`。

明细：`summary.json`（逐实例速度、token、工具调用，40 个问题用例与干净用例的命中与均分；`extra10` 为加测到 10 次的逐实例、汇总与逐用例命中）。
