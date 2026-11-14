# Hydrogen（Antigravity）补测计划：phase 4 补充（2026-11-14，已按独立审查意见修订，见 §10）

任务：`common/hydrobench`（用户 2026-11-14 08:5x：Hydrogen 三档推理强度的 benchmark 全做，结果要能与 reviewer-bench 页面上的 v1 数据放在一起）。依据：[plan.md](../../plan.md)（v1 冻结计划，§3 固定条件、§5 统计、§6.2 盲裁）、[export-format.md](../../export-format.md)、luna 补测先例（`../luna-xhigh-1022/`，phase 3）。本文按[运行计划](../../../../.claude/skills/run-plan/SKILL.md)的结构写成。**不改 v1 冻结件**：场景 plan、答案键、测量说明、盲裁 brief、锚点、计分 r8.4 都原样使用。

## 1. 目的

用 v1 冻结的四个 ARW Reviewer 场景（Code Spec v5、Code Standards v5.1、Commit Audit v3、Spec Readiness v4.3）测 Antigravity 上 Gemini 4 Hydrogen 的 medium / high / xhigh 三档，每档每场景 5 次有效运行，分数与页面上 页面上已有的 31 个配置（27 个，加 2 个 DeepSeek medium 补充，加 phase 3 的 28、29）同口径，作为 phase 4 补充配置 30–32（只报每格结果，不进预登记比较，与 phase 3 的 luna xhigh/max 相同）。

## 2. 配置

| # | harness | 模型 | 强度 |
|---|---|---|---|
| 30 | Antigravity `agy` 1.5.8（二进制 sha 开跑前记录；`~/.gemini/antigravity-cli/bin` 在沙箱里只读，运行期间不会自更新；每个实例开始前核对版本，变了就停） | `gemini-4-hydrogen-medium` | medium |
| 31 | 同上 | `gemini-4-hydrogen-high` | high |
| 32 | 同上 | `gemini-4-hydrogen-xhigh` | xhigh |

- 三档的调用方式：`agy -p … --model gemini-4-hydrogen-<强度> --effort <强度>`（`agy models` 列出 low/medium/high/xhigh 四档，本计划不跑 low，用户只要三档）。模型 id 的后缀和 `--effort` 取同一值；开跑前的 P4 探针记录各档 `thinking_tokens`，只在明显倒挂（xhigh 的思考 token 少于 medium）时判 `--effort` 没生效而停下；每档 1 个样本噪声大，不要求严格单调。P4 实测（G 与 T 见 §3）三档 T 在 341–401 秒内，彼此不超过 3 倍。
- 每格 4 场景 × 5 次有效实例；SR 每实例两个根线程（RM、AP），共 3 档 × 3 场景（CA、CS、CStd）× 5 = 45 个实例 + 3 × 5 × 2 = 30 个 SR 线程 → 实际 `agy` 会话 75 个（CA/CS/CStd 各 15 + SR 30），不含重跑和探针。

## 3. 固定条件

- **场景与计分**：与 v1 相同：四个场景 plan（`scenarios/*.json`，冻结 sha 见 plan §14）；ARW 零模型物化（`arw_dimension.prepare`，冻结源 manifest）；计分 r8.4（`bench_score` → ARW `score-completed`，repair、格式罚照旧）；时限规则照旧：SR、CA 用 ARW 原版（提醒 55 分钟、中断 60 分钟；本 harness 的提醒用结束当前轮再发消息的方式送达，见 §4），CS、CStd 按各配置自己的 P4 探针算 T = round(B × k ÷ (G × β))（k = 2.0755，1/P = 0，B = CS 152919 / CStd 142529 字节，方法同 luna 补测）。
- **v1 plan 的 Codex 绑定**：场景 plan 的 `fixed_conditions.codex` 绑 0.163.0 副本，它已不在本机（只有 0.164.0）。`prepare` 只用它核对一次 sha，不运行；本补测用把 `codex` 和 `native_cli_sha256` 改为 0.164.0 副本的临时 plan 副本（`/tmp/hydrobench/plans/`）做 `prepare`，其余字段逐字不变。Agy 不经 Codex，对已物化的场景根、handoff 和提示没有影响（零模型核对：同一场景用两个 plan 物化，handoff 的 `input`、测量说明、场景根文件列表逐字相同，见 §9 步骤 2）。
- **提示**：v1 Claude Code 臂的形态（`claude_scenario.prompt_text`，`role_as_system` 为假）：绑定的 Role 指令 + handoff + 冻结测量说明（CS/CStd 为填入 T 的限时说明），作为单条用户消息交给 `agy -p`；agy 没有可由调用方设置的系统提示，所以 Role 不能放系统位（Claude 臂在 v1 里同此）。路径按 `claude_scenario.stage` 改写到 `/tmp/hydrobench/<单元>/work`，提示不含用户家目录。基础提示（Strata 的启动和压缩提示）不适用。
- **工作目录**：每个 handoff 一个全新的场景根副本 `/tmp/hydrobench/<单元>/work`（含 `.git`，`agy-run.py` 的 git 根检查），每个 handoff 一个新 agy 会话。
- **权限与沙箱**：`agy --sandbox` 实测拦不住读取（`cat` 能读工作目录外任意文件，包括 `$HOME` 下的文件；`write_file` 工具写 `$HOME` 被拒，写 `/tmp` 不被拒，`node` 能写 `/tmp`），所以隔离改用 bwrap（`agyrun.bwrap`）：只读挂 `/usr`、`/etc`，家目录和 `/tmp` 是空的 tmpfs，用户的项目目录、`~/.claude`、`/mnt/c` 等不可见；唯一可写的项目路径是该 handoff 的工作副本（`/tmp/hydrobench/work/<实例>`），答案键所在的 `prep` 在沙箱里不存在；agy 的状态目录每个实例一份私有副本（不带别的会话、记忆、历史；OAuth token 文件直接绑定，刷新能回到原文件）。实测：沙箱内 `ls ~/projects`、读工作目录外的合成密钥文件都失败；`git`、`node`、`sed`、`awk`、写报告都可用。网络保持开通（agy 要访问 API），所以 curl/wget 靠命令拒绝名单，`python3` 等能联网的命令用事后扫描（命令里的 `http`、`curl`、`wget`、`requests`、`urllib`）标出。agy 自带的 `--sandbox` 在 bwrap 里嵌套会失败，不用。权限设置仍沿用 `agentMode auto` 与 `permissions.allow`（命令白名单扩到只读等价集合：ls cat echo wc head tail grep find sort diff nl sed awk tr cut uniq stat tree date pwd jq node python3 git status/diff/log/show/cat-file/ls-tree/ls-files/grep/rev-parse/blame/rev-list/diff-tree/merge-base/branch/tag/show-ref/for-each-ref 等），拒绝名单 sudo/rm -rf/curl/wget/git push/reset/checkout/stash。不在白名单里的命令会被 agy 自动拒绝并使整个运行提前结束，这样的实例记 `denied_actions` 作废重跑，作废率在报告中给出。`--disable-slash-commands` 打开，防提示里 `/` 开头的内容被展开。跨会话记忆：实测新会话问"之前对话里让你记的词"得 NONE，状态目录私有，且每实例新建。
- **输出格式**：`--output-format stream-json`；提示经 stdin 的 `--input-format stream-json` 一行用户消息送入（材料 152919 字节，超过 Linux 单参数上限 131072，不能用 `-p <全文>`）：逐步事件含每次模型响应的 `usage` 与 `duration_seconds`、每次工具调用名，用于 token、G、工具数和搜索/子 agent 检查。流存为 `h<k>/stream.jsonl`（续接段 `stream-<i>.jsonl`）。
- **时限、提醒、续接与硬停**：整个实例（所有段）的墙钟从第一段开始算，硬停在 T（SR/CA 为 3600 秒）。提醒：`reminder_time(T)`（T ≥ 600 秒取 T − 300，否则 T/2；与 Claude 臂相同）时，第一段的 `--print-timeout` 到期结束当前轮（实测到期的轮以 `status SUCCESS`、空回复、`finished_reason print_timeout` 结束，已写文件保留，会话可用 `--conversation <ID>` 续接），随后在同一会话发 `review_deadlines.reminder_message` 的原文（含剩余秒数和硬截止时刻）作为下一轮，这与 Codex 路径"打断生成后送达"效果相同；到 T 的那一轮 `--print-timeout` 到期即硬停，按已写出的报告计分。每段的预算扣去 agy 启停开销 7 秒（实测约 6.5–7 秒，`agyrun.STARTUP`）。早退接续：照 `claude_headless.execute_continued` 的逻辑，一轮正常结束但最终消息不是恰为 `{"status":"ready"}` 或报告为空时，用 ARW 的接续原文（`early_exit` 的三种指令）在同一会话继续；计满 10 次正常早退后记一次暂停，之后每 5 次一次，暂停时发"继续"；暂停罚与 v1 相同（每实例最多扣一次）。接续、提醒、续接 ID 都在 `continuation` 字段里留证。这一套与 v1 用户决定一致（plan §14.1：不接续"完全不对等"，早退的重跑或续跑），不再把早退记 0。若接续因会话丢失无法进行（`no_conversation`）、报告不可读或 API 流错误，该实例作废重跑。
- **排程**：顺序执行，不并行。按强度分段：先 high 全部 20 个实例，再 medium，再 xhigh（额度不足时先保 high，用户指示）；每个强度内场景顺序 CA → CS → CStd → SR，每场景 5 个实例连续。Hydrogen 的三档因此在同一两天内跑完，段间时间漂移由报告注明。每次启动前读 Gemini 组额度（`~/.claude/statusline/limits/antigravity-gemini.json`，必要时 `limits.py --refresh agy`），5h 或周剩余低于 30% 不启动；停下写 `progress.md`。
- **凭据与外送内容**：agy 用已登录的 Google 账号，不涉及本工程凭据。送出的内容只有公开 ARW 快照物化的场景根和提示。送出前对每个单元的场景根与提示做隐私扫描：用户名、`/home/`、邮箱、`sk-`/Bearer/JWT/PEM 样式、`.private.toml`、`.credentials`；有命中不送。
- **逐实例核对**（实例有效的条件，对应 v1 §10 S5 和 claude_scenario.checks）：
  1. 请求的模型 id 即 stream `init.model`（agy 不返回别名后的真实 id，这一项只能核对请求回显，是弱核对）；
  2. 没有搜索、网页、浏览器、子 agent 工具调用（`search_web`、`read_url_content`、`open_browser_url`、`browser_*`、`invoke_subagent`、`define_subagent`、`manage_subagents`、`browser_subagent`、`run_workflow`、`generate_image`），正文里出现 URL 或引用也标出，并按格报告作废率。agy 的设置里没有禁用这些工具的办法（已试 `disabledTools` 键，报未知设置；`permissions.deny` 写工具名不起作用，模型照样调用了 `search_web`），所以改为事后检测：出现任一次调用，该实例作废重跑，计入重跑次数并在报告里列出；
  3. 结束方式正常：完整交付，或到 T 的硬停（`finished_reason print_timeout`）；其他 ERROR（API 流断 EOF、重试耗尽等）作废重跑（与 v1 "API 或传输错误无效"一致；hydrocmp 里 `sr-5-rm` 那种 EOF 但报告完整的，这里也作废）；没有 `denied_actions`；
  4. 撞额度（429、限额错误）作废，不计入尝试次数，等窗口恢复；
  5. 实例要么完整交付（最终消息恰为 `{"status":"ready"}` 且报告非空），要么被硬停（到 T）；只有硬停时报告缺失或模型侧错误才按 v1 "模型失误"记 0；
  5b. 硬停之后立刻快照报告，并核对之后文件不再变（agy 进程在 bwrap 的 pid 命名空间里，随会话结束一并退出）；
  6. 工作目录里报告目录之外的改动（`unexpected_changes`）只记录，由会话检查判定，影响评分或越出工作目录才作废。
- **每格尝试上限**：与 v1 相同，每格（强度 × 场景）最多 8 次尝试，撞额度的不计。因搜索/子 agent 作废的比例超过 30%（一格 8 次里超过 2 次，或全部 60 个实例里超过 18 个；命令被拒导致的作废也算入这一线）时停下报告：模型会用搜索说明该配置在这个 harness 里不可能在无搜索条件下测。

## 4. 与 v1 的不同及对可比性的影响

| 项 | v1 | 本补测 | 影响 |
|---|---|---|---|
| harness | Codex 0.163.0 + ARW 运行时，或 Claude Code 2.1.303 无头 | Antigravity `agy`，自带 agent 循环和约 10K token 的系统提示（实测空提示输入 10.2K token）、自带工具集 | 最大的混杂：系统提示、工具、上下文管理不同；harness 本来就是 v1 配置的一部分（plan §1），但 Hydrogen 没有"另一个 harness"的对照。Hydrogen 与 Opus/Sol 的差不能全归于模型 |
| 搜索 | 全部关闭 | 无法关闭，事后检测，出现即作废重跑 | 无搜索的实例仍满足 v1 条件；作废率是选择偏倚的指标，报告给出 |
| 子 agent | 不可用 | 同上（`invoke_subagent` 等检测） | 同上 |
| 时限提醒与硬停 | Codex：ARW 在 T 前发高优先级提醒；Claude Code：PostToolUse hook 注入；到 T 硬中断 | 提醒经"到点结束当前轮、同会话发提醒原文"送达（§3）；到 T 硬中断；每段扣启停 7 秒 | 提醒在轮边界而非轮中注入，等同 Codex 的"打断生成后送达"；Hydrogen 的 T 来自其 G，P4 实测 341–401 秒，可能较紧，报告给出用时占时限比例和撞 T 的实例数 |
| 早退接续 | ARW（Codex）与 `execute_continued`（Claude Code）在早退时接续并计暂停 | 同 `execute_continued` 的逻辑，用 `--conversation` 续接，ARW 原文指令，第 10 次起每 5 次一次暂停（§3） | 实测续接可用；暂停点和扣分与 v1 一致 |
| 写权限 | Claude Code：只可写报告目录；Codex：`:read-only` + 报告目录 | bwrap 内整个工作副本可写（报告目录之外的改动记 `unexpected_changes`，会话检查判定）；其余路径不可写 | 模型可能改动受审文件；事后核对 |
| 读取范围 | Claude Code 只读工作目录；Codex 可读宿主文件（凭据除外） | bwrap：只见工作副本、系统只读目录和 agy 自己的私有状态；OAuth token 文件对进程可见（agy 刷新 token 必需，v1 的 Claude/Codex 同样要读自己的凭据），模型自己拒绝过读取它但无技术拦截 | 答案键、用户文件、别的会话不可见（已实测）；token 可见写入 caveats |
| 模型 id 核对 | API 返回的 id 与绑定逐实例比对 | 只有请求回显 | 弱核对，记入 caveats |
| service tier | 逐实例记录 | agy 不提供 | 记未知 |
| token | Codex rollout/relay、Claude result usage | stream 每步 `usage`：`input_tokens`（未缓存）、`cache_read_tokens`、`output_tokens`（含 `thinking_tokens`）按步求和 | 输出 token 含思考；与 Claude/Codex 的口径一致（均含思考） |
| 费用 | Anthropic/DeepSeek 有 `cost`，其余无 | 无 `cost`（订阅配额；报告另给占 Gemini 组 5h/周额度的百分点） | 导出里 `cost` 为 null |
| 时间 | 2026-10-20 至 11-02（v1）；luna 补测 10-22/23 | 2026-11-14 起，晚约三周 | 服务端漂移不可排除；agy 与模型版本在 v1 时不存在，不能做同期对照；报告注明 |
| 盲裁 | 单名 Opus high，冻结 brief，锚点 + 合成负例 | 同；裁决调用隔离（不加载用户级配置、记忆、hooks：`--setting-sources ""`，显式 `--model claude-opus-5-5 --effort high`，cwd 为 `<ADJ>`）；v1 的 2.1.303 副本已不在，用现有 claude 版本，记为偏离，由锚点门槛兜底；Hydrogen 是新的来源 family，按 v1 §6.2 的规则第一批裁决后从 Main 可执行检查过的题里分层抽样（种子 20261021）登记新锚点并回查第一批，一致率按 family 报告 | 门槛照旧（≥ 90%，合成项全对）；Hydrogen 的写法没有锚点时只能证明裁决者对别家写法没漂移，所以补锚点 |
| 工具 | v1 的 bench_records / benchmark_summary / benchmark_export 只认 Codex 与 Claude Code 的记录 | 记录适配（`hydrogen_records.py`，字段同 `claude_record`）和导出由本补测脚本生成；计分和盲裁用冻结工具 | 偏离用户 10-23 的两条决定（只接受带 `generator` 的工具生成 summary；配置编号只有 `CONFIG_TABLE`）：本补测的导出文件单独存放，**不并入页面数据**，是否把 antigravity 臂和配置 30–32 加进 `bench_records` / `CONFIG_TABLE` 并重新生成合一文件，交 Main / 用户决定，写进报告 |
| 会话检查 | 便宜模型读过滤后的 actions.md | 用 stream 的工具步骤生成同样的 actions.md，由 Sonnet 无头检查；必做 | 见报告 |

## 5. 统计口径

照 plan §5，逐场景逐配置：n、均值、SD、t 分布 95% 区间、负分数、最小、中位、`rawScore`、格式罚与修复数、耗时与占时限比例、token、工具调用、与页面现有配置的对照表（页面数据取自 `reports/v0.1.45/multi-model-benchmark/benchmark-results.json`，只读）。**不做预登记比较**（phase 4 配置 `inComparisons: false`），对照表只列各配置的均值与区间，不做统计检验（用户 10-22 对 phase 3 的决定），不写"高于/低于"。

## 6. 盲裁（plan §6.2 原样）

- 全部配置跑完（或停在某处）后统一盲裁；池按场景构建（`blind_pool build`），混入锚点（注册表 `anchors/<场景>.json`，每池 12 个）和全部合成项；裁决者 Opus high（`claude-api -p`），冻结 brief，只替换 `<ADJ>` 和 `<名>`，其后附 §14.1 的公平性说明。
- 通过门槛：锚点一致率 ≥ 90%，且合成项全部判对，且两类都存在；不通过整池重裁，不写入。`supported` 决定和有争议的 `unsupported` 进复核清单。
- 沿用已有决定：只对内容指纹相同的候选。

## 7. 计分与导出

- 计分：`bench_score`（r8.4）对每个实例，输入为本补测的归一化记录（字段同 `bench_records.claude_record` 输出，`arm: antigravity`，`harness: antigravity`，`style_family` 取 §4 所述）；记录的 `time_limit_seconds` 是实例实际的 T。
- 导出：配置 30–32（`configNumber` 30、31、32；`kind: phase4`；`inComparisons: false`），实例 `stage: phase4`，`selection.mainStatistic` 为真表示进它们自己的主统计（全部有效实例，不做前 5 个的截取，同 phase 3 的处理）；`cost: null`；`tokens.source` 写 "agy stream usage"；其余按 `export-format.md` 白名单复制，发布安全自检同样适用（用本补测的扫描脚本重现 `benchmark_export` 的检查项）。

## 8. 规模与耗时

- 额度依据：hydrocmp（11-14 同模型 high，15 个会话）用掉 Gemini 组 5h 37.1 点、周 11.2 点；本补测的 6 次 P4 探针实测只用周额度 1 点左右。实例按会话估约 0.75 周点：每档（3 场景 × 5 + SR 的第二线程）约 19 点，xhigh 估 25–35 点。周额度现剩 87%，扣 30% 停线后可用约 57 点：high、medium 够，xhigh 可能停在中途；周额度重置时刻读 `limits/antigravity-gemini.json` 的 `resets_at`，写进 `progress.md`，由 Main 决定等待。5h 窗口 300 分钟，剩余低于 30% 时停下等恢复。**先保 high**，再 medium，再 xhigh。
- 墙钟：每会话 2–10 分钟，75 个会话 + 重跑 + 续接约 7–10 小时纯运行，加等窗口，可能超过一天；本次无头会话在额度停线处写 `progress.md` 结束，由 Main 续开。
- 磁盘：每次 `prepare` 约 14 MB 写入 `/tmp`；实例结束后删除 `prep/arw` 里除 `.tmp`（计分要放回的保留数据）之外的内容和工作副本，保留记录、流、报告、agy 私有状态（含会话记录，约 1–2 MB）；总计远低于 100 MB 闸线。无大下载。

## 9. 步骤与停止条件

1. 复核：本计划经 Opus high 独立审查，按意见改完才开跑；审查认为有不可比的硬伤则停下写报告，不跑。
2. 零模型核对：原 plan 物化不出来（缺 Codex 0.163.0 副本），所以不做"两个 plan 对照"；改为用临时 plan 物化，核对场景根字节数与 v1 记录一致（CS 152919、CStd 142529 字节，SR/CA 的文件数，`check_materialize.py` 已通过），并与 v1 留存的 Claude 臂 `prompt-h*.md`/`prompt_sha256` 在路径归一化后比较提示；`codex` 字段不进 `prepared.json` 的 identity 字段（实例的 `prepared.json` 里查）；staged 提示不含家目录；隐私扫描通过。
3. P4 探针（CS、CStd 各 3 档，外加每档 1 次基线）算 T：β 的输入 token 取 `input_tokens + cache_read_tokens`，G 取最长输出那次响应的输出 token（含思考）÷ 该次的 `duration_seconds`；离同类（同一模型三档）3 倍以上就重测一次；记录三档 `thinking_tokens`。开跑前的预检（不计入）：CA 和 Code Spec 各跑 1 个实例（`a0`），确认白名单与沙箱下不被大面积拒绝。
4. 运行（§3 排程）。
5. 全部运行后：盲裁 → 计分 → 导出 → 报告。
- **停止条件**：额度线（§3）；`--effort` 未生效；搜索/子 agent 作废比例过高（§3）；任一单步写盘或下载 ≥ 100 MB；agy 登录/权限问题；连续 3 个实例因同一原因作废（harness 故障，写报告，不改规则硬跑）。
- 完成条件：每格 5 个有效实例，且全部盲裁、计分完成，报告写成。停在中途时 `progress.md` 写明已完成的格、下一个单元和续跑命令。


## 10. 独立审查（2026-11-14，Opus high 无头，原文 `.tasks/common/hydrobench/data/review/review1.md`）

结论"改后可跑"，无不可比的硬伤。已按意见改动：早退接续和提醒（§3，实测可用）；命令白名单扩到只读等价集合并预检 CA/CS（§3、§9）；P4 取数（stdin 输入、β 含缓存输入，§9）；跨会话记忆、读取范围实测并以 bwrap 隔离（§3）；agy 版本固定（§2）；临时 plan 的核对方法（§9）；盲裁调用隔离与新 family 锚点（§4 盲裁行）；计分前保留 `prep/arw/.tmp`（§8）；删除 Welch p 值（§5）；周额度算术（§8）；表中的笔误（配置数、场景名、实例数算式）。未采纳的一条：把 antigravity 臂并入 `bench_records` / `CONFIG_TABLE`（工具与页面都在本任务范围外），按 §4 工具行单列。本文中的"phase 4"指补充测量阶段，不是 v1 plan §9 的"阶段 4（报告与独立审查）"。`--print-timeout` 自进程启动计时，耗时口径写进导出的 `durationBasis`。
