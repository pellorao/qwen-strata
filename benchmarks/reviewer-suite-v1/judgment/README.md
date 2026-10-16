# A 类标记（两类计分）

两类计分（用户 2026-10-15，规则见 `.claude/rules/measurement.md`「评分口径」）把用例分成 A、B 两类。本目录存放冻结场景的 A 类标记，不改冻结件。

## 文件

- `registry.json`：登记表。把每个已知答案键（reviewerId 和 `expected.json` 的 sha256）对应到一个覆盖文件，或写明 `in-key`（A 类标记直接写在答案键用例的 `judgment: true` 字段）或 `all-B`（全部按 B 计分）。
- `<场景>.json`：覆盖文件。字段有：
  - `reviewerId`、`expectedSha256`：所标记的答案键。
  - `counts`：正例数和反例数。
  - `cases`：每个 A 类用例的 `scope`、`kind`（`problem` 或 `clean`）、`index`（0 起）、`expectation` 原文和标定理由 `reason`。

计分入口（`tools.reviewer.freeze_arw_source.upgrade_scoring`）会检查副本里的每个答案键。答案键没有登记就报错。覆盖文件与答案键对不上、正反例数不等或 `counts` 不符，也报错。登记为 `in-key` 的答案键必须带有标记且正反数相等；没登记为 `in-key` 的答案键带有标记，说明登记与实际不符，同样报错。检查通过后，把登记表和所用覆盖文件复制到 `<arw>/reviewer-judgment/`。ARW 加载答案键时再核对一次，并在计分结果的 `judgmentBinding` 里写明所用覆盖文件的名字和 sha256，标记在答案键里时写 `in-key` 和答案键 sha256，全 B 时写 `all-B`。

新的场景版本（包括草稿）都要先登记才能计分；还没有标定的版本登记为 `all-B`。

## 分界标准

看答错与答对对项目的影响是否大致相当，同时考虑 main agent 能否验证并拦住错误答案：

- B 类：违反规格、缺陷、漏洞，以及与它们对应的合规写法。误报可以用具体输入、复现、测试或对照规格核实，main agent 能排除。
- A 类：答错会促成同样有分量的改动，而且没有可执行的核对方法。例如该不该合并：不该合并的被合并了，可能引入严重 bug，main agent 也未必拦得住。

每个用例独立判断，不配对。每个计分单位中，正例和反例的总数要相等，这样"一律报"和"一律不报"都得 0。Spec Readiness 的计分单位是一次重复（RM 与 AP 合并）。同一 A 类用例在两个子场景都计分时，每次按 0.5 计。标定只看场景、答案键和设计说明，不看模型结果；生效前要经独立审查。

## 现状（2026-10-15，已经独立审查）

| 场景 | 登记 | 说明 |
|---|---|---|
| Spec Readiness v4.1 | 全 B（过渡期） | A 类随 v4.2 的覆盖文件提交 |
| Spec Readiness v4.2（2026-10-16 冻结） | `spec-readiness-v4.2.json` | 4:4（RM 1:0，AP 3:4）：新增 2 个正例、2 个反例，REQUIREMENTS 反例 3、4 改 B（待用户复核）；经 4 轮审计，见 [v4.2 说明](../spec-readiness-v4.md#v42a-类平衡到-44修订号-452026-10-16-冻结) |
| Code Spec v5 | 全 B | |
| Commit Audit | 全 B | |
| 其他已冻结的旧版本 | 全 B | 不再标定 |
| Code Standards | 由场景 worker 登记 | v5 草稿修订 22 为 `in-key`（12:12） |

### Spec Readiness：留给 v4.2 的判定

审查确定的 v4.1 A 类有 2 个正例、4 个反例（下列为 v4.1 的判定）。v4.2 补 2 个正例，另把 REQUIREMENTS 反例 3、4 改 B 并补 2 个反例，最终 4:4，详见 v4.2 说明。

- 正例：
  - REQUIREMENTS 正例 2「加入了本 issue 不需要的 image-preview 清理」：范围是否必要，没有复现可以核对。
  - MODULES 正例 0「两个 Module 重复持有校验」：属于该不该合并。
- 反例：
  - REQUIREMENTS 反例 3「稳定边界正确区分 Engine、Reviewer 和 Input 作者的职责」：误报会推动重新划分职责。
  - REQUIREMENTS 反例 4「Requirements 不必规定解析器、辅助函数或存储细节」：误报会促成过度规定。
  - MODULES 反例 0「两个操作各自按同一契约校验，不是重复归属」：误报会推动错误合并。
  - MODULES 反例 1「Readiness Module 保留原有非报告职责，没有重叠」：误报会推动搬移职责。
- 归 B：SEAMS-ADAPTERS 反例 2、3。

其余用例归 B：缺少 Input、结果字段不全、理由缺替代方案、ADR 或 Module Design 豁免的适用性、接口契约缺项、数据流缺权威来源表等，都能对照规则或其他规范逐条核实。

### Code Spec v5

20 个问题都是违反规格的缺陷，用具体输入能复现。28 个普通 clean 被误报时，也能用输入或对照规格核实。clean「NEEDS_QUOTES 缺 g 但只用于 test()」曾列为待定，审查后归 B：误报促成的"加 g"改动能用测试证伪。

### Commit Audit

40 个问题和 78 个普通 clean（两个 Gate 各 39 个）逐条看过。每条都是"实现是否满足某项要求"，要求原文明确，能用具体输入或对照要求核实；误报促成的改动也能按要求原文排除。
