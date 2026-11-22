---
paths:
  - "config/arw-pin.json"
  - "tools/arw/**"
  - "tools/tuning/arw_*"
  - "tools/safety/**"
  - "benchmarks/reviewer-suite-v1/**"
---

# ARW Reviewer 测量规则

## 现行做法（2026-11-22 起）
- ARW 是 Reviewer 场景、答案键、跑分和计分代码的唯一来源（用户 2026-11-18）。本工程不复制、不改 ARW 源，按 `config/arw-pin.json`（ARW 提交加夹具树 SHA）引用：`tools/arw/pin.py` 把该提交 `git archive` 到 `.tmp/arw/<提交>/` 并核对 SHA，`tools/arw/run.py` 跑单个实例（ARW 自己的 `reviewer-capability run`，Strata 提供方），`tools/arw/measure.py` 跑一格并存小结果。
- 计分只经 ARW 入口（`reviewer-capability score`）；本工程不再补评分升级、格式罚或盲裁池代码。换 ARW 提交是改测量设计，先写进 pin 的 `note` 并跑新基线，旧分数不直接比较。
- 基础提示按 AGENTS.md 硬约束 3：启动提示由 Strata 服务端追加，开跑前核对 `/health` 的加载 SHA，绑定记进 `binding.json`；场景提示只能追加。
- 调参用的 `tools/tuning/arw_dimension`、`arw_blocks` 同样走 pin 版 ARW 的 run。
- 通用测量规则（预热连跑、分阶段判定、计时）见 [measurement.md](measurement.md)。

## v1 归档
4 个 Reviewer 的 v1 benchmark（冻结 ARW 760007c 快照与补丁、套件材料、答案键 judgment、格式罚基准、评分 r8 规则、v1/v2 运行器和计划、多模型 benchmark 的统计与导出代码、旧版本规则全文）已从 HEAD 删除，原样保存在 tag `reviewer-bench-v1`（a0fab1f，本工程无远端，靠 kaze-sync 备份）：

    git show reviewer-bench-v1:.claude/rules/reviewer-suite.md
    git show reviewer-bench-v1:benchmarks/multi-model-v1/plan.md
    git checkout reviewer-bench-v1 -- <路径>     # 取回某个文件到工作树

历史报告、`docs/work-history*.md` 和 README 里指向这些路径的链接按 tag 解析。`benchmarks/reviewer-suite-v1/` 里只留各场景版本的调参结果和 `*-plan.json`（测量结果，不是套件材料）。Codex 原生沙箱门（`safety_gate`）随冻结 ARW 一起归档；`tools/safety/` 里保留 Claude Code 沙箱门、Codex 压缩门和沙箱校验。
