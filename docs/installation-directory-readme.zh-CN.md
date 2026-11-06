# Strata 模型服务

[English](README.md) | [简体中文](README.zh-CN.md)

本安装提供 Qwen3.8-Flash-Next 的 Windows 原生推理服务。服务由一个监听局域网固定地址的常驻前端统一对外，负责独占租约、模型启停和推理转发。调用方使用时，先向前端领取 key，选择量化和参数并启动模型，再通过 OpenAI Chat、OpenAI Responses 或 Anthropic Messages 接口推理，最后归还。

调用方自行管理 Codex、Claude Code 或其他 harness，包括 provider、权限、工具、会话与压缩策略。

本文供初次接入的调用方快速跑通流程；关于接口、启动参数、Codex 与 Claude Code 的接入、网页搜索、已观察到的执行异常等完整说明，请见[详细手册](docs/manuals/caller-manual.zh-CN.md)。

## 地址

调用方只需连接以下前端地址即可使用服务：

| 主机 | 前端地址 |
|---|---|
| {{host}} | `{{base_url}}` |

前端随 Windows 用户登录由计划任务 `QwenStrataFrontend` 启动并常驻运行，因此不需要调用方启动。在访问范围上，前端只接受本机及本机各网卡所在子网（含 WSL 虚拟网卡）的客户端，其他地址返回 403。如果调用环境中存在 HTTP 代理，请对该地址设置 `NO_PROXY` 或显式直连。

## 完整调用一次

调用方依次领取 key、启动模型、推理、归还：

1. 先调用 `POST /lease/acquire` 领取 key（此请求不需要 key）。如果已有持有者则返回 409；不排队、不抢占。
2. 领到 key 后，之后的请求都要带上 `Authorization: Bearer <key>`（也接受 `x-api-key: <key>`）。缺失、错误或已归还的 key 返回 403。
3. 调用 `POST /model/start` 启动模型并等待就绪。由于本机只对外一个模型，请求体可以直接是 `{}`：省略 `model` 即用它，省略 `context_window` 即用第一档。
4. 模型就绪后，向 `/strata/v1/chat/completions`（OpenAI Chat）、`/strata/v1/responses`（OpenAI Responses，Codex）或 `/strata/v1/messages`（Anthropic Messages，Claude Code）发推理请求。
5. 用完后调用 `POST /lease/release` 归还：这会撤销 key，但模型继续加载，留给下一个调用方复用。没有租约的模型在空闲 30 分钟后由前端停止。

调用方只能选三项：模型、上下文大小（启动时选择档位）、推理强度（随每个请求传递）；其余的引擎参数、环境变量、采样默认值、思考预算和输出上限都已由安装目录预置。为了与所选档位对齐，调用方必须把自己 harness 的窗口和自动压缩阈值设为所用档的值。完整的租约规则、接口表和参数见[详细手册](docs/manuals/caller-manual.zh-CN.md)。

### 用启动脚本运行 Codex 或 Claude Code

如果直接运行 Codex 或 Claude Code，可以用自带的 `bin/qwen-agent` 自动完成整个生命周期：领取租约 → 启动模型 → 运行 Codex 或 Claude Code → 退出后归还租约（模型留给下一次复用）。该脚本只依赖本安装目录和 Python 3 标准库。

```bash
qwen_install={{installation_wsl}}
python3 "$qwen_install/bin/qwen-agent" codex                       # 交互式 Codex，本机对外模型、high
python3 "$qwen_install/bin/qwen-agent" --effort medium codex exec "任务描述"
python3 "$qwen_install/bin/qwen-agent" claude                      # Claude Code
```

- 如果租约已被他人持有，脚本会立即退出，不排队、不抢占。
- 其余选项、加载耗时和环境变量的处理见[详细手册](docs/manuals/caller-manual.zh-CN.md#启动脚本wsl)。

### 用 Python 直接调用

如果在自己的代码中接入服务，可以按下面的示例依次执行上述步骤。这段代码仅依赖标准库，可从局域网或 WSL 执行。

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

同一持有者可以保留 key 完成多个任务；但不要让多个后台任务共享 key 后各自停止或归还。

## 使用时要注意

为了避免任务卡住、租约未释放或异常重试，接入和运行时请注意以下事项：

- 运行长时间任务前，请先阅读详细手册的[已观察到的执行异常](docs/manuals/caller-manual.zh-CN.md#已观察到的执行异常)及[调用方动态防重复建议](docs/manuals/caller-manual.zh-CN.md#调用方动态防重复建议)，并为整个任务设置截止时间。
- 因为租约没有超时，也不自动回收，所以调用方必须在自己的 finally 路径里归还。同时，key 是调用方凭据，不写入提示词、版本控制、共享日志或报告。
- 流式响应在返回 HTTP 200 之后仍可能失败，因此终态以流内事件为准，不能只看 HTTP 状态；看到断流后，也不要盲目重试可能已经执行过工具的请求。
