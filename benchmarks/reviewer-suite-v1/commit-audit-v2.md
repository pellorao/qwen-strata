# Commit Audit 能力场景 v2：相对 ARW 原版的变更说明（草稿，未冻结）

v2 以补丁 [`arw-patches/commit-audit-v2.patch`](arw-patches/commit-audit-v2.patch) 提供，登记在 `source-snapshots/current/manifest-commit-audit-v2.json`（即 `manifest.json` 加上这一项）。补丁 sha256 以 manifest 为准（改版时会变）。改动范围：

- 夹具：两个 issue（base 与 candidate 同步）和 `spec.md` 删除重复的要求行；`spec.md` 改写一行消除歧义（见「第 1 轮审计后的修正」）；源码、测试代码、存储合同、配置不改；
- 答案键：删除与被删要求行绑定的用例，`auditRecords` 重编行号；改写三条期望句、一个正例加一种放置（见「第 1 轮审计后的修正」）；
- `SCENARIO_REVISIONS` 中 commit-audit-reviewer 由 19 改为 20；
- ARW 自带的 conformance 测试按新行号和新用例数更新清单（`targeted Commit Audit capability binds three Requests …` 与三个按行号挑要求行的测试）。

评分规则、角色规则和交接不改；准备 / 生成 / 评分程序只改 `SCENARIO_REVISIONS` 一个常量。ARW 文档 `docs/agents/reviewer-capability-scenarios.md` 写明的清单数量已不再成立，差异见「与 ARW 合同的差异」。答案键 `159a586e…` 在 `judgment/registry.json` 登记为 `all-B`；分数只与 v2 比较，与 ARW 原版、F6 不可比。

## 起因

用户 2026-10-16/17 定下出题原则：同一道题只出一次，两个子场景之间、同一答案键内部都不得出现同一缺陷；重复就改题，不靠计分端打折或去重。

ARW 原版的 Gate 1（两个 issue 的验收项）和 Gate 2（`spec.md` 的长期规则）大量重述同一要求：12 个缺陷、约 23 个成立的事实各出了两次（一次带函数名写在 issue 里，一次不带函数名写在 spec 里），issue 内部还有几组同义行。例如 Gate 1 正例 15 与 Gate 2 正例 3 的期望句和证据完全相同（`redactManifestEvent`）。同一缺陷找到一次就在两个 Gate 各得一次分，漏掉一次就各失一次分，相当于加倍计权，也让场景更容易。

冻结工具同时加了通用检查（`tools/reviewer/freeze_arw_source.py` 的 `check_repeats`）：同一答案键内期望句相同，或证据相同，就报错；豁免只能逐键登记在 `judgment/repeats.json`。

## 做法

每组重复只保留一处要求行，删除其余行及其绑定用例。保留哪一处按以下顺序取舍：

1. 一处是另一处的超集（多一个独立性质）时保留超集，如 `computeBackoff` "doubles from 250 … caps at 2000" 保留、spec "backoff is capped at 2000" 删除；
2. 正例：否则优先保留需要定位语义对象的 spec 写法或调用链写法（如 spec `canAssignAllPackages` 经严格比较拒绝等于上限，保留；issue `withinVehicleCapacity` 直接写出函数名，删除）；issue 的 What to build 行（01:7）保留。反例多为同义行，按第 3 条（正例数相等、连续同结果约束）在两侧取舍；
3. 在此前提下让两个 Gate 的正例数相等（各 14），并让每份审计记录中连续同结果的要求行不超过 8 行（ARW 夹具设计约束，原测试断言）。

不改源码，不新增缺陷；保留行的文字只改一处（spec 路由令牌行，见下文）。

## 删除清单（原行号）

正例（12 组，Gate 1 删 6、Gate 2 删 6）：

| 缺陷 | 删除 | 保留 |
|---|---|---|
| 公共入口未导出 executor | spec:28 | 01:7 |
| `emitPlanCreated` 先于存储完成发出 | 01:29 | spec:43 |
| `parseRetryCount` 拒绝上界 3 | 01:31 | spec:61 |
| `executeAuthorizedPlan` 先派发后鉴权 | spec:57 | 01:21 |
| `restore` 部分写入后的返回值无合同（uncertain） | spec:55 | 01:45 |
| 通告失败不回滚已存 manifest | spec:18 | 02:22 |
| `redactManifestEvent` 漏删嵌套凭据 | 02:24 | spec:12 |
| NDJSON 缺末尾 LF | spec:48 | 02:33 |
| `orderManifestGroups` 降序 | 02:34 | spec:47 |
| `publishWithRetry` 不看 transient 标记 | spec:73 | 02:52 |
| `coalescePackages` 只在组内去重 | 02:56 | spec:23 |
| 容量谓词严格小于、拒绝等于上限 | 01:51 | spec:27 |

反例（成立的事实，29 行）：

| 事实 | 删除 | 保留 |
|---|---|---|
| 停靠点排序（01:19 = spec:7 + spec:67） | 01:19 | spec:7、spec:67 |
| `savePlan` 写入前完成校验 | spec:17 | 01:42 |
| 包裹重量合计 | spec:45 | 01:23 |
| `previewPlan` 不碰存储 | 01:34 | spec:30 |
| 访问日志脱敏 | spec:44 | 01:35 |
| 退避上限 | spec:32 | 01:43 |
| transient 分类要求显式标记 | 01:44 | spec:38 |
| 排程偏移原样保留 | spec:10 | 01:49 |
| 跳过已取消停靠点 | spec:26 | 01:50 |
| 司机标签去空白不改大小写（4 行同一事实） | 01:40、02:30、spec:16 | 02:54 |
| 通告去掉顶层凭据 | spec:33 | 02:19 |
| UTF-8 编码 | 02:20 | spec:74 |
| 空包裹 ID 使条目无效 | spec:59 | 02:21 |
| 空 manifest 的 entries 与 generated 标记 | 02:23、02:25 | spec:14 |
| manifest 分块不超上限 | 02:29 | spec:69 |
| 发布结果的成功 / 失败结构 | spec:58 | 02:39 |
| 计划存储键去空白并大写 | spec:71 | 02:40 |
| 包裹 ID 去空白、去重、排序 | 02:43、02:53 | spec:22 |
| 成功遥测字段 | spec:29 | 02:49 |
| 按规范化目的地键分组 | 02:50 | spec:53 |
| 失败遥测字段 | spec:15 | 02:51 |
| `checksumPlan` 对序列化字节求哈希 | 02:55 | 01:55 |
| 公共入口导出 `publishManifest`（与 02:7 同义） | 02:32 | 02:7 |
| 发布集成测试经公共入口导入（与 spec:52 正例同题） | 02:45 | spec:52 |
| 未生效的授权声明在规划前排除（与 01:54 同一事实） | spec:13 | 01:54 |

`spec:71` 与 `02:40` 的取舍是例外：按第 2 条应保留 spec 一侧，但那样 spec 审计记录会出现连续 9 行成立，违反第 3 条，所以改删 spec 一侧。

## 结果

| | ARW 原版 | v2 |
|---|---|---|
| Gate 1 正例（gap / uncertain） | 20（18 / 2） | 14（12 / 2） |
| Gate 2 正例（gap / uncertain） | 20（18 / 2） | 14（13 / 1） |
| Gate 1 / Gate 2 反例（不含 noOther） | 39 / 39 | 24 / 25 |
| 审计记录要求行（01 / 02 / spec） | 29 / 30 / 59 | 22 / 16 / 39 |
| `spec.md` 正文要求行 | 59 | 39 |

经审查保留的共用证据只有一组，登记在 `judgment/repeats.json`：Gate 1 正例 `problem/2`（从 0 起；原 01:24，v2 01:23，`chooseDeparture` 取本地小时而非 UTC，缺陷）与 Gate 2 反例 `clean/5`（spec:9，窗口含首尾小时，成立；`chooseDeparture` 第 1、4、5 行是可选证据）。两者问的是不同性质。

## 第 1 轮审计后的修正

第 1 轮 Opus（high）审计（78/79 行与盲审一致，无键外缺陷，未误删）提出的修正（以下 1–4 用原行号，与删除清单一致）：

1. 保留 02:19（`safeAnnouncement` omits a top-level credential，单数，成立），改删 spec:33（"omit top-level credential fields"，复数宽集合）：按正例 spec:11 的口径（凭据集合文本更广时不缩小），spec:33 也应判 gap，键却判成立，两处口径冲突；
2. 删 02:45：与 spec:52 正例问同一件事（集成测试是否经公共入口导入并调用），02:45 判成立、spec:52 判缺陷，报同一观察在一处得分、另一处算误报；
3. 删 spec:13：与 01:54（`selectActiveClaims`）是同一事实；
4. spec 原 76 行 "Route tokens combine the normalized destination and route key." 改为 "… and the normalized route key."，消除 "normalized" 是否修饰 route key 的歧义（第 1 轮盲答因此判为 uncertain）；
5. 期望句改写：两条 uncertain 改为 "No available contract establishes …"（原句只点名某一份合同，而缺的是任何可用合同）；重复检测一条改为 "… does not apply `normalizeRouteKey` (NFKC and uppercase)."（原句只说大写，实现同时缺 NFKC）；
6. `chooseDeparture` 正例增加一种放置：关联证据取 `schedule.mjs` 第 1 行（函数定义），与原放置并列，任一种即可匹配。

裁决口径（判定候选是否与用例匹配时使用，冻结前随答案键一起确认；行号均为 v2 夹具行号）：

- 把令牌字段置为 `undefined` 算移除（JSON 序列化后不出现）；
- `localeCompare` 视为字典序；
- spec:10（"Stable JSON sorts keys recursively at every object depth."，Gate 2 正例 `toStableJson` 只排顶层）：finding 指出只排顶层、嵌套对象顺序不变即匹配，不必写出"递归"；
- 01:46（"`serializePlan` sorts keys lexically, uses two-space JSON, and ends with one LF."，Gate 1 正例：格式模式导致缺末尾 LF）：finding 必须指出缺末尾 LF；只以"只排顶层"或 `localeCompare` 为理由的 finding 不匹配，裁为 `unsupported`。

## 与 ARW 合同的差异

规则「不裁剪用例」指使用冻结 ARW 的原场景。v2 删除了 ARW 原版的 41 个用例（12 正例、29 反例），属于改变合同，依据是用户 2026-10-16/17 的去重原则；删除而不是换新题，是因为换新题要新造缺陷代码，难度和效度都要重新审计。另一种做法是删除后补新题，保持每 Gate 20 正例，留待 Main 决定。

ARW `docs/agents/reviewer-capability-scenarios.md`「Commit Audit scenario」段和「Case inventory」段的约定与 v2 的对照如下。该文档是评分升级补丁（`scoring-k.patch`）的成员，冻结工具要求它与原版或升级版逐字节一致，所以 v2 补丁不改它；对 Commit Audit 而言以本节为准。该文档不进入 Reviewer 的交接，不影响被测模型。

| 约定 | ARW 原值 | v2 值 |
|---|---|---|
| 每 Gate 正式要求 | 59 | Gate 1 38（issue 01 22、issue 02 16），Gate 2 39 |
| 每 Gate 问题用例 | 20（18 gap + 2 uncertain） | Gate 1 14（12 + 2），Gate 2 14（13 + 1） |
| 每 Gate 干净用例（含 1 个 noOther） | 40 | Gate 1 25，Gate 2 26 |
| 单行字面量问题 | 最多 4（原测试断言恰为 4） | 最多 4（实际各 3；测试只断言列名的至少 2 个） |
| 需多处证据的问题 | 至少 12 | 至少 8（实际各 11） |
| 近邻对照干净用例 | 至少 20 | 至少 12（各列 13 个） |
| 问题与干净比例 | 两 Gate 相同，`1:2` | 不再保持（14:25、14:26），两 Gate 全量评分 |
| 「Commit Audit 使用前述固定完整审计清单」 | ARW 原清单 | 本 v2 清单 |
| 合并清单下限（问题 ≥ 20、干净 ≥ 20） | 满足 | 满足（28、51） |
| 缩减清单时同步修复或移除不再保留的可见真实缺陷 | — | 满足：被删 12 个正例的缺陷都由保留行覆盖，源码没有失去考点的缺陷 |

ARW conformance 测试的对应断言随补丁改为上表 v2 值；改后失败集与「ARW 原版 + 本工程评分补丁」相同（26 个既有失败，均来自评分补丁，与 v2 无关）。

## 审计

第 1 步（Opus high 审计 + 盲答循环）的记录见下文各轮，冻结前另需独立审查。
