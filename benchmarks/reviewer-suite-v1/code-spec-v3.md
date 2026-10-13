# Code Spec 能力场景 v3（加难度版）：相对 v2 的变更说明

v3 以补丁 [`arw-patches/code-spec-v3.patch`](arw-patches/code-spec-v3.patch) 提供，在冻结源 manifest 中叠加在 `code-spec-v2.patch` 之后。

- 改动范围：重写 Code Spec 夹具的可见内容（spec 与实现）和答案键；`SCENARIO_REVISIONS` 中 code-spec-reviewer 从 12 改为 13。
- 不改动：评分规则、角色规则、交接（`handoff.md`），以及准备、生成、评分程序。
- 可比范围：v3 分数只与 v3 比较。

## 起因

v2 测量（[报告](../../reports/v0.1.42/code-spec-v2/summary.md)）显示场景没有区分度：

- 21 个问题用例，Opus medium 3/3 全部检出，Q3 10/10 全部检出。
- Q3/Opus = 1.02，分差只来自证据定位精度和格式罚分。

用户 2026-10-13 同意做 Code Spec 的优化迭代，目标是 Q3/Opus 明显低于 1。

## v2 为什么双方全检出（分析，未跑模型）

1. **每个缺陷都是"一句 spec 对一行代码"的直接对照。** 例如：
   - spec "ten minutes" 对 `HOLD_DURATION_MS = 5 * 60 * 1_000`；
   - "every requested amenity" 对 `.some(`；
   - "positive integer" 对 `Number.isInteger(partySize) &&`（缺少 `> 0`）。
2. **spec 是 40 条可逐条勾选的清单，缺陷所在行就在同名函数里。** 逐条走一遍清单就能找全，不需要跨文件追数据流。
3. **常量名和数值直接暴露缺陷。** 如 `EARLY_ACCESS_MS = 10 * 60 * 1_000` 对照 "fifteen minutes"。

## v3 设计原则

- **难度来自推理深度，不来自阅读量**（reviewer-suite.md「场景时长」）。可见 Input 17.9K 字节，v2 为 14.2K（1.26 倍）；问题用例 22 个，v2 为 21 个。
- **大多数缺陷需要跨文件对照或多步推理**，而不是 spec 原句与单行代码的直接对照。保留少量直接对照的缺陷作为下限，避免出现双方都 0 命中的用例。
- **加入"看起来可疑但正确"的诱饵**，检验误报：
  - 半开区间 `<`；
  - `now() >= expiresAt`；
  - 取消时 history 用新数组；
  - 访问窗口开始用 `minutes()`；
  - 改期复用 `createHold` 后保留 id、room、building。
- **spec 每行一条要求，缺陷与 clean 交错分布**，不按 spec 顺序与实现一一对应（ARW「Scenario layout」）。

## 问题用例（22 个）

难度栏取审计阶段 1 独立给出的评级（easy = 与 spec 句直接对照；medium = 需要一次交叉引用；hard = 跨文件或多步推理）。

| # | 缺陷（位置） | 为什么需要推理 | 审计难度 |
|---|---|---|---|
| P1 | `memberId` 只查 `length === 0`（`request-validation.mjs:9`） | 直接对照（下限） | easy |
| P2 | 选房用原始 `request.roomId`，而 trim 后的值在 `preparedRequest`（`reservation-service.mjs:21`） | 需区分 `request` 与 `preparedRequest` | medium |
| P3 | `Number(request.partySize)` 强制转换，接受字符串（`request-validation.mjs:10`） | 正整数检查本身正确，需看出转换违反"supplied as a number" | medium |
| P4 | 合格房间列表不过滤 active（`reservation-service.mjs:33-36`） | 创建路径有 active 检查，列表路径漏了 | medium |
| P5 | 房间设施在 `loadRooms` 里转小写，请求设施不转（`room-catalog.mjs:5,15`） | 跨函数：一侧规范化，另一侧没有 | hard |
| P6 | 比较器 `Number(left.id > right.id)` 从不返回负值（`room-catalog.mjs:19`） | 需理解 sort 比较器合同 | hard |
| P7 | 幂等查找用原始键，存储用规范化键（`reservation-service.mjs:19`） | 跨文件：存储侧在 `hold-policy.mjs:16`、`request-validation.mjs:18` | medium |
| P8 | `nextId()` 在幂等查找之前调用（`reservation-service.mjs:18`） | 语句顺序 | easy |
| P9 | 占用判断调用 `isExpired(reservation)` 不传 `now`，默认回落 `Date.now`（`availability.mjs:12`、`hold-policy.mjs:25`） | 跨文件默认参数 | hard |
| P10 | 排除自身比较 `reservation.reservationId`，记录字段是 `id`（`availability.mjs:22`） | 字段名与类型定义、调用方对照 | hard |
| P11 | `createdAt + holdTtlSeconds`，600 秒按毫秒相加（`hold-policy.mjs:20`、`settings.mjs:2`） | 跨文件单位 | medium |
| P12 | `confirmedAt: now`，存的是函数（`reservation-service.mjs:42`） | 少一对括号 | easy |
| P13 | 浅拷贝后 `history.push`，修改了调用方的数组（`reservation-service.mjs:42-43`） | 引用语义；取消路径用新数组可作对照 | medium |
| P14 | `store.save` 未 await（`reservation-service.mjs:44`） | 异步时序 | easy |
| P15 | 取消通知由原 `reservation` 构建，没有 `canceledAt`（`reservation-service.mjs:60`） | 变量混用 | medium |
| P16 | 结束余量 `accessTrailMinutes * 1_000`，只有 15 秒（`access-policy.mjs:8`） | 单位；开始余量用 `minutes()`，正确 | medium |
| P17 | 进入只排除 canceled，held 也能进入（`access-policy.mjs:12`） | 直接对照（下限） | easy |
| P18 | 改期校验旧窗口 `reservation.endAt/startAt`（`reservation-service.mjs:66`） | 变量混用 | easy |
| P19 | 改期经 `createHold` 重建，`requestKey` 变 undefined，history 重置，confirmedAt 丢失（`reservation-service.mjs:71`、`hold-policy.mjs:16`） | 多步：改期记录没有 `idempotencyKey` 字段 | hard |
| P20 | 新预订 `buildingId` 取自请求，不取自房间（`hold-policy.mjs:11`） | 需对照 Room 类型与 spec | medium |
| P21 | 容量判断 `partySize < capacity`（`room-catalog.mjs:12`） | 直接对照（下限） | easy |
| P22 | 过去起始判断用 `Date.now()`（`request-validation.mjs:13`） | 需对照 spec「Conventions」 | easy |

全部 22 个缺陷都用 node 行为探针复现过（`.tmp/code-spec-v3/check/probe.mjs`，审计阶段 1 另有独立探针）。

## clean 用例（27 个 + noOtherSupportedFinding）

逐条对应 spec 中被满足的要求行（spec:10、13、15、19、20、22、27、30、39–42、48、51、52、56、57、61、65–68、74、75、80、83、84）。其中 5 个是上文列出的诱饵。

## 答案键设计

- **associationEvidence 取缺陷所在的最小行。** 有多个合理定位时，用 placements 列出替代关联集，evidence 不变；这符合 ARW「Problem association」中"最小非空子集"的要求。
- **共用根因的处理。** P21 的 `roomCanHost` 与 P5 的 `hasRequestedAmenities` 在创建和列表两条路径上共用，各按一个根因计一个用例。

## 审计（全新 Opus-high，ARW 两阶段，一轮）

| 阶段 | 结论 |
|---|---|
| 1（不看答案键） | 独立找到 22 条 finding，与答案键 22 个问题用例一一对应，引用的 spec 行号完全一致；没有键外缺陷；27 条 clean 全部判为满足；提出 6 条歧义 A1–A6 |
| 2（对照答案键） | blocker 0，major 1，minor 7；全部 clean 用例和问题用例真实、证据集正确 |
| 键修订 r2 复核（同一线程，只改键，按 ARW 规则不重新盲审） | M1、m1–m4 已解决，无 blocker 或 major；新增 minor n1、n2（见下） |

**major M1**：P5 原本的关联集要求同时引用 `room-catalog.mjs:15` 和 `reservation-service.mjs:25`。只引用缺陷所在行 `:15` 的正确 finding 关联不上，还会连带让 C8 与 noOtherSupportedFinding 失败。已改为 `{rc:15}`、`{rs:25}`、`{rs:36}` 三个单行关联集。

**minor 的处理**：

| ID | 问题 | 处理 |
|---|---|---|
| m1 | P13 不接受只引用 `rs:42`（浅拷贝来源）的 finding | 加关联集 `{rs:42}` |
| m2 | P4 不接受只引用函数声明 `rs:33` 的 finding | 加关联集 `{rs:33}`，evidence 补 `:33` |
| m3 | P19 期望依赖对 spec:85 的一种读法（history、confirmedAt 是否属于"其他存储字段"，歧义 A1） | 期望改为报出任一丢失字段即匹配（`requestKey` 丢失在任何读法下都成立）；加关联集 `{hp:16}` |
| m4 | 经 spec:84 报出的"改期后 0.6 秒过期"只引用 `rs:71` 时关联不到 P11 | P11 加关联集 `{rs:71, spec:84}` |
| m5 | spec:21 "allocating an identifier" 有"给记录赋 id"的反方读法 | **不改**，记为残余：改成"calling `nextId`"会直接提示答案；反方读法只会漏报 P8，不产生误报 |
| m6 | 歧义 A7：「Request fields」是否也适用于列表请求；报"列表未校验 partySize"会让 noOtherSupportedFinding 失败 | **不改**，记为残余：改可见内容需要新的全量盲审；预计很少出现，测量后在逐实例检查中核对 |
| m7 | 一条 finding 合写 P12、P13 时的计分 | 无需改：ARW 原子性公式（caseUniqueness / findingPurity）已有规定 |
| n1 | r2 给 P4 的 evidence 加了 `rs:33`，只引 `rs:34` 的 finding 覆盖率被稀释 | 改为分 placement：`{rs:33}` 的 evidence 含 `:33`，`{rs:34}`/`{rs:35}`/`{rs:36}` 的 evidence 保持 `rs:34-36` + spec:34 |
| n2 | P12 与 P13 都接受单行 `rs:42` 关联，区分完全依赖语义裁决 | 不改：两者缺陷含义不同（函数值 vs 共享数组），裁决可区分 |

## 机械检查

- 答案键自检：全部定位都落在夹具的非空行上（`.tmp/code-spec-v3/check/build_expected.py` 逐行打印核对）。
- ARW 自带测试 `tests/release/reviewer-capability-conformance.test.mjs` 打补丁后 70/70 通过；按 manifest 物化后夹具与工作副本逐字节一致（expected.json sha256 `7697c380…`）。
- 补丁 sha256 `a5de617a6335c5d9ef0b984f46c86db531bfe4df7f896e1dbd38fdde00f7e5f9`。

## 残余

- m5、m6，见上文。
- 歧义 A3：spec:35 没有规定 id 的字符串比较方式。当前比较器在任何读法下都错，不影响 P6。
- v2 残余中的规则冲突各 Code Spec 实例共有，仍然存在：
  - `reviewer.md` Communication 一节要求 send_message 和运行标识；
  - Role Inputs 要求治理副本的 SHA-256，而交接不提供。
