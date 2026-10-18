# Commit Audit v3（修订号 24）出题设计

状态：**修订号 24，2026-10-18 冻结**（末稿 v3.3，经 3 轮审计；Main 与独立审查一致：有条件冻结，条件已落实）。冻结件、裁决口径与冻结记录见 [commit-audit-v3.md](commit-audit-v3.md)。本文记出题设计、推理链与校准依据；文中"第 N 版（稿）"与 v3.x 是草稿序号，末稿 v3.3 即冻结版。方向依据是加难方向的独立意见"方案 1′"（2026-10-18，Main 采纳，要点与停止条件见 §11）。

## 1. 结论与改动

- **第 3 版校准**：Q3 上界 0.677，用时 35.6 分钟，压缩 1 次；Opus medium 0.838。新增的 5 道规则网络题两个模型都命中（Q3 0.71–0.85，Opus 0.78–0.87），对两者没有区分作用。
- **第 4 版相对第 3 版的改动**：
  - **撤掉**第 3 版的 5 道规则网络题（01:21 `releasedStops`、01:32 `canDriveRoute`、01:38 `handlingClass`、spec:74 `announcementChannels`、spec:11 `canConsolidate`），连同政策第 30–48 条和相应函数。
  - **保留**第 3 版对 spec:23、spec:24、01:51/spec:73 的去歧义修改（§9）。不恢复第 2 版为凑步数做的合并。
  - **新题按难度因素出**（§3）：
    - (a) 合同可读但对该行为沉默；
    - (b) 远处定义的术语；
    - (c) 助手函数调用形状不符，或要求行不点名实现。

    新题共 8 道（每 Gate 4 道），另配 7 道干净孪生题（§4）。
  - 删除孤立模块 `src/dispatch/policy.mjs`。它自第 2 版起已无要求行，第 3 版校准时却引出一条挂在 01:7 上的无关 finding，导致 01:7 在 G1 侧得 0 分。
- **第 4.1 版相对第 4 版的改动**（独立审查意见）：
  - 分层：不设 k = 1，维持 all-B（§6）。
  - §2 的 uncertain 依据改为 ARW 原版先例加角色规则排除法。
  - spec:53：第 28、29 条改为只约束"dispatch records or compares"的值，去掉"秤读数也按克"的第二种读法。
  - spec:58 孪生：实现由 `??` 改为 `||`，`reassignment` 为 `false`、`0`、`''` 时回落到停靠点本身。
  - 02:31 孪生：第 33 条写明 "every space (` `) and hyphen (`-`) character"。
  - spec:35：`stableTopLevel` 改名为 `withSortedKeys`（行号不变）。spec:35 与 01:38 改标为保底题，不计入加难因素。
  - §4 改写：孪生会给问题题提供线索；§3 的难度估计已考虑这一点。
  - 删除孤立的 base `config/dispatch-policy.json`：它与 `docs/dispatch/dispatch-policy.md` 同名，可能让审查者打开错的文件。
- **v3.2 相对第 4.1 版的改动**（第 1 轮审计，全部采纳）：
  - M1：01:20 行（base 与 candidate 两份）改为 "`executeAuthorizedPlan` rejects an unauthorized caller before invoking dispatch."。原句 "checks authorization before invoking dispatch" 可以字面判成立（`canPlanRoute` 确实先求值），与 spec:55 不再是同一要求。期望句、证据、`findingTerms` 不变。
  - M2：`manifest.mjs:11` 的参数标注改为 `{destination: string}[]`（同一行）；spec:45 改为点名 `orderManifestGroups`，期望句同步修改，`findingTerms` 改为 `orderManifestGroups`。原 spec:45 不点名实现，可以合理读成"系统产出的分组没有排序"（指向 01:38）。
  - S2：02:31 行（两份）末尾加 "that has a `phone`"，去掉"缺 `phone` 的条目会抛异常"这一误报面。代码不动。
  - S1、S3 改在 `commit-audit-v3.md`（01:19/spec:75 的裁决口径接受第二个理由；差异表补记删除 `config/dispatch-policy.json`）。
- **v3.3 相对 v3.2 的改动**（第 2 轮审计，全部采纳）：
  - M3：S2 只改行文、不改代码，使"缺 `phone` 就抛异常、一个都列不出"成为正当的 gap 读法。`manifest.mjs:44` 在同一行加 `filter(entry => typeof entry.phone === 'string')`，行号与证据不变；02:31 行文与答案键不变。spec:74 只写"缺 `phone` 发给 `undefined`"的 finding 仍不匹配。
  - 文字：`commit-audit-v3.md` 抬头的 manifest 与 judgment 名改为 v3.3，删去过时的 02:31/spec:8 一组；`register.py` 的 reason 改为 v3.3。
- **规模**：
  - 计分单位：正例 29（第 3 版 28），反例 50（第 3 版 49）。
  - 材料：579 行、33.2 KB。第 2 版为 532 行、29.4 KB；第 3 版为 600 行、33.5 KB。
- **用时**：已确认。d41（第 4.1 稿，Strata 0.1.45）Q3 三次 10.5 / 9.2 / 11.4 分钟，0 压缩，工具调用 25 / 34 / 34 次；d4（第 4 稿）一次 13.1 分钟，0 压缩（§7）。

## 2. 合同核查（出题前）

| 项 | 依据 | 结论 |
|---|---|---|
| uncertain 的定义（合同可读但沉默时） | ① ARW 原版先例：原版 `expected.json` 的 uncertain 期望句是 "The available storage contract does not establish cleanup behavior when `renameTemporary` fails."，当时存储合同可读，只是没写这一行为（原版快照 `arw-760007c2134d…`、`arw-39fe7f508237…` 中均如此）。② 角色规则 `docs/agents/roles/commit-audit-reviewer.md` 的排除法："只有直接矛盾时才使用 `gap`"，satisfied 又必须有支持；既无支持、又无矛盾，就只能是 uncertain | 合同可读但沉默 → uncertain。01:28/spec:41、01:43、spec:53 都按这一依据出题 |
| 每 Gate uncertain 数 | `docs/agents/reviewer-capability-scenarios.md`："问题用例包含 18 个 `gap` 和 2 个 `uncertain`"；conformance 测试逐 Gate 断言 18 / 2 | **受合同限制，每 Gate 恰为 2 个** |
| uncertain 判成 gap 怎么计分 | `lib/release/reviewer-capability-scoring.mjs`，scoredAssociation：`basePoints = (结果相同 ? 0.4 : 0) + evidenceF2 × 0.4`，再加原子性 0.2 | k = 0.25（现行 all-B）时，判 gap 但关联命中只失去结果分 0.4，最高 0.6；判 satisfied 不会产生 finding，得 0。k ≥ 1 时（reviewer-suite 规则 r8），关联命中即记 1，不再区分 gap 与 uncertain |

**(a) 类在限制内的安排**：

- 每 Gate 只有 2 个 uncertain 名额。
- 01:28/spec:41（`onCommit`）已经属于 (a) 类：Q3 时中时漏，Opus 0.92。保留不动。
- 01:43/spec:53（`restore`）是地板题：没有任何合同文件，Q3 0.80、Opus 0.80，没有区分作用。它的名额让给新的 (a) 题，每 Gate 一道，且**不再合并**（G1 01:43 `locateStops`，G2 spec:53 `weighPackages`），因此正例计分单位从 28 变为 29。

## 3. 新题（8 道）

推理链只写结论所需的最短路径。"为什么局部探针给不出答案"中的局部探针，指只读被点名的函数，或者用行文和代码本身能想到的输入去跑它。

### G1

**01:21 (b) `stopsForDriver`：指派司机**（gap）

- 行：`Under docs/dispatch/dispatch-policy.md, stopsForDriver returns exactly the stops whose assigned driver is the given driver.`
- 代码：`queue.mjs:30` `stops.filter(stop => stop.driver === driver)`。
- 推理链：
  1. 政策 Terms 节第 30 条：停靠点的 assigned driver 指它的 `reassignment` 的 `driver`（有 `reassignment` 时），否则才是它自己的 `driver`；
  2. 代码只比较自身的 `driver`；
  3. 带 `reassignment` 的停靠点会被归给原司机，不归给新司机。
- 为什么局部探针给不出答案：行里的 "assigned driver" 读起来就是 `driver` 字段，代码也只出现这个字段。`reassignment` 只在第 30 条出现，探针不会构造带 `reassignment` 的输入，跑出来全对。
- 孪生：spec:58 `driverWorkload`（`(stop.reassignment || stop).driver`，正确）。
- 孪生线索：`capacity.mjs:18` 的孪生实现直接写出了 `reassignment`。读到它的审查者，可能不看第 30 条也会察觉两处不一致，但仍要靠第 30 条判断哪一处正确。

**01:32 (b) `pendingStops`：已送达**（gap）

- 行：`… pendingStops returns every stop except the delivered stops.`
- 代码：`executor.mjs:19` `stop.state !== 'delivered'`。
- 推理链：
  1. 第 31 条：delivered stop 指 `state` 为 `delivered` 或 `handedOver`；
  2. 代码只排除 `delivered`；
  3. `handedOver` 的停靠点仍被返回。
- 为什么局部探针给不出答案：词面与状态值 `'delivered'` 完全对上，`handedOver` 只在第 31 条出现。
- 孪生：spec:61 `deliveredCount`（`['delivered', 'handedOver'].includes`，正确）。
- 孪生线索：较强。孪生在 `queue.mjs:36`，与 01:21、01:43 的实现同处一个文件，几行之隔，直接列出 `handedOver`。

**01:38 保底题 `orderedDestinationGroups`：调用形状不符**（gap，不计入加难因素）

- 行：`` `orderedDestinationGroups` returns the destination groups of the records in ascending lexical order. ``
- 代码：`manifest.mjs:42` `orderManifestGroups(groupByDestination(records))`。
- 推理链：
  1. `groupByDestination` 返回 `Map`（`manifest.mjs:3`）；
  2. `orderManifestGroups` 对 `[...groups]` 按元素的 `destination` 排序（`manifest.mjs:11`）；
  3. 展开 `Map` 得到 `[key, group]` 二元组，没有 `destination` 字段，比较器恒为 0；
  4. 稳定排序保持插入顺序，结果既不是升序，元素也不是分组本身。
- 为什么局部探针给不出答案：
  - 只读这一行，两次调用的组合看上去正确；
  - 两个助手各自都正确，02:30 和 02:44 两个反例行替它们"背书"；
  - 只有执行探针、并用乱序的目的地去跑组合本身，才能看出问题。这类题的难点在于意识到形状不符（eval4 §5 的 02:23 型）。
- 结构与 v2 的 `redactNestedDriverToken({driver: event.auth}).driver` 不同：这里是把返回的 `Map` 当成分组数组传给下一个助手。

**01:43 (a) `locateStops`：未知地址**（uncertain）

- 行：`Under docs/dispatch/adapter-contracts.md, locateStops leaves out every stop whose address the geocoder does not know.`
- 代码：`queue.mjs:34`，对每个停靠点 `await geocoder.lookup(address)`，再过滤掉 `point !== undefined` 不成立的项。
- 合同：`adapter-contracts.md:3` 只写 "resolves to the `{lat, lon}` point of a known address"，没有写未知地址时怎样。
- 推理链：
  1. 实现依赖 `lookup` 对未知地址解析为 `undefined`；
  2. 合同没有规定未知地址的行为：解析为 `null` 时保留，拒绝时整个调用拒绝；
  3. 不存在直接矛盾，所以判 uncertain。
- 诱导：过滤 `undefined` 看起来是有意处理，合理默认（"查不到返回 undefined"）会把这行判成 satisfied。函数名不暗示这一行为。
- 为什么局部探针给不出答案：探针必须自己写一个假 geocoder，而假 geocoder 怎么处理未知地址，恰恰就是那个未知量。探针给出的只是假对象被设定的答案（`undefined` → 成立，`null` 或拒绝 → 不成立，探针已核）。
- 孪生：01:39 `routeDistance`（合同写明 `distance` 无路时拒绝，实现 `await` 传播，成立）。
- 孪生线索：合同第 3、4 行相邻。第 4 行写了 "rejects when …"，反衬出第 3 行没有写未知地址；这让沉默更显眼，但不改变答案。

### G2

**spec:11 (b) 路线时长：服务时间**（gap）

- 行：`… a route duration adds the travel minutes and the service time of every stop.`
- 代码：`queue.mjs:32` `total + stop.travelMinutes + stop.serviceMinutes`。
- 推理链：
  1. 第 32 条：service time 指 `serviceMinutes` 加 5 分钟停车时间；
  2. 代码只加 `serviceMinutes`；
  3. 每个停靠点少算 5 分钟。
- 为什么局部探针给不出答案：行不点名函数，要从 "route duration" 找到 `routeDuration`；"service time" 与字段 `serviceMinutes` 字面对应，按字面算全对，加 5 只在第 32 条。
- 孪生：02:45 `departureMinute`（`+ stop.serviceMinutes + 5`，正确）。
- 孪生线索：较弱。孪生在 `schedule.mjs:28`，只是一个不加说明的 `+ 5`，要回到第 32 条才知道含义。

**spec:35 保底题 计划哈希：不点名实现**（gap，不计入加难因素）

- 行：`Two plans that differ only in the order of the fields inside their nested objects have the same plan hash.`
- 代码：
  - `serialize.mjs:7` `checksumPlan` 哈希 `serializePlan` 的结果；
  - `serialize.mjs:3` 用 `withSortedKeys`（第 4.1 版由 `stableTopLevel` 改名，去掉"只排顶层"的名字线索）；
  - `serialize.mjs:1` 的 Proxy 只拦截顶层对象的 `ownKeys`。
- 推理链：
  1. "plan hash" 对应 `checksumPlan`；
  2. 哈希对象是序列化字节；
  3. 只有顶层键排序，嵌套对象保持插入顺序；
  4. 嵌套字段顺序不同的计划序列化字节不同，哈希也不同。
- 为什么局部探针给不出答案：行不点名函数，要从规则映射到实现链（eval4 §5 G2#16 型）；`toStableJson` 与 `withSortedKeys` 的名字都暗示"已排序"。行文已写明 nested objects，构造嵌套探针并不难，所以只作保底题。
- 这是第 3 版 §9 记下的"只排顶层、无要求行"的既有行为，本版给它加上要求行，没有新增代码。原 spec:35（`freezeDispatchPlan`，两模型都命中，Q3 0.93、Opus 1.00）随之撤掉，代码改回正确实现。

**spec:53 (a) 称重：单位**（uncertain）

- 行：`Under docs/dispatch/dispatch-policy.md, package weighing records each package weight in the unit that the Vehicle capacity rules give.`
- 代码：`capacity.mjs:20` `weight: await scale.read(entry.packageId)`，原样记录。
- 合同：`adapter-contracts.md:8` 只写 "resolves to the measured weight of that package"，不写单位。
- 推理链：
  1. 第 28 条（第 4.1 版）："Package weights that dispatch records or compares are in grams."，约束的是本系统记录的值，不是秤的读数；
  2. 实现把 `scale.read` 的值原样记录；
  3. 合同不写读数单位，无法确认记录的值是克；不存在直接矛盾，判 uncertain。
- 第 4 版的第二种读法（审查意见）：旧第 28 条 "Package weights are in grams." 可以读成连秤的读数也按克，那样就能判 satisfied。第 4.1 版改成只约束 dispatch 记录或比较的值，第 29 条同步修改。合同仍保持沉默，没有写"单位取决于设备"，以免太直白。
- 诱导：合理默认是"秤给克"，会判 satisfied。行没有引用合同文件，审查者要自己在 `docs/dispatch/` 里找到它。
- 为什么局部探针给不出答案：假秤返回的只是一个没有单位的数，探针无法揭示单位。
- 孪生：spec:70 `measuredVehicleLimit`（合同写明 weighbridge 以千克计，第 29 条要求千克，成立）。
- 孪生线索：较强。孪生在 `capacity.mjs:16`，与问题题 `capacity.mjs:20` 相邻；合同第 9 行写了 "in kilograms"，第 8 行没写，沉默很显眼。

**spec:74 (b) 送达通知：联系电话**（gap）

- 行：`… delivery notices go to the contact phone of every manifest entry.`
- 代码：`publisher.mjs:31` `sms.send(entry.phone, …)`。
- 推理链：
  1. 第 33 条：contact phone 指去掉所有空格（` `）和连字符（`-`）字符的 `phone`；
  2. 代码发往原始 `phone`；
  3. 含空格或连字符的号码不是联系电话。
- 为什么局部探针给不出答案：行不点名函数；"contact phone" 与字段 `phone` 字面对应，规范化只在第 33 条。
- 孪生：02:31 `manifestRecipients`（`phone.replace(/[ -]/g, '')`，正确）。
- 孪生线索：孪生在 `manifest.mjs:44`，对同一字段做了规范化，对照很明显。

### 已有题的归类（不改）

| 题 | 归类 | 第 3 版 Q3 / Opus |
|---|---|---|
| 01:28/spec:41 | (a)：Plan Store Contract 可读，但不写 `onCommit` 的时机 | 0 / 0.92 |
| 01:51/spec:73 | 定义术语 "held scopes"，但定义与使用在同一节，不算 (b) 的"远处" | 0 / 0.84 |
| 02:23/spec:12 | v3 改为"递归不进数组"，已不是调用形状题 | 0.87 / 0.89 |

按方向意见，失败题 01:51 与 G1#7 的结构都没有克隆：

- (b) 的 4 个术语各属一种形态：覆盖字段、枚举集合、加常数、格式规范化；都不涉及"暂停加 claim"。
- (a) 都有可读的合同文件，只是缺少相关条文。v2 G1#7 是完全没有合同。

**因素结论（第 1 轮审计 S4，依据 scenario-design 第 7 行）**：

- **(b) 远处定义术语：本构造对 Q3 无效**。Q3 命中 11/12，Opus high 盲答 4/4。按第 7 行"加了某因素而 Q3 不降，就判这种构造无效、换因素"，(b) 不算已确认的因素，**不再加 (b) 题**。
- **(a) 合同可读但沉默：已确认**。01:28+spec:41、01:43、spec:53 三道题，Q3 3 次作答共 9 题次，命中 3 次（1/3）；Opus 全部命中；审计已排除歧义。满足第 7 行的确认方式二（至少 2 道题、Q3 命中 ≤ 1/3、Opus 命中、审计排除歧义）。
- **孪生移远**：属于改变因素强度，要先做因素探针，不在场景里直接改。

**孪生线索对难度的影响（第 4.1 版的事前估计）**：

- 孪生实现会把"有一个定义"或"合同在别处写明了"暴露在代码里。
- 线索强的题（01:32、spec:53、spec:74）：难度更多落在"注意到两处实现不一致，再回到政策或合同判定哪一处对"。这仍需跨文件读政策，但比完全没有线索容易。
- 线索弱的题（spec:11）和需要先读别的模块才看得到线索的题（01:21）：难度基本保持。
- 对 (a) 类，合同里相邻条文的对照让"沉默"更容易被注意到，但难点在"沉默时判 uncertain，而不是按默认判 satisfied"，这一点不受影响。
- 因此预计 (b) 类的命中率高于孤立出题时的水平。是否要把孪生移到更远的位置（如另一个模块的末尾），请审计判断：移动不改变题的设计，但会改变证据行。

## 4. 孪生题（7 道，均为 satisfied）

孪生题由原有的非近邻反例行改写而成，所以反例数不变。

- 问题版本与孪生版本的要求行大多分在不同 Gate。但这**不能**挡住对照：同一个审查者在一次会话里会审两个 Gate，要求行和代码都看得到。
- 孪生实现在代码里也和问题题挨得很近：
  - `queue.mjs:30–36` 依次是 01:21、spec:11、01:43 的实现和 01:32 的孪生；
  - `capacity.mjs:16–20` 中 spec:53 的问题题与孪生相邻；
  - `manifest.mjs:42–44` 中 01:38 与 spec:74 的孪生相邻。
- 孪生的作用是防止"凡依赖就判 uncertain、凡术语就报 gap"的偏向，不是隐藏对照。它们给问题题带来的线索见 §3 末尾。

| 孪生 | Gate | 对应问题题 | 实现 | 成立的依据 |
|---|---|---|---|---|
| 01:22+spec:43（合并） | 两侧 | 01:28/spec:41 | `writePlanAtomically` 先 `await writeTemporary` 再 rename | 合同新增第 15 行："`store.writeTemporary(bytes)` resolves only after the temporary bytes are durable." |
| 01:39 `routeDistance` | G1 | 01:43 | 逐段 `await geocoder.distance` | `adapter-contracts.md:4`：无路时拒绝，拒绝会传播 |
| spec:70 `measuredVehicleLimit` | G2 | spec:53 | 原样返回 `weighbridge.read` | `adapter-contracts.md:9`：千克；第 29 条：千克 |
| spec:58 `driverWorkload` | G2 | 01:21 | `(stop.reassignment \|\| stop).driver` | 第 30 条 |
| spec:61 `deliveredCount` | G2 | 01:32 | `['delivered', 'handedOver'].includes` | 第 31 条 |
| 02:45 `departureMinute` | G1 | spec:11 | `arrivalMinute + serviceMinutes + 5` | 第 32 条 |
| 02:31 `manifestRecipients` | G1 | spec:74 | `phone.replace(/[ -]/g, '')` | 第 33 条 |

- 被改写的原反例行：01:22+spec:43（包裹重量合计）、01:39（invalid-storage 测试）、02:31（`auditFieldsPresent`）、02:45（失败遥测）、spec:58（显式零容量）、spec:61（depot 别名）、spec:70（窗口时区）。它们都不在近邻清单里。
- 02:45 原与 spec:14 合并。spec:14 保持原文，改为单独计分，所以反例计分单位 +1。
- 误报面（第 4.1 版已处理）：
  - spec:58：实现改为 `||`，`reassignment` 为 `null`、`false`、`0`、`''` 时都回落到停靠点本身（探针已核）；
  - 02:31：第 33 条写明只去空格（` `）与连字符（`-`）字符，与正则 `/[ -]/g` 逐字一致。

## 5. 比例与分工

| 约束 | 要求 | G1 | G2 |
|---|---|---|---|
| 正例（gap / uncertain） | 20（18 / 2） | 20（18 / 2） | 20（18 / 2） |
| (a) 合同沉默（uncertain） | (a)+(b) 4–6，且 ≤ 1/3 | 2（01:28、01:43） | 2（spec:41、spec:53） |
| (b) 远处定义术语 | 同上 | 2（01:21、01:32） | 2（spec:11、spec:74） |
| (a)+(b) 合计 | 4–6 | **4**（另有同节术语题 01:51） | **4**（另有 spec:73） |
| (c) 调用形状 / 不点名实现 | 1–2 | 0（01:38 改为保底题） | 0（spec:35 改为保底题） |
| 保底题 | | 01:38 | spec:35 |
| 单行字面量问题 | ≤ 4 | 2（01:19、01:50） | 2（spec:50、spec:75） |
| 多处证据问题 | ≥ 12 | 18 | 18 |
| 近邻干净用例 | ≥ 15 | 17 | 20 |
| 反例（含 noOther） | 不变 | 30 | 38 |
| 合并 | | 正例 11 对、反例 18 对，共 29 对 | 同 |
| 计分单位 | 约 28 | 正例 29，反例 50 | |
| 审计记录要求行 | 27 / 22 / 57 | 不变 | |

- 新题证据互不共用；`check_repeats` 通过，`repeats.json` 无新登记。
- 每份审计记录中同一结果的最长连续段不超过 8（conformance 断言通过）。

**与 Spec Readiness 的分工**：两个场景的题型可能看起来相近，例如都涉及"合同或政策没写"。区别在于审查对象：

| | Commit Audit（本场景） | Spec Readiness |
|---|---|---|
| 审查对象 | 实现是否满足已写下的要求行 | 规格本身是否完整、一致、可实现 |
| "合同或政策没写" 的处理 | 实现依赖未写明的行为 → `uncertain`；不评价规格写得好不好 | 规格缺条文本身就是发现 |
| 定义术语 | 按定义检查实现（(b) 类） | 检查定义是否存在、是否自洽 |
| 本版各类题的落点 | (a)、(b) 与保底题都要求读实现并与合同或政策比较 | 不涉及 |

本版没有"规格自身缺陷"题：要求行、政策与合同之间无矛盾；(a) 类的空白是依赖合同的空白，答案落在实现能否被确认上。

## 6. 分层：不设 k = 1，维持 all-B（独立审查结论）

答案键保持 all-B（全部 k = 0.25），没有写任何 `k`。

第 4 版曾建议把非合并的 (a)、(b) 题与孪生放进 k = 1 层。独立审查否决了这一建议，理由如下：

- **这些题的结论都能简单核实**：只要对照一条定义或一行合同即可，按分层规则应定 0.25 档。
- **k = 1 会抹掉 (a) 类的考点**：k ≥ 1 时关联命中即记 1，不再区分 gap 和 uncertain，而 (a) 类正是要考这个区分。
- **合并对不能进层**：`judgment_binding` 拒绝在 merge 用例上标 k ≥ 1，01:28+spec:41 与 01:22+spec:43 只能留在 0.25 档，同一题型会被拆到两个档里。

## 7. 用时

- 基线：第 2 版 15.8 分钟，46–56 次工具调用，材料 29.4 KB。
- 第 4.1 版：579 行、33.2 KB（+13%），与第 3 版基本相同。
  - 政策：29 条 + Terms 4 条（第 3 版为 48 条）；
  - 新合同文件 9 行，存储合同 +1 行；
  - 新增 13 个单行或短函数（7 道问题题、6 道孪生题）；
  - 删除 `policy.mjs` 与 base `config/dispatch-policy.json`。
- 第 3 版超时的主因是 5 道规则网络题逐条对照、逐题探针，以及压缩后的整套重读；压缩前约 19 分钟。本版新题都是单行实现：
  - (b) 类只要读一条定义；
  - (a) 类只要读一个 9 行的合同文件；
  - 探针负担明显小于第 3 版。
- 事前估计 18–20 分钟、压缩风险未消除；**实测（已确认）**：d41（第 4.1 稿，Strata 0.1.45，rtx3080ti，IQ3_XXS）Q3 三次 10.5 / 9.2 / 11.4 分钟，压缩 0 次，工具调用 25 / 34 / 34 次；d4（第 4 稿）一次 13.1 分钟，压缩 0 次，工具调用 42 次。与 v2 正式测量的 11.7 分钟同一量级，在 20 分钟以内。v3.3 相对第 4.1 稿只改了 6 行，材料体量不变。正式测量再验证一次：任一实例超过 30 分钟或均值明显超过 20 分钟，按设计规则先缩场景。
- 如果正式测量超时，可按以下顺序缩减：
  1. 删除孤立的正确函数：`restorePlan`、`resolveVehicleCapacity`、`normalizeDepotAlias`、`freezeDispatchPlan`、`formatRouteToken`（需重映射行号）；
  2. 撤掉保底题 01:38。

## 8. 检查（v3.3，冻结前）

- conformance：70 项测试，45 通过、25 失败。失败集与 v2 基线（ARW 原版 + v2 + 评分补丁）逐条相同；数字、UUID 与哈希屏蔽后，失败详情与当次 v2 运行逐行相同（diff 0 行）。Commit Audit 夹具清单测试通过。
- 每份审计记录中连续同结果的最长串：01 为 4，02 为 7，spec 为 8，与第 4.1 版相同，没有超过上限 8（答案键与 v3.2 逐字节相同）。
- 场景测试：`plan.test.mjs`、`publish.test.mjs` 4/4 通过。
- 工程 unittest：423 项，OK。
- 探针（草稿期的临时 node 脚本，直接调用候选实现，未入库）：01:38 组合仍不排序（`["B","C","A"]`）；02:30 对分组对象排序正确；spec:58 的 `false`、`0`、`''` 三种 `reassignment` 都回落；02:31 去空格与连字符正确，缺 `phone` 的条目被跳过、不抛异常。
- 入库后从入库 manifest 重新物化一次，与冻结前的检查结果一致（见 `commit-audit-v3.md`「审计、校准与冻结」）。

## 9. 第 3 版的三项核查（第 4 版保留）

**01:51 / spec:73**：旧第 5 条 "holds no scopes" 可以读成"自身 `scopes` 字段为空"。第 3 版把"持有范围"写成定义术语（第 1、3、4、5 条），修改后的唯一推理：

1. 无持有范围；
2. 持有范围含 claim 范围；
3. 规划需要持有 `routes:plan`；
4. 代码在暂停时仍拼接 claim 范围。

修后第 3 版 Q3 仍为 0（三次试跑全漏），Opus 0.84。按方向意见原样保留，不克隆其结构。

**spec:23**：原为 uncertain，但函数名 `discardTemporary` 偏向"成立"。第 3 版改为由 Plan Store Contract 推出的 gap：

- rename 被拒后，临时字节被锁定；
- 锁定期间，`discard` 只关闭写入、不删除字节；
- 代码没有调用 `removeTemporary`。

修后 Q3 0.87。第 4 版在该节末尾追加第 15 行（`writeTemporary` 的持久性，供孪生 01:22/spec:43 使用），第 11–14 行不变。

**spec:24 诱饵**：合同第 4 条改为 "resolves to the supplied manifest object itself"。修后 Q3 0.95，判通过。

## 10. 审计记录（3 轮，Opus high 审计加盲答）

| 轮 | 对象 | 必须改 | 建议改 | 盲答（r8.3） |
|---|---|---|---|---|
| R1 | 第 4.1 稿 | 2：01:20 措辞（M1）、02:30+spec:45 读法（M2） | 4：S1–S4 | 0.844，漏检 1，误报 spec:45 |
| R2 | v3.2 | 1：02:31 限定语使"缺 `phone` 就抛异常"成为正当读法（M3） | 4（文字） | 0.831，正例全中，误报 02:31 |
| R3 | v3.3 | 0 | 0 | 0.899，106/106 行结论与答案键一致，0 误报 |

- 各轮修改见 §1 的改动清单；R1 判定"不改"的点：01:43 唯一性、(b) 定义没有第二种读法、孪生不移远（见 §3 末「因素结论」）、(c) 每 Gate 为 0 不补题、spec:58 `||` 与第 33 条写法没有误报、串扰没有问题、删除两个孤立文件。
- R2 另记一条不改：盲答把政策证据写成规则序号而不是实际行号，证据分因此偏低；角色文档已要求用实际行号，属答题者错误。
- 三轮发现的歧义（01:20、02:30/spec:45、02:31 两次）都已修，修后盲答两侧判断一致；R3 中 29 对合并两侧结论全部一致。

## 11. 方向、停止条件与核对（冻结前，2026-10-18）

**方向（方案 1′ 要点）**：撤掉第 3 稿的规则网络题，回到第 2 稿规模；新题按难度因素 (a)、(b)、(c) 出，不克隆失分题结构；(a)+(b) 每 Gate 4–6 个正例且不超过 1/3；计为加难配额第 1 版，这一方向最多再出 d4、d5 两稿，之后必须冻结末稿进入正式测量。新题类型来自 Q3 在 v2 上的失分模式。

**停止条件（看结果前定）**：Q3 ×3 均值上界 / Opus ≥ 0.85 → 方向无效，进 d5；比值 < 0.85 且新题型 3 次平均命中率 ≤ 2/3、Opus 命中 → 审计 → 冻结 → 正式测量。区分度是否达标只看正式测量。

**核对（d41：第 4.1 稿，Q3 ×3 与 Opus medium ×1，机械上界，未盲裁）**：

| 条件 | 结果 | 判定 |
|---|---|---|
| 比值 | Q3 均值 0.6157 / Opus 0.8375 = 0.735 | < 0.85，满足，余量大 |
| 新题型命中率，01:38、spec:35 记为保底题 | 14/21 = 2/3：(a) 3/9，(b) 11/12 | 正好压在 2/3 线上 |
| 新题型命中率，01:38、spec:35 记为 (c) | 20/27 = 0.74 | 超过 2/3 |
| Opus 命中新题 | 7/7 | 满足 |

- 命中率条件只在把 01:38、spec:35 记为保底题时成立。方向意见没有定义"比值 < 0.85 但命中率 > 2/3"这种情况。
- **改标时间的核对**（依据：出题 agent 的会话记录与文件时间戳，均为 2026-10-18 JST）：
  - 第 4 稿（答案键 `0436deaf…`）里 01:38 标为 (c) 调用形状、spec:35 标为 (c) 不点名实现。
  - 14:11:39，协调方把第 4 稿的独立审查意见转给出题 agent，其中第 5 条要求 `stableTopLevel` 改名，并把 spec:35 与 01:38 标为保底题、不计入加难因素。意见只对 spec:35 给了理由（`stableTopLevel` 是局部线索），01:38 一并改标，没有单独理由。第 4.1 稿按此构建，补丁写出于 14:12:52。
  - d4（第 4 稿 Q3 ×1）实例 14:06:54 开始、14:19:54 结束，结果记录写于 14:23:20。改标意见到达时 d4 实例还在运行，还没有分数。
  - 第 3 稿的 d3 结果（12:49）在此之前已有，但第 3 稿的 01:38 是另一道题（`handlingClass` 规则网络题），spec:35 也不是现在这道题；现在的两道题首见于第 4 稿，改标前没有它们的 Q3 结果。
  - 所以按记录，改标发生在 d4、d41 结果出来**之前**。查不到的部分：独立审查意见本身写成的时间（只核到它到达出题 agent 的时间，这是上限），以及审查者能否看到运行中 d4 实例的中间输出。d4 结果记录仍把 01:38 列为"新题有效的 6 道"之一，因为校准记录沿用了第 4 稿的标注。
- **因素状态**：(a) 已确认（scenario-design 第 7 行确认方式二），每 Gate 2 个 uncertain 名额已全部用给 (a)；(b) 判为无效构造（Q3 11/12），不再加题；(c) 不是已确认因素。
- **结论：冻结，不出 d5**（独立意见，Main 同意）。即使按严格读法算命中率条件没过，也冻结：
  1. d5 没有能合法加强的已确认因素：(a) 名额已满，(b) 无效，按第 7 行不能靠堆量加难；
  2. 区分度不靠新题：不含新题时比值 0.694，含新题时 0.735，新题反而把比值抬高了一点；命中率条件要防的"把无效构造当难度"在这里不成立；
  3. 方向意见规定最多出到 d5 就必须冻结，区分度只看正式测量。
- **校准在第 4.1 稿上做，冻结 v3.3，不重新校准**：v3.1 → v3.3 场景里只改了 6 行（01:20 两份、02:31 两份、spec:45、`manifest.mjs` 两行）。按 d41 逐用例分数估算，对 Q3 均值的影响合计约 +0.01，最多约 +0.02，比值约 0.75–0.76，仍低于 0.85 和 0.8，也远小于 Q3 自身的波动（三次 SD 约 0.116）。这只是估算，没有在 v3.3 上跑 Q3。
- 正式测量报告要如实写明：命中率压线、改标时间、(b) 是无效构造；给含与不含 (a)+(b) 题、再不含孪生的三套分数与比值，按 (a)、(b)、保底分别给命中率。
