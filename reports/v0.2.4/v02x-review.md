# Strata 0.2.0–0.2.4 新功能对本工程适配的核查（只读，2026-10-24）

worker（Opus high）报告，Main 整理存档。来源：`artifacts/strata/0.2.4/source.zip` 自带的 0.2.0–0.2.4 六份发布说明，加上 0.2.2、0.2.4 源码的逐文件 diff。0.1.45 源码已删，0.2.0–0.2.2 的改动只能依据发布说明。

## 结论（建议做的改动，按收益排序）

1. **在 `installation_defaults` 显式写 `presence_penalty: 0`**（中等收益，零成本）：
   - 0.2.x 的 `serve/server.py` 有一张 `MODEL_CARD_SAMPLING` 表：请求、Chat 设置和 config 都没给的采样键，用模型卡的值补上。思考关闭（instruct）一档带 `presence_penalty 1.5`。
   - 我们只给了 temperature、top_p、top_k，所以只要 Messages 请求带 `thinking.type: disabled`，greedy 下就会被加 1.5 的存在惩罚。
   - 同时要把它加进 `tools/ops/deployment_source.py` 的 `INSTALLATION_DEFAULTS` 白名单。
   - 属于默认参数改值，要先过独立审查。先验证：零模型抓包看 Claude Code 会不会发 `thinking: disabled`；或在 `STRATA_BATCH_TRACE` 下看采样 trace。
2. **`STRATA_SM86_PERF` A/B**（低收益，plan 第 9 项遗留）：
   - sm_86 开关表默认设 9 个变量，其中 `STRATA_ADAPT_LAG=2` 和我们第 0 维的调参结论相同。
   - 建议保留我们的显式值，A/B 只关另外 8 个开关。
   - 需要先把 `STRATA_SM86_PERF` 加进 `src/model_process.py` 的 `ENVIRONMENT` 白名单，按块交替测。
3. **前缀缓存的尾部检查点**（收益可能不小）：
   - 上游问题第 2 条已查明是 `prompt_cache_every = 16384` 的设计行为。
   - 补救开关：`--prompt-cache-tail`（不改计算，优先测）和 `STRATA_CACHE_MESSAGE_BOUNDARY=1`（草案，会改分块）。
   - 先离线统计已有 ARW 运行里"按 16384 取整"造成的重复 prefill；常见才排速度 A/B。
4. **前端注释过时**：Strata 从 0.1.45 起把 `thinking.budget_tokens` 当作真实预算读，只改注释，逻辑不动。Main 已改。

除此之外，0.2.x 没有能替代本工程适配层的功能。

## 逐条表（相关项）

| 0.2.x 功能 | 本工程适配 | 判断 | 建议 |
|---|---|---|---|
| 模型卡采样默认值 | `config/installation.json` installation_defaults | 要补显式值 | 做（结论 1） |
| sm_86 解码开关表 | `src/model_process.py` ENVIRONMENT；`STRATA_ADAPT_LAG: 2` | 有一项重复，保留 | 按块交替 A/B |
| `--prompt-cache-tail`、message boundary | `src/model_process.py` 白名单 | 可能改进 | 先离线统计 |
| 工具调用解析改进（0.2.2–0.2.4） | `src/hosted_search.py`、`src/output_limit.py` | 不受影响 | 继续在会话检查里统计 |
| 被打断的调用标为 incomplete（0.2.4） | `src/output_limit.py` | 与我们的判定一致 | 不做 |
| custom 工具输入仍到调用结束才整段发出 | 上游问题第 4 条 | 没修 | 输出上限重试保留 |
| `HOSTED_TOOLS` 仍含 web_search、tool_search；Messages 仍不实现 defer_loading | hosted_search、catalog、qwen-agent | 没修 | 保留 |
| 上游 MCP | `src/brave_mcp.py` | 只供自带网页聊天用 | 不做 |
| 会话缓存自动定大小 | 显式值 | 自动值随空闲内存浮动，影响复现 | 保留显式值 |
| 显存预留 512 | 显式 512 | 相同 | 保留 |
| `--pool-workers 15` 建议 | 23 | 已对照 | 维持 23 |
| `--pool-cores`（实验性） | 不在白名单 | 上游自测差异在噪声内 | 低优先级 |
| `STRATA_SPEC_ADAPT_SM86`、`STRATA_ROUTE_PRIOR` | — | 上游 A/B 不显著；会改输出 | 不做 |
| lifeline、`--owner-fd` | `src/model_process.py` 进程树停止 | 可略微简化，收益小 | 不做 |
| 单一思考预算、`answer_room` | 前端分强度预算、guardian 预算 | 上游没有，不能替代 | 保留 |
| `idle_unload_s` | 前端 30 分钟无租约就停进程 | 上游只卸载模型，不认租约 | 保留 |
| `/metrics`、telemetry | `tools/metrics/strata_tokens.py` | 只有聚合值 | 不做 |
| 官方安装程序、`strata update` | upgrade_release、install_offline | 现行决定已定不用 | 维持 |
| `codex_compaction_cache`（默认关） | 无 | 会改压缩时的工具表，输出跟着变 | 超出范围 |

## 可删除的绕过代码

现在没有能删的：
- 第 4 条、第 5 条没修；
- 第 2 条本工程没写绕过代码，已在 `docs/strata-upstream-issues.md` 改为"已解释"；
- 启动提示 monkeypatch 用到的挂钩点在 0.2.4 里都还在。

## 未核实项

- Claude Code 实际会不会发 `thinking: disabled`。这决定结论 1 是不是已经在影响现有运行。
- 0.1.45 是否已有上述几个功能，没有比对。
- 16384 取整造成的重复 prefill 有多大，没有统计。
- `STRATA_SM86_PERF` 的速度和输出差异。
- 前端 `/unload` 在 0.2.4 下是否返回 clean。
