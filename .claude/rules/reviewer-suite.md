---
paths:
  - "benchmarks/reviewer-suite-v1/**"
  - "tools/reviewer/**"
  - "tools/safety/**"
---

# ARW Reviewer 测量规则

## 合同
- 直接使用冻结 ARW 的原场景、完整规则、准备 / 生成 / 评分入口和 Reviewer 运行层。不裁剪用例。确实需要改变合同时，先列出差异并取得同意。
- 评分按场景分两种口径，定义见[测量规则 · 评分口径](measurement.md#评分口径)（用户 2026-10-12）：调参取 ARW 扣罚前分，格式与报告诊断只记录；能力验证和 benchmark 完全按 ARW 原版罚分。两者都先由 `tools.reviewer.repair_reviewer_report` 在绑定原实例的独立副本中修复可机械修复的错误（数组外的单个整数 `lines`；markdown 首个条目前的前言；能唯一对应文件的简写证据引用；证据定位含义以 ARW 定义为准，顶层 `[a,b]` 是两行，不改写为区间），让报告能被评分；benchmark 另记录做过修复并照 ARW 规则 ×0.9。原报告不改，修复处数和类型标在分数旁。
- 所有场景的能力判定都用相对口径：Q3 分数与同场景同版本的 Opus 参考分之比（Q3 / Opus），不设绝对分数通过线（如 0.75）；报告给出两者分数、比值和双方 0 命中的用例（用户 2026-10-13）。
- 权限沿用原生设置：`:read-only` 加显式写路径，审批走 on-request / auto_review；网络、搜索、MCP 保持原生。不额外收紧，不启用可选的严格隔离。
- 正式能力测量之前，先确认所需的安全证据（原生沙箱行为、auto_review 审批质量）。见 `docs/plan.md`。

## 执行
- 时限按累计工作时间计：初审 55 分钟提醒、60 分钟中断；同线程后续沟通 10 分钟提醒、15 分钟中断。提醒和中断使用原版 ARW 接口。
- 能力验证和 benchmark 中，早停接续使用 ARW 原版运行层的接续机制，本工程驱动不另发继续指示（用户 2026-10-11：最大限度还原 ARW，便于与 ARW 自己的结果直接对比）。到达原版 10 / 5 次早退暂停点时，停下交给用户决定。
- 能力验证和 benchmark 由 ARW 自己的 Strata provider 持有独占并启动模型（打了本工程接口补丁的 ARW，`selection.model_owner = "arw"`），引擎参数用安装目录的每机每量化默认值。每批开跑前 `arw_measure` 经租约停掉常驻模型，批从冷加载开始；实例之间不停模型，只允许 Strata 精确前缀缓存的复用，不复用上一个实例的上下文；token 按派发时刻切分的引擎日志段计算（用户 2026-10-11）。
- 测量交接末尾追加冻结的测量说明（不发送中途消息、不需要运行标识、禁止查询环境变量和平台身份），记录 SHA；只追加，不改原版交接和 Role。
- Reviewer 的命令环境用 Codex 原生 `shell_environment_policy.exclude` 去掉 `STRATA_API_KEY`（用户 2026-10-12；provider key 由 Codex 自己经 `env_key` 读取，命令不需要）。Codex 0.162.0 默认会把它传给命令，无模型探测已确认排除生效、`set` 的变量照常可见。
- Spec Readiness 的 runtime-migration 与 artifact-promotion 各用全新根线程，互不可见，与 ARW 准备规则一致（每个 instanceId 一个独立线程和一次审核）；两份报告分别绑定，按原版融合评分。原"合并实例"（同一线程先 RM 后 AP）已停用（用户 2026-10-13）：它偏离 ARW，且有 AP 照搬 RM finding、引用 RM 专有约定的污染证据（[审查报告](../../reports/v0.1.42/spec-rule-audit/summary.md)）；此前用合并实例得到的 Spec Readiness 结果只在合并实例之间可比。
- Spec Readiness 使用 v2 场景（修订号 41，用户 2026-10-13 决定 ARW 采用 v2）：夹具与答案键由 `arw-patches/spec-readiness-v2.patch` 提供，冻结源 manifest 登记；与原版的差异、原因和审查依据见 [v2 变更说明](../../benchmarks/reviewer-suite-v1/spec-readiness-v2.md)。v2 的分数只与 v2 比较。v2 先用于能力验证和 benchmark；是否用于调参，待 IQ3_XXS ×5 的组内标准差明显低于 0.1 再定。
- 冻结源现已叠加 v3（修订号 42，`arw-patches/spec-readiness-v3.patch`，自主模式按 main 计划 587fe9b 登记，待用户确认是否采用）：消除 v2 审计后发现的歧义，见 [v3 变更说明](../../benchmarks/reviewer-suite-v1/spec-readiness-v3.md)。v3 的分数只与 v3 比较；v2 结果仍只与 v2 比较。
- 冻结源现已叠加 v4（修订号 43，`arw-patches/spec-readiness-v4.patch`，用户 2026-10-13 决定做 v4）：修 v3 两个双 0 用例的非智力成因（AP vr:45 写明 extra field 的 reason、prec:59 写明失败形状是 Seam 返回值），并入 v3.1 键，见 [v4 变更说明](../../benchmarks/reviewer-suite-v1/spec-readiness-v4.md)。v4 的分数只与 v4 比较。
- Code Spec 使用 v2 场景（code-spec-reviewer 修订号 12，`arw-patches/code-spec-v2.patch`，自主模式登记，待用户确认是否采用）：访问窗口结束边界改为半开、取消状态要求写明、答案键补 4 个直接证据关联点，见 [Code Spec v2 变更说明](../../benchmarks/reviewer-suite-v1/code-spec-v2.md)。v2 的分数只与 v2 比较，不与 F6 等原版结果直接比较。

## 会话检查
- 按冻结 ARW 的 `docs/agents/reviewer-capability-session-inspection.md` 检查每个原生会话：准备项、线程身份、启动上下文、交接后的全部消息、每次工具调用及结果、读写范围、报告和终态，并排查隐藏答案、其他实例等禁止来源。
- 用 `tools.reviewer.inspect_session` 提取，Main 逐条审阅动作（用户 2026-10-11）：
  - 必读 `actions.md` 全文和 `flagged.md` 全文。后者含被标记调用（目标出根目录、`..` 越界、未赋值变量、环境与身份查询、网络、会话或凭据材料、拒绝报错、无结果）的完整命令和结果，以及交接后的非 assistant 消息。
  - 推理、元数据、压缩摘要和未标记调用的结果不作例行阅读。依据：Reviewer 只能经工具调用接触来源，调用目标限于场景根时，结果也只来自场景根。ARW 文档不要求检查推理。诊断早停、卡住等问题时按事件号调取原文。
  - 启动上下文按 `summary.json` 的归一化 SHA 在同批实例间比对，不一致时读原文。
  - 程序只做提取和标记，结论由 Main 根据逐条动作作出；标记项逐条写明判定。
- 环境变量与平台身份查询按结果判定（用户 2026-10-12），调参与 benchmark 相同：
  - 输出或其后续动作接触到隐藏答案、评分材料或其他实例结果，可能抬高得分：该实例无效，按「失败与重跑」处理。
  - 否则（只看到变量名、路径、运行标识、端点等，且后续动作未借此访问禁止来源）：样本保留，分数照常计入均值，在分数旁标"诊断分（环境查询 1 次）"并记录命令与输出范围；不乘 0.9，也不因此判批次失败。
  - 判定写明依据：命令、输出内容范围（是否含值）、之后的工具调用是否用到这些信息。
- 检查完成前不清理原始记录。
