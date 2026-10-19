# Sonnet 盲裁试点：设计与通过线（开跑前写定，2026-10-19）

目的：决定多模型 benchmark 的语义裁决模型（裁决量 = 模型数 × 4 场景 × 5 次）。在已由 Opus 盲裁、结果已定版的池上，让 Sonnet 用同一 brief 盲裁，比一致率。

## 池

**s1（主检验集）：Commit Audit v3 修订号 24**，来源 `reports/v0.1.45/commit-audit-v3/data/adjudication/`（p1–p4 原裁决，r1 第二裁决者复评与合成负例）。
- 难项层：p1–p4 中原判不是 `matched` 或 `kind = finding` 的全部真实候选（36 项）。
- r1 锚点中的 matched 关联（23 项；原判与第二名 Opus 一致）。
- 补充 matched 关联 22 项（种子 20261019，Opus 7、Q3 正式 8、Q3 加测 7，优先选未覆盖的期望组）。
- 合成负例 11 项，沿用 r1 的构造（6 错配、3 口径不匹配写法、2 事实错误发现），正确答案：关联 `not-matched`，发现 `unsupported`。
- 合计 92 项；参考答案 = Opus 原判（p1–p4），合成项 = 构造答案。
- brief：冻结件 `benchmarks/reviewer-suite-v1/commit-audit-v3-brief.md`（sha256 9c36e60b…），只替换 `<ADJ>`（隔离裁决目录）与 `<名>`（`s1`），与 p1–p4、r1 相同；输出格式中的 `adjudicator` 标签原样保留。
- 被审代码 view：`.tmp/commit-audit/v3formal/readj/view/` 原样复制进隔离目录。

**s2（次要集）：Code Standards v5.1 修订 25 的增量池** `.tmp/code-standards-v5/v51/pool.json` 全部 62 项（Opus worker 原判 matched 43、not-matched 19，其中锚点 12）。
- 偏离：该池当时的裁决 brief 没有存档，这里按冻结 ARW Adjudication 原文 + v5.1 变更说明「重复类题对端由盲裁判定」重建 brief；池只有期望句与 finding 正文（无 view，与原池相同）。结果只作次要证据，不作单独否决。

## 运行

- Claude Code 无头 `claude -p --model sonnet --effort medium`，参数同 Commit Audit v3 参考运行：`--safe-mode --restricted --strict-mcp-config --disable-slash-commands --setting-sources ""`，`--settings` 带 Bash 沙箱（denyRead /home /mnt /tmp /etc/claude-code，allowRead 隔离目录；写入只允许决定文件所在的隔离目录内新建文件，已有条目逐项禁写；网络空），`--tools Read,Write,Edit,Glob,Grep,Bash --permission-mode dontAsk`。工作目录 = 工程外隔离目录 `/home/pello/arw-opus/sadj-<池>-<强度>`。
- 每个运行结束执行 `estimate.sh --add-stream <stream.jsonl> <标签>`。
- s1、s2 两个运行独立，可并行。

## 通过线（三条同时满足才算 Sonnet medium 可用作 benchmark 裁决者）

1. s1 真实候选（81 项）与 Opus 原判逐字一致率 ≥ 95%，且难项层（36 项）一致率 ≥ 90%。
2. s1 合成负例 11/11 识别。
3. 把 s1 中 Sonnet 的决定代入正式 ×5（Q3 Af/B/Bf 与 Opus ×3）重新计分，候选集合变化按两种方向机械补齐（对 Q3 有利 / 不利），Q3/Opus 比值变化 |Δ| ≤ 0.02，且 < 0.8 的判定不变。

s2：一致率 ≥ 95% 视为支持；不达标时先看是否来自 brief 重建，再决定是否算作否定证据。

不满足：用同一池、同一 brief 再跑 Sonnet high（另行 `estimate.sh --can-start`）；high 仍不满足，则建议 benchmark 继续用 Opus 裁决。

## 统计

- 混淆矩阵：参考决定类别（matched / not-matched / problem-N / false-positive / supported / unsupported）× Sonnet 决定类别；`problem-N` 要求 N 相同。
- 一致率按层（matched 关联、难项、合成）与来源（Q3 / Opus）分列。
- 不一致项逐条列出：池 id、原 id、来源、原判、Sonnet 判、理由。
- 耗时（stream 的 duration_ms）、token 与 API 等价费用（result 事件）。
