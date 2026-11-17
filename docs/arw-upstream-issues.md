# ARW 上游缺陷记录

本文件记录在本工程使用 ARW 时发现的上游缺陷，由用户定期转交 ARW 修复。每条写明版本、现象、证据、影响和建议；本工程的临时绕行措施另行注明，不代替上游修复。上游确认修复后，标注修复版本并移到"已修复"一节。

## 未修复

### 1. Reviewer 被要求用命令发送中途消息，但原版权限不允许命令联网

- **版本**：ARW 760007c（`benchmarks/reviewer-suite-v1/source-snapshots/current/`）。
- **现象**：`docs/agents/reviewer.md` 要求 Reviewer"核实问题后先写入绑定报告，再通过 `arw background-agent` 的 `send_message` 及时通知"。这个命令要连接本机 127.0.0.1 的管理进程端口。原版 Reviewer 权限是 `:read-only` 加显式读写路径（`lib/reviewer-runtime/reviewer-native-policy.mjs`），命令没有网络权限；规格（`docs/specs/agent-repository-workflow/spec.md` 管理进程一节）也写明控制连接"不决定 Agent 的模型网络权限"。所以不提权的 `send_message` 必然失败（`connect EPERM 127.0.0.1:<port>`）。要发出消息只能申请提权，每次都会触发一个 auto_review guardian 审批线程。
- **证据**：2026-10-11 rtx3080ti 的 Commit Audit 运行中，IQ3_XXS 一个实例两次调用 `send_message`，第二次报 `connect EPERM 127.0.0.1:34787`，消息没有送达。Q2_0 一个实例改为提权调用，两次触发 guardian，额外消耗约 26.9K 未缓存输入和 2K 输出。
- **影响**：Role 要求的通知路径在默认权限下走不通。模型为完成这项要求会去提权、尝试其他 `arw` 操作，增加 token、时间和违规风险。在 Reviewer Capability 验证和 benchmark 中，中途消息本来就没有作用（最终结果由运行层通过 `completion` 交付，评分不使用中途消息），却仍然诱发这些行为。
- **建议**：能力验证和 benchmark 的交接不再要求、也不鼓励中途消息；普通审核如果保留这条要求，应给出不需要命令联网的通道，或在 Role 中写明需要提权并说明代价。
- **本工程临时措施**：能力测量交接末尾追加说明（不发送中途消息、不需要运行标识、禁止查询环境变量和平台身份），见 [多模型 benchmark 计划](../benchmarks/multi-model-v1/plan.md)。

### 2. Role 没有说明运行标识的取得方式，诱发环境身份查询

- **版本**：ARW 760007c。
- **现象**：`docs/agents/reviewer.md` 要求"使用运行环境提供的 `ARW_BACKGROUND_AGENT_RUN_ID` 作为准确 `runId`"，没有说明它是环境变量，也没有给出读取方式。运行标识只通过 `lib/background-agent/codex-app-server.mjs` 写入的 `shell_environment_policy.set` 提供。会话检查规范（`docs/agents/reviewer-capability-session-inspection.md`）允许使用这个变量，但把"查询模型或平台环境身份"列为违规，任何允许清单外的观察都会使整批失败。
- **证据**：2026-10-11 rtx3080ti 的 Commit Audit 运行中，IQ3_XXS 和 Q2_0 各有 1 个实例为找运行标识执行了 `env | grep`，输出里有 `CODEX_HOME`、`CODEX_PERMISSION_PROFILE`、运行时文件路径和模型端点（没有凭据）。两批都按规范判为正式验收失败。
- **影响**：Role 的要求与检查规范互相冲突。模型按 Role 去取运行标识时，最自然的做法就是宽泛查询环境变量，而这正是检查规范判失败的行为。
- **建议**：与第 1 条一起处理。若保留中途消息，在 Role 中写明"直接读取环境变量 `ARW_BACKGROUND_AGENT_RUN_ID`，不得枚举其他环境变量"；更好的做法是由运行层把运行标识注入 `arw` 命令，Reviewer 不必知道它。

### 3. 报告目录"只能有绑定报告"的检查与 Codex 沙箱挂载点竞态

- **版本**：ARW 760007c。
- **现象**：`lib/reviewer-runtime/reviewer-runtime.mjs` 的 `checkReportBinding` 非递归列出报告目录，只要有绑定报告以外的条目就报 `report-binding-invalid`（"The Reviewer report directory must contain only its exact bound report."）。报告目录同时是 Reviewer 的可写根，Codex 沙箱会在可写根内为受保护名称建空的挂载点目录（`.agents`、`.aws`、`.codex`、`.git`），建立和清理时机由沙箱决定。如果检查时挂载点还没被清理，Reviewer 已经完成的审核会被判为绑定失败。
- **证据**：2026-10-12 rtx3080ti F6 commit-audit-a 实例 3：Reviewer 已返回 ready，`wait_agent` 报上述错误；报告目录里有派发时刻（07:57）创建的四个空目录，Reviewer 命令没有创建它们。同批实例 2 的同一目录在 07:57 有增删，检查时已清理，所以没有出错。处理是停掉该 agent，单独补跑 1 次（commit-audit-c）。
- **影响**：偶发，与 Reviewer 行为无关，但会让已完成的实例失败，还会让批次缺少重复、拿不到原版批分。
- **建议**：检查时忽略沙箱的受保护名称挂载点（空目录），或者把报告目录与可写根分开，让沙箱挂载点不落在报告目录里。

### 4. Markdown 证据解析把反引号里的时刻当作 `路径:行` 定位

- **版本**：ARW 760007c（Code Spec Reviewer，`markdown-findings` 评分路径）。
- **现象**：`lib/release/reviewer-capability-conformance.mjs` 的 Markdown 报告解析把 finding 正文中反引号内形如 `a:b` 的片段都当作证据定位。`` `13:45` `` 被读成文件 `13` 的第 45 行，`` `startAt: 12:00` ``、`` `11:00 <= 11:00` `` 同理；随后第 2638 行按冻结源核对，记 `review-evidence-invalid`（"Markdown evidence is outside the frozen source."），整个实例分数 ×0.9。
- **证据**：2026-10-13 rtx3080ti Code Spec v2，IQ3_XXS ×10 中有 7 次被 ×0.9，其中全部 `review-evidence-invalid` 都来自这一点（另有 3 次 `review-format-invalid`），没有一条是真实的代码或 spec 引用错误；场景本身是预约时间规则，引用时刻是正常写法。报告见 `reports/v0.1.42/code-spec-v2/summary.md`。
- **影响**：罚的是写作习惯，不是证据错误；在时间、端口、比例等含冒号内容常见的场景里，会给分数加入与审查能力无关的噪声，也会把调参引向"别把时刻写进反引号"。
- **建议**：只把路径部分能在冻结源中解析为文件的片段视为定位（或要求定位出现在 Evidence 字段、带文件扩展名）；无法解析为文件的 `a:b` 片段当作普通代码文本，不产生诊断。
- **本工程临时措施**：无，按 ARW 原版照罚并在报告中注明。

### 5. Code Standards 原版答案键漏收 `writing.md` 规定成立的发现，且一个 clean 用例与 `writing.md:49` 矛盾

- 场景：ARW 760007c `tests/fixtures/reviewer-capability/code-standards-reviewer`。Role 要求审查者同时执行 `docs/agents/writing.md`，但答案键只按 `src/AGENTS.md` 与 role 的设计检查出题。
- 漏收的成立发现（按 `writing.md` 成立，键外报告记为误报）：
  - `src/orders/order-service.mjs:74`（`reviewerCapabilityLoadFulfillmentPolicy` 只转发 `reviewerCapabilityLoadCarrierPolicy`）、`:82`（`reviewerCapabilityResolveDispatch` 只转发）：`writing.md:49` 不写纯转发包装器。本工程 Code Standards 基线 Q3 ×3 每次都报。
  - `src/shared/path.mjs:1` 只再导出 `node:path` 的 `basename`：同 `writing.md:49`。
  - `src/persistence/order-store.mjs:4`、`:24` 用 class 实现 store：`writing.md:111` 非必要不用 class。
- 矛盾的 clean 用例："The shared path helper directly re-exports reviewerCapabilityBasename from node:path."（证据 `src/shared/path.mjs:1`）。它只判定 `node:` 前缀合规，但 findingTerms 含 `path`、`prefix`，按 `writing.md:49` 报这个再导出模块的正确发现会命中它而被扣分。
- 影响：正确遵守 role 的审查者被计误报和 clean 失败，模型越认真越吃亏。
- 建议上游：答案键补收这些发现（或从夹具中去掉对应代码），clean 用例改成只断言 `node:` 前缀且 findingTerms 不含模块形态的词。
- 本工程处理：用户 2026-10-14 决定 (a)，在 Code Standards v5 中把纯转发、再导出、class 作为问题用例重建（新场景 S09、S10、S08），path helper clean 用例删除；v5 与 ARW 原版不可比。

## 本工程对 ARW 的修改（建议上游同样修改）

本工程按自己当前的 Strata 工作方式修改了冻结的 ARW。修改以补丁形式登记在 `benchmarks/reviewer-suite-v1/source-snapshots/current/manifest.json` 的 `patches` 里，展开冻结源码时打上，并校验打完后的 SHA。这些不是 ARW 的缺陷，而是本工程升级了 Strata 的接入方式，建议 ARW 适配。

### A. Strata provider 改用常驻前端接口（`arw-patches/strata-frontend-protocol.patch`）

- **版本**：ARW 760007c，`lib/background-agent/strata-driver.mjs`、`strata-work-policy.mjs`、`strata-models.mjs`、`model-catalog.mjs`、`manager.mjs`，以及对应测试 `tests/background-agent/strata-driver.test.mjs`、`model-catalog.test.mjs`、`host.test.mjs`。
- **原做法**：每次连接都运行安装目录的 `Run-Strata-Controller.sh` 启动控制进程，用 `/ownership/acquire|status|start|stop|release` 管理独占和模型；启动模型时写死 `spec-min-p 0.7`、`max-context 156584` 和 temperature 0 / top_p 1 / top_k 20；`strata-models.mjs` 的 `STRATA_CONTEXT_WINDOW = 156584` 同时写进模型目录和任务设置，压缩阈值写死为 100000；压缩提示读取 `config/compact_prompt.txt`。
- **本工程现状**：安装目录有一个常驻前端，网卡名前缀和端口写在 `config/frontend.json`（`listen_interface`、`port`），接口为 `POST /lease/acquire`、`GET /model/status`、`POST /model/start`、`POST /model/stop`、`POST /lease/release`，模型请求走 `/strata/v1`。引擎参数和请求默认值由安装目录按"主机 + 量化"实测选定（例如 rtx3080ti 的 IQ3_XXS 用 `spec-min-p 0.9`）。公开的 `/model/start` 只接受 `{model, context_window}`，其他字段一律拒绝；`context_window` 必须是安装目录 `config/deployment.json` 里该量化 `context_tiers` 发布的档位之一（每档带 `context_window` 和 `auto_compact_token_limit`，第一档为默认）。调用方因此只选三项：模型、推理强度（随请求）、上下文档位。压缩提示位于 `config/prompts/compact-prompt.txt`。旧的控制脚本和 `/ownership/*` 已经删除。
- **修改**：
  1. `connect()` 不再运行脚本，改为读取 `config/frontend.json`，得到控制地址，模型地址为 `<控制地址>/strata/v1`。
  2. 五个操作改为上面的新路径；解析新的返回字段（`acquire` 返回 `key` 与 `lease: "held"`，`release` 返回 `lease: "free"`）；前端把加载中的模型报告为 `starting`，按原 `partial` 处理。
  3. `start` 只传 `{model: <量化名>, context_window: <档位窗口>}`，不再写死引擎参数和采样参数。
  4. 去掉 `STRATA_CONTEXT_WINDOW` 和固定的 100000。新增 `readStrataContextTier`：读取安装目录 `config/deployment.json` 的 `context_tiers`，按 provider 配置的 `contextWindow` 选档（未配置用第一档），档位不存在时报错。模型启动窗口、模型目录里的 `context_window` / `max_context_window`、任务设置里的 `model_context_window` 和 `model_auto_compact_token_limit` 都取自同一档位。
  4a. 档位按量化分别发布（2026-10-12 补）。模型目录一次覆盖所有 Strata 变体，选定窗口只套用到发布了该档的变体，其余变体保留各自的默认档；没有任何变体发布该档时才报错。启动与任务设置只针对所选模型，档位不存在时仍然报错。起因：第 9 维选 IQ3_XXS 的 206584 档时，Q2_0 没有这一档，模型目录生成失败，ARW daemon 退出。
  5. `models.custom.json` 的 Strata provider 新增可选字段 `contextWindow`（正整数，只允许 Strata driver）。模型目录先校验 provider，再用校验后的 provider 套档位。
  6. 压缩提示路径改为 `config/prompts/compact-prompt.txt`。
  7. 同步更新 ARW 自带的 driver、模型目录和 host 测试（旧 driver 测试仍按已删除的控制脚本断言；host 测试的夹具改为新压缩提示路径并提供档位）。改动后 `tests/background-agent/` 与 `tests/reviewer-runtime/` 只剩 1 个与本补丁无关、未打补丁时同样失败的终端标题测试。
- **建议**：ARW 按上述新接口适配；不要在 ARW 中写死引擎参数、窗口或压缩阈值，由安装方的每机每量化默认值和发布档位决定。

### C. 嵌入式宿主传入 `nativeSessions` 时，管理器读不到 provider（本工程运行层已绕开，未改 ARW）

- **版本**：ARW 760007c，`lib/arw-background-agent-host.mjs` 的 `createBackgroundAgentHost`。
- **现象**：调用方传入 `nativeSessions` 而没有传 `modelCatalog` 时，宿主既不创建共享模型目录，也不设 Strata driver 工厂；管理器的 `providerConfigurations()` 因此为空，`model_owner = "arw"` 的任务不会领 key、不会启动模型，模型请求直接被前端以 403（缺少有效 key）拒绝。本工程 2026-10-11 的 F3 试跑即因此失败。
- **本工程处理**：运行层 `tools/reviewer/arw_native_setup.mjs` 按 ARW 宿主自己的做法，创建一个共享目录（`CODEX_HOME` 指向隔离的 codex-home），同时传给 App Server 和宿主；provider 写进 codex-home 的 `models.custom.json`（ARW 只从这里读 provider）；daemon 就绪时回报 ARW 实际读到的 provider，`arw_measure` 核对一致后才派发。
- **建议**：宿主在收到 `nativeSessions` 时也应接受或创建 `modelCatalog`，或在缺少目录而 provider 需要 driver 时明确报错，而不是静默丢掉 provider。

### D. 原线程已卸载时，followup_task 用新交接的文件系统检查原报告，判定"报告缺失"并无限接续（`arw-patches/reviewer-followup-original-scope.patch`）

- **版本**：ARW 760007c，`lib/reviewer-runtime/reviewer-runtime.mjs` 的 `followup`。
- **现象**：App Server 以 `thread_unload_delay_secs=0` 启动，Reviewer 回合一结束原线程就卸载。此时发 `followup_task`，若新交接的 `cwd` 与原任务不同（本工程 Spec Readiness 合并实例：runtime-migration 后在同一线程接续 artifact-promotion），`followup` 重开条目时把**新交接**的 `reviewFilesystem`（根为新 `cwd`）与**原记录**（原 `cwd`、原报告路径）放在一起，接受任务前的 `refresh` 在错误的根下找原报告，判定缺失，于是走原生接续：发"报告缺失"指示、开新回合，`followup_task` 本身返回 `reviewer-busy`。之后每次刷新都用同一错误作用域，Reviewer 每回合都重写报告并回答 `ready`，ARW 仍判缺失，直到第 10 次早退暂停。2026-10-11 F3 第二次试跑：runtime-migration 首回合 09:13:57 回答 ready，驱动看到 completion=ready 并立即 followup；09:14:01 起连续 10 次接续，报告文件始终存在。
- **依据**：代码路径（`followup` 在条目不在内存时，用 `checkReportBinding(handoff,…)` 的结果建条目，接受任务后才赋值 `held.reviewFilesystem`）与会话记录、报告文件修改时间一致。补丁附带复现测试 `an unloaded Reviewer checks its original report in the original scope before a followup in another cwd`：只卸载线程、App Server 仍在运行，provider 能接续任务，followup 改用另一个 cwd。修复前，测试因为触发恢复接续而失败；修复后通过。
- **本工程修改**（2026-10-11）：重开条目时，`reviewFilesystem` 改用 `checkReportBinding(previous, false, recoveryPath)`，也就是原记录的作用域，与条目仍在内存时的路径一致。新交接的文件系统照旧在 `acceptTask` 成功后替换。新交接仍按原样先做 `fresh` 校验。ARW 全套测试的失败集合和未修改时完全相同，都是安装、发布、终端标题类的环境性失败，与本补丁无关。
- **建议上游**：采用同样的修改。更一般地说，条目的文件系统应当始终和 `entry.record` 描述的任务一致，只有在任务切换（接受新任务）时才一起替换。

### E. Codex 0.163 在报告目录留下 synthetic mount target 空目录，绑定检查判失败（`arw-patches/codex-0.163-synthetic-mount-targets.patch`）

- **现象**（2026-10-20，多模型 benchmark OpenAI 臂）：Codex 0.163.0 的 bubblewrap 沙箱会在每个写授权目录里为受保护的名字（`.git`、`.codex`、`.agents`、`.aws`）建空的挂载占位目录，session 启动后不到 1 秒就出现。正常情况下 Codex 在 turn 结束前会自己删掉，但删除不可靠，有时会留下，留下后进程关闭也不删。ARW 的报告目录正是 Reviewer 唯一的写授权目录，`checkReportBinding` 要求它只含绑定报告，所以完成时判 "The Reviewer report directory must contain only its exact bound report."。CA 正式运行的 10 个实例都受到影响，其中 1 个提前终止。
- **证据**：`.tmp/bench-openai-1020/stubtest2/`（零模型，真实 CA 嵌套布局的副本，主机每 0.1 秒列一次目录）：13 次运行全部出现占位目录，5 次留到进程关闭以后。哪个目录是写授权，占位目录就出现在哪里，与布局、git、/tmp 无关。把写授权换成报告文件本身时 thread/start 被拒；设 `features.use_legacy_landlock` 时也被拒；设 `features.use_linux_sandbox_bwrap=false` 不起作用。Codex 二进制里有 "synthetic mount registry"、"failed to remove synthetic bubblewrap mount target" 字样。端到端零模型门：`.tmp/bench-openai-1020/mtgate/`（真实 arw_measure 走 OpenAI 路径，脚本化模型，网络命名空间）。未打补丁时，占位目录留下的那次判 incomplete；打补丁后，留下的那次判 ready，并记录了 12 条忽略事件。
- **本工程修改**：`checkReportBinding` 把报告目录直属、名字恰为这四个之一的真实空目录放过，其余额外条目照旧失败，包括：非空的占位目录、名单外的名字、符号链接、文件、额外文件。每次放过都在 stderr 写一行 `{"event":"codex-synthetic-mount-target-ignored","path":…}`。补丁不在冻结 manifest 里，由调用方在 prepare 时选择应用（`tools.reviewer.freeze_arw_source.HARNESS_PATCHES`，`prepare(..., harness_patches=…)`），核对补丁前后成员的 sha。写权限不变。
- **建议上游**：绑定检查应能识别 Codex 自建的挂载占位目录；也可以向 Codex 报告：同步删除失败时，至少应在进程退出时把占位目录清掉。

### F. 冷恢复（restorePausedTask）用原始交接 settings 重开线程，丢掉 Reviewer 的 profile、私有 scratch、TMPDIR 与凭据 deny-read（本工程运行层 `tools/reviewer/arw_native_setup.mjs` 已绕开，未改 ARW）

- **版本**：ARW 760007c，`lib/reviewer-runtime/reviewer-runtime.mjs` 的 `restorePausedTask`（约 859 行）。
- **现象**：spawn（721 行）和 followup（786 行）都会把交接经 `reviewerNativeSettings` 转成带权限 profile 的 settings 再 `nativeSessions.open`；只有 `restorePausedTask` 冷恢复时直接 `nativeSessions.open({settings: record.settings, …})`，`record.settings` 是原始的 `review_settings`，没有 profile。于是运行时重启或 `--resume` 恢复出来的 Reviewer：`default_permissions` 为 null（丢掉 `:read-only` 加显式写路径的 profile），没有私有 scratch（`reviewer-private-scratch`）和指向它的 TMPDIR，也没有凭据路径 deny-read（G7）。`arw_measure` 同进程内的早退暂停续跑走的是热路径（`runs` 里仍持有该 run，不重开），不受影响；只有冷恢复（运行时重启、`--resume`）受影响。
- **证据**：冷 `restorePausedTask` 探针显示重开会话的 `default_permissions`、TMPDIR、`approval_policy` 都是 null（`.tmp/scratch-verify-1024/resume/`）。本工程运行栈上 `denyReadSettings` 对这种无 profile 的 settings 会直接抛错（fail-closed），所以实际不会以降级权限静默跑完，但恢复本身会失败。
- **本工程修改**（2026-10-24）：`arw_native_setup.mjs` 的 `reviewerResumeOpen` 包住 `sessions.open`：对任何 settings 里还没有 `default_permissions` 的 open（即冷恢复），先补 `reviewerNativeSettings`（用该 open 自带的 cwd、readPaths、writePaths，与首段同源，所以 profile、scratch 路径、TMPDIR 与首段一致），再叠加 deny-read；已带 profile 的 open（spawn、followup）原样放过，不重复加 profile。回归测试 `tests/test_reviewer_scratch.py::test_resume_reopens_a_reviewer_with_the_same_scratch_and_deny_read`：断言恢复后重新拿到 profile、TMPDIR 与首段相同、scratch 为 write、公共根为 none、恢复和普通 open 都带 deny，而普通 open 的 profile 不变。
- **建议上游**：`restorePausedTask` 应与 spawn、followup 一样，把恢复的交接经 `reviewerNativeSettings`（或等效的权限派生）再 open，使恢复后的线程与原线程权限一致。

### B. 能力测量中不要求每实例冷启动

- 本工程以前在每个实例之间停模型、冷启动，以便按引擎日志分段计量。这是本工程自己的旧做法，ARW 本身不这样做（它在整个共享 App Server 期间持有独占，关闭时才归还，也不停模型）。现在本工程也不再停模型，引擎日志按派发时刻分段。
- 实例之间只会复用 Strata 的精确前缀缓存（系统提示和工具列表等逐 token 相同的开头），模型输入不变，不会看到上一个实例的内容。
- **建议**：ARW 的能力验证和 benchmark 规则如果要求冷启动，应改为只要求"不复用上一个实例的上下文"，不要求停模型。

## 已修复

（暂无）
