# 内存 6600 → 5600 速度加测（rtx3080ti / IQ3_XXS，Strata 0.2.11，2026-11-08）

只测量，生产未改。完整对比：短提示、M、L 的 decode，L 的 prefill，8 个长生成任务（rep）。5600 一侧：speed 共 9 次冷加载，rep 8 个任务（4 次有效加载 + 1 次作废）。

## 配置核实（ROUTE_PRIOR 关闭）
- 生产自 02:26 的 `e038bbf` 起默认 `STRATA_ROUTE_PRIOR=1.5`，已装 `iq3_xxs-prebuilt.json` 的 `engine_environment` 含该键。驱动 `driver3.py`（派生自 `routeprior2/driver2.py`）在启动临时进程前显式删除该键，也从父环境剔除，`meta.json` 记录实际启动环境：`STRATA_PREFILL_CPU_SHARE=auto`、`STRATA_ADAPT_LAG=2`，无 ROUTE_PRIOR。
- 子进程实际环境（psutil 读取，本次可读）：6 次加载的 `strata.exe` 及其父进程的 `STRATA_ROUTE_PRIOR` 均为空；`STRATA_ADAPT_LAG`、`STRATA_PREFILL_CPU_SHARE` 在。
- 首轮 memspeed（02:07-02:20）早于 02:26 的部署；02:26 部署备份里的旧 prebuilt 配置 `engine_environment` 只有 PREFILL_CPU_SHARE=auto、ADAPT_LAG=2，所以首轮同样无 ROUTE_PRIOR。
- 其余参数、提示、`--spec 4 --mtp`、窗口档位均来自同一已装配置，与 routeprior2 C 臂一致（`git log -- src config` 在基线之后只有 ROUTE_PRIOR 一项）。
- rep 阶段（第二批）每次加载的子进程环境同样读到：`STRATA_ROUTE_PRIOR` 为空（`child-env.json`，驱动日志 `rep-progress.log`）。临时进程 127.0.0.1:8199，经前端停止后运行。

## 基线与可比性
- benchmark v1（multi-model-v1）不能当同配置基线：它的 Strata 臂是 v0.1.45（引擎更早）；0.2.2 起 sm_86 解码开关表和工具调用解析有变（README 现行决定：此后测量不与 0.1.45 结果直接比较）；草稿器当时未钉 MTP（11-03 才钉死）；负载是 Codex / Claude Code 的 reviewer 任务，不是固定提示。其 Strata 引擎输出约 88 tok/s（n=120，SD 约 4）只能作量级参考。
- 同配置（0.2.11、关 ROUTE_PRIOR、6600）的数据：routeprior2 C 臂 speed 3 次冷加载（逐次值在 `routeprior2/speed.txt`）；rep 8 个长生成任务（约 112 tok/s，本次未能加测）；ARW code-spec-v5 rp-off 实例 6600 共 11 个（引擎输出 95.2 / 96.8 tok/s）对 5600 的 4 个（86.1，约 -11%），见 routeprior3。本次沿用第一种。

## 并发负载核对与加载取舍
用 `.claude-user/resmon/events.jsonl` 与小时汇总核对每次加载的时段：
- rep load1（03:42-03:56）与 kaze-sync 的 Go 构建重叠：主机内存 crit（97.0-97.8%）事件 4 次，该小时 CPU 峰值 87.6%。作废，用 load5（04:53-05:07，同 pure 任务）补跑。作废的数据仍留在 `rep-5600.json`（pure 均值 108.8，低于干净的 111.4，方向与并发拖慢一致）。
- rep load2（03:56-04:11）开头有一次 92.9% 的非 severe 内存事件：数值与 Strata 自身占用相同（00:59、01:25 无并发负载时同样出现，strata 进程 5.8 万 MB），不算并发；load3、load4、load5 只有内存温度事件。
- 加测第 6 次加载（短提示 48-58、M 68、L 58-91 tok/s）的原因：当时 Windows 侧日志与引擎日志已随临时目录删除，无法回查。可见证据：该次读入速度也低（短提示 250-270 对其他次 360-400），L3 又恢复到 91，说明是加载期间暂时拖慢；02:00-03:00 的 resmon 小时汇总有 kaze-sync 的 `client.test` 占 CPU 1320 秒、主机 CPU 峰值 98.5%；同时段 Windows 系统/应用事件只有 Windows Update 扫描、PerfNet，没有硬件/降频类记录。结论：最可能是并发 CPU 争用（Strata 用 23 个 pool worker），没有直接证据，原因算"查不清"，按规则补跑替换。
- 替换加载（speed load6，05:08-05:12）期间 resmon 无事件。该次短提示 86.6-109.3，读入 412-460；M 112.7 和 L 103-106 偏低（其他次 M 123-132、L 106-125），仍在 L 的整体离散范围内，未再补跑；M 用 n=9 次均值。

## 结果（5600 = 首轮 3 次 + 加测 5 次 + 替换 1 次 = 9 次冷加载；6600 = routeprior2 C 臂 3 次冷加载）
| 提示 | 6600 均值（SD） | 5600 均值（SD），n=9 次加载 | 差异 | z（Welch） |
|---|---|---|---|---|
| 短故事1 | 99.6（1.9，n=3） | 89.6（6.0） | -10.0% | -4.4 |
| 短代码1 | 112.8（3.8） | 102.8（6.8） | -8.9% | -3.2 |
| 短故事2 | 94.6（3.9） | 82.9（4.2） | -12.4% | -4.5 |
| 短代码2 | 121.0（2.1） | 105.1（4.9） | -13.2% | -7.8 |
| 短提示四项平均 | 107.0 | 95.1 | -11.1% | 超出噪声 |
| M 2.89 万 | 129.2（0.9，n=3） | 126.8（5.9，n=9） | -1.8% | -1.2，噪声内 |
| L 11.9 万 | 118.0（8.8，n=9） | 113.4（10.4，n=27） | -3.9% | -1.3，噪声内 |

读入速度：L 2541（SD 24，基线约 2640，-3.8%）；M 2420（SD 46）。逐次加载短提示均值 97.8/95.0/94.5/97.7/96.8/84.8/93.7/95.0/100.5。

### rep 长生成（8 个任务，开思考 high/8192，上限 24576，温度 0；tok/s = 生成数 / 生成用时）
| 组 | 6600（routeprior2 C 臂） | 5600 | 差异 | 
|---|---|---|---|
| pure 4 任务 | 112.6（SD 0.6，n=4） | 111.4（SD 2.9，n=8：load3、load5 各 4） | -1.0%，噪声内 |
| doc 4 任务 | 116.5（SD 5.3，n=4） | 124.0（SD 16.6，n=8：load2、load4 各 4） | +6.5%，噪声内（任务内容依赖大） |
| 全部 | 114.5（SD 4.1，n=8） | 117.7（SD 13.2，n=16） | +2.8%，噪声内 |

说明：温度 0 的长生成在两次运行间不逐字相同（如 pure-2 生成 19919、13695、19928 token），文档类任务草稿接受率随生成内容变化大（doc-B 142-155 tok/s，doc-A 109-119），所以 doc 组离散大，不能据此说 5600 更快。rep 的 pure 组方向与长上下文 decode 一致（小幅偏慢，噪声内）。

## 结论
- 短提示 decode 慢约 9-13%（四项平均 -11.1%，超出噪声，n=9 次加载）；长上下文 decode（M -1.8%、L -3.9%）和长生成（rep -1% 至 +3%）在噪声内；L 读入慢约 3.8%。与 routeprior3 的 ARW 块（decode -11%、prefill -5%）一致。
- 机理：短提示 decode 主要受内存带宽限制，长上下文和长生成里 attention、KV 读取和草稿接受率的影响掩盖了带宽差。
- 局限：6600 基线 speed 只有 3 次冷加载（M、短提示 n=3）、rep 8 个任务，且无法再增（需用户改 BIOS），精度受限于基线；L、rep 的离散大于差异，只能说"没检出差别"，不能证明等价。
- 数据：`speed-extra.json`（加载 1-5）、`speed-load6-rerun.json`、`rep-5600.json`、`rep-progress.log`、`speed-load6-progress.log`。加测原第 6 次加载的数据保留在 `speed-extra.json` 的键 "6"，不进统计。
