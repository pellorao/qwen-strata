# 前端运行与维护

调用方的接口、启动参数和示例见[调用手册](installation-directory-readme.md)。本文说明前端的结构、一次性安装、部署和升级。

## 结构

| 组件 | 位置 | 作用 |
|---|---|---|
| 前端 | `src/frontend.py`，监听 `config/frontend.json` 的地址和端口（rtx3080ti 为 `192.168.60.212:8000`） | 独占租约、模型启停、`/strata/*` 转发、客户端地址检查 |
| 模型进程管理 | `src/model_process.py` | 校验启动参数，生成临时运行配置（`.tmp/model/`），启动并停止原生服务 |
| 原生服务 | `src/native_service.py` 包装 Strata `serve`，只监听 `127.0.0.1:8100` | 加载基础提示，提供 Chat / Responses / Messages；内部 key 每次启动随机生成，经环境变量 `STRATA_API_KEY` 传入 |

- 推理全部在 Windows 原生进程中运行。WSL 保持 NAT，不做端口转发；WSL 内的调用方直接访问 `192.168.60.212:8000`。
- 客户端允许列表按本机各网卡子网动态计算（每 60 秒刷新），WSL 虚拟网卡子网每次开机变化也能自动覆盖。
- 租约只在内存中。前端启动时会先停掉遗留的模型进程，因此重启前端等于强制回收。租约本身没有超时回收。
- 模型跨租约驻留：归还租约不停模型，下一个租约用相同参数启动时直接复用（省掉约 16 秒加载和 36 GB SSD 读取）。参数比较的是校验后的完整运行配置的 SHA。没有租约的模型空闲 `IDLE_STOP_MINUTES`（30）分钟后停止，0 表示不停。代价是空闲期间一直占用约 39 GB 内存和约 11 GB 显存；上一个调用方的 prompt cache 也留在进程中。
- 测量工具经 `tools/ops/controller_client.py` 领租约后，若发现模型在运行就先停掉，保证每个测量实例从冷加载开始；部署和升级同样先停模型。ARW 持有模型的批次（`selection.model_owner = "arw"`）由 `arw_measure` 在交给 ARW 之前做同样的事：领租约、停常驻模型、核实已停后归还，ARW 再自己领租约启动，所以每批从冷加载开始（批内实例之间不停模型）。
- 采样默认值写入原生运行配置的 `sampling`；前端只为 Chat 和 Responses 补推理强度、思考预算和输出上限。
- 流式 Responses／Messages 回答撞到输出上限时，`src/output_limit.py` 在前端内部带服务端通知重试一次，调用方看不到截断的回答；没撞上限的流逐字节原样转发。做法和边界见调用手册「撞到输出上限时的内部重试」。
- 原生服务丢弃 `web_search` 等服务端托管工具。前端 `src/hosted_search.py` 为 Responses 流式请求补上，经 `src/brave_search.py` 调用 Brave；搜索结果按随机 id 存在前端内存，跨租约保留以便 resume 回放，超过上限淘汰最旧的，前端重启清空。
- 日志 `logs/frontend.log` 每行带本地时间（毫秒），用于计算工作时间。

## 一次性安装（需要管理员授权）

首次部署后，在 Windows 上以安装用户身份运行一次：

```powershell
& 'C:\Users\pello\AppData\Local\Programs\qwen-3.8-flash-next\maintenance\Install-Frontend.ps1'
```

脚本会请求一次 UAC，然后：
- 删除旧规则 `QwenStrata-WSL-API`、`QwenStrata-Native-8000`，创建 `QwenStrata-Frontend`：入站 TCP，本地地址和端口取自 `config/frontend.json`，远端限 `LocalSubnet`。
- 给当前用户授予"Lock pages in memory"（`SeLockMemoryPrivilege`），引擎的专家区要用它分配大页；重新登录后才生效。
- 注册计划任务 `QwenStrataFrontend`：当前用户登录时用安装 venv 的 `pythonw.exe` 运行前端，无运行时限，不重复启动，以最高权限、Normal 优先级运行；并立即启动一次。

前端和它启动的引擎以管理员令牌运行。原因是受限令牌会去掉 `SeLockMemoryPrivilege`，而上游实测计划任务默认的 Below normal 优先级会使专家加载慢约 24 倍。前端只接受本机子网，文件 MCP 只读。地址或端口变化时重新运行该脚本。

## 部署

从维护工程执行：

```bash
python3 -m tools.ops.deploy --host rtx3080ti
```

流程：
1. 前端在运行时，领取租约（已被持有则中止，不抢占），确认模型已停，再调用 `/admin/shutdown` 关闭前端。
2. 备份将被替换或删除的文件到工程 `.tmp/maintenance-backups/deploy-*`。
3. 写入前端、模型管理、原生服务包装、基础提示、模型 catalog、每机渲染的模型预置和配置、调用手册、`maintenance/Install-Frontend.ps1`。
4. 删除旧控制器的入口、协议桥、网络脚本、`config/service.json` 和 `.state/`。
5. 逐文件回读 SHA，写 `deployment-manifest.json`。
6. `schtasks /run` 重新启动前端并等待 `/health`。计划任务不存在时提示先运行 `Install-Frontend.ps1`。

`--docs-only` 只替换调用手册，不停前端。部署不改模型权重、引擎、私有依赖或 `config/installed-release.json`。

## 升级 Strata

```bash
python3 -m tools.ops.upgrade_release --host rtx3080ti --metadata <发布元数据> --source <源码 ZIP> --engine <引擎 ZIP> --output <回执>
```

与部署相同：先经前端租约关闭前端，替换期间没有任何调用方能启动模型；完成后重新启动前端。`--rollback <备份目录>` 回滚。校验内容和周期流程见[安装与维护](installation.md#升级部署与恢复)。

## 日志与故障

安装目录 `logs/frontend.log` 记录前端请求和错误，`logs/model-server.log` 记录原生服务输出，`logs/<量化>-prebuilt-engine.log` 是引擎日志（测量用的 token 计数从这里读取）。

- 前端无响应：在 Windows 任务计划程序中查看 `QwenStrataFrontend` 的上次运行结果，或手动运行该任务。
- 租约卡住（测量工具的持有者已退出，例如 WSL 崩溃或驱动被杀）：工具领租约时会把 key 留在运行目录的 `controller/controller-key.private.json`。用 `python3 -m tools.ops.release_orphan_lease <该目录>` 完成归还：
  - 它停模型、还 key、删除 key 文件，全程不打印 key；
  - 如果前端已不接受这个 key（租约已被别人持有，或已经归还），它不做任何改动，报告后以状态 1 退出，不抢占。
- 找不到 key 文件时，只能重启前端，这会停止正在运行的模型。
- 采样驱动在每组开始前读取 Windows 剩余提交内存（`Win32_OperatingSystem.FreeVirtualMemory`）。低于计划参数 `min_free_commit_gib`（默认 8）时暂停，每 30 秒重查一次；暂停超过 10 分钟按故障中止，停模型、还 key。2026-10-12 的 WSL 崩溃就是提交内存耗尽造成的。
- 模型停止失败：前端返回 503；按日志排查后重启前端。
