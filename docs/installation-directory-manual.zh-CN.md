# Strata 模型服务详细调用手册

[English](caller-manual.md) | [简体中文](caller-manual.zh-CN.md)

读完[简介](../../README.zh-CN.md)了解前端地址和一次完整调用的示例（含 Python 示例）后，如果你需要查阅具体接口、参数和接入配置，或者排查运行中的问题，可以在本手册中找到详细说明：涵盖租约、全部接口、启动参数、推理强度与输出、Codex 与 Claude Code 的接入、网页搜索、日志、已观察到的执行异常和防重复建议。

在运行长时间任务前，请先阅读[已观察到的执行异常](#已观察到的执行异常)及[调用方动态防重复建议](#调用方动态防重复建议)，并为整个任务设置截止时间。

## 独占租约

同一时间只有一个持有者。调用方按以下顺序领取、使用和归还租约：

1. 调用 `POST /lease/acquire` 领取 key。如果已有持有者，接口直接返回 409；不排队、不抢占。
2. 拿到 key 后，之后的请求都要带 `Authorization: Bearer <key>`（也接受 `x-api-key: <key>`），包括模型启停、状态和推理。缺失、错误或已归还的 key 会返回 403。
3. 调用 `POST /model/start` 选择上下文档位并等待模型就绪。如果上一个租约留下的正是同一模型、同一档位，服务会直接复用而不重新加载，并返回 `reused: true`；否则会先停掉旧模型再启动。
4. 调用 `POST /model/stop` 只停模型，租约仍保留在当前调用方手中，因此可换档位重新启动。
5. 任务结束后调用 `POST /lease/release` 归还租约：这会撤销 key，但**模型继续加载**，留给下一个调用方复用。没有租约的模型在空闲 30 分钟后由前端停止；如果要立即释放内存和显存，请在归还前先调用 `/model/stop`。

因为租约只保存在前端内存中，既没有超时，也不自动回收，所以调用方必须在自己的 finally 路径里归还。一旦 key 丢失或持有者异常退出，服务不提供无 key 夺取接口，只能由维护者重启前端——重启会停止模型并清空租约。此外，key 是调用方凭据，不写入提示词、版本控制、共享日志或报告。

## 接口

前端同时提供租约与模型管理接口，以及推理入口。所有路径都相对于[前端地址](../../README.zh-CN.md#地址)，发送 JSON 请求时使用 `Content-Type: application/json`。

| 方法与路径 | key | 说明 |
|---|---|---|
| `GET /health` | 不需要 | 前端身份、`lease`（free/held）、当前加载的模型 ID、该模型实际加载的启动提示 SHA（`startup_instructions`，只有 SHA 和开关，不含正文；未加载时为 null）；不代表模型可推理 |
| `POST /lease/acquire` | 不需要 | 请求 `{}`；返回 `key` |
| `POST /lease/release` | 需要 | 请求 `{}`；撤销 key，返回 `lease` 和仍加载的 `model`（不停模型） |
| `POST /model/start` | 需要 | 只接受 `model` 和 `context_window`，见下文；就绪后返回状态，`reused` 表示是否复用了已加载的模型 |
| `POST /maintenance/model/start` | 需要 | 维护工程的测量和调参专用，接受完整维护选项；不是调用接口，调用方不得使用 |
| `POST /model/stop` | 需要 | 请求 `{}`；返回 `status=stopped` 及是否正常卸载 |
| `GET /model/status` | 需要 | `status` 为 stopped、starting、unloaded 或 running；运行时含 `native_health` |
| `POST /admin/shutdown` | 需要 | 维护用；模型停止后关闭前端 |
| `/strata/v1/chat/completions` | 需要 | OpenAI Chat |
| `/strata/v1/responses` | 需要 | OpenAI Responses（Codex） |
| `/strata/v1/messages`、`/strata/v1/messages/count_tokens` | 需要 | Anthropic Messages（Claude Code） |

之所以所有请求都要经过前端，是因为本机内部的原生 Strata 服务只监听 127.0.0.1，并使用每次启动随机生成的内部 key，调用方无法绕过前端访问。发往 `/strata/` 下的请求会原样转发给原生 Strata 服务，响应（含流式）也原样返回。

转发前，前端只做四件事：
- 请求的 `model` 必须等于当前加载的模型 ID，否则返回 409；省略时自动填入。没有运行中的模型则返回 503。
- Chat 和 Responses 请求缺少推理强度、思考预算或输出上限时，按[推理强度与输出](#推理强度与输出)补齐。
- Responses 流式请求声明了 `{"type": "web_search"}` 时，由前端经 Brave 执行搜索，见[网页搜索](#网页搜索)。
- Messages 请求缺少思考预算时，前端会补齐思考上限，但不补 `max_tokens`，该项由调用方自行设置（见 Claude Code 一节）。

### 错误

请求被拒绝或执行失败时，前端按以下状态码返回原因：

| 状态码 | 含义 |
|---|---|
| 403 | key 无效，或客户端地址不在本地网络 |
| 409 | 租约已被持有、请求的模型与已加载模型不一致，或关闭前端时模型未停 |
| 400 | 启动参数或请求体无效 |
| 503 | 模型未运行、启动失败或停止失败；详情见安装目录 `logs/` |

需要注意，流式响应在返回 HTTP 200 之后仍可能失败。判断终态必须以流内事件为准，不能只看 HTTP 状态；看到断流后，不要盲目重试那些可能已经执行过工具的请求。

## 启动参数

引擎参数、环境变量、采样默认值、思考预算和输出上限都由安装目录按"本机 + 量化"预置，调用方不能覆盖。调用方只能选择两项：**上下文大小**（启动时选择档位）、**推理强度**（随每个请求传递）；模型固定为本机对外的那一个。

其中，模型和上下文大小通过 `POST /model/start` 传入，示例如下：

```json
{"model": "{{model}}", "context_window": {{example_context_window}}}
```

| 字段 | 说明 |
|---|---|
| `model` | 可省略。本机只对外提供一个模型，即 `config/deployment.json` 中 `models` 列出的那一个，省略即用它；安装目录里其他量化的权重不对外，请求它们返回 400 |
| `context_window` | 可省略，省略为对外模型的第一档。只能取安装目录 `config/deployment.json` 中 `context_tiers.<模型>` 列出的 `context_window`；每档附带实测的 `auto_compact_token_limit`，调用方必须把自己 harness 的窗口和自动压缩阈值设为同一档的这两个值。该量化没有列出档位时只能省略 |

传入其他字段会返回 400。推理强度的传参规则见[推理强度与输出](#推理强度与输出)。

当调用方换档位时，`/model/start` 会自动先停掉旧模型；判断是否"相同"并可复用时，按校验后的完整运行配置比较，包括部署后改动的安装预置。启动完成时，前端还会核对实际加载的模型和上下文容量。

对外模型的模型 ID 为 `qwen3.8-flash-next-` 加对外模型名的小写（如 {{model}} 为 `{{model_slug}}`）。

### 安装预置

{{local.presets}}

## 推理强度与输出

每次推理请求都可以指定推理强度和输出上限：Responses 使用 `reasoning.effort` 和 `max_output_tokens`，Chat 使用 `reasoning_effort` 和 `max_tokens`。请求指定的值优先；请求未指定时，由前端按下表自动补齐。

| 强度 | 思考 token 上限 | 默认总输出上限（含思考） |
|---|---:|---:|
| low | 2048 | 8192 |
| medium | 4096 | 16384 |
| high、xhigh、max | 8192 | 24576 |

服务不提供 none 档：请求指定其他强度（包括 none）时会返回 400。在此基础上，不同场景和参数组合遵循以下规则：

- Codex 的 guardian 审批请求有单独的默认值，与强度无关：思考 512、总输出 1024（安装预置，与 `bin/qwen-approve` 相同）。服务不看提示词内容，而是按 Codex 随请求发送的元数据识别它，即 `client_metadata["x-codex-turn-metadata"]` 中 `thread_source` 为 `guardian_review`。审批只需输出一段简短的 JSON 结论。由于 Strata 会为回答保留 min(max(512, 总输出/4), 总输出/2) 的空间，当总输出为 1024 时正好保留 512，思考可以用满 512。如果请求自己给了思考预算或输出上限，则以请求为准。实际调用时，Codex 对 guardian 请求发 `reasoning_effort: low`、不带输出上限和采样字段，而 `bin/qwen-approve` 也显式发同样的值，所以两边审批参数相同。
- 与该次运行默认强度相同的请求，直接使用默认值中的预算和输出上限（当前为 {{reasoning_effort}}，思考 {{reasoning_budget_tokens}}／总输出 {{max_tokens}}）。
- 当请求自己给了输出上限、没给思考预算时，思考预算不超过输出上限的一半；Strata 另外为回答至少保留输出上限的 1/4。
- 思考上限不等于实际思考长度。当请求给的输出上限超出窗口剩余空间时，服务会将其缩短到剩余空间，不返回 400；但如果输入本身超出窗口，仍返回 400，不会静默裁剪输入。
- Messages 接口按 Anthropic 协议由调用方设置 `max_tokens`，因此前端不补总输出，只补思考上限，见下文 Claude Code 一节。

### 撞到输出上限时的内部重试

在 Codex 中，一旦模型输出因撞到总输出上限而截断，Codex 就会直接结束当前回合；模型既不知道原因，也没有机会重写。为此，对于 Responses 的**流式**请求，如果模型这一次输出撞到总输出上限（即以 `response.incomplete`、`incomplete_details.reason = max_output_tokens` 结束），前端不会把截断的回答直接交给调用方，而是在内部自动重新生成一次。

- 触发判定只看协议里的这个信号，不看工具名、提示词或客户端，对所有客户端和任务一样。
- 重试请求 = 原请求 + 这次已经完整交给调用方的推理和文本 + 一条服务端自动通知。该通知作为用户消息发送，并注明来自模型服务、不是用户：说明上一次输出达到输出上限、在写什么时被截断、截断部分已丢弃未执行，要求模型重新回应上一个请求，缩短输出，或把必须很长的输出分成几步（例如几次较小的工具调用），不要再写同样一次很长的输出。通知不写具体数字，只进转发给模型的请求，不进响应，也不写回调用方的历史。
- 当输出上限是服务按强度补的默认值（即请求没给 `max_output_tokens`）时，重试的上限会加倍，但不超过 24576（high 档的总输出）；同时思考上限不变，多出的空间全部留给回答，通知里也会说明这次空间更大。反之，请求自己给了 `max_output_tokens` 的，重试沿用原值，只加通知。因此，没给上限的调用方收到的 `output_tokens` 可能超过该强度的默认总输出。如果上限超出窗口剩余空间，服务照常将其缩短到剩余空间——这时通知仍说空间更大，可能与实际不符。Codex guardian 请求的 1024 也是服务预置值，重试时同样加倍。
- 对调用方而言，看到的是同一个响应接着流下去：被截断的那一项只出现过开头和增量，没有完成事件，因此不进入调用方历史，也不会被执行；重试的事件会重新编号后接在后面。至于没撞上限的响应，则逐字节原样转发，不增加延迟。
- 每个请求最多重试 1 次；当上限加倍时，重试最长约是第一次的 2 倍耗时。如果重试仍撞上限、重试无法开始、处理中出现意外错误，或截断前已经有工具调用完整交给了调用方（此时调用方可能已在执行），前端就照原样返回截断的结果。
- 调用方收到的 usage 是最后一次生成的值，与它的上下文一致；被丢弃那次的上限、token 和耗时记在 `logs/frontend.log` 的 `output limit:` 行，而引擎日志里两次生成都有。
- 以下情况不处理，撞上限时行为与以前相同：一是 Messages（Claude Code），因为 Claude Code 自己会把截断的工具调用作为失败结果交回模型并继续，而在 Anthropic 流里重试必须重开已出现过的内容块编号，不符合协议；二是非流式请求、Chat 接口和托管 web_search 的 Responses 请求。

## 启动脚本（WSL）

在 WSL 中运行 Codex 或 Claude Code 时，无需手动调用租约与模型接口；`bin/qwen-agent` 会自动完成整个生命周期：领取租约 → 启动模型 → 运行 Codex 或 Claude Code → 退出后归还租约（模型留给下一次复用）。该脚本只依赖本安装目录和 Python 3 标准库。

```bash
qwen_install={{installation_wsl}}
python3 "$qwen_install/bin/qwen-agent" codex                       # 交互式 Codex，本机对外模型、high
python3 "$qwen_install/bin/qwen-agent" --effort medium codex exec "任务描述"
python3 "$qwen_install/bin/qwen-agent" claude                      # Claude Code
```

脚本在管理租约和隔离环境时遵循以下规则：

- `--model` 可省略，默认即本机对外模型（`config/deployment.json` 的 `models`）；如果写其他量化，脚本会在领租约前报错退出。
- 租约已被他人持有时立即退出，不排队、不抢占。
- 模型加载耗时：{{local.load_time}}；使用相同参数复用已加载的模型时不再重新加载。运行期间 Ctrl-C 交给 agent 处理；无论 agent 退出、终端关闭还是进程被终止，脚本都会归还租约，并在归还失败时提示重启前端任务。
- key 只放在 agent 进程的环境变量里，不写入文件或命令行参数。
- 调用方环境中的 `ANTHROPIC_*`、`OPENAI_*`、`AI_AGENT` 和以 `CLAUDE` 开头的变量（`CLAUDE_CONFIG_DIR` 除外）不会传给 agent；所以在 Claude Code 会话里启动时，agent 拿不到父会话的会话 id 和消息通道。需要的 Claude Code 定制写进 settings.json 的 `env`。
- 脚本不修改调用方的 `~/.codex` 或 `~/.claude` 配置；所有设置都以命令行覆盖或环境变量传入。

## Codex 接入

如果不通过启动脚本、而是自行配置 Codex 接入本服务，请照以下参数设置。这也是启动脚本传给 Codex 的实际配置（以 {{model}} 默认档为例，窗口和阈值取所用量化在 `config/deployment.json` 中的第一档）：

```toml
model = "{{model_slug}}"
model_provider = "qwen_strata"
model_catalog_json = "{{installation_wsl}}/config/model-catalog.json"
experimental_compact_prompt_file = "{{installation_wsl}}/config/prompts/compact-prompt.txt"
model_context_window = {{context_window}}
model_auto_compact_token_limit = {{auto_compact_token_limit}}
web_search = "live"

[model_providers.qwen_strata]
name = "Local Strata"
base_url = "{{base_url}}/strata/v1"
wire_api = "responses"
env_key = "QWEN_STRATA_KEY"
requires_openai_auth = false
supports_websockets = false
request_max_retries = 0
stream_max_retries = 0
```

其中，租约 key 通过 `env_key` 指定的环境变量只提供给该 harness；同时将请求重试设为 0，避免重试重复已执行的工具操作。

如果程序在测量或批处理时每次运行都新建 `CODEX_HOME`，请另加 `-c features.plugins=false`，或在该目录的 `config.toml` 写 `[features]` `plugins = false`；否则 Codex 0.162 会在每个新目录克隆约 105MB 的插件仓库，而这些内容并不进入模型输入。固定使用 `~/.codex` 的交互式用法只克隆一次，不需要设置。

配置中的 `config/model-catalog.json` 只描述本机对外模型的事实：模型名、推理档位、窗口（本机该模型的默认档，即 `config/deployment.json` 中 `context_tiers` 的第一档）、只接收文本、可使用网页搜索工具，以及 `auto_review_model_override` 指向自身。基础指令与消息结构取自所装 Codex 版本自带的 luna 模型条目，不额外限制工作内容；只读、可写范围等约束由各场景的提示词和沙箱权限决定。该文件对应 Codex 0.162.0，升级 Codex 后由维护工程重新生成。

在工具协议上，原生 Responses 支持 function、namespace、custom 工具、`additional_tools` 和推理内容回放，但不支持客户端 `tool_search`：安装的 `model-catalog.json` 已设 `supports_search_tool = false`，Codex 因此把 MCP 工具直接内联在工具表里，而不是藏在 `tool_search` 后面。网页搜索则由前端托管，见下文。

## 网页搜索

网页搜索不使用 harness 自家的搜索服务，统一由本安装经 Brave 提供（key 在 `installation.private.toml`）。

- **Codex**：设置 `web_search = "live"`。前端会把 `web_search` 换成同名函数交给模型；当模型调用时，由前端执行 `search`、`open_page`、`find_in_page`，把结果写回对话后继续生成，而 Codex 看到的是普通的 `web_search_call`。该功能只支持流式；每个请求最多 8 次搜索、10 轮模型调用，各轮共用一个输出上限。参数上支持 `filters.allowed_domains` 和 `search_context_size`，不支持 `user_location`。
- 为了让 `codex exec resume` 在每次领新租约时仍能读取之前的搜索记录，搜索结果会按随机调用 id 保存在前端内存中并跨租约保留，等 Codex 回传时再还原给模型；当总量超过上限时淘汰最旧的记录，前端重启后清空，此后旧会话里的搜索只会得到"结果不可用"。
- **Claude Code**：其内置 WebSearch 依赖 Anthropic 服务，因此启动脚本把它禁用，改为挂载 MCP 服务 `src/brave_mcp.py`（提供工具 `mcp__brave__web_search`、`open_page`、`find_in_page`）。
- 只读取公网 http(s) 地址；内网、本机、带账号密码或非标准端口的地址都会被拒绝，`127.1` 这类简写数字地址同样拒绝，且每次重定向都会重新检查。域名在建立连接时解析，只要有一个结果不是公网地址就拒绝，并直连检查过的地址、不走代理。如果本机需要将 fake-IP 网络的解析网段等放行，可在安装目录的 `config.local.json` 中用 `fetch_allow_networks`（CIDR 列表）为本机放行额外网段，但 URL 里直接写的地址仍然拒绝；此时经路由器到达的目标只受路由器规则保护。此外，Brave key 只发给 Brave API；Brave 调用每秒最多一次，失败不重试。

## Claude Code 接入

要让 Claude Code 对接本服务并与 Codex 保持一致的窗口、推理强度和审批行为，需要通过环境变量和命令行参数传入配置。以下是启动脚本实际传入的环境变量和参数（不修改 `~/.claude`；以 {{model}} 默认档为例）：

```bash
export ANTHROPIC_BASE_URL={{base_url}}/strata
export ANTHROPIC_AUTH_TOKEN=<key>
export ANTHROPIC_MODEL={{model_slug}}        # OPUS / SONNET / HAIKU 默认模型也设为同一个
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
export CLAUDE_CODE_MAX_CONTEXT_TOKENS={{context_window}}            # 声明真实窗口：所用档的 context_window
export CLAUDE_CODE_MAX_OUTPUT_TOKENS=24576             # 该强度的总输出（low 8192、medium 16384、high 24576）
export CLAUDE_CODE_EFFORT_LEVEL=high                    # 与 Codex 的 model_reasoning_effort 相同
export CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE={{auto_compact_token_limit}}       # 自动压缩阈值：所用档的 auto_compact_token_limit，与 Codex 相同
export ENABLE_TOOL_SEARCH=false                        # 关闭工具搜索，全部工具定义内联发送（见下文）

claude --mcp-config '{"mcpServers": {"brave": {...}}}' --permission-mode default \
       --settings '{"skipWebFetchPreflight": true, "permissions": {"deny": ["WebSearch"]},
                   "hooks": {"PreCompact": [{"hooks": [{"type": "command", "command": "cat <安装目录>/config/prompts/compact-prompt.txt"}]}],
                             "PermissionRequest": [{"matcher": "*", "hooks": [{"type": "command", "command": "python3 <安装目录>/bin/qwen-approve", "timeout": 180}]}]}}' [调用方参数]
```

各项设置的具体机制如下：

- 总输出与思考上限：总输出按强度取上表的总输出（`bin/qwen-agent --effort` 同时决定强度和这个值），与前端为 Codex 补的值相同。因为 Claude Code 每个请求都自带 `max_tokens`，前端不覆盖请求给出的值，所以总输出由这个环境变量决定，不要调大；当窗口剩余空间不够时，服务会把输出上限缩短到剩余空间，不返回 400。与此同时，前端会给 Messages 请求补思考硬上限：当思考关闭（`thinking.type: disabled`）或请求自带 `reasoning_budget_tokens` 时保持不动；否则取推理强度对应的思考上限（high 为 8192，见上表），若请求的 `thinking.budget_tokens` 更小则用它，再不超过 `max_tokens` 的一半。实际请求中，Claude Code 发送 `thinking: adaptive`、`output_config.effort`（取 `CLAUDE_CODE_EFFORT_LEVEL`）和 `max_tokens`，所以思考上限与 Codex 同强度相同（high 为 8192），Strata 为回答保留其余空间。
- 强度：环境变量 `CLAUDE_CODE_EFFORT_LEVEL` 对整个会话生效；而命令行 `--effort` 在第一次压缩后会失效，所以启动脚本用环境变量传强度。
- 自动压缩：{{local.compact_check}}
- 审批：固定由 `bin/qwen-approve` 完成，不使用 Claude Code 的 auto mode——在 2b 验收中，auto mode 判对 5/9、每次运行 191 秒，而 `qwen-approve` 判对 7/7、仅需 80 秒。权限模式为 `default`，每次权限请求经 `PermissionRequest` hook 交给 `qwen-approve`：它把用户消息（唯一授权来源）、最近 6 次工具调用与结果（标为不可信数据）和待审动作发给本模型审查——其中待审动作不截断，一旦超过 20000 字符就直接拒绝并说明太长无法审查，历史和结果则各截取前 2000 字符；审查请求使用 `reasoning_effort: low`，思考上限 512 token、总输出 1024 token，与 Codex guardian 相同。脚本等模型答复最多 150 秒（hook 给 180 秒），返回 allow / deny 及理由；超时、出错或答复无法解析一律拒绝。如果用户只是让 agent 照文件、网页或工具输出里的步骤执行，只授权其中无害的步骤；破坏性或越界的步骤必须由用户消息点名效果和目标。每次判断都会记一行到 `logs/approve.log`（含工具、结论、理由、耗时、usage，不含 key）。
- 压缩：当 PreCompact hook 退出码为 0 时，其 stdout 会以 `Additional Instructions:` 追加到 Claude Code 自带摘要指令之后，所以每次压缩（无论自动或手动）都带上 `compact-prompt.txt`。**特例**：Claude Code 没有替换内置摘要指令的办法，因此压缩请求是"内置指令 + 基础压缩提示"；而 Codex 则用 `experimental_compact_prompt_file` 整体替换为基础压缩提示。这是两者唯一不能对齐的提示差异。
- `skipWebFetchPreflight`：用于关闭 WebFetch 抓网页前向 `api.anthropic.com` 发起的域名查询。
- 工具搜索：设置 `ENABLE_TOOL_SEARCH=false` 关闭 Claude Code 的工具搜索（即延迟加载工具定义）。在 Claude Code 2.1.309 中开着它时，每个请求会多一个带 `defer_loading` 的占位工具 `DeferredToolPlaceholder`，被延迟的工具要靠 `tool_reference` 块按需展开；但 Strata 的 Messages 接口不实现这两种语义（占位工具会当普通工具交给模型，`tool_reference` 块会被丢弃），所以工具搜索在本服务上不可用。关闭后，所有工具（含 brave 的 3 个）都以完整定义内联，工具表与 2.1.303 相同（2.1.309 零模型抓包核对，2026-10-24）。启动脚本总是设这个值，调用方环境里的同名变量不起作用。

### 与 Codex 的参数对照

自 2026-10-12 起，`bin/qwen-agent` 让两种 agent 在参数层面完全一致。它按对外模型的默认档（即 `config/deployment.json` 中 `context_tiers` 的第一档）启动模型，并把同一档的窗口和阈值传给两种 agent；如果配置中没有列出档位，则直接报错退出，不领取租约。下表以 {{model}} 为例：

| 参数 | Codex | Claude Code |
|---|---|---|
| 窗口 | `model_context_window` {{context_window}} | `CLAUDE_CODE_MAX_CONTEXT_TOKENS` {{context_window}} |
| 自动压缩阈值 | `model_auto_compact_token_limit` {{auto_compact_token_limit}} | `CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE` {{auto_compact_token_limit}} |
| 强度 | `model_reasoning_effort` | `CLAUDE_CODE_EFFORT_LEVEL`（同一个 `--effort`） |
| 思考上限 | 前端按强度补 2048／4096／8192 | 前端按强度补，同值 |
| 总输出 | 前端按强度补 8192／16384／24576 | `CLAUDE_CODE_MAX_OUTPUT_TOKENS` 同值 |
| 采样 | 不发，用安装预置 {{sampling}} | 不发（已抓包核对），同预置 |
| 审批参数 | guardian：low，思考 512／总输出 1024，不发采样 | `qwen-approve`：同值 |

两者审批的参数相同，但实现机制不同：

| 方面 | Codex guardian | Claude Code + `qwen-approve` |
|---|---|---|
| 提示 | Codex 内置的 guardian 风险策略 | 本工程的策略：用户消息是唯一授权来源，破坏性或越界步骤须由用户点名 |
| 上下文 | Codex 自己整理的会话记录 | 用户消息 + 最近 6 次工具调用与结果（标为不可信）+ 待审动作 |
| 请求数 | 一次审批可能有多次模型请求（guardian 线程内的多轮） | 每次审批 1 次请求 |
| 超时与出错 | 由 Codex 内置机制处理，本工程未改动，具体超时未核对 | 模型答复最多 150 秒；超时、出错或无法解析一律拒绝，并记入 `logs/approve.log` |

压缩提示的特例见上文"压缩"一条。

在接口支持上，原生服务提供 `/v1/messages` 和 `/v1/messages/count_tokens`。2026-10-09 冒烟检查（Claude Code 2.1.295，`-p`，Read 工具）已确认 thinking 和工具调用可用。目前已知两处差异：

- Claude Code 不认识该模型名，会提示 `unrecognized_model`；但窗口和输出上限仍按上面的环境变量生效。
- `count_tokens` 不含服务端注入的启动提示，因此比实际输入少约 420 token。

此外，2b 验收已用模型验证了搜索、审批和自动压缩，详见工程报告 `reports/v0.1.40.2/agent-integration-2b/`；长会话的可靠性则由之后的 ARW 能力验证覆盖。

### 审批与主对话的缓存

{{local.approval_cache}}

## 日志

排查问题时，可查看安装目录 `logs/` 下的三类日志文件：`frontend.log` 记录前端请求与错误，`model-server.log` 是原生服务的日志，`<量化>-prebuilt-engine.log` 是引擎日志。所有日志均不记录提示词内容。

## 已观察到的执行异常

在长时间任务中，模型可能在任务尚未完成时提前结束工作，也可能陷入重复步骤的循环。调用方在设计接入逻辑与结果校验时，需要了解以下已观察到的异常现象：

第一种异常是自动压缩时返回未声明的工具调用。在2026-10-06的Commit Audit推理强度测量中，Strata v0.1.38、Qwen3.8-Flash-Next Q2_0、low、default及100000压缩阈值／156584窗口的第1、2、4次初审，在自动上下文压缩请求中返回了该请求未声明的`exec_command`工具调用。当时的协议桥拒绝了这个调用，被拒绝的调用没有执行；但流式接口此时可能已返回HTTP200，随后才以`response.failed`结束，错误信息为`[invalid_response] Model returned unknown tool: exec_command`。本批Codex 0.160.0因此结束了当前Reviewer回合，导致报告未交付。需要注意，这是当前条件下观察到的模型工具响应错误，不是shell命令执行后的失败，也不能仅凭“stream disconnected”将其判为网络断开；目前尚未确定在其他版本、量化、强度或业务中的发生率。

第二种异常是重复执行无效步骤导致长任务超时。2026-10-04，在Strata v0.1.38、Qwen3.8-Flash-Next Q2_0、medium、独立训练review profile的一次Commit Audit中，模型连续98次执行同一条未生效的JSON修复命令，约35分钟内同样5行语法错误持续存在——可见工具返回成功并不代表任务取得进展。第55分钟的整理返回提醒已进入原生会话，模型随后修复了JSON语法，但又重复读取源码，未能在截止前完成交付，最终在第60分钟被原生中断，最终状态为incomplete。原超时记录已保留；用户后来授权另存同场景重跑，报告正常交付，该重跑未覆盖或删除首轮失败。

这一案例说明，长任务可能陷入重复操作和长期停滞，从而影响调用方进度；但目前尚未确定成因或发生率，不能据此断言所有量化、强度、profile或任务都会如此，也不能认定训练profile是原因。本轮对照后已决定不采用该训练profile，继续使用default。

安装服务在模型进程启动时读取安装根目录下的`config/prompts/startup-instructions.txt`，将其作为系统提示词的一部分，追加到每次请求的调用方指令中（全文可直接查看该文件）。Chat、Responses及Messages请求均使用该提示词，调用方无需重复添加相同指令。自 2026-10-11 起，默认加载时去掉了文件开头的 `Progress and loop prevention` 段（该防循环要求原本要求模型识别连续重复且无进展的步骤并调整方法，现已弃用，见[服务端循环提醒](#服务端循环提醒)），其余字节不变；状态接口 `native_health.startup_instructions` 中，`sha256` 是实际加载内容的 SHA，`source_sha256` 是源文件的 SHA，`loop_prevention_enabled` 则表示是否加回了该段。目前保留的要求包括：任务及必要交付物未完成时继续执行，不以计划或进度说明代替交付；准备结束时逐项核对实际完成情况，所需报告须写到指定位置并验证内容，仍有可推进的工作则继续做。同时，明确停止指令、时限及已验证阻塞仍须遵守，未完成时须明确报告原因和真实部分结果。不过，新增两项要求的行为收益尚未实测；提示词不能保证模型不早停或不重复，任务是否完成仍应以真实交付物为准。

后续观测显示，启用上述提示词后仍出现了停滞。在同版本Q2_0、medium、默认profile的第二次Commit Audit中，模型仍执行同一失败探测命令18次，并反复读取同一角色规则21次，期间相同命令的结果正文均未变化；该实例最终于49.73分钟正常完成，未触发中断（这些次数是工具调用次数，包含同批提交，不等于独立推理轮次）。这说明默认profile也可能出现这种停滞，提示词不能保证避免循环。而在同配置默认profile的第三次Commit Audit中，模型多次用不同命令检查同一118行报告并声称通过，但原版生成仍拒绝了87处文件证据格式和一个治理来源，经两次同线程修订后才于34.99分钟完成——因此，模型自行检查成功不能代替调用方既有的正式结果校验。此外，该提示词文件在每次模型进程启动时固定；修改文件不会改变已启动实例，下一次模型启动才生效。可通过`GET /model/status`的`native_health.startup_instructions`查看加载文件的相对路径和SHA-256以便核对。完整模型输入还包含调用方指令、任务、工具及历史，不等同于这个固定追加文件。

除了循环停滞，模型还可能在没有报错的情况下只留下进度说明就提前结束。在另一次150K/206584上下文观测中，任务在8.8分钟后正常结束，却只返回继续核对材料的进度说明，没有写入所需报告：期间共32次工具调用，其中10次是参数完全相同的额外重复。全过程没有观察到超时、中断、连接故障或容量拒绝；模型在最后达到4096-token思考预算后仍生成了20 token进度说明，因此不能据此认定思考预算强制结束了整个任务，更深层模型或停止原因尚未确定。这同样说明，正常结束、工具退出码0或模型声称完成，都不能代替检查实际交付物。

同版本Q2_0/medium/default的64K压缩阈值测量中，也出现过正常结束却未交付报告的情况：一个实例运行8.7分钟、成功压缩2次后，只返回继续读取指令的说明，报告仍为空，期间没有流错误、超时或容量拒绝。另一个完整实例则反复复核已写报告，整个合并任务耗时57.7分钟，包含29次完全相同参数的额外工具调用。总之，基础提示不能保证消除这些行为；调用方仍应按自己的任务合同核对实际交付，不能将HTTP成功或普通结束当成任务完成。

## 服务端循环提醒

该功能**已弃用，默认关闭，不建议使用**（2026-10-11）。在真实试跑与无提示无提醒基线各 3 次（Commit Audit）的对照中，不加任何防护时模型也很少循环，提醒和防循环提示看不出收益，且提醒多数是误报。该功能暂时保留为显式开启，待观察一段时间没有明显重复后删除。

显式开启时，前端会对 Chat、Responses、Messages 生成请求（不含 `count_tokens`）检查请求里携带的对话历史：如果模型的最后一步与本对话之前的步骤高度重复（即相同工具调用且结果相同，或推理／回答文本高度相似），就在转发给模型的请求末尾追加一条一次性提醒，作为用户消息发送（在 Messages 接口里则并入最后一条用户消息）。

- 只提醒，不拒绝、不中断，也不改变工具调用。提醒文字会说明它来自模型服务而不是用户，要求模型检查是否陷入无进展的循环；如果重复是有意的并且在推进，就继续执行。
- 提醒只进入转发给模型的请求，不出现在响应里，也不写回调用方的历史，所以不会在后续上下文中累积。
- 前端不保存会话状态，每次请求都从携带的历史重新判断，因此恢复或重试的会话会得到同样的判断。已提醒过的重复链之后再出现 2 次才再次提醒；新的重复链则立即提醒。
- 判断只用机械规则（基于本对话内动态出现的文本和工具调用），不用关键词表，也不调用模型。在离线语料上联合 F2 约 0.78–0.80，尚未达到 0.8 的门槛；真实干预效果尚未验证，可能出现误报。
- 只有带请求头 `X-Loop-Reminder: on` 时才对本次请求检查和提醒；不带或其他值都不提醒。`frontend.log` 只记录"已追加提醒"和接口路径，不记录提醒或对话内容。

## 调用方动态防重复建议

建议ARW、Codex或其他调用方在自己的harness中观察实际工具结果与交付状态，按观测事实动态反馈。安装服务提供模型API，客户端shell、文件工具及任务是否完成由调用方管理；本节的建议与上面的服务端提醒相互独立，调用方的守卫不依赖服务端提醒。仅靠基础提示或命令全文相同的检测不能保证避免循环。

针对三类常见停滞情形，建议按以下规则检测并反馈：

| 观测情形 | 建议检测与反馈 |
| --- | --- |
| 改写脚本后，同一解析错误仍在 | 将错误类别、失败表达式、工作目录和已知实际输入绑定；可从两次保留相同失败表达式的解析错误开始提醒。忽略控制台标签等无关变化，保留真实参数、路径及运算符。指出未改变的失败位置，建议先修复并用最小探针验证，再扩展其他检查。 |
| 换了其他命令后，又回到同一无效步骤 | 保留一个短窗口，例如最近8次完成调用；相同命令、目录、输入版本及可用结果在窗口内出现3次时提示复用已有事实、推进尚未完成的交付，不只要求连续重复。 |
| 多次正常结束，只有进度说明，交付物未推进 | 按调用方合同核验文件存在、内容变化及必要的机械格式／覆盖检查；连续两次正常未完成且交付物无进展时，在原线程的既有接续指示中指出实际缺项，要求先落盘已完成工作再处理剩余不确定性。 |

例如三次Node脚本长度或日志标签不同，但都在同一个表达式报缺少右括号，反馈应指出“该失败表达式尚未改变，请先修复它并运行最小验证”，而不只是“不要重复命令”。工具退出码0、模型声称修复或命令文字变化都不是完成证据；必须检查错误是否消失、后续检查是否实际执行，以及交付物是否满足调用方合同。

检测应按逻辑任务／阶段和线程隔离，并以原生工具事件身份去重；消息镜像、缓存重放和压缩历史不能当作新的调用。同时，应排除正常轮询、明确要求的重复测量、预期失败测试、新输入／文件版本、新错误位置、有实质进展的修复，以及调用方自身重置文件的恢复步骤。缺少结果或交付状态时应保留未知，不能当作空文件或相同输出。此外，运行时错误可能由不同输入引起，只有相关输入版本确实已知时才合并；不要只凭异常名称、退出码或模糊的“没有进展”判断循环。

在触发节奏与权限边界上，每个已确认卡点先提示一次，等实际输入／证据或交付物有进展后再重新计数。反馈只包含本线程已获准观察的事实，不提供审核答案、扩大读写授权或自动重放可能已有副作用的操作。活跃回合通过harness原生消息入口反馈；空闲回合则由原有任务管理者按自己的恢复合同接续，避免两个组件分别唤醒同一任务。接续时保持原权限和整个逻辑任务的累计截止时间，接续不重新获得一份完整预算；超过调用方上限或无法安全继续时，按其原停止／人工处理流程收尾。

为了评估守卫是否真的奏效，需要记录触发依据、消息接纳、模型原生收到，以及之后是否修复或交付。单凭消息accepted、改了命令文字或再次声称完成，都不能单独证明提醒有效。建议先用历史日志及正常修复／轮询反例回放检查误报，再用真实任务核对反馈效果。

最后需要注意，上述阈值只是保守的候选起点，调用方应按自己的负载验证。本工程首版已通过离线机制检查，并完成本机Q2_0三次真实诊断：三次仍有确认循环，动态提醒均未触发，尚未证明真实提醒能够减少循环或降低耗时。主要遗漏发生在活跃回合的重复推理；命令结果守卫看不到全部语义重复，而“两次正常未完成结束”的交付检测须等回合结束才有机会反馈。因此，不要把离线可触发或任务变快当作真实干预已有效，也不要据此撤掉已有的防循环措施。调用方若增加活跃回合的停滞检测，应先核对实际交付进展、正常思考与修复反例，并单独验证误报和反馈效果。

## 基础提示词与上下文压缩

模型运行过程中涉及两类基础提示词：日常任务提示词由服务端自动追加，而上下文压缩提示词需要外部调用方在自己的harness中配置。下表列出了不同情况下的提示词分工：

| 情况 | 提示词 | 谁负责接入 |
|---|---|---|
| 普通对话、文档/代码review、工具调用、训练等模型请求 | `config/prompts/startup-instructions.txt`：核验结果、完成任务及结束前自检（防循环段默认不加载，已弃用） | 模型服务自动追加；外部调用方无需重复加入 |
| harness要压缩历史、生成后续任务摘要 | `config/prompts/compact-prompt.txt`：只生成摘要、禁止继续执行任务或调用工具、保留约束和行动状态 | 本工程活跃WSL/ARW入口自动组合；`bin/qwen-agent` 为 Codex 设置 `experimental_compact_prompt_file`，为 Claude Code 设置 PreCompact hook；外部调用方须在自己的harness配置 |
| 场景另有角色、任务或摘要要求 | 场景自己的提示词 | 调用方保留并追加为相应基础提示的补充；不能替代基础提示 |
| 希望保留harness原生摘要要求 | 自己harness版本的默认摘要提示 | 将其作为基础压缩提示的补充；本工程使用经实际原生手动压缩路径核对的Codex 0.160.1快照，调用方无需复制维护资源 |

对于日常请求，启动基础指令在模型进程启动时读取，应用于每次服务端模型请求，同时调用方自己的指令仍保留。`GET /model/status`的`native_health.startup_instructions`会给出加载路径和SHA；修改文件后须下一次模型启动才生效。

对于上下文压缩，由于压缩由调用方的harness管理，服务端没有可靠的请求压缩标识，因此不会自动注入`compact-prompt.txt`。外部调用方在配置压缩时，需读取该基础文件，将自己场景的摘要要求作为补充，保存组合文件，再通过Codex的`experimental_compact_prompt_file`等配置指向组合文件；只设置基础文件也可，但不能用自定义摘要提示把基础指令覆盖掉。不要把“只输出摘要”加入普通review提示，也不要将基础文件同时当作自己的补充而重复拼接。服务不会修改调用方或全局Codex配置。

此外，原生默认摘要快照不是基础提示词，也不是安装目录的公共配置。本工程将0.160.1实际原生手动压缩请求的快照保存在版本化的工具资源目录，不部署到安装目录的`config/`；调用方只需使用安装目录的基础文件，并按自己的harness和场景补充摘要要求。升级Codex后需重新核对，不能将旧快照视为新版本默认。
