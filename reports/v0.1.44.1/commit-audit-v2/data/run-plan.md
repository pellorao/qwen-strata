# Commit Audit v2 修订号 23 正式测量：运行计划（2026-10-17）

1. **目的**：在冻结的 Commit Audit v2（修订号 23，a1ed615）上得到 Q3 IQ3_XXS 的正式分数与 Opus medium 参考分，按相对口径 Q3/Opus 判定场景区分度（< 0.8）；Haiku-high ×5 登记格式罚 p基准并作第二参考。结论用于 Commit Audit 是否"一切正常"、能否定版或需加难（比值 ≥ 0.8 时先按"一切正常"判据评估，再决定是否加难，不当成场景缺陷）。
2. **主机与模型**：rtx3080ti；IQ3_XXS；Strata 0.1.44.1（已核对安装版本）；Q3 用 ARW/Codex 运行层（Codex 0.162.0，ARW 自己的 Strata provider 持有独占）；Opus 5.5 medium、Haiku 5.5 high 用 Claude Code 2.1.302 无头运行（`claude -p`，隔离方式沿用第 1 步盲答：safe-mode/restricted、Bash 沙箱、工作目录在工程外）。
3. **固定条件**：plan `benchmarks/reviewer-suite-v1/commit-audit-v2-iq3_xxs-2026-10-17-v0.1.44.1/plan.json`。effort high（budget 8192 / max 24576，服务日志核对）；窗口 206584、压缩 150000；启动提示源 5f9efc02…、压缩提示 3856cb62…（已核对源，prepare 预检核对已安装）；测量说明 `measurement-note-commit-audit.txt` sha 35e135fd…（不限时，三方同一份）；manifest-commit-audit-v2.json，补丁 13936171…，答案键 0f02cf43…（all-B）；评分 r8.3。
4. **候选或维度**：单条件（effort-high）；参考 Opus medium、Haiku high。
5. **规模**：Q3 有效 5 次（批 A 3、B 2；每批一次 prepare、一次冷加载，共 2 次加载）；不预定空闲加测。Opus medium ×3、Haiku high ×5（每次 1 个交接）。盲裁 1 名 Opus（high）裁决者，裁决 brief 原样带「裁决口径」并记 sha。
6. **预计耗时**：准备 10 分钟；Q3 每实例 7–25 分钟（v0.1.42 spec 维度实测 7.1–24.5 分钟），5 次约 1–1.5 小时加两次加载；Opus 每次约 5 分钟（R4 high 4.7 分钟）；Haiku 每次约 3–5 分钟；后处理与会话检查约 40 分钟；盲裁约 30 分钟；报告 30 分钟。
7. **前置条件**：冻结提交 a1ed615；租约 free、model null、`.tmp/gpu-priority/` 空（已核对）；安全验收沿用 rtx3080ti 现行证据（`reports/v0.1.40.1/current-safety-gate/report-directory-workaround/summary.md`：原生沙箱 8 类外部写入拒绝、15 个审批用例符合预期），v2 补丁只改夹具、答案键与 conformance 断言，不改运行层与权限生成器，与此前 Spec Readiness v4.2、Code Spec v5 的做法相同；Anthropic 运行每项先过 `estimate.sh --can-start`。
8. **停止条件**：Q3 5 次有效即完成；失败或无效实例补跑累计至多 2 次；引擎输出 < 60 tok/s 记为意外事件；到达 ARW 原版 10/5 次早退暂停点停下报告。Anthropic 运行不建议时不空等，Q3 完成后停下报告。偏离记录在 progress.md 并写进报告。
