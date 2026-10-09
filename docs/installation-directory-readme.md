# Strata 模型服务调用手册

本安装提供 Qwen3.8-Flash-Next 的 Windows 原生推理服务。通过安装入口启动独占控制器后，调用方经 HTTP API 领取独占 key，选择量化和参数，再进行模型请求、查询、停止及归还。调用方只需知道安装目录，无需访问维护工程。

长时间任务使用前，请阅读[已观察到的执行异常](#已观察到的执行异常)及[调用方动态防重复建议](#调用方动态防重复建议)，为整个任务设置截止时间。

各调用方自行管理 Codex 或其他 harness，包括 provider、权限、工具、会话与压缩策略。

## 调用方使用方法

只需要知道安装目录：

```bash
qwen_install=/mnt/c/Users/Pello/AppData/Local/Programs/qwen-3.8-flash-next
bash "$qwen_install/Run-Strata-Controller.sh"
```

WSL部署使用上述入口，原生Windows LAN部署使用安装根目录`Run-Strata-Controller.ps1`。Windows PowerShell可执行`& '<安装目录>\Run-Strata-Controller.ps1'`，也可通过已配置的SSH调用；远端运行不依赖WSL。入口只检查并启动对应控制器，不启动模型、领取key或改变现有持有者。端口属于其他程序、控制器配置不匹配时拒绝操作，不接管或停止对方。输出JSON含controller_base_url、responses_base_url和chat_base_url；使用当次结果，不将某台机器的地址／端口复制给其他部署。

模型内部端口、控制器监听端口与调用方访问端口分别由本安装配置决定。现有本机WSL部署为内部8100、控制器8101；RTX 3080 Ti部署为内部8100、控制器监听8000，调用地址`http://192.168.0.4:28000`。调用方继续使用相同API及独占生命周期。

模型启停脚本不作为外部接口。之后的领取、启动、查询、模型请求、停止及归还全部通过返回的controller_base_url完成。控制器在模型停止后继续运行。

### 独占生命周期

1. POST /ownership/acquire领取key。只在模型已停止且无人持有时成功；其他调用方得到409。
2. 后续请求带Authorization: Bearer <key>，包括启动、停止、状态、Chat和Responses。缺失、错误或已归还的key得到403，操作不执行。
3. 用POST /ownership/start指定量化、引擎参数及可选专家profile；生成请求分别指定推理强度和采样/输出参数。
4. POST /ownership/stop只停止模型，仍保留独占权；持有者可以随后重新选择配置启动。
5. POST /ownership/release归还。控制器立即换随机key、撤销原key，然后正常卸载并停止模型。确认无遗留模型进程后才恢复可领取状态。

归还时模型未运行也会换key；旧key不能再次启动、查询或请求。关闭失败则原key仍已撤销，状态为blocked，不发放下一把key；后续领取请求只会先重试已授权的清理，清理成功才可领取。控制器重启保留持有状态，不按时间过期、不因模型停止就自动转交。调用方须在自己的finally清理路径归还并妥善保管凭据；丢失key或控制器状态损坏需要维护者检查，不提供无key强制夺取接口。

### HTTP接口

下表路径均相对于controller_base_url。JSON请求使用Content-Type: application/json。

| 方法与路径 | key | 内容/结果 |
|---|---|---|
| GET /health | 无 | 控制器身份、ownership与available；不表示模型已加载 |
| POST /ownership/acquire | 无 | 请求{}；成功返回一次性key及held状态 |
| POST /ownership/start | 必需 | 指定模型与启动参数，等待模型ready后返回状态及API地址 |
| GET /ownership/status | 必需 | stopped、partial、unloaded或running，以及模型信息 |
| POST /ownership/stop | 必需 | 请求{}；停止模型，独占权仍保留 |
| POST /ownership/release | 必需 | 请求{}；先撤销key，再关闭模型并释放独占权 |
| POST /v1/chat/completions | 必需 | 原生Chat请求，由控制器传给已加载模型 |
| POST /v1/responses | 必需 | Responses请求，适用于Codex自定义provider |

模型端口8100是内部实现，同样检查持有key，不能绕过控制器进行无key推理、load/unload或settings操作。外部调用方统一使用启动入口返回的controller_base_url及其访问端口；本机WSL部署为8101，其他主机可能通过映射端口访问。key是调用方凭据，不进入提示词、版本控制、共享日志或报告；服务端持有状态保存key摘要，内部维护凭据不发给调用方。这是服务API授权，不替代操作系统账户权限；可任意修改安装文件或终止宿主进程的同账户程序仍属于安装维护权限范围。

### 当前维护基线

当前安装Strata v0.1.40.2。每机安装预置分别渲染：RTX3080Ti默认窗口156584、high、思考8192／总输出24576，CPU辅助auto；本机预置仍保持250000窗口及原生成默认，CPU辅助关闭，维护调用可显式使用本机已选156584／high起点。CPU辅助短输入收益只在远端Q2测过，不代表本机或其他量化已验证同等收益。调用方显式提供的强度、预算及环境选项优先，显式low不会被high默认覆盖。

公共维护起点为Q2_0/high/default、temperature0／top_p1／top_k20及spec-min-p0.7，来自既有维护选择；原生预置的spec-min-p仍为0.5，远端尚未单独比较0.5／0.7，不能把固定使用0.7当作其优于0.5的证据。100000压缩阈值按`100000 + 32000 + 24576 + 8 = 156584`派生容量，harness阈值由调用方设置，不由模型预置自动压缩。未传profile_file／profile_save_file时使用默认profile、不保存学习。完整维护覆盖选项见安装`config/maintenance-baseline.json`，省略覆盖则按该机`config/*-prebuilt.json`的安装默认运行；当前基线不代表完整质量或参数最优验收，历史配置不重标。

训练profile没有显示四类review的整体优势，维护基线继续default，不自动训练或采用新profile。当前对照是诊断评分，Spec Readiness均未达原版门槛；所选参数并非所有业务的最优或正式能力通过证明。调用方持有独占key后仍可按自己的任务选择其他量化、推理强度及支持参数。

### 启动参数

POST /ownership/start示例请求体：

```json
{
  "model": "Q2_0",
  "engine_overrides": {"max-context": 156584},
  "request_defaults": {"reasoning_effort": "high", "temperature": 0.0, "top_p": 1.0, "top_k": 20, "max_tokens": 24576, "reasoning_budget_tokens": 8192}
}
```

| 字段 | 支持值与作用 |
|---|---|
| model | Q2_0、IQ2_XS、IQ3_XXS；省略为Q2_0 |
| startup_instructions | 可选布尔值，默认true，按进程加载并追加工程启动提示；false仅用于已明确获准的无追加提示诊断，health回显enabled=false。不删除提示文件，也不改变后续进程默认 |
| loop_prevention_instructions | 可选布尔值，默认true；false仅按进程排除启动提示的`Progress and loop prevention`段，保留任务完成与结束检查要求，health回显enabled=true、loop_prevention_enabled=false及原文件／实际加载文本SHA。不改永久文件或日常默认 |
| fit_max_tokens | 可选布尔值；省略沿用安装配置（当前false）。true使用Strata原生策略，在请求输出预算超过剩余上下文容量时自动缩小输出上限，完整保留输入；输入本身已无回答空间仍拒绝 |
| engine_overrides.prefill | 4096、8192、16384 |
| engine_overrides.max-context | 80000、125000、188000、250000及新公式容量120584、156584、206584、256584；省略沿用安装原始配置250000；当前维护推荐显式指定156584 |
| engine_overrides.kv | int8、fp16、q4_0 |
| engine_overrides.kv-resident | 20480、32768 |
| engine_overrides.pool-workers | 8、12、15、23 |
| engine_overrides.pcie-frac | 0、0.25、0.5 |
| engine_overrides.spec | 2、4 |
| engine_overrides.spec-min-p | 0.3、0.5、0.7 |
| engine_overrides.expert-cache | auto、5000、6000 |
| engine_overrides.vram-reserve-mib | 700、981、1200 |
| engine_overrides.adapt-every / adapt-swaps / adapt-decay | 4、2、8、0 / 96、48、192 / 0.7、0.5、0.9 |
| engine_overrides.mtp-window / pcie-mode | 32768、16384、65536 / auto、direct、dma、kernel |
| engine_overrides.pool-affinity / ple-io / ple-inflight | auto、p-cores、all / direct、mmap / 256、128、512 |
| 布尔引擎开关 | expert-cache-per-layer、expert-cache-cpu-order、no-capture、no-host-worker、no-ple-prefetch、no-prefill-borrow、no-split-rows、no-coupled-draft；只接受JSON布尔值 |
| 其他布尔引擎开关 | shared-late、keep-canonical、no-token-graph、no-fused-gr、no-hit-poke、ple-sync-submit、no-spec-split、gr-fp32-activations；只接受JSON布尔值 |
| engine_overrides.ple-row-cache / short-read | 1048576、0、262144 / 64、0、256 |
| engine_overrides.suffix-draft / mtp-max-t | 3、0、5 / 0、2、4 |
| engine_overrides.prompt-cache / prompt-cache-every / prompt-cache-root | 6、0、2 / 16384、0、8192 / 2048、0、4096 |
| engine_environment | 接受STRATA_HC_SPLIT与STRATA_ADAPT_NOWAIT的0/1、STRATA_SSD_KEEPALIVE的0/100/200、诊断STRATA_BATCH_TRACE=1，以及STRATA_PREFILL_CPU_SHARE的0／"auto"；显式值覆盖该机预置，null清除环境值。CPU辅助远端默认auto、本机关闭；它只分担实际短输入片段的部分专家计算，可能改变输出。SSD值单位为毫秒，不是布尔开关；trace记录引擎管道头，仅在明确诊断时启用 |
| request_defaults | 持有者选择的生成默认值；见下文，未知字段拒绝 |
| profile_file | 安装data/profiles/下已存在的Windows绝对路径，加载专家排序 |
| profile_save_file | 同目录下独立Windows绝对路径，训练阶段在正常退出保存学习profile |

未提供的参数沿用安装配置；这些支持值是实验候选，不都是推荐值。输入须为有效类型，未知字段拒绝。启动时产生临时配置，不改写config中的基线。已运行模型须先通过/ownership/stop停止再改变启动参数。最大窗口候选为80000、125000、188000、250000及新公式容量120584、156584、206584、256584。启动完成时校验引擎实际容量与请求值一致；当前推荐启动容量156584，调用方还须配置自己的`model_context_window=156584`、`model_auto_compact_token_limit=100000`及所选模型catalog的`context_window/max_context_window=156584`；服务不替调用方设置自动压缩。量化对应模型ID如下。生成请求的model必须与当前加载量化的模型ID一致；不一致时桥在转发前返回HTTP409及model_mismatch，不执行推理。省略model则绑定当前已加载模型，未加载／未就绪返回HTTP503及model_not_ready。修改请求model不会自动切换模型，必须先停模，再通过/ownership/start选择目标；新启动重新读取目标预置，显式覆盖参数仍优先。

当前CPU专家池配置不能使用`no-capture=true`；本机250K窗口下`no-prefill-borrow=true`也曾因专家缓存显存不足启动失败。接口接受一个实验值不表示引擎组合可正常启动；失败保留具体诊断，调用方应查询状态并停止后再调整。

| 量化 | 请求model |
|---|---|
| Q2_0 | qwen3.8-flash-next-q2_0 |
| IQ2_XS | qwen3.8-flash-next-iq2_xs |
| IQ3_XXS | qwen3.8-flash-next-iq3_xxs |

### 推理强度与输出

Responses使用reasoning.effort，Chat使用reasoning_effort；每次请求可选择low、medium、high。

| 强度 | 思考token上限 | 默认总输出上限，含思考 |
|---|---:|---:|
| low | 2048 | 8192 |
| medium | 4096 | 16384 |
| high | 8192 | 24576 |

这张表是Responses桥的预算预设；另设max_output_tokens时思考预算还限制到总输出的一半。Chat调用方需同时提供reasoning_budget_tokens和max_tokens，不能假定只传强度标签就得到同一上限。上限不等于实际思考长度。

两个生成接口均可在请求中设置temperature、top_p；Chat还可设置top_k、seed、reasoning_budget_tokens及max_tokens，Responses使用max_output_tokens。输入加输出预算超出窗口会返回400，不静默裁剪。桥只在Responses中执行Hosted网页搜索；shell、文件操作、其他工具及压缩仍由调用方harness执行。

Responses支持原生`additional_tools`及客户端`tool_search`声明、调用和结果重放，可用于Codex发现延迟加载的MCP工具。工具发现与MCP执行仍由调用方harness处理，安装服务不执行这些工具；服务端执行的仍仅为Hosted网页搜索。

### 网页搜索

安装服务在Responses桥内接入Brave Search API。继续使用原有`/v1/responses`、provider地址及独占key；调用方无需安装搜索skill/MCP，无需提供Brave key，也无需启用Codex实验性独立搜索。Codex仍按自身的`web_search`设置声明工具；请求没有搜索工具或`tool_choice=none`时，桥不擅自添加搜索。

支持`web_search`的文本搜索、页面打开/正文读取、页内查找和来源链接；模型决定何时使用，桥执行后继续调用同一个本地模型。仅搜索工具在服务内执行，其他工具调用返回harness。支持`search_context_size`的low/medium/high和`filters.allowed_domains`；近似地理位置、PDF/图片、截图和完整OpenAI搜索工具的其他功能尚不支持，明确报错。

`external_web_access=false`由桥限制为Brave索引模式：只调用Brave搜索API，不抓取结果网站；打开或查找只读取此前搜索返回的索引摘要，并标注`indexed_excerpt=true`。它不是OpenAI缓存服务，也不保证缓存全文。`true`或省略该参数允许从HTTP(S)页面提取正文；URL中显式的私网、本机、保留IP、局域网名称及非文本内容拒绝。Brave本身没有同名参数，这项限制由安装服务执行。

搜索调用使用持有者的同一独占key，归还后不能继续请求或读取该key下的搜索历史。服务在每个搜索/模型步骤重新鉴权；已发出的网络请求不能撤回，但返回后不会继续生成或向失效持有者交付结果。搜索记录私有保存在安装`.state/search/`中，以支持控制器重启后的原生历史重放。维护者在对应独占权归还且不再需要会话恢复后可以清理旧记录。

搜索/网页失败作为真实工具结果反馈给本地模型，不由桥自动重试；模型可以解释失败或选择其他证据。单个Responses请求最多8个模型轮次和8次搜索操作，原始输出预算覆盖所有内部模型轮次。Responses的usage汇总所有模型轮次；未知可选计数省略、不填零，缺失必要总计则明确失败，不返回虚假的完成计量。原始逐轮usage和搜索失败见响应`strata_search`及安装私有计量记录。Brave查询次数属于API请求数，不是模型token，也不能冒充OpenAI搜索计费；页面读取不调用Brave搜索API。

Brave key只由安装维护者配置在`.state/brave-api-key.txt`，文件只含一行key，更新后下一次搜索读取，无需调用方重启。它不会发给本地模型、调用方或目标网站；服务仅向固定Brave API地址发送查询及key，不自动上传整个会话或工程文件。模型生成的查询可能包含当前任务信息。搜索内容仍是不可信证据，来源引用只能证明来源，不能保证网页内容正确。未配置或额度/网络失败会明确反馈。

网络请求使用域名及标准HTTP客户端，遵循系统DNS、代理和网络路由；不自行解析或检查目标IP，不固定IP，不识别VPN/Fake-IP，不使用自建DoH回退。HTTPS由标准客户端正常校验证书；网页逐次重定向检查URL及允许域名，Brave带key的请求不跟随重定向。不携带浏览器cookie或安装凭据，不修改系统DNS、代理、WSL NAT或调用方配置。URL检查不承诺识别DNS或代理背后的最终网络目的地址；网络路由和访问策略由运行环境管理。

持有者也可在启动时提供`request_defaults`，例如`{"temperature":0,"top_p":1,"top_k":20,"reasoning_effort":"high","max_tokens":24576,"reasoning_budget_tokens":8192}`。两个生成接口均使用这些默认值，显式请求值优先；预算仅对指定的同一推理强度生效，不覆盖其他强度的预算预设。每次启动都会重新设置默认值，省略该字段即清空上一轮设置，不改写安装配置。

默认值的允许范围为temperature 0–2、top_p/min_p 0–1、top_k整数1–64、presence_penalty/frequency_penalty −2–2、repetition_penalty 0.5–2、penalty_last_n整数0–65536、max_tokens整数8192–24576、reasoning_budget_tokens整数2048–8192；预算必须同时绑定low/medium/high中的一档。具体参数是否起作用仍取决于引擎路径，例如贪婪生成时top_p/top_k不改变采样，未启用惩罚时penalty_last_n不生效。这些范围是接口许可范围，不表示每个值均已选优。

### 完整Python调用示例

在调用方工程从WSL执行，仅依赖Python标准库。它检查端口、按需启动控制器，领取key并保存在调用方自己的0600凭据文件，然后启动、请求、查询及归还。已有凭据文件时拒绝覆盖，避免丢失仍有效的key。

```python
import json, os, socket, subprocess, urllib.request
from pathlib import Path

installation = Path("/mnt/c/Users/Pello/AppData/Local/Programs/qwen-3.8-flash-next")
route = json.loads(subprocess.check_output(["ip", "-j", "-4", "route", "show", "default"]))
host = next(row["gateway"] for row in route if row.get("gateway"))
base = f"http://{host}:8101"
try:
    with socket.create_connection((host, 8101), timeout=2):
        pass
except OSError:
    info = json.loads(subprocess.check_output(
        ["bash", str(installation / "Run-Strata-Controller.sh")], text=True))
    base = info["controller_base_url"]

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
def request(path, body=None, key=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    data = None if body is None else json.dumps(body).encode()
    with opener.open(urllib.request.Request(base + path, data, headers), timeout=650) as reply:
        return json.load(reply)

health = request("/health")
if not health.get("controller") or health.get("service") != "strata-responses-bridge":
    raise RuntimeError("指定端口不是Strata独占控制器")

credential = Path(".strata-access.json")  # 调用方私有状态，须排除版本控制
fd = os.open(credential, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
key = None
try:
    key = request("/ownership/acquire", {})["key"]
    with os.fdopen(fd, "w") as stream:
        fd = None
        json.dump({"controller_base_url": base, "key": key}, stream)
        stream.flush()
        os.fsync(stream.fileno())
    request("/ownership/start", {"model": "Q2_0"}, key)
    answer = request("/v1/chat/completions", {
        "model": "qwen3.8-flash-next-q2_0",
        "messages": [{"role": "user", "content": "2+2=?"}],
        "reasoning_effort": "low", "reasoning_budget_tokens": 2048,
        "max_tokens": 8192, "temperature": 0, "top_p": 1
    }, key)
    print(answer["choices"][0]["message"]["content"])
    print(request("/ownership/status", key=key)["status"])
finally:
    if fd is not None:
        os.close(fd)
    if key is not None:
        request("/ownership/release", {}, key)  # 失败会保留凭据文件供诊断
    credential.unlink(missing_ok=True)
```

同一调用方可以保留key完成多个review，不必每个模型请求都重新领取；它管理自己的会话和工具。不要让后台任务共享key后各自停止或归还，持有者负责整个调用生命周期。

### Codex接入与网络

调用方设置自定义provider的base_url为http://当次网关:8101/v1，wire_api为responses，model与已加载量化一致，model_reasoning_effort选择low/medium/high。将key通过provider的env_key所指环境变量提供，只给该harness，不写入共享配置或提示词。工程自行管理CODEX_HOME、catalog、MCP、沙箱、审批和会话；安装项目不提供Codex启动器。

安装`config/model-catalog.json`提供三种量化的Codex模型信息，如实声明文本搜索及本地guardian模型。使用时在**启动app-server时**传入`model_catalog_json`的实际WSL路径；仅在线程创建时提供可能不能更新已加载的模型目录。各条目的`auto_review_model_override`指向自身模型名；是否启用auto_review及权限仍由调用方决定。原生guardian的推理强度为low，本服务通常映射为2048推理预算/8192输出预算；如持有者指定相同强度的默认预算，会按请求优先规则生效。预算不等于实际推理长度，计量不足时不推算后者。

WSL保持NAT，不使用portproxy、隧道或端口转发。服务绑定Windows WSL虚拟网卡IPv4，Responses控制器还核对客户端IP。防火墙一次性设置由安装维护者从WSL执行maintenance/Setup-WSL-Network.sh，会请求Windows管理员授权，仅放行指定Python、8100/8101、WSL网卡和同网段。调用方不承担这项安装操作。存在HTTP代理时，对当前宿主设置NO_PROXY/no_proxy或显式直连，示例已经绕过代理。

HTTP409表示当前不可领取/已有持有者，不应强行重启控制器或停止模型；403表示key无效；503表示服务或清理失败，查看返回信息和安装logs/wsl-server.log、logs/wsl-bridge.log。等待与重试由调用方决定，不默默重做可能有副作用的请求。

Responses流在HTTP200后仍可能失败；桥以`response.failed`结束，`response.status=failed`，`response.error`包含具体原因（例如未声明工具、上游超时或生成失败），不发送虚假的`response.completed`。HTTP状态本身不能作为请求成功的依据，部分输出也不是完整交付。调用方应按终态处理，避免仅看到EOF后盲目重试可能已执行的工具。安装`logs/wsl-bridge.log`记录请求编号、错误类别、异常类型及工具名，不记录提示词或工具参数；完整trace仅在显式配置时使用。

## 已观察到的执行异常

模型可能在任务尚未完成时提前结束工作，也可能陷入重复步骤的循环。

2026-10-06的Commit Audit推理强度测量中，Strata v0.1.38、Qwen3.8-Flash-Next Q2_0、low、default及100000压缩阈值／156584窗口的第1、2、4次初审，在自动上下文压缩请求中返回了该请求未声明的`exec_command`工具调用。桥拒绝了这个调用，被拒绝的调用没有执行；流式接口可能已返回HTTP200，随后以`response.failed`结束，错误信息为`[invalid_response] Model returned unknown tool: exec_command`。本批Codex 0.160.0因此结束当前Reviewer回合，报告未交付。这是当前条件下观察到的模型工具响应错误，不是shell命令执行后的失败，也不能仅凭“stream disconnected”将其判为网络断开；尚未确定在其他版本、量化、强度或业务中的发生率。

2026-10-04，在Strata v0.1.38、Qwen3.8-Flash-Next Q2_0、medium、独立训练review profile的一次Commit Audit中，模型连续98次执行同一条未生效的JSON修复命令，约35分钟内同样5行语法错误持续存在。工具返回成功不代表任务取得进展。第55分钟的整理返回提醒已进入原生会话；模型随后修复了JSON语法，但又重复读取源码，未在截止前完成交付。第60分钟被原生中断，最终状态为incomplete。原超时记录保留。用户后来授权另存同场景重跑，报告正常交付；该重跑未覆盖或删除首轮失败。

这说明长任务可能陷入重复操作和长期停滞，影响调用方进度；尚未确定成因或发生率，不能据此断言所有量化、强度、profile或任务都会如此，也不能认定训练profile是原因。本轮对照后已决定不采用该训练profile，继续default。

安装服务在模型进程启动时读取安装根目录下的`config/prompts/startup-instructions.txt`，将其作为系统提示词的一部分，追加到每次请求的调用方指令中。全文可直接查看该文件。它要求模型核验真实结果、识别连续重复且无进展的步骤、调整方法或说明阻碍，并在证据足够时整理交付。另有两项独立要求：任务及必要交付物未完成时继续执行，不以计划或进度说明代替交付；准备结束时逐项核对实际完成情况，所需报告须写到指定位置并验证内容，仍有可推进的工作则继续做。明确停止指令、时限及已验证阻塞仍须遵守，未完成时明确报告原因和真实部分结果。Chat、Responses及服务内MCP后续轮次均使用该提示词，调用方无需添加相同指令。新增两项要求的行为收益尚未实测；提示词不能保证模型不早停或不重复，任务是否完成仍应以真实交付物为准。

启用上述提示词后，同版本Q2_0、medium、默认profile的第二次Commit Audit仍执行同一失败探测命令18次，并反复读取同一角色规则21次；相同命令的结果正文均未变化。该实例最终于49.73分钟正常完成，未触发中断。这些次数是工具调用次数，包含同批提交，不等于独立推理轮次。默认profile也可能出现这种停滞，提示词不能保证避免循环。同配置默认profile的第三次Commit Audit还多次用不同命令检查同一118行报告并声称通过，原版生成仍拒绝87处文件证据格式和一个治理来源；经两次同线程修订后于34.99分钟完成。模型自行检查成功不能代替调用方既有的正式结果校验。文件在每次模型进程启动时固定；修改文件不会改变已启动实例，下一次模型启动才生效。`GET /ownership/status`的`native_health.startup_instructions`返回加载文件的相对路径和SHA-256，便于核对。完整模型输入还包含调用方指令、任务、工具及历史，不等同于这个固定追加文件。

另一次150K/206584上下文观测在8.8分钟后正常结束，只返回继续核对材料的进度说明，没有写入所需报告：共32次工具调用，其中10次是参数完全相同的额外重复。没有观察到超时、中断、连接故障或容量拒绝；最后达到4096-token思考预算后仍生成了20 token进度说明，不能据此认定思考预算强制结束整个任务。更深层模型或停止原因尚未确定。正常结束、工具退出码0或模型声称完成，都不能代替检查实际交付物。

同版本Q2_0/medium/default的64K压缩阈值测量中，也出现过正常结束却未交付报告：实例运行8.7分钟、成功压缩2次后，只返回继续读取指令的说明，报告仍为空；没有流错误、超时或容量拒绝。另一个完整实例反复复核已写报告，整个合并任务耗时57.7分钟，包含29次完全相同参数的额外工具调用。基础提示不能保证消除这些行为；调用方仍应按自己的任务合同核对实际交付，不能将HTTP成功或普通结束当成任务完成。

## 调用方动态防重复建议

建议ARW、Codex或其他调用方在自己的harness中观察实际工具结果与交付状态，按观测事实动态反馈。安装服务提供模型API，客户端shell、文件工具及任务是否完成由调用方管理；本节不是服务内置守卫开关。仅靠基础提示或命令全文相同的检测不能保证避免循环。

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
| 普通对话、文档/代码review、工具调用、训练等模型请求 | `config/prompts/startup-instructions.txt`：核验结果、识别无进展重复并调整方法、完成任务及结束前自检 | 模型服务自动追加；外部调用方无需重复加入 |
| harness要压缩历史、生成后续任务摘要 | `config/prompts/compact-prompt.txt`：只生成摘要、禁止继续执行任务或调用工具、保留约束和行动状态 | 本工程活跃WSL/ARW入口自动组合；外部调用方须在自己的harness配置 |
| 场景另有角色、任务或摘要要求 | 场景自己的提示词 | 调用方保留并追加为相应基础提示的补充；不能替代基础提示 |
| 希望保留harness原生摘要要求 | 自己harness版本的默认摘要提示 | 将其作为基础压缩提示的补充；本工程使用经实际原生手动压缩路径核对的Codex 0.160.1快照，调用方无需复制维护资源 |

启动基础指令在模型进程启动时读取，应用于每次服务端模型请求，调用方自己的指令仍保留。`GET /ownership/status`的`native_health.startup_instructions`给出加载路径和SHA；修改后须下一次模型启动才生效。

压缩由调用方的harness管理，桥没有可靠的请求压缩标识，因此不会自动注入`compact_prompt.txt`。外部调用方在配置压缩时，读取该基础文件，将自己场景的摘要要求作为补充，保存组合文件，再通过Codex的`experimental_compact_prompt_file`等配置指向组合文件；只设置基础文件也可，不能用自定义摘要提示把基础指令覆盖掉。不要把“只输出摘要”加入普通review提示，也不要将基础文件同时当作自己的补充而重复拼接。服务不会修改调用方或全局Codex配置。

原生默认摘要快照不是基础提示词，也不是安装目录的公共配置。本工程将0.160.1实际原生手动压缩请求的快照保存在版本化的工具资源目录，不部署到安装目录的`config/`；调用方只需使用安装目录的基础文件，并按自己的harness和场景补充摘要要求。升级Codex后需重新核对，不能将旧快照视为新版本默认。
