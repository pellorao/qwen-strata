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

- **版本**：ARW 760007c，`lib/background-agent/strata-driver.mjs`、`lib/background-agent/strata-work-policy.mjs`。
- **原做法**：每次连接都运行安装目录的 `Run-Strata-Controller.sh` 启动控制进程，用 `/ownership/acquire|status|start|stop|release` 管理独占和模型；启动模型时写死 `spec-min-p 0.7`、`max-context 156584` 和 temperature 0 / top_p 1 / top_k 20；压缩提示读取 `config/compact_prompt.txt`。
- **本工程现状**：安装目录有一个常驻前端，地址写在 `config/frontend.json`（`listen_address`、`port`），接口为 `POST /lease/acquire`、`GET /model/status`、`POST /model/start`、`POST /model/stop`、`POST /lease/release`，模型请求走 `/strata/v1`。引擎参数和请求默认值由安装目录按"主机 + 量化"实测选定（例如 rtx3080ti 的 IQ3_XXS 用 `spec-min-p 0.9`），调用方只需给出量化名。压缩提示位于 `config/prompts/compact-prompt.txt`。旧的控制脚本和 `/ownership/*` 已经删除。
- **修改**：
  1. `connect()` 不再运行脚本，改为读取 `config/frontend.json`，得到控制地址，模型地址为 `<控制地址>/strata/v1`。
  2. 五个操作改为上面的新路径；解析新的返回字段（`acquire` 返回 `key` 与 `lease: "held"`，`release` 返回 `lease: "free"`）；前端把加载中的模型报告为 `starting`，按原 `partial` 处理。
  3. `start` 只传 `{model: <量化名>}`，不再写死引擎参数和采样参数。
  4. 压缩提示路径改为 `config/prompts/compact-prompt.txt`。
- **建议**：ARW 按上述新接口适配；不要在 ARW 中写死引擎参数，由安装方的每机每量化默认值决定。补丁只改了实现，没有改 ARW 自带的 driver 测试，上游适配时需要同步更新这些测试。

### B. 能力测量中不要求每实例冷启动

- 本工程以前在每个实例之间停模型、冷启动，以便按引擎日志分段计量。这是本工程自己的旧做法，ARW 本身不这样做（它在整个共享 App Server 期间持有独占，关闭时才归还，也不停模型）。现在本工程也不再停模型，引擎日志按派发时刻分段。
- 实例之间只会复用 Strata 的精确前缀缓存（系统提示和工具列表等逐 token 相同的开头），模型输入不变，不会看到上一个实例的内容。
- **建议**：ARW 的能力验证和 benchmark 规则如果要求冷启动，应改为只要求"不复用上一个实例的上下文"，不要求停模型。

## 已修复

（暂无）
