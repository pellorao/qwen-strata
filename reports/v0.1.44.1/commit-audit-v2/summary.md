# Commit Audit v2 正式测量（修订号 23，v0.1.44.1，Q3 ×5）

## 结论

- **Q3/Opus = 0.830，高于判据 0.8**：Q3（IQ3_XXS）×5 罚后 **0.7233 ± 0.1458**（罚前 0.7394，比值 0.849）；Opus 5.5 medium ×3 **0.8714 ± 0.0390**。按场景规则，比值 ≥ 0.8 先按"一切正常"判据评估，再决定是否加难，不当成场景缺陷（初评见"第 4 步判据初评"，最终判断待"独立评估"）。
- **差距主要来自一次异常实例**：A2 只有 0.480，原因是它对 25 条不属于 Request 范围的行（如 issue 的 Status、Governing requirements 等元数据行）写了审查行，计分器把每条记为多出的失败干净用例（`extraFailedCleanCases` 25，`cleanAcceptanceRate` 0.589）。其余 4 次在 0.727–0.847；去掉 A2，Q3 均值 0.784，比值约 0.90。这是 Q3 自身的行为，不是计分噪声，正式分不剔除。
- **区分度来自少数用例**：40 个问题用例中没有 Q3 与 Opus 都 0 命中的用例。Q3 落后集中在 G1#7（provider.load 合同不确定，Q3 0/5、Opus 1/3）、合并用例 02:23+spec:12（redactManifestEvent，2/5 对 3/3）、G2#16（formatRouteToken，3/5 对 3/3）和 01:43+spec:53（restore 合同，4/5 对 3/3）。其余 34 个（按 Gate 分别计）双方都是全部命中。
- **SD 大，单次分数没有意义**：Q3 5 次 SD 0.146（0.480–0.847），均值标准误约 0.065，比值约 ±0.08；回答不了"0.80 还是 0.85"。不满足调参 SD 标准（≤ 0.068，r8 尺度阈值待用户定）。
- **5 个 Q3 实例全部有效**：complete、终态 ready、0 压缩、启动上下文 SHA 一致；会话检查 6 条标记全部无害。Opus 3 次会话也无异常。
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

r 为格式罚计数（A3 的 76 处是 `lines` 写成标量，按可修复项修复后计分并罚分）；T 为计分器读到的定位数。

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
- **局限**：没有锚点，也没有第二个裁决者复评；全部 matched 意味着裁决没有排除任何候选，分数等于各候选按证据计分的结果。最勉强的 p1-073 来自 Opus（opus-1，用例 02:23+spec:12），改判 not-matched 只会降低 Opus 分、使比值更高，不改变比值 ≥ 0.8 的结论（未重算）。

### 合并用例两侧一致性

29 对合并用例（同一缺陷在 issue 与 spec 两侧各一行）两侧结论不一致的对数：Q3 5 次全部 0；Opus 3 次全部 0；Haiku 5 次中 3 次各 1 对（都是 01:30+spec:59，gap/satisfied）。

### 会话检查

- Q3（5 个实例的会话记录）：全部 complete、state idle、终态 `{"status":"ready"}`、0 压缩，启动上下文（base_instructions、developer@2、user@3、user@6）SHA 5 次一致，交接都在。标记 6 条全部无害：A1 #17/#18/#20 为 `node` 探测被误标为环境查询；A3 #28、B1 #27、B2 #28 为 `node` 子进程 spawn `git` 被沙箱以 EPERM 拒绝（命令未越界执行）。B1 交接后有 2 条中间 assistant 文本（非 send_message），不影响交付。没有越界写入或禁止来源访问。
- Opus 与 Haiku（无头运行，`data/ref-inspect.json`）：隔离检查清洁（隔离副本中无答案键、judgment、凭据、`.state`）；工具调用参数中无工程目录、答案键或凭据路径；文件改动只有报告文件一处；结果都是 `success`。Opus 3 次无工具错误；Haiku 有 4 个无害的工具错误（haiku-1 多传 `workdir` 参数、自检脚本非零退出；haiku-3、haiku-4 读不存在的文件）。

### 格式罚与 p基准

- p基准（Haiku-high ×5，已在 db03be2 登记于 `benchmarks/reviewer-suite-v1/format-baseline.json`，存档 `format-baseline/commit-audit-v2/`）：sumR 0、sumT 763，pBase 0.0131062（floor），bootstrap 90% 区间 [0.01277, 0.01346]。
- Q3 只有 A3 被罚：76 处 `lines` 写成标量（可机械修复），修复副本计分 0.808，罚后 0.727。其余 Q3 与 Opus 的 r 都是 0，罚前分等于罚后分。

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

- 干净用例的部分分多数来自证据覆盖：模型判 satisfied 但只引用了期望证据的一部分（例如 G1c#14 双方都只引了 `index.mjs` 与 `publisher.mjs` 中的部分行，Q3 0.35、Opus 0.33），不是误报。A2 的 25 个多出失败干净用例不在本表（它们不是答案键内的用例）。
- **没有双 0 用例**。最低的 G1#7（"No available provider contract establishes that `provider.load()` returns the configured …"）Q3 0/5、Opus 1/3，属于 uncertain 类（需要指出合同缺失）；Opus 能命中，说明可以从 Input 推出。

## 偏离

1. **Q3 A 首次启动失败**：队列脚本预先建了 run 目录，`arw_measure` 拒绝已存在的目录；当时未加载模型、租约 free。修脚本后重开，失败目录保留为 `A-failed-mkdir`，不计入样本。
2. **安全验收沿用 rtx3080ti 现有证据**（`reports/v0.1.40.1/current-safety-gate/report-directory-workaround/summary.md`：原生沙箱 8 类外部写入拒绝、15 个审批用例符合预期）。v2 补丁只改夹具、答案键与 conformance 断言，不改运行层和权限生成器，与 Spec Readiness v4.2、Code Spec v5 的做法相同；本次没有重跑安全探针。
3. **运行层不同**：Opus、Haiku 走 Claude Code 无头运行，Q3 走 ARW/Codex。两者用同一份冻结测量说明和同一夹具，但工具集、系统提示和交接方式不同，比值包含运行层差异。
4. **A3 格式修复**：A3 的 76 处标量 `lines` 按修复规则在副本中补成数组后计分，并计入 r = 76 罚分（修复记录 `data/runs/A/review-3.jsonl.changes.json`）。
5. **Q3 A2 的 token 记录**：记录脚本在 results.json 写入 token 字段前读取，得到空值；按引擎日志段补算（read 62,900 / reused 1,251,353 / generated 65,906）。
6. **Opus 跑在 Q3 之后约 20 小时**：Q3 完成时额度判定为"不建议"，Opus ×3 到 2026-10-18 才运行；夹具、测量说明与计分版本不变。

## 未验证项

- 盲裁没有锚点，也没有独立复评；"评分可复现"目前只由确定性重算支持（`final.py` 对每个来源连跑两次上游计分并断言一致，整份 `final.json` 两次运行逐项相同）。
- 本次没有重跑安全探针（见偏离 2）。
- Q3 只有 5 次；没有加测到 10 次，SD 与比值精度按 5 次估计。

## 第 4 步"一切正常"判据初评

本节是收尾 worker 的初步评估，不是最终判断。

| 判据 | 初评 | 依据 |
|---|---|---|
| Opus 基准明显高于 Q3 | 部分成立 | Opus 0.871 对 Q3 0.723，差 0.148，约 2.3 个 Q3 标准误；但比值 0.830 ≥ 0.8，去掉 A2 后约 0.90。Opus 3 次都高于 Q3 的 4/5 次，只有 A1（0.847）高于 opus-1（0.837）。 |
| 没有 Opus 与 Q3 都 0 命中且可疑的用例 | 成立 | 40 个问题用例无双 0；最低的 G1#7 Opus 1/3。干净用例的低分来自证据覆盖，不是双方一致误报。 |
| Q3 5 次会话全部有效 | 成立 | 全部 complete/ready、0 压缩、启动 SHA 一致、标记无害、引擎输出 93.1–97.2 tok/s（≥ 60）。A2 的范围外审查行是有效会话中的能力表现。 |
| 评分可复现（独立复评一致） | 部分成立 | 确定性重算一致；单裁决者、无锚点、无独立复评。279 项全 matched、24 项全补关联，裁决结论对分数的影响面小（见盲裁局限）。 |

初步看法：场景本身未见缺陷（无双 0、合并对一致、会话有效），但 Q3/Opus = 0.830 ≥ 0.8，按"加难最多两版"的规则需要决定是否加难；Q3 的主要失分模式（范围外审查行、uncertain 类合同用例、嵌套凭据脱敏）可作为加难方向的参考。

## 独立评估

（待填：Main 交独立 agent 评估"一切正常"是否成立、是否加难或冻结，Main 综合后写入此处。）

## 存档

`data/` 下存有本报告所需的全部数据，不依赖 `.tmp/`：

- `data/runs/<A|B|opus-N>/`：Q3 与 Opus 的报告（`review-N.jsonl`，A3 附修复记录）、`score-final.json`、`candidates.json`、`score-input.json`、`metrics.json`；`data/index.json` 为实例 → 报告映射。
- `data/adjudication/`：brief、池 p1、来源映射 key、盲裁决定。
- `data/session-check/`：Q3 会话检查摘要与标记全文；`data/ref-inspect.json`：无头参考运行检查。
- `data/final.json`（正式分与 Haiku 区间）、`data/merge-consistency.json`、`data/run-plan.md`、`data/scripts/`（生成本报告的后处理脚本，原在 `.tmp/commit-audit/measure/`）。
- Haiku 报告与修复记录随 p基准存档在 `benchmarks/reviewer-suite-v1/format-baseline/commit-audit-v2/`。

明细：`summary.json`（逐实例速度、token、工具调用，40 个问题用例与干净用例的命中与均分）。
