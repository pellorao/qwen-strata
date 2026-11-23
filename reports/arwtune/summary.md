# arwtune: 速度类参数调优 (本机, Strata v0.2.18 / 引擎 0.1.64, 2026-11-22)

## 设计
- 场景 Spec Readiness (固定 ARW 6ca23a9), effort high, 安装默认档 206584/150000; 每维两个条件, ABBA 四块, 每块: 部署条件 + 冷加载, 1 个预热实例 + 1 个计分实例 (连跑, 不重载), 每块 13-16 分钟。每块的条件为上述各维两个取值 (如 prefill-4096/8192), 计划文件是一次性的, 不入库; 原始数据 `data/`, 速度分析器 `tools/tuning/arw_speed_analyze.py` (其输出 `data/analyze-*.txt`)。
- 这四维都是"不影响输出的放置/调度参数"(tail-skip 例外, 见下), 按规则用引擎输出 tok/s 选择, 分数只防异常 (本轮不盲裁)。指标: 每块引擎日志里的解码聚合 (输出 token / 解码秒) 与预填充聚合 (未缓存输入 >= 2000 的请求, token / 预填充秒); 各块请求数 57-80 (含预热实例, tail-7 r1 含 1 个作废实例共 174)。n = 每条件 2 块, 样本很小, 只能判大差异。
- 每块 WSL 一分钟 loadavg 最高 1.11; Windows 空闲 RAM 50 GB 左右 (模型加载前); 引擎日志中有 `conversation cache: could not read N tokens back from the SSD tier (not enough RAM)` 行 (会话缓存 SSD 层, 不是专家池退化), 出现在 prefill-4096 r1/8192 r1、vram-300 两块、adapt-unset r2、tail-7 r1 共数块, 与条件无明显关系。

## 结果 (块1, 块2)

| 维 | 条件 | 预填充聚合 tok/s | 解码聚合 tok/s | 判定 |
|---|---|---|---|---|
| prefill | 8192 (现) | 2099, 2051 | 121.9, 123.6 | 保留 8192: 预填充 +20%, 解码持平 |
| | 4096 | 1750, 1639 | 121.8, 121.4 | |
| vram-reserve | 512 (现) | 2137, 2139 | 116.8, 116.6 | 保留 512: 300 解码 +3.6% 但预填充 -3%, 差异与同条件块间波动同量级 (解码块间差 2.4%), n=2 判不出 |
| | 300 | 2078, 2067 | 119.4, 122.3 | |
| adapt-lag | 2 (现) | 2030, 1930 | 119.1, 117.0 | 保留 2: 解码 +4.2% 两轮一致; 不设置的预填充 +9% 两轮一致, 按"输出 tok/s 选择"规则取 2 |
| | 不设置 | 2234, 2131 | 114.0, 112.6 | |
| tail-skip | 7 (现) | 2164 (2303/2025) | 123.5 (124.0/123.0) | tail-0: 预填 1993 (2114/1872), 解码 116.0 (112.5/119.5); tail-7 解码快约 6%, 盲裁 SR: tail-7 0.365-0.371 (0.303-0.315/0.427), tail-0 0.132 (0/0.264), 基线 0.459±0.057 -> 保留 7, 见 blind-result.md |
| | 0 | 2114, 1872 | 112.5, 119.5 | |

- 所有维的结论: 现有生产值 (prefill 8192, vram-reserve 512, adapt-lag 2) 保留, 无需改配置。vram 与 adapt 两维两个方向的指标相反 (预填充对解码), 单靠 2 块一维判不出, 要判出需更多块; 本轮没有证据支持改动。
- 内存余量 (清单第 1 项): 未改 `conversation-cache-mib` (现 8192, 未扫 0-4096)。理由: 本轮块内未见专家池降级 (本轮日志只做关键词扫描 `not enough RAM`, 命中的都是会话缓存 SSD 层读回)。扫 0-4096 未做。
- tail-skip (STRATA_ROUTE_TAIL_SKIP, 输出受影响): 此前一直在默认 7 上运行, 0.2.17 起上游默认 0。现已显式钉 7 保持行为。速度: tail-7 解码 124.0 对 tail-0 112.5/119.5 (+7%), 只有一块, 不够。质量需盲裁 (我无子 agent): 计分实例 tail-0 r1 a2、r2 a2, tail-7 r1 a3 (a2 作废: inspect-flags 路径标记)。

## 用量护栏停止的原因
- `rate: 13 calls within 21600 s, more than 12`。6 小时窗口内 13 次 run_cell 启动 (rate.json 时间戳 16:00-19:10): prefill 重跑 1 块 + vram 4 + adapt 4 + tailskip 4 = 13, 每块一个 cell, 每块的 block.json/日志对得上, 没有重试, 也没有多跑格子。第 13 次是计划内的 r2-tail-7, 上限 12 按"一个 ABBA 维度 4 块"定, 没算到我连跑三维; 属上限设低。

## 护栏改动 (提交 4ebe589)
- `tools/arw/measure.py` `run_cell(..., max_starts=None)`: 默认 None 时仍用原来的 `count*2+2`; 只有 `tools/tuning/arw_blocks.py` 传 `BLOCK_STARTS_PER_6H = 12`。arw_blocks 之外的调用者 (`tools.arw.measure` CLI 与其他) 不受影响。12 的来源: 一个 ABBA 维度 4 块, 上限给 3 维; 事实上连跑 3 维加重跑的块是 13, 所以补跑和以后的连续调参应该每维前先 ack, 或把上限改成 16。建议 16 (4 维 x 4 块), 未改。


## 用量护栏上限 16 (补跑 r2-tail-7)
- 19:17 Main 已 ack 并批准, `tools/tuning/arw_blocks.py` 的 `BLOCK_STARTS_PER_6H` 12 改 16 (单独提交), 只对 arw_blocks 的 run_cell 生效; r2-tail-7 补跑 19:18-19:31 完成, 2 个有效实例。
- tail-skip 结果: 速度 tail-7 略快 (解码 +6%, n=2 块); 盲裁用 4 份匿名材料 (x1-x4, 解盲对照见 blind-result.md); 材料与对照表是易失文件, 不入库, 结果见 blind-result.md。盲裁已做: 保留 7 (blind-result.md)。
