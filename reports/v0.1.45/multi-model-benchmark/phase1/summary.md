# 多模型 benchmark v1 第一阶段报告

第一阶段报告，2026-10-22。第一阶段（预登记实例）是一份完整的 benchmark 结果；第二阶段（Strata 加测进主统计）另出更新版。所有表格由同目录 `summary.json`（sha256 `47500e75334396c4d286ec7d8b86561db2350243885c64925414985c1a99cd6c`）生成，敏感性一节的数取自计分时的变体汇总（明细删除后只保留本文中的数）；文字里的数都取自这些表。计分口径：CA 第 2 关行号整体错位已按用户 10-22 的决定改挂（N1，见下文），第一阶段 557 个实例全部用现行 master（e46006d）重算。计划与口径见 [plan.md](../../../../benchmarks/multi-model-v1/plan.md)，裁决先例见 [rulings.md](../../../../benchmarks/reviewer-suite-v1/rulings.md)。

## 结论与适用范围

**结论**（预登记的 100 个比较，每场景 25 个、各自 Holm 校正，双侧 α = 0.05）：低于 21 个、高于 10 个、未分出 69 个。按对手归并（四个场景 × 三档，DeepSeek 只有 low、high 两档参与同强度比较）：

- **Codex 上，Strata 对 gpt-6.1-sol 同档**（12 个）：低于 8 个（CS 三档、CStd high、CA low、SR 三档），未分出 4 个（CStd low、medium，CA medium、high）。
- **Codex 上，Strata 对 gpt-6-luna 同档**（12 个）：高于 5 个（CS low、CStd low、CStd high、CA low、SR low），其余 7 个未分出。
- **Codex 上，Strata 对 DeepSeek 同档**（8 个）：全部未分出。
- **Claude Code 上，Strata 对 Opus 同档**（12 个）：低于 6 个（CS medium、high，CA medium，SR 三档），未分出 6 个。
- **Claude Code 上，Strata 对 Sonnet 同档**（12 个）：低于 3 个（CA medium，SR medium、high），未分出 9 个。
- **Claude Code 上，Strata 对 Haiku 同档**（12 个）：高于 3 个（CStd 三档），低于 4 个（CA medium，SR 三档），未分出 5 个。
- **Claude Code 上，Strata 对 DeepSeek 同档**（8 个）：全部未分出。
- **harness（同一模型 Codex 对 Claude Code）**：Strata 12 个中高于 2 个（SR medium、high：Codex 上的分数高于 Claude Code 上的），其余未分出；DeepSeek 12 个（low / high / max）全部未分出。

**意义**：在这四个 reviewer 场景上，本地 Strata IQ3_XXS 没有在任何场景、任何档上分出高于 gpt-6.1-sol 或 Opus；对其他模型分出高于的只有 gpt-6-luna（5 处）和 Haiku 的 CStd（3 处）。和 DeepSeek-Flash 的 16 个同强度比较都没分出高下。SR 上，Claude Code 侧 Strata 对三个 Anthropic 模型的 9 个比较中 8 个低于。

**适用范围**：

- 只是第一阶段：Strata 每格只用按开始时刻的前 5 个有效实例，付费模型和 DeepSeek 用全部有效实例（DeepSeek 合并格见 plan §14.4）。Strata 加测到 10 个的第二阶段另出更新版，结论可能变。
- n = 5 对 5 时能分辨的差约 0.3（plan §5 审查估算）。"未分出"不等于"相同"：69 个未分出的比较中有 34 个 |d| 在 0.1–0.3 之间。
- 单机单量化：rtx3080ti、IQ3_XXS，参数来自 v0.1.42 调参。
- 混杂（plan §4 全部 14 条成立）：场景按 Opus 标定、Opus 也是唯一盲裁者，Opus 的位置可能偏高；厂商与 harness 部分绑定；各家"强度"含义不同；基础提示只给 Strata；搜索全部关闭；guardian、窗口与压缩、时限提醒送达方式各臂不同。
- 分数尺度是评分 r8.4：不在 0 处截断，负分按答案键全部反例的 k 之和归一，正负两侧单位不同（plan §14.1 r8.4 条）。负分只出现在 CA 的 gpt-6-luna（9 个实例，见敏感性一节）。
- 会话检查（D9）已完成：557 个实例没有因会话检查作废的，12 个记诊断分（环境查询），计分不变。
- 不给比值、综合分和排名（D7）。

## 每场景结果

每个场景两张表：配置表（主统计、一致性行、DeepSeek 补充行与描述性合并行；补充行和敏感性行不进比较）和预登记比较表。文字结论只用"高于 / 低于 / 未分出"；"d"为 Strata（harness 组为 Codex 侧）减对照。耗时为分钟、一位小数，"占时限"为实际用时 ÷ T（SR、CA 不设 T，写"无时限"）。费用：OpenAI 只报 token；DeepSeek 括号内为人民币，"≥"表示有提醒中断丢弃的请求未计入，是下界；Strata 按测量规则的等效费用公式；"周额度"是 Anthropic 周额度折算。工具调用：Codex 从 rollout 的根线程计（不含 guardian），Claude Code 从 stream 的主会话 tool_use 计（按块 id 去重）；Codex 的 code mode 一次 exec 记 1 次，所以 gpt-6.1-sol / gpt-6-luna 的工具调用数和别的臂不完全同义。四项速度：引擎输入、引擎输出是模型直接速度，任务平均输入、输出是用户感知速度（未缓存输入、输出 ÷ 工作秒数）。Strata 的模型直接速度取引擎日志（read ÷ 输入处理秒数、generated ÷ 解码秒数）；API 模型分不出输入处理时间，引擎输入写"未知"，引擎输出按 API 请求时间算（Claude Code 取 stream 的 `duration_api_ms`，Codex 取 relay 每个请求从到达到流结束的时长），含首 token 延迟和输入处理，是下限，标"≥"。配置表的速度是格内各实例速度的算术平均。写"未知"的是缺数据，不是零。

### Code Spec v5（CS）

#### 配置

| 配置 | 行 | 有效 | n | 无效 | 均值 ± SD | SE | 95% 区间 | 负分数 | 最小 | 中位数 | r8.3 均值 | rawScore | f | 修复 | 耗时（分钟） | 占时限 | 未缓存 | 缓存 | 输出 | token 来源 | 工具调用 | 引擎输入 tok/s | 引擎输出 tok/s | 任务平均输入 tok/s | 任务平均输出 tok/s | 费用均值（美元；DeepSeek 括号内人民币） | 周额度 | 模型 ID | service tier |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 Codex gpt-6.1-sol low | 主统计 | 5 | 5 | 1 | 0.858 ± 0.011 | 0.005 | 0.844 – 0.871 | 0 | 0.848 | 0.852 | 0.858 | 0.858 | 0.000 | 0 | 2.3 | 0.09 | 114,355 | 1,063,859 | 6,505 | API usage (relay) | 14.4 | 未知 | ≥48.6 | 862.8 | 48.3 | 只报 token |  | gpt-6.1-sol | default |
| 2 Codex gpt-6.1-sol medium | 主统计 | 5 | 5 | 0 | 0.832 ± 0.007 | 0.003 | 0.824 – 0.840 | 0 | 0.826 | 0.832 | 0.832 | 0.832 | 0.000 | 0 | 2.8 | 0.12 | 112,228 | 1,056,410 | 8,011 | API usage (relay) | 14.8 | 未知 | ≥48.1 | 679.2 | 47.8 | 只报 token |  | gpt-6.1-sol | default |
| 3 Codex gpt-6.1-sol high | 主统计 | 5 | 5 | 0 | 0.826 ± 0.022 | 0.010 | 0.798 – 0.853 | 0 | 0.802 | 0.825 | 0.826 | 0.826 | 0.000 | 0 | 4.8 | 0.20 | 118,153 | 1,301,197 | 14,232 | API usage (relay) | 16.2 | 未知 | ≥49.6 | 412.8 | 49.4 | 只报 token |  | gpt-6.1-sol | default |
| 4 Codex gpt-6-luna low | 主统计 | 5 | 5 | 0 | 0.045 ± 0.026 | 0.012 | 0.012 – 0.078 | 0 | 0.021 | 0.037 | 0.045 | 0.045 | 0.000 | 0 | 0.8 | 0.08 | 80,284 | 924,774 | 3,473 | API usage (relay) | 13.8 | 未知 | ≥70.9 | 1631.0 | 68.2 | 只报 token |  | gpt-6-luna | default |
| 5 Codex gpt-6-luna medium | 主统计 | 5 | 5 | 0 | 0.238 ± 0.177 | 0.079 | 0.019 – 0.457 | 0 | 0.012 | 0.251 | 0.238 | 0.238 | 0.000 | 0 | 1.2 | 0.12 | 87,073 | 995,302 | 5,573 | API usage (relay) | 15.8 | 未知 | ≥77.5 | 1344.1 | 76.1 | 只报 token |  | gpt-6-luna | default |
| 6 Codex gpt-6-luna high | 主统计 | 5 | 5 | 0 | 0.517 ± 0.122 | 0.054 | 0.366 – 0.668 | 0 | 0.361 | 0.512 | 0.517 | 0.517 | 0.000 | 0 | 1.8 | 0.18 | 107,862 | 1,057,485 | 10,232 | API usage (relay) | 15.8 | 未知 | ≥94.8 | 1146.9 | 94.3 | 只报 token |  | gpt-6-luna | default |
| 7 Codex deepseek-flash low | 主统计 | 5 | 5 | 0 | 0.531 ± 0.067 | 0.030 | 0.448 – 0.614 | 0 | 0.468 | 0.519 | 0.531 | 0.531 | 0.000 | 0 | 2.7 | 0.50 | 86,495 | 1,033,830 | 26,382 | API usage (relay) | 27.4 | 未知 | ≥169.4 | 535.7 | 162.2 | ≥0.032（¥0.213） |  | deepseek-flash | default、not-returned |
| 8 Codex deepseek-flash high | 主统计 | 5 | 5 | 0 | 0.531 ± 0.107 | 0.048 | 0.399 – 0.664 | 0 | 0.431 | 0.530 | 0.531 | 0.531 | 0.000 | 0 | 3.3 | 0.48 | 86,181 | 1,308,416 | 32,929 | API usage (relay) | 35.2 | 未知 | ≥173.8 | 450.4 | 169.4 | ≥0.037（¥0.244） |  | deepseek-flash | default、not-returned |
| 8 Codex deepseek-flash high | high requested as medium, T=344 | 5 | 5 | 0 | 0.522 ± 0.162 | 0.073 | 0.321 – 0.723 | 0 | 0.245 | 0.559 | 0.522 | 0.527 | 0.008 | 1 | 2.3 | 0.40 | 79,784 | 1,115,725 | 22,965 | API usage (relay) | 27.0 | 未知 | ≥168.5 | 668.1 | 165.0 | ≥0.029（¥0.194） |  | deepseek-flash | default、not-returned |
| 8 Codex deepseek-flash high | 敏感性：high+medium 合并（描述性，high requested as medium, T=344） | 10 | 10 | 0 | 0.527 ± 0.130 | 0.041 | 0.434 – 0.619 | 0 | 0.245 | 0.533 | 0.527 | 0.529 | 0.004 | 1 | 2.8 | 0.44 | 82,983 | 1,212,070 | 27,947 | API usage (relay) | 31.1 | 未知 | ≥171.1 | 559.2 | 167.2 | ≥0.033（¥0.219） |  | deepseek-flash | default、not-returned |
| 9 Codex deepseek-flash max | 主统计 | 5 | 5 | 0 | 0.601 ± 0.033 | 0.015 | 0.560 – 0.642 | 0 | 0.557 | 0.608 | 0.601 | 0.601 | 0.000 | 0 | 3.4 | 0.50 | 92,959 | 1,550,259 | 37,177 | API usage (relay) | 39.0 | 未知 | ≥195.6 | 464.0 | 182.7 | ≥0.041（¥0.273） |  | deepseek-flash | default、not-returned |
| 10 Codex Strata IQ3_XXS low | 主统计 | 10 | 5 | 0 | 0.447 ± 0.063 | 0.028 | 0.370 – 0.525 | 0 | 0.361 | 0.448 | 0.447 | 0.447 | 0.000 | 0 | 8.6 | 0.56 | 95,277 | 2,217,213 | 36,312 | engine log | 27.6 | 1680.2 | 86.5 | 184.2 | 70.3 | 0.067 |  | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | 主统计 | 10 | 5 | 0 | 0.492 ± 0.034 | 0.015 | 0.450 – 0.535 | 0 | 0.461 | 0.478 | 0.492 | 0.499 | 0.013 | 3 | 8.4 | 0.55 | 84,249 | 1,351,208 | 36,154 | engine log | 24.0 | 1834.5 | 86.6 | 169.1 | 71.8 | 0.051 |  | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | 主统计 | 10 | 5 | 0 | 0.492 ± 0.028 | 0.013 | 0.458 – 0.527 | 0 | 0.466 | 0.485 | 0.492 | 0.492 | 0.000 | 0 | 9.5 | 0.62 | 81,979 | 1,727,966 | 41,534 | engine log | 33.4 | 1652.2 | 85.9 | 144.6 | 72.5 | 0.059 |  | 未知 | 未知 |
| 13 Claude Code opus low | 主统计 | 5 | 5 | 0 | 0.616 ± 0.102 | 0.045 | 0.490 – 0.742 | 0 | 0.517 | 0.598 | 0.616 | 0.629 | 0.024 | 0 | 3.2 | 0.16 | 97,022 | 715,887 | 7,141 | Claude Code stream result usage | 12.4 | 未知 | ≥73.8 | 623.7 | 46.0 | 1.062 | 0.46% | claude-opus-5-5 | standard |
| 14 Claude Code opus medium | 主统计 | 5 | 5 | 0 | 0.699 ± 0.058 | 0.026 | 0.626 – 0.771 | 0 | 0.640 | 0.696 | 0.699 | 0.699 | 0.000 | 0 | 3.3 | 0.18 | 103,512 | 938,025 | 10,090 | Claude Code stream result usage | 15.2 | 未知 | ≥88.6 | 565.0 | 55.2 | 1.217 | 0.52% | claude-opus-5-5 | standard |
| 15 Claude Code opus high | 主统计 | 5 | 5 | 0 | 0.760 ± 0.056 | 0.025 | 0.690 – 0.830 | 0 | 0.702 | 0.734 | 0.760 | 0.764 | 0.006 | 1 | 4.6 | 0.23 | 106,450 | 1,015,201 | 13,054 | Claude Code stream result usage | 16.0 | 未知 | ≥87.4 | 433.4 | 53.7 | 1.316 | 0.57% | claude-opus-5-5 | standard |
| 16 Claude Code sonnet low | 主统计 | 5 | 5 | 0 | 0.458 ± 0.077 | 0.034 | 0.363 – 0.554 | 0 | 0.363 | 0.453 | 0.458 | 0.495 | 0.074 | 0 | 2.9 | 0.18 | 92,467 | 558,247 | 9,793 | Claude Code stream result usage | 10.4 | 未知 | ≥98.4 | 554.1 | 59.1 | 0.524 | 0.23% | claude-sonnet-5-5 | standard |
| 17 Claude Code sonnet medium | 主统计 | 5 | 5 | 0 | 0.575 ± 0.094 | 0.042 | 0.459 – 0.691 | 0 | 0.483 | 0.544 | 0.575 | 0.594 | 0.032 | 0 | 3.6 | 0.23 | 96,807 | 588,158 | 12,853 | Claude Code stream result usage | 11.4 | 未知 | ≥105.7 | 522.1 | 68.7 | 0.575 | 0.25% | claude-sonnet-5-5 | standard |
| 18 Claude Code sonnet high | 主统计 | 5 | 5 | 0 | 0.585 ± 0.086 | 0.038 | 0.479 – 0.691 | 0 | 0.521 | 0.546 | 0.585 | 0.615 | 0.051 | 1 | 4.4 | 0.27 | 107,023 | 716,451 | 20,243 | Claude Code stream result usage | 13.2 | 未知 | ≥118.9 | 426.7 | 81.1 | 0.702 | 0.30% | claude-sonnet-5-5 | standard |
| 19 Claude Code haiku low | 主统计 | 5 | 5 | 3 | 0.266 ± 0.132 | 0.059 | 0.102 – 0.430 | 0 | 0.129 | 0.246 | 0.266 | 0.284 | 0.011 | 0 | 4.8 | 0.52 | 111,221 | 4,067,961 | 19,811 | Claude Code stream result usage、Claude Code stream result usage (lower bound: a segment without result) | 21.4 | 未知 | 未知 | ≥534.1 | ≥79.9 | 未知 |  | claude-haiku-5-5 | standard |
| 20 Claude Code haiku medium | 主统计 | 5 | 5 | 5 | 0.413 ± 0.157 | 0.070 | 0.218 – 0.609 | 0 | 0.210 | 0.480 | 0.413 | 0.422 | 0.014 | 1 | 2.2 | 0.26 | 103,158 | 749,440 | 24,535 | Claude Code stream result usage | 13.4 | 未知 | ≥188.6 | 799.4 | 177.8 | 0.085 | 0.04% | claude-haiku-5-5 | standard |
| 21 Claude Code haiku high | 主统计 | 5 | 5 | 2 | 0.577 ± 0.092 | 0.041 | 0.462 – 0.691 | 0 | 0.445 | 0.579 | 0.577 | 0.577 | 0.000 | 0 | 3.6 | 0.42 | 138,517 | 1,024,578 | 36,002 | Claude Code stream result usage | 19.2 | 未知 | ≥208.1 | 647.1 | 168.7 | 0.165 | 0.07% | claude-haiku-5-5 | standard |
| 22 Claude Code deepseek-flash low | 主统计 | 5 | 5 | 0 | 0.470 ± 0.096 | 0.043 | 0.351 – 0.590 | 0 | 0.366 | 0.427 | 0.470 | 0.470 | 0.000 | 0 | 3.3 | 0.48 | 74,102 | 540,314 | 17,573 | Claude Code stream result usage | 15.2 | 未知 | ≥162.3 | 472.8 | 99.6 | 0.023（¥0.155） |  | deepseek-flash | standard |
| 23 Claude Code deepseek-flash high | 主统计 | 5 | 5 | 0 | 0.435 ± 0.085 | 0.038 | 0.329 – 0.541 | 0 | 0.336 | 0.420 | 0.435 | 0.435 | 0.000 | 0 | 3.5 | 0.61 | 78,022 | 545,408 | 18,801 | Claude Code stream result usage | 16.0 | 未知 | ≥169.7 | 427.4 | 100.4 | 0.025（¥0.164） |  | deepseek-flash | standard |
| 23 Claude Code deepseek-flash high | high requested as medium, T=391 | 5 | 5 | 0 | 0.509 ± 0.105 | 0.047 | 0.379 – 0.639 | 0 | 0.392 | 0.522 | 0.509 | 0.515 | 0.016 | 0 | 4.4 | 0.67 | 72,740 | 631,680 | 32,382 | Claude Code stream result usage | 15.8 | 未知 | ≥185.1 | 279.8 | 124.0 | 0.032（¥0.215） |  | deepseek-flash | standard |
| 23 Claude Code deepseek-flash high | 敏感性：high+medium 合并（描述性，high requested as medium, T=391） | 10 | 10 | 0 | 0.472 ± 0.098 | 0.031 | 0.402 – 0.542 | 0 | 0.336 | 0.449 | 0.472 | 0.475 | 0.008 | 0 | 3.9 | 0.64 | 75,381 | 588,544 | 25,592 | Claude Code stream result usage | 15.9 | 未知 | ≥177.4 | 353.6 | 112.2 | 0.028（¥0.190） |  | deepseek-flash | standard |
| 24 Claude Code deepseek-flash max | 主统计 | 6 | 5 | 0 | 0.311 ± 0.192 | 0.086 | 0.073 – 0.549 | 0 | 0.000 | 0.338 | 0.311 | 0.311 | 0.000 | 0 | 4.4 | 0.70 | 未知 | 未知 | 未知 | Claude Code stream result usage | 17.0 | 未知 | 未知 | 未知 | 未知 | 0.033（¥0.221） |  | deepseek-flash | standard |
| 25 Claude Code Strata IQ3_XXS low | 主统计 | 10 | 5 | 1 | 0.418 ± 0.091 | 0.041 | 0.304 – 0.531 | 0 | 0.304 | 0.433 | 0.418 | 0.420 | 0.007 | 1 | 7.9 | 0.55 | 87,776 | 2,495,671 | 35,440 | engine log | 27.6 | 1636.4 | 87.8 | 190.8 | 74.9 | 0.070 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 26 Claude Code Strata IQ3_XXS medium | 主统计 | 10 | 5 | 0 | 0.480 ± 0.064 | 0.029 | 0.401 – 0.560 | 0 | 0.388 | 0.479 | 0.480 | 0.489 | 0.020 | 24 | 8.8 | 0.59 | 88,314 | 1,826,317 | 39,751 | engine log | 56.0 | 1693.8 | 85.3 | 170.4 | 75.1 | 0.061 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 27 Claude Code Strata IQ3_XXS high | 主统计 | 10 | 5 | 0 | 0.460 ± 0.048 | 0.022 | 0.400 – 0.520 | 0 | 0.392 | 0.463 | 0.460 | 0.463 | 0.006 | 0 | 10.1 | 0.67 | 77,847 | 1,452,332 | 46,232 | engine log | 25.6 | 1760.2 | 84.1 | 129.2 | 76.1 | 0.057 |  | qwen3.8-flash-next-iq3_xxs | not-returned |

#### 预登记比较（25 个，Holm）

| 组 | Strata / Codex 侧 | 对照 / Claude Code 侧 | n | d | SE | df | p | Holm p | 结论 | r8.3 Holm p | r8.3 结论 | 结论改变 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Codex 同强度 | 10 Codex Strata IQ3_XXS low | 1 Codex gpt-6.1-sol low | 5 / 5 | -0.411 | 0.028 | 4.2 | 9.2e-05 | 0.0019 | 低于 | 0.0019 | 低于 | 否 |
| Codex 同强度 | 10 Codex Strata IQ3_XXS low | 4 Codex gpt-6-luna low | 5 / 5 | 0.402 | 0.030 | 5.4 | 2.6e-05 | 0.0006 | 高于 | 0.0006 | 高于 | 否 |
| Codex 同强度 | 10 Codex Strata IQ3_XXS low | 7 Codex deepseek-flash low | 5 / 5 | -0.084 | 0.041 | 8.0 | 0.0758 | 1.0000 | 未分出 | 1.0000 | 未分出 | 否 |
| Codex 同强度 | 11 Codex Strata IQ3_XXS medium | 2 Codex gpt-6.1-sol medium | 5 / 5 | -0.339 | 0.015 | 4.3 | 1.4e-05 | 0.0003 | 低于 | 0.0003 | 低于 | 否 |
| Codex 同强度 | 11 Codex Strata IQ3_XXS medium | 5 Codex gpt-6-luna medium | 5 / 5 | 0.255 | 0.080 | 4.3 | 0.0308 | 0.4924 | 未分出 | 0.4924 | 未分出 | 否 |
| Codex 同强度 | 12 Codex Strata IQ3_XXS high | 3 Codex gpt-6.1-sol high | 5 / 5 | -0.333 | 0.016 | 7.6 | 5.5e-08 | 1.4e-06 | 低于 | 1.4e-06 | 低于 | 否 |
| Codex 同强度 | 12 Codex Strata IQ3_XXS high | 6 Codex gpt-6-luna high | 5 / 5 | -0.024 | 0.056 | 4.4 | 0.6832 | 1.0000 | 未分出 | 1.0000 | 未分出 | 否 |
| Codex 同强度 | 12 Codex Strata IQ3_XXS high | 8 Codex deepseek-flash high | 5 / 5 | -0.039 | 0.049 | 4.5 | 0.4697 | 1.0000 | 未分出 | 1.0000 | 未分出 | 否 |
| Claude Code 同强度 | 25 Claude Code Strata IQ3_XXS low | 13 Claude Code opus low | 5 / 5 | -0.198 | 0.061 | 7.9 | 0.0120 | 0.2276 | 未分出 | 0.2276 | 未分出 | 否 |
| Claude Code 同强度 | 25 Claude Code Strata IQ3_XXS low | 16 Claude Code sonnet low | 5 / 5 | -0.040 | 0.053 | 7.8 | 0.4719 | 1.0000 | 未分出 | 1.0000 | 未分出 | 否 |
| Claude Code 同强度 | 25 Claude Code Strata IQ3_XXS low | 19 Claude Code haiku low | 5 / 5 | 0.152 | 0.072 | 7.1 | 0.0718 | 1.0000 | 未分出 | 1.0000 | 未分出 | 否 |
| Claude Code 同强度 | 25 Claude Code Strata IQ3_XXS low | 22 Claude Code deepseek-flash low | 5 / 5 | -0.053 | 0.059 | 8.0 | 0.3991 | 1.0000 | 未分出 | 1.0000 | 未分出 | 否 |
| Claude Code 同强度 | 26 Claude Code Strata IQ3_XXS medium | 14 Claude Code opus medium | 5 / 5 | -0.218 | 0.039 | 7.9 | 0.0005 | 0.0103 | 低于 | 0.0103 | 低于 | 否 |
| Claude Code 同强度 | 26 Claude Code Strata IQ3_XXS medium | 17 Claude Code sonnet medium | 5 / 5 | -0.095 | 0.051 | 7.1 | 0.1039 | 1.0000 | 未分出 | 1.0000 | 未分出 | 否 |
| Claude Code 同强度 | 26 Claude Code Strata IQ3_XXS medium | 20 Claude Code haiku medium | 5 / 5 | 0.067 | 0.076 | 5.3 | 0.4153 | 1.0000 | 未分出 | 1.0000 | 未分出 | 否 |
| Claude Code 同强度 | 27 Claude Code Strata IQ3_XXS high | 15 Claude Code opus high | 5 / 5 | -0.300 | 0.033 | 7.8 | 2.1e-05 | 0.0005 | 低于 | 0.0005 | 低于 | 否 |
| Claude Code 同强度 | 27 Claude Code Strata IQ3_XXS high | 18 Claude Code sonnet high | 5 / 5 | -0.125 | 0.044 | 6.3 | 0.0278 | 0.4806 | 未分出 | 0.4806 | 未分出 | 否 |
| Claude Code 同强度 | 27 Claude Code Strata IQ3_XXS high | 21 Claude Code haiku high | 5 / 5 | -0.117 | 0.046 | 6.0 | 0.0452 | 0.6786 | 未分出 | 0.6786 | 未分出 | 否 |
| Claude Code 同强度 | 27 Claude Code Strata IQ3_XXS high | 23 Claude Code deepseek-flash high | 5 / 5 | 0.025 | 0.044 | 6.3 | 0.5879 | 1.0000 | 未分出 | 1.0000 | 未分出 | 否 |
| Codex 对 Claude Code | 10 Codex Strata IQ3_XXS low | 25 Claude Code Strata IQ3_XXS low | 5 / 5 | 0.030 | 0.050 | 7.1 | 0.5681 | 1.0000 | 未分出 | 1.0000 | 未分出 | 否 |
| Codex 对 Claude Code | 11 Codex Strata IQ3_XXS medium | 26 Claude Code Strata IQ3_XXS medium | 5 / 5 | 0.012 | 0.033 | 6.1 | 0.7229 | 1.0000 | 未分出 | 1.0000 | 未分出 | 否 |
| Codex 对 Claude Code | 12 Codex Strata IQ3_XXS high | 27 Claude Code Strata IQ3_XXS high | 5 / 5 | 0.033 | 0.025 | 6.4 | 0.2357 | 1.0000 | 未分出 | 1.0000 | 未分出 | 否 |
| Codex 对 Claude Code | 7 Codex deepseek-flash low | 22 Claude Code deepseek-flash low | 5 / 5 | 0.060 | 0.052 | 7.1 | 0.2848 | 1.0000 | 未分出 | 1.0000 | 未分出 | 否 |
| Codex 对 Claude Code | 8 Codex deepseek-flash high | 23 Claude Code deepseek-flash high | 5 / 5 | 0.096 | 0.061 | 7.6 | 0.1550 | 1.0000 | 未分出 | 1.0000 | 未分出 | 否 |
| Codex 对 Claude Code | 9 Codex deepseek-flash max | 24 Claude Code deepseek-flash max | 5 / 5 | 0.290 | 0.087 | 4.2 | 0.0267 | 0.4806 | 未分出 | 0.4806 | 未分出 | 否 |

### Code Standards v5.1（CStd）

#### 配置

| 配置 | 行 | 有效 | n | 无效 | 均值 ± SD | SE | 95% 区间 | 负分数 | 最小 | 中位数 | r8.3 均值 | rawScore | f | 修复 | 耗时（分钟） | 占时限 | 未缓存 | 缓存 | 输出 | token 来源 | 工具调用 | 引擎输入 tok/s | 引擎输出 tok/s | 任务平均输入 tok/s | 任务平均输出 tok/s | 费用均值（美元；DeepSeek 括号内人民币） | 周额度 | 模型 ID | service tier |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 Codex gpt-6.1-sol low | 主统计 | 5 | 5 | 0 | 0.845 ± 0.070 | 0.032 | 0.758 – 0.933 | 0 | 0.759 | 0.871 | 0.845 | 0.845 | 0.000 | 0 | 2.3 | 0.10 | 85,859 | 576,128 | 6,162 | API usage (relay) | 10.6 | 未知 | ≥44.9 | 646.1 | 44.5 | 只报 token |  | gpt-6.1-sol | default |
| 2 Codex gpt-6.1-sol medium | 主统计 | 5 | 5 | 0 | 0.892 ± 0.033 | 0.015 | 0.851 – 0.933 | 0 | 0.841 | 0.893 | 0.892 | 0.892 | 0.000 | 0 | 2.9 | 0.13 | 78,453 | 671,770 | 7,632 | API usage (relay) | 11.4 | 未知 | ≥44.6 | 455.6 | 44.2 | 只报 token |  | gpt-6.1-sol | default |
| 3 Codex gpt-6.1-sol high | 主统计 | 5 | 5 | 0 | 0.885 ± 0.043 | 0.019 | 0.831 – 0.939 | 0 | 0.815 | 0.906 | 0.885 | 0.885 | 0.000 | 0 | 4.7 | 0.22 | 100,401 | 862,285 | 12,640 | API usage (relay) | 13.4 | 未知 | ≥44.9 | 355.1 | 44.5 | 只报 token |  | gpt-6.1-sol | default |
| 4 Codex gpt-6-luna low | 主统计 | 5 | 5 | 1 | 0.163 ± 0.085 | 0.038 | 0.057 – 0.269 | 0 | 0.026 | 0.176 | 0.163 | 0.163 | 0.000 | 0 | 0.6 | 0.07 | 53,602 | 385,459 | 2,523 | API usage (relay) | 9.0 | 未知 | ≥66.8 | 1488.0 | 65.3 | 只报 token |  | gpt-6-luna | default |
| 5 Codex gpt-6-luna medium | 主统计 | 5 | 5 | 0 | 0.343 ± 0.168 | 0.075 | 0.135 – 0.552 | 0 | 0.157 | 0.363 | 0.343 | 0.346 | 0.015 | 1 | 0.9 | 0.09 | 54,954 | 417,690 | 4,016 | API usage (relay) | 9.4 | 未知 | ≥79.1 | 1258.9 | 77.7 | 只报 token |  | gpt-6-luna | default |
| 6 Codex gpt-6-luna high | 主统计 | 5 | 5 | 0 | 0.472 ± 0.077 | 0.034 | 0.377 – 0.568 | 0 | 0.346 | 0.499 | 0.472 | 0.472 | 0.000 | 0 | 1.3 | 0.13 | 56,941 | 378,317 | 7,391 | API usage (relay) | 8.8 | 未知 | ≥91.0 | 725.1 | 90.7 | 只报 token |  | gpt-6-luna | default |
| 7 Codex deepseek-flash low | 主统计 | 5 | 5 | 0 | 0.634 ± 0.059 | 0.026 | 0.561 – 0.707 | 0 | 0.570 | 0.648 | 0.634 | 0.634 | 0.000 | 0 | 2.0 | 0.32 | 48,966 | 727,014 | 22,591 | API usage (relay) | 34.8 | 未知 | ≥190.9 | 420.2 | 188.7 | 0.023（¥0.154） |  | deepseek-flash | default |
| 8 Codex deepseek-flash high | 主统计 | 5 | 5 | 0 | 0.655 ± 0.088 | 0.040 | 0.545 – 0.764 | 0 | 0.532 | 0.659 | 0.655 | 0.657 | 0.005 | 1 | 2.5 | 0.45 | 47,878 | 858,010 | 23,831 | API usage (relay) | 33.8 | 未知 | ≥168.7 | 343.5 | 164.4 | ≥0.024（¥0.160） |  | deepseek-flash | default、not-returned |
| 9 Codex deepseek-flash max | 主统计 | 5 | 5 | 0 | 0.737 ± 0.077 | 0.034 | 0.642 – 0.833 | 0 | 0.624 | 0.727 | 0.737 | 0.743 | 0.008 | 2 | 2.7 | 0.45 | 55,262 | 1,174,528 | 31,206 | API usage (relay) | 43.4 | 未知 | ≥203.6 | 351.7 | 197.8 | ≥0.031（¥0.204） |  | deepseek-flash | default、not-returned |
| 10 Codex Strata IQ3_XXS low | 主统计 | 6 | 5 | 0 | 0.766 ± 0.024 | 0.011 | 0.736 – 0.796 | 0 | 0.734 | 0.765 | 0.766 | 0.804 | 0.046 | 56 | 9.5 | 0.61 | 64,949 | 2,192,653 | 39,834 | engine log | 39.0 | 1359.7 | 83.4 | 114.2 | 69.9 | 0.064 |  | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | 主统计 | 10 | 5 | 0 | 0.716 ± 0.090 | 0.040 | 0.605 – 0.827 | 0 | 0.619 | 0.727 | 0.716 | 0.760 | 0.060 | 94 | 9.6 | 0.60 | 60,977 | 1,726,964 | 40,991 | engine log | 35.6 | 1454.0 | 83.3 | 106.3 | 70.9 | 0.056 |  | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | 主统计 | 10 | 5 | 0 | 0.767 ± 0.039 | 0.017 | 0.719 – 0.816 | 0 | 0.705 | 0.782 | 0.767 | 0.818 | 0.061 | 67 | 10.4 | 0.60 | 64,589 | 1,526,163 | 45,054 | engine log | 32.8 | 1579.4 | 83.2 | 104.1 | 72.0 | 0.055 |  | 未知 | 未知 |
| 13 Claude Code opus low | 主统计 | 5 | 5 | 0 | 0.658 ± 0.045 | 0.020 | 0.601 – 0.714 | 0 | 0.607 | 0.650 | 0.658 | 0.697 | 0.056 | 75 | 1.6 | 0.09 | 47,540 | 258,803 | 4,928 | Claude Code stream result usage | 6.8 | 未知 | ≥77.6 | 539.7 | 55.0 | 0.531 | 0.23% | claude-opus-5-5 | standard |
| 14 Claude Code opus medium | 主统计 | 5 | 5 | 0 | 0.774 ± 0.037 | 0.016 | 0.728 – 0.819 | 0 | 0.738 | 0.770 | 0.774 | 0.812 | 0.047 | 93 | 2.0 | 0.11 | 59,533 | 456,039 | 9,656 | Claude Code stream result usage | 10.4 | 未知 | ≥91.2 | 526.4 | 83.5 | 0.761 | 0.33% | claude-opus-5-5 | standard |
| 15 Claude Code opus high | 主统计 | 5 | 5 | 0 | 0.847 ± 0.035 | 0.016 | 0.803 – 0.891 | 0 | 0.805 | 0.835 | 0.847 | 0.858 | 0.013 | 6 | 2.5 | 0.15 | 63,400 | 568,341 | 12,174 | Claude Code stream result usage | 11.8 | 未知 | ≥88.2 | 423.3 | 81.0 | 0.864 | 0.37% | claude-opus-5-5 | standard |
| 16 Claude Code sonnet low | 主统计 | 5 | 5 | 0 | 0.486 ± 0.088 | 0.039 | 0.377 – 0.595 | 0 | 0.412 | 0.440 | 0.486 | 0.498 | 0.021 | 3 | 1.5 | 0.11 | 44,761 | 268,998 | 4,059 | Claude Code stream result usage | 8.4 | 未知 | ≥88.0 | 608.5 | 54.2 | 0.247 | 0.11% | claude-sonnet-5-5 | standard |
| 17 Claude Code sonnet medium | 主统计 | 5 | 5 | 0 | 0.529 ± 0.091 | 0.041 | 0.415 – 0.643 | 0 | 0.421 | 0.532 | 0.529 | 0.534 | 0.010 | 2 | 1.4 | 0.10 | 46,320 | 225,781 | 5,027 | Claude Code stream result usage | 7.2 | 未知 | ≥100.8 | 660.5 | 72.8 | 0.258 | 0.11% | claude-sonnet-5-5 | standard |
| 18 Claude Code sonnet high | 主统计 | 5 | 5 | 0 | 0.651 ± 0.059 | 0.026 | 0.577 – 0.724 | 0 | 0.580 | 0.656 | 0.651 | 0.674 | 0.035 | 12 | 2.0 | 0.14 | 55,293 | 348,729 | 8,420 | Claude Code stream result usage | 9.6 | 未知 | ≥99.9 | 525.6 | 79.3 | 0.340 | 0.15% | claude-sonnet-5-5 | standard |
| 19 Claude Code haiku low | 主统计 | 5 | 5 | 0 | 0.415 ± 0.065 | 0.029 | 0.334 – 0.496 | 0 | 0.331 | 0.392 | 0.415 | 0.418 | 0.007 | 1 | 1.3 | 0.15 | 50,052 | 218,546 | 11,498 | Claude Code stream result usage | 7.6 | 未知 | ≥198.8 | 679.7 | 155.3 | 0.018 | 0.01% | claude-haiku-5-5 | standard |
| 20 Claude Code haiku medium | 主统计 | 5 | 5 | 0 | 0.501 ± 0.055 | 0.025 | 0.432 – 0.570 | 0 | 0.429 | 0.502 | 0.501 | 0.514 | 0.025 | 5 | 1.6 | 0.20 | 55,875 | 298,643 | 15,486 | Claude Code stream result usage | 9.0 | 未知 | ≥197.8 | 624.2 | 171.5 | 0.022 | 0.01% | claude-haiku-5-5 | standard |
| 21 Claude Code haiku high | 主统计 | 5 | 5 | 0 | 0.530 ± 0.047 | 0.021 | 0.472 – 0.588 | 0 | 0.480 | 0.510 | 0.530 | 0.546 | 0.030 | 10 | 2.2 | 0.27 | 64,293 | 336,609 | 21,151 | Claude Code stream result usage | 10.8 | 未知 | ≥207.0 | 501.5 | 163.5 | 0.027 | 0.01% | claude-haiku-5-5 | standard |
| 22 Claude Code deepseek-flash low | 主统计 | 5 | 5 | 0 | 0.532 ± 0.099 | 0.044 | 0.409 – 0.655 | 0 | 0.420 | 0.521 | 0.532 | 0.563 | 0.056 | 18 | 2.8 | 0.49 | 38,620 | 280,192 | 10,241 | Claude Code stream result usage | 15.0 | 未知 | ≥148.2 | 279.5 | 77.9 | 0.013（¥0.085） |  | deepseek-flash | standard |
| 23 Claude Code deepseek-flash high | 主统计 | 5 | 5 | 0 | 0.594 ± 0.105 | 0.047 | 0.465 – 0.724 | 0 | 0.423 | 0.606 | 0.594 | 0.640 | 0.073 | 22 | 3.2 | 0.56 | 43,170 | 493,005 | 14,499 | Claude Code stream result usage | 18.4 | 未知 | ≥143.0 | 226.7 | 76.5 | 0.017（¥0.111） |  | deepseek-flash | standard |
| 23 Claude Code deepseek-flash high | high requested as medium, T=362 | 1 | 1 | 0 | 0.563 ± 未知 | 未知 | 未知 | 0 | 0.563 | 0.563 | 0.563 | 0.626 | 0.100 | 6 | 3.8 | 0.63 | 41,861 | 324,864 | 10,223 | Claude Code stream result usage | 13.0 | 未知 | ≥144.0 | 184.8 | 45.1 | 0.013（¥0.089） |  | deepseek-flash | standard |
| 23 Claude Code deepseek-flash high | 敏感性：high+medium 合并（描述性，high requested as medium, T=362） | 6 | 6 | 0 | 0.589 ± 0.094 | 0.039 | 0.490 – 0.688 | 0 | 0.423 | 0.599 | 0.589 | 0.638 | 0.078 | 28 | 3.3 | 0.57 | 42,952 | 464,981 | 13,787 | Claude Code stream result usage | 17.5 | 未知 | ≥143.2 | 219.7 | 71.3 | 0.016（¥0.107） |  | deepseek-flash | standard |
| 24 Claude Code deepseek-flash max | 主统计 | 5 | 5 | 0 | 0.610 ± 0.071 | 0.032 | 0.522 – 0.698 | 0 | 0.511 | 0.633 | 0.610 | 0.643 | 0.050 | 14 | 3.7 | 0.62 | 47,831 | 531,277 | 22,256 | Claude Code stream result usage | 23.8 | 未知 | ≥179.2 | 220.4 | 104.1 | 0.022（¥0.147） |  | deepseek-flash | standard |
| 25 Claude Code Strata IQ3_XXS low | 主统计 | 5 | 5 | 4 | 0.703 ± 0.083 | 0.037 | 0.599 – 0.806 | 0 | 0.591 | 0.719 | 0.703 | 0.738 | 0.047 | 115 | 10.0 | 0.69 | 59,875 | 2,174,520 | 45,394 | engine log | 43.4 | 1240.7 | 84.7 | 100.3 | 75.8 | 0.065 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 26 Claude Code Strata IQ3_XXS medium | 主统计 | 5 | 5 | 5 | 0.706 ± 0.052 | 0.023 | 0.642 – 0.770 | 0 | 0.661 | 0.690 | 0.706 | 0.770 | 0.081 | 84 | 6.9 | 0.47 | 49,224 | 1,043,134 | 32,368 | engine log | 29.6 | 1473.0 | 86.4 | 123.6 | 77.3 | 0.039 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 27 Claude Code Strata IQ3_XXS high | 主统计 | 5 | 5 | 5 | 0.718 ± 0.067 | 0.030 | 0.635 – 0.801 | 0 | 0.682 | 0.690 | 0.718 | 0.757 | 0.051 | 31 | 9.2 | 0.62 | 57,419 | 1,161,646 | 43,895 | engine log | 30.6 | 1539.6 | 86.3 | 104.0 | 79.4 | 0.048 |  | qwen3.8-flash-next-iq3_xxs | not-returned |

#### 预登记比较（25 个，Holm）

| 组 | Strata / Codex 侧 | 对照 / Claude Code 侧 | n | d | SE | df | p | Holm p | 结论 | r8.3 Holm p | r8.3 结论 | 结论改变 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Codex 同强度 | 10 Codex Strata IQ3_XXS low | 1 Codex gpt-6.1-sol low | 5 / 5 | -0.080 | 0.033 | 4.9 | 0.0632 | 0.5619 | 未分出 | 0.5619 | 未分出 | 否 |
| Codex 同强度 | 10 Codex Strata IQ3_XXS low | 4 Codex gpt-6-luna low | 5 / 5 | 0.603 | 0.040 | 4.6 | 3.9e-05 | 0.0010 | 高于 | 0.0010 | 高于 | 否 |
| Codex 同强度 | 10 Codex Strata IQ3_XXS low | 7 Codex deepseek-flash low | 5 / 5 | 0.132 | 0.028 | 5.3 | 0.0050 | 0.0843 | 未分出 | 0.0843 | 未分出 | 否 |
| Codex 同强度 | 11 Codex Strata IQ3_XXS medium | 2 Codex gpt-6.1-sol medium | 5 / 5 | -0.177 | 0.043 | 5.1 | 0.0088 | 0.1342 | 未分出 | 0.1342 | 未分出 | 否 |
| Codex 同强度 | 11 Codex Strata IQ3_XXS medium | 5 Codex gpt-6-luna medium | 5 / 5 | 0.372 | 0.085 | 6.1 | 0.0045 | 0.0809 | 未分出 | 0.0809 | 未分出 | 否 |
| Codex 同强度 | 12 Codex Strata IQ3_XXS high | 3 Codex gpt-6.1-sol high | 5 / 5 | -0.118 | 0.026 | 7.9 | 0.0020 | 0.0399 | 低于 | 0.0399 | 低于 | 否 |
| Codex 同强度 | 12 Codex Strata IQ3_XXS high | 6 Codex gpt-6-luna high | 5 / 5 | 0.295 | 0.038 | 5.9 | 0.0003 | 0.0067 | 高于 | 0.0067 | 高于 | 否 |
| Codex 同强度 | 12 Codex Strata IQ3_XXS high | 8 Codex deepseek-flash high | 5 / 5 | 0.113 | 0.043 | 5.5 | 0.0433 | 0.4764 | 未分出 | 0.4764 | 未分出 | 否 |
| Claude Code 同强度 | 25 Claude Code Strata IQ3_XXS low | 13 Claude Code opus low | 5 / 5 | 0.045 | 0.042 | 6.2 | 0.3277 | 0.9832 | 未分出 | 0.9832 | 未分出 | 否 |
| Claude Code 同强度 | 25 Claude Code Strata IQ3_XXS low | 16 Claude Code sonnet low | 5 / 5 | 0.216 | 0.054 | 8.0 | 0.0040 | 0.0756 | 未分出 | 0.0756 | 未分出 | 否 |
| Claude Code 同强度 | 25 Claude Code Strata IQ3_XXS low | 19 Claude Code haiku low | 5 / 5 | 0.288 | 0.047 | 7.6 | 0.0004 | 0.0080 | 高于 | 0.0080 | 高于 | 否 |
| Claude Code 同强度 | 25 Claude Code Strata IQ3_XXS low | 22 Claude Code deepseek-flash low | 5 / 5 | 0.171 | 0.058 | 7.8 | 0.0189 | 0.2453 | 未分出 | 0.2453 | 未分出 | 否 |
| Claude Code 同强度 | 26 Claude Code Strata IQ3_XXS medium | 14 Claude Code opus medium | 5 / 5 | -0.067 | 0.028 | 7.2 | 0.0478 | 0.4780 | 未分出 | 0.4780 | 未分出 | 否 |
| Claude Code 同强度 | 26 Claude Code Strata IQ3_XXS medium | 17 Claude Code sonnet medium | 5 / 5 | 0.177 | 0.047 | 6.3 | 0.0084 | 0.1342 | 未分出 | 0.1342 | 未分出 | 否 |
| Claude Code 同强度 | 26 Claude Code Strata IQ3_XXS medium | 20 Claude Code haiku medium | 5 / 5 | 0.205 | 0.034 | 8.0 | 0.0003 | 0.0071 | 高于 | 0.0071 | 高于 | 否 |
| Claude Code 同强度 | 27 Claude Code Strata IQ3_XXS high | 15 Claude Code opus high | 5 / 5 | -0.129 | 0.034 | 6.1 | 0.0086 | 0.1342 | 未分出 | 0.1342 | 未分出 | 否 |
| Claude Code 同强度 | 27 Claude Code Strata IQ3_XXS high | 18 Claude Code sonnet high | 5 / 5 | 0.067 | 0.040 | 7.9 | 0.1316 | 0.7895 | 未分出 | 0.7895 | 未分出 | 否 |
| Claude Code 同强度 | 27 Claude Code Strata IQ3_XXS high | 21 Claude Code haiku high | 5 / 5 | 0.188 | 0.037 | 7.2 | 0.0012 | 0.0257 | 高于 | 0.0257 | 高于 | 否 |
| Claude Code 同强度 | 27 Claude Code Strata IQ3_XXS high | 23 Claude Code deepseek-flash high | 5 / 5 | 0.124 | 0.056 | 6.8 | 0.0624 | 0.5619 | 未分出 | 0.5619 | 未分出 | 否 |
| Codex 对 Claude Code | 10 Codex Strata IQ3_XXS low | 25 Claude Code Strata IQ3_XXS low | 5 / 5 | 0.063 | 0.039 | 4.7 | 0.1678 | 0.8392 | 未分出 | 0.8392 | 未分出 | 否 |
| Codex 对 Claude Code | 11 Codex Strata IQ3_XXS medium | 26 Claude Code Strata IQ3_XXS medium | 5 / 5 | 0.009 | 0.046 | 6.4 | 0.8438 | 0.9832 | 未分出 | 0.9832 | 未分出 | 否 |
| Codex 对 Claude Code | 12 Codex Strata IQ3_XXS high | 27 Claude Code Strata IQ3_XXS high | 5 / 5 | 0.049 | 0.035 | 6.4 | 0.2004 | 0.8392 | 未分出 | 0.8392 | 未分出 | 否 |
| Codex 对 Claude Code | 7 Codex deepseek-flash low | 22 Claude Code deepseek-flash low | 5 / 5 | 0.103 | 0.052 | 6.5 | 0.0898 | 0.6288 | 未分出 | 0.6288 | 未分出 | 否 |
| Codex 对 Claude Code | 8 Codex deepseek-flash high | 23 Claude Code deepseek-flash high | 5 / 5 | 0.060 | 0.061 | 7.8 | 0.3564 | 0.9832 | 未分出 | 0.9832 | 未分出 | 否 |
| Codex 对 Claude Code | 9 Codex deepseek-flash max | 24 Claude Code deepseek-flash max | 5 / 5 | 0.128 | 0.047 | 8.0 | 0.0262 | 0.3141 | 未分出 | 0.3141 | 未分出 | 否 |

### Commit Audit v3（CA）

#### 配置

| 配置 | 行 | 有效 | n | 无效 | 均值 ± SD | SE | 95% 区间 | 负分数 | 最小 | 中位数 | r8.3 均值 | rawScore | f | 修复 | 耗时（分钟） | 占时限 | 未缓存 | 缓存 | 输出 | token 来源 | 工具调用 | 引擎输入 tok/s | 引擎输出 tok/s | 任务平均输入 tok/s | 任务平均输出 tok/s | 费用均值（美元；DeepSeek 括号内人民币） | 周额度 | 模型 ID | service tier |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 Codex gpt-6.1-sol low | 主统计 | 5 | 5 | 0 | 0.868 ± 0.017 | 0.008 | 0.847 – 0.890 | 0 | 0.851 | 0.868 | 0.868 | 0.868 | 0.000 | 0 | 1.5 | 无时限 | 65,511 | 303,846 | 5,929 | API usage (relay) | 6.6 | 未知 | ≥64.3 | 741.4 | 63.6 | 只报 token |  | gpt-6.1-sol | default |
| 2 Codex gpt-6.1-sol medium | 主统计 | 5 | 5 | 0 | 0.872 ± 0.007 | 0.003 | 0.863 – 0.880 | 0 | 0.865 | 0.872 | 0.872 | 0.872 | 0.000 | 0 | 2.0 | 无时限 | 64,688 | 359,910 | 7,572 | API usage (relay) | 7.4 | 未知 | ≥63.9 | 564.9 | 63.8 | 只报 token |  | gpt-6.1-sol | default |
| 3 Codex gpt-6.1-sol high | 主统计 | 5 | 5 | 0 | 0.866 ± 0.016 | 0.007 | 0.846 – 0.886 | 0 | 0.837 | 0.873 | 0.866 | 0.866 | 0.000 | 0 | 2.9 | 无时限 | 69,537 | 447,846 | 10,287 | API usage (relay) | 8.6 | 未知 | ≥59.6 | 419.5 | 59.5 | 只报 token |  | gpt-6.1-sol | default |
| 4 Codex gpt-6-luna low | 主统计 | 5 | 5 | 2 | -1.045 ± 0.370 | 0.165 | -1.504 – -0.586 | 5 | -1.567 | -1.074 | 0.000 | -0.442 | 0.020 | 16 | 1.4 | 无时限 | 58,620 | 660,326 | 8,449 | API usage (relay) | 12.4 | 未知 | ≥100.7 | 732.6 | 99.8 | 只报 token |  | gpt-6-luna | default |
| 5 Codex gpt-6-luna medium | 主统计 | 5 | 5 | 2 | -0.216 ± 0.480 | 0.215 | -0.811 – 0.380 | 3 | -0.861 | -0.228 | 0.090 | -0.042 | 0.000 | 0 | 2.4 | 无时限 | 67,415 | 1,103,872 | 15,183 | API usage (relay) | 18.4 | 未知 | ≥103.4 | 508.7 | 103.0 | 只报 token |  | gpt-6-luna | default |
| 6 Codex gpt-6-luna high | 主统计 | 5 | 5 | 5 | 0.134 ± 0.628 | 0.281 | -0.646 – 0.914 | 1 | -0.932 | 0.360 | 0.320 | 0.241 | 0.008 | 0 | 3.9 | 无时限 | 84,567 | 1,256,166 | 26,183 | API usage (relay) | 19.4 | 未知 | ≥112.2 | 389.2 | 111.5 | 只报 token |  | gpt-6-luna | default |
| 7 Codex deepseek-flash low | 主统计 | 5 | 5 | 0 | 0.707 ± 0.076 | 0.034 | 0.612 – 0.802 | 0 | 0.622 | 0.710 | 0.707 | 0.721 | 0.020 | 85 | 4.9 | 无时限 | 61,255 | 2,262,195 | 60,415 | API usage (relay) | 61.6 | 未知 | ≥210.1 | 218.9 | 208.4 | 0.052（¥0.348） |  | deepseek-flash | default |
| 8 Codex deepseek-flash high | 主统计 | 8 | 8 | 0 | 0.645 ± 0.219 | 0.077 | 0.463 – 0.828 | 0 | 0.223 | 0.740 | 0.645 | 0.654 | 0.020 | 9 | 5.1 | 无时限 | 60,030 | 2,211,392 | 65,934 | API usage (relay) | 64.0 | 未知 | ≥216.0 | 196.7 | 214.6 | 0.055（¥0.368） |  | deepseek-flash | default |
| 8 Codex deepseek-flash high | 一致性行（前 5 个） | 8 | 5 | 0 | 0.577 ± 0.258 | 0.115 | 0.257 – 0.897 | 0 | 0.223 | 0.734 | 0.577 | 0.592 | 0.032 | 9 | 5.1 | 无时限 | 56,399 | 1,936,563 | 63,196 | API usage (relay) | 54.0 | 未知 | ≥210.7 | 189.3 | 209.4 | 0.052（¥0.348） |  | deepseek-flash | default |
| 9 Codex deepseek-flash max | 主统计 | 5 | 5 | 0 | 0.744 ± 0.188 | 0.084 | 0.512 – 0.977 | 0 | 0.416 | 0.830 | 0.744 | 0.744 | 0.000 | 0 | 7.5 | 无时限 | 70,953 | 3,158,170 | 83,300 | API usage (relay) | 72.0 | 未知 | ≥220.7 | 174.3 | 201.4 | 0.070（¥0.467） |  | deepseek-flash | default |
| 10 Codex Strata IQ3_XXS low | 主统计 | 10 | 5 | 2 | 0.545 ± 0.101 | 0.045 | 0.419 – 0.670 | 0 | 0.385 | 0.557 | 0.545 | 0.553 | 0.020 | 93 | 15.5 | 无时限 | 95,497 | 3,526,212 | 74,886 | engine log | 41.8 | 1225.8 | 91.7 | 99.5 | 80.6 | 0.106 |  | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | 主统计 | 10 | 5 | 2 | 0.657 ± 0.150 | 0.067 | 0.471 – 0.842 | 0 | 0.428 | 0.661 | 0.657 | 0.657 | 0.000 | 0 | 17.8 | 无时限 | 133,840 | 3,295,804 | 86,406 | engine log | 41.2 | 1504.3 | 91.8 | 125.6 | 80.8 | 0.113 |  | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | 主统计 | 10 | 5 | 0 | 0.661 ± 0.089 | 0.040 | 0.551 – 0.771 | 0 | 0.554 | 0.664 | 0.661 | 0.661 | 0.000 | 0 | 19.9 | 无时限 | 176,168 | 3,281,530 | 96,995 | engine log | 51.2 | 1611.5 | 91.8 | 134.8 | 80.9 | 0.125 |  | 未知 | 未知 |
| 13 Claude Code opus low | 主统计 | 5 | 5 | 0 | 0.830 ± 0.027 | 0.012 | 0.797 – 0.863 | 0 | 0.799 | 0.823 | 0.830 | 0.846 | 0.019 | 0 | 2.9 | 无时限 | 58,744 | 211,738 | 13,747 | Claude Code stream result usage | 5.4 | 未知 | ≥110.9 | 361.3 | 83.4 | 0.787 | 0.34% | claude-opus-5-5 | standard |
| 14 Claude Code opus medium | 主统计 | 5 | 5 | 0 | 0.856 ± 0.019 | 0.008 | 0.832 – 0.879 | 0 | 0.839 | 0.851 | 0.856 | 0.856 | 0.000 | 0 | 4.4 | 无时限 | 71,744 | 381,204 | 20,306 | Claude Code stream result usage | 8.6 | 未知 | ≥106.5 | 287.1 | 81.5 | 1.056 | 0.45% | claude-opus-5-5 | standard |
| 15 Claude Code opus high | 主统计 | 5 | 5 | 0 | 0.876 ± 0.018 | 0.008 | 0.853 – 0.898 | 0 | 0.847 | 0.876 | 0.876 | 0.883 | 0.009 | 0 | 7.3 | 无时限 | 87,707 | 658,386 | 33,566 | Claude Code stream result usage | 12.0 | 未知 | ≥109.4 | 205.7 | 77.1 | 1.505 | 0.65% | claude-opus-5-5 | standard |
| 16 Claude Code sonnet low | 主统计 | 5 | 5 | 0 | 0.814 ± 0.012 | 0.005 | 0.799 – 0.828 | 0 | 0.797 | 0.811 | 0.814 | 0.839 | 0.031 | 0 | 3.4 | 无时限 | 59,161 | 280,743 | 15,905 | Claude Code stream result usage | 7.6 | 未知 | ≥117.3 | 310.3 | 83.0 | 0.424 | 0.18% | claude-sonnet-5-5 | standard |
| 17 Claude Code sonnet medium | 主统计 | 5 | 5 | 0 | 0.831 ± 0.058 | 0.026 | 0.759 – 0.904 | 0 | 0.733 | 0.851 | 0.831 | 0.849 | 0.021 | 0 | 3.6 | 无时限 | 63,856 | 291,961 | 19,228 | Claude Code stream result usage | 7.8 | 未知 | ≥127.9 | 310.5 | 92.9 | 0.477 | 0.21% | claude-sonnet-5-5 | standard |
| 18 Claude Code sonnet high | 主统计 | 5 | 5 | 0 | 0.851 ± 0.010 | 0.004 | 0.839 – 0.863 | 0 | 0.836 | 0.852 | 0.851 | 0.872 | 0.024 | 0 | 4.8 | 无时限 | 76,064 | 423,798 | 30,246 | Claude Code stream result usage | 10.2 | 未知 | ≥144.7 | 267.5 | 106.7 | 0.649 | 0.28% | claude-sonnet-5-5 | standard |
| 19 Claude Code haiku low | 主统计 | 5 | 5 | 0 | 0.863 ± 0.018 | 0.008 | 0.840 – 0.886 | 0 | 0.833 | 0.874 | 0.863 | 0.863 | 0.000 | 0 | 5.7 | 无时限 | 112,977 | 605,827 | 65,653 | Claude Code stream result usage | 11.0 | 未知 | ≥243.2 | 334.2 | 194.2 | 0.140 | 0.06% | claude-haiku-5-5 | standard |
| 20 Claude Code haiku medium | 主统计 | 5 | 5 | 0 | 0.874 ± 0.017 | 0.008 | 0.853 – 0.896 | 0 | 0.850 | 0.875 | 0.874 | 0.879 | 0.005 | 0 | 6.7 | 无时限 | 123,365 | 588,370 | 75,697 | Claude Code stream result usage | 13.8 | 未知 | ≥240.7 | 311.7 | 191.5 | 0.144 | 0.06% | claude-haiku-5-5 | standard |
| 21 Claude Code haiku high | 主统计 | 5 | 5 | 0 | 0.862 ± 0.023 | 0.010 | 0.833 – 0.891 | 0 | 0.824 | 0.863 | 0.862 | 0.862 | 0.000 | 0 | 9.3 | 无时限 | 157,462 | 1,201,950 | 103,424 | Claude Code stream result usage | 18.4 | 未知 | ≥240.6 | 286.2 | 188.4 | 0.297 | 0.13% | claude-haiku-5-5 | standard |
| 22 Claude Code deepseek-flash low | 主统计 | 5 | 5 | 0 | 0.704 ± 0.075 | 0.033 | 0.611 – 0.797 | 0 | 0.631 | 0.709 | 0.704 | 0.704 | 0.000 | 0 | 8.1 | 无时限 | 44,289 | 1,055,667 | 62,161 | Claude Code stream result usage | 26.8 | 未知 | ≥211.0 | 94.2 | 128.3 | 0.047（¥0.314） |  | deepseek-flash | standard |
| 23 Claude Code deepseek-flash high | 主统计 | 8 | 8 | 0 | 0.742 ± 0.086 | 0.030 | 0.670 – 0.814 | 0 | 0.629 | 0.732 | 0.742 | 0.742 | 0.000 | 0 | 11.3 | 无时限 | 53,452 | 1,795,920 | 87,010 | Claude Code stream result usage | 37.1 | 未知 | ≥209.4 | 82.9 | 132.0 | 0.066（¥0.437） |  | deepseek-flash | standard |
| 23 Claude Code deepseek-flash high | 一致性行（前 5 个） | 8 | 5 | 0 | 0.739 ± 0.082 | 0.037 | 0.637 – 0.841 | 0 | 0.629 | 0.731 | 0.739 | 0.739 | 0.000 | 0 | 12.3 | 无时限 | 52,706 | 1,756,237 | 92,185 | Claude Code stream result usage | 37.8 | 未知 | ≥207.9 | 73.8 | 127.8 | 0.068（¥0.457） |  | deepseek-flash | standard |
| 24 Claude Code deepseek-flash max | 主统计 | 5 | 5 | 0 | 0.817 ± 0.059 | 0.027 | 0.744 – 0.891 | 0 | 0.735 | 0.843 | 0.817 | 0.817 | 0.000 | 0 | 15.9 | 无时限 | 72,637 | 2,498,355 | 134,932 | Claude Code stream result usage | 65.2 | 未知 | ≥205.2 | 81.1 | 151.2 | 0.099（¥0.662） |  | deepseek-flash | standard |
| 25 Claude Code Strata IQ3_XXS low | 主统计 | 10 | 5 | 0 | 0.571 ± 0.212 | 0.095 | 0.308 – 0.835 | 0 | 0.254 | 0.608 | 0.571 | 0.574 | 0.006 | 0 | 16.8 | 无时限 | 79,056 | 4,660,554 | 81,461 | engine log | 62.6 | 1153.5 | 89.8 | 80.0 | 81.1 | 0.125 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 26 Claude Code Strata IQ3_XXS medium | 主统计 | 10 | 5 | 0 | 0.526 ± 0.080 | 0.036 | 0.427 – 0.625 | 0 | 0.394 | 0.555 | 0.526 | 0.532 | 0.011 | 0 | 16.1 | 无时限 | 71,517 | 2,185,275 | 71,277 | engine log | 41.8 | 1454.3 | 93.5 | 81.4 | 78.8 | 0.079 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 27 Claude Code Strata IQ3_XXS high | 主统计 | 10 | 5 | 0 | 0.601 ± 0.149 | 0.066 | 0.417 – 0.786 | 0 | 0.441 | 0.568 | 0.601 | 0.601 | 0.000 | 0 | 13.7 | 无时限 | 59,736 | 2,324,608 | 71,029 | engine log | 43.6 | 1378.6 | 93.1 | 78.5 | 85.6 | 0.080 |  | qwen3.8-flash-next-iq3_xxs | not-returned |

#### 预登记比较（25 个，Holm）

| 组 | Strata / Codex 侧 | 对照 / Claude Code 侧 | n | d | SE | df | p | Holm p | 结论 | r8.3 Holm p | r8.3 结论 | 结论改变 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Codex 同强度 | 10 Codex Strata IQ3_XXS low | 1 Codex gpt-6.1-sol low | 5 / 5 | -0.323 | 0.046 | 4.2 | 0.0017 | 0.0359 | 低于 | 0.0342 | 低于 | 否 |
| Codex 同强度 | 10 Codex Strata IQ3_XXS low | 4 Codex gpt-6-luna low | 5 / 5 | 1.590 | 0.171 | 4.6 | 0.0004 | 0.0091 | 高于 | 0.0065 | 高于 | 否 |
| Codex 同强度 | 10 Codex Strata IQ3_XXS low | 7 Codex deepseek-flash low | 5 / 5 | -0.162 | 0.057 | 7.4 | 0.0228 | 0.3425 | 未分出 | 0.3425 | 未分出 | 否 |
| Codex 同强度 | 11 Codex Strata IQ3_XXS medium | 2 Codex gpt-6.1-sol medium | 5 / 5 | -0.215 | 0.067 | 4.0 | 0.0323 | 0.4528 | 未分出 | 0.4528 | 未分出 | 否 |
| Codex 同强度 | 11 Codex Strata IQ3_XXS medium | 5 Codex gpt-6-luna medium | 5 / 5 | 0.872 | 0.225 | 4.8 | 0.0128 | 0.2423 | 未分出 | 0.0139 | 高于 | 是 |
| Codex 同强度 | 12 Codex Strata IQ3_XXS high | 3 Codex gpt-6.1-sol high | 5 / 5 | -0.205 | 0.040 | 4.3 | 0.0060 | 0.1199 | 未分出 | 0.1139 | 未分出 | 否 |
| Codex 同强度 | 12 Codex Strata IQ3_XXS high | 6 Codex gpt-6-luna high | 5 / 5 | 0.527 | 0.284 | 4.2 | 0.1341 | 1.0000 | 未分出 | 0.5247 | 未分出 | 否 |
| Codex 同强度 | 12 Codex Strata IQ3_XXS high | 8 Codex deepseek-flash high | 5 / 8 | 0.015 | 0.087 | 10.0 | 0.8620 | 1.0000 | 未分出 | 1.0000 | 未分出 | 否 |
| Claude Code 同强度 | 25 Claude Code Strata IQ3_XXS low | 13 Claude Code opus low | 5 / 5 | -0.259 | 0.096 | 4.1 | 0.0521 | 0.6256 | 未分出 | 0.5734 | 未分出 | 否 |
| Claude Code 同强度 | 25 Claude Code Strata IQ3_XXS low | 16 Claude Code sonnet low | 5 / 5 | -0.243 | 0.095 | 4.0 | 0.0630 | 0.6927 | 未分出 | 0.6297 | 未分出 | 否 |
| Claude Code 同强度 | 25 Claude Code Strata IQ3_XXS low | 19 Claude Code haiku low | 5 / 5 | -0.292 | 0.095 | 4.1 | 0.0369 | 0.4799 | 未分出 | 0.4799 | 未分出 | 否 |
| Claude Code 同强度 | 25 Claude Code Strata IQ3_XXS low | 22 Claude Code deepseek-flash low | 5 / 5 | -0.133 | 0.101 | 5.0 | 0.2442 | 1.0000 | 未分出 | 1.0000 | 未分出 | 否 |
| Claude Code 同强度 | 26 Claude Code Strata IQ3_XXS medium | 14 Claude Code opus medium | 5 / 5 | -0.330 | 0.037 | 4.4 | 0.0005 | 0.0114 | 低于 | 0.0114 | 低于 | 否 |
| Claude Code 同强度 | 26 Claude Code Strata IQ3_XXS medium | 17 Claude Code sonnet medium | 5 / 5 | -0.306 | 0.044 | 7.3 | 0.0002 | 0.0046 | 低于 | 0.0046 | 低于 | 否 |
| Claude Code 同强度 | 26 Claude Code Strata IQ3_XXS medium | 20 Claude Code haiku medium | 5 / 5 | -0.349 | 0.037 | 4.4 | 0.0004 | 0.0099 | 低于 | 0.0099 | 低于 | 否 |
| Claude Code 同强度 | 27 Claude Code Strata IQ3_XXS high | 15 Claude Code opus high | 5 / 5 | -0.274 | 0.067 | 4.1 | 0.0140 | 0.2517 | 未分出 | 0.2517 | 未分出 | 否 |
| Claude Code 同强度 | 27 Claude Code Strata IQ3_XXS high | 18 Claude Code sonnet high | 5 / 5 | -0.250 | 0.067 | 4.0 | 0.0196 | 0.3133 | 未分出 | 0.3133 | 未分出 | 否 |
| Claude Code 同强度 | 27 Claude Code Strata IQ3_XXS high | 21 Claude Code haiku high | 5 / 5 | -0.260 | 0.067 | 4.2 | 0.0164 | 0.2789 | 未分出 | 0.2789 | 未分出 | 否 |
| Claude Code 同强度 | 27 Claude Code Strata IQ3_XXS high | 23 Claude Code deepseek-flash high | 5 / 8 | -0.141 | 0.073 | 5.7 | 0.1052 | 1.0000 | 未分出 | 0.9469 | 未分出 | 否 |
| Codex 对 Claude Code | 10 Codex Strata IQ3_XXS low | 25 Claude Code Strata IQ3_XXS low | 5 / 5 | -0.026 | 0.105 | 5.7 | 0.8108 | 1.0000 | 未分出 | 1.0000 | 未分出 | 否 |
| Codex 对 Claude Code | 11 Codex Strata IQ3_XXS medium | 26 Claude Code Strata IQ3_XXS medium | 5 / 5 | 0.131 | 0.076 | 6.1 | 0.1339 | 1.0000 | 未分出 | 1.0000 | 未分出 | 否 |
| Codex 对 Claude Code | 12 Codex Strata IQ3_XXS high | 27 Claude Code Strata IQ3_XXS high | 5 / 5 | 0.060 | 0.077 | 6.5 | 0.4672 | 1.0000 | 未分出 | 1.0000 | 未分出 | 否 |
| Codex 对 Claude Code | 7 Codex deepseek-flash low | 22 Claude Code deepseek-flash low | 5 / 5 | 0.003 | 0.048 | 8.0 | 0.9580 | 1.0000 | 未分出 | 1.0000 | 未分出 | 否 |
| Codex 对 Claude Code | 8 Codex deepseek-flash high | 23 Claude Code deepseek-flash high | 8 / 8 | -0.096 | 0.083 | 9.1 | 0.2756 | 1.0000 | 未分出 | 1.0000 | 未分出 | 否 |
| Codex 对 Claude Code | 9 Codex deepseek-flash max | 24 Claude Code deepseek-flash max | 5 / 5 | -0.073 | 0.088 | 4.8 | 0.4460 | 1.0000 | 未分出 | 1.0000 | 未分出 | 否 |

### Spec Readiness v4.3（SR）

#### 配置

| 配置 | 行 | 有效 | n | 无效 | 均值 ± SD | SE | 95% 区间 | 负分数 | 最小 | 中位数 | r8.3 均值 | rawScore | f | 修复 | 耗时（分钟） | 占时限 | 未缓存 | 缓存 | 输出 | token 来源 | 工具调用 | 引擎输入 tok/s | 引擎输出 tok/s | 任务平均输入 tok/s | 任务平均输出 tok/s | 费用均值（美元；DeepSeek 括号内人民币） | 周额度 | 模型 ID | service tier |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 Codex gpt-6.1-sol low | 主统计 | 5 | 5 | 0 | 0.817 ± 0.034 | 0.015 | 0.775 – 0.859 | 0 | 0.765 | 0.832 | 0.817 | 0.817 | 0.000 | 0 | 5.0 | 无时限 | 145,885 | 1,481,344 | 9,256 | API usage (relay) | 24.8 | 未知 | ≥32.5 | 510.1 | 32.0 | 只报 token |  | gpt-6.1-sol | default |
| 2 Codex gpt-6.1-sol medium | 主统计 | 5 | 5 | 1 | 0.784 ± 0.070 | 0.031 | 0.698 – 0.871 | 0 | 0.679 | 0.811 | 0.784 | 0.784 | 0.000 | 0 | 6.1 | 无时限 | 154,450 | 1,744,896 | 11,778 | API usage (relay) | 28.4 | 未知 | ≥33.1 | 437.7 | 32.8 | 只报 token |  | gpt-6.1-sol | default |
| 3 Codex gpt-6.1-sol high | 主统计 | 5 | 5 | 1 | 0.803 ± 0.067 | 0.030 | 0.720 – 0.886 | 0 | 0.702 | 0.821 | 0.803 | 0.803 | 0.000 | 0 | 10.6 | 无时限 | 172,083 | 2,751,232 | 20,536 | API usage (relay) | 39.8 | 未知 | ≥33.2 | 283.5 | 32.9 | 只报 token |  | gpt-6.1-sol | default |
| 4 Codex gpt-6-luna low | 主统计 | 5 | 5 | 1 | 0.143 ± 0.101 | 0.045 | 0.018 – 0.269 | 0 | 0.020 | 0.125 | 0.143 | 0.143 | 0.000 | 0 | 3.0 | 无时限 | 159,322 | 1,677,670 | 10,614 | API usage (relay) | 27.6 | 未知 | ≥59.7 | 879.0 | 59.2 | 只报 token |  | gpt-6-luna | default |
| 5 Codex gpt-6-luna medium | 主统计 | 5 | 5 | 0 | 0.260 ± 0.185 | 0.083 | 0.030 – 0.490 | 0 | 0.102 | 0.229 | 0.260 | 0.260 | 0.000 | 0 | 3.0 | 无时限 | 140,123 | 1,169,178 | 11,228 | API usage (relay) | 21.4 | 未知 | ≥65.4 | 872.9 | 64.0 | 只报 token |  | gpt-6-luna | default |
| 6 Codex gpt-6-luna high | 主统计 | 5 | 5 | 1 | 0.459 ± 0.077 | 0.034 | 0.364 – 0.555 | 0 | 0.375 | 0.447 | 0.459 | 0.459 | 0.000 | 0 | 4.6 | 无时限 | 158,994 | 1,368,346 | 20,331 | API usage (relay) | 24.4 | 未知 | ≥75.5 | 590.5 | 74.7 | 只报 token |  | gpt-6-luna | default |
| 7 Codex deepseek-flash low | 主统计 | 5 | 5 | 2 | 0.691 ± 0.047 | 0.021 | 0.633 – 0.750 | 0 | 0.632 | 0.685 | 0.691 | 0.691 | 0.000 | 0 | 11.1 | 无时限 | 146,361 | 4,136,038 | 108,048 | API usage (relay) | 98.6 | 未知 | ≥179.8 | 223.6 | 165.6 | 0.099（¥0.661） |  | deepseek-flash | default |
| 8 Codex deepseek-flash high | 主统计 | 5 | 5 | 0 | 0.586 ± 0.223 | 0.100 | 0.308 – 0.863 | 0 | 0.192 | 0.659 | 0.586 | 0.590 | 0.000 | 0 | 21.3 | 无时限 | 未知 | 未知 | 未知 | API usage (relay) | 140.6 | 未知 | ≥155.0 | 未知 | 未知 | ≥0.220（¥1.466） |  | deepseek-flash | default、not-returned |
| 9 Codex deepseek-flash max | 主统计 | 5 | 5 | 0 | 0.677 ± 0.058 | 0.026 | 0.605 – 0.749 | 0 | 0.633 | 0.658 | 0.677 | 0.677 | 0.000 | 0 | 12.4 | 无时限 | 159,419 | 4,353,050 | 139,912 | API usage (relay) | 97.6 | 未知 | ≥188.7 | 215.0 | 187.7 | 0.121（¥0.806） |  | deepseek-flash | default、not-returned |
| 10 Codex Strata IQ3_XXS low | 主统计 | 5 | 5 | 0 | 0.490 ± 0.115 | 0.051 | 0.347 – 0.633 | 0 | 0.370 | 0.457 | 0.490 | 0.490 | 0.000 | 0 | 13.2 | 无时限 | 146,287 | 4,170,147 | 56,770 | engine log | 59.8 | 1521.1 | 88.6 | 188.8 | 71.4 | 0.115 |  | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | 主统计 | 5 | 5 | 0 | 0.564 ± 0.065 | 0.029 | 0.483 – 0.645 | 0 | 0.473 | 0.563 | 0.564 | 0.564 | 0.000 | 0 | 13.5 | 无时限 | 146,559 | 3,335,728 | 57,870 | engine log | 53.2 | 1567.8 | 87.0 | 183.9 | 71.1 | 0.103 |  | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | 主统计 | 5 | 5 | 0 | 0.494 ± 0.074 | 0.033 | 0.403 – 0.586 | 0 | 0.373 | 0.513 | 0.494 | 0.494 | 0.000 | 0 | 13.9 | 无时限 | 146,189 | 2,668,437 | 59,813 | engine log | 50.8 | 1652.2 | 86.7 | 177.1 | 71.8 | 0.093 |  | 未知 | 未知 |
| 13 Claude Code opus low | 主统计 | 5 | 5 | 0 | 0.665 ± 0.070 | 0.031 | 0.578 – 0.752 | 0 | 0.564 | 0.654 | 0.665 | 0.665 | 0.000 | 0 | 5.4 | 无时限 | 121,623 | 529,115 | 11,393 | Claude Code stream result usage | 11.6 | 未知 | ≥70.2 | 399.4 | 37.1 | 1.307 | 0.56% | claude-opus-5-5 | standard |
| 14 Claude Code opus medium | 主统计 | 5 | 5 | 0 | 0.772 ± 0.044 | 0.020 | 0.718 – 0.826 | 0 | 0.720 | 0.768 | 0.772 | 0.772 | 0.000 | 0 | 11.2 | 无时限 | 168,137 | 1,133,872 | 31,481 | Claude Code stream result usage | 21.0 | 未知 | ≥73.8 | 255.2 | 47.2 | 2.201 | 0.95% | claude-opus-5-5 | standard |
| 15 Claude Code opus high | 主统计 | 5 | 5 | 0 | 0.812 ± 0.033 | 0.015 | 0.772 – 0.853 | 0 | 0.764 | 0.812 | 0.812 | 0.812 | 0.000 | 0 | 13.1 | 无时限 | 222,030 | 1,610,609 | 51,963 | Claude Code stream result usage | 29.6 | 未知 | ≥87.0 | 291.5 | 67.6 | 3.137 | 1.35% | claude-opus-5-5 | standard |
| 16 Claude Code sonnet low | 主统计 | 5 | 5 | 0 | 0.478 ± 0.044 | 0.020 | 0.422 – 0.533 | 0 | 0.426 | 0.468 | 0.478 | 0.478 | 0.000 | 0 | 3.2 | 无时限 | 132,486 | 583,784 | 13,768 | Claude Code stream result usage | 13.4 | 未知 | ≥100.1 | 728.5 | 71.5 | 0.726 | 0.31% | claude-sonnet-5-5 | standard |
| 17 Claude Code sonnet medium | 主统计 | 5 | 5 | 0 | 0.689 ± 0.175 | 0.078 | 0.472 – 0.906 | 0 | 0.428 | 0.672 | 0.689 | 0.703 | 0.007 | 0 | 15.5 | 无时限 | 174,428 | 8,266,482 | 28,603 | Claude Code stream result usage | 16.8 | 未知 | ≥105.6 | 576.2 | 91.5 | 1.810 | 0.78% | claude-sonnet-5-5 | standard |
| 18 Claude Code sonnet high | 主统计 | 5 | 5 | 0 | 0.795 ± 0.076 | 0.034 | 0.700 – 0.889 | 0 | 0.707 | 0.838 | 0.795 | 0.795 | 0.000 | 0 | 8.4 | 无时限 | 225,989 | 982,542 | 56,719 | Claude Code stream result usage | 28.6 | 未知 | ≥129.9 | 450.6 | 112.3 | 1.569 | 0.67% | claude-sonnet-5-5 | standard |
| 19 Claude Code haiku low | 主统计 | 5 | 5 | 0 | 0.633 ± 0.063 | 0.028 | 0.555 – 0.711 | 0 | 0.542 | 0.639 | 0.633 | 0.633 | 0.000 | 0 | 9.7 | 无时限 | 312,950 | 960,927 | 129,555 | Claude Code stream result usage | 28.4 | 未知 | ≥236.1 | 540.7 | 221.9 | 0.324 | 0.14% | claude-haiku-5-5 | standard |
| 20 Claude Code haiku medium | 主统计 | 5 | 5 | 0 | 0.612 ± 0.140 | 0.063 | 0.438 – 0.786 | 0 | 0.376 | 0.644 | 0.612 | 0.612 | 0.000 | 0 | 11.2 | 无时限 | 331,383 | 1,185,086 | 149,505 | Claude Code stream result usage | 30.0 | 未知 | ≥237.2 | 495.3 | 223.0 | 0.360 | 0.15% | claude-haiku-5-5 | standard |
| 21 Claude Code haiku high | 主统计 | 5 | 5 | 0 | 0.590 ± 0.053 | 0.024 | 0.524 – 0.656 | 0 | 0.518 | 0.585 | 0.590 | 0.590 | 0.000 | 0 | 16.1 | 无时限 | 409,900 | 1,615,586 | 221,977 | Claude Code stream result usage | 31.8 | 未知 | ≥239.7 | 425.8 | 230.3 | 0.608 | 0.26% | claude-haiku-5-5 | standard |
| 22 Claude Code deepseek-flash low | 主统计 | 5 | 5 | 0 | 0.464 ± 0.270 | 0.121 | 0.129 – 0.799 | 0 | 0.171 | 0.591 | 0.464 | 0.464 | 0.000 | 0 | 14.9 | 无时限 | 131,805 | 1,451,034 | 160,413 | Claude Code stream result usage | 33.4 | 未知 | ≥208.3 | 147.9 | 178.7 | 0.120（¥0.802） |  | deepseek-flash | not-returned、standard |
| 23 Claude Code deepseek-flash high | 主统计 | 5 | 5 | 0 | 0.521 ± 0.200 | 0.089 | 0.273 – 0.769 | 0 | 0.172 | 0.565 | 0.521 | 0.521 | 0.000 | 0 | 24.0 | 无时限 | 146,494 | 2,508,902 | 258,314 | Claude Code stream result usage | 44.8 | 未知 | ≥209.3 | 104.6 | 178.5 | 0.184（¥1.230） |  | deepseek-flash | not-returned、standard |
| 24 Claude Code deepseek-flash max | 主统计 | 5 | 5 | 0 | 0.253 ± 0.192 | 0.086 | 0.015 – 0.491 | 0 | 0.160 | 0.174 | 0.253 | 0.253 | 0.000 | 0 | 25.5 | 无时限 | 155,435 | 2,221,133 | 303,668 | Claude Code stream result usage | 41.0 | 未知 | ≥215.4 | 103.0 | 201.1 | 0.212（¥1.415） |  | deepseek-flash | not-returned、standard |
| 25 Claude Code Strata IQ3_XXS low | 主统计 | 5 | 5 | 0 | 0.236 ± 0.110 | 0.049 | 0.099 – 0.373 | 0 | 0.133 | 0.215 | 0.236 | 0.236 | 0.000 | 0 | 9.9 | 无时限 | 148,065 | 2,872,861 | 44,815 | engine log | 42.4 | 1822.9 | 88.5 | 257.3 | 74.5 | 0.089 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 26 Claude Code Strata IQ3_XXS medium | 主统计 | 5 | 5 | 0 | 0.261 ± 0.092 | 0.041 | 0.147 – 0.375 | 0 | 0.156 | 0.270 | 0.261 | 0.261 | 0.000 | 0 | 10.4 | 无时限 | 165,083 | 1,841,376 | 48,486 | engine log | 33.2 | 2081.7 | 88.6 | 275.6 | 76.1 | 0.077 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 27 Claude Code Strata IQ3_XXS high | 主统计 | 5 | 5 | 1 | 0.260 ± 0.089 | 0.040 | 0.150 – 0.371 | 0 | 0.164 | 0.255 | 0.260 | 0.260 | 0.000 | 0 | 13.1 | 无时限 | 146,251 | 1,656,810 | 63,686 | engine log | 32.0 | 2089.0 | 88.2 | 224.7 | 78.2 | 0.078 |  | qwen3.8-flash-next-iq3_xxs | not-returned |

#### 预登记比较（25 个，Holm）

| 组 | Strata / Codex 侧 | 对照 / Claude Code 侧 | n | d | SE | df | p | Holm p | 结论 | r8.3 Holm p | r8.3 结论 | 结论改变 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Codex 同强度 | 10 Codex Strata IQ3_XXS low | 1 Codex gpt-6.1-sol low | 5 / 5 | -0.327 | 0.054 | 4.7 | 0.0022 | 0.0314 | 低于 | 0.0314 | 低于 | 否 |
| Codex 同强度 | 10 Codex Strata IQ3_XXS low | 4 Codex gpt-6-luna low | 5 / 5 | 0.347 | 0.069 | 7.9 | 0.0010 | 0.0163 | 高于 | 0.0163 | 高于 | 否 |
| Codex 同强度 | 10 Codex Strata IQ3_XXS low | 7 Codex deepseek-flash low | 5 / 5 | -0.201 | 0.056 | 5.3 | 0.0138 | 0.1104 | 未分出 | 0.1104 | 未分出 | 否 |
| Codex 同强度 | 11 Codex Strata IQ3_XXS medium | 2 Codex gpt-6.1-sol medium | 5 / 5 | -0.220 | 0.043 | 8.0 | 0.0009 | 0.0146 | 低于 | 0.0146 | 低于 | 否 |
| Codex 同强度 | 11 Codex Strata IQ3_XXS medium | 5 Codex gpt-6-luna medium | 5 / 5 | 0.304 | 0.088 | 5.0 | 0.0183 | 0.1280 | 未分出 | 0.1280 | 未分出 | 否 |
| Codex 同强度 | 12 Codex Strata IQ3_XXS high | 3 Codex gpt-6.1-sol high | 5 / 5 | -0.308 | 0.045 | 7.9 | 0.0001 | 0.0028 | 低于 | 0.0028 | 低于 | 否 |
| Codex 同强度 | 12 Codex Strata IQ3_XXS high | 6 Codex gpt-6-luna high | 5 / 5 | 0.035 | 0.048 | 8.0 | 0.4846 | 1.0000 | 未分出 | 1.0000 | 未分出 | 否 |
| Codex 同强度 | 12 Codex Strata IQ3_XXS high | 8 Codex deepseek-flash high | 5 / 5 | -0.091 | 0.105 | 4.9 | 0.4261 | 1.0000 | 未分出 | 1.0000 | 未分出 | 否 |
| Claude Code 同强度 | 25 Claude Code Strata IQ3_XXS low | 13 Claude Code opus low | 5 / 5 | -0.428 | 0.058 | 6.8 | 0.0002 | 0.0039 | 低于 | 0.0039 | 低于 | 否 |
| Claude Code 同强度 | 25 Claude Code Strata IQ3_XXS low | 16 Claude Code sonnet low | 5 / 5 | -0.241 | 0.053 | 5.3 | 0.0055 | 0.0601 | 未分出 | 0.0601 | 未分出 | 否 |
| Claude Code 同强度 | 25 Claude Code Strata IQ3_XXS low | 19 Claude Code haiku low | 5 / 5 | -0.397 | 0.057 | 6.3 | 0.0003 | 0.0064 | 低于 | 0.0064 | 低于 | 否 |
| Claude Code 同强度 | 25 Claude Code Strata IQ3_XXS low | 22 Claude Code deepseek-flash low | 5 / 5 | -0.228 | 0.130 | 5.3 | 0.1373 | 0.6659 | 未分出 | 0.6659 | 未分出 | 否 |
| Claude Code 同强度 | 26 Claude Code Strata IQ3_XXS medium | 14 Claude Code opus medium | 5 / 5 | -0.511 | 0.045 | 5.7 | 4.1e-05 | 0.0010 | 低于 | 0.0010 | 低于 | 否 |
| Claude Code 同强度 | 26 Claude Code Strata IQ3_XXS medium | 17 Claude Code sonnet medium | 5 / 5 | -0.428 | 0.088 | 6.0 | 0.0028 | 0.0338 | 低于 | 0.0338 | 低于 | 否 |
| Claude Code 同强度 | 26 Claude Code Strata IQ3_XXS medium | 20 Claude Code haiku medium | 5 / 5 | -0.351 | 0.075 | 6.9 | 0.0023 | 0.0314 | 低于 | 0.0314 | 低于 | 否 |
| Claude Code 同强度 | 27 Claude Code Strata IQ3_XXS high | 15 Claude Code opus high | 5 / 5 | -0.552 | 0.042 | 5.1 | 4.4e-05 | 0.0010 | 低于 | 0.0010 | 低于 | 否 |
| Claude Code 同强度 | 27 Claude Code Strata IQ3_XXS high | 18 Claude Code sonnet high | 5 / 5 | -0.535 | 0.052 | 7.8 | 8.6e-06 | 0.0002 | 低于 | 0.0002 | 低于 | 否 |
| Claude Code 同强度 | 27 Claude Code Strata IQ3_XXS high | 21 Claude Code haiku high | 5 / 5 | -0.330 | 0.046 | 6.5 | 0.0003 | 0.0052 | 低于 | 0.0052 | 低于 | 否 |
| Claude Code 同强度 | 27 Claude Code Strata IQ3_XXS high | 23 Claude Code deepseek-flash high | 5 / 5 | -0.261 | 0.098 | 5.5 | 0.0402 | 0.2413 | 未分出 | 0.2413 | 未分出 | 否 |
| Codex 对 Claude Code | 10 Codex Strata IQ3_XXS low | 25 Claude Code Strata IQ3_XXS low | 5 / 5 | 0.254 | 0.071 | 8.0 | 0.0074 | 0.0665 | 未分出 | 0.0665 | 未分出 | 否 |
| Codex 对 Claude Code | 11 Codex Strata IQ3_XXS medium | 26 Claude Code Strata IQ3_XXS medium | 5 / 5 | 0.303 | 0.050 | 7.2 | 0.0005 | 0.0086 | 高于 | 0.0086 | 高于 | 否 |
| Codex 对 Claude Code | 12 Codex Strata IQ3_XXS high | 27 Claude Code Strata IQ3_XXS high | 5 / 5 | 0.234 | 0.052 | 7.7 | 0.0021 | 0.0314 | 高于 | 0.0314 | 高于 | 否 |
| Codex 对 Claude Code | 7 Codex deepseek-flash low | 22 Claude Code deepseek-flash low | 5 / 5 | 0.227 | 0.123 | 4.2 | 0.1332 | 0.6659 | 未分出 | 0.6659 | 未分出 | 否 |
| Codex 对 Claude Code | 8 Codex deepseek-flash high | 23 Claude Code deepseek-flash high | 5 / 5 | 0.065 | 0.134 | 7.9 | 0.6408 | 1.0000 | 未分出 | 1.0000 | 未分出 | 否 |
| Codex 对 Claude Code | 9 Codex deepseek-flash max | 24 Claude Code deepseek-flash max | 5 / 5 | 0.424 | 0.090 | 4.7 | 0.0060 | 0.0601 | 未分出 | 0.0601 | 未分出 | 否 |

## 敏感性

### r8.3 对照

r8.3（分数截到 [0, 1]）与 r8.4 只在负分实例上不同。100 个预登记比较中只有 1 个结论改变：


| 场景 | Strata 侧 | 对照 | r8.3 Holm p | r8.3 结论 | r8.4 Holm p | r8.4 结论 |
|---|---|---|---|---|---|---|
| commit-audit-v3 | 11 Codex Strata IQ3_XXS medium | 5 Codex gpt-6-luna medium | 0.0139 | 高于 | 0.2423 | 未分出 |

原因是 gpt-6-luna medium 在 CA 有 3 个负分实例（r8.3 下都记 0），r8.4 下这一格的 SD 变大。全部负分实例：


| 场景 | 实例 | 最终分 | rawScore | f | 修复 |
|---|---|---|---|---|---|
| commit-audit-v3 | openai/commit-audit-v3/luna-low-a1 | -1.155 | -0.498 | 0.000 | 0 |
| commit-audit-v3 | openai/commit-audit-v3/luna-low-a3 | -0.568 | -0.245 | 0.000 | 0 |
| commit-audit-v3 | openai/commit-audit-v3/luna-low-a5 | -1.567 | -0.676 | 0.000 | 0 |
| commit-audit-v3 | openai/commit-audit-v3/luna-low-a6 | -0.862 | -0.371 | 0.000 | 0 |
| commit-audit-v3 | openai/commit-audit-v3/luna-low-a7 | -1.074 | -0.421 | 0.100 | 16 |
| commit-audit-v3 | openai/commit-audit-v3/luna-medium-a2 | -0.228 | -0.098 | 0.000 | 0 |
| commit-audit-v3 | openai/commit-audit-v3/luna-medium-a6 | -0.441 | -0.190 | 0.000 | 0 |
| commit-audit-v3 | openai/commit-audit-v3/luna-medium-a7 | -0.861 | -0.371 | 0.000 | 0 |
| commit-audit-v3 | openai/commit-audit-v3/luna-high-a5 | -0.932 | -0.402 | 0.000 | 0 |

luna-low-a7 的 f = 0.1 来自 16 处修复（「CA 要求行号整体错位」改挂，每行计 1 处格式错误）。正分实例的 r8.3 与 r8.4 分数逐位相同（计分 worker 自查）。

### A1、A2 与缺口上下界

A1（CS `governing-spec.md:160` 空白目录键归 `en`，相关 finding 判 supported）和 A2（CA "returns an error result" 须带 `error` 字段的读法，min / full 两版）是歧义清单 A1、A2 的另一种读法。A1、A2 用补裁后的正式决定库改写同样的 finding 重算（变体分数见 `sens-final/`；变体只动 CS 和 CA 的其他实例，不涉及行号修复的两个实例，其余实例取行号修复后的 `root-final`，汇总为 `summary-A1-final2` 等），基准是正式汇总 `summary-final`；缺口上下界两行仍以补裁前的 `summary-pre-gap` 为基准，`summary`（缺口补裁后、行号修复前）一行以 `summary-pre-gap` 为基准。下表列出各变体的结论分布和相对基准改变结论的比较（未计分完的比较不算改变）：


| 变体 | 数据基准 | 完整 | 低于 | 高于 | 未分出 | 未计分完 | 相对基准改变结论的比较 |
|---|---|---|---|---|---|---|---|
| 补裁缺口前的正式口径 | — | 否 | 21 | 10 | 60 | 9 | 无 |
| A1：CS governing-spec.md:160 判 supported（行号修复后数据） | summary-final | 是 | 21 | 10 | 69 | 0 | 无 |
| A2（min）：CA "error result" 须带 error 字段（行号修复后数据） | summary-final | 是 | 21 | 10 | 69 | 0 | 无 |
| A2（full）（行号修复后数据） | summary-final | 是 | 21 | 10 | 69 | 0 | 无 |
| 缺口下界（9 个待裁实例按暂定下界） | summary-pre-gap | 是 | 21 | 10 | 69 | 0 | 无 |
| 缺口上界 | summary-pre-gap | 是 | 21 | 10 | 69 | 0 | 无 |
| 缺口补裁后、CA 第 2 关行号修复前 | summary-pre-gap | 是 | 21 | 10 | 69 | 0 | 无 |
| 正式（CA 第 2 关行号修复、现行 master 全量重算） | summary | 是 | 21 | 10 | 69 | 0 | 无 |


| 场景 | 比较（配置号） | 下界 Holm p | 正式 Holm p | 上界 Holm p | 正式结论 |
|---|---|---|---|---|---|
| code-spec-v5 | 9 对 24 | 0.4806 | 0.4806 | 0.4806 | 未分出 |
| code-standards-v5.1 | 25 对 22 | 0.9614 | 0.2453 | 0.2453 | 未分出 |
| code-standards-v5.1 | 7 对 22 | 1.0000 | 0.6288 | 0.6288 | 未分出 |
| spec-readiness-v4.3 | 12 对 8 | 1.0000 | 1.0000 | 1.0000 | 未分出 |
| spec-readiness-v4.3 | 25 对 22 | 1.0000 | 0.6659 | 0.6689 | 未分出 |
| spec-readiness-v4.3 | 27 对 23 | 0.9948 | 0.2413 | 0.2626 | 未分出 |
| spec-readiness-v4.3 | 7 对 22 | 0.8728 | 0.6659 | 0.6689 | 未分出 |
| spec-readiness-v4.3 | 8 对 23 | 1.0000 | 1.0000 | 1.0000 | 未分出 |
| spec-readiness-v4.3 | 9 对 24 | 0.0813 | 0.0601 | 0.0601 | 未分出 |

- 以下 Holm p 是行号修复前的数（行号修复只改 CA DeepSeek codex high 格的两个比较的未校正 p，Holm p 都仍是 1，其余 p 不变）。用补裁后数据重算，A1、A2（min、full）在全部 100 个比较上都不改结论。A1 动了 15 条 finding（歧义清单 A1 写的是 13 条，以实际 15 条为准），涉及 sol 三档和 DeepSeek codex-high-a1，每个受影响实例的分数都升 0.0125；CS 的 Strata codex 对 sol 三档仍是低于（Holm p 0.0019→0.0020、0.0003→0.0003、<0.0001），其余 p 不变到 4 位小数。A2 min 只动 luna-high-a10（0.096→0.104），它不在主统计，p 不变；A2 full 另动 strata-low-a4（0.254→0.271），CA Claude Code 上 Strata low 对 Opus、Sonnet、Haiku low 的 Holm p 由 0.626、0.693、0.480 降到 0.595、0.663、0.453，仍是未分出。
- 这些变体分数与补裁前算的逐位相同；区别只在基准数据（9 个缺口实例已补裁）。
- 缺口上下界：9 个当时待裁实例按暂定下界和上界计分，9 个比较在两端都是未分出；SR 的 DeepSeek max harness 比较（9 对 24）Holm p 在 0.0601–0.0813 之间，离线最近。补裁后（缺口补裁 2 池，锚点 24/24、合成项全对）9 个比较的正式结论与上下界两端相同，都是未分出；Holm p 不随单个实例的分数单调变化，正式 p 不一定落在两端之间（如 SR 27 对 23）。

### N1：CA 第 2 关行号错位（已按用户决定处理）

DeepSeek CA codex-medium-a1（第 2 关 7 行）和 codex-medium-a3（2 行）把第 2 关的要求行号整体标错。用户 10-22 定：行号错位修复按行号的作用划分，只改标识用的行号（CA 两关的 `source.line`），证据定位不改挂，不分关、不分场景（rulings、reviewer-suite 规则「评分」；实现合并于 e46006d）。改挂后要重裁的候选按常规盲裁（池 shift-ca：实例候选 13 个，即 7 个待裁候选加 medium-a1 第 2 关 6 个内容变了的 finding 候选；锚点 12/12、合成项 18/18，$0.63），不按指纹沿用旧决定；medium-a3 原 Main override（false-positive:clean-9）和 medium-a1 两条 override（clean-10、clean-13）被新的盲裁决定取代（历史保留）。

结果：medium-a1 0.095 → 0.223（rawScore 0.248，7 处修复，格式罚 f = 0.1）；medium-a3 0.7339 → 0.7338（rawScore 0.780，2 处修复，f = 0.060，两者几乎抵消）。两者都在 DeepSeek codex high 合并格（CA 配置 8），格均值 0.629 → 0.645（一致性行 0.552 → 0.577）。受影响的两个比较（Codex 同强度 12 对 8、harness 8 对 23）未校正 p 由 0.757、0.270 变为 0.862、0.276，Holm p 都仍是 1，结论不变（未分出）。实际分高于此前估算的读法 B 区间（medium-a1 0.110–0.156、medium-a3 0.690–0.731）。

### CStd p基准

CStd 的格式罚基准 p基准按 Haiku-high ×5 的登记为 Σr / ΣT = 18 / 224 = 0.0803571。用现行 master 的修复器和计分器（613066e 起修复器删除首个条目之后的列 0 非条目行）对存档的 5 份基准报告重算：把每份报告放进一个 CStd benchmark 记录的位置完整计分，r 与 T 逐份和登记相同（7/41、0/44、1/54、0/37、10/48，rUnrepairable、rOverrun 都是 0），Σr / ΣT 仍是 18 / 224 = 0.0803571。5 份报告都没有条目外行，修复只有 `short-evidence-path`。这只是敏感性核对，不改登记。

## 偏离与已知问题

- **看过暂定分之后定下的口径**：逐条列在 plan §14.1 末尾的 2026-10-22 汇总表（决定者、日期、影响的 family）。其中 Main 定的有：条目外行由修复器删除（只影响 DeepSeek-CC CStd cc-low-a4）、9 个模型失误登记（都在 DeepSeek）、spill 只取被引用的落盘文件，以及几条先由 Main 暂行、后经用户确认的先例。
- **会话检查（D9）**：557 个实例全部由 Haiku（medium）按固定清单逐实例审阅（读过滤并打码后的 actions.md、flagged.md），567 次调用约 $5.31；结论 valid 525、诊断分 10、可疑 21、无效 1。可疑与无效的 22 个及覆盖不全的 10 个共 32 个由 Main 按完整命令复核：没有实例接触到隐藏答案、评分材料、其他实例结果或凭据，全部保留。唯一判无效的 deepseek-codex SR codex-high-a4 三次出根搜索自己的草稿，一次参数错误未执行、两次被 guardian 拒绝，按「被沙箱拦下的只记录」改为有效（该实例 AP 本已登记为模型失误，分数不受影响）。诊断分共 12 个（Haiku 判的 10 个，加 2 个由可疑改为保留、但有 TZ 查询的），按环境查询的字面口径记（多为 `echo $TMPDIR`、TZ 查询，输出只有本实例路径或时区名）。
  - 诊断分实例（环境查询次数）：`anthropic/code-spec-v5/haiku-high-a3`（1 次）；`anthropic/commit-audit-v3/opus-high-a2`（1 次）；`anthropic/commit-audit-v3/opus-high-a5`（1 次）；`anthropic/commit-audit-v3/sonnet-high-a1`（1 次）；`deepseek-claude/code-spec-v5/cc-low-a3`（1 次）；`deepseek-claude/commit-audit-v3/cc-max-a5`（1 次）；`deepseek-claude/commit-audit-v3/cc-medium-a4`（1 次）；`strata-claude/commit-audit-v3/strata-high-a1`（1 次）；`strata-claude/commit-audit-v3/strata-low-a2`（2 次）；`strata-claude/commit-audit-v3/strata-medium-a2`（1 次）；`strata-codex/commit-audit-v3/codex-strata-low-a6`（1 次）；`strata-codex/spec-readiness-v4.3/codex-strata-high-a3`（1 次）。
- **审查 C**：CA 第 2 关行号错位（N1）与"机制写对、结果方向写反"（N2，ds-ca-4-149）这两类情形，裁决先例表都没有覆盖。N1 已由用户 10-22 决定并处理（见上文 N1 一节）；N2 维持 supported。
- **审查 G**：strata-codex CA low-a1、low-a2 的 preparation 无法验证。两个实例照常计分并进主统计（0.557、0.544）。
- **审查 H**：已处理，CStd p基准按现行修复器重算后不变（见上一节）。
- **审查 I**：DeepSeek 桥接批复核摘要写"不同意 11"，明细合计为 10，以明细为准；审查另指出 SR 漏检得负分的激励不对称，原文未展开，列为下一版评分要看的问题。
- **审查 A、B**（计分前阻塞项）：已修。正式根里 ds-ca-15-098/100/116 曾改为可选值内的 false-positive（行号修复后这三个候选已由 shift-ca 盲裁重新决定，见 N1 一节），luna-high-a10 的 ca-2-143 维持 supported、ca-1-150 按 A2 主读法判 supported，决定都注明"审查 A/B 修正 10-22"；override 从 613066e 起校验可选值。
- **审查 F**：10 个 upstream-failed 实例已处理：9 个空报告登记为模型失误（`model-failures.json`，失误的子场景按什么都不报计；SR 的 8 个经缺口补裁 RM 候选后定分，CS cc-max-a4 为 0），CStd cc-low-a4 由新修复器修复后补裁。
- **速度与工具调用数**：已补进 summary.json（bench_records 原来不算速度、Claude Code 和 Strata-Codex 的工具调用数记为空）。第一阶段 557 个实例中缺数据的：deepseek-codex SR codex-high-a4（60 分钟硬时限、无 token，用户感知速度未知）、deepseek-claude CS cc-max-a4（无 result 事件，token 和两项速度未知）、anthropic CS haiku-low-a8（末段被硬时限杀掉无 result，API 时间未知，所以引擎输出未知；token 和用户感知速度是下限）。API 模型的引擎输入一律未知。gpt-6.1-sol / gpt-6-luna 的引擎输出（按 relay 请求时间）与任务平均输出几乎相同，7 个实例略低于任务平均输出（差不到 5%）：relay 计时从请求到达 relay 算起，比 ARW 的工作计时起点早。
- **Claude Code 的 `duration_api_ms` 跨 `--resume` 累计**：与 `total_cost_usd` 一样，接续段的值是会话累计（如 anthropic CS haiku-low-a7 共 46 段）。`claude_headless.stream_summary` 原来逐段相加，已改为单调不减时取末值；它此前只用于诊断，不影响分数和 token。
- **Claude Code 遇 model_error 不接续**：DeepSeek-CC SR 的 7 个 AP 子场景撞 32000 输出上限后停为 model_error，没有接续。这一处理已由 plan §14.1 2026-10-20 F4 条（用户决定）预登记：按已写出的内容计分，作 ARW 的 incomplete，不接续。不是待定问题。
- **A1 条数**：歧义清单 A1 写 13 条，敏感性实际改了 15 条。

## 逐实例表

summary.json 里的全部实例，含无效、没进主统计的和第二阶段加测（加测实例"计分"一栏为 unscored）。"计分"为 final 的才有分数。四项速度的口径见「每场景结果」开头；"≥"是下限，"未知"是缺数据。

### Code Spec v5（CS）

| 配置 | 实例 | 有效 | 进主统计 | 计分 | 分数 | rawScore | f | 修复 | 耗时（分钟） | 时限（秒） | 未缓存 | 缓存 | 输出 | token 来源 | 工具调用 | 费用（美元；括号内人民币） | 引擎输入 tok/s | 引擎输出 tok/s | 任务平均输入 tok/s | 任务平均输出 tok/s | 模型 ID | tier |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 Codex gpt-6.1-sol low | sol-low-a1 | 否：no-record | 否 | — | 未知 | 未知 | 未知 |  | 未知 | 无 | 未知 | 未知 | 未知 | 未知 | 未知 | 只报 token | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 |
| 1 Codex gpt-6.1-sol low | sol-low-a2 | 是 | 是 | final | 0.852 | 0.852 | 0.000 | 0 | 2.6 | 1456 | 115,551 | 1,292,288 | 7,016 | API usage (relay) | 17 | 只报 token | 未知 | ≥46.0 | 752.6 | 45.7 | gpt-6.1-sol | default 18 |
| 1 Codex gpt-6.1-sol low | sol-low-a3 | 是 | 是 | final | 0.872 | 0.872 | 0.000 | 0 | 1.6 | 1456 | 99,162 | 819,584 | 5,127 | API usage (relay) | 12 | 只报 token | 未知 | ≥52.5 | 1004.6 | 51.9 | gpt-6.1-sol | default 13 |
| 1 Codex gpt-6.1-sol low | sol-low-a4 | 是 | 是 | final | 0.868 | 0.868 | 0.000 | 0 | 1.9 | 1456 | 100,557 | 735,872 | 5,242 | API usage (relay) | 11 | 只报 token | 未知 | ≥46.8 | 887.9 | 46.3 | gpt-6.1-sol | default 12 |
| 1 Codex gpt-6.1-sol low | sol-low-a5 | 是 | 是 | final | 0.850 | 0.850 | 0.000 | 0 | 2.4 | 1456 | 133,893 | 1,212,544 | 7,121 | API usage (relay) | 15 | 只报 token | 未知 | ≥50.6 | 947.8 | 50.4 | gpt-6.1-sol | default 16 |
| 1 Codex gpt-6.1-sol low | sol-low-a6 | 是 | 是 | final | 0.848 | 0.848 | 0.000 | 0 | 2.8 | 1456 | 122,610 | 1,259,008 | 8,021 | API usage (relay) | 17 | 只报 token | 未知 | ≥47.1 | 721.3 | 47.2 | gpt-6.1-sol | default 18 |
| 2 Codex gpt-6.1-sol medium | sol-medium-a1 | 是 | 是 | final | 0.842 | 0.842 | 0.000 | 0 | 2.7 | 1351 | 103,785 | 869,504 | 8,188 | API usage (relay) | 13 | 只报 token | 未知 | ≥50.1 | 634.3 | 50.0 | gpt-6.1-sol | default 14 |
| 2 Codex gpt-6.1-sol medium | sol-medium-a2 | 是 | 是 | final | 0.832 | 0.832 | 0.000 | 0 | 2.1 | 1351 | 103,843 | 872,448 | 5,850 | API usage (relay) | 12 | 只报 token | 未知 | ≥46.2 | 808.2 | 45.5 | gpt-6.1-sol | default 13 |
| 2 Codex gpt-6.1-sol medium | sol-medium-a3 | 是 | 是 | final | 0.827 | 0.827 | 0.000 | 0 | 2.9 | 1351 | 125,710 | 1,044,864 | 7,920 | API usage (relay) | 15 | 只报 token | 未知 | ≥46.1 | 725.6 | 45.7 | gpt-6.1-sol | default 16 |
| 2 Codex gpt-6.1-sol medium | sol-medium-a4 | 是 | 是 | final | 0.832 | 0.832 | 0.000 | 0 | 3.1 | 1351 | 117,827 | 1,576,320 | 8,961 | API usage (relay) | 20 | 只报 token | 未知 | ≥48.0 | 628.7 | 47.8 | gpt-6.1-sol | default 21 |
| 2 Codex gpt-6.1-sol medium | sol-medium-a5 | 是 | 是 | final | 0.826 | 0.826 | 0.000 | 0 | 3.1 | 1351 | 109,975 | 918,912 | 9,138 | API usage (relay) | 14 | 只报 token | 未知 | ≥49.9 | 599.2 | 49.8 | gpt-6.1-sol | default 15 |
| 3 Codex gpt-6.1-sol high | sol-high-a1 | 是 | 是 | final | 0.858 | 0.858 | 0.000 | 0 | 5.0 | 1409 | 119,187 | 1,195,264 | 15,105 | API usage (relay) | 16 | 只报 token | 未知 | ≥50.9 | 399.7 | 50.7 | gpt-6.1-sol | default 17 |
| 3 Codex gpt-6.1-sol high | sol-high-a2 | 是 | 是 | final | 0.834 | 0.834 | 0.000 | 0 | 5.5 | 1409 | 127,798 | 1,666,816 | 15,635 | API usage (relay) | 19 | 只报 token | 未知 | ≥47.4 | 386.5 | 47.3 | gpt-6.1-sol | default 20 |
| 3 Codex gpt-6.1-sol high | sol-high-a3 | 是 | 是 | final | 0.809 | 0.809 | 0.000 | 0 | 4.2 | 1409 | 120,580 | 1,243,008 | 12,495 | API usage (relay) | 15 | 只报 token | 未知 | ≥49.8 | 476.8 | 49.4 | gpt-6.1-sol | default 16 |
| 3 Codex gpt-6.1-sol high | sol-high-a4 | 是 | 是 | final | 0.825 | 0.825 | 0.000 | 0 | 5.0 | 1409 | 110,267 | 1,154,432 | 15,064 | API usage (relay) | 15 | 只报 token | 未知 | ≥50.2 | 366.6 | 50.1 | gpt-6.1-sol | default 16 |
| 3 Codex gpt-6.1-sol high | sol-high-a5 | 是 | 是 | final | 0.802 | 0.802 | 0.000 | 0 | 4.3 | 1409 | 112,932 | 1,246,464 | 12,860 | API usage (relay) | 16 | 只报 token | 未知 | ≥49.7 | 434.5 | 49.5 | gpt-6.1-sol | default 17 |
| 4 Codex gpt-6-luna low | luna-low-a1 | 是 | 是 | final | 0.037 | 0.037 | 0.000 | 0 | 0.9 | 657 | 90,579 | 1,096,832 | 3,546 | API usage (relay) | 17 | 只报 token | 未知 | ≥67.8 | 1667.4 | 65.3 | gpt-6-luna | default 18 |
| 4 Codex gpt-6-luna low | luna-low-a2 | 是 | 是 | final | 0.068 | 0.068 | 0.000 | 0 | 1.4 | 657 | 126,264 | 2,193,536 | 6,454 | API usage (relay) | 23 | 只报 token | 未知 | ≥79.7 | 1532.8 | 78.3 | gpt-6-luna | default 24 |
| 4 Codex gpt-6-luna low | luna-low-a3 | 是 | 是 | final | 0.023 | 0.023 | 0.000 | 0 | 0.6 | 657 | 54,941 | 424,320 | 2,448 | API usage (relay) | 10 | 只报 token | 未知 | ≥72.1 | 1566.2 | 69.8 | gpt-6-luna | default 11 |
| 4 Codex gpt-6-luna low | luna-low-a4 | 是 | 是 | final | 0.021 | 0.021 | 0.000 | 0 | 0.6 | 657 | 68,995 | 576,768 | 2,374 | API usage (relay) | 11 | 只报 token | 未知 | ≥66.2 | 1898.5 | 65.3 | gpt-6-luna | default 12 |
| 4 Codex gpt-6-luna low | luna-low-a5 | 是 | 是 | final | 0.079 | 0.079 | 0.000 | 0 | 0.7 | 657 | 60,640 | 332,416 | 2,542 | API usage (relay) | 8 | 只报 token | 未知 | ≥68.9 | 1490.0 | 62.5 | gpt-6-luna | default 9 |
| 5 Codex gpt-6-luna medium | luna-medium-a1 | 是 | 是 | final | 0.172 | 0.172 | 0.000 | 0 | 0.8 | 594 | 65,906 | 565,632 | 3,566 | API usage (relay) | 11 | 只报 token | 未知 | ≥79.6 | 1400.9 | 75.8 | gpt-6-luna | default 12 |
| 5 Codex gpt-6-luna medium | luna-medium-a2 | 是 | 是 | final | 0.012 | 0.012 | 0.000 | 0 | 0.7 | 594 | 96,059 | 871,040 | 3,208 | API usage (relay) | 14 | 只报 token | 未知 | ≥72.7 | 2145.2 | 71.6 | gpt-6-luna | default 15 |
| 5 Codex gpt-6-luna medium | luna-medium-a3 | 是 | 是 | final | 0.254 | 0.254 | 0.000 | 0 | 1.0 | 594 | 73,597 | 638,720 | 4,558 | API usage (relay) | 13 | 只报 token | 未知 | ≥77.3 | 1228.6 | 76.1 | gpt-6-luna | default 14 |
| 5 Codex gpt-6-luna medium | luna-medium-a4 | 是 | 是 | final | 0.500 | 0.500 | 0.000 | 0 | 2.0 | 594 | 100,654 | 1,727,744 | 9,676 | API usage (relay) | 24 | 只报 token | 未知 | ≥81.1 | 840.8 | 80.8 | gpt-6-luna | default 25 |
| 5 Codex gpt-6-luna medium | luna-medium-a5 | 是 | 是 | final | 0.251 | 0.251 | 0.000 | 0 | 1.5 | 594 | 99,149 | 1,173,376 | 6,856 | API usage (relay) | 17 | 只报 token | 未知 | ≥76.9 | 1104.8 | 76.4 | gpt-6-luna | default 18 |
| 6 Codex gpt-6-luna high | luna-high-a1 | 是 | 是 | final | 0.700 | 0.700 | 0.000 | 0 | 2.4 | 612 | 114,779 | 1,137,024 | 15,397 | API usage (relay) | 16 | 只报 token | 未知 | ≥106.0 | 784.9 | 105.3 | gpt-6-luna | default 17 |
| 6 Codex gpt-6-luna high | luna-high-a2 | 是 | 是 | final | 0.361 | 0.361 | 0.000 | 0 | 1.0 | 612 | 112,746 | 545,920 | 5,646 | API usage (relay) | 10 | 只报 token | 未知 | ≥94.4 | 1858.2 | 93.1 | gpt-6-luna | default 11 |
| 6 Codex gpt-6-luna high | luna-high-a3 | 是 | 是 | final | 0.482 | 0.482 | 0.000 | 0 | 2.2 | 612 | 103,333 | 1,773,952 | 10,446 | API usage (relay) | 27 | 只报 token | 未知 | ≥80.7 | 798.3 | 80.7 | gpt-6-luna | default 28 |
| 6 Codex gpt-6-luna high | luna-high-a4 | 是 | 是 | final | 0.512 | 0.512 | 0.000 | 0 | 2.3 | 612 | 111,778 | 1,309,568 | 13,625 | API usage (relay) | 17 | 只报 token | 未知 | ≥100.6 | 824.1 | 100.4 | gpt-6-luna | default 18 |
| 6 Codex gpt-6-luna high | luna-high-a5 | 是 | 是 | final | 0.528 | 0.528 | 0.000 | 0 | 1.1 | 612 | 96,674 | 520,960 | 6,044 | API usage (relay) | 9 | 只报 token | 未知 | ≥92.3 | 1469.1 | 91.8 | gpt-6-luna | default 10 |
| 7 Codex deepseek-flash low | codex-low-a1 | 是 | 是 | final | 0.566 | 0.566 | 0.000 | 0 | 2.9 | 329 | 94,750 | 1,091,968 | 25,866 | API usage (relay) | 22 | ≥0.033（¥0.220） | 未知 | ≥160.5 | 549.1 | 149.9 | deepseek-flash | default 12、not-returned 1 |
| 7 Codex deepseek-flash low | codex-low-a2 | 是 | 是 | final | 0.519 | 0.519 | 0.000 | 0 | 3.1 | 329 | 89,624 | 1,277,824 | 27,897 | API usage (relay) | 35 | ≥0.034（¥0.227） | 未知 | ≥162.2 | 488.2 | 152.0 | deepseek-flash | default 15、not-returned 1 |
| 7 Codex deepseek-flash low | codex-low-a3 | 是 | 是 | final | 0.627 | 0.627 | 0.000 | 0 | 2.8 | 329 | 81,919 | 670,976 | 28,353 | API usage (relay) | 26 | ≥0.031（¥0.209） | 未知 | ≥178.4 | 482.3 | 166.9 | deepseek-flash | default 9、not-returned 1 |
| 7 Codex deepseek-flash low | codex-low-a4 | 是 | 是 | final | 0.468 | 0.468 | 0.000 | 0 | 2.1 | 329 | 79,136 | 649,600 | 21,387 | API usage (relay) | 22 | 0.027（¥0.178） | 未知 | ≥175.1 | 643.1 | 173.8 | deepseek-flash | default 10 |
| 7 Codex deepseek-flash low | codex-low-a5 | 是 | 是 | final | 0.474 | 0.474 | 0.000 | 0 | 2.8 | 329 | 87,048 | 1,478,784 | 28,407 | API usage (relay) | 32 | ≥0.035（¥0.230） | 未知 | ≥170.7 | 516.0 | 168.4 | deepseek-flash | default 17、not-returned 1 |
| 8 Codex deepseek-flash high | codex-high-a1 | 是 | 是 | final | 0.533 | 0.533 | 0.000 | 0 | 3.6 | 409 | 89,213 | 1,397,376 | 32,965 | API usage (relay) | 34 | ≥0.037（¥0.249） | 未知 | ≥162.7 | 416.9 | 154.0 | deepseek-flash | default 15、not-returned 1 |
| 8 Codex deepseek-flash high | codex-high-a2 | 是 | 是 | final | 0.530 | 0.530 | 0.000 | 0 | 3.5 | 409 | 76,981 | 1,591,552 | 33,221 | API usage (relay) | 31 | 0.036（¥0.242） | 未知 | ≥161.9 | 370.7 | 160.0 | deepseek-flash | default 19 |
| 8 Codex deepseek-flash high | codex-high-a3 | 是 | 是 | final | 0.431 | 0.431 | 0.000 | 0 | 2.5 | 409 | 88,583 | 780,800 | 27,571 | API usage (relay) | 34 | 0.032（¥0.214） | 未知 | ≥187.2 | 599.2 | 186.5 | deepseek-flash | default 12 |
| 8 Codex deepseek-flash high | codex-high-a4 | 是 | 是 | final | 0.457 | 0.457 | 0.000 | 0 | 3.2 | 409 | 89,439 | 1,017,984 | 32,512 | API usage (relay) | 27 | 0.036（¥0.240） | 未知 | ≥168.2 | 460.6 | 167.4 | deepseek-flash | default 12 |
| 8 Codex deepseek-flash high | codex-high-a5 | 是 | 是 | final | 0.705 | 0.705 | 0.000 | 0 | 3.6 | 409 | 86,689 | 1,754,368 | 38,377 | API usage (relay) | 50 | ≥0.041（¥0.275） | 未知 | ≥189.0 | 404.8 | 179.2 | deepseek-flash | default 17、not-returned 1 |
| 8 Codex deepseek-flash high | codex-medium-a1（补充行） | 是 | 是 | final | 0.245 | 0.245 | 0.000 | 0 | 1.0 | 344 | 58,470 | 339,840 | 9,045 | API usage (relay) | 14 | 0.015（¥0.101） | 未知 | ≥153.6 | 993.3 | 153.7 | deepseek-flash | default 7 |
| 8 Codex deepseek-flash high | codex-medium-a2（补充行） | 是 | 是 | final | 0.650 | 0.650 | 0.000 | 0 | 3.3 | 344 | 83,692 | 1,371,520 | 34,568 | API usage (relay) | 26 | ≥0.037（¥0.249） | 未知 | ≥178.7 | 423.4 | 174.9 | deepseek-flash | default 15、not-returned 1 |
| 8 Codex deepseek-flash high | codex-medium-a3（补充行） | 是 | 是 | final | 0.559 | 0.559 | 0.000 | 0 | 2.6 | 344 | 84,048 | 908,032 | 26,173 | API usage (relay) | 22 | 0.031（¥0.207） | 未知 | ≥166.1 | 531.1 | 165.4 | deepseek-flash | default 11 |
| 8 Codex deepseek-flash high | codex-medium-a4（补充行） | 是 | 是 | final | 0.624 | 0.648 | 0.038 | 1 | 3.0 | 344 | 90,803 | 2,172,032 | 29,644 | API usage (relay) | 47 | ≥0.038（¥0.253） | 未知 | ≥174.3 | 501.4 | 163.7 | deepseek-flash | default 23、not-returned 1 |
| 8 Codex deepseek-flash high | codex-medium-a5（补充行） | 是 | 是 | final | 0.532 | 0.532 | 0.000 | 0 | 1.5 | 344 | 81,908 | 787,200 | 15,393 | API usage (relay) | 26 | 0.024（¥0.159） | 未知 | ≥169.6 | 891.1 | 167.5 | deepseek-flash | default 11 |
| 9 Codex deepseek-flash max | codex-max-a1 | 是 | 是 | final | 0.577 | 0.577 | 0.000 | 0 | 3.5 | 406 | 94,322 | 894,592 | 36,826 | API usage (relay) | 40 | ≥0.039（¥0.260） | 未知 | ≥210.8 | 443.5 | 173.2 | deepseek-flash | default 11、not-returned 1 |
| 9 Codex deepseek-flash max | codex-max-a2 | 是 | 是 | final | 0.557 | 0.557 | 0.000 | 0 | 2.5 | 406 | 90,744 | 1,228,544 | 29,362 | API usage (relay) | 37 | 0.035（¥0.233） | 未知 | ≥196.9 | 603.4 | 195.2 | deepseek-flash | default 14 |
| 9 Codex deepseek-flash max | codex-max-a3 | 是 | 是 | final | 0.638 | 0.638 | 0.000 | 0 | 3.6 | 406 | 89,894 | 1,771,776 | 40,346 | API usage (relay) | 43 | ≥0.043（¥0.287） | 未知 | ≥193.4 | 421.9 | 189.4 | deepseek-flash | default 19、not-returned 1 |
| 9 Codex deepseek-flash max | codex-max-a4 | 是 | 是 | final | 0.608 | 0.608 | 0.000 | 0 | 3.7 | 406 | 91,583 | 2,279,424 | 40,378 | API usage (relay) | 45 | ≥0.045（¥0.299） | 未知 | ≥187.0 | 407.4 | 179.6 | deepseek-flash | default 22、not-returned 1 |
| 9 Codex deepseek-flash max | codex-max-a5 | 是 | 是 | final | 0.625 | 0.625 | 0.000 | 0 | 3.7 | 406 | 98,254 | 1,576,960 | 38,972 | API usage (relay) | 30 | ≥0.043（¥0.286） | 未知 | ≥189.7 | 443.6 | 175.9 | deepseek-flash | default 16、not-returned 1 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a1 | 是 | 是 | final | 0.448 | 0.448 | 0.000 | 0 | 8.9 | 920 | 93,732 | 2,872,972 | 37,642 | engine log | 30 | 未知 | 1613.5 | 86.0 | 174.7 | 70.2 | 未知 | 未知 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a2 | 是 | 是 | final | 0.414 | 0.414 | 0.000 | 0 | 8.0 | 920 | 88,605 | 2,037,573 | 34,488 | engine log | 29 | 未知 | 1623.3 | 89.2 | 184.2 | 71.7 | 未知 | 未知 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a3 | 是 | 是 | final | 0.511 | 0.511 | 0.000 | 0 | 9.4 | 920 | 96,301 | 2,647,217 | 39,928 | engine log | 33 | 未知 | 1597.8 | 86.5 | 171.3 | 71.0 | 未知 | 未知 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a4 | 是 | 是 | final | 0.503 | 0.503 | 0.000 | 0 | 9.1 | 920 | 116,004 | 1,765,987 | 36,948 | engine log | 26 | 未知 | 1846.1 | 83.4 | 212.7 | 67.8 | 未知 | 未知 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a5 | 是 | 是 | final | 0.361 | 0.361 | 0.000 | 0 | 7.6 | 920 | 81,742 | 1,762,317 | 32,556 | engine log | 20 | 未知 | 1720.1 | 87.5 | 178.2 | 71.0 | 未知 | 未知 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a6 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 8.9 | 920 | 94,905 | 2,790,252 | 35,524 | engine log | 31 | 未知 | 1630.8 | 82.4 | 177.8 | 66.6 | 未知 | 未知 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a7 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 6.6 | 920 | 80,736 | 1,393,901 | 26,390 | engine log | 23 | 未知 | 1780.4 | 85.4 | 203.4 | 66.5 | 未知 | 未知 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a8 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 8.8 | 920 | 83,528 | 1,935,582 | 37,495 | engine log | 31 | 未知 | 1755.7 | 85.6 | 158.1 | 71.0 | 未知 | 未知 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a9 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 11.6 | 920 | 296,055 | 2,963,558 | 45,797 | engine log | 26 | 未知 | 2109.5 | 89.0 | 423.9 | 65.6 | 未知 | 未知 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a10 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 8.5 | 920 | 88,595 | 2,057,790 | 36,142 | engine log | 27 | 未知 | 1680.6 | 87.5 | 173.8 | 70.9 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a1 | 是 | 是 | final | 0.520 | 0.520 | 0.000 | 0 | 7.8 | 908 | 80,883 | 1,310,953 | 33,450 | engine log | 21 | 未知 | 1841.1 | 86.4 | 172.2 | 71.2 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a2 | 是 | 是 | final | 0.537 | 0.537 | 0.000 | 0 | 7.9 | 908 | 78,037 | 1,047,036 | 33,137 | engine log | 26 | 未知 | 1898.7 | 84.4 | 165.5 | 70.3 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a3 | 是 | 是 | final | 0.467 | 0.475 | 0.018 | 1 | 7.1 | 908 | 80,111 | 1,081,959 | 29,435 | engine log | 18 | 未知 | 1899.6 | 85.4 | 188.4 | 69.2 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a4 | 是 | 是 | final | 0.478 | 0.486 | 0.016 | 1 | 9.6 | 908 | 85,371 | 1,768,668 | 43,601 | engine log | 29 | 未知 | 1736.2 | 89.0 | 147.5 | 75.3 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a5 | 是 | 是 | final | 0.461 | 0.475 | 0.029 | 1 | 9.4 | 908 | 96,842 | 1,547,426 | 41,149 | engine log | 26 | 未知 | 1796.8 | 87.7 | 172.2 | 73.2 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a6 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 7.8 | 908 | 79,605 | 1,759,142 | 31,999 | engine log | 26 | 未知 | 1614.0 | 85.7 | 171.0 | 68.7 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a7 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 7.8 | 908 | 88,110 | 1,522,165 | 31,322 | engine log | 21 | 未知 | 1888.2 | 83.1 | 188.7 | 67.1 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a8 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 8.4 | 908 | 90,008 | 1,380,687 | 35,235 | engine log | 26 | 未知 | 1959.5 | 85.4 | 179.6 | 70.3 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a9 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 8.1 | 908 | 91,170 | 1,682,175 | 33,088 | engine log | 25 | 未知 | 1739.6 | 84.9 | 188.1 | 68.3 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a10 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 7.7 | 908 | 79,475 | 1,755,287 | 31,109 | engine log | 20 | 未知 | 1836.5 | 82.8 | 171.8 | 67.3 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a1 | 是 | 是 | final | 0.485 | 0.485 | 0.000 | 0 | 8.8 | 916 | 91,051 | 1,216,246 | 37,947 | engine log | 23 | 未知 | 1928.6 | 85.2 | 171.6 | 71.5 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a2 | 是 | 是 | final | 0.466 | 0.466 | 0.000 | 0 | 9.5 | 916 | 75,519 | 1,734,608 | 40,020 | engine log | 44 | 未知 | 1507.1 | 83.5 | 132.7 | 70.3 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a3 | 是 | 是 | final | 0.509 | 0.509 | 0.000 | 0 | 10.1 | 916 | 82,767 | 1,896,331 | 44,474 | engine log | 27 | 未知 | 1674.0 | 86.3 | 137.1 | 73.7 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a4 | 是 | 是 | final | 0.469 | 0.469 | 0.000 | 0 | 8.7 | 916 | 82,293 | 1,973,814 | 36,738 | engine log | 37 | 未知 | 1537.2 | 85.9 | 158.2 | 70.6 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a5 | 是 | 是 | final | 0.532 | 0.532 | 0.000 | 0 | 10.6 | 916 | 78,266 | 1,818,831 | 48,491 | engine log | 36 | 未知 | 1614.1 | 88.4 | 123.2 | 76.3 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a6 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 8.6 | 916 | 83,844 | 1,501,224 | 37,234 | engine log | 29 | 未知 | 1847.9 | 86.7 | 162.3 | 72.1 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a7 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 8.3 | 916 | 82,158 | 1,086,661 | 35,909 | engine log | 20 | 未知 | 1977.0 | 86.7 | 165.2 | 72.2 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a8 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 9.0 | 916 | 82,799 | 1,106,734 | 39,085 | engine log | 18 | 未知 | 2015.4 | 85.9 | 153.8 | 72.6 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a9 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 10.1 | 916 | 78,427 | 2,218,027 | 45,379 | engine log | 32 | 未知 | 1494.6 | 89.1 | 129.6 | 75.0 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a10 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 9.4 | 916 | 75,650 | 1,290,942 | 40,868 | engine log | 26 | 未知 | 1727.9 | 85.9 | 134.5 | 72.7 | 未知 | 未知 |
| 13 Claude Code opus low | opus-low-a1 | 是 | 是 | final | 0.598 | 0.598 | 0.000 | 0 | 4.4 | 1202 | 98,190 | 716,682 | 6,688 | Claude Code stream result usage | 12 | 1.063 | 未知 | ≥66.8 | 372.5 | 25.4 | claude-opus-5-5 | standard 13 |
| 13 Claude Code opus low | opus-low-a2 | 是 | 是 | final | 0.542 | 0.569 | 0.047 | 0 | 1.7 | 1202 | 96,068 | 666,181 | 6,820 | Claude Code stream result usage | 13 | 1.038 | 未知 | ≥82.2 | 947.0 | 67.2 | claude-opus-5-5 | standard 13 |
| 13 Claude Code opus low | opus-low-a3 | 是 | 是 | final | 0.517 | 0.557 | 0.073 | 0 | 2.0 | 1202 | 96,040 | 615,842 | 6,776 | Claude Code stream result usage | 11 | 1.027 | 未知 | ≥73.1 | 787.8 | 55.6 | claude-opus-5-5 | standard 12 |
| 13 Claude Code opus low | opus-low-a4 | 是 | 是 | final | 0.772 | 0.772 | 0.000 | 0 | 2.3 | 1202 | 98,373 | 645,615 | 8,180 | Claude Code stream result usage | 11 | 1.080 | 未知 | ≥95.0 | 715.5 | 59.5 | claude-opus-5-5 | standard 12 |
| 13 Claude Code opus low | opus-low-a5 | 是 | 是 | final | 0.651 | 0.651 | 0.000 | 0 | 5.4 | 1202 | 96,439 | 935,116 | 7,240 | Claude Code stream result usage | 15 | 1.103 | 未知 | ≥51.9 | 295.8 | 22.2 | claude-opus-5-5 | standard 16 |
| 14 Claude Code opus medium | opus-medium-a1 | 是 | 是 | final | 0.731 | 0.731 | 0.000 | 0 | 2.1 | 1132 | 101,604 | 634,852 | 10,491 | Claude Code stream result usage | 10 | 1.150 | 未知 | ≥92.4 | 825.3 | 85.2 | claude-opus-5-5 | standard 11 |
| 14 Claude Code opus medium | opus-medium-a2 | 是 | 是 | final | 0.779 | 0.779 | 0.000 | 0 | 3.8 | 1132 | 109,116 | 1,294,016 | 9,859 | Claude Code stream result usage | 20 | 1.329 | 未知 | ≥81.5 | 478.1 | 43.2 | claude-opus-5-5 | standard 20 |
| 14 Claude Code opus medium | opus-medium-a3 | 是 | 是 | final | 0.647 | 0.647 | 0.000 | 0 | 3.2 | 1132 | 104,098 | 1,079,177 | 10,796 | Claude Code stream result usage | 18 | 1.264 | 未知 | ≥92.4 | 542.6 | 56.3 | claude-opus-5-5 | standard 17 |
| 14 Claude Code opus medium | opus-medium-a4 | 是 | 是 | final | 0.640 | 0.640 | 0.000 | 0 | 2.7 | 1132 | 100,051 | 792,307 | 8,806 | Claude Code stream result usage | 14 | 1.135 | 未知 | ≥89.4 | 623.8 | 54.9 | claude-opus-5-5 | standard 14 |
| 14 Claude Code opus medium | opus-medium-a5 | 是 | 是 | final | 0.696 | 0.696 | 0.000 | 0 | 4.8 | 1132 | 102,690 | 889,775 | 10,498 | Claude Code stream result usage | 14 | 1.209 | 未知 | ≥87.2 | 355.2 | 36.3 | claude-opus-5-5 | standard 15 |
| 15 Claude Code opus high | opus-high-a1 | 是 | 是 | final | 0.819 | 0.819 | 0.000 | 0 | 2.9 | 1188 | 110,108 | 751,287 | 14,363 | Claude Code stream result usage | 14 | 1.318 | 未知 | ≥97.5 | 622.2 | 81.2 | claude-opus-5-5 | standard 13 |
| 15 Claude Code opus high | opus-high-a2 | 是 | 是 | final | 0.702 | 0.702 | 0.000 | 0 | 4.9 | 1188 | 104,340 | 1,032,435 | 12,710 | Claude Code stream result usage | 17 | 1.295 | 未知 | ≥82.7 | 355.5 | 43.3 | claude-opus-5-5 | standard 16 |
| 15 Claude Code opus high | opus-high-a3 | 是 | 是 | final | 0.722 | 0.743 | 0.029 | 1 | 5.6 | 1188 | 106,183 | 822,399 | 12,982 | Claude Code stream result usage | 13 | 1.273 | 未知 | ≥76.9 | 316.4 | 38.7 | claude-opus-5-5 | standard 13 |
| 15 Claude Code opus high | opus-high-a4 | 是 | 是 | final | 0.821 | 0.821 | 0.000 | 0 | 2.9 | 1188 | 107,202 | 1,233,340 | 13,148 | Claude Code stream result usage | 19 | 1.367 | 未知 | ≥90.1 | 607.4 | 74.5 | claude-opus-5-5 | standard 19 |
| 15 Claude Code opus high | opus-high-a5 | 是 | 是 | final | 0.734 | 0.734 | 0.000 | 0 | 6.6 | 1188 | 104,416 | 1,236,542 | 12,066 | Claude Code stream result usage | 17 | 1.324 | 未知 | ≥89.8 | 265.5 | 30.7 | claude-opus-5-5 | standard 18 |
| 16 Claude Code sonnet low | sonnet-low-a1 | 是 | 是 | final | 0.409 | 0.444 | 0.079 | 0 | 3.1 | 990 | 94,210 | 527,995 | 9,608 | Claude Code stream result usage | 9 | 0.526 | 未知 | ≥91.3 | 514.2 | 52.4 | claude-sonnet-5-5 | standard 10 |
| 16 Claude Code sonnet low | sonnet-low-a2 | 是 | 是 | final | 0.554 | 0.582 | 0.048 | 0 | 2.9 | 990 | 91,225 | 622,167 | 9,585 | Claude Code stream result usage | 11 | 0.523 | 未知 | ≥98.9 | 531.9 | 55.9 | claude-sonnet-5-5 | standard 12 |
| 16 Claude Code sonnet low | sonnet-low-a3 | 是 | 是 | final | 0.453 | 0.486 | 0.068 | 0 | 3.5 | 990 | 98,320 | 481,175 | 11,017 | Claude Code stream result usage | 10 | 0.552 | 未知 | ≥109.2 | 463.6 | 51.9 | claude-sonnet-5-5 | standard 10 |
| 16 Claude Code sonnet low | sonnet-low-a4 | 是 | 是 | final | 0.512 | 0.569 | 0.100 | 0 | 1.8 | 990 | 90,510 | 640,415 | 10,162 | Claude Code stream result usage | 12 | 0.528 | 未知 | ≥101.1 | 834.0 | 93.6 | claude-sonnet-5-5 | standard 13 |
| 16 Claude Code sonnet low | sonnet-low-a5 | 是 | 是 | final | 0.363 | 0.392 | 0.075 | 0 | 3.4 | 990 | 88,069 | 519,482 | 8,594 | Claude Code stream result usage | 10 | 0.490 | 未知 | ≥91.7 | 426.7 | 41.6 | claude-sonnet-5-5 | standard 11 |
| 17 Claude Code sonnet medium | sonnet-medium-a1 | 是 | 是 | final | 0.544 | 0.595 | 0.084 | 0 | 4.1 | 911 | 97,676 | 614,481 | 14,594 | Claude Code stream result usage | 12 | 0.598 | 未知 | ≥102.0 | 399.3 | 59.7 | claude-sonnet-5-5 | standard 11 |
| 17 Claude Code sonnet medium | sonnet-medium-a2 | 是 | 是 | final | 0.483 | 0.483 | 0.000 | 0 | 2.9 | 911 | 92,803 | 460,091 | 10,760 | Claude Code stream result usage | 9 | 0.525 | 未知 | ≥106.2 | 530.8 | 61.5 | claude-sonnet-5-5 | standard 9 |
| 17 Claude Code sonnet medium | sonnet-medium-a3 | 是 | 是 | final | 0.647 | 0.647 | 0.000 | 0 | 5.5 | 911 | 102,633 | 855,571 | 13,067 | Claude Code stream result usage | 15 | 0.627 | 未知 | ≥98.3 | 313.5 | 39.9 | claude-sonnet-5-5 | standard 15 |
| 17 Claude Code sonnet medium | sonnet-medium-a4 | 是 | 是 | final | 0.698 | 0.716 | 0.025 | 0 | 1.7 | 911 | 96,405 | 462,073 | 12,548 | Claude Code stream result usage | 9 | 0.557 | 未知 | ≥128.3 | 930.3 | 121.1 | claude-sonnet-5-5 | standard 9 |
| 17 Claude Code sonnet medium | sonnet-medium-a5 | 是 | 是 | final | 0.503 | 0.528 | 0.048 | 0 | 3.6 | 911 | 94,517 | 548,572 | 13,297 | Claude Code stream result usage | 12 | 0.566 | 未知 | ≥93.7 | 436.7 | 61.4 | claude-sonnet-5-5 | standard 11 |
| 18 Claude Code sonnet high | sonnet-high-a1 | 是 | 是 | final | 0.521 | 0.563 | 0.075 | 0 | 4.2 | 976 | 101,714 | 632,723 | 17,807 | Claude Code stream result usage | 13 | 0.648 | 未知 | ≥112.0 | 399.1 | 69.9 | claude-sonnet-5-5 | standard 11 |
| 18 Claude Code sonnet high | sonnet-high-a2 | 是 | 是 | final | 0.546 | 0.595 | 0.082 | 1 | 5.1 | 976 | 108,051 | 746,816 | 20,085 | Claude Code stream result usage | 13 | 0.708 | 未知 | ≥112.0 | 353.2 | 65.7 | claude-sonnet-5-5 | standard 12 |
| 18 Claude Code sonnet high | sonnet-high-a3 | 是 | 是 | final | 0.524 | 0.583 | 0.100 | 0 | 5.7 | 976 | 108,350 | 613,981 | 22,024 | Claude Code stream result usage | 12 | 0.715 | 未知 | ≥120.9 | 316.2 | 64.3 | claude-sonnet-5-5 | standard 11 |
| 18 Claude Code sonnet high | sonnet-high-a4 | 是 | 是 | final | 0.608 | 0.608 | 0.000 | 0 | 2.7 | 976 | 102,937 | 686,564 | 20,797 | Claude Code stream result usage | 14 | 0.688 | 未知 | ≥135.9 | 638.8 | 129.1 | claude-sonnet-5-5 | standard 13 |
| 18 Claude Code sonnet high | sonnet-high-a5 | 是 | 是 | final | 0.725 | 0.725 | 0.000 | 0 | 4.5 | 976 | 114,063 | 902,173 | 20,504 | Claude Code stream result usage | 14 | 0.751 | 未知 | ≥113.9 | 426.1 | 76.6 | claude-sonnet-5-5 | standard 14 |
| 19 Claude Code haiku low | haiku-low-a1 | 是 | 是 | final | 0.150 | 0.150 | 0.000 | 0 | 1.3 | 546 | 54,835 | 314,769 | 6,185 | Claude Code stream result usage | 8 | 0.017 | 未知 | ≥141.7 | 684.4 | 77.2 | claude-haiku-5-5 | standard 8 |
| 19 Claude Code haiku low | haiku-low-a2 | 否：void | 否 | — | 未知 | 未知 | 未知 |  | 3.6 | 546 | 57,834 | 469,997 | 7,619 | Claude Code stream result usage | 11 | 0.020 | 未知 | ≥105.8 | 271.5 | 35.8 | claude-haiku-5-5 | standard 11 |
| 19 Claude Code haiku low | haiku-low-a3 | 是 | 是 | final | 0.246 | 0.246 | 0.000 | 0 | 3.4 | 546 | 71,988 | 431,169 | 9,375 | Claude Code stream result usage | 10 | 0.023 | 未知 | ≥183.6 | 354.8 | 46.2 | claude-haiku-5-5 | standard 9 |
| 19 Claude Code haiku low | haiku-low-a4 | 否：void | 否 | — | 未知 | 未知 | 未知 |  | 1.4 | 546 | 53,925 | 400,589 | 8,281 | Claude Code stream result usage | 10 | 0.019 | 未知 | ≥176.3 | 629.6 | 96.7 | claude-haiku-5-5 | standard 10 |
| 19 Claude Code haiku low | haiku-low-a5 | 否：void | 否 | — | 未知 | 未知 | 未知 |  | 3.3 | 546 | 69,023 | 712,631 | 12,577 | Claude Code stream result usage | 13 | 0.027 | 未知 | ≥163.1 | 352.6 | 64.3 | claude-haiku-5-5 | standard 14 |
| 19 Claude Code haiku low | haiku-low-a6 | 是 | 是 | final | 0.129 | 0.129 | 0.000 | 0 | 0.9 | 544 | 49,415 | 494,295 | 7,208 | Claude Code stream result usage | 11 | 0.018 | 未知 | ≥157.2 | 934.3 | 136.3 | claude-haiku-5-5 | standard 12 |
| 19 Claude Code haiku low | haiku-low-a7 | 是 | 是 | final | 0.384 | 0.426 | 0.000 | 0 | 9.1 | 544 | 258,204 | 11,172,693 | 38,486 | Claude Code stream result usage | 38 | 0.741 | 未知 | ≥100.2 | 473.9 | 70.6 | claude-haiku-5-5 | standard 78 |
| 19 Claude Code haiku low | haiku-low-a8 | 是 | 是 | final | 0.420 | 0.466 | 0.054 | 0 | 9.1 | 544 | 121,664 | 7,926,878 | 37,803 | Claude Code stream result usage (lower bound: a segment without result) | 40 | 未知 | 未知 | 未知 | ≥223.2 | ≥69.3 | claude-haiku-5-5 | standard 85 |
| 20 Claude Code haiku medium | haiku-medium-a1 | 否：void | 否 | — | 未知 | 未知 | 未知 |  | 1.0 | 540 | 50,542 | 302,552 | 8,157 | Claude Code stream result usage | 9 | 0.017 | 未知 | ≥154.1 | 840.6 | 135.7 | claude-haiku-5-5 | standard 8 |
| 20 Claude Code haiku medium | haiku-medium-a2 | 否：void | 否 | — | 未知 | 未知 | 未知 |  | 3.3 | 540 | 78,392 | 500,255 | 12,392 | Claude Code stream result usage | 10 | 0.027 | 未知 | ≥133.7 | 397.2 | 62.8 | claude-haiku-5-5 | standard 9 |
| 20 Claude Code haiku medium | haiku-medium-a3 | 否：void | 否 | — | 未知 | 未知 | 未知 |  | 4.0 | 540 | 56,643 | 484,580 | 11,291 | Claude Code stream result usage | 11 | 0.022 | 未知 | ≥191.1 | 238.4 | 47.5 | claude-haiku-5-5 | standard 11 |
| 20 Claude Code haiku medium | haiku-medium-a4 | 否：void | 否 | — | 未知 | 未知 | 未知 |  | 3.1 | 540 | 58,311 | 465,763 | 9,976 | Claude Code stream result usage | 12 | 0.021 | 未知 | ≥150.5 | 310.8 | 53.2 | claude-haiku-5-5 | standard 11 |
| 20 Claude Code haiku medium | haiku-medium-a5 | 否：void | 否 | — | 未知 | 未知 | 未知 |  | 3.2 | 540 | 57,200 | 416,834 | 10,464 | Claude Code stream result usage | 12 | 0.021 | 未知 | ≥139.6 | 300.4 | 55.0 | claude-haiku-5-5 | standard 10 |
| 20 Claude Code haiku medium | haiku-medium-a6 | 是 | 是 | final | 0.210 | 0.210 | 0.000 | 0 | 1.3 | 515 | 67,717 | 476,553 | 12,439 | Claude Code stream result usage | 11 | 0.025 | 未知 | ≥171.4 | 846.1 | 155.4 | claude-haiku-5-5 | standard 10 |
| 20 Claude Code haiku medium | haiku-medium-a7 | 是 | 是 | final | 0.287 | 0.287 | 0.000 | 0 | 1.2 | 515 | 65,789 | 472,350 | 11,478 | Claude Code stream result usage | 9 | 0.024 | 未知 | ≥173.1 | 915.7 | 159.8 | claude-haiku-5-5 | standard 10 |
| 20 Claude Code haiku medium | haiku-medium-a8 | 是 | 是 | final | 0.480 | 0.480 | 0.000 | 0 | 2.6 | 515 | 117,863 | 866,360 | 28,385 | Claude Code stream result usage | 13 | 0.110 | 未知 | ≥197.5 | 768.4 | 185.1 | claude-haiku-5-5 | standard 13 |
| 20 Claude Code haiku medium | haiku-medium-a9 | 是 | 是 | final | 0.579 | 0.623 | 0.071 | 1 | 3.3 | 515 | 148,728 | 788,859 | 41,393 | Claude Code stream result usage | 13 | 0.160 | 未知 | ≥216.3 | 757.6 | 210.8 | claude-haiku-5-5 | standard 9 |
| 20 Claude Code haiku medium | haiku-medium-a10 | 是 | 是 | final | 0.511 | 0.511 | 0.000 | 0 | 2.7 | 515 | 115,694 | 1,143,079 | 28,980 | Claude Code stream result usage | 21 | 0.109 | 未知 | ≥184.5 | 709.3 | 177.7 | claude-haiku-5-5 | standard 16 |
| 21 Claude Code haiku high | haiku-high-a1 | 否：void | 否 | — | 未知 | 未知 | 未知 |  | 4.0 | 514 | 98,434 | 1,646,496 | 26,107 | Claude Code stream result usage | 23 | 0.078 | 未知 | ≥173.2 | 415.3 | 110.1 | claude-haiku-5-5 | standard 23 |
| 21 Claude Code haiku high | haiku-high-a2 | 是 | 是 | final | 0.680 | 0.680 | 0.000 | 0 | 3.6 | 514 | 135,072 | 844,167 | 42,132 | Claude Code stream result usage | 17 | 0.144 | 未知 | ≥223.6 | 620.6 | 193.6 | claude-haiku-5-5 | standard 12 |
| 21 Claude Code haiku high | haiku-high-a3 | 是 | 是 | final | 0.537 | 0.537 | 0.000 | 0 | 4.0 | 514 | 136,499 | 753,769 | 31,197 | Claude Code stream result usage | 17 | 0.146 | 未知 | ≥213.7 | 564.2 | 129.0 | claude-haiku-5-5 | standard 11 |
| 21 Claude Code haiku high | haiku-high-a4 | 否：void | 否 | — | 未知 | 未知 | 未知 |  | 3.2 | 514 | 99,639 | 596,970 | 20,831 | Claude Code stream result usage | 13 | 0.057 | 未知 | ≥183.8 | 521.6 | 109.0 | claude-haiku-5-5 | standard 10 |
| 21 Claude Code haiku high | haiku-high-a5 | 是 | 是 | final | 0.445 | 0.445 | 0.000 | 0 | 4.2 | 514 | 137,126 | 928,337 | 29,162 | Claude Code stream result usage | 20 | 0.154 | 未知 | ≥173.0 | 543.2 | 115.5 | claude-haiku-5-5 | standard 11 |
| 21 Claude Code haiku high | haiku-high-a6 | 是 | 是 | final | 0.643 | 0.643 | 0.000 | 0 | 3.6 | 521 | 145,707 | 1,416,307 | 44,023 | Claude Code stream result usage | 22 | 0.225 | 未知 | ≥215.7 | 667.9 | 201.8 | claude-haiku-5-5 | standard 16 |
| 21 Claude Code haiku high | haiku-high-a7 | 是 | 是 | final | 0.579 | 0.579 | 0.000 | 0 | 2.7 | 521 | 138,182 | 1,180,309 | 33,496 | Claude Code stream result usage | 20 | 0.154 | 未知 | ≥214.3 | 839.4 | 203.5 | claude-haiku-5-5 | standard 15 |
| 22 Claude Code deepseek-flash low | cc-low-a1 | 是 | 是 | final | 0.533 | 0.533 | 0.000 | 0 | 3.6 | 409 | 85,980 | 865,664 | 24,463 | Claude Code stream result usage | 16 | 0.030（¥0.201） | 未知 | ≥169.2 | 393.7 | 112.0 | deepseek-flash | standard 15 |
| 22 Claude Code deepseek-flash low | cc-low-a2 | 是 | 是 | final | 0.427 | 0.427 | 0.000 | 0 | 4.2 | 409 | 66,471 | 444,032 | 16,202 | Claude Code stream result usage | 16 | 0.021（¥0.140） | 未知 | ≥122.2 | 263.4 | 64.2 | deepseek-flash | standard 11 |
| 22 Claude Code deepseek-flash low | cc-low-a3 | 是 | 是 | final | 0.423 | 0.423 | 0.000 | 0 | 3.3 | 409 | 74,018 | 375,296 | 17,775 | Claude Code stream result usage | 15 | 0.023（¥0.153） | 未知 | ≥184.0 | 371.9 | 89.3 | deepseek-flash | standard 11 |
| 22 Claude Code deepseek-flash low | cc-low-a4 | 是 | 是 | final | 0.604 | 0.604 | 0.000 | 0 | 4.0 | 409 | 71,409 | 642,176 | 18,590 | Claude Code stream result usage | 14 | 0.024（¥0.159） | 未知 | ≥172.7 | 300.1 | 78.1 | deepseek-flash | standard 13 |
| 22 Claude Code deepseek-flash low | cc-low-a5 | 是 | 是 | final | 0.366 | 0.366 | 0.000 | 0 | 1.2 | 409 | 72,632 | 374,400 | 10,836 | Claude Code stream result usage | 15 | 0.019（¥0.123） | 未知 | ≥163.3 | 1035.1 | 154.4 | deepseek-flash | standard 9 |
| 23 Claude Code deepseek-flash high | cc-high-a1 | 是 | 是 | final | 0.336 | 0.336 | 0.000 | 0 | 4.9 | 342 | 70,481 | 468,352 | 10,458 | Claude Code stream result usage | 20 | 0.018（¥0.122） | 未知 | ≥112.3 | 240.8 | 35.7 | deepseek-flash | standard 12 |
| 23 Claude Code deepseek-flash high | cc-high-a2 | 是 | 是 | final | 0.385 | 0.385 | 0.000 | 0 | 1.6 | 342 | 73,946 | 725,376 | 13,835 | Claude Code stream result usage | 18 | 0.022（¥0.144） | 未知 | ≥161.3 | 761.3 | 142.4 | deepseek-flash | standard 14 |
| 23 Claude Code deepseek-flash high | cc-high-a3 | 是 | 是 | final | 0.420 | 0.420 | 0.000 | 0 | 4.1 | 342 | 76,686 | 523,264 | 20,829 | Claude Code stream result usage | 15 | 0.026（¥0.171） | 未知 | ≥177.4 | 315.1 | 85.6 | deepseek-flash | standard 12 |
| 23 Claude Code deepseek-flash high | cc-high-a4 | 是 | 是 | final | 0.557 | 0.557 | 0.000 | 0 | 3.3 | 342 | 82,746 | 427,648 | 26,259 | Claude Code stream result usage | 12 | 0.029（¥0.196） | 未知 | ≥208.7 | 420.8 | 133.5 | deepseek-flash | standard 11 |
| 23 Claude Code deepseek-flash high | cc-high-a5 | 是 | 是 | final | 0.475 | 0.475 | 0.000 | 0 | 3.6 | 342 | 86,252 | 582,400 | 22,624 | Claude Code stream result usage | 15 | 0.028（¥0.188） | 未知 | ≥188.6 | 399.1 | 104.7 | deepseek-flash | standard 11 |
| 23 Claude Code deepseek-flash high | cc-medium-a1（补充行） | 是 | 是 | final | 0.392 | 0.425 | 0.079 | 0 | 4.3 | 391 | 67,026 | 599,936 | 27,257 | Claude Code stream result usage | 15 | 0.028（¥0.188） | 未知 | ≥194.1 | 259.9 | 105.7 | deepseek-flash | standard 13 |
| 23 Claude Code deepseek-flash high | cc-medium-a2（补充行） | 是 | 是 | final | 0.423 | 0.423 | 0.000 | 0 | 4.9 | 391 | 83,195 | 547,328 | 41,634 | Claude Code stream result usage | 15 | 0.039（¥0.261） | 未知 | ≥180.7 | 281.5 | 140.9 | deepseek-flash | standard 12 |
| 23 Claude Code deepseek-flash high | cc-medium-a3（补充行） | 是 | 是 | final | 0.522 | 0.522 | 0.000 | 0 | 3.4 | 391 | 68,118 | 686,208 | 31,031 | Claude Code stream result usage | 17 | 0.031（¥0.206） | 未知 | ≥191.4 | 336.9 | 153.5 | deepseek-flash | standard 14 |
| 23 Claude Code deepseek-flash high | cc-medium-a4（补充行） | 是 | 是 | final | 0.652 | 0.652 | 0.000 | 0 | 4.8 | 391 | 68,827 | 482,688 | 38,607 | Claude Code stream result usage | 13 | 0.035（¥0.233） | 未知 | ≥190.4 | 238.5 | 133.8 | deepseek-flash | standard 11 |
| 23 Claude Code deepseek-flash high | cc-medium-a5（补充行） | 是 | 是 | final | 0.554 | 0.554 | 0.000 | 0 | 4.5 | 391 | 76,535 | 842,240 | 23,381 | Claude Code stream result usage | 19 | 0.028（¥0.187） | 未知 | ≥168.8 | 282.0 | 86.2 | deepseek-flash | standard 15 |
| 24 Claude Code deepseek-flash max | cc-max-a1 | 是 | 是 | final | 0.338 | 0.338 | 0.000 | 0 | 3.9 | 376 | 67,763 | 445,440 | 19,310 | Claude Code stream result usage | 16 | 0.023（¥0.154） | 未知 | ≥163.0 | 287.2 | 81.8 | deepseek-flash | standard 10 |
| 24 Claude Code deepseek-flash max | cc-max-a2 | 是 | 是 | final | 0.382 | 0.382 | 0.000 | 0 | 3.5 | 376 | 62,577 | 1,098,752 | 25,352 | Claude Code stream result usage | 24 | 0.028（¥0.186） | 未知 | ≥170.0 | 295.9 | 119.9 | deepseek-flash | standard 22 |
| 24 Claude Code deepseek-flash max | cc-max-a3 | 是 | 是 | final | 0.523 | 0.523 | 0.000 | 0 | 4.2 | 376 | 83,089 | 494,464 | 41,543 | Claude Code stream result usage | 12 | 0.039（¥0.259） | 未知 | ≥227.6 | 331.7 | 165.9 | deepseek-flash | standard 9 |
| 24 Claude Code deepseek-flash max | cc-max-a4 | 是 | 是 | final | 0.000 | 0.000 | 0.000 | 0 | 6.3 | 376 | 未知 | 未知 | 未知 | 未知 | 13 | 0.049（¥0.326） | 未知 | 未知 | 未知 | 未知 | deepseek-flash | standard 11 |
| 24 Claude Code deepseek-flash max | cc-max-a5 | 是 | 是 | final | 0.313 | 0.313 | 0.000 | 0 | 4.0 | 376 | 76,642 | 601,856 | 22,311 | Claude Code stream result usage | 20 | 0.027（¥0.178） | 未知 | ≥169.5 | 322.5 | 93.9 | deepseek-flash | standard 13 |
| 24 Claude Code deepseek-flash max | cc-max-a6 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 5.3 | 376 | 56,803 | 528,256 | 11,595 | Claude Code stream result usage | 17 | 0.017（¥0.114） | 未知 | ≥100.6 | 179.8 | 36.7 | deepseek-flash | standard 14 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a1 | 是 | 是 | final | 0.458 | 0.458 | 0.000 | 0 | 7.5 | 867 | 87,106 | 2,302,884 | 33,800 | engine log | 27 | 2.189 | 1614.2 | 89.0 | 193.1 | 74.9 | qwen3.8-flash-next-iq3_xxs | not-returned 26 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a2 | 是 | 是 | final | 0.356 | 0.356 | 0.000 | 0 | 6.4 | 867 | 72,986 | 1,580,239 | 29,006 | engine log | 20 | 1.573 | 1680.3 | 88.5 | 190.8 | 75.8 | qwen3.8-flash-next-iq3_xxs | not-returned 18 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a3 | 是 | 是 | final | 0.433 | 0.433 | 0.000 | 0 | 7.4 | 867 | 87,297 | 1,890,520 | 32,543 | engine log | 26 | 1.979 | 1632.8 | 86.8 | 196.7 | 73.3 | qwen3.8-flash-next-iq3_xxs | not-returned 23 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a4 | 是 | 是 | final | 0.539 | 0.539 | 0.000 | 0 | 11.4 | 867 | 98,844 | 4,585,989 | 51,421 | engine log | 40 | 3.478 | 1475.0 | 87.2 | 144.6 | 75.2 | qwen3.8-flash-next-iq3_xxs | not-returned 38 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a5 | 否：harness-fault | 否 | — | 未知 | 未知 | 未知 |  | 1.6 | 867 | 21,817 | 219,333 | 6,761 | engine log | 12 | 0.377 | 1589.1 | 86.0 | 227.0 | 70.3 | qwen3.8-flash-next-iq3_xxs | not-returned 10 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a6 | 是 | 是 | final | 0.304 | 0.314 | 0.034 | 1 | 6.8 | 867 | 92,646 | 2,118,722 | 30,430 | engine log | 25 | 1.990 | 1779.7 | 87.7 | 228.6 | 75.1 | qwen3.8-flash-next-iq3_xxs | not-returned 23 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a7 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 6.0 | 867 | 85,665 | 1,754,443 | 24,779 | engine log | 26 | 1.566 | 1794.1 | 82.7 | 239.9 | 69.4 | qwen3.8-flash-next-iq3_xxs | not-returned 17 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a8 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 8.0 | 867 | 82,407 | 1,937,606 | 31,426 | engine log | 28 | 1.944 | 1515.6 | 77.3 | 172.7 | 65.9 | qwen3.8-flash-next-iq3_xxs | not-returned 26 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a9 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 6.5 | 867 | 63,557 | 1,463,131 | 26,385 | engine log | 25 | 1.594 | 1413.3 | 78.4 | 162.3 | 67.4 | qwen3.8-flash-next-iq3_xxs | not-returned 23 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a10 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 6.9 | 867 | 87,261 | 1,773,945 | 29,527 | engine log | 27 | 1.884 | 1566.6 | 84.9 | 210.7 | 71.3 | qwen3.8-flash-next-iq3_xxs | not-returned 26 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a11 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 6.4 | 867 | 76,281 | 1,506,759 | 27,613 | engine log | 23 | 1.729 | 1578.5 | 85.7 | 199.0 | 72.0 | qwen3.8-flash-next-iq3_xxs | not-returned 23 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a1 | 是 | 是 | final | 0.479 | 0.479 | 0.000 | 0 | 9.0 | 889 | 76,727 | 1,421,529 | 42,104 | engine log | 20 | 1.963 | 1855.1 | 85.8 | 141.8 | 77.8 | qwen3.8-flash-next-iq3_xxs | not-returned 18 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a2 | 是 | 是 | final | 0.510 | 0.510 | 0.000 | 0 | 9.5 | 889 | 80,961 | 1,916,942 | 43,513 | engine log | 102 | 2.451 | 1552.0 | 85.7 | 142.3 | 76.5 | qwen3.8-flash-next-iq3_xxs | not-returned 29 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a3 | 是 | 是 | final | 0.462 | 0.462 | 0.000 | 0 | 8.8 | 889 | 86,694 | 1,818,019 | 38,425 | engine log | 24 | 2.135 | 1646.6 | 83.3 | 164.2 | 72.8 | qwen3.8-flash-next-iq3_xxs | not-returned 23 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a4 | 是 | 是 | final | 0.563 | 0.563 | 0.000 | 0 | 9.5 | 889 | 93,908 | 1,850,619 | 43,253 | engine log | 108 | 2.373 | 1660.3 | 85.4 | 164.8 | 75.9 | qwen3.8-flash-next-iq3_xxs | not-returned 25 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a5 | 是 | 是 | final | 0.388 | 0.431 | 0.100 | 24 | 7.2 | 889 | 103,278 | 2,124,474 | 31,459 | engine log | 26 | 2.106 | 1755.0 | 86.5 | 238.8 | 72.7 | qwen3.8-flash-next-iq3_xxs | not-returned 22 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a6 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 9.5 | 889 | 94,313 | 1,823,963 | 43,597 | engine log | 21 | 2.170 | 1896.1 | 85.7 | 166.1 | 76.8 | qwen3.8-flash-next-iq3_xxs | not-returned 18 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a7 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 8.8 | 889 | 83,066 | 1,554,482 | 40,510 | engine log | 23 | 2.111 | 1671.8 | 86.6 | 157.2 | 76.6 | qwen3.8-flash-next-iq3_xxs | not-returned 22 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a8 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 8.5 | 889 | 83,283 | 1,782,666 | 38,440 | engine log | 39 | 2.212 | 1616.0 | 86.5 | 163.4 | 75.4 | qwen3.8-flash-next-iq3_xxs | not-returned 27 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a9 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 8.3 | 889 | 74,829 | 1,454,686 | 37,527 | engine log | 97 | 1.970 | 1526.6 | 84.7 | 149.9 | 75.2 | qwen3.8-flash-next-iq3_xxs | not-returned 24 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a10 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 6.8 | 889 | 87,272 | 1,740,850 | 29,745 | engine log | 32 | 1.887 | 1775.6 | 84.6 | 213.6 | 72.8 | qwen3.8-flash-next-iq3_xxs | not-returned 20 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a1 | 是 | 是 | final | 0.493 | 0.509 | 0.031 | 0 | 10.5 | 911 | 74,158 | 1,992,930 | 49,343 | engine log | 34 | 2.546 | 1477.7 | 87.2 | 117.7 | 78.3 | qwen3.8-flash-next-iq3_xxs | not-returned 27 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a2 | 是 | 是 | final | 0.437 | 0.437 | 0.000 | 0 | 10.2 | 911 | 75,942 | 1,410,744 | 45,934 | engine log | 27 | 2.233 | 1732.7 | 83.4 | 124.6 | 75.4 | qwen3.8-flash-next-iq3_xxs | not-returned 22 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a3 | 是 | 是 | final | 0.463 | 0.463 | 0.000 | 0 | 9.0 | 911 | 82,036 | 877,366 | 42,170 | engine log | 16 | 1.748 | 1983.9 | 86.2 | 152.3 | 78.3 | qwen3.8-flash-next-iq3_xxs | not-returned 10 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a4 | 是 | 是 | final | 0.515 | 0.515 | 0.000 | 0 | 11.8 | 911 | 82,794 | 1,791,385 | 52,806 | engine log | 27 | 2.518 | 1791.8 | 81.5 | 116.6 | 74.4 | qwen3.8-flash-next-iq3_xxs | not-returned 22 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a5 | 是 | 是 | final | 0.392 | 0.392 | 0.000 | 0 | 9.2 | 911 | 74,304 | 1,189,234 | 40,907 | engine log | 24 | 1.906 | 1815.0 | 82.3 | 134.8 | 74.2 | qwen3.8-flash-next-iq3_xxs | not-returned 21 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a6 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 9.9 | 911 | 71,468 | 1,509,916 | 44,447 | engine log | 98 | 2.168 | 1495.3 | 81.7 | 119.8 | 74.5 | qwen3.8-flash-next-iq3_xxs | not-returned 24 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a7 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 8.7 | 911 | 62,910 | 976,913 | 40,775 | engine log | 17 | 1.776 | 1856.6 | 84.7 | 120.6 | 78.2 | qwen3.8-flash-next-iq3_xxs | not-returned 15 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a8 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 7.6 | 911 | 92,346 | 1,170,498 | 33,512 | engine log | 29 | 1.885 | 1827.5 | 85.0 | 202.9 | 73.6 | qwen3.8-flash-next-iq3_xxs | not-returned 19 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a9 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 10.4 | 911 | 88,368 | 2,263,666 | 48,091 | engine log | 34 | 2.689 | 1737.4 | 85.4 | 141.4 | 77.0 | qwen3.8-flash-next-iq3_xxs | not-returned 27 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a10 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 11.2 | 911 | 85,295 | 1,042,401 | 53,049 | engine log | 19 | 2.173 | 1978.3 | 85.1 | 127.0 | 79.0 | qwen3.8-flash-next-iq3_xxs | not-returned 14 |

### Code Standards v5.1（CStd）

| 配置 | 实例 | 有效 | 进主统计 | 计分 | 分数 | rawScore | f | 修复 | 耗时（分钟） | 时限（秒） | 未缓存 | 缓存 | 输出 | token 来源 | 工具调用 | 费用（美元；括号内人民币） | 引擎输入 tok/s | 引擎输出 tok/s | 任务平均输入 tok/s | 任务平均输出 tok/s | 模型 ID | tier |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 Codex gpt-6.1-sol low | sol-low-a1 | 是 | 是 | final | 0.783 | 0.783 | 0.000 | 0 | 2.0 | 1416 | 136,805 | 394,368 | 5,725 | API usage (relay) | 9 | 只报 token | 未知 | ≥48.6 | 1160.8 | 48.6 | gpt-6.1-sol | default 10 |
| 1 Codex gpt-6.1-sol low | sol-low-a2 | 是 | 是 | final | 0.759 | 0.759 | 0.000 | 0 | 1.8 | 1416 | 63,846 | 461,824 | 4,860 | API usage (relay) | 9 | 只报 token | 未知 | ≥44.9 | 585.8 | 44.6 | gpt-6.1-sol | default 10 |
| 1 Codex gpt-6.1-sol low | sol-low-a3 | 是 | 是 | final | 0.897 | 0.897 | 0.000 | 0 | 2.5 | 1416 | 80,142 | 643,584 | 6,410 | API usage (relay) | 11 | 只报 token | 未知 | ≥42.2 | 524.2 | 41.9 | gpt-6.1-sol | default 12 |
| 1 Codex gpt-6.1-sol low | sol-low-a4 | 是 | 是 | final | 0.871 | 0.871 | 0.000 | 0 | 3.0 | 1416 | 78,093 | 756,992 | 8,108 | API usage (relay) | 13 | 只报 token | 未知 | ≥44.8 | 429.3 | 44.6 | gpt-6.1-sol | default 14 |
| 1 Codex gpt-6.1-sol low | sol-low-a5 | 是 | 是 | final | 0.917 | 0.917 | 0.000 | 0 | 2.2 | 1416 | 70,407 | 623,872 | 5,706 | API usage (relay) | 11 | 只报 token | 未知 | ≥44.3 | 530.3 | 43.0 | gpt-6.1-sol | default 12 |
| 2 Codex gpt-6.1-sol medium | sol-medium-a1 | 是 | 是 | final | 0.893 | 0.893 | 0.000 | 0 | 2.8 | 1335 | 80,504 | 627,328 | 8,008 | API usage (relay) | 11 | 只报 token | 未知 | ≥48.0 | 480.5 | 47.8 | gpt-6.1-sol | default 12 |
| 2 Codex gpt-6.1-sol medium | sol-medium-a2 | 是 | 是 | final | 0.919 | 0.919 | 0.000 | 0 | 2.8 | 1335 | 72,994 | 761,984 | 7,041 | API usage (relay) | 13 | 只报 token | 未知 | ≥42.7 | 437.1 | 42.2 | gpt-6.1-sol | default 14 |
| 2 Codex gpt-6.1-sol medium | sol-medium-a3 | 是 | 是 | final | 0.841 | 0.841 | 0.000 | 0 | 2.6 | 1335 | 71,835 | 510,976 | 6,825 | API usage (relay) | 9 | 只报 token | 未知 | ≥44.5 | 465.3 | 44.2 | gpt-6.1-sol | default 10 |
| 2 Codex gpt-6.1-sol medium | sol-medium-a4 | 是 | 是 | final | 0.886 | 0.886 | 0.000 | 0 | 2.9 | 1335 | 87,253 | 667,648 | 7,946 | API usage (relay) | 11 | 只报 token | 未知 | ≥45.8 | 499.2 | 45.5 | gpt-6.1-sol | default 12 |
| 2 Codex gpt-6.1-sol medium | sol-medium-a5 | 是 | 是 | final | 0.923 | 0.923 | 0.000 | 0 | 3.4 | 1335 | 79,677 | 790,912 | 8,339 | API usage (relay) | 13 | 只报 token | 未知 | ≥41.9 | 396.1 | 41.5 | gpt-6.1-sol | default 14 |
| 3 Codex gpt-6.1-sol high | sol-high-a1 | 是 | 是 | final | 0.924 | 0.924 | 0.000 | 0 | 5.4 | 1300 | 101,215 | 1,056,512 | 14,484 | API usage (relay) | 16 | 只报 token | 未知 | ≥44.6 | 309.6 | 44.3 | gpt-6.1-sol | default 17 |
| 3 Codex gpt-6.1-sol high | sol-high-a2 | 是 | 是 | final | 0.906 | 0.906 | 0.000 | 0 | 4.8 | 1300 | 96,787 | 1,027,584 | 13,353 | API usage (relay) | 15 | 只报 token | 未知 | ≥47.1 | 339.0 | 46.8 | gpt-6.1-sol | default 16 |
| 3 Codex gpt-6.1-sol high | sol-high-a3 | 是 | 是 | final | 0.909 | 0.909 | 0.000 | 0 | 3.8 | 1300 | 84,789 | 675,456 | 9,911 | API usage (relay) | 11 | 只报 token | 未知 | ≥43.7 | 370.2 | 43.3 | gpt-6.1-sol | default 12 |
| 3 Codex gpt-6.1-sol high | sol-high-a4 | 是 | 是 | final | 0.872 | 0.872 | 0.000 | 0 | 5.0 | 1300 | 133,164 | 701,184 | 13,509 | API usage (relay) | 12 | 只报 token | 未知 | ≥45.5 | 446.9 | 45.3 | gpt-6.1-sol | default 13 |
| 3 Codex gpt-6.1-sol high | sol-high-a5 | 是 | 是 | final | 0.815 | 0.815 | 0.000 | 0 | 4.6 | 1300 | 86,052 | 850,688 | 11,945 | API usage (relay) | 13 | 只报 token | 未知 | ≥43.7 | 310.1 | 43.0 | gpt-6.1-sol | default 14 |
| 4 Codex gpt-6-luna low | luna-low-a1 | 是 | 是 | final | 0.176 | 0.176 | 0.000 | 0 | 0.7 | 582 | 57,222 | 438,272 | 2,667 | API usage (relay) | 10 | 只报 token | 未知 | ≥59.6 | 1272.1 | 59.3 | gpt-6-luna | default 11 |
| 4 Codex gpt-6-luna low | luna-low-a2 | 否：void | 否 | — | 未知 | 未知 | 未知 |  | <0.1 | 582 | 未知 | 未知 | 未知 | 未知 | 0 | 只报 token | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 |
| 4 Codex gpt-6-luna low | luna-low-a3 | 是 | 是 | final | 0.026 | 0.026 | 0.000 | 0 | 0.6 | 582 | 44,905 | 348,672 | 1,995 | API usage (relay) | 9 | 只报 token | 未知 | ≥60.2 | 1312.3 | 58.3 | gpt-6-luna | default 10 |
| 4 Codex gpt-6-luna low | luna-low-a4 | 是 | 是 | final | 0.156 | 0.156 | 0.000 | 0 | 0.6 | 582 | 54,271 | 391,040 | 2,238 | API usage (relay) | 9 | 只报 token | 未知 | ≥68.5 | 1642.5 | 67.7 | gpt-6-luna | default 10 |
| 4 Codex gpt-6-luna low | luna-low-a5 | 是 | 是 | final | 0.257 | 0.257 | 0.000 | 0 | 1.0 | 582 | 59,704 | 523,776 | 3,986 | API usage (relay) | 11 | 只报 token | 未知 | ≥70.9 | 1028.8 | 68.7 | gpt-6-luna | default 12 |
| 4 Codex gpt-6-luna low | luna-low-a6 | 是 | 是 | final | 0.199 | 0.199 | 0.000 | 0 | 0.4 | 582 | 51,907 | 225,536 | 1,728 | API usage (relay) | 6 | 只报 token | 未知 | ≥75.0 | 2184.4 | 72.7 | gpt-6-luna | default 7 |
| 5 Codex gpt-6-luna medium | luna-medium-a1 | 是 | 是 | final | 0.363 | 0.363 | 0.000 | 0 | 0.8 | 575 | 55,161 | 410,752 | 4,116 | API usage (relay) | 10 | 只报 token | 未知 | ≥90.7 | 1189.8 | 88.8 | gpt-6-luna | default 11 |
| 5 Codex gpt-6-luna medium | luna-medium-a2 | 是 | 是 | final | 0.157 | 0.169 | 0.073 | 1 | 0.5 | 575 | 48,794 | 260,352 | 2,248 | API usage (relay) | 7 | 只报 token | 未知 | ≥77.2 | 1642.1 | 75.7 | gpt-6-luna | default 8 |
| 5 Codex gpt-6-luna medium | luna-medium-a3 | 是 | 是 | final | 0.564 | 0.564 | 0.000 | 0 | 1.6 | 575 | 61,086 | 674,176 | 7,302 | API usage (relay) | 13 | 只报 token | 未知 | ≥75.3 | 622.7 | 74.4 | gpt-6-luna | default 14 |
| 5 Codex gpt-6-luna medium | luna-medium-a4 | 是 | 是 | final | 0.434 | 0.434 | 0.000 | 0 | 0.9 | 575 | 47,847 | 385,664 | 4,242 | API usage (relay) | 9 | 只报 token | 未知 | ≥83.8 | 929.2 | 82.4 | gpt-6-luna | default 10 |
| 5 Codex gpt-6-luna medium | luna-medium-a5 | 是 | 是 | final | 0.199 | 0.199 | 0.000 | 0 | 0.5 | 575 | 61,883 | 357,504 | 2,172 | API usage (relay) | 8 | 只报 token | 未知 | ≥68.5 | 1911.0 | 67.1 | gpt-6-luna | default 9 |
| 6 Codex gpt-6-luna high | luna-high-a1 | 是 | 是 | final | 0.463 | 0.463 | 0.000 | 0 | 1.5 | 606 | 62,767 | 508,800 | 9,474 | API usage (relay) | 10 | 只报 token | 未知 | ≥108.7 | 712.8 | 107.6 | gpt-6-luna | default 11 |
| 6 Codex gpt-6-luna high | luna-high-a2 | 是 | 是 | final | 0.506 | 0.506 | 0.000 | 0 | 1.5 | 606 | 51,461 | 269,952 | 8,390 | API usage (relay) | 7 | 只报 token | 未知 | ≥92.6 | 562.4 | 91.7 | gpt-6-luna | default 8 |
| 6 Codex gpt-6-luna high | luna-high-a3 | 是 | 是 | final | 0.549 | 0.549 | 0.000 | 0 | 1.6 | 606 | 61,888 | 417,920 | 8,680 | API usage (relay) | 10 | 只报 token | 未知 | ≥93.4 | 653.5 | 91.6 | gpt-6-luna | default 11 |
| 6 Codex gpt-6-luna high | luna-high-a4 | 是 | 是 | final | 0.499 | 0.499 | 0.000 | 0 | 1.1 | 606 | 62,876 | 282,112 | 5,708 | API usage (relay) | 7 | 只报 token | 未知 | ≥89.9 | 980.1 | 89.0 | gpt-6-luna | default 8 |
| 6 Codex gpt-6-luna high | luna-high-a5 | 是 | 是 | final | 0.346 | 0.346 | 0.000 | 0 | 1.1 | 606 | 45,714 | 412,800 | 4,701 | API usage (relay) | 10 | 只报 token | 未知 | ≥70.4 | 716.5 | 73.7 | gpt-6-luna | default 11 |
| 7 Codex deepseek-flash low | codex-low-a1 | 是 | 是 | final | 0.575 | 0.575 | 0.000 | 0 | 1.8 | 374 | 55,107 | 511,744 | 18,614 | API usage (relay) | 37 | 0.021（¥0.140） | 未知 | ≥168.7 | 497.3 | 168.0 | deepseek-flash | default 10 |
| 7 Codex deepseek-flash low | codex-low-a2 | 是 | 是 | final | 0.570 | 0.570 | 0.000 | 0 | 2.2 | 374 | 49,642 | 698,368 | 25,595 | API usage (relay) | 33 | 0.025（¥0.166） | 未知 | ≥199.8 | 383.2 | 197.6 | deepseek-flash | default 12 |
| 7 Codex deepseek-flash low | codex-low-a3 | 是 | 是 | final | 0.682 | 0.682 | 0.000 | 0 | 1.8 | 374 | 44,081 | 555,392 | 21,269 | API usage (relay) | 28 | 0.021（¥0.140） | 未知 | ≥200.0 | 409.5 | 197.6 | deepseek-flash | default 11 |
| 7 Codex deepseek-flash low | codex-low-a4 | 是 | 是 | final | 0.648 | 0.648 | 0.000 | 0 | 1.6 | 374 | 47,858 | 508,288 | 18,214 | API usage (relay) | 28 | 0.020（¥0.131） | 未知 | ≥190.5 | 495.3 | 188.5 | deepseek-flash | default 10 |
| 7 Codex deepseek-flash low | codex-low-a5 | 是 | 是 | final | 0.696 | 0.696 | 0.000 | 0 | 2.5 | 374 | 48,142 | 1,361,280 | 29,262 | API usage (relay) | 48 | 0.029（¥0.192） | 未知 | ≥195.3 | 315.9 | 192.0 | deepseek-flash | default 23 |
| 8 Codex deepseek-flash high | codex-medium-a1 | 是 | 是 | final | 0.732 | 0.732 | 0.000 | 0 | 2.9 | 332 | 48,836 | 1,260,160 | 24,700 | API usage (relay) | 46 | ≥0.026（¥0.173） | 未知 | ≥144.5 | 280.6 | 141.9 | deepseek-flash | default 21、not-returned 1 |
| 8 Codex deepseek-flash high | codex-medium-a2 | 是 | 是 | final | 0.607 | 0.607 | 0.000 | 0 | 2.0 | 332 | 44,878 | 513,536 | 20,340 | API usage (relay) | 30 | 0.020（¥0.137） | 未知 | ≥168.6 | 368.9 | 167.2 | deepseek-flash | default 10 |
| 8 Codex deepseek-flash high | codex-high-a1 | 是 | 是 | final | 0.743 | 0.743 | 0.000 | 0 | 3.0 | 333 | 57,717 | 803,072 | 29,494 | API usage (relay) | 36 | ≥0.029（¥0.192） | 未知 | ≥167.6 | 320.2 | 163.6 | deepseek-flash | default 12、not-returned 1 |
| 8 Codex deepseek-flash high | codex-high-a2 | 是 | 是 | final | 0.659 | 0.659 | 0.000 | 0 | 3.0 | 333 | 45,047 | 1,209,856 | 27,874 | API usage (relay) | 36 | ≥0.027（¥0.181） | 未知 | ≥165.9 | 250.9 | 155.3 | deepseek-flash | default 19、not-returned 1 |
| 8 Codex deepseek-flash high | codex-high-a3 | 是 | 是 | final | 0.532 | 0.547 | 0.027 | 1 | 1.4 | 333 | 42,914 | 503,424 | 16,745 | API usage (relay) | 21 | 0.018（¥0.120） | 未知 | ≥197.0 | 496.8 | 193.8 | deepseek-flash | default 10 |
| 9 Codex deepseek-flash max | codex-max-a1 | 是 | 是 | final | 0.796 | 0.796 | 0.000 | 0 | 2.4 | 350 | 56,748 | 990,080 | 29,685 | API usage (relay) | 42 | 0.029（¥0.195） | 未知 | ≥211.7 | 399.7 | 209.1 | deepseek-flash | default 16 |
| 9 Codex deepseek-flash max | codex-max-a2 | 是 | 是 | final | 0.624 | 0.637 | 0.021 | 1 | 2.2 | 350 | 52,615 | 1,007,104 | 28,618 | API usage (relay) | 54 | 0.028（¥0.187） | 未知 | ≥218.6 | 396.4 | 215.6 | deepseek-flash | default 16 |
| 9 Codex deepseek-flash max | codex-max-a3 | 是 | 是 | final | 0.720 | 0.734 | 0.018 | 1 | 2.6 | 350 | 50,155 | 781,568 | 30,042 | API usage (relay) | 35 | 0.028（¥0.186） | 未知 | ≥196.2 | 325.5 | 195.0 | deepseek-flash | default 13 |
| 9 Codex deepseek-flash max | codex-max-a4 | 是 | 是 | final | 0.727 | 0.727 | 0.000 | 0 | 3.0 | 350 | 55,947 | 1,367,040 | 31,784 | API usage (relay) | 37 | ≥0.032（¥0.210） | 未知 | ≥189.0 | 309.3 | 175.7 | deepseek-flash | default 20、not-returned 1 |
| 9 Codex deepseek-flash max | codex-max-a5 | 是 | 是 | final | 0.820 | 0.820 | 0.000 | 0 | 3.1 | 350 | 60,843 | 1,726,848 | 35,902 | API usage (relay) | 49 | ≥0.036（¥0.239） | 未知 | ≥202.5 | 327.8 | 193.4 | deepseek-flash | default 23、not-returned 1 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a1 | 是 | 是 | final | 0.734 | 0.734 | 0.000 | 0 | 8.0 | 930 | 57,724 | 1,437,304 | 34,111 | engine log | 32 | 未知 | 1479.1 | 85.2 | 119.7 | 70.8 | 未知 | 未知 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a2 | 是 | 是 | final | 0.758 | 0.787 | 0.037 | 9 | 10.8 | 930 | 79,427 | 2,514,426 | 46,893 | engine log | 40 | 未知 | 1434.4 | 85.5 | 122.4 | 72.2 | 未知 | 未知 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a3 | 是 | 是 | final | 0.801 | 0.833 | 0.039 | 9 | 10.0 | 930 | 61,759 | 2,497,253 | 40,409 | engine log | 39 | 未知 | 1213.0 | 79.5 | 102.5 | 67.1 | 未知 | 未知 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a4 | 是 | 是 | final | 0.765 | 0.807 | 0.052 | 10 | 9.0 | 930 | 67,825 | 1,879,367 | 37,405 | engine log | 33 | 未知 | 1528.6 | 82.6 | 125.7 | 69.3 | 未知 | 未知 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a5 | 是 | 是 | final | 0.771 | 0.857 | 0.100 | 28 | 9.6 | 930 | 58,011 | 2,634,914 | 40,350 | engine log | 51 | 未知 | 1143.3 | 84.1 | 100.9 | 70.2 | 未知 | 未知 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a6 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 8.3 | 930 | 57,303 | 1,515,462 | 35,565 | engine log | 32 | 未知 | 1475.9 | 85.3 | 115.0 | 71.4 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a1 | 是 | 是 | final | 0.844 | 0.876 | 0.036 | 7 | 11.3 | 963 | 69,145 | 2,947,721 | 47,856 | engine log | 48 | 未知 | 1287.5 | 82.4 | 101.9 | 70.5 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a2 | 是 | 是 | final | 0.643 | 0.714 | 0.100 | 23 | 10.2 | 963 | 52,664 | 1,749,649 | 43,616 | engine log | 37 | 未知 | 1341.6 | 82.1 | 85.9 | 71.1 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a3 | 是 | 是 | final | 0.619 | 0.688 | 0.100 | 54 | 10.0 | 963 | 71,445 | 1,380,309 | 43,760 | engine log | 29 | 未知 | 1651.3 | 85.2 | 119.3 | 73.0 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a4 | 是 | 是 | final | 0.746 | 0.760 | 0.019 | 1 | 7.7 | 963 | 53,821 | 1,041,212 | 32,770 | engine log | 31 | 未知 | 1553.1 | 84.6 | 116.0 | 70.6 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a5 | 是 | 是 | final | 0.727 | 0.762 | 0.045 | 9 | 8.9 | 963 | 57,808 | 1,515,928 | 36,953 | engine log | 33 | 未知 | 1436.5 | 82.0 | 108.5 | 69.4 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a6 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 9.9 | 963 | 73,780 | 2,112,528 | 42,486 | engine log | 36 | 未知 | 1536.8 | 84.6 | 124.4 | 71.6 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a7 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 8.9 | 963 | 62,085 | 1,406,077 | 38,294 | engine log | 26 | 未知 | 1675.5 | 84.3 | 116.3 | 71.7 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a8 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 8.1 | 963 | 60,995 | 1,432,895 | 34,218 | engine log | 32 | 未知 | 1575.4 | 84.5 | 125.3 | 70.3 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a9 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 6.6 | 963 | 57,750 | 1,027,574 | 27,532 | engine log | 24 | 未知 | 1597.6 | 86.3 | 145.3 | 69.3 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a10 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 7.8 | 963 | 49,002 | 1,268,970 | 33,524 | engine log | 31 | 未知 | 1454.6 | 85.4 | 104.3 | 71.4 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a1 | 是 | 是 | final | 0.756 | 0.761 | 0.006 | 1 | 10.8 | 1034 | 57,629 | 1,254,908 | 49,028 | engine log | 29 | 未知 | 1482.9 | 86.9 | 89.2 | 75.9 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a2 | 是 | 是 | final | 0.794 | 0.822 | 0.034 | 4 | 11.5 | 1034 | 58,455 | 2,479,356 | 50,920 | engine log | 41 | 未知 | 1274.1 | 85.0 | 84.9 | 73.9 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a3 | 是 | 是 | final | 0.705 | 0.783 | 0.100 | 33 | 10.5 | 1034 | 71,644 | 1,830,825 | 45,034 | engine log | 35 | 未知 | 1627.5 | 82.6 | 113.2 | 71.2 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a4 | 是 | 是 | final | 0.782 | 0.869 | 0.100 | 18 | 10.2 | 1034 | 75,806 | 927,341 | 42,969 | engine log | 29 | 未知 | 1846.7 | 81.4 | 124.1 | 70.4 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a5 | 是 | 是 | final | 0.800 | 0.854 | 0.064 | 11 | 9.1 | 1034 | 59,409 | 1,138,384 | 37,318 | engine log | 30 | 未知 | 1665.8 | 80.0 | 109.2 | 68.6 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a6 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 11.1 | 1034 | 66,355 | 1,770,199 | 50,303 | engine log | 44 | 未知 | 1474.6 | 87.0 | 99.6 | 75.5 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a7 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 8.5 | 1034 | 48,832 | 1,060,125 | 36,013 | engine log | 30 | 未知 | 1450.9 | 83.0 | 95.8 | 70.6 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a8 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 9.6 | 1034 | 57,901 | 1,849,570 | 41,717 | engine log | 44 | 未知 | 1287.1 | 85.8 | 100.6 | 72.5 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a9 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 9.3 | 1034 | 58,637 | 1,316,231 | 40,449 | engine log | 35 | 未知 | 1468.9 | 85.2 | 105.0 | 72.5 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a10 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 11.4 | 1034 | 67,714 | 2,050,700 | 50,799 | engine log | 39 | 未知 | 1478.3 | 85.7 | 99.3 | 74.5 | 未知 | 未知 |
| 13 Claude Code opus low | opus-low-a1 | 是 | 是 | final | 0.607 | 0.645 | 0.059 | 3 | 2.1 | 1099 | 47,062 | 276,613 | 5,476 | Claude Code stream result usage | 7 | 0.541 | 未知 | ≥93.7 | 369.4 | 43.0 | claude-opus-5-5 | standard 8 |
| 13 Claude Code opus low | opus-low-a2 | 是 | 是 | final | 0.625 | 0.694 | 0.100 | 34 | 1.0 | 1052 | 47,933 | 212,344 | 4,501 | Claude Code stream result usage | 6 | 0.516 | 未知 | ≥81.4 | 812.4 | 76.3 | claude-opus-5-5 | standard 7 |
| 13 Claude Code opus low | opus-low-a3 | 是 | 是 | final | 0.717 | 0.717 | 0.000 | 0 | 1.6 | 1052 | 47,042 | 304,413 | 5,441 | Claude Code stream result usage | 8 | 0.546 | 未知 | ≥61.2 | 485.3 | 56.1 | claude-opus-5-5 | standard 9 |
| 13 Claude Code opus low | opus-low-a4 | 是 | 是 | final | 0.650 | 0.664 | 0.020 | 1 | 1.5 | 1052 | 43,521 | 201,531 | 4,504 | Claude Code stream result usage | 6 | 0.478 | 未知 | ≥71.9 | 499.3 | 51.7 | claude-opus-5-5 | standard 7 |
| 13 Claude Code opus low | opus-low-a5 | 是 | 是 | final | 0.688 | 0.765 | 0.100 | 37 | 1.6 | 1052 | 52,144 | 299,113 | 4,718 | Claude Code stream result usage | 7 | 0.571 | 未知 | ≥80.1 | 532.1 | 48.1 | claude-opus-5-5 | standard 8 |
| 14 Claude Code opus medium | opus-medium-a1 | 是 | 是 | final | 0.770 | 0.778 | 0.011 | 1 | 2.9 | 1106 | 54,784 | 538,225 | 10,564 | Claude Code stream result usage | 13 | 0.757 | 未知 | ≥81.2 | 311.6 | 60.1 | claude-opus-5-5 | standard 13 |
| 14 Claude Code opus medium | opus-medium-a2 | 是 | 是 | final | 0.823 | 0.832 | 0.012 | 1 | 2.0 | 1065 | 58,102 | 665,918 | 10,553 | Claude Code stream result usage | 16 | 0.809 | 未知 | ≥90.7 | 474.7 | 86.2 | claude-opus-5-5 | standard 15 |
| 14 Claude Code opus medium | opus-medium-a3 | 是 | 是 | final | 0.798 | 0.809 | 0.014 | 1 | 1.6 | 1065 | 60,451 | 379,516 | 8,711 | Claude Code stream result usage | 8 | 0.734 | 未知 | ≥93.2 | 616.4 | 88.8 | claude-opus-5-5 | standard 9 |
| 14 Claude Code opus medium | opus-medium-a4 | 是 | 是 | final | 0.738 | 0.820 | 0.100 | 43 | 1.6 | 1065 | 60,791 | 313,435 | 9,088 | Claude Code stream result usage | 7 | 0.731 | 未知 | ≥100.0 | 638.5 | 95.5 | claude-opus-5-5 | standard 8 |
| 14 Claude Code opus medium | opus-medium-a5 | 是 | 是 | final | 0.740 | 0.822 | 0.100 | 47 | 1.8 | 1065 | 63,538 | 383,102 | 9,364 | Claude Code stream result usage | 8 | 0.772 | 未知 | ≥91.1 | 590.6 | 87.0 | claude-opus-5-5 | standard 9 |
| 15 Claude Code opus high | opus-high-a1 | 是 | 是 | final | 0.881 | 0.881 | 0.000 | 0 | 2.1 | 1043 | 59,914 | 405,358 | 11,251 | Claude Code stream result usage | 10 | 0.785 | 未知 | ≥93.1 | 472.4 | 88.7 | claude-opus-5-5 | standard 10 |
| 15 Claude Code opus high | opus-high-a2 | 是 | 是 | final | 0.828 | 0.828 | 0.000 | 0 | 2.6 | 1034 | 72,206 | 828,753 | 13,226 | Claude Code stream result usage | 15 | 1.008 | 未知 | ≥91.3 | 469.7 | 86.0 | claude-opus-5-5 | standard 16 |
| 15 Claude Code opus high | opus-high-a3 | 是 | 是 | final | 0.886 | 0.886 | 0.000 | 0 | 2.6 | 1034 | 63,071 | 637,432 | 12,232 | Claude Code stream result usage | 14 | 0.877 | 未知 | ≥82.6 | 405.7 | 78.7 | claude-opus-5-5 | standard 13 |
| 15 Claude Code opus high | opus-high-a4 | 是 | 是 | final | 0.805 | 0.852 | 0.055 | 5 | 3.0 | 1034 | 61,408 | 501,226 | 12,844 | Claude Code stream result usage | 10 | 0.848 | 未知 | ≥90.6 | 341.4 | 71.4 | claude-opus-5-5 | standard 11 |
| 15 Claude Code opus high | opus-high-a5 | 是 | 是 | final | 0.835 | 0.843 | 0.010 | 1 | 2.4 | 1034 | 60,403 | 468,938 | 11,319 | Claude Code stream result usage | 10 | 0.803 | 未知 | ≥83.5 | 427.3 | 80.1 | claude-opus-5-5 | standard 11 |
| 16 Claude Code sonnet low | sonnet-low-a1 | 是 | 是 | final | 0.432 | 0.432 | 0.000 | 0 | 2.2 | 843 | 45,814 | 309,917 | 4,618 | Claude Code stream result usage | 9 | 0.260 | 未知 | ≥104.3 | 340.0 | 34.3 | claude-sonnet-5-5 | standard 9 |
| 16 Claude Code sonnet low | sonnet-low-a2 | 是 | 是 | final | 0.412 | 0.426 | 0.033 | 1 | 2.3 | 843 | 42,660 | 197,221 | 3,466 | Claude Code stream result usage | 6 | 0.225 | 未知 | ≥82.7 | 315.1 | 25.6 | claude-sonnet-5-5 | standard 7 |
| 16 Claude Code sonnet low | sonnet-low-a3 | 是 | 是 | final | 0.440 | 0.453 | 0.027 | 0 | 1.1 | 794 | 47,443 | 245,722 | 3,665 | Claude Code stream result usage | 8 | 0.251 | 未知 | ≥61.2 | 701.3 | 54.2 | claude-sonnet-5-5 | standard 8 |
| 16 Claude Code sonnet low | sonnet-low-a4 | 是 | 是 | final | 0.624 | 0.654 | 0.046 | 2 | 1.4 | 794 | 44,948 | 277,978 | 4,847 | Claude Code stream result usage | 9 | 0.256 | 未知 | ≥77.8 | 545.1 | 58.8 | claude-sonnet-5-5 | standard 9 |
| 16 Claude Code sonnet low | sonnet-low-a5 | 是 | 是 | final | 0.523 | 0.523 | 0.000 | 0 | 0.6 | 794 | 42,939 | 314,151 | 3,701 | Claude Code stream result usage | 10 | 0.240 | 未知 | ≥113.8 | 1141.1 | 98.4 | claude-sonnet-5-5 | standard 10 |
| 17 Claude Code sonnet medium | sonnet-medium-a1 | 是 | 是 | final | 0.421 | 0.421 | 0.000 | 0 | 1.8 | 848 | 49,424 | 236,677 | 4,689 | Claude Code stream result usage | 7 | 0.268 | 未知 | ≥79.6 | 453.3 | 43.0 | claude-sonnet-5-5 | standard 7 |
| 17 Claude Code sonnet medium | sonnet-medium-a2 | 是 | 是 | final | 0.602 | 0.602 | 0.000 | 0 | 2.4 | 848 | 47,596 | 217,132 | 5,151 | Claude Code stream result usage | 7 | 0.264 | 未知 | ≥98.1 | 332.4 | 36.0 | claude-sonnet-5-5 | standard 7 |
| 17 Claude Code sonnet medium | sonnet-medium-a3 | 是 | 是 | final | 0.532 | 0.543 | 0.021 | 1 | 0.7 | 799 | 44,811 | 215,412 | 5,001 | Claude Code stream result usage | 6 | 0.251 | 未知 | ≥133.9 | 1092.6 | 121.9 | claude-sonnet-5-5 | standard 7 |
| 17 Claude Code sonnet medium | sonnet-medium-a4 | 是 | 是 | final | 0.456 | 0.470 | 0.030 | 1 | 1.2 | 799 | 43,174 | 243,853 | 4,956 | Claude Code stream result usage | 9 | 0.247 | 未知 | ≥92.1 | 603.5 | 69.3 | claude-sonnet-5-5 | standard 8 |
| 17 Claude Code sonnet medium | sonnet-medium-a5 | 是 | 是 | final | 0.634 | 0.634 | 0.000 | 0 | 0.9 | 799 | 46,593 | 215,829 | 5,336 | Claude Code stream result usage | 7 | 0.261 | 未知 | ≥100.0 | 820.5 | 94.0 | claude-sonnet-5-5 | standard 7 |
| 18 Claude Code sonnet high | sonnet-high-a1 | 是 | 是 | final | 0.705 | 0.746 | 0.055 | 3 | 3.5 | 861 | 57,946 | 424,467 | 9,259 | Claude Code stream result usage | 11 | 0.367 | 未知 | ≥89.2 | 273.8 | 43.7 | claude-sonnet-5-5 | standard 10 |
| 18 Claude Code sonnet high | sonnet-high-a2 | 是 | 是 | final | 0.602 | 0.602 | 0.000 | 0 | 1.7 | 861 | 48,950 | 258,302 | 7,607 | Claude Code stream result usage | 8 | 0.298 | 未知 | ≥102.9 | 476.5 | 74.0 | claude-sonnet-5-5 | standard 8 |
| 18 Claude Code sonnet high | sonnet-high-a3 | 是 | 是 | final | 0.580 | 0.644 | 0.100 | 8 | 1.4 | 761 | 53,554 | 317,957 | 6,946 | Claude Code stream result usage | 9 | 0.315 | 未知 | ≥88.1 | 632.9 | 82.1 | claude-sonnet-5-5 | standard 9 |
| 18 Claude Code sonnet high | sonnet-high-a4 | 是 | 是 | final | 0.712 | 0.712 | 0.000 | 0 | 1.5 | 761 | 55,229 | 247,206 | 9,209 | Claude Code stream result usage | 8 | 0.338 | 未知 | ≥121.7 | 625.3 | 104.3 | claude-sonnet-5-5 | standard 7 |
| 18 Claude Code sonnet high | sonnet-high-a5 | 是 | 是 | final | 0.656 | 0.668 | 0.018 | 1 | 1.6 | 761 | 60,784 | 495,715 | 9,078 | Claude Code stream result usage | 12 | 0.383 | 未知 | ≥97.5 | 619.5 | 92.5 | claude-sonnet-5-5 | standard 11 |
| 19 Claude Code haiku low | haiku-low-a1 | 是 | 是 | final | 0.331 | 0.331 | 0.000 | 0 | 1.8 | 553 | 44,689 | 152,998 | 6,830 | Claude Code stream result usage | 5 | 0.014 | 未知 | ≥180.3 | 421.8 | 64.5 | claude-haiku-5-5 | standard 5 |
| 19 Claude Code haiku low | haiku-low-a2 | 是 | 是 | final | 0.392 | 0.407 | 0.037 | 1 | 1.1 | 553 | 49,695 | 310,211 | 10,291 | Claude Code stream result usage | 10 | 0.018 | 未知 | ≥188.9 | 774.7 | 160.4 | claude-haiku-5-5 | standard 9 |
| 19 Claude Code haiku low | haiku-low-a3 | 是 | 是 | final | 0.490 | 0.490 | 0.000 | 0 | 1.4 | 509 | 55,810 | 167,161 | 17,273 | Claude Code stream result usage | 10 | 0.021 | 未知 | ≥223.1 | 656.5 | 203.2 | claude-haiku-5-5 | standard 5 |
| 19 Claude Code haiku low | haiku-low-a4 | 是 | 是 | final | 0.470 | 0.470 | 0.000 | 0 | 1.4 | 509 | 53,879 | 266,761 | 13,440 | Claude Code stream result usage | 7 | 0.020 | 未知 | ≥198.3 | 631.5 | 157.5 | claude-haiku-5-5 | standard 7 |
| 19 Claude Code haiku low | haiku-low-a5 | 是 | 是 | final | 0.390 | 0.390 | 0.000 | 0 | 0.8 | 509 | 46,187 | 195,597 | 9,657 | Claude Code stream result usage | 6 | 0.016 | 未知 | ≥203.4 | 913.8 | 191.1 | claude-haiku-5-5 | standard 6 |
| 20 Claude Code haiku medium | haiku-medium-a1 | 是 | 是 | final | 0.429 | 0.454 | 0.057 | 2 | 2.6 | 499 | 54,385 | 209,406 | 15,151 | Claude Code stream result usage | 7 | 0.021 | 未知 | ≥170.1 | 353.7 | 98.5 | claude-haiku-5-5 | standard 6 |
| 20 Claude Code haiku medium | haiku-medium-a2 | 是 | 是 | final | 0.538 | 0.538 | 0.000 | 0 | 1.2 | 499 | 54,000 | 311,189 | 14,203 | Claude Code stream result usage | 10 | 0.021 | 未知 | ≥209.6 | 739.7 | 194.6 | claude-haiku-5-5 | standard 8 |
| 20 Claude Code haiku medium | haiku-medium-a3 | 是 | 是 | final | 0.569 | 0.609 | 0.067 | 3 | 1.6 | 483 | 59,668 | 333,773 | 18,706 | Claude Code stream result usage | 9 | 0.025 | 未知 | ≥209.1 | 634.1 | 198.8 | claude-haiku-5-5 | standard 8 |
| 20 Claude Code haiku medium | haiku-medium-a4 | 是 | 是 | final | 0.467 | 0.467 | 0.000 | 0 | 1.5 | 483 | 56,524 | 320,131 | 15,736 | Claude Code stream result usage | 10 | 0.022 | 未知 | ≥194.1 | 636.0 | 177.1 | claude-haiku-5-5 | standard 8 |
| 20 Claude Code haiku medium | haiku-medium-a5 | 是 | 是 | final | 0.502 | 0.502 | 0.000 | 0 | 1.2 | 483 | 54,799 | 318,715 | 13,636 | Claude Code stream result usage | 9 | 0.021 | 未知 | ≥205.8 | 757.7 | 188.5 | claude-haiku-5-5 | standard 8 |
| 21 Claude Code haiku high | haiku-high-a1 | 是 | 是 | final | 0.510 | 0.567 | 0.100 | 8 | 3.0 | 491 | 71,927 | 316,811 | 22,168 | Claude Code stream result usage | 10 | 0.029 | 未知 | ≥190.8 | 401.4 | 123.7 | claude-haiku-5-5 | standard 7 |
| 21 Claude Code haiku high | haiku-high-a2 | 是 | 是 | final | 0.552 | 0.552 | 0.000 | 0 | 1.7 | 491 | 57,009 | 284,568 | 16,319 | Claude Code stream result usage | 13 | 0.022 | 未知 | ≥206.8 | 544.9 | 156.0 | claude-haiku-5-5 | standard 7 |
| 21 Claude Code haiku high | haiku-high-a3 | 是 | 是 | final | 0.600 | 0.611 | 0.018 | 1 | 1.9 | 497 | 61,597 | 277,279 | 20,971 | Claude Code stream result usage | 9 | 0.026 | 未知 | ≥218.5 | 545.5 | 185.7 | claude-haiku-5-5 | standard 7 |
| 21 Claude Code haiku high | haiku-high-a4 | 是 | 是 | final | 0.480 | 0.495 | 0.031 | 1 | 1.7 | 497 | 59,886 | 336,420 | 19,015 | Claude Code stream result usage | 10 | 0.025 | 未知 | ≥201.8 | 572.2 | 181.7 | claude-haiku-5-5 | standard 8 |
| 21 Claude Code haiku high | haiku-high-a5 | 是 | 是 | final | 0.507 | 0.507 | 0.000 | 0 | 2.7 | 497 | 71,046 | 467,968 | 27,280 | Claude Code stream result usage | 12 | 0.033 | 未知 | ≥217.0 | 443.7 | 170.4 | claude-haiku-5-5 | standard 9 |
| 22 Claude Code deepseek-flash low | cc-low-a1 | 是 | 是 | final | 0.597 | 0.648 | 0.078 | 4 | 1.5 | 343 | 39,435 | 327,680 | 12,744 | Claude Code stream result usage | 16 | 0.015（¥0.097） | 未知 | ≥145.8 | 436.9 | 141.2 | deepseek-flash | standard 11 |
| 22 Claude Code deepseek-flash low | cc-low-a2 | 是 | 是 | final | 0.662 | 0.662 | 0.000 | 0 | 3.0 | 343 | 41,087 | 244,352 | 9,375 | Claude Code stream result usage | 11 | 0.013（¥0.084） | 未知 | ≥186.9 | 225.4 | 51.4 | deepseek-flash | standard 9 |
| 22 Claude Code deepseek-flash low | cc-low-a3 | 是 | 是 | final | 0.459 | 0.459 | 0.000 | 0 | 4.5 | 343 | 31,981 | 206,720 | 8,394 | Claude Code stream result usage | 13 | 0.010（¥0.070） | 未知 | ≥115.4 | 119.5 | 31.4 | deepseek-flash | standard 9 |
| 22 Claude Code deepseek-flash low | cc-low-a4 | 是 | 是 | final | 0.521 | 0.579 | 0.100 | 6 | 1.7 | 343 | 42,169 | 297,728 | 12,472 | Claude Code stream result usage | 12 | 0.015（¥0.098） | 未知 | ≥187.3 | 415.3 | 122.8 | deepseek-flash | standard 9 |
| 22 Claude Code deepseek-flash low | cc-low-a5 | 是 | 是 | final | 0.420 | 0.466 | 0.100 | 8 | 3.2 | 343 | 38,430 | 324,480 | 8,219 | Claude Code stream result usage | 23 | 0.012（¥0.078） | 未知 | ≥105.6 | 200.2 | 42.8 | deepseek-flash | standard 11 |
| 23 Claude Code deepseek-flash high | cc-high-a1 | 是 | 是 | final | 0.592 | 0.657 | 0.100 | 10 | 3.1 | 345 | 46,151 | 259,200 | 14,030 | Claude Code stream result usage | 11 | 0.016（¥0.107） | 未知 | ≥136.2 | 249.0 | 75.7 | deepseek-flash | standard 8 |
| 23 Claude Code deepseek-flash high | cc-high-a2 | 是 | 是 | final | 0.698 | 0.698 | 0.000 | 0 | 3.5 | 345 | 42,850 | 215,168 | 10,862 | Claude Code stream result usage | 12 | 0.014（¥0.091） | 未知 | ≥123.4 | 203.4 | 51.6 | deepseek-flash | standard 8 |
| 23 Claude Code deepseek-flash high | cc-high-a3 | 是 | 是 | final | 0.423 | 0.466 | 0.093 | 3 | 3.6 | 345 | 33,503 | 240,512 | 9,982 | Claude Code stream result usage | 12 | 0.012（¥0.078） | 未知 | ≥124.0 | 154.0 | 45.9 | deepseek-flash | standard 9 |
| 23 Claude Code deepseek-flash high | cc-high-a4 | 是 | 是 | final | 0.654 | 0.714 | 0.084 | 4 | 2.6 | 345 | 39,907 | 594,304 | 14,013 | Claude Code stream result usage | 26 | 0.016（¥0.108） | 未知 | ≥151.8 | 259.7 | 91.2 | deepseek-flash | standard 17 |
| 23 Claude Code deepseek-flash high | cc-high-a5 | 是 | 是 | final | 0.606 | 0.665 | 0.089 | 5 | 3.3 | 345 | 53,440 | 1,155,840 | 23,610 | Claude Code stream result usage | 31 | 0.026（¥0.171） | 未知 | ≥179.7 | 267.2 | 118.0 | deepseek-flash | standard 24 |
| 23 Claude Code deepseek-flash high | cc-medium-a1（补充行） | 是 | 是 | final | 0.563 | 0.626 | 0.100 | 6 | 3.8 | 362 | 41,861 | 324,864 | 10,223 | Claude Code stream result usage | 13 | 0.013（¥0.089） | 未知 | ≥144.0 | 184.8 | 45.1 | deepseek-flash | standard 11 |
| 24 Claude Code deepseek-flash max | cc-max-a1 | 是 | 是 | final | 0.633 | 0.633 | 0.000 | 0 | 3.5 | 362 | 48,509 | 599,680 | 22,895 | Claude Code stream result usage | 28 | 0.023（¥0.152） | 未知 | ≥168.6 | 230.9 | 109.0 | deepseek-flash | standard 15 |
| 24 Claude Code deepseek-flash max | cc-max-a2 | 是 | 是 | final | 0.567 | 0.618 | 0.083 | 4 | 4.1 | 362 | 42,542 | 289,024 | 17,159 | Claude Code stream result usage | 10 | 0.018（¥0.117） | 未知 | ≥201.5 | 173.7 | 70.0 | deepseek-flash | standard 10 |
| 24 Claude Code deepseek-flash max | cc-max-a3 | 是 | 是 | final | 0.645 | 0.716 | 0.098 | 6 | 3.1 | 362 | 55,107 | 863,360 | 32,428 | Claude Code stream result usage | 25 | 0.030（¥0.202） | 未知 | ≥202.0 | 297.9 | 175.3 | deepseek-flash | standard 18 |
| 24 Claude Code deepseek-flash max | cc-max-a4 | 是 | 是 | final | 0.511 | 0.522 | 0.020 | 1 | 4.8 | 362 | 47,100 | 643,072 | 19,868 | Claude Code stream result usage | 41 | 0.021（¥0.139） | 未知 | ≥147.8 | 164.2 | 69.2 | deepseek-flash | standard 15 |
| 24 Claude Code deepseek-flash max | cc-max-a5 | 是 | 是 | final | 0.693 | 0.726 | 0.047 | 3 | 3.2 | 362 | 45,899 | 261,248 | 18,929 | Claude Code stream result usage | 15 | 0.019（¥0.127） | 未知 | ≥176.1 | 235.5 | 97.1 | deepseek-flash | standard 8 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a1 | 是 | 是 | final | 0.788 | 0.788 | 0.000 | 0 | 9.5 | 867 | 60,686 | 2,314,910 | 43,016 | engine log | 43 | 2.264 | 1169.6 | 86.0 | 106.4 | 75.5 | qwen3.8-flash-next-iq3_xxs | not-returned 34 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a2 | 否：harness-fault | 否 | — | 未知 | 未知 | 未知 |  | 1.1 | 867 | 16,599 | 143,063 | 4,650 | engine log | 11 | 0.261 | 1606.1 | 86.1 | 245.4 | 68.7 | qwen3.8-flash-next-iq3_xxs | not-returned 8 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a3 | 否：harness-fault | 否 | — | 未知 | 未知 | 未知 |  | 1.2 | 867 | 20,179 | 114,411 | 4,632 | engine log | 7 | 0.255 | 1680.9 | 85.0 | 292.4 | 67.1 | qwen3.8-flash-next-iq3_xxs | not-returned 6 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a4 | 否：harness-fault | 否 | — | 未知 | 未知 | 未知 |  | 7.3 | 867 | 38,195 | 840,612 | 34,572 | engine log | 36 | 1.393 | 1336.8 | 85.4 | 87.4 | 79.1 | qwen3.8-flash-next-iq3_xxs | not-returned 19 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a5 | 否：harness-fault | 否 | — | 未知 | 未知 | 未知 |  | 2.5 | 867 | 31,234 | 302,506 | 10,807 | engine log | 19 | 0.566 | 1753.4 | 84.5 | 209.4 | 72.4 | qwen3.8-flash-next-iq3_xxs | not-returned 12 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a6 | 是 | 是 | final | 0.719 | 0.799 | 0.100 | 44 | 9.8 | 867 | 72,009 | 2,466,933 | 45,032 | engine log | 62 | 2.505 | 1307.6 | 86.9 | 123.1 | 77.0 | qwen3.8-flash-next-iq3_xxs | not-returned 34 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a7 | 是 | 是 | final | 0.591 | 0.602 | 0.018 | 2 | 10.6 | 867 | 59,370 | 2,700,417 | 47,603 | engine log | 48 | 2.733 | 1152.0 | 83.8 | 93.0 | 74.6 | qwen3.8-flash-next-iq3_xxs | not-returned 42 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a8 | 是 | 是 | final | 0.646 | 0.718 | 0.100 | 66 | 9.6 | 867 | 53,965 | 1,522,960 | 43,555 | engine log | 31 | 1.951 | 1404.9 | 82.3 | 93.4 | 75.4 | qwen3.8-flash-next-iq3_xxs | not-returned 23 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a9 | 是 | 是 | final | 0.770 | 0.783 | 0.017 | 3 | 10.4 | 867 | 53,347 | 1,867,378 | 47,765 | engine log | 33 | 2.153 | 1169.4 | 84.5 | 85.4 | 76.5 | qwen3.8-flash-next-iq3_xxs | not-returned 29 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a1 | 否：harness-fault | 否 | — | 未知 | 未知 | 未知 |  | 8.4 | 886 | 37,405 | 844,570 | 40,128 | engine log | 42 | 1.528 | 1493.0 | 84.0 | 73.9 | 79.3 | qwen3.8-flash-next-iq3_xxs | not-returned 17 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a2 | 否：harness-fault | 否 | — | 未知 | 未知 | 未知 |  | 9.1 | 886 | 46,333 | 1,115,204 | 46,746 | engine log | 44 | 1.695 | 1472.2 | 91.3 | 84.7 | 85.5 | qwen3.8-flash-next-iq3_xxs | not-returned 17 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a3 | 否：harness-fault | 否 | — | 未知 | 未知 | 未知 |  | 1.3 | 886 | 18,787 | 113,335 | 5,646 | engine log | 10 | 0.292 | 1674.3 | 86.8 | 237.9 | 71.5 | qwen3.8-flash-next-iq3_xxs | not-returned 7 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a4 | 否：harness-fault | 否 | — | 未知 | 未知 | 未知 |  | 2.5 | 886 | 24,767 | 195,506 | 10,735 | engine log | 12 | 0.490 | 1670.3 | 82.4 | 167.7 | 72.7 | qwen3.8-flash-next-iq3_xxs | not-returned 9 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a5 | 否：harness-fault | 否 | — | 未知 | 未知 | 未知 |  | 8.7 | 886 | 57,675 | 1,338,475 | 44,671 | engine log | 41 | 1.809 | 1545.2 | 93.0 | 110.6 | 85.7 | qwen3.8-flash-next-iq3_xxs | not-returned 21 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a6 | 是 | 是 | final | 0.684 | 0.760 | 0.100 | 27 | 6.9 | 886 | 50,060 | 950,116 | 32,607 | engine log | 29 | 1.478 | 1585.3 | 87.8 | 121.6 | 79.2 | qwen3.8-flash-next-iq3_xxs | not-returned 18 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a7 | 是 | 是 | final | 0.690 | 0.694 | 0.007 | 1 | 8.6 | 886 | 50,670 | 1,486,316 | 40,101 | engine log | 36 | 1.947 | 1320.8 | 86.8 | 98.7 | 78.1 | qwen3.8-flash-next-iq3_xxs | not-returned 28 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a8 | 是 | 是 | final | 0.661 | 0.734 | 0.100 | 14 | 4.1 | 886 | 41,250 | 641,754 | 18,203 | engine log | 23 | 0.922 | 1493.8 | 85.3 | 166.7 | 73.6 | qwen3.8-flash-next-iq3_xxs | not-returned 16 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a9 | 是 | 是 | final | 0.795 | 0.883 | 0.100 | 18 | 8.4 | 886 | 54,496 | 1,273,225 | 40,004 | engine log | 31 | 1.737 | 1398.8 | 87.7 | 108.0 | 79.3 | qwen3.8-flash-next-iq3_xxs | not-returned 22 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a10 | 是 | 是 | final | 0.703 | 0.781 | 0.100 | 24 | 6.7 | 886 | 49,642 | 864,257 | 30,927 | engine log | 29 | 1.420 | 1566.1 | 84.2 | 122.9 | 76.6 | qwen3.8-flash-next-iq3_xxs | not-returned 17 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a1 | 否：harness-fault | 否 | — | 未知 | 未知 | 未知 |  | 11.3 | 898 | 59,222 | 921,311 | 57,012 | engine log | 50 | 2.106 | 1749.8 | 89.3 | 87.6 | 84.3 | qwen3.8-flash-next-iq3_xxs | not-returned 17 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a2 | 否：harness-fault | 否 | — | 未知 | 未知 | 未知 |  | 1.9 | 898 | 18,643 | 92,503 | 8,690 | engine log | 8 | 0.357 | 1696.4 | 85.9 | 162.4 | 75.7 | qwen3.8-flash-next-iq3_xxs | not-returned 6 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a3 | 否：harness-fault | 否 | — | 未知 | 未知 | 未知 |  | 8.9 | 898 | 40,100 | 670,438 | 46,559 | engine log | 38 | 1.662 | 1690.8 | 91.4 | 74.7 | 86.8 | qwen3.8-flash-next-iq3_xxs | not-returned 14 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a4 | 否：harness-fault | 否 | — | 未知 | 未知 | 未知 |  | 7.1 | 898 | 41,195 | 679,438 | 35,773 | engine log | 45 | 1.348 | 1486.5 | 91.4 | 97.1 | 84.3 | qwen3.8-flash-next-iq3_xxs | not-returned 18 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a5 | 否：harness-fault | 否 | — | 未知 | 未知 | 未知 |  | 10.6 | 898 | 55,247 | 820,190 | 51,369 | engine log | 43 | 1.892 | 1668.3 | 85.9 | 87.0 | 80.9 | qwen3.8-flash-next-iq3_xxs | not-returned 17 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a6 | 是 | 是 | final | 0.837 | 0.837 | 0.000 | 0 | 9.6 | 898 | 64,469 | 1,455,000 | 44,010 | engine log | 29 | 2.034 | 1616.3 | 83.5 | 112.3 | 76.7 | qwen3.8-flash-next-iq3_xxs | not-returned 21 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a7 | 是 | 是 | final | 0.685 | 0.728 | 0.058 | 6 | 9.4 | 898 | 69,763 | 1,325,846 | 46,902 | engine log | 30 | 1.969 | 1621.9 | 91.2 | 123.4 | 82.9 | qwen3.8-flash-next-iq3_xxs | not-returned 20 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a8 | 是 | 是 | final | 0.690 | 0.690 | 0.000 | 0 | 8.0 | 898 | 50,305 | 860,760 | 38,288 | engine log | 29 | 1.572 | 1555.8 | 86.2 | 104.5 | 79.5 | qwen3.8-flash-next-iq3_xxs | not-returned 17 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a9 | 是 | 是 | final | 0.697 | 0.774 | 0.100 | 14 | 10.1 | 898 | 50,631 | 1,131,422 | 48,126 | engine log | 28 | 1.959 | 1389.3 | 85.3 | 83.2 | 79.1 | qwen3.8-flash-next-iq3_xxs | not-returned 21 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a10 | 是 | 是 | final | 0.682 | 0.756 | 0.098 | 11 | 8.9 | 898 | 51,925 | 1,035,202 | 42,151 | engine log | 37 | 1.792 | 1514.6 | 85.1 | 96.8 | 78.6 | qwen3.8-flash-next-iq3_xxs | not-returned 19 |

### Commit Audit v3（CA）

| 配置 | 实例 | 有效 | 进主统计 | 计分 | 分数 | rawScore | f | 修复 | 耗时（分钟） | 时限（秒） | 未缓存 | 缓存 | 输出 | token 来源 | 工具调用 | 费用（美元；括号内人民币） | 引擎输入 tok/s | 引擎输出 tok/s | 任务平均输入 tok/s | 任务平均输出 tok/s | 模型 ID | tier |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 Codex gpt-6.1-sol low | sol-low-a1 | 是 | 是 | final | 0.894 | 0.894 | 0.000 | 0 | 1.8 | 无 | 71,028 | 322,560 | 7,755 | API usage (relay) | 7 | 只报 token | 未知 | ≥70.7 | 643.4 | 70.2 | gpt-6.1-sol | default 8 |
| 1 Codex gpt-6.1-sol low | sol-low-a2 | 是 | 是 | final | 0.853 | 0.853 | 0.000 | 0 | 2.1 | 无 | 72,377 | 394,624 | 8,145 | API usage (relay) | 8 | 只报 token | 未知 | ≥64.3 | 563.4 | 63.4 | gpt-6.1-sol | default 9 |
| 1 Codex gpt-6.1-sol low | sol-low-a3 | 是 | 是 | final | 0.868 | 0.868 | 0.000 | 0 | 1.4 | 无 | 59,568 | 265,344 | 5,128 | API usage (relay) | 6 | 只报 token | 未知 | ≥62.4 | 714.9 | 61.5 | gpt-6.1-sol | default 7 |
| 1 Codex gpt-6.1-sol low | sol-low-a4 | 是 | 是 | final | 0.875 | 0.875 | 0.000 | 0 | 1.2 | 无 | 55,663 | 264,064 | 4,478 | API usage (relay) | 6 | 只报 token | 未知 | ≥62.8 | 770.8 | 62.0 | gpt-6.1-sol | default 7 |
| 1 Codex gpt-6.1-sol low | sol-low-a5 | 是 | 是 | final | 0.851 | 0.851 | 0.000 | 0 | 1.1 | 无 | 68,918 | 272,640 | 4,141 | API usage (relay) | 6 | 只报 token | 未知 | ≥61.3 | 1014.4 | 60.9 | gpt-6.1-sol | default 7 |
| 2 Codex gpt-6.1-sol medium | sol-medium-a1 | 是 | 是 | final | 0.872 | 0.872 | 0.000 | 0 | 1.5 | 无 | 56,244 | 309,760 | 5,355 | API usage (relay) | 7 | 只报 token | 未知 | ≥59.5 | 622.7 | 59.3 | gpt-6.1-sol | default 8 |
| 2 Codex gpt-6.1-sol medium | sol-medium-a2 | 是 | 是 | final | 0.865 | 0.865 | 0.000 | 0 | 2.3 | 无 | 69,877 | 492,928 | 8,348 | API usage (relay) | 9 | 只报 token | 未知 | ≥60.1 | 507.3 | 60.6 | gpt-6.1-sol | default 10 |
| 2 Codex gpt-6.1-sol medium | sol-medium-a3 | 是 | 是 | final | 0.866 | 0.866 | 0.000 | 0 | 2.2 | 无 | 70,919 | 327,552 | 9,217 | API usage (relay) | 7 | 只报 token | 未知 | ≥68.7 | 528.0 | 68.6 | gpt-6.1-sol | default 8 |
| 2 Codex gpt-6.1-sol medium | sol-medium-a4 | 是 | 是 | final | 0.873 | 0.873 | 0.000 | 0 | 1.5 | 无 | 61,300 | 269,312 | 5,549 | API usage (relay) | 6 | 只报 token | 未知 | ≥63.8 | 700.6 | 63.4 | gpt-6.1-sol | default 7 |
| 2 Codex gpt-6.1-sol medium | sol-medium-a5 | 是 | 是 | final | 0.882 | 0.882 | 0.000 | 0 | 2.3 | 无 | 65,100 | 400,000 | 9,389 | API usage (relay) | 8 | 只报 token | 未知 | ≥67.5 | 465.8 | 67.2 | gpt-6.1-sol | default 9 |
| 3 Codex gpt-6.1-sol high | sol-high-a1 | 是 | 是 | final | 0.873 | 0.873 | 0.000 | 0 | 2.5 | 无 | 66,500 | 414,080 | 9,030 | API usage (relay) | 8 | 只报 token | 未知 | ≥59.9 | 439.4 | 59.7 | gpt-6.1-sol | default 9 |
| 3 Codex gpt-6.1-sol high | sol-high-a2 | 是 | 是 | final | 0.873 | 0.873 | 0.000 | 0 | 2.5 | 无 | 64,385 | 412,032 | 8,906 | API usage (relay) | 8 | 只报 token | 未知 | ≥59.0 | 425.6 | 58.9 | gpt-6.1-sol | default 9 |
| 3 Codex gpt-6.1-sol high | sol-high-a3 | 是 | 是 | final | 0.871 | 0.871 | 0.000 | 0 | 4.0 | 无 | 73,867 | 620,032 | 13,837 | API usage (relay) | 11 | 只报 token | 未知 | ≥58.1 | 308.8 | 57.8 | gpt-6.1-sol | default 12 |
| 3 Codex gpt-6.1-sol high | sol-high-a4 | 是 | 是 | final | 0.874 | 0.874 | 0.000 | 0 | 2.2 | 无 | 74,956 | 338,816 | 7,853 | API usage (relay) | 7 | 只报 token | 未知 | ≥59.9 | 571.8 | 59.9 | gpt-6.1-sol | default 8 |
| 3 Codex gpt-6.1-sol high | sol-high-a5 | 是 | 是 | final | 0.837 | 0.837 | 0.000 | 0 | 3.2 | 无 | 67,975 | 454,272 | 11,810 | API usage (relay) | 9 | 只报 token | 未知 | ≥61.3 | 352.1 | 61.2 | gpt-6.1-sol | default 10 |
| 4 Codex gpt-6-luna low | luna-low-a2 | 否：no-record | 否 | — | 未知 | 未知 | 未知 |  | 未知 | 无 | 未知 | 未知 | 未知 | 未知 | 未知 | 只报 token | 未知 | ≥74.6 | 未知 | 未知 | 未知 | 未知 |
| 4 Codex gpt-6-luna low | luna-low-a4 | 否：void | 否 | — | 未知 | 未知 | 未知 |  | 未知 | 无 | 未知 | 未知 | 未知 | 未知 | 未知 | 只报 token | 未知 | ≥57.0 | 未知 | 未知 | 未知 | 未知 |
| 4 Codex gpt-6-luna low | luna-low-a1 | 是 | 是 | final | -1.155 | -0.498 | 0.000 | 0 | 1.0 | 无 | 66,953 | 566,272 | 5,761 | API usage (relay) | 10 | 只报 token | 未知 | ≥97.7 | 1133.6 | 97.5 | gpt-6-luna | default 13 |
| 4 Codex gpt-6-luna low | luna-low-a3 | 是 | 是 | final | -0.568 | -0.245 | 0.000 | 0 | 1.8 | 无 | 62,586 | 555,392 | 12,517 | API usage (relay) | 11 | 只报 token | 未知 | ≥115.4 | 576.5 | 115.3 | gpt-6-luna | default 13 |
| 4 Codex gpt-6-luna low | luna-low-a5 | 是 | 是 | final | -1.567 | -0.676 | 0.000 | 0 | 1.2 | 无 | 48,254 | 709,760 | 7,462 | API usage (relay) | 14 | 只报 token | 未知 | ≥104.3 | 650.5 | 100.6 | gpt-6-luna | default 17 |
| 4 Codex gpt-6-luna low | luna-low-a6 | 是 | 是 | final | -0.862 | -0.371 | 0.000 | 0 | 1.6 | 无 | 59,196 | 909,440 | 8,908 | API usage (relay) | 15 | 只报 token | 未知 | ≥91.7 | 613.6 | 92.3 | gpt-6-luna | default 20 |
| 4 Codex gpt-6-luna low | luna-low-a7 | 是 | 是 | final | -1.074 | -0.421 | 0.100 | 16 | 1.4 | 无 | 56,110 | 560,768 | 7,595 | API usage (relay) | 12 | 只报 token | 未知 | ≥94.3 | 689.0 | 93.3 | gpt-6-luna | default 13 |
| 5 Codex gpt-6-luna medium | luna-medium-a5 | 否：no-record | 否 | — | 未知 | 未知 | 未知 |  | 未知 | 无 | 未知 | 未知 | 未知 | 未知 | 未知 | 只报 token | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 |
| 5 Codex gpt-6-luna medium | luna-medium-a1 | 是 | 是 | final | 0.046 | 0.046 | 0.000 | 0 | 2.6 | 无 | 68,580 | 1,166,080 | 17,387 | API usage (relay) | 21 | 只报 token | 未知 | ≥111.4 | 437.3 | 110.9 | gpt-6-luna | default 23 |
| 5 Codex gpt-6-luna medium | luna-medium-a2 | 是 | 是 | final | -0.228 | -0.098 | 0.000 | 0 | 1.3 | 无 | 59,418 | 560,768 | 7,040 | API usage (relay) | 11 | 只报 token | 未知 | ≥92.9 | 778.4 | 92.2 | gpt-6-luna | default 14 |
| 5 Codex gpt-6-luna medium | luna-medium-a3 | 是 | 是 | final | 0.406 | 0.406 | 0.000 | 0 | 4.0 | 无 | 90,773 | 2,125,568 | 25,952 | API usage (relay) | 29 | 只报 token | 未知 | ≥108.4 | 379.5 | 108.5 | gpt-6-luna | default 34 |
| 5 Codex gpt-6-luna medium | luna-medium-a4 | 否：invalid | 否 | — | 未知 | 未知 | 未知 |  | 2.7 | 无 | 69,509 | 1,081,344 | 13,197 | API usage (relay) | 19 | 只报 token | 未知 | ≥97.3 | 426.7 | 81.0 | gpt-6-luna | not-returned 1、default 25 |
| 5 Codex gpt-6-luna medium | luna-medium-a6 | 是 | 是 | final | -0.441 | -0.190 | 0.000 | 0 | 1.9 | 无 | 53,905 | 740,608 | 10,839 | API usage (relay) | 14 | 只报 token | 未知 | ≥95.8 | 474.9 | 95.5 | gpt-6-luna | default 18 |
| 5 Codex gpt-6-luna medium | luna-medium-a7 | 是 | 是 | final | -0.861 | -0.371 | 0.000 | 0 | 2.3 | 无 | 64,401 | 926,336 | 14,695 | API usage (relay) | 17 | 只报 token | 未知 | ≥108.5 | 473.2 | 108.0 | gpt-6-luna | default 20 |
| 6 Codex gpt-6-luna high | luna-high-a1 | 否：no-record | 否 | — | 未知 | 未知 | 未知 |  | 未知 | 无 | 未知 | 未知 | 未知 | 未知 | 未知 | 只报 token | 未知 | ≥93.6 | 未知 | 未知 | 未知 | 未知 |
| 6 Codex gpt-6-luna high | luna-high-a2 | 否：no-record | 否 | — | 未知 | 未知 | 未知 |  | 未知 | 无 | 未知 | 未知 | 未知 | 未知 | 未知 | 只报 token | 未知 | ≥102.6 | 未知 | 未知 | 未知 | 未知 |
| 6 Codex gpt-6-luna high | luna-high-a3 | 否：void | 否 | — | 未知 | 未知 | 未知 |  | 未知 | 无 | 未知 | 未知 | 未知 | 未知 | 未知 | 只报 token | 未知 | ≥80.5 | 未知 | 未知 | 未知 | 未知 |
| 6 Codex gpt-6-luna high | luna-high-a4 | 是 | 是 | final | 0.610 | 0.610 | 0.000 | 0 | 6.2 | 无 | 117,796 | 2,824,960 | 42,927 | API usage (relay) | 34 | 只报 token | 未知 | ≥115.5 | 314.9 | 114.7 | gpt-6-luna | default 38 |
| 6 Codex gpt-6-luna high | luna-high-a5 | 是 | 是 | final | -0.932 | -0.402 | 0.000 | 0 | 2.1 | 无 | 71,282 | 678,016 | 15,008 | API usage (relay) | 13 | 只报 token | 未知 | ≥116.9 | 553.1 | 116.5 | gpt-6-luna | default 15 |
| 6 Codex gpt-6-luna high | luna-high-a6 | 否：invalid | 否 | — | 未知 | 未知 | 未知 |  | 5.0 | 无 | 93,170 | 1,085,568 | 31,328 | API usage (relay) | 17 | 只报 token | 未知 | ≥116.8 | 312.1 | 104.9 | gpt-6-luna | default 21、not-returned 1 |
| 6 Codex gpt-6-luna high | luna-high-a7 | 是 | 是 | final | 0.360 | 0.360 | 0.000 | 0 | 2.5 | 无 | 62,025 | 765,696 | 16,835 | API usage (relay) | 15 | 只报 token | 未知 | ≥111.2 | 407.0 | 110.5 | gpt-6-luna | default 16 |
| 6 Codex gpt-6-luna high | luna-high-a8 | 否：void | 否 | — | 未知 | 未知 | 未知 |  | 未知 | 无 | 未知 | 未知 | 未知 | 未知 | 未知 | 只报 token | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 |
| 6 Codex gpt-6-luna high | luna-high-a9 | 是 | 是 | final | 0.537 | 0.537 | 0.000 | 0 | 4.7 | 无 | 85,855 | 982,400 | 32,623 | API usage (relay) | 18 | 只报 token | 未知 | ≥115.9 | 304.2 | 115.6 | gpt-6-luna | default 20 |
| 6 Codex gpt-6-luna high | luna-high-a10 | 是 | 是 | final | 0.096 | 0.100 | 0.038 | 0 | 3.9 | 无 | 85,876 | 1,029,760 | 23,521 | API usage (relay) | 17 | 只报 token | 未知 | ≥101.4 | 366.8 | 100.5 | gpt-6-luna | default 20 |
| 7 Codex deepseek-flash low | codex-low-a1 | 是 | 是 | final | 0.759 | 0.759 | 0.000 | 0 | 7.0 | 无 | 59,569 | 3,637,248 | 78,575 | API usage (relay) | 76 | 0.067（¥0.447） | 未知 | ≥188.7 | 142.2 | 187.6 | deepseek-flash | default 38 |
| 7 Codex deepseek-flash low | codex-low-a2 | 是 | 是 | final | 0.710 | 0.710 | 0.000 | 0 | 4.7 | 无 | 62,451 | 2,041,088 | 58,783 | API usage (relay) | 58 | 0.051（¥0.338） | 未知 | ≥208.6 | 219.8 | 206.9 | deepseek-flash | default 24 |
| 7 Codex deepseek-flash low | codex-low-a3 | 是 | 是 | final | 0.622 | 0.622 | 0.000 | 0 | 4.1 | 无 | 60,352 | 2,099,072 | 50,019 | API usage (relay) | 48 | 0.045（¥0.302） | 未知 | ≥207.9 | 248.3 | 205.8 | deepseek-flash | default 27 |
| 7 Codex deepseek-flash low | codex-low-a4 | 是 | 是 | final | 0.641 | 0.712 | 0.100 | 85 | 3.8 | 无 | 62,793 | 1,402,368 | 51,693 | API usage (relay) | 54 | 0.045（¥0.298） | 未知 | ≥230.5 | 277.5 | 228.4 | deepseek-flash | default 18 |
| 7 Codex deepseek-flash low | codex-low-a5 | 是 | 是 | final | 0.802 | 0.802 | 0.000 | 0 | 4.9 | 无 | 61,111 | 2,131,200 | 63,003 | API usage (relay) | 72 | 0.053（¥0.356） | 未知 | ≥215.0 | 206.7 | 213.2 | deepseek-flash | default 26 |
| 8 Codex deepseek-flash high | codex-medium-a1 | 是 | 是 | final | 0.223 | 0.248 | 0.100 | 7 | 6.6 | 无 | 53,313 | 2,731,008 | 77,931 | API usage (relay) | 66 | 0.063（¥0.420） | 未知 | ≥197.5 | 134.3 | 196.3 | deepseek-flash | default 28 |
| 8 Codex deepseek-flash high | codex-high-a1 | 是 | 是 | final | 0.384 | 0.384 | 0.000 | 0 | 4.2 | 无 | 46,124 | 1,277,056 | 49,581 | API usage (relay) | 41 | 0.040（¥0.270） | 未知 | ≥197.2 | 182.6 | 196.2 | deepseek-flash | default 17 |
| 8 Codex deepseek-flash high | codex-high-a2 | 是 | 是 | final | 0.800 | 0.800 | 0.000 | 0 | 4.5 | 无 | 56,662 | 1,691,904 | 58,375 | API usage (relay) | 43 | 0.049（¥0.324） | 未知 | ≥215.2 | 207.9 | 214.2 | deepseek-flash | default 20 |
| 8 Codex deepseek-flash high | codex-medium-a2 | 是 | 是 | final | 0.745 | 0.745 | 0.000 | 0 | 5.4 | 无 | 72,245 | 2,273,024 | 67,161 | API usage (relay) | 44 | 0.058（¥0.386） | 未知 | ≥209.6 | 224.0 | 208.2 | deepseek-flash | default 25 |
| 8 Codex deepseek-flash high | codex-medium-a3 | 是 | 是 | final | 0.734 | 0.780 | 0.060 | 2 | 4.5 | 无 | 53,653 | 1,709,824 | 62,933 | API usage (relay) | 76 | 0.051（¥0.340） | 未知 | ≥233.8 | 198.0 | 232.2 | deepseek-flash | default 22 |
| 8 Codex deepseek-flash high | codex-high-a3 | 是 | 是 | final | 0.691 | 0.691 | 0.000 | 0 | 4.9 | 无 | 71,842 | 2,461,184 | 66,475 | API usage (relay) | 93 | 0.058（¥0.387） | 未知 | ≥226.0 | 242.4 | 224.3 | deepseek-flash | default 27 |
| 8 Codex deepseek-flash high | codex-high-a4 | 是 | 是 | final | 0.791 | 0.791 | 0.000 | 0 | 6.0 | 无 | 75,827 | 3,368,064 | 80,927 | API usage (relay) | 74 | 0.070（¥0.467） | 未知 | ≥226.7 | 210.7 | 224.9 | deepseek-flash | default 29 |
| 8 Codex deepseek-flash high | codex-medium-a4 | 是 | 是 | final | 0.795 | 0.795 | 0.000 | 0 | 4.8 | 无 | 50,571 | 2,179,072 | 64,086 | API usage (relay) | 75 | 0.053（¥0.350） | 未知 | ≥222.3 | 173.9 | 220.3 | deepseek-flash | default 26 |
| 9 Codex deepseek-flash max | codex-max-a1 | 是 | 是 | final | 0.416 | 0.416 | 0.000 | 0 | 6.5 | 无 | 73,446 | 1,841,024 | 83,689 | API usage (relay) | 69 | 0.067（¥0.445） | 未知 | ≥217.0 | 189.4 | 215.8 | deepseek-flash | default 23 |
| 9 Codex deepseek-flash max | codex-max-a2 | 是 | 是 | final | 0.769 | 0.769 | 0.000 | 0 | 5.3 | 无 | 63,697 | 2,404,608 | 71,159 | API usage (relay) | 66 | 0.059（¥0.396） | 未知 | ≥228.0 | 202.1 | 225.8 | deepseek-flash | default 28 |
| 9 Codex deepseek-flash max | codex-max-a3 | 是 | 是 | final | 0.830 | 0.830 | 0.000 | 0 | 5.6 | 无 | 68,585 | 2,971,776 | 73,489 | API usage (relay) | 58 | 0.063（¥0.422） | 未知 | ≥218.8 | 202.6 | 217.1 | deepseek-flash | default 30 |
| 9 Codex deepseek-flash max | codex-max-a4 | 是 | 是 | final | 0.833 | 0.833 | 0.000 | 0 | 6.5 | 无 | 69,239 | 4,060,672 | 86,327 | API usage (relay) | 83 | 0.074（¥0.496） | 未知 | ≥225.4 | 178.8 | 222.9 | deepseek-flash | default 37 |
| 9 Codex deepseek-flash max | codex-max-a5 | 是 | 是 | final | 0.874 | 0.874 | 0.000 | 0 | 13.5 | 无 | 79,799 | 4,512,768 | 101,836 | API usage (relay) | 84 | 0.087（¥0.577） | 未知 | ≥214.2 | 98.4 | 125.5 | deepseek-flash | default 38 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a1 | 是 | 是 | final | 0.557 | 0.557 | 0.000 | 0 | 17.2 | 无 | 235,260 | 4,005,490 | 77,120 | engine log | 46 | 未知 | 1839.4 | 89.5 | 228.1 | 74.8 | 未知 | 未知 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a2 | 是 | 是 | final | 0.544 | 0.544 | 0.000 | 0 | 13.3 | 无 | 61,727 | 2,905,846 | 63,479 | engine log | 38 | 未知 | 1122.1 | 90.5 | 77.4 | 79.6 | 未知 | 未知 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a3 | 否：void | 否 | — | 未知 | 未知 | 未知 |  | 9.1 | 无 | 48,262 | 1,629,358 | 43,947 | engine log | 29 | 未知 | 1168.9 | 94.4 | 88.2 | 80.3 | 未知 | 未知 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a4 | 是 | 是 | final | 0.574 | 0.574 | 0.000 | 0 | 14.8 | 无 | 62,325 | 3,260,507 | 73,853 | engine log | 41 | 未知 | 1045.6 | 94.2 | 70.3 | 83.3 | 未知 | 未知 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a5 | 否：void | 否 | — | 未知 | 未知 | 未知 |  | 13.4 | 无 | 58,563 | 3,266,037 | 61,695 | engine log | 53 | 未知 | 1117.7 | 87.3 | 73.0 | 76.9 | 未知 | 未知 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a6 | 是 | 是 | final | 0.664 | 0.664 | 0.000 | 0 | 15.9 | 无 | 54,141 | 3,653,024 | 79,735 | engine log | 41 | 未知 | 1024.9 | 93.1 | 56.7 | 83.5 | 未知 | 未知 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a7 | 是 | 是 | final | 0.385 | 0.428 | 0.100 | 93 | 16.4 | 无 | 64,030 | 3,806,192 | 80,241 | engine log | 43 | 未知 | 1096.9 | 91.0 | 65.1 | 81.6 | 未知 | 未知 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a8 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 15.7 | 无 | 71,001 | 4,188,956 | 76,692 | engine log | 47 | 未知 | 1142.2 | 91.9 | 75.3 | 81.3 | 未知 | 未知 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a9 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 14.4 | 无 | 65,710 | 3,731,892 | 71,292 | engine log | 52 | 未知 | 1197.0 | 93.4 | 76.0 | 82.4 | 未知 | 未知 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a10 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 11.8 | 无 | 64,723 | 3,162,784 | 56,254 | engine log | 45 | 未知 | 1118.7 | 93.2 | 91.3 | 79.3 | 未知 | 未知 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a11 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 15.4 | 无 | 69,876 | 3,612,858 | 75,160 | engine log | 49 | 未知 | 1113.1 | 92.4 | 75.7 | 81.5 | 未知 | 未知 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a12 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 12.8 | 无 | 69,560 | 3,136,708 | 62,855 | engine log | 38 | 未知 | 1205.6 | 94.3 | 90.3 | 81.6 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a1 | 是 | 是 | final | 0.661 | 0.661 | 0.000 | 0 | 17.2 | 无 | 78,344 | 2,362,876 | 86,039 | engine log | 30 | 未知 | 1427.6 | 91.9 | 76.0 | 83.4 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a2 | 否：void | 否 | — | 未知 | 未知 | 未知 |  | 9.7 | 无 | 47,293 | 1,154,275 | 47,183 | engine log | 21 | 未知 | 1439.9 | 92.1 | 81.0 | 80.9 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a3 | 否：void | 否 | — | 未知 | 未知 | 未知 |  | 9.7 | 无 | 48,065 | 1,384,802 | 47,404 | engine log | 28 | 未知 | 1255.5 | 93.6 | 82.4 | 81.3 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a4 | 是 | 是 | final | 0.428 | 0.428 | 0.000 | 0 | 21.4 | 无 | 230,748 | 3,805,168 | 102,833 | engine log | 49 | 未知 | 1895.1 | 92.0 | 180.0 | 80.2 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a5 | 是 | 是 | final | 0.708 | 0.708 | 0.000 | 0 | 15.4 | 无 | 213,242 | 2,483,460 | 69,953 | engine log | 35 | 未知 | 1900.7 | 91.0 | 230.2 | 75.5 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a6 | 是 | 是 | final | 0.842 | 0.842 | 0.000 | 0 | 15.8 | 无 | 75,590 | 3,404,483 | 77,154 | engine log | 44 | 未知 | 1186.1 | 91.5 | 79.7 | 81.4 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a7 | 是 | 是 | final | 0.644 | 0.644 | 0.000 | 0 | 19.1 | 无 | 71,275 | 4,423,035 | 96,049 | engine log | 48 | 未知 | 1112.3 | 92.4 | 62.1 | 83.6 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a8 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 13.8 | 无 | 66,340 | 2,335,308 | 70,101 | engine log | 32 | 未知 | 1369.9 | 95.5 | 80.2 | 84.8 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a9 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 16.2 | 无 | 70,619 | 2,555,504 | 80,411 | engine log | 36 | 未知 | 1304.2 | 92.4 | 72.8 | 82.9 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a10 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 10.0 | 无 | 61,922 | 1,280,001 | 49,281 | engine log | 24 | 未知 | 1438.4 | 95.8 | 102.9 | 81.9 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a11 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 13.0 | 无 | 62,812 | 2,085,223 | 64,435 | engine log | 28 | 未知 | 1388.8 | 94.0 | 80.7 | 82.8 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a12 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 14.7 | 无 | 57,572 | 2,701,500 | 73,432 | engine log | 33 | 未知 | 1214.0 | 93.0 | 65.3 | 83.2 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a1 | 是 | 是 | final | 0.664 | 0.664 | 0.000 | 0 | 23.4 | 无 | 279,695 | 3,568,007 | 110,637 | engine log | 56 | 未知 | 1900.7 | 91.3 | 199.5 | 78.9 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a2 | 是 | 是 | final | 0.720 | 0.720 | 0.000 | 0 | 25.7 | 无 | 254,306 | 3,293,602 | 127,366 | engine log | 65 | 未知 | 1916.4 | 93.4 | 165.2 | 82.7 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a3 | 是 | 是 | final | 0.772 | 0.772 | 0.000 | 0 | 15.4 | 无 | 71,224 | 3,777,263 | 74,595 | engine log | 48 | 未知 | 1226.4 | 91.0 | 77.3 | 81.0 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a4 | 是 | 是 | final | 0.554 | 0.554 | 0.000 | 0 | 11.9 | 无 | 52,382 | 2,026,237 | 56,628 | engine log | 32 | 未知 | 1215.0 | 89.7 | 73.3 | 79.3 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a5 | 是 | 是 | final | 0.595 | 0.595 | 0.000 | 0 | 23.4 | 无 | 223,233 | 3,742,540 | 115,750 | engine log | 55 | 未知 | 1799.1 | 93.6 | 158.8 | 82.3 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a6 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 17.1 | 无 | 79,574 | 4,017,899 | 85,465 | engine log | 46 | 未知 | 1296.2 | 93.0 | 77.6 | 83.3 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a7 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 16.1 | 无 | 64,856 | 2,539,849 | 78,526 | engine log | 34 | 未知 | 1319.8 | 90.4 | 67.3 | 81.5 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a8 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 15.4 | 无 | 59,285 | 2,527,233 | 77,312 | engine log | 35 | 未知 | 1253.0 | 93.1 | 64.2 | 83.7 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a9 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 12.2 | 无 | 56,160 | 2,470,791 | 60,000 | engine log | 36 | 未知 | 1280.5 | 93.0 | 76.6 | 81.8 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a10 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 16.1 | 无 | 93,913 | 2,620,886 | 76,210 | engine log | 40 | 未知 | 1559.2 | 88.5 | 97.1 | 78.8 | 未知 | 未知 |
| 13 Claude Code opus low | opus-low-a1 | 是 | 是 | final | 0.799 | 0.819 | 0.025 | 0 | 1.8 | 无 | 62,746 | 253,501 | 12,412 | Claude Code stream result usage | 6 | 0.801 | 未知 | ≥117.6 | 567.4 | 112.2 | claude-opus-5-5 | standard 7 |
| 13 Claude Code opus low | opus-low-a2 | 是 | 是 | final | 0.823 | 0.842 | 0.023 | 0 | 2.7 | 无 | 55,215 | 186,902 | 14,524 | Claude Code stream result usage | 5 | 0.770 | 未知 | ≥117.9 | 347.0 | 91.3 | claude-opus-5-5 | standard 6 |
| 13 Claude Code opus low | opus-low-a3 | 是 | 是 | final | 0.839 | 0.839 | 0.000 | 0 | 2.8 | 无 | 57,717 | 154,051 | 14,604 | Claude Code stream result usage | 5 | 0.785 | 未知 | ≥108.9 | 349.5 | 88.4 | claude-opus-5-5 | standard 5 |
| 13 Claude Code opus low | opus-low-a4 | 是 | 是 | final | 0.819 | 0.839 | 0.024 | 0 | 3.4 | 无 | 58,500 | 196,905 | 13,338 | Claude Code stream result usage | 5 | 0.774 | 未知 | ≥101.4 | 289.3 | 66.0 | claude-opus-5-5 | standard 6 |
| 13 Claude Code opus low | opus-low-a5 | 是 | 是 | final | 0.870 | 0.892 | 0.024 | 0 | 3.9 | 无 | 59,540 | 267,329 | 13,858 | Claude Code stream result usage | 6 | 0.807 | 未知 | ≥108.7 | 253.3 | 59.0 | claude-opus-5-5 | standard 7 |
| 14 Claude Code opus medium | opus-medium-a1 | 是 | 是 | final | 0.839 | 0.839 | 0.000 | 0 | 2.8 | 无 | 67,977 | 317,642 | 19,237 | Claude Code stream result usage | 7 | 0.992 | 未知 | ≥119.1 | 408.0 | 115.5 | claude-opus-5-5 | standard 8 |
| 14 Claude Code opus medium | opus-medium-a2 | 是 | 是 | final | 0.845 | 0.845 | 0.000 | 0 | 4.3 | 无 | 72,463 | 400,687 | 20,514 | Claude Code stream result usage | 9 | 1.070 | 未知 | ≥116.3 | 280.8 | 79.5 | claude-opus-5-5 | standard 10 |
| 14 Claude Code opus medium | opus-medium-a3 | 是 | 是 | final | 0.887 | 0.887 | 0.000 | 0 | 4.0 | 无 | 67,333 | 320,409 | 20,068 | Claude Code stream result usage | 9 | 1.004 | 未知 | ≥95.0 | 278.1 | 82.9 | claude-opus-5-5 | standard 8 |
| 14 Claude Code opus medium | opus-medium-a4 | 是 | 是 | final | 0.851 | 0.851 | 0.000 | 0 | 5.1 | 无 | 69,939 | 306,200 | 19,091 | Claude Code stream result usage | 8 | 1.003 | 未知 | ≥100.3 | 230.7 | 63.0 | claude-opus-5-5 | standard 8 |
| 14 Claude Code opus medium | opus-medium-a5 | 是 | 是 | final | 0.856 | 0.856 | 0.000 | 0 | 5.7 | 无 | 81,009 | 561,082 | 22,621 | Claude Code stream result usage | 10 | 1.213 | 未知 | ≥101.7 | 238.0 | 66.5 | claude-opus-5-5 | standard 11 |
| 15 Claude Code opus high | opus-high-a1 | 是 | 是 | final | 0.887 | 0.887 | 0.000 | 0 | 6.0 | 无 | 80,950 | 492,960 | 34,280 | Claude Code stream result usage | 10 | 1.432 | 未知 | ≥114.8 | 224.3 | 95.0 | claude-opus-5-5 | standard 10 |
| 15 Claude Code opus high | opus-high-a2 | 是 | 是 | final | 0.876 | 0.876 | 0.000 | 0 | 6.2 | 无 | 86,567 | 564,396 | 29,616 | Claude Code stream result usage | 10 | 1.398 | 未知 | ≥105.5 | 232.9 | 79.7 | claude-opus-5-5 | standard 11 |
| 15 Claude Code opus high | opus-high-a3 | 是 | 是 | final | 0.872 | 0.893 | 0.024 | 0 | 6.8 | 无 | 80,732 | 535,835 | 27,782 | Claude Code stream result usage | 11 | 1.309 | 未知 | ≥95.4 | 197.9 | 68.1 | claude-opus-5-5 | standard 12 |
| 15 Claude Code opus high | opus-high-a4 | 是 | 是 | final | 0.847 | 0.864 | 0.020 | 0 | 7.2 | 无 | 92,692 | 686,265 | 27,538 | Claude Code stream result usage | 12 | 1.429 | 未知 | ≥110.1 | 214.7 | 63.8 | claude-opus-5-5 | standard 13 |
| 15 Claude Code opus high | opus-high-a5 | 是 | 是 | final | 0.896 | 0.896 | 0.000 | 0 | 10.3 | 无 | 97,595 | 1,012,476 | 48,614 | Claude Code stream result usage | 17 | 1.955 | 未知 | ≥121.1 | 158.6 | 79.0 | claude-opus-5-5 | standard 17 |
| 16 Claude Code sonnet low | sonnet-low-a1 | 是 | 是 | final | 0.811 | 0.836 | 0.030 | 0 | 2.3 | 无 | 64,036 | 296,926 | 16,641 | Claude Code stream result usage | 8 | 0.452 | 未知 | ≥129.8 | 471.4 | 122.5 | claude-sonnet-5-5 | standard 8 |
| 16 Claude Code sonnet low | sonnet-low-a2 | 是 | 是 | final | 0.822 | 0.847 | 0.029 | 0 | 4.2 | 无 | 61,568 | 309,857 | 16,402 | Claude Code stream result usage | 9 | 0.441 | 未知 | ≥116.6 | 246.4 | 65.6 | claude-sonnet-5-5 | standard 8 |
| 16 Claude Code sonnet low | sonnet-low-a3 | 是 | 是 | final | 0.811 | 0.836 | 0.030 | 0 | 3.2 | 无 | 56,228 | 257,180 | 15,384 | Claude Code stream result usage | 7 | 0.404 | 未知 | ≥126.2 | 289.9 | 79.3 | claude-sonnet-5-5 | standard 7 |
| 16 Claude Code sonnet low | sonnet-low-a4 | 是 | 是 | final | 0.797 | 0.824 | 0.033 | 0 | 2.9 | 无 | 57,580 | 221,124 | 15,309 | Claude Code stream result usage | 6 | 0.405 | 未知 | ≥117.0 | 327.4 | 87.0 | claude-sonnet-5-5 | standard 7 |
| 16 Claude Code sonnet low | sonnet-low-a5 | 是 | 是 | final | 0.827 | 0.854 | 0.031 | 0 | 4.3 | 无 | 56,395 | 318,627 | 15,790 | Claude Code stream result usage | 8 | 0.415 | 未知 | ≥96.7 | 216.4 | 60.6 | claude-sonnet-5-5 | standard 8 |
| 17 Claude Code sonnet medium | sonnet-medium-a1 | 是 | 是 | final | 0.861 | 0.885 | 0.027 | 0 | 2.5 | 无 | 70,888 | 283,330 | 20,106 | Claude Code stream result usage | 8 | 0.513 | 未知 | ≥137.7 | 467.6 | 132.6 | claude-sonnet-5-5 | standard 7 |
| 17 Claude Code sonnet medium | sonnet-medium-a2 | 是 | 是 | final | 0.851 | 0.875 | 0.028 | 0 | 3.7 | 无 | 58,743 | 299,997 | 17,503 | Claude Code stream result usage | 7 | 0.440 | 未知 | ≥142.3 | 263.7 | 78.6 | claude-sonnet-5-5 | standard 8 |
| 17 Claude Code sonnet medium | sonnet-medium-a3 | 是 | 是 | final | 0.883 | 0.883 | 0.000 | 0 | 4.2 | 无 | 64,887 | 356,414 | 19,988 | Claude Code stream result usage | 9 | 0.495 | 未知 | ≥109.3 | 255.3 | 78.7 | claude-sonnet-5-5 | standard 9 |
| 17 Claude Code sonnet medium | sonnet-medium-a4 | 是 | 是 | final | 0.733 | 0.750 | 0.023 | 0 | 3.4 | 无 | 61,133 | 204,330 | 18,677 | Claude Code stream result usage | 7 | 0.452 | 未知 | ≥133.5 | 300.3 | 91.8 | claude-sonnet-5-5 | standard 6 |
| 17 Claude Code sonnet medium | sonnet-medium-a5 | 是 | 是 | final | 0.830 | 0.854 | 0.028 | 0 | 4.0 | 无 | 63,628 | 315,733 | 19,864 | Claude Code stream result usage | 8 | 0.485 | 未知 | ≥116.5 | 265.6 | 82.9 | claude-sonnet-5-5 | standard 8 |
| 18 Claude Code sonnet high | sonnet-high-a1 | 是 | 是 | final | 0.862 | 0.883 | 0.024 | 0 | 4.4 | 无 | 92,375 | 581,298 | 42,758 | Claude Code stream result usage | 12 | 0.855 | 未知 | ≥165.1 | 349.2 | 161.6 | claude-sonnet-5-5 | standard 11 |
| 18 Claude Code sonnet high | sonnet-high-a2 | 是 | 是 | final | 0.852 | 0.873 | 0.024 | 0 | 4.3 | 无 | 67,127 | 329,877 | 23,846 | Claude Code stream result usage | 8 | 0.540 | 未知 | ≥147.0 | 258.0 | 91.6 | claude-sonnet-5-5 | standard 8 |
| 18 Claude Code sonnet high | sonnet-high-a3 | 是 | 是 | final | 0.857 | 0.878 | 0.023 | 0 | 4.3 | 无 | 70,108 | 210,749 | 26,827 | Claude Code stream result usage | 8 | 0.570 | 未知 | ≥131.5 | 268.7 | 102.8 | claude-sonnet-5-5 | standard 6 |
| 18 Claude Code sonnet high | sonnet-high-a4 | 是 | 是 | final | 0.836 | 0.859 | 0.027 | 0 | 5.6 | 无 | 73,504 | 451,379 | 26,478 | Claude Code stream result usage | 11 | 0.604 | 未知 | ≥132.7 | 217.9 | 78.5 | claude-sonnet-5-5 | standard 10 |
| 18 Claude Code sonnet high | sonnet-high-a5 | 是 | 是 | final | 0.847 | 0.867 | 0.023 | 0 | 5.3 | 无 | 77,206 | 545,689 | 31,322 | Claude Code stream result usage | 12 | 0.677 | 未知 | ≥147.1 | 243.7 | 98.9 | claude-sonnet-5-5 | standard 11 |
| 19 Claude Code haiku low | haiku-low-a1 | 是 | 是 | final | 0.874 | 0.874 | 0.000 | 0 | 5.5 | 无 | 118,442 | 787,455 | 71,624 | Claude Code stream result usage | 13 | 0.179 | 未知 | ≥244.5 | 361.5 | 218.6 | claude-haiku-5-5 | standard 13 |
| 19 Claude Code haiku low | haiku-low-a2 | 是 | 是 | final | 0.833 | 0.833 | 0.000 | 0 | 5.6 | 无 | 112,017 | 589,576 | 67,147 | Claude Code stream result usage | 10 | 0.127 | 未知 | ≥259.6 | 331.6 | 198.8 | claude-haiku-5-5 | standard 11 |
| 19 Claude Code haiku low | haiku-low-a3 | 是 | 是 | final | 0.876 | 0.876 | 0.000 | 0 | 5.6 | 无 | 109,554 | 690,320 | 55,795 | Claude Code stream result usage | 11 | 0.100 | 未知 | ≥242.6 | 326.0 | 166.0 | claude-haiku-5-5 | standard 11 |
| 19 Claude Code haiku low | haiku-low-a4 | 是 | 是 | final | 0.874 | 0.874 | 0.000 | 0 | 7.3 | 无 | 117,632 | 654,328 | 69,976 | Claude Code stream result usage | 13 | 0.182 | 未知 | ≥223.0 | 269.9 | 160.6 | claude-haiku-5-5 | standard 12 |
| 19 Claude Code haiku low | haiku-low-a5 | 是 | 是 | final | 0.858 | 0.858 | 0.000 | 0 | 4.7 | 无 | 107,240 | 307,457 | 63,721 | Claude Code stream result usage | 8 | 0.113 | 未知 | ≥246.3 | 382.0 | 227.0 | claude-haiku-5-5 | standard 7 |
| 20 Claude Code haiku medium | haiku-medium-a1 | 是 | 是 | final | 0.892 | 0.892 | 0.000 | 0 | 5.8 | 无 | 125,920 | 668,908 | 78,334 | Claude Code stream result usage | 12 | 0.202 | 未知 | ≥260.6 | 364.8 | 226.9 | claude-haiku-5-5 | standard 12 |
| 20 Claude Code haiku medium | haiku-medium-a2 | 是 | 是 | final | 0.866 | 0.866 | 0.000 | 0 | 5.8 | 无 | 116,142 | 409,212 | 70,495 | Claude Code stream result usage | 10 | 0.125 | 未知 | ≥233.0 | 334.9 | 203.2 | claude-haiku-5-5 | standard 9 |
| 20 Claude Code haiku medium | haiku-medium-a3 | 是 | 是 | final | 0.875 | 0.875 | 0.000 | 0 | 8.0 | 无 | 134,020 | 741,280 | 80,080 | Claude Code stream result usage | 15 | 0.162 | 未知 | ≥239.2 | 280.7 | 167.7 | claude-haiku-5-5 | standard 13 |
| 20 Claude Code haiku medium | haiku-medium-a4 | 是 | 是 | final | 0.850 | 0.871 | 0.024 | 0 | 6.5 | 无 | 118,810 | 635,759 | 73,908 | Claude Code stream result usage | 18 | 0.099 | 未知 | ≥230.2 | 304.0 | 189.1 | claude-haiku-5-5 | standard 12 |
| 20 Claude Code haiku medium | haiku-medium-a5 | 是 | 是 | final | 0.889 | 0.889 | 0.000 | 0 | 7.4 | 无 | 121,933 | 486,692 | 75,669 | Claude Code stream result usage | 14 | 0.134 | 未知 | ≥240.7 | 274.4 | 170.3 | claude-haiku-5-5 | standard 11 |
| 21 Claude Code haiku high | haiku-high-a1 | 是 | 是 | final | 0.874 | 0.874 | 0.000 | 0 | 9.6 | 无 | 189,199 | 2,028,303 | 116,416 | Claude Code stream result usage | 21 | 0.413 | 未知 | ≥237.0 | 328.0 | 201.8 | claude-haiku-5-5 | standard 17 |
| 21 Claude Code haiku high | haiku-high-a2 | 是 | 是 | final | 0.886 | 0.886 | 0.000 | 0 | 9.8 | 无 | 159,730 | 1,100,292 | 107,787 | Claude Code stream result usage | 21 | 0.314 | 未知 | ≥239.8 | 270.5 | 182.5 | claude-haiku-5-5 | standard 14 |
| 21 Claude Code haiku high | haiku-high-a3 | 是 | 是 | final | 0.863 | 0.863 | 0.000 | 0 | 10.3 | 无 | 144,329 | 1,109,904 | 96,337 | Claude Code stream result usage | 15 | 0.286 | 未知 | ≥240.4 | 234.5 | 156.5 | claude-haiku-5-5 | standard 14 |
| 21 Claude Code haiku high | haiku-high-a4 | 是 | 是 | final | 0.824 | 0.824 | 0.000 | 0 | 9.5 | 无 | 144,098 | 1,056,190 | 94,253 | Claude Code stream result usage | 20 | 0.249 | 未知 | ≥230.1 | 252.3 | 165.0 | claude-haiku-5-5 | standard 17 |
| 21 Claude Code haiku high | haiku-high-a5 | 是 | 是 | final | 0.861 | 0.861 | 0.000 | 0 | 7.2 | 无 | 149,953 | 715,060 | 102,329 | Claude Code stream result usage | 15 | 0.222 | 未知 | ≥255.5 | 345.9 | 236.1 | claude-haiku-5-5 | standard 13 |
| 22 Claude Code deepseek-flash low | cc-low-a1 | 是 | 是 | final | 0.816 | 0.816 | 0.000 | 0 | 9.8 | 无 | 45,829 | 1,770,752 | 80,450 | Claude Code stream result usage | 32 | 0.060（¥0.403） | 未知 | ≥210.7 | 78.0 | 137.0 | deepseek-flash | standard 26 |
| 22 Claude Code deepseek-flash low | cc-low-a2 | 是 | 是 | final | 0.639 | 0.639 | 0.000 | 0 | 9.2 | 无 | 40,865 | 488,320 | 62,392 | Claude Code stream result usage | 18 | 0.045（¥0.300） | 未知 | ≥181.6 | 74.2 | 113.3 | deepseek-flash | standard 13 |
| 22 Claude Code deepseek-flash low | cc-low-a3 | 是 | 是 | final | 0.709 | 0.709 | 0.000 | 0 | 6.8 | 无 | 36,890 | 795,392 | 47,483 | Claude Code stream result usage | 28 | 0.036（¥0.243） | 未知 | ≥199.7 | 90.3 | 116.2 | deepseek-flash | standard 21 |
| 22 Claude Code deepseek-flash low | cc-low-a4 | 是 | 是 | final | 0.726 | 0.726 | 0.000 | 0 | 6.3 | 无 | 53,748 | 910,592 | 57,652 | Claude Code stream result usage | 25 | 0.045（¥0.303） | 未知 | ≥233.0 | 141.9 | 152.2 | deepseek-flash | standard 15 |
| 22 Claude Code deepseek-flash low | cc-low-a5 | 是 | 是 | final | 0.631 | 0.631 | 0.000 | 0 | 8.5 | 无 | 44,112 | 1,313,280 | 62,826 | Claude Code stream result usage | 31 | 0.048（¥0.322） | 未知 | ≥230.1 | 86.3 | 122.9 | deepseek-flash | standard 22 |
| 23 Claude Code deepseek-flash high | cc-medium-a1 | 是 | 是 | final | 0.698 | 0.698 | 0.000 | 0 | 10.1 | 无 | 44,575 | 1,438,080 | 65,716 | Claude Code stream result usage | 40 | 0.050（¥0.336） | 未知 | ≥205.7 | 73.5 | 108.3 | deepseek-flash | standard 26 |
| 23 Claude Code deepseek-flash high | cc-high-a1 | 是 | 是 | final | 0.805 | 0.805 | 0.000 | 0 | 14.8 | 无 | 48,801 | 2,116,480 | 85,595 | Claude Code stream result usage | 40 | 0.065（¥0.433） | 未知 | ≥182.8 | 54.9 | 96.2 | deepseek-flash | standard 32 |
| 23 Claude Code deepseek-flash high | cc-high-a2 | 是 | 是 | final | 0.629 | 0.629 | 0.000 | 0 | 8.7 | 无 | 50,524 | 1,253,248 | 89,739 | Claude Code stream result usage | 33 | 0.065（¥0.434） | 未知 | ≥225.1 | 96.6 | 171.7 | deepseek-flash | standard 19 |
| 23 Claude Code deepseek-flash high | cc-medium-a2 | 是 | 是 | final | 0.731 | 0.731 | 0.000 | 0 | 13.4 | 无 | 67,269 | 1,676,672 | 106,891 | Claude Code stream result usage | 34 | 0.079（¥0.528） | 未知 | ≥218.3 | 83.7 | 133.0 | deepseek-flash | standard 27 |
| 23 Claude Code deepseek-flash high | cc-medium-a3 | 是 | 是 | final | 0.833 | 0.833 | 0.000 | 0 | 14.5 | 无 | 52,363 | 2,296,704 | 112,984 | Claude Code stream result usage | 42 | 0.083（¥0.550） | 未知 | ≥207.8 | 60.2 | 129.9 | deepseek-flash | standard 37 |
| 23 Claude Code deepseek-flash high | cc-high-a3 | 是 | 是 | final | 0.863 | 0.863 | 0.000 | 0 | 11.0 | 无 | 54,911 | 2,128,128 | 77,526 | Claude Code stream result usage | 44 | 0.061（¥0.408） | 未知 | ≥180.6 | 83.0 | 117.2 | deepseek-flash | standard 32 |
| 23 Claude Code deepseek-flash high | cc-high-a4 | 是 | 是 | final | 0.733 | 0.733 | 0.000 | 0 | 7.6 | 无 | 59,647 | 1,321,728 | 77,120 | Claude Code stream result usage | 28 | 0.059（¥0.395） | 未知 | ≥242.8 | 131.1 | 169.4 | deepseek-flash | standard 19 |
| 23 Claude Code deepseek-flash high | cc-medium-a4 | 是 | 是 | final | 0.642 | 0.642 | 0.000 | 0 | 10.3 | 无 | 49,523 | 2,136,320 | 80,506 | Claude Code stream result usage | 36 | 0.062（¥0.414） | 未知 | ≥211.8 | 80.1 | 130.3 | deepseek-flash | standard 32 |
| 24 Claude Code deepseek-flash max | cc-max-a1 | 是 | 是 | final | 0.843 | 0.843 | 0.000 | 0 | 13.5 | 无 | 48,645 | 2,314,752 | 139,685 | Claude Code stream result usage | 55 | 0.098（¥0.654） | 未知 | ≥228.2 | 60.2 | 172.8 | deepseek-flash | standard 32 |
| 24 Claude Code deepseek-flash max | cc-max-a2 | 是 | 是 | final | 0.877 | 0.877 | 0.000 | 0 | 16.4 | 无 | 95,010 | 2,613,760 | 145,911 | Claude Code stream result usage | 90 | 0.110（¥0.731） | 未知 | ≥209.0 | 96.7 | 148.5 | deepseek-flash | standard 41 |
| 24 Claude Code deepseek-flash max | cc-max-a3 | 是 | 是 | final | 0.735 | 0.735 | 0.000 | 0 | 8.4 | 无 | 57,281 | 1,392,640 | 89,392 | Claude Code stream result usage | 54 | 0.066（¥0.443） | 未知 | ≥216.4 | 113.6 | 177.2 | deepseek-flash | standard 21 |
| 24 Claude Code deepseek-flash max | cc-max-a4 | 是 | 是 | final | 0.855 | 0.855 | 0.000 | 0 | 13.0 | 无 | 57,636 | 1,759,616 | 117,551 | Claude Code stream result usage | 34 | 0.084（¥0.563） | 未知 | ≥218.7 | 73.7 | 150.3 | deepseek-flash | standard 25 |
| 24 Claude Code deepseek-flash max | cc-max-a5 | 是 | 是 | final | 0.776 | 0.776 | 0.000 | 0 | 28.4 | 无 | 104,612 | 4,411,008 | 182,121 | Claude Code stream result usage | 93 | 0.138（¥0.921） | 未知 | ≥154.0 | 61.4 | 106.9 | deepseek-flash | standard 58 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a1 | 是 | 是 | final | 0.812 | 0.812 | 0.000 | 0 | 15.8 | 无 | 101,927 | 4,577,226 | 75,500 | engine log | 62 | 3.932 | 1268.0 | 89.6 | 107.8 | 79.8 | qwen3.8-flash-next-iq3_xxs | not-returned 45 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a2 | 是 | 是 | final | 0.690 | 0.690 | 0.000 | 0 | 13.8 | 无 | 58,852 | 3,457,630 | 67,272 | engine log | 59 | 3.431 | 1085.1 | 89.2 | 71.1 | 81.2 | qwen3.8-flash-next-iq3_xxs | not-returned 44 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a3 | 是 | 是 | final | 0.608 | 0.608 | 0.000 | 0 | 21.2 | 无 | 81,258 | 5,376,440 | 99,249 | engine log | 72 | 4.991 | 1090.2 | 85.3 | 64.0 | 78.2 | qwen3.8-flash-next-iq3_xxs | not-returned 53 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a4 | 是 | 是 | final | 0.254 | 0.254 | 0.000 | 0 | 13.1 | 无 | 68,580 | 3,336,570 | 66,261 | engine log | 45 | 3.399 | 1282.9 | 93.5 | 87.2 | 84.3 | qwen3.8-flash-next-iq3_xxs | not-returned 39 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a5 | 是 | 是 | final | 0.492 | 0.507 | 0.029 | 0 | 20.2 | 无 | 84,662 | 6,554,905 | 99,022 | engine log | 75 | 5.531 | 1041.3 | 91.4 | 69.9 | 81.7 | qwen3.8-flash-next-iq3_xxs | not-returned 67 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a6 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 16.8 | 无 | 67,220 | 4,858,738 | 81,741 | engine log | 75 | 4.399 | 1025.3 | 89.4 | 66.8 | 81.3 | qwen3.8-flash-next-iq3_xxs | not-returned 53 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a7 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 13.6 | 无 | 73,152 | 4,876,040 | 64,981 | engine log | 73 | 4.024 | 1090.1 | 89.6 | 89.8 | 79.8 | qwen3.8-flash-next-iq3_xxs | not-returned 55 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a8 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 12.8 | 无 | 56,723 | 3,329,780 | 64,711 | engine log | 64 | 3.254 | 1025.3 | 93.1 | 73.7 | 84.0 | qwen3.8-flash-next-iq3_xxs | not-returned 46 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a9 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 11.5 | 无 | 67,328 | 3,473,072 | 57,307 | engine log | 61 | 3.196 | 1173.9 | 92.7 | 97.2 | 82.7 | qwen3.8-flash-next-iq3_xxs | not-returned 42 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a10 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 16.9 | 无 | 74,200 | 4,942,166 | 83,906 | engine log | 56 | 4.563 | 1128.6 | 91.3 | 73.4 | 83.0 | qwen3.8-flash-next-iq3_xxs | not-returned 54 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a1 | 是 | 是 | final | 0.572 | 0.572 | 0.000 | 0 | 12.5 | 无 | 52,225 | 2,191,688 | 63,193 | engine log | 46 | 2.629 | 1285.7 | 90.7 | 69.5 | 84.1 | qwen3.8-flash-next-iq3_xxs | not-returned 28 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a2 | 是 | 是 | final | 0.555 | 0.588 | 0.055 | 0 | 27.8 | 无 | 74,417 | 2,922,729 | 85,354 | engine log | 56 | 3.565 | 1373.7 | 94.3 | 44.5 | 51.1 | qwen3.8-flash-next-iq3_xxs | not-returned 31 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a3 | 是 | 是 | final | 0.394 | 0.394 | 0.000 | 0 | 9.8 | 无 | 60,705 | 1,716,964 | 49,435 | engine log | 28 | 2.166 | 1534.6 | 92.6 | 103.0 | 83.9 | qwen3.8-flash-next-iq3_xxs | not-returned 23 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a4 | 是 | 是 | final | 0.512 | 0.512 | 0.000 | 0 | 20.5 | 无 | 112,082 | 2,783,509 | 106,349 | engine log | 53 | 4.189 | 1522.2 | 93.5 | 91.1 | 86.4 | qwen3.8-flash-next-iq3_xxs | not-returned 35 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a5 | 是 | 是 | final | 0.595 | 0.595 | 0.000 | 0 | 9.8 | 无 | 58,156 | 1,311,483 | 52,054 | engine log | 26 | 2.081 | 1555.1 | 96.5 | 98.8 | 88.4 | qwen3.8-flash-next-iq3_xxs | not-returned 20 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a6 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 16.5 | 无 | 79,800 | 2,974,484 | 81,731 | engine log | 40 | 3.566 | 1361.8 | 91.0 | 80.8 | 82.8 | qwen3.8-flash-next-iq3_xxs | not-returned 36 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a7 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 13.2 | 无 | 51,226 | 1,724,172 | 63,962 | engine log | 45 | 2.442 | 1413.3 | 85.4 | 64.6 | 80.6 | qwen3.8-flash-next-iq3_xxs | not-returned 22 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a8 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 33.7 | 无 | 95,255 | 5,087,258 | 173,693 | engine log | 73 | 7.092 | 1145.2 | 91.2 | 47.1 | 85.9 | qwen3.8-flash-next-iq3_xxs | not-returned 67 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a9 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 10.9 | 无 | 67,757 | 2,110,515 | 51,276 | engine log | 37 | 2.400 | 1353.7 | 86.7 | 103.4 | 78.3 | qwen3.8-flash-next-iq3_xxs | not-returned 30 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a10 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 13.4 | 无 | 76,904 | 2,024,474 | 62,054 | engine log | 45 | 2.597 | 1403.6 | 83.6 | 95.3 | 76.9 | qwen3.8-flash-next-iq3_xxs | not-returned 28 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a1 | 是 | 是 | final | 0.568 | 0.568 | 0.000 | 0 | 18.0 | 无 | 52,845 | 2,303,379 | 96,586 | engine log | 61 | 3.551 | 1341.8 | 95.1 | 49.1 | 89.7 | qwen3.8-flash-next-iq3_xxs | not-returned 27 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a2 | 是 | 是 | final | 0.589 | 0.589 | 0.000 | 0 | 15.9 | 无 | 55,537 | 3,692,805 | 81,680 | engine log | 46 | 4.020 | 1171.0 | 93.1 | 58.3 | 85.7 | qwen3.8-flash-next-iq3_xxs | not-returned 40 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a3 | 是 | 是 | final | 0.441 | 0.441 | 0.000 | 0 | 9.0 | 无 | 69,121 | 1,636,846 | 42,594 | engine log | 33 | 2.163 | 1529.1 | 89.6 | 128.6 | 79.3 | qwen3.8-flash-next-iq3_xxs | not-returned 28 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a4 | 是 | 是 | final | 0.846 | 0.846 | 0.000 | 0 | 13.1 | 无 | 52,531 | 1,703,173 | 68,533 | engine log | 44 | 2.655 | 1425.2 | 93.4 | 67.1 | 87.5 | qwen3.8-flash-next-iq3_xxs | not-returned 25 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a5 | 是 | 是 | final | 0.561 | 0.561 | 0.000 | 0 | 12.8 | 无 | 68,645 | 2,286,839 | 65,751 | engine log | 34 | 2.997 | 1426.0 | 94.5 | 89.7 | 85.9 | qwen3.8-flash-next-iq3_xxs | not-returned 32 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a6 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 15.0 | 无 | 50,447 | 2,214,618 | 74,368 | engine log | 35 | 3.059 | 1233.7 | 87.8 | 56.0 | 82.6 | qwen3.8-flash-next-iq3_xxs | not-returned 31 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a7 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 17.2 | 无 | 68,012 | 2,336,513 | 85,620 | engine log | 34 | 3.384 | 1427.4 | 88.2 | 65.9 | 83.0 | qwen3.8-flash-next-iq3_xxs | not-returned 30 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a8 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 17.8 | 无 | 68,264 | 2,235,180 | 89,830 | engine log | 36 | 3.519 | 1373.4 | 89.7 | 64.0 | 84.2 | qwen3.8-flash-next-iq3_xxs | not-returned 31 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a9 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 16.2 | 无 | 84,037 | 2,212,193 | 79,824 | engine log | 30 | 3.262 | 1604.9 | 87.9 | 86.4 | 82.1 | qwen3.8-flash-next-iq3_xxs | not-returned 27 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a10 | 是 | 否 | unscored | 未知 | 未知 | 未知 |  | 14.7 | 无 | 74,034 | 1,289,828 | 70,900 | engine log | 41 | 2.594 | 1652.8 | 85.2 | 83.9 | 80.3 | qwen3.8-flash-next-iq3_xxs | not-returned 20 |

### Spec Readiness v4.3（SR）

| 配置 | 实例 | 有效 | 进主统计 | 计分 | 分数 | rawScore | f | 修复 | 耗时（分钟） | 时限（秒） | 未缓存 | 缓存 | 输出 | token 来源 | 工具调用 | 费用（美元；括号内人民币） | 引擎输入 tok/s | 引擎输出 tok/s | 任务平均输入 tok/s | 任务平均输出 tok/s | 模型 ID | tier |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 Codex gpt-6.1-sol low | sol-low-a1 | 是 | 是 | final | 0.847 | 0.847 | 0.000 | 0 | 3.4 | 无 | 127,581 | 1,208,704 | 8,077 | API usage (relay) | 22 | 只报 token | 未知 | ≥40.3 | 631.6 | 40.0 | gpt-6.1-sol | default 24 |
| 1 Codex gpt-6.1-sol low | sol-low-a2 | 是 | 是 | final | 0.765 | 0.765 | 0.000 | 0 | 3.7 | 无 | 139,518 | 1,039,232 | 7,991 | API usage (relay) | 20 | 只报 token | 未知 | ≥36.1 | 620.8 | 35.6 | gpt-6.1-sol | default 22 |
| 1 Codex gpt-6.1-sol low | sol-low-a3 | 是 | 是 | final | 0.832 | 0.832 | 0.000 | 0 | 5.6 | 无 | 159,929 | 1,773,184 | 9,873 | API usage (relay) | 28 | 只报 token | 未知 | ≥30.0 | 477.5 | 29.5 | gpt-6.1-sol | default 29 |
| 1 Codex gpt-6.1-sol low | sol-low-a4 | 是 | 是 | final | 0.801 | 0.801 | 0.000 | 0 | 5.1 | 无 | 138,823 | 1,238,400 | 9,119 | API usage (relay) | 21 | 只报 token | 未知 | ≥31.0 | 453.9 | 29.8 | gpt-6.1-sol | default 23 |
| 1 Codex gpt-6.1-sol low | sol-low-a5 | 是 | 是 | final | 0.841 | 0.841 | 0.000 | 0 | 7.4 | 无 | 163,574 | 2,147,200 | 11,221 | API usage (relay) | 33 | 只报 token | 未知 | ≥25.3 | 366.6 | 25.1 | gpt-6.1-sol | default 35 |
| 2 Codex gpt-6.1-sol medium | sol-medium-a1 | 否：void | 否 | — | 未知 | 未知 | 未知 |  | 未知 | 无 | 未知 | 未知 | 未知 | 未知 | 未知 | 只报 token | 未知 | ≥39.5 | 未知 | 未知 | 未知 | 未知 |
| 2 Codex gpt-6.1-sol medium | sol-medium-a2 | 是 | 是 | final | 0.679 | 0.679 | 0.000 | 0 | 4.8 | 无 | 164,523 | 1,549,824 | 11,504 | API usage (relay) | 26 | 只报 token | 未知 | ≥40.0 | 566.0 | 39.6 | gpt-6.1-sol | default 28 |
| 2 Codex gpt-6.1-sol medium | sol-medium-a3 | 是 | 是 | final | 0.840 | 0.840 | 0.000 | 0 | 4.8 | 无 | 151,781 | 1,873,408 | 10,504 | API usage (relay) | 30 | 只报 token | 未知 | ≥37.0 | 530.6 | 36.7 | gpt-6.1-sol | default 32 |
| 2 Codex gpt-6.1-sol medium | sol-medium-a4 | 是 | 是 | final | 0.811 | 0.811 | 0.000 | 0 | 7.1 | 无 | 158,500 | 1,811,840 | 12,906 | API usage (relay) | 29 | 只报 token | 未知 | ≥30.6 | 373.7 | 30.4 | gpt-6.1-sol | default 31 |
| 2 Codex gpt-6.1-sol medium | sol-medium-a5 | 是 | 是 | final | 0.842 | 0.842 | 0.000 | 0 | 6.0 | 无 | 139,018 | 1,524,480 | 10,616 | API usage (relay) | 26 | 只报 token | 未知 | ≥29.7 | 386.1 | 29.5 | gpt-6.1-sol | default 28 |
| 2 Codex gpt-6.1-sol medium | sol-medium-a6 | 是 | 是 | final | 0.750 | 0.750 | 0.000 | 0 | 8.0 | 无 | 158,428 | 1,964,928 | 13,361 | API usage (relay) | 31 | 只报 token | 未知 | ≥28.2 | 331.8 | 28.0 | gpt-6.1-sol | default 33 |
| 3 Codex gpt-6.1-sol high | sol-high-a1 | 否：void | 否 | — | 未知 | 未知 | 未知 |  | 未知 | 无 | 未知 | 未知 | 未知 | 未知 | 未知 | 只报 token | 未知 | ≥41.7 | 未知 | 未知 | 未知 | 未知 |
| 3 Codex gpt-6.1-sol high | sol-high-a2 | 是 | 是 | final | 0.821 | 0.821 | 0.000 | 0 | 7.9 | 无 | 161,171 | 2,247,296 | 18,782 | API usage (relay) | 35 | 只报 token | 未知 | ≥40.1 | 339.3 | 39.5 | gpt-6.1-sol | default 37 |
| 3 Codex gpt-6.1-sol high | sol-high-a3 | 是 | 是 | final | 0.773 | 0.773 | 0.000 | 0 | 8.9 | 无 | 164,004 | 2,588,288 | 18,928 | API usage (relay) | 39 | 只报 token | 未知 | ≥35.7 | 306.9 | 35.4 | gpt-6.1-sol | default 41 |
| 3 Codex gpt-6.1-sol high | sol-high-a4 | 是 | 是 | final | 0.850 | 0.850 | 0.000 | 0 | 8.8 | 无 | 163,054 | 2,318,208 | 17,134 | API usage (relay) | 34 | 只报 token | 未知 | ≥32.4 | 307.4 | 32.3 | gpt-6.1-sol | default 36 |
| 3 Codex gpt-6.1-sol high | sol-high-a5 | 是 | 是 | final | 0.702 | 0.702 | 0.000 | 0 | 16.1 | 无 | 185,024 | 3,534,464 | 29,020 | API usage (relay) | 48 | 只报 token | 未知 | ≥30.2 | 191.5 | 30.0 | gpt-6.1-sol | default 50 |
| 3 Codex gpt-6.1-sol high | sol-high-a6 | 是 | 是 | final | 0.869 | 0.869 | 0.000 | 0 | 11.5 | 无 | 187,163 | 3,067,904 | 18,816 | API usage (relay) | 43 | 只报 token | 未知 | ≥27.5 | 272.2 | 27.4 | gpt-6.1-sol | default 45 |
| 4 Codex gpt-6-luna low | luna-low-a1 | 否：void | 否 | — | 未知 | 未知 | 未知 |  | 未知 | 无 | 未知 | 未知 | 未知 | 未知 | 未知 | 只报 token | 未知 | ≥89.6 | 未知 | 未知 | 未知 | 未知 |
| 4 Codex gpt-6-luna low | luna-low-a2 | 是 | 是 | final | 0.209 | 0.209 | 0.000 | 0 | 2.6 | 无 | 149,877 | 1,481,728 | 11,020 | API usage (relay) | 28 | 只报 token | 未知 | ≥71.0 | 975.2 | 71.7 | gpt-6-luna | default 32 |
| 4 Codex gpt-6-luna low | luna-low-a3 | 是 | 是 | final | 0.020 | 0.020 | 0.000 | 0 | 3.2 | 无 | 163,740 | 2,370,944 | 11,882 | API usage (relay) | 36 | 只报 token | 未知 | ≥62.2 | 853.2 | 61.9 | gpt-6-luna | default 42 |
| 4 Codex gpt-6-luna low | luna-low-a4 | 是 | 是 | final | 0.276 | 0.276 | 0.000 | 0 | 2.9 | 无 | 169,066 | 1,423,104 | 11,487 | API usage (relay) | 24 | 只报 token | 未知 | ≥66.9 | 974.5 | 66.2 | gpt-6-luna | default 26 |
| 4 Codex gpt-6-luna low | luna-low-a5 | 是 | 是 | final | 0.125 | 0.125 | 0.000 | 0 | 2.6 | 无 | 124,321 | 905,216 | 8,118 | API usage (relay) | 19 | 只报 token | 未知 | ≥53.6 | 801.0 | 52.3 | gpt-6-luna | default 21 |
| 4 Codex gpt-6-luna low | luna-low-a6 | 是 | 是 | final | 0.085 | 0.085 | 0.000 | 0 | 4.0 | 无 | 189,606 | 2,207,360 | 10,565 | API usage (relay) | 31 | 只报 token | 未知 | ≥44.6 | 791.2 | 44.1 | gpt-6-luna | default 34 |
| 5 Codex gpt-6-luna medium | luna-medium-a1 | 是 | 是 | final | 0.229 | 0.229 | 0.000 | 0 | 1.7 | 无 | 125,444 | 822,912 | 8,499 | API usage (relay) | 17 | 只报 token | 未知 | ≥85.6 | 1195.5 | 81.0 | gpt-6-luna | default 19 |
| 5 Codex gpt-6-luna medium | luna-medium-a2 | 是 | 是 | final | 0.111 | 0.111 | 0.000 | 0 | 2.0 | 无 | 135,739 | 1,288,448 | 8,651 | API usage (relay) | 22 | 只报 token | 未知 | ≥73.6 | 1144.9 | 73.0 | gpt-6-luna | default 24 |
| 5 Codex gpt-6-luna medium | luna-medium-a3 | 是 | 是 | final | 0.556 | 0.556 | 0.000 | 0 | 4.5 | 无 | 175,329 | 1,454,848 | 18,160 | API usage (relay) | 24 | 只报 token | 未知 | ≥67.3 | 644.4 | 66.7 | gpt-6-luna | default 26 |
| 5 Codex gpt-6-luna medium | luna-medium-a4 | 是 | 是 | final | 0.102 | 0.102 | 0.000 | 0 | 2.5 | 无 | 131,957 | 859,264 | 7,328 | API usage (relay) | 18 | 只报 token | 未知 | ≥50.4 | 892.4 | 49.6 | gpt-6-luna | default 20 |
| 5 Codex gpt-6-luna medium | luna-medium-a5 | 是 | 是 | final | 0.304 | 0.304 | 0.000 | 0 | 4.5 | 无 | 132,147 | 1,420,416 | 13,502 | API usage (relay) | 26 | 只报 token | 未知 | ≥50.2 | 487.2 | 49.8 | gpt-6-luna | default 28 |
| 6 Codex gpt-6-luna high | luna-high-a1 | 是 | 是 | final | 0.375 | 0.375 | 0.000 | 0 | 3.6 | 无 | 155,618 | 1,608,064 | 18,495 | API usage (relay) | 28 | 只报 token | 未知 | ≥85.8 | 713.5 | 84.8 | gpt-6-luna | default 30 |
| 6 Codex gpt-6-luna high | luna-high-a2 | 是 | 是 | final | 0.495 | 0.495 | 0.000 | 0 | 3.5 | 无 | 147,085 | 1,466,112 | 18,852 | API usage (relay) | 27 | 只报 token | 未知 | ≥90.0 | 697.5 | 89.4 | gpt-6-luna | default 29 |
| 6 Codex gpt-6-luna high | luna-high-a3 | 否：invalid | 否 | — | 未知 | 未知 | 未知 |  | 4.5 | 无 | 150,670 | 997,760 | 17,185 | API usage (relay) | 20 | 只报 token | 未知 | ≥66.6 | 555.9 | 63.4 | gpt-6-luna | default 22、not-returned 1 |
| 6 Codex gpt-6-luna high | luna-high-a4 | 是 | 是 | final | 0.409 | 0.409 | 0.000 | 0 | 4.8 | 无 | 169,010 | 1,148,288 | 19,753 | API usage (relay) | 20 | 只报 token | 未知 | ≥67.6 | 581.8 | 68.0 | gpt-6-luna | default 22 |
| 6 Codex gpt-6-luna high | luna-high-a5 | 是 | 是 | final | 0.447 | 0.447 | 0.000 | 0 | 5.2 | 无 | 151,791 | 1,215,872 | 18,924 | API usage (relay) | 22 | 只报 token | 未知 | ≥62.3 | 483.8 | 60.3 | gpt-6-luna | default 24 |
| 6 Codex gpt-6-luna high | luna-high-a6 | 是 | 是 | final | 0.572 | 0.572 | 0.000 | 0 | 6.0 | 无 | 171,467 | 1,403,392 | 25,633 | API usage (relay) | 25 | 只报 token | 未知 | ≥72.0 | 476.1 | 71.2 | gpt-6-luna | default 27 |
| 7 Codex deepseek-flash low | codex-low-a1 | 否：invalid | 否 | — | 未知 | 未知 | 未知 |  | 62.1 | 无 | 未知 | 未知 | 未知 | 未知 | 147 | ≥0.559（¥3.724） | 未知 | ≥47.7 | 未知 | 未知 | deepseek-flash | default 732、not-returned 3 |
| 7 Codex deepseek-flash low | codex-low-a2 | 是 | 是 | final | 0.685 | 0.685 | 0.000 | 0 | 9.6 | 无 | 136,636 | 3,892,096 | 92,226 | API usage (relay) | 83 | 0.088（¥0.583） | 未知 | ≥161.5 | 237.8 | 160.5 | deepseek-flash | default 39 |
| 7 Codex deepseek-flash low | codex-low-a3 | 是 | 是 | final | 0.755 | 0.755 | 0.000 | 0 | 10.2 | 无 | 140,833 | 4,048,512 | 118,726 | API usage (relay) | 117 | 0.105（¥0.697） | 未知 | ≥195.3 | 229.7 | 193.6 | deepseek-flash | default 48 |
| 7 Codex deepseek-flash low | codex-low-a4 | 是 | 是 | final | 0.667 | 0.667 | 0.000 | 0 | 10.0 | 无 | 136,210 | 5,043,712 | 110,172 | API usage (relay) | 98 | 0.102（¥0.678） | 未知 | ≥185.3 | 227.2 | 183.8 | deepseek-flash | default 60 |
| 7 Codex deepseek-flash low | codex-low-a5 | 否：invalid | 否 | — | 未知 | 未知 | 未知 |  | 63.7 | 无 | 未知 | 未知 | 未知 | 未知 | 138 | ≥0.542（¥3.612） | 未知 | ≥63.1 | 未知 | 未知 | deepseek-flash | default 740、not-returned 3 |
| 7 Codex deepseek-flash low | codex-low-a6 | 是 | 是 | final | 0.718 | 0.718 | 0.000 | 0 | 15.1 | 无 | 154,478 | 3,520,128 | 109,412 | API usage (relay) | 96 | 0.099（¥0.662） | 未知 | ≥186.3 | 170.1 | 120.5 | deepseek-flash | default 38 |
| 7 Codex deepseek-flash low | codex-low-a7 | 是 | 是 | final | 0.632 | 0.632 | 0.000 | 0 | 10.8 | 无 | 163,647 | 4,175,744 | 109,704 | API usage (relay) | 99 | 0.103（¥0.686） | 未知 | ≥170.6 | 253.3 | 169.8 | deepseek-flash | default 53 |
| 8 Codex deepseek-flash high | codex-medium-a1 | 是 | 是 | final | 0.749 | 0.749 | 0.000 | 0 | 9.6 | 无 | 123,056 | 4,318,336 | 99,840 | API usage (relay) | 152 | 0.091（¥0.609） | 未知 | ≥173.5 | 212.7 | 172.6 | deepseek-flash | default 50 |
| 8 Codex deepseek-flash high | codex-high-a1 | 是 | 是 | final | 0.656 | 0.656 | 0.000 | 0 | 12.5 | 无 | 129,878 | 4,135,424 | 125,681 | API usage (relay) | 90 | 0.107（¥0.715） | 未知 | ≥168.2 | 173.2 | 167.6 | deepseek-flash | default 39、not-returned 1 |
| 8 Codex deepseek-flash high | codex-high-a2 | 是 | 是 | final | 0.674 | 0.674 | 0.000 | 0 | 9.4 | 无 | 132,947 | 3,728,896 | 101,233 | API usage (relay) | 120 | 0.092（¥0.613） | 未知 | ≥179.8 | 235.0 | 178.9 | deepseek-flash | default 43 |
| 8 Codex deepseek-flash high | codex-high-a3 | 是 | 是 | final | 0.659 | 0.659 | 0.000 | 0 | 10.8 | 无 | 155,832 | 4,130,432 | 128,829 | API usage (relay) | 116 | 0.113（¥0.754） | 未知 | ≥199.9 | 240.3 | 198.6 | deepseek-flash | default 46 |
| 8 Codex deepseek-flash high | codex-high-a4 | 是 | 是 | final | 0.192 | 0.213 | 0.000 | 0 | 64.4 | 无 | 未知 | 未知 | 未知 | 未知 | 225 | ≥0.696（¥4.640） | 未知 | ≥53.5 | 未知 | 未知 | deepseek-flash | default 901、not-returned 2 |
| 9 Codex deepseek-flash max | codex-max-a1 | 是 | 是 | final | 0.778 | 0.778 | 0.000 | 0 | 12.7 | 无 | 177,162 | 6,140,800 | 142,619 | API usage (relay) | 105 | 0.131（¥0.871） | 未知 | ≥189.1 | 233.3 | 187.8 | deepseek-flash | default 63 |
| 9 Codex deepseek-flash max | codex-max-a2 | 是 | 是 | final | 0.658 | 0.658 | 0.000 | 0 | 13.0 | 无 | 149,323 | 3,399,552 | 149,319 | API usage (relay) | 82 | 0.122（¥0.815） | 未知 | ≥191.7 | 190.8 | 190.8 | deepseek-flash | default 37 |
| 9 Codex deepseek-flash max | codex-max-a3 | 是 | 是 | final | 0.633 | 0.633 | 0.000 | 0 | 11.0 | 无 | 170,832 | 2,975,232 | 128,560 | API usage (relay) | 91 | 0.112（¥0.745） | 未知 | ≥196.4 | 259.8 | 195.5 | deepseek-flash | default 38、not-returned 1 |
| 9 Codex deepseek-flash max | codex-max-a4 | 是 | 是 | final | 0.672 | 0.672 | 0.000 | 0 | 12.7 | 无 | 143,623 | 4,453,888 | 146,685 | API usage (relay) | 114 | 0.123（¥0.819） | 未知 | ≥193.9 | 188.8 | 192.8 | deepseek-flash | default 48、not-returned 1 |
| 9 Codex deepseek-flash max | codex-max-a5 | 是 | 是 | final | 0.645 | 0.645 | 0.000 | 0 | 12.9 | 无 | 156,157 | 4,795,776 | 132,376 | API usage (relay) | 96 | 0.117（¥0.782） | 未知 | ≥172.4 | 202.3 | 171.5 | deepseek-flash | default 48 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a1 | 是 | 是 | final | 0.457 | 0.457 | 0.000 | 0 | 14.3 | 无 | 161,646 | 4,949,725 | 62,325 | engine log | 69 | 未知 | 1499.8 | 89.8 | 188.8 | 72.8 | 未知 | 未知 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a2 | 是 | 是 | final | 0.416 | 0.416 | 0.000 | 0 | 15.0 | 无 | 160,337 | 4,314,054 | 62,009 | engine log | 58 | 未知 | 1526.6 | 84.0 | 178.7 | 69.1 | 未知 | 未知 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a3 | 是 | 是 | final | 0.551 | 0.551 | 0.000 | 0 | 15.1 | 无 | 145,387 | 5,038,465 | 65,992 | engine log | 72 | 未知 | 1439.8 | 88.0 | 160.5 | 72.8 | 未知 | 未知 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a4 | 是 | 是 | final | 0.370 | 0.370 | 0.000 | 0 | 8.9 | 无 | 129,468 | 2,433,637 | 36,906 | engine log | 46 | 未知 | 1689.2 | 91.6 | 243.2 | 69.3 | 未知 | 未知 |
| 10 Codex Strata IQ3_XXS low | codex-strata-low-a5 | 是 | 是 | final | 0.658 | 0.658 | 0.000 | 0 | 13.0 | 无 | 134,596 | 4,114,854 | 56,620 | engine log | 54 | 未知 | 1450.3 | 89.7 | 173.1 | 72.8 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a1 | 是 | 是 | final | 0.582 | 0.582 | 0.000 | 0 | 14.5 | 无 | 157,035 | 3,456,807 | 62,316 | engine log | 51 | 未知 | 1542.9 | 86.8 | 180.1 | 71.5 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a2 | 是 | 是 | final | 0.473 | 0.473 | 0.000 | 0 | 13.1 | 无 | 136,564 | 3,742,636 | 56,182 | engine log | 60 | 未知 | 1513.3 | 87.3 | 173.6 | 71.4 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a3 | 是 | 是 | final | 0.654 | 0.654 | 0.000 | 0 | 16.0 | 无 | 152,999 | 3,899,283 | 69,819 | engine log | 57 | 未知 | 1528.8 | 86.5 | 159.4 | 72.7 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a4 | 是 | 是 | final | 0.563 | 0.563 | 0.000 | 0 | 13.7 | 无 | 142,337 | 3,380,377 | 59,007 | engine log | 54 | 未知 | 1547.1 | 87.2 | 173.2 | 71.8 | 未知 | 未知 |
| 11 Codex Strata IQ3_XXS medium | codex-strata-medium-a5 | 是 | 是 | final | 0.548 | 0.548 | 0.000 | 0 | 10.3 | 无 | 143,862 | 2,199,538 | 42,026 | engine log | 44 | 未知 | 1706.7 | 87.4 | 233.3 | 68.2 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a1 | 是 | 是 | final | 0.534 | 0.534 | 0.000 | 0 | 14.5 | 无 | 127,882 | 2,942,328 | 61,978 | engine log | 54 | 未知 | 1534.1 | 84.4 | 147.1 | 71.3 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a2 | 是 | 是 | final | 0.487 | 0.487 | 0.000 | 0 | 16.9 | 无 | 179,382 | 3,309,990 | 73,899 | engine log | 56 | 未知 | 1699.4 | 86.2 | 176.9 | 72.9 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a3 | 是 | 是 | final | 0.566 | 0.566 | 0.000 | 0 | 15.5 | 无 | 166,554 | 2,614,611 | 66,837 | engine log | 48 | 未知 | 1700.0 | 85.4 | 178.7 | 71.7 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a4 | 是 | 是 | final | 0.373 | 0.373 | 0.000 | 0 | 10.4 | 无 | 121,327 | 2,266,976 | 44,727 | engine log | 50 | 未知 | 1577.3 | 90.1 | 194.2 | 71.6 | 未知 | 未知 |
| 12 Codex Strata IQ3_XXS high | codex-strata-high-a5 | 是 | 是 | final | 0.513 | 0.513 | 0.000 | 0 | 12.0 | 无 | 135,798 | 2,208,278 | 51,623 | engine log | 46 | 未知 | 1750.2 | 87.3 | 188.8 | 71.8 | 未知 | 未知 |
| 13 Claude Code opus low | opus-low-a1 | 是 | 是 | final | 0.733 | 0.733 | 0.000 | 0 | 4.5 | 无 | 127,073 | 499,911 | 11,058 | Claude Code stream result usage | 11 | 1.338 | 未知 | ≥84.6 | 475.8 | 41.4 | claude-opus-5-5 | standard 13 |
| 13 Claude Code opus low | opus-low-a2 | 是 | 是 | final | 0.730 | 0.730 | 0.000 | 0 | 5.1 | 无 | 121,683 | 628,602 | 10,641 | Claude Code stream result usage | 13 | 1.312 | 未知 | ≥66.9 | 393.9 | 34.4 | claude-opus-5-5 | standard 15 |
| 13 Claude Code opus low | opus-low-a3 | 是 | 是 | final | 0.643 | 0.643 | 0.000 | 0 | 5.4 | 无 | 118,537 | 555,330 | 11,876 | Claude Code stream result usage | 12 | 1.297 | 未知 | ≥78.2 | 367.5 | 36.8 | claude-opus-5-5 | standard 14 |
| 13 Claude Code opus low | opus-low-a4 | 是 | 是 | final | 0.564 | 0.564 | 0.000 | 0 | 4.0 | 无 | 122,024 | 482,122 | 11,397 | Claude Code stream result usage | 11 | 1.300 | 未知 | ≥86.2 | 514.8 | 48.1 | claude-opus-5-5 | standard 13 |
| 13 Claude Code opus low | opus-low-a5 | 是 | 是 | final | 0.654 | 0.654 | 0.000 | 0 | 8.1 | 无 | 118,798 | 479,612 | 11,991 | Claude Code stream result usage | 11 | 1.286 | 未知 | ≥35.0 | 245.2 | 24.7 | claude-opus-5-5 | standard 13 |
| 14 Claude Code opus medium | opus-medium-a1 | 是 | 是 | final | 0.798 | 0.798 | 0.000 | 0 | 9.0 | 无 | 162,097 | 1,047,014 | 26,538 | Claude Code stream result usage | 21 | 2.037 | 未知 | ≥75.7 | 301.3 | 49.3 | claude-opus-5-5 | standard 21 |
| 14 Claude Code opus medium | opus-medium-a2 | 是 | 是 | final | 0.830 | 0.830 | 0.000 | 0 | 12.9 | 无 | 166,198 | 1,169,552 | 34,439 | Claude Code stream result usage | 23 | 2.252 | 未知 | ≥71.8 | 215.0 | 44.6 | claude-opus-5-5 | standard 24 |
| 14 Claude Code opus medium | opus-medium-a3 | 是 | 是 | final | 0.720 | 0.720 | 0.000 | 0 | 10.1 | 无 | 168,094 | 1,092,251 | 31,001 | Claude Code stream result usage | 20 | 2.183 | 未知 | ≥89.4 | 277.3 | 51.1 | claude-opus-5-5 | standard 21 |
| 14 Claude Code opus medium | opus-medium-a4 | 是 | 是 | final | 0.768 | 0.768 | 0.000 | 0 | 13.4 | 无 | 170,961 | 1,036,294 | 34,978 | Claude Code stream result usage | 18 | 2.274 | 未知 | ≥63.0 | 212.6 | 43.5 | claude-opus-5-5 | standard 18 |
| 14 Claude Code opus medium | opus-medium-a5 | 是 | 是 | final | 0.743 | 0.743 | 0.000 | 0 | 10.7 | 无 | 173,333 | 1,324,248 | 30,447 | Claude Code stream result usage | 23 | 2.260 | 未知 | ≥69.0 | 269.9 | 47.4 | claude-opus-5-5 | standard 24 |
| 15 Claude Code opus high | opus-high-a1 | 是 | 是 | final | 0.764 | 0.764 | 0.000 | 0 | 11.9 | 无 | 217,991 | 1,783,635 | 50,244 | Claude Code stream result usage | 26 | 3.105 | 未知 | ≥91.6 | 305.3 | 70.4 | claude-opus-5-5 | standard 28 |
| 15 Claude Code opus high | opus-high-a2 | 是 | 是 | final | 0.837 | 0.837 | 0.000 | 0 | 14.2 | 无 | 236,934 | 1,498,354 | 55,427 | Claude Code stream result usage | 29 | 3.304 | 未知 | ≥94.6 | 277.9 | 65.0 | claude-opus-5-5 | standard 22 |
| 15 Claude Code opus high | opus-high-a3 | 是 | 是 | final | 0.847 | 0.847 | 0.000 | 0 | 10.8 | 无 | 235,739 | 1,518,848 | 49,573 | Claude Code stream result usage | 30 | 3.181 | 未知 | ≥96.8 | 365.5 | 76.9 | claude-opus-5-5 | standard 23 |
| 15 Claude Code opus high | opus-high-a4 | 是 | 是 | final | 0.812 | 0.812 | 0.000 | 0 | 17.5 | 无 | 219,538 | 1,767,056 | 56,466 | Claude Code stream result usage | 31 | 3.239 | 未知 | ≥65.9 | 208.7 | 53.7 | claude-opus-5-5 | standard 25 |
| 15 Claude Code opus high | opus-high-a5 | 是 | 是 | final | 0.801 | 0.801 | 0.000 | 0 | 11.1 | 无 | 199,946 | 1,485,151 | 48,103 | Claude Code stream result usage | 32 | 2.858 | 未知 | ≥86.1 | 300.2 | 72.2 | claude-opus-5-5 | standard 26 |
| 16 Claude Code sonnet low | sonnet-low-a1 | 是 | 是 | final | 0.468 | 0.468 | 0.000 | 0 | 2.3 | 无 | 132,008 | 345,858 | 9,836 | Claude Code stream result usage | 12 | 0.661 | 未知 | ≥116.4 | 944.9 | 70.4 | claude-sonnet-5-5 | standard 9 |
| 16 Claude Code sonnet low | sonnet-low-a2 | 是 | 是 | final | 0.426 | 0.426 | 0.000 | 0 | 3.5 | 无 | 131,340 | 414,966 | 14,449 | Claude Code stream result usage | 11 | 0.711 | 未知 | ≥95.4 | 622.4 | 68.5 | claude-sonnet-5-5 | standard 10 |
| 16 Claude Code sonnet low | sonnet-low-a3 | 是 | 是 | final | 0.542 | 0.542 | 0.000 | 0 | 2.4 | 无 | 126,855 | 494,528 | 9,304 | Claude Code stream result usage | 13 | 0.650 | 未知 | ≥78.4 | 869.6 | 63.8 | claude-sonnet-5-5 | standard 11 |
| 16 Claude Code sonnet low | sonnet-low-a4 | 是 | 是 | final | 0.453 | 0.453 | 0.000 | 0 | 3.5 | 无 | 132,399 | 639,136 | 14,847 | Claude Code stream result usage | 14 | 0.742 | 未知 | ≥101.1 | 622.4 | 69.8 | claude-sonnet-5-5 | standard 13 |
| 16 Claude Code sonnet low | sonnet-low-a5 | 是 | 是 | final | 0.498 | 0.498 | 0.000 | 0 | 4.0 | 无 | 139,830 | 1,024,434 | 20,402 | Claude Code stream result usage | 17 | 0.866 | 未知 | ≥109.1 | 583.2 | 85.1 | claude-sonnet-5-5 | standard 18 |
| 17 Claude Code sonnet medium | sonnet-medium-a1 | 是 | 是 | final | 0.864 | 0.864 | 0.000 | 0 | 4.6 | 无 | 191,032 | 737,945 | 34,501 | Claude Code stream result usage | 22 | 1.183 | 未知 | ≥132.4 | 698.8 | 126.2 | claude-sonnet-5-5 | standard 12 |
| 17 Claude Code sonnet medium | sonnet-medium-a2 | 是 | 是 | final | 0.836 | 0.836 | 0.000 | 0 | 3.9 | 无 | 165,671 | 407,536 | 28,303 | Claude Code stream result usage | 15 | 0.986 | 未知 | ≥129.2 | 699.6 | 119.5 | claude-sonnet-5-5 | standard 9 |
| 17 Claude Code sonnet medium | sonnet-medium-a3 | 是 | 是 | final | 0.428 | 0.428 | 0.000 | 0 | 3.6 | 无 | 154,510 | 468,405 | 18,510 | Claude Code stream result usage | 15 | 0.850 | 未知 | ≥113.1 | 724.4 | 86.8 | claude-sonnet-5-5 | standard 10 |
| 17 Claude Code sonnet medium | sonnet-medium-a4 | 是 | 是 | final | 0.672 | 0.672 | 0.000 | 0 | 3.5 | 无 | 147,727 | 303,148 | 24,191 | Claude Code stream result usage | 12 | 0.863 | 未知 | ≥127.8 | 701.0 | 114.8 | claude-sonnet-5-5 | standard 8 |
| 17 Claude Code sonnet medium | sonnet-medium-a5 | 是 | 是 | final | 0.645 | 0.717 | 0.037 | 0 | 62.0 | 无 | 213,201 | 39,415,377 | 37,509 | Claude Code stream result usage | 20 | 5.168 | 未知 | ≥25.3 | 57.3 | 10.1 | claude-sonnet-5-5 | standard 350 |
| 18 Claude Code sonnet high | sonnet-high-a1 | 是 | 是 | final | 0.867 | 0.867 | 0.000 | 0 | 7.6 | 无 | 231,060 | 1,075,614 | 53,944 | Claude Code stream result usage | 30 | 1.571 | 未知 | ≥133.4 | 506.1 | 118.2 | claude-sonnet-5-5 | standard 15 |
| 18 Claude Code sonnet high | sonnet-high-a2 | 是 | 是 | final | 0.844 | 0.844 | 0.000 | 0 | 9.6 | 无 | 236,823 | 1,235,748 | 61,279 | Claude Code stream result usage | 30 | 1.684 | 未知 | ≥126.6 | 410.4 | 106.2 | claude-sonnet-5-5 | standard 17 |
| 18 Claude Code sonnet high | sonnet-high-a3 | 是 | 是 | final | 0.707 | 0.707 | 0.000 | 0 | 9.1 | 无 | 223,965 | 732,083 | 63,188 | Claude Code stream result usage | 26 | 1.601 | 未知 | ≥131.3 | 411.8 | 116.2 | claude-sonnet-5-5 | standard 12 |
| 18 Claude Code sonnet high | sonnet-high-a4 | 是 | 是 | final | 0.718 | 0.718 | 0.000 | 0 | 7.2 | 无 | 216,410 | 924,489 | 49,425 | Claude Code stream result usage | 28 | 1.452 | 未知 | ≥128.0 | 503.0 | 114.9 | claude-sonnet-5-5 | standard 14 |
| 18 Claude Code sonnet high | sonnet-high-a5 | 是 | 是 | final | 0.838 | 0.838 | 0.000 | 0 | 8.8 | 无 | 221,689 | 944,777 | 55,758 | Claude Code stream result usage | 29 | 1.539 | 未知 | ≥130.4 | 421.5 | 106.0 | claude-sonnet-5-5 | standard 14 |
| 19 Claude Code haiku low | haiku-low-a1 | 是 | 是 | final | 0.639 | 0.639 | 0.000 | 0 | 8.8 | 无 | 295,302 | 856,346 | 114,346 | Claude Code stream result usage | 28 | 0.271 | 未知 | ≥234.0 | 560.3 | 217.0 | claude-haiku-5-5 | standard 11 |
| 19 Claude Code haiku low | haiku-low-a2 | 是 | 是 | final | 0.542 | 0.542 | 0.000 | 0 | 8.6 | 无 | 296,234 | 1,028,028 | 113,934 | Claude Code stream result usage | 29 | 0.278 | 未知 | ≥235.0 | 576.5 | 221.7 | claude-haiku-5-5 | standard 12 |
| 19 Claude Code haiku low | haiku-low-a3 | 是 | 是 | final | 0.708 | 0.708 | 0.000 | 0 | 10.0 | 无 | 323,610 | 1,036,321 | 133,879 | Claude Code stream result usage | 29 | 0.330 | 未知 | ≥238.4 | 541.2 | 223.9 | claude-haiku-5-5 | standard 12 |
| 19 Claude Code haiku low | haiku-low-a4 | 是 | 是 | final | 0.607 | 0.607 | 0.000 | 0 | 9.4 | 无 | 309,619 | 1,000,783 | 125,689 | Claude Code stream result usage | 28 | 0.317 | 未知 | ≥233.2 | 549.3 | 223.0 | claude-haiku-5-5 | standard 12 |
| 19 Claude Code haiku low | haiku-low-a5 | 是 | 是 | final | 0.668 | 0.668 | 0.000 | 0 | 11.9 | 无 | 339,987 | 883,156 | 159,927 | Claude Code stream result usage | 28 | 0.422 | 未知 | ≥240.2 | 476.3 | 224.1 | claude-haiku-5-5 | standard 11 |
| 20 Claude Code haiku medium | haiku-medium-a1 | 是 | 是 | final | 0.644 | 0.644 | 0.000 | 0 | 10.0 | 无 | 313,972 | 1,206,922 | 137,698 | Claude Code stream result usage | 29 | 0.338 | 未知 | ≥238.1 | 521.4 | 228.6 | claude-haiku-5-5 | standard 13 |
| 20 Claude Code haiku medium | haiku-medium-a2 | 是 | 是 | final | 0.642 | 0.642 | 0.000 | 0 | 10.4 | 无 | 329,677 | 1,273,012 | 138,403 | Claude Code stream result usage | 31 | 0.362 | 未知 | ≥232.2 | 527.5 | 221.5 | claude-haiku-5-5 | standard 14 |
| 20 Claude Code haiku medium | haiku-medium-a3 | 是 | 是 | final | 0.646 | 0.646 | 0.000 | 0 | 11.1 | 无 | 328,935 | 745,859 | 154,688 | Claude Code stream result usage | 28 | 0.316 | 未知 | ≥241.7 | 495.4 | 233.0 | claude-haiku-5-5 | standard 10 |
| 20 Claude Code haiku medium | haiku-medium-a4 | 是 | 是 | final | 0.752 | 0.752 | 0.000 | 0 | 13.5 | 无 | 357,024 | 1,947,550 | 164,200 | Claude Code stream result usage | 34 | 0.482 | 未知 | ≥236.6 | 442.3 | 203.4 | claude-haiku-5-5 | standard 17 |
| 20 Claude Code haiku medium | haiku-medium-a5 | 是 | 是 | final | 0.376 | 0.376 | 0.000 | 0 | 11.1 | 无 | 327,309 | 752,088 | 152,534 | Claude Code stream result usage | 28 | 0.301 | 未知 | ≥237.3 | 490.1 | 228.4 | claude-haiku-5-5 | standard 10 |
| 21 Claude Code haiku high | haiku-high-a1 | 是 | 是 | final | 0.646 | 0.646 | 0.000 | 0 | 17.0 | 无 | 423,344 | 2,761,962 | 216,454 | Claude Code stream result usage | 39 | 0.745 | 未知 | ≥224.2 | 414.7 | 212.0 | claude-haiku-5-5 | standard 20 |
| 21 Claude Code haiku high | haiku-high-a2 | 是 | 是 | final | 0.585 | 0.585 | 0.000 | 0 | 17.1 | 无 | 435,361 | 2,081,191 | 231,939 | Claude Code stream result usage | 34 | 0.603 | 未知 | ≥239.1 | 424.0 | 225.9 | claude-haiku-5-5 | standard 16 |
| 21 Claude Code haiku high | haiku-high-a3 | 是 | 是 | final | 0.518 | 0.518 | 0.000 | 0 | 13.5 | 无 | 370,111 | 1,120,179 | 195,346 | Claude Code stream result usage | 30 | 0.396 | 未知 | ≥250.8 | 456.0 | 240.7 | claude-haiku-5-5 | standard 12 |
| 21 Claude Code haiku high | haiku-high-a4 | 是 | 是 | final | 0.638 | 0.638 | 0.000 | 0 | 17.4 | 无 | 422,395 | 991,191 | 248,150 | Claude Code stream result usage | 28 | 0.680 | 未知 | ≥243.7 | 404.6 | 237.7 | claude-haiku-5-5 | standard 11 |
| 21 Claude Code haiku high | haiku-high-a5 | 是 | 是 | final | 0.564 | 0.564 | 0.000 | 0 | 15.4 | 无 | 398,287 | 1,123,408 | 217,998 | Claude Code stream result usage | 28 | 0.616 | 未知 | ≥240.8 | 429.9 | 235.3 | claude-haiku-5-5 | standard 12 |
| 22 Claude Code deepseek-flash low | cc-low-a1 | 是 | 是 | final | 0.704 | 0.704 | 0.000 | 0 | 14.4 | 无 | 134,272 | 1,803,136 | 126,897 | Claude Code stream result usage | 38 | 0.102（¥0.678） | 未知 | ≥196.3 | 155.4 | 146.8 | deepseek-flash | standard 27 |
| 22 Claude Code deepseek-flash low | cc-low-a2 | 是 | 是 | final | 0.682 | 0.682 | 0.000 | 0 | 15.4 | 无 | 140,023 | 1,846,016 | 183,568 | Claude Code stream result usage | 37 | 0.137（¥0.911） | 未知 | ≥214.0 | 151.4 | 198.5 | deepseek-flash | standard 27 |
| 22 Claude Code deepseek-flash low | cc-low-a3 | 是 | 是 | final | 0.171 | 0.171 | 0.000 | 0 | 13.8 | 无 | 127,230 | 982,912 | 167,355 | Claude Code stream result usage | 29 | 0.122（¥0.816） | 未知 | ≥205.4 | 153.2 | 201.5 | deepseek-flash | standard 18、not-returned 1 |
| 22 Claude Code deepseek-flash low | cc-low-a4 | 是 | 是 | final | 0.174 | 0.174 | 0.000 | 0 | 16.7 | 无 | 127,181 | 1,264,384 | 189,073 | Claude Code stream result usage | 30 | 0.136（¥0.909） | 未知 | ≥215.1 | 126.8 | 188.5 | deepseek-flash | standard 22、not-returned 1 |
| 22 Claude Code deepseek-flash low | cc-low-a5 | 是 | 是 | final | 0.591 | 0.591 | 0.000 | 0 | 14.2 | 无 | 130,321 | 1,358,720 | 135,170 | Claude Code stream result usage | 33 | 0.105（¥0.698） | 未知 | ≥211.0 | 152.6 | 158.2 | deepseek-flash | standard 19 |
| 23 Claude Code deepseek-flash high | cc-medium-a1 | 是 | 是 | final | 0.649 | 0.649 | 0.000 | 0 | 16.7 | 无 | 140,262 | 2,597,376 | 169,217 | Claude Code stream result usage | 45 | 0.130（¥0.869） | 未知 | ≥207.5 | 140.0 | 168.9 | deepseek-flash | standard 32 |
| 23 Claude Code deepseek-flash high | cc-high-a1 | 是 | 是 | final | 0.564 | 0.564 | 0.000 | 0 | 29.0 | 无 | 188,870 | 2,887,936 | 303,006 | Claude Code stream result usage | 56 | 0.219（¥1.459） | 未知 | ≥206.9 | 108.4 | 174.0 | deepseek-flash | standard 46 |
| 23 Claude Code deepseek-flash high | cc-high-a2 | 是 | 是 | final | 0.172 | 0.172 | 0.000 | 0 | 28.7 | 无 | 142,736 | 2,178,816 | 341,845 | Claude Code stream result usage | 37 | 0.233（¥1.554） | 未知 | ≥214.7 | 82.9 | 198.6 | deepseek-flash | standard 33、not-returned 1 |
| 23 Claude Code deepseek-flash high | cc-high-a3 | 是 | 是 | final | 0.565 | 0.565 | 0.000 | 0 | 24.3 | 无 | 135,051 | 2,964,480 | 249,481 | Claude Code stream result usage | 47 | 0.179（¥1.192） | 未知 | ≥205.9 | 92.7 | 171.2 | deepseek-flash | standard 37 |
| 23 Claude Code deepseek-flash high | cc-high-a4 | 是 | 是 | final | 0.654 | 0.654 | 0.000 | 0 | 21.1 | 无 | 125,549 | 1,915,904 | 228,021 | Claude Code stream result usage | 39 | 0.161（¥1.076） | 未知 | ≥211.8 | 99.1 | 179.9 | deepseek-flash | standard 27 |
| 24 Claude Code deepseek-flash max | cc-max-a1 | 是 | 是 | final | 0.160 | 0.160 | 0.000 | 0 | 22.5 | 无 | 135,250 | 2,107,648 | 277,875 | Claude Code stream result usage | 36 | 0.193（¥1.289） | 未知 | ≥217.7 | 100.2 | 205.8 | deepseek-flash | standard 31、not-returned 1 |
| 24 Claude Code deepseek-flash max | cc-max-a2 | 是 | 是 | final | 0.163 | 0.163 | 0.000 | 0 | 20.8 | 无 | 120,519 | 1,028,864 | 238,971 | Claude Code stream result usage | 29 | 0.165（¥1.097） | 未知 | ≥205.2 | 96.6 | 191.5 | deepseek-flash | standard 19、not-returned 1 |
| 24 Claude Code deepseek-flash max | cc-max-a3 | 是 | 是 | final | 0.596 | 0.596 | 0.000 | 0 | 40.4 | 无 | 249,553 | 3,792,896 | 463,083 | Claude Code stream result usage | 64 | 0.327（¥2.178） | 未知 | ≥211.3 | 102.9 | 190.9 | deepseek-flash | standard 57 |
| 24 Claude Code deepseek-flash max | cc-max-a4 | 是 | 是 | final | 0.174 | 0.174 | 0.000 | 0 | 17.0 | 无 | 126,846 | 926,464 | 224,046 | Claude Code stream result usage | 27 | 0.156（¥1.042） | 未知 | ≥225.3 | 124.4 | 219.7 | deepseek-flash | standard 16、not-returned 1 |
| 24 Claude Code deepseek-flash max | cc-max-a5 | 是 | 是 | final | 0.174 | 0.174 | 0.000 | 0 | 26.5 | 无 | 145,008 | 3,249,792 | 314,367 | Claude Code stream result usage | 49 | 0.220（¥1.468） | 未知 | ≥217.3 | 91.0 | 197.3 | deepseek-flash | standard 44、not-returned 1 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a1 | 是 | 是 | final | 0.141 | 0.141 | 0.000 | 0 | 12.8 | 无 | 143,531 | 2,986,240 | 62,182 | engine log | 41 | 3.280 | 1823.8 | 91.2 | 186.3 | 80.7 | qwen3.8-flash-next-iq3_xxs | not-returned 33 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a2 | 是 | 是 | final | 0.133 | 0.133 | 0.000 | 0 | 10.3 | 无 | 141,559 | 3,037,451 | 46,833 | engine log | 43 | 2.952 | 1758.1 | 88.5 | 229.6 | 76.0 | qwen3.8-flash-next-iq3_xxs | not-returned 36 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a3 | 是 | 是 | final | 0.393 | 0.393 | 0.000 | 0 | 9.8 | 无 | 163,905 | 3,928,331 | 41,605 | engine log | 57 | 3.389 | 1645.6 | 88.3 | 278.9 | 70.8 | qwen3.8-flash-next-iq3_xxs | not-returned 49 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a4 | 是 | 是 | final | 0.215 | 0.215 | 0.000 | 0 | 9.6 | 无 | 141,832 | 2,389,646 | 42,857 | engine log | 37 | 2.559 | 1878.8 | 87.0 | 245.7 | 74.3 | qwen3.8-flash-next-iq3_xxs | not-returned 27 |
| 25 Claude Code Strata IQ3_XXS low | strata-low-a5 | 是 | 是 | final | 0.300 | 0.300 | 0.000 | 0 | 7.2 | 无 | 149,500 | 2,022,636 | 30,598 | engine log | 34 | 2.224 | 2008.1 | 87.2 | 345.8 | 70.8 | qwen3.8-flash-next-iq3_xxs | not-returned 24 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a1 | 是 | 是 | final | 0.181 | 0.181 | 0.000 | 0 | 6.6 | 无 | 136,313 | 1,106,502 | 28,545 | engine log | 27 | 1.798 | 2180.3 | 86.8 | 345.2 | 72.3 | qwen3.8-flash-next-iq3_xxs | not-returned 16 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a2 | 是 | 是 | final | 0.156 | 0.156 | 0.000 | 0 | 8.4 | 无 | 139,127 | 1,740,662 | 36,928 | engine log | 32 | 2.233 | 2024.8 | 85.9 | 276.0 | 73.3 | qwen3.8-flash-next-iq3_xxs | not-returned 21 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a3 | 是 | 是 | final | 0.325 | 0.325 | 0.000 | 0 | 17.9 | 无 | 245,160 | 2,567,497 | 88,145 | engine log | 40 | 4.221 | 2064.8 | 92.8 | 227.7 | 81.9 | qwen3.8-flash-next-iq3_xxs | not-returned 29 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a4 | 是 | 是 | final | 0.371 | 0.371 | 0.000 | 0 | 8.9 | 无 | 147,964 | 1,974,906 | 38,744 | engine log | 33 | 2.424 | 1996.5 | 84.7 | 275.8 | 72.2 | qwen3.8-flash-next-iq3_xxs | not-returned 24 |
| 26 Claude Code Strata IQ3_XXS medium | strata-medium-a5 | 是 | 是 | final | 0.270 | 0.270 | 0.000 | 0 | 10.3 | 无 | 156,850 | 1,817,311 | 50,070 | engine log | 34 | 2.702 | 2142.1 | 92.7 | 253.2 | 80.8 | qwen3.8-flash-next-iq3_xxs | not-returned 22 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a1 | 否：harness-fault | 否 | — | 未知 | 未知 | 未知 |  | 17.7 | 无 | 163,001 | 2,693,395 | 86,265 | engine log | 46 | 3.951 | 1997.8 | 88.7 | 153.5 | 81.2 | qwen3.8-flash-next-iq3_xxs | not-returned 31 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a2 | 是 | 是 | final | 0.324 | 0.324 | 0.000 | 0 | 13.8 | 无 | 168,572 | 1,898,362 | 62,874 | engine log | 34 | 3.051 | 2056.7 | 85.2 | 203.9 | 76.1 | qwen3.8-flash-next-iq3_xxs | not-returned 24 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a3 | 是 | 是 | final | 0.164 | 0.164 | 0.000 | 0 | 5.2 | 无 | 123,047 | 747,543 | 22,982 | engine log | 25 | 1.460 | 2243.6 | 90.3 | 393.7 | 73.5 | qwen3.8-flash-next-iq3_xxs | not-returned 14 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a4 | 是 | 是 | final | 0.185 | 0.185 | 0.000 | 0 | 9.8 | 无 | 125,937 | 1,506,244 | 45,583 | engine log | 33 | 2.337 | 2074.4 | 87.1 | 214.1 | 77.5 | qwen3.8-flash-next-iq3_xxs | not-returned 21 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a5 | 是 | 是 | final | 0.373 | 0.373 | 0.000 | 0 | 24.8 | 无 | 173,921 | 2,279,526 | 134,294 | engine log | 34 | 4.904 | 2036.3 | 96.1 | 116.8 | 90.2 | qwen3.8-flash-next-iq3_xxs | not-returned 23 |
| 27 Claude Code Strata IQ3_XXS high | strata-high-a6 | 是 | 是 | final | 0.255 | 0.255 | 0.000 | 0 | 11.9 | 无 | 139,780 | 1,852,374 | 52,697 | engine log | 34 | 2.740 | 2034.2 | 82.1 | 195.1 | 73.6 | qwen3.8-flash-next-iq3_xxs | not-returned 23 |

## 墙钟耗时按阶段

能从 summary.json 的实例开始时刻和各 worker 报告摘要得出的部分。批次窗口按实例的 `started` 和工作耗时近似（末个结束 = 最晚的开始 + 该实例工作秒数，不含收尾），含无效实例；同一臂不同场景之间有并行，跨度不能相加。

### 场景批次（第一阶段实例）

| 臂 | 场景 | 实例数（含无效） | 首个开始（JST） | 末个结束（近似，JST） | 跨度（小时） |
|---|---|---|---|---|---|
| Anthropic（Claude Code） | commit-audit-v3 | 45 | 10-19 23:48 | 10-20 01:27 | 1.7 |
| Strata（Claude Code） | commit-audit-v3 | 15 | 10-20 00:25 | 10-20 04:41 | 4.3 |
| Anthropic（Claude Code） | code-spec-v5 | 55 | 10-20 01:29 | 10-20 17:41 | 16.2 |
| Strata（Claude Code） | code-spec-v5 | 16 | 10-20 04:47 | 10-20 09:48 | 5.0 |
| Anthropic（Claude Code） | code-standards-v5.1 | 45 | 10-20 06:05 | 10-20 18:48 | 12.7 |
| Strata（Claude Code） | code-standards-v5.1 | 29 | 10-20 07:25 | 10-21 05:39 | 22.2 |
| OpenAI（Codex） | commit-audit-v3 | 33 | 10-20 07:49 | 10-20 10:20 | 2.5 |
| OpenAI（Codex） | code-spec-v5 | 30 | 10-20 09:11 | 10-20 09:38 | 0.4 |
| Strata（Claude Code） | spec-readiness-v4.3 | 16 | 10-20 09:21 | 10-21 09:02 | 23.7 |
| OpenAI（Codex） | code-standards-v5.1 | 31 | 10-20 09:54 | 10-20 10:28 | 0.6 |
| OpenAI（Codex） | spec-readiness-v4.3 | 31 | 10-20 10:37 | 10-20 12:15 | 1.6 |
| Strata（Codex） | commit-audit-v3 | 19 | 10-20 10:37 | 10-20 21:20 | 10.7 |
| Strata（Codex） | code-spec-v5 | 15 | 10-20 11:50 | 10-20 14:37 | 2.8 |
| Anthropic（Claude Code） | spec-readiness-v4.3 | 45 | 10-20 12:28 | 10-20 17:26 | 5.0 |
| Strata（Codex） | code-standards-v5.1 | 15 | 10-20 21:25 | 10-21 00:14 | 2.8 |
| DeepSeek（Codex） | code-spec-v5 | 20 | 10-20 22:15 | 10-21 05:11 | 6.9 |
| DeepSeek（Claude Code） | code-spec-v5 | 21 | 10-20 22:16 | 10-21 05:16 | 7.0 |
| DeepSeek（Codex） | commit-audit-v3 | 18 | 10-20 22:27 | 10-21 06:09 | 7.7 |
| DeepSeek（Claude Code） | commit-audit-v3 | 18 | 10-20 22:32 | 10-21 06:24 | 7.9 |
| DeepSeek（Codex） | code-standards-v5.1 | 15 | 10-20 23:03 | 10-21 07:01 | 8.0 |
| DeepSeek（Claude Code） | code-standards-v5.1 | 16 | 10-20 23:05 | 10-21 07:04 | 8.0 |
| DeepSeek（Codex） | spec-readiness-v4.3 | 17 | 10-20 23:26 | 10-21 19:30 | 20.1 |
| DeepSeek（Claude Code） | spec-readiness-v4.3 | 15 | 10-20 23:26 | 10-21 19:57 | 20.5 |
| Strata（Codex） | spec-readiness-v4.3 | 15 | 10-21 00:15 | 10-21 04:01 | 3.8 |

### Strata 加测（第二阶段，进行中，截至 summary.json 生成时）

| 臂 | 场景 | 已有加测有效实例 | 首个开始（JST） | 已有末个结束（近似，JST） |
|---|---|---|---|---|
| Strata（Codex） | commit-audit-v3 | 15 | 10-21 09:14 | 10-21 13:10 |
| Strata（Claude Code） | commit-audit-v3 | 15 | 10-21 13:12 | 10-21 17:36 |
| Strata（Codex） | code-spec-v5 | 15 | 10-21 17:38 | 10-21 20:08 |
| Strata（Claude Code） | code-spec-v5 | 15 | 10-21 20:10 | 10-21 22:38 |
| Strata（Codex） | code-standards-v5.1 | 11 | 10-21 22:39 | 10-22 00:34 |

### 盲裁、复核与计分

| 阶段 | 时间（JST） | 来源 |
|---|---|---|
| CS、CA 第一批盲裁 | 10-20 夜间开始；结束时刻未汇总 | plan §14.1 2026-10-20 提前盲裁条 |
| CStd、SR 第一批盲裁 | 未汇总 | — |
| DeepSeek 桥接批盲裁（42 池，$53.14） | 10-21 20:22:39 开始，10-22 00:16 前结束 | adjudication-ds-1021 摘要；plan 提交 861ff43 |
| 桥接批复核（120 条） | 10-22 00:3x 结束 | adj-review-ds-1021 摘要 |
| 计分前独立审查 | 10-22 01:0x | override-ds-1022 摘要 |
| 第一阶段正式计分 | 10-22 01:3x 结束 | phase1-score-1022 摘要 |
| 缺口补裁（2 池，$2.24） | 10-22 01:18–01:35 | adjudication-gap-1022 摘要 |
| 计分缺口修复 | 10-22 01:13 提交 613066e | gapfix-1022 摘要 |
| CA 第 2 关行号修复 | 10-22 合并 e46006d | shiftfix-1022 摘要 |
| 行号修复补裁（1 池，$0.63） | 10-22 02:27–02:29 | adjudication-shift-1022 |
| 全量重算（557 实例，master e46006d） | 10-22 02:3x | phase1-score-1022/root-final、summary-final |
| 门与探针 | 未汇总 | plan §7、§14.x 有逐项记录 |
| 会话检查 | 已完成（Haiku 逐实例审阅 + Main 复核 32 个） | — |
