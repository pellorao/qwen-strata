# 下一版场景修订：已发现的文本歧义

截至 2026-10-21 的多模型 benchmark 第一批盲裁与复核。用户 10-20 定：本次 benchmark 结束后，从源头改掉有两种读法的句子。已由先例定下判法的也列在这里，下一版要从场景原文或 brief 里消除。现行判法以 [rulings.md](rulings.md) 为准。

分三类：(a) 场景原文（规格、被审代码、Role、workflow）有两种读法；(b) 裁决 brief 或评分规则措辞有歧义或互相矛盾；(c) 答案键或锚点定论有误。

## (a) 场景原文

| 编号 | 场景与位置 | 问题 | 现行处理 | 影响 | 改写方向 |
|---|---|---|---|---|---|
| A1 | CS `governing-spec.md:160` | "Catalog locale keys and a member's `locale` are trimmed and lowercased, a missing or blank locale being `en`."：空白目录键是否也归 `en` | rulings「CS v5 governing-spec.md:160」（用户定 10-20）：不归，判 unsupported，报告另给判 supported 时的分数 | 13 条（另 10-14 试点 1 条） | 拆成两句，分别写明成员 locale 与目录键的处理 |
| A2 | CA 需求行 `01:30`、`spec:59`，规则 `dispatch-policy.md:42-43` | "returns an error result"：指带 `error` 字段的结果，还是 `ok:false` 即可 | 可执行检查定不了（两种读法下代码行为相同：被拒输入返回 `{ok:false}`，无 `error` 字段），确属两可。主读法按答案键：`ok:false` 即可，ca-1-150 判 supported（它讲到 `Number` 强转），ca-2-137 判 unsupported（10-21）；报告另给"须带 `error` 字段"读法下的分数（该读法下两条都判 supported，ca-56-130、ca-56-135 逐条复核） | 4 条 | 需求行写明错误结果的形状 |
| A3 | CA `dispatch-policy.md:52-54`（规则 26、27），需求行 `spec:71` / `02:46` | 规则 26"带有限 `retryAfter` 的失败也是 transient"与规则 27"`transient: false` 永不 transient"哪个优先 | 经核对不是歧义：政策文档头写明"同节内后一条覆盖前一条"，规则 27 在 26 之后，所以规则 27 优先，与答案键一致（10-21）。ca-2-143 没有写出 `transient: false`，按 brief:46 不匹配问题用例，维持 supported | 1 条 | 文档头的覆盖规则离规则 26、27 太远，容易漏看；规则 26 直接加"除非标为 `transient: false`" |
| A4 | SR `promotion-recovery.md:65`、`:85` | recoverPromotion 拒绝调用方自报，与别处状态读取要求是否矛盾 | 判 unsupported，复核同意但认为较难 | 6 条 | 待确认是否真有歧义；改成一处写清来源要求 |
| A5（待核） | SR `promotion-runtime.md:11`、`:15`、`:45`、`:97` 与 Acceptance criteria | request binding、`retentionDays`、ADR 0004/0005、测试分支等，多个模型反复提出同类 finding | 都判 unsupported，复核全部同意 | 83 条（RM 21、AP 62） | 只是推测：逐类确认后，在规格里对常见误报加一句明确排除 |

## (b) brief 与评分措辞

| 编号 | 场景与位置 | 问题 | 现行处理 | 影响 | 改写方向 |
|---|---|---|---|---|---|
| B1 | 四份 brief 第 21 行，SR brief 第 30 行 | CS、CStd 写"答案键外的成立缺陷"，CA 写"不对应任何列出的问题用例"，SR 另有明文：答案键内缺陷挂在别处判 supported | rulings「答案键里的缺陷挂在了别的位置」（用户定 10-21，经独立审查）：统一判 supported | CA 4 条、SR 42 条（另 sr-1-206） | 四份 brief 统一一句；写明已满足行按 r8.1 判误报的例外；CStd brief:31、:33"修法与干净用例相反、未被提名判 unsupported"注明为何方向不同 |
| B2 | CA brief 第 21 行 | 只说"违背 / 未满足"、不讲机制的 finding 算什么，brief 没写 | rulings「CA 只说违背」（用户定 10-21）：判 unsupported | 22 条由 supported 改判，另 22 条原本就是 unsupported | brief 明写 finding 须写出具体机制，否则判 unsupported |
| B3 | CA brief 第 21 行（r8.1） | finding 落在已满足行、讲的却是相邻行的真缺陷：判误报还是 supported，池间不一致 | rulings「挂在已满足的要求行上」（规则 r8.1）：判所挂行误报 | 25 条，含孪生 clean 行 02:30 与 spec:45 | brief 写明决策树（先看挂载行是否满足）；孪生行在 brief 里点名 |
| B4 | CStd brief 第 33 行（中性规则） | "只存在于未改动文件的既有问题"是否包括新代码照搬已有多份的同构机制 | rulings「新代码照搬仓库里已有多份的重复实现」（用户定 10-21）：算本次变更的问题，判 supported | 6 条 | 改写为"重复完全在未改动文件里的情形"，并补一句照搬算本次变更的问题 |
| B5 | SR brief 第 27、29、40 行（m1） | :40 只写了 RM"委托给未选 Interfaces 节"一种；依据其他未选节的类推是否同判 | 判 unsupported；RM、AP 按 :27 独立判定 | RM 类推 11 条、委托 12 条，AP 未选节 27 条 | :40 扩写为"依据未选节的 finding 一律 unsupported" |
| B6 | SR brief 第 30 行 | 判据是答案键的 placement，裁决者看不到答案键，只能从 `problemOptions` 推断；EXEMPTION 正例 0 与 APPLICABILITY 正例 0 边界模糊 | sr-1-206 已改 supported；sr-20-105 不确定，维持原判 | 2 条 | 给裁决者 placement 简表，或写明两者边界 |
| B7 | CA 需求文件行号 | 模型把要求行号整体数错 | rulings「CA 要求行号整体错位」（用户定 10-21）：原文能唯一定位就改挂并计格式错误 | luna-low-a7 改挂 16 行；另 ca-14-134、ca-14-136 | 需求行加显式编号，或在 handoff 里给行号对照 |

## (c) 答案键与锚点

| 编号 | 场景与位置 | 问题 | 现行处理 | 影响 | 改写方向 |
|---|---|---|---|---|---|
| C1 | CStd 锚点 a06（期望句 P13：catering-store 写成 class） | 原定 not-matched，但 finding 单列了这一缺陷，按"一条 finding 讲两个缺陷"应判对上 | a06 改为 matched，另加 not-matched 锚点 cstd-9-130 | 24 个池的锚点门槛无余量 | 若下一版仍考 P13，把"重复实现"和"写成 class"分成两个独立用例 |

## 未决事项

