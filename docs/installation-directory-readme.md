# Strata 模型服务调用手册

本安装提供 Qwen3.8-Flash-Next 的 Windows 原生推理服务。常驻前端监听局域网固定地址，负责独占租约、模型启停和推理转发。调用方领取 key，选择量化和参数，启动模型，再通过 OpenAI Chat、OpenAI Responses 或 Anthropic Messages 接口推理，最后归还。

长时间任务使用前，请阅读[已观察到的执行异常](#已观察到的执行异常)及[调用方动态防重复建议](#调用方动态防重复建议)，为整个任务设置截止时间。

调用方自行管理 Codex、Claude Code 或其他 harness，包括 provider、权限、工具、会话与压缩策略。

## 地址

| 主机 | 前端地址 |
|---|---|
| rtx3080ti | `http://192.168.60.212:8000` |

前端随 Windows 用户登录由计划任务 `QwenStrataFrontend` 启动，常驻运行，不需要调用方启动。只接受本机及本机各网卡所在子网（含 WSL 虚拟网卡）的客户端，其他地址返回 403。存在 HTTP 代理时，对该地址设置 `NO_PROXY` 或显式直连。

## 独占租约

同一时间只有一个持有者。

1. `POST /lease/acquire` 领取 key。已有持有者时返回 409；不排队、不抢占。
2. 之后的请求都带 `Authorization: Bearer <key>`（也接受 `x-api-key: <key>`），包括模型启停、状态和推理。缺失、错误或已归还的 key 返回 403。
3. `POST /model/start` 选择量化和上下文档位并等待模型就绪。如果上一个租约留下的模型正好是同一量化和同一档位，直接复用，不重新加载（返回 `reused: true`）；不同则先停再启动。
4. `POST /model/stop` 只停模型，租约仍保留，可换量化或档位重新启动。
5. `POST /lease/release` 归还：撤销 key，**模型继续加载**，留给下一个调用方复用。没有租约的模型空闲 30 分钟后由前端停止。要立即释放内存和显存，归还前先调用 `/model/stop`。

租约只保存在前端内存中，没有超时，也不自动回收。调用方必须在自己的 finally 路径里归还。key 丢失或持有者异常退出时，由维护者重启前端（重启会停止模型并清空租约），不提供无 key 夺取接口。key 是调用方凭据，不写入提示词、版本控制、共享日志或报告。

## 接口

路径相对于前端地址。JSON 请求使用 `Content-Type: application/json`。

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

`/strata/` 下的请求原样转发给本机内部的原生 Strata 服务，响应（含流式）原样返回。原生服务只监听 127.0.0.1，使用每次启动随机生成的内部 key，调用方无法绕过前端访问。

转发前，前端只做三件事：
- 请求的 `model` 必须等于当前加载的模型 ID，否则返回 409；省略时自动填入。没有运行中的模型返回 503。
- Chat 和 Responses 请求缺少推理强度、思考预算或输出上限时，按[推理强度与输出](#推理强度与输出)补齐。
- Responses 流式请求声明了 `{"type": "web_search"}` 时，由前端经 Brave 执行搜索，见[网页搜索](#网页搜索)。
- Messages 请求不补默认值，由调用方自己设置 `max_tokens` 和 thinking。

### 错误

| 状态码 | 含义 |
|---|---|
| 403 | key 无效，或客户端地址不在本地网络 |
| 409 | 租约已被持有、请求的模型与已加载模型不一致，或关闭前端时模型未停 |
| 400 | 启动参数或请求体无效 |
| 503 | 模型未运行、启动失败或停止失败；详情见安装目录 `logs/` |

流式响应在 HTTP 200 之后仍可能失败。终态以流内事件为准，不能只看 HTTP 状态；不要在看到断流后盲目重试可能已经执行过工具的请求。

## 启动参数

调用方只能选择三项：**模型**、**上下文大小**（启动时选择档位）、**推理强度**（随每个请求传递）。引擎参数、环境变量、采样默认值、思考预算和输出上限都由安装目录按"本机 + 量化"预置，调用方不能覆盖。

`POST /model/start` 示例：

```json
{"model": "IQ3_XXS", "context_window": 156584}
```

| 字段 | 说明 |
|---|---|
| `model` | 可省略。本机只对外提供一个模型，即 `config/deployment.json` 中 `models` 列出的那一个，省略即用它；安装目录里其他量化的权重不对外，请求它们返回 400 |
| `context_window` | 可省略，省略为对外模型的第一档。只能取安装目录 `config/deployment.json` 中 `context_tiers.<模型>` 列出的 `context_window`；每档附带实测的 `auto_compact_token_limit`，调用方必须把自己 harness 的窗口和自动压缩阈值设为同一档的这两个值。该量化没有列出档位时只能省略 |

其他字段返回 400。推理强度见[推理强度与输出](#推理强度与输出)。

启动完成时前端核对实际加载的模型和上下文容量。换档位时，`/model/start` 会自动先停掉旧模型；"相同"按校验后的完整运行配置比较，包括部署后改动的安装预置。

模型 ID 为 `qwen3.8-flash-next-` 加对外模型名的小写（如 IQ3_XXS 为 `qwen3.8-flash-next-iq3_xxs`）。

### 安装预置

rtx3080ti：对外模型为 IQ3_XXS，默认档是窗口 206584、自动压缩阈值 150000（2026-10-14 起），另有可选档窗口 156584、阈值 100000。206584 已在约 151K token 以内的长上下文检索负载上验证，同负载下与 156584 档速度相同；更长的提示在 200K 级检索中出现过系统性错误，256584 未发布。`config/model-catalog.json` 只列对外模型，窗口是它在本机的默认档；调用方仍需把自己 harness 的自动压缩阈值设为所用档的值（IQ3_XXS 默认档为 150000）。`bin/qwen-agent` 使用对外模型的默认档，即 `context_tiers` 的第一档（见[与 Codex 的参数对照](#与-codex-的参数对照)）。其余预置：high，思考 8192／总输出 24576，temperature 0、top_p 1、top_k 20，CPU 辅助 auto。这是维护起点，不是完整质量验收或最优参数的结论。服务不会替调用方压缩。

## 推理强度与输出

Responses 使用 `reasoning.effort` 和 `max_output_tokens`，Chat 使用 `reasoning_effort` 和 `max_tokens`。请求未指定时按下表补齐；请求指定的值优先。

| 强度 | 思考 token 上限 | 默认总输出上限（含思考） |
|---|---:|---:|
| low | 2048 | 8192 |
| medium | 4096 | 16384 |
| high、xhigh、max | 8192 | 24576 |

不提供 none 档：请求指定其他强度（包括 none）时返回 400。

- Codex 的 guardian 审批请求有单独的默认值，与强度无关：思考 512、总输出 1024（安装预置，与 `bin/qwen-approve` 相同）。服务按 Codex 随请求发送的元数据识别它（`client_metadata["x-codex-turn-metadata"]` 中 `thread_source` 为 `guardian_review`），不看提示词内容。审批只需输出一段简短的 JSON 结论。Strata 为回答保留 min(max(512, 总输出/4), 总输出/2)，总输出 1024 时正好保留 512，思考可以用满 512。请求自己给了思考预算或输出上限时，以请求为准。Codex 对 guardian 请求发 `reasoning_effort: low`、不带输出上限和采样字段，`bin/qwen-approve` 显式发同样的值，所以两边审批参数相同。
- 与该次运行默认强度相同的请求，使用默认值中的预算和输出上限（rtx3080ti 为 high，思考 8192／总输出 24576）。
- 请求自己给了输出上限、没给思考预算时，思考预算不超过输出上限的一半。Strata 另外为回答至少保留输出上限的 1/4。
- 上限不等于实际思考长度。请求给的输出上限超出窗口剩余空间时，缩短到剩余空间，不返回 400；输入本身超出窗口仍返回 400，不静默裁剪输入。
- Messages 接口不补总输出（按 Anthropic 协议由调用方设置 `max_tokens`），只补思考上限，见下文 Claude Code 一节。

### 撞到输出上限时的内部重试

Responses 的**流式**请求，如果模型这一次输出撞到总输出上限（以 `response.incomplete`、`incomplete_details.reason = max_output_tokens` 结束），前端不把截断的回答交给调用方，而是在内部重新生成一次。起因是 Codex 遇到这种结束会直接结束回合，模型不知道原因，也没有机会重写。

- 判定只看协议里的这个信号，不看工具名、提示词或客户端，对所有客户端和任务一样。
- 重试请求 = 原请求 + 这次已经完整交给调用方的推理和文本 + 一条服务端自动通知（用户消息，注明来自模型服务、不是用户）：说明上一次输出达到输出上限、在写什么时被截断、截断部分已丢弃未执行，请重新回应上一个请求，缩短输出，或把必须很长的输出分成几步（例如几次较小的工具调用）。通知不写具体数字，只进转发给模型的请求，不进响应，也不写回调用方的历史。
- 调用方看到的是同一个响应接着流下去：截断的那一项只出现过开头和增量，没有完成事件，不进入调用方历史，也不会被执行；重试的事件重新编号后接在后面。没撞上限的响应逐字节原样转发，不增加延迟。
- 最多重试 1 次。重试仍撞上限、重试无法开始、处理中出现意外错误，或截断前已经有工具调用完整交给了调用方（调用方可能已在执行），就照原样返回截断的结果。
- 调用方收到的 usage 是最后一次生成的值（与它的上下文一致）；被丢弃那次的上限、token 和耗时记在 `logs/frontend.log`（`output limit:` 行），引擎日志里两次生成都有。
- 不处理：Messages（Claude Code）——Claude Code 自己会把截断的工具调用作为失败结果交回模型并继续，而在 Anthropic 流里重试必须重开已出现过的内容块编号，不符合协议；非流式请求、Chat 接口和托管 web_search 的 Responses 请求也不处理，撞上限时行为与以前相同。

## 启动脚本（WSL）

`bin/qwen-agent` 完成整个生命周期：领取租约 → 启动模型 → 运行 Codex 或 Claude Code → 退出后归还租约（模型留给下一次复用）。只依赖本安装目录和 Python 3 标准库。

```bash
qwen_install=/mnt/c/Users/pello/AppData/Local/Programs/qwen-3.8-flash-next
python3 "$qwen_install/bin/qwen-agent" codex                       # 交互式 Codex，本机对外模型、high
python3 "$qwen_install/bin/qwen-agent" --effort medium codex exec "任务描述"
python3 "$qwen_install/bin/qwen-agent" claude                      # Claude Code
```

- `--model` 可省略，默认即本机对外模型（`config/deployment.json` 的 `models`）；写其他量化时在领租约前报错退出。
- 租约已被他人持有时立即退出，不排队、不抢占。
- 加载耗时：rtx3080ti 上旧 Q2_0 约 20 秒，IQ3_XXS 未单独记录；相同参数复用已加载的模型时不再加载。Ctrl-C 交给 agent 处理；agent 退出、终端关闭或进程被终止时都会归还租约。归还失败时会提示重启前端任务。
- key 只放在 agent 进程的环境变量里，不写入文件或命令行参数。
- 调用方环境中的 `ANTHROPIC_*`、`OPENAI_*`、`AI_AGENT` 和以 `CLAUDE` 开头的变量（`CLAUDE_CONFIG_DIR` 除外）不传给 agent，所以在 Claude Code 会话里启动时，agent 拿不到父会话的会话 id 和消息通道；需要的 Claude Code 定制写进 settings.json 的 `env`。
- 脚本不修改调用方的 `~/.codex` 或 `~/.claude` 配置；所有设置都以命令行覆盖或环境变量传入。

## Codex 接入

启动脚本传给 Codex 的设置如下（以 IQ3_XXS 默认档为例，窗口和阈值取所用量化在 `config/deployment.json` 中的第一档）；自行配置时照此设置：

```toml
model = "qwen3.8-flash-next-iq3_xxs"
model_provider = "qwen_strata"
model_catalog_json = "/mnt/c/Users/pello/AppData/Local/Programs/qwen-3.8-flash-next/config/model-catalog.json"
experimental_compact_prompt_file = "/mnt/c/Users/pello/AppData/Local/Programs/qwen-3.8-flash-next/config/prompts/compact-prompt.txt"
model_context_window = 206584
model_auto_compact_token_limit = 150000
web_search = "live"

[model_providers.qwen_strata]
name = "Local Strata"
base_url = "http://192.168.60.212:8000/strata/v1"
wire_api = "responses"
env_key = "QWEN_STRATA_KEY"
requires_openai_auth = false
supports_websockets = false
request_max_retries = 0
stream_max_retries = 0
```

key 通过 `env_key` 指定的环境变量只提供给该 harness。请求重试设为 0，避免重试重复已执行的工具操作。

程序每次运行都新建 `CODEX_HOME` 时（测量、批处理），另加 `-c features.plugins=false`（或在该目录的 `config.toml` 写 `[features]` `plugins = false`）：否则 Codex 0.162 会在每个新目录克隆约 105MB 的插件仓库，这些内容不进入模型输入。固定使用 `~/.codex` 的交互式用法只克隆一次，不需要设置。

`config/model-catalog.json` 只描述本机对外模型的事实：模型名、推理档位、窗口（本机该模型的默认档，即 `config/deployment.json` 中 `context_tiers` 的第一档）、只接收文本、可使用网页搜索工具，以及 `auto_review_model_override` 指向自身。基础指令与消息结构取自所装 Codex 版本自带的 luna 模型条目，不额外限制工作内容；只读、可写范围等约束由各场景的提示词和沙箱权限决定。该文件对应 Codex 0.162.0，升级 Codex 后由维护工程重新生成。

原生 Responses 支持 function、namespace、custom 工具、`additional_tools`、客户端 `tool_search` 和推理内容回放。网页搜索由前端托管，见下文。

## 网页搜索

不使用 harness 自家的搜索服务，统一由本安装经 Brave 提供（key 在 `installation.private.toml`）。

- **Codex**：设置 `web_search = "live"`。前端把 `web_search` 换成同名函数交给模型；模型调用时由前端执行 `search`、`open_page`、`find_in_page`，结果写回对话后继续生成，Codex 看到的是普通的 `web_search_call`。只支持流式；每个请求最多 8 次搜索、10 轮模型调用，各轮共用一个输出上限。支持 `filters.allowed_domains` 和 `search_context_size`，不支持 `user_location`。
- 搜索结果按随机调用 id 保存在前端内存，跨租约保留（`codex exec resume` 每次领新租约），Codex 回传时还原给模型；总量超过上限时淘汰最旧的，前端重启后清空，此后旧会话里的搜索只会得到"结果不可用"。
- **Claude Code**：内置 WebSearch 依赖 Anthropic 服务，启动脚本把它禁用，改为挂载 MCP 服务 `src/brave_mcp.py`（工具 `mcp__brave__web_search`、`open_page`、`find_in_page`）。
- 只读取公网 http(s) 地址；内网、本机、带账号密码或非标准端口的地址都会拒绝，每次重定向重新检查。Brave key 只发给 Brave API。Brave 调用每秒最多一次，失败不重试。

## Claude Code 接入

启动脚本传入的环境变量和参数（不修改 `~/.claude`；以 IQ3_XXS 默认档为例）：

```bash
export ANTHROPIC_BASE_URL=http://192.168.60.212:8000/strata
export ANTHROPIC_AUTH_TOKEN=<key>
export ANTHROPIC_MODEL=qwen3.8-flash-next-iq3_xxs        # OPUS / SONNET / HAIKU 默认模型也设为同一个
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
export CLAUDE_CODE_MAX_CONTEXT_TOKENS=206584            # 声明真实窗口：所用档的 context_window
export CLAUDE_CODE_MAX_OUTPUT_TOKENS=24576             # 该强度的总输出（low 8192、medium 16384、high 24576）
export CLAUDE_CODE_EFFORT_LEVEL=high                    # 与 Codex 的 model_reasoning_effort 相同
export CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE=150000       # 自动压缩阈值：所用档的 auto_compact_token_limit，与 Codex 相同

claude --mcp-config '{"mcpServers": {"brave": {...}}}' --permission-mode default \
       --settings '{"skipWebFetchPreflight": true, "permissions": {"deny": ["WebSearch"]},
                   "hooks": {"PreCompact": [{"hooks": [{"type": "command", "command": "cat <安装目录>/config/prompts/compact-prompt.txt"}]}],
                             "PermissionRequest": [{"matcher": "*", "hooks": [{"type": "command", "command": "python3 <安装目录>/bin/qwen-approve", "timeout": 180}]}]}}' [调用方参数]
```

- 总输出按强度取上表的总输出（`bin/qwen-agent --effort` 同时决定强度和这个值），与前端为 Codex 补的值相同。Claude Code 每个请求都自带 `max_tokens`，前端不覆盖请求给出的值，所以总输出由这个环境变量决定，不要调大；剩余空间不够时服务把输出上限缩短到剩余空间，不返回 400。前端给 Messages 请求补思考硬上限：思考关闭（`thinking.type: disabled`）或请求自带 `reasoning_budget_tokens` 时不动；否则取推理强度对应的思考上限（high 为 8192，见上表），请求的 `thinking.budget_tokens` 更小时用它，再不超过 `max_tokens` 的一半。Claude Code 发 `thinking: adaptive`、`output_config.effort`（取 `CLAUDE_CODE_EFFORT_LEVEL`）和 `max_tokens`，所以思考上限与 Codex 同强度相同（high 为 8192），Strata 为回答保留其余空间。
- 强度：`CLAUDE_CODE_EFFORT_LEVEL` 对整个会话生效；命令行 `--effort` 在第一次压缩后会失效，所以启动脚本用环境变量。
- 自动压缩：Claude Code 不按 `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` 压缩，只在阻塞上限（窗口 − 20000 − 3000：206584 窗口为 183584，156584 窗口为 133584）压缩；`CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE` 把这个上限设为所用档的阈值，与 Codex 相同。Claude Code 2.1.303 假服务器核对（两回合与回合中途工具调用两种方式）：206584／150000 档输入 150.1K 时压缩、149.9K 时不压缩；156584／100000 档 100.1K 压缩、99.9K 不压缩；206584 窗口不设该变量时 183.7K 才压缩、183.5K 不压缩。压缩后会话都正常继续。Claude Code 2.1.304 于 2026-10-20、2.1.308 于 2026-10-22 用压缩探针重新核对，206584／150000 档各 3 次全部通过。这个变量不在 Claude Code 公开文档里，升级 Claude Code 后要重新核对。
- 审批固定由 `bin/qwen-approve` 完成，不使用 Claude Code 的 auto mode（2b 验收中 auto mode 判对 5/9、每次运行 191 秒；`qwen-approve` 判对 7/7、80 秒）。权限模式为 `default`，每次权限请求经 `PermissionRequest` hook 交给 `qwen-approve`：它把用户消息（唯一授权来源）、最近 6 次工具调用与结果（标为不可信数据）和待审动作发给本模型（`reasoning_effort: low`），思考上限 512 token、总输出 1024 token，与 Codex guardian 相同；等模型答复最多 150 秒（hook 给 180 秒）；返回 allow / deny 及理由；超时、出错或答复无法解析一律拒绝。用户只是让 agent 照文件、网页或工具输出里的步骤执行时，只授权其中无害的步骤；破坏性或越界的步骤必须由用户消息点名效果和目标。每次判断记一行到 `logs/approve.log`（工具、结论、理由、耗时、usage，不含 key）。
- 压缩：PreCompact hook 退出码为 0 时，其 stdout 会以 `Additional Instructions:` 追加到 Claude Code 自带摘要指令之后，所以每次压缩（自动或手动）都带上 `compact-prompt.txt`。**特例**：Claude Code 没有替换内置摘要指令的办法，压缩请求是"内置指令 + 基础压缩提示"；Codex 用 `experimental_compact_prompt_file` 整体替换为基础压缩提示。这是两者唯一不能对齐的提示差异。
- `skipWebFetchPreflight` 关闭 WebFetch 抓网页前向 `api.anthropic.com` 的域名查询。

### 与 Codex 的参数对照

`bin/qwen-agent` 让两种 agent 在参数层面完全一致（2026-10-12 起）。它按对外模型的默认档（`config/deployment.json` 中 `context_tiers` 的第一档）启动模型，并把同一档的窗口和阈值传给两种 agent；没有列出档位时报错退出，不领取租约。下表以 rtx3080ti 的 IQ3_XXS 为例。

| 参数 | Codex | Claude Code |
|---|---|---|
| 窗口 | `model_context_window` 206584 | `CLAUDE_CODE_MAX_CONTEXT_TOKENS` 206584 |
| 自动压缩阈值 | `model_auto_compact_token_limit` 150000 | `CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE` 150000 |
| 强度 | `model_reasoning_effort` | `CLAUDE_CODE_EFFORT_LEVEL`（同一个 `--effort`） |
| 思考上限 | 前端按强度补 2048／4096／8192 | 前端按强度补，同值 |
| 总输出 | 前端按强度补 8192／16384／24576 | `CLAUDE_CODE_MAX_OUTPUT_TOKENS` 同值 |
| 采样 | 不发，用安装预置 temperature 0、top_p 1、top_k 20 | 不发（已抓包核对），同预置 |
| 审批参数 | guardian：low，思考 512／总输出 1024，不发采样 | `qwen-approve`：同值 |

两者审批的参数相同，机制不同：

| 方面 | Codex guardian | Claude Code + `qwen-approve` |
|---|---|---|
| 提示 | Codex 内置的 guardian 风险策略 | 本工程的策略：用户消息是唯一授权来源，破坏性或越界步骤须由用户点名 |
| 上下文 | Codex 自己整理的会话记录 | 用户消息 + 最近 6 次工具调用与结果（标为不可信）+ 待审动作 |
| 请求数 | 一次审批可能有多次模型请求（guardian 线程内的多轮） | 每次审批 1 次请求 |
| 超时与出错 | 由 Codex 内置机制处理，本工程未改动，具体超时未核对 | 模型答复最多 150 秒；超时、出错或无法解析一律拒绝，并记入 `logs/approve.log` |

压缩提示的特例见上文"压缩"一条。

原生服务提供 `/v1/messages` 和 `/v1/messages/count_tokens`。2026-10-09 冒烟检查（Claude Code 2.1.295，`-p`，Read 工具）确认 thinking 和工具调用可用。已知差异：

- Claude Code 不认识该模型名，会提示 `unrecognized_model`；窗口和输出上限按上面的环境变量生效。
- `count_tokens` 不含服务端注入的启动提示，比实际输入少约 420 token。

2b 验收已用模型验证搜索、审批和自动压缩，见工程报告 `reports/v0.1.40.2/agent-integration-2b/`。长会话的可靠性由之后的 ARW 能力验证覆盖。

### 审批与主对话的缓存

引擎单会话持有显存前缀缓存，审批请求会挤掉主对话的缓存。本机默认开启会话暂存（`conversation-cache-mib 8192`、`conversation-cache-slots 4`、`conversation-cache-min-free-mib 5120`）：切换时把会话暂存到内存，约 17K token 的主对话暂存约 0.1 秒、恢复约 0.03 秒；不暂存时每次审批后主对话要整段重读（17K 约 16 秒）。实测同一审批场景每次运行 69.0 → 46.2 秒。

## Python 示例

仅依赖标准库，从局域网或 WSL 执行。

```python
import json, os, urllib.request
from pathlib import Path

base = "http://192.168.60.212:8000"
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def request(path, body=None, key=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    data = None if body is None else json.dumps(body).encode()
    with opener.open(urllib.request.Request(base + path, data, headers), timeout=900) as reply:
        return json.load(reply)

credential = Path(".strata-access.json")  # 调用方私有文件，排除版本控制
fd = os.open(credential, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
key = None
try:
    key = request("/lease/acquire", {})["key"]
    with os.fdopen(fd, "w") as stream:
        fd = None
        json.dump({"base_url": base, "key": key}, stream)
    request("/model/start", {}, key)  # 省略 model 即本机对外模型
    answer = request("/strata/v1/chat/completions", {
        "messages": [{"role": "user", "content": "2+2=?"}],
        "reasoning_effort": "low", "temperature": 0}, key)
    print(answer["choices"][0]["message"]["content"])
finally:
    if fd is not None:
        os.close(fd)
    if key is not None:
        request("/lease/release", {}, key)  # 失败时保留凭据文件供诊断
        credential.unlink(missing_ok=True)
```

同一持有者可以保留 key 完成多个任务。不要让多个后台任务共享 key 后各自停止或归还。

## 日志

安装目录 `logs/`：`frontend.log`（前端请求与错误）、`model-server.log`（原生服务）、`<量化>-prebuilt-engine.log`（引擎）。日志不记录提示词内容。

## 已观察到的执行异常

模型可能在任务尚未完成时提前结束工作，也可能陷入重复步骤的循环。

2026-10-06的Commit Audit推理强度测量中，Strata v0.1.38、Qwen3.8-Flash-Next Q2_0、low、default及100000压缩阈值／156584窗口的第1、2、4次初审，在自动上下文压缩请求中返回了该请求未声明的`exec_command`工具调用。当时的协议桥拒绝了这个调用，被拒绝的调用没有执行；流式接口可能已返回HTTP200，随后以`response.failed`结束，错误信息为`[invalid_response] Model returned unknown tool: exec_command`。本批Codex 0.160.0因此结束当前Reviewer回合，报告未交付。这是当前条件下观察到的模型工具响应错误，不是shell命令执行后的失败，也不能仅凭“stream disconnected”将其判为网络断开；尚未确定在其他版本、量化、强度或业务中的发生率。

2026-10-04，在Strata v0.1.38、Qwen3.8-Flash-Next Q2_0、medium、独立训练review profile的一次Commit Audit中，模型连续98次执行同一条未生效的JSON修复命令，约35分钟内同样5行语法错误持续存在。工具返回成功不代表任务取得进展。第55分钟的整理返回提醒已进入原生会话；模型随后修复了JSON语法，但又重复读取源码，未在截止前完成交付。第60分钟被原生中断，最终状态为incomplete。原超时记录保留。用户后来授权另存同场景重跑，报告正常交付；该重跑未覆盖或删除首轮失败。

这说明长任务可能陷入重复操作和长期停滞，影响调用方进度；尚未确定成因或发生率，不能据此断言所有量化、强度、profile或任务都会如此，也不能认定训练profile是原因。本轮对照后已决定不采用该训练profile，继续default。

安装服务在模型进程启动时读取安装根目录下的`config/prompts/startup-instructions.txt`，将其作为系统提示词的一部分，追加到每次请求的调用方指令中。全文可直接查看该文件。2026-10-11 起，默认加载时去掉文件开头的 `Progress and loop prevention` 段（防循环要求，已弃用，见[服务端循环提醒](#服务端循环提醒)），其余字节不变；`native_health.startup_instructions` 中 `sha256` 是实际加载内容的 SHA，`source_sha256` 是源文件的 SHA，`loop_prevention_enabled` 表示是否加回了该段。去掉的段要求模型识别连续重复且无进展的步骤并调整方法。保留的要求：任务及必要交付物未完成时继续执行，不以计划或进度说明代替交付；准备结束时逐项核对实际完成情况，所需报告须写到指定位置并验证内容，仍有可推进的工作则继续做。明确停止指令、时限及已验证阻塞仍须遵守，未完成时明确报告原因和真实部分结果。Chat、Responses及Messages请求均使用该提示词，调用方无需添加相同指令。新增两项要求的行为收益尚未实测；提示词不能保证模型不早停或不重复，任务是否完成仍应以真实交付物为准。

启用上述提示词后，同版本Q2_0、medium、默认profile的第二次Commit Audit仍执行同一失败探测命令18次，并反复读取同一角色规则21次；相同命令的结果正文均未变化。该实例最终于49.73分钟正常完成，未触发中断。这些次数是工具调用次数，包含同批提交，不等于独立推理轮次。默认profile也可能出现这种停滞，提示词不能保证避免循环。同配置默认profile的第三次Commit Audit还多次用不同命令检查同一118行报告并声称通过，原版生成仍拒绝87处文件证据格式和一个治理来源；经两次同线程修订后于34.99分钟完成。模型自行检查成功不能代替调用方既有的正式结果校验。文件在每次模型进程启动时固定；修改文件不会改变已启动实例，下一次模型启动才生效。`GET /model/status`的`native_health.startup_instructions`返回加载文件的相对路径和SHA-256，便于核对。完整模型输入还包含调用方指令、任务、工具及历史，不等同于这个固定追加文件。

另一次150K/206584上下文观测在8.8分钟后正常结束，只返回继续核对材料的进度说明，没有写入所需报告：共32次工具调用，其中10次是参数完全相同的额外重复。没有观察到超时、中断、连接故障或容量拒绝；最后达到4096-token思考预算后仍生成了20 token进度说明，不能据此认定思考预算强制结束整个任务。更深层模型或停止原因尚未确定。正常结束、工具退出码0或模型声称完成，都不能代替检查实际交付物。

同版本Q2_0/medium/default的64K压缩阈值测量中，也出现过正常结束却未交付报告：实例运行8.7分钟、成功压缩2次后，只返回继续读取指令的说明，报告仍为空；没有流错误、超时或容量拒绝。另一个完整实例反复复核已写报告，整个合并任务耗时57.7分钟，包含29次完全相同参数的额外工具调用。基础提示不能保证消除这些行为；调用方仍应按自己的任务合同核对实际交付，不能将HTTP成功或普通结束当成任务完成。

## 服务端循环提醒

**已弃用，默认关闭，不建议使用**（2026-10-11）。真实试跑与无提示无提醒基线各 3 次（Commit Audit）中，不加任何防护时模型也很少循环，提醒和防循环提示看不出收益，提醒多数是误报。功能暂时保留为显式开启，观察一段时间没有明显重复后删除。

前端对 Chat、Responses、Messages 生成请求（不含 `count_tokens`）检查请求里携带的对话历史：模型的最后一步若与本对话之前的步骤高度重复（相同工具调用且结果相同，或推理／回答文本高度相似），就在转发给模型的请求末尾追加一条一次性提醒，作为用户消息（Messages 接口里并入最后一条用户消息）。

- 只提醒，不拒绝、不中断，也不改变工具调用。提醒文字说明它来自模型服务而不是用户，要求模型检查是否陷入无进展的循环；如果重复是有意的并且在推进，就继续。
- 提醒只进入转发给模型的请求，不出现在响应里，也不写回调用方的历史，所以不会在后续上下文中累积。
- 前端不保存会话状态，每次请求从携带的历史重新判断，因此恢复或重试的会话会得到同样的判断。已提醒过的重复链之后再出现 2 次才再次提醒；新的重复链立即提醒。
- 判断只用机械规则（本对话内动态出现的文本和工具调用），不用关键词表，也不调用模型。离线语料上联合 F2 约 0.78–0.80，尚未达到 0.8 的门槛；真实干预效果尚未验证，可能出现误报。
- 只有请求头 `X-Loop-Reminder: on` 时才对本次请求检查和提醒；不带或其他值都不提醒。`frontend.log` 只记录"已追加提醒"和接口路径，不记录提醒或对话内容。

## 调用方动态防重复建议

建议ARW、Codex或其他调用方在自己的harness中观察实际工具结果与交付状态，按观测事实动态反馈。安装服务提供模型API，客户端shell、文件工具及任务是否完成由调用方管理；本节的建议与上面的服务端提醒相互独立，调用方的守卫不依赖服务端提醒。仅靠基础提示或命令全文相同的检测不能保证避免循环。

| 观测情形 | 建议检测与反馈 |
| --- | --- |
| 改写脚本后，同一解析错误仍在 | 将错误类别、失败表达式、工作目录和已知实际输入绑定；可从两次保留相同失败表达式的解析错误开始提醒。忽略控制台标签等无关变化，保留真实参数、路径及运算符。指出未改变的失败位置，建议先修复并用最小探针验证，再扩展其他检查。 |
| 换了其他命令后，又回到同一无效步骤 | 保留一个短窗口，例如最近8次完成调用；相同命令、目录、输入版本及可用结果在窗口内出现3次时提示复用已有事实、推进尚未完成的交付，不只要求连续重复。 |
| 多次正常结束，只有进度说明，交付物未推进 | 按调用方合同核验文件存在、内容变化及必要的机械格式／覆盖检查；连续两次正常未完成且交付物无进展时，在原线程的既有接续指示中指出实际缺项，要求先落盘已完成工作再处理剩余不确定性。 |

例如三次Node脚本长度或日志标签不同，但都在同一个表达式报缺少右括号，反馈应指出“该失败表达式尚未改变，请先修复它并运行最小验证”，而不只是“不要重复命令”。工具退出码0、模型声称修复或命令文字变化都不是完成证据；须检查错误是否消失、后续检查是否实际执行及交付物是否满足调用方合同。

检测按逻辑任务／阶段和线程隔离，并以原生工具事件身份去重；消息镜像、缓存重放和压缩历史不能当作新的调用。正常轮询、明确要求的重复测量、预期失败测试、新输入／文件版本、新错误位置、有实质进展的修复，以及调用方自身重置文件的恢复步骤应排除。缺少结果或交付状态时保留未知，不能当作空文件或相同输出。运行时错误可能由不同输入引起，只有相关输入版本确实已知时才合并；不要只凭异常名称、退出码或模糊的“没有进展”判断循环。

每个已确认卡点先提示一次，实际输入／证据或交付物有进展后重新计数。反馈只包含本线程已获准观察的事实，不提供审核答案、扩大读写授权或自动重放可能已有副作用的操作。活跃回合通过harness原生消息入口反馈；空闲回合由原有任务管理者按自己的恢复合同接续，避免两个组件分别唤醒同一任务。保持原权限和整个逻辑任务的累计截止时间，接续不重新获得一份完整预算；超过调用方上限或无法安全继续时按其原停止／人工处理流程收尾。

记录触发依据、消息接纳、模型原生收到，以及之后是否修复或交付。消息accepted、改了命令文字或再次声称完成，都不能单独证明提醒有效。先用历史日志及正常修复／轮询反例回放检查误报，再用真实任务核对反馈效果。

上述阈值是保守的候选起点，调用方应按自己的负载验证。本工程首版已通过离线机制检查，并完成本机Q2_0三次真实诊断：三次仍有确认循环，动态提醒均未触发，尚未证明真实提醒能够减少循环或降低耗时。主要遗漏发生在活跃回合的重复推理；命令结果守卫看不到全部语义重复，而“两次正常未完成结束”的交付检测须等回合结束才有机会反馈。不要把离线可触发或任务变快当作真实干预已有效，也不要据此替换已有日常防循环提示。调用方若增加活跃回合的停滞检测，应先核对实际交付进展、正常思考与修复反例，并单独验证误报和反馈效果。

## 基础提示词与上下文压缩

| 情况 | 提示词 | 谁负责接入 |
|---|---|---|
| 普通对话、文档/代码review、工具调用、训练等模型请求 | `config/prompts/startup-instructions.txt`：核验结果、完成任务及结束前自检（防循环段默认不加载，已弃用） | 模型服务自动追加；外部调用方无需重复加入 |
| harness要压缩历史、生成后续任务摘要 | `config/prompts/compact-prompt.txt`：只生成摘要、禁止继续执行任务或调用工具、保留约束和行动状态 | 本工程活跃WSL/ARW入口自动组合；`bin/qwen-agent` 为 Codex 设置 `experimental_compact_prompt_file`，为 Claude Code 设置 PreCompact hook；外部调用方须在自己的harness配置 |
| 场景另有角色、任务或摘要要求 | 场景自己的提示词 | 调用方保留并追加为相应基础提示的补充；不能替代基础提示 |
| 希望保留harness原生摘要要求 | 自己harness版本的默认摘要提示 | 将其作为基础压缩提示的补充；本工程使用经实际原生手动压缩路径核对的Codex 0.160.1快照，调用方无需复制维护资源 |

启动基础指令在模型进程启动时读取，应用于每次服务端模型请求，调用方自己的指令仍保留。`GET /model/status`的`native_health.startup_instructions`给出加载路径和SHA；修改后须下一次模型启动才生效。

压缩由调用方的harness管理，服务没有可靠的请求压缩标识，因此不会自动注入`compact-prompt.txt`。外部调用方在配置压缩时，读取该基础文件，将自己场景的摘要要求作为补充，保存组合文件，再通过Codex的`experimental_compact_prompt_file`等配置指向组合文件；只设置基础文件也可，不能用自定义摘要提示把基础指令覆盖掉。不要把“只输出摘要”加入普通review提示，也不要将基础文件同时当作自己的补充而重复拼接。服务不会修改调用方或全局Codex配置。

原生默认摘要快照不是基础提示词，也不是安装目录的公共配置。本工程将0.160.1实际原生手动压缩请求的快照保存在版本化的工具资源目录，不部署到安装目录的`config/`；调用方只需使用安装目录的基础文件，并按自己的harness和场景补充摘要要求。升级Codex后需重新核对，不能将旧快照视为新版本默认。
