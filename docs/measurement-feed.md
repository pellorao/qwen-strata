# 正式压力测量的离线收尾

入口 `scripts/wsl/finalize-stress-measurement`：离线，不加载模型，不读私有配置。

```sh
python3 scripts/wsl/finalize-stress-measurement \
  --binding <公开的批次绑定.json> \
  --scores <已结束的stress-sr-scores.json> \
  --speed <已结束的stress-speed-detail.txt> \
  --output <projects根目录>/.tasks/qwen-strata/measurements.jsonl
```

默认输出 `~/projects/.tasks/qwen-strata/measurements.jsonl`；测试必须指定临时输出。

## 口径

固定基线见 `reports/rtx3080ti/v0.2.12/` 的 `stress-compare.md`、`stress-sr-scores.json`、`stress-speed-detail.txt`。速度：每版本每档 4 个冷启动实例、每实例 initial-extraction / cached-calculation / cached-update 三个请求，decode 取全部请求的引擎 token / 秒，prefill 只取冷 initial。智力：Spec Readiness v4.3，每版本 n=10 的 `scoreBeforePenalty total` 均值。工作日志速度、speed_probe、短冒烟不能替代。

## 绑定文件

字段为 `tools.metrics.measurement_feed.BINDING` 的全部字段，加被测 `version` 和实际批次完成时间 `ts`（Unix 秒或完整 ISO 时间）。不填文件修改时间、导出时间或基线的日精度界限，不从当前部署推断历史批次版本。只放公开信息。所有字段须逐字匹配当前基线；新主机、配置或协议先登记对应基线。这只校验绑定与汇总格式，不能替代运行时对配置/提示 SHA 的核验。

## 输出

一次收尾追加两行，每档一行（125K、150K；150K 冻结负载实际 150254 token）。每行含智力分数、decode/prefill、完成时间、主机、版本、配置、协议、`baseline_id` 和两个源文件的 SHA256；两档分别与各自基线的 95% 线比较。

## 失败条件

两档与评分全部校验通过后才打开输出追加。缺档、缺版本、协议错误、非有限值、绑定与基线不一致都失败，且不写输出。应由单一批次驱动在全部实例关闭、租约归还、正式盲裁和汇总完成后调用一次并传递退出码；重复调用会追加重复行（消费者按每项最新完成时间读取）。
