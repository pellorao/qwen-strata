# Code Spec 阅读量维度（rv）运行计划

依据：reviewer 规则「阅读量维度」（用户 2026-10-14）与 `docs/plan.md`「待你决定」第 1–3 项的决定（2026-10-14，独立 agent 意见，待用户复核）。本文件在构造前写定，冻结时补 `code-spec-rv-iq3_xxs-2026-10-14/plan.json`（冻结版的条件、补丁与 SHA 以 plan.json 为准）。

## 1. 目的

在推理难度不变的前提下，只把阅读量从 v4.7 的 17.9K 提高到约 150K，回答：Opus 在按同一公式给出的时限内能否仍找到大部分缺陷（判据），以及 Q3 在大阅读量下的得分（报告，不作判据）。结论用于决定代码题的阅读量档位和压缩阈值方向；只适用于 Strata v0.1.43.1、rtx3080ti、IQ3_XXS。

## 2. 主机与模型

- rtx3080ti，IQ3_XXS，Strata 0.1.43.1，Codex 0.162.0，effort high。
- 参考：Opus-high（Claude agent，与 Q3 相同的渲染交接盲答），不占 GPU。

## 3. 固定条件

- 与 v4.7 冻结版相同：安装默认值（IQ3_XXS 首档 206584/150000，high 思考 8192、总输出 24576）；启动提示 `config/prompts/startup-instructions.txt`（源 SHA 5f9efc02…，去掉防循环段）与 `config/prompts/compact-prompt.txt`（3856cb62…）接入，开跑前核对已安装 SHA；native CLI SHA 50ed828f…；按 ARW 原版罚分。
- 缺陷组不变：v4.7 的 20 个问题用例与 31 个 clean 用例（含 `noOtherSupportedFinding`）原样沿用，`governing-spec.md` 原有各行和 `src/reservations/` 字节不变，答案键行号仍有效。
- 测量说明改用模板 `benchmarks/reviewer-suite-v1/measurement-note-time-limit.txt`（SHA 4c7558c8…）：原测量说明全文 + 时限、按截至时刻计分、每确认一个问题就追加写入结果文件。每批由 `arw_dimension prepare --time-limit-seconds T` 渲染到批目录，selection 同时记录模板 SHA、渲染 SHA 和 `review_time_limit_seconds`。
- 时限：T 秒 = B ×（1/P + k/G）/ β。B 为 `governing-spec.md` 与候选代码的总字节；P、G、β 由每批开跑前的速度探针（`tools.metrics.speed_probe`，一次冷加载、两个请求，引擎日志取值）在本批材料上测得。k 只在首批（150K）按"Q3 时限 = B/10K 分钟"反推一次：k = G ×（0.006β − 1/P），之后固定并记录；两个模型用同一个 k。
- 时限执行：Q3 用 ARW 原版提醒与中断（`ReviewDeadline`，截止前 5 分钟提醒，时限不足 10 分钟时提前一半）；被中断的实例按截至时刻已写出的结果计分。
- Opus：同一公式，P 取无穷（1/P = 0），G、β 用 Opus 探针 agent 的用量差估计（读材料与不读材料两次求 β；长输出与短输出两次求 G），是近似值，报告注明；到 T − 5 分钟发提醒，到 T 停止该 agent，按结果文件计分。这与 ARW 原版机制不同，报告注明。Opus 窗口更大、压缩更少，接受这一差异。

## 4. 维度与取值

- 维度：阅读量 B。干草堆是同一预订系统里新增的 12 个正确子系统（每个约 11K：代码 8.5–10K + spec 一节 1.6–2.4K），互不导入，只可从 `src/reservations/calendar.mjs` 导入 `MINUTE`、`minutes`、`overlaps`；spec 新节追加在原文之后，只写直接规则，不覆盖、不例外原有条款；不用开源代码。
- 档位按固定顺序取子系统前缀组装：members、badges、billing、utilization、waitlist、messaging、visitors、audit、payments、exports、maintenance、schedules。12 个全取约 150K，10 个约 125K；二分时取最接近目标的前缀，报告实际 B。
- 防搜索：spec 关键词（hold、confirmed、canceled、expiresAt、partySize、buildingId、fee、history、now() 等）在新代码里按各子系统自身含义多处出现。

## 5. 规模

- 每档：速度探针 1 次（1 次加载）+ Q3 ×3（每次全新 ARW 准备、冷加载）+ Opus ×1；Opus 落在 16–18/20 时补到 ×3 再定方向。
- 空闲加测：GPU 空闲时 150K 档 Q3 加测到 5 次（目标事先定为 5，不按中途结果决定），报告同时给前 3 次和全部结果；加测与评估并行，不拖慢判定。
- 构造期：Q3 本地试跑 ×1（初筛）、Opus 全量审计 ×1。

## 6. 预计耗时

- 构造：2 个 Opus 子 agent 并行写 6 个子系统，约 1–2 小时；组装、可执行测试、conformance 约 20 分钟。
- 初筛与审计：Q3 试跑约 20 分钟（15 分钟时限 + 加载）；逐条核实新代码发现约 20 分钟；Opus 审计约 30 分钟。
- 正式：每档 Q3 ×3 约 55 分钟（15 分钟时限 ×3 + 冷加载与预检，依据 v4.7 Q3 5.1–7.7 分钟/17.9K 外推为必然撞时限）；Opus ×1 约 25 分钟，与 Q3 并行。
- 评估：机械计分、增量盲裁（12 个锚点）、会话检查约 40 分钟。二分每多一档再加约 1.5 小时。

## 7. 前置条件

- `ReviewDeadline` 接受 selection 时限（73625b1）、速度探针（33aee5e）、`arw_dimension` 的模板渲染与 `--time-limit-seconds`（本次提交），单元测试全过。
- 干草堆：每条新 spec 条款至少一个可执行测试且全过；v4.7 `verify.sh` 仍全过（20 个缺陷各自只破坏自己的检查）；conformance 通过；新代码导入白名单机械检查通过。
- 初筛与审计：新代码上的每条发现逐条核实；真缺陷修正后重跑测试。冻结前写定：冻结后核实为真缺陷的新代码发现，修正代码（下一版）并在本版计分中按中性处理（不计入 `noOtherSupportedFinding` 失败，也不计分）。
- 冻结：独立 agent（不低于 Main）给意见后冻结，记入 `docs/plan.md`；冻结版用独立 manifest（`code-spec-v4.patch` 换为 rv 补丁），v4.7 现行 manifest 不变。
- 每实例：经前端领租约、冷加载、结束停模型并归还；有其他持有者时等待，不抢占。

## 8. 停止条件

- 150K 档 Opus ≥17/20 且 clean 误报没有明显增加（相对 v4.7 Opus ×3 无误报）：定在 150K，完成加测与报告后停。
- 16–18/20：Opus 补到 ×3，按均值再判。
- 不达标：先看 Opus 是否被时限中断。被中断：按规则调大 k（两模型同一 k，记录新旧值），重算 T 后在同档重跑。未被中断：降到 125K，之后对半二分；区间小于 12.5K 时停。
- 偏离计划记入进度文件并在汇报中说明。
