# Strata Model Service: Detailed Caller Manual

[English](caller-manual.md) | [简体中文](caller-manual.zh-CN.md)

After reading the [introduction](../../README.md) for the frontend address and a complete call example (including a Python example), use this manual to look up specific endpoints, parameters, and integration configs, or to troubleshoot runtime issues. It covers leases, all endpoints, start parameters, reasoning effort and output, Codex and Claude Code integration, web search, logs, observed execution anomalies, and anti-repetition guidance.

Before running a long task, read [Observed execution anomalies](#observed-execution-anomalies) and [Caller-side dynamic anti-repetition guidance](#caller-side-dynamic-anti-repetition-guidance), and set a deadline for the entire task.

## Exclusive lease

Only one holder is allowed at a time. A caller acquires, uses, and releases a lease in this order:

1. Call `POST /lease/acquire` to acquire a key. If a holder already exists, the endpoint immediately returns 409; there is no queuing and no preemption.
2. Once you have the key, include `Authorization: Bearer <key>` (or `x-api-key: <key>`) on every subsequent request, including model start/stop, status, and inference. A missing, invalid, or released key returns 403.
3. Call `POST /model/start` to select the quantization and context tier and wait for the model to become ready. If the model left behind by the previous lease has the exact same quantization and tier, the service reuses it without reloading and returns `reused: true`; if it differs, the service stops the old model before starting the new one.
4. Call `POST /model/stop` to stop only the model while keeping the lease with the current caller, so you can restart with a different quantization or tier.
5. When the task finishes, call `POST /lease/release` to release the lease: this revokes the key, but **the model stays loaded** for the next caller to reuse. A model without a lease is stopped by the frontend after 30 minutes of idle time; to free system and GPU memory immediately, call `/model/stop` before releasing the lease.

Because the lease is kept only in frontend memory, with no timeout and no automatic reclamation, the caller must release it in its own finally path. If a key is lost or the holder exits abnormally, the service offers no keyless takeover endpoint; a maintainer must restart the frontend, which stops the model and clears the lease. In addition, the key is a caller credential: do not write it into prompts, version control, shared logs, or reports.

## Endpoints

The frontend provides both lease/model management endpoints and inference entry points. All paths are relative to the [frontend address](../../README.md#address); use `Content-Type: application/json` when sending JSON requests.

| Method and path | key | Description |
|---|---|---|
| `GET /health` | Not required | Frontend identity, `lease` (free/held), currently loaded model ID, and the startup-instructions SHA actually loaded for that model (`startup_instructions`, containing only the SHA and toggle, without body text; null when unloaded); does not mean the model is ready for inference |
| `POST /lease/acquire` | Not required | Request `{}`; returns `key` |
| `POST /lease/release` | Required | Request `{}`; revokes the key and returns `lease` and the still-loaded `model` (does not stop the model) |
| `POST /model/start` | Required | Accepts only `model` and `context_window` (see below); returns status once ready, with `reused` indicating whether an already-loaded model was reused |
| `POST /maintenance/model/start` | Required | Reserved for measurement and tuning by the maintenance project, accepting full maintenance options; not a caller endpoint and must not be used by callers |
| `POST /model/stop` | Required | Request `{}`; returns `status=stopped` and whether unloading succeeded cleanly |
| `GET /model/status` | Required | `status` is stopped, starting, unloaded, or running; includes `native_health` when running |
| `POST /admin/shutdown` | Required | For maintenance; shuts down the frontend after the model stops |
| `/strata/v1/chat/completions` | Required | OpenAI Chat |
| `/strata/v1/responses` | Required | OpenAI Responses (Codex) |
| `/strata/v1/messages`, `/strata/v1/messages/count_tokens` | Required | Anthropic Messages (Claude Code) |

Every request must go through the frontend because the internal native Strata service on this host listens only on 127.0.0.1 and uses an internal key generated randomly on each startup, so callers cannot bypass the frontend. Requests under `/strata/` are forwarded as-is to the native Strata service, and responses (including streams) are returned as-is.

Before forwarding, the frontend does only three things:
- The requested `model` must equal the currently loaded model ID, or the frontend returns 409; if omitted, it is filled in automatically. If no model is running, the frontend returns 503.
- When a Chat or Responses request omits reasoning effort, thinking budget, or output limit, the frontend fills them in according to [Reasoning effort and output](#reasoning-effort-and-output).
- When a streaming Responses request declares `{"type": "web_search"}`, the frontend executes the search via Brave; see [Web search](#web-search).
- Messages requests do not get default values filled in; the caller sets `max_tokens` and thinking itself.

### Errors

When a request is rejected or fails during execution, the frontend returns the reason using these status codes:

| Status code | Meaning |
|---|---|
| 403 | Invalid key, or client address is not on the local network |
| 409 | Lease is already held, requested model does not match the loaded model, or model is not stopped when shutting down the frontend |
| 400 | Invalid start parameters or request body |
| 503 | Model is not running, failed to start, or failed to stop; see `logs/` in the installation directory for details |

Note that a streaming response can still fail after returning HTTP 200. Determine the final state from in-stream events rather than HTTP status alone; after seeing a broken stream, do not blindly retry requests that may already have executed tools.

## Start parameters

Engine parameters, environment variables, sampling defaults, thinking budgets, and output limits are preset by the installation directory per "this host + quantization" and cannot be overridden by the caller. A caller can choose only three things: **model**, **context size** (selecting a tier at start time), and **reasoning effort** (passed with each request).

Pass the model and context size through `POST /model/start`, for example:

```json
{"model": "{{model}}", "context_window": {{example_context_window}}}
```

| Field | Description |
|---|---|
| `model` | Optional. This host exposes only one served model, the one listed under `models` in `config/deployment.json`, which is used when omitted; weights of other quantizations in the installation directory are not exposed, and requesting them returns 400 |
| `context_window` | Optional; defaults to the first tier of the served model when omitted. Must be one of the `context_window` values listed under `context_tiers.<model>` in `config/deployment.json` in the installation directory; each tier comes with a measured `auto_compact_token_limit`, and the caller must set its harness context window and auto-compact threshold to those two values from the same tier. When no tiers are listed for that quantization, this field must be omitted |

Passing any other field returns 400. For how to pass reasoning effort, see [Reasoning effort and output](#reasoning-effort-and-output).

When a caller switches tiers, `/model/start` automatically stops the old model first; to decide whether a model is "the same" and reusable, the service compares the full validated runtime configuration, including installation presets modified after deployment. When startup completes, the frontend also verifies the actually loaded model and context capacity.

The model ID of the served model is `qwen3.8-flash-next-` followed by the lowercase name of the served model (for example, {{model}} becomes `{{model_slug}}`).

### Installation presets

{{host.presets}}

## Reasoning effort and output

Each inference request can specify a reasoning effort and an output limit: Responses uses `reasoning.effort` and `max_output_tokens`, while Chat uses `reasoning_effort` and `max_tokens`. Values specified in the request take precedence; when omitted, the frontend fills them in automatically from the table below.

| Effort | Thinking token limit | Default total output limit (including thinking) |
|---|---:|---:|
| low | 2048 | 8192 |
| medium | 4096 | 16384 |
| high, xhigh, max | 8192 | 24576 |

The service does not offer a none tier: specifying any other effort (including none) returns 400. On top of this, different scenarios and parameter combinations follow these rules:

- Codex guardian approval requests have separate defaults regardless of effort: thinking 512, total output 1024 (installation presets, identical to `bin/qwen-approve`). Rather than inspecting prompt content, the service identifies these requests from the metadata Codex sends with the request, namely `thread_source` equal to `guardian_review` in `client_metadata["x-codex-turn-metadata"]`. An approval only needs to output a short JSON conclusion. Because Strata reserves min(max(512, total output/4), total output/2) for the answer, a total output of 1024 reserves exactly 512, allowing thinking to use the full 512. If the request supplies its own thinking budget or output limit, the request value takes precedence. In practice, Codex sends `reasoning_effort: low` without an output limit or sampling fields on guardian requests, and `bin/qwen-approve` explicitly sends the same values, so both sides use identical approval parameters.
- Requests whose effort matches the default effort of the current run directly use the budget and output limit from the defaults (for {{host}}: {{reasoning_effort}}, thinking {{reasoning_budget_tokens}} / total output {{max_tokens}}).
- When a request supplies its own output limit without a thinking budget, the thinking budget does not exceed half of the output limit; Strata additionally reserves at least 1/4 of the output limit for the answer.
- The thinking limit is not the actual thinking length. When the output limit supplied by a request exceeds the remaining space in the context window, the service shortens it to the remaining space instead of returning 400; if the input itself exceeds the context window, however, the service still returns 400 and never silently truncates the input.
- On the Messages endpoint, the caller sets `max_tokens` per the Anthropic protocol, so the frontend does not fill in the total output limit and only fills in the thinking limit; see the Claude Code section below.

### Internal retry when output hits the limit

In Codex, once model output is truncated because it hits the total output limit, Codex immediately ends the current turn; the model neither knows why nor gets a chance to rewrite. To address this, for **streaming** Responses requests, if the model's output hits the total output limit (ending with `response.incomplete` and `incomplete_details.reason = max_output_tokens`), the frontend does not hand the truncated answer directly to the caller, but instead automatically regenerates once internally.

- Trigger detection checks only this protocol signal, regardless of tool name, prompt, or client, behaving identically across all clients and tasks.
- Retry request = original request + reasoning and text already delivered in full to the caller during this generation + an automatic server notification. This notification is sent as a user message and explicitly notes that it comes from the model service rather than the user: it explains that the previous output hit the output limit, states what was being written when truncation occurred, notes that the truncated part was discarded without execution, and asks the model to respond to the previous request again by shortening the output or splitting an unavoidably long output into several steps (such as several smaller tool calls) instead of writing another equally long output in one go. The notification contains no specific numbers; it goes only into the request forwarded to the model, does not appear in the response, and is not written back into the caller's history.
- When the output limit was the default filled in by the service for the effort tier (meaning the request did not supply `max_output_tokens`), the retry doubles the limit, capped at 24576 (the total output limit of the high tier); the thinking limit stays unchanged, all extra space goes to the answer, and the notification also notes that more space is available this time. Conversely, if the request supplied its own `max_output_tokens`, the retry keeps the original value and only adds the notification. Consequently, a caller that did not supply a limit may receive `output_tokens` exceeding the default total output limit for that effort. If the limit exceeds the remaining space in the context window, the service shortens it to the remaining space as usual—in which case the notification still says more space is available, which may not match reality. The 1024 limit for Codex guardian requests is also a service preset and is likewise doubled on retry.
- From the caller's perspective, the same response simply continues streaming: the truncated item only ever emitted its start and deltas without a completion event, so it neither enters the caller's history nor gets executed; the retry events are renumbered and appended right after. Responses that do not hit the limit are forwarded byte-for-byte as-is with no added latency.
- Each request is retried at most 1 time; when the limit is doubled, the retry takes up to roughly 2 times as long as the first attempt. If the retry still hits the limit, cannot start, encounters an unexpected error during processing, or if a tool call was already delivered in full to the caller before truncation (in which case the caller may already be executing it), the frontend returns the truncated result as-is.
- The usage received by the caller is the value from the final generation, matching its context; the limit, tokens, and duration of the discarded generation are logged in the `output limit:` line of `logs/frontend.log`, while the engine log contains both generations.
- The following cases are not handled and behave as before when hitting the limit: first, Messages (Claude Code), because Claude Code itself returns a truncated tool call to the model as a failed result and continues, whereas retrying in an Anthropic stream would require reopening an already-emitted content block index, violating the protocol; second, non-streaming requests, the Chat endpoint, and Responses requests with hosted web_search.

## Launch script (WSL)

When running Codex or Claude Code in WSL, you do not need to call the lease and model endpoints manually; `bin/qwen-agent` handles the entire lifecycle automatically: acquire lease → start model → run Codex or Claude Code → release lease on exit (leaving the model loaded for the next reuse). The script depends only on this installation directory and the Python 3 standard library.

```bash
qwen_install={{installation_wsl}}
python3 "$qwen_install/bin/qwen-agent" codex                       # Interactive Codex, this host's served model, high
python3 "$qwen_install/bin/qwen-agent" --effort medium codex exec "task description"
python3 "$qwen_install/bin/qwen-agent" claude                      # Claude Code
```

The script follows these rules when managing leases and isolating the environment:

- `--model` is optional and defaults to this host's served model (`models` in `config/deployment.json`); if another quantization is specified, the script exits with an error before acquiring a lease.
- If the lease is already held by someone else, the script exits immediately without queuing or preemption.
- Model load time: {{host.load_time}}; reusing an already-loaded model with the same parameters skips reloading. During execution, Ctrl-C is passed to the agent; whether the agent exits, the terminal closes, or the process is terminated, the script releases the lease and prompts you to restart the frontend task if releasing fails.
- The key is placed only in the agent process's environment variables, never written to files or command-line arguments.
- `ANTHROPIC_*`, `OPENAI_*`, `AI_AGENT`, and variables starting with `CLAUDE` (except `CLAUDE_CONFIG_DIR`) in the caller's environment are not passed to the agent; therefore, when launched inside a Claude Code session, the agent does not inherit the parent session's session id or message channel. Put any needed Claude Code customizations into `env` in settings.json.
- The script does not modify the caller's `~/.codex` or `~/.claude` configuration; all settings are passed via command-line overrides or environment variables.

## Codex integration

If you configure Codex to connect to this service yourself instead of using the launch script, set the parameters below. This is also the exact configuration the launch script passes to Codex (shown for the default tier of {{model}}, where the context window and threshold come from the first tier of the quantization in `config/deployment.json`):

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

Here, the lease key is provided only to this harness through the environment variable named by `env_key`; request retries are set to 0 so retries do not repeat tool operations that have already executed.

If your program creates a new `CODEX_HOME` on every run during measurement or batch processing, also pass `-c features.plugins=false` or write `[features]` `plugins = false` in that directory's `config.toml`; otherwise Codex 0.162 clones a roughly 105MB plugin repository into every new directory even though none of that content enters the model input. Interactive use with a fixed `~/.codex` clones only once and does not need this setting.

The `config/model-catalog.json` file in the configuration describes only the facts of this host's served model: model name, reasoning tiers, context window (the default tier of this model on this host, i.e., the first tier in `context_tiers` in `config/deployment.json`), text-only input, web search tool availability, and `auto_review_model_override` pointing to itself. Base instructions and message structure are taken from the luna model entry bundled with the installed Codex version and impose no extra restrictions on what work can be done; read-only or writable scope constraints are determined by each scenario's prompts and sandbox permissions. This file corresponds to Codex 0.162.0 and is regenerated by the maintenance project after Codex upgrades.

For the tool protocol, native Responses supports function, namespace, custom tools, `additional_tools`, and reasoning content replay, but does not support client-side `tool_search`: the installed `model-catalog.json` sets `supports_search_tool = false`, so Codex inlines MCP tools directly in the tool list rather than hiding them behind `tool_search`. Web search is hosted by the frontend; see below.

## Web search

Web search does not use the harness's own search service; instead, this installation provides it uniformly via Brave (with the key in `installation.private.toml`).

- **Codex**: Set `web_search = "live"`. The frontend replaces `web_search` with a function of the same name for the model; when the model calls it, the frontend executes `search`, `open_page`, and `find_in_page`, writes the results back into the conversation, and continues generation, while Codex sees ordinary `web_search_call` items. This feature supports streaming only; each request allows at most 8 searches and 10 model turns, with all turns sharing a single output limit. Supported parameters are `filters.allowed_domains` and `search_context_size`; `user_location` is not supported.
- So that `codex exec resume` can still read earlier search records when acquiring a new lease each time, search results are kept in frontend memory by random call id and retained across leases, then restored for the model when Codex sends them back; the oldest records are evicted when the total exceeds the limit, and all records are cleared when the frontend restarts, after which searches from old sessions receive only "result unavailable".
- **Claude Code**: Its built-in WebSearch depends on Anthropic's service, so the launch script disables it and mounts the MCP server `src/brave_mcp.py` instead (providing the tools `mcp__brave__web_search`, `open_page`, and `find_in_page`).
- Only public http(s) addresses are fetched; intranet, localhost, credentialed, or non-standard-port addresses are rejected, shorthand numeric addresses such as `127.1` are likewise rejected, and every redirect is rechecked. Domain names are resolved at connection time, rejected if any resolved address is non-public, and connected to directly using the verified address without going through a proxy. If this host needs to allow ranges such as fake-IP network resolution subnets, you can allow extra CIDR ranges for this host via `fetch_allow_networks` (a CIDR list) in `config.local.json` in the installation directory, though literal IP addresses written directly in a URL are still rejected; destinations reached through a router are then protected only by the router's rules. In addition, the Brave key is sent only to the Brave API; Brave calls are rate-limited to at most one per second, with no retries on failure.

## Claude Code integration

To connect Claude Code to this service with the same context window, reasoning effort, and approval behavior as Codex, pass the configuration via environment variables and command-line arguments. Below are the exact environment variables and arguments passed by the launch script (without modifying `~/.claude`; shown for the default tier of {{model}}):

```bash
export ANTHROPIC_BASE_URL={{base_url}}/strata
export ANTHROPIC_AUTH_TOKEN=<key>
export ANTHROPIC_MODEL={{model_slug}}        # Default model for OPUS / SONNET / HAIKU is also set to the same model
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
export CLAUDE_CODE_MAX_CONTEXT_TOKENS={{context_window}}            # Declare real context window: context_window of the selected tier
export CLAUDE_CODE_MAX_OUTPUT_TOKENS=24576             # Total output for this effort (low 8192, medium 16384, high 24576)
export CLAUDE_CODE_EFFORT_LEVEL=high                    # Same as model_reasoning_effort in Codex
export CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE={{auto_compact_token_limit}}       # Auto-compact threshold: auto_compact_token_limit of the selected tier, same as Codex
export ENABLE_TOOL_SEARCH=false                        # Disable tool search and send all tool definitions inline (see below)

claude --mcp-config '{"mcpServers": {"brave": {...}}}' --permission-mode default \
       --settings '{"skipWebFetchPreflight": true, "permissions": {"deny": ["WebSearch"]},
                   "hooks": {"PreCompact": [{"hooks": [{"type": "command", "command": "cat <installation directory>/config/prompts/compact-prompt.txt"}]}],
                             "PermissionRequest": [{"matcher": "*", "hooks": [{"type": "command", "command": "python3 <installation directory>/bin/qwen-approve", "timeout": 180}]}]}}' [caller arguments]
```

Each setting works as follows:

- Total output and thinking limits: Total output takes the value for the effort from the table above (`bin/qwen-agent --effort` sets both the effort and this value), matching what the frontend fills in for Codex. Because Claude Code includes `max_tokens` on every request and the frontend does not override a value supplied by the request, total output is governed by this environment variable—do not raise it; when remaining space in the context window is insufficient, the service shortens the output limit to the remaining space without returning 400. Meanwhile, the frontend fills in a hard thinking limit on Messages requests: when thinking is disabled (`thinking.type: disabled`) or the request already includes `reasoning_budget_tokens`, it leaves the request untouched; otherwise it takes the thinking limit corresponding to the reasoning effort (8192 for high, see the table above), uses the request's `thinking.budget_tokens` if smaller, and caps the result at half of `max_tokens`. In actual requests, Claude Code sends `thinking: adaptive`, `output_config.effort` (from `CLAUDE_CODE_EFFORT_LEVEL`), and `max_tokens`, so the thinking limit matches Codex at the same effort (8192 for high), and Strata reserves the remaining space for the answer.
- Effort: The environment variable `CLAUDE_CODE_EFFORT_LEVEL` applies to the entire session, whereas the command-line flag `--effort` stops taking effect after the first compaction, so the launch script passes effort via the environment variable.
- Auto-compaction: {{host.compact_check}}
- Approval: Handled exclusively by `bin/qwen-approve` rather than Claude Code's auto mode—in 2b acceptance testing, auto mode judged 5/9 correctly and took 191 seconds per run, whereas `qwen-approve` judged 7/7 correctly in just 80 seconds. The permission mode is `default`, and every permission request is handed to `qwen-approve` via the `PermissionRequest` hook: it sends the user messages (the sole source of authorization), the last 6 tool calls and results (marked as untrusted data), and the pending action to this model for review—the pending action is never truncated and is rejected outright as too long to review if it exceeds 20000 characters, while history and results are each truncated to their first 2000 characters; the review request uses `reasoning_effort: low`, a thinking limit of 512 tokens, and a total output of 1024 tokens, identical to Codex guardian. The script waits up to 150 seconds for the model's reply (the hook allows 180 seconds) and returns allow / deny with a reason; any timeout, error, or unparseable reply results in a denial. If the user merely asks the agent to follow steps found in a file, webpage, or tool output, only harmless steps are authorized; destructive or out-of-bounds steps must have their effect and target explicitly named in the user's message. Every decision logs one line to `logs/approve.log` (including tool, decision, reason, duration, and usage, without the key).
- Compaction: When the PreCompact hook exits with code 0, its stdout is appended after Claude Code's built-in summary instructions under `Additional Instructions:`, so every compaction (automatic or manual) includes `compact-prompt.txt`. **Exception**: Claude Code provides no way to replace its built-in summary instructions, so a compaction request combines "built-in instructions + base compaction prompt", whereas Codex replaces the prompt entirely with the base compaction prompt via `experimental_compact_prompt_file`. This is the only prompt difference between the two that cannot be aligned.
- `skipWebFetchPreflight`: Disables the domain check query that WebFetch sends to `api.anthropic.com` before fetching a webpage.
- Tool search: Setting `ENABLE_TOOL_SEARCH=false` disables Claude Code's tool search (lazy loading of tool definitions). When left enabled in Claude Code 2.1.309, every request adds a placeholder tool `DeferredToolPlaceholder` with `defer_loading`, and deferred tools must be expanded on demand via `tool_reference` blocks; however, Strata's Messages endpoint does not implement either semantics (the placeholder tool is passed to the model as an ordinary tool and `tool_reference` blocks are dropped), so tool search cannot work on this service. Once disabled, all tools (including the 3 from brave) are inlined with full definitions, matching the 2.1.303 tool list (verified by zero-model packet capture on 2.1.309, 2026-10-24). The launch script always sets this value, overriding any variable of the same name in the caller's environment.

### Parameter comparison with Codex

Since 2026-10-12, `bin/qwen-agent` keeps the two agents completely identical at the parameter level. It starts the model using the served model's default tier (the first tier of `context_tiers` in `config/deployment.json`) and passes the context window and threshold from that same tier to both agents; if no tiers are listed in the configuration, it exits with an error immediately without acquiring a lease. The table below uses {{host}}'s {{model}} as an example:

| Parameter | Codex | Claude Code |
|---|---|---|
| Context window | `model_context_window` {{context_window}} | `CLAUDE_CODE_MAX_CONTEXT_TOKENS` {{context_window}} |
| Auto-compact threshold | `model_auto_compact_token_limit` {{auto_compact_token_limit}} | `CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE` {{auto_compact_token_limit}} |
| Effort | `model_reasoning_effort` | `CLAUDE_CODE_EFFORT_LEVEL` (same `--effort`) |
| Thinking limit | Filled by frontend per effort: 2048 / 4096 / 8192 | Filled by frontend per effort, same values |
| Total output | Filled by frontend per effort: 8192 / 16384 / 24576 | `CLAUDE_CODE_MAX_OUTPUT_TOKENS`, same values |
| Sampling | Not sent; uses installation presets {{sampling}} | Not sent (verified by packet capture); same presets |
| Approval parameters | guardian: low, thinking 512 / total output 1024, no sampling sent | `qwen-approve`: same values |

The two agents share identical approval parameters, but their implementation mechanisms differ:

| Aspect | Codex guardian | Claude Code + `qwen-approve` |
|---|---|---|
| Prompt | Codex's built-in guardian risk policy | This project's policy: user messages are the sole source of authorization; destructive or out-of-bounds steps must be explicitly named by the user |
| Context | Session transcript organized by Codex itself | User messages + last 6 tool calls and results (marked untrusted) + pending action |
| Request count | A single approval may involve multiple model requests (multi-turn within the guardian thread) | 1 request per approval |
| Timeout and errors | Handled by Codex's built-in mechanism, unmodified by this project; exact timeout not verified | Up to 150 seconds for model reply; timeout, error, or unparseable reply is always denied and logged to `logs/approve.log` |

For the compaction prompt exception, see the "Compaction" bullet above.

In terms of endpoint support, the native service provides `/v1/messages` and `/v1/messages/count_tokens`. A smoke check on 2026-10-09 (Claude Code 2.1.295, `-p`, Read tool) confirmed that thinking and tool calls work. Two differences are currently known:

- Claude Code does not recognize this model name and warns `unrecognized_model`, but the context window and output limit still take effect from the environment variables above.
- `count_tokens` does not include the startup instructions injected by the server, so its count is roughly 420 tokens lower than the actual input.

In addition, 2b acceptance testing verified search, approval, and auto-compaction with the model (see engineering report `reports/v0.1.40.2/agent-integration-2b/`); long-session reliability is covered by subsequent ARW capability verification.

### Approvals and the main conversation's cache

{{host.approval_cache}}

## Logs

When troubleshooting, check three log files under `logs/` in the installation directory: `frontend.log` records frontend requests and errors, `model-server.log` is the native service log, and `<quantization>-prebuilt-engine.log` is the engine log. None of the logs record prompt content.

## Observed execution anomalies

During long tasks, the model may finish early before the task is complete, or fall into a loop of repeated steps. When designing integration logic and result validation, callers should account for the following observed anomalies:

The first anomaly is returning an undeclared tool call during auto-compaction. In the Commit Audit reasoning effort measurements on 2026-10-06, initial review runs 1, 2, and 4 under Strata v0.1.38, Qwen3.8-Flash-Next Q2_0, low, default, and a 100000 compaction threshold / 156584 context window returned an `exec_command` tool call during the automatic context compaction request even though that request declared no such tool. The protocol bridge at the time rejected the call, and the rejected call was not executed; however, the streaming endpoint may already have returned HTTP 200 before ending with `response.failed` and the error message `[invalid_response] Model returned unknown tool: exec_command`. Codex 0.160.0 in that batch therefore terminated the current Reviewer turn, leaving the report undelivered. Note that this was a model tool-response error observed under those conditions, not a failure after executing a shell command, and it must not be diagnosed as a network disconnect merely from "stream disconnected"; its incidence rate across other versions, quantizations, efforts, or workloads is not yet determined.

The second anomaly is repeating ineffective steps until a long task times out. On 2026-10-04, during a Commit Audit under Strata v0.1.38, Qwen3.8-Flash-Next Q2_0, medium, and a separately trained review profile, the model executed the exact same ineffective JSON-fix command 98 times in a row while the same 5 lines of syntax errors persisted for roughly 35 minutes—showing that a successful tool return does not mean the task is making progress. A wrap-up reminder at minute 55 entered the native session, after which the model fixed the JSON syntax but then repeatedly read source files, failed to deliver before the deadline, and was natively interrupted at minute 60 with a final status of incomplete. The original timeout record was preserved; the user later authorized a separately saved rerun of the same scenario, which delivered the report normally without overwriting or deleting the first-run failure.

This case shows that long tasks can fall into repetitive operations and prolonged stalls that hold up caller progress; however, neither the cause nor the incidence rate is yet determined, so it cannot be asserted that all quantizations, efforts, profiles, or tasks will behave this way, nor can the training profile be identified as the cause. After that comparison round, the decision was made not to adopt that training profile and to continue using default.

When the model process starts, the installed service reads `config/prompts/startup-instructions.txt` under the installation root and appends it as part of the system prompt to the caller's instructions on every request (view the file directly for the full text). Chat, Responses, and Messages requests all use this prompt, so callers do not need to add the same instructions again. Since 2026-10-11, default loading strips the leading `Progress and loop prevention` section from the file (that loop prevention requirement originally asked the model to recognize consecutive repeated steps with no progress and change its approach, and is now deprecated; see [Server-side loop reminder](#server-side-loop-reminder)), leaving all other bytes unchanged; in `native_health.startup_instructions` on the status endpoint, `sha256` is the SHA of the actually loaded content, `source_sha256` is the SHA of the source file, and `loop_prevention_enabled` indicates whether that section was added back. The currently retained requirements are: keep executing while the task and required deliverables remain incomplete, without substituting a plan or progress note for delivery; before finishing, verify actual completion item by item, write required reports to their designated locations and verify their contents, and continue working if actionable work remains. At the same time, explicit stop instructions, time limits, and verified blockers must still be obeyed, and when a task cannot be completed the model must clearly report the reason and actual partial results. However, the behavioral benefit of the two added requirements has not yet been measured; prompts cannot guarantee that the model will not stop early or repeat itself, and task completion must still be judged by actual deliverables.

Subsequent observations showed that stalls still occurred with the prompt above enabled. In the second Commit Audit under the same version, Q2_0, medium, and default profile, the model still ran the same failing probe command 18 times and re-read the same role rules 21 times while the output body of the identical command never changed; that instance eventually finished normally at 49.73 minutes without triggering an interrupt (these counts are tool-call counts, including batched submissions, and do not equal independent inference turns). This shows that the default profile can also exhibit such stalls and that prompts cannot guarantee loop avoidance. In the third Commit Audit under the same configuration and default profile, the model checked the same 118-line report multiple times with different commands and claimed it passed, yet the original generator still rejected 87 file-evidence format items and one governance source, completing at 34.99 minutes only after two same-thread revisions—showing that the model's own successful self-check cannot replace the caller's existing formal result validation. Furthermore, this prompt file is fixed each time the model process starts; editing the file does not change an already-started instance and takes effect only on the next model start. You can check the relative path and SHA-256 of the loaded file via `native_health.startup_instructions` in `GET /model/status`. The full model input also includes caller instructions, task, tools, and history, and is not identical to this fixed appended file.

Beyond looping stalls, the model may also stop early without any error, leaving only a progress note. In another observation with a 150K/206584 context, the task ended normally after 8.8 minutes but returned only a progress note about continuing to check materials, without writing the required report: across 32 total tool calls during the run, 10 were extra repetitions with identical parameters. No timeouts, interrupts, connection faults, or capacity rejections were observed throughout; after reaching the 4096-token thinking budget at the end, the model still generated a 20-token progress note, so the thinking budget cannot be identified as having forcibly ended the entire task, and the deeper model or stopping cause is not yet determined. This likewise shows that a normal finish, a tool exit code of 0, or the model's claim of completion cannot replace checking the actual deliverables.

In the 64K compaction threshold measurements under the same version with Q2_0/medium/default, normal completion without delivering a report also occurred: one instance ran for 8.7 minutes and compacted successfully 2 times, only to return a note about continuing to read instructions while leaving the report empty, with no stream errors, timeouts, or capacity rejections during the run. Another complete instance repeatedly re-verified an already-written report, taking 57.7 minutes for the combined task and making 29 extra tool calls with identical parameters. In short, base prompts cannot guarantee the elimination of these behaviors; callers must still verify actual deliverables against their own task contract and must not treat HTTP success or an ordinary finish as task completion.

## Server-side loop reminder

This feature is **deprecated, disabled by default, and not recommended for use** (2026-10-11). In a comparison of 3 runs each between real trial runs and a baseline with neither prompt nor reminder (Commit Audit), the model rarely looped even without any protection, the reminder and loop prevention prompt showed no discernible benefit, and most reminders were false positives. The feature is temporarily retained behind an explicit opt-in and will be removed after an observation period with no significant repetition.

When explicitly enabled, the frontend inspects the conversation history carried in Chat, Responses, and Messages generation requests (excluding `count_tokens`): if the model's last step is highly repetitive with earlier steps in the same conversation (identical tool calls with identical results, or highly similar reasoning/answer text), the frontend appends a one-time reminder to the end of the request forwarded to the model, sent as a user message (or merged into the last user message on the Messages endpoint).

- It only reminds; it never rejects, interrupts, or alters tool calls. The reminder text states that it comes from the model service rather than the user and asks the model to check whether it is stuck in a loop without progress; if the repetition is intentional and making progress, the model should continue.
- The reminder goes only into the request forwarded to the model; it does not appear in the response and is not written back into the caller's history, so it never accumulates in subsequent context.
- The frontend stores no session state and re-evaluates from the carried history on every request, so resumed or retried sessions receive the same evaluation. An already-reminded repetition chain triggers another reminder only after appearing 2 more times, whereas a new repetition chain triggers a reminder immediately.
- Detection uses only mechanical rules (based on text and tool calls appearing dynamically within the current conversation), without keyword lists or model calls. Its joint F2 on offline corpora is roughly 0.78–0.80, below the 0.8 threshold; real intervention effectiveness has not yet been verified, and false positives may occur.
- A request is checked and reminded only when it carries the request header `X-Loop-Reminder: on`; omitting the header or passing any other value disables reminders. `frontend.log` records only "reminder appended" and the endpoint path, never the reminder text or conversation content.

## Caller-side dynamic anti-repetition guidance

ARW, Codex, or other callers should observe actual tool results and delivery status in their own harness and provide dynamic feedback based on observed facts. The installed service provides the model API, while client shells, file tools, and task completion are managed by the caller; the guidance in this section is independent of the server-side reminder above, and caller guards do not depend on the server-side reminder. Relying solely on base prompts or exact full-command string matching cannot guarantee loop avoidance.

For three common stall patterns, detect and provide feedback according to the rules below:

| Observed pattern | Recommended detection and feedback |
| --- | --- |
| After rewriting a script, the same parse error persists | Bind the error category, failing expression, working directory, and known actual inputs; start reminding after a parse error preserves the same failing expression twice. Ignore irrelevant changes such as console labels while retaining real arguments, paths, and operators. Point out the unchanged failure location and suggest fixing it and verifying with a minimal probe before expanding to other checks. |
| After switching to other commands, the model returns to the same ineffective step | Keep a short window, such as the last 8 completed calls; when the same command, directory, input version, and usable result appear 3 times within the window, prompt the model to reuse established facts and advance unfinished deliverables, rather than requiring consecutive repetition. |
| Multiple normal finishes leave only progress notes without advancing deliverables | Verify file existence, content changes, and required mechanical format/coverage checks against the caller contract; after two consecutive normal yet incomplete finishes with no deliverable progress, point out the actual missing items in the existing continuation instructions of the original thread and require persisting completed work to disk before handling remaining uncertainties. |

For example, if three Node scripts differ in length or log labels but all report a missing closing parenthesis on the same expression, the feedback should state "that failing expression has not changed; fix it first and run a minimal verification" rather than merely "do not repeat commands". A tool exit code of 0, a model claim of having fixed the issue, or a change in command wording is not evidence of completion; you must check whether the error disappeared, whether follow-up checks actually ran, and whether the deliverables satisfy the caller contract.

Isolate detection by logical task/phase and thread, and deduplicate by native tool-event identity; message mirroring, cache replay, and compacted history must not be counted as new calls. At the same time, exclude normal polling, explicitly requested repeated measurements, expected-failure tests, new input/file versions, new error locations, fixes that make substantive progress, and recovery steps where the caller itself resets files. When results or delivery status are missing, keep the state as unknown rather than treating it as an empty file or identical output. Furthermore, runtime errors can be caused by different inputs, so merge them only when the relevant input versions are positively known; do not judge a loop solely from exception names, exit codes, or a vague "lack of progress".

For trigger cadence and permission boundaries, prompt once for each confirmed stall point and reset the count only after actual inputs/evidence or deliverables progress. Feedback must contain only facts that the current thread is already permitted to observe; do not supply review answers, expand read/write permissions, or automatically replay operations that may already have had side effects. For an active turn, deliver feedback through the harness's native message entry point; for an idle turn, let the original task manager resume according to its own recovery contract so two components do not separately wake the same task. When resuming, keep the original permissions and the cumulative deadline of the entire logical task rather than granting a fresh full budget; if the caller's limit is exceeded or continuation is unsafe, wrap up through its original stop/manual-handling flow.

To evaluate whether the guard actually works, record the trigger basis, message acceptance, native receipt by the model, and whether a fix or delivery followed. Message acceptance alone, a change in command text, or another claim of completion cannot by itself prove that the reminder worked. First replay historical logs and counterexamples of normal fixes/polling to check for false positives, then verify feedback effectiveness on real tasks.

Finally, note that the thresholds above are only conservative candidate starting points that callers should validate against their own workloads. The first version in this project passed offline mechanism checks and completed three real diagnostic runs on this host with Q2_0: all three still had confirmed loops, dynamic reminders never triggered, and real reminders have not yet been shown to reduce loops or shorten runtime. The main misses occurred in repeated reasoning within active turns; command-result guards cannot see all semantic repetition, while deliverable detection for "two normal yet incomplete finishes" must wait until a turn ends before it can give feedback. Therefore, do not treat offline triggerability or faster tasks as proof that real intervention is effective, and do not replace existing everyday loop prevention prompts on that basis. If a caller adds stall detection for active turns, it should first check actual deliverable progress and counterexamples of normal thinking and fixing, and separately validate false positives and feedback effectiveness.

## Base prompts and context compaction

Two kinds of base prompts are involved during model execution: the everyday task prompt is appended automatically by the server, whereas the context compaction prompt must be configured by external callers in their own harness. The table below lists how prompt responsibilities are divided across scenarios:

| Scenario | Prompt | Who integrates it |
|---|---|---|
| Ordinary chat, document/code review, tool calls, training, and other model requests | `config/prompts/startup-instructions.txt`: verify results, complete the task, and self-check before finishing (the loop prevention section is not loaded by default and is deprecated) | Appended automatically by the model service; external callers do not need to add it again |
| The harness needs to compact history and generate a summary for follow-up work | `config/prompts/compact-prompt.txt`: generate only a summary, forbid continuing task execution or calling tools, and preserve constraints and action state | Assembled automatically by this project's active WSL/ARW entry points; `bin/qwen-agent` sets `experimental_compact_prompt_file` for Codex and a PreCompact hook for Claude Code; external callers must configure it in their own harness |
| A scenario has additional role, task, or summary requirements | The scenario's own prompt | Retained and appended by the caller as a supplement to the corresponding base prompt; must not replace the base prompt |
| You want to preserve the harness's native summary requirements | The default summary prompt of your harness version | Use it as a supplement to the base compaction prompt; this project uses a Codex 0.160.1 snapshot verified against the actual native manual compaction path, and callers do not need to copy maintenance resources |

For everyday requests, the startup base instructions are read when the model process starts and applied to every server-side model request while preserving the caller's own instructions. `native_health.startup_instructions` in `GET /model/status` reports the loaded path and SHA; edits to the file take effect only on the next model start.

For context compaction, because compaction is managed by the caller's harness and the server has no reliable way to identify a compaction request, the server does not inject `compact-prompt.txt` automatically. When configuring compaction, an external caller must read that base file, append its scenario's summary requirements as a supplement, save the combined file, and point Codex's `experimental_compact_prompt_file` (or equivalent setting) to the combined file; using the base file alone is also acceptable, but a custom summary prompt must not overwrite the base instructions. Do not add "output only a summary" to ordinary review prompts, and do not duplicate the base file by also treating it as your own supplement. The service never modifies caller or global Codex configurations.

In addition, the native default summary snapshot is neither a base prompt nor a public configuration in the installation directory. This project stores the snapshot of the actual 0.160.1 native manual compaction request in a versioned tool-resources directory rather than deploying it to `config/` in the installation directory; callers only need to use the base file in the installation directory and supplement it with summary requirements for their own harness and scenario. After upgrading Codex, re-verify rather than treating an old snapshot as the default for the new version.
