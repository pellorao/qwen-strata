# Commit Audit 能力场景 v2：相对 ARW 原版的变更说明（草稿，未冻结）

v2 以补丁 [`arw-patches/commit-audit-v2.patch`](arw-patches/commit-audit-v2.patch) 提供，登记在 `source-snapshots/current/manifest-commit-audit-v2.json`（即 `manifest.json` 加上这一项）。补丁 sha256 以 manifest 为准（改版时会变）。改动范围：

- 夹具：两个 issue（base 与 candidate 同步）和 `spec.md` 删除重复的要求行；源码、测试代码、存储合同、配置不改；
- 答案键：删除与被删要求行绑定的用例，`auditRecords` 重编行号；
- `SCENARIO_REVISIONS` 中 commit-audit-reviewer 由 19 改为 20；
- ARW 自带的 conformance 测试按新行号和新用例数更新清单（`targeted Commit Audit capability binds three Requests …` 与三个按行号挑要求行的测试）。

评分规则、角色规则、交接，以及准备 / 生成 / 评分程序都不改。答案键 `f583cc7c…` 在 `judgment/registry.json` 登记为 `all-B`；分数只与 v2 比较，与 ARW 原版、F6 不可比。

## 起因

用户 2026-10-16/17 定下出题原则：同一道题只出一次，两个子场景之间、同一答案键内部都不得出现同一缺陷；重复就改题，不靠计分端打折或去重。

ARW 原版的 Gate 1（两个 issue 的验收项）和 Gate 2（`spec.md` 的长期规则）大量重述同一要求：12 个缺陷、约 23 个成立的事实各出了两次（一次带函数名写在 issue 里，一次不带函数名写在 spec 里），issue 内部还有几组同义行。例如 Gate 1 正例 15 与 Gate 2 正例 3 的期望句和证据完全相同（`redactManifestEvent`）。同一缺陷找到一次就在两个 Gate 各得一次分，漏掉一次就各失一次分，相当于加倍计权，也让场景更容易。

冻结工具同时加了通用检查（`tools/reviewer/freeze_arw_source.py` 的 `check_repeats`）：同一答案键内期望句相同，或证据相同，就报错；豁免只能逐键登记在 `judgment/repeats.json`。

## 做法

每组重复只保留一处要求行，删除其余行及其绑定用例。保留哪一处按以下顺序取舍：

1. 一处是另一处的超集（多一个独立性质）时保留超集，如 `computeBackoff` "doubles from 250 … caps at 2000" 保留、spec "backoff is capped at 2000" 删除；
2. 否则优先保留需要定位语义对象的 spec 写法或调用链写法（如 spec `canAssignAllPackages` 经严格比较拒绝等于上限，保留；issue `withinVehicleCapacity` 直接写出函数名，删除）；issue 的 What to build 行（01:7）保留；
3. 在此前提下让两个 Gate 的正例数相等（各 14），并让每份审计记录中连续同结果的要求行不超过 8 行（ARW 夹具设计约束，原测试断言）。

不改源码，不新增缺陷，不改写保留行的文字。

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

反例（成立的事实，27 行）：

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
| 通告去掉顶层凭据 | 02:19 | spec:33 |
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

`spec:71` 与 `02:40` 的取舍是例外：按第 2 条应保留 spec 一侧，但那样 spec 审计记录会出现连续 9 行成立，违反第 3 条，所以改删 spec 一侧。

## 结果

| | ARW 原版 | v2 |
|---|---|---|
| Gate 1 正例（gap / uncertain） | 20（18 / 2） | 14（12 / 2） |
| Gate 2 正例（gap / uncertain） | 20（18 / 2） | 14（13 / 1） |
| Gate 1 / Gate 2 反例（不含 noOther） | 39 / 39 | 24 / 27 |
| 审计记录要求行（01 / 02 / spec） | 29 / 30 / 59 | 22 / 16 / 41 |
| `spec.md` 正文要求行 | 59 | 41 |

经审查保留的共用证据只有一组，登记在 `judgment/repeats.json`：Gate 1 正例 3（01:24，`chooseDeparture` 取本地小时而非 UTC，缺陷）与 Gate 2 反例 7（spec:9，窗口含首尾小时，成立；`chooseDeparture` 第 1、4、5 行是可选证据）。两者问的是不同性质。

## 与 ARW 合同的差异

规则「不裁剪用例」指使用冻结 ARW 的原场景。v2 删除了 ARW 原版的 39 个用例（12 正例、27 反例），属于改变合同，依据是用户 2026-10-16/17 的去重原则；删除而不是换新题，是因为换新题要新造缺陷代码，难度和效度都要重新审计。另一种做法是删除后补新题，保持每 Gate 20 正例，留待 Main 决定。

## 审计

第 1 步（Opus high 审计 + 盲答循环）的记录见下文各轮，冻结前另需独立审查。
