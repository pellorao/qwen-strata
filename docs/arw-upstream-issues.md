# ARW 上游缺陷记录

本文件记录在本工程使用 ARW 时发现的上游缺陷，由用户定期转交 ARW 修复。每条写明版本、现象、证据、影响和建议；本工程的临时绕行措施另行注明，不代替上游修复。上游确认修复后，标注修复版本并移到"已修复"一节。

## 未修复

### 1. Reviewer 被要求用命令发送中途消息，但原版权限不允许命令联网

- **版本**：ARW 760007c（`benchmarks/reviewer-suite-v1/source-snapshots/current/`）。
- **现象**：`docs/agents/reviewer.md` 要求 Reviewer"核实问题后先写入绑定报告，再通过 `arw background-agent` 的 `send_message` 及时通知"。这个命令要连接本机 127.0.0.1 的管理进程端口。原版 Reviewer 权限是 `:read-only` 加显式读写路径（`lib/reviewer-runtime/reviewer-native-policy.mjs`），命令没有网络权限；规格（`docs/specs/agent-repository-workflow/spec.md` 管理进程一节）也写明控制连接"不决定 Agent 的模型网络权限"。所以不提权的 `send_message` 必然失败（`connect EPERM 127.0.0.1:<port>`）。要发出消息只能申请提权，每次都会触发一个 auto_review guardian 审批线程。
- **证据**：2026-10-11 rtx3080ti 的 Commit Audit 运行中，IQ3_XXS 一个实例两次调用 `send_message`，第二次报 `connect EPERM 127.0.0.1:34787`，消息没有送达。Q2_0 一个实例改为提权调用，两次触发 guardian，额外消耗约 26.9K 未缓存输入和 2K 输出。
- **影响**：Role 要求的通知路径在默认权限下走不通。模型为完成这项要求会去提权、尝试其他 `arw` 操作，增加 token、时间和违规风险。在 Reviewer Capability 验证和 benchmark 中，中途消息本来就没有作用（最终结果由运行层通过 `completion` 交付，评分不使用中途消息），却仍然诱发这些行为。
- **建议**：能力验证和 benchmark 的交接不再要求、也不鼓励中途消息；普通审核如果保留这条要求，应给出不需要命令联网的通道，或在 Role 中写明需要提权并说明代价。
- **本工程临时措施**：能力测量交接末尾追加说明（不发送中途消息、不需要运行标识、禁止查询环境变量和平台身份），见 `docs/plan.md`。

### 2. Role 没有说明运行标识的取得方式，诱发环境身份查询

- **版本**：ARW 760007c。
- **现象**：`docs/agents/reviewer.md` 要求"使用运行环境提供的 `ARW_BACKGROUND_AGENT_RUN_ID` 作为准确 `runId`"，没有说明它是环境变量，也没有给出读取方式。运行标识只通过 `lib/background-agent/codex-app-server.mjs` 写入的 `shell_environment_policy.set` 提供。会话检查规范（`docs/agents/reviewer-capability-session-inspection.md`）允许使用这个变量，但把"查询模型或平台环境身份"列为违规，任何允许清单外的观察都会使整批失败。
- **证据**：2026-10-11 rtx3080ti 的 Commit Audit 运行中，IQ3_XXS 和 Q2_0 各有 1 个实例为找运行标识执行了 `env | grep`，输出里有 `CODEX_HOME`、`CODEX_PERMISSION_PROFILE`、运行时文件路径和模型端点（没有凭据）。两批都按规范判为正式验收失败。
- **影响**：Role 的要求与检查规范互相冲突。模型按 Role 去取运行标识时，最自然的做法就是宽泛查询环境变量，而这正是检查规范判失败的行为。
- **建议**：与第 1 条一起处理。若保留中途消息，在 Role 中写明"直接读取环境变量 `ARW_BACKGROUND_AGENT_RUN_ID`，不得枚举其他环境变量"；更好的做法是由运行层把运行标识注入 `arw` 命令，Reviewer 不必知道它。

## 本工程对 ARW 的修改（建议上游同样修改）

本工程按自己当前的 Strata 工作方式修改了冻结的 ARW。修改以补丁形式登记在 `benchmarks/reviewer-suite-v1/source-snapshots/current/manifest.json` 的 `patches` 里，展开冻结源码时打上，并校验打完后的 SHA。这些不是 ARW 的缺陷，而是本工程升级了 Strata 的接入方式，建议 ARW 适配。

### A. Strata provider 改用常驻前端接口（`arw-patches/strata-frontend-protocol.patch`）

- **版本**：ARW 760007c，`lib/background-agent/strata-driver.mjs`、`strata-work-policy.mjs`、`strata-models.mjs`、`model-catalog.mjs`、`manager.mjs`，以及对应测试 `tests/background-agent/strata-driver.test.mjs`、`model-catalog.test.mjs`、`host.test.mjs`。
- **原做法**：每次连接都运行安装目录的 `Run-Strata-Controller.sh` 启动控制进程，用 `/ownership/acquire|status|start|stop|release` 管理独占和模型；启动模型时写死 `spec-min-p 0.7`、`max-context 156584` 和 temperature 0 / top_p 1 / top_k 20；`strata-models.mjs` 的 `STRATA_CONTEXT_WINDOW = 156584` 同时写进模型目录和任务设置，压缩阈值写死为 100000；压缩提示读取 `config/compact_prompt.txt`。
- **本工程现状**：安装目录有一个常驻前端，地址写在 `config/frontend.json`（`listen_address`、`port`），接口为 `POST /lease/acquire`、`GET /model/status`、`POST /model/start`、`POST /model/stop`、`POST /lease/release`，模型请求走 `/strata/v1`。引擎参数和请求默认值由安装目录按"主机 + 量化"实测选定（例如 rtx3080ti 的 IQ3_XXS 用 `spec-min-p 0.9`）。公开的 `/model/start` 只接受 `{model, context_window}`，其他字段一律拒绝；`context_window` 必须是安装目录 `config/deployment.json` 里该量化 `context_tiers` 发布的档位之一（每档带 `context_window` 和 `auto_compact_token_limit`，第一档为默认）。调用方因此只选三项：模型、推理强度（随请求）、上下文档位。压缩提示位于 `config/prompts/compact-prompt.txt`。旧的控制脚本和 `/ownership/*` 已经删除。
- **修改**：
  1. `connect()` 不再运行脚本，改为读取 `config/frontend.json`，得到控制地址，模型地址为 `<控制地址>/strata/v1`。
  2. 五个操作改为上面的新路径；解析新的返回字段（`acquire` 返回 `key` 与 `lease: "held"`，`release` 返回 `lease: "free"`）；前端把加载中的模型报告为 `starting`，按原 `partial` 处理。
  3. `start` 只传 `{model: <量化名>, context_window: <档位窗口>}`，不再写死引擎参数和采样参数。
  4. 去掉 `STRATA_CONTEXT_WINDOW` 和固定的 100000。新增 `readStrataContextTier`：读取安装目录 `config/deployment.json` 的 `context_tiers`，按 provider 配置的 `contextWindow` 选档（未配置用第一档），档位不存在时报错。模型启动窗口、模型目录里的 `context_window` / `max_context_window`、任务设置里的 `model_context_window` 和 `model_auto_compact_token_limit` 都取自同一档位。
  5. `models.custom.json` 的 Strata provider 新增可选字段 `contextWindow`（正整数，只允许 Strata driver）。模型目录先校验 provider，再用校验后的 provider 套档位。
  6. 压缩提示路径改为 `config/prompts/compact-prompt.txt`。
  7. 同步更新 ARW 自带的 driver、模型目录和 host 测试（旧 driver 测试仍按已删除的控制脚本断言；host 测试的夹具改为新压缩提示路径并提供档位）。改动后 `tests/background-agent/` 与 `tests/reviewer-runtime/` 只剩 1 个与本补丁无关、未打补丁时同样失败的终端标题测试。
- **建议**：ARW 按上述新接口适配；不要在 ARW 中写死引擎参数、窗口或压缩阈值，由安装方的每机每量化默认值和发布档位决定。

### C. 嵌入式宿主传入 `nativeSessions` 时，管理器读不到 provider（本工程运行层已绕开，未改 ARW）

- **版本**：ARW 760007c，`lib/arw-background-agent-host.mjs` 的 `createBackgroundAgentHost`。
- **现象**：调用方传入 `nativeSessions` 而没有传 `modelCatalog` 时，宿主既不创建共享模型目录，也不设 Strata driver 工厂；管理器的 `providerConfigurations()` 因此为空，`model_owner = "arw"` 的任务不会领 key、不会启动模型，模型请求直接被前端以 403（缺少有效 key）拒绝。本工程 2026-10-11 的 F3 试跑即因此失败。
- **本工程处理**：运行层 `tools/reviewer/arw_native_setup.mjs` 按 ARW 宿主自己的做法，创建一个共享目录（`CODEX_HOME` 指向隔离的 codex-home），同时传给 App Server 和宿主；provider 写进 codex-home 的 `models.custom.json`（ARW 只从这里读 provider）；daemon 就绪时回报 ARW 实际读到的 provider，`arw_measure` 核对一致后才派发。
- **建议**：宿主在收到 `nativeSessions` 时也应接受或创建 `modelCatalog`，或在缺少目录而 provider 需要 driver 时明确报错，而不是静默丢掉 provider。

### D. 原线程已卸载时，followup_task 用新交接的文件系统检查原报告，判定"报告缺失"并无限接续（未修复，待用户决定是否打补丁）

- **版本**：ARW 760007c，`lib/reviewer-runtime/reviewer-runtime.mjs` 的 `followup`。
- **现象**：App Server 以 `thread_unload_delay_secs=0` 启动，Reviewer 回合一结束原线程就卸载。此时发 `followup_task`，若新交接的 `cwd` 与原任务不同（本工程 Spec Readiness 合并实例：runtime-migration 后在同一线程接续 artifact-promotion），`followup` 重开条目时把**新交接**的 `reviewFilesystem`（根为新 `cwd`）与**原记录**（原 `cwd`、原报告路径）放在一起，接受任务前的 `refresh` 在错误的根下找原报告，判定缺失，于是走原生接续：发"报告缺失"指示、开新回合，`followup_task` 本身返回 `reviewer-busy`。之后每次刷新都用同一错误作用域，Reviewer 每回合都重写报告并回答 `ready`，ARW 仍判缺失，直到第 10 次早退暂停。2026-10-11 F3 第二次试跑：runtime-migration 首回合 09:13:57 回答 ready，驱动看到 completion=ready 并立即 followup；09:14:01 起连续 10 次接续，报告文件始终存在。
- **依据**：代码路径（`followup` 中 `managementState()==='exited'` 时以 `checkReportBinding(handoff,…)` 的结果建条目，接受后才赋值 `held.reviewFilesystem`）与会话记录、报告文件 mtime 吻合；未单独写复现测试。
- **建议修改**：重开条目时用原记录建文件系统（`checkReportBinding(previous, false, recoveryPath)`），新交接的文件系统只在接受任务后替换，与条目仍在内存时的路径一致。

### B. 能力测量中不要求每实例冷启动

- 本工程以前在每个实例之间停模型、冷启动，以便按引擎日志分段计量。这是本工程自己的旧做法，ARW 本身不这样做（它在整个共享 App Server 期间持有独占，关闭时才归还，也不停模型）。现在本工程也不再停模型，引擎日志按派发时刻分段。
- 实例之间只会复用 Strata 的精确前缀缓存（系统提示和工具列表等逐 token 相同的开头），模型输入不变，不会看到上一个实例的内容。
- **建议**：ARW 的能力验证和 benchmark 规则如果要求冷启动，应改为只要求"不复用上一个实例的上下文"，不要求停模型。

## 已修复

（暂无）
