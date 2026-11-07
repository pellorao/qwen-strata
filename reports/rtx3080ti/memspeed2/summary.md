# 内存 6600 → 5600 速度加测（rtx3080ti / IQ3_XXS，Strata 0.2.11，2026-11-08）

只测量，生产未改。用户要求中途停止：只完成了 speed 加测（6 次冷加载），计划中的 rep 长生成（4 次加载）未运行。

## 配置核实（ROUTE_PRIOR 关闭）
- 生产自 02:26 的 `e038bbf` 起默认 `STRATA_ROUTE_PRIOR=1.5`，已装 `iq3_xxs-prebuilt.json` 的 `engine_environment` 含该键。驱动 `driver3.py`（派生自 `routeprior2/driver2.py`）在启动临时进程前显式删除该键，也从父环境剔除，`meta.json` 记录实际启动环境：`STRATA_PREFILL_CPU_SHARE=auto`、`STRATA_ADAPT_LAG=2`，无 ROUTE_PRIOR。
- 子进程实际环境（psutil 读取，本次可读）：6 次加载的 `strata.exe` 及其父进程的 `STRATA_ROUTE_PRIOR` 均为空；`STRATA_ADAPT_LAG`、`STRATA_PREFILL_CPU_SHARE` 在。
- 首轮 memspeed（02:07-02:20）早于 02:26 的部署；02:26 部署备份里的旧 prebuilt 配置 `engine_environment` 只有 PREFILL_CPU_SHARE=auto、ADAPT_LAG=2，所以首轮同样无 ROUTE_PRIOR。
- 其余参数、提示、`--spec 4 --mtp`、窗口档位均来自同一已装配置，与 routeprior2 C 臂一致（`git log -- src config` 在基线之后只有 ROUTE_PRIOR 一项）。

## 基线与可比性
- benchmark v1（multi-model-v1）不能当同配置基线：它的 Strata 臂是 v0.1.45（引擎更早）；0.2.2 起 sm_86 解码开关表和工具调用解析有变（README 现行决定：此后测量不与 0.1.45 结果直接比较）；草稿器当时未钉 MTP（11-03 才钉死）；负载是 Codex / Claude Code 的 reviewer 任务，不是固定提示。其 Strata 引擎输出约 88 tok/s（n=120，SD 约 4）只能作量级参考。
- 同配置（0.2.11、关 ROUTE_PRIOR、6600）的数据：routeprior2 C 臂 speed 3 次冷加载（逐次值在 `routeprior2/speed.txt`）；rep 8 个长生成任务（约 112 tok/s，本次未能加测）；ARW code-spec-v5 rp-off 实例 6600 共 11 个（引擎输出 95.2 / 96.8 tok/s）对 5600 的 4 个（86.1，约 -11%），见 routeprior3。本次沿用第一种。

## 结果（5600 = 首轮 3 次 + 加测 6 次冷加载；6600 = routeprior2 C 臂 3 次）
加测第 6 次加载出现整体降速（短提示均值 53、M 68、L 70 tok/s，低于 60 的降速线；读入速度正常 2540），原因未查，按意外事件记录：下表给排除该次的结果（n=8 次加载），含该次的在后。

| 提示 | 6600 均值（SD） | 5600 均值（SD），n=8 次加载 | 差异 | z（Welch） |
|---|---|---|---|---|
| 短故事1 | 99.6（1.9，n=3） | 88.6（5.6） | -11.0% | -4.9 |
| 短代码1 | 112.8（3.8） | 102.1（6.9） | -9.5% | -3.3 |
| 短故事2 | 94.6（3.9） | 82.4（4.2） | -12.9% | -4.6 |
| 短代码2 | 121.0（2.1） | 104.5（5.0） | -13.6% | -7.7 |
| 短提示四项平均 | 107.0 | 94.4 | -11.8% | 超出噪声 |
| M 2.89 万 | 129.2（0.9） | 128.6（2.9） | -0.5% | -0.5，噪声内 |
| L 11.9 万 | 118.0（8.8，n=9） | 114.5（10.6，n=24） | -3.0% | -1.0，噪声内 |

含第 6 次加载（n=9）：短提示平均 89.8（-16.1%）、M 121.9（-5.6%）、L 109.5（-7.2%，SD 18.2）。读入速度：L 2544（SD 22），较基线约 2640 低约 3.6%；M 2405。逐次加载：短提示均值 97.7/96.8/84.8/93.7/95.0/53.2，L 均值 118.8/106.6/114.2/119.7/119.5/69.6（加载 1-6）。显存峰值 11460-11553 MiB，内存占用峰值 90.7-93.3%，加载均 16.2 秒。

## 结论
- 短提示 decode 慢约 10-14%，超出噪声（加测使首轮 -10.5% 的估计更稳，方向和量级一致）；长上下文（M、L）decode 在噪声内（-0.5%、-3%）；读入慢约 3-4%。与 routeprior3 的 ARW 块（decode -11%、prefill -5%）一致。
- 局限：6600 基线只有 3 次冷加载且无法再增（需用户改 BIOS），所以精度受基线限制；加测的 L 与 5600 之间的 SD（10.6）比基线（8.8）大；第 6 次加载降速未查；rep 长生成对照未跑。
- 续跑：`.tmp/memspeed2/driver3.py rep`（Windows 侧，`C:\Users\pello\AppData\Local\Temp\memspeed2\`，用安装目录 venv python，先停前端），4 次加载约 60-70 分钟。
