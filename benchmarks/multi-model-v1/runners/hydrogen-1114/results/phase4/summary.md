# 多模型 benchmark v1 汇总

第四阶段补充（只含补充）：Gemini 4 Hydrogen medium / high / xhigh（配置 30–32，Antigravity，各格取全部有效实例，不截取前 5 个，也没有一致性行；用户 2026-11-14，规则同第三阶段补充）。本文件只有这三个配置，不含预登记配置和比较；预登记配置与前三阶段见第三阶段文件。

不做组间比较（补充文件只含补充配置）；条件相同的组内统计与 v1 相同。
主统计多于前 5 个的格另给一致性行（按开始时刻的前 5 个；第三阶段补充配置不给）；不给比值、综合分和排名。

## code-spec-v5

### 配置

| 配置 | 行 | 有效 | 选入 n | 已计分 | 无效 | 均值 ± SD | SE | 95% 区间 | 负分数 | 最小 | 中位数 | r8.3 均值 | rawScore | f | 修复 | 耗时（分钟） | 占时限 | 未缓存 | 缓存 | 输出 | token 来源 | 工具调用 | 费用（美元；DeepSeek 括号内为人民币 ¥） | 周额度 | 模型 ID | service tier |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 30 antigravity gemini-4-hydrogen medium | 第四阶段补充（不比较） | 5 | 5 | 5 |  | 0.549 ± 0.116 | 0.052 | 0.405–0.693 | 0 | 0.412 | 0.516 | 0.549 | 0.554 | 0.012 | 0 | 5.6 | 0.88 | 111,625 | 1,088,509 | 13,472 | agy stream usage | 27.4 | 只报 token |  | gemini-4-hydrogen-medium | 未知 |
| 31 antigravity gemini-4-hydrogen high | 第四阶段补充（不比较） | 5 | 5 | 5 |  | 0.670 ± 0.027 | 0.012 | 0.637–0.703 | 0 | 0.635 | 0.669 | 0.670 | 0.670 | 0.000 | 0 | 4.2 | 0.70 | 133,129 | 1,247,884 | 23,898 | agy stream usage | 26.0 | 只报 token |  | gemini-4-hydrogen-high | 未知 |
| 32 antigravity gemini-4-hydrogen xhigh | 第四阶段补充（不比较） | 5 | 5 | 5 |  | 0.691 ± 0.070 | 0.031 | 0.604–0.778 | 0 | 0.631 | 0.659 | 0.691 | 0.700 | 0.013 | 0 | 6.1 | 0.97 | 146,457 | 700,709 | 34,776 | agy stream usage | 25.4 | 只报 token |  | gemini-4-hydrogen-xhigh | 未知 |

### 逐实例

速度：引擎输入、引擎输出是模型直接速度，任务平均输入、输出是用户感知速度（未缓存输入、输出 ÷ 工作秒数）。API 模型分不出输入处理时间，引擎输入记未知；引擎输出按 API 请求时间算，含首 token 延迟和输入处理，是下限（≥）。

速度汇总口径（用户 2026-10-22）：多个实例的速度（summary.json 各行的 speeds_mean）是总 token ÷ 总耗时（各实例 speed_parts 的分子之和 ÷ 分母之和，speed_totals 给出两者），不是各实例速度的算术平均；任一实例该项未知，汇总即未知；任一实例该项是下限，汇总也是下限。Codex 上的 API 模型（gpt-6.1-sol、gpt-6-luna、DeepSeek）的引擎输出按 relay 日志的 output token ÷ 请求秒数计算，v1 的记录没有保存请求秒数，原始 relay 日志已删除，所以这一项按用户 10-22 的选择近似汇总：分子取实例的输出 token（同样来自 relay usage），分母取 输出 token ÷ 逐实例引擎输出速度 反推的请求秒数；汇总标为近似（speeds_approximate，表中写"≥≈"），仍是下限。

| 配置 | 实例 | 补充 | 有效 | 序 | 主统计 | 分数 | r8.3 分数 | rawScore | f | 修复 | 耗时（分钟） | 占时限 | 未缓存 | 缓存 | 输出 | 工具调用 | 费用（美元；DeepSeek 括号内为人民币 ¥） | 模型 ID | service tier | 引擎输入 tok/s | 引擎输出 tok/s | 任务平均输入 tok/s | 任务平均输出 tok/s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 30 antigravity gemini-4-hydrogen medium | hydrogen-medium-a1 |  | 是 | 1 | 是 | 0.664 | 0.664 | 0.664 | 0.000 | 0 | 5.5 | 0.86 | 118,500 | 1,129,120 | 13,813 | 30 | 只报 token | gemini-4-hydrogen-medium | 未知 | 未知 | 未知 | 357.5 | 41.7 |
| 30 antigravity gemini-4-hydrogen medium | hydrogen-medium-a2 |  | 是 | 2 | 是 | 0.516 | 0.516 | 0.516 | 0.000 | 0 | 4.8 | 0.74 | 100,670 | 791,096 | 12,825 | 27 | 只报 token | gemini-4-hydrogen-medium | 未知 | 未知 | 未知 | 353.1 | 45.0 |
| 30 antigravity gemini-4-hydrogen medium | hydrogen-medium-a3 |  | 是 | 3 | 是 | 0.674 | 0.674 | 0.674 | 0.000 | 0 | 6.4 | 1.00 | 106,558 | 1,154,893 | 13,978 | 27 | 只报 token | gemini-4-hydrogen-medium | 未知 | 未知 | 未知 | 276.6 | 36.3 |
| 30 antigravity gemini-4-hydrogen medium | hydrogen-medium-a4 |  | 是 | 4 | 是 | 0.480 | 0.480 | 0.480 | 0.000 | 0 | 5.0 | 0.78 | 108,308 | 848,542 | 13,116 | 25 | 只报 token | gemini-4-hydrogen-medium | 未知 | 未知 | 未知 | 362.7 | 43.9 |
| 30 antigravity gemini-4-hydrogen medium | hydrogen-medium-a5 |  | 是 | 5 | 是 | 0.412 | 0.412 | 0.437 | 0.059 | 0 | 6.5 | 1.01 | 124,087 | 1,518,893 | 13,628 | 28 | 只报 token | gemini-4-hydrogen-medium | 未知 | 未知 | 未知 | 318.2 | 34.9 |
| 31 antigravity gemini-4-hydrogen high | hydrogen-high-a1 |  | 是 | 1 | 是 | 0.691 | 0.691 | 0.691 | 0.000 | 0 | 3.7 | 0.62 | 143,082 | 1,326,527 | 28,564 | 24 | 只报 token | gemini-4-hydrogen-high | 未知 | 未知 | 未知 | 638.1 | 127.4 |
| 31 antigravity gemini-4-hydrogen high | hydrogen-high-a2 |  | 是 | 2 | 是 | 0.635 | 0.635 | 0.635 | 0.000 | 0 | 4.0 | 0.67 | 138,598 | 1,231,655 | 27,964 | 32 | 只报 token | gemini-4-hydrogen-high | 未知 | 未知 | 未知 | 578.1 | 116.6 |
| 31 antigravity gemini-4-hydrogen high | hydrogen-high-a3 |  | 是 | 3 | 是 | 0.700 | 0.700 | 0.700 | 0.000 | 0 | 4.3 | 0.72 | 131,977 | 1,105,259 | 23,287 | 25 | 只报 token | gemini-4-hydrogen-high | 未知 | 未知 | 未知 | 512.4 | 90.4 |
| 31 antigravity gemini-4-hydrogen high | hydrogen-high-a4 |  | 是 | 4 | 是 | 0.655 | 0.655 | 0.655 | 0.000 | 0 | 4.3 | 0.71 | 141,638 | 1,910,099 | 22,037 | 29 | 只报 token | gemini-4-hydrogen-high | 未知 | 未知 | 未知 | 552.1 | 85.9 |
| 31 antigravity gemini-4-hydrogen high | hydrogen-high-a5 |  | 是 | 5 | 是 | 0.669 | 0.669 | 0.669 | 0.000 | 0 | 4.5 | 0.75 | 110,352 | 665,882 | 17,639 | 20 | 只报 token | gemini-4-hydrogen-high | 未知 | 未知 | 未知 | 408.3 | 65.3 |
| 32 antigravity gemini-4-hydrogen xhigh | hydrogen-xhigh-a1 |  | 是 | 1 | 是 | 0.659 | 0.659 | 0.688 | 0.042 | 0 | 6.4 | 1.01 | 152,065 | 1,069,941 | 29,746 | 29 | 只报 token | gemini-4-hydrogen-xhigh | 未知 | 未知 | 未知 | 398.5 | 77.9 |
| 32 antigravity gemini-4-hydrogen xhigh | hydrogen-xhigh-a2 |  | 是 | 2 | 是 | 0.631 | 0.631 | 0.631 | 0.000 | 0 | 5.4 | 0.85 | 145,210 | 653,799 | 38,510 | 23 | 只报 token | gemini-4-hydrogen-xhigh | 未知 | 未知 | 未知 | 448.6 | 119.0 |
| 32 antigravity gemini-4-hydrogen xhigh | hydrogen-xhigh-a3 |  | 是 | 3 | 是 | 0.790 | 0.790 | 0.790 | 0.000 | 0 | 6.3 | 0.99 | 163,097 | 653,501 | 40,670 | 25 | 只报 token | gemini-4-hydrogen-xhigh | 未知 | 未知 | 未知 | 433.3 | 108.1 |
| 32 antigravity gemini-4-hydrogen xhigh | hydrogen-xhigh-a4 |  | 是 | 4 | 是 | 0.739 | 0.739 | 0.756 | 0.022 | 0 | 6.3 | 1.00 | 140,332 | 515,975 | 39,712 | 21 | 只报 token | gemini-4-hydrogen-xhigh | 未知 | 未知 | 未知 | 369.2 | 104.5 |
| 32 antigravity gemini-4-hydrogen xhigh | hydrogen-xhigh-a5 |  | 是 | 5 | 是 | 0.637 | 0.637 | 0.637 | 0.000 | 0 | 6.3 | 0.99 | 131,581 | 610,328 | 25,240 | 29 | 只报 token | gemini-4-hydrogen-xhigh | 未知 | 未知 | 未知 | 349.3 | 67.0 |

## code-standards-v5.1

### 配置

| 配置 | 行 | 有效 | 选入 n | 已计分 | 无效 | 均值 ± SD | SE | 95% 区间 | 负分数 | 最小 | 中位数 | r8.3 均值 | rawScore | f | 修复 | 耗时（分钟） | 占时限 | 未缓存 | 缓存 | 输出 | token 来源 | 工具调用 | 费用（美元；DeepSeek 括号内为人民币 ¥） | 周额度 | 模型 ID | service tier |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 30 antigravity gemini-4-hydrogen medium | 第四阶段补充（不比较） | 5 | 5 | 5 |  | 0.791 ± 0.056 | 0.025 | 0.721–0.861 | 0 | 0.723 | 0.786 | 0.791 | 0.818 | 0.033 | 16 | 4.5 | 0.72 | 74,939 | 562,044 | 18,333 | agy stream usage | 28.0 | 只报 token |  | gemini-4-hydrogen-medium | 未知 |
| 31 antigravity gemini-4-hydrogen high | 第四阶段补充（不比较） | 5 | 5 | 5 |  | 0.843 ± 0.035 | 0.016 | 0.799–0.887 | 0 | 0.797 | 0.849 | 0.843 | 0.863 | 0.023 | 12 | 5.0 | 0.74 | 109,143 | 1,089,818 | 29,025 | agy stream usage | 31.0 | 只报 token |  | gemini-4-hydrogen-high | 未知 |
| 32 antigravity gemini-4-hydrogen xhigh | 第四阶段补充（不比较） | 5 | 5 | 5 |  | 0.472 ± 0.432 | 0.193 | -0.064–1.008 | 0 | 0.000 | 0.757 | 0.472 | 0.486 | 0.016 | 8 | 5.7 | 1.00 | 112,638 | 824,734 | 25,501 | agy stream usage | 28.8 | 只报 token |  | gemini-4-hydrogen-xhigh | 未知 |

### 逐实例

速度：引擎输入、引擎输出是模型直接速度，任务平均输入、输出是用户感知速度（未缓存输入、输出 ÷ 工作秒数）。API 模型分不出输入处理时间，引擎输入记未知；引擎输出按 API 请求时间算，含首 token 延迟和输入处理，是下限（≥）。

速度汇总口径（用户 2026-10-22）：多个实例的速度（summary.json 各行的 speeds_mean）是总 token ÷ 总耗时（各实例 speed_parts 的分子之和 ÷ 分母之和，speed_totals 给出两者），不是各实例速度的算术平均；任一实例该项未知，汇总即未知；任一实例该项是下限，汇总也是下限。Codex 上的 API 模型（gpt-6.1-sol、gpt-6-luna、DeepSeek）的引擎输出按 relay 日志的 output token ÷ 请求秒数计算，v1 的记录没有保存请求秒数，原始 relay 日志已删除，所以这一项按用户 10-22 的选择近似汇总：分子取实例的输出 token（同样来自 relay usage），分母取 输出 token ÷ 逐实例引擎输出速度 反推的请求秒数；汇总标为近似（speeds_approximate，表中写"≥≈"），仍是下限。

| 配置 | 实例 | 补充 | 有效 | 序 | 主统计 | 分数 | r8.3 分数 | rawScore | f | 修复 | 耗时（分钟） | 占时限 | 未缓存 | 缓存 | 输出 | 工具调用 | 费用（美元；DeepSeek 括号内为人民币 ¥） | 模型 ID | service tier | 引擎输入 tok/s | 引擎输出 tok/s | 任务平均输入 tok/s | 任务平均输出 tok/s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 30 antigravity gemini-4-hydrogen medium | hydrogen-medium-a1 |  | 是 | 1 | 是 | 0.723 | 0.723 | 0.803 | 0.100 | 11 | 4.6 | 0.75 | 73,459 | 674,522 | 17,870 | 27 | 只报 token | gemini-4-hydrogen-medium | 未知 | 未知 | 未知 | 264.3 | 64.3 |
| 30 antigravity gemini-4-hydrogen medium | hydrogen-medium-a2 |  | 是 | 2 | 是 | 0.844 | 0.844 | 0.855 | 0.013 | 1 | 4.3 | 0.69 | 75,994 | 508,476 | 21,052 | 24 | 只报 token | gemini-4-hydrogen-medium | 未知 | 未知 | 未知 | 297.9 | 82.5 |
| 30 antigravity gemini-4-hydrogen medium | hydrogen-medium-a3 |  | 是 | 3 | 是 | 0.851 | 0.851 | 0.851 | 0.000 | 0 | 4.2 | 0.68 | 70,141 | 472,575 | 18,268 | 29 | 只报 token | gemini-4-hydrogen-medium | 未知 | 未知 | 未知 | 276.3 | 72.0 |
| 30 antigravity gemini-4-hydrogen medium | hydrogen-medium-a4 |  | 是 | 4 | 是 | 0.786 | 0.786 | 0.786 | 0.000 | 0 | 4.8 | 0.77 | 79,870 | 651,034 | 18,529 | 35 | 只报 token | gemini-4-hydrogen-medium | 未知 | 未知 | 未知 | 278.9 | 64.7 |
| 30 antigravity gemini-4-hydrogen medium | hydrogen-medium-a5 |  | 是 | 5 | 是 | 0.750 | 0.750 | 0.793 | 0.054 | 4 | 4.4 | 0.71 | 75,231 | 503,611 | 15,946 | 25 | 只报 token | gemini-4-hydrogen-medium | 未知 | 未知 | 未知 | 284.9 | 60.4 |
| 31 antigravity gemini-4-hydrogen high | hydrogen-high-a1 |  | 是 | 1 | 是 | 0.887 | 0.887 | 0.916 | 0.032 | 3 | 5.3 | 0.79 | 99,619 | 1,042,562 | 25,384 | 30 | 只报 token | gemini-4-hydrogen-high | 未知 | 未知 | 未知 | 314.1 | 80.0 |
| 31 antigravity gemini-4-hydrogen high | hydrogen-high-a2 |  | 是 | 2 | 是 | 0.797 | 0.797 | 0.868 | 0.081 | 9 | 5.1 | 0.76 | 111,545 | 1,107,576 | 30,781 | 32 | 只报 token | gemini-4-hydrogen-high | 未知 | 未知 | 未知 | 365.8 | 100.9 |
| 31 antigravity gemini-4-hydrogen high | hydrogen-high-a3 |  | 是 | 3 | 是 | 0.863 | 0.863 | 0.863 | 0.000 | 0 | 5.1 | 0.77 | 119,830 | 1,292,879 | 28,493 | 32 | 只报 token | gemini-4-hydrogen-high | 未知 | 未知 | 未知 | 388.2 | 92.3 |
| 31 antigravity gemini-4-hydrogen high | hydrogen-high-a4 |  | 是 | 4 | 是 | 0.849 | 0.849 | 0.849 | 0.000 | 0 | 4.8 | 0.71 | 113,131 | 1,206,136 | 34,285 | 30 | 只报 token | gemini-4-hydrogen-high | 未知 | 未知 | 未知 | 396.6 | 120.2 |
| 31 antigravity gemini-4-hydrogen high | hydrogen-high-a5 |  | 是 | 5 | 是 | 0.819 | 0.819 | 0.819 | 0.000 | 0 | 4.6 | 0.68 | 101,590 | 799,936 | 26,181 | 31 | 只报 token | gemini-4-hydrogen-high | 未知 | 未知 | 未知 | 370.2 | 95.4 |
| 32 antigravity gemini-4-hydrogen xhigh | hydrogen-xhigh-a1 |  | 是 | 1 | 是 | 0.000 | 0.000 | 0.000 | 0.000 | 0 | 5.8 | 1.03 | 85,450 | 558,717 | 12,039 | 27 | 只报 token | gemini-4-hydrogen-xhigh | 未知 | 未知 | 未知 | 244.4 | 34.4 |
| 32 antigravity gemini-4-hydrogen xhigh | hydrogen-xhigh-a2 |  | 是 | 2 | 是 | 0.000 | 0.000 | 0.000 | 0.000 | 0 | 5.8 | 1.02 | 103,034 | 661,978 | 22,722 | 27 | 只报 token | gemini-4-hydrogen-xhigh | 未知 | 未知 | 未知 | 297.3 | 65.6 |
| 32 antigravity gemini-4-hydrogen xhigh | hydrogen-xhigh-a3 |  | 是 | 3 | 是 | 0.783 | 0.783 | 0.783 | 0.000 | 0 | 5.3 | 0.93 | 123,343 | 1,086,352 | 23,199 | 30 | 只报 token | gemini-4-hydrogen-xhigh | 未知 | 未知 | 未知 | 391.0 | 73.5 |
| 32 antigravity gemini-4-hydrogen xhigh | hydrogen-xhigh-a4 |  | 是 | 4 | 是 | 0.757 | 0.757 | 0.817 | 0.073 | 7 | 5.8 | 1.02 | 113,177 | 786,350 | 35,295 | 31 | 只报 token | gemini-4-hydrogen-xhigh | 未知 | 未知 | 未知 | 325.6 | 101.5 |
| 32 antigravity gemini-4-hydrogen xhigh | hydrogen-xhigh-a5 |  | 是 | 5 | 是 | 0.821 | 0.821 | 0.828 | 0.009 | 1 | 5.7 | 1.00 | 138,185 | 1,030,275 | 34,249 | 29 | 只报 token | gemini-4-hydrogen-xhigh | 未知 | 未知 | 未知 | 404.5 | 100.2 |

## commit-audit-v3

### 配置

| 配置 | 行 | 有效 | 选入 n | 已计分 | 无效 | 均值 ± SD | SE | 95% 区间 | 负分数 | 最小 | 中位数 | r8.3 均值 | rawScore | f | 修复 | 耗时（分钟） | 占时限 | 未缓存 | 缓存 | 输出 | token 来源 | 工具调用 | 费用（美元；DeepSeek 括号内为人民币 ¥） | 周额度 | 模型 ID | service tier |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 30 antigravity gemini-4-hydrogen medium | 第四阶段补充（不比较） | 5 | 5 | 5 |  | 0.837 ± 0.009 | 0.004 | 0.826–0.848 | 0 | 0.831 | 0.832 | 0.837 | 0.837 | 0.000 | 0 | 5.1 | 未知 | 97,102 | 644,084 | 40,795 | agy stream usage | 37.4 | 只报 token |  | gemini-4-hydrogen-medium | 未知 |
| 31 antigravity gemini-4-hydrogen high | 第四阶段补充（不比较） | 5 | 5 | 5 |  | 0.862 ± 0.024 | 0.011 | 0.832–0.892 | 0 | 0.821 | 0.870 | 0.862 | 0.862 | 0.000 | 0 | 5.5 | 未知 | 158,994 | 994,432 | 63,585 | agy stream usage | 39.4 | 只报 token |  | gemini-4-hydrogen-high | 未知 |
| 32 antigravity gemini-4-hydrogen xhigh | 第四阶段补充（不比较） | 5 | 5 | 5 |  | 0.856 ± 0.018 | 0.008 | 0.834–0.879 | 0 | 0.824 | 0.864 | 0.856 | 0.856 | 0.000 | 0 | 15.2 | 未知 | 280,153 | 1,525,849 | 125,577 | agy stream usage | 43.8 | 只报 token |  | gemini-4-hydrogen-xhigh | 未知 |

### 逐实例

速度：引擎输入、引擎输出是模型直接速度，任务平均输入、输出是用户感知速度（未缓存输入、输出 ÷ 工作秒数）。API 模型分不出输入处理时间，引擎输入记未知；引擎输出按 API 请求时间算，含首 token 延迟和输入处理，是下限（≥）。

速度汇总口径（用户 2026-10-22）：多个实例的速度（summary.json 各行的 speeds_mean）是总 token ÷ 总耗时（各实例 speed_parts 的分子之和 ÷ 分母之和，speed_totals 给出两者），不是各实例速度的算术平均；任一实例该项未知，汇总即未知；任一实例该项是下限，汇总也是下限。Codex 上的 API 模型（gpt-6.1-sol、gpt-6-luna、DeepSeek）的引擎输出按 relay 日志的 output token ÷ 请求秒数计算，v1 的记录没有保存请求秒数，原始 relay 日志已删除，所以这一项按用户 10-22 的选择近似汇总：分子取实例的输出 token（同样来自 relay usage），分母取 输出 token ÷ 逐实例引擎输出速度 反推的请求秒数；汇总标为近似（speeds_approximate，表中写"≥≈"），仍是下限。

| 配置 | 实例 | 补充 | 有效 | 序 | 主统计 | 分数 | r8.3 分数 | rawScore | f | 修复 | 耗时（分钟） | 占时限 | 未缓存 | 缓存 | 输出 | 工具调用 | 费用（美元；DeepSeek 括号内为人民币 ¥） | 模型 ID | service tier | 引擎输入 tok/s | 引擎输出 tok/s | 任务平均输入 tok/s | 任务平均输出 tok/s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 30 antigravity gemini-4-hydrogen medium | hydrogen-medium-a2 |  | 是 | 1 | 是 | 0.832 | 0.832 | 0.832 | 0.000 | 0 | 4.8 | 未知 | 97,281 | 644,671 | 40,073 | 39 | 只报 token | gemini-4-hydrogen-medium | 未知 | 未知 | 未知 | 340.8 | 140.4 |
| 30 antigravity gemini-4-hydrogen medium | hydrogen-medium-a3 |  | 是 | 2 | 是 | 0.831 | 0.831 | 0.831 | 0.000 | 0 | 5.7 | 未知 | 102,351 | 807,768 | 43,961 | 37 | 只报 token | gemini-4-hydrogen-medium | 未知 | 未知 | 未知 | 301.9 | 129.7 |
| 30 antigravity gemini-4-hydrogen medium | hydrogen-medium-a4 |  | 是 | 3 | 是 | 0.852 | 0.852 | 0.852 | 0.000 | 0 | 5.8 | 未知 | 97,763 | 666,668 | 40,286 | 39 | 只报 token | gemini-4-hydrogen-medium | 未知 | 未知 | 未知 | 278.7 | 114.8 |
| 30 antigravity gemini-4-hydrogen medium | hydrogen-medium-a5 |  | 是 | 4 | 是 | 0.839 | 0.839 | 0.839 | 0.000 | 0 | 5.4 | 未知 | 102,427 | 708,776 | 41,861 | 36 | 只报 token | gemini-4-hydrogen-medium | 未知 | 未知 | 未知 | 316.9 | 129.5 |
| 30 antigravity gemini-4-hydrogen medium | hydrogen-medium-a6 |  | 是 | 5 | 是 | 0.832 | 0.832 | 0.832 | 0.000 | 0 | 3.8 | 未知 | 85,688 | 392,536 | 37,795 | 36 | 只报 token | gemini-4-hydrogen-medium | 未知 | 未知 | 未知 | 379.1 | 167.2 |
| 30 antigravity gemini-4-hydrogen medium | hydrogen-medium-a1 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 7.2 | 未知 | 172,575 | 402,590 | 71,859 | 36 | 只报 token | gemini-4-hydrogen-medium | 未知 | 未知 | 未知 | 398.7 | 166.0 |
| 31 antigravity gemini-4-hydrogen high | hydrogen-high-a1 |  | 是 | 1 | 是 | 0.863 | 0.863 | 0.863 | 0.000 | 0 | 5.0 | 未知 | 124,134 | 605,986 | 60,064 | 27 | 只报 token | gemini-4-hydrogen-high | 未知 | 未知 | 未知 | 415.0 | 200.8 |
| 31 antigravity gemini-4-hydrogen high | hydrogen-high-a2 |  | 是 | 2 | 是 | 0.881 | 0.881 | 0.881 | 0.000 | 0 | 4.9 | 未知 | 122,449 | 730,464 | 59,860 | 37 | 只报 token | gemini-4-hydrogen-high | 未知 | 未知 | 未知 | 414.9 | 202.8 |
| 31 antigravity gemini-4-hydrogen high | hydrogen-high-a3 |  | 是 | 3 | 是 | 0.875 | 0.875 | 0.875 | 0.000 | 0 | 5.1 | 未知 | 147,612 | 1,177,681 | 57,537 | 48 | 只报 token | gemini-4-hydrogen-high | 未知 | 未知 | 未知 | 478.2 | 186.4 |
| 31 antigravity gemini-4-hydrogen high | hydrogen-high-a4 |  | 是 | 4 | 是 | 0.870 | 0.870 | 0.870 | 0.000 | 0 | 5.9 | 未知 | 146,700 | 846,990 | 69,997 | 34 | 只报 token | gemini-4-hydrogen-high | 未知 | 未知 | 未知 | 417.4 | 199.2 |
| 31 antigravity gemini-4-hydrogen high | hydrogen-high-a5 |  | 是 | 5 | 是 | 0.821 | 0.821 | 0.821 | 0.000 | 0 | 6.5 | 未知 | 254,075 | 1,611,041 | 70,469 | 51 | 只报 token | gemini-4-hydrogen-high | 未知 | 未知 | 未知 | 651.7 | 180.8 |
| 32 antigravity gemini-4-hydrogen xhigh | hydrogen-xhigh-a1 |  | 是 | 1 | 是 | 0.864 | 0.864 | 0.864 | 0.000 | 0 | 15.3 | 未知 | 260,894 | 1,368,089 | 125,215 | 28 | 只报 token | gemini-4-hydrogen-xhigh | 未知 | 未知 | 未知 | 284.0 | 136.3 |
| 32 antigravity gemini-4-hydrogen xhigh | hydrogen-xhigh-a2 |  | 是 | 2 | 是 | 0.869 | 0.869 | 0.869 | 0.000 | 0 | 13.7 | 未知 | 282,673 | 1,494,057 | 120,508 | 32 | 只报 token | gemini-4-hydrogen-xhigh | 未知 | 未知 | 未知 | 344.1 | 146.7 |
| 32 antigravity gemini-4-hydrogen xhigh | hydrogen-xhigh-a3 |  | 是 | 3 | 是 | 0.860 | 0.860 | 0.860 | 0.000 | 0 | 17.6 | 未知 | 254,265 | 1,436,746 | 125,762 | 51 | 只报 token | gemini-4-hydrogen-xhigh | 未知 | 未知 | 未知 | 241.4 | 119.4 |
| 32 antigravity gemini-4-hydrogen xhigh | hydrogen-xhigh-a4 |  | 是 | 4 | 是 | 0.824 | 0.824 | 0.824 | 0.000 | 0 | 17.3 | 未知 | 357,292 | 1,948,120 | 146,757 | 54 | 只报 token | gemini-4-hydrogen-xhigh | 未知 | 未知 | 未知 | 344.0 | 141.3 |
| 32 antigravity gemini-4-hydrogen xhigh | hydrogen-xhigh-a6 |  | 是 | 5 | 是 | 0.864 | 0.864 | 0.864 | 0.000 | 0 | 12.2 | 未知 | 245,641 | 1,382,235 | 109,642 | 54 | 只报 token | gemini-4-hydrogen-xhigh | 未知 | 未知 | 未知 | 334.7 | 149.4 |
| 32 antigravity gemini-4-hydrogen xhigh | hydrogen-xhigh-a5 |  | 否 |  |  | 未知 |  | 未知 | 未知 | 未知 | 17.7 | 未知 | 303,462 | 2,386,209 | 144,584 | 42 | 只报 token | gemini-4-hydrogen-xhigh | 未知 | 未知 | 未知 | 285.5 | 136.0 |

## spec-readiness-v4.3

### 配置

| 配置 | 行 | 有效 | 选入 n | 已计分 | 无效 | 均值 ± SD | SE | 95% 区间 | 负分数 | 最小 | 中位数 | r8.3 均值 | rawScore | f | 修复 | 耗时（分钟） | 占时限 | 未缓存 | 缓存 | 输出 | token 来源 | 工具调用 | 费用（美元；DeepSeek 括号内为人民币 ¥） | 周额度 | 模型 ID | service tier |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 30 antigravity gemini-4-hydrogen medium | 第四阶段补充（不比较） | 5 | 5 | 5 |  | 0.655 ± 0.076 | 0.034 | 0.561–0.750 | 0 | 0.592 | 0.627 | 0.655 | 0.655 | 0.000 | 0 | 8.8 | 未知 | 203,982 | 1,257,175 | 42,857 | agy stream usage | 35.2 | 只报 token |  | gemini-4-hydrogen-medium | 未知 |
| 31 antigravity gemini-4-hydrogen high | 第四阶段补充（不比较） | 5 | 5 | 5 |  | 0.833 ± 0.032 | 0.014 | 0.793–0.873 | 0 | 0.794 | 0.833 | 0.833 | 0.833 | 0.000 | 0 | 12.2 | 未知 | 331,378 | 1,342,744 | 120,070 | agy stream usage | 36.0 | 只报 token |  | gemini-4-hydrogen-high | 未知 |
| 32 antigravity gemini-4-hydrogen xhigh | 第四阶段补充（不比较） | 5 | 5 | 5 |  | 0.769 ± 0.033 | 0.015 | 0.728–0.810 | 0 | 0.732 | 0.763 | 0.769 | 0.769 | 0.000 | 0 | 36.9 | 未知 | 635,643 | 2,442,850 | 291,141 | agy stream usage | 48.0 | 只报 token |  | gemini-4-hydrogen-xhigh | 未知 |

### 逐实例

速度：引擎输入、引擎输出是模型直接速度，任务平均输入、输出是用户感知速度（未缓存输入、输出 ÷ 工作秒数）。API 模型分不出输入处理时间，引擎输入记未知；引擎输出按 API 请求时间算，含首 token 延迟和输入处理，是下限（≥）。

速度汇总口径（用户 2026-10-22）：多个实例的速度（summary.json 各行的 speeds_mean）是总 token ÷ 总耗时（各实例 speed_parts 的分子之和 ÷ 分母之和，speed_totals 给出两者），不是各实例速度的算术平均；任一实例该项未知，汇总即未知；任一实例该项是下限，汇总也是下限。Codex 上的 API 模型（gpt-6.1-sol、gpt-6-luna、DeepSeek）的引擎输出按 relay 日志的 output token ÷ 请求秒数计算，v1 的记录没有保存请求秒数，原始 relay 日志已删除，所以这一项按用户 10-22 的选择近似汇总：分子取实例的输出 token（同样来自 relay usage），分母取 输出 token ÷ 逐实例引擎输出速度 反推的请求秒数；汇总标为近似（speeds_approximate，表中写"≥≈"），仍是下限。

| 配置 | 实例 | 补充 | 有效 | 序 | 主统计 | 分数 | r8.3 分数 | rawScore | f | 修复 | 耗时（分钟） | 占时限 | 未缓存 | 缓存 | 输出 | 工具调用 | 费用（美元；DeepSeek 括号内为人民币 ¥） | 模型 ID | service tier | 引擎输入 tok/s | 引擎输出 tok/s | 任务平均输入 tok/s | 任务平均输出 tok/s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 30 antigravity gemini-4-hydrogen medium | hydrogen-medium-a1 |  | 是 | 1 | 是 | 0.595 | 0.595 | 0.595 | 0.000 | 0 | 7.7 | 未知 | 184,559 | 1,033,770 | 44,407 | 32 | 只报 token | gemini-4-hydrogen-medium | 未知 | 未知 | 未知 | 401.1 | 96.5 |
| 30 antigravity gemini-4-hydrogen medium | hydrogen-medium-a2 |  | 是 | 2 | 是 | 0.592 | 0.592 | 0.592 | 0.000 | 0 | 7.8 | 未知 | 182,159 | 1,346,637 | 41,888 | 35 | 只报 token | gemini-4-hydrogen-medium | 未知 | 未知 | 未知 | 388.2 | 89.3 |
| 30 antigravity gemini-4-hydrogen medium | hydrogen-medium-a3 |  | 是 | 3 | 是 | 0.772 | 0.772 | 0.772 | 0.000 | 0 | 7.5 | 未知 | 187,063 | 1,071,336 | 40,543 | 36 | 只报 token | gemini-4-hydrogen-medium | 未知 | 未知 | 未知 | 416.6 | 90.3 |
| 30 antigravity gemini-4-hydrogen medium | hydrogen-medium-a4 |  | 是 | 4 | 是 | 0.691 | 0.691 | 0.691 | 0.000 | 0 | 7.9 | 未知 | 243,982 | 986,616 | 38,908 | 32 | 只报 token | gemini-4-hydrogen-medium | 未知 | 未知 | 未知 | 514.7 | 82.1 |
| 30 antigravity gemini-4-hydrogen medium | hydrogen-medium-a5 |  | 是 | 5 | 是 | 0.627 | 0.627 | 0.627 | 0.000 | 0 | 12.9 | 未知 | 222,145 | 1,847,515 | 48,538 | 41 | 只报 token | gemini-4-hydrogen-medium | 未知 | 未知 | 未知 | 286.0 | 62.5 |
| 31 antigravity gemini-4-hydrogen high | hydrogen-high-a1 |  | 是 | 1 | 是 | 0.834 | 0.834 | 0.834 | 0.000 | 0 | 10.0 | 未知 | 290,135 | 1,405,880 | 115,060 | 33 | 只报 token | gemini-4-hydrogen-high | 未知 | 未知 | 未知 | 481.4 | 190.9 |
| 31 antigravity gemini-4-hydrogen high | hydrogen-high-a2 |  | 是 | 2 | 是 | 0.833 | 0.833 | 0.833 | 0.000 | 0 | 10.9 | 未知 | 297,704 | 1,289,221 | 119,041 | 37 | 只报 token | gemini-4-hydrogen-high | 未知 | 未知 | 未知 | 456.1 | 182.4 |
| 31 antigravity gemini-4-hydrogen high | hydrogen-high-a3 |  | 是 | 3 | 是 | 0.883 | 0.883 | 0.883 | 0.000 | 0 | 11.1 | 未知 | 280,678 | 1,131,579 | 111,060 | 34 | 只报 token | gemini-4-hydrogen-high | 未知 | 未知 | 未知 | 419.9 | 166.1 |
| 31 antigravity gemini-4-hydrogen high | hydrogen-high-a4 |  | 是 | 4 | 是 | 0.821 | 0.821 | 0.821 | 0.000 | 0 | 12.2 | 未知 | 299,559 | 1,486,031 | 126,268 | 35 | 只报 token | gemini-4-hydrogen-high | 未知 | 未知 | 未知 | 408.0 | 172.0 |
| 31 antigravity gemini-4-hydrogen high | hydrogen-high-a5 |  | 是 | 5 | 是 | 0.794 | 0.794 | 0.794 | 0.000 | 0 | 16.9 | 未知 | 488,815 | 1,401,011 | 128,922 | 41 | 只报 token | gemini-4-hydrogen-high | 未知 | 未知 | 未知 | 482.9 | 127.4 |
| 32 antigravity gemini-4-hydrogen xhigh | hydrogen-xhigh-a1 |  | 是 | 1 | 是 | 0.766 | 0.766 | 0.766 | 0.000 | 0 | 28.0 | 未知 | 685,597 | 1,803,671 | 284,940 | 46 | 只报 token | gemini-4-hydrogen-xhigh | 未知 | 未知 | 未知 | 407.5 | 169.4 |
| 32 antigravity gemini-4-hydrogen xhigh | hydrogen-xhigh-a2 |  | 是 | 2 | 是 | 0.732 | 0.732 | 0.732 | 0.000 | 0 | 42.5 | 未知 | 740,403 | 3,654,851 | 290,240 | 63 | 只报 token | gemini-4-hydrogen-xhigh | 未知 | 未知 | 未知 | 290.1 | 113.7 |
| 32 antigravity gemini-4-hydrogen xhigh | hydrogen-xhigh-a3 |  | 是 | 3 | 是 | 0.761 | 0.761 | 0.761 | 0.000 | 0 | 38.5 | 未知 | 585,302 | 1,313,666 | 373,278 | 39 | 只报 token | gemini-4-hydrogen-xhigh | 未知 | 未知 | 未知 | 253.2 | 161.5 |
| 32 antigravity gemini-4-hydrogen xhigh | hydrogen-xhigh-a4 |  | 是 | 4 | 是 | 0.763 | 0.763 | 0.763 | 0.000 | 0 | 38.8 | 未知 | 657,240 | 2,992,551 | 263,244 | 48 | 只报 token | gemini-4-hydrogen-xhigh | 未知 | 未知 | 未知 | 282.0 | 112.9 |
| 32 antigravity gemini-4-hydrogen xhigh | hydrogen-xhigh-a5 |  | 是 | 5 | 是 | 0.823 | 0.823 | 0.823 | 0.000 | 0 | 36.4 | 未知 | 509,674 | 2,449,512 | 244,005 | 44 | 只报 token | gemini-4-hydrogen-xhigh | 未知 | 未知 | 未知 | 233.4 | 111.7 |
