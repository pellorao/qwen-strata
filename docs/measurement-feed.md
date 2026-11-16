# 正式压力测量的离线收尾

当前固定基线来自 `reports/rtx3080ti/v0.2.12/stress-compare.md`、
`stress-sr-scores.json` 和 `stress-speed-detail.txt`。速度是每版本每档
4 个冷启动实例、每实例 initial-extraction / cached-calculation / cached-update
三个请求；decode 用全部请求的引擎 token / 秒，prefill 仅用冷 initial。
智力是 Spec Readiness v4.3 每版本 n=10 的 `scoreBeforePenalty total` 均值。
不能用工作日志速度、speed_probe 或短冒烟替代。

收尾入口（离线，不加载模型，不读取私有配置）：

```sh
python3 scripts/wsl/finalize-stress-measurement \
  --binding <公开的批次绑定.json> \
  --scores <已结束的stress-sr-scores.json> \
  --speed <已结束的stress-speed-detail.txt> \
  --output <projects根目录>/.tasks/qwen-strata/measurements.jsonl
```

默认输出是 `~/projects/.tasks/qwen-strata/measurements.jsonl`。测试必须指定临时输出。
绑定文件包含 `tools.metrics.measurement_feed.BINDING` 的全部字段，追加被测
`version` 和实际批次完成时间 `ts`（Unix 秒或完整 ISO 时间）。不要填文件修改时间、
导出时间或基线的日精度界限，不从当前部署推断历史批次版本。绑定文件只放公开信息。
所有字段逐字匹配当前基线；新主机、配置或协议先登记对应基线，不能沿用此绑定。
这仅校验提供的绑定与汇总格式，不能替代实际运行时的配置/提示 SHA 核验。

一次收尾追加两行，每个上下文档位一行，均含智力分数、decode/prefill、完成时间、
主机、版本、配置、协议、baseline_id，以及两个源文件的 SHA256。125K 与 150K
分别比较各自基线的 95% 线；150K 冻结负载实际 150254 token，按用户决定纳入上端。
完整校验两档及评分后才打开输出追加，缺档、缺版本、错误协议、非有限值都失败。
收尾应由单一批次驱动调用一次；重复调用会追加重复行，消费者按每项最新完成时间读取。

## 驱动接入边界

仓库 `scripts/` 没有现存的正式压力批次驱动。历史任务
`qwen-strata/v0212test` 的驱动位于 `.tmp/v0212test/driver.py`，任务记录说明
该目录在评分结束后已删除；不能声称已修改了这个驱动。
恢复正式驱动时，在全部实例关闭、租约归还、正式盲裁和汇总完成之后调用此入口，
并传递失败退出码。`arw_measure` 结束时尚未盲裁，不能在那里导出智力结果；
每日 `engine_speed` 是缓存工作负载，也不能导出成该冷压力协议。

## 服务遥测

服务遥测保持待埋点。前端 HTTP 日志只有时间、地址、路由、状态，token 引擎记录
没有逐请求时间或关联 ID；现有 `engine_speed` 按完成顺序对齐并报告 `unaligned`，
不足以可靠导出 TTFT 和租约生命周期。缺失字段与证据见本次任务报告。
