# 上下文档位统一：Codex 与 Claude Code 同用默认档（rtx3080ti 部署与冒烟）

日期：2026-10-19　主机：rtx3080ti　Strata v0.1.45　Codex 0.162.0　Claude Code 2.1.303

## 结论

- 4 个提交（01d6aa7、b6bf6a6、6f18380、04dbab5）已部署到 rtx3080ti。23 个文件逐个回读 SHA，全部与工程渲染结果一致；前端已重启，`/health` 正常。
- `qwen-agent` 现在按所选量化的默认档启动。IQ3_XXS 为 206584／150000，Codex 和 Claude Code 用同一组值。冒烟检查两个阶段都通过：`/model/start` 返回 `max_context` 206584，第二次及以后的启动 `reused=true`，传给 Claude Code 的 `CLAUDE_CODE_MAX_CONTEXT_TOKENS` 为 206584、`CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE` 为 150000，Codex 收到的覆盖值同为 206584／150000。引擎输出 98.9 和 109.9 tok/s，高于 60 的意外线。结束后租约为 free。
- Claude Code 的压缩点用工程工具 `tools/ops/claude_compact_probe.py` 复核（假服务器，不用模型）。在 2.1.303 上，三组档位各取阈值 ±100，两种进入方式各跑 3 次，36 格全部符合预期。
- 适用范围：只覆盖 rtx3080ti 和 Claude Code 2.1.303。rtx4070tis 没有 `context_tiers`，没有同步，记为待同步。
- 安全门实跑**没有做**，等用户决定（计划要点见「遗留」）。按现行规则，默认模式安全门记为"未完整通过（已知类型）"。

## 目的

benchmark 前置工作第 2–4 项要求 Codex 和 Claude Code 两条路径用同一档位，并且代码里不再有写死的窗口或阈值。原因是 benchmark 如果经 Claude Code 跑 Strata，或者把 harness 列为一个维度，两条路径的档位必须相同。这些代码改动属于默认参数改值，须经独立审查，并在维护窗口部署后才生效。

## 改动（4 个提交）

| 提交 | 内容 |
|---|---|
| 01d6aa7 | catalog 窗口改为取部署档位的首档，不再写死 156584。IQ3_XXS 为 206584，Q2_0、IQ2_XS 仍为 156584。渲染 catalog 时，已安装的量化如果没有发布档位就报错 |
| b6bf6a6 | 去掉 `arw_measure`、`wsl_client`、`verify_codex_compact_prompt` 里写死的 250000／200000 和 156584／100000：driver 持有模型时缺值就报错，加载后核对 `max_context`。修好零模型沙箱探针（改为放行 ARW 使用的原生 Codex 二进制，拒读目标换成实际存在的文件）。删除无引用的 `config/qwen-strata.config.toml` |
| 6f18380 | 安全门按运行计划给出的模型和已发布档位运行，不再写死 Q2_0 与 156584／100000。实跑必须带 `--plan`；启动提示 SHA 按实际加载的字节核对 |
| 04dbab5 | `qwen-agent` 改用所选量化的默认档：`/model/start` 显式传窗口，Codex 和 Claude Code 用同一组值，缺档时在领取租约前报错。调用手册同步修改 |

本次另有两个提交：0c9bfbc 把压缩点探针纳入工具；09def4a 提交本报告的数据。

## 假服务器核对

工具：`python3 -m tools.ops.claude_compact_probe`。环境变量直接取自工程 `scripts/wsl/qwen-agent` 的 `claude()`，与日常启动时相同；档位取 `config/deployments/rtx3080ti.json` 发布的首档。

两种进入方式：
- 两回合：第 1 回合的回复声明输入 N，第 2 回合用 `--continue`，看先压缩还是直接发送；
- 回合中途：第一个回复是工具调用，看同一回合里的后续请求。

判定：阈值以下不压缩；阈值以上要压缩，并且压缩之后会话继续；每次运行的退出码都是 0。

隔离：每格都用全新的 HOME 和 `CLAUDE_CONFIG_DIR`，加 `--setting-sources user --strict-mcp-config`，工作目录是 /tmp 下用完即删的临时目录（不在 /home/pello 之下）。

| 档位 | override | 声明输入 | 两回合（压缩次数/次数） | 回合中途（压缩次数/次数） | 结果 |
|---|---|---:|---:|---:|---|
| 206584／150000 | 设 150000 | 149,900 | 0/3 | 0/3 | 符合 |
| 206584／150000 | 设 150000 | 150,100 | 3/3（均继续） | 3/3（均继续） | 符合 |
| 156584／100000（Q2_0） | 设 100000 | 99,900 | 0/3 | 0/3 | 符合 |
| 156584／100000（Q2_0） | 设 100000 | 100,100 | 3/3（均继续） | 3/3（均继续） | 符合 |
| 206584 | 不设 | 183,484 | 0/3 | 0/3 | 符合（默认点 183584） |
| 206584 | 不设 | 183,684 | 3/3（均继续） | 3/3（均继续） | 符合 |

原证据（`.tmp/ctx-fix-1019`，旧探针生成，Claude Code 2.1.303）共 18 格。逐格读取保存下来的原始请求，用现行判定重判：只有 `w206584-l150000-c150100-mid` 一格结论变化，从"未压缩"更正为"已压缩"。原因是这一格由加入压缩标记之前的旧探针生成，第 2 个请求里实际带有 Claude Code 的摘要指令。其余 17 格的结论不变：不设 override 时 150.1K、170K、174K、180K、183.5K 都不压缩，183.7K、184K 压缩；设 150000 时 140K、149.9K 不压缩，150.1K、160K 压缩；156584／100000 档 99.9K 不压缩，100.1K 压缩。重判表在 `data/original-ctx-fix-1019/rejudged.json`。

数据：`data/probe-iq3/`、`data/probe-q2/`、`data/probe-iq3-nob/`，每格一个 `result.json`，另有 `summary.json`；原始请求没有收入报告。

## 独立审查意见（原文）

> 独立审查（2026-10-19）：4 个提交（01d6aa7、b6bf6a6、6f18380、04dbab5）有条件同意部署。单测 434 个全部通过，catalog --check 为 current，本机安装目录除 bin/qwen-agent 外与工程一致。缺值报错只出现在 driver 持有路径（含旧批次 resume）和没有档位的主机上；ARW 测量、日常 qwen-agent（rtx3080ti 三个量化都有档位）不受影响。rtx4070tis 没有 context_tiers，部署时会在渲染 catalog 一步失败即停，恢复后须先补档位再同步。qwen-agent 改为 206584/150000 的依据成立：现行探针复跑，回合中途 150.1K 有 6/6 次压缩、149.9K 有 6/6 次不压缩，两回合与不设 override 的 183.6K 边界也一致。原证据中 c150100-mid 的 result.json 由旧版探针生成、判定标记错误，原始请求显示确实发生了压缩，已更正。风险在于 CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE 未公开文档，升级 Claude Code 后可能退回 183.6K 压缩；须把探针纳入工具并在升级流程中重新核对；回退方式是 revert 04dbab5 后重新部署。安全门：实跑的自动 pass 不覆盖默认 exec_command 单文件授权的已知 bwrap 失败，不能把 all_observed_pass 当作安全门通过。按现行规则，默认模式安全门应记"未完整通过（已知类型）"；能否以已知例外开跑 benchmark，属于测量和安全口径，由用户决定；report-directory 授权会扩大写范围，须用户明确同意才可采用。

## Main 意见

同意审查结论，按以下顺序执行：
1. 把探针纳入工具，并写进升级流程；
2. 整理证据；
3. 部署到 rtx3080ti；
4. 冒烟检查；
5. 不做安全门实跑，等用户决定。

## 部署

- 部署前核对：租约 free，没有加载模型；安装目录与工程渲染结果不同的文件有两个，`bin/qwen-agent` 和 `README.md`（调用手册）。审查说只有 `bin/qwen-agent` 不同，实际手册也不同。差异内容就是 04dbab5 和 01d6aa7 对手册的修改，属于预期部署内容。
- `python3 -m tools.ops.deploy --host rtx3080ti`：流程为领租约 → 确认模型已停 → 关闭前端 → 备份、替换 → 回读 → 计划任务重启 → `/health`，用时 16.9 秒，退出码 0。
- 部署后另行逐文件回读：23 个文件的 SHA 都与工程渲染结果一致，与 `deployment-manifest.json` 一致；没有过时文件需要删除。
  - `bin/qwen-agent` 为 1f2165c9…
  - 启动提示源 5f9efc02…
  - 压缩提示 3856cb62…
- 备份：`.tmp/maintenance-backups/deploy-20261019-144518-791700`。按保留规则，删除了上一个部署备份 deploy-20261018-115145（删除前已确认没有任何文档引用它）。
- 回退方式：revert 04dbab5 后重新部署，或从上述备份恢复。
- rtx4070tis 没有连接，记为待同步：须先在 `config/deployments/rtx4070tis.json` 补上 `context_tiers`，否则渲染 catalog 一步就会失败停下。

## 冒烟检查

开跑前已按 run-plan 写下计划（`.tmp/deploy-ctx-1019/progress.md`）。

运行方式：
- 用包装脚本加载**安装目录**里的 `bin/qwen-agent` 运行，只记录 `/model/start` 的回复字段和传给 agent 的档位，不记录 key；
- 每个阶段从引擎日志的偏移处开始切分执行段；
- 隔离：Codex 用全新的 `CODEX_HOME`，Claude Code 用全新的 `CLAUDE_CONFIG_DIR` 并加 `--strict-mcp-config --setting-sources user`；工作目录 `/tmp/deploy-ctx-1019-smoke`（在 /home/pello 之外，已删除）。

任务：读出 `note.txt` 里的随机标记，原样回答。

启动提示：`/health` 和 `/model/start` 的 `native_health` 都显示 `sha256` 1cae169a…（去掉防循环段之后实际加载的字节），`source_sha256` 为 5f9efc02…，`loop_prevention_enabled` 为 false，与开跑前算出的值一致。压缩提示经安装目录回读一致；Codex 收到的 `experimental_compact_prompt_file` 指向安装目录里的这个文件。

| 阶段 | 结果 | /model/start | 传给 agent 的档位 | 总耗时（秒） | 执行段 | 未缓存输入 | 已缓存输入 | 输出 | 引擎输入 tok/s | 引擎输出 tok/s | 任务平均输入 tok/s | 任务平均输出 tok/s |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| X1 Codex `exec` | 通过：执行 `cat note.txt`，回答标记正确 | reused=true，max_context 206584 | `model_context_window` 206584，`model_auto_compact_token_limit` 150000，high | 13.0 | 2 | 67 | 18237 | 140 | 95.0 | 98.9 | 5.2 | 10.8 |
| C1 Claude Code `-p` | 通过：Read 工具读取 note.txt，回答标记正确 | reused=true，max_context 206584 | `CLAUDE_CODE_MAX_CONTEXT_TOKENS` 206584，`CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE` 150000，`CLAUDE_CODE_MAX_OUTPUT_TOKENS` 24576，`CLAUDE_CODE_EFFORT_LEVEL` high | 18.9 | 2 | 15863 | 15909 | 138 | 2060.1 | 109.9 | 839.3 | 7.3 |

- token 全部取自引擎日志。总耗时是每次 `qwen-agent` 从启动到退出的时间，含领租约和复用启动，所以任务平均速度偏低，只作参考。
- X1 的未缓存输入只有 67，因为它的前缀已被前一次 X1 缓存（见下面的偏离第 1 条），这一行的引擎输入速度没有参考意义。
- 只跑一次，不作速度比较。
- 结束后 `/health` 显示 lease free；模型保持加载，按设计由前端在空闲后停掉。
- 数据：`data/smoke/X1.json`、`data/smoke/C1.json`，部署结果在 `data/deploy-result.json`。

偏离：
1. 第一次 X1 由 `qwen-agent` 正常跑完：冷加载，回答标记正确，租约已归还。但包装脚本的输出路径写成了相对路径，进入工作目录后写记录失败，冷启动那次的 `/model/start` 回复没有记下。修正后重跑了一次 X1（复用）。所以 `qwen-agent` 共运行 3 次（计划 2 次），冷加载耗时未记录。冷加载时的窗口由两次复用回复中的 `native_health.max_context` 206584 证实：复用的是同一个引擎进程。
2. 全新的 `CODEX_HOME` 放在 /tmp 下时，Codex 提示 "Refusing to create helper binaries under temporary dir"。这只影响 apply_patch 等辅助命令的别名，对本次 exec 没有影响。

## 遗留

1. **rtx4070tis 待同步**：恢复后先核对实际状态，在 `config/deployments/rtx4070tis.json` 补上 `context_tiers`，再同步部署（不补的话，渲染 catalog 一步就会失败停下）。
2. **探针已纳入工具**（0c9bfbc）：`tools/ops/claude_compact_probe.py`，附 5 个单元测试。部署规则新增一条：用 `qwen-agent` 跑 Claude Code 的测试（冒烟、升级短检查、测量）之前，核对 `claude --version` 与调用手册「自动压缩」一节记的核对版本（现为 2.1.303）；版本不同就先运行 `python3 -m tools.ops.claude_compact_probe --out .tmp/<工作>/compact-probe --repeat 3`，通过后更新手册里的版本号并部署；不通过按意外事件处理。风险依旧存在：`CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE` 没有公开文档。
3. **安全门实跑待用户决定**，本次没有跑。计划要点：
   - 先请用户定三件事：(a) WSL 是否先升级再跑；(b) 默认 `exec_command` 单文件授权的已知 bwrap 失败（v0.1.40.1 起一直存在，见 `reports/v0.1.40.1/current-safety-gate/summary.md`）怎么判定——记为"未完整通过（已知类型）"、按已知例外开跑 benchmark，还是修好后再跑；(c) 是否采用 report-directory 授权（会扩大写范围，须用户明确同意）。
   - 开跑前：按 run-plan 写计划，内容为 host rtx3080ti、IQ3_XXS、默认档 206584／150000、启动提示加载 SHA 1cae169a…、压缩提示 3856cb62…。在已部署版本上重跑零模型预检：`verify_reviewer_sandbox` 零模型模式，以及 `safety_gate` 零模型的 apply_patch、exec_escalated、directory-probe、mock-approval 四项。
   - 运行：`python3 -m tools.safety.safety_gate --source <冻结 ARW> --run <.tmp/...> --plan <已批准计划>`。规模按 reviewer-suite「正式测量前的安全验收」：3 个原生实例（沙箱、报告写入、同线程接续），加 15 个审批用例（约 21 次 guardian 决定）；冷加载 1 次，预计 30–60 分钟；不用 Anthropic 模型。
   - 判定：不把 `all_observed_pass` 当作安全门通过，逐项核对实际字节。默认 exec_command 那一项按用户定的口径记录。出现已知类型以外的安全违规，就停止、保留现场，并列入状态页 `decide`。
4. 临时目录 `.tmp/deploy-ctx-1019/`（含探针原始请求，约 6.6 MB）和 `.tmp/ctx-fix-1019/cc/`：报告数据已收入 `data/`，报告落盘后可以删除。`.tmp/ctx-fix-1019/` 下的 gate-mock-* 和 sandbox-probe-* 是安全门零模型证据，等安全门实跑做完再处理。
