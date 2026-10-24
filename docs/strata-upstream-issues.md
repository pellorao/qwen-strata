# Strata 上游问题

本工程在使用 Strata 时发现的上游缺陷或疑点。用户会定期整理后反馈给上游。ARW 的问题另见 [ARW 上游问题](arw-upstream-issues.md)。

## 1. Windows 上 `--ple-io direct` 的读取速度只达到磁盘能力的约 1/10（已撤回：本机环境原因）

- **撤回说明**（2026-10-11）：前端计划任务从默认的 Below normal（Priority 7）、受限令牌，改为 Normal（Priority 4）、最高权限，大页也授权生效。重启后，同一安装、同一模型纯加载时，PLE 探测值从 12850 rows/s 变为 `PLE direct read probe: 171347 rows/s (fine)`，告警消失。最可能的原因是计划任务的低优先级同时压低了引擎的 I/O 优先级，上游 DETAILS.md 的 Task Scheduler 一节已经说明过这类影响。优先级和大页两项是同时改的，没有分开验证各自的作用。这一项不再作为 Strata 缺陷反馈。
- **可以给上游的建议**：启动时的慢读告警可以像加载慢的提示一样，提到计划任务的优先级可能是原因。

以下是撤回前的原始记录：

- **环境**：rtx3080ti，Windows 11，三星 990 PRO 2TB NVMe；Strata v0.1.42（release），IQ3_XXS。
- **现象**：引擎启动时探测 PLE 读取速度为 12850 rows/s（约 53 MB/s 的 4 KiB 随机读），并警告长提示可能在读第 1 层时耗时数分钟，触发停滞看门狗（上游 #1425、#1629）。
- **磁盘实测**（2026-10-11，未加载模型）：对同一个 PLE 文件（`...-00002-of-00002.gguf`，28.8 GB）做只读的无缓冲 4 KiB 随机读，每个线程用独立句柄做阻塞读，每项测 3 秒：

| 队列深度 | 读次数/秒 | MB/s |
|---:|---:|---:|
| 1 | 13,634 | 55.8 |
| 16 | 138,308 | 566.5 |

- **判断**：
  - 引擎的探测值和队列深度 1 几乎相同，磁盘在并发读下能做到它的约 10 倍。所以瓶颈在引擎的读取路径或它的探测方式，不在磁盘或系统环境。
  - 如果多个线程共用同一个同步句柄，Windows 会把读取串行化，任何队列深度下都只有约 1.33 万次/秒，和引擎值相近。
  - 引擎源码（`direct_file.cpp`）用的是 `FILE_FLAG_NO_BUFFERING | FILE_FLAG_OVERLAPPED` 加完成端口，默认 4 个发起线程，完成端口并发数为 1。按原理不应被串行化，实际原因未查清。
- **本机对照**：`--ple-io mmap` 在本机更慢。同样约 21.6K 的冷请求，mmap 读了 13.4 GB、用时 35.5 秒；direct 读了 0.95 GB、用时 25.8 秒。
- **状态**：已获批做 PLE 路径测量（direct、mmap、direct 加更高读并发），结果出来后补到这里。

## 2. 精确前缀缓存的复用量按 16384 向下取整（已解释：设计行为）

- **环境**：rtx3080ti，Strata v0.1.42，IQ3_XXS，`--kv int8`，`--kv-resident` 20480/32768。2026-10-12 长上下文 KV 驻留测量（[报告](../reports/v0.1.42/iq3_xxs-tuning/kv-resident-long/summary.md)）。
- **现象**：同一会话的后续请求共享首请求的整段前缀，但引擎日志里每个后续请求复用的缓存 token 数都是 16384 的整数倍：
  - 64K 负载：49152，前缀约 64K，每次约 15K 需要重新 prefill；
  - 100K、150K、200K 负载：分别为 98304、147456、196608，每次损失 2–4K。
- **影响**：前缀刚超过 16384 整数倍时损失最大，可达近 16K token 的重复 prefill。两个 kv-resident 条件结果相同。
- **解释**（2026-10-24，0.2.4 源码核查）：`generate.cpp` 里 `prompt_cache_every = 16384` 是定期检查点间隔，请求在最后缓存状态之前分叉时只能退回最近的 16384 倍数位置，不是缺陷。上游有两个默认关闭的补救：`--prompt-cache-tail`（提示末尾附近多存一个检查点，不改计算）和 `STRATA_CACHE_MESSAGE_BOUNDARY=1`（在上一回合边界存检查点，草案，会改分块几何）；`--prompt-cache-every` 已可通过部署调。是否值得测，先离线统计重复 prefill 再定（[核查报告](../reports/v0.2.4/v02x-review.md)）。离线统计（2026-10-24）：重复 prefill 耗时只占推理时间 0.6–1.2%，低于 3% 判据，不做 A/B；只有 100K+ 长上下文负载上限约 7%，以后若看重长会话延迟再测（[统计](../reports/v0.2.4/cache-tail/stats.md)）。

## 3. v0.1.43.1 引擎输出比 v0.1.42 低约 10%（待归因，暂不反馈）

- **环境**：rtx3080ti，IQ3_XXS，`--max-context 156584`、`--kv-resident 20480`，100K 合成检索负载，每实例 3 个请求。
- **现象**：2026-10-14 在 v0.1.43.1 上跑同一负载 4 次，引擎输出 106.2 tok/s（104.7–108.0）。2026-10-12 的 v0.1.42 为 117.7（3 次），低 9.8%。引擎输入低 1.5%。
- **混淆因素**：
  - 两次测量之间，2026-10-13 主机升级了 BIOS 1.C0（微码 0x137），并改用 Intel Default 功耗档（PL1 65 W）。
  - 同一个 v0.1.42 在 BIOS 前后已经掉了约 11%（约 99 对 88）。
  - 发布说明称，Windows NVIDIA 的默认路径与 0.1.42 相同。
- **状态**：未归因，不作为上游缺陷反馈。归因需要在当前主机状态下，对 v0.1.42 和 v0.1.43.1 按块交替测量（[报告](../reports/v0.1.43.1/slowdown-recheck/summary.md)）。

## 4. Codex 遇到 `response.incomplete`（max_output_tokens）直接结束回合（Codex 侧行为，已在前端缓解）

- **环境**：rtx3080ti，Strata v0.1.45，IQ3_XXS；多模型 benchmark 的 Strata Codex 臂（Codex 0.163.0 + ARW），CA 场景 low-a3、low-a5、medium-a2、medium-a3 四个实例。
- **现象**：模型想用一次 `apply_patch` 写完整份报告，输出超过档位的单次输出上限（low 8192、medium 16384，前端按档位补的 `max_output_tokens`）。Strata 按 Responses 协议以 `response.incomplete`、`incomplete_details.reason = max_output_tokens` 结束，截断的调用 `status: incomplete`。Codex 0.163.0 把它当致命错误结束回合：`task_complete.error = "Incomplete response returned, reason: max_output_tokens"`。截断的调用在本地被判为 invalid patch，这条结果没有发回模型，模型没有机会重写，实例就此结束。
- **Strata 侧相关点**：custom 工具（如 `apply_patch`）的输入只在调用结束时整段发出（`serve/responses.py` 的 `Assembler.feed`），所以截断时 `input` 为空，已生成的部分内容全部丢失；function 工具的参数是逐段发的，截断时是半截 JSON。
- **mock 复现**（假引擎 + 真实 Codex 0.163.0，2026-10-20）：同一截断流原样返回时 Codex 报 `turn.failed`；只把结束事件换成 `response.completed` 时回合继续。Claude Code 2.1.304 走 Messages（`stop_reason: max_tokens`、半截 `tool_use`）不中断回合，工具返回 InputValidationError（提到可能是输出被截断），模型下一轮能看到；benchmark 的 Claude Code Strata 臂也有实例这样自己恢复。
- **工程的缓解**（2026-10-20，用户决定在服务端通用处理，经独立审查）：前端 `src/output_limit.py` 只对流式 Responses 回答处理：撞到输出上限时不把截断的回答交给调用方，在内部带一条服务端自动通知重试一次，调用方看到的是正常完成的响应；判定只看协议的输出上限信号。下一版（分支待审，未部署）：上限是服务默认值时，重试上限加倍（最多 24576）、思考上限不变，起因是 strata-codex CStd low-a9 仅靠通知重试仍撞上限。Messages 不处理：Claude Code 已能自行恢复，且在 Anthropic 流里重试要重开已出现的内容块编号，不符合协议。细节见调用手册「撞到输出上限时的内部重试」。
- **可以给上游的建议**：Codex 可以像其他工具失败一样，把 `max_output_tokens` 截断的调用作为失败结果交回模型并继续回合，而不是结束回合；Strata 可以考虑让 custom 工具的输入也逐段发出，截断时至少保留已生成的部分。

## 5. 不实现延迟工具加载：Claude Code `defer_loading` / `tool_reference`、Codex `tool_search`，工具搜索不可用（已在调用方关闭）

- **环境**：rtx3080ti，Strata v0.2.2（引擎 0.1.47）原生服务 `runtime/Strata/serve/frontend.py`；Claude Code 2.1.309 经 `/strata/v1/messages`。
- **现象**：Claude Code 2.1.309 默认开着工具搜索：请求里带 `ToolSearch` 工具和一个 `defer_loading: true` 的占位工具 `DeferredToolPlaceholder`（"never call this tool"），其余内置工具（Cron*、EnterWorktree/ExitWorktree、NotebookEdit、SendMessage、TaskStop、WebFetch）和 MCP 工具（brave 的 3 个）不发 schema，只在 system 角色消息里列出名字，要模型先调用 `ToolSearch`、由返回的 `tool_reference` 块展开定义（零模型抓包，2026-10-24）。
- **Strata 侧相关点**：`serve/frontend.py` 转换工具表时只取 `name`、`description`、`input_schema`（633–634 行），不看 `defer_loading`，占位工具作为普通工具交给模型；`tool_reference` 块属于不读取的内容块，被静默丢弃（`_check_parts`，202–224 行）。所以 `ToolSearch` 的结果到不了模型，延迟工具实际无法调用。
- **工程的处理**（2026-10-24，经独立审查）：`qwen-agent` 设 `ENABLE_TOOL_SEARCH=false`，所有工具以完整定义内联，与 Claude Code 2.1.303 相同（测量 runner `tools/reviewer/claude_headless.py` 同样设置）。前端不按工具名或 `defer_loading` 丢弃工具：前者是专门逻辑，后者会藏掉真实工具。
- **Codex 侧同类机制**（2026-10-24，Codex 0.164.0 零模型抓包）：模型 catalog 的 `supports_search_tool: true` 时，Codex 把 MCP 工具延迟，请求里只有 `{"type":"tool_search","execution":"client"}`。Responses 接口 `serve/responses.py` 把 `tool_search` 归入托管工具丢弃（`HOSTED_TOOLS`），收到 `tool_search_call` 输入回 400，所以 MCP 工具到不了模型。Codex 没有 config 键或命令行开关，只有 catalog 字段。工程处理：`tools/ops/model_catalog.py` 的 `FACTS` 设 `supports_search_tool: False`，MCP 工具以 namespace 内联；无 MCP 时请求不变。ARW benchmark 的冻结 catalog 不改。`incremental_tools`、`skill_search` 对请求无影响。
- **可以给上游的建议**：Messages 接口实现延迟加载：`defer_loading` 的工具不进模型的工具表，`tool_reference` 块展开为对应工具的定义；或至少在收到这两种内容时给出明确的不支持提示，而不是静默丢弃；Responses 接口同理，实现客户端 `tool_search` 或在 Codex 能感知的 catalog 里声明不支持。
