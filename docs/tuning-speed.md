# 调参目标一：提速

Strata 的调参有两个目标（用户 2026-11-08）：**提高速度**（本页）和**维持或提升智力水平**（见[智力](tuning-quality.md)）。两个目标分开记录历史与进展；同一个改动对两边都有影响时两页各记一次。主机与量化各自独立。细节与证据在各报告、[每机调参](host-tuning/rtx3080ti.md)和[调优记录](tuning.md)。

## 当前状态（rtx3080ti / IQ3_XXS，Strata 0.2.11）

引擎输出：ARW 负载约 95 tok/s（路由先验关）/ 约 134 tok/s（开，生产默认）；固定提示短输入约 95-107、12 万长输入约 115-118 tok/s（内存 5600/6600 之间，路由先验关）。

## 历史与进展

| 日期 | 事项 | 结论 | 入口 |
|---|---|---|---|
| 2026-10-11 | v0.1.42 逐维调参：pcie-frac 实测、pool-affinity all、pool-workers 23、ple-io direct、cpu-prefill-share auto、spec-min-p 0.9、adapt-lag 2、vram-reserve 512、kv-resident 20480、spec 4 | 各维结论与报告见表 | [rtx3080ti 调参](host-tuning/rtx3080ti.md) |
| 2026-10-22/24 | 升级 0.2.2、0.2.4 | sm_86 解码开关表变，此后不与 0.1.45 直接比较 | [README 现行决定](../README.md) |
| 2026-11-03 | 草稿器钉死 MTP | DFlash2 评估（11-07）无提升，长输入更慢 | [主机说明](hosts/rtx3080ti.md) |
| 2026-11-07 | prefill 档位 | 16384/32768 被引擎降回 8192，auto 为 7680，差异在 ±2% 内，生产不改 | `.tasks` prefill-report（本机） |
| 2026-11-07/08 | `STRATA_ROUTE_PRIOR=1.5` | 每实例约快 35%（338 对 516 秒），decode 约 134 对 91 tok/s；用户选 B 生产默认开启 | [routeprior2](../reports/rtx3080ti/routeprior2/summary.md) · [routeprior3](../reports/rtx3080ti/routeprior3/summary.md) |
| 2026-11-08 | 内存频率 6600→5600 | 见下 | [memspeed](../reports/rtx3080ti/memspeed/summary.md) · [memspeed2](../reports/rtx3080ti/memspeed2/summary.md) |

## 内存频率对速度的影响

长期参考：DDR5 从 6600 降到 5600（-15% 带宽）对本机 IQ3_XXS 的影响（Strata 0.2.11，关路由先验，同一临时进程驱动、固定提示、温度 0）。5600 一侧 speed 共 9 次冷加载、rep 8 个任务；6600 基线为 routeprior2 C 臂（speed 3 次冷加载，L 9 个值；rep 8 个任务）。

| 负载 | 样本（6600 / 5600） | decode | prefill |
|---|---|---|---|
| 短提示（约 300 token，四项平均） | 3 / 9 次加载 | -11%（-9% 至 -13%），超出噪声 | 无基线 |
| M 2.89 万 token | 3 / 9 | -1.8%，噪声内 | 无基线 |
| L 11.9 万 token | 9 / 27 | -3.9%，噪声内 | 约 -3.8%（2541 对 2640） |
| rep 长生成 8 任务（思考开，至 2.4 万 token） | 8 / 16 | pure -1.0%、doc +6.5%、合计 +2.8%，均噪声内 | 不适用 |
| ARW 代码规格实例（routeprior3 块） | 11 / 4 个实例 | 约 -11%（96.8 → 86.1） | 约 -5% |

草稿接受率不变，所以是带宽使单步变慢，不是投机行为变化。长生成温度 0 也不逐字重复，文档类任务的接受率随内容变化大，所以 rep 离散大（doc 组 SD 16.6），不能读成 5600 更快。每实例工作时间无明显差别（500 对 532 秒，实例间 SD 约 100 秒）。意义：内存降频的速度代价集中在短提示/短输出的 decode（约 11%），长上下文和长生成内没检出；折算到 agent 工作约个位数百分比，小于路由先验带来的约 35% 提升。局限：6600 基线样本少且无法再增（需用户改 BIOS），长上下文和 rep 只能说"没检出差别"。过程中有并发负载的加载（rep 一次与 Go 构建重叠、speed 一次整体降速）已作废并补跑，核对依据见报告。报告：[memspeed2](../reports/rtx3080ti/memspeed2/summary.md)。

## 未决

- 参数在 v0.2.4-v0.2.11 上未重新调参。
