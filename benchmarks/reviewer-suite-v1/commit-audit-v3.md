# Commit Audit 能力场景 v3：相对 v2 的变更说明（修订号 24，2026-10-18 冻结）

v3 以补丁 [`arw-patches/commit-audit-v3.patch`](arw-patches/commit-audit-v3.patch) 提供（sha256 `0e0ffca8…`，26 个文件，含删除 `src/dispatch/policy.mjs` 与 base `config/dispatch-policy.json`），登记在 `source-snapshots/current/manifest-commit-audit-v3.json`（即 v2 的 `manifest-commit-audit-v2.json` 加上这一项）。补丁叠在 v2 补丁（修订号 23）之后，评分升级 `scoring-k.patch` 在物化时最后应用。冻结版是草稿经 3 轮审计后的末稿 v3.3。

答案键 `81796f46…` 在 `judgment/registry.json` 登记为 `all-B`（"29 个合并用例"），需评分 r8.3。分数只与修订号 24 比较，与修订号 23 及以前不可比。出题设计、推理链、比例、分层、停止条件核对见[设计说明](commit-audit-v3-design.md)；正式盲裁用冻结的 [brief](commit-audit-v3-brief.md)。

改动范围：

- **源码**（candidate）：
  - 8 个文件重写：`access`、`capacity`、`executor`、`manifest`、`publisher`、`queue`、`retry`、`schedule`；末尾新增 13 个函数：
    - 问题题：`stopsForDriver`、`routeDuration`、`locateStops`（queue）、`weighPackages`（capacity）、`pendingStops`（executor）、`orderedDestinationGroups`（manifest）、`sendDeliveryNotices`（publisher）；
    - 孪生题：`deliveredCount`（queue）、`driverWorkload`、`measuredVehicleLimit`（capacity）、`manifestRecipients`（manifest）、`routeDistance`、`departureMinute`（schedule）；
  - 4 个文件局部修改：`serialize`、`storage`、`telemetry`、`normalize`；
  - 删除孤立模块 `policy.mjs`；`serialize` 中 `stableTopLevel` 改名为 `withSortedKeys`（行号不变）；
  - `tests/dispatch/publish.test.mjs` 改为经公共入口。
- **文档**（base）：
  - 删除孤立的 `config/dispatch-policy.json`（与政策文档同名，易误导）；
  - 新增政策文档 `docs/dispatch/dispatch-policy.md`：33 条规则，10 节；第 28、29 条只约束 dispatch 记录或比较的值；Terms 节（第 30–33 条）用 "X means …" 定义 4 个术语；文档头写明"参考政策，不是要求清单，只适用于引用它的要求；同节内后一条覆盖前一条"；
  - 新增 `docs/dispatch/adapter-contracts.md`：Geocoder 与 Weighing 两节，各 2 条；
  - `docs/dispatch/storage-contract.md`：第 4 条改为 "resolves to the supplied manifest object itself"；追加 `store.get`、`store.remove` 两条；新增 "Plan Store Contract" 一节（5 条）。
- **要求行**：issue 改写 20 行（candidate 与 base 同步），spec 改写 21 行；行数和行号不变。
- **答案键**：
  - 换题、改写见下表；
  - `auditRecords` 按新证据重建；
  - 合并用例 29 对（正例 11、反例 18）。
- `SCENARIO_REVISIONS` 中 commit-audit-reviewer 由 23 改为 24。
- **conformance 测试**按新清单更新：
  - 单行字面量、多处证据、近邻清单（由生成脚本按答案键计算）；
  - `singleLineProblems.size <= 4`；
  - 计划 JSON 以 LF 结尾。

角色规则、交接、测量说明不改；范围外审查行沿用 v2 计法（每行 0.25，各自计分）。

## 起因

v2（修订号 23）正式测量 Q3 IQ3_XXS ×5 0.723±0.146、Opus medium ×3 0.871±0.039，比值 0.830，未达 < 0.8。加难按 [`scenario-design.md`](scenario-design.md)「难度设计」一条（第 7 行，2026-10-18 修订，用户已同意）：只提高已确认对被测模型有效的难度因素，确认方式为因素探针，或同类题至少 2 道、Q3 累计至少 6 次作答命中不超过 1/3 且 Opus 命中、审计排除歧义。旧的"加难后平均推理步数至少 +2"指标已由这次修订取代。

Eval4 §5 的建议：

- 替换 Q3 已 5/5 的字面量题：`orderManifestGroups`、`retryAfterDelay`、NDJSON LF、`scopeAllowsPlan`；
- 避免两模型都判 gap 的 uncertain 题（spec:23）；
- uncertain 改用"合同缺失 + 实现看似合理"型；
- 不引入清单外缺陷。

第 3 版的规则网络题两个模型都命中、用时超限，第 4 版改为按难度因素出题（加难方向独立意见"方案 1′"，Main 采纳；要点与停止条件见设计说明 §11）：(a) 合同可读但沉默、(b) 远处定义术语、(c) 调用形状不符或不点名实现。

## 用例替换（修订号 24 行号，与修订号 23 相同）

| 行 | 修订号 23 | 修订号 24 |
|---|---|---|
| 01:19 / spec:75 | 01:19 容量测试缺等号边界；spec:75 `retryAfterDelay` 最小值 | 合并：`nextRetryDelay` 真值判断，`retryAfter` 为 0 回退退避 |
| 01:20 / spec:55 | 先派发后鉴权 | `await` 作 `unlessForbidden` 实参先求值；01:20 行改为 "`executeAuthorizedPlan` rejects an unauthorized caller before invoking dispatch."（v3.2，审计 M1：原 "checks authorization before" 可字面判成立） |
| 01:21 | satisfied | (b) gap：`stopsForDriver` 只比较自身 `driver`，第 30 条 assigned driver 含 `reassignment` |
| 01:22 / spec:43 | satisfied（包裹重量合计） | satisfied 孪生（合并）：`writePlanAtomically` 先等 `writeTemporary` 持久再 rename（合同第 15 行） |
| spec:40 | satisfied | gap：`nextDispatchTime` 用本地小时（规则 10/12/13） |
| 01:23 | 取本地小时 | gap：移到禁发结束小时后未按规则 14 拒绝 |
| spec:74 | `formatRouteToken` 漏规范化 | (b) gap：送达通知发往原始 `phone`，第 33 条 contact phone 去空格与连字符 |
| 01:28 / spec:41 | gap：先发事件后存储 | uncertain：`onCommit` 时机无合同 |
| 01:29 | 未调 `normalizeRouteKey` | gap：身份无分隔拼接导致碰撞（规则 19/20） |
| spec:11 | 只排顶层 | (b) gap：路线时长只加 `serviceMinutes`，第 32 条 service time 另加 5 分钟 |
| 01:30 / spec:59 | 拒绝上界 3 | `Number()` 接受非十进制数字文本（规则 21/22） |
| 01:32 | 原地排序 | (b) gap：`pendingStops` 只排除 `delivered`，第 31 条 delivered 含 `handedOver` |
| spec:50 | 测试绕过公共入口 | gap：文本 `sequence` 被强制转换，违反规则 18 |
| 01:38 | provider 无合同（uncertain） | 保底 gap（调用形状）：`orderedDestinationGroups` 把 `Map` 传给按 `destination` 排序的助手，顺序不变 |
| 01:39 | satisfied（invalid-storage 测试） | satisfied 孪生：`routeDistance`，合同写明无路时拒绝 |
| 01:43 / spec:53 | 合并 uncertain：`restore` 无合同 | 拆开。01:43 (a) uncertain：`locateStops` 依赖 `lookup` 对未知地址的行为，合同未写；spec:53 (a) uncertain：`scale.read` 单位合同未写 |
| spec:38 | `splice` | gap：剩余分区用原始 `priority`，`'7'` 不在任何分区（规则 15/16） |
| 01:49 / spec:26 | 严格小于 | 克 / 千克换算后余量钳为 0，`> 0` 拒绝等号（规则 28/29） |
| 01:50 | 范围与所有权用"或" | `routes:admin` 只查自身范围（规则 3/4） |
| 01:51 / spec:73 | 01:51 缺末尾 LF；spec:73 前缀匹配 | 合并：暂停时仍保留 claim 范围（规则 4/5，"held scopes" 为定义术语） |
| 02:22 / spec:17 | 失败分支不删 | 删除 `store.get` 返回的副本，合同只删精确对象 |
| 02:23 / spec:12 | 漏删嵌套凭据 | 递归不进入数组，数组里的凭据保留（规则 23/24） |
| 02:29 / spec:46 | gap：NDJSON 缺末尾 LF | satisfied（近邻反例） |
| 02:30 / spec:45 | gap：降序 | satisfied（近邻反例，码元字典序）；v3.2（审计 M2）：spec:45 改为点名 "`orderManifestGroups` orders destination groups in ascending lexical order."，`orderManifestGroups` 参数标注改为 `{destination: string}[]`（同一行） |
| 02:37 | satisfied | gap：`labelDriver` 用 `Object.assign` 改写调用方 driver |
| 02:38 | satisfied | satisfied（改写为引用规则 9 的近邻反例） |
| 02:39 | 先存后校验 | `map(async)` + `every(Boolean)` 恒真 |
| 02:31 | satisfied（`auditFieldsPresent`） | satisfied 孪生：`manifestRecipients` 去空格与连字符；v3.2（审计 S2）行末加 "that has a `phone`"；v3.3（审计 M3）`manifestRecipients` 在同一行先滤掉没有字符串 `phone` 的条目，缺 `phone` 不再抛异常 |
| 02:45 / spec:14 | 合并 satisfied（失败遥测） | 拆开。02:45 satisfied 孪生：`departureMinute` 含 5 分钟停车；spec:14 原文不变，单独计分 |
| 02:46 / spec:71 | 不看 transient | 规则 27 覆盖规则 26，实现让 `retryAfter` 胜过显式 false |
| 02:48 / spec:22 | 只在组内去重 | 已见集合存原始 ID、过滤用规范化 ID |
| spec:23 | uncertain：rename 失败的清理无合同 | gap：plan store 合同规定 rename 被拒后字节锁定，锁定时 `discardTemporary` 只关闭不删除 |
| spec:24 | satisfied | satisfied（行与合同第 4 条改写，去掉"丢弃 `put` 解析值"的误读空间） |
| spec:35 | satisfied | 保底 gap（不点名实现）：计划哈希只排顶层键，嵌套字段顺序不同则哈希不同（行不点名实现）；`freezeDispatchPlan` 为正确实现 |
| spec:58 / spec:61 / spec:70 | satisfied | satisfied 孪生：`driverWorkload`（第 30 条，`\|\|` 回落）、`deliveredCount`（第 31 条）、`measuredVehicleLimit`（千克） |
| spec:52 | 只返回第一个结果 | `findIndex <= 0`，首条不归属时放行 |

- **保留**（行号与证据随源码重映射）：01:7+spec:27。
- **随题删除的旧缺陷已改回正确实现**：`formatRouteToken`、`createDispatchPlan`、`retryPublication` 循环、`freezeDispatchPlan`。

反例证据变更：

- 01:41/spec:31 → `retry.mjs:8,22`；
- spec:24 → `storage-contract.md:3,4`、`manifest.mjs:30`、`publisher.mjs:7`；
- spec:9 可选证据 → `schedule.mjs:1,5`；
- 02:38 → `publisher.mjs:17`、`retry.mjs:13,14,20`。

01:21 原反例（`planFailure`）随行改写删除；01:22+spec:43、01:39、02:31、02:45、spec:58、spec:61、spec:70 的原反例改写为孪生题。

## 合并用例（29 对）

正例 11 对：

| 合并用例 | 缺陷 | 相对修订号 23 |
|---|---|---|
| 01:7+spec:27 | 公共入口未导出 executor（超集对） | 不变 |
| 01:19+spec:75 | `retryAfter` 为 0 时回退退避 | 新 |
| 01:20+spec:55 | 实参先求值，派发先于鉴权生效 | 换缺陷 |
| 01:28+spec:41 | `onCommit` 时机无合同（uncertain） | 换缺陷，gap → uncertain |
| 01:30+spec:59 | `Number()` 接受非十进制数字文本 | 换缺陷 |
| 01:49+spec:26 | 余量钳为 0 后 `> 0` 拒绝等号（两种放置） | 换缺陷 |
| 01:51+spec:73 | 暂停者保留 claim 范围 | 新 |
| 02:22+spec:17 | 删除副本而非已存对象 | 换缺陷 |
| 02:23+spec:12 | 数组里的凭据未删除 | 换缺陷 |
| 02:46+spec:71 | 显式 false 被 `retryAfter` 覆盖 | 换缺陷 |
| 02:48+spec:22 | 原始 / 规范化 ID 不一致，跨组留重 | 换缺陷 |

- 修订号 23 的 01:43+spec:53 拆成两道 (a) 题；
- 02:29+spec:46、02:30+spec:45 两对正例改为反例对。

反例 18 对：

- 修订号 23 的 17 对中，01:22+spec:43 改写为孪生对，02:45+spec:14 拆开；
- 另加 02:29+spec:46（NDJSON 每条以 LF 结尾）、02:30+spec:45（目的地分组升序）。

## 未合并的相近行

修订号 23 的一组照旧：01:23 对 spec:9。

新增需要注意的几组，都按不同的题分别计分：

- 01:23（`chooseDeparture`）、spec:40（`nextDispatchTime`）、spec:54（禁发时段含首不含尾，satisfied）：操作或引用的规则范围不同；
- spec:7（排序用降序优先级和升序 sequence，satisfied）对 spec:50：spec:7 不引用政策，数值 sequence 排序正确；
- 问题题与孪生按术语成对，但分在不同 Gate：01:21 / spec:58、01:32 / spec:61、spec:11 / 02:45、spec:74 / 02:31、01:43 / 01:39（同 Gate，不同合同条文）、spec:53 / spec:70（同 Gate，不同合同条文）。

## 结果

| | 修订号 23 | 修订号 24 |
|---|---|---|
| Gate 1 正例（gap / uncertain） | 20（18 / 2） | 20（18 / 2） |
| Gate 2 正例（gap / uncertain） | 20（18 / 2） | 20（18 / 2） |
| Gate 1 / Gate 2 反例（含 noOther） | 30 / 38 | 30 / 38 |
| 合并用例（正例 / 反例） | 12 / 17 | 11 / 18 |
| 计分单位（正例 / 反例，合并后） | 28 / 51 | 29 / 50 |
| 审计记录要求行（01 / 02 / spec） | 27 / 22 / 57 | 27 / 22 / 57 |
| 单行字面量问题（G1 / G2） | 4 / 4 | 2 / 2 |
| 多处证据问题（G1 / G2） | 13 / 12 | 18 / 18 |
| 近邻干净用例（G1 / G2） | 15 / 18 | 17 / 20 |
| 难度因素题 (a) / (b) / (c)（每 Gate） | — | 2 / 2 / 0（另有保底题 1） |

共用证据：修订号 23 在 `repeats.json` 登记的一组（01:23 正例与 spec:9 反例）在修订号 24 不再共用，无新登记；`check_repeats` 通过。

## 测量说明

不改，沿用修订号 23 的 `measurement-note-commit-audit.txt`（含 Repeated requirements 段三句）。

## 裁决口径

随答案键冻结；正式盲裁 brief（[`commit-audit-v3-brief.md`](commit-audit-v3-brief.md)）原样带上本段并记录 sha256（修订号 24 行号）。

**沿用修订号 23**：

- 把令牌字段置为 `undefined` 算移除（JSON 序列化后不出现）；
- 引用已审行：finding 只引用已审行（如 "Same as spec:27"）并照抄结论与证据时，按被引行的 finding 文本裁决。被引行与本用例同属一个合并用例时，本行裁决与被引行相同；不在同一合并用例时，引用本身不构成理由，按本行自身的期望句裁决。
- 合并用例的候选与两侧任一期望句描述的是同一缺陷即算匹配。

**新增**：

- 字典序：`localeCompare` 与按码元比较（`<`、`>`）都视为字典序（02:30/spec:45 的比较器）。
- 01:51 / spec:73：finding 必须指出暂停时 active claim 的范围仍被保留（或等价：暂停只清空自身范围）。只说"未检查暂停"不匹配。
- spec:40：finding 必须指出取的是主机本地小时（`getHours`）而非 UTC。
- 01:19 / spec:75：finding 指出 `retryAfter` 为 0 时回退到退避，或指出非有限 / 非数值的真值 `retryAfter`（如 `Infinity`、非数字文本）替代了计算退避，任一即匹配。只谈单位或上限不匹配。
- 01:23：finding 必须指出移到禁发结束小时后落在窗口外而未拒绝。只谈本地小时不匹配（本版取 `getUTCHours`）。
- 01:30 / spec:59：finding 必须指出 `Number()` 接受非十进制数字文本（任一例即可：`'0x2'`、`'2e0'`、`' 2'`、`''`），或指出接受布尔值。只谈上界 3 不匹配（本版接受 3）。
- spec:50：finding 必须指出非数值的 `sequence`（文本或 `NaN`）没有排在有数值 sequence 的同优先级停靠点之后。只谈缺失 sequence 不匹配（本版缺失值已排后）。
- spec:38：finding 必须指出某类 `priority`（数字文本大于 5，或 `Infinity`）的停靠点不在任何分区。只谈缺失 priority 不匹配。
- spec:23：finding 必须指出 rename 被拒后 `discardTemporary` 不删除（锁定）的临时字节，或指出未调用 `removeTemporary`。只说"没有合同"不匹配。
- 02:22 / spec:17：finding 必须指出传给 `store.remove` 的是 `store.get` 的副本，不是已存对象。
- 02:23 / spec:12：finding 必须指出数组（或非 `Object` 构造的值）里的凭据未删除。
- 02:46 / spec:71：finding 必须指出标 `transient: false` 但带有限 `retryAfter` 的失败被重试。
- 01:49 / spec:26：finding 指出等于上限时余量为 0、`> 0` 为假即匹配，不必提单位换算。
- 01:21：finding 必须指出带 `reassignment` 的停靠点按自身 `driver` 而不是 `reassignment.driver` 归属。
- 01:32：finding 必须指出 `handedOver` 状态的停靠点仍被返回。
- spec:11：finding 必须指出每个停靠点少算 5 分钟停车时间（service time 的定义）。
- spec:74：finding 必须指出通知发往未去空格或连字符的原始 `phone`。
- 01:43：判 uncertain 且指出合同未规定未知地址时 `lookup` 的行为，即完全匹配；判 gap 但理由相同（如"可能拒绝"或"可能返回 null"）时仍算匹配，结果分由评分规则扣除。只说"没有检查未知地址"而不涉及合同的 finding 不匹配。
- spec:53：判 uncertain 且指出合同未规定 `scale.read` 的单位，即完全匹配；理由同 01:43。
- 01:38：finding 必须指出 `groupByDestination` 返回的 `Map`（或其条目）不是 `orderManifestGroups` 期待的分组对象，因此没有排序。
- spec:35（保底题）：finding 必须指出只有顶层键被排序（`withSortedKeys` 只代理计划对象本身），嵌套对象的字段顺序进入序列化字节和哈希。
- 02:37：`labelDriver` 在缺 label 时写入字符串 `"undefined"`，是同一处改写的附带表现，不算清单外缺陷。只以此为理由、未指出改写调用方对象的 finding 不匹配。

修订号 23 中 spec:11（只排顶层）和 01:51（缺末尾 LF）两条口径随旧题删除。spec:35 现在考的是"只排顶层"，口径按本版。

## 与 ARW 合同的差异

在修订号 23 的对照表基础上：

| 约定 | ARW 原值 | 修订号 24 |
|---|---|---|
| 每 Gate 问题用例 | 20（18 gap + 2 uncertain） | 各 20（18 + 2） |
| 单行字面量问题 | 最多 4 | 各 2 |
| 需多处证据的问题 | 至少 12 | 各 18 |
| 近邻对照干净用例 | 至少 20 | G1 17，G2 20 |
| 合并后正例计分单位 | 40（无合并） | 29 |
| 可见文档 | ARW 原夹具 | 加 `docs/dispatch/dispatch-policy.md`（33 条）、`docs/dispatch/adapter-contracts.md`（4 条）；存储合同改 1 条、加 7 条；删除 base `config/dispatch-policy.json`（无引用、与政策文档同名易误导） |

conformance 改后失败集的测试名与 v2 基线（ARW 原版 + v2 + 评分补丁）逐条相同：70 项中 25 项失败，均为既有失败，来自评分补丁。把数字、UUID 与哈希屏蔽后，失败详情与 v2 基线逐行相同。

## 审计、校准与冻结（2026-10-18）

**校准**（本机，IQ3_XXS，Strata 0.1.45，机械上界，未盲裁）：

- d4（第 4 稿）Q3 ×1：上界 0.651，13.1 分钟，0 压缩。
- d41（第 4.1 稿）Q3 ×3、Opus medium ×1：Q3 均值 0.6157，Opus 0.8375，比值 0.735。不含新题时比值 0.694，再不含孪生时 0.687。Q3 用时 10.5 / 9.2 / 11.4 分钟，0 压缩，工具调用 25 / 34 / 34 次。
- 新题型命中（Q3 三次，不含保底题）为 14/21，正好压在方向意见的 2/3 线上；把 01:38、spec:35 记为 (c) 时是 20/27。改标时间等核对见设计说明 §11：按记录，改标在 d4、d41 结果之前。
- 因素结论：(a) 已确认，(b) 判为无效构造（Q3 11/12）。

**审计**（Opus high 审计加盲答，3 轮，设计说明 §10）：R1 提出 2 项必须改，R2 提出 1 项；R3 为 0 项必须改，盲答 0.899，106/106 行结论与答案键一致，0 误报。R1、R2 的必须改和建议改全部采纳，形成 v3.2、v3.3。

**分层**：独立审查结论为不设 k = 1，维持 all-B（设计说明 §6）。

**冻结**：Main 与独立审查一致，判为有条件冻结，条件均已落实：

- 过时文字已改：用时写入实测；起因改为引用现行难度因素规则；补写停止条件核对。
- 入库：
  - 补丁移入 `arw-patches/commit-audit-v3.patch`；
  - 新建 `manifest-commit-audit-v3.json`，补丁路径改为入库路径；
  - 登记写入 `judgment/registry.json` 与 `repeats.json`；
  - 同步 `versions.md`、`judgment/README.md`；
  - 测量说明的场景映射（`tools/tuning/arw_dimension.py`）加上 v3 manifest。
- 入库 manifest sha256 `56a95344f07e1e0c…`。从它重新物化后：补丁仍为 `0e0ffca8…`，`expected.json` 仍为 `81796f46…`，夹具与冻结前逐文件相同（只有复制进 ARW 的 `reviewer-judgment/registry.json` 因登记文字与格式不同而不同，各答案键的登记结果相同），conformance 70 项中 45 过 25 败，失败集与 v2 基线逐条相同。
- 裁决 brief 已冻结为 [`commit-audit-v3-brief.md`](commit-audit-v3-brief.md)（sha256 `9c36e60b8090e24e…`），内含本说明「裁决口径」一节正文（标题下一行起、到下一节标题前，去掉首尾空行、末尾一个 LF；sha256 `a425b70f0fa5ec4d…`）。正式盲裁原样使用，只替换裁决目录与池名。

**冻结后、正式测量前后的要求**（独立意见，Main 同意）：

1. 运行计划事先写定：
   - 本机、IQ3_XXS、Strata 0.1.45、Codex 0.162.0、effort high；
   - 测量说明 `measurement-note-commit-audit.txt`，不限时；
   - 启动提示与压缩提示核对 SHA；服务日志确认 budget 8192 (max 24576)；引擎输出不低于 60 tok/s；
   - 每批冷加载，用完归还租约；
   - 运行层安全门在 0.1.45 上是否仍然有效，列为核对项。
2. 样本：
   - Q3 ×5 为正式值，空闲时加测到 10 次只作补充；
   - Opus medium ×3，d41 的 Opus 跑在 v3.1 上，不沿用；
   - Haiku-high ×5，同时作第二参考和格式罚 p 基准，登记到 `format-baseline.json` 后才能算罚后分。
3. 盲裁：Q3 与 Opus 的全部候选都要盲裁，用冻结 brief，不沿用校准与审计阶段的候选核对。
4. 报告：
   - 罚前、罚后两个口径；
   - 三套分数与比值：全部 29 个正例单位、不含 7 个 (a)+(b) 单位、再不含孪生；
   - 按 (a)、(b)、保底分别给命中率；
   - 核对 M2、M3 是否生效：02:30/spec:45、02:31 的 Q3 误报次数，01:20 两侧是否一致；
   - 如实写明命中率压线、改标时间、(b) 为无效构造；
   - 每个得分处同时给耗时、token、工具调用数。
5. 用时：任一实例超过 30 分钟或均值明显超过 20 分钟，先缩场景。
6. 版本混杂：v2 在 Strata 0.1.44.1 上测，v3 在 0.1.45 上测，两版的等价性没有核实，所以 v2 → v3 的分数变化不能全部归因于加难，判定只用同版本的 Q3/Opus。
7. 判定事先写定：Q3/Opus < 0.8 就定版。≥ 0.8 时，按规则只剩一个中点版；但 (a) 名额已满，中点版没有合法的加强方向，多半直接记为区分度不足。
