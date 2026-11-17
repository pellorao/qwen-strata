# Strata Model Service

[English](README.md) | [简体中文](README.zh-CN.md)

This installation provides a Windows-native inference service for Qwen3.8-Flash-Next. A resident frontend listening on a fixed LAN address serves all requests and manages exclusive leases, model startup and shutdown, and inference forwarding. To use the service, a caller first acquires a key from the frontend, starts the model by selecting a context tier, runs inference through the OpenAI Chat, OpenAI Responses, or Anthropic Messages API, and finally releases the lease.

The caller manages Codex, Claude Code, or any other harness on its own, including providers, permissions, tools, sessions, and compaction policies.

This document helps first-time callers get a complete workflow running quickly; for full details on APIs, startup parameters, Codex and Claude Code integration, web search, and observed execution anomalies, see the [detailed manual](docs/manuals/caller-manual.md).

## Address

Callers only need to connect to the following frontend address to use the service. The frontend listens only on the WSL virtual network adapter, so it is unreachable from the LAN; its address is assigned by Windows and can change, so take `<WSL-gateway>` from the default route in WSL (`ip route show default`, the address after `via`) rather than writing it down:

| Host | Frontend Address |
|---|---|
| {{host}} | `{{base_url}}` |

The scheduled task `QwenStrataFrontend` starts the frontend at Windows user login and keeps it running, so callers do not need to start it. For access control, the frontend only accepts clients from this host and the subnets of this host's network interfaces (including the WSL virtual network interface), and returns 403 for all other addresses. If an HTTP proxy is configured in the caller's environment, set `NO_PROXY` for this address or connect directly.

## Complete a Full Call

The caller acquires a key, starts the model, runs inference, and releases the lease, in that order:

1. First call `POST /lease/acquire` to acquire a key (this request does not require a key). If another caller already holds the lease, it returns 409; there is no queuing or preemption.
2. Once you have acquired a key, include `Authorization: Bearer <key>` on all subsequent requests (`x-api-key: <key>` is also accepted). A missing, invalid, or already released key returns 403.
3. Call `POST /model/start` to start the model and wait until it is ready. Because this host serves only one model, the request body can simply be `{}`: omitting `model` selects that model, and omitting `context_window` selects the first tier.
4. Once the model is ready, send inference requests to `/strata/v1/chat/completions` (OpenAI Chat), `/strata/v1/responses` (OpenAI Responses, for Codex), or `/strata/v1/messages` (Anthropic Messages, for Claude Code).
5. When finished, call `POST /lease/release` to release the lease: this revokes the key, while the model stays loaded for the next caller to reuse. The frontend stops a model with no active lease after 30 minutes of idle time.

A caller can choose only two settings: the context size (by selecting a tier at startup) and the reasoning effort (passed with each request), since the model is fixed to this host's one served model; all other engine parameters, environment variables, sampling defaults, thinking budgets, and output limits are preset by the installation directory. To align with the selected tier, the caller must set its harness's context window and auto-compact threshold to the values for that tier. For the complete lease rules, API reference table, and parameters, see the [detailed manual](docs/manuals/caller-manual.md).

### Run Codex or Claude Code with the Launch Script

If you are running Codex or Claude Code directly, the bundled `bin/qwen-agent` script automates the entire lifecycle: acquire the lease → start the model → run Codex or Claude Code → release the lease on exit (leaving the model loaded for the next run). This script depends only on this installation directory and the Python 3 standard library.

```bash
qwen_install={{installation_wsl}}
python3 "$qwen_install/bin/qwen-agent" codex                       # Interactive Codex, served model on this host, high
python3 "$qwen_install/bin/qwen-agent" --effort medium codex exec "task description"
python3 "$qwen_install/bin/qwen-agent" claude                      # Claude Code
```

- If the lease is already held by another caller, the script exits immediately without queuing or preemption.
- For the remaining options, loading times, and environment variable handling, see the [detailed manual](docs/manuals/caller-manual.md#launch-script-wsl).

### Call Directly from Python

If you are integrating the service into your own code, follow the example below to run the steps above in order. This snippet uses only the standard library and runs from the LAN or WSL.

```python
import json, os, urllib.request
from pathlib import Path

base = "{{base_url}}"
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def request(path, body=None, key=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    data = None if body is None else json.dumps(body).encode()
    with opener.open(urllib.request.Request(base + path, data, headers), timeout=900) as reply:
        return json.load(reply)

credential = Path(".strata-access.json")  # Caller-private file, excluded from version control
fd = os.open(credential, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
key = None
try:
    key = request("/lease/acquire", {})["key"]
    with os.fdopen(fd, "w") as stream:
        fd = None
        json.dump({"base_url": base, "key": key}, stream)
    request("/model/start", {}, key)  # Omitting model uses the served model on this host
    answer = request("/strata/v1/chat/completions", {
        "messages": [{"role": "user", "content": "2+2=?"}],
        "reasoning_effort": "low", "temperature": 0}, key)
    print(answer["choices"][0]["message"]["content"])
finally:
    if fd is not None:
        os.close(fd)
    if key is not None:
        request("/lease/release", {}, key)  # Keep the credential file on failure for diagnosis
        credential.unlink(missing_ok=True)
```

The same holder can keep a key across multiple tasks, but do not let multiple background tasks share a key and independently stop the model or release the lease.

## Notes on Usage

To prevent stuck tasks, unreleased leases, or unintended retries, keep the following points in mind when integrating and running tasks:

- Before running a long task, read [Observed Execution Anomalies](docs/manuals/caller-manual.md#observed-execution-anomalies) and [Caller-Side Dynamic Anti-Repetition Guidance](docs/manuals/caller-manual.md#caller-side-dynamic-anti-repetition-guidance) in the detailed manual, and set a deadline for the entire task.
- Because a lease never times out and is never reclaimed automatically, the caller must release it in its own finally path. In addition, the key is a caller credential: do not write it into prompts, version control, shared logs, or reports.
- A streaming response can still fail after returning HTTP 200, so determine the final status from the in-stream events rather than the HTTP status alone; after an interrupted stream, do not blindly retry a request that may have already executed tools.
