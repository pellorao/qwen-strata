# 多模型 benchmark v1 运行计划（定稿，待冻结）

2026-10-19 定稿。依据：用户决定（`docs/plan.md`「多模型 benchmark」，三轮答复）、方案稿与独立审查（Opus high）。本计划按[运行计划](../../.claude/skills/run-plan/SKILL.md)的结构写成。独立审查（硬约束 1「重要决策」）已完成，意见和处理记在 §13。三份盲裁 brief（Code Spec v5、Code Standards v5.1、Spec Readiness v4.3）已按独立核对修改，2026-10-19 在看到任何 benchmark 输出之前冻结（[versions.md](../reviewer-suite-v1/versions.md)）。顺序固定为：在看到任何 benchmark 输出之前冻结 brief → 用冻结 brief 做单名 Opus 盲裁（§6.2；用户 2026-10-19 决定不改双裁）。

## 1. 目的

在同一套四个 ARW reviewer 场景上，测量各模型配置作为 reviewer 的表现，包括分数、耗时、token、工具调用数和费用。结论用于选择后续工作的后端，并说明本地 Strata（IQ3_XXS）处在什么位置。

- 只报分场景的原始结果，不算比值、不算综合分、不排名次（用户 2026-10-19，D7）。
- 不回答"哪个 harness 更好"。harness 是配置的一部分；Strata 和 DeepSeek 两边都跑，是为了让 harness 的影响能被看见（Q2）。

## 2. 配置清单

27 个配置，每个配置跑 4 个场景，每个场景 5 次，共 540 个有效实例。Spec Readiness 的每个实例含 RM 和 AP 两个根线程。

| # | harness | 模型 | 强度 | 凭据 | 基础提示 | guardian |
|---|---|---|---|---|---|---|
| 1–3 | Codex 0.163.0 + ARW | `gpt-6.1-sol` | low / medium / high | ChatGPT 套餐登录 | 无 | 原生默认（codex-auto-review） |
| 4–6 | Codex 0.163.0 + ARW | `gpt-6-luna` | low / medium / high | ChatGPT 套餐登录 | 无 | 原生默认（codex-auto-review） |
| 7–9 | Codex 0.163.0 + ARW | `deepseek-flash` | low / medium / high | `DEEPSEEK_API_KEY` | 无 | 无原生默认，用同模型 low |
| 10–12 | Codex 0.163.0 + ARW | Strata `qwen3.8-flash-next-iq3_xxs` | low / medium / high | 前端租约 | 启动提示与压缩提示 | Strata 自身（512/1024） |
| 13–15 | Claude Code 2.1.303 无头 | Opus（`opus`） | low / medium / high | 订阅 | 无 | 无（dontAsk） |
| 16–18 | Claude Code 2.1.303 无头 | Sonnet（`sonnet`） | low / medium / high | 订阅 | 无 | 无 |
| 19–21 | Claude Code 2.1.303 无头 | Haiku（`haiku`） | low / medium / high | 订阅 | 无 | 无 |
| 22–24 | Claude Code 2.1.303 无头 | `deepseek-flash` | low / medium / high | `DEEPSEEK_API_KEY` | 无 | 无 |
| 25–27 | Claude Code 2.1.303 无头 | Strata `qwen3.8-flash-next-iq3_xxs` | low / medium / high | 前端租约 | 启动提示（服务端）与压缩提示（PreCompact） | 无 |

- 模型 ID 以 API 实际返回的为准，逐实例记录：Codex 的 API provider 由 relay 记录，Claude Code 从 stream 的 `model` 和 `modelUsage` 读取。别名 `opus`、`sonnet`、`haiku` 在开跑前解析成具体 ID，写进绑定，正式运行的 `--model` 直接传具体 ID。
- 匹配规则（用于 S5）：返回的 ID 与绑定 ID 完全相同，或是绑定 ID 后接日期后缀（`-YYYY-MM-DD` 或 `-YYYYMMDD`），算一致；其余算不符。ChatGPT 后端若不返回模型 ID，记为未知，不触发 S5。Strata 不适用。
- DeepSeek 在两个 harness 上都写死为 `deepseek-flash`（官方 2026-10-19：当前为 DeepSeek-V4.1-Flash-1017）。在 Claude Code 上，`claude-opus-*` 这类名字会被端点映射到 v4-pro，所以 runner 把所有模型变量都设为 `deepseek-flash`，并拒绝 Claude 名字（`tools/reviewer/claude_headless.py` 的 `deepseek_model`）。
- 端点：
  - DeepSeek 在 Codex 上用 OpenAI 格式 `https://api.deepseek.com`（Responses，`wire_api = "responses"`），在 Claude Code 上用 Anthropic 格式 `https://api.deepseek.com/anthropic`。
  - OpenAI 用 Codex 内置的 `openai` provider（ChatGPT 后端），`openai_base_url` 只是指向本地 relay。
- 不用 ultra、xhigh、max。ultra 会派子 agent，ARW 拒收；Strata 的 xhigh、max 预算与 high 相同。

### 2.1 Strata 三档参数在两个 harness 上的映射

数据来源：`src/frontend.py`（`EFFORT_BUDGETS`、`apply_reasoning_defaults`、`apply_messages_budget`）、`scripts/wsl/qwen-agent`（`MAX_OUTPUT`）、`config/deployments/rtx3080ti.json`（部署默认 high 8192/24576）。

| 强度 | Codex：请求 | Codex：前端填入（思考上限/总输出） | Claude Code：请求 | Claude Code：前端得到的思考上限 |
|---|---|---|---|---|
| low | `reasoning.effort = low` | 2048 / 8192 | `output_config.effort = low`，`thinking: adaptive`，`max_tokens = 8192` | min(2048, 8192 ÷ 2) = 2048 |
| medium | `reasoning.effort = medium` | 4096 / 16384 | `output_config.effort = medium`，`max_tokens = 16384` | min(4096, 16384 ÷ 2) = 4096 |
| high | `reasoning.effort = high` | 8192 / 24576（部署默认） | `output_config.effort = high`，`max_tokens = 24576` | 8192（部署默认） |

- 两个 harness 的思考上限和总输出完全相同。guardian 请求（只在 Codex 上）不论强度，一律 512/1024。
- 窗口和压缩点两边都用部署档位 206584 / 150000。Codex 由 catalog 取档位；Claude Code 由 qwen-agent 的环境变量 `CLAUDE_CODE_MAX_CONTEXT_TOKENS` 和 `CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE` 设定。
- 已用无模型方式核实（2026-10-19，`.tmp/bench-final-1019/claude-gate-*-mock`）：Claude Code 2.1.303 对 `qwen3.8-flash-next-iq3_xxs` 和 `deepseek-flash` 这类未知模型名照样发送 `output_config.effort` low、medium、high，以及 `thinking: {type: adaptive}`。表中 `max_tokens` 那一列来自 qwen-agent 的环境变量。mock 门没有设这个变量，所以 mock 请求里是 32000。
- 其他模型的三档：
  - OpenAI 在 Codex 上用 `reasoning.effort`，原生含义；Anthropic 在 Claude Code 上用 `--effort` 和 `CLAUDE_CODE_EFFORT_LEVEL`。
  - DeepSeek 在两个 harness 上是否真的区分三档还未验证，见 §8 探针 P1。各厂商的"high"含义不同，列为混杂。

## 3. 固定条件

开跑前逐项核对实际加载的值并写进绑定，执行窗口内不改。

- **版本**：
  - Strata 开跑前可以升级（D12），第一个模型实例开始后固定，直到最后一个实例跑完。
  - Codex 0.163.0（用户 2026-10-19 决定，取代 0.162.0）和 Claude Code 2.1.303 另装 benchmark 专用副本，记录 SHA，不动用户日常安装和它们的自动更新。Codex 副本由 `native_cli_binding`（`CODEX`、`pinned_codex`）固定：安全门每个会话、`arw_measure` 未写 `native_cli` 的 selection 都用它，启动前核对 SHA 和版本，不再用 PATH 上的 `codex`（用户日常安装已改为 `~/.codex/packages/standalone` 下自动更新的版本，位于 G7 deny-read 范围内）；Claude Code 副本用 `--claude` 传给 `claude_headless` 和 `claude_gate`，两个 CLI 都拒绝运行版本不是 2.1.303 的二进制，并把路径和 SHA 写进绑定（`claude_headless.pinned_binary`）。
  - Claude Code 副本在核对版本后跑一次 `tools.ops.claude_compact_probe`（部署规则），否则 Strata 臂的压缩点可能退回到窗口 − 23000。
  - 已安装（2026-10-19，阶段 0），目录只读，不在任何 PATH 上：
    - Claude Code：`/home/pello/.local/share/qwen-bench/claude-code-2.1.303/claude`，sha256 `375988f457756524234695cf2d8f64ace99c5f68682e47ea24862a843c191450`。与官方 2.1.303 发布清单（manifest.json，linux-x64）的 checksum 一致；从日常安装的同一版本复制，未另行下载。`--claude` 传这个路径；运行环境照旧 `DISABLE_AUTOUPDATER=1`。compact probe（`--claude` 指向该副本，`--repeat 3`，两种方式 × 阈值 ±100）12 格全部通过：149.9K 不压缩，150.1K 压缩后继续。
    - Codex：`/home/pello/.local/share/qwen-bench/codex-0.163.0/node_modules/@openai/codex/`，由 npm registry 的 `@openai/codex@0.163.0` 与 `@openai/codex@0.163.0-linux-x64` 两个 tarball 解出（sha512 与 registry integrity 一致，包里没有安装脚本，未运行任何脚本）。`native_cli` 绑定的 executable 为其下 `node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex`，sha256 `399ff69c431c066e40de318fba45c2b07f45a76b19939d247ee4828fc70c4215`；vendor 目录 43 个文件与用户日常安装的 0.163.0（standalone）逐字节相同。
    - 0.162.0 副本（`codex-0.162.0/`，sha256 `50ed828f…`）保留到 #10–12 的 0.163.0 证据全部入库，之后可删；0.162.0 上的零模型证据只作历史。
    - 0.162.0 → 0.163.0 的相关变化（release notes 与零模型核对，2026-10-19）：内置 catalog（`debug models --bundled`）逐字节相同；原生压缩提示仍为 `ab0c334d…`；mock 门请求里模型可见的工具和输入（路径归一化后）与 0.162.0 相同，rollout 的 `session_meta.runtime_workspace_roots` 结构不变（ARW 补丁 `codex-0.162-workspace-roots.patch` 仍适用）。新默认开的特性：`cli_daybreak`（eligible OpenAI 账号的 background turns 用 Daybreak）、`api_key_cyber_access_programs`、`code_mode_interrupt`；命令环境新增 `CODEX_THREAD_ID`、`CODEX_TOOL_CALL_ID`（关联用，非凭据）；冷 resume 恢复线程自有的权限快照；Guardian Decisions 在默认 openai provider 下可回退到 `OPENAI_API_KEY`（ARW daemon 环境已去掉 `OPENAI_*`）；`async_compaction` 新增但默认关。
- **场景与评分**：
  - 场景版本：Code Spec v5（修订 38）、Code Standards v5.1（修订 25）、Spec Readiness v4.3（修订 46）、Commit Audit v3（修订 24），各自的冻结源 manifest 见 [versions.md](../reviewer-suite-v1/versions.md)。
  - 评分用 r8.3，格式罚基准用 `format-baseline.json` 的现行登记。测量说明（`measurement-note*.txt`）的 SHA 写进绑定。
  - 计分只经 `arw_native.mjs` / `single_scenario_score`。全部跑完后按最终规则统一重评一次。
- **时限**：
  - Spec Readiness 和 Commit Audit 用 ARW 原版：55 分钟提醒，60 分钟中断。
  - Code Spec 和 Code Standards 用阅读量时限公式 T = B ×（1/P + k/G）/ β（[scenario-design.md](../reviewer-suite-v1/scenario-design.md)），P、G、β 取每个配置自己的值。每个配置在这两个场景的批次前先跑一次短探针，测出 P、G、β。
  - 报告给出每个配置实际用时占时限的比例。API 模型的 P、G 含网络和首 token 延迟。
- **基础提示**（D4，硬约束 3 的 benchmark 例外）：
  - 启动提示和压缩提示只给 Strata，SHA 绑定照旧：启动提示 `5f9efc02…`，去掉防循环段后加载；压缩提示 `3856cb62…`。
  - API 模型都不接入：Codex 的 selection 写 `startup_instructions: false` 和 `project_compaction_instructions: false`；Claude Code 传 `--no-startup-prompt --no-compact-prompt`。
  - 逐实例核对：API 臂的记录必须是 `startup_instructions.enabled == false`、`compact_prompt_sha256` 为空，Strata 臂必须是两份 SHA 与上面一致；不符的实例无效。
  - 场景提示只追加，与 Strata 相同。
- **搜索全部关闭**（D5 最终，2026-10-11 规则在 benchmark 期间豁免）：
  - Codex：所有 selection（包括 Strata）都写 `web_search: "disabled"`。安全门在请求里看到搜索工具即判失败（`web_search_tools`）。正式实例逐个检查 rollout 中 `web_search_call` 为 0。
  - Claude Code：`--tools` 不含任何 web 工具，同时 `--disallowedTools WebSearch,WebFetch`。`claude_gate` 检查请求和 init 事件中都没有客户端或服务端搜索工具，并逐实例统计 `server_web_requests`，必须为 0。
- **service tier**（D14）：
  - 一律 default。Codex 用 `serviceTier: default`（mock 请求显示，default 时 Codex 不发送 `service_tier` 字段）；Claude Code 不传。
  - 实际返回值逐实例记录：Codex 的 API provider 由 `tools/reviewer/api_relay.py` 记录（`service_tier_returned`）；Claude Code 从 stream 每条 assistant 消息的 `usage.service_tier` 读取（`service_tiers`）。Strata 不适用。
  - 只有实际返回了 tier、且不在 {default, standard} 内时，才按停止点 S5 处理。没有返回（`not-returned`）的记为未知，照常计分，在报告里注明。
- **guardian**（D6）：OpenAI 用原生默认 codex-auto-review；DeepSeek 用同模型 low（selection 写 `guardian_model`）；Strata 用服务端默认。Claude Code 的 dontAsk 没有 guardian，列为混杂。
- **权限**：
  - Codex 路径沿用 `:read-only` 加报告专用父目录写授权，审批走 on-request / auto_review。
  - 收紧（G7，2026-10-19 已实施，待用户复核）：所有 Codex 臂（包括 Strata）对 `~/.claude/.credentials.json`、`~/.codex` 整个目录（ChatGPT 登录按用户 2026-10-19 决定用默认的 `~/.codex`；selection 另写的 `auth_home` 同样拒读）和 `project.private.toml` 一律 deny-read。原因：`:read-only` 能读这些文件，API 臂会把读到的内容发往外部服务。这偏离 reviewer-suite「不额外收紧」，规则的豁免已同时写入。
    - 实现：`providers.credential_deny_paths` 列出路径（不打开），`arw_measure` 写进 runtime 的 `denyRead`；`arw_native_setup.mjs` 在每次 `open` 时把这些路径以 `none` 加进 ARW 生成的 Reviewer profile（不改 ARW 代码和它保存的设置，接续线程同样生效）。安全门也用同一份列表，外加合成 HOME 下的合成目标。
    - 零模型验证（`.tmp/bench-stage0-1019/g7/`）：Strata、DeepSeek、ChatGPT（合成登录、netns）三种 mock 门都通过，四类合成目标和链接进 CODEX_HOME 的登录文件全部 `denied`，原生沙箱写边界 8 类照旧拒绝；场景根外的合成答案键和工程 README 仍可读（`:read-only` 原样）。读探针遇到任一目标可读即判门失败（`deny_read_pass`）。
  - Claude Code 路径用 `claude_headless` 的隔离参数：`--setting-sources ""`、`--restricted`、dontAsk、只授权写路径、Bash 沙箱只读工作目录且无网络、`CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1`、工作目录在 `/var/tmp/qwen-claude`。DeepSeek 和 Strata 臂另用全新的 `HOME` 和 `CLAUDE_CONFIG_DIR`。
- **凭据**：
  - ChatGPT 登录：每次运行的全新 CODEX_HOME 里只放一个指向 benchmark 专用登录文件的符号链接，运行结束时移除；Codex 刷新登录、把链接换成真文件时，原样移回（`providers.link_login` / `release_login`）。工程从不打开登录文件。
  - 同一份登录在同一时刻只给一个 Codex 运行用，所以 OpenAI 的 6 个配置串行，不并行，以免 refresh token 轮换时互相作废。
  - DeepSeek key 只在进程环境里，由 Codex 的 `env_key` 读取，或作为 Claude Code 的 `ANTHROPIC_AUTH_TOKEN`；命令环境里会被去掉。
  - 所有凭据变量（`DEEPSEEK_API_KEY`、`BENCHMARK_OPENAI_API_KEY`、`STRATA_API_KEY`、`STRATA_REMOTE_PASSWORD`），以及名字形如 `*_API_KEY`、`*_TOKEN`、`*_SECRET` 的任何变量，在每个 Codex 臂（包括 Strata 臂）的命令环境里一律排除；ARW daemon 的环境也去掉本次 provider 以外的这类变量，`STRATA_*` 除外（Strata 路径要用 `STRATA_API_KEY`）（`providers.shell_exclude`、`process_environment`）。通配排除防止以后换变量名时漏掉（用户 2026-10-19 把 DeepSeek key 设为 `DEEPSEEK_API_KEY`）。Claude Code 臂本来就只给最小环境，DeepSeek key 只作为 `ANTHROPIC_AUTH_TOKEN` 交给 Claude Code 进程。审查前的 ChatGPT mock 门显示，全局设置的 DeepSeek key 在 OpenAI 臂的命令环境里可见（`shell_env_key: VISIBLE`）；修复后用 DeepSeek 变量名作 canary 重跑，结果为 `absent`（`.tmp/bench-final-1019/codex-chatgpt-mock-m1`）。
  - 需要恢复的运行（`recovery-required.json`）不归还登录，因为恢复还要用它；恢复完成后由恢复步骤调用 `release_login`。
- **API 模型的 catalog**：开跑前把 Codex 0.163.0 内置 catalog（与 0.162.0 逐字节相同）中 `gpt-6.1-sol`、`gpt-6-luna` 的条目，以及 DeepSeek 条目（按 ARW `deepseek.md` 写），存为 `benchmarks/multi-model-v1/catalogs/` 下的冻结文件并记 SHA。注意 catalog 里 luna 的默认档可能是 priority，`serviceTier` 显式写 default。
- **排程**：同一场景内，配置按块交替，每轮反转顺序；Strata 的同一配置连跑，换配置时冷加载并预热（测量规则）。付费模型固定 5 次；Strata 在 GPU 空闲时加测到 10 次，目标次数事先定为 10，主表只用预登记的前 5 次。

## 4. 混杂与适用范围

报告逐条列出以下各项，结论只在这些条件下成立。

1. **场景按 Opus 标定**：加难时确认的是"Q3 低、Opus 命中"；答案键经 Opus 审计；Opus 同时担任参考和裁决者。所以 Opus 的位置可能偏高，Opus 的绝对分不是上限。Commit Audit v3 另给"含 / 不含难度因素题"两套分数。
2. **厂商与 harness 部分绑定**：OpenAI 只在 Codex 上，Anthropic 只在 Claude Code 上。只有 Strata 和 DeepSeek 两边都有，可以用来观察 harness 的影响。
3. **"强度"含义因厂商而异**：Strata 三档见 §2.1；DeepSeek 在 Claude Code 上可能不区分（P1）。
4. **基础提示只给 Strata**：注入位置不同。Codex 路径由服务端追加；Claude Code 路径由服务端追加启动提示，PreCompact hook 追加压缩提示。
5. **搜索全部关闭**，偏离 ARW 原生设置（2026-10-11 规则）。各模型都没有搜索，但这与 ARW 自己的结果不可直接比较。
6. **guardian 不同**：OpenAI 用 codex-auto-review，DeepSeek 用同模型 low，Strata 用自身，Claude Code 没有。
7. **窗口与压缩不同**：Strata 为 206584/150000，其他模型用原生设置（OpenAI catalog 272000）。OpenAI 用服务端压缩（零模型核实，见 §9 阶段 0）。Claude Code 路径的压缩提示只给 Strata。
8. **ARW 早停接续只在 Codex 路径**：Claude Code `-p` 没有接续。
9. **时限按各自的速度计算**：API 模型的速度含网络。服务端可能漂移，而执行窗口约一到两周。
10. **ChatGPT 套餐**：只报 token，不报金额。套餐的限速或路由可能与 API 不同。
11. **IQ3_XXS 参数来自 v0.1.42 调参**：benchmark 就在当前版本上跑。Haiku 的订阅额度扣减比例未核对，首次 Haiku 运行时记录前后用量。
12. **盲裁方式**（§6）：单名 Opus 盲裁，与场景标定同一模型（见第 1 条）。
13. **两个 harness 的读取范围不同**：Claude Code 的工具和 Bash 沙箱只能读工作目录；Codex `:read-only` 能读宿主文件（G7 只去掉凭据路径）。

## 5. 统计口径

- 逐场景、逐配置报告以下各项：
  - n、均值 ± SD、SE 与 t 分布 95% 区间、截断前 `rawScore`；
  - 格式罚 f 与修复处数；
  - 耗时（分钟，保留一位小数）、实际用时占时限的比例；
  - 三类 token（未缓存、缓存、输出）及其来源：Strata 取引擎日志，API 模型取 API usage，Claude Code 取 stream result；
  - 工具调用数；
  - 费用：Anthropic 按 API 等价美元并折算周额度；DeepSeek 按开跑当日的官方单价；OpenAI 只报 token；Strata 按测量规则的等效费用公式；
  - 实际返回的模型 ID 和 service tier。
- 逐实例表固定保留（测量规则）。不给比值、综合分和排名（D7）。
- 文字比较只用预登记的一组：同一 harness、同一强度下，Strata 对其他每个配置（Codex 3 × 3、Claude Code 4 × 3）；DeepSeek 和 Strata 各自的 Codex 对 Claude Code（2 × 3）。每个场景是一个校正族，共 27 个比较，Holm 校正，双侧 α = 0.05，Welch t 检验用 Welch–Satterthwaite 自由度；Strata 只用预登记的前 5 次。校正后显著才写"高于 / 低于"，其余写"未分出"。n = 5 对 5 时能分辨的差约 0.3（审查估算），报告写明这一点。表中全部数字照常给出。
- 墙钟耗时按阶段报告（门与探针、每个场景批次、盲裁、会话检查、计分），用于下次 benchmark 的排期。
- 实例无效、重跑和会话检查按测量规则与 reviewer-suite「会话检查」执行。会话检查交便宜模型（D9，reviewer-suite「会话检查」已写入例外）：它读过滤后的 `actions.md` 和 `flagged.md`（`inspect_session` 已对凭据值打码），被标记项和它判为可疑的实例再由 Main 复核。

## 6. 盲裁

### 6.1 占比评估（用户规则：不足 20% 维持单名 Opus；≥ 20% 改为 Sonnet medium + gpt-6-luna high 双裁，分歧和拿不准的交 Opus，先试点）

数据来源：`~/.claude/statusline/starts.log` 与 `headless-cost.log`（只读），以及已有报告。

- 每项裁决成本：
  - Opus：Commit Audit v2 共 4 次 `ca2-blind`，合计 $4.07，覆盖 558 项，约 $0.0073/项；Spec Readiness v4.2 两次合计 $3.01，覆盖 282 项，约 $0.0107/项。
  - Sonnet medium：约 $0.0035/项（试点）。
- 候选量：每实例约 25 项（CS 15–22、CStd ~26、SR 19–28、CA 30–34），每配置约 500 项，27 个配置约 13,500 项。加锚点、合成负例和第二轮 ×1.15 后约 15,500 项。

| 项（Anthropic 周额度，美元） | 低 | 中 | 高 | 依据 |
|---|---|---|---|---|
| 盲裁（单名 Opus） | 113 | 140 | 166 | 15,500 项 × $0.0073 / 0.009 / 0.0107 |
| Anthropic 模型运行（9 个配置） | 122 | 125 | 129 | Opus high 每配置约 $28（CS $1.34、CStd ~$1.0、SR ~$2.3、CA medium $0.95，每场景 ×5），medium 按 ×0.8、low 按 ×0.6，三档约 $67；Sonnet 约 $40–47（无实测）；Haiku 三档约 $15 |
| 会话检查（便宜模型） | 27 | 40 | 54 | 540 实例 × 每实例 $0.05–0.10 |
| 运行监督（便宜 worker，负载 0.25） | 20 | 50 | 90 | Strata 约 25 小时 GPU，API 运行由脚本驱动 |
| 后处理（脚本流水线 + 异常复核） | 130 | 175 | 220 | 540 实例 × 每实例约 0.6–1.0 分钟 Opus；前提是先写好汇总流水线 |
| 门、冒烟、探针 | 10 | 15 | 20 | Haiku 完整门、Opus 抽查、9 个 Anthropic 配置冒烟 |
| 审查与报告 agent | 30 | 45 | 60 | 本轮两名 Opus 审查及报告审查 |
| 合计（不含 Main 开销） | 452 | 590 | 739 | |

- 盲裁占比：中值 140 / 590 ≈ **24%**。极端组合下，最低为 113 /（113 + 其余各项取高 573）≈ 16%，最高为 166 /（166 + 其余各项取低 339）≈ 33%。
- Main 开销按 +15% 加到所有项上，不改变占比。
- 历史对照：已完成场景周期的启动估计里，盲裁约占三分之一。Commit Audit v3 正式周期中，两次 Opus 盲裁 $28.4 / 周期合计 $81.3 ≈ 35%；Spec Readiness v4.2 为 $22.0 / $65.6 ≈ 34%。那些周期的模型运行几乎都是 Strata，不占额度，所以只作上界参考。
- 总量：中值约 $680（含 Main 开销）。按 K = 0.086%/美元（`estimate.sh` 已校准）折算，约占周额度 58%，范围 45–73%，需要跨两个额度周期。最能省的是后处理脚本化和会话检查交便宜模型。

**结论（用户 2026-10-19 决定）**：维持单名 Opus 全量盲裁，加锚点和合成负例，不改双裁。按"占 benchmark 的 Anthropic 总消耗"算中值约 24%，超过 20% 规则的线，但用户按例外处理：双裁只省约 $55–58（约占周额度 5%），benchmark 结果影响后续全部工作，质量优先。README「现行决定」中"盲裁用 Opus，不用 Sonnet"一条继续有效。双裁试点、luna 裁决 runner（原 G6）和 brief 的 `unsure` 字段都不做。

### 6.2 单名 Opus 盲裁流程

- 裁决者为 Opus high（Claude Code 无头，与 Commit Audit v3 的盲裁相同），用冻结 brief，读被审代码的 view。brief 输出写死 `"adjudicator": "blind Opus high"`，与已冻结的 Commit Audit v3 brief 同一合同。
- 池按场景混合打乱，所有配置跑完后统一盲裁，隐去来源。每池混入锚点（10–15 个已有 Opus 裁决，取自同一场景版本的已裁池；Code Spec v5 正式池里来自 v4.7 的锚点不能用，它们引用的代码在 v5 已改正）和合成负例。锚点一致率按来源模型分组报告。
- 某个池的锚点一致率低于 90% 或合成负例有一个没识别，该池整池重裁并扩大复核（reviewer-suite「盲裁只裁有变化的部分」）。
- 所有 k = 4 档的反例误报一律双裁（评分 r8）；现行四个场景没有 k = 4 用例，不涉及。
- 裁决编排（拆池、合并）的费用计入 §6.1 的"后处理"一项。
- 第一个场景批次做完后，用实测费用重算一次占比，只用于下一个周期的额度预测。

## 7. 安全验收

默认模式的门没通过，就不启动同一运行层的能力测量。门的报告写入 `reports/v<Strata 版本>/multi-model-benchmark/safety/`。

- **每种 harness 一次完整门**（D10），每类探针 3 次：
  - Codex + ARW：`tools.safety.safety_gate --run`，在 Strata IQ3_XXS high 上跑。内容：原生沙箱 3、报告写入、同线程接续，15 个审批用例，再加读取探针（场景根外合成答案键、合成凭据文件、工程文件、假 key 在命令环境与 `/proc/<pid>/environ` 中的可见性）。plan 写 `web_search: disabled`。
  - Claude Code：`tools.safety.claude_gate --live --backend anthropic --model haiku --effort high --no-startup-prompt --repeat 3`，加一次 Opus 抽查。探针覆盖文件工具越界读、凭据、假 key、shell 读写越界、符号链接、路径穿越、硬链接、`/proc`、网络，以及隔离（canary、hook、MCP、技能、搜索工具）。
- **每个模型配置一次短冒烟**（27 次）：
  - Codex 的 API 配置：`safety_gate --provider-run`，plan 写 `smoke: true`，效果为 `authorized_read` 加 `unauthorized_delete` 各 1 次，读探针开启。
  - Claude Code 的 API 配置：`claude_gate --live --subset smoke --repeat 1`。
  - Strata 配置：Codex 侧用 `safety_gate --run` 的 smoke plan。Claude Code 侧见下文 G8。
- **零模型证据**（2026-10-19，`.tmp/bench-final-1019/`）全部通过：
  - Codex mock 门：ChatGPT 合成登录（netns 内）、DeepSeek key 模式、Strata。三者都是原生沙箱 9 类中 8 类拒绝，`new_sibling` 按已批准策略允许。搜索工具：DeepSeek 和 ChatGPT 的 plan 写了 disabled，为 0；Strata 第一次没传 `web_search`，请求里有 2 个搜索工具，加 `--web-search disabled` 重跑后为 0（`codex-strata-mock-nosearch`）。
  - M1 修复后的 ChatGPT mock 门（`codex-chatgpt-mock-m1`）：命令环境里的 DeepSeek canary 为 `absent`，`/proc` 祖先不可读。
  - Claude Code mock 门：DeepSeek low/medium/high、Strata low/medium，隔离通过，搜索工具 0。
  - 观察到：ChatGPT 登录下 Codex 照样走 `openai_base_url`，请求体用 zstd 压缩，mock 已支持。
- **Codex 0.163.0 上的 Strata 证据**（2026-10-19，#10–12，取代 0.162.0 上的 safety-gate-env-fix；报告 `reports/v0.1.45/safety-gate-codex-0.163.0/`）：
  - 完整门 `safety_gate --run`（rtx3080ti、IQ3_XXS、high、benchmark 副本 `399ff69c…`，plan 加 `read_probes: true`、`web_search: disabled`）：18 个观测全部通过；读探针 3 次 `deny_read_pass` 为真，搜索工具 0；56 个请求，引擎输出 90.8 tok/s（最低单例 71.5）；启动提示加载 `1cae169a…`；结束后 clean_unload，租约 free。
  - 三档冒烟（`smoke: true`，low / medium / high 各 1 次）：全部通过，请求里的推理强度与 plan 一致，guardian 都是 low；引擎输出 97.8 / 97.3 / 92.0 tok/s。
  - 零模型：三种 mock 门、审批路由 mock、原生压缩提示与远端压缩无残留都在 0.163.0 上重做并通过（§9 阶段 0）。
- **残余风险**：
  - Codex `:read-only` 能读宿主文件，包括链接进来的 ChatGPT 登录文件、`~/.claude/.credentials.json` 和 `project.private.toml`；mock 读探针显示 `credential_file: READABLE`。API 臂会把读到的内容发往外部服务，所以与 Strata 路径能读工程文件不同类。处理：G7 deny-read（§3「权限」），已实施，三种 mock 门用合成文件验证通过；live 门的读探针同样检查，没通过就不启动 API 臂。会话检查把 `auth.json`、`.credentials.json` 标为凭据材料，提取输出对 token 打码，作为兜底。
  - Claude Code 上的 Strata 臂原先没有 live 冒烟，因为 `claude_gate` 的 live 模式不支持 Strata。G8（阶段 0）已完成（2026-10-19）：`claude_gate --live --backend strata --host <id>` 领租约冷启动（安装默认、发布档），核对实际加载的启动提示，结束后停引擎并保存本次引擎日志段；smoke 子集 1 次在 rtx3080ti 上通过（见 §9 阶段 0）。
  - DeepSeek key 在 Codex 进程环境里。mock 门显示 `/proc` 祖先不可读，命令环境里没有这个 key。建议用户在 DeepSeek 控制台给 benchmark key 设单独的花费上限。

## 8. 开跑前的探针方案（只写方案，本轮不运行）

| 编号 | 问题 | 做法 | 规模与费用 | 判定 |
|---|---|---|---|---|
| P0 | ChatGPT 登录 + relay 是否可用；WebSocket 是否会回退到 HTTP；返回的 tier | 用户登录后，在 `gpt-6-luna` low 上跑一次 `safety_gate --provider-run`（smoke） | 2 个会话，少量 token | 判定条件：`relay.jsonl` 中请求数 > 0；`websocket_refused` 为 0，或被拒后 HTTP 请求成功；`service_tiers` 只有 default；`login-release.json` 为 `link-removed` 或 `refreshed-file-moved-back`。失败时先关 relay（`relay: false`），tier 记为未知，交 Main 定。同时记下这 2 个会话消耗的套餐用量，估算 6 个 OpenAI 配置 × 20 实例能否在套餐限额内跑完 |
| P1 | DeepSeek 在 Claude Code（Anthropic 格式）和 Codex（Responses）上，三档是否真的不同 | 固定一道需要多步推理的短题，每档 3 次单请求，直接发给端点，key 取自环境变量，不打印。Anthropic 格式发 `output_config.effort` 和 `thinking: adaptive`，与 Claude Code 2.1.303 实际发送的相同（mock 已核实）；Responses 发 `reasoning.effort` | 每个格式 9 个请求，约 $0.05 | 记录各档输出 token 中位数和思考 token（若返回）。high 的中位数不到 low 的 1.5 倍，且分布重叠，就判"该格式下三档无差别"。三档照跑（用户已定），但报告注明；是否删档属于测量目标，交用户 |
| P2 | Claude Code 上 DeepSeek 的搜索能否关掉 | 零模型部分已完成：mock 请求里没有任何客户端或服务端搜索工具。live 部分：用 `claude_gate --live --backend deepseek --subset smoke` 跑一次，再发 1 个不带工具、询问当日新闻的单请求 | 2 次 | 通过条件：stream 的 `server_web_requests` 为 0，响应 `usage.server_tool_use` 为空或 0，正文没有引用来源。之后每个实例持续检查 `server_web_requests` 为 0 |
| P3 | DeepSeek 的 Responses 端点能否支撑 Codex + ARW（自由格式工具 apply_patch、推理项回放、流事件） | 每个 provider 先跑 1 个预检实例（Commit Audit，不计入统计） | 1 实例 | ARW 正常交付报告即通过。出现 ARW 的 `deepseek-timeout`、`deepseek-no-final-report` 标签或协议错误，就停下这一组配置并报告 |
| P4 | CS/CStd 时限公式的 P、G、β | 每个配置在这两个场景的批次前跑一次短探针（[scenario-design.md](../reviewer-suite-v1/scenario-design.md) 的定义）：P、G 为该配置的读入、生成速度（token/s），β 为该场景输入的字节 ÷ 实际输入 token（字节/token），k 沿用场景已定值。Strata 取引擎日志；API 模型取 usage 与墙钟，P 含网络和首 token 延迟 | 每配置 1 次 | 写进绑定；探针失败或数值离同类配置 3 倍以上时重测一次，仍异常就交 Main |
| P5 | Claude Code 对 Anthropic 具体模型 ID 是否也发送 `output_config.effort` | 零模型：mock 门用具体 ID（如 Opus 的完整 ID）跑 low/high 各 1 次，查看请求体 | 0 费用 | 请求里有对应的 `output_config.effort` 即通过；不通过就改用别名并记录解析结果 |
| P6 | Strata 与其他运行同机并行时速度是否下降 | 预登记：每个 Strata 批次记引擎输出 tok/s，与无并行时的基线对照 | 不额外运行 | 低于 60 tok/s 按 S3 处理；与基线差超过 10% 时在报告里注明 |

## 9. 分批顺序与额度、GPU 预算

- **阶段 0（无模型，开跑前）**：
  状态（2026-10-19 阶段 0 worker）：除 API catalog 冻结、汇总适配层和本计划冻结外都已完成。
  - [x] 冻结三份 brief（08484d7；单名 Opus 输出合同，S3 诱饵条款经机械核对，没有再经 Opus 复核）；
  - [ ] 冻结 API catalog（本轮未做）；
  - [x] 安装 benchmark 专用的 Codex 和 Claude Code 副本，并跑 compact probe（见 §3「版本」）；
  - [x] G7 Codex 凭据路径 deny-read，并用合成文件验证（eeae71e；三种 mock 门通过；登录改用默认 `~/.codex` 后，deny 改为整个 `~/.codex` 目录，三种 mock 门重跑通过；Codex 0.163.0 副本上三种 mock 门重跑通过，`deny_read_pass` 为真、搜索工具 0；live 门的 deny 未实测；待用户复核）；
  - [x] G8 `claude_gate` 的 Strata live smoke：rtx3080ti、IQ3_XXS、high、benchmark 副本，smoke 6 个探针全部尝试且通过，隔离通过；加载 28.7 秒，会话 43.1 秒（stream `duration_ms`），7 个引擎请求，token 未缓存 8,519 / 缓存 61,477 / 输出 3,140（引擎日志），引擎输入 1,220.7 tok/s、引擎输出 88.9 tok/s，任务平均输入约 197.7 tok/s、输出约 72.9 tok/s（按 stream 时长近似，没有用 `review_work_time`）；启动提示加载 SHA `1cae169a…`（源 `5f9efc02…`，防循环段关闭）；引擎正常卸载，租约已归还；
  - [x] Code Standards brief 的 extraCharges / memberId 诱饵条款：按答案键 C22、C29 的 placement 核对后补上（独立核对建议 S3）；
  - [x] 重建物化目录，`check_briefs.py` 改为缺副本时自动物化，冻结前的机械核对全部通过；
  - [x] 盲裁 view 从冻结 fixture 构造（`tools/reviewer/adjudication_view.py`；Commit Audit v3 重建结果与先例逐字节相同）；
  - [~] 跨模型汇总报告流水线（含 G4 Code Standards 逐实例表）；
    - 汇总层已实现（2026-10-19）：`tools/reviewer/benchmark_summary.py`，输入每实例一条的归一化记录（JSONL），输出 `summary.json`/`summary.md`（§5 各项、27 个预登记比较、逐实例表，含 Code Standards），用合成数据测试。未做：把 Codex（`arw_measure`）和 Claude Code（`claude_scenario`）的运行记录与评分结果转成归一化记录的适配层，等两条路径的记录格式在阶段 1 冒烟中定下后再写。
  - [x] 核实项目压缩提示文件对 OpenAI 远端压缩是否生效（API 臂已关闭该提示，只需确认关闭后没有残留）；
    - 已核实（2026-10-19，零模型）：API 臂（`project_compaction_instructions: false`）渲染出的压缩提示只有 Codex 原生提示一个来源（sha256 `ab0c334d…`，policy `native-only-diagnostic`），不含工程压缩提示；Codex 0.162.0 的原生提示用 `verify_codex_compact_prompt` 重新采集，与存档的 0.160.1 版逐字节相同。内置 openai provider 加合成 ChatGPT 登录、在只有回环的网络命名空间里对 mock 手动压缩：Codex 走服务端压缩（`responses_compaction_v2`，向 `/responses` 发一次 `request_kind: compaction` 请求），请求里既没有原生压缩提示，也没有 `experimental_compact_prompt_file` 中的标记文字，两种设置的请求除 id、路径和时间外相同。所以 OpenAI 臂的压缩不受该文件影响；DeepSeek 臂走本地压缩，用的是与原生相同的提示。
    - 0.163.0 重核（2026-10-19，零模型）：原生提示重新采集仍为 `ab0c334d…`（426 字节，与 0.162.0、0.160.1 存档逐字节相同）；OpenAI 臂同样走 `responses_compaction_v2`，有无 `experimental_compact_prompt_file` 的两次请求都不含原生提示和标记文字，除 id、路径和时间外相同。
  - [ ] 本计划冻结（本轮按指示不冻结）。
  - 不做（用户 2026-10-19）：G6 luna 裁决 runner、Commit Audit v3 brief 的 `unsure` 字段。P5 改由另一 worker 做。
- **阶段 1（门与探针）**：两种 harness 的完整门 → P0–P2 → 27 次冒烟 → P3 预检。
- **阶段 2（按场景分批）**：每个场景的全部配置尽量在 48 小时内跑完，场景之间不并行。
  - 顺序为 Commit Audit v3（brief 已冻结）→ Code Spec v5 → Code Standards v5.1 → Spec Readiness v4.3。
  - 场景内的执行方式：
    - Strata 臂占用 GPU，与 API 运行并行；
    - OpenAI 臂串行；
    - Anthropic 臂按 `estimate.sh --can-start` 逐批放行；
    - DeepSeek 臂受用户给的花费上限约束。
- **阶段 3**：按场景单名 Opus 盲裁，再做会话检查和计分。全部完成后统一重评一次。
- **阶段 4**：报告与独立审查。
- **GPU**：Strata 6 个配置 × 20 实例。每实例实测 CS 9.5、CStd ~9.5、SR 15.9、CA 13.8 分钟（high；low、medium 按 ×0.8 估），合计约 22–25 小时，另加每批冷加载与预热约 2 小时。空闲加测到 10 次再加约 22 小时，与其他工作并行，不拖慢其他工作。
- **Anthropic 额度**：中值约 $680，占周额度约 58%（§6.1），跨两个周期。每个 Anthropic 批次开跑前都要跑一次 `estimate.sh --can-start`；判定不建议时，只推进 Strata、OpenAI、DeepSeek 的运行。
- **OpenAI / DeepSeek**：按历史每配置约 1.9–2.4M 未缓存、19–48M 缓存、0.4–1.1M 输出 token 估算。DeepSeek 9 个配置的金额按开跑当日单价计算，开跑前报给用户；OpenAI 只报 token。

## 10. 停止点

- S1：任一门未通过，就不启动该 harness 或该配置的能力测量，按"已知类型外的安全违规"处理（停止、保留现场、列入 decide）。
- S2：ARW 到达原版 10/5 次早退暂停点，停下交用户。
- S3：意外事件，如 Strata 引擎输出低于 60 tok/s、主机重启、租约异常。先记录，再尽量解决或绕过；受影响的实例作废后重跑。
- S4：`estimate.sh --can-start` 判定不建议，暂停 Anthropic 批次，其余照常。
- S5：实际返回的 service tier 不在 {default, standard} 内（未返回的不算）、模型 ID 按 §2 的匹配规则与绑定不符，或 `server_web_requests` > 0、rollout 中 `web_search_call` > 0，该实例无效，暂停该配置，查明原因后再继续。
- S6：DeepSeek 达到用户给的花费上限、ChatGPT 套餐限速持续超过 1 小时，暂停对应配置。
- S7：P3 预检失败，该 provider 的那组配置停下报告，其余配置继续。
- 完成条件：540 个有效实例全部计分，会话检查完成，报告经独立审查。

## 11. 需要用户动手的步骤

开始前由 Main 说明清楚并取得用户同意，再开始等待。

1. **Codex 登录**（使用 OpenAI 模型之前）：用户决定（2026-10-19）用默认的 `~/.codex` 登录，不建专用目录；selection 的 `auth_home` 写 `/home/pello/.codex`。每次运行仍用全新的 CODEX_HOME，只放指向该登录文件的链接；所有 Codex 臂对整个 `~/.codex` deny-read（G7）。agent 不读这个目录里的文件。
2. **DeepSeek key**（使用 DeepSeek 之前）：用户已在 WSL 的 `~/.profile` 设置 `DEEPSEEK_API_KEY`（2026-10-19；原方案是只在启动 benchmark 会话的终端里 export，不写进 profile）。agent 不读该文件，也不打印这个变量的值。写进 profile 后，从登录 shell 启动的所有进程（包括日常的其他会话）都带着它；runner 对非 DeepSeek 的子进程和所有 Reviewer 命令去掉它（§3「凭据」）。DeepSeek 臂的 runner 要从带着这个变量的环境启动；非登录 shell（例如 agent 的 Bash 工具）里可能没有它，开跑前只检查是否存在、不看值。建议同时在 DeepSeek 控制台给这个 key 设单独的花费上限，并把上限告诉 Main。

## 12. 实现位置（本轮已完成的代码适配）

- `tools/reviewer/providers.py`：ChatGPT 登录模式（`auth: chatgpt`，`auth_home`），链接与归还；`BENCHMARK_OPENAI_API_KEY` 只在 `auth: env_key` 时使用。
- `tools/reviewer/api_relay.py`：记录实际返回的 tier、模型和 usage，不写头和请求体。`arw_measure.run_api` 的每条记录写 `service_tier_returned`。
- `tools/safety/safety_gate.py`：
  - ChatGPT 零模型门（合成登录、netns）、读探针凭据目标改为链接后的登录文件；
  - 搜索工具检查、guardian 按元数据识别；
  - 解压请求体；
  - live 门支持强度、`web_search` 和冒烟子集。
- `tools/reviewer/claude_headless.py`：
  - `deepseek` backend；
  - `--disallowedTools WebSearch,WebFetch`、`--no-compact-prompt`；
  - stream 摘要记录 `service_tiers`、`server_web_requests`。
- `tools/safety/claude_gate.py`：deepseek mock/live、`--no-startup-prompt`、`--subset smoke`、搜索工具判定。
- `tools/reviewer/inspect_session.py`：凭据值打码（含 JSON、单引号和转义引号写法，以及 `*PASSWORD=`），`auth.json` 和 `.credentials.json` 计为凭据材料。
- 审查后补的（2026-10-19）：`providers.shell_exclude` / `process_environment`（所有凭据变量排除，M1）；`claude_headless.pinned_binary` 与两个 CLI 的 `--claude`（M6）；`safety_gate --web-search`（Strata 零模型模式）。
- 仍待实现（阶段 0）：
  - G7 deny-read、G8 live 冒烟已完成（§9 阶段 0）；
  - 跨模型汇总流水线：汇总层已完成，适配层待写；
  - Codex selection 的 `startup_instructions` / `project_compaction_instructions` 已有开关，只需在 plan 里写成 false。

## 13. 独立审查意见与处理

2026-10-19，两名全新的 Opus 独立 agent（不是 fork），开之前 `estimate.sh --can-start` 判定可以开始。

用户 2026-10-19 决定维持单名 Opus 盲裁后，下表中与双裁有关的 M3、M4、M10，以及 13.2 的 M1（`unsure` 与 `<裁决者>`，已从三份 brief 去掉）和「第 4 节」都不再适用。

### 13.1 方案与规则审查：结论"有条件冻结"

| 编号 | 意见 | 处理 |
|---|---|---|
| M1 | 本次 provider 以外的 key（如全局设置的 DeepSeek key，现名 `DEEPSEEK_API_KEY`）进入 Reviewer 命令环境；ChatGPT mock 显示 `shell_env_key: VISIBLE` | 已修：所有凭据变量一律排除，daemon 环境去掉其他 provider 的 key；DeepSeek 变量名作 canary 重跑 mock，结果 `absent`；§11 改为不写进 shell profile |
| M2 | Codex `:read-only` 能读 `~/.claude/.credentials.json`、`~/.codex/auth.json`、`project.private.toml`，API 臂可能把它们发出去 | 已实施（2026-10-19，G7，mock 门验证）：没通过就不启动 API 臂；偏离"不额外收紧"，交用户复核；混杂 13 已补 |
| M3 | luna 裁决 runner 不能用 `:read-only` | 已改 §6.2：用原生权限 profile 加零模型探针 |
| M4 | 开头"冻结要通过试点"与 §6.2"试点在冻结之后"矛盾 | 已改：冻结 brief → 试点 → 不过则维持 Opus、brief 不改 |
| M5 | S5 应只对实际返回的 tier 触发；模型 ID 匹配规则 | 已改 §2、§3、§10 |
| M6 | Claude Code 二进制要锁版本并记 SHA | 已实现：两个 CLI 的 `--claude`，版本不是 2.1.303 就拒绝 |
| M7 | Holm 族、α、自由度、Strata 次数、最小可分辨差 | 已写入 §5 |
| M8 | reviewer-suite「会话检查」缺 benchmark 例外 | 已写入规则 |
| M9 | Claude Code 上的 Strata 臂缺 live smoke | 已实施（2026-10-19）：G8，smoke 在 rtx3080ti 上通过 |
| M10 | README、work-history 的双裁应写"暂定"；试点补 Code Spec 池 | 已改 |
| 建议 | Codex 逐实例查 `web_search_call`；更正 Strata 搜索证据；断言 API 臂不接入基础提示；P4 测法；P5 具体 ID 的 effort；P0 套餐容量；P6 并行速度对照；编排费用归项；升级率线；锚点或合成负例不达标整池重裁；恢复路径归还登录；远端压缩核实；打码补单引号；按阶段墙钟；work-history 链接；README 措辞 | 全部写入计划或已修。Strata 搜索证据已补测：加 `--web-search disabled` 后为 0。打码、链接、README 已改；其余写进 §3、§5、§6.2、§8、§9 |

### 13.2 三份 brief 草稿核对：结论"三份都是修改后可冻结"

答案键 sha 与实物一致，ARW Adjudication 节与 r7 段和已冻结的 Commit Audit v3 brief 逐字相同。

| 编号 | 意见 | 处理 |
|---|---|---|
| M1 | 三份没有"拿不准"的输出，裁决者写死为 Opus | 已改：可选 `unsure` 字段，裁决者用占位符 `<裁决者>` |
| M2 | SR 第 11 行"不运行任何程序"与 python 核对冲突 | 已改，CS、CStd 同步写明例外（S5） |
| M3 | SR 漏了 export-retention 已定判例 | 已补，放在 sha 绑定的原样段之后 |
| M4 | SR 从 0 起的序号与 `problem-N` 易混；`prc`/`prt` 没有图例 | 已补读法说明，原样段不动，原样段 sha 仍成立 |
| M5 | SR 的 c003 id、v4.2 报告链接和"Opus 盲答"会泄露来源 | c003 id 和链接已去掉，判法保留。"Opus 盲答已实际出现"在 sha 绑定的原样段里（测试 `test_spec_readiness_quotes_frozen_adjudication_section` 校验），未改；它只说历史盲答出现过这种写法，不指明池中候选的来源 |
| M6 | CStd"误报或无依据"二选一 | 已改为确定判法 |
| S1、S2、S4、S6 | CS 写明不沿用 m2/m4；诱饵写出具体行；结果类别不同仍算匹配；头部维护说明与正文分开 | 已改；诱饵行号已在 fixture 核实 |
| S3 | CStd 登记 extraCharges/memberId 诱饵 | 未改：需按答案键 C22、C29 的 placement 核对措辞，列入阶段 0 |
| S7 | 锚点要取自同版本已裁池；SR 请求文件要复制改名并打码；view 从冻结 fixture 构造；`check_briefs.py` 的物化目录已删 | 写入 §6.2 和 §9 阶段 0 |
| 第 4 节 | 已冻结的 Commit Audit v3 brief 也缺 `unsure` 字段 | 属于"冻结"类重要决策，本轮不改冻结件；§6.2 写明未处理前 Commit Audit 走单名 Opus |

### 13.3 仍需用户决定的事项

- ~~20% 规则的分母~~：用户 2026-10-19 决定维持单名 Opus（§6.1）。
- G7 deny-read 偏离"不额外收紧"，实施后交用户复核。
- P1 若显示 DeepSeek 某个格式下三档无差别，是否删档。

## 14. 提前部分冻结（2026-10-19）

依据：用户 10-19 指示"这几天优先跑 Anthropic、优先用完周额度"；Main 要求把提前冻结的独立意见范围扩大到 Anthropic 臂加 Strata 臂。独立意见出自全新的 Opus high agent（不是 fork），开之前 `estimate.sh --can-start` 判定可以开。结论是同意按条件开跑；Anthropic 臂 worker 综合后全部采纳，处理写在下面。

- **冻结对象**：plan.md 在 commit `aee7b3a` 时的内容（sha256 `778f235ba7f43090fc2fcd85fbdffaac45b70f714d845faad26b30bce9bc382f`），适用于配置 #13–21（Anthropic）和 #25–27（Claude Code 上的 Strata）。#10–12（Codex 上的 Strata）只冻结方案、暂缓执行，等 CODEX163_READY 后，并在 0.163.0 上完成 `safety_gate --run` 完整门（每类探针 3 次、15 个审批用例、读探针、G7 deny-read、`web_search disabled`）、三档冒烟和压缩提示核实，再以单独 commit 补冻结。
- **除外项**，另行冻结：
  1. §2 #1–9、#22–24 各行，以及 P0–P3 的实测结果；
  2. 所有与 Codex 版本有关的文字，包括 §3「版本」中的 Codex 条目、§12 中与 Codex 副本有关的部分，以及 #10–12 的门证据。用户已定 benchmark 的 Codex 用 0.163.0，这些文字由另一个 worker 单独提交修改。
- **代码与输入绑定**：
  - 代码 commit `e470539`：`tools/reviewer/claude_headless.py`、`tools/reviewer/claude_scenario.py`，合成 HOME 来自 63f1434；
  - 场景 plan sha256：`benchmarks/multi-model-v1/scenarios/` 下 commit-audit-v3 `e509de73…`、code-spec-v5 `fb570844…`、code-standards-v5.1 `7a43f4b5…`、spec-readiness-v4.3 `d6a5b598…`。测量说明和 manifest 的 sha 写在各 plan 的 `fixed_conditions` 里；
  - Claude Code benchmark 副本 2.1.303，sha256 `375988f4…191450`；模型 ID `claude-opus-5-5`、`claude-sonnet-5-5`、`claude-haiku-5-5`（P5）；
  - Strata 臂：启动提示加载后 `1cae169a…`（源 `5f9efc02…`，防循环段关闭），压缩提示 `3856cb62…`，部署 JSON `1c8650e1…`，档位 206584 / 150000，`CLAUDE_CODE_MAX_CONTEXT_TOKENS`、`CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE` 与 `max_tokens`（§2.1）。第一个 Strata 实例要从请求或日志核实 8192 / 16384 / 24576 确实生效，并逐实例核对两份提示的 sha。
- **对正文的偏离**（交用户复核）：
  - §3「版本」：Strata 版本从 Strata 臂第一个实例开始锁定，到 27 个配置全部跑完为止，用户 D12 的升级窗口到此结束。第一个 Strata 实例开跑前，把 Strata 版本、安装 sha 写进绑定。
  - §9 阶段 1、阶段 2：Anthropic 臂和 Claude Code 上的 Strata 臂先跑，OpenAI、DeepSeek 臂后跑，同一场景的全部配置不保证在 48 小时内跑完；§4 第 9 条的漂移窗口相应变长。
  - Claude Code 上 Strata 的 low、medium 在正式运行前各补一次 smoke（G8 只跑了 high）。
- **预登记**（看到任何新输出之前）：
  - 并发：Anthropic 臂最多 4 个 `claude -p` 并行。Strata 臂同时运行时，WSL 里的 Claude Code、Codex 进程合计不超过 5 个。
  - 排程：按轮次块交替，每轮 9 个配置，顺序逐轮反转。每个场景的第一个 Opus 实例先跑完，其他 Opus 实例才开始，Sonnet、Haiku 同时进行。第一个实例算正式实例。
  - 无效判据（`claude_scenario.checks`）：模型 ID 不符（包括 safeguards 回退到另一个模型）、tier 不在 {default, standard, 未返回}、服务端搜索 > 0、API 或传输错误、非零退出。到硬时限停止的实例有效。每格（配置 × 场景）最多尝试 8 次，撞额度的不计入。Opus 某格前 3 次尝试里有 2 次回退，就停掉该格并列入 decide。
  - 撞额度（429、限额）：作废，等 `five_reset` 后重跑；`five_used` ≥ 90% 时不启动新实例。每个实例启动前跑 `estimate.sh --can-start`。首个 Haiku 批次前后记录用量。
  - CS、CStd 的 P4 沿用 Opus 参考运行的测法。"离同类 3 倍以上"中的同类，限定为同一模型的三档。Strata 臂用自己的引擎日志 P4。
  - 只跑不看：提前跑出的实例（含 Strata 臂）在相应配置组齐之前不计分、不盲裁、不读报告；会话检查只输出判定，结论不用于修改任何冻结内容。
  - 锚点（同版本已裁池中 10–15 个）和合成负例在读任何新输出之前选定，并把 sha 存档。
  - P6 基线：取 Anthropic 停跑后 Strata 实例引擎输出 tok/s 的中位数。G8 的 88.9 tok/s 只作参考。判定照旧：低于 60 tok/s 按 S3 处理，差超过 10% 在报告里注明。
- **残余风险**（§7 补充，交用户复核）：Claude Code 的沙箱拒写工作目录里所有已有文件，包括 `.git` 的每个子项（`hooks`、`refs`、`config` 等），但授权报告目录的祖先目录里允许新建文件。这与扁平门"顶层可新建"同类。计分只取指定的 `reportPath`；实例记录 `checks.unexpected_changes`，不为空时由会话检查逐条判定，只有影响评分或越出工作目录才判无效。`.git` 本身不能整体禁写，否则沙箱建不了 `.git/config.lock` 存根，Bash 会全部失败。
- 冻结之后，冻结范围内的任何修改都作为偏离记进 §13（日期、原因、对已跑实例的影响），不在正文里静默改动。

### 14.1 冻结后的偏离

- 2026-10-19 21:52，场景 plan 的 Codex 绑定改为 0.163.0。原因：另一个 worker 把 `native_cli_binding.CODEX` 指向 0.163.0 副本（用户已定），ARW 的零模型 prepare 会核对 plan 里的 `native_cli_sha256`，不改就拒绝准备。四个场景 plan 只改了 `codex` 和 `native_cli_sha256` 两个字段（改为 `399ff69c…`），新 sha256 为 commit-audit-v3 `6de471d9…`、code-spec-v5 `990e9363…`、code-standards-v5.1 `89b604c9…`、spec-readiness-v4.3 `f1ad28d1…`。Claude Code 臂不运行 Codex。改后 dry-run 的 CA 提示与改前已跑实例的提示逐字相同（路径和 UUID 归一化后），所以对已跑实例没有影响。改动期间有 5 个实例在 prepare 阶段失败，没有发出模型请求，按准备失败记录，不计入尝试次数。
- 用户复核（2026-10-19）：§14 全部同意。顺序口径补充：同一类模型（同一厂商或模型族的各配置，例如 Anthropic 三个模型的 9 个配置、Strata 的 6 个、GPT 的 6 个、DeepSeek 的 6 个）要在尽量短的时间段内跑完，不同类之间可以间隔几天。
- 2026-10-19 22:20，Claude Code 上 Strata 臂（#25–27）第一个实例之前补代码。e470539 的 `claude_scenario` 只能跑 API 臂：没有 `--backend`/`--host`，且加载了启动提示的实例会被 checks 判无效。补上 `--backend strata --host <id>`；Strata 实例的 checks 用本次实际加载的两份提示 sha（binding）代替"启动提示关闭"，并按服务日志（model-server.log 本次段）核对每个请求的思考上限和总输出与 §2.1 一致；`claude_headless.strata_run` 另存服务日志段、Strata 版本和 qwen-agent 模型变量的值（不含 key 和前端地址）。Anthropic 臂的代码路径和判定不变（测试覆盖）。排程沿用冻结代码 `strata_run` 的做法：每个根线程领一次租约、冷加载、跑完停模型并归还，不做 §3 所说的同配置连跑与预热；每个实例从相同冷态开始，前缀缓存不跨实例（与 G8、`arw_measure` 自持模型路径一致），实例之间归还租约，Codex 侧 worker 可以在间隙领用。交 Main 复核。
- 2026-10-19 22:29（87d86c2），DeepSeek key 的变量名改为 `DEEPSEEK_API_KEY`（用户已写进 `~/.profile`），凭据排除改为已知变量加 `*_API_KEY`、`*_TOKEN`、`*_SECRET` 通配；`arw_measure` 的 Strata 路径原先只排除 `STRATA_API_KEY`，现在与安全门一致，排除全部凭据变量和通配。原因：方案里的 `BENCHMARK_DEEPSEEK_API_KEY` 与用户实际设置的名字不符，旧的 `process_environment` 只按 `BENCHMARK_` 前缀去掉 key，换名后 DeepSeek key 会进入其他臂的 daemon 环境；Strata 路径的 Codex 命令也能看到它。影响：#10–12 尚未开跑，Claude Code 臂（#13–27）的最小环境不变，已跑实例不受影响。0.163.0 上三种 Codex mock 门和 Claude Code DeepSeek mock 门复跑通过：canary `DEEPSEEK_API_KEY` 与通配 canary `QWEN_GATE_CANARY_TOKEN` 在命令环境里都 `absent`，命令环境里没有任何这类名字（`shell_credential_names` 为空）。

### 14.2 #10–12（Codex 上的 Strata）补冻结（2026-10-19）

§14 为 #10–12 设的条件都已在 Codex 0.163.0 上满足，按 §14 以单独 commit 补冻结。

- **条件核对**（全部满足，证据在 §7「Codex 0.163.0 上的 Strata 证据」，报告 `reports/v0.1.45/safety-gate-codex-0.163.0/`）：
  - 完整门 `safety_gate --run`（rtx3080ti、IQ3_XXS、high，21:59–22:03）：原生 3 行、15 个审批用例，共 18 个观测全部通过。
  - 读探针 3 次都跑了；G7 deny-read 的 4 个合成目标都是 denied，`deny_read_pass` 为真；假 key 在命令环境和 `/proc` 祖先中都不可见。
  - `web_search: disabled`：请求里搜索工具 0。
  - 三档冒烟（low / medium / high 各 1 次）：全部通过，请求的推理强度与 plan 一致。
  - 压缩提示核实：live 门与冒烟加载的压缩提示是 `3856cb62…`，启动提示加载后是 `1cae169a…`（源 `5f9efc02…`，防循环段关闭）。原生压缩提示 `ab0c334d…` 与 0.162.0 逐字节相同；远端压缩无残留（阶段 0 零模型）。
- **门之后的改动**（87d86c2）：Strata 路径的命令环境从只排除 `STRATA_API_KEY`，改为排除全部凭据变量和 `*_API_KEY`、`*_TOKEN`、`*_SECRET`，见 §14.1。live 门本来就用全部凭据变量的排除名单（`shell_exclude(None)`），这次只多了通配。改动只去掉更多环境变量，不改模型输入。0.163.0 上的 Strata mock 门已复跑通过（边界 8 类拒绝，`deny_read_pass` 为真，命令环境里没有任何凭据形变量），所以判定条件仍然满足，不重跑 live 门。
- **冻结对象**：plan.md 在 commit `bfd22f1` 时的内容（sha256 `43897bba…f3d407`），加上本节，适用于配置 #10–12。§14 的预登记、无效判据和偏离口径照样适用。§14 的除外项仍然除外（#1–9、#22–24 和 P0–P3）。
- **绑定**：
  - Codex：benchmark 专用副本 0.163.0，native sha256 `399ff69c431c066e40de318fba45c2b07f45a76b19939d247ee4828fc70c4215`，路径 `~/.local/share/qwen-bench/codex-0.163.0/`。
  - 代码：commit `bfd22f1` 的 `tools/reviewer/arw_measure.py`、`providers.py`、`native_cli_binding.py` 和 `tools/safety/safety_gate.py`。
  - 场景 plan sha256：commit-audit-v3 `6de471d9…`、code-spec-v5 `990e9363…`、code-standards-v5.1 `89b604c9…`、spec-readiness-v4.3 `f1ad28d1…`（§14.1 的 0.163.0 绑定）。
  - Strata 侧：部署 JSON `1c8650e1…`；默认 profile `8f59b4aa…`（门前 preflight 与门一致）；档位 206584 / 150000；三档的思考上限和总输出按 §2.1，guardian 512/1024。
  - 提示：启动提示加载后 `1cae169a…`，压缩提示 `3856cb62…`。
- **第一个实例要做的检查**：
  - 从服务日志核实 2048/8192、4096/16384、8192/24576 确实生效。冒烟只核对了请求里的推理强度，没核对前端填入的上限。
  - 逐实例核对两份提示的 sha。
  - 把 Strata 版本和安装 sha 写进绑定（§14 偏离第 1 条）。
