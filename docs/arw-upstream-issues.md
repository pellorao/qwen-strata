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

## 已修复

（暂无）
