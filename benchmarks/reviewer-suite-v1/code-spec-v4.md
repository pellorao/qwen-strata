# Code Spec 能力场景 v4（v4.7 混合题型版）：相对 v3 的变更说明

v4 以补丁 [`arw-patches/code-spec-v4.patch`](arw-patches/code-spec-v4.patch) 提供，在冻结源 manifest 中叠加在 `code-spec-v3.patch` 之后。冻结内容是迭代中的 v4.7 版。

- 改动范围：重写 Code Spec 夹具的可见内容（spec 与实现）和答案键；`SCENARIO_REVISIONS` 中 code-spec-reviewer 从 13 改为 25。修订号 14–24 是未冻结的试跑版本。
- 不改动：评分规则、角色规则、交接（`handoff.md`），以及准备、生成、评分程序。
- 可比范围：v4 分数只与 v4 比较。阅读量 17.9K 字节（spec 6.0K + 实现 11.9K），v3 为 17.9K。

## 起因

v3 测量（[报告](../../reports/v0.1.42/code-spec-v3/summary.md)）中 Q3 ×5 平均检出 21.8/22，按预设门槛判定需要重新设计，没有跑 Opus。目标是 Q3/Opus 明显低于 0.8（用户 2026-10-13）。

## 迭代过程（v4.0–v4.7，均为 Q3 单次或 ×3 试跑）

| 版本 | 思路 | Q3 结果 | 结论 |
|---|---|---|---|
| v4.0–v4.2 | 每个缺陷推理步数提到 4–6 步 | 19、17、17/20 | 太容易 |
| v4.3 | 约 7.7 步，混入 JS 语义型缺陷 | 13、17/20；Opus-high 19/20 | 比值约 0.79，但差距来自局部可见的语义缺陷 |
| 因素探针 | 步数（约 20 步）与困难类型分开测 | 9 次全部 7/7 | Q3 用 node 执行代码把静态链压平；单个因素不降分 |
| v4.4–v4.6 | spec 写成规则网络（优先级、覆盖、例外），非保底平均 5–9 步 | 19–20/20；v4.6 Opus-high 20/20 | 规则网络被逐句当清单核对，比值约 0.93，无区分度 |
| v4.7 | 以 v4.3 为基础的混合题型：长链无线索为主，加短而隐晦、规则交互、保底 | 修订 24：14、13、14/20；Opus-high 20/20 | 比值约 0.68，进入审计与冻结 |

v4.7 的设计依据是 reviewer 规则（7177008）：缺陷行本身写得自然、只有懂语言语义或把数据流追到最终结果才能判错的，不算捷径；一套题要混合题型和难度。

## 问题用例（20 个）

有效步数按审计阶段 2 的复核（spec 到判定的最短路径），不是设计时写下的链长。

| # | 用例（缺陷位置） | 类别 | 题型 | 有效步数 | 为什么不能跳步 |
|---|---|---|---|---|---|
| P1 | quotaAllRooms：成员上限用 `store.list(window)` 计数，window 带 roomId 成了房间过滤（`reservation-service.mjs:20`） | 长链 | 数据流（参数携带字段） | 4 | 改期处同一调用是正确的；要追到 store 的解构 |
| P2 | holdUnits：`addMinutes(from, SETTINGS.hold)`，hold 已是毫秒，再乘一分钟（`policy.mjs:3`） | 长链 | 单位 | 4 | addMinutes 与参数都自然；要查到 SETTINGS 的单位 |
| P3 | selfConflict：改期把预订对象当 excludedId 传入，与 id 用 `!==` 比较（`reservation-service.mjs:57`） | 长链 | 类型/身份比较 | 3 | 要看到 policy 的参数名和比较 |
| P4 | confirmedAtKept：先展开原记录再展开已删字段的 moved，原 confirmedAt 保留（`reservation-service.mjs:61`） | 长链 | 展开覆盖顺序 | 4 | 要知道 moved 已 delete 字段且展开不覆盖缺失键 |
| P5 | buildingFromRoom：catalog 白名单解构丢了 buildingId（`catalog.mjs:4-5`） | 长链 | 数据流（字段丢失） | 4 | newHold 取 `room.buildingId` 是正确的；字段在房间来源处丢失 |
| P6 | accessFromInstant：用 `overlaps(instant(at), window)` 判时刻，零长度区间在 accessFrom 处失败（`policy.mjs:64`） | 长链 | 边界（零长度区间） | 3 | 要代入 instant 与严格比较 |
| P7 | durationUnits：`maxDuration: minutes(240)` 是毫秒，与分钟长度比较，上限永不触发（`calendar.mjs:16`） | 长链 | 单位 | 3–4 | 要追到 windowLength 的单位 |
| P8 | expirySubMinute：`remaining(at, expiresAt) <= 0`，截断取整使最后一分钟被判过期（`policy.mjs:27`） | 长链 | 边界（截断取整） | 3 | remaining 在别处是正确的；要代入不足一分钟的值 |
| P9 | lateFeeState：费用由转换后的 canceled 记录计算，恒为 0（`reservation-service.mjs:47`） | 长链 | 转换后的状态 | 3 | 要知道 next 已是 canceled |
| P10 | snapEnd：endAt = 下吸附的 startAt + 原长度向上取整的槽数，可能早于请求值（`calendar.mjs:26-27`） | 长链 | 边界（吸附推算） | 2 + 代入一次 | 看似向外吸附；要代入非边界起点 |
| P11 | rescheduleHoldLarge：改期 hold 按人数取 largeHold，spec 规定不论人数 10 分钟（`reservation-service.mjs:63`） | 规则交互 | 规则覆盖 | 2 | 与 spec 例外句可直接对照 |
| P12 | accessUntilLarge：窗口终点也加按人数的提前量（`policy.mjs:58`） | 规则交互 | 规则覆盖 | 2–3 | 同上 |
| P13 | heldRescheduleCutoff：held 与 confirmed 合并成一条带 60 分钟截止的改期规则（`transitions.mjs:7`） | 规则交互 | 规则表例外 | 2 | 同上 |
| P14 | trimBoth：去空白正则缺 `g`（`request-validation.mjs:1`） | 短而隐晦 | 正则语义 | 2 | 局部可判，写法常见，需懂语义 |
| P15 | activeDefault：默认值 `active: true` 展开在原始房间下（`catalog.mjs:1`） | 短而隐晦 | 默认值展开 | 2 | 同上 |
| P16 | amenityDup：用并集大小与房间列表长度比较（`catalog.mjs:16`） | 短而隐晦 | 集合大小 | 2 | 同上 |
| P17 | notifyBeforeSave：`save` 未 await 就发通知；store 经写队列异步落盘（`notifications.mjs:15`） | 短而隐晦 | 异步时序 | 2 | 同上 |
| P18 | historyShared：浅展开后 push 到共享的 history 数组（`transitions.mjs:16`） | 短而隐晦 | 引用共享 | 2 | 同上 |
| P19 | noteExact：`note.trim()`（`request-validation.mjs:21`） | 保底 | — | 1–2 | 与 spec 句直接对照 |
| P20 | rescheduleDuration：改期路径没有时长检查（`reservation-service.mjs:53-58`） | 保底 | — | 1–2 | 同上 |

- 长链平均约 3.4 步，审计前设计写的是 5.0。"推算"和"语义"不单独计步。
- 规则交互 3 例与 spec 例外句能直接对照，属于步数少的题；按用户要求保留，不当作长链。
- 题型分散，每种不超过 2 个。
- 两处检查重叠属同一事实链：holdUnits 也使改期 hold 偏大；durationUnits 使改期的时长检查即使存在也不会触发。修好前者后，后者的缺陷仍在。
- 实测难度（修订 24 校准，Q3 ×3；修订 25 只改了 store 的写队列和答案键，写队列可能让 P17 稍容易，正式测量重测）：P2、P5、P7、P14 三次都漏，P4、P15 各中 1 次，P12、P16、P17 各中 2 次；其余用例三次都中。

## clean 用例（30 个 + noOtherSupportedFinding）

逐条对应 spec 中被满足的要求行。外形与缺陷相近的合规诱饵包括：

- `Number.isInteger` 的正整数检查；
- `byId` 字符串比较器；
- 计价用 `Math.ceil`；
- 晚取消门槛与改期截止用同一个截断取整的 `remaining`，对 `< 120`、`< 60` 都精确，包括 startAt 之后的负值；
- 改期可用性检查用 `store.list(window)`；
- 半开区间的 `overlaps`；
- held 改期不受截止限制（规则表中 held、confirmed 分开）；
- 其余写操作都 `await store.save`。

## 答案键设计

- `associationEvidence` 取缺陷所在的最小行。写入点和查询点都能证明、都能修复的缺陷，用 placements 列出替代关联集：
  - P2：policy:3、calendar:11、calendar:5；
  - P5：catalog:4、catalog:5、policy:13；
  - P7：calendar:16、policy:5；
  - P9：service:47、policy:47；
  - P10：calendar:26、calendar:27；
  - P13：transitions:7、transitions:13；
  - P15：catalog:1、catalog:4；
  - P20：service:56、service:53。
- clean 期望只描述代码中确实成立的部分。例如 C16 只说"按 partySize > 8 选 largeHold"，不说"30 分钟"，因为 P2 存在时实际值不是 30 分钟。

## 审计（全新 Opus-high，ARW 两阶段，两轮）

| 轮次 | 阶段 | 结论 |
|---|---|---|
| 1（修订 24） | 1（盲答） | 20 条发现与 20 个问题用例一一对应，误报 0，没有键外缺陷 |
| 1 | 2（对照答案键） | blocker 0，major 5，minor 6，见下表 |
| 2（修订 25） | 1（盲答，与正式 Q3 相同的渲染交接） | 19 条发现，裁决后 19/20（漏 P2），误报 0，没有键外缺陷；兼作正式 Opus 第 1 次 |
| 2 | 2（另一个全新 Opus-high；阶段 1 线程续做时读答案键被权限拒绝，改由新实例按书面授权读取） | blocker 0，major 0，minor 7；20 个问题用例都在源码上用 node 复现；P17 在写队列下可由代码证明（通知时 `findByRequestKey` 返回 null）；P2 漏检属确实难，非歧义 |

第 1 轮 major 的处理：

| ID | 问题 | 处理 |
|---|---|---|
| M1 | P17：内存 store 的 `save` 在第一个 await 之前同步执行 `records.set`，当前代码下证明不了"先通知后保存"，答案不唯一 | store 改为串行写队列（`writes = writes.then(...)`），写入真正异步；探针改用真实 store 验证；可见内容变化，修订号改为 25，重做两阶段审计 |
| M2 | C16 声称大团队 hold 为 30 分钟，P2 存在时不成立；P2 只有 policy:3 一个关联位置，定位在 calendar:11 的正确发现会让 P2、C16、noOther 一起失分 | C16 改写；P2 增加 calendar:11、calendar:5 |
| M3 | P7 缺比较点的关联位置 | 增加 policy:5 |
| M4 | 规则交互 P11–P13 与 spec 例外句字面对照，约 2–3 步 | 改归步数少的题，代码不变（用户要求保留规则交互题） |
| M5 | 设计中的长链步数偏高 | 按复核重写步数，见上表 |

第 1 轮 minor 的处理：

| ID | 问题 | 处理 |
|---|---|---|
| m1 | P11 期望写"30 分钟" | 改为"得到 largeHold，而不是固定 10 分钟" |
| m2 | C15、C9 措辞在 P1 存在时字面不成立 | 改为只描述阈值比较与 `Math.ceil` |
| m3 | P5、P20 的单行位置是 P15、P16、P3、P10 发现的自然定位行，形成多余机械候选 | 不改：只增加裁决负担，裁决正确就不影响分数 |
| m4 | P13、P9 只写可修复的另一处时关联不上 | 补 placements transitions:13、policy:47 |
| m5 | P2 与 P7 可能被理解为同一根因（SETTINGS 毫秒与分钟混用）而合并成一条 | 不改，记为残余：分两条是主流读法 |
| m6 | SETTINGS 中 `minutes(...)` 与纯分钟数并列、`SLOT_MINUTES` 命名，对 P2、P7 是轻度提示 | 不改：仍需跨定义推理，按现行标准不算捷径 |

第 2 轮 minor 的处理（只改答案键或文档，可见内容不变，不重新盲审）：

| ID | 问题 | 处理 |
|---|---|---|
| m1 | P5 "can never authorize building access"、P17 "even when saving fails" 措辞偏强 | 改为"不能进入所属房间的楼"、"在排队的写入完成之前发出通知" |
| m2 | P7 新增 policy:5 后，讲吸附算短、绕过上限的 P10 发现也成为 P7 候选 | 不改键；裁决提示写明这类发现不匹配 P7 |
| m3 | P15 默认值在 catalog:4 的展开处生效，也可在那里修复 | 补 placement catalog:4 |
| m4 | P11 发现常写"30 分钟"（P2 存在时数值不对） | 裁决提示写明：核心是按人数取值，匹配 P11，不匹配 P2 |
| m5、m6 | 说明中的实测难度不全；校准数据属于修订 24 | 已补全并注明 |
| m7 | 多用例共用定位只增加裁决负担 | 维持现状 |

## 机械检查

- 生成方式：`base/` 是正确实现，生成器逐个注入缺陷。验证结果：
  - 正确版 0 失败；
  - 每个缺陷单独注入时只破坏自己的检查（上述两处同链重叠除外）；
  - 全部注入时 20 个问题检查失败，30 个干净检查全过。
- 答案键：20 个问题用例、31 个干净用例，定位行均非空行。
- ARW 自带测试 `tests/release/reviewer-capability-conformance.test.mjs` 打补丁后 70/70 通过。按 manifest 物化后，夹具、spec、expected.json 与工作副本逐字节一致。
- 补丁 sha256 `95b658c080618af01c578ae2010d6b047438816f286c88ad459961b243a8c1c5`；expected.json sha256 `849c6248…`。按冻结 manifest 物化后一致性测试同样 70/70。

## 残余

- m5，见上文。
- 审计第 1 轮提出的低风险读法：改期不检查房间 active 和容量。Rescheduling 一节列出了全部条件并写明"no request validation other than…"，不算缺陷。若有回答报出这一条，会让 noOtherSupportedFinding 失败，测量后在逐实例检查中核对。
- v2、v3 残余中的规则冲突各 Code Spec 实例共有，仍然存在：
  - `reviewer.md` Communication 一节要求 send_message 和运行标识；
  - Role Inputs 要求治理副本的 SHA-256，而交接不提供。
