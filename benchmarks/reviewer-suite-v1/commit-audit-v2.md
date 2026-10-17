# Commit Audit 能力场景 v2：相对 ARW 原版的变更说明（草稿，未冻结）

v2 以补丁 [`arw-patches/commit-audit-v2.patch`](arw-patches/commit-audit-v2.patch) 提供，登记在 `source-snapshots/current/manifest-commit-audit-v2.json`（即 `manifest.json` 加上这一项）。补丁 sha256 以 manifest 为准（改版时会变）。现行为修订号 22（用户 2026-10-17；修订号 21 的修正见「修订号 22」），改动范围：

- 夹具：两个 issue（base 与 candidate 同步）和 `spec.md` 删除 11 行意外重复的要求行；`spec.md` 改写一行消除歧义（见「第 1 轮审计后的修正」）；源码、测试代码、存储合同、配置不改；
- 答案键：删除与被删要求行绑定的用例，`auditRecords` 重编行号；issue 与 spec 之间有意保留的重复成对声明为合并用例（`merge` 字段，29 对；其中两对先统一两侧的期望证据）；改写三条期望句、一个正例加一种放置；
- `SCENARIO_REVISIONS` 中 commit-audit-reviewer 由 19 改为 22；
- ARW 自带的 conformance 测试按新行号和新用例数更新清单，复制问题用例的测试去掉复制出的 `merge`；conformance 接受 `merge` 字段（评分 r8.2，`scoring-k.patch`）。

角色规则和交接不改，测量说明追加一句（见「测量说明」）。答案键 `5cf73928…` 在 `judgment/registry.json` 登记为 `all-B`，需评分 r8.3；分数只与修订号 22 比较，与修订号 20、21、ARW 原版、F6 不可比。

## 起因

用户 2026-10-16/17 定下出题原则：同一道题只出一次，两个子场景之间、同一答案键内部都不得出现同一缺陷。

ARW 原版的 Gate 1（两个 issue 的验收项）和 Gate 2（`spec.md` 的长期规则）大量重述同一要求：12 个缺陷、约 23 个成立的事实各出了两次（一次带函数名写在 issue 里，一次不带函数名写在 spec 里），issue 内部还有几组同义行。同一缺陷找到一次就在两个 Gate 各得一次分，漏掉一次就各失一次分，相当于加倍计权。

修订号 20 删掉每组重复的一侧（正例 40 → 28、反例 80 → 51）。用户 2026-10-17 改定（修订号 21）：

1. 恢复 ARW 原版 issue 与 spec 之间的重复要求行；issue 内部的同义行仍删除；
2. 有意保留的重复在答案键里成对声明为合并用例：两份各判一次、取低分、只计一次（正例、反例都适用）；
3. 测量说明追加一句英文，告诉 reviewer 重复要求只计一次分、可引用已审过的行并照抄结论和证据；不改 ARW 报告格式、不新增结果类型，只追加、不改原版交接和 Role；
4. 出题原则改为"意外的重复改题；有意保留的重复必须在答案键里显式声明，评分按声明合并"；"不靠计分端去重"继续有效（合并只按答案键的声明进行，计分端不自行识别重复）。

冻结工具的通用检查（`tools/reviewer/freeze_arw_source.py` 的 `check_repeats`）：同一答案键内期望句相同或证据相同就报错，由同一合并用例的两个用例组成的组除外；其余豁免只能逐键登记在 `judgment/repeats.json`。

## 做法

从 ARW 原版出发，只删以下三类行（及其绑定用例），其余 issue 与 spec 的重复保留：

1. issue 一侧的内部重复（同一 Gate 内两行问同一件事）；
2. 非一对一的重复：一行同时重述另一侧的两行，或两行合起来才等于另一侧一行，无法成对合并；
3. 口径冲突：两行问同一件事、键给出不同结论，或一行的口径与同类正例冲突。

保留的 issue / spec 重复对，问的是同一个要求就声明为合并用例，两侧期望证据须相同（原本不同的先统一，见「修订号 22」）；不是同一个要求的按两道题分别计分（见「未合并的恢复行」）。冻结工具要求合并用例两侧的期望证据相同，否则报错。

## 删除清单（原行号）

| 删除 | 类别 | 说明 |
|---|---|---|
| 01:19 | 非一对一 | 停靠点排序，等于 spec:7 + spec:67 两行 |
| 01:40 | issue 内部 | 司机标签去空白不改大小写，与 02:54 同义（01:40、02:30、02:54、spec:16 四行同一事实，保留 02:54 与 spec:16） |
| 02:23、02:25 | 非一对一 | 空 manifest 的 entries 与 generated 标记，两行合起来对应 spec:14 |
| 02:30 | issue 内部 | 同 01:40 |
| 02:32 | issue 内部 | 公共入口导出 `publishManifest`，与 02:7 同义 |
| 02:43、02:53 | 非一对一 | 包裹 ID 去空白、去重、排序，两行合起来对应 spec:22 |
| 02:45 | 口径冲突 | 集成测试经公共入口导入：02:45 判成立、spec:52 判缺陷，同一观察一处得分一处算误报 |
| 02:55 | issue 内部 | `checksumPlan` 对序列化字节求哈希，与 01:55 同义 |
| spec:33 | 口径冲突 | "omit top-level credential fields"（复数宽集合），按正例 spec:12（原行号，`redactManifestEvent`）的口径应判 gap，键判成立；保留 02:19（单数，成立） |

修订号 20 删除的 spec:13 恢复：它与 01:54（`selectActiveClaims`）不是同一道题，见「未合并的恢复行」。

## 合并用例（新行号，29 对）

合并用例名就是 `merge` 字段的值。正例 12 对：

| 合并用例 | 缺陷 |
|---|---|
| 01:7+spec:28 | 公共入口未导出 executor |
| 01:20+spec:56 | `executeAuthorizedPlan` 先派发后鉴权 |
| 01:28+spec:42 | `emitPlanCreated` 先于存储完成发出 |
| 01:30+spec:60 | `parseRetryCount` 拒绝上界 3 |
| 01:43+spec:54 | `restore` 部分写入后的返回值无合同（uncertain） |
| 01:49+spec:27 | `withinVehicleCapacity` 严格小于，拒绝等于上限（修订号 22） |
| 02:22+spec:18 | 通告失败不回滚已存 manifest |
| 02:23+spec:12 | `redactManifestEvent` 漏删嵌套凭据 |
| 02:29+spec:47 | NDJSON 缺末尾 LF |
| 02:30+spec:46 | `orderManifestGroups` 降序 |
| 02:46+spec:72 | `retryPublication` 不看 transient 标记 |
| 02:48+spec:23 | `coalescePackages` 只在组内去重 |

反例 17 对：

| 合并用例 | 事实 |
|---|---|
| 01:22+spec:44 | 包裹重量合计 |
| 01:33+spec:30 | `previewPlan` 不碰存储 |
| 01:34+spec:43 | 访问日志脱敏 |
| 01:40+spec:17 | `savePlan` 写入前完成校验 |
| 01:41+spec:32 | 退避倍增与上限（spec 只写上限，两侧证据相同） |
| 01:42+spec:37 | transient 分类要求显式标记 |
| 01:47+spec:10 | 排程偏移原样保留 |
| 01:48+spec:26 | 跳过已取消停靠点 |
| 02:20+spec:73 | UTF-8 编码 |
| 02:21+spec:58 | 空包裹 ID 使条目无效 |
| 02:27+spec:68 | manifest 分块不超上限 |
| 02:35+spec:57 | 发布结果的成功 / 失败结构 |
| 02:36+spec:70 | 计划存储键去空白并大写 |
| 02:43+spec:29 | 成功遥测字段 |
| 02:44+spec:52 | 按规范化目的地键分组 |
| 02:45+spec:15 | 失败遥测字段 |
| 02:47+spec:16 | 司机标签去空白不改大小写（修订号 22） |

## 未合并的恢复行

以下一组在 ARW 原版里是 issue 与 spec 的相近要求，修订号 20 当作重复删了一侧。它们问的不是同一个要求，按两道题分别计分：

| issue 行 | spec 行 | 区别 |
|---|---|---|
| 01:52 `selectActiveClaims` 排除未开始和已过期的声明（反例） | spec:13 未生效的授权声明在规划前排除（反例） | 函数自身的时间边界（`access.mjs:1`、`:16`）与规划流程里的过滤（`queue.mjs:7–8`）；`createDispatchPlan` 内联过滤、不调用 `selectActiveClaims`，一侧成立推不出另一侧成立 |

两行文字已足够不同（一行点名函数和时间边界，一行讲规划流程），照抄另一行的证据本身就是审查错误，测量说明的"重复要求只计一次"不覆盖它。

## 修订号 22（用户 2026-10-17）

修订号 21 留下三组恢复行不合并，理由是两侧期望证据不同；但测量说明承诺重复要求只计一次、可照抄，reviewer 分不出哪些相近行不算重复，照抄会失分。Main 决定逐组判断两侧是否同一个要求：是就统一期望证据后合并；不是且文字几乎相同就删一行。结果：

| 组 | 判断 | 处理 |
|---|---|---|
| 01:49 / spec:27 | 同一要求：容量等于上限时应接受，缺陷只有一处（`capacity.mjs:3` 的严格小于），`canAssignAllPackages`（第 14 行）只是委托 | 两侧问题用例都接受两种放置：关联第 3 行、证据第 3 行；或关联第 14 行、证据第 1、3、14 行（原 spec:27 放置）。声明合并 `01:49+spec:27` |
| 02:47 / spec:16 | 同一要求：issue 行就是 spec 规则带上函数名（ARW 的写法），`preserveManifestDriver` 直接委托 `preserveDriverLabel` | 两侧反例都接受两组证据：`manifest.mjs:24` + `normalize.mjs:5`，或 `normalize.mjs:1`、`:5`（`evidenceAlternatives`）。声明合并 `02:47+spec:16` |
| 01:52 / spec:13 | 不是同一要求（见上节） | 保留分开计分，文字已足够不同，不删行 |

两侧的期望句和 `findingTerms` 保持原样（`findingTerms` 对问题用例只作裁决参考，反例按要求行提名）。夹具文字、行号、正反例数不变，只改答案键；单行字面量问题与多处证据问题的清单不变（01:49 仍有单行放置，spec:27 仍有多行放置）。

## 结果

| | ARW 原版 | 修订号 20 | 修订号 21、22 |
|---|---|---|---|
| Gate 1 正例（gap / uncertain） | 20（18 / 2） | 14（12 / 2） | 20（18 / 2） |
| Gate 2 正例（gap / uncertain） | 20（18 / 2） | 14（13 / 1） | 20（18 / 2） |
| Gate 1 / Gate 2 反例（含 noOther） | 40 / 40 | 25 / 26 | 30 / 39 |
| 合并用例（正例 / 反例） | — | — | 12 / 17（修订号 21 为 11 / 16） |
| 计分单位（正例 / 反例，合并后） | 40 / 80 | 28 / 51 | 28 / 52（修订号 21 为 29 / 53） |
| 审计记录要求行（01 / 02 / spec） | 29 / 30 / 59 | 22 / 16 / 39 | 27 / 22 / 58 |

经审查保留的共用证据只有一组，登记在 `judgment/repeats.json`：Gate 1 正例 `problem/2`（从 0 起；`chooseDeparture` 取本地小时而非 UTC，缺陷）与 Gate 2 反例 `clean/10`（窗口含首尾小时，成立；`chooseDeparture` 第 1、4、5 行是可选证据）。两者问的是不同性质。

## 测量说明

Commit Audit 的测量说明是通用说明加一句（`measurement-note-commit-audit.txt`；限时版 `measurement-note-time-limit-commit-audit.txt`），由 plan 的 `fixed_conditions.measurement_note_path` 指定，sha 照常绑定在 `measurement_note_sha256`（或限时版的 `measurement_note_template`）：

> Repeated requirements: a requirement that the spec and an issue both state is scored once. When you reach the second row, you may cite the row you already reviewed and copy its conclusion and evidence.

通用说明 `measurement-note.txt` 被所有场景共用，不改。说明只追加在交接之后，原版交接和 Role 不改；报告格式不变，两行仍各写一行判断。

## 第 1 轮审计后的修正

第 1 轮 Opus（high）审计（修订号 20）提出的修正，修订号 21 的处理（原行号）：

1. 删 spec:33、保留 02:19：仍然有效（口径冲突，见删除清单）；
2. 删 02:45：仍然有效（口径冲突）；
3. 删 spec:13：撤销，spec:13 恢复，与 01:54 按不同的题计分（见「未合并的恢复行」）；
4. spec 原 76 行 "Route tokens combine the normalized destination and route key." 改为 "… and the normalized route key."（新行号 spec:75），消除 "normalized" 是否修饰 route key 的歧义；
5. 期望句改写：两条 uncertain 改为 "No available contract establishes …"（原句只点名某一份合同，而缺的是任何可用合同）；重复检测一条改为 "… does not apply `normalizeRouteKey` (NFKC and uppercase)."（原句只说大写，实现同时缺 NFKC）；
6. `chooseDeparture` 正例增加一种放置：关联证据取 `schedule.mjs` 第 1 行（函数定义），与原放置并列，任一种即可匹配。

裁决口径（判定候选是否与用例匹配时使用，冻结前随答案键一起确认；行号为修订号 21、22 夹具行号，两者夹具相同）：

- 把令牌字段置为 `undefined` 算移除（JSON 序列化后不出现）；
- `localeCompare` 视为字典序；
- spec:11（"Stable JSON sorts keys recursively at every object depth."，Gate 2 正例 `toStableJson` 只排顶层）：finding 指出只排顶层、嵌套对象顺序不变即匹配，不必写出"递归"；
- 01:51（"`serializePlan` sorts keys lexically, uses two-space JSON, and ends with one LF."，Gate 1 正例：格式模式导致缺末尾 LF）：finding 必须指出缺末尾 LF；只以"只排顶层"或 `localeCompare` 为理由的 finding 不匹配，裁为 `unsupported`。
- 引用已审行（第 3 轮审计）：finding 只引用已审行（如 "Same as spec:28"）并照抄结论与证据时，按被引行的 finding 文本裁决。被引行与本用例同属一个合并用例时，本行裁决与被引行相同；不在同一合并用例时（例如 spec:13 引 01:52），引用本身不构成理由，按本行自身的期望句裁决。
- 合并用例的候选与两侧任一期望句描述的是同一缺陷即算匹配（例如 01:49+spec:27 一侧只谈 `withinVehicleCapacity` 的严格小于，另一侧期望句点名 `canAssignAllPackages`，仍算匹配）。

## 与 ARW 合同的差异

规则「不裁剪用例」指使用冻结 ARW 的原场景。修订号 21、22 删除了 ARW 原版的 11 个反例（正例不删），属于改变合同，依据是用户 2026-10-16/17 的出题原则；另把 29 对重复声明为合并用例，计分单位少于用例数。

ARW `docs/agents/reviewer-capability-scenarios.md`「Commit Audit scenario」段和「Case inventory」段的约定与修订号 22 的对照如下。该文档是评分升级补丁（`scoring-k.patch`）的成员，冻结工具要求它与原版或升级版逐字节一致，所以 v2 补丁不改它；对 Commit Audit 而言以本节为准。该文档不进入 Reviewer 的交接，不影响被测模型。

| 约定 | ARW 原值 | 修订号 22 |
|---|---|---|
| 每 Gate 正式要求 | 59 | Gate 1 49（issue 01 27、issue 02 22），Gate 2 58 |
| 每 Gate 问题用例 | 20（18 gap + 2 uncertain） | 20（18 + 2） |
| 每 Gate 干净用例（含 1 个 noOther） | 40 | Gate 1 30，Gate 2 39 |
| 单行字面量问题 | 最多 4 | 各 4 |
| 需多处证据的问题 | 至少 12 | Gate 1 13，Gate 2 12 |
| 近邻对照干净用例 | 至少 20 | 至少 15（Gate 1 列 15 个，Gate 2 列 19 个） |
| 问题与干净比例 | 两 Gate 相同，`1:2` | 不再保持（20:30、20:39），两 Gate 全量评分 |
| 「Commit Audit 使用前述固定完整审计清单」 | ARW 原清单 | 本修订号 22 清单 |
| 合并清单下限（问题 ≥ 20、干净 ≥ 20） | 满足 | 满足（用例 40、69；合并后计分单位 28、52） |
| 缩减清单时同步修复或移除不再保留的可见真实缺陷 | — | 满足：没有删除正例 |

ARW conformance 测试的对应断言随补丁改为上表的值；改后失败集与「ARW 原版 + 本工程评分补丁」相同（26 个既有失败，均来自评分补丁，与 v2 无关）。

## 审计

第 1 步（Opus high 审计 + 盲答循环）的记录见下文各轮，冻结前另需独立审查。

- 第 2 轮审计 S1（评分端）：审查者把 satisfied 行判成 gap 或 uncertain 时，该行反例已经因干净观察失败；finding 又因证据或 `findingTerms` 对不上而提名不到该反例，只能裁成无依据，再占掉 noOther，同一个错误扣两次。用户 2026-10-17 采用 A：由评分 r8.1 修复（`scoring-k.patch`）。落在 satisfied 行上的 finding 按 `requirementSource` 直接提名该行反例；裁为无依据时也只让该反例失败，只扣一次。两次 Opus 盲答按 r8.1 重算，分数不变（0.858、0.840）。
- 修订号 21（用户 2026-10-17，见「起因」）：评分 r8.2 实现合并用例计分。两次 Opus 盲答（修订号 20 夹具上作答，opus-1 用的还是第 1 轮修正前的夹具）换算到修订号 21 后重算，只用于核对实现，见下表。

| 盲答 | 耗时 | token（未缓存 / 缓存写入 / 缓存读取 / 输出） | 工具调用 | r8.1（修订号 20） | r8.2（修订号 21，缺行留空） | r8.2（修订号 21，相近行照抄） |
|---|---|---|---|---|---|---|
| opus-1 | 2.9 分钟 | 24 / 70,248 / 440,930 / 19,622 | 11 | 0.858 | 0.815 | 0.852 |
| opus-2 | 2.5 分钟 | 20 / 74,398 / 357,369 / 15,623 | 10 | 0.840 | 0.793 | 0.830 |

换算做法：按要求行文字把旧报告映射到新行号；新夹具恢复、旧报告没有的行，若是合并用例的一侧，照抄另一侧的结论与证据（即测量说明允许的做法）；三条未合并的恢复行（01:49、spec:13、spec:16）在"缺行留空"列留空（记缺行），在"相近行照抄"列从相近行照抄，作为上界估计；opus-1 的夹具没有 02:19，两列都留空。裁决沿用旧裁决（同一 finding 与期望句，或合并对的另一侧），新出现的两个候选按 finding 文字裁为匹配。耗时和 token 是修订号 20 夹具上的实际运行（78–79 行要求），修订号 21 有 107 行，不能外推。旧报告本身的格式诊断（opus-2 一行重复）照旧保留。

- 修订号 22 与评分 r8.3（2026-10-17）：上表未按修订号 22 重算。修订号 22 只把 01:49/spec:27、02:47/spec:16 两组改为合并用例（统一证据），预期分数落在上表两列之间、接近"相近行照抄"列；r8.3 只限制发现候选的补关联范围，两次盲答的裁决里没有发现候选裁到问题用例的决定，不受影响。下一轮盲答直接在修订号 22 夹具上作答。
- 第 3 轮（修订号 22，2026-10-17）：Opus（high）审计确认 29 对合并两侧证据一致、11 行删除合理、行号一致；补了两条裁决口径（引用已审行、合并用例按任一侧期望句裁）并改正删除清单一处行号。待定：测量说明是否限定"重复"的范围（01:52/spec:13、02:31/spec:8 两对与 01:23 对 spec:9、spec:71 的超集照抄会失分）、spec:13 措辞是否点名 `createDispatchPlan` 的 `activeClaims`。Opus（high）盲答 0.848（r8.3），172 秒、8 次工具调用、输出 20,525 token；29 对合并中 26 对两侧逐字照抄，未写引用句；01:52/spec:13 两侧分别作答。
