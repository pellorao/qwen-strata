# 多模型 benchmark v1 第三阶段补充：gpt-6-luna xhigh / max

**结论**：gpt-6-luna 的 xhigh（配置 28）和 max（配置 29）在 4 个场景共有 51 个有效实例，每格 5–8 个，全部最终计分（评分 r8.4，rulings e1e73dcb）。按用户要求（2026-10-22），本报告只列每个实例的结果，不与其他配置比较，也不做统计检验。

## 条件

- 与 v1 相同：Codex `399ff69c…4215`、catalog `40484beb…`、各场景冻结 plan、harness 补丁、`arw_measure` `1735b7be`；运行脚本存档在 `benchmarks/multi-model-v1/runners/luna-xhigh-1022/`。不经过 Strata，与 Strata 版本无关。
- 运行时间 2026-10-23 02:20–07:12，借用 ChatGPT 登录，最多 3 个实例并行，场景依次进行：CS → CStd → CA → SR。用完已归还登录。周用量最高 2%。
- 有效性按 v1 规则判定，包括计分时的重判。提醒中断按 10-23 用户定的一条判据：提醒或中断送达时正在进行的请求，其错误行不算 relay 错误（取代原先的 7 条判据）。
  - CS、CStd 的 xhigh 在运行时有多个实例被判作废，原因是 BrokenPipe；计分时重判，全部恢复为有效。
  - CStd luna-max-a4、a6 在旧判据下无效：relay 要到下次写数据才发现客户端断开，记下的结束时刻比重发晚，不满足旧判据的时间窗。按新判据，它们的错误行是提醒送达时正在进行的请求（结束时刻在送达尝试后 3.8 秒、1.8 秒），所以有效。51 个实例全部有效。
- 实例集合：每格取全部有效实例，不截取前 5 个（用户 2026-10-23，测量规则「失败与重跑」）。多出的实例来自并行调度，不是因为已有分数差才加跑，所以和预登记的实例效力相同；第三阶段没有 surplus，也没有一致性行。每格 n：CS xhigh 8、max 6；CStd xhigh 8、max 8；CA xhigh 6、max 5；SR xhigh 5、max 5。
- 盲裁按 §6.2，由单名 Opus high 进行，分两批：先裁每格前 5 个（40 个实例），规则改变后再裁其余 11 个，流程、brief、view 和提示相同。
  - 共 20 池（16 + 4），第一次全部通过：锚点一致率都是 1.0，合成负例全部识别正确。
  - 写入 2388 条决定（1950 + 438），费用 $24.61（$20.13 + $4.48）。
  - 复核清单 122 条（114 + 8），改判 4 条，都在 CStd，都是又一份 store 写队列，按 rulings「新代码照搬仓库里已有多份的重复实现」从 unsupported 改为 supported：luna-max-a2 finding-15、luna-xhigh-a1 finding-20、luna-max-a6 finding-13、luna-xhigh-a8 finding-22。
- 会话检查按 D9：51 个实例中脚本标出 7 个可疑，Main 侧逐个复核后都判有效。原因是拼错路径、ENOENT、git EPERM、未执行的路径常量这类无害情况，没有违规。

## 异常与说明

- **CA luna-xhigh-a5**：得分 −0.182，是本补测唯一的负分。
  - 它写完 Gate 1 的 49 行后，认定 Gate 2 需要一个文件 `docs/agents/commit-audit-reviewer/gate-2.md`；这个文件在所有 CA 实例中都不存在，其他实例照常按请求完成了 Gate 2。
  - 此后约 737 个轮次都只回复 `{"status":"incomplete"}`，触发 146 次早退暂停，每次都已回复"继续"。
  - 60 分钟时被 ARW 截断，报告只有 Gate 1；暂停扣 0.1。
  - 记录里没有 token 数。token 由 bench_records 从 relay 日志求和（762 个请求），为下界：其中 1 个被中断的请求没有 usage。
- **SR luna-max-a4**：有 6 次早退暂停，扣 0.1。
- **CStd luna-max-a8**：得分 0.253，是同格最低。它只用了时限的 38%（4.1 分钟），报告只有 20 个定位，没有罚分。
- **格式罚**：CStd max-a7（f 0.1）、CA max-a2（f 0.098）、CStd max-a4（f 0.036）、CS xhigh-a3（f 0.026）、SR xhigh-a3（f 0.025）、CStd xhigh-a7（f 0.018）、CStd xhigh-a6（f 0.017）。
  - SR xhigh-a3 的 h0 报告第 5 行不是合法 JSON，引号没有转义。修复工具原先遇到这种行会崩溃，改为不修复、交 ARW 按原样计分（e2c5fdd）。ARW 判 `review-format-invalid`，r 计 1。
- 无 ARW 截断扣分。

## 数据

- `summary.json`：由 `benchmark_summary --phase 3` 生成，含第二阶段全部实例和本补充的完整精度数据；三阶段合一的公开结果文件是 [`../benchmark-results.json`](../benchmark-results.json)。10-23 改为全部有效实例后，两份文件都已用工具链重新生成；第二阶段的实例与统计不变。
- 运行明细、决定库和复核明细在 `.tmp/luna-xhigh-1022/`（第二批在 `score2/`、`adjud2/`）。这些是可删的运行明细，删除后只能凭本报告和 `summary.json` 查看结果，无法重放盲裁。

---

以下为 `benchmark_summary` 生成的完整汇总（第二阶段全部配置不变，配置 28/29 为第三阶段补充行；逐实例表在各场景末尾）。

# 多模型 benchmark v1 汇总

第三阶段补充：第二阶段的全部实例与统计不变，另加 gpt-6-luna xhigh（配置 28）、max（配置 29）两个补充配置（Codex，各格取全部有效实例，不截取前 5 个，也没有一致性行：用户 2026-10-23，非因分数加跑的有效实例与预登记实例效力相同）；它们只给配置行和逐实例结果，不进预登记比较和 Holm 族。第二阶段：Strata 各格取全部有效实例（至多 10 个，不足按实际 n），其余同第一阶段。

每个场景 25 个预登记比较，Holm 校正，双侧 α = 0.05，Welch t 检验（Welch–Satterthwaite 自由度）。主统计多于前 5 个的格另给一致性行（按开始时刻的前 5 个；第三阶段补充配置不给）；补充行和敏感性行不进比较。不给比值、综合分和排名。

## code-spec-v5

### 配置

| 配置 | 行 | 有效 | 选入 n | 已计分 | 无效 | 均值 ± SD | SE | 95% 区间 | 负分数 | 最小 | 中位数 | r8.3 均值 | rawScore | f | 修复 | 耗时（分钟） | 占时限 | 未缓存 | 缓存 | 输出 | token 来源 | 工具调用 | 费用（美元；DeepSeek 括号内为人民币 ¥） | 周额度 | 模型 ID | service tier |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 codex gpt-6.1-sol low | 主统计 | 5 | 5 | 5 | 1 | 0.858 ± 0.011 | 0.005 | 0.844–0.871 | 0 | 0.848 | 0.852 | 0.858 | 0.858 | 0.000 | 0 | 2.3 | 0.09 | 114,355 | 1,063,859 | 6,505 | API usage (relay) | 14.4 | 只报 token |  | gpt-6.1-sol | default |
| 2 codex gpt-6.1-sol medium | 主统计 | 5 | 5 | 5 | 0 | 0.832 ± 0.007 | 0.003 | 0.824–0.840 | 0 | 0.826 | 0.832 | 0.832 | 0.832 | 0.000 | 0 | 2.8 | 0.12 | 112,228 | 1,056,410 | 8,011 | API usage (relay) | 14.8 | 只报 token |  | gpt-6.1-sol | default |
| 3 codex gpt-6.1-sol high | 主统计 | 5 | 5 | 5 | 0 | 0.826 ± 0.022 | 0.010 | 0.798–0.853 | 0 | 0.802 | 0.825 | 0.826 | 0.826 | 0.000 | 0 | 4.8 | 0.20 | 118,153 | 1,301,197 | 14,232 | API usage (relay) | 16.2 | 只报 token |  | gpt-6.1-sol | default |
| 4 codex gpt-6-luna low | 主统计 | 5 | 5 | 5 | 0 | 0.045 ± 0.026 | 0.012 | 0.012–0.078 | 0 | 0.021 | 0.037 | 0.045 | 0.045 | 0.000 | 0 | 0.8 | 0.08 | 80,284 | 924,774 | 3,473 | API usage (relay) | 13.8 | 只报 token |  | gpt-6-luna | default |
| 5 codex gpt-6-luna medium | 主统计 | 5 | 5 | 5 | 0 | 0.238 ± 0.177 | 0.079 | 0.019–0.457 | 0 | 0.012 | 0.251 | 0.238 | 0.238 | 0.000 | 0 | 1.2 | 0.12 | 87,073 | 995,302 | 5,573 | API usage (relay) | 15.8 | 只报 token |  | gpt-6-luna | default |
| 6 codex gpt-6-luna high | 主统计 | 5 | 5 | 5 | 0 | 0.517 ± 0.122 | 0.054 | 0.366–0.668 | 0 | 0.361 | 0.512 | 0.517 | 0.517 | 0.000 | 0 | 1.8 | 0.18 | 107,862 | 1,057,485 | 10,232 | API usage (relay) | 15.8 | 只报 token |  | gpt-6-luna | default |
| 7 codex deepseek-flash low | 主统计 | 5 | 5 | 5 | 0 | 0.531 ± 0.067 | 0.030 | 0.448–0.614 | 0 | 0.468 | 0.519 | 0.531 | 0.531 | 0.000 | 0 | 2.7 | 0.50 | 86,495 | 1,033,830 | 26,382 | API usage (relay) | 27.4 | ≥0.160（¥1.064） |  | deepseek-flash | default、not-returned |
| 8 codex deepseek-flash high | 主统计 | 5 | 5 | 5 | 0 | 0.531 ± 0.107 | 0.048 | 0.399–0.664 | 0 | 0.431 | 0.530 | 0.531 | 0.531 | 0.000 | 0 | 3.3 | 0.48 | 86,181 | 1,308,416 | 32,929 | API usage (relay) | 35.2 | ≥0.183（¥1.220） |  | deepseek-flash | default、not-returned |
| 8 codex deepseek-flash high | 补充行（high requested as medium, T=344） | 5 | 5 | 5 | 0 | 0.522 ± 0.162 | 0.073 | 0.321–0.723 | 0 | 0.245 | 0.559 | 0.522 | 0.527 | 0.008 | 1 | 2.3 | 0.40 | 79,784 | 1,115,725 | 22,965 | API usage (relay) | 27.0 | ≥0.145（¥0.970） |  | deepseek-flash | default、not-returned |
| 8 codex deepseek-flash high | 敏感性行：high+medium 合并（描述性，high requested as medium, T=344） | 10 | 10 | 10 |  | 0.527 ± 0.130 | 0.041 | 0.434–0.619 | 0 | 0.245 | 0.533 | 0.527 | 0.529 | 0.004 | 1 | 2.8 | 0.44 | 82,983 | 1,212,070 | 27,947 | API usage (relay) | 31.1 | ≥0.329（¥2.190） |  | deepseek-flash | default、not-returned |
| 9 codex deepseek-flash max | 主统计 | 5 | 5 | 5 | 0 | 0.601 ± 0.033 | 0.015 | 0.560–0.642 | 0 | 0.557 | 0.608 | 0.601 | 0.601 | 0.000 | 0 | 3.4 | 0.50 | 92,959 | 1,550,259 | 37,177 | API usage (relay) | 39.0 | ≥0.205（¥1.363） |  | deepseek-flash | default、not-returned |
| 10 codex strata-iq3_xxs low | 主统计 | 10 | 10 | 10 | 0 | 0.446 ± 0.055 | 0.017 | 0.407–0.486 | 0 | 0.361 | 0.459 | 0.446 | 0.452 | 0.013 | 16 | 8.8 | 0.57 | 112,020 | 2,222,715 | 36,291 | engine log | 27.6 | 0.694 |  | 未知 | 未知 |
| 10 codex strata-iq3_xxs low | 一致性行（前 5） | 10 | 5 | 5 |  | 0.447 ± 0.063 | 0.028 | 0.370–0.525 | 0 | 0.361 | 0.448 | 0.447 | 0.447 | 0.000 | 0 | 8.6 | 0.56 | 95,277 | 2,217,213 | 36,312 | engine log | 27.6 | 0.334 |  | 未知 | 未知 |
| 11 codex strata-iq3_xxs medium | 主统计 | 10 | 10 | 10 | 0 | 0.485 ± 0.058 | 0.018 | 0.443–0.527 | 0 | 0.363 | 0.477 | 0.485 | 0.491 | 0.013 | 5 | 8.1 | 0.54 | 84,961 | 1,485,550 | 34,352 | engine log | 23.8 | 0.527 |  | 未知 | 未知 |
| 11 codex strata-iq3_xxs medium | 一致性行（前 5） | 10 | 5 | 5 |  | 0.492 ± 0.034 | 0.015 | 0.450–0.535 | 0 | 0.461 | 0.478 | 0.492 | 0.499 | 0.013 | 3 | 8.4 | 0.55 | 84,249 | 1,351,208 | 36,154 | engine log | 24.0 | 0.256 |  | 未知 | 未知 |
| 12 codex strata-iq3_xxs high | 主统计 | 10 | 10 | 10 | 0 | 0.484 ± 0.029 | 0.009 | 0.463–0.505 | 0 | 0.444 | 0.472 | 0.484 | 0.484 | 0.000 | 0 | 9.3 | 0.61 | 81,277 | 1,584,342 | 40,614 | engine log | 29.2 | 0.566 |  | 未知 | 未知 |
| 12 codex strata-iq3_xxs high | 一致性行（前 5） | 10 | 5 | 5 |  | 0.492 ± 0.028 | 0.013 | 0.458–0.527 | 0 | 0.466 | 0.485 | 0.492 | 0.492 | 0.000 | 0 | 9.5 | 0.62 | 81,979 | 1,727,966 | 41,534 | engine log | 33.4 | 0.297 |  | 未知 | 未知 |
| 13 claude-code opus low | 主统计 | 5 | 5 | 5 | 0 | 0.616 ± 0.102 | 0.045 | 0.490–0.742 | 0 | 0.517 | 0.598 | 0.616 | 0.629 | 0.024 | 0 | 3.2 | 0.16 | 97,022 | 715,887 | 7,141 | Claude Code stream result usage | 12.4 | 5.310 | 0.46% | claude-opus-5-5 | standard |
| 14 claude-code opus medium | 主统计 | 5 | 5 | 5 | 0 | 0.699 ± 0.058 | 0.026 | 0.626–0.771 | 0 | 0.640 | 0.696 | 0.699 | 0.699 | 0.000 | 0 | 3.3 | 0.18 | 103,512 | 938,025 | 10,090 | Claude Code stream result usage | 15.2 | 6.087 | 0.52% | claude-opus-5-5 | standard |
| 15 claude-code opus high | 主统计 | 5 | 5 | 5 | 0 | 0.760 ± 0.056 | 0.025 | 0.690–0.830 | 0 | 0.702 | 0.734 | 0.760 | 0.764 | 0.006 | 1 | 4.6 | 0.23 | 106,450 | 1,015,201 | 13,054 | Claude Code stream result usage | 16.0 | 6.578 | 0.57% | claude-opus-5-5 | standard |
| 16 claude-code sonnet low | 主统计 | 5 | 5 | 5 | 0 | 0.458 ± 0.077 | 0.034 | 0.363–0.554 | 0 | 0.363 | 0.453 | 0.458 | 0.495 | 0.074 | 0 | 2.9 | 0.18 | 92,467 | 558,247 | 9,793 | Claude Code stream result usage | 10.4 | 2.618 | 0.23% | claude-sonnet-5-5 | standard |
| 17 claude-code sonnet medium | 主统计 | 5 | 5 | 5 | 0 | 0.575 ± 0.094 | 0.042 | 0.459–0.691 | 0 | 0.483 | 0.544 | 0.575 | 0.594 | 0.032 | 0 | 3.6 | 0.23 | 96,807 | 588,158 | 12,853 | Claude Code stream result usage | 11.4 | 2.873 | 0.25% | claude-sonnet-5-5 | standard |
| 18 claude-code sonnet high | 主统计 | 5 | 5 | 5 | 0 | 0.585 ± 0.086 | 0.038 | 0.479–0.691 | 0 | 0.521 | 0.546 | 0.585 | 0.615 | 0.051 | 1 | 4.4 | 0.27 | 107,023 | 716,451 | 20,243 | Claude Code stream result usage | 13.2 | 3.511 | 0.30% | claude-sonnet-5-5 | standard |
| 19 claude-code haiku low | 主统计 | 5 | 5 | 5 | 3 | 0.266 ± 0.132 | 0.059 | 0.102–0.430 | 0 | 0.129 | 0.246 | 0.266 | 0.284 | 0.011 | 0 | 4.8 | 0.52 | 111,221 | 4,067,961 | 19,811 | Claude Code stream result usage、Claude Code stream result usage (lower bound: a segment without result) | 21.4 | 未知 |  | claude-haiku-5-5 | standard |
| 20 claude-code haiku medium | 主统计 | 5 | 5 | 5 | 5 | 0.413 ± 0.157 | 0.070 | 0.218–0.609 | 0 | 0.210 | 0.480 | 0.413 | 0.422 | 0.014 | 1 | 2.2 | 0.26 | 103,158 | 749,440 | 24,535 | Claude Code stream result usage | 13.4 | 0.427 | 0.04% | claude-haiku-5-5 | standard |
| 21 claude-code haiku high | 主统计 | 5 | 5 | 5 | 2 | 0.577 ± 0.092 | 0.041 | 0.462–0.691 | 0 | 0.445 | 0.579 | 0.577 | 0.577 | 0.000 | 0 | 3.6 | 0.42 | 138,517 | 1,024,578 | 36,002 | Claude Code stream result usage | 19.2 | 0.823 | 0.07% | claude-haiku-5-5 | standard |
| 22 claude-code deepseek-flash low | 主统计 | 5 | 5 | 5 | 0 | 0.470 ± 0.096 | 0.043 | 0.351–0.590 | 0 | 0.366 | 0.427 | 0.470 | 0.470 | 0.000 | 0 | 3.3 | 0.48 | 74,102 | 540,314 | 17,573 | Claude Code stream result usage | 15.2 | 0.116（¥0.776） |  | deepseek-flash | standard |
| 23 claude-code deepseek-flash high | 主统计 | 5 | 5 | 5 | 0 | 0.435 ± 0.085 | 0.038 | 0.329–0.541 | 0 | 0.336 | 0.420 | 0.435 | 0.435 | 0.000 | 0 | 3.5 | 0.61 | 78,022 | 545,408 | 18,801 | Claude Code stream result usage | 16.0 | 0.123（¥0.821） |  | deepseek-flash | standard |
| 23 claude-code deepseek-flash high | 补充行（high requested as medium, T=391） | 5 | 5 | 5 | 0 | 0.509 ± 0.105 | 0.047 | 0.379–0.639 | 0 | 0.392 | 0.522 | 0.509 | 0.515 | 0.016 | 0 | 4.4 | 0.67 | 72,740 | 631,680 | 32,382 | Claude Code stream result usage | 15.8 | 0.161（¥1.075） |  | deepseek-flash | standard |
| 23 claude-code deepseek-flash high | 敏感性行：high+medium 合并（描述性，high requested as medium, T=391） | 10 | 10 | 10 |  | 0.472 ± 0.098 | 0.031 | 0.402–0.542 | 0 | 0.336 | 0.449 | 0.472 | 0.475 | 0.008 | 0 | 3.9 | 0.64 | 75,381 | 588,544 | 25,592 | Claude Code stream result usage | 15.9 | 0.284（¥1.895） |  | deepseek-flash | standard |
| 24 claude-code deepseek-flash max | 主统计 | 6 | 5 | 5 | 0 | 0.311 ± 0.192 | 0.086 | 0.073–0.549 | 0 | 0.000 | 0.338 | 0.311 | 0.311 | 0.000 | 0 | 4.4 | 0.70 | 未知 | 未知 | 未知 | Claude Code stream result usage | 17.0 | 0.165（¥1.103） |  | deepseek-flash | standard |
| 25 claude-code strata-iq3_xxs low | 主统计 | 10 | 10 | 10 | 1 | 0.435 ± 0.069 | 0.022 | 0.386–0.485 | 0 | 0.304 | 0.445 | 0.435 | 0.441 | 0.014 | 2 | 7.3 | 0.51 | 83,405 | 2,091,424 | 31,693 | engine log | 26.7 | 0.609 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 25 claude-code strata-iq3_xxs low | 一致性行（前 5） | 10 | 5 | 5 |  | 0.418 ± 0.091 | 0.041 | 0.304–0.531 | 0 | 0.304 | 0.433 | 0.418 | 0.420 | 0.007 | 1 | 7.9 | 0.55 | 87,776 | 2,495,671 | 35,440 | engine log | 27.6 | 0.349 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 26 claude-code strata-iq3_xxs medium | 主统计 | 10 | 10 | 10 | 0 | 0.475 ± 0.066 | 0.021 | 0.428–0.522 | 0 | 0.388 | 0.467 | 0.475 | 0.479 | 0.010 | 24 | 8.6 | 0.58 | 86,433 | 1,748,823 | 38,857 | engine log | 49.2 | 0.592 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 26 claude-code strata-iq3_xxs medium | 一致性行（前 5） | 10 | 5 | 5 |  | 0.480 ± 0.064 | 0.029 | 0.401–0.560 | 0 | 0.388 | 0.479 | 0.480 | 0.489 | 0.020 | 24 | 8.8 | 0.59 | 88,314 | 1,826,317 | 39,751 | engine log | 56.0 | 0.306 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 27 claude-code strata-iq3_xxs high | 主统计 | 10 | 10 | 10 | 0 | 0.464 ± 0.033 | 0.011 | 0.440–0.488 | 0 | 0.392 | 0.470 | 0.464 | 0.466 | 0.003 | 0 | 9.8 | 0.65 | 78,962 | 1,422,505 | 45,103 | engine log | 32.5 | 0.558 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 27 claude-code strata-iq3_xxs high | 一致性行（前 5） | 10 | 5 | 5 |  | 0.460 ± 0.048 | 0.022 | 0.400–0.520 | 0 | 0.392 | 0.463 | 0.460 | 0.463 | 0.006 | 0 | 10.1 | 0.67 | 77,847 | 1,452,332 | 46,232 | engine log | 25.6 | 0.283 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 28 codex gpt-6-luna xhigh | 第三阶段补充（不比较） | 8 | 8 | 8 |  | 0.666 ± 0.055 | 0.020 | 0.620–0.712 | 0 | 0.580 | 0.671 | 0.666 | 0.668 | 0.003 | 0 | 5.1 | 0.47 | 162,189 | 1,840,608 | 30,383 | API usage (relay) | 20.6 | 只报 token |  | gpt-6-luna | default、not-returned |
| 29 codex gpt-6-luna max | 第三阶段补充（不比较） | 6 | 6 | 6 |  | 0.685 ± 0.061 | 0.025 | 0.621–0.749 | 0 | 0.600 | 0.696 | 0.685 | 0.685 | 0.000 | 0 | 6.4 | 0.53 | 151,817 | 2,677,589 | 38,726 | API usage (relay) | 28.5 | 只报 token |  | gpt-6-luna | default、not-returned |

### 预登记比较

r8.3 列：同一批实例按 r8.3（截到 0、整体扣减相乘）计分的对照（plan §14.1）。

| 组 | 前者 | 后者 | n | 差值 | SE | t | 自由度 | p | Holm p | 结论 | r8.3 差值 | r8.3 Holm p | r8.3 结论 | 结论改变 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| codex | 10 codex strata-iq3_xxs low | 1 codex gpt-6.1-sol low | 10 / 5 | -0.411 | 0.018 | -22.85 | 10.3 | 0.0000 | 0.0000 | 低于 | -0.411 | 0.0000 | 低于 | 否 |
| codex | 10 codex strata-iq3_xxs low | 4 codex gpt-6-luna low | 10 / 5 | 0.401 | 0.021 | 19.11 | 13.0 | 0.0000 | 0.0000 | 高于 | 0.401 | 0.0000 | 高于 | 否 |
| codex | 10 codex strata-iq3_xxs low | 7 codex deepseek-flash low | 10 / 5 | -0.084 | 0.035 | -2.45 | 6.8 | 0.0453 | 0.6357 | 未分出 | -0.084 | 0.6357 | 未分出 | 否 |
| codex | 11 codex strata-iq3_xxs medium | 2 codex gpt-6.1-sol medium | 10 / 5 | -0.347 | 0.019 | -18.53 | 9.5 | 0.0000 | 0.0000 | 低于 | -0.347 | 0.0000 | 低于 | 否 |
| codex | 11 codex strata-iq3_xxs medium | 5 codex gpt-6-luna medium | 10 / 5 | 0.247 | 0.081 | 3.05 | 4.4 | 0.0332 | 0.5400 | 未分出 | 0.247 | 0.5400 | 未分出 | 否 |
| codex | 12 codex strata-iq3_xxs high | 3 codex gpt-6.1-sol high | 10 / 5 | -0.342 | 0.014 | -25.25 | 10.6 | 0.0000 | 0.0000 | 低于 | -0.342 | 0.0000 | 低于 | 否 |
| codex | 12 codex strata-iq3_xxs high | 6 codex gpt-6-luna high | 10 / 5 | -0.033 | 0.055 | -0.60 | 4.2 | 0.5812 | 1.0000 | 未分出 | -0.033 | 1.0000 | 未分出 | 否 |
| codex | 12 codex strata-iq3_xxs high | 8 codex deepseek-flash high | 10 / 5 | -0.047 | 0.049 | -0.98 | 4.3 | 0.3805 | 1.0000 | 未分出 | -0.047 | 1.0000 | 未分出 | 否 |
| claude-code | 25 claude-code strata-iq3_xxs low | 13 claude-code opus low | 10 / 5 | -0.181 | 0.050 | -3.59 | 5.9 | 0.0119 | 0.2256 | 未分出 | -0.181 | 0.2256 | 未分出 | 否 |
| claude-code | 25 claude-code strata-iq3_xxs low | 16 claude-code sonnet low | 10 / 5 | -0.023 | 0.041 | -0.56 | 7.3 | 0.5918 | 1.0000 | 未分出 | -0.023 | 1.0000 | 未分出 | 否 |
| claude-code | 25 claude-code strata-iq3_xxs low | 19 claude-code haiku low | 10 / 5 | 0.169 | 0.063 | 2.69 | 5.1 | 0.0424 | 0.6357 | 未分出 | 0.169 | 0.6357 | 未分出 | 否 |
| claude-code | 25 claude-code strata-iq3_xxs low | 22 claude-code deepseek-flash low | 10 / 5 | -0.035 | 0.048 | -0.73 | 6.1 | 0.4911 | 1.0000 | 未分出 | -0.035 | 1.0000 | 未分出 | 否 |
| claude-code | 26 claude-code strata-iq3_xxs medium | 14 claude-code opus medium | 10 / 5 | -0.223 | 0.033 | -6.69 | 9.1 | 0.0001 | 0.0017 | 低于 | -0.223 | 0.0017 | 低于 | 否 |
| claude-code | 26 claude-code strata-iq3_xxs medium | 17 claude-code sonnet medium | 10 / 5 | -0.100 | 0.047 | -2.14 | 6.1 | 0.0759 | 0.9104 | 未分出 | -0.100 | 0.9104 | 未分出 | 否 |
| claude-code | 26 claude-code strata-iq3_xxs medium | 20 claude-code haiku medium | 10 / 5 | 0.062 | 0.073 | 0.84 | 4.7 | 0.4395 | 1.0000 | 未分出 | 0.062 | 1.0000 | 未分出 | 否 |
| claude-code | 27 claude-code strata-iq3_xxs high | 15 claude-code opus high | 10 / 5 | -0.296 | 0.027 | -10.82 | 5.5 | 0.0001 | 0.0014 | 低于 | -0.296 | 0.0014 | 低于 | 否 |
| claude-code | 27 claude-code strata-iq3_xxs high | 18 claude-code sonnet high | 10 / 5 | -0.121 | 0.040 | -3.04 | 4.6 | 0.0318 | 0.5400 | 未分出 | -0.121 | 0.5400 | 未分出 | 否 |
| claude-code | 27 claude-code strata-iq3_xxs high | 21 claude-code haiku high | 10 / 5 | -0.113 | 0.043 | -2.65 | 4.5 | 0.0500 | 0.6503 | 未分出 | -0.113 | 0.6503 | 未分出 | 否 |
| claude-code | 27 claude-code strata-iq3_xxs high | 23 claude-code deepseek-flash high | 10 / 5 | 0.029 | 0.040 | 0.74 | 4.6 | 0.4960 | 1.0000 | 未分出 | 0.029 | 1.0000 | 未分出 | 否 |
| harness | 10 codex strata-iq3_xxs low | 25 claude-code strata-iq3_xxs low | 10 / 10 | 0.011 | 0.028 | 0.40 | 17.1 | 0.6924 | 1.0000 | 未分出 | 0.011 | 1.0000 | 未分出 | 否 |
| harness | 11 codex strata-iq3_xxs medium | 26 claude-code strata-iq3_xxs medium | 10 / 10 | 0.010 | 0.028 | 0.36 | 17.7 | 0.7260 | 1.0000 | 未分出 | 0.010 | 1.0000 | 未分出 | 否 |
| harness | 12 codex strata-iq3_xxs high | 27 claude-code strata-iq3_xxs high | 10 / 10 | 0.020 | 0.014 | 1.40 | 17.7 | 0.1783 | 1.0000 | 未分出 | 0.020 | 1.0000 | 未分出 | 否 |
| harness | 7 codex deepseek-flash low | 22 claude-code deepseek-flash low | 5 / 5 | 0.060 | 0.052 | 1.16 | 7.1 | 0.2848 | 1.0000 | 未分出 | 0.060 | 1.0000 | 未分出 | 否 |
| harness | 8 codex deepseek-flash high | 23 claude-code deepseek-flash high | 5 / 5 | 0.096 | 0.061 | 1.58 | 7.6 | 0.1550 | 1.0000 | 未分出 | 0.096 | 1.0000 | 未分出 | 否 |
| harness | 9 codex deepseek-flash max | 24 claude-code deepseek-flash max | 5 / 5 | 0.290 | 0.087 | 3.33 | 4.2 | 0.0267 | 0.4806 | 未分出 | 0.290 | 0.4806 | 未分出 | 否 |

### 逐实例

速度：引擎输入、引擎输出是模型直接速度，任务平均输入、输出是用户感知速度（未缓存输入、输出 ÷ 工作秒数）。API 模型分不出输入处理时间，引擎输入记未知；引擎输出按 API 请求时间算，含首 token 延迟和输入处理，是下限（≥）。

速度汇总口径（用户 2026-10-22）：多个实例的速度（summary.json 各行的 speeds_mean）是总 token ÷ 总耗时（各实例 speed_parts 的分子之和 ÷ 分母之和，speed_totals 给出两者），不是各实例速度的算术平均；任一实例该项未知，汇总即未知；任一实例该项是下限，汇总也是下限。Codex 上的 API 模型（gpt-6.1-sol、gpt-6-luna、DeepSeek）的引擎输出按 relay 日志的 output token ÷ 请求秒数计算，v1 的记录没有保存请求秒数，原始 relay 日志已删除，所以这一项按用户 10-22 的选择近似汇总：分子取实例的输出 token（同样来自 relay usage），分母取 输出 token ÷ 逐实例引擎输出速度 反推的请求秒数；汇总标为近似（speeds_approximate，表中写"≥≈"），仍是下限。

| 配置 | 实例 | 补充 | 有效 | 序 | 主统计 | 分数 | r8.3 分数 | rawScore | f | 修复 | 耗时（分钟） | 占时限 | 未缓存 | 缓存 | 输出 | 工具调用 | 费用（美元；DeepSeek 括号内为人民币 ¥） | 模型 ID | service tier | 引擎输入 tok/s | 引擎输出 tok/s | 任务平均输入 tok/s | 任务平均输出 tok/s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 codex gpt-6.1-sol low | sol-low-a2 |  | 是 | 1 | 是 | 0.852 | 0.852 | 0.852 | 0.000 | 0 | 2.6 | 0.11 | 115,551 | 1,292,288 | 7,016 | 17 | 只报 token | gpt-6.1-sol | default | 未知 | ≥46.0 | 752.6 | 45.7 |
| 1 codex gpt-6.1-sol low | sol-low-a3 |  | 是 | 2 | 是 | 0.872 | 0.872 | 0.872 | 0.000 | 0 | 1.6 | 0.07 | 99,162 | 819,584 | 5,127 | 12 | 只报 token | gpt-6.1-sol | default | 未知 | ≥52.5 | 1004.6 | 51.9 |
| 1 codex gpt-6.1-sol low | sol-low-a4 |  | 是 | 3 | 是 | 0.868 | 0.868 | 0.868 | 0.000 | 0 | 1.9 | 0.08 | 100,557 | 735,872 | 5,242 | 11 | 只报 token | gpt-6.1-sol | default | 未知 | ≥46.8 | 887.9 | 46.3 |
| 1 codex gpt-6.1-sol low | sol-low-a5 |  | 是 | 4 | 是 | 0.850 | 0.850 | 0.850 | 0.000 | 0 | 2.4 | 0.10 | 133,893 | 1,212,544 | 7,121 | 15 | 只报 token | gpt-6.1-sol | default | 未知 | ≥50.6 | 947.8 | 50.4 |
| 1 codex gpt-6.1-sol low | sol-low-a6 |  | 是 | 5 | 是 | 0.848 | 0.848 | 0.848 | 0.000 | 0 | 2.8 | 0.12 | 122,610 | 1,259,008 | 8,021 | 17 | 只报 token | gpt-6.1-sol | default | 未知 | ≥47.1 | 721.3 | 47.2 |
| 1 codex gpt-6.1-sol low | sol-low-a1 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 只报 token | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 |
| 2 codex gpt-6.1-sol medium | sol-medium-a1 |  | 是 | 1 | 是 | 0.842 | 0.842 | 0.842 | 0.000 | 0 | 2.7 | 0.12 | 103,785 | 869,504 | 8,188 | 13 | 只报 token | gpt-6.1-sol | default | 未知 | ≥50.1 | 634.3 | 50.0 |
| 2 codex gpt-6.1-sol medium | sol-medium-a2 |  | 是 | 2 | 是 | 0.832 | 0.832 | 0.832 | 0.000 | 0 | 2.1 | 0.10 | 103,843 | 872,448 | 5,850 | 12 | 只报 token | gpt-6.1-sol | default | 未知 | ≥46.2 | 808.2 | 45.5 |
| 2 codex gpt-6.1-sol medium | sol-medium-a3 |  | 是 | 3 | 是 | 0.827 | 0.827 | 0.827 | 0.000 | 0 | 2.9 | 0.13 | 125,710 | 1,044,864 | 7,920 | 15 | 只报 token | gpt-6.1-sol | default | 未知 | ≥46.1 | 725.6 | 45.7 |
| 2 codex gpt-6.1-sol medium | sol-medium-a4 |  | 是 | 4 | 是 | 0.832 | 0.832 | 0.832 | 0.000 | 0 | 3.1 | 0.14 | 117,827 | 1,576,320 | 8,961 | 20 | 只报 token | gpt-6.1-sol | default | 未知 | ≥48.0 | 628.7 | 47.8 |
| 2 codex gpt-6.1-sol medium | sol-medium-a5 |  | 是 | 5 | 是 | 0.826 | 0.826 | 0.826 | 0.000 | 0 | 3.1 | 0.14 | 109,975 | 918,912 | 9,138 | 14 | 只报 token | gpt-6.1-sol | default | 未知 | ≥49.9 | 599.2 | 49.8 |
| 3 codex gpt-6.1-sol high | sol-high-a1 |  | 是 | 1 | 是 | 0.858 | 0.858 | 0.858 | 0.000 | 0 | 5.0 | 0.21 | 119,187 | 1,195,264 | 15,105 | 16 | 只报 token | gpt-6.1-sol | default | 未知 | ≥50.9 | 399.7 | 50.7 |
| 3 codex gpt-6.1-sol high | sol-high-a2 |  | 是 | 2 | 是 | 0.834 | 0.834 | 0.834 | 0.000 | 0 | 5.5 | 0.23 | 127,798 | 1,666,816 | 15,635 | 19 | 只报 token | gpt-6.1-sol | default | 未知 | ≥47.4 | 386.5 | 47.3 |
| 3 codex gpt-6.1-sol high | sol-high-a3 |  | 是 | 3 | 是 | 0.809 | 0.809 | 0.809 | 0.000 | 0 | 4.2 | 0.18 | 120,580 | 1,243,008 | 12,495 | 15 | 只报 token | gpt-6.1-sol | default | 未知 | ≥49.8 | 476.8 | 49.4 |
| 3 codex gpt-6.1-sol high | sol-high-a4 |  | 是 | 4 | 是 | 0.825 | 0.825 | 0.825 | 0.000 | 0 | 5.0 | 0.21 | 110,267 | 1,154,432 | 15,064 | 15 | 只报 token | gpt-6.1-sol | default | 未知 | ≥50.2 | 366.6 | 50.1 |
| 3 codex gpt-6.1-sol high | sol-high-a5 |  | 是 | 5 | 是 | 0.802 | 0.802 | 0.802 | 0.000 | 0 | 4.3 | 0.18 | 112,932 | 1,246,464 | 12,860 | 16 | 只报 token | gpt-6.1-sol | default | 未知 | ≥49.7 | 434.5 | 49.5 |
| 4 codex gpt-6-luna low | luna-low-a1 |  | 是 | 1 | 是 | 0.037 | 0.037 | 0.037 | 0.000 | 0 | 0.9 | 0.08 | 90,579 | 1,096,832 | 3,546 | 17 | 只报 token | gpt-6-luna | default | 未知 | ≥67.8 | 1667.4 | 65.3 |
| 4 codex gpt-6-luna low | luna-low-a2 |  | 是 | 2 | 是 | 0.068 | 0.068 | 0.068 | 0.000 | 0 | 1.4 | 0.13 | 126,264 | 2,193,536 | 6,454 | 23 | 只报 token | gpt-6-luna | default | 未知 | ≥79.7 | 1532.8 | 78.3 |
| 4 codex gpt-6-luna low | luna-low-a3 |  | 是 | 3 | 是 | 0.023 | 0.023 | 0.023 | 0.000 | 0 | 0.6 | 0.05 | 54,941 | 424,320 | 2,448 | 10 | 只报 token | gpt-6-luna | default | 未知 | ≥72.1 | 1566.2 | 69.8 |
| 4 codex gpt-6-luna low | luna-low-a4 |  | 是 | 4 | 是 | 0.021 | 0.021 | 0.021 | 0.000 | 0 | 0.6 | 0.06 | 68,995 | 576,768 | 2,374 | 11 | 只报 token | gpt-6-luna | default | 未知 | ≥66.2 | 1898.5 | 65.3 |
| 4 codex gpt-6-luna low | luna-low-a5 |  | 是 | 5 | 是 | 0.079 | 0.079 | 0.079 | 0.000 | 0 | 0.7 | 0.06 | 60,640 | 332,416 | 2,542 | 8 | 只报 token | gpt-6-luna | default | 未知 | ≥68.9 | 1490.0 | 62.5 |
| 5 codex gpt-6-luna medium | luna-medium-a1 |  | 是 | 1 | 是 | 0.172 | 0.172 | 0.172 | 0.000 | 0 | 0.8 | 0.08 | 65,906 | 565,632 | 3,566 | 11 | 只报 token | gpt-6-luna | default | 未知 | ≥79.6 | 1400.9 | 75.8 |
| 5 codex gpt-6-luna medium | luna-medium-a2 |  | 是 | 2 | 是 | 0.012 | 0.012 | 0.012 | 0.000 | 0 | 0.7 | 0.08 | 96,059 | 871,040 | 3,208 | 14 | 只报 token | gpt-6-luna | default | 未知 | ≥72.7 | 2145.2 | 71.6 |
| 5 codex gpt-6-luna medium | luna-medium-a3 |  | 是 | 3 | 是 | 0.254 | 0.254 | 0.254 | 0.000 | 0 | 1.0 | 0.10 | 73,597 | 638,720 | 4,558 | 13 | 只报 token | gpt-6-luna | default | 未知 | ≥77.3 | 1228.6 | 76.1 |
| 5 codex gpt-6-luna medium | luna-medium-a4 |  | 是 | 4 | 是 | 0.500 | 0.500 | 0.500 | 0.000 | 0 | 2.0 | 0.20 | 100,654 | 1,727,744 | 9,676 | 24 | 只报 token | gpt-6-luna | default | 未知 | ≥81.1 | 840.8 | 80.8 |
| 5 codex gpt-6-luna medium | luna-medium-a5 |  | 是 | 5 | 是 | 0.251 | 0.251 | 0.251 | 0.000 | 0 | 1.5 | 0.15 | 99,149 | 1,173,376 | 6,856 | 17 | 只报 token | gpt-6-luna | default | 未知 | ≥76.9 | 1104.8 | 76.4 |
| 6 codex gpt-6-luna high | luna-high-a1 |  | 是 | 1 | 是 | 0.700 | 0.700 | 0.700 | 0.000 | 0 | 2.4 | 0.24 | 114,779 | 1,137,024 | 15,397 | 16 | 只报 token | gpt-6-luna | default | 未知 | ≥106.0 | 784.9 | 105.3 |
| 6 codex gpt-6-luna high | luna-high-a2 |  | 是 | 2 | 是 | 0.361 | 0.361 | 0.361 | 0.000 | 0 | 1.0 | 0.10 | 112,746 | 545,920 | 5,646 | 10 | 只报 token | gpt-6-luna | default | 未知 | ≥94.4 | 1858.2 | 93.1 |
| 6 codex gpt-6-luna high | luna-high-a3 |  | 是 | 3 | 是 | 0.482 | 0.482 | 0.482 | 0.000 | 0 | 2.2 | 0.21 | 103,333 | 1,773,952 | 10,446 | 27 | 只报 token | gpt-6-luna | default | 未知 | ≥80.7 | 798.3 | 80.7 |
| 6 codex gpt-6-luna high | luna-high-a4 |  | 是 | 4 | 是 | 0.512 | 0.512 | 0.512 | 0.000 | 0 | 2.3 | 0.22 | 111,778 | 1,309,568 | 13,625 | 17 | 只报 token | gpt-6-luna | default | 未知 | ≥100.6 | 824.1 | 100.4 |
| 6 codex gpt-6-luna high | luna-high-a5 |  | 是 | 5 | 是 | 0.528 | 0.528 | 0.528 | 0.000 | 0 | 1.1 | 0.11 | 96,674 | 520,960 | 6,044 | 9 | 只报 token | gpt-6-luna | default | 未知 | ≥92.3 | 1469.1 | 91.8 |
| 7 codex deepseek-flash low | codex-low-a1 |  | 是 | 1 | 是 | 0.566 | 0.566 | 0.566 | 0.000 | 0 | 2.9 | 0.52 | 94,750 | 1,091,968 | 25,866 | 22 | ≥0.033（¥0.220） | deepseek-flash | default、not-returned | 未知 | ≥160.5 | 549.1 | 149.9 |
| 7 codex deepseek-flash low | codex-low-a2 |  | 是 | 2 | 是 | 0.519 | 0.519 | 0.519 | 0.000 | 0 | 3.1 | 0.56 | 89,624 | 1,277,824 | 27,897 | 35 | ≥0.034（¥0.227） | deepseek-flash | default、not-returned | 未知 | ≥162.2 | 488.2 | 152.0 |
| 7 codex deepseek-flash low | codex-low-a3 |  | 是 | 3 | 是 | 0.627 | 0.627 | 0.627 | 0.000 | 0 | 2.8 | 0.52 | 81,919 | 670,976 | 28,353 | 26 | ≥0.031（¥0.209） | deepseek-flash | default、not-returned | 未知 | ≥178.4 | 482.3 | 166.9 |
| 7 codex deepseek-flash low | codex-low-a4 |  | 是 | 4 | 是 | 0.468 | 0.468 | 0.468 | 0.000 | 0 | 2.1 | 0.37 | 79,136 | 649,600 | 21,387 | 22 | 0.027（¥0.178） | deepseek-flash | default | 未知 | ≥175.1 | 643.1 | 173.8 |
| 7 codex deepseek-flash low | codex-low-a5 |  | 是 | 5 | 是 | 0.474 | 0.474 | 0.474 | 0.000 | 0 | 2.8 | 0.51 | 87,048 | 1,478,784 | 28,407 | 32 | ≥0.035（¥0.230） | deepseek-flash | default、not-returned | 未知 | ≥170.7 | 516.0 | 168.4 |
| 8 codex deepseek-flash high | codex-high-a1 |  | 是 | 1 | 是 | 0.533 | 0.533 | 0.533 | 0.000 | 0 | 3.6 | 0.52 | 89,213 | 1,397,376 | 32,965 | 34 | ≥0.037（¥0.249） | deepseek-flash | default、not-returned | 未知 | ≥162.7 | 416.9 | 154.0 |
| 8 codex deepseek-flash high | codex-high-a2 |  | 是 | 2 | 是 | 0.530 | 0.530 | 0.530 | 0.000 | 0 | 3.5 | 0.51 | 76,981 | 1,591,552 | 33,221 | 31 | 0.036（¥0.242） | deepseek-flash | default | 未知 | ≥161.9 | 370.7 | 160.0 |
| 8 codex deepseek-flash high | codex-high-a3 |  | 是 | 3 | 是 | 0.431 | 0.431 | 0.431 | 0.000 | 0 | 2.5 | 0.36 | 88,583 | 780,800 | 27,571 | 34 | 0.032（¥0.214） | deepseek-flash | default | 未知 | ≥187.2 | 599.2 | 186.5 |
| 8 codex deepseek-flash high | codex-high-a4 |  | 是 | 4 | 是 | 0.457 | 0.457 | 0.457 | 0.000 | 0 | 3.2 | 0.47 | 89,439 | 1,017,984 | 32,512 | 27 | 0.036（¥0.240） | deepseek-flash | default | 未知 | ≥168.2 | 460.6 | 167.4 |
| 8 codex deepseek-flash high | codex-high-a5 |  | 是 | 5 | 是 | 0.705 | 0.705 | 0.705 | 0.000 | 0 | 3.6 | 0.52 | 86,689 | 1,754,368 | 38,377 | 50 | ≥0.041（¥0.275） | deepseek-flash | default、not-returned | 未知 | ≥189.0 | 404.8 | 179.2 |
| 8 codex deepseek-flash high | codex-medium-a1 | high requested as medium, T=344 | 是 | 1 | 是 | 0.245 | 0.245 | 0.245 | 0.000 | 0 | 1.0 | 0.17 | 58,470 | 339,840 | 9,045 | 14 | 0.015（¥0.101） | deepseek-flash | default | 未知 | ≥153.6 | 993.3 | 153.7 |
| 8 codex deepseek-flash high | codex-medium-a2 | high requested as medium, T=344 | 是 | 2 | 是 | 0.650 | 0.650 | 0.650 | 0.000 | 0 | 3.3 | 0.57 | 83,692 | 1,371,520 | 34,568 | 26 | ≥0.037（¥0.249） | deepseek-flash | default、not-returned | 未知 | ≥178.7 | 423.4 | 174.9 |
| 8 codex deepseek-flash high | codex-medium-a3 | high requested as medium, T=344 | 是 | 3 | 是 | 0.559 | 0.559 | 0.559 | 0.000 | 0 | 2.6 | 0.46 | 84,048 | 908,032 | 26,173 | 22 | 0.031（¥0.207） | deepseek-flash | default | 未知 | ≥166.1 | 531.1 | 165.4 |
| 8 codex deepseek-flash high | codex-medium-a4 | high requested as medium, T=344 | 是 | 4 | 是 | 0.624 | 0.624 | 0.648 | 0.038 | 1 | 3.0 | 0.53 | 90,803 | 2,172,032 | 29,644 | 47 | ≥0.038（¥0.253） | deepseek-flash | default、not-returned | 未知 | ≥174.3 | 501.4 | 163.7 |
| 8 codex deepseek-flash high | codex-medium-a5 | high requested as medium, T=344 | 是 | 5 | 是 | 0.532 | 0.532 | 0.532 | 0.000 | 0 | 1.5 | 0.27 | 81,908 | 787,200 | 15,393 | 26 | 0.024（¥0.159） | deepseek-flash | default | 未知 | ≥169.6 | 891.1 | 167.5 |
| 9 codex deepseek-flash max | codex-max-a1 |  | 是 | 1 | 是 | 0.577 | 0.577 | 0.577 | 0.000 | 0 | 3.5 | 0.52 | 94,322 | 894,592 | 36,826 | 40 | ≥0.039（¥0.260） | deepseek-flash | default、not-returned | 未知 | ≥210.8 | 443.5 | 173.2 |
| 9 codex deepseek-flash max | codex-max-a2 |  | 是 | 2 | 是 | 0.557 | 0.557 | 0.557 | 0.000 | 0 | 2.5 | 0.37 | 90,744 | 1,228,544 | 29,362 | 37 | 0.035（¥0.233） | deepseek-flash | default | 未知 | ≥196.9 | 603.4 | 195.2 |
| 9 codex deepseek-flash max | codex-max-a3 |  | 是 | 3 | 是 | 0.638 | 0.638 | 0.638 | 0.000 | 0 | 3.6 | 0.52 | 89,894 | 1,771,776 | 40,346 | 43 | ≥0.043（¥0.287） | deepseek-flash | default、not-returned | 未知 | ≥193.4 | 421.9 | 189.4 |
| 9 codex deepseek-flash max | codex-max-a4 |  | 是 | 4 | 是 | 0.608 | 0.608 | 0.608 | 0.000 | 0 | 3.7 | 0.55 | 91,583 | 2,279,424 | 40,378 | 45 | ≥0.045（¥0.299） | deepseek-flash | default、not-returned | 未知 | ≥187.0 | 407.4 | 179.6 |
| 9 codex deepseek-flash max | codex-max-a5 |  | 是 | 5 | 是 | 0.625 | 0.625 | 0.625 | 0.000 | 0 | 3.7 | 0.55 | 98,254 | 1,576,960 | 38,972 | 30 | ≥0.043（¥0.286） | deepseek-flash | default、not-returned | 未知 | ≥189.7 | 443.6 | 175.9 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a1 |  | 是 | 1 | 是 | 0.448 | 0.448 | 0.448 | 0.000 | 0 | 8.9 | 0.58 | 93,732 | 2,872,972 | 37,642 | 30 | 0.078 | 未知 | 未知 | 1613.5 | 86.0 | 174.7 | 70.2 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a2 |  | 是 | 2 | 是 | 0.414 | 0.414 | 0.414 | 0.000 | 0 | 8.0 | 0.52 | 88,605 | 2,037,573 | 34,488 | 29 | 0.062 | 未知 | 未知 | 1623.3 | 89.2 | 184.2 | 71.7 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a3 |  | 是 | 3 | 是 | 0.511 | 0.511 | 0.511 | 0.000 | 0 | 9.4 | 0.61 | 96,301 | 2,647,217 | 39,928 | 33 | 0.076 | 未知 | 未知 | 1597.8 | 86.5 | 171.3 | 71.0 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a4 |  | 是 | 4 | 是 | 0.503 | 0.503 | 0.503 | 0.000 | 0 | 9.1 | 0.59 | 116,004 | 1,765,987 | 36,948 | 26 | 0.063 | 未知 | 未知 | 1846.1 | 83.4 | 212.7 | 67.8 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a5 |  | 是 | 5 | 是 | 0.361 | 0.361 | 0.361 | 0.000 | 0 | 7.6 | 0.50 | 81,742 | 1,762,317 | 32,556 | 20 | 0.056 | 未知 | 未知 | 1720.1 | 87.5 | 178.2 | 71.0 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a6 |  | 是 | 6 | 是 | 0.388 | 0.388 | 0.431 | 0.100 | 16 | 8.9 | 0.58 | 94,905 | 2,790,252 | 35,524 | 31 | 0.076 | 未知 | 未知 | 1630.8 | 82.4 | 177.8 | 66.6 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a7 |  | 是 | 7 | 是 | 0.388 | 0.388 | 0.388 | 0.000 | 0 | 6.6 | 0.43 | 80,736 | 1,393,901 | 26,390 | 23 | 0.047 | 未知 | 未知 | 1780.4 | 85.4 | 203.4 | 66.5 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a8 |  | 是 | 8 | 是 | 0.489 | 0.489 | 0.497 | 0.017 | 0 | 8.8 | 0.57 | 83,528 | 1,935,582 | 37,495 | 31 | 0.061 | 未知 | 未知 | 1755.7 | 85.6 | 158.1 | 71.0 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a9 |  | 是 | 9 | 是 | 0.493 | 0.493 | 0.500 | 0.014 | 0 | 11.6 | 0.76 | 296,055 | 2,963,558 | 45,797 | 26 | 0.113 | 未知 | 未知 | 2109.5 | 89.0 | 423.9 | 65.6 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a10 |  | 是 | 10 | 是 | 0.470 | 0.470 | 0.470 | 0.000 | 0 | 8.5 | 0.55 | 88,595 | 2,057,790 | 36,142 | 27 | 0.063 | 未知 | 未知 | 1680.6 | 87.5 | 173.8 | 70.9 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a1 |  | 是 | 1 | 是 | 0.520 | 0.520 | 0.520 | 0.000 | 0 | 7.8 | 0.52 | 80,883 | 1,310,953 | 33,450 | 21 | 0.049 | 未知 | 未知 | 1841.1 | 86.4 | 172.2 | 71.2 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a2 |  | 是 | 2 | 是 | 0.537 | 0.537 | 0.537 | 0.000 | 0 | 7.9 | 0.52 | 78,037 | 1,047,036 | 33,137 | 26 | 0.044 | 未知 | 未知 | 1898.7 | 84.4 | 165.5 | 70.3 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a3 |  | 是 | 3 | 是 | 0.467 | 0.467 | 0.475 | 0.018 | 1 | 7.1 | 0.47 | 80,111 | 1,081,959 | 29,435 | 18 | 0.043 | 未知 | 未知 | 1899.6 | 85.4 | 188.4 | 69.2 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a4 |  | 是 | 4 | 是 | 0.478 | 0.478 | 0.486 | 0.016 | 1 | 9.6 | 0.64 | 85,371 | 1,768,668 | 43,601 | 29 | 0.062 | 未知 | 未知 | 1736.2 | 89.0 | 147.5 | 75.3 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a5 |  | 是 | 5 | 是 | 0.461 | 0.461 | 0.475 | 0.029 | 1 | 9.4 | 0.62 | 96,842 | 1,547,426 | 41,149 | 26 | 0.059 | 未知 | 未知 | 1796.8 | 87.7 | 172.2 | 73.2 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a6 |  | 是 | 6 | 是 | 0.588 | 0.588 | 0.588 | 0.000 | 0 | 7.8 | 0.51 | 79,605 | 1,759,142 | 31,999 | 26 | 0.055 | 未知 | 未知 | 1614.0 | 85.7 | 171.0 | 68.7 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a7 |  | 是 | 7 | 是 | 0.363 | 0.363 | 0.391 | 0.071 | 2 | 7.8 | 0.51 | 88,110 | 1,522,165 | 31,322 | 21 | 0.052 | 未知 | 未知 | 1888.2 | 83.1 | 188.7 | 67.1 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a8 |  | 是 | 8 | 是 | 0.477 | 0.477 | 0.477 | 0.000 | 0 | 8.4 | 0.55 | 90,008 | 1,380,687 | 35,235 | 26 | 0.052 | 未知 | 未知 | 1959.5 | 85.4 | 179.6 | 70.3 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a9 |  | 是 | 9 | 是 | 0.471 | 0.471 | 0.471 | 0.000 | 0 | 8.1 | 0.53 | 91,170 | 1,682,175 | 33,088 | 25 | 0.056 | 未知 | 未知 | 1739.6 | 84.9 | 188.1 | 68.3 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a10 |  | 是 | 10 | 是 | 0.489 | 0.489 | 0.489 | 0.000 | 0 | 7.7 | 0.51 | 79,475 | 1,755,287 | 31,109 | 20 | 0.055 | 未知 | 未知 | 1836.5 | 82.8 | 171.8 | 67.3 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a1 |  | 是 | 1 | 是 | 0.485 | 0.485 | 0.485 | 0.000 | 0 | 8.8 | 0.58 | 91,051 | 1,216,246 | 37,947 | 23 | 0.051 | 未知 | 未知 | 1928.6 | 85.2 | 171.6 | 71.5 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a2 |  | 是 | 2 | 是 | 0.466 | 0.466 | 0.466 | 0.000 | 0 | 9.5 | 0.62 | 75,519 | 1,734,608 | 40,020 | 44 | 0.058 | 未知 | 未知 | 1507.1 | 83.5 | 132.7 | 70.3 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a3 |  | 是 | 3 | 是 | 0.509 | 0.509 | 0.509 | 0.000 | 0 | 10.1 | 0.66 | 82,767 | 1,896,331 | 44,474 | 27 | 0.064 | 未知 | 未知 | 1674.0 | 86.3 | 137.1 | 73.7 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a4 |  | 是 | 4 | 是 | 0.469 | 0.469 | 0.469 | 0.000 | 0 | 8.7 | 0.57 | 82,293 | 1,973,814 | 36,738 | 37 | 0.061 | 未知 | 未知 | 1537.2 | 85.9 | 158.2 | 70.6 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a5 |  | 是 | 5 | 是 | 0.532 | 0.532 | 0.532 | 0.000 | 0 | 10.6 | 0.69 | 78,266 | 1,818,831 | 48,491 | 36 | 0.064 | 未知 | 未知 | 1614.1 | 88.4 | 123.2 | 76.3 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a6 |  | 是 | 6 | 是 | 0.444 | 0.444 | 0.444 | 0.000 | 0 | 8.6 | 0.56 | 83,844 | 1,501,224 | 37,234 | 29 | 0.054 | 未知 | 未知 | 1847.9 | 86.7 | 162.3 | 72.1 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a7 |  | 是 | 7 | 是 | 0.527 | 0.527 | 0.527 | 0.000 | 0 | 8.3 | 0.54 | 82,158 | 1,086,661 | 35,909 | 20 | 0.047 | 未知 | 未知 | 1977.0 | 86.7 | 165.2 | 72.2 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a8 |  | 是 | 8 | 是 | 0.465 | 0.465 | 0.465 | 0.000 | 0 | 9.0 | 0.59 | 82,799 | 1,106,734 | 39,085 | 18 | 0.048 | 未知 | 未知 | 2015.4 | 85.9 | 153.8 | 72.6 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a9 |  | 是 | 9 | 是 | 0.464 | 0.464 | 0.464 | 0.000 | 0 | 10.1 | 0.66 | 78,427 | 2,218,027 | 45,379 | 32 | 0.069 | 未知 | 未知 | 1494.6 | 89.1 | 129.6 | 75.0 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a10 |  | 是 | 10 | 是 | 0.476 | 0.476 | 0.476 | 0.000 | 0 | 9.4 | 0.61 | 75,650 | 1,290,942 | 40,868 | 26 | 0.051 | 未知 | 未知 | 1727.9 | 85.9 | 134.5 | 72.7 |
| 13 claude-code opus low | opus-low-a1 |  | 是 | 1 | 是 | 0.598 | 0.598 | 0.598 | 0.000 | 0 | 4.4 | 0.22 | 98,190 | 716,682 | 6,688 | 12 | 1.063 | claude-opus-5-5 | standard | 未知 | ≥66.8 | 372.5 | 25.4 |
| 13 claude-code opus low | opus-low-a2 |  | 是 | 2 | 是 | 0.542 | 0.542 | 0.569 | 0.047 | 0 | 1.7 | 0.08 | 96,068 | 666,181 | 6,820 | 13 | 1.038 | claude-opus-5-5 | standard | 未知 | ≥82.2 | 947.0 | 67.2 |
| 13 claude-code opus low | opus-low-a3 |  | 是 | 3 | 是 | 0.517 | 0.517 | 0.557 | 0.073 | 0 | 2.0 | 0.10 | 96,040 | 615,842 | 6,776 | 11 | 1.027 | claude-opus-5-5 | standard | 未知 | ≥73.1 | 787.8 | 55.6 |
| 13 claude-code opus low | opus-low-a4 |  | 是 | 4 | 是 | 0.772 | 0.772 | 0.772 | 0.000 | 0 | 2.3 | 0.11 | 98,373 | 645,615 | 8,180 | 11 | 1.080 | claude-opus-5-5 | standard | 未知 | ≥95.0 | 715.5 | 59.5 |
| 13 claude-code opus low | opus-low-a5 |  | 是 | 5 | 是 | 0.651 | 0.651 | 0.651 | 0.000 | 0 | 5.4 | 0.27 | 96,439 | 935,116 | 7,240 | 15 | 1.103 | claude-opus-5-5 | standard | 未知 | ≥51.9 | 295.8 | 22.2 |
| 14 claude-code opus medium | opus-medium-a1 |  | 是 | 1 | 是 | 0.731 | 0.731 | 0.731 | 0.000 | 0 | 2.1 | 0.11 | 101,604 | 634,852 | 10,491 | 10 | 1.150 | claude-opus-5-5 | standard | 未知 | ≥92.4 | 825.3 | 85.2 |
| 14 claude-code opus medium | opus-medium-a2 |  | 是 | 2 | 是 | 0.779 | 0.779 | 0.779 | 0.000 | 0 | 3.8 | 0.20 | 109,116 | 1,294,016 | 9,859 | 20 | 1.329 | claude-opus-5-5 | standard | 未知 | ≥81.5 | 478.1 | 43.2 |
| 14 claude-code opus medium | opus-medium-a3 |  | 是 | 3 | 是 | 0.647 | 0.647 | 0.647 | 0.000 | 0 | 3.2 | 0.17 | 104,098 | 1,079,177 | 10,796 | 18 | 1.264 | claude-opus-5-5 | standard | 未知 | ≥92.4 | 542.6 | 56.3 |
| 14 claude-code opus medium | opus-medium-a4 |  | 是 | 4 | 是 | 0.640 | 0.640 | 0.640 | 0.000 | 0 | 2.7 | 0.14 | 100,051 | 792,307 | 8,806 | 14 | 1.135 | claude-opus-5-5 | standard | 未知 | ≥89.4 | 623.8 | 54.9 |
| 14 claude-code opus medium | opus-medium-a5 |  | 是 | 5 | 是 | 0.696 | 0.696 | 0.696 | 0.000 | 0 | 4.8 | 0.26 | 102,690 | 889,775 | 10,498 | 14 | 1.209 | claude-opus-5-5 | standard | 未知 | ≥87.2 | 355.2 | 36.3 |
| 15 claude-code opus high | opus-high-a1 |  | 是 | 1 | 是 | 0.819 | 0.819 | 0.819 | 0.000 | 0 | 2.9 | 0.15 | 110,108 | 751,287 | 14,363 | 14 | 1.318 | claude-opus-5-5 | standard | 未知 | ≥97.5 | 622.2 | 81.2 |
| 15 claude-code opus high | opus-high-a2 |  | 是 | 2 | 是 | 0.702 | 0.702 | 0.702 | 0.000 | 0 | 4.9 | 0.25 | 104,340 | 1,032,435 | 12,710 | 17 | 1.295 | claude-opus-5-5 | standard | 未知 | ≥82.7 | 355.5 | 43.3 |
| 15 claude-code opus high | opus-high-a3 |  | 是 | 3 | 是 | 0.722 | 0.722 | 0.743 | 0.029 | 1 | 5.6 | 0.28 | 106,183 | 822,399 | 12,982 | 13 | 1.273 | claude-opus-5-5 | standard | 未知 | ≥76.9 | 316.4 | 38.7 |
| 15 claude-code opus high | opus-high-a4 |  | 是 | 4 | 是 | 0.821 | 0.821 | 0.821 | 0.000 | 0 | 2.9 | 0.15 | 107,202 | 1,233,340 | 13,148 | 19 | 1.367 | claude-opus-5-5 | standard | 未知 | ≥90.1 | 607.4 | 74.5 |
| 15 claude-code opus high | opus-high-a5 |  | 是 | 5 | 是 | 0.734 | 0.734 | 0.734 | 0.000 | 0 | 6.6 | 0.33 | 104,416 | 1,236,542 | 12,066 | 17 | 1.324 | claude-opus-5-5 | standard | 未知 | ≥89.8 | 265.5 | 30.7 |
| 16 claude-code sonnet low | sonnet-low-a1 |  | 是 | 1 | 是 | 0.409 | 0.409 | 0.444 | 0.079 | 0 | 3.1 | 0.19 | 94,210 | 527,995 | 9,608 | 9 | 0.526 | claude-sonnet-5-5 | standard | 未知 | ≥91.3 | 514.2 | 52.4 |
| 16 claude-code sonnet low | sonnet-low-a2 |  | 是 | 2 | 是 | 0.554 | 0.554 | 0.582 | 0.048 | 0 | 2.9 | 0.17 | 91,225 | 622,167 | 9,585 | 11 | 0.523 | claude-sonnet-5-5 | standard | 未知 | ≥98.9 | 531.9 | 55.9 |
| 16 claude-code sonnet low | sonnet-low-a3 |  | 是 | 3 | 是 | 0.453 | 0.453 | 0.486 | 0.068 | 0 | 3.5 | 0.21 | 98,320 | 481,175 | 11,017 | 10 | 0.552 | claude-sonnet-5-5 | standard | 未知 | ≥109.2 | 463.6 | 51.9 |
| 16 claude-code sonnet low | sonnet-low-a4 |  | 是 | 4 | 是 | 0.512 | 0.512 | 0.569 | 0.100 | 0 | 1.8 | 0.11 | 90,510 | 640,415 | 10,162 | 12 | 0.528 | claude-sonnet-5-5 | standard | 未知 | ≥101.1 | 834.0 | 93.6 |
| 16 claude-code sonnet low | sonnet-low-a5 |  | 是 | 5 | 是 | 0.363 | 0.363 | 0.392 | 0.075 | 0 | 3.4 | 0.21 | 88,069 | 519,482 | 8,594 | 10 | 0.490 | claude-sonnet-5-5 | standard | 未知 | ≥91.7 | 426.7 | 41.6 |
| 17 claude-code sonnet medium | sonnet-medium-a1 |  | 是 | 1 | 是 | 0.544 | 0.544 | 0.595 | 0.084 | 0 | 4.1 | 0.27 | 97,676 | 614,481 | 14,594 | 12 | 0.598 | claude-sonnet-5-5 | standard | 未知 | ≥102.0 | 399.3 | 59.7 |
| 17 claude-code sonnet medium | sonnet-medium-a2 |  | 是 | 2 | 是 | 0.483 | 0.483 | 0.483 | 0.000 | 0 | 2.9 | 0.19 | 92,803 | 460,091 | 10,760 | 9 | 0.525 | claude-sonnet-5-5 | standard | 未知 | ≥106.2 | 530.8 | 61.5 |
| 17 claude-code sonnet medium | sonnet-medium-a3 |  | 是 | 3 | 是 | 0.647 | 0.647 | 0.647 | 0.000 | 0 | 5.5 | 0.36 | 102,633 | 855,571 | 13,067 | 15 | 0.627 | claude-sonnet-5-5 | standard | 未知 | ≥98.3 | 313.5 | 39.9 |
| 17 claude-code sonnet medium | sonnet-medium-a4 |  | 是 | 4 | 是 | 0.698 | 0.698 | 0.716 | 0.025 | 0 | 1.7 | 0.11 | 96,405 | 462,073 | 12,548 | 9 | 0.557 | claude-sonnet-5-5 | standard | 未知 | ≥128.3 | 930.3 | 121.1 |
| 17 claude-code sonnet medium | sonnet-medium-a5 |  | 是 | 5 | 是 | 0.503 | 0.503 | 0.528 | 0.048 | 0 | 3.6 | 0.24 | 94,517 | 548,572 | 13,297 | 12 | 0.566 | claude-sonnet-5-5 | standard | 未知 | ≥93.7 | 436.7 | 61.4 |
| 18 claude-code sonnet high | sonnet-high-a1 |  | 是 | 1 | 是 | 0.521 | 0.521 | 0.563 | 0.075 | 0 | 4.2 | 0.26 | 101,714 | 632,723 | 17,807 | 13 | 0.648 | claude-sonnet-5-5 | standard | 未知 | ≥112.0 | 399.1 | 69.9 |
| 18 claude-code sonnet high | sonnet-high-a2 |  | 是 | 2 | 是 | 0.546 | 0.546 | 0.595 | 0.082 | 1 | 5.1 | 0.31 | 108,051 | 746,816 | 20,085 | 13 | 0.708 | claude-sonnet-5-5 | standard | 未知 | ≥112.0 | 353.2 | 65.7 |
| 18 claude-code sonnet high | sonnet-high-a3 |  | 是 | 3 | 是 | 0.524 | 0.524 | 0.583 | 0.100 | 0 | 5.7 | 0.35 | 108,350 | 613,981 | 22,024 | 12 | 0.715 | claude-sonnet-5-5 | standard | 未知 | ≥120.9 | 316.2 | 64.3 |
| 18 claude-code sonnet high | sonnet-high-a4 |  | 是 | 4 | 是 | 0.608 | 0.608 | 0.608 | 0.000 | 0 | 2.7 | 0.17 | 102,937 | 686,564 | 20,797 | 14 | 0.688 | claude-sonnet-5-5 | standard | 未知 | ≥135.9 | 638.8 | 129.1 |
| 18 claude-code sonnet high | sonnet-high-a5 |  | 是 | 5 | 是 | 0.725 | 0.725 | 0.725 | 0.000 | 0 | 4.5 | 0.27 | 114,063 | 902,173 | 20,504 | 14 | 0.751 | claude-sonnet-5-5 | standard | 未知 | ≥113.9 | 426.1 | 76.6 |
| 19 claude-code haiku low | haiku-low-a1 |  | 是 | 1 | 是 | 0.150 | 0.150 | 0.150 | 0.000 | 0 | 1.3 | 0.15 | 54,835 | 314,769 | 6,185 | 8 | 0.017 | claude-haiku-5-5 | standard | 未知 | ≥141.7 | 684.4 | 77.2 |
| 19 claude-code haiku low | haiku-low-a3 |  | 是 | 2 | 是 | 0.246 | 0.246 | 0.246 | 0.000 | 0 | 3.4 | 0.37 | 71,988 | 431,169 | 9,375 | 10 | 0.023 | claude-haiku-5-5 | standard | 未知 | ≥183.6 | 354.8 | 46.2 |
| 19 claude-code haiku low | haiku-low-a6 |  | 是 | 3 | 是 | 0.129 | 0.129 | 0.129 | 0.000 | 0 | 0.9 | 0.10 | 49,415 | 494,295 | 7,208 | 11 | 0.018 | claude-haiku-5-5 | standard | 未知 | ≥157.2 | 934.3 | 136.3 |
| 19 claude-code haiku low | haiku-low-a7 |  | 是 | 4 | 是 | 0.384 | 0.384 | 0.426 | 0.000 | 0 | 9.1 | 1.00 | 258,204 | 11,172,693 | 38,486 | 38 | 0.741 | claude-haiku-5-5 | standard | 未知 | ≥100.2 | 473.9 | 70.6 |
| 19 claude-code haiku low | haiku-low-a8 |  | 是 | 5 | 是 | 0.420 | 0.420 | 0.466 | 0.054 | 0 | 9.1 | 1.00 | 121,664 | 7,926,878 | 37,803 | 40 | 未知 | claude-haiku-5-5 | standard | 未知 | 未知 | ≥223.2 | ≥69.3 |
| 19 claude-code haiku low | haiku-low-a2 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 3.6 | 0.39 | 57,834 | 469,997 | 7,619 | 11 | 0.020 | claude-haiku-5-5 | standard | 未知 | ≥105.8 | 271.5 | 35.8 |
| 19 claude-code haiku low | haiku-low-a4 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 1.4 | 0.16 | 53,925 | 400,589 | 8,281 | 10 | 0.019 | claude-haiku-5-5 | standard | 未知 | ≥176.3 | 629.6 | 96.7 |
| 19 claude-code haiku low | haiku-low-a5 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 3.3 | 0.36 | 69,023 | 712,631 | 12,577 | 13 | 0.027 | claude-haiku-5-5 | standard | 未知 | ≥163.1 | 352.6 | 64.3 |
| 20 claude-code haiku medium | haiku-medium-a6 |  | 是 | 1 | 是 | 0.210 | 0.210 | 0.210 | 0.000 | 0 | 1.3 | 0.16 | 67,717 | 476,553 | 12,439 | 11 | 0.025 | claude-haiku-5-5 | standard | 未知 | ≥171.4 | 846.1 | 155.4 |
| 20 claude-code haiku medium | haiku-medium-a7 |  | 是 | 2 | 是 | 0.287 | 0.287 | 0.287 | 0.000 | 0 | 1.2 | 0.14 | 65,789 | 472,350 | 11,478 | 9 | 0.024 | claude-haiku-5-5 | standard | 未知 | ≥173.1 | 915.7 | 159.8 |
| 20 claude-code haiku medium | haiku-medium-a8 |  | 是 | 3 | 是 | 0.480 | 0.480 | 0.480 | 0.000 | 0 | 2.6 | 0.30 | 117,863 | 866,360 | 28,385 | 13 | 0.110 | claude-haiku-5-5 | standard | 未知 | ≥197.5 | 768.4 | 185.1 |
| 20 claude-code haiku medium | haiku-medium-a9 |  | 是 | 4 | 是 | 0.579 | 0.579 | 0.623 | 0.071 | 1 | 3.3 | 0.38 | 148,728 | 788,859 | 41,393 | 13 | 0.160 | claude-haiku-5-5 | standard | 未知 | ≥216.3 | 757.6 | 210.8 |
| 20 claude-code haiku medium | haiku-medium-a10 |  | 是 | 5 | 是 | 0.511 | 0.511 | 0.511 | 0.000 | 0 | 2.7 | 0.32 | 115,694 | 1,143,079 | 28,980 | 21 | 0.109 | claude-haiku-5-5 | standard | 未知 | ≥184.5 | 709.3 | 177.7 |
| 20 claude-code haiku medium | haiku-medium-a1 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 1.0 | 0.11 | 50,542 | 302,552 | 8,157 | 9 | 0.017 | claude-haiku-5-5 | standard | 未知 | ≥154.1 | 840.6 | 135.7 |
| 20 claude-code haiku medium | haiku-medium-a2 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 3.3 | 0.37 | 78,392 | 500,255 | 12,392 | 10 | 0.027 | claude-haiku-5-5 | standard | 未知 | ≥133.7 | 397.2 | 62.8 |
| 20 claude-code haiku medium | haiku-medium-a3 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 4.0 | 0.44 | 56,643 | 484,580 | 11,291 | 11 | 0.022 | claude-haiku-5-5 | standard | 未知 | ≥191.1 | 238.4 | 47.5 |
| 20 claude-code haiku medium | haiku-medium-a4 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 3.1 | 0.35 | 58,311 | 465,763 | 9,976 | 12 | 0.021 | claude-haiku-5-5 | standard | 未知 | ≥150.5 | 310.8 | 53.2 |
| 20 claude-code haiku medium | haiku-medium-a5 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 3.2 | 0.35 | 57,200 | 416,834 | 10,464 | 12 | 0.021 | claude-haiku-5-5 | standard | 未知 | ≥139.6 | 300.4 | 55.0 |
| 21 claude-code haiku high | haiku-high-a2 |  | 是 | 1 | 是 | 0.680 | 0.680 | 0.680 | 0.000 | 0 | 3.6 | 0.42 | 135,072 | 844,167 | 42,132 | 17 | 0.144 | claude-haiku-5-5 | standard | 未知 | ≥223.6 | 620.6 | 193.6 |
| 21 claude-code haiku high | haiku-high-a3 |  | 是 | 2 | 是 | 0.537 | 0.537 | 0.537 | 0.000 | 0 | 4.0 | 0.47 | 136,499 | 753,769 | 31,197 | 17 | 0.146 | claude-haiku-5-5 | standard | 未知 | ≥213.7 | 564.2 | 129.0 |
| 21 claude-code haiku high | haiku-high-a5 |  | 是 | 3 | 是 | 0.445 | 0.445 | 0.445 | 0.000 | 0 | 4.2 | 0.49 | 137,126 | 928,337 | 29,162 | 20 | 0.154 | claude-haiku-5-5 | standard | 未知 | ≥173.0 | 543.2 | 115.5 |
| 21 claude-code haiku high | haiku-high-a6 |  | 是 | 4 | 是 | 0.643 | 0.643 | 0.643 | 0.000 | 0 | 3.6 | 0.42 | 145,707 | 1,416,307 | 44,023 | 22 | 0.225 | claude-haiku-5-5 | standard | 未知 | ≥215.7 | 667.9 | 201.8 |
| 21 claude-code haiku high | haiku-high-a7 |  | 是 | 5 | 是 | 0.579 | 0.579 | 0.579 | 0.000 | 0 | 2.7 | 0.32 | 138,182 | 1,180,309 | 33,496 | 20 | 0.154 | claude-haiku-5-5 | standard | 未知 | ≥214.3 | 839.4 | 203.5 |
| 21 claude-code haiku high | haiku-high-a1 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 4.0 | 0.46 | 98,434 | 1,646,496 | 26,107 | 23 | 0.078 | claude-haiku-5-5 | standard | 未知 | ≥173.2 | 415.3 | 110.1 |
| 21 claude-code haiku high | haiku-high-a4 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 3.2 | 0.37 | 99,639 | 596,970 | 20,831 | 13 | 0.057 | claude-haiku-5-5 | standard | 未知 | ≥183.8 | 521.6 | 109.0 |
| 22 claude-code deepseek-flash low | cc-low-a1 |  | 是 | 1 | 是 | 0.533 | 0.533 | 0.533 | 0.000 | 0 | 3.6 | 0.53 | 85,980 | 865,664 | 24,463 | 16 | 0.030（¥0.201） | deepseek-flash | standard | 未知 | ≥169.2 | 393.7 | 112.0 |
| 22 claude-code deepseek-flash low | cc-low-a2 |  | 是 | 2 | 是 | 0.427 | 0.427 | 0.427 | 0.000 | 0 | 4.2 | 0.62 | 66,471 | 444,032 | 16,202 | 16 | 0.021（¥0.140） | deepseek-flash | standard | 未知 | ≥122.2 | 263.4 | 64.2 |
| 22 claude-code deepseek-flash low | cc-low-a3 |  | 是 | 3 | 是 | 0.423 | 0.423 | 0.423 | 0.000 | 0 | 3.3 | 0.49 | 74,018 | 375,296 | 17,775 | 15 | 0.023（¥0.153） | deepseek-flash | standard | 未知 | ≥184.0 | 371.9 | 89.3 |
| 22 claude-code deepseek-flash low | cc-low-a4 |  | 是 | 4 | 是 | 0.604 | 0.604 | 0.604 | 0.000 | 0 | 4.0 | 0.58 | 71,409 | 642,176 | 18,590 | 14 | 0.024（¥0.159） | deepseek-flash | standard | 未知 | ≥172.7 | 300.1 | 78.1 |
| 22 claude-code deepseek-flash low | cc-low-a5 |  | 是 | 5 | 是 | 0.366 | 0.366 | 0.366 | 0.000 | 0 | 1.2 | 0.17 | 72,632 | 374,400 | 10,836 | 15 | 0.019（¥0.123） | deepseek-flash | standard | 未知 | ≥163.3 | 1035.1 | 154.4 |
| 23 claude-code deepseek-flash high | cc-high-a1 |  | 是 | 1 | 是 | 0.336 | 0.336 | 0.336 | 0.000 | 0 | 4.9 | 0.86 | 70,481 | 468,352 | 10,458 | 20 | 0.018（¥0.122） | deepseek-flash | standard | 未知 | ≥112.3 | 240.8 | 35.7 |
| 23 claude-code deepseek-flash high | cc-high-a2 |  | 是 | 2 | 是 | 0.385 | 0.385 | 0.385 | 0.000 | 0 | 1.6 | 0.28 | 73,946 | 725,376 | 13,835 | 18 | 0.022（¥0.144） | deepseek-flash | standard | 未知 | ≥161.3 | 761.3 | 142.4 |
| 23 claude-code deepseek-flash high | cc-high-a3 |  | 是 | 3 | 是 | 0.420 | 0.420 | 0.420 | 0.000 | 0 | 4.1 | 0.71 | 76,686 | 523,264 | 20,829 | 15 | 0.026（¥0.171） | deepseek-flash | standard | 未知 | ≥177.4 | 315.1 | 85.6 |
| 23 claude-code deepseek-flash high | cc-high-a4 |  | 是 | 4 | 是 | 0.557 | 0.557 | 0.557 | 0.000 | 0 | 3.3 | 0.57 | 82,746 | 427,648 | 26,259 | 12 | 0.029（¥0.196） | deepseek-flash | standard | 未知 | ≥208.7 | 420.8 | 133.5 |
| 23 claude-code deepseek-flash high | cc-high-a5 |  | 是 | 5 | 是 | 0.475 | 0.475 | 0.475 | 0.000 | 0 | 3.6 | 0.63 | 86,252 | 582,400 | 22,624 | 15 | 0.028（¥0.188） | deepseek-flash | standard | 未知 | ≥188.6 | 399.1 | 104.7 |
| 23 claude-code deepseek-flash high | cc-medium-a1 | high requested as medium, T=391 | 是 | 1 | 是 | 0.392 | 0.392 | 0.425 | 0.079 | 0 | 4.3 | 0.66 | 67,026 | 599,936 | 27,257 | 15 | 0.028（¥0.188） | deepseek-flash | standard | 未知 | ≥194.1 | 259.9 | 105.7 |
| 23 claude-code deepseek-flash high | cc-medium-a2 | high requested as medium, T=391 | 是 | 2 | 是 | 0.423 | 0.423 | 0.423 | 0.000 | 0 | 4.9 | 0.76 | 83,195 | 547,328 | 41,634 | 15 | 0.039（¥0.261） | deepseek-flash | standard | 未知 | ≥180.7 | 281.5 | 140.9 |
| 23 claude-code deepseek-flash high | cc-medium-a3 | high requested as medium, T=391 | 是 | 3 | 是 | 0.522 | 0.522 | 0.522 | 0.000 | 0 | 3.4 | 0.52 | 68,118 | 686,208 | 31,031 | 17 | 0.031（¥0.206） | deepseek-flash | standard | 未知 | ≥191.4 | 336.9 | 153.5 |
| 23 claude-code deepseek-flash high | cc-medium-a4 | high requested as medium, T=391 | 是 | 4 | 是 | 0.652 | 0.652 | 0.652 | 0.000 | 0 | 4.8 | 0.74 | 68,827 | 482,688 | 38,607 | 13 | 0.035（¥0.233） | deepseek-flash | standard | 未知 | ≥190.4 | 238.5 | 133.8 |
| 23 claude-code deepseek-flash high | cc-medium-a5 | high requested as medium, T=391 | 是 | 5 | 是 | 0.554 | 0.554 | 0.554 | 0.000 | 0 | 4.5 | 0.69 | 76,535 | 842,240 | 23,381 | 19 | 0.028（¥0.187） | deepseek-flash | standard | 未知 | ≥168.8 | 282.0 | 86.2 |
| 24 claude-code deepseek-flash max | cc-max-a1 |  | 是 | 1 | 是 | 0.338 | 0.338 | 0.338 | 0.000 | 0 | 3.9 | 0.63 | 67,763 | 445,440 | 19,310 | 16 | 0.023（¥0.154） | deepseek-flash | standard | 未知 | ≥163.0 | 287.2 | 81.8 |
| 24 claude-code deepseek-flash max | cc-max-a2 |  | 是 | 2 | 是 | 0.382 | 0.382 | 0.382 | 0.000 | 0 | 3.5 | 0.56 | 62,577 | 1,098,752 | 25,352 | 24 | 0.028（¥0.186） | deepseek-flash | standard | 未知 | ≥170.0 | 295.9 | 119.9 |
| 24 claude-code deepseek-flash max | cc-max-a3 |  | 是 | 3 | 是 | 0.523 | 0.523 | 0.523 | 0.000 | 0 | 4.2 | 0.67 | 83,089 | 494,464 | 41,543 | 12 | 0.039（¥0.259） | deepseek-flash | standard | 未知 | ≥227.6 | 331.7 | 165.9 |
| 24 claude-code deepseek-flash max | cc-max-a4 |  | 是 | 4 | 是 | 0.000 | 0.000 | 0.000 | 0.000 | 0 | 6.3 | 1.00 | 未知 | 未知 | 未知 | 13 | 0.049（¥0.326） | deepseek-flash | standard | 未知 | 未知 | 未知 | 未知 |
| 24 claude-code deepseek-flash max | cc-max-a5 |  | 是 | 5 | 是 | 0.313 | 0.313 | 0.313 | 0.000 | 0 | 4.0 | 0.63 | 76,642 | 601,856 | 22,311 | 20 | 0.027（¥0.178） | deepseek-flash | standard | 未知 | ≥169.5 | 322.5 | 93.9 |
| 24 claude-code deepseek-flash max | cc-max-a6 |  | 是 | 6 |  | unscored |  | 未知 | 未知 | 未知 | 5.3 | 0.84 | 56,803 | 528,256 | 11,595 | 17 | 0.017（¥0.114） | deepseek-flash | standard | 未知 | ≥100.6 | 179.8 | 36.7 |
| 25 claude-code strata-iq3_xxs low | strata-low-a1 |  | 是 | 1 | 是 | 0.458 | 0.458 | 0.458 | 0.000 | 0 | 7.5 | 0.52 | 87,106 | 2,302,884 | 33,800 | 27 | 0.066 | qwen3.8-flash-next-iq3_xxs | not-returned | 1614.2 | 89.0 | 193.1 | 74.9 |
| 25 claude-code strata-iq3_xxs low | strata-low-a2 |  | 是 | 2 | 是 | 0.356 | 0.356 | 0.356 | 0.000 | 0 | 6.4 | 0.44 | 72,986 | 1,580,239 | 29,006 | 20 | 0.050 | qwen3.8-flash-next-iq3_xxs | not-returned | 1680.3 | 88.5 | 190.8 | 75.8 |
| 25 claude-code strata-iq3_xxs low | strata-low-a3 |  | 是 | 3 | 是 | 0.433 | 0.433 | 0.433 | 0.000 | 0 | 7.4 | 0.51 | 87,297 | 1,890,520 | 32,543 | 26 | 0.059 | qwen3.8-flash-next-iq3_xxs | not-returned | 1632.8 | 86.8 | 196.7 | 73.3 |
| 25 claude-code strata-iq3_xxs low | strata-low-a4 |  | 是 | 4 | 是 | 0.539 | 0.539 | 0.539 | 0.000 | 0 | 11.4 | 0.79 | 98,844 | 4,585,989 | 51,421 | 40 | 0.112 | qwen3.8-flash-next-iq3_xxs | not-returned | 1475.0 | 87.2 | 144.6 | 75.2 |
| 25 claude-code strata-iq3_xxs low | strata-low-a6 |  | 是 | 5 | 是 | 0.304 | 0.304 | 0.314 | 0.034 | 1 | 6.8 | 0.47 | 92,646 | 2,118,722 | 30,430 | 25 | 0.062 | qwen3.8-flash-next-iq3_xxs | not-returned | 1779.7 | 87.7 | 228.6 | 75.1 |
| 25 claude-code strata-iq3_xxs low | strata-low-a7 |  | 是 | 6 | 是 | 0.413 | 0.413 | 0.413 | 0.000 | 0 | 6.0 | 0.41 | 85,665 | 1,754,443 | 24,779 | 26 | 0.053 | qwen3.8-flash-next-iq3_xxs | not-returned | 1794.1 | 82.7 | 239.9 | 69.4 |
| 25 claude-code strata-iq3_xxs low | strata-low-a8 |  | 是 | 7 | 是 | 0.456 | 0.456 | 0.474 | 0.038 | 1 | 8.0 | 0.55 | 82,407 | 1,937,606 | 31,426 | 28 | 0.058 | qwen3.8-flash-next-iq3_xxs | not-returned | 1515.6 | 77.3 | 172.7 | 65.9 |
| 25 claude-code strata-iq3_xxs low | strata-low-a9 |  | 是 | 8 | 是 | 0.499 | 0.499 | 0.514 | 0.030 | 0 | 6.5 | 0.45 | 63,557 | 1,463,131 | 26,385 | 25 | 0.045 | qwen3.8-flash-next-iq3_xxs | not-returned | 1413.3 | 78.4 | 162.3 | 67.4 |
| 25 claude-code strata-iq3_xxs low | strata-low-a10 |  | 是 | 9 | 是 | 0.484 | 0.484 | 0.491 | 0.014 | 0 | 6.9 | 0.48 | 87,261 | 1,773,945 | 29,527 | 27 | 0.055 | qwen3.8-flash-next-iq3_xxs | not-returned | 1566.6 | 84.9 | 210.7 | 71.3 |
| 25 claude-code strata-iq3_xxs low | strata-low-a11 |  | 是 | 10 | 是 | 0.412 | 0.412 | 0.422 | 0.022 | 0 | 6.4 | 0.44 | 76,281 | 1,506,759 | 27,613 | 23 | 0.049 | qwen3.8-flash-next-iq3_xxs | not-returned | 1578.5 | 85.7 | 199.0 | 72.0 |
| 25 claude-code strata-iq3_xxs low | strata-low-a5 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 1.6 | 0.11 | 21,817 | 219,333 | 6,761 | 12 | 0.010 | qwen3.8-flash-next-iq3_xxs | not-returned | 1589.1 | 86.0 | 227.0 | 70.3 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a1 |  | 是 | 1 | 是 | 0.479 | 0.479 | 0.479 | 0.000 | 0 | 9.0 | 0.61 | 76,727 | 1,421,529 | 42,104 | 20 | 0.054 | qwen3.8-flash-next-iq3_xxs | not-returned | 1855.1 | 85.8 | 141.8 | 77.8 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a2 |  | 是 | 2 | 是 | 0.510 | 0.510 | 0.510 | 0.000 | 0 | 9.5 | 0.64 | 80,961 | 1,916,942 | 43,513 | 102 | 0.063 | qwen3.8-flash-next-iq3_xxs | not-returned | 1552.0 | 85.7 | 142.3 | 76.5 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a3 |  | 是 | 3 | 是 | 0.462 | 0.462 | 0.462 | 0.000 | 0 | 8.8 | 0.59 | 86,694 | 1,818,019 | 38,425 | 24 | 0.060 | qwen3.8-flash-next-iq3_xxs | not-returned | 1646.6 | 83.3 | 164.2 | 72.8 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a4 |  | 是 | 4 | 是 | 0.563 | 0.563 | 0.563 | 0.000 | 0 | 9.5 | 0.64 | 93,908 | 1,850,619 | 43,253 | 108 | 0.064 | qwen3.8-flash-next-iq3_xxs | not-returned | 1660.3 | 85.4 | 164.8 | 75.9 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a5 |  | 是 | 5 | 是 | 0.388 | 0.388 | 0.431 | 0.100 | 24 | 7.2 | 0.49 | 103,278 | 2,124,474 | 31,459 | 26 | 0.064 | qwen3.8-flash-next-iq3_xxs | not-returned | 1755.0 | 86.5 | 238.8 | 72.7 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a6 |  | 是 | 6 | 是 | 0.597 | 0.597 | 0.597 | 0.000 | 0 | 9.5 | 0.64 | 94,313 | 1,823,963 | 43,597 | 21 | 0.064 | qwen3.8-flash-next-iq3_xxs | not-returned | 1896.1 | 85.7 | 166.1 | 76.8 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a7 |  | 是 | 7 | 是 | 0.436 | 0.436 | 0.436 | 0.000 | 0 | 8.8 | 0.59 | 83,066 | 1,554,482 | 40,510 | 23 | 0.056 | qwen3.8-flash-next-iq3_xxs | not-returned | 1671.8 | 86.6 | 157.2 | 76.6 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a8 |  | 是 | 8 | 是 | 0.440 | 0.440 | 0.440 | 0.000 | 0 | 8.5 | 0.57 | 83,283 | 1,782,666 | 38,440 | 39 | 0.059 | qwen3.8-flash-next-iq3_xxs | not-returned | 1616.0 | 86.5 | 163.4 | 75.4 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a9 |  | 是 | 9 | 是 | 0.472 | 0.472 | 0.472 | 0.000 | 0 | 8.3 | 0.56 | 74,829 | 1,454,686 | 37,527 | 97 | 0.052 | qwen3.8-flash-next-iq3_xxs | not-returned | 1526.6 | 84.7 | 149.9 | 75.2 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a10 |  | 是 | 10 | 是 | 0.405 | 0.405 | 0.405 | 0.000 | 0 | 6.8 | 0.46 | 87,272 | 1,740,850 | 29,745 | 32 | 0.055 | qwen3.8-flash-next-iq3_xxs | not-returned | 1775.6 | 84.6 | 213.6 | 72.8 |
| 27 claude-code strata-iq3_xxs high | strata-high-a1 |  | 是 | 1 | 是 | 0.493 | 0.493 | 0.509 | 0.031 | 0 | 10.5 | 0.69 | 74,158 | 1,992,930 | 49,343 | 34 | 0.066 | qwen3.8-flash-next-iq3_xxs | not-returned | 1477.7 | 87.2 | 117.7 | 78.3 |
| 27 claude-code strata-iq3_xxs high | strata-high-a2 |  | 是 | 2 | 是 | 0.437 | 0.437 | 0.437 | 0.000 | 0 | 10.2 | 0.67 | 75,942 | 1,410,744 | 45,934 | 27 | 0.056 | qwen3.8-flash-next-iq3_xxs | not-returned | 1732.7 | 83.4 | 124.6 | 75.4 |
| 27 claude-code strata-iq3_xxs high | strata-high-a3 |  | 是 | 3 | 是 | 0.463 | 0.463 | 0.463 | 0.000 | 0 | 9.0 | 0.59 | 82,036 | 877,366 | 42,170 | 16 | 0.046 | qwen3.8-flash-next-iq3_xxs | not-returned | 1983.9 | 86.2 | 152.3 | 78.3 |
| 27 claude-code strata-iq3_xxs high | strata-high-a4 |  | 是 | 4 | 是 | 0.515 | 0.515 | 0.515 | 0.000 | 0 | 11.8 | 0.78 | 82,794 | 1,791,385 | 52,806 | 27 | 0.066 | qwen3.8-flash-next-iq3_xxs | not-returned | 1791.8 | 81.5 | 116.6 | 74.4 |
| 27 claude-code strata-iq3_xxs high | strata-high-a5 |  | 是 | 5 | 是 | 0.392 | 0.392 | 0.392 | 0.000 | 0 | 9.2 | 0.60 | 74,304 | 1,189,234 | 40,907 | 24 | 0.049 | qwen3.8-flash-next-iq3_xxs | not-returned | 1815.0 | 82.3 | 134.8 | 74.2 |
| 27 claude-code strata-iq3_xxs high | strata-high-a6 |  | 是 | 6 | 是 | 0.471 | 0.471 | 0.471 | 0.000 | 0 | 9.9 | 0.65 | 71,468 | 1,509,916 | 44,447 | 98 | 0.056 | qwen3.8-flash-next-iq3_xxs | not-returned | 1495.3 | 81.7 | 119.8 | 74.5 |
| 27 claude-code strata-iq3_xxs high | strata-high-a7 |  | 是 | 7 | 是 | 0.475 | 0.475 | 0.475 | 0.000 | 0 | 8.7 | 0.57 | 62,910 | 976,913 | 40,775 | 17 | 0.044 | qwen3.8-flash-next-iq3_xxs | not-returned | 1856.6 | 84.7 | 120.6 | 78.2 |
| 27 claude-code strata-iq3_xxs high | strata-high-a8 |  | 是 | 8 | 是 | 0.447 | 0.447 | 0.447 | 0.000 | 0 | 7.6 | 0.50 | 92,346 | 1,170,498 | 33,512 | 29 | 0.048 | qwen3.8-flash-next-iq3_xxs | not-returned | 1827.5 | 85.0 | 202.9 | 73.6 |
| 27 claude-code strata-iq3_xxs high | strata-high-a9 |  | 是 | 9 | 是 | 0.479 | 0.479 | 0.479 | 0.000 | 0 | 10.4 | 0.69 | 88,368 | 2,263,666 | 48,091 | 34 | 0.072 | qwen3.8-flash-next-iq3_xxs | not-returned | 1737.4 | 85.4 | 141.4 | 77.0 |
| 27 claude-code strata-iq3_xxs high | strata-high-a10 |  | 是 | 10 | 是 | 0.469 | 0.469 | 0.469 | 0.000 | 0 | 11.2 | 0.74 | 85,295 | 1,042,401 | 53,049 | 19 | 0.054 | qwen3.8-flash-next-iq3_xxs | not-returned | 1978.3 | 85.1 | 127.0 | 79.0 |
| 28 codex gpt-6-luna xhigh | luna-xhigh-a1 |  | 是 | 1 | 是 | 0.691 | 0.691 | 0.691 | 0.000 | 0 | 4.3 | 0.40 | 231,236 | 1,709,440 | 27,806 | 21 | 只报 token | gpt-6-luna | default | 未知 | ≥108.3 | 892.8 | 107.4 |
| 28 codex gpt-6-luna xhigh | luna-xhigh-a2 |  | 是 | 2 | 是 | 0.707 | 0.707 | 0.707 | 0.000 | 0 | 2.4 | 0.22 | 117,190 | 1,003,008 | 14,103 | 13 | 只报 token | gpt-6-luna | default | 未知 | ≥95.5 | 812.5 | 97.8 |
| 28 codex gpt-6-luna xhigh | luna-xhigh-a3 |  | 是 | 3 | 是 | 0.580 | 0.580 | 0.596 | 0.026 | 0 | 6.2 | 0.58 | 137,826 | 2,605,824 | 32,895 | 29 | 只报 token | gpt-6-luna | default、not-returned | 未知 | ≥90.5 | 368.8 | 88.0 |
| 28 codex gpt-6-luna xhigh | luna-xhigh-a4 |  | 是 | 4 | 是 | 0.620 | 0.620 | 0.620 | 0.000 | 0 | 6.7 | 0.62 | 202,901 | 1,868,160 | 40,045 | 23 | 只报 token | gpt-6-luna | default、not-returned | 未知 | ≥105.7 | 506.5 | 100.0 |
| 28 codex gpt-6-luna xhigh | luna-xhigh-a5 |  | 是 | 5 | 是 | 0.652 | 0.652 | 0.652 | 0.000 | 0 | 3.8 | 0.35 | 136,417 | 1,200,512 | 25,034 | 15 | 只报 token | gpt-6-luna | default | 未知 | ≥109.6 | 594.9 | 109.2 |
| 28 codex gpt-6-luna xhigh | luna-xhigh-a6 |  | 是 | 6 | 是 | 0.737 | 0.737 | 0.737 | 0.000 | 0 | 6.2 | 0.57 | 160,443 | 2,208,384 | 35,427 | 22 | 只报 token | gpt-6-luna | default、not-returned | 未知 | ≥96.0 | 432.7 | 95.5 |
| 28 codex gpt-6-luna xhigh | luna-xhigh-a7 |  | 是 | 7 | 是 | 0.717 | 0.717 | 0.717 | 0.000 | 0 | 5.9 | 0.55 | 156,327 | 2,236,928 | 36,015 | 21 | 只报 token | gpt-6-luna | default、not-returned | 未知 | ≥104.9 | 441.3 | 101.7 |
| 28 codex gpt-6-luna xhigh | luna-xhigh-a8 |  | 是 | 8 | 是 | 0.625 | 0.625 | 0.625 | 0.000 | 0 | 4.9 | 0.45 | 155,171 | 1,892,608 | 31,738 | 21 | 只报 token | gpt-6-luna | default | 未知 | ≥108.8 | 530.2 | 108.4 |
| 29 codex gpt-6-luna max | luna-max-a1 |  | 是 | 1 | 是 | 0.700 | 0.700 | 0.700 | 0.000 | 0 | 5.0 | 0.41 | 120,440 | 1,229,312 | 34,252 | 15 | 只报 token | gpt-6-luna | default | 未知 | ≥115.1 | 404.4 | 115.0 |
| 29 codex gpt-6-luna max | luna-max-a2 |  | 是 | 2 | 是 | 0.758 | 0.758 | 0.758 | 0.000 | 0 | 7.2 | 0.60 | 162,596 | 3,279,232 | 35,474 | 36 | 只报 token | gpt-6-luna | default、not-returned | 未知 | ≥85.7 | 374.6 | 81.7 |
| 29 codex gpt-6-luna max | luna-max-a3 |  | 是 | 3 | 是 | 0.628 | 0.628 | 0.628 | 0.000 | 0 | 6.8 | 0.57 | 155,819 | 3,999,616 | 38,955 | 43 | 只报 token | gpt-6-luna | default | 未知 | ≥94.8 | 379.9 | 95.0 |
| 29 codex gpt-6-luna max | luna-max-a4 |  | 是 | 4 | 是 | 0.734 | 0.734 | 0.734 | 0.000 | 0 | 6.4 | 0.53 | 154,329 | 2,189,184 | 37,325 | 24 | 只报 token | gpt-6-luna | default | 未知 | ≥96.9 | 400.8 | 96.9 |
| 29 codex gpt-6-luna max | luna-max-a5 |  | 是 | 5 | 是 | 0.600 | 0.600 | 0.600 | 0.000 | 0 | 6.5 | 0.54 | 141,886 | 2,974,464 | 41,168 | 31 | 只报 token | gpt-6-luna | default | 未知 | ≥105.9 | 365.0 | 105.9 |
| 29 codex gpt-6-luna max | luna-max-a6 |  | 是 | 6 | 是 | 0.692 | 0.692 | 0.692 | 0.000 | 0 | 6.5 | 0.54 | 175,834 | 2,393,728 | 45,181 | 22 | 只报 token | gpt-6-luna | default | 未知 | ≥116.7 | 452.7 | 116.3 |

## code-standards-v5.1

### 配置

| 配置 | 行 | 有效 | 选入 n | 已计分 | 无效 | 均值 ± SD | SE | 95% 区间 | 负分数 | 最小 | 中位数 | r8.3 均值 | rawScore | f | 修复 | 耗时（分钟） | 占时限 | 未缓存 | 缓存 | 输出 | token 来源 | 工具调用 | 费用（美元；DeepSeek 括号内为人民币 ¥） | 周额度 | 模型 ID | service tier |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 codex gpt-6.1-sol low | 主统计 | 5 | 5 | 5 | 0 | 0.845 ± 0.070 | 0.032 | 0.758–0.933 | 0 | 0.759 | 0.871 | 0.845 | 0.845 | 0.000 | 0 | 2.3 | 0.10 | 85,859 | 576,128 | 6,162 | API usage (relay) | 10.6 | 只报 token |  | gpt-6.1-sol | default |
| 2 codex gpt-6.1-sol medium | 主统计 | 5 | 5 | 5 | 0 | 0.892 ± 0.033 | 0.015 | 0.851–0.933 | 0 | 0.841 | 0.893 | 0.892 | 0.892 | 0.000 | 0 | 2.9 | 0.13 | 78,453 | 671,770 | 7,632 | API usage (relay) | 11.4 | 只报 token |  | gpt-6.1-sol | default |
| 3 codex gpt-6.1-sol high | 主统计 | 5 | 5 | 5 | 0 | 0.885 ± 0.043 | 0.019 | 0.831–0.939 | 0 | 0.815 | 0.906 | 0.885 | 0.885 | 0.000 | 0 | 4.7 | 0.22 | 100,401 | 862,285 | 12,640 | API usage (relay) | 13.4 | 只报 token |  | gpt-6.1-sol | default |
| 4 codex gpt-6-luna low | 主统计 | 5 | 5 | 5 | 1 | 0.163 ± 0.085 | 0.038 | 0.057–0.269 | 0 | 0.026 | 0.176 | 0.163 | 0.163 | 0.000 | 0 | 0.6 | 0.07 | 53,602 | 385,459 | 2,523 | API usage (relay) | 9.0 | 只报 token |  | gpt-6-luna | default |
| 5 codex gpt-6-luna medium | 主统计 | 5 | 5 | 5 | 0 | 0.343 ± 0.168 | 0.075 | 0.135–0.552 | 0 | 0.157 | 0.363 | 0.343 | 0.346 | 0.015 | 1 | 0.9 | 0.09 | 54,954 | 417,690 | 4,016 | API usage (relay) | 9.4 | 只报 token |  | gpt-6-luna | default |
| 6 codex gpt-6-luna high | 主统计 | 5 | 5 | 5 | 0 | 0.472 ± 0.077 | 0.034 | 0.377–0.568 | 0 | 0.346 | 0.499 | 0.472 | 0.472 | 0.000 | 0 | 1.3 | 0.13 | 56,941 | 378,317 | 7,391 | API usage (relay) | 8.8 | 只报 token |  | gpt-6-luna | default |
| 7 codex deepseek-flash low | 主统计 | 5 | 5 | 5 | 0 | 0.634 ± 0.059 | 0.026 | 0.561–0.707 | 0 | 0.570 | 0.648 | 0.634 | 0.634 | 0.000 | 0 | 2.0 | 0.32 | 48,966 | 727,014 | 22,591 | API usage (relay) | 34.8 | 0.115（¥0.769） |  | deepseek-flash | default |
| 8 codex deepseek-flash high | 主统计 | 5 | 5 | 5 | 0 | 0.655 ± 0.088 | 0.040 | 0.545–0.764 | 0 | 0.532 | 0.659 | 0.655 | 0.657 | 0.005 | 1 | 2.5 | 0.45 | 47,878 | 858,010 | 23,831 | API usage (relay) | 33.8 | ≥0.120（¥0.802） |  | deepseek-flash | default、not-returned |
| 9 codex deepseek-flash max | 主统计 | 5 | 5 | 5 | 0 | 0.737 ± 0.077 | 0.034 | 0.642–0.833 | 0 | 0.624 | 0.727 | 0.737 | 0.743 | 0.008 | 2 | 2.7 | 0.45 | 55,262 | 1,174,528 | 31,206 | API usage (relay) | 43.4 | ≥0.153（¥1.018） |  | deepseek-flash | default、not-returned |
| 10 codex strata-iq3_xxs low | 主统计 | 10 | 10 | 10 | 0 | 0.694 ± 0.245 | 0.077 | 0.519–0.869 | 0 | 0.000 | 0.767 | 0.694 | 0.733 | 0.047 | 98 | 8.7 | 0.56 | 62,407 | 1,736,130 | 36,059 | engine log | 33.0 | 0.541 |  | 未知 | 未知 |
| 10 codex strata-iq3_xxs low | 一致性行（前 5） | 10 | 5 | 5 |  | 0.766 ± 0.024 | 0.011 | 0.736–0.796 | 0 | 0.734 | 0.765 | 0.766 | 0.804 | 0.046 | 56 | 9.5 | 0.61 | 64,949 | 2,192,653 | 39,834 | engine log | 39.0 | 0.318 |  | 未知 | 未知 |
| 11 codex strata-iq3_xxs medium | 主统计 | 10 | 10 | 10 | 0 | 0.750 ± 0.072 | 0.023 | 0.699–0.802 | 0 | 0.619 | 0.765 | 0.750 | 0.776 | 0.035 | 104 | 8.9 | 0.56 | 60,850 | 1,588,286 | 38,101 | engine log | 32.7 | 0.524 |  | 未知 | 未知 |
| 11 codex strata-iq3_xxs medium | 一致性行（前 5） | 10 | 5 | 5 |  | 0.716 ± 0.090 | 0.040 | 0.605–0.827 | 0 | 0.619 | 0.727 | 0.716 | 0.760 | 0.060 | 94 | 9.6 | 0.60 | 60,977 | 1,726,964 | 40,991 | engine log | 35.6 | 0.280 |  | 未知 | 未知 |
| 12 codex strata-iq3_xxs high | 主统计 | 10 | 10 | 10 | 0 | 0.767 ± 0.050 | 0.016 | 0.731–0.803 | 0 | 0.690 | 0.779 | 0.767 | 0.811 | 0.054 | 111 | 10.2 | 0.59 | 62,238 | 1,567,764 | 44,455 | engine log | 35.6 | 0.553 |  | 未知 | 未知 |
| 12 codex strata-iq3_xxs high | 一致性行（前 5） | 10 | 5 | 5 |  | 0.767 ± 0.039 | 0.017 | 0.719–0.816 | 0 | 0.705 | 0.782 | 0.767 | 0.818 | 0.061 | 67 | 10.4 | 0.60 | 64,589 | 1,526,163 | 45,054 | engine log | 32.8 | 0.276 |  | 未知 | 未知 |
| 13 claude-code opus low | 主统计 | 5 | 5 | 5 | 0 | 0.658 ± 0.045 | 0.020 | 0.601–0.714 | 0 | 0.607 | 0.650 | 0.658 | 0.697 | 0.056 | 75 | 1.6 | 0.09 | 47,540 | 258,803 | 4,928 | Claude Code stream result usage | 6.8 | 2.653 | 0.23% | claude-opus-5-5 | standard |
| 14 claude-code opus medium | 主统计 | 5 | 5 | 5 | 0 | 0.774 ± 0.037 | 0.016 | 0.728–0.819 | 0 | 0.738 | 0.770 | 0.774 | 0.812 | 0.047 | 93 | 2.0 | 0.11 | 59,533 | 456,039 | 9,656 | Claude Code stream result usage | 10.4 | 3.803 | 0.33% | claude-opus-5-5 | standard |
| 15 claude-code opus high | 主统计 | 5 | 5 | 5 | 0 | 0.847 ± 0.035 | 0.016 | 0.803–0.891 | 0 | 0.805 | 0.835 | 0.847 | 0.858 | 0.013 | 6 | 2.5 | 0.15 | 63,400 | 568,341 | 12,174 | Claude Code stream result usage | 11.8 | 4.321 | 0.37% | claude-opus-5-5 | standard |
| 16 claude-code sonnet low | 主统计 | 5 | 5 | 5 | 0 | 0.486 ± 0.088 | 0.039 | 0.377–0.595 | 0 | 0.412 | 0.440 | 0.486 | 0.498 | 0.021 | 3 | 1.5 | 0.11 | 44,761 | 268,998 | 4,059 | Claude Code stream result usage | 8.4 | 1.233 | 0.11% | claude-sonnet-5-5 | standard |
| 17 claude-code sonnet medium | 主统计 | 5 | 5 | 5 | 0 | 0.529 ± 0.091 | 0.041 | 0.415–0.643 | 0 | 0.421 | 0.532 | 0.529 | 0.534 | 0.010 | 2 | 1.4 | 0.10 | 46,320 | 225,781 | 5,027 | Claude Code stream result usage | 7.2 | 1.290 | 0.11% | claude-sonnet-5-5 | standard |
| 18 claude-code sonnet high | 主统计 | 5 | 5 | 5 | 0 | 0.651 ± 0.059 | 0.026 | 0.577–0.724 | 0 | 0.580 | 0.656 | 0.651 | 0.674 | 0.035 | 12 | 2.0 | 0.14 | 55,293 | 348,729 | 8,420 | Claude Code stream result usage | 9.6 | 1.701 | 0.15% | claude-sonnet-5-5 | standard |
| 19 claude-code haiku low | 主统计 | 5 | 5 | 5 | 0 | 0.415 ± 0.065 | 0.029 | 0.334–0.496 | 0 | 0.331 | 0.392 | 0.415 | 0.418 | 0.007 | 1 | 1.3 | 0.15 | 50,052 | 218,546 | 11,498 | Claude Code stream result usage | 7.6 | 0.090 | 0.01% | claude-haiku-5-5 | standard |
| 20 claude-code haiku medium | 主统计 | 5 | 5 | 5 | 0 | 0.501 ± 0.055 | 0.025 | 0.432–0.570 | 0 | 0.429 | 0.502 | 0.501 | 0.514 | 0.025 | 5 | 1.6 | 0.20 | 55,875 | 298,643 | 15,486 | Claude Code stream result usage | 9.0 | 0.110 | 0.01% | claude-haiku-5-5 | standard |
| 21 claude-code haiku high | 主统计 | 5 | 5 | 5 | 0 | 0.530 ± 0.047 | 0.021 | 0.472–0.588 | 0 | 0.480 | 0.510 | 0.530 | 0.546 | 0.030 | 10 | 2.2 | 0.27 | 64,293 | 336,609 | 21,151 | Claude Code stream result usage | 10.8 | 0.134 | 0.01% | claude-haiku-5-5 | standard |
| 22 claude-code deepseek-flash low | 主统计 | 5 | 5 | 5 | 0 | 0.532 ± 0.099 | 0.044 | 0.409–0.655 | 0 | 0.420 | 0.521 | 0.532 | 0.563 | 0.056 | 18 | 2.8 | 0.49 | 38,620 | 280,192 | 10,241 | Claude Code stream result usage | 15.0 | 0.064（¥0.426） |  | deepseek-flash | standard |
| 23 claude-code deepseek-flash high | 主统计 | 5 | 5 | 5 | 0 | 0.594 ± 0.105 | 0.047 | 0.465–0.724 | 0 | 0.423 | 0.606 | 0.594 | 0.640 | 0.073 | 22 | 3.2 | 0.56 | 43,170 | 493,005 | 14,499 | Claude Code stream result usage | 18.4 | 0.083（¥0.555） |  | deepseek-flash | standard |
| 23 claude-code deepseek-flash high | 补充行（high requested as medium, T=362） | 1 | 1 | 1 | 0 | 0.563 ± 未知 | 未知 | 未知 | 0 | 0.563 | 0.563 | 0.563 | 0.626 | 0.100 | 6 | 3.8 | 0.63 | 41,861 | 324,864 | 10,223 | Claude Code stream result usage | 13.0 | 0.013（¥0.089） |  | deepseek-flash | standard |
| 23 claude-code deepseek-flash high | 敏感性行：high+medium 合并（描述性，high requested as medium, T=362） | 6 | 6 | 6 |  | 0.589 ± 0.094 | 0.039 | 0.490–0.688 | 0 | 0.423 | 0.599 | 0.589 | 0.638 | 0.078 | 28 | 3.3 | 0.57 | 42,952 | 464,981 | 13,787 | Claude Code stream result usage | 17.5 | 0.097（¥0.644） |  | deepseek-flash | standard |
| 24 claude-code deepseek-flash max | 主统计 | 5 | 5 | 5 | 0 | 0.610 ± 0.071 | 0.032 | 0.522–0.698 | 0 | 0.511 | 0.633 | 0.610 | 0.643 | 0.050 | 14 | 3.7 | 0.62 | 47,831 | 531,277 | 22,256 | Claude Code stream result usage | 23.8 | 0.111（¥0.737） |  | deepseek-flash | standard |
| 25 claude-code strata-iq3_xxs low | 主统计 | 10 | 10 | 10 | 4 | 0.708 ± 0.065 | 0.020 | 0.662–0.754 | 0 | 0.591 | 0.711 | 0.708 | 0.756 | 0.063 | 334 | 9.3 | 0.64 | 59,378 | 2,076,397 | 41,826 | engine log | 40.3 | 0.618 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 25 claude-code strata-iq3_xxs low | 一致性行（前 5） | 10 | 5 | 5 |  | 0.703 ± 0.083 | 0.037 | 0.599–0.806 | 0 | 0.591 | 0.719 | 0.703 | 0.738 | 0.047 | 115 | 10.0 | 0.69 | 59,875 | 2,174,520 | 45,394 | engine log | 43.4 | 0.326 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 26 claude-code strata-iq3_xxs medium | 主统计 | 10 | 10 | 10 | 5 | 0.700 ± 0.063 | 0.020 | 0.656–0.745 | 0 | 0.615 | 0.695 | 0.700 | 0.754 | 0.070 | 175 | 7.0 | 0.48 | 53,261 | 1,123,740 | 32,516 | engine log | 30.2 | 0.413 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 26 claude-code strata-iq3_xxs medium | 一致性行（前 5） | 10 | 5 | 5 |  | 0.706 ± 0.052 | 0.023 | 0.642–0.770 | 0 | 0.661 | 0.690 | 0.706 | 0.770 | 0.081 | 84 | 6.9 | 0.47 | 49,224 | 1,043,134 | 32,368 | engine log | 29.6 | 0.196 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 27 claude-code strata-iq3_xxs high | 主统计 | 10 | 10 | 10 | 5 | 0.704 ± 0.081 | 0.025 | 0.646–0.761 | 0 | 0.566 | 0.693 | 0.704 | 0.740 | 0.050 | 66 | 8.6 | 0.57 | 58,123 | 1,124,519 | 41,190 | engine log | 29.0 | 0.461 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 27 claude-code strata-iq3_xxs high | 一致性行（前 5） | 10 | 5 | 5 |  | 0.718 ± 0.067 | 0.030 | 0.635–0.801 | 0 | 0.682 | 0.690 | 0.718 | 0.757 | 0.051 | 31 | 9.2 | 0.62 | 57,419 | 1,161,646 | 43,895 | engine log | 30.6 | 0.239 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 28 codex gpt-6-luna xhigh | 第三阶段补充（不比较） | 8 | 8 | 8 |  | 0.637 ± 0.055 | 0.019 | 0.591–0.683 | 0 | 0.587 | 0.617 | 0.637 | 0.640 | 0.004 | 2 | 4.8 | 0.51 | 95,555 | 832,688 | 31,690 | API usage (relay) | 13.6 | 只报 token |  | gpt-6-luna | default、not-returned |
| 29 codex gpt-6-luna max | 第三阶段补充（不比较） | 8 | 8 | 8 |  | 0.586 ± 0.146 | 0.052 | 0.463–0.708 | 0 | 0.253 | 0.613 | 0.586 | 0.597 | 0.017 | 10 | 5.3 | 0.49 | 100,301 | 1,004,384 | 35,264 | API usage (relay) | 15.5 | 只报 token |  | gpt-6-luna | default、not-returned |

### 预登记比较

r8.3 列：同一批实例按 r8.3（截到 0、整体扣减相乘）计分的对照（plan §14.1）。

| 组 | 前者 | 后者 | n | 差值 | SE | t | 自由度 | p | Holm p | 结论 | r8.3 差值 | r8.3 Holm p | r8.3 结论 | 结论改变 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| codex | 10 codex strata-iq3_xxs low | 1 codex gpt-6.1-sol low | 10 / 5 | -0.151 | 0.084 | -1.81 | 11.5 | 0.0964 | 0.7488 | 未分出 | -0.151 | 0.7488 | 未分出 | 否 |
| codex | 10 codex strata-iq3_xxs low | 4 codex gpt-6-luna low | 10 / 5 | 0.531 | 0.086 | 6.15 | 12.3 | 0.0000 | 0.0011 | 高于 | 0.531 | 0.0011 | 高于 | 否 |
| codex | 10 codex strata-iq3_xxs low | 7 codex deepseek-flash low | 10 / 5 | 0.060 | 0.082 | 0.73 | 10.9 | 0.4810 | 1.0000 | 未分出 | 0.060 | 1.0000 | 未分出 | 否 |
| codex | 11 codex strata-iq3_xxs medium | 2 codex gpt-6.1-sol medium | 10 / 5 | -0.142 | 0.027 | -5.25 | 13.0 | 0.0002 | 0.0035 | 低于 | -0.142 | 0.0035 | 低于 | 否 |
| codex | 11 codex strata-iq3_xxs medium | 5 codex gpt-6-luna medium | 10 / 5 | 0.407 | 0.078 | 5.18 | 4.7 | 0.0041 | 0.0652 | 未分出 | 0.407 | 0.0652 | 未分出 | 否 |
| codex | 12 codex strata-iq3_xxs high | 3 codex gpt-6.1-sol high | 10 / 5 | -0.118 | 0.025 | -4.73 | 9.3 | 0.0010 | 0.0179 | 低于 | -0.118 | 0.0179 | 低于 | 否 |
| codex | 12 codex strata-iq3_xxs high | 6 codex gpt-6-luna high | 10 / 5 | 0.294 | 0.038 | 7.78 | 5.8 | 0.0003 | 0.0058 | 高于 | 0.294 | 0.0058 | 高于 | 否 |
| codex | 12 codex strata-iq3_xxs high | 8 codex deepseek-flash high | 10 / 5 | 0.112 | 0.043 | 2.64 | 5.3 | 0.0434 | 0.4776 | 未分出 | 0.112 | 0.4776 | 未分出 | 否 |
| claude-code | 25 claude-code strata-iq3_xxs low | 13 claude-code opus low | 10 / 5 | 0.051 | 0.029 | 1.75 | 11.2 | 0.1068 | 0.7488 | 未分出 | 0.051 | 0.7488 | 未分出 | 否 |
| claude-code | 25 claude-code strata-iq3_xxs low | 16 claude-code sonnet low | 10 / 5 | 0.222 | 0.044 | 5.01 | 6.3 | 0.0021 | 0.0364 | 高于 | 0.222 | 0.0364 | 高于 | 否 |
| claude-code | 25 claude-code strata-iq3_xxs low | 19 claude-code haiku low | 10 / 5 | 0.293 | 0.036 | 8.23 | 8.1 | 0.0000 | 0.0009 | 高于 | 0.293 | 0.0009 | 高于 | 否 |
| claude-code | 25 claude-code strata-iq3_xxs low | 22 claude-code deepseek-flash low | 10 / 5 | 0.176 | 0.049 | 3.62 | 5.8 | 0.0119 | 0.1662 | 未分出 | 0.176 | 0.1662 | 未分出 | 否 |
| claude-code | 26 claude-code strata-iq3_xxs medium | 14 claude-code opus medium | 10 / 5 | -0.073 | 0.026 | -2.86 | 12.4 | 0.0140 | 0.1820 | 未分出 | -0.073 | 0.1820 | 未分出 | 否 |
| claude-code | 26 claude-code strata-iq3_xxs medium | 17 claude-code sonnet medium | 10 / 5 | 0.171 | 0.045 | 3.77 | 5.9 | 0.0095 | 0.1418 | 未分出 | 0.171 | 0.1418 | 未分出 | 否 |
| claude-code | 26 claude-code strata-iq3_xxs medium | 20 claude-code haiku medium | 10 / 5 | 0.199 | 0.032 | 6.29 | 9.1 | 0.0001 | 0.0032 | 高于 | 0.199 | 0.0032 | 高于 | 否 |
| claude-code | 27 claude-code strata-iq3_xxs high | 15 claude-code opus high | 10 / 5 | -0.144 | 0.030 | -4.79 | 12.9 | 0.0004 | 0.0067 | 低于 | -0.144 | 0.0067 | 低于 | 否 |
| claude-code | 27 claude-code strata-iq3_xxs high | 18 claude-code sonnet high | 10 / 5 | 0.053 | 0.037 | 1.43 | 10.7 | 0.1805 | 0.7488 | 未分出 | 0.053 | 0.7488 | 未分出 | 否 |
| claude-code | 27 claude-code strata-iq3_xxs high | 21 claude-code haiku high | 10 / 5 | 0.174 | 0.033 | 5.26 | 12.5 | 0.0002 | 0.0037 | 高于 | 0.174 | 0.0037 | 高于 | 否 |
| claude-code | 27 claude-code strata-iq3_xxs high | 23 claude-code deepseek-flash high | 10 / 5 | 0.109 | 0.053 | 2.05 | 6.5 | 0.0832 | 0.7488 | 未分出 | 0.109 | 0.7488 | 未分出 | 否 |
| harness | 10 codex strata-iq3_xxs low | 25 claude-code strata-iq3_xxs low | 10 / 10 | -0.014 | 0.080 | -0.18 | 10.3 | 0.8633 | 1.0000 | 未分出 | -0.014 | 1.0000 | 未分出 | 否 |
| harness | 11 codex strata-iq3_xxs medium | 26 claude-code strata-iq3_xxs medium | 10 / 10 | 0.050 | 0.030 | 1.65 | 17.7 | 0.1160 | 0.7488 | 未分出 | 0.050 | 0.7488 | 未分出 | 否 |
| harness | 12 codex strata-iq3_xxs high | 27 claude-code strata-iq3_xxs high | 10 / 10 | 0.063 | 0.030 | 2.11 | 15.0 | 0.0522 | 0.5219 | 未分出 | 0.063 | 0.5219 | 未分出 | 否 |
| harness | 7 codex deepseek-flash low | 22 claude-code deepseek-flash low | 5 / 5 | 0.103 | 0.052 | 1.99 | 6.5 | 0.0898 | 0.7488 | 未分出 | 0.103 | 0.7488 | 未分出 | 否 |
| harness | 8 codex deepseek-flash high | 23 claude-code deepseek-flash high | 5 / 5 | 0.060 | 0.061 | 0.98 | 7.8 | 0.3564 | 1.0000 | 未分出 | 0.060 | 1.0000 | 未分出 | 否 |
| harness | 9 codex deepseek-flash max | 24 claude-code deepseek-flash max | 5 / 5 | 0.128 | 0.047 | 2.73 | 8.0 | 0.0262 | 0.3141 | 未分出 | 0.128 | 0.3141 | 未分出 | 否 |

### 逐实例

速度：引擎输入、引擎输出是模型直接速度，任务平均输入、输出是用户感知速度（未缓存输入、输出 ÷ 工作秒数）。API 模型分不出输入处理时间，引擎输入记未知；引擎输出按 API 请求时间算，含首 token 延迟和输入处理，是下限（≥）。

速度汇总口径（用户 2026-10-22）：多个实例的速度（summary.json 各行的 speeds_mean）是总 token ÷ 总耗时（各实例 speed_parts 的分子之和 ÷ 分母之和，speed_totals 给出两者），不是各实例速度的算术平均；任一实例该项未知，汇总即未知；任一实例该项是下限，汇总也是下限。Codex 上的 API 模型（gpt-6.1-sol、gpt-6-luna、DeepSeek）的引擎输出按 relay 日志的 output token ÷ 请求秒数计算，v1 的记录没有保存请求秒数，原始 relay 日志已删除，所以这一项按用户 10-22 的选择近似汇总：分子取实例的输出 token（同样来自 relay usage），分母取 输出 token ÷ 逐实例引擎输出速度 反推的请求秒数；汇总标为近似（speeds_approximate，表中写"≥≈"），仍是下限。

| 配置 | 实例 | 补充 | 有效 | 序 | 主统计 | 分数 | r8.3 分数 | rawScore | f | 修复 | 耗时（分钟） | 占时限 | 未缓存 | 缓存 | 输出 | 工具调用 | 费用（美元；DeepSeek 括号内为人民币 ¥） | 模型 ID | service tier | 引擎输入 tok/s | 引擎输出 tok/s | 任务平均输入 tok/s | 任务平均输出 tok/s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 codex gpt-6.1-sol low | sol-low-a1 |  | 是 | 1 | 是 | 0.783 | 0.783 | 0.783 | 0.000 | 0 | 2.0 | 0.08 | 136,805 | 394,368 | 5,725 | 9 | 只报 token | gpt-6.1-sol | default | 未知 | ≥48.6 | 1160.8 | 48.6 |
| 1 codex gpt-6.1-sol low | sol-low-a2 |  | 是 | 2 | 是 | 0.759 | 0.759 | 0.759 | 0.000 | 0 | 1.8 | 0.08 | 63,846 | 461,824 | 4,860 | 9 | 只报 token | gpt-6.1-sol | default | 未知 | ≥44.9 | 585.8 | 44.6 |
| 1 codex gpt-6.1-sol low | sol-low-a3 |  | 是 | 3 | 是 | 0.897 | 0.897 | 0.897 | 0.000 | 0 | 2.5 | 0.11 | 80,142 | 643,584 | 6,410 | 11 | 只报 token | gpt-6.1-sol | default | 未知 | ≥42.2 | 524.2 | 41.9 |
| 1 codex gpt-6.1-sol low | sol-low-a4 |  | 是 | 4 | 是 | 0.871 | 0.871 | 0.871 | 0.000 | 0 | 3.0 | 0.13 | 78,093 | 756,992 | 8,108 | 13 | 只报 token | gpt-6.1-sol | default | 未知 | ≥44.8 | 429.3 | 44.6 |
| 1 codex gpt-6.1-sol low | sol-low-a5 |  | 是 | 5 | 是 | 0.917 | 0.917 | 0.917 | 0.000 | 0 | 2.2 | 0.09 | 70,407 | 623,872 | 5,706 | 11 | 只报 token | gpt-6.1-sol | default | 未知 | ≥44.3 | 530.3 | 43.0 |
| 2 codex gpt-6.1-sol medium | sol-medium-a1 |  | 是 | 1 | 是 | 0.893 | 0.893 | 0.893 | 0.000 | 0 | 2.8 | 0.13 | 80,504 | 627,328 | 8,008 | 11 | 只报 token | gpt-6.1-sol | default | 未知 | ≥48.0 | 480.5 | 47.8 |
| 2 codex gpt-6.1-sol medium | sol-medium-a2 |  | 是 | 2 | 是 | 0.919 | 0.919 | 0.919 | 0.000 | 0 | 2.8 | 0.13 | 72,994 | 761,984 | 7,041 | 13 | 只报 token | gpt-6.1-sol | default | 未知 | ≥42.7 | 437.1 | 42.2 |
| 2 codex gpt-6.1-sol medium | sol-medium-a3 |  | 是 | 3 | 是 | 0.841 | 0.841 | 0.841 | 0.000 | 0 | 2.6 | 0.12 | 71,835 | 510,976 | 6,825 | 9 | 只报 token | gpt-6.1-sol | default | 未知 | ≥44.5 | 465.3 | 44.2 |
| 2 codex gpt-6.1-sol medium | sol-medium-a4 |  | 是 | 4 | 是 | 0.886 | 0.886 | 0.886 | 0.000 | 0 | 2.9 | 0.13 | 87,253 | 667,648 | 7,946 | 11 | 只报 token | gpt-6.1-sol | default | 未知 | ≥45.8 | 499.2 | 45.5 |
| 2 codex gpt-6.1-sol medium | sol-medium-a5 |  | 是 | 5 | 是 | 0.923 | 0.923 | 0.923 | 0.000 | 0 | 3.4 | 0.15 | 79,677 | 790,912 | 8,339 | 13 | 只报 token | gpt-6.1-sol | default | 未知 | ≥41.9 | 396.1 | 41.5 |
| 3 codex gpt-6.1-sol high | sol-high-a1 |  | 是 | 1 | 是 | 0.924 | 0.924 | 0.924 | 0.000 | 0 | 5.4 | 0.25 | 101,215 | 1,056,512 | 14,484 | 16 | 只报 token | gpt-6.1-sol | default | 未知 | ≥44.6 | 309.6 | 44.3 |
| 3 codex gpt-6.1-sol high | sol-high-a2 |  | 是 | 2 | 是 | 0.906 | 0.906 | 0.906 | 0.000 | 0 | 4.8 | 0.22 | 96,787 | 1,027,584 | 13,353 | 15 | 只报 token | gpt-6.1-sol | default | 未知 | ≥47.1 | 339.0 | 46.8 |
| 3 codex gpt-6.1-sol high | sol-high-a3 |  | 是 | 3 | 是 | 0.909 | 0.909 | 0.909 | 0.000 | 0 | 3.8 | 0.18 | 84,789 | 675,456 | 9,911 | 11 | 只报 token | gpt-6.1-sol | default | 未知 | ≥43.7 | 370.2 | 43.3 |
| 3 codex gpt-6.1-sol high | sol-high-a4 |  | 是 | 4 | 是 | 0.872 | 0.872 | 0.872 | 0.000 | 0 | 5.0 | 0.23 | 133,164 | 701,184 | 13,509 | 12 | 只报 token | gpt-6.1-sol | default | 未知 | ≥45.5 | 446.9 | 45.3 |
| 3 codex gpt-6.1-sol high | sol-high-a5 |  | 是 | 5 | 是 | 0.815 | 0.815 | 0.815 | 0.000 | 0 | 4.6 | 0.21 | 86,052 | 850,688 | 11,945 | 13 | 只报 token | gpt-6.1-sol | default | 未知 | ≥43.7 | 310.1 | 43.0 |
| 4 codex gpt-6-luna low | luna-low-a1 |  | 是 | 1 | 是 | 0.176 | 0.176 | 0.176 | 0.000 | 0 | 0.7 | 0.08 | 57,222 | 438,272 | 2,667 | 10 | 只报 token | gpt-6-luna | default | 未知 | ≥59.6 | 1272.1 | 59.3 |
| 4 codex gpt-6-luna low | luna-low-a3 |  | 是 | 2 | 是 | 0.026 | 0.026 | 0.026 | 0.000 | 0 | 0.6 | 0.06 | 44,905 | 348,672 | 1,995 | 9 | 只报 token | gpt-6-luna | default | 未知 | ≥60.2 | 1312.3 | 58.3 |
| 4 codex gpt-6-luna low | luna-low-a4 |  | 是 | 3 | 是 | 0.156 | 0.156 | 0.156 | 0.000 | 0 | 0.6 | 0.06 | 54,271 | 391,040 | 2,238 | 9 | 只报 token | gpt-6-luna | default | 未知 | ≥68.5 | 1642.5 | 67.7 |
| 4 codex gpt-6-luna low | luna-low-a5 |  | 是 | 4 | 是 | 0.257 | 0.257 | 0.257 | 0.000 | 0 | 1.0 | 0.10 | 59,704 | 523,776 | 3,986 | 11 | 只报 token | gpt-6-luna | default | 未知 | ≥70.9 | 1028.8 | 68.7 |
| 4 codex gpt-6-luna low | luna-low-a6 |  | 是 | 5 | 是 | 0.199 | 0.199 | 0.199 | 0.000 | 0 | 0.4 | 0.04 | 51,907 | 225,536 | 1,728 | 6 | 只报 token | gpt-6-luna | default | 未知 | ≥75.0 | 2184.4 | 72.7 |
| 4 codex gpt-6-luna low | luna-low-a2 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 0.0 | 0.00 | 未知 | 未知 | 未知 | 0 | 只报 token | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 |
| 5 codex gpt-6-luna medium | luna-medium-a1 |  | 是 | 1 | 是 | 0.363 | 0.363 | 0.363 | 0.000 | 0 | 0.8 | 0.08 | 55,161 | 410,752 | 4,116 | 10 | 只报 token | gpt-6-luna | default | 未知 | ≥90.7 | 1189.8 | 88.8 |
| 5 codex gpt-6-luna medium | luna-medium-a2 |  | 是 | 2 | 是 | 0.157 | 0.157 | 0.169 | 0.073 | 1 | 0.5 | 0.05 | 48,794 | 260,352 | 2,248 | 7 | 只报 token | gpt-6-luna | default | 未知 | ≥77.2 | 1642.1 | 75.7 |
| 5 codex gpt-6-luna medium | luna-medium-a3 |  | 是 | 3 | 是 | 0.564 | 0.564 | 0.564 | 0.000 | 0 | 1.6 | 0.17 | 61,086 | 674,176 | 7,302 | 13 | 只报 token | gpt-6-luna | default | 未知 | ≥75.3 | 622.7 | 74.4 |
| 5 codex gpt-6-luna medium | luna-medium-a4 |  | 是 | 4 | 是 | 0.434 | 0.434 | 0.434 | 0.000 | 0 | 0.9 | 0.09 | 47,847 | 385,664 | 4,242 | 9 | 只报 token | gpt-6-luna | default | 未知 | ≥83.8 | 929.2 | 82.4 |
| 5 codex gpt-6-luna medium | luna-medium-a5 |  | 是 | 5 | 是 | 0.199 | 0.199 | 0.199 | 0.000 | 0 | 0.5 | 0.06 | 61,883 | 357,504 | 2,172 | 8 | 只报 token | gpt-6-luna | default | 未知 | ≥68.5 | 1911.0 | 67.1 |
| 6 codex gpt-6-luna high | luna-high-a1 |  | 是 | 1 | 是 | 0.463 | 0.463 | 0.463 | 0.000 | 0 | 1.5 | 0.15 | 62,767 | 508,800 | 9,474 | 10 | 只报 token | gpt-6-luna | default | 未知 | ≥108.7 | 712.8 | 107.6 |
| 6 codex gpt-6-luna high | luna-high-a2 |  | 是 | 2 | 是 | 0.506 | 0.506 | 0.506 | 0.000 | 0 | 1.5 | 0.15 | 51,461 | 269,952 | 8,390 | 7 | 只报 token | gpt-6-luna | default | 未知 | ≥92.6 | 562.4 | 91.7 |
| 6 codex gpt-6-luna high | luna-high-a3 |  | 是 | 3 | 是 | 0.549 | 0.549 | 0.549 | 0.000 | 0 | 1.6 | 0.16 | 61,888 | 417,920 | 8,680 | 10 | 只报 token | gpt-6-luna | default | 未知 | ≥93.4 | 653.5 | 91.6 |
| 6 codex gpt-6-luna high | luna-high-a4 |  | 是 | 4 | 是 | 0.499 | 0.499 | 0.499 | 0.000 | 0 | 1.1 | 0.11 | 62,876 | 282,112 | 5,708 | 7 | 只报 token | gpt-6-luna | default | 未知 | ≥89.9 | 980.1 | 89.0 |
| 6 codex gpt-6-luna high | luna-high-a5 |  | 是 | 5 | 是 | 0.346 | 0.346 | 0.346 | 0.000 | 0 | 1.1 | 0.11 | 45,714 | 412,800 | 4,701 | 10 | 只报 token | gpt-6-luna | default | 未知 | ≥70.4 | 716.5 | 73.7 |
| 7 codex deepseek-flash low | codex-low-a1 |  | 是 | 1 | 是 | 0.575 | 0.575 | 0.575 | 0.000 | 0 | 1.8 | 0.30 | 55,107 | 511,744 | 18,614 | 37 | 0.021（¥0.140） | deepseek-flash | default | 未知 | ≥168.7 | 497.3 | 168.0 |
| 7 codex deepseek-flash low | codex-low-a2 |  | 是 | 2 | 是 | 0.570 | 0.570 | 0.570 | 0.000 | 0 | 2.2 | 0.35 | 49,642 | 698,368 | 25,595 | 33 | 0.025（¥0.166） | deepseek-flash | default | 未知 | ≥199.8 | 383.2 | 197.6 |
| 7 codex deepseek-flash low | codex-low-a3 |  | 是 | 3 | 是 | 0.682 | 0.682 | 0.682 | 0.000 | 0 | 1.8 | 0.29 | 44,081 | 555,392 | 21,269 | 28 | 0.021（¥0.140） | deepseek-flash | default | 未知 | ≥200.0 | 409.5 | 197.6 |
| 7 codex deepseek-flash low | codex-low-a4 |  | 是 | 4 | 是 | 0.648 | 0.648 | 0.648 | 0.000 | 0 | 1.6 | 0.26 | 47,858 | 508,288 | 18,214 | 28 | 0.020（¥0.131） | deepseek-flash | default | 未知 | ≥190.5 | 495.3 | 188.5 |
| 7 codex deepseek-flash low | codex-low-a5 |  | 是 | 5 | 是 | 0.696 | 0.696 | 0.696 | 0.000 | 0 | 2.5 | 0.41 | 48,142 | 1,361,280 | 29,262 | 48 | 0.029（¥0.192） | deepseek-flash | default | 未知 | ≥195.3 | 315.9 | 192.0 |
| 8 codex deepseek-flash high | codex-medium-a1 |  | 是 | 1 | 是 | 0.732 | 0.732 | 0.732 | 0.000 | 0 | 2.9 | 0.52 | 48,836 | 1,260,160 | 24,700 | 46 | ≥0.026（¥0.173） | deepseek-flash | default、not-returned | 未知 | ≥144.5 | 280.6 | 141.9 |
| 8 codex deepseek-flash high | codex-medium-a2 |  | 是 | 2 | 是 | 0.607 | 0.607 | 0.607 | 0.000 | 0 | 2.0 | 0.37 | 44,878 | 513,536 | 20,340 | 30 | 0.020（¥0.137） | deepseek-flash | default | 未知 | ≥168.6 | 368.9 | 167.2 |
| 8 codex deepseek-flash high | codex-high-a1 |  | 是 | 3 | 是 | 0.743 | 0.743 | 0.743 | 0.000 | 0 | 3.0 | 0.54 | 57,717 | 803,072 | 29,494 | 36 | ≥0.029（¥0.192） | deepseek-flash | default、not-returned | 未知 | ≥167.6 | 320.2 | 163.6 |
| 8 codex deepseek-flash high | codex-high-a2 |  | 是 | 4 | 是 | 0.659 | 0.659 | 0.659 | 0.000 | 0 | 3.0 | 0.54 | 45,047 | 1,209,856 | 27,874 | 36 | ≥0.027（¥0.181） | deepseek-flash | default、not-returned | 未知 | ≥165.9 | 250.9 | 155.3 |
| 8 codex deepseek-flash high | codex-high-a3 |  | 是 | 5 | 是 | 0.532 | 0.532 | 0.547 | 0.027 | 1 | 1.4 | 0.26 | 42,914 | 503,424 | 16,745 | 21 | 0.018（¥0.120） | deepseek-flash | default | 未知 | ≥197.0 | 496.8 | 193.8 |
| 9 codex deepseek-flash max | codex-max-a1 |  | 是 | 1 | 是 | 0.796 | 0.796 | 0.796 | 0.000 | 0 | 2.4 | 0.41 | 56,748 | 990,080 | 29,685 | 42 | 0.029（¥0.195） | deepseek-flash | default | 未知 | ≥211.7 | 399.7 | 209.1 |
| 9 codex deepseek-flash max | codex-max-a2 |  | 是 | 2 | 是 | 0.624 | 0.624 | 0.637 | 0.021 | 1 | 2.2 | 0.38 | 52,615 | 1,007,104 | 28,618 | 54 | 0.028（¥0.187） | deepseek-flash | default | 未知 | ≥218.6 | 396.4 | 215.6 |
| 9 codex deepseek-flash max | codex-max-a3 |  | 是 | 3 | 是 | 0.720 | 0.720 | 0.734 | 0.018 | 1 | 2.6 | 0.44 | 50,155 | 781,568 | 30,042 | 35 | 0.028（¥0.186） | deepseek-flash | default | 未知 | ≥196.2 | 325.5 | 195.0 |
| 9 codex deepseek-flash max | codex-max-a4 |  | 是 | 4 | 是 | 0.727 | 0.727 | 0.727 | 0.000 | 0 | 3.0 | 0.52 | 55,947 | 1,367,040 | 31,784 | 37 | ≥0.032（¥0.210） | deepseek-flash | default、not-returned | 未知 | ≥189.0 | 309.3 | 175.7 |
| 9 codex deepseek-flash max | codex-max-a5 |  | 是 | 5 | 是 | 0.820 | 0.820 | 0.820 | 0.000 | 0 | 3.1 | 0.53 | 60,843 | 1,726,848 | 35,902 | 49 | ≥0.036（¥0.239） | deepseek-flash | default、not-returned | 未知 | ≥202.5 | 327.8 | 193.4 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a1 |  | 是 | 1 | 是 | 0.734 | 0.734 | 0.734 | 0.000 | 0 | 8.0 | 0.52 | 57,724 | 1,437,304 | 34,111 | 32 | 0.048 | 未知 | 未知 | 1479.1 | 85.2 | 119.7 | 70.8 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a2 |  | 是 | 2 | 是 | 0.758 | 0.758 | 0.787 | 0.037 | 9 | 10.8 | 0.70 | 79,427 | 2,514,426 | 46,893 | 40 | 0.074 | 未知 | 未知 | 1434.4 | 85.5 | 122.4 | 72.2 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a3 |  | 是 | 3 | 是 | 0.801 | 0.801 | 0.833 | 0.039 | 9 | 10.0 | 0.65 | 61,759 | 2,497,253 | 40,409 | 39 | 0.068 | 未知 | 未知 | 1213.0 | 79.5 | 102.5 | 67.1 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a4 |  | 是 | 4 | 是 | 0.765 | 0.765 | 0.807 | 0.052 | 10 | 9.0 | 0.58 | 67,825 | 1,879,367 | 37,405 | 33 | 0.058 | 未知 | 未知 | 1528.6 | 82.6 | 125.7 | 69.3 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a5 |  | 是 | 5 | 是 | 0.771 | 0.771 | 0.857 | 0.100 | 28 | 9.6 | 0.62 | 58,011 | 2,634,914 | 40,350 | 51 | 0.070 | 未知 | 未知 | 1143.3 | 84.1 | 100.9 | 70.2 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a6 |  | 是 | 6 | 是 | 0.746 | 0.746 | 0.809 | 0.078 | 14 | 8.3 | 0.54 | 57,303 | 1,515,462 | 35,565 | 32 | 0.050 | 未知 | 未知 | 1475.9 | 85.3 | 115.0 | 71.4 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a7 |  | 是 | 7 | 是 | 0.780 | 0.780 | 0.835 | 0.066 | 13 | 10.4 | 0.67 | 61,543 | 1,349,365 | 41,807 | 28 | 0.050 | 未知 | 未知 | 1564.7 | 77.6 | 99.0 | 67.3 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a8 |  | 是 | 8 | 是 | 0.816 | 0.816 | 0.855 | 0.045 | 7 | 7.4 | 0.48 | 57,565 | 1,600,795 | 30,306 | 30 | 0.048 | 未知 | 未知 | 1393.0 | 84.6 | 129.7 | 68.3 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a9 |  | 是 | 9 | 是 | 0.000 | 0.000 | 0.000 | 0.000 | 0 | 6.6 | 0.42 | 59,158 | 779,516 | 27,163 | 22 | 0.034 | 未知 | 未知 | 1729.9 | 84.8 | 149.8 | 68.8 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a10 |  | 是 | 10 | 是 | 0.769 | 0.769 | 0.811 | 0.052 | 8 | 6.5 | 0.42 | 63,753 | 1,152,893 | 26,582 | 23 | 0.041 | 未知 | 未知 | 1605.8 | 85.8 | 162.9 | 67.9 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a1 |  | 是 | 1 | 是 | 0.844 | 0.844 | 0.876 | 0.036 | 7 | 11.3 | 0.70 | 69,145 | 2,947,721 | 47,856 | 48 | 0.080 | 未知 | 未知 | 1287.5 | 82.4 | 101.9 | 70.5 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a2 |  | 是 | 2 | 是 | 0.643 | 0.643 | 0.714 | 0.100 | 23 | 10.2 | 0.64 | 52,664 | 1,749,649 | 43,616 | 37 | 0.056 | 未知 | 未知 | 1341.6 | 82.1 | 85.9 | 71.1 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a3 |  | 是 | 3 | 是 | 0.619 | 0.619 | 0.688 | 0.100 | 54 | 10.0 | 0.62 | 71,445 | 1,380,309 | 43,760 | 29 | 0.053 | 未知 | 未知 | 1651.3 | 85.2 | 119.3 | 73.0 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a4 |  | 是 | 4 | 是 | 0.746 | 0.746 | 0.760 | 0.019 | 1 | 7.7 | 0.48 | 53,821 | 1,041,212 | 32,770 | 31 | 0.040 | 未知 | 未知 | 1553.1 | 84.6 | 116.0 | 70.6 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a5 |  | 是 | 5 | 是 | 0.727 | 0.727 | 0.762 | 0.045 | 9 | 8.9 | 0.55 | 57,808 | 1,515,928 | 36,953 | 33 | 0.050 | 未知 | 未知 | 1436.5 | 82.0 | 108.5 | 69.4 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a6 |  | 是 | 6 | 是 | 0.780 | 0.780 | 0.780 | 0.000 | 0 | 9.9 | 0.62 | 73,780 | 2,112,528 | 42,486 | 36 | 0.065 | 未知 | 未知 | 1536.8 | 84.6 | 124.4 | 71.6 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a7 |  | 是 | 7 | 是 | 0.782 | 0.782 | 0.793 | 0.014 | 4 | 8.9 | 0.55 | 62,085 | 1,406,077 | 38,294 | 26 | 0.050 | 未知 | 未知 | 1675.5 | 84.3 | 116.3 | 71.7 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a8 |  | 是 | 8 | 是 | 0.823 | 0.823 | 0.835 | 0.015 | 3 | 8.1 | 0.51 | 60,995 | 1,432,895 | 34,218 | 32 | 0.048 | 未知 | 未知 | 1575.4 | 84.5 | 125.3 | 70.3 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a9 |  | 是 | 9 | 是 | 0.750 | 0.750 | 0.764 | 0.018 | 3 | 6.6 | 0.41 | 57,750 | 1,027,574 | 27,532 | 24 | 0.038 | 未知 | 未知 | 1597.6 | 86.3 | 145.3 | 69.3 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a10 |  | 是 | 10 | 是 | 0.787 | 0.787 | 0.787 | 0.000 | 0 | 7.8 | 0.49 | 49,002 | 1,268,970 | 33,524 | 31 | 0.043 | 未知 | 未知 | 1454.6 | 85.4 | 104.3 | 71.4 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a1 |  | 是 | 1 | 是 | 0.756 | 0.756 | 0.761 | 0.006 | 1 | 10.8 | 0.63 | 57,629 | 1,254,908 | 49,028 | 29 | 0.052 | 未知 | 未知 | 1482.9 | 86.9 | 89.2 | 75.9 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a2 |  | 是 | 2 | 是 | 0.794 | 0.794 | 0.822 | 0.034 | 4 | 11.5 | 0.67 | 58,455 | 2,479,356 | 50,920 | 41 | 0.072 | 未知 | 未知 | 1274.1 | 85.0 | 84.9 | 73.9 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a3 |  | 是 | 3 | 是 | 0.705 | 0.705 | 0.783 | 0.100 | 33 | 10.5 | 0.61 | 71,644 | 1,830,825 | 45,034 | 35 | 0.061 | 未知 | 未知 | 1627.5 | 82.6 | 113.2 | 71.2 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a4 |  | 是 | 4 | 是 | 0.782 | 0.782 | 0.869 | 0.100 | 18 | 10.2 | 0.59 | 75,806 | 927,341 | 42,969 | 29 | 0.046 | 未知 | 未知 | 1846.7 | 81.4 | 124.1 | 70.4 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a5 |  | 是 | 5 | 是 | 0.800 | 0.800 | 0.854 | 0.064 | 11 | 9.1 | 0.53 | 59,409 | 1,138,384 | 37,318 | 30 | 0.045 | 未知 | 未知 | 1665.8 | 80.0 | 109.2 | 68.6 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a6 |  | 是 | 6 | 是 | 0.724 | 0.724 | 0.753 | 0.038 | 6 | 11.1 | 0.64 | 66,355 | 1,770,199 | 50,303 | 44 | 0.062 | 未知 | 未知 | 1474.6 | 87.0 | 99.6 | 75.5 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a7 |  | 是 | 7 | 是 | 0.690 | 0.690 | 0.714 | 0.033 | 5 | 8.5 | 0.49 | 48,832 | 1,060,125 | 36,013 | 30 | 0.041 | 未知 | 未知 | 1450.9 | 83.0 | 95.8 | 70.6 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a8 |  | 是 | 8 | 是 | 0.776 | 0.776 | 0.862 | 0.100 | 18 | 9.6 | 0.56 | 57,901 | 1,849,570 | 41,717 | 44 | 0.058 | 未知 | 未知 | 1287.1 | 85.8 | 100.6 | 72.5 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a9 |  | 是 | 9 | 是 | 0.859 | 0.859 | 0.864 | 0.006 | 1 | 9.3 | 0.54 | 58,637 | 1,316,231 | 40,449 | 35 | 0.049 | 未知 | 未知 | 1468.9 | 85.2 | 105.0 | 72.5 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a10 |  | 是 | 10 | 是 | 0.782 | 0.782 | 0.831 | 0.058 | 14 | 11.4 | 0.66 | 67,714 | 2,050,700 | 50,799 | 39 | 0.067 | 未知 | 未知 | 1478.3 | 85.7 | 99.3 | 74.5 |
| 13 claude-code opus low | opus-low-a1 |  | 是 | 1 | 是 | 0.607 | 0.607 | 0.645 | 0.059 | 3 | 2.1 | 0.12 | 47,062 | 276,613 | 5,476 | 7 | 0.541 | claude-opus-5-5 | standard | 未知 | ≥93.7 | 369.4 | 43.0 |
| 13 claude-code opus low | opus-low-a2 |  | 是 | 2 | 是 | 0.625 | 0.625 | 0.694 | 0.100 | 34 | 1.0 | 0.06 | 47,933 | 212,344 | 4,501 | 6 | 0.516 | claude-opus-5-5 | standard | 未知 | ≥81.4 | 812.4 | 76.3 |
| 13 claude-code opus low | opus-low-a3 |  | 是 | 3 | 是 | 0.717 | 0.717 | 0.717 | 0.000 | 0 | 1.6 | 0.09 | 47,042 | 304,413 | 5,441 | 8 | 0.546 | claude-opus-5-5 | standard | 未知 | ≥61.2 | 485.3 | 56.1 |
| 13 claude-code opus low | opus-low-a4 |  | 是 | 4 | 是 | 0.650 | 0.650 | 0.664 | 0.020 | 1 | 1.5 | 0.08 | 43,521 | 201,531 | 4,504 | 6 | 0.478 | claude-opus-5-5 | standard | 未知 | ≥71.9 | 499.3 | 51.7 |
| 13 claude-code opus low | opus-low-a5 |  | 是 | 5 | 是 | 0.688 | 0.688 | 0.765 | 0.100 | 37 | 1.6 | 0.09 | 52,144 | 299,113 | 4,718 | 7 | 0.571 | claude-opus-5-5 | standard | 未知 | ≥80.1 | 532.1 | 48.1 |
| 14 claude-code opus medium | opus-medium-a1 |  | 是 | 1 | 是 | 0.770 | 0.770 | 0.778 | 0.011 | 1 | 2.9 | 0.16 | 54,784 | 538,225 | 10,564 | 13 | 0.757 | claude-opus-5-5 | standard | 未知 | ≥81.2 | 311.6 | 60.1 |
| 14 claude-code opus medium | opus-medium-a2 |  | 是 | 2 | 是 | 0.823 | 0.823 | 0.832 | 0.012 | 1 | 2.0 | 0.11 | 58,102 | 665,918 | 10,553 | 16 | 0.809 | claude-opus-5-5 | standard | 未知 | ≥90.7 | 474.7 | 86.2 |
| 14 claude-code opus medium | opus-medium-a3 |  | 是 | 3 | 是 | 0.798 | 0.798 | 0.809 | 0.014 | 1 | 1.6 | 0.09 | 60,451 | 379,516 | 8,711 | 8 | 0.734 | claude-opus-5-5 | standard | 未知 | ≥93.2 | 616.4 | 88.8 |
| 14 claude-code opus medium | opus-medium-a4 |  | 是 | 4 | 是 | 0.738 | 0.738 | 0.820 | 0.100 | 43 | 1.6 | 0.09 | 60,791 | 313,435 | 9,088 | 7 | 0.731 | claude-opus-5-5 | standard | 未知 | ≥100.0 | 638.5 | 95.5 |
| 14 claude-code opus medium | opus-medium-a5 |  | 是 | 5 | 是 | 0.740 | 0.740 | 0.822 | 0.100 | 47 | 1.8 | 0.10 | 63,538 | 383,102 | 9,364 | 8 | 0.772 | claude-opus-5-5 | standard | 未知 | ≥91.1 | 590.6 | 87.0 |
| 15 claude-code opus high | opus-high-a1 |  | 是 | 1 | 是 | 0.881 | 0.881 | 0.881 | 0.000 | 0 | 2.1 | 0.12 | 59,914 | 405,358 | 11,251 | 10 | 0.785 | claude-opus-5-5 | standard | 未知 | ≥93.1 | 472.4 | 88.7 |
| 15 claude-code opus high | opus-high-a2 |  | 是 | 2 | 是 | 0.828 | 0.828 | 0.828 | 0.000 | 0 | 2.6 | 0.15 | 72,206 | 828,753 | 13,226 | 15 | 1.008 | claude-opus-5-5 | standard | 未知 | ≥91.3 | 469.7 | 86.0 |
| 15 claude-code opus high | opus-high-a3 |  | 是 | 3 | 是 | 0.886 | 0.886 | 0.886 | 0.000 | 0 | 2.6 | 0.15 | 63,071 | 637,432 | 12,232 | 14 | 0.877 | claude-opus-5-5 | standard | 未知 | ≥82.6 | 405.7 | 78.7 |
| 15 claude-code opus high | opus-high-a4 |  | 是 | 4 | 是 | 0.805 | 0.805 | 0.852 | 0.055 | 5 | 3.0 | 0.17 | 61,408 | 501,226 | 12,844 | 10 | 0.848 | claude-opus-5-5 | standard | 未知 | ≥90.6 | 341.4 | 71.4 |
| 15 claude-code opus high | opus-high-a5 |  | 是 | 5 | 是 | 0.835 | 0.835 | 0.843 | 0.010 | 1 | 2.4 | 0.14 | 60,403 | 468,938 | 11,319 | 10 | 0.803 | claude-opus-5-5 | standard | 未知 | ≥83.5 | 427.3 | 80.1 |
| 16 claude-code sonnet low | sonnet-low-a1 |  | 是 | 1 | 是 | 0.432 | 0.432 | 0.432 | 0.000 | 0 | 2.2 | 0.16 | 45,814 | 309,917 | 4,618 | 9 | 0.260 | claude-sonnet-5-5 | standard | 未知 | ≥104.3 | 340.0 | 34.3 |
| 16 claude-code sonnet low | sonnet-low-a2 |  | 是 | 2 | 是 | 0.412 | 0.412 | 0.426 | 0.033 | 1 | 2.3 | 0.16 | 42,660 | 197,221 | 3,466 | 6 | 0.225 | claude-sonnet-5-5 | standard | 未知 | ≥82.7 | 315.1 | 25.6 |
| 16 claude-code sonnet low | sonnet-low-a3 |  | 是 | 3 | 是 | 0.440 | 0.440 | 0.453 | 0.027 | 0 | 1.1 | 0.09 | 47,443 | 245,722 | 3,665 | 8 | 0.251 | claude-sonnet-5-5 | standard | 未知 | ≥61.2 | 701.3 | 54.2 |
| 16 claude-code sonnet low | sonnet-low-a4 |  | 是 | 4 | 是 | 0.624 | 0.624 | 0.654 | 0.046 | 2 | 1.4 | 0.10 | 44,948 | 277,978 | 4,847 | 9 | 0.256 | claude-sonnet-5-5 | standard | 未知 | ≥77.8 | 545.1 | 58.8 |
| 16 claude-code sonnet low | sonnet-low-a5 |  | 是 | 5 | 是 | 0.523 | 0.523 | 0.523 | 0.000 | 0 | 0.6 | 0.05 | 42,939 | 314,151 | 3,701 | 10 | 0.240 | claude-sonnet-5-5 | standard | 未知 | ≥113.8 | 1141.1 | 98.4 |
| 17 claude-code sonnet medium | sonnet-medium-a1 |  | 是 | 1 | 是 | 0.421 | 0.421 | 0.421 | 0.000 | 0 | 1.8 | 0.13 | 49,424 | 236,677 | 4,689 | 7 | 0.268 | claude-sonnet-5-5 | standard | 未知 | ≥79.6 | 453.3 | 43.0 |
| 17 claude-code sonnet medium | sonnet-medium-a2 |  | 是 | 2 | 是 | 0.602 | 0.602 | 0.602 | 0.000 | 0 | 2.4 | 0.17 | 47,596 | 217,132 | 5,151 | 7 | 0.264 | claude-sonnet-5-5 | standard | 未知 | ≥98.1 | 332.4 | 36.0 |
| 17 claude-code sonnet medium | sonnet-medium-a3 |  | 是 | 3 | 是 | 0.532 | 0.532 | 0.543 | 0.021 | 1 | 0.7 | 0.05 | 44,811 | 215,412 | 5,001 | 6 | 0.251 | claude-sonnet-5-5 | standard | 未知 | ≥133.9 | 1092.6 | 121.9 |
| 17 claude-code sonnet medium | sonnet-medium-a4 |  | 是 | 4 | 是 | 0.456 | 0.456 | 0.470 | 0.030 | 1 | 1.2 | 0.09 | 43,174 | 243,853 | 4,956 | 9 | 0.247 | claude-sonnet-5-5 | standard | 未知 | ≥92.1 | 603.5 | 69.3 |
| 17 claude-code sonnet medium | sonnet-medium-a5 |  | 是 | 5 | 是 | 0.634 | 0.634 | 0.634 | 0.000 | 0 | 0.9 | 0.07 | 46,593 | 215,829 | 5,336 | 7 | 0.261 | claude-sonnet-5-5 | standard | 未知 | ≥100.0 | 820.5 | 94.0 |
| 18 claude-code sonnet high | sonnet-high-a1 |  | 是 | 1 | 是 | 0.705 | 0.705 | 0.746 | 0.055 | 3 | 3.5 | 0.25 | 57,946 | 424,467 | 9,259 | 11 | 0.367 | claude-sonnet-5-5 | standard | 未知 | ≥89.2 | 273.8 | 43.7 |
| 18 claude-code sonnet high | sonnet-high-a2 |  | 是 | 2 | 是 | 0.602 | 0.602 | 0.602 | 0.000 | 0 | 1.7 | 0.12 | 48,950 | 258,302 | 7,607 | 8 | 0.298 | claude-sonnet-5-5 | standard | 未知 | ≥102.9 | 476.5 | 74.0 |
| 18 claude-code sonnet high | sonnet-high-a3 |  | 是 | 3 | 是 | 0.580 | 0.580 | 0.644 | 0.100 | 8 | 1.4 | 0.11 | 53,554 | 317,957 | 6,946 | 9 | 0.315 | claude-sonnet-5-5 | standard | 未知 | ≥88.1 | 632.9 | 82.1 |
| 18 claude-code sonnet high | sonnet-high-a4 |  | 是 | 4 | 是 | 0.712 | 0.712 | 0.712 | 0.000 | 0 | 1.5 | 0.12 | 55,229 | 247,206 | 9,209 | 8 | 0.338 | claude-sonnet-5-5 | standard | 未知 | ≥121.7 | 625.3 | 104.3 |
| 18 claude-code sonnet high | sonnet-high-a5 |  | 是 | 5 | 是 | 0.656 | 0.656 | 0.668 | 0.018 | 1 | 1.6 | 0.13 | 60,784 | 495,715 | 9,078 | 12 | 0.383 | claude-sonnet-5-5 | standard | 未知 | ≥97.5 | 619.5 | 92.5 |
| 19 claude-code haiku low | haiku-low-a1 |  | 是 | 1 | 是 | 0.331 | 0.331 | 0.331 | 0.000 | 0 | 1.8 | 0.19 | 44,689 | 152,998 | 6,830 | 5 | 0.014 | claude-haiku-5-5 | standard | 未知 | ≥180.3 | 421.8 | 64.5 |
| 19 claude-code haiku low | haiku-low-a2 |  | 是 | 2 | 是 | 0.392 | 0.392 | 0.407 | 0.037 | 1 | 1.1 | 0.12 | 49,695 | 310,211 | 10,291 | 10 | 0.018 | claude-haiku-5-5 | standard | 未知 | ≥188.9 | 774.7 | 160.4 |
| 19 claude-code haiku low | haiku-low-a3 |  | 是 | 3 | 是 | 0.490 | 0.490 | 0.490 | 0.000 | 0 | 1.4 | 0.17 | 55,810 | 167,161 | 17,273 | 10 | 0.021 | claude-haiku-5-5 | standard | 未知 | ≥223.1 | 656.5 | 203.2 |
| 19 claude-code haiku low | haiku-low-a4 |  | 是 | 4 | 是 | 0.470 | 0.470 | 0.470 | 0.000 | 0 | 1.4 | 0.17 | 53,879 | 266,761 | 13,440 | 7 | 0.020 | claude-haiku-5-5 | standard | 未知 | ≥198.3 | 631.5 | 157.5 |
| 19 claude-code haiku low | haiku-low-a5 |  | 是 | 5 | 是 | 0.390 | 0.390 | 0.390 | 0.000 | 0 | 0.8 | 0.10 | 46,187 | 195,597 | 9,657 | 6 | 0.016 | claude-haiku-5-5 | standard | 未知 | ≥203.4 | 913.8 | 191.1 |
| 20 claude-code haiku medium | haiku-medium-a1 |  | 是 | 1 | 是 | 0.429 | 0.429 | 0.454 | 0.057 | 2 | 2.6 | 0.31 | 54,385 | 209,406 | 15,151 | 7 | 0.021 | claude-haiku-5-5 | standard | 未知 | ≥170.1 | 353.7 | 98.5 |
| 20 claude-code haiku medium | haiku-medium-a2 |  | 是 | 2 | 是 | 0.538 | 0.538 | 0.538 | 0.000 | 0 | 1.2 | 0.15 | 54,000 | 311,189 | 14,203 | 10 | 0.021 | claude-haiku-5-5 | standard | 未知 | ≥209.6 | 739.7 | 194.6 |
| 20 claude-code haiku medium | haiku-medium-a3 |  | 是 | 3 | 是 | 0.569 | 0.569 | 0.609 | 0.067 | 3 | 1.6 | 0.19 | 59,668 | 333,773 | 18,706 | 9 | 0.025 | claude-haiku-5-5 | standard | 未知 | ≥209.1 | 634.1 | 198.8 |
| 20 claude-code haiku medium | haiku-medium-a4 |  | 是 | 4 | 是 | 0.467 | 0.467 | 0.467 | 0.000 | 0 | 1.5 | 0.18 | 56,524 | 320,131 | 15,736 | 10 | 0.022 | claude-haiku-5-5 | standard | 未知 | ≥194.1 | 636.0 | 177.1 |
| 20 claude-code haiku medium | haiku-medium-a5 |  | 是 | 5 | 是 | 0.502 | 0.502 | 0.502 | 0.000 | 0 | 1.2 | 0.15 | 54,799 | 318,715 | 13,636 | 9 | 0.021 | claude-haiku-5-5 | standard | 未知 | ≥205.8 | 757.7 | 188.5 |
| 21 claude-code haiku high | haiku-high-a1 |  | 是 | 1 | 是 | 0.510 | 0.510 | 0.567 | 0.100 | 8 | 3.0 | 0.36 | 71,927 | 316,811 | 22,168 | 10 | 0.029 | claude-haiku-5-5 | standard | 未知 | ≥190.8 | 401.4 | 123.7 |
| 21 claude-code haiku high | haiku-high-a2 |  | 是 | 2 | 是 | 0.552 | 0.552 | 0.552 | 0.000 | 0 | 1.7 | 0.21 | 57,009 | 284,568 | 16,319 | 13 | 0.022 | claude-haiku-5-5 | standard | 未知 | ≥206.8 | 544.9 | 156.0 |
| 21 claude-code haiku high | haiku-high-a3 |  | 是 | 3 | 是 | 0.600 | 0.600 | 0.611 | 0.018 | 1 | 1.9 | 0.23 | 61,597 | 277,279 | 20,971 | 9 | 0.026 | claude-haiku-5-5 | standard | 未知 | ≥218.5 | 545.5 | 185.7 |
| 21 claude-code haiku high | haiku-high-a4 |  | 是 | 4 | 是 | 0.480 | 0.480 | 0.495 | 0.031 | 1 | 1.7 | 0.21 | 59,886 | 336,420 | 19,015 | 10 | 0.025 | claude-haiku-5-5 | standard | 未知 | ≥201.8 | 572.2 | 181.7 |
| 21 claude-code haiku high | haiku-high-a5 |  | 是 | 5 | 是 | 0.507 | 0.507 | 0.507 | 0.000 | 0 | 2.7 | 0.32 | 71,046 | 467,968 | 27,280 | 12 | 0.033 | claude-haiku-5-5 | standard | 未知 | ≥217.0 | 443.7 | 170.4 |
| 22 claude-code deepseek-flash low | cc-low-a1 |  | 是 | 1 | 是 | 0.597 | 0.597 | 0.648 | 0.078 | 4 | 1.5 | 0.26 | 39,435 | 327,680 | 12,744 | 16 | 0.015（¥0.097） | deepseek-flash | standard | 未知 | ≥145.8 | 436.9 | 141.2 |
| 22 claude-code deepseek-flash low | cc-low-a2 |  | 是 | 2 | 是 | 0.662 | 0.662 | 0.662 | 0.000 | 0 | 3.0 | 0.53 | 41,087 | 244,352 | 9,375 | 11 | 0.013（¥0.084） | deepseek-flash | standard | 未知 | ≥186.9 | 225.4 | 51.4 |
| 22 claude-code deepseek-flash low | cc-low-a3 |  | 是 | 3 | 是 | 0.459 | 0.459 | 0.459 | 0.000 | 0 | 4.5 | 0.78 | 31,981 | 206,720 | 8,394 | 13 | 0.010（¥0.070） | deepseek-flash | standard | 未知 | ≥115.4 | 119.5 | 31.4 |
| 22 claude-code deepseek-flash low | cc-low-a4 |  | 是 | 4 | 是 | 0.521 | 0.521 | 0.579 | 0.100 | 6 | 1.7 | 0.30 | 42,169 | 297,728 | 12,472 | 12 | 0.015（¥0.098） | deepseek-flash | standard | 未知 | ≥187.3 | 415.3 | 122.8 |
| 22 claude-code deepseek-flash low | cc-low-a5 |  | 是 | 5 | 是 | 0.420 | 0.420 | 0.466 | 0.100 | 8 | 3.2 | 0.56 | 38,430 | 324,480 | 8,219 | 23 | 0.012（¥0.078） | deepseek-flash | standard | 未知 | ≥105.6 | 200.2 | 42.8 |
| 23 claude-code deepseek-flash high | cc-high-a1 |  | 是 | 1 | 是 | 0.592 | 0.592 | 0.657 | 0.100 | 10 | 3.1 | 0.54 | 46,151 | 259,200 | 14,030 | 11 | 0.016（¥0.107） | deepseek-flash | standard | 未知 | ≥136.2 | 249.0 | 75.7 |
| 23 claude-code deepseek-flash high | cc-high-a2 |  | 是 | 2 | 是 | 0.698 | 0.698 | 0.698 | 0.000 | 0 | 3.5 | 0.61 | 42,850 | 215,168 | 10,862 | 12 | 0.014（¥0.091） | deepseek-flash | standard | 未知 | ≥123.4 | 203.4 | 51.6 |
| 23 claude-code deepseek-flash high | cc-high-a3 |  | 是 | 3 | 是 | 0.423 | 0.423 | 0.466 | 0.093 | 3 | 3.6 | 0.63 | 33,503 | 240,512 | 9,982 | 12 | 0.012（¥0.078） | deepseek-flash | standard | 未知 | ≥124.0 | 154.0 | 45.9 |
| 23 claude-code deepseek-flash high | cc-high-a4 |  | 是 | 4 | 是 | 0.654 | 0.654 | 0.714 | 0.084 | 4 | 2.6 | 0.45 | 39,907 | 594,304 | 14,013 | 26 | 0.016（¥0.108） | deepseek-flash | standard | 未知 | ≥151.8 | 259.7 | 91.2 |
| 23 claude-code deepseek-flash high | cc-high-a5 |  | 是 | 5 | 是 | 0.606 | 0.606 | 0.665 | 0.089 | 5 | 3.3 | 0.58 | 53,440 | 1,155,840 | 23,610 | 31 | 0.026（¥0.171） | deepseek-flash | standard | 未知 | ≥179.7 | 267.2 | 118.0 |
| 23 claude-code deepseek-flash high | cc-medium-a1 | high requested as medium, T=362 | 是 | 1 | 是 | 0.563 | 0.563 | 0.626 | 0.100 | 6 | 3.8 | 0.63 | 41,861 | 324,864 | 10,223 | 13 | 0.013（¥0.089） | deepseek-flash | standard | 未知 | ≥144.0 | 184.8 | 45.1 |
| 24 claude-code deepseek-flash max | cc-max-a1 |  | 是 | 1 | 是 | 0.633 | 0.633 | 0.633 | 0.000 | 0 | 3.5 | 0.58 | 48,509 | 599,680 | 22,895 | 28 | 0.023（¥0.152） | deepseek-flash | standard | 未知 | ≥168.6 | 230.9 | 109.0 |
| 24 claude-code deepseek-flash max | cc-max-a2 |  | 是 | 2 | 是 | 0.567 | 0.567 | 0.618 | 0.083 | 4 | 4.1 | 0.68 | 42,542 | 289,024 | 17,159 | 10 | 0.018（¥0.117） | deepseek-flash | standard | 未知 | ≥201.5 | 173.7 | 70.0 |
| 24 claude-code deepseek-flash max | cc-max-a3 |  | 是 | 3 | 是 | 0.645 | 0.645 | 0.716 | 0.098 | 6 | 3.1 | 0.51 | 55,107 | 863,360 | 32,428 | 25 | 0.030（¥0.202） | deepseek-flash | standard | 未知 | ≥202.0 | 297.9 | 175.3 |
| 24 claude-code deepseek-flash max | cc-max-a4 |  | 是 | 4 | 是 | 0.511 | 0.511 | 0.522 | 0.020 | 1 | 4.8 | 0.79 | 47,100 | 643,072 | 19,868 | 41 | 0.021（¥0.139） | deepseek-flash | standard | 未知 | ≥147.8 | 164.2 | 69.2 |
| 24 claude-code deepseek-flash max | cc-max-a5 |  | 是 | 5 | 是 | 0.693 | 0.693 | 0.726 | 0.047 | 3 | 3.2 | 0.54 | 45,899 | 261,248 | 18,929 | 15 | 0.019（¥0.127） | deepseek-flash | standard | 未知 | ≥176.1 | 235.5 | 97.1 |
| 25 claude-code strata-iq3_xxs low | strata-low-a1 |  | 是 | 1 | 是 | 0.788 | 0.788 | 0.788 | 0.000 | 0 | 9.5 | 0.66 | 60,686 | 2,314,910 | 43,016 | 43 | 0.066 | qwen3.8-flash-next-iq3_xxs | not-returned | 1169.6 | 86.0 | 106.4 | 75.5 |
| 25 claude-code strata-iq3_xxs low | strata-low-a6 |  | 是 | 2 | 是 | 0.719 | 0.719 | 0.799 | 0.100 | 44 | 9.8 | 0.67 | 72,009 | 2,466,933 | 45,032 | 62 | 0.071 | qwen3.8-flash-next-iq3_xxs | not-returned | 1307.6 | 86.9 | 123.1 | 77.0 |
| 25 claude-code strata-iq3_xxs low | strata-low-a7 |  | 是 | 3 | 是 | 0.591 | 0.591 | 0.602 | 0.018 | 2 | 10.6 | 0.74 | 59,370 | 2,700,417 | 47,603 | 48 | 0.074 | qwen3.8-flash-next-iq3_xxs | not-returned | 1152.0 | 83.8 | 93.0 | 74.6 |
| 25 claude-code strata-iq3_xxs low | strata-low-a8 |  | 是 | 4 | 是 | 0.646 | 0.646 | 0.718 | 0.100 | 66 | 9.6 | 0.67 | 53,965 | 1,522,960 | 43,555 | 31 | 0.053 | qwen3.8-flash-next-iq3_xxs | not-returned | 1404.9 | 82.3 | 93.4 | 75.4 |
| 25 claude-code strata-iq3_xxs low | strata-low-a9 |  | 是 | 5 | 是 | 0.770 | 0.770 | 0.783 | 0.017 | 3 | 10.4 | 0.72 | 53,347 | 1,867,378 | 47,765 | 33 | 0.060 | qwen3.8-flash-next-iq3_xxs | not-returned | 1169.4 | 84.5 | 85.4 | 76.5 |
| 25 claude-code strata-iq3_xxs low | strata-low-a10 |  | 是 | 6 | 是 | 0.795 | 0.795 | 0.795 | 0.000 | 0 | 9.0 | 0.62 | 60,023 | 1,783,495 | 39,843 | 38 | 0.056 | qwen3.8-flash-next-iq3_xxs | not-returned | 1326.4 | 83.2 | 111.8 | 74.2 |
| 25 claude-code strata-iq3_xxs low | strata-low-a11 |  | 是 | 7 | 是 | 0.706 | 0.706 | 0.784 | 0.100 | 107 | 9.7 | 0.67 | 56,497 | 1,875,452 | 44,446 | 35 | 0.059 | qwen3.8-flash-next-iq3_xxs | not-returned | 1286.8 | 85.2 | 97.5 | 76.7 |
| 25 claude-code strata-iq3_xxs low | strata-low-a12 |  | 是 | 8 | 是 | 0.717 | 0.717 | 0.792 | 0.095 | 15 | 8.4 | 0.58 | 68,341 | 2,390,301 | 36,132 | 43 | 0.065 | qwen3.8-flash-next-iq3_xxs | not-returned | 1235.1 | 83.3 | 135.7 | 71.7 |
| 25 claude-code strata-iq3_xxs low | strata-low-a13 |  | 是 | 9 | 是 | 0.687 | 0.687 | 0.763 | 0.100 | 30 | 8.1 | 0.56 | 50,130 | 1,505,413 | 37,208 | 27 | 0.049 | qwen3.8-flash-next-iq3_xxs | not-returned | 1370.0 | 84.7 | 103.0 | 76.5 |
| 25 claude-code strata-iq3_xxs low | strata-low-a14 |  | 是 | 10 | 是 | 0.665 | 0.665 | 0.738 | 0.100 | 67 | 7.7 | 0.53 | 59,407 | 2,336,713 | 33,655 | 43 | 0.062 | qwen3.8-flash-next-iq3_xxs | not-returned | 1185.2 | 85.4 | 129.0 | 73.1 |
| 25 claude-code strata-iq3_xxs low | strata-low-a2 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 1.1 | 0.08 | 16,599 | 143,063 | 4,650 | 11 | 0.007 | qwen3.8-flash-next-iq3_xxs | not-returned | 1606.1 | 86.1 | 245.4 | 68.7 |
| 25 claude-code strata-iq3_xxs low | strata-low-a3 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 1.2 | 0.08 | 20,179 | 114,411 | 4,632 | 7 | 0.007 | qwen3.8-flash-next-iq3_xxs | not-returned | 1680.9 | 85.0 | 292.4 | 67.1 |
| 25 claude-code strata-iq3_xxs low | strata-low-a4 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 7.3 | 0.50 | 38,195 | 840,612 | 34,572 | 36 | 0.035 | qwen3.8-flash-next-iq3_xxs | not-returned | 1336.8 | 85.4 | 87.4 | 79.1 |
| 25 claude-code strata-iq3_xxs low | strata-low-a5 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 2.5 | 0.17 | 31,234 | 302,506 | 10,807 | 19 | 0.015 | qwen3.8-flash-next-iq3_xxs | not-returned | 1753.4 | 84.5 | 209.4 | 72.4 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a6 |  | 是 | 1 | 是 | 0.684 | 0.684 | 0.760 | 0.100 | 27 | 6.9 | 0.46 | 50,060 | 950,116 | 32,607 | 29 | 0.038 | qwen3.8-flash-next-iq3_xxs | not-returned | 1585.3 | 87.8 | 121.6 | 79.2 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a7 |  | 是 | 2 | 是 | 0.690 | 0.690 | 0.694 | 0.007 | 1 | 8.6 | 0.58 | 50,670 | 1,486,316 | 40,101 | 36 | 0.050 | qwen3.8-flash-next-iq3_xxs | not-returned | 1320.8 | 86.8 | 98.7 | 78.1 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a8 |  | 是 | 3 | 是 | 0.661 | 0.661 | 0.734 | 0.100 | 14 | 4.1 | 0.28 | 41,250 | 641,754 | 18,203 | 23 | 0.025 | qwen3.8-flash-next-iq3_xxs | not-returned | 1493.8 | 85.3 | 166.7 | 73.6 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a9 |  | 是 | 4 | 是 | 0.795 | 0.795 | 0.883 | 0.100 | 18 | 8.4 | 0.57 | 54,496 | 1,273,225 | 40,004 | 31 | 0.047 | qwen3.8-flash-next-iq3_xxs | not-returned | 1398.8 | 87.7 | 108.0 | 79.3 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a10 |  | 是 | 5 | 是 | 0.703 | 0.703 | 0.781 | 0.100 | 24 | 6.7 | 0.46 | 49,642 | 864,257 | 30,927 | 29 | 0.036 | qwen3.8-flash-next-iq3_xxs | not-returned | 1566.1 | 84.2 | 122.9 | 76.6 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a11 |  | 是 | 6 | 是 | 0.639 | 0.639 | 0.690 | 0.074 | 5 | 6.3 | 0.42 | 46,513 | 905,180 | 27,583 | 29 | 0.034 | qwen3.8-flash-next-iq3_xxs | not-returned | 1498.0 | 81.7 | 123.6 | 73.3 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a12 |  | 是 | 7 | 是 | 0.615 | 0.615 | 0.683 | 0.100 | 66 | 7.9 | 0.54 | 69,162 | 1,363,965 | 37,570 | 40 | 0.050 | qwen3.8-flash-next-iq3_xxs | not-returned | 1587.9 | 88.7 | 145.3 | 78.9 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a13 |  | 是 | 8 | 是 | 0.816 | 0.816 | 0.816 | 0.000 | 0 | 8.0 | 0.54 | 70,213 | 1,181,513 | 37,745 | 25 | 0.047 | qwen3.8-flash-next-iq3_xxs | not-returned | 1664.3 | 87.4 | 145.9 | 78.4 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a14 |  | 是 | 9 | 是 | 0.702 | 0.702 | 0.780 | 0.100 | 18 | 8.9 | 0.60 | 55,528 | 1,828,372 | 40,101 | 40 | 0.056 | qwen3.8-flash-next-iq3_xxs | not-returned | 1266.8 | 84.8 | 104.5 | 75.5 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a15 |  | 是 | 10 | 是 | 0.700 | 0.700 | 0.717 | 0.023 | 2 | 4.5 | 0.31 | 45,076 | 742,706 | 20,318 | 20 | 0.028 | qwen3.8-flash-next-iq3_xxs | not-returned | 1596.1 | 85.3 | 165.2 | 74.5 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a1 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 8.4 | 0.57 | 37,405 | 844,570 | 40,128 | 42 | 0.038 | qwen3.8-flash-next-iq3_xxs | not-returned | 1493.0 | 84.0 | 73.9 | 79.3 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a2 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 9.1 | 0.62 | 46,333 | 1,115,204 | 46,746 | 44 | 0.047 | qwen3.8-flash-next-iq3_xxs | not-returned | 1472.2 | 91.3 | 84.7 | 85.5 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a3 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 1.3 | 0.09 | 18,787 | 113,335 | 5,646 | 10 | 0.007 | qwen3.8-flash-next-iq3_xxs | not-returned | 1674.3 | 86.8 | 237.9 | 71.5 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a4 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 2.5 | 0.17 | 24,767 | 195,506 | 10,735 | 12 | 0.012 | qwen3.8-flash-next-iq3_xxs | not-returned | 1670.3 | 82.4 | 167.7 | 72.7 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a5 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 8.7 | 0.59 | 57,675 | 1,338,475 | 44,671 | 41 | 0.051 | qwen3.8-flash-next-iq3_xxs | not-returned | 1545.2 | 93.0 | 110.6 | 85.7 |
| 27 claude-code strata-iq3_xxs high | strata-high-a6 |  | 是 | 1 | 是 | 0.837 | 0.837 | 0.837 | 0.000 | 0 | 9.6 | 0.64 | 64,469 | 1,455,000 | 44,010 | 29 | 0.054 | qwen3.8-flash-next-iq3_xxs | not-returned | 1616.3 | 83.5 | 112.3 | 76.7 |
| 27 claude-code strata-iq3_xxs high | strata-high-a7 |  | 是 | 2 | 是 | 0.685 | 0.685 | 0.728 | 0.058 | 6 | 9.4 | 0.63 | 69,763 | 1,325,846 | 46,902 | 30 | 0.054 | qwen3.8-flash-next-iq3_xxs | not-returned | 1621.9 | 91.2 | 123.4 | 82.9 |
| 27 claude-code strata-iq3_xxs high | strata-high-a8 |  | 是 | 3 | 是 | 0.690 | 0.690 | 0.690 | 0.000 | 0 | 8.0 | 0.54 | 50,305 | 860,760 | 38,288 | 29 | 0.039 | qwen3.8-flash-next-iq3_xxs | not-returned | 1555.8 | 86.2 | 104.5 | 79.5 |
| 27 claude-code strata-iq3_xxs high | strata-high-a9 |  | 是 | 4 | 是 | 0.697 | 0.697 | 0.774 | 0.100 | 14 | 10.1 | 0.68 | 50,631 | 1,131,422 | 48,126 | 28 | 0.048 | qwen3.8-flash-next-iq3_xxs | not-returned | 1389.3 | 85.3 | 83.2 | 79.1 |
| 27 claude-code strata-iq3_xxs high | strata-high-a10 |  | 是 | 5 | 是 | 0.682 | 0.682 | 0.756 | 0.098 | 11 | 8.9 | 0.60 | 51,925 | 1,035,202 | 42,151 | 37 | 0.044 | qwen3.8-flash-next-iq3_xxs | not-returned | 1514.6 | 85.1 | 96.8 | 78.6 |
| 27 claude-code strata-iq3_xxs high | strata-high-a11 |  | 是 | 6 | 是 | 0.700 | 0.700 | 0.729 | 0.041 | 2 | 6.5 | 0.43 | 49,182 | 817,765 | 30,770 | 21 | 0.035 | qwen3.8-flash-next-iq3_xxs | not-returned | 1569.8 | 87.9 | 126.7 | 79.3 |
| 27 claude-code strata-iq3_xxs high | strata-high-a12 |  | 是 | 7 | 是 | 0.727 | 0.727 | 0.727 | 0.000 | 0 | 8.6 | 0.58 | 51,472 | 1,149,684 | 40,946 | 24 | 0.045 | qwen3.8-flash-next-iq3_xxs | not-returned | 1453.7 | 86.6 | 99.7 | 79.3 |
| 27 claude-code strata-iq3_xxs high | strata-high-a13 |  | 是 | 8 | 是 | 0.566 | 0.566 | 0.629 | 0.100 | 20 | 8.0 | 0.53 | 47,985 | 1,461,479 | 38,392 | 38 | 0.049 | qwen3.8-flash-next-iq3_xxs | not-returned | 1441.4 | 87.9 | 100.4 | 80.3 |
| 27 claude-code strata-iq3_xxs high | strata-high-a14 |  | 是 | 9 | 是 | 0.628 | 0.628 | 0.698 | 0.100 | 12 | 8.5 | 0.57 | 68,585 | 1,044,340 | 41,937 | 28 | 0.047 | qwen3.8-flash-next-iq3_xxs | not-returned | 1705.9 | 90.7 | 134.7 | 82.3 |
| 27 claude-code strata-iq3_xxs high | strata-high-a15 |  | 是 | 10 | 是 | 0.824 | 0.824 | 0.830 | 0.008 | 1 | 8.2 | 0.55 | 76,913 | 963,695 | 40,373 | 26 | 0.046 | qwen3.8-flash-next-iq3_xxs | not-returned | 1842.9 | 91.0 | 156.5 | 82.1 |
| 27 claude-code strata-iq3_xxs high | strata-high-a1 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 11.3 | 0.75 | 59,222 | 921,311 | 57,012 | 50 | 0.050 | qwen3.8-flash-next-iq3_xxs | not-returned | 1749.8 | 89.3 | 87.6 | 84.3 |
| 27 claude-code strata-iq3_xxs high | strata-high-a2 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 1.9 | 0.13 | 18,643 | 92,503 | 8,690 | 8 | 0.008 | qwen3.8-flash-next-iq3_xxs | not-returned | 1696.4 | 85.9 | 162.4 | 75.7 |
| 27 claude-code strata-iq3_xxs high | strata-high-a3 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 8.9 | 0.60 | 40,100 | 670,438 | 46,559 | 38 | 0.039 | qwen3.8-flash-next-iq3_xxs | not-returned | 1690.8 | 91.4 | 74.7 | 86.8 |
| 27 claude-code strata-iq3_xxs high | strata-high-a4 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 7.1 | 0.47 | 41,195 | 679,438 | 35,773 | 45 | 0.034 | qwen3.8-flash-next-iq3_xxs | not-returned | 1486.5 | 91.4 | 97.1 | 84.3 |
| 27 claude-code strata-iq3_xxs high | strata-high-a5 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 10.6 | 0.71 | 55,247 | 820,190 | 51,369 | 43 | 0.046 | qwen3.8-flash-next-iq3_xxs | not-returned | 1668.3 | 85.9 | 87.0 | 80.9 |
| 28 codex gpt-6-luna xhigh | luna-xhigh-a1 |  | 是 | 1 | 是 | 0.707 | 0.707 | 0.707 | 0.000 | 0 | 4.7 | 0.49 | 100,731 | 1,182,208 | 31,853 | 17 | 只报 token | gpt-6-luna | default | 未知 | ≥112.9 | 356.8 | 112.8 |
| 28 codex gpt-6-luna xhigh | luna-xhigh-a2 |  | 是 | 2 | 是 | 0.587 | 0.587 | 0.587 | 0.000 | 0 | 3.9 | 0.40 | 77,940 | 597,248 | 26,429 | 12 | 只报 token | gpt-6-luna | default | 未知 | ≥114.3 | 335.9 | 113.9 |
| 28 codex gpt-6-luna xhigh | luna-xhigh-a3 |  | 是 | 3 | 是 | 0.591 | 0.591 | 0.591 | 0.000 | 0 | 4.9 | 0.52 | 85,496 | 794,112 | 30,780 | 14 | 只报 token | gpt-6-luna | default、not-returned | 未知 | ≥105.1 | 289.3 | 104.1 |
| 28 codex gpt-6-luna xhigh | luna-xhigh-a4 |  | 是 | 4 | 是 | 0.701 | 0.701 | 0.701 | 0.000 | 0 | 4.6 | 0.48 | 90,999 | 834,304 | 32,044 | 13 | 只报 token | gpt-6-luna | default | 未知 | ≥116.1 | 328.4 | 115.6 |
| 28 codex gpt-6-luna xhigh | luna-xhigh-a5 |  | 是 | 5 | 是 | 0.640 | 0.640 | 0.640 | 0.000 | 0 | 5.0 | 0.52 | 90,916 | 936,064 | 32,738 | 16 | 只报 token | gpt-6-luna | default、not-returned | 未知 | ≥111.0 | 305.7 | 110.1 |
| 28 codex gpt-6-luna xhigh | luna-xhigh-a6 |  | 是 | 6 | 是 | 0.588 | 0.588 | 0.598 | 0.017 | 1 | 5.1 | 0.54 | 82,296 | 810,368 | 32,336 | 13 | 只报 token | gpt-6-luna | default、not-returned | 未知 | ≥105.5 | 268.2 | 105.4 |
| 28 codex gpt-6-luna xhigh | luna-xhigh-a7 |  | 是 | 7 | 是 | 0.593 | 0.593 | 0.604 | 0.018 | 1 | 4.6 | 0.48 | 94,891 | 684,544 | 31,877 | 11 | 只报 token | gpt-6-luna | default | 未知 | ≥115.3 | 342.5 | 115.1 |
| 28 codex gpt-6-luna xhigh | luna-xhigh-a8 |  | 是 | 8 | 是 | 0.692 | 0.692 | 0.692 | 0.000 | 0 | 5.8 | 0.61 | 141,172 | 822,656 | 35,460 | 13 | 只报 token | gpt-6-luna | default、not-returned | 未知 | ≥102.1 | 403.9 | 101.5 |
| 29 codex gpt-6-luna max | luna-max-a1 |  | 是 | 1 | 是 | 0.713 | 0.713 | 0.713 | 0.000 | 0 | 6.0 | 0.56 | 124,453 | 1,113,728 | 34,162 | 18 | 只报 token | gpt-6-luna | default、not-returned | 未知 | ≥100.1 | 343.7 | 94.3 |
| 29 codex gpt-6-luna max | luna-max-a2 |  | 是 | 2 | 是 | 0.634 | 0.634 | 0.634 | 0.000 | 0 | 4.7 | 0.44 | 85,413 | 1,103,360 | 30,293 | 19 | 只报 token | gpt-6-luna | default | 未知 | ≥107.1 | 303.0 | 107.5 |
| 29 codex gpt-6-luna max | luna-max-a3 |  | 是 | 3 | 是 | 0.575 | 0.575 | 0.575 | 0.000 | 0 | 5.2 | 0.48 | 93,028 | 989,184 | 36,972 | 14 | 只报 token | gpt-6-luna | default | 未知 | ≥118.9 | 298.4 | 118.6 |
| 29 codex gpt-6-luna max | luna-max-a4 |  | 是 | 4 | 是 | 0.714 | 0.714 | 0.740 | 0.036 | 2 | 6.1 | 0.57 | 105,678 | 952,960 | 40,465 | 14 | 只报 token | gpt-6-luna | default、not-returned | 未知 | ≥120.2 | 287.4 | 110.1 |
| 29 codex gpt-6-luna max | luna-max-a5 |  | 是 | 5 | 是 | 0.592 | 0.592 | 0.592 | 0.000 | 0 | 5.2 | 0.49 | 96,297 | 751,616 | 37,380 | 12 | 只报 token | gpt-6-luna | default | 未知 | ≥119.8 | 308.1 | 119.6 |
| 29 codex gpt-6-luna max | luna-max-a6 |  | 是 | 6 | 是 | 0.645 | 0.645 | 0.645 | 0.000 | 0 | 6.0 | 0.56 | 108,404 | 1,194,368 | 40,306 | 17 | 只报 token | gpt-6-luna | default、not-returned | 未知 | ≥118.4 | 299.9 | 111.5 |
| 29 codex gpt-6-luna max | luna-max-a7 |  | 是 | 7 | 是 | 0.561 | 0.561 | 0.623 | 0.100 | 8 | 4.9 | 0.46 | 109,667 | 894,464 | 34,726 | 12 | 只报 token | gpt-6-luna | default | 未知 | ≥118.2 | 372.3 | 117.9 |
| 29 codex gpt-6-luna max | luna-max-a8 |  | 是 | 8 | 是 | 0.253 | 0.253 | 0.253 | 0.000 | 0 | 4.1 | 0.38 | 79,467 | 1,035,392 | 27,809 | 18 | 只报 token | gpt-6-luna | default | 未知 | ≥114.6 | 325.7 | 114.0 |

## commit-audit-v3

### 配置

| 配置 | 行 | 有效 | 选入 n | 已计分 | 无效 | 均值 ± SD | SE | 95% 区间 | 负分数 | 最小 | 中位数 | r8.3 均值 | rawScore | f | 修复 | 耗时（分钟） | 占时限 | 未缓存 | 缓存 | 输出 | token 来源 | 工具调用 | 费用（美元；DeepSeek 括号内为人民币 ¥） | 周额度 | 模型 ID | service tier |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 codex gpt-6.1-sol low | 主统计 | 5 | 5 | 5 | 0 | 0.868 ± 0.017 | 0.008 | 0.847–0.890 | 0 | 0.851 | 0.868 | 0.868 | 0.868 | 0.000 | 0 | 1.5 | 未知 | 65,511 | 303,846 | 5,929 | API usage (relay) | 6.6 | 只报 token |  | gpt-6.1-sol | default |
| 2 codex gpt-6.1-sol medium | 主统计 | 5 | 5 | 5 | 0 | 0.872 ± 0.007 | 0.003 | 0.863–0.880 | 0 | 0.865 | 0.872 | 0.872 | 0.872 | 0.000 | 0 | 2.0 | 未知 | 64,688 | 359,910 | 7,572 | API usage (relay) | 7.4 | 只报 token |  | gpt-6.1-sol | default |
| 3 codex gpt-6.1-sol high | 主统计 | 5 | 5 | 5 | 0 | 0.866 ± 0.016 | 0.007 | 0.846–0.886 | 0 | 0.837 | 0.873 | 0.866 | 0.866 | 0.000 | 0 | 2.9 | 未知 | 69,537 | 447,846 | 10,287 | API usage (relay) | 8.6 | 只报 token |  | gpt-6.1-sol | default |
| 4 codex gpt-6-luna low | 主统计 | 5 | 5 | 5 | 2 | -1.045 ± 0.370 | 0.165 | -1.504–-0.586 | 5 | -1.567 | -1.074 | 0.000 | -0.442 | 0.020 | 16 | 1.4 | 未知 | 58,620 | 660,326 | 8,449 | API usage (relay) | 12.4 | 只报 token |  | gpt-6-luna | default |
| 5 codex gpt-6-luna medium | 主统计 | 5 | 5 | 5 | 2 | -0.216 ± 0.480 | 0.215 | -0.811–0.380 | 3 | -0.861 | -0.228 | 0.090 | -0.042 | 0.000 | 0 | 2.4 | 未知 | 67,415 | 1,103,872 | 15,183 | API usage (relay) | 18.4 | 只报 token |  | gpt-6-luna | default |
| 6 codex gpt-6-luna high | 主统计 | 5 | 5 | 5 | 5 | 0.134 ± 0.628 | 0.281 | -0.646–0.914 | 1 | -0.932 | 0.360 | 0.320 | 0.241 | 0.008 | 0 | 3.9 | 未知 | 84,567 | 1,256,166 | 26,183 | API usage (relay) | 19.4 | 只报 token |  | gpt-6-luna | default |
| 7 codex deepseek-flash low | 主统计 | 5 | 5 | 5 | 0 | 0.707 ± 0.076 | 0.034 | 0.612–0.802 | 0 | 0.622 | 0.710 | 0.707 | 0.721 | 0.020 | 85 | 4.9 | 未知 | 61,255 | 2,262,195 | 60,415 | API usage (relay) | 61.6 | 0.261（¥1.741） |  | deepseek-flash | default |
| 8 codex deepseek-flash high | 主统计 | 8 | 8 | 8 | 0 | 0.645 ± 0.219 | 0.077 | 0.463–0.828 | 0 | 0.223 | 0.740 | 0.645 | 0.654 | 0.020 | 9 | 5.1 | 未知 | 60,030 | 2,211,392 | 65,934 | API usage (relay) | 64.0 | 0.442（¥2.944） |  | deepseek-flash | default |
| 8 codex deepseek-flash high | 一致性行（前 5） | 8 | 5 | 5 |  | 0.577 ± 0.258 | 0.115 | 0.257–0.897 | 0 | 0.223 | 0.734 | 0.577 | 0.592 | 0.032 | 9 | 5.1 | 未知 | 56,399 | 1,936,563 | 63,196 | API usage (relay) | 54.0 | 0.261（¥1.740） |  | deepseek-flash | default |
| 9 codex deepseek-flash max | 主统计 | 5 | 5 | 5 | 0 | 0.744 ± 0.188 | 0.084 | 0.512–0.977 | 0 | 0.416 | 0.830 | 0.744 | 0.744 | 0.000 | 0 | 7.5 | 未知 | 70,953 | 3,158,170 | 83,300 | API usage (relay) | 72.0 | 0.350（¥2.337） |  | deepseek-flash | default |
| 10 codex strata-iq3_xxs low | 主统计 | 10 | 10 | 10 | 2 | 0.510 ± 0.097 | 0.031 | 0.441–0.580 | 0 | 0.324 | 0.531 | 0.510 | 0.515 | 0.010 | 93 | 14.8 | 未知 | 81,835 | 3,546,426 | 71,668 | engine log | 44.0 | 1.027 |  | 未知 | 未知 |
| 10 codex strata-iq3_xxs low | 一致性行（前 5） | 10 | 5 | 5 |  | 0.545 ± 0.101 | 0.045 | 0.419–0.670 | 0 | 0.385 | 0.557 | 0.545 | 0.553 | 0.020 | 93 | 15.5 | 未知 | 95,497 | 3,526,212 | 74,886 | engine log | 41.8 | 0.530 |  | 未知 | 未知 |
| 11 codex strata-iq3_xxs medium | 主统计 | 10 | 10 | 10 | 2 | 0.611 ± 0.125 | 0.040 | 0.521–0.701 | 0 | 0.428 | 0.628 | 0.611 | 0.611 | 0.000 | 0 | 15.7 | 未知 | 98,846 | 2,743,656 | 76,969 | engine log | 35.9 | 0.949 |  | 未知 | 未知 |
| 11 codex strata-iq3_xxs medium | 一致性行（前 5） | 10 | 5 | 5 |  | 0.657 ± 0.150 | 0.067 | 0.471–0.842 | 0 | 0.428 | 0.661 | 0.657 | 0.657 | 0.000 | 0 | 17.8 | 未知 | 133,840 | 3,295,804 | 86,406 | engine log | 41.2 | 0.567 |  | 未知 | 未知 |
| 12 codex strata-iq3_xxs high | 主统计 | 10 | 10 | 10 | 0 | 0.664 ± 0.087 | 0.028 | 0.602–0.726 | 0 | 0.554 | 0.661 | 0.664 | 0.664 | 0.000 | 0 | 17.7 | 未知 | 123,463 | 3,058,431 | 86,249 | engine log | 44.7 | 1.080 |  | 未知 | 未知 |
| 12 codex strata-iq3_xxs high | 一致性行（前 5） | 10 | 5 | 5 |  | 0.661 ± 0.089 | 0.040 | 0.551–0.771 | 0 | 0.554 | 0.664 | 0.661 | 0.661 | 0.000 | 0 | 19.9 | 未知 | 176,168 | 3,281,530 | 96,995 | engine log | 51.2 | 0.623 |  | 未知 | 未知 |
| 13 claude-code opus low | 主统计 | 5 | 5 | 5 | 0 | 0.830 ± 0.027 | 0.012 | 0.797–0.863 | 0 | 0.799 | 0.823 | 0.830 | 0.846 | 0.019 | 0 | 2.9 | 未知 | 58,744 | 211,738 | 13,747 | Claude Code stream result usage | 5.4 | 3.936 | 0.34% | claude-opus-5-5 | standard |
| 14 claude-code opus medium | 主统计 | 5 | 5 | 5 | 0 | 0.856 ± 0.019 | 0.008 | 0.832–0.879 | 0 | 0.839 | 0.851 | 0.856 | 0.856 | 0.000 | 0 | 4.4 | 未知 | 71,744 | 381,204 | 20,306 | Claude Code stream result usage | 8.6 | 5.281 | 0.45% | claude-opus-5-5 | standard |
| 15 claude-code opus high | 主统计 | 5 | 5 | 5 | 0 | 0.876 ± 0.018 | 0.008 | 0.853–0.898 | 0 | 0.847 | 0.876 | 0.876 | 0.883 | 0.009 | 0 | 7.3 | 未知 | 87,707 | 658,386 | 33,566 | Claude Code stream result usage | 12.0 | 7.523 | 0.65% | claude-opus-5-5 | standard |
| 16 claude-code sonnet low | 主统计 | 5 | 5 | 5 | 0 | 0.814 ± 0.012 | 0.005 | 0.799–0.828 | 0 | 0.797 | 0.811 | 0.814 | 0.839 | 0.031 | 0 | 3.4 | 未知 | 59,161 | 280,743 | 15,905 | Claude Code stream result usage | 7.6 | 2.119 | 0.18% | claude-sonnet-5-5 | standard |
| 17 claude-code sonnet medium | 主统计 | 5 | 5 | 5 | 0 | 0.831 ± 0.058 | 0.026 | 0.759–0.904 | 0 | 0.733 | 0.851 | 0.831 | 0.849 | 0.021 | 0 | 3.6 | 未知 | 63,856 | 291,961 | 19,228 | Claude Code stream result usage | 7.8 | 2.384 | 0.21% | claude-sonnet-5-5 | standard |
| 18 claude-code sonnet high | 主统计 | 5 | 5 | 5 | 0 | 0.851 ± 0.010 | 0.004 | 0.839–0.863 | 0 | 0.836 | 0.852 | 0.851 | 0.872 | 0.024 | 0 | 4.8 | 未知 | 76,064 | 423,798 | 30,246 | Claude Code stream result usage | 10.2 | 3.245 | 0.28% | claude-sonnet-5-5 | standard |
| 19 claude-code haiku low | 主统计 | 5 | 5 | 5 | 0 | 0.863 ± 0.018 | 0.008 | 0.840–0.886 | 0 | 0.833 | 0.874 | 0.863 | 0.863 | 0.000 | 0 | 5.7 | 未知 | 112,977 | 605,827 | 65,653 | Claude Code stream result usage | 11.0 | 0.701 | 0.06% | claude-haiku-5-5 | standard |
| 20 claude-code haiku medium | 主统计 | 5 | 5 | 5 | 0 | 0.874 ± 0.017 | 0.008 | 0.853–0.896 | 0 | 0.850 | 0.875 | 0.874 | 0.879 | 0.005 | 0 | 6.7 | 未知 | 123,365 | 588,370 | 75,697 | Claude Code stream result usage | 13.8 | 0.721 | 0.06% | claude-haiku-5-5 | standard |
| 21 claude-code haiku high | 主统计 | 5 | 5 | 5 | 0 | 0.862 ± 0.023 | 0.010 | 0.833–0.891 | 0 | 0.824 | 0.863 | 0.862 | 0.862 | 0.000 | 0 | 9.3 | 未知 | 157,462 | 1,201,950 | 103,424 | Claude Code stream result usage | 18.4 | 1.483 | 0.13% | claude-haiku-5-5 | standard |
| 22 claude-code deepseek-flash low | 主统计 | 5 | 5 | 5 | 0 | 0.704 ± 0.075 | 0.033 | 0.611–0.797 | 0 | 0.631 | 0.709 | 0.704 | 0.704 | 0.000 | 0 | 8.1 | 未知 | 44,289 | 1,055,667 | 62,161 | Claude Code stream result usage | 26.8 | 0.236（¥1.570） |  | deepseek-flash | standard |
| 23 claude-code deepseek-flash high | 主统计 | 8 | 8 | 8 | 0 | 0.742 ± 0.086 | 0.030 | 0.670–0.814 | 0 | 0.629 | 0.732 | 0.742 | 0.742 | 0.000 | 0 | 11.3 | 未知 | 53,452 | 1,795,920 | 87,010 | Claude Code stream result usage | 37.1 | 0.525（¥3.499） |  | deepseek-flash | standard |
| 23 claude-code deepseek-flash high | 一致性行（前 5） | 8 | 5 | 5 |  | 0.739 ± 0.082 | 0.037 | 0.637–0.841 | 0 | 0.629 | 0.731 | 0.739 | 0.739 | 0.000 | 0 | 12.3 | 未知 | 52,706 | 1,756,237 | 92,185 | Claude Code stream result usage | 37.8 | 0.342（¥2.283） |  | deepseek-flash | standard |
| 24 claude-code deepseek-flash max | 主统计 | 5 | 5 | 5 | 0 | 0.817 ± 0.059 | 0.027 | 0.744–0.891 | 0 | 0.735 | 0.843 | 0.817 | 0.817 | 0.000 | 0 | 15.9 | 未知 | 72,637 | 2,498,355 | 134,932 | Claude Code stream result usage | 65.2 | 0.497（¥3.312） |  | deepseek-flash | standard |
| 25 claude-code strata-iq3_xxs low | 主统计 | 10 | 10 | 10 | 0 | 0.599 ± 0.148 | 0.047 | 0.493–0.704 | 0 | 0.254 | 0.616 | 0.599 | 0.600 | 0.003 | 0 | 15.6 | 未知 | 73,390 | 4,478,257 | 75,995 | engine log | 64.2 | 1.184 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 25 claude-code strata-iq3_xxs low | 一致性行（前 5） | 10 | 5 | 5 |  | 0.571 ± 0.212 | 0.095 | 0.308–0.835 | 0 | 0.254 | 0.608 | 0.571 | 0.574 | 0.006 | 0 | 16.8 | 未知 | 79,056 | 4,660,554 | 81,461 | engine log | 62.6 | 0.624 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 26 claude-code strata-iq3_xxs medium | 主统计 | 10 | 10 | 10 | 0 | 0.588 ± 0.131 | 0.041 | 0.495–0.682 | 0 | 0.391 | 0.583 | 0.588 | 0.597 | 0.012 | 0 | 16.8 | 未知 | 72,853 | 2,484,728 | 78,910 | engine log | 44.9 | 0.878 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 26 claude-code strata-iq3_xxs medium | 一致性行（前 5） | 10 | 5 | 5 |  | 0.526 ± 0.080 | 0.036 | 0.427–0.625 | 0 | 0.394 | 0.555 | 0.526 | 0.532 | 0.011 | 0 | 16.1 | 未知 | 71,517 | 2,185,275 | 71,277 | engine log | 41.8 | 0.396 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 27 claude-code strata-iq3_xxs high | 主统计 | 10 | 10 | 10 | 0 | 0.590 ± 0.144 | 0.045 | 0.487–0.693 | 0 | 0.441 | 0.565 | 0.590 | 0.596 | 0.010 | 81 | 15.0 | 未知 | 64,347 | 2,191,137 | 75,569 | engine log | 39.4 | 0.802 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 27 claude-code strata-iq3_xxs high | 一致性行（前 5） | 10 | 5 | 5 |  | 0.601 ± 0.149 | 0.066 | 0.417–0.786 | 0 | 0.441 | 0.568 | 0.601 | 0.601 | 0.000 | 0 | 13.7 | 未知 | 59,736 | 2,324,608 | 71,029 | engine log | 43.6 | 0.398 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 28 codex gpt-6-luna xhigh | 第三阶段补充（不比较） | 6 | 6 | 6 |  | 0.672 ± 0.419 | 0.171 | 0.232–1.111 | 1 | -0.182 | 0.842 | 0.702 | 0.690 | 0.000 | 0 | 16.7 | 未知 | 195,388 | 11,877,120 | 66,394 | API usage (relay log sum, 762 requests; lower bound: 1 request(s) without usage)、API usage (relay) | 19.3 | 只报 token |  | gpt-6-luna | default、not-returned |
| 29 codex gpt-6-luna max | 第三阶段补充（不比较） | 5 | 5 | 5 |  | 0.795 ± 0.097 | 0.043 | 0.675–0.915 | 0 | 0.631 | 0.827 | 0.795 | 0.809 | 0.020 | 4 | 7.3 | 未知 | 122,303 | 993,971 | 57,419 | API usage (relay) | 13.6 | 只报 token |  | gpt-6-luna | default |

### 预登记比较

r8.3 列：同一批实例按 r8.3（截到 0、整体扣减相乘）计分的对照（plan §14.1）。

| 组 | 前者 | 后者 | n | 差值 | SE | t | 自由度 | p | Holm p | 结论 | r8.3 差值 | r8.3 Holm p | r8.3 结论 | 结论改变 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| codex | 10 codex strata-iq3_xxs low | 1 codex gpt-6.1-sol low | 10 / 5 | -0.358 | 0.032 | -11.26 | 10.1 | 0.0000 | 0.0000 | 低于 | -0.358 | 0.0000 | 低于 | 否 |
| codex | 10 codex strata-iq3_xxs low | 4 codex gpt-6-luna low | 10 / 5 | 1.556 | 0.168 | 9.25 | 4.3 | 0.0005 | 0.0082 | 高于 | 0.510 | 0.0000 | 高于 | 否 |
| codex | 10 codex strata-iq3_xxs low | 7 codex deepseek-flash low | 10 / 5 | -0.196 | 0.046 | -4.27 | 10.2 | 0.0016 | 0.0189 | 低于 | -0.196 | 0.0174 | 低于 | 否 |
| codex | 11 codex strata-iq3_xxs medium | 2 codex gpt-6.1-sol medium | 10 / 5 | -0.261 | 0.040 | -6.55 | 9.1 | 0.0001 | 0.0021 | 低于 | -0.261 | 0.0020 | 低于 | 否 |
| codex | 11 codex strata-iq3_xxs medium | 5 codex gpt-6-luna medium | 10 / 5 | 0.827 | 0.218 | 3.79 | 4.3 | 0.0171 | 0.1710 | 未分出 | 0.521 | 0.0134 | 高于 | 是 |
| codex | 12 codex strata-iq3_xxs high | 3 codex gpt-6.1-sol high | 10 / 5 | -0.201 | 0.028 | -7.08 | 10.2 | 0.0000 | 0.0007 | 低于 | -0.201 | 0.0007 | 低于 | 否 |
| codex | 12 codex strata-iq3_xxs high | 6 codex gpt-6-luna high | 10 / 5 | 0.530 | 0.282 | 1.88 | 4.1 | 0.1322 | 1.0000 | 未分出 | 0.344 | 0.3898 | 未分出 | 否 |
| codex | 12 codex strata-iq3_xxs high | 8 codex deepseek-flash high | 10 / 8 | 0.019 | 0.082 | 0.23 | 8.8 | 0.8243 | 1.0000 | 未分出 | 0.019 | 1.0000 | 未分出 | 否 |
| claude-code | 25 claude-code strata-iq3_xxs low | 13 claude-code opus low | 10 / 5 | -0.232 | 0.048 | -4.79 | 10.1 | 0.0007 | 0.0100 | 低于 | -0.232 | 0.0100 | 低于 | 否 |
| claude-code | 25 claude-code strata-iq3_xxs low | 16 claude-code sonnet low | 10 / 5 | -0.215 | 0.047 | -4.57 | 9.2 | 0.0013 | 0.0165 | 低于 | -0.215 | 0.0152 | 低于 | 否 |
| claude-code | 25 claude-code strata-iq3_xxs low | 19 claude-code haiku low | 10 / 5 | -0.265 | 0.048 | -5.56 | 9.5 | 0.0003 | 0.0046 | 低于 | -0.265 | 0.0044 | 低于 | 否 |
| claude-code | 25 claude-code strata-iq3_xxs low | 22 claude-code deepseek-flash low | 10 / 5 | -0.106 | 0.058 | -1.84 | 12.9 | 0.0895 | 0.8052 | 未分出 | -0.106 | 0.7158 | 未分出 | 否 |
| claude-code | 26 claude-code strata-iq3_xxs medium | 14 claude-code opus medium | 10 / 5 | -0.267 | 0.042 | -6.34 | 9.7 | 0.0001 | 0.0021 | 低于 | -0.267 | 0.0020 | 低于 | 否 |
| claude-code | 26 claude-code strata-iq3_xxs medium | 17 claude-code sonnet medium | 10 / 5 | -0.243 | 0.049 | -4.97 | 13.0 | 0.0003 | 0.0046 | 低于 | -0.243 | 0.0044 | 低于 | 否 |
| claude-code | 26 claude-code strata-iq3_xxs medium | 20 claude-code haiku medium | 10 / 5 | -0.286 | 0.042 | -6.80 | 9.6 | 0.0001 | 0.0013 | 低于 | -0.286 | 0.0013 | 低于 | 否 |
| claude-code | 27 claude-code strata-iq3_xxs high | 15 claude-code opus high | 10 / 5 | -0.285 | 0.046 | -6.17 | 9.6 | 0.0001 | 0.0025 | 低于 | -0.285 | 0.0024 | 低于 | 否 |
| claude-code | 27 claude-code strata-iq3_xxs high | 18 claude-code sonnet high | 10 / 5 | -0.261 | 0.046 | -5.71 | 9.2 | 0.0003 | 0.0046 | 低于 | -0.261 | 0.0044 | 低于 | 否 |
| claude-code | 27 claude-code strata-iq3_xxs high | 21 claude-code haiku high | 10 / 5 | -0.271 | 0.047 | -5.82 | 9.9 | 0.0002 | 0.0033 | 低于 | -0.271 | 0.0032 | 低于 | 否 |
| claude-code | 27 claude-code strata-iq3_xxs high | 23 claude-code deepseek-flash high | 10 / 8 | -0.152 | 0.055 | -2.77 | 15.0 | 0.0143 | 0.1576 | 未分出 | -0.152 | 0.1432 | 未分出 | 否 |
| harness | 10 codex strata-iq3_xxs low | 25 claude-code strata-iq3_xxs low | 10 / 10 | -0.088 | 0.056 | -1.57 | 15.6 | 0.1360 | 1.0000 | 未分出 | -0.088 | 0.9522 | 未分出 | 否 |
| harness | 11 codex strata-iq3_xxs medium | 26 claude-code strata-iq3_xxs medium | 10 / 10 | 0.023 | 0.057 | 0.39 | 18.0 | 0.6987 | 1.0000 | 未分出 | 0.023 | 1.0000 | 未分出 | 否 |
| harness | 12 codex strata-iq3_xxs high | 27 claude-code strata-iq3_xxs high | 10 / 10 | 0.074 | 0.053 | 1.39 | 14.8 | 0.1847 | 1.0000 | 未分出 | 0.074 | 1.0000 | 未分出 | 否 |
| harness | 7 codex deepseek-flash low | 22 claude-code deepseek-flash low | 5 / 5 | 0.003 | 0.048 | 0.05 | 8.0 | 0.9580 | 1.0000 | 未分出 | 0.003 | 1.0000 | 未分出 | 否 |
| harness | 8 codex deepseek-flash high | 23 claude-code deepseek-flash high | 8 / 8 | -0.096 | 0.083 | -1.16 | 9.1 | 0.2756 | 1.0000 | 未分出 | -0.096 | 1.0000 | 未分出 | 否 |
| harness | 9 codex deepseek-flash max | 24 claude-code deepseek-flash max | 5 / 5 | -0.073 | 0.088 | -0.83 | 4.8 | 0.4460 | 1.0000 | 未分出 | -0.073 | 1.0000 | 未分出 | 否 |

### 逐实例

速度：引擎输入、引擎输出是模型直接速度，任务平均输入、输出是用户感知速度（未缓存输入、输出 ÷ 工作秒数）。API 模型分不出输入处理时间，引擎输入记未知；引擎输出按 API 请求时间算，含首 token 延迟和输入处理，是下限（≥）。

速度汇总口径（用户 2026-10-22）：多个实例的速度（summary.json 各行的 speeds_mean）是总 token ÷ 总耗时（各实例 speed_parts 的分子之和 ÷ 分母之和，speed_totals 给出两者），不是各实例速度的算术平均；任一实例该项未知，汇总即未知；任一实例该项是下限，汇总也是下限。Codex 上的 API 模型（gpt-6.1-sol、gpt-6-luna、DeepSeek）的引擎输出按 relay 日志的 output token ÷ 请求秒数计算，v1 的记录没有保存请求秒数，原始 relay 日志已删除，所以这一项按用户 10-22 的选择近似汇总：分子取实例的输出 token（同样来自 relay usage），分母取 输出 token ÷ 逐实例引擎输出速度 反推的请求秒数；汇总标为近似（speeds_approximate，表中写"≥≈"），仍是下限。

| 配置 | 实例 | 补充 | 有效 | 序 | 主统计 | 分数 | r8.3 分数 | rawScore | f | 修复 | 耗时（分钟） | 占时限 | 未缓存 | 缓存 | 输出 | 工具调用 | 费用（美元；DeepSeek 括号内为人民币 ¥） | 模型 ID | service tier | 引擎输入 tok/s | 引擎输出 tok/s | 任务平均输入 tok/s | 任务平均输出 tok/s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 codex gpt-6.1-sol low | sol-low-a1 |  | 是 | 1 | 是 | 0.894 | 0.894 | 0.894 | 0.000 | 0 | 1.8 | 未知 | 71,028 | 322,560 | 7,755 | 7 | 只报 token | gpt-6.1-sol | default | 未知 | ≥70.7 | 643.4 | 70.2 |
| 1 codex gpt-6.1-sol low | sol-low-a2 |  | 是 | 2 | 是 | 0.853 | 0.853 | 0.853 | 0.000 | 0 | 2.1 | 未知 | 72,377 | 394,624 | 8,145 | 8 | 只报 token | gpt-6.1-sol | default | 未知 | ≥64.3 | 563.4 | 63.4 |
| 1 codex gpt-6.1-sol low | sol-low-a3 |  | 是 | 3 | 是 | 0.868 | 0.868 | 0.868 | 0.000 | 0 | 1.4 | 未知 | 59,568 | 265,344 | 5,128 | 6 | 只报 token | gpt-6.1-sol | default | 未知 | ≥62.4 | 714.9 | 61.5 |
| 1 codex gpt-6.1-sol low | sol-low-a4 |  | 是 | 4 | 是 | 0.875 | 0.875 | 0.875 | 0.000 | 0 | 1.2 | 未知 | 55,663 | 264,064 | 4,478 | 6 | 只报 token | gpt-6.1-sol | default | 未知 | ≥62.8 | 770.8 | 62.0 |
| 1 codex gpt-6.1-sol low | sol-low-a5 |  | 是 | 5 | 是 | 0.851 | 0.851 | 0.851 | 0.000 | 0 | 1.1 | 未知 | 68,918 | 272,640 | 4,141 | 6 | 只报 token | gpt-6.1-sol | default | 未知 | ≥61.3 | 1014.4 | 60.9 |
| 2 codex gpt-6.1-sol medium | sol-medium-a1 |  | 是 | 1 | 是 | 0.872 | 0.872 | 0.872 | 0.000 | 0 | 1.5 | 未知 | 56,244 | 309,760 | 5,355 | 7 | 只报 token | gpt-6.1-sol | default | 未知 | ≥59.5 | 622.7 | 59.3 |
| 2 codex gpt-6.1-sol medium | sol-medium-a2 |  | 是 | 2 | 是 | 0.865 | 0.865 | 0.865 | 0.000 | 0 | 2.3 | 未知 | 69,877 | 492,928 | 8,348 | 9 | 只报 token | gpt-6.1-sol | default | 未知 | ≥60.1 | 507.3 | 60.6 |
| 2 codex gpt-6.1-sol medium | sol-medium-a3 |  | 是 | 3 | 是 | 0.866 | 0.866 | 0.866 | 0.000 | 0 | 2.2 | 未知 | 70,919 | 327,552 | 9,217 | 7 | 只报 token | gpt-6.1-sol | default | 未知 | ≥68.7 | 528.0 | 68.6 |
| 2 codex gpt-6.1-sol medium | sol-medium-a4 |  | 是 | 4 | 是 | 0.873 | 0.873 | 0.873 | 0.000 | 0 | 1.5 | 未知 | 61,300 | 269,312 | 5,549 | 6 | 只报 token | gpt-6.1-sol | default | 未知 | ≥63.8 | 700.6 | 63.4 |
| 2 codex gpt-6.1-sol medium | sol-medium-a5 |  | 是 | 5 | 是 | 0.882 | 0.882 | 0.882 | 0.000 | 0 | 2.3 | 未知 | 65,100 | 400,000 | 9,389 | 8 | 只报 token | gpt-6.1-sol | default | 未知 | ≥67.5 | 465.8 | 67.2 |
| 3 codex gpt-6.1-sol high | sol-high-a1 |  | 是 | 1 | 是 | 0.873 | 0.873 | 0.873 | 0.000 | 0 | 2.5 | 未知 | 66,500 | 414,080 | 9,030 | 8 | 只报 token | gpt-6.1-sol | default | 未知 | ≥59.9 | 439.4 | 59.7 |
| 3 codex gpt-6.1-sol high | sol-high-a2 |  | 是 | 2 | 是 | 0.873 | 0.873 | 0.873 | 0.000 | 0 | 2.5 | 未知 | 64,385 | 412,032 | 8,906 | 8 | 只报 token | gpt-6.1-sol | default | 未知 | ≥59.0 | 425.6 | 58.9 |
| 3 codex gpt-6.1-sol high | sol-high-a3 |  | 是 | 3 | 是 | 0.871 | 0.871 | 0.871 | 0.000 | 0 | 4.0 | 未知 | 73,867 | 620,032 | 13,837 | 11 | 只报 token | gpt-6.1-sol | default | 未知 | ≥58.1 | 308.8 | 57.8 |
| 3 codex gpt-6.1-sol high | sol-high-a4 |  | 是 | 4 | 是 | 0.874 | 0.874 | 0.874 | 0.000 | 0 | 2.2 | 未知 | 74,956 | 338,816 | 7,853 | 7 | 只报 token | gpt-6.1-sol | default | 未知 | ≥59.9 | 571.8 | 59.9 |
| 3 codex gpt-6.1-sol high | sol-high-a5 |  | 是 | 5 | 是 | 0.837 | 0.837 | 0.837 | 0.000 | 0 | 3.2 | 未知 | 67,975 | 454,272 | 11,810 | 9 | 只报 token | gpt-6.1-sol | default | 未知 | ≥61.3 | 352.1 | 61.2 |
| 4 codex gpt-6-luna low | luna-low-a1 |  | 是 | 1 | 是 | -1.155 | 0.000 | -0.498 | 0.000 | 0 | 1.0 | 未知 | 66,953 | 566,272 | 5,761 | 10 | 只报 token | gpt-6-luna | default | 未知 | ≥97.7 | 1133.6 | 97.5 |
| 4 codex gpt-6-luna low | luna-low-a3 |  | 是 | 2 | 是 | -0.568 | 0.000 | -0.245 | 0.000 | 0 | 1.8 | 未知 | 62,586 | 555,392 | 12,517 | 11 | 只报 token | gpt-6-luna | default | 未知 | ≥115.4 | 576.5 | 115.3 |
| 4 codex gpt-6-luna low | luna-low-a5 |  | 是 | 3 | 是 | -1.567 | 0.000 | -0.676 | 0.000 | 0 | 1.2 | 未知 | 48,254 | 709,760 | 7,462 | 14 | 只报 token | gpt-6-luna | default | 未知 | ≥104.3 | 650.5 | 100.6 |
| 4 codex gpt-6-luna low | luna-low-a6 |  | 是 | 4 | 是 | -0.862 | 0.000 | -0.371 | 0.000 | 0 | 1.6 | 未知 | 59,196 | 909,440 | 8,908 | 15 | 只报 token | gpt-6-luna | default | 未知 | ≥91.7 | 613.6 | 92.3 |
| 4 codex gpt-6-luna low | luna-low-a7 |  | 是 | 5 | 是 | -1.074 | 0.000 | -0.421 | 0.100 | 16 | 1.4 | 未知 | 56,110 | 560,768 | 7,595 | 12 | 只报 token | gpt-6-luna | default | 未知 | ≥94.3 | 689.0 | 93.3 |
| 4 codex gpt-6-luna low | luna-low-a2 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 只报 token | 未知 | 未知 | 未知 | ≥74.6 | 未知 | 未知 |
| 4 codex gpt-6-luna low | luna-low-a4 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 只报 token | 未知 | 未知 | 未知 | ≥57.0 | 未知 | 未知 |
| 5 codex gpt-6-luna medium | luna-medium-a1 |  | 是 | 1 | 是 | 0.046 | 0.046 | 0.046 | 0.000 | 0 | 2.6 | 未知 | 68,580 | 1,166,080 | 17,387 | 21 | 只报 token | gpt-6-luna | default | 未知 | ≥111.4 | 437.3 | 110.9 |
| 5 codex gpt-6-luna medium | luna-medium-a2 |  | 是 | 2 | 是 | -0.228 | 0.000 | -0.098 | 0.000 | 0 | 1.3 | 未知 | 59,418 | 560,768 | 7,040 | 11 | 只报 token | gpt-6-luna | default | 未知 | ≥92.9 | 778.4 | 92.2 |
| 5 codex gpt-6-luna medium | luna-medium-a3 |  | 是 | 3 | 是 | 0.406 | 0.406 | 0.406 | 0.000 | 0 | 4.0 | 未知 | 90,773 | 2,125,568 | 25,952 | 29 | 只报 token | gpt-6-luna | default | 未知 | ≥108.4 | 379.5 | 108.5 |
| 5 codex gpt-6-luna medium | luna-medium-a6 |  | 是 | 4 | 是 | -0.441 | 0.000 | -0.190 | 0.000 | 0 | 1.9 | 未知 | 53,905 | 740,608 | 10,839 | 14 | 只报 token | gpt-6-luna | default | 未知 | ≥95.8 | 474.9 | 95.5 |
| 5 codex gpt-6-luna medium | luna-medium-a7 |  | 是 | 5 | 是 | -0.861 | 0.000 | -0.371 | 0.000 | 0 | 2.3 | 未知 | 64,401 | 926,336 | 14,695 | 17 | 只报 token | gpt-6-luna | default | 未知 | ≥108.5 | 473.2 | 108.0 |
| 5 codex gpt-6-luna medium | luna-medium-a4 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 2.7 | 未知 | 69,509 | 1,081,344 | 13,197 | 19 | 只报 token | gpt-6-luna | default、not-returned | 未知 | ≥97.3 | 426.7 | 81.0 |
| 5 codex gpt-6-luna medium | luna-medium-a5 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 只报 token | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 |
| 6 codex gpt-6-luna high | luna-high-a4 |  | 是 | 1 | 是 | 0.610 | 0.610 | 0.610 | 0.000 | 0 | 6.2 | 未知 | 117,796 | 2,824,960 | 42,927 | 34 | 只报 token | gpt-6-luna | default | 未知 | ≥115.5 | 314.9 | 114.7 |
| 6 codex gpt-6-luna high | luna-high-a5 |  | 是 | 2 | 是 | -0.932 | 0.000 | -0.402 | 0.000 | 0 | 2.1 | 未知 | 71,282 | 678,016 | 15,008 | 13 | 只报 token | gpt-6-luna | default | 未知 | ≥116.9 | 553.1 | 116.5 |
| 6 codex gpt-6-luna high | luna-high-a7 |  | 是 | 3 | 是 | 0.360 | 0.360 | 0.360 | 0.000 | 0 | 2.5 | 未知 | 62,025 | 765,696 | 16,835 | 15 | 只报 token | gpt-6-luna | default | 未知 | ≥111.2 | 407.0 | 110.5 |
| 6 codex gpt-6-luna high | luna-high-a9 |  | 是 | 4 | 是 | 0.537 | 0.537 | 0.537 | 0.000 | 0 | 4.7 | 未知 | 85,855 | 982,400 | 32,623 | 18 | 只报 token | gpt-6-luna | default | 未知 | ≥115.9 | 304.2 | 115.6 |
| 6 codex gpt-6-luna high | luna-high-a10 |  | 是 | 5 | 是 | 0.096 | 0.096 | 0.100 | 0.038 | 0 | 3.9 | 未知 | 85,876 | 1,029,760 | 23,521 | 17 | 只报 token | gpt-6-luna | default | 未知 | ≥101.4 | 366.8 | 100.5 |
| 6 codex gpt-6-luna high | luna-high-a1 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 只报 token | 未知 | 未知 | 未知 | ≥93.6 | 未知 | 未知 |
| 6 codex gpt-6-luna high | luna-high-a2 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 只报 token | 未知 | 未知 | 未知 | ≥102.6 | 未知 | 未知 |
| 6 codex gpt-6-luna high | luna-high-a3 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 只报 token | 未知 | 未知 | 未知 | ≥80.5 | 未知 | 未知 |
| 6 codex gpt-6-luna high | luna-high-a6 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 5.0 | 未知 | 93,170 | 1,085,568 | 31,328 | 17 | 只报 token | gpt-6-luna | default、not-returned | 未知 | ≥116.8 | 312.1 | 104.9 |
| 6 codex gpt-6-luna high | luna-high-a8 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 只报 token | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 |
| 7 codex deepseek-flash low | codex-low-a1 |  | 是 | 1 | 是 | 0.759 | 0.759 | 0.759 | 0.000 | 0 | 7.0 | 未知 | 59,569 | 3,637,248 | 78,575 | 76 | 0.067（¥0.447） | deepseek-flash | default | 未知 | ≥188.7 | 142.2 | 187.6 |
| 7 codex deepseek-flash low | codex-low-a2 |  | 是 | 2 | 是 | 0.710 | 0.710 | 0.710 | 0.000 | 0 | 4.7 | 未知 | 62,451 | 2,041,088 | 58,783 | 58 | 0.051（¥0.338） | deepseek-flash | default | 未知 | ≥208.6 | 219.8 | 206.9 |
| 7 codex deepseek-flash low | codex-low-a3 |  | 是 | 3 | 是 | 0.622 | 0.622 | 0.622 | 0.000 | 0 | 4.1 | 未知 | 60,352 | 2,099,072 | 50,019 | 48 | 0.045（¥0.302） | deepseek-flash | default | 未知 | ≥207.9 | 248.3 | 205.8 |
| 7 codex deepseek-flash low | codex-low-a4 |  | 是 | 4 | 是 | 0.641 | 0.641 | 0.712 | 0.100 | 85 | 3.8 | 未知 | 62,793 | 1,402,368 | 51,693 | 54 | 0.045（¥0.298） | deepseek-flash | default | 未知 | ≥230.5 | 277.5 | 228.4 |
| 7 codex deepseek-flash low | codex-low-a5 |  | 是 | 5 | 是 | 0.802 | 0.802 | 0.802 | 0.000 | 0 | 4.9 | 未知 | 61,111 | 2,131,200 | 63,003 | 72 | 0.053（¥0.356） | deepseek-flash | default | 未知 | ≥215.0 | 206.7 | 213.2 |
| 8 codex deepseek-flash high | codex-medium-a1 |  | 是 | 1 | 是 | 0.223 | 0.223 | 0.248 | 0.100 | 7 | 6.6 | 未知 | 53,313 | 2,731,008 | 77,931 | 66 | 0.063（¥0.420） | deepseek-flash | default | 未知 | ≥197.5 | 134.3 | 196.3 |
| 8 codex deepseek-flash high | codex-high-a1 |  | 是 | 2 | 是 | 0.384 | 0.384 | 0.384 | 0.000 | 0 | 4.2 | 未知 | 46,124 | 1,277,056 | 49,581 | 41 | 0.040（¥0.270） | deepseek-flash | default | 未知 | ≥197.2 | 182.6 | 196.2 |
| 8 codex deepseek-flash high | codex-high-a2 |  | 是 | 3 | 是 | 0.800 | 0.800 | 0.800 | 0.000 | 0 | 4.5 | 未知 | 56,662 | 1,691,904 | 58,375 | 43 | 0.049（¥0.324） | deepseek-flash | default | 未知 | ≥215.2 | 207.9 | 214.2 |
| 8 codex deepseek-flash high | codex-medium-a2 |  | 是 | 4 | 是 | 0.745 | 0.745 | 0.745 | 0.000 | 0 | 5.4 | 未知 | 72,245 | 2,273,024 | 67,161 | 44 | 0.058（¥0.386） | deepseek-flash | default | 未知 | ≥209.6 | 224.0 | 208.2 |
| 8 codex deepseek-flash high | codex-medium-a3 |  | 是 | 5 | 是 | 0.734 | 0.734 | 0.780 | 0.060 | 2 | 4.5 | 未知 | 53,653 | 1,709,824 | 62,933 | 76 | 0.051（¥0.340） | deepseek-flash | default | 未知 | ≥233.8 | 198.0 | 232.2 |
| 8 codex deepseek-flash high | codex-high-a3 |  | 是 | 6 | 是 | 0.691 | 0.691 | 0.691 | 0.000 | 0 | 4.9 | 未知 | 71,842 | 2,461,184 | 66,475 | 93 | 0.058（¥0.387） | deepseek-flash | default | 未知 | ≥226.0 | 242.4 | 224.3 |
| 8 codex deepseek-flash high | codex-high-a4 |  | 是 | 7 | 是 | 0.791 | 0.791 | 0.791 | 0.000 | 0 | 6.0 | 未知 | 75,827 | 3,368,064 | 80,927 | 74 | 0.070（¥0.467） | deepseek-flash | default | 未知 | ≥226.7 | 210.7 | 224.9 |
| 8 codex deepseek-flash high | codex-medium-a4 |  | 是 | 8 | 是 | 0.795 | 0.795 | 0.795 | 0.000 | 0 | 4.8 | 未知 | 50,571 | 2,179,072 | 64,086 | 75 | 0.053（¥0.350） | deepseek-flash | default | 未知 | ≥222.3 | 173.9 | 220.3 |
| 9 codex deepseek-flash max | codex-max-a1 |  | 是 | 1 | 是 | 0.416 | 0.416 | 0.416 | 0.000 | 0 | 6.5 | 未知 | 73,446 | 1,841,024 | 83,689 | 69 | 0.067（¥0.445） | deepseek-flash | default | 未知 | ≥217.0 | 189.4 | 215.8 |
| 9 codex deepseek-flash max | codex-max-a2 |  | 是 | 2 | 是 | 0.769 | 0.769 | 0.769 | 0.000 | 0 | 5.3 | 未知 | 63,697 | 2,404,608 | 71,159 | 66 | 0.059（¥0.396） | deepseek-flash | default | 未知 | ≥228.0 | 202.1 | 225.8 |
| 9 codex deepseek-flash max | codex-max-a3 |  | 是 | 3 | 是 | 0.830 | 0.830 | 0.830 | 0.000 | 0 | 5.6 | 未知 | 68,585 | 2,971,776 | 73,489 | 58 | 0.063（¥0.422） | deepseek-flash | default | 未知 | ≥218.8 | 202.6 | 217.1 |
| 9 codex deepseek-flash max | codex-max-a4 |  | 是 | 4 | 是 | 0.833 | 0.833 | 0.833 | 0.000 | 0 | 6.5 | 未知 | 69,239 | 4,060,672 | 86,327 | 83 | 0.074（¥0.496） | deepseek-flash | default | 未知 | ≥225.4 | 178.8 | 222.9 |
| 9 codex deepseek-flash max | codex-max-a5 |  | 是 | 5 | 是 | 0.874 | 0.874 | 0.874 | 0.000 | 0 | 13.5 | 未知 | 79,799 | 4,512,768 | 101,836 | 84 | 0.087（¥0.577） | deepseek-flash | default | 未知 | ≥214.2 | 98.4 | 125.5 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a1 |  | 是 | 1 | 是 | 0.557 | 0.557 | 0.557 | 0.000 | 0 | 17.2 | 未知 | 235,260 | 4,005,490 | 77,120 | 46 | 0.136 | 未知 | 未知 | 1839.4 | 89.5 | 228.1 | 74.8 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a2 |  | 是 | 2 | 是 | 0.544 | 0.544 | 0.544 | 0.000 | 0 | 13.3 | 未知 | 61,727 | 2,905,846 | 63,479 | 38 | 0.086 | 未知 | 未知 | 1122.1 | 90.5 | 77.4 | 79.6 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a4 |  | 是 | 3 | 是 | 0.574 | 0.574 | 0.574 | 0.000 | 0 | 14.8 | 未知 | 62,325 | 3,260,507 | 73,853 | 41 | 0.096 | 未知 | 未知 | 1045.6 | 94.2 | 70.3 | 83.3 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a6 |  | 是 | 4 | 是 | 0.664 | 0.664 | 0.664 | 0.000 | 0 | 15.9 | 未知 | 54,141 | 3,653,024 | 79,735 | 41 | 0.104 | 未知 | 未知 | 1024.9 | 93.1 | 56.7 | 83.5 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a7 |  | 是 | 5 | 是 | 0.385 | 0.385 | 0.428 | 0.100 | 93 | 16.4 | 未知 | 64,030 | 3,806,192 | 80,241 | 43 | 0.108 | 未知 | 未知 | 1096.9 | 91.0 | 65.1 | 81.6 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a8 |  | 是 | 6 | 是 | 0.561 | 0.561 | 0.561 | 0.000 | 0 | 15.7 | 未知 | 71,001 | 4,188,956 | 76,692 | 47 | 0.114 | 未知 | 未知 | 1142.2 | 91.9 | 75.3 | 81.3 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a9 |  | 是 | 7 | 是 | 0.518 | 0.518 | 0.518 | 0.000 | 0 | 14.4 | 未知 | 65,710 | 3,731,892 | 71,292 | 52 | 0.103 | 未知 | 未知 | 1197.0 | 93.4 | 76.0 | 82.4 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a10 |  | 是 | 8 | 是 | 0.501 | 0.501 | 0.501 | 0.000 | 0 | 11.8 | 未知 | 64,723 | 3,162,784 | 56,254 | 45 | 0.087 | 未知 | 未知 | 1118.7 | 93.2 | 91.3 | 79.3 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a11 |  | 是 | 9 | 是 | 0.324 | 0.324 | 0.324 | 0.000 | 0 | 15.4 | 未知 | 69,876 | 3,612,858 | 75,160 | 49 | 0.104 | 未知 | 未知 | 1113.1 | 92.4 | 75.7 | 81.5 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a12 |  | 是 | 10 | 是 | 0.475 | 0.475 | 0.475 | 0.000 | 0 | 12.8 | 未知 | 69,560 | 3,136,708 | 62,855 | 38 | 0.090 | 未知 | 未知 | 1205.6 | 94.3 | 90.3 | 81.6 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a3 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 9.1 | 未知 | 48,262 | 1,629,358 | 43,947 | 29 | 0.054 | 未知 | 未知 | 1168.9 | 94.4 | 88.2 | 80.3 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a5 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 13.4 | 未知 | 58,563 | 3,266,037 | 61,695 | 53 | 0.090 | 未知 | 未知 | 1117.7 | 87.3 | 73.0 | 76.9 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a1 |  | 是 | 1 | 是 | 0.661 | 0.661 | 0.661 | 0.000 | 0 | 17.2 | 未知 | 78,344 | 2,362,876 | 86,039 | 30 | 0.090 | 未知 | 未知 | 1427.6 | 91.9 | 76.0 | 83.4 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a4 |  | 是 | 2 | 是 | 0.428 | 0.428 | 0.428 | 0.000 | 0 | 21.4 | 未知 | 230,748 | 3,805,168 | 102,833 | 49 | 0.144 | 未知 | 未知 | 1895.1 | 92.0 | 180.0 | 80.2 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a5 |  | 是 | 3 | 是 | 0.708 | 0.708 | 0.708 | 0.000 | 0 | 15.4 | 未知 | 213,242 | 2,483,460 | 69,953 | 35 | 0.105 | 未知 | 未知 | 1900.7 | 91.0 | 230.2 | 75.5 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a6 |  | 是 | 4 | 是 | 0.842 | 0.842 | 0.842 | 0.000 | 0 | 15.8 | 未知 | 75,590 | 3,404,483 | 77,154 | 44 | 0.102 | 未知 | 未知 | 1186.1 | 91.5 | 79.7 | 81.4 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a7 |  | 是 | 5 | 是 | 0.644 | 0.644 | 0.644 | 0.000 | 0 | 19.1 | 未知 | 71,275 | 4,423,035 | 96,049 | 48 | 0.127 | 未知 | 未知 | 1112.3 | 92.4 | 62.1 | 83.6 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a8 |  | 是 | 6 | 是 | 0.611 | 0.611 | 0.611 | 0.000 | 0 | 13.8 | 未知 | 66,340 | 2,335,308 | 70,101 | 32 | 0.080 | 未知 | 未知 | 1369.9 | 95.5 | 80.2 | 84.8 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a9 |  | 是 | 7 | 是 | 0.581 | 0.581 | 0.581 | 0.000 | 0 | 16.2 | 未知 | 70,619 | 2,555,504 | 80,411 | 36 | 0.089 | 未知 | 未知 | 1304.2 | 92.4 | 72.8 | 82.9 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a10 |  | 是 | 8 | 是 | 0.483 | 0.483 | 0.483 | 0.000 | 0 | 10.0 | 未知 | 61,922 | 1,280,001 | 49,281 | 24 | 0.053 | 未知 | 未知 | 1438.4 | 95.8 | 102.9 | 81.9 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a11 |  | 是 | 9 | 是 | 0.471 | 0.471 | 0.471 | 0.000 | 0 | 13.0 | 未知 | 62,812 | 2,085,223 | 64,435 | 28 | 0.073 | 未知 | 未知 | 1388.8 | 94.0 | 80.7 | 82.8 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a12 |  | 是 | 10 | 是 | 0.680 | 0.680 | 0.680 | 0.000 | 0 | 14.7 | 未知 | 57,572 | 2,701,500 | 73,432 | 33 | 0.086 | 未知 | 未知 | 1214.0 | 93.0 | 65.3 | 83.2 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a2 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 9.7 | 未知 | 47,293 | 1,154,275 | 47,183 | 21 | 0.048 | 未知 | 未知 | 1439.9 | 92.1 | 81.0 | 80.9 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a3 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 9.7 | 未知 | 48,065 | 1,384,802 | 47,404 | 28 | 0.052 | 未知 | 未知 | 1255.5 | 93.6 | 82.4 | 81.3 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a1 |  | 是 | 1 | 是 | 0.664 | 0.664 | 0.664 | 0.000 | 0 | 23.4 | 未知 | 279,695 | 3,568,007 | 110,637 | 56 | 0.151 | 未知 | 未知 | 1900.7 | 91.3 | 199.5 | 78.9 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a2 |  | 是 | 2 | 是 | 0.720 | 0.720 | 0.720 | 0.000 | 0 | 25.7 | 未知 | 254,306 | 3,293,602 | 127,366 | 65 | 0.151 | 未知 | 未知 | 1916.4 | 93.4 | 165.2 | 82.7 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a3 |  | 是 | 3 | 是 | 0.772 | 0.772 | 0.772 | 0.000 | 0 | 15.4 | 未知 | 71,224 | 3,777,263 | 74,595 | 48 | 0.106 | 未知 | 未知 | 1226.4 | 91.0 | 77.3 | 81.0 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a4 |  | 是 | 4 | 是 | 0.554 | 0.554 | 0.554 | 0.000 | 0 | 11.9 | 未知 | 52,382 | 2,026,237 | 56,628 | 32 | 0.067 | 未知 | 未知 | 1215.0 | 89.7 | 73.3 | 79.3 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a5 |  | 是 | 5 | 是 | 0.595 | 0.595 | 0.595 | 0.000 | 0 | 23.4 | 未知 | 223,233 | 3,742,540 | 115,750 | 55 | 0.148 | 未知 | 未知 | 1799.1 | 93.6 | 158.8 | 82.3 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a6 |  | 是 | 6 | 是 | 0.571 | 0.571 | 0.571 | 0.000 | 0 | 17.1 | 未知 | 79,574 | 4,017,899 | 85,465 | 46 | 0.116 | 未知 | 未知 | 1296.2 | 93.0 | 77.6 | 83.3 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a7 |  | 是 | 7 | 是 | 0.658 | 0.658 | 0.658 | 0.000 | 0 | 16.1 | 未知 | 64,856 | 2,539,849 | 78,526 | 34 | 0.087 | 未知 | 未知 | 1319.8 | 90.4 | 67.3 | 81.5 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a8 |  | 是 | 8 | 是 | 0.822 | 0.822 | 0.822 | 0.000 | 0 | 15.4 | 未知 | 59,285 | 2,527,233 | 77,312 | 35 | 0.086 | 未知 | 未知 | 1253.0 | 93.1 | 64.2 | 83.7 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a9 |  | 是 | 9 | 是 | 0.612 | 0.612 | 0.612 | 0.000 | 0 | 12.2 | 未知 | 56,160 | 2,470,791 | 60,000 | 36 | 0.076 | 未知 | 未知 | 1280.5 | 93.0 | 76.6 | 81.8 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a10 |  | 是 | 10 | 是 | 0.674 | 0.674 | 0.674 | 0.000 | 0 | 16.1 | 未知 | 93,913 | 2,620,886 | 76,210 | 40 | 0.092 | 未知 | 未知 | 1559.2 | 88.5 | 97.1 | 78.8 |
| 13 claude-code opus low | opus-low-a1 |  | 是 | 1 | 是 | 0.799 | 0.799 | 0.819 | 0.025 | 0 | 1.8 | 未知 | 62,746 | 253,501 | 12,412 | 6 | 0.801 | claude-opus-5-5 | standard | 未知 | ≥117.6 | 567.4 | 112.2 |
| 13 claude-code opus low | opus-low-a2 |  | 是 | 2 | 是 | 0.823 | 0.823 | 0.842 | 0.023 | 0 | 2.7 | 未知 | 55,215 | 186,902 | 14,524 | 5 | 0.770 | claude-opus-5-5 | standard | 未知 | ≥117.9 | 347.0 | 91.3 |
| 13 claude-code opus low | opus-low-a3 |  | 是 | 3 | 是 | 0.839 | 0.839 | 0.839 | 0.000 | 0 | 2.8 | 未知 | 57,717 | 154,051 | 14,604 | 5 | 0.785 | claude-opus-5-5 | standard | 未知 | ≥108.9 | 349.5 | 88.4 |
| 13 claude-code opus low | opus-low-a4 |  | 是 | 4 | 是 | 0.819 | 0.819 | 0.839 | 0.024 | 0 | 3.4 | 未知 | 58,500 | 196,905 | 13,338 | 5 | 0.774 | claude-opus-5-5 | standard | 未知 | ≥101.4 | 289.3 | 66.0 |
| 13 claude-code opus low | opus-low-a5 |  | 是 | 5 | 是 | 0.870 | 0.870 | 0.892 | 0.024 | 0 | 3.9 | 未知 | 59,540 | 267,329 | 13,858 | 6 | 0.807 | claude-opus-5-5 | standard | 未知 | ≥108.7 | 253.3 | 59.0 |
| 14 claude-code opus medium | opus-medium-a1 |  | 是 | 1 | 是 | 0.839 | 0.839 | 0.839 | 0.000 | 0 | 2.8 | 未知 | 67,977 | 317,642 | 19,237 | 7 | 0.992 | claude-opus-5-5 | standard | 未知 | ≥119.1 | 408.0 | 115.5 |
| 14 claude-code opus medium | opus-medium-a2 |  | 是 | 2 | 是 | 0.845 | 0.845 | 0.845 | 0.000 | 0 | 4.3 | 未知 | 72,463 | 400,687 | 20,514 | 9 | 1.070 | claude-opus-5-5 | standard | 未知 | ≥116.3 | 280.8 | 79.5 |
| 14 claude-code opus medium | opus-medium-a3 |  | 是 | 3 | 是 | 0.887 | 0.887 | 0.887 | 0.000 | 0 | 4.0 | 未知 | 67,333 | 320,409 | 20,068 | 9 | 1.004 | claude-opus-5-5 | standard | 未知 | ≥95.0 | 278.1 | 82.9 |
| 14 claude-code opus medium | opus-medium-a4 |  | 是 | 4 | 是 | 0.851 | 0.851 | 0.851 | 0.000 | 0 | 5.1 | 未知 | 69,939 | 306,200 | 19,091 | 8 | 1.003 | claude-opus-5-5 | standard | 未知 | ≥100.3 | 230.7 | 63.0 |
| 14 claude-code opus medium | opus-medium-a5 |  | 是 | 5 | 是 | 0.856 | 0.856 | 0.856 | 0.000 | 0 | 5.7 | 未知 | 81,009 | 561,082 | 22,621 | 10 | 1.213 | claude-opus-5-5 | standard | 未知 | ≥101.7 | 238.0 | 66.5 |
| 15 claude-code opus high | opus-high-a1 |  | 是 | 1 | 是 | 0.887 | 0.887 | 0.887 | 0.000 | 0 | 6.0 | 未知 | 80,950 | 492,960 | 34,280 | 10 | 1.432 | claude-opus-5-5 | standard | 未知 | ≥114.8 | 224.3 | 95.0 |
| 15 claude-code opus high | opus-high-a2 |  | 是 | 2 | 是 | 0.876 | 0.876 | 0.876 | 0.000 | 0 | 6.2 | 未知 | 86,567 | 564,396 | 29,616 | 10 | 1.398 | claude-opus-5-5 | standard | 未知 | ≥105.5 | 232.9 | 79.7 |
| 15 claude-code opus high | opus-high-a3 |  | 是 | 3 | 是 | 0.872 | 0.872 | 0.893 | 0.024 | 0 | 6.8 | 未知 | 80,732 | 535,835 | 27,782 | 11 | 1.309 | claude-opus-5-5 | standard | 未知 | ≥95.4 | 197.9 | 68.1 |
| 15 claude-code opus high | opus-high-a4 |  | 是 | 4 | 是 | 0.847 | 0.847 | 0.864 | 0.020 | 0 | 7.2 | 未知 | 92,692 | 686,265 | 27,538 | 12 | 1.429 | claude-opus-5-5 | standard | 未知 | ≥110.1 | 214.7 | 63.8 |
| 15 claude-code opus high | opus-high-a5 |  | 是 | 5 | 是 | 0.896 | 0.896 | 0.896 | 0.000 | 0 | 10.3 | 未知 | 97,595 | 1,012,476 | 48,614 | 17 | 1.955 | claude-opus-5-5 | standard | 未知 | ≥121.1 | 158.6 | 79.0 |
| 16 claude-code sonnet low | sonnet-low-a1 |  | 是 | 1 | 是 | 0.811 | 0.811 | 0.836 | 0.030 | 0 | 2.3 | 未知 | 64,036 | 296,926 | 16,641 | 8 | 0.452 | claude-sonnet-5-5 | standard | 未知 | ≥129.8 | 471.4 | 122.5 |
| 16 claude-code sonnet low | sonnet-low-a2 |  | 是 | 2 | 是 | 0.822 | 0.822 | 0.847 | 0.029 | 0 | 4.2 | 未知 | 61,568 | 309,857 | 16,402 | 9 | 0.441 | claude-sonnet-5-5 | standard | 未知 | ≥116.6 | 246.4 | 65.6 |
| 16 claude-code sonnet low | sonnet-low-a3 |  | 是 | 3 | 是 | 0.811 | 0.811 | 0.836 | 0.030 | 0 | 3.2 | 未知 | 56,228 | 257,180 | 15,384 | 7 | 0.404 | claude-sonnet-5-5 | standard | 未知 | ≥126.2 | 289.9 | 79.3 |
| 16 claude-code sonnet low | sonnet-low-a4 |  | 是 | 4 | 是 | 0.797 | 0.797 | 0.824 | 0.033 | 0 | 2.9 | 未知 | 57,580 | 221,124 | 15,309 | 6 | 0.405 | claude-sonnet-5-5 | standard | 未知 | ≥117.0 | 327.4 | 87.0 |
| 16 claude-code sonnet low | sonnet-low-a5 |  | 是 | 5 | 是 | 0.827 | 0.827 | 0.854 | 0.031 | 0 | 4.3 | 未知 | 56,395 | 318,627 | 15,790 | 8 | 0.415 | claude-sonnet-5-5 | standard | 未知 | ≥96.7 | 216.4 | 60.6 |
| 17 claude-code sonnet medium | sonnet-medium-a1 |  | 是 | 1 | 是 | 0.861 | 0.861 | 0.885 | 0.027 | 0 | 2.5 | 未知 | 70,888 | 283,330 | 20,106 | 8 | 0.513 | claude-sonnet-5-5 | standard | 未知 | ≥137.7 | 467.6 | 132.6 |
| 17 claude-code sonnet medium | sonnet-medium-a2 |  | 是 | 2 | 是 | 0.851 | 0.851 | 0.875 | 0.028 | 0 | 3.7 | 未知 | 58,743 | 299,997 | 17,503 | 7 | 0.440 | claude-sonnet-5-5 | standard | 未知 | ≥142.3 | 263.7 | 78.6 |
| 17 claude-code sonnet medium | sonnet-medium-a3 |  | 是 | 3 | 是 | 0.883 | 0.883 | 0.883 | 0.000 | 0 | 4.2 | 未知 | 64,887 | 356,414 | 19,988 | 9 | 0.495 | claude-sonnet-5-5 | standard | 未知 | ≥109.3 | 255.3 | 78.7 |
| 17 claude-code sonnet medium | sonnet-medium-a4 |  | 是 | 4 | 是 | 0.733 | 0.733 | 0.750 | 0.023 | 0 | 3.4 | 未知 | 61,133 | 204,330 | 18,677 | 7 | 0.452 | claude-sonnet-5-5 | standard | 未知 | ≥133.5 | 300.3 | 91.8 |
| 17 claude-code sonnet medium | sonnet-medium-a5 |  | 是 | 5 | 是 | 0.830 | 0.830 | 0.854 | 0.028 | 0 | 4.0 | 未知 | 63,628 | 315,733 | 19,864 | 8 | 0.485 | claude-sonnet-5-5 | standard | 未知 | ≥116.5 | 265.6 | 82.9 |
| 18 claude-code sonnet high | sonnet-high-a1 |  | 是 | 1 | 是 | 0.862 | 0.862 | 0.883 | 0.024 | 0 | 4.4 | 未知 | 92,375 | 581,298 | 42,758 | 12 | 0.855 | claude-sonnet-5-5 | standard | 未知 | ≥165.1 | 349.2 | 161.6 |
| 18 claude-code sonnet high | sonnet-high-a2 |  | 是 | 2 | 是 | 0.852 | 0.852 | 0.873 | 0.024 | 0 | 4.3 | 未知 | 67,127 | 329,877 | 23,846 | 8 | 0.540 | claude-sonnet-5-5 | standard | 未知 | ≥147.0 | 258.0 | 91.6 |
| 18 claude-code sonnet high | sonnet-high-a3 |  | 是 | 3 | 是 | 0.857 | 0.857 | 0.878 | 0.023 | 0 | 4.3 | 未知 | 70,108 | 210,749 | 26,827 | 8 | 0.570 | claude-sonnet-5-5 | standard | 未知 | ≥131.5 | 268.7 | 102.8 |
| 18 claude-code sonnet high | sonnet-high-a4 |  | 是 | 4 | 是 | 0.836 | 0.836 | 0.859 | 0.027 | 0 | 5.6 | 未知 | 73,504 | 451,379 | 26,478 | 11 | 0.604 | claude-sonnet-5-5 | standard | 未知 | ≥132.7 | 217.9 | 78.5 |
| 18 claude-code sonnet high | sonnet-high-a5 |  | 是 | 5 | 是 | 0.847 | 0.847 | 0.867 | 0.023 | 0 | 5.3 | 未知 | 77,206 | 545,689 | 31,322 | 12 | 0.677 | claude-sonnet-5-5 | standard | 未知 | ≥147.1 | 243.7 | 98.9 |
| 19 claude-code haiku low | haiku-low-a1 |  | 是 | 1 | 是 | 0.874 | 0.874 | 0.874 | 0.000 | 0 | 5.5 | 未知 | 118,442 | 787,455 | 71,624 | 13 | 0.179 | claude-haiku-5-5 | standard | 未知 | ≥244.5 | 361.5 | 218.6 |
| 19 claude-code haiku low | haiku-low-a2 |  | 是 | 2 | 是 | 0.833 | 0.833 | 0.833 | 0.000 | 0 | 5.6 | 未知 | 112,017 | 589,576 | 67,147 | 10 | 0.127 | claude-haiku-5-5 | standard | 未知 | ≥259.6 | 331.6 | 198.8 |
| 19 claude-code haiku low | haiku-low-a3 |  | 是 | 3 | 是 | 0.876 | 0.876 | 0.876 | 0.000 | 0 | 5.6 | 未知 | 109,554 | 690,320 | 55,795 | 11 | 0.100 | claude-haiku-5-5 | standard | 未知 | ≥242.6 | 326.0 | 166.0 |
| 19 claude-code haiku low | haiku-low-a4 |  | 是 | 4 | 是 | 0.874 | 0.874 | 0.874 | 0.000 | 0 | 7.3 | 未知 | 117,632 | 654,328 | 69,976 | 13 | 0.182 | claude-haiku-5-5 | standard | 未知 | ≥223.0 | 269.9 | 160.6 |
| 19 claude-code haiku low | haiku-low-a5 |  | 是 | 5 | 是 | 0.858 | 0.858 | 0.858 | 0.000 | 0 | 4.7 | 未知 | 107,240 | 307,457 | 63,721 | 8 | 0.113 | claude-haiku-5-5 | standard | 未知 | ≥246.3 | 382.0 | 227.0 |
| 20 claude-code haiku medium | haiku-medium-a1 |  | 是 | 1 | 是 | 0.892 | 0.892 | 0.892 | 0.000 | 0 | 5.8 | 未知 | 125,920 | 668,908 | 78,334 | 12 | 0.202 | claude-haiku-5-5 | standard | 未知 | ≥260.6 | 364.8 | 226.9 |
| 20 claude-code haiku medium | haiku-medium-a2 |  | 是 | 2 | 是 | 0.866 | 0.866 | 0.866 | 0.000 | 0 | 5.8 | 未知 | 116,142 | 409,212 | 70,495 | 10 | 0.125 | claude-haiku-5-5 | standard | 未知 | ≥233.0 | 334.9 | 203.2 |
| 20 claude-code haiku medium | haiku-medium-a3 |  | 是 | 3 | 是 | 0.875 | 0.875 | 0.875 | 0.000 | 0 | 8.0 | 未知 | 134,020 | 741,280 | 80,080 | 15 | 0.162 | claude-haiku-5-5 | standard | 未知 | ≥239.2 | 280.7 | 167.7 |
| 20 claude-code haiku medium | haiku-medium-a4 |  | 是 | 4 | 是 | 0.850 | 0.850 | 0.871 | 0.024 | 0 | 6.5 | 未知 | 118,810 | 635,759 | 73,908 | 18 | 0.099 | claude-haiku-5-5 | standard | 未知 | ≥230.2 | 304.0 | 189.1 |
| 20 claude-code haiku medium | haiku-medium-a5 |  | 是 | 5 | 是 | 0.889 | 0.889 | 0.889 | 0.000 | 0 | 7.4 | 未知 | 121,933 | 486,692 | 75,669 | 14 | 0.134 | claude-haiku-5-5 | standard | 未知 | ≥240.7 | 274.4 | 170.3 |
| 21 claude-code haiku high | haiku-high-a1 |  | 是 | 1 | 是 | 0.874 | 0.874 | 0.874 | 0.000 | 0 | 9.6 | 未知 | 189,199 | 2,028,303 | 116,416 | 21 | 0.413 | claude-haiku-5-5 | standard | 未知 | ≥237.0 | 328.0 | 201.8 |
| 21 claude-code haiku high | haiku-high-a2 |  | 是 | 2 | 是 | 0.886 | 0.886 | 0.886 | 0.000 | 0 | 9.8 | 未知 | 159,730 | 1,100,292 | 107,787 | 21 | 0.314 | claude-haiku-5-5 | standard | 未知 | ≥239.8 | 270.5 | 182.5 |
| 21 claude-code haiku high | haiku-high-a3 |  | 是 | 3 | 是 | 0.863 | 0.863 | 0.863 | 0.000 | 0 | 10.3 | 未知 | 144,329 | 1,109,904 | 96,337 | 15 | 0.286 | claude-haiku-5-5 | standard | 未知 | ≥240.4 | 234.5 | 156.5 |
| 21 claude-code haiku high | haiku-high-a4 |  | 是 | 4 | 是 | 0.824 | 0.824 | 0.824 | 0.000 | 0 | 9.5 | 未知 | 144,098 | 1,056,190 | 94,253 | 20 | 0.249 | claude-haiku-5-5 | standard | 未知 | ≥230.1 | 252.3 | 165.0 |
| 21 claude-code haiku high | haiku-high-a5 |  | 是 | 5 | 是 | 0.861 | 0.861 | 0.861 | 0.000 | 0 | 7.2 | 未知 | 149,953 | 715,060 | 102,329 | 15 | 0.222 | claude-haiku-5-5 | standard | 未知 | ≥255.5 | 345.9 | 236.1 |
| 22 claude-code deepseek-flash low | cc-low-a1 |  | 是 | 1 | 是 | 0.816 | 0.816 | 0.816 | 0.000 | 0 | 9.8 | 未知 | 45,829 | 1,770,752 | 80,450 | 32 | 0.060（¥0.403） | deepseek-flash | standard | 未知 | ≥210.7 | 78.0 | 137.0 |
| 22 claude-code deepseek-flash low | cc-low-a2 |  | 是 | 2 | 是 | 0.639 | 0.639 | 0.639 | 0.000 | 0 | 9.2 | 未知 | 40,865 | 488,320 | 62,392 | 18 | 0.045（¥0.300） | deepseek-flash | standard | 未知 | ≥181.6 | 74.2 | 113.3 |
| 22 claude-code deepseek-flash low | cc-low-a3 |  | 是 | 3 | 是 | 0.709 | 0.709 | 0.709 | 0.000 | 0 | 6.8 | 未知 | 36,890 | 795,392 | 47,483 | 28 | 0.036（¥0.243） | deepseek-flash | standard | 未知 | ≥199.7 | 90.3 | 116.2 |
| 22 claude-code deepseek-flash low | cc-low-a4 |  | 是 | 4 | 是 | 0.726 | 0.726 | 0.726 | 0.000 | 0 | 6.3 | 未知 | 53,748 | 910,592 | 57,652 | 25 | 0.045（¥0.303） | deepseek-flash | standard | 未知 | ≥233.0 | 141.9 | 152.2 |
| 22 claude-code deepseek-flash low | cc-low-a5 |  | 是 | 5 | 是 | 0.631 | 0.631 | 0.631 | 0.000 | 0 | 8.5 | 未知 | 44,112 | 1,313,280 | 62,826 | 31 | 0.048（¥0.322） | deepseek-flash | standard | 未知 | ≥230.1 | 86.3 | 122.9 |
| 23 claude-code deepseek-flash high | cc-medium-a1 |  | 是 | 1 | 是 | 0.698 | 0.698 | 0.698 | 0.000 | 0 | 10.1 | 未知 | 44,575 | 1,438,080 | 65,716 | 40 | 0.050（¥0.336） | deepseek-flash | standard | 未知 | ≥205.7 | 73.5 | 108.3 |
| 23 claude-code deepseek-flash high | cc-high-a1 |  | 是 | 2 | 是 | 0.805 | 0.805 | 0.805 | 0.000 | 0 | 14.8 | 未知 | 48,801 | 2,116,480 | 85,595 | 40 | 0.065（¥0.433） | deepseek-flash | standard | 未知 | ≥182.8 | 54.9 | 96.2 |
| 23 claude-code deepseek-flash high | cc-high-a2 |  | 是 | 3 | 是 | 0.629 | 0.629 | 0.629 | 0.000 | 0 | 8.7 | 未知 | 50,524 | 1,253,248 | 89,739 | 33 | 0.065（¥0.434） | deepseek-flash | standard | 未知 | ≥225.1 | 96.6 | 171.7 |
| 23 claude-code deepseek-flash high | cc-medium-a2 |  | 是 | 4 | 是 | 0.731 | 0.731 | 0.731 | 0.000 | 0 | 13.4 | 未知 | 67,269 | 1,676,672 | 106,891 | 34 | 0.079（¥0.528） | deepseek-flash | standard | 未知 | ≥218.3 | 83.7 | 133.0 |
| 23 claude-code deepseek-flash high | cc-medium-a3 |  | 是 | 5 | 是 | 0.833 | 0.833 | 0.833 | 0.000 | 0 | 14.5 | 未知 | 52,363 | 2,296,704 | 112,984 | 42 | 0.083（¥0.550） | deepseek-flash | standard | 未知 | ≥207.8 | 60.2 | 129.9 |
| 23 claude-code deepseek-flash high | cc-high-a3 |  | 是 | 6 | 是 | 0.863 | 0.863 | 0.863 | 0.000 | 0 | 11.0 | 未知 | 54,911 | 2,128,128 | 77,526 | 44 | 0.061（¥0.408） | deepseek-flash | standard | 未知 | ≥180.6 | 83.0 | 117.2 |
| 23 claude-code deepseek-flash high | cc-high-a4 |  | 是 | 7 | 是 | 0.733 | 0.733 | 0.733 | 0.000 | 0 | 7.6 | 未知 | 59,647 | 1,321,728 | 77,120 | 28 | 0.059（¥0.395） | deepseek-flash | standard | 未知 | ≥242.8 | 131.1 | 169.4 |
| 23 claude-code deepseek-flash high | cc-medium-a4 |  | 是 | 8 | 是 | 0.642 | 0.642 | 0.642 | 0.000 | 0 | 10.3 | 未知 | 49,523 | 2,136,320 | 80,506 | 36 | 0.062（¥0.414） | deepseek-flash | standard | 未知 | ≥211.8 | 80.1 | 130.3 |
| 24 claude-code deepseek-flash max | cc-max-a1 |  | 是 | 1 | 是 | 0.843 | 0.843 | 0.843 | 0.000 | 0 | 13.5 | 未知 | 48,645 | 2,314,752 | 139,685 | 55 | 0.098（¥0.654） | deepseek-flash | standard | 未知 | ≥228.2 | 60.2 | 172.8 |
| 24 claude-code deepseek-flash max | cc-max-a2 |  | 是 | 2 | 是 | 0.877 | 0.877 | 0.877 | 0.000 | 0 | 16.4 | 未知 | 95,010 | 2,613,760 | 145,911 | 90 | 0.110（¥0.731） | deepseek-flash | standard | 未知 | ≥209.0 | 96.7 | 148.5 |
| 24 claude-code deepseek-flash max | cc-max-a3 |  | 是 | 3 | 是 | 0.735 | 0.735 | 0.735 | 0.000 | 0 | 8.4 | 未知 | 57,281 | 1,392,640 | 89,392 | 54 | 0.066（¥0.443） | deepseek-flash | standard | 未知 | ≥216.4 | 113.6 | 177.2 |
| 24 claude-code deepseek-flash max | cc-max-a4 |  | 是 | 4 | 是 | 0.855 | 0.855 | 0.855 | 0.000 | 0 | 13.0 | 未知 | 57,636 | 1,759,616 | 117,551 | 34 | 0.084（¥0.563） | deepseek-flash | standard | 未知 | ≥218.7 | 73.7 | 150.3 |
| 24 claude-code deepseek-flash max | cc-max-a5 |  | 是 | 5 | 是 | 0.776 | 0.776 | 0.776 | 0.000 | 0 | 28.4 | 未知 | 104,612 | 4,411,008 | 182,121 | 93 | 0.138（¥0.921） | deepseek-flash | standard | 未知 | ≥154.0 | 61.4 | 106.9 |
| 25 claude-code strata-iq3_xxs low | strata-low-a1 |  | 是 | 1 | 是 | 0.812 | 0.812 | 0.812 | 0.000 | 0 | 15.8 | 未知 | 101,927 | 4,577,226 | 75,500 | 62 | 0.124 | qwen3.8-flash-next-iq3_xxs | not-returned | 1268.0 | 89.6 | 107.8 | 79.8 |
| 25 claude-code strata-iq3_xxs low | strata-low-a2 |  | 是 | 2 | 是 | 0.690 | 0.690 | 0.690 | 0.000 | 0 | 13.8 | 未知 | 58,852 | 3,457,630 | 67,272 | 59 | 0.096 | qwen3.8-flash-next-iq3_xxs | not-returned | 1085.1 | 89.2 | 71.1 | 81.2 |
| 25 claude-code strata-iq3_xxs low | strata-low-a3 |  | 是 | 3 | 是 | 0.608 | 0.608 | 0.608 | 0.000 | 0 | 21.2 | 未知 | 81,258 | 5,376,440 | 99,249 | 72 | 0.145 | qwen3.8-flash-next-iq3_xxs | not-returned | 1090.2 | 85.3 | 64.0 | 78.2 |
| 25 claude-code strata-iq3_xxs low | strata-low-a4 |  | 是 | 4 | 是 | 0.254 | 0.254 | 0.254 | 0.000 | 0 | 13.1 | 未知 | 68,580 | 3,336,570 | 66,261 | 45 | 0.095 | qwen3.8-flash-next-iq3_xxs | not-returned | 1282.9 | 93.5 | 87.2 | 84.3 |
| 25 claude-code strata-iq3_xxs low | strata-low-a5 |  | 是 | 5 | 是 | 0.492 | 0.492 | 0.507 | 0.029 | 0 | 20.2 | 未知 | 84,662 | 6,554,905 | 99,022 | 75 | 0.164 | qwen3.8-flash-next-iq3_xxs | not-returned | 1041.3 | 91.4 | 69.9 | 81.7 |
| 25 claude-code strata-iq3_xxs low | strata-low-a6 |  | 是 | 6 | 是 | 0.652 | 0.652 | 0.652 | 0.000 | 0 | 16.8 | 未知 | 67,220 | 4,858,738 | 81,741 | 75 | 0.126 | qwen3.8-flash-next-iq3_xxs | not-returned | 1025.3 | 89.4 | 66.8 | 81.3 |
| 25 claude-code strata-iq3_xxs low | strata-low-a7 |  | 是 | 7 | 是 | 0.560 | 0.560 | 0.560 | 0.000 | 0 | 13.6 | 未知 | 73,152 | 4,876,040 | 64,981 | 73 | 0.120 | qwen3.8-flash-next-iq3_xxs | not-returned | 1090.1 | 89.6 | 89.8 | 79.8 |
| 25 claude-code strata-iq3_xxs low | strata-low-a8 |  | 是 | 8 | 是 | 0.689 | 0.689 | 0.689 | 0.000 | 0 | 12.8 | 未知 | 56,723 | 3,329,780 | 64,711 | 64 | 0.092 | qwen3.8-flash-next-iq3_xxs | not-returned | 1025.3 | 93.1 | 73.7 | 84.0 |
| 25 claude-code strata-iq3_xxs low | strata-low-a9 |  | 是 | 9 | 是 | 0.603 | 0.603 | 0.603 | 0.000 | 0 | 11.5 | 未知 | 67,328 | 3,473,072 | 57,307 | 61 | 0.093 | qwen3.8-flash-next-iq3_xxs | not-returned | 1173.9 | 92.7 | 97.2 | 82.7 |
| 25 claude-code strata-iq3_xxs low | strata-low-a10 |  | 是 | 10 | 是 | 0.624 | 0.624 | 0.624 | 0.000 | 0 | 16.9 | 未知 | 74,200 | 4,942,166 | 83,906 | 56 | 0.130 | qwen3.8-flash-next-iq3_xxs | not-returned | 1128.6 | 91.3 | 73.4 | 83.0 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a1 |  | 是 | 1 | 是 | 0.572 | 0.572 | 0.572 | 0.000 | 0 | 12.5 | 未知 | 52,225 | 2,191,688 | 63,193 | 46 | 0.073 | qwen3.8-flash-next-iq3_xxs | not-returned | 1285.7 | 90.7 | 69.5 | 84.1 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a2 |  | 是 | 2 | 是 | 0.555 | 0.555 | 0.588 | 0.055 | 0 | 27.8 | 未知 | 74,417 | 2,922,729 | 85,354 | 56 | 0.098 | qwen3.8-flash-next-iq3_xxs | not-returned | 1373.7 | 94.3 | 44.5 | 51.1 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a3 |  | 是 | 3 | 是 | 0.394 | 0.394 | 0.394 | 0.000 | 0 | 9.8 | 未知 | 60,705 | 1,716,964 | 49,435 | 28 | 0.060 | qwen3.8-flash-next-iq3_xxs | not-returned | 1534.6 | 92.6 | 103.0 | 83.9 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a4 |  | 是 | 4 | 是 | 0.512 | 0.512 | 0.512 | 0.000 | 0 | 20.5 | 未知 | 112,082 | 2,783,509 | 106,349 | 53 | 0.111 | qwen3.8-flash-next-iq3_xxs | not-returned | 1522.2 | 93.5 | 91.1 | 86.4 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a5 |  | 是 | 5 | 是 | 0.595 | 0.595 | 0.595 | 0.000 | 0 | 9.8 | 未知 | 58,156 | 1,311,483 | 52,054 | 26 | 0.054 | qwen3.8-flash-next-iq3_xxs | not-returned | 1555.1 | 96.5 | 98.8 | 88.4 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a6 |  | 是 | 6 | 是 | 0.674 | 0.674 | 0.674 | 0.000 | 0 | 16.5 | 未知 | 79,800 | 2,974,484 | 81,731 | 40 | 0.098 | qwen3.8-flash-next-iq3_xxs | not-returned | 1361.8 | 91.0 | 80.8 | 82.8 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a7 |  | 是 | 7 | 是 | 0.756 | 0.756 | 0.804 | 0.060 | 0 | 13.2 | 未知 | 51,226 | 1,724,172 | 63,962 | 45 | 0.065 | qwen3.8-flash-next-iq3_xxs | not-returned | 1413.3 | 85.4 | 64.6 | 80.6 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a8 |  | 是 | 8 | 是 | 0.701 | 0.701 | 0.701 | 0.000 | 0 | 33.7 | 未知 | 95,255 | 5,087,258 | 173,693 | 73 | 0.177 | qwen3.8-flash-next-iq3_xxs | not-returned | 1145.2 | 91.2 | 47.1 | 85.9 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a9 |  | 是 | 9 | 是 | 0.391 | 0.391 | 0.391 | 0.000 | 0 | 10.9 | 未知 | 67,757 | 2,110,515 | 51,276 | 37 | 0.068 | qwen3.8-flash-next-iq3_xxs | not-returned | 1353.7 | 86.7 | 103.4 | 78.3 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a10 |  | 是 | 10 | 是 | 0.735 | 0.735 | 0.735 | 0.000 | 0 | 13.4 | 未知 | 76,904 | 2,024,474 | 62,054 | 45 | 0.073 | qwen3.8-flash-next-iq3_xxs | not-returned | 1403.6 | 83.6 | 95.3 | 76.9 |
| 27 claude-code strata-iq3_xxs high | strata-high-a1 |  | 是 | 1 | 是 | 0.568 | 0.568 | 0.568 | 0.000 | 0 | 18.0 | 未知 | 52,845 | 2,303,379 | 96,586 | 61 | 0.090 | qwen3.8-flash-next-iq3_xxs | not-returned | 1341.8 | 95.1 | 49.1 | 89.7 |
| 27 claude-code strata-iq3_xxs high | strata-high-a2 |  | 是 | 2 | 是 | 0.589 | 0.589 | 0.589 | 0.000 | 0 | 15.9 | 未知 | 55,537 | 3,692,805 | 81,680 | 46 | 0.106 | qwen3.8-flash-next-iq3_xxs | not-returned | 1171.0 | 93.1 | 58.3 | 85.7 |
| 27 claude-code strata-iq3_xxs high | strata-high-a3 |  | 是 | 3 | 是 | 0.441 | 0.441 | 0.441 | 0.000 | 0 | 9.0 | 未知 | 69,121 | 1,636,846 | 42,594 | 33 | 0.057 | qwen3.8-flash-next-iq3_xxs | not-returned | 1529.1 | 89.6 | 128.6 | 79.3 |
| 27 claude-code strata-iq3_xxs high | strata-high-a4 |  | 是 | 4 | 是 | 0.846 | 0.846 | 0.846 | 0.000 | 0 | 13.1 | 未知 | 52,531 | 1,703,173 | 68,533 | 44 | 0.067 | qwen3.8-flash-next-iq3_xxs | not-returned | 1425.2 | 93.4 | 67.1 | 87.5 |
| 27 claude-code strata-iq3_xxs high | strata-high-a5 |  | 是 | 5 | 是 | 0.561 | 0.561 | 0.561 | 0.000 | 0 | 12.8 | 未知 | 68,645 | 2,286,839 | 65,751 | 34 | 0.078 | qwen3.8-flash-next-iq3_xxs | not-returned | 1426.0 | 94.5 | 89.7 | 85.9 |
| 27 claude-code strata-iq3_xxs high | strata-high-a6 |  | 是 | 6 | 是 | 0.481 | 0.481 | 0.534 | 0.100 | 81 | 15.0 | 未知 | 50,447 | 2,214,618 | 74,368 | 35 | 0.078 | qwen3.8-flash-next-iq3_xxs | not-returned | 1233.7 | 87.8 | 56.0 | 82.6 |
| 27 claude-code strata-iq3_xxs high | strata-high-a7 |  | 是 | 7 | 是 | 0.741 | 0.741 | 0.741 | 0.000 | 0 | 17.2 | 未知 | 68,012 | 2,336,513 | 85,620 | 34 | 0.088 | qwen3.8-flash-next-iq3_xxs | not-returned | 1427.4 | 88.2 | 65.9 | 83.0 |
| 27 claude-code strata-iq3_xxs high | strata-high-a8 |  | 是 | 8 | 是 | 0.460 | 0.460 | 0.460 | 0.000 | 0 | 17.8 | 未知 | 68,264 | 2,235,180 | 89,830 | 36 | 0.088 | qwen3.8-flash-next-iq3_xxs | not-returned | 1373.4 | 89.7 | 64.0 | 84.2 |
| 27 claude-code strata-iq3_xxs high | strata-high-a9 |  | 是 | 9 | 是 | 0.458 | 0.458 | 0.458 | 0.000 | 0 | 16.2 | 未知 | 84,037 | 2,212,193 | 79,824 | 30 | 0.086 | qwen3.8-flash-next-iq3_xxs | not-returned | 1604.9 | 87.9 | 86.4 | 82.1 |
| 27 claude-code strata-iq3_xxs high | strata-high-a10 |  | 是 | 10 | 是 | 0.757 | 0.757 | 0.757 | 0.000 | 0 | 14.7 | 未知 | 74,034 | 1,289,828 | 70,900 | 41 | 0.065 | qwen3.8-flash-next-iq3_xxs | not-returned | 1652.8 | 85.2 | 83.9 | 80.3 |
| 28 codex gpt-6-luna xhigh | luna-xhigh-a1 |  | 是 | 1 | 是 | 0.860 | 0.860 | 0.860 | 0.000 | 0 | 7.0 | 未知 | 118,352 | 828,800 | 55,643 | 12 | 只报 token | gpt-6-luna | default | 未知 | ≥133.4 | 283.4 | 133.2 |
| 28 codex gpt-6-luna xhigh | luna-xhigh-a2 |  | 是 | 2 | 是 | 0.829 | 0.829 | 0.829 | 0.000 | 0 | 10.0 | 未知 | 133,034 | 2,070,912 | 78,729 | 22 | 只报 token | gpt-6-luna | default | 未知 | ≥131.2 | 221.6 | 131.1 |
| 28 codex gpt-6-luna xhigh | luna-xhigh-a3 |  | 是 | 3 | 是 | 0.810 | 0.810 | 0.810 | 0.000 | 0 | 8.5 | 未知 | 120,095 | 1,156,480 | 52,437 | 15 | 只报 token | gpt-6-luna | default | 未知 | ≥102.6 | 234.5 | 102.4 |
| 28 codex gpt-6-luna xhigh | luna-xhigh-a4 |  | 是 | 4 | 是 | 0.858 | 0.858 | 0.858 | 0.000 | 0 | 7.6 | 未知 | 190,645 | 1,426,560 | 59,697 | 20 | 只报 token | gpt-6-luna | default | 未知 | ≥130.9 | 416.4 | 130.4 |
| 28 codex gpt-6-luna xhigh | luna-xhigh-a5 |  | 是 | 5 | 是 | -0.182 | 0.000 | -0.071 | 0.000 | 0 | 60.0 | 未知 | 499,290 | 64,167,552 | 101,998 | 24 | 只报 token | gpt-6-luna | default、not-returned | 未知 | ≥28.2 | ≥138.7 | ≥28.3 |
| 28 codex gpt-6-luna xhigh | luna-xhigh-a6 |  | 是 | 6 | 是 | 0.856 | 0.856 | 0.856 | 0.000 | 0 | 7.0 | 未知 | 110,912 | 1,612,416 | 49,863 | 23 | 只报 token | gpt-6-luna | default | 未知 | ≥118.7 | 263.4 | 118.4 |
| 29 codex gpt-6-luna max | luna-max-a1 |  | 是 | 1 | 是 | 0.791 | 0.791 | 0.791 | 0.000 | 0 | 6.1 | 未知 | 110,017 | 667,264 | 47,187 | 11 | 只报 token | gpt-6-luna | default | 未知 | ≥129.2 | 300.2 | 128.8 |
| 29 codex gpt-6-luna max | luna-max-a2 |  | 是 | 2 | 是 | 0.631 | 0.631 | 0.700 | 0.098 | 4 | 6.4 | 未知 | 100,324 | 754,688 | 49,531 | 13 | 只报 token | gpt-6-luna | default | 未知 | ≥129.3 | 261.4 | 129.1 |
| 29 codex gpt-6-luna max | luna-max-a3 |  | 是 | 3 | 是 | 0.859 | 0.859 | 0.859 | 0.000 | 0 | 8.0 | 未知 | 112,195 | 904,960 | 62,864 | 12 | 只报 token | gpt-6-luna | default | 未知 | ≥131.0 | 233.2 | 130.6 |
| 29 codex gpt-6-luna max | luna-max-a4 |  | 是 | 4 | 是 | 0.868 | 0.868 | 0.868 | 0.000 | 0 | 8.7 | 未知 | 137,329 | 1,537,792 | 66,773 | 17 | 只报 token | gpt-6-luna | default | 未知 | ≥128.1 | 263.3 | 128.0 |
| 29 codex gpt-6-luna max | luna-max-a5 |  | 是 | 5 | 是 | 0.827 | 0.827 | 0.827 | 0.000 | 0 | 7.5 | 未知 | 151,652 | 1,105,152 | 60,741 | 15 | 只报 token | gpt-6-luna | default | 未知 | ≥135.0 | 336.6 | 134.8 |

## spec-readiness-v4.3

### 配置

| 配置 | 行 | 有效 | 选入 n | 已计分 | 无效 | 均值 ± SD | SE | 95% 区间 | 负分数 | 最小 | 中位数 | r8.3 均值 | rawScore | f | 修复 | 耗时（分钟） | 占时限 | 未缓存 | 缓存 | 输出 | token 来源 | 工具调用 | 费用（美元；DeepSeek 括号内为人民币 ¥） | 周额度 | 模型 ID | service tier |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 codex gpt-6.1-sol low | 主统计 | 5 | 5 | 5 | 0 | 0.817 ± 0.034 | 0.015 | 0.775–0.859 | 0 | 0.765 | 0.832 | 0.817 | 0.817 | 0.000 | 0 | 5.0 | 未知 | 145,885 | 1,481,344 | 9,256 | API usage (relay) | 24.8 | 只报 token |  | gpt-6.1-sol | default |
| 2 codex gpt-6.1-sol medium | 主统计 | 5 | 5 | 5 | 1 | 0.784 ± 0.070 | 0.031 | 0.698–0.871 | 0 | 0.679 | 0.811 | 0.784 | 0.784 | 0.000 | 0 | 6.1 | 未知 | 154,450 | 1,744,896 | 11,778 | API usage (relay) | 28.4 | 只报 token |  | gpt-6.1-sol | default |
| 3 codex gpt-6.1-sol high | 主统计 | 5 | 5 | 5 | 1 | 0.803 ± 0.067 | 0.030 | 0.720–0.886 | 0 | 0.702 | 0.821 | 0.803 | 0.803 | 0.000 | 0 | 10.6 | 未知 | 172,083 | 2,751,232 | 20,536 | API usage (relay) | 39.8 | 只报 token |  | gpt-6.1-sol | default |
| 4 codex gpt-6-luna low | 主统计 | 5 | 5 | 5 | 1 | 0.143 ± 0.101 | 0.045 | 0.018–0.269 | 0 | 0.020 | 0.125 | 0.143 | 0.143 | 0.000 | 0 | 3.0 | 未知 | 159,322 | 1,677,670 | 10,614 | API usage (relay) | 27.6 | 只报 token |  | gpt-6-luna | default |
| 5 codex gpt-6-luna medium | 主统计 | 5 | 5 | 5 | 0 | 0.260 ± 0.185 | 0.083 | 0.030–0.490 | 0 | 0.102 | 0.229 | 0.260 | 0.260 | 0.000 | 0 | 3.0 | 未知 | 140,123 | 1,169,178 | 11,228 | API usage (relay) | 21.4 | 只报 token |  | gpt-6-luna | default |
| 6 codex gpt-6-luna high | 主统计 | 5 | 5 | 5 | 1 | 0.459 ± 0.077 | 0.034 | 0.364–0.555 | 0 | 0.375 | 0.447 | 0.459 | 0.459 | 0.000 | 0 | 4.6 | 未知 | 158,994 | 1,368,346 | 20,331 | API usage (relay) | 24.4 | 只报 token |  | gpt-6-luna | default |
| 7 codex deepseek-flash low | 主统计 | 5 | 5 | 5 | 2 | 0.691 ± 0.047 | 0.021 | 0.633–0.750 | 0 | 0.632 | 0.685 | 0.691 | 0.691 | 0.000 | 0 | 11.1 | 未知 | 146,361 | 4,136,038 | 108,048 | API usage (relay) | 98.6 | 0.496（¥3.306） |  | deepseek-flash | default |
| 8 codex deepseek-flash high | 主统计 | 5 | 5 | 5 | 0 | 0.586 ± 0.223 | 0.100 | 0.308–0.863 | 0 | 0.192 | 0.659 | 0.586 | 0.590 | 0.000 | 0 | 21.3 | 未知 | 未知 | 未知 | 未知 | API usage (relay) | 140.6 | ≥1.099（¥7.330） |  | deepseek-flash | default、not-returned |
| 9 codex deepseek-flash max | 主统计 | 5 | 5 | 5 | 0 | 0.677 ± 0.058 | 0.026 | 0.605–0.749 | 0 | 0.633 | 0.658 | 0.677 | 0.677 | 0.000 | 0 | 12.4 | 未知 | 159,419 | 4,353,050 | 139,912 | API usage (relay) | 97.6 | 0.605（¥4.031） |  | deepseek-flash | default、not-returned |
| 10 codex strata-iq3_xxs low | 主统计 | 10 | 10 | 10 | 0 | 0.463 ± 0.128 | 0.041 | 0.371–0.555 | 0 | 0.301 | 0.436 | 0.463 | 0.463 | 0.000 | 0 | 12.1 | 未知 | 143,995 | 3,676,768 | 51,661 | engine log | 55.7 | 1.047 |  | 未知 | 未知 |
| 10 codex strata-iq3_xxs low | 一致性行（前 5） | 10 | 5 | 5 |  | 0.490 ± 0.115 | 0.051 | 0.347–0.633 | 0 | 0.370 | 0.457 | 0.490 | 0.490 | 0.000 | 0 | 13.2 | 未知 | 146,287 | 4,170,147 | 56,770 | engine log | 59.8 | 0.577 |  | 未知 | 未知 |
| 11 codex strata-iq3_xxs medium | 主统计 | 10 | 10 | 10 | 0 | 0.521 ± 0.074 | 0.024 | 0.468–0.574 | 0 | 0.396 | 0.532 | 0.521 | 0.521 | 0.000 | 0 | 13.3 | 未知 | 145,024 | 3,154,979 | 56,298 | engine log | 51.2 | 0.987 |  | 未知 | 未知 |
| 11 codex strata-iq3_xxs medium | 一致性行（前 5） | 10 | 5 | 5 |  | 0.564 ± 0.065 | 0.029 | 0.483–0.645 | 0 | 0.473 | 0.563 | 0.564 | 0.564 | 0.000 | 0 | 13.5 | 未知 | 146,559 | 3,335,728 | 57,870 | engine log | 53.2 | 0.513 |  | 未知 | 未知 |
| 12 codex strata-iq3_xxs high | 主统计 | 10 | 10 | 10 | 0 | 0.532 ± 0.081 | 0.026 | 0.474–0.590 | 0 | 0.373 | 0.548 | 0.532 | 0.532 | 0.000 | 0 | 14.2 | 未知 | 142,591 | 2,598,279 | 62,219 | engine log | 49.2 | 0.922 |  | 未知 | 未知 |
| 12 codex strata-iq3_xxs high | 一致性行（前 5） | 10 | 5 | 5 |  | 0.494 ± 0.074 | 0.033 | 0.403–0.586 | 0 | 0.373 | 0.513 | 0.494 | 0.494 | 0.000 | 0 | 13.9 | 未知 | 146,189 | 2,668,437 | 59,813 | engine log | 50.8 | 0.464 |  | 未知 | 未知 |
| 13 claude-code opus low | 主统计 | 5 | 5 | 5 | 0 | 0.665 ± 0.070 | 0.031 | 0.578–0.752 | 0 | 0.564 | 0.654 | 0.665 | 0.665 | 0.000 | 0 | 5.4 | 未知 | 121,623 | 529,115 | 11,393 | Claude Code stream result usage | 11.6 | 6.533 | 0.56% | claude-opus-5-5 | standard |
| 14 claude-code opus medium | 主统计 | 5 | 5 | 5 | 0 | 0.772 ± 0.044 | 0.020 | 0.718–0.826 | 0 | 0.720 | 0.768 | 0.772 | 0.772 | 0.000 | 0 | 11.2 | 未知 | 168,137 | 1,133,872 | 31,481 | Claude Code stream result usage | 21.0 | 11.007 | 0.95% | claude-opus-5-5 | standard |
| 15 claude-code opus high | 主统计 | 5 | 5 | 5 | 0 | 0.812 ± 0.033 | 0.015 | 0.772–0.853 | 0 | 0.764 | 0.812 | 0.812 | 0.812 | 0.000 | 0 | 13.1 | 未知 | 222,030 | 1,610,609 | 51,963 | Claude Code stream result usage | 29.6 | 15.687 | 1.35% | claude-opus-5-5 | standard |
| 16 claude-code sonnet low | 主统计 | 5 | 5 | 5 | 0 | 0.478 ± 0.044 | 0.020 | 0.422–0.533 | 0 | 0.426 | 0.468 | 0.478 | 0.478 | 0.000 | 0 | 3.2 | 未知 | 132,486 | 583,784 | 13,768 | Claude Code stream result usage | 13.4 | 3.630 | 0.31% | claude-sonnet-5-5 | standard |
| 17 claude-code sonnet medium | 主统计 | 5 | 5 | 5 | 0 | 0.689 ± 0.175 | 0.078 | 0.472–0.906 | 0 | 0.428 | 0.672 | 0.689 | 0.703 | 0.007 | 0 | 15.5 | 未知 | 174,428 | 8,266,482 | 28,603 | Claude Code stream result usage | 16.8 | 9.050 | 0.78% | claude-sonnet-5-5 | standard |
| 18 claude-code sonnet high | 主统计 | 5 | 5 | 5 | 0 | 0.795 ± 0.076 | 0.034 | 0.700–0.889 | 0 | 0.707 | 0.838 | 0.795 | 0.795 | 0.000 | 0 | 8.4 | 未知 | 225,989 | 982,542 | 56,719 | Claude Code stream result usage | 28.6 | 7.847 | 0.67% | claude-sonnet-5-5 | standard |
| 19 claude-code haiku low | 主统计 | 5 | 5 | 5 | 0 | 0.633 ± 0.063 | 0.028 | 0.555–0.711 | 0 | 0.542 | 0.639 | 0.633 | 0.633 | 0.000 | 0 | 9.7 | 未知 | 312,950 | 960,927 | 129,555 | Claude Code stream result usage | 28.4 | 1.618 | 0.14% | claude-haiku-5-5 | standard |
| 20 claude-code haiku medium | 主统计 | 5 | 5 | 5 | 0 | 0.612 ± 0.140 | 0.063 | 0.438–0.786 | 0 | 0.376 | 0.644 | 0.612 | 0.612 | 0.000 | 0 | 11.2 | 未知 | 331,383 | 1,185,086 | 149,505 | Claude Code stream result usage | 30.0 | 1.798 | 0.15% | claude-haiku-5-5 | standard |
| 21 claude-code haiku high | 主统计 | 5 | 5 | 5 | 0 | 0.590 ± 0.053 | 0.024 | 0.524–0.656 | 0 | 0.518 | 0.585 | 0.590 | 0.590 | 0.000 | 0 | 16.1 | 未知 | 409,900 | 1,615,586 | 221,977 | Claude Code stream result usage | 31.8 | 3.039 | 0.26% | claude-haiku-5-5 | standard |
| 22 claude-code deepseek-flash low | 主统计 | 5 | 5 | 5 | 0 | 0.464 ± 0.270 | 0.121 | 0.129–0.799 | 0 | 0.171 | 0.591 | 0.464 | 0.464 | 0.000 | 0 | 14.9 | 未知 | 131,805 | 1,451,034 | 160,413 | Claude Code stream result usage | 33.4 | 0.602（¥4.012） |  | deepseek-flash | not-returned、standard |
| 23 claude-code deepseek-flash high | 主统计 | 5 | 5 | 5 | 0 | 0.521 ± 0.200 | 0.089 | 0.273–0.769 | 0 | 0.172 | 0.565 | 0.521 | 0.521 | 0.000 | 0 | 24.0 | 未知 | 146,494 | 2,508,902 | 258,314 | Claude Code stream result usage | 44.8 | 0.922（¥6.150） |  | deepseek-flash | not-returned、standard |
| 24 claude-code deepseek-flash max | 主统计 | 5 | 5 | 5 | 0 | 0.253 ± 0.192 | 0.086 | 0.015–0.491 | 0 | 0.160 | 0.174 | 0.253 | 0.253 | 0.000 | 0 | 25.5 | 未知 | 155,435 | 2,221,133 | 303,668 | Claude Code stream result usage | 41.0 | 1.061（¥7.073） |  | deepseek-flash | not-returned、standard |
| 25 claude-code strata-iq3_xxs low | 主统计 | 10 | 10 | 10 | 0 | 0.208 ± 0.082 | 0.026 | 0.149–0.266 | 0 | 0.130 | 0.191 | 0.208 | 0.208 | 0.000 | 0 | 8.8 | 未知 | 151,843 | 2,683,960 | 38,551 | engine log | 43.9 | 0.838 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 25 claude-code strata-iq3_xxs low | 一致性行（前 5） | 10 | 5 | 5 |  | 0.236 ± 0.110 | 0.049 | 0.099–0.373 | 0 | 0.133 | 0.215 | 0.236 | 0.236 | 0.000 | 0 | 9.9 | 未知 | 148,065 | 2,872,861 | 44,815 | engine log | 42.4 | 0.446 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 26 claude-code strata-iq3_xxs medium | 主统计 | 10 | 10 | 10 | 0 | 0.267 ± 0.140 | 0.044 | 0.167–0.367 | 1 | -0.012 | 0.298 | 0.268 | 0.268 | 0.000 | 0 | 10.7 | 未知 | 163,501 | 2,060,149 | 50,583 | engine log | 37.0 | 0.813 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 26 claude-code strata-iq3_xxs medium | 一致性行（前 5） | 10 | 5 | 5 |  | 0.261 ± 0.092 | 0.041 | 0.147–0.375 | 0 | 0.156 | 0.270 | 0.261 | 0.261 | 0.000 | 0 | 10.4 | 未知 | 165,083 | 1,841,376 | 48,486 | engine log | 33.2 | 0.385 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 27 claude-code strata-iq3_xxs high | 主统计 | 10 | 10 | 10 | 1 | 0.294 ± 0.083 | 0.026 | 0.235–0.353 | 0 | 0.164 | 0.288 | 0.294 | 0.294 | 0.000 | 0 | 12.7 | 未知 | 147,138 | 1,714,078 | 62,143 | engine log | 33.9 | 0.787 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 27 claude-code strata-iq3_xxs high | 一致性行（前 5） | 10 | 5 | 5 |  | 0.260 ± 0.089 | 0.040 | 0.150–0.371 | 0 | 0.164 | 0.255 | 0.260 | 0.260 | 0.000 | 0 | 13.1 | 未知 | 146,251 | 1,656,810 | 63,686 | engine log | 32.0 | 0.392 |  | qwen3.8-flash-next-iq3_xxs | not-returned |
| 28 codex gpt-6-luna xhigh | 第三阶段补充（不比较） | 5 | 5 | 5 |  | 0.543 ± 0.069 | 0.031 | 0.458–0.629 | 0 | 0.444 | 0.533 | 0.543 | 0.546 | 0.005 | 0 | 20.0 | 未知 | 326,475 | 5,593,062 | 145,114 | API usage (relay) | 55.8 | 只报 token |  | gpt-6-luna | default |
| 29 codex gpt-6-luna max | 第三阶段补充（不比较） | 5 | 5 | 5 |  | 0.576 ± 0.116 | 0.052 | 0.433–0.720 | 0 | 0.410 | 0.575 | 0.576 | 0.588 | 0.000 | 0 | 25.3 | 未知 | 366,747 | 6,345,370 | 180,215 | API usage (relay) | 55.6 | 只报 token |  | codex-auto-review、gpt-6-luna | default |

### 预登记比较

r8.3 列：同一批实例按 r8.3（截到 0、整体扣减相乘）计分的对照（plan §14.1）。

| 组 | 前者 | 后者 | n | 差值 | SE | t | 自由度 | p | Holm p | 结论 | r8.3 差值 | r8.3 Holm p | r8.3 结论 | 结论改变 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| codex | 10 codex strata-iq3_xxs low | 1 codex gpt-6.1-sol low | 10 / 5 | -0.354 | 0.043 | -8.18 | 11.2 | 0.0000 | 0.0001 | 低于 | -0.354 | 0.0001 | 低于 | 否 |
| codex | 10 codex strata-iq3_xxs low | 4 codex gpt-6-luna low | 10 / 5 | 0.320 | 0.061 | 5.26 | 10.1 | 0.0004 | 0.0039 | 高于 | 0.320 | 0.0039 | 高于 | 否 |
| codex | 10 codex strata-iq3_xxs low | 7 codex deepseek-flash low | 10 / 5 | -0.228 | 0.046 | -5.00 | 12.5 | 0.0003 | 0.0033 | 低于 | -0.228 | 0.0033 | 低于 | 否 |
| codex | 11 codex strata-iq3_xxs medium | 2 codex gpt-6.1-sol medium | 10 / 5 | -0.263 | 0.039 | -6.74 | 8.6 | 0.0001 | 0.0015 | 低于 | -0.263 | 0.0015 | 低于 | 否 |
| codex | 11 codex strata-iq3_xxs medium | 5 codex gpt-6-luna medium | 10 / 5 | 0.261 | 0.086 | 3.03 | 4.7 | 0.0319 | 0.2234 | 未分出 | 0.261 | 0.2234 | 未分出 | 否 |
| codex | 12 codex strata-iq3_xxs high | 3 codex gpt-6.1-sol high | 10 / 5 | -0.271 | 0.039 | -6.87 | 9.7 | 0.0001 | 0.0008 | 低于 | -0.271 | 0.0008 | 低于 | 否 |
| codex | 12 codex strata-iq3_xxs high | 6 codex gpt-6-luna high | 10 / 5 | 0.073 | 0.043 | 1.70 | 8.5 | 0.1264 | 0.5055 | 未分出 | 0.073 | 0.5055 | 未分出 | 否 |
| codex | 12 codex strata-iq3_xxs high | 8 codex deepseek-flash high | 10 / 5 | -0.054 | 0.103 | -0.52 | 4.5 | 0.6279 | 1.0000 | 未分出 | -0.054 | 1.0000 | 未分出 | 否 |
| claude-code | 25 claude-code strata-iq3_xxs low | 13 claude-code opus low | 10 / 5 | -0.457 | 0.041 | -11.26 | 9.4 | 0.0000 | 0.0000 | 低于 | -0.457 | 0.0000 | 低于 | 否 |
| claude-code | 25 claude-code strata-iq3_xxs low | 16 claude-code sonnet low | 10 / 5 | -0.270 | 0.033 | -8.27 | 12.8 | 0.0000 | 0.0000 | 低于 | -0.270 | 0.0000 | 低于 | 否 |
| claude-code | 25 claude-code strata-iq3_xxs low | 19 claude-code haiku low | 10 / 5 | -0.425 | 0.038 | -11.14 | 10.3 | 0.0000 | 0.0000 | 低于 | -0.425 | 0.0000 | 低于 | 否 |
| claude-code | 25 claude-code strata-iq3_xxs low | 22 claude-code deepseek-flash low | 10 / 5 | -0.257 | 0.123 | -2.08 | 4.4 | 0.1002 | 0.5011 | 未分出 | -0.257 | 0.5011 | 未分出 | 否 |
| claude-code | 26 claude-code strata-iq3_xxs medium | 14 claude-code opus medium | 10 / 5 | -0.505 | 0.048 | -10.43 | 11.8 | 0.0000 | 0.0000 | 低于 | -0.503 | 0.0000 | 低于 | 否 |
| claude-code | 26 claude-code strata-iq3_xxs medium | 17 claude-code sonnet medium | 10 / 5 | -0.422 | 0.090 | -4.69 | 6.7 | 0.0025 | 0.0229 | 低于 | -0.420 | 0.0237 | 低于 | 否 |
| claude-code | 26 claude-code strata-iq3_xxs medium | 20 claude-code haiku medium | 10 / 5 | -0.345 | 0.077 | -4.49 | 8.1 | 0.0020 | 0.0196 | 低于 | -0.344 | 0.0202 | 低于 | 否 |
| claude-code | 27 claude-code strata-iq3_xxs high | 15 claude-code opus high | 10 / 5 | -0.518 | 0.030 | -17.32 | 12.7 | 0.0000 | 0.0000 | 低于 | -0.518 | 0.0000 | 低于 | 否 |
| claude-code | 27 claude-code strata-iq3_xxs high | 18 claude-code sonnet high | 10 / 5 | -0.501 | 0.043 | -11.67 | 8.7 | 0.0000 | 0.0000 | 低于 | -0.501 | 0.0000 | 低于 | 否 |
| claude-code | 27 claude-code strata-iq3_xxs high | 21 claude-code haiku high | 10 / 5 | -0.296 | 0.035 | -8.37 | 11.8 | 0.0000 | 0.0001 | 低于 | -0.296 | 0.0001 | 低于 | 否 |
| claude-code | 27 claude-code strata-iq3_xxs high | 23 claude-code deepseek-flash high | 10 / 5 | -0.227 | 0.093 | -2.44 | 4.7 | 0.0619 | 0.3715 | 未分出 | -0.227 | 0.3715 | 未分出 | 否 |
| harness | 10 codex strata-iq3_xxs low | 25 claude-code strata-iq3_xxs low | 10 / 10 | 0.255 | 0.048 | 5.31 | 15.3 | 0.0001 | 0.0012 | 高于 | 0.255 | 0.0012 | 高于 | 否 |
| harness | 11 codex strata-iq3_xxs medium | 26 claude-code strata-iq3_xxs medium | 10 / 10 | 0.254 | 0.050 | 5.07 | 13.7 | 0.0002 | 0.0024 | 高于 | 0.253 | 0.0021 | 高于 | 否 |
| harness | 12 codex strata-iq3_xxs high | 27 claude-code strata-iq3_xxs high | 10 / 10 | 0.238 | 0.037 | 6.51 | 18.0 | 0.0000 | 0.0001 | 高于 | 0.238 | 0.0001 | 高于 | 否 |
| harness | 7 codex deepseek-flash low | 22 claude-code deepseek-flash low | 5 / 5 | 0.227 | 0.123 | 1.85 | 4.2 | 0.1332 | 0.5055 | 未分出 | 0.227 | 0.5055 | 未分出 | 否 |
| harness | 8 codex deepseek-flash high | 23 claude-code deepseek-flash high | 5 / 5 | 0.065 | 0.134 | 0.49 | 7.9 | 0.6408 | 1.0000 | 未分出 | 0.065 | 1.0000 | 未分出 | 否 |
| harness | 9 codex deepseek-flash max | 24 claude-code deepseek-flash max | 5 / 5 | 0.424 | 0.090 | 4.73 | 4.7 | 0.0060 | 0.0479 | 高于 | 0.424 | 0.0479 | 高于 | 否 |

### 逐实例

速度：引擎输入、引擎输出是模型直接速度，任务平均输入、输出是用户感知速度（未缓存输入、输出 ÷ 工作秒数）。API 模型分不出输入处理时间，引擎输入记未知；引擎输出按 API 请求时间算，含首 token 延迟和输入处理，是下限（≥）。

速度汇总口径（用户 2026-10-22）：多个实例的速度（summary.json 各行的 speeds_mean）是总 token ÷ 总耗时（各实例 speed_parts 的分子之和 ÷ 分母之和，speed_totals 给出两者），不是各实例速度的算术平均；任一实例该项未知，汇总即未知；任一实例该项是下限，汇总也是下限。Codex 上的 API 模型（gpt-6.1-sol、gpt-6-luna、DeepSeek）的引擎输出按 relay 日志的 output token ÷ 请求秒数计算，v1 的记录没有保存请求秒数，原始 relay 日志已删除，所以这一项按用户 10-22 的选择近似汇总：分子取实例的输出 token（同样来自 relay usage），分母取 输出 token ÷ 逐实例引擎输出速度 反推的请求秒数；汇总标为近似（speeds_approximate，表中写"≥≈"），仍是下限。

| 配置 | 实例 | 补充 | 有效 | 序 | 主统计 | 分数 | r8.3 分数 | rawScore | f | 修复 | 耗时（分钟） | 占时限 | 未缓存 | 缓存 | 输出 | 工具调用 | 费用（美元；DeepSeek 括号内为人民币 ¥） | 模型 ID | service tier | 引擎输入 tok/s | 引擎输出 tok/s | 任务平均输入 tok/s | 任务平均输出 tok/s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 codex gpt-6.1-sol low | sol-low-a1 |  | 是 | 1 | 是 | 0.847 | 0.847 | 0.847 | 0.000 | 0 | 3.4 | 未知 | 127,581 | 1,208,704 | 8,077 | 22 | 只报 token | gpt-6.1-sol | default | 未知 | ≥40.3 | 631.6 | 40.0 |
| 1 codex gpt-6.1-sol low | sol-low-a2 |  | 是 | 2 | 是 | 0.765 | 0.765 | 0.765 | 0.000 | 0 | 3.7 | 未知 | 139,518 | 1,039,232 | 7,991 | 20 | 只报 token | gpt-6.1-sol | default | 未知 | ≥36.1 | 620.8 | 35.6 |
| 1 codex gpt-6.1-sol low | sol-low-a3 |  | 是 | 3 | 是 | 0.832 | 0.832 | 0.832 | 0.000 | 0 | 5.6 | 未知 | 159,929 | 1,773,184 | 9,873 | 28 | 只报 token | gpt-6.1-sol | default | 未知 | ≥30.0 | 477.5 | 29.5 |
| 1 codex gpt-6.1-sol low | sol-low-a4 |  | 是 | 4 | 是 | 0.801 | 0.801 | 0.801 | 0.000 | 0 | 5.1 | 未知 | 138,823 | 1,238,400 | 9,119 | 21 | 只报 token | gpt-6.1-sol | default | 未知 | ≥31.0 | 453.9 | 29.8 |
| 1 codex gpt-6.1-sol low | sol-low-a5 |  | 是 | 5 | 是 | 0.841 | 0.841 | 0.841 | 0.000 | 0 | 7.4 | 未知 | 163,574 | 2,147,200 | 11,221 | 33 | 只报 token | gpt-6.1-sol | default | 未知 | ≥25.3 | 366.6 | 25.1 |
| 2 codex gpt-6.1-sol medium | sol-medium-a2 |  | 是 | 1 | 是 | 0.679 | 0.679 | 0.679 | 0.000 | 0 | 4.8 | 未知 | 164,523 | 1,549,824 | 11,504 | 26 | 只报 token | gpt-6.1-sol | default | 未知 | ≥40.0 | 566.0 | 39.6 |
| 2 codex gpt-6.1-sol medium | sol-medium-a3 |  | 是 | 2 | 是 | 0.840 | 0.840 | 0.840 | 0.000 | 0 | 4.8 | 未知 | 151,781 | 1,873,408 | 10,504 | 30 | 只报 token | gpt-6.1-sol | default | 未知 | ≥37.0 | 530.6 | 36.7 |
| 2 codex gpt-6.1-sol medium | sol-medium-a4 |  | 是 | 3 | 是 | 0.811 | 0.811 | 0.811 | 0.000 | 0 | 7.1 | 未知 | 158,500 | 1,811,840 | 12,906 | 29 | 只报 token | gpt-6.1-sol | default | 未知 | ≥30.6 | 373.7 | 30.4 |
| 2 codex gpt-6.1-sol medium | sol-medium-a5 |  | 是 | 4 | 是 | 0.842 | 0.842 | 0.842 | 0.000 | 0 | 6.0 | 未知 | 139,018 | 1,524,480 | 10,616 | 26 | 只报 token | gpt-6.1-sol | default | 未知 | ≥29.7 | 386.1 | 29.5 |
| 2 codex gpt-6.1-sol medium | sol-medium-a6 |  | 是 | 5 | 是 | 0.750 | 0.750 | 0.750 | 0.000 | 0 | 8.0 | 未知 | 158,428 | 1,964,928 | 13,361 | 31 | 只报 token | gpt-6.1-sol | default | 未知 | ≥28.2 | 331.8 | 28.0 |
| 2 codex gpt-6.1-sol medium | sol-medium-a1 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 只报 token | 未知 | 未知 | 未知 | ≥39.5 | 未知 | 未知 |
| 3 codex gpt-6.1-sol high | sol-high-a2 |  | 是 | 1 | 是 | 0.821 | 0.821 | 0.821 | 0.000 | 0 | 7.9 | 未知 | 161,171 | 2,247,296 | 18,782 | 35 | 只报 token | gpt-6.1-sol | default | 未知 | ≥40.1 | 339.3 | 39.5 |
| 3 codex gpt-6.1-sol high | sol-high-a3 |  | 是 | 2 | 是 | 0.773 | 0.773 | 0.773 | 0.000 | 0 | 8.9 | 未知 | 164,004 | 2,588,288 | 18,928 | 39 | 只报 token | gpt-6.1-sol | default | 未知 | ≥35.7 | 306.9 | 35.4 |
| 3 codex gpt-6.1-sol high | sol-high-a4 |  | 是 | 3 | 是 | 0.850 | 0.850 | 0.850 | 0.000 | 0 | 8.8 | 未知 | 163,054 | 2,318,208 | 17,134 | 34 | 只报 token | gpt-6.1-sol | default | 未知 | ≥32.4 | 307.4 | 32.3 |
| 3 codex gpt-6.1-sol high | sol-high-a5 |  | 是 | 4 | 是 | 0.702 | 0.702 | 0.702 | 0.000 | 0 | 16.1 | 未知 | 185,024 | 3,534,464 | 29,020 | 48 | 只报 token | gpt-6.1-sol | default | 未知 | ≥30.2 | 191.5 | 30.0 |
| 3 codex gpt-6.1-sol high | sol-high-a6 |  | 是 | 5 | 是 | 0.869 | 0.869 | 0.869 | 0.000 | 0 | 11.5 | 未知 | 187,163 | 3,067,904 | 18,816 | 43 | 只报 token | gpt-6.1-sol | default | 未知 | ≥27.5 | 272.2 | 27.4 |
| 3 codex gpt-6.1-sol high | sol-high-a1 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 只报 token | 未知 | 未知 | 未知 | ≥41.7 | 未知 | 未知 |
| 4 codex gpt-6-luna low | luna-low-a2 |  | 是 | 1 | 是 | 0.209 | 0.209 | 0.209 | 0.000 | 0 | 2.6 | 未知 | 149,877 | 1,481,728 | 11,020 | 28 | 只报 token | gpt-6-luna | default | 未知 | ≥71.0 | 975.2 | 71.7 |
| 4 codex gpt-6-luna low | luna-low-a3 |  | 是 | 2 | 是 | 0.020 | 0.020 | 0.020 | 0.000 | 0 | 3.2 | 未知 | 163,740 | 2,370,944 | 11,882 | 36 | 只报 token | gpt-6-luna | default | 未知 | ≥62.2 | 853.2 | 61.9 |
| 4 codex gpt-6-luna low | luna-low-a4 |  | 是 | 3 | 是 | 0.276 | 0.276 | 0.276 | 0.000 | 0 | 2.9 | 未知 | 169,066 | 1,423,104 | 11,487 | 24 | 只报 token | gpt-6-luna | default | 未知 | ≥66.9 | 974.5 | 66.2 |
| 4 codex gpt-6-luna low | luna-low-a5 |  | 是 | 4 | 是 | 0.125 | 0.125 | 0.125 | 0.000 | 0 | 2.6 | 未知 | 124,321 | 905,216 | 8,118 | 19 | 只报 token | gpt-6-luna | default | 未知 | ≥53.6 | 801.0 | 52.3 |
| 4 codex gpt-6-luna low | luna-low-a6 |  | 是 | 5 | 是 | 0.085 | 0.085 | 0.085 | 0.000 | 0 | 4.0 | 未知 | 189,606 | 2,207,360 | 10,565 | 31 | 只报 token | gpt-6-luna | default | 未知 | ≥44.6 | 791.2 | 44.1 |
| 4 codex gpt-6-luna low | luna-low-a1 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 只报 token | 未知 | 未知 | 未知 | ≥89.6 | 未知 | 未知 |
| 5 codex gpt-6-luna medium | luna-medium-a1 |  | 是 | 1 | 是 | 0.229 | 0.229 | 0.229 | 0.000 | 0 | 1.7 | 未知 | 125,444 | 822,912 | 8,499 | 17 | 只报 token | gpt-6-luna | default | 未知 | ≥85.6 | 1195.5 | 81.0 |
| 5 codex gpt-6-luna medium | luna-medium-a2 |  | 是 | 2 | 是 | 0.111 | 0.111 | 0.111 | 0.000 | 0 | 2.0 | 未知 | 135,739 | 1,288,448 | 8,651 | 22 | 只报 token | gpt-6-luna | default | 未知 | ≥73.6 | 1144.9 | 73.0 |
| 5 codex gpt-6-luna medium | luna-medium-a3 |  | 是 | 3 | 是 | 0.556 | 0.556 | 0.556 | 0.000 | 0 | 4.5 | 未知 | 175,329 | 1,454,848 | 18,160 | 24 | 只报 token | gpt-6-luna | default | 未知 | ≥67.3 | 644.4 | 66.7 |
| 5 codex gpt-6-luna medium | luna-medium-a4 |  | 是 | 4 | 是 | 0.102 | 0.102 | 0.102 | 0.000 | 0 | 2.5 | 未知 | 131,957 | 859,264 | 7,328 | 18 | 只报 token | gpt-6-luna | default | 未知 | ≥50.4 | 892.4 | 49.6 |
| 5 codex gpt-6-luna medium | luna-medium-a5 |  | 是 | 5 | 是 | 0.304 | 0.304 | 0.304 | 0.000 | 0 | 4.5 | 未知 | 132,147 | 1,420,416 | 13,502 | 26 | 只报 token | gpt-6-luna | default | 未知 | ≥50.2 | 487.2 | 49.8 |
| 6 codex gpt-6-luna high | luna-high-a1 |  | 是 | 1 | 是 | 0.375 | 0.375 | 0.375 | 0.000 | 0 | 3.6 | 未知 | 155,618 | 1,608,064 | 18,495 | 28 | 只报 token | gpt-6-luna | default | 未知 | ≥85.8 | 713.5 | 84.8 |
| 6 codex gpt-6-luna high | luna-high-a2 |  | 是 | 2 | 是 | 0.495 | 0.495 | 0.495 | 0.000 | 0 | 3.5 | 未知 | 147,085 | 1,466,112 | 18,852 | 27 | 只报 token | gpt-6-luna | default | 未知 | ≥90.0 | 697.5 | 89.4 |
| 6 codex gpt-6-luna high | luna-high-a4 |  | 是 | 3 | 是 | 0.409 | 0.409 | 0.409 | 0.000 | 0 | 4.8 | 未知 | 169,010 | 1,148,288 | 19,753 | 20 | 只报 token | gpt-6-luna | default | 未知 | ≥67.6 | 581.8 | 68.0 |
| 6 codex gpt-6-luna high | luna-high-a5 |  | 是 | 4 | 是 | 0.447 | 0.447 | 0.447 | 0.000 | 0 | 5.2 | 未知 | 151,791 | 1,215,872 | 18,924 | 22 | 只报 token | gpt-6-luna | default | 未知 | ≥62.3 | 483.8 | 60.3 |
| 6 codex gpt-6-luna high | luna-high-a6 |  | 是 | 5 | 是 | 0.572 | 0.572 | 0.572 | 0.000 | 0 | 6.0 | 未知 | 171,467 | 1,403,392 | 25,633 | 25 | 只报 token | gpt-6-luna | default | 未知 | ≥72.0 | 476.1 | 71.2 |
| 6 codex gpt-6-luna high | luna-high-a3 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 4.5 | 未知 | 150,670 | 997,760 | 17,185 | 20 | 只报 token | gpt-6-luna | default、not-returned | 未知 | ≥66.6 | 555.9 | 63.4 |
| 7 codex deepseek-flash low | codex-low-a2 |  | 是 | 1 | 是 | 0.685 | 0.685 | 0.685 | 0.000 | 0 | 9.6 | 未知 | 136,636 | 3,892,096 | 92,226 | 83 | 0.088（¥0.583） | deepseek-flash | default | 未知 | ≥161.5 | 237.8 | 160.5 |
| 7 codex deepseek-flash low | codex-low-a3 |  | 是 | 2 | 是 | 0.755 | 0.755 | 0.755 | 0.000 | 0 | 10.2 | 未知 | 140,833 | 4,048,512 | 118,726 | 117 | 0.105（¥0.697） | deepseek-flash | default | 未知 | ≥195.3 | 229.7 | 193.6 |
| 7 codex deepseek-flash low | codex-low-a4 |  | 是 | 3 | 是 | 0.667 | 0.667 | 0.667 | 0.000 | 0 | 10.0 | 未知 | 136,210 | 5,043,712 | 110,172 | 98 | 0.102（¥0.678） | deepseek-flash | default | 未知 | ≥185.3 | 227.2 | 183.8 |
| 7 codex deepseek-flash low | codex-low-a6 |  | 是 | 4 | 是 | 0.718 | 0.718 | 0.718 | 0.000 | 0 | 15.1 | 未知 | 154,478 | 3,520,128 | 109,412 | 96 | 0.099（¥0.662） | deepseek-flash | default | 未知 | ≥186.3 | 170.1 | 120.5 |
| 7 codex deepseek-flash low | codex-low-a7 |  | 是 | 5 | 是 | 0.632 | 0.632 | 0.632 | 0.000 | 0 | 10.8 | 未知 | 163,647 | 4,175,744 | 109,704 | 99 | 0.103（¥0.686） | deepseek-flash | default | 未知 | ≥170.6 | 253.3 | 169.8 |
| 7 codex deepseek-flash low | codex-low-a1 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 62.1 | 未知 | 未知 | 未知 | 未知 | 147 | ≥0.559（¥3.724） | deepseek-flash | default、not-returned | 未知 | ≥47.7 | 未知 | 未知 |
| 7 codex deepseek-flash low | codex-low-a5 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 63.7 | 未知 | 未知 | 未知 | 未知 | 138 | ≥0.542（¥3.612） | deepseek-flash | default、not-returned | 未知 | ≥63.1 | 未知 | 未知 |
| 8 codex deepseek-flash high | codex-medium-a1 |  | 是 | 1 | 是 | 0.749 | 0.749 | 0.749 | 0.000 | 0 | 9.6 | 未知 | 123,056 | 4,318,336 | 99,840 | 152 | 0.091（¥0.609） | deepseek-flash | default | 未知 | ≥173.5 | 212.7 | 172.6 |
| 8 codex deepseek-flash high | codex-high-a1 |  | 是 | 2 | 是 | 0.656 | 0.656 | 0.656 | 0.000 | 0 | 12.5 | 未知 | 129,878 | 4,135,424 | 125,681 | 90 | 0.107（¥0.715） | deepseek-flash | default、not-returned | 未知 | ≥168.2 | 173.2 | 167.6 |
| 8 codex deepseek-flash high | codex-high-a2 |  | 是 | 3 | 是 | 0.674 | 0.674 | 0.674 | 0.000 | 0 | 9.4 | 未知 | 132,947 | 3,728,896 | 101,233 | 120 | 0.092（¥0.613） | deepseek-flash | default | 未知 | ≥179.8 | 235.0 | 178.9 |
| 8 codex deepseek-flash high | codex-high-a3 |  | 是 | 4 | 是 | 0.659 | 0.659 | 0.659 | 0.000 | 0 | 10.8 | 未知 | 155,832 | 4,130,432 | 128,829 | 116 | 0.113（¥0.754） | deepseek-flash | default | 未知 | ≥199.9 | 240.3 | 198.6 |
| 8 codex deepseek-flash high | codex-high-a4 |  | 是 | 5 | 是 | 0.192 | 0.192 | 0.213 | 0.000 | 0 | 64.4 | 未知 | 未知 | 未知 | 未知 | 225 | ≥0.696（¥4.640） | deepseek-flash | default、not-returned | 未知 | ≥53.5 | 未知 | 未知 |
| 9 codex deepseek-flash max | codex-max-a1 |  | 是 | 1 | 是 | 0.778 | 0.778 | 0.778 | 0.000 | 0 | 12.7 | 未知 | 177,162 | 6,140,800 | 142,619 | 105 | 0.131（¥0.871） | deepseek-flash | default | 未知 | ≥189.1 | 233.3 | 187.8 |
| 9 codex deepseek-flash max | codex-max-a2 |  | 是 | 2 | 是 | 0.658 | 0.658 | 0.658 | 0.000 | 0 | 13.0 | 未知 | 149,323 | 3,399,552 | 149,319 | 82 | 0.122（¥0.815） | deepseek-flash | default | 未知 | ≥191.7 | 190.8 | 190.8 |
| 9 codex deepseek-flash max | codex-max-a3 |  | 是 | 3 | 是 | 0.633 | 0.633 | 0.633 | 0.000 | 0 | 11.0 | 未知 | 170,832 | 2,975,232 | 128,560 | 91 | 0.112（¥0.745） | deepseek-flash | default、not-returned | 未知 | ≥196.4 | 259.8 | 195.5 |
| 9 codex deepseek-flash max | codex-max-a4 |  | 是 | 4 | 是 | 0.672 | 0.672 | 0.672 | 0.000 | 0 | 12.7 | 未知 | 143,623 | 4,453,888 | 146,685 | 114 | 0.123（¥0.819） | deepseek-flash | default、not-returned | 未知 | ≥193.9 | 188.8 | 192.8 |
| 9 codex deepseek-flash max | codex-max-a5 |  | 是 | 5 | 是 | 0.645 | 0.645 | 0.645 | 0.000 | 0 | 12.9 | 未知 | 156,157 | 4,795,776 | 132,376 | 96 | 0.117（¥0.782） | deepseek-flash | default | 未知 | ≥172.4 | 202.3 | 171.5 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a1 |  | 是 | 1 | 是 | 0.457 | 0.457 | 0.457 | 0.000 | 0 | 14.3 | 未知 | 161,646 | 4,949,725 | 62,325 | 69 | 0.133 | 未知 | 未知 | 1499.8 | 89.8 | 188.8 | 72.8 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a2 |  | 是 | 2 | 是 | 0.416 | 0.416 | 0.416 | 0.000 | 0 | 15.0 | 未知 | 160,337 | 4,314,054 | 62,009 | 58 | 0.122 | 未知 | 未知 | 1526.6 | 84.0 | 178.7 | 69.1 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a3 |  | 是 | 3 | 是 | 0.551 | 0.551 | 0.551 | 0.000 | 0 | 15.1 | 未知 | 145,387 | 5,038,465 | 65,992 | 72 | 0.133 | 未知 | 未知 | 1439.8 | 88.0 | 160.5 | 72.8 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a4 |  | 是 | 4 | 是 | 0.370 | 0.370 | 0.370 | 0.000 | 0 | 8.9 | 未知 | 129,468 | 2,433,637 | 36,906 | 46 | 0.076 | 未知 | 未知 | 1689.2 | 91.6 | 243.2 | 69.3 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a5 |  | 是 | 5 | 是 | 0.658 | 0.658 | 0.658 | 0.000 | 0 | 13.0 | 未知 | 134,596 | 4,114,854 | 56,620 | 54 | 0.113 | 未知 | 未知 | 1450.3 | 89.7 | 173.1 | 72.8 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a6 |  | 是 | 6 | 是 | 0.540 | 0.540 | 0.540 | 0.000 | 0 | 11.8 | 未知 | 152,196 | 3,556,149 | 49,742 | 53 | 0.103 | 未知 | 未知 | 1606.2 | 88.6 | 214.6 | 70.1 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a7 |  | 是 | 7 | 是 | 0.369 | 0.369 | 0.369 | 0.000 | 0 | 13.4 | 未知 | 156,451 | 3,925,338 | 58,669 | 60 | 0.114 | 未知 | 未知 | 1571.9 | 89.8 | 193.9 | 72.7 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a8 |  | 是 | 8 | 是 | 0.327 | 0.327 | 0.327 | 0.000 | 0 | 8.6 | 未知 | 125,498 | 2,241,685 | 34,926 | 41 | 0.071 | 未知 | 未知 | 1675.2 | 90.4 | 244.5 | 68.0 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a9 |  | 是 | 9 | 是 | 0.641 | 0.641 | 0.641 | 0.000 | 0 | 11.7 | 未知 | 159,460 | 3,586,360 | 48,324 | 52 | 0.104 | 未知 | 未知 | 1639.1 | 87.7 | 227.6 | 69.0 |
| 10 codex strata-iq3_xxs low | codex-strata-low-a10 |  | 是 | 10 | 是 | 0.301 | 0.301 | 0.301 | 0.000 | 0 | 9.6 | 未知 | 114,913 | 2,607,408 | 41,096 | 52 | 0.078 | 未知 | 未知 | 1542.6 | 91.2 | 198.7 | 71.1 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a1 |  | 是 | 1 | 是 | 0.582 | 0.582 | 0.582 | 0.000 | 0 | 14.5 | 未知 | 157,035 | 3,456,807 | 62,316 | 51 | 0.108 | 未知 | 未知 | 1542.9 | 86.8 | 180.1 | 71.5 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a2 |  | 是 | 2 | 是 | 0.473 | 0.473 | 0.473 | 0.000 | 0 | 13.1 | 未知 | 136,564 | 3,742,636 | 56,182 | 60 | 0.107 | 未知 | 未知 | 1513.3 | 87.3 | 173.6 | 71.4 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a3 |  | 是 | 3 | 是 | 0.654 | 0.654 | 0.654 | 0.000 | 0 | 16.0 | 未知 | 152,999 | 3,899,283 | 69,819 | 57 | 0.118 | 未知 | 未知 | 1528.8 | 86.5 | 159.4 | 72.7 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a4 |  | 是 | 4 | 是 | 0.563 | 0.563 | 0.563 | 0.000 | 0 | 13.7 | 未知 | 142,337 | 3,380,377 | 59,007 | 54 | 0.103 | 未知 | 未知 | 1547.1 | 87.2 | 173.2 | 71.8 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a5 |  | 是 | 5 | 是 | 0.548 | 0.548 | 0.548 | 0.000 | 0 | 10.3 | 未知 | 143,862 | 2,199,538 | 42,026 | 44 | 0.077 | 未知 | 未知 | 1706.7 | 87.4 | 233.3 | 68.2 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a6 |  | 是 | 6 | 是 | 0.517 | 0.517 | 0.517 | 0.000 | 0 | 15.2 | 未知 | 139,290 | 2,940,159 | 60,715 | 44 | 0.096 | 未知 | 未知 | 1535.2 | 78.9 | 152.5 | 66.5 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a7 |  | 是 | 7 | 是 | 0.477 | 0.477 | 0.477 | 0.000 | 0 | 11.8 | 未知 | 137,330 | 2,824,466 | 49,638 | 52 | 0.089 | 未知 | 未知 | 1661.1 | 86.4 | 193.4 | 69.9 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a8 |  | 是 | 8 | 是 | 0.396 | 0.396 | 0.396 | 0.000 | 0 | 13.9 | 未知 | 162,722 | 3,372,511 | 56,670 | 59 | 0.105 | 未知 | 未知 | 1505.8 | 84.1 | 194.6 | 67.8 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a9 |  | 是 | 9 | 是 | 0.449 | 0.449 | 0.449 | 0.000 | 0 | 10.5 | 未知 | 131,747 | 2,288,762 | 42,362 | 41 | 0.076 | 未知 | 未知 | 1678.2 | 85.3 | 210.0 | 67.5 |
| 11 codex strata-iq3_xxs medium | codex-strata-medium-a10 |  | 是 | 10 | 是 | 0.553 | 0.553 | 0.553 | 0.000 | 0 | 14.4 | 未知 | 146,349 | 3,445,255 | 64,246 | 50 | 0.107 | 未知 | 未知 | 1644.6 | 89.5 | 169.8 | 74.5 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a1 |  | 是 | 1 | 是 | 0.534 | 0.534 | 0.534 | 0.000 | 0 | 14.5 | 未知 | 127,882 | 2,942,328 | 61,978 | 54 | 0.095 | 未知 | 未知 | 1534.1 | 84.4 | 147.1 | 71.3 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a2 |  | 是 | 2 | 是 | 0.487 | 0.487 | 0.487 | 0.000 | 0 | 16.9 | 未知 | 179,382 | 3,309,990 | 73,899 | 56 | 0.115 | 未知 | 未知 | 1699.4 | 86.2 | 176.9 | 72.9 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a3 |  | 是 | 3 | 是 | 0.566 | 0.566 | 0.566 | 0.000 | 0 | 15.5 | 未知 | 166,554 | 2,614,611 | 66,837 | 48 | 0.098 | 未知 | 未知 | 1700.0 | 85.4 | 178.7 | 71.7 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a4 |  | 是 | 4 | 是 | 0.373 | 0.373 | 0.373 | 0.000 | 0 | 10.4 | 未知 | 121,327 | 2,266,976 | 44,727 | 50 | 0.075 | 未知 | 未知 | 1577.3 | 90.1 | 194.2 | 71.6 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a5 |  | 是 | 5 | 是 | 0.513 | 0.513 | 0.513 | 0.000 | 0 | 12.0 | 未知 | 135,798 | 2,208,278 | 51,623 | 46 | 0.080 | 未知 | 未知 | 1750.2 | 87.3 | 188.8 | 71.8 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a6 |  | 是 | 6 | 是 | 0.562 | 0.562 | 0.562 | 0.000 | 0 | 12.0 | 未知 | 128,311 | 2,338,447 | 54,084 | 46 | 0.082 | 未知 | 未知 | 1656.6 | 91.3 | 177.5 | 74.8 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a7 |  | 是 | 7 | 是 | 0.663 | 0.663 | 0.663 | 0.000 | 0 | 14.2 | 未知 | 137,671 | 2,970,737 | 61,795 | 51 | 0.097 | 未知 | 未知 | 1671.5 | 86.3 | 161.7 | 72.6 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a8 |  | 是 | 8 | 是 | 0.455 | 0.455 | 0.455 | 0.000 | 0 | 12.9 | 未知 | 128,072 | 2,270,887 | 59,108 | 48 | 0.083 | 未知 | 未知 | 1627.0 | 92.7 | 166.1 | 76.6 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a9 |  | 是 | 9 | 是 | 0.568 | 0.568 | 0.568 | 0.000 | 0 | 16.3 | 未知 | 149,277 | 2,353,854 | 70,728 | 45 | 0.093 | 未知 | 未知 | 1711.9 | 84.1 | 152.3 | 72.2 |
| 12 codex strata-iq3_xxs high | codex-strata-high-a10 |  | 是 | 10 | 是 | 0.602 | 0.602 | 0.602 | 0.000 | 0 | 17.4 | 未知 | 151,632 | 2,706,681 | 77,415 | 48 | 0.102 | 未知 | 未知 | 1685.1 | 85.8 | 144.9 | 74.0 |
| 13 claude-code opus low | opus-low-a1 |  | 是 | 1 | 是 | 0.733 | 0.733 | 0.733 | 0.000 | 0 | 4.5 | 未知 | 127,073 | 499,911 | 11,058 | 11 | 1.338 | claude-opus-5-5 | standard | 未知 | ≥84.6 | 475.8 | 41.4 |
| 13 claude-code opus low | opus-low-a2 |  | 是 | 2 | 是 | 0.730 | 0.730 | 0.730 | 0.000 | 0 | 5.1 | 未知 | 121,683 | 628,602 | 10,641 | 13 | 1.312 | claude-opus-5-5 | standard | 未知 | ≥66.9 | 393.9 | 34.4 |
| 13 claude-code opus low | opus-low-a3 |  | 是 | 3 | 是 | 0.643 | 0.643 | 0.643 | 0.000 | 0 | 5.4 | 未知 | 118,537 | 555,330 | 11,876 | 12 | 1.297 | claude-opus-5-5 | standard | 未知 | ≥78.2 | 367.5 | 36.8 |
| 13 claude-code opus low | opus-low-a4 |  | 是 | 4 | 是 | 0.564 | 0.564 | 0.564 | 0.000 | 0 | 4.0 | 未知 | 122,024 | 482,122 | 11,397 | 11 | 1.300 | claude-opus-5-5 | standard | 未知 | ≥86.2 | 514.8 | 48.1 |
| 13 claude-code opus low | opus-low-a5 |  | 是 | 5 | 是 | 0.654 | 0.654 | 0.654 | 0.000 | 0 | 8.1 | 未知 | 118,798 | 479,612 | 11,991 | 11 | 1.286 | claude-opus-5-5 | standard | 未知 | ≥35.0 | 245.2 | 24.7 |
| 14 claude-code opus medium | opus-medium-a1 |  | 是 | 1 | 是 | 0.798 | 0.798 | 0.798 | 0.000 | 0 | 9.0 | 未知 | 162,097 | 1,047,014 | 26,538 | 21 | 2.037 | claude-opus-5-5 | standard | 未知 | ≥75.7 | 301.3 | 49.3 |
| 14 claude-code opus medium | opus-medium-a2 |  | 是 | 2 | 是 | 0.830 | 0.830 | 0.830 | 0.000 | 0 | 12.9 | 未知 | 166,198 | 1,169,552 | 34,439 | 23 | 2.252 | claude-opus-5-5 | standard | 未知 | ≥71.8 | 215.0 | 44.6 |
| 14 claude-code opus medium | opus-medium-a3 |  | 是 | 3 | 是 | 0.720 | 0.720 | 0.720 | 0.000 | 0 | 10.1 | 未知 | 168,094 | 1,092,251 | 31,001 | 20 | 2.183 | claude-opus-5-5 | standard | 未知 | ≥89.4 | 277.3 | 51.1 |
| 14 claude-code opus medium | opus-medium-a4 |  | 是 | 4 | 是 | 0.768 | 0.768 | 0.768 | 0.000 | 0 | 13.4 | 未知 | 170,961 | 1,036,294 | 34,978 | 18 | 2.274 | claude-opus-5-5 | standard | 未知 | ≥63.0 | 212.6 | 43.5 |
| 14 claude-code opus medium | opus-medium-a5 |  | 是 | 5 | 是 | 0.743 | 0.743 | 0.743 | 0.000 | 0 | 10.7 | 未知 | 173,333 | 1,324,248 | 30,447 | 23 | 2.260 | claude-opus-5-5 | standard | 未知 | ≥69.0 | 269.9 | 47.4 |
| 15 claude-code opus high | opus-high-a1 |  | 是 | 1 | 是 | 0.764 | 0.764 | 0.764 | 0.000 | 0 | 11.9 | 未知 | 217,991 | 1,783,635 | 50,244 | 26 | 3.105 | claude-opus-5-5 | standard | 未知 | ≥91.6 | 305.3 | 70.4 |
| 15 claude-code opus high | opus-high-a2 |  | 是 | 2 | 是 | 0.837 | 0.837 | 0.837 | 0.000 | 0 | 14.2 | 未知 | 236,934 | 1,498,354 | 55,427 | 29 | 3.304 | claude-opus-5-5 | standard | 未知 | ≥94.6 | 277.9 | 65.0 |
| 15 claude-code opus high | opus-high-a3 |  | 是 | 3 | 是 | 0.847 | 0.847 | 0.847 | 0.000 | 0 | 10.8 | 未知 | 235,739 | 1,518,848 | 49,573 | 30 | 3.181 | claude-opus-5-5 | standard | 未知 | ≥96.8 | 365.5 | 76.9 |
| 15 claude-code opus high | opus-high-a4 |  | 是 | 4 | 是 | 0.812 | 0.812 | 0.812 | 0.000 | 0 | 17.5 | 未知 | 219,538 | 1,767,056 | 56,466 | 31 | 3.239 | claude-opus-5-5 | standard | 未知 | ≥65.9 | 208.7 | 53.7 |
| 15 claude-code opus high | opus-high-a5 |  | 是 | 5 | 是 | 0.801 | 0.801 | 0.801 | 0.000 | 0 | 11.1 | 未知 | 199,946 | 1,485,151 | 48,103 | 32 | 2.858 | claude-opus-5-5 | standard | 未知 | ≥86.1 | 300.2 | 72.2 |
| 16 claude-code sonnet low | sonnet-low-a1 |  | 是 | 1 | 是 | 0.468 | 0.468 | 0.468 | 0.000 | 0 | 2.3 | 未知 | 132,008 | 345,858 | 9,836 | 12 | 0.661 | claude-sonnet-5-5 | standard | 未知 | ≥116.4 | 944.9 | 70.4 |
| 16 claude-code sonnet low | sonnet-low-a2 |  | 是 | 2 | 是 | 0.426 | 0.426 | 0.426 | 0.000 | 0 | 3.5 | 未知 | 131,340 | 414,966 | 14,449 | 11 | 0.711 | claude-sonnet-5-5 | standard | 未知 | ≥95.4 | 622.4 | 68.5 |
| 16 claude-code sonnet low | sonnet-low-a3 |  | 是 | 3 | 是 | 0.542 | 0.542 | 0.542 | 0.000 | 0 | 2.4 | 未知 | 126,855 | 494,528 | 9,304 | 13 | 0.650 | claude-sonnet-5-5 | standard | 未知 | ≥78.4 | 869.6 | 63.8 |
| 16 claude-code sonnet low | sonnet-low-a4 |  | 是 | 4 | 是 | 0.453 | 0.453 | 0.453 | 0.000 | 0 | 3.5 | 未知 | 132,399 | 639,136 | 14,847 | 14 | 0.742 | claude-sonnet-5-5 | standard | 未知 | ≥101.1 | 622.4 | 69.8 |
| 16 claude-code sonnet low | sonnet-low-a5 |  | 是 | 5 | 是 | 0.498 | 0.498 | 0.498 | 0.000 | 0 | 4.0 | 未知 | 139,830 | 1,024,434 | 20,402 | 17 | 0.866 | claude-sonnet-5-5 | standard | 未知 | ≥109.1 | 583.2 | 85.1 |
| 17 claude-code sonnet medium | sonnet-medium-a1 |  | 是 | 1 | 是 | 0.864 | 0.864 | 0.864 | 0.000 | 0 | 4.6 | 未知 | 191,032 | 737,945 | 34,501 | 22 | 1.183 | claude-sonnet-5-5 | standard | 未知 | ≥132.4 | 698.8 | 126.2 |
| 17 claude-code sonnet medium | sonnet-medium-a2 |  | 是 | 2 | 是 | 0.836 | 0.836 | 0.836 | 0.000 | 0 | 3.9 | 未知 | 165,671 | 407,536 | 28,303 | 15 | 0.986 | claude-sonnet-5-5 | standard | 未知 | ≥129.2 | 699.6 | 119.5 |
| 17 claude-code sonnet medium | sonnet-medium-a3 |  | 是 | 3 | 是 | 0.428 | 0.428 | 0.428 | 0.000 | 0 | 3.6 | 未知 | 154,510 | 468,405 | 18,510 | 15 | 0.850 | claude-sonnet-5-5 | standard | 未知 | ≥113.1 | 724.4 | 86.8 |
| 17 claude-code sonnet medium | sonnet-medium-a4 |  | 是 | 4 | 是 | 0.672 | 0.672 | 0.672 | 0.000 | 0 | 3.5 | 未知 | 147,727 | 303,148 | 24,191 | 12 | 0.863 | claude-sonnet-5-5 | standard | 未知 | ≥127.8 | 701.0 | 114.8 |
| 17 claude-code sonnet medium | sonnet-medium-a5 |  | 是 | 5 | 是 | 0.645 | 0.645 | 0.717 | 0.037 | 0 | 62.0 | 未知 | 213,201 | 39,415,377 | 37,509 | 20 | 5.168 | claude-sonnet-5-5 | standard | 未知 | ≥25.3 | 57.3 | 10.1 |
| 18 claude-code sonnet high | sonnet-high-a1 |  | 是 | 1 | 是 | 0.867 | 0.867 | 0.867 | 0.000 | 0 | 7.6 | 未知 | 231,060 | 1,075,614 | 53,944 | 30 | 1.571 | claude-sonnet-5-5 | standard | 未知 | ≥133.4 | 506.1 | 118.2 |
| 18 claude-code sonnet high | sonnet-high-a2 |  | 是 | 2 | 是 | 0.844 | 0.844 | 0.844 | 0.000 | 0 | 9.6 | 未知 | 236,823 | 1,235,748 | 61,279 | 30 | 1.684 | claude-sonnet-5-5 | standard | 未知 | ≥126.6 | 410.4 | 106.2 |
| 18 claude-code sonnet high | sonnet-high-a3 |  | 是 | 3 | 是 | 0.707 | 0.707 | 0.707 | 0.000 | 0 | 9.1 | 未知 | 223,965 | 732,083 | 63,188 | 26 | 1.601 | claude-sonnet-5-5 | standard | 未知 | ≥131.3 | 411.8 | 116.2 |
| 18 claude-code sonnet high | sonnet-high-a4 |  | 是 | 4 | 是 | 0.718 | 0.718 | 0.718 | 0.000 | 0 | 7.2 | 未知 | 216,410 | 924,489 | 49,425 | 28 | 1.452 | claude-sonnet-5-5 | standard | 未知 | ≥128.0 | 503.0 | 114.9 |
| 18 claude-code sonnet high | sonnet-high-a5 |  | 是 | 5 | 是 | 0.838 | 0.838 | 0.838 | 0.000 | 0 | 8.8 | 未知 | 221,689 | 944,777 | 55,758 | 29 | 1.539 | claude-sonnet-5-5 | standard | 未知 | ≥130.4 | 421.5 | 106.0 |
| 19 claude-code haiku low | haiku-low-a1 |  | 是 | 1 | 是 | 0.639 | 0.639 | 0.639 | 0.000 | 0 | 8.8 | 未知 | 295,302 | 856,346 | 114,346 | 28 | 0.271 | claude-haiku-5-5 | standard | 未知 | ≥234.0 | 560.3 | 217.0 |
| 19 claude-code haiku low | haiku-low-a2 |  | 是 | 2 | 是 | 0.542 | 0.542 | 0.542 | 0.000 | 0 | 8.6 | 未知 | 296,234 | 1,028,028 | 113,934 | 29 | 0.278 | claude-haiku-5-5 | standard | 未知 | ≥235.0 | 576.5 | 221.7 |
| 19 claude-code haiku low | haiku-low-a3 |  | 是 | 3 | 是 | 0.708 | 0.708 | 0.708 | 0.000 | 0 | 10.0 | 未知 | 323,610 | 1,036,321 | 133,879 | 29 | 0.330 | claude-haiku-5-5 | standard | 未知 | ≥238.4 | 541.2 | 223.9 |
| 19 claude-code haiku low | haiku-low-a4 |  | 是 | 4 | 是 | 0.607 | 0.607 | 0.607 | 0.000 | 0 | 9.4 | 未知 | 309,619 | 1,000,783 | 125,689 | 28 | 0.317 | claude-haiku-5-5 | standard | 未知 | ≥233.2 | 549.3 | 223.0 |
| 19 claude-code haiku low | haiku-low-a5 |  | 是 | 5 | 是 | 0.668 | 0.668 | 0.668 | 0.000 | 0 | 11.9 | 未知 | 339,987 | 883,156 | 159,927 | 28 | 0.422 | claude-haiku-5-5 | standard | 未知 | ≥240.2 | 476.3 | 224.1 |
| 20 claude-code haiku medium | haiku-medium-a1 |  | 是 | 1 | 是 | 0.644 | 0.644 | 0.644 | 0.000 | 0 | 10.0 | 未知 | 313,972 | 1,206,922 | 137,698 | 29 | 0.338 | claude-haiku-5-5 | standard | 未知 | ≥238.1 | 521.4 | 228.6 |
| 20 claude-code haiku medium | haiku-medium-a2 |  | 是 | 2 | 是 | 0.642 | 0.642 | 0.642 | 0.000 | 0 | 10.4 | 未知 | 329,677 | 1,273,012 | 138,403 | 31 | 0.362 | claude-haiku-5-5 | standard | 未知 | ≥232.2 | 527.5 | 221.5 |
| 20 claude-code haiku medium | haiku-medium-a3 |  | 是 | 3 | 是 | 0.646 | 0.646 | 0.646 | 0.000 | 0 | 11.1 | 未知 | 328,935 | 745,859 | 154,688 | 28 | 0.316 | claude-haiku-5-5 | standard | 未知 | ≥241.7 | 495.4 | 233.0 |
| 20 claude-code haiku medium | haiku-medium-a4 |  | 是 | 4 | 是 | 0.752 | 0.752 | 0.752 | 0.000 | 0 | 13.5 | 未知 | 357,024 | 1,947,550 | 164,200 | 34 | 0.482 | claude-haiku-5-5 | standard | 未知 | ≥236.6 | 442.3 | 203.4 |
| 20 claude-code haiku medium | haiku-medium-a5 |  | 是 | 5 | 是 | 0.376 | 0.376 | 0.376 | 0.000 | 0 | 11.1 | 未知 | 327,309 | 752,088 | 152,534 | 28 | 0.301 | claude-haiku-5-5 | standard | 未知 | ≥237.3 | 490.1 | 228.4 |
| 21 claude-code haiku high | haiku-high-a1 |  | 是 | 1 | 是 | 0.646 | 0.646 | 0.646 | 0.000 | 0 | 17.0 | 未知 | 423,344 | 2,761,962 | 216,454 | 39 | 0.745 | claude-haiku-5-5 | standard | 未知 | ≥224.2 | 414.7 | 212.0 |
| 21 claude-code haiku high | haiku-high-a2 |  | 是 | 2 | 是 | 0.585 | 0.585 | 0.585 | 0.000 | 0 | 17.1 | 未知 | 435,361 | 2,081,191 | 231,939 | 34 | 0.603 | claude-haiku-5-5 | standard | 未知 | ≥239.1 | 424.0 | 225.9 |
| 21 claude-code haiku high | haiku-high-a3 |  | 是 | 3 | 是 | 0.518 | 0.518 | 0.518 | 0.000 | 0 | 13.5 | 未知 | 370,111 | 1,120,179 | 195,346 | 30 | 0.396 | claude-haiku-5-5 | standard | 未知 | ≥250.8 | 456.0 | 240.7 |
| 21 claude-code haiku high | haiku-high-a4 |  | 是 | 4 | 是 | 0.638 | 0.638 | 0.638 | 0.000 | 0 | 17.4 | 未知 | 422,395 | 991,191 | 248,150 | 28 | 0.680 | claude-haiku-5-5 | standard | 未知 | ≥243.7 | 404.6 | 237.7 |
| 21 claude-code haiku high | haiku-high-a5 |  | 是 | 5 | 是 | 0.564 | 0.564 | 0.564 | 0.000 | 0 | 15.4 | 未知 | 398,287 | 1,123,408 | 217,998 | 28 | 0.616 | claude-haiku-5-5 | standard | 未知 | ≥240.8 | 429.9 | 235.3 |
| 22 claude-code deepseek-flash low | cc-low-a1 |  | 是 | 1 | 是 | 0.704 | 0.704 | 0.704 | 0.000 | 0 | 14.4 | 未知 | 134,272 | 1,803,136 | 126,897 | 38 | 0.102（¥0.678） | deepseek-flash | standard | 未知 | ≥196.3 | 155.4 | 146.8 |
| 22 claude-code deepseek-flash low | cc-low-a2 |  | 是 | 2 | 是 | 0.682 | 0.682 | 0.682 | 0.000 | 0 | 15.4 | 未知 | 140,023 | 1,846,016 | 183,568 | 37 | 0.137（¥0.911） | deepseek-flash | standard | 未知 | ≥214.0 | 151.4 | 198.5 |
| 22 claude-code deepseek-flash low | cc-low-a3 |  | 是 | 3 | 是 | 0.171 | 0.171 | 0.171 | 0.000 | 0 | 13.8 | 未知 | 127,230 | 982,912 | 167,355 | 29 | 0.122（¥0.816） | deepseek-flash | not-returned、standard | 未知 | ≥205.4 | 153.2 | 201.5 |
| 22 claude-code deepseek-flash low | cc-low-a4 |  | 是 | 4 | 是 | 0.174 | 0.174 | 0.174 | 0.000 | 0 | 16.7 | 未知 | 127,181 | 1,264,384 | 189,073 | 30 | 0.136（¥0.909） | deepseek-flash | not-returned、standard | 未知 | ≥215.1 | 126.8 | 188.5 |
| 22 claude-code deepseek-flash low | cc-low-a5 |  | 是 | 5 | 是 | 0.591 | 0.591 | 0.591 | 0.000 | 0 | 14.2 | 未知 | 130,321 | 1,358,720 | 135,170 | 33 | 0.105（¥0.698） | deepseek-flash | standard | 未知 | ≥211.0 | 152.6 | 158.2 |
| 23 claude-code deepseek-flash high | cc-medium-a1 |  | 是 | 1 | 是 | 0.649 | 0.649 | 0.649 | 0.000 | 0 | 16.7 | 未知 | 140,262 | 2,597,376 | 169,217 | 45 | 0.130（¥0.869） | deepseek-flash | standard | 未知 | ≥207.5 | 140.0 | 168.9 |
| 23 claude-code deepseek-flash high | cc-high-a1 |  | 是 | 2 | 是 | 0.564 | 0.564 | 0.564 | 0.000 | 0 | 29.0 | 未知 | 188,870 | 2,887,936 | 303,006 | 56 | 0.219（¥1.459） | deepseek-flash | standard | 未知 | ≥206.9 | 108.4 | 174.0 |
| 23 claude-code deepseek-flash high | cc-high-a2 |  | 是 | 3 | 是 | 0.172 | 0.172 | 0.172 | 0.000 | 0 | 28.7 | 未知 | 142,736 | 2,178,816 | 341,845 | 37 | 0.233（¥1.554） | deepseek-flash | not-returned、standard | 未知 | ≥214.7 | 82.9 | 198.6 |
| 23 claude-code deepseek-flash high | cc-high-a3 |  | 是 | 4 | 是 | 0.565 | 0.565 | 0.565 | 0.000 | 0 | 24.3 | 未知 | 135,051 | 2,964,480 | 249,481 | 47 | 0.179（¥1.192） | deepseek-flash | standard | 未知 | ≥205.9 | 92.7 | 171.2 |
| 23 claude-code deepseek-flash high | cc-high-a4 |  | 是 | 5 | 是 | 0.654 | 0.654 | 0.654 | 0.000 | 0 | 21.1 | 未知 | 125,549 | 1,915,904 | 228,021 | 39 | 0.161（¥1.076） | deepseek-flash | standard | 未知 | ≥211.8 | 99.1 | 179.9 |
| 24 claude-code deepseek-flash max | cc-max-a1 |  | 是 | 1 | 是 | 0.160 | 0.160 | 0.160 | 0.000 | 0 | 22.5 | 未知 | 135,250 | 2,107,648 | 277,875 | 36 | 0.193（¥1.289） | deepseek-flash | not-returned、standard | 未知 | ≥217.7 | 100.2 | 205.8 |
| 24 claude-code deepseek-flash max | cc-max-a2 |  | 是 | 2 | 是 | 0.163 | 0.163 | 0.163 | 0.000 | 0 | 20.8 | 未知 | 120,519 | 1,028,864 | 238,971 | 29 | 0.165（¥1.097） | deepseek-flash | not-returned、standard | 未知 | ≥205.2 | 96.6 | 191.5 |
| 24 claude-code deepseek-flash max | cc-max-a3 |  | 是 | 3 | 是 | 0.596 | 0.596 | 0.596 | 0.000 | 0 | 40.4 | 未知 | 249,553 | 3,792,896 | 463,083 | 64 | 0.327（¥2.178） | deepseek-flash | standard | 未知 | ≥211.3 | 102.9 | 190.9 |
| 24 claude-code deepseek-flash max | cc-max-a4 |  | 是 | 4 | 是 | 0.174 | 0.174 | 0.174 | 0.000 | 0 | 17.0 | 未知 | 126,846 | 926,464 | 224,046 | 27 | 0.156（¥1.042） | deepseek-flash | not-returned、standard | 未知 | ≥225.3 | 124.4 | 219.7 |
| 24 claude-code deepseek-flash max | cc-max-a5 |  | 是 | 5 | 是 | 0.174 | 0.174 | 0.174 | 0.000 | 0 | 26.5 | 未知 | 145,008 | 3,249,792 | 314,367 | 49 | 0.220（¥1.468） | deepseek-flash | not-returned、standard | 未知 | ≥217.3 | 91.0 | 197.3 |
| 25 claude-code strata-iq3_xxs low | strata-low-a1 |  | 是 | 1 | 是 | 0.141 | 0.141 | 0.141 | 0.000 | 0 | 12.8 | 未知 | 143,531 | 2,986,240 | 62,182 | 41 | 0.099 | qwen3.8-flash-next-iq3_xxs | not-returned | 1823.8 | 91.2 | 186.3 | 80.7 |
| 25 claude-code strata-iq3_xxs low | strata-low-a2 |  | 是 | 2 | 是 | 0.133 | 0.133 | 0.133 | 0.000 | 0 | 10.3 | 未知 | 141,559 | 3,037,451 | 46,833 | 43 | 0.092 | qwen3.8-flash-next-iq3_xxs | not-returned | 1758.1 | 88.5 | 229.6 | 76.0 |
| 25 claude-code strata-iq3_xxs low | strata-low-a3 |  | 是 | 3 | 是 | 0.393 | 0.393 | 0.393 | 0.000 | 0 | 9.8 | 未知 | 163,905 | 3,928,331 | 41,605 | 57 | 0.107 | qwen3.8-flash-next-iq3_xxs | not-returned | 1645.6 | 88.3 | 278.9 | 70.8 |
| 25 claude-code strata-iq3_xxs low | strata-low-a4 |  | 是 | 4 | 是 | 0.215 | 0.215 | 0.215 | 0.000 | 0 | 9.6 | 未知 | 141,832 | 2,389,646 | 42,857 | 37 | 0.080 | qwen3.8-flash-next-iq3_xxs | not-returned | 1878.8 | 87.0 | 245.7 | 74.3 |
| 25 claude-code strata-iq3_xxs low | strata-low-a5 |  | 是 | 5 | 是 | 0.300 | 0.300 | 0.300 | 0.000 | 0 | 7.2 | 未知 | 149,500 | 2,022,636 | 30,598 | 34 | 0.069 | qwen3.8-flash-next-iq3_xxs | not-returned | 2008.1 | 87.2 | 345.8 | 70.8 |
| 25 claude-code strata-iq3_xxs low | strata-low-a6 |  | 是 | 6 | 是 | 0.189 | 0.189 | 0.189 | 0.000 | 0 | 6.9 | 未知 | 160,624 | 1,853,352 | 30,305 | 37 | 0.068 | qwen3.8-flash-next-iq3_xxs | not-returned | 1867.2 | 95.4 | 390.4 | 73.7 |
| 25 claude-code strata-iq3_xxs low | strata-low-a7 |  | 是 | 7 | 是 | 0.130 | 0.130 | 0.130 | 0.000 | 0 | 6.7 | 未知 | 136,889 | 2,126,996 | 28,779 | 36 | 0.068 | qwen3.8-flash-next-iq3_xxs | not-returned | 1876.4 | 89.9 | 340.0 | 71.5 |
| 25 claude-code strata-iq3_xxs low | strata-low-a8 |  | 是 | 8 | 是 | 0.203 | 0.203 | 0.203 | 0.000 | 0 | 10.3 | 未知 | 160,148 | 3,513,370 | 44,734 | 75 | 0.101 | qwen3.8-flash-next-iq3_xxs | not-returned | 1619.9 | 87.9 | 258.1 | 72.1 |
| 25 claude-code strata-iq3_xxs low | strata-low-a9 |  | 是 | 9 | 是 | 0.193 | 0.193 | 0.193 | 0.000 | 0 | 7.0 | 未知 | 153,653 | 2,527,013 | 29,160 | 43 | 0.077 | qwen3.8-flash-next-iq3_xxs | not-returned | 1803.4 | 89.4 | 364.9 | 69.2 |
| 25 claude-code strata-iq3_xxs low | strata-low-a10 |  | 是 | 10 | 是 | 0.181 | 0.181 | 0.181 | 0.000 | 0 | 7.1 | 未知 | 166,789 | 2,454,560 | 28,461 | 36 | 0.078 | qwen3.8-flash-next-iq3_xxs | not-returned | 1882.7 | 86.9 | 394.1 | 67.2 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a1 |  | 是 | 1 | 是 | 0.181 | 0.181 | 0.181 | 0.000 | 0 | 6.6 | 未知 | 136,313 | 1,106,502 | 28,545 | 27 | 0.052 | qwen3.8-flash-next-iq3_xxs | not-returned | 2180.3 | 86.8 | 345.2 | 72.3 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a2 |  | 是 | 2 | 是 | 0.156 | 0.156 | 0.156 | 0.000 | 0 | 8.4 | 未知 | 139,127 | 1,740,662 | 36,928 | 32 | 0.066 | qwen3.8-flash-next-iq3_xxs | not-returned | 2024.8 | 85.9 | 276.0 | 73.3 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a3 |  | 是 | 3 | 是 | 0.325 | 0.325 | 0.325 | 0.000 | 0 | 17.9 | 未知 | 245,160 | 2,567,497 | 88,145 | 40 | 0.119 | qwen3.8-flash-next-iq3_xxs | not-returned | 2064.8 | 92.8 | 227.7 | 81.9 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a4 |  | 是 | 4 | 是 | 0.371 | 0.371 | 0.371 | 0.000 | 0 | 8.9 | 未知 | 147,964 | 1,974,906 | 38,744 | 33 | 0.072 | qwen3.8-flash-next-iq3_xxs | not-returned | 1996.5 | 84.7 | 275.8 | 72.2 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a5 |  | 是 | 5 | 是 | 0.270 | 0.270 | 0.270 | 0.000 | 0 | 10.3 | 未知 | 156,850 | 1,817,311 | 50,070 | 34 | 0.076 | qwen3.8-flash-next-iq3_xxs | not-returned | 2142.1 | 92.7 | 253.2 | 80.8 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a6 |  | 是 | 6 | 是 | -0.012 | 0.000 | -0.008 | 0.000 | 0 | 5.5 | 未知 | 124,852 | 1,160,660 | 24,627 | 32 | 0.049 | qwen3.8-flash-next-iq3_xxs | not-returned | 2036.9 | 92.1 | 375.3 | 74.0 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a7 |  | 是 | 7 | 是 | 0.360 | 0.360 | 0.360 | 0.000 | 0 | 9.8 | 未知 | 172,713 | 2,401,701 | 42,526 | 40 | 0.084 | qwen3.8-flash-next-iq3_xxs | not-returned | 1889.3 | 87.0 | 292.9 | 72.1 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a8 |  | 是 | 8 | 是 | 0.189 | 0.189 | 0.189 | 0.000 | 0 | 13.4 | 未知 | 151,473 | 2,029,237 | 71,564 | 38 | 0.089 | qwen3.8-flash-next-iq3_xxs | not-returned | 1888.0 | 99.5 | 188.2 | 88.9 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a9 |  | 是 | 9 | 是 | 0.363 | 0.363 | 0.363 | 0.000 | 0 | 13.4 | 未知 | 174,655 | 2,417,803 | 67,107 | 38 | 0.096 | qwen3.8-flash-next-iq3_xxs | not-returned | 1971.2 | 94.6 | 217.2 | 83.4 |
| 26 claude-code strata-iq3_xxs medium | strata-medium-a10 |  | 是 | 10 | 是 | 0.468 | 0.468 | 0.468 | 0.000 | 0 | 12.9 | 未知 | 185,903 | 3,385,211 | 57,573 | 56 | 0.109 | qwen3.8-flash-next-iq3_xxs | not-returned | 1862.0 | 87.3 | 240.7 | 74.5 |
| 27 claude-code strata-iq3_xxs high | strata-high-a2 |  | 是 | 1 | 是 | 0.324 | 0.324 | 0.324 | 0.000 | 0 | 13.8 | 未知 | 168,572 | 1,898,362 | 62,874 | 34 | 0.085 | qwen3.8-flash-next-iq3_xxs | not-returned | 2056.7 | 85.2 | 203.9 | 76.1 |
| 27 claude-code strata-iq3_xxs high | strata-high-a3 |  | 是 | 2 | 是 | 0.164 | 0.164 | 0.164 | 0.000 | 0 | 5.2 | 未知 | 123,047 | 747,543 | 22,982 | 25 | 0.041 | qwen3.8-flash-next-iq3_xxs | not-returned | 2243.6 | 90.3 | 393.7 | 73.5 |
| 27 claude-code strata-iq3_xxs high | strata-high-a4 |  | 是 | 3 | 是 | 0.185 | 0.185 | 0.185 | 0.000 | 0 | 9.8 | 未知 | 125,937 | 1,506,244 | 45,583 | 33 | 0.064 | qwen3.8-flash-next-iq3_xxs | not-returned | 2074.4 | 87.1 | 214.1 | 77.5 |
| 27 claude-code strata-iq3_xxs high | strata-high-a5 |  | 是 | 4 | 是 | 0.373 | 0.373 | 0.373 | 0.000 | 0 | 24.8 | 未知 | 173,921 | 2,279,526 | 134,294 | 34 | 0.126 | qwen3.8-flash-next-iq3_xxs | not-returned | 2036.3 | 96.1 | 116.8 | 90.2 |
| 27 claude-code strata-iq3_xxs high | strata-high-a6 |  | 是 | 5 | 是 | 0.255 | 0.255 | 0.255 | 0.000 | 0 | 11.9 | 未知 | 139,780 | 1,852,374 | 52,697 | 34 | 0.075 | qwen3.8-flash-next-iq3_xxs | not-returned | 2034.2 | 82.1 | 195.1 | 73.6 |
| 27 claude-code strata-iq3_xxs high | strata-high-a7 |  | 是 | 6 | 是 | 0.294 | 0.294 | 0.294 | 0.000 | 0 | 10.3 | 未知 | 144,761 | 1,873,933 | 45,707 | 39 | 0.073 | qwen3.8-flash-next-iq3_xxs | not-returned | 1973.8 | 85.6 | 234.1 | 73.9 |
| 27 claude-code strata-iq3_xxs high | strata-high-a8 |  | 是 | 7 | 是 | 0.262 | 0.262 | 0.262 | 0.000 | 0 | 10.4 | 未知 | 147,907 | 1,542,752 | 49,060 | 34 | 0.070 | qwen3.8-flash-next-iq3_xxs | not-returned | 2076.3 | 89.6 | 236.5 | 78.4 |
| 27 claude-code strata-iq3_xxs high | strata-high-a9 |  | 是 | 8 | 是 | 0.283 | 0.283 | 0.283 | 0.000 | 0 | 17.7 | 未知 | 142,656 | 1,999,283 | 98,792 | 35 | 0.100 | qwen3.8-flash-next-iq3_xxs | not-returned | 1996.1 | 100.3 | 134.1 | 92.9 |
| 27 claude-code strata-iq3_xxs high | strata-high-a10 |  | 是 | 9 | 是 | 0.387 | 0.387 | 0.387 | 0.000 | 0 | 10.7 | 未知 | 144,976 | 1,581,305 | 50,721 | 34 | 0.071 | qwen3.8-flash-next-iq3_xxs | not-returned | 2062.0 | 89.5 | 225.1 | 78.8 |
| 27 claude-code strata-iq3_xxs high | strata-high-a11 |  | 是 | 10 | 是 | 0.413 | 0.413 | 0.413 | 0.000 | 0 | 12.6 | 未知 | 159,822 | 1,859,460 | 58,723 | 37 | 0.081 | qwen3.8-flash-next-iq3_xxs | not-returned | 2037.0 | 87.7 | 211.0 | 77.5 |
| 27 claude-code strata-iq3_xxs high | strata-high-a1 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 17.7 | 未知 | 163,001 | 2,693,395 | 86,265 | 46 | 0.108 | qwen3.8-flash-next-iq3_xxs | not-returned | 1997.8 | 88.7 | 153.5 | 81.2 |
| 28 codex gpt-6-luna xhigh | luna-xhigh-a1 |  | 是 | 1 | 是 | 0.444 | 0.444 | 0.444 | 0.000 | 0 | 24.8 | 未知 | 371,136 | 6,993,408 | 178,190 | 65 | 只报 token | gpt-6-luna | default | 未知 | ≥119.9 | 249.8 | 119.9 |
| 28 codex gpt-6-luna xhigh | luna-xhigh-a2 |  | 是 | 2 | 是 | 0.533 | 0.533 | 0.533 | 0.000 | 0 | 22.6 | 未知 | 341,803 | 7,629,312 | 163,310 | 74 | 只报 token | gpt-6-luna | default | 未知 | ≥120.3 | 251.8 | 120.3 |
| 28 codex gpt-6-luna xhigh | luna-xhigh-a3 |  | 是 | 3 | 是 | 0.529 | 0.529 | 0.542 | 0.025 | 0 | 13.6 | 未知 | 263,019 | 3,203,840 | 97,195 | 37 | 只报 token | gpt-6-luna | default | 未知 | ≥118.8 | 321.4 | 118.8 |
| 28 codex gpt-6-luna xhigh | luna-xhigh-a4 |  | 是 | 4 | 是 | 0.585 | 0.585 | 0.585 | 0.000 | 0 | 15.2 | 未知 | 293,653 | 3,947,904 | 110,163 | 45 | 只报 token | gpt-6-luna | default | 未知 | ≥120.7 | 321.8 | 120.7 |
| 28 codex gpt-6-luna xhigh | luna-xhigh-a5 |  | 是 | 5 | 是 | 0.626 | 0.626 | 0.626 | 0.000 | 0 | 23.9 | 未知 | 362,763 | 6,190,848 | 176,710 | 58 | 只报 token | gpt-6-luna | default | 未知 | ≥123.4 | 253.1 | 123.3 |
| 29 codex gpt-6-luna max | luna-max-a1 |  | 是 | 1 | 是 | 0.652 | 0.652 | 0.652 | 0.000 | 0 | 28.6 | 未知 | 394,397 | 5,842,048 | 204,963 | 55 | 只报 token | gpt-6-luna | default | 未知 | ≥119.4 | 229.8 | 119.4 |
| 29 codex gpt-6-luna max | luna-max-a2 |  | 是 | 2 | 是 | 0.575 | 0.575 | 0.575 | 0.000 | 0 | 26.1 | 未知 | 357,386 | 5,448,320 | 184,961 | 47 | 只报 token | gpt-6-luna | default | 未知 | ≥118.3 | 228.5 | 118.3 |
| 29 codex gpt-6-luna max | luna-max-a3 |  | 是 | 3 | 是 | 0.410 | 0.410 | 0.410 | 0.000 | 0 | 17.9 | 未知 | 293,054 | 3,698,176 | 131,850 | 46 | 只报 token | gpt-6-luna | default | 未知 | ≥122.7 | 272.8 | 122.7 |
| 29 codex gpt-6-luna max | luna-max-a4 |  | 是 | 4 | 是 | 0.533 | 0.533 | 0.593 | 0.000 | 0 | 35.3 | 未知 | 495,323 | 14,157,568 | 237,985 | 96 | 只报 token | codex-auto-review、gpt-6-luna | default | 未知 | ≥112.2 | 233.7 | 112.3 |
| 29 codex gpt-6-luna max | luna-max-a5 |  | 是 | 5 | 是 | 0.711 | 0.711 | 0.711 | 0.000 | 0 | 18.7 | 未知 | 293,573 | 2,580,736 | 141,316 | 34 | 只报 token | gpt-6-luna | default | 未知 | ≥125.8 | 261.0 | 125.6 |

## DeepSeek 批次对账

余额差取自 schedule.jsonl 每次启动前读到的余额（只用已落盘记录，不调余额接口），窗口两端都是没有实例在跑的读数；计价合计是窗口内启动并结束的实例按请求时刻计的人民币。偏差 = 余额差 − 计价合计，只报告，不调整任何实例的费用（计划 14.4 没有规定处理）；窗口内实例之外的花费（定价核对、探测）也落在偏差里，被弃请求的 token 不进计价合计。

| 窗口 | 余额（起 → 止） | 余额差 | 实例数 | 无费用 | 计价合计 | 偏差 | 偏差占余额差 |
|---|---|---|---|---|---|---|---|
| 全部 | 78.78 → 12.86 | ¥65.92 | 137 | 0 | ¥64.2178 | ¥1.7022 | 2.58% |
| 2026-10-20 | 78.78 → 73.07 | ¥5.71 | 22 | 0 | ¥4.9414 | ¥0.7686 | 13.46% |
| 2026-10-21 | 63.76 → 12.86 | ¥50.90 | 107 | 0 | ¥50.0262 | ¥0.8738 | 1.72% |
