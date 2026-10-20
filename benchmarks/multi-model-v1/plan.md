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
| 7–9 | Codex 0.163.0 + ARW | `deepseek-flash` | low / high / max（用户 2026-10-21；已跑的 medium 见 §14.4） | `DEEPSEEK_API_KEY` | 无 | 无原生默认，用同模型 low |
| 10–12 | Codex 0.163.0 + ARW | Strata `qwen3.8-flash-next-iq3_xxs` | low / medium / high | 前端租约 | 启动提示与压缩提示 | Strata 自身（512/1024） |
| 13–15 | Claude Code 2.1.303 无头 | Opus（`opus`） | low / medium / high | 订阅 | 无 | 无（dontAsk） |
| 16–18 | Claude Code 2.1.303 无头 | Sonnet（`sonnet`） | low / medium / high | 订阅 | 无 | 无 |
| 19–21 | Claude Code 2.1.303 无头 | Haiku（`haiku`） | low / medium / high | 订阅 | 无 | 无 |
| 22–24 | Claude Code 2.1.303 无头 | `deepseek-flash` | low / high / max（用户 2026-10-21；已跑的 medium 见 §14.4） | `DEEPSEEK_API_KEY` | 无 | 无 |
| 25–27 | Claude Code 2.1.303 无头 | Strata `qwen3.8-flash-next-iq3_xxs` | low / medium / high | 前端租约 | 启动提示（服务端）与压缩提示（PreCompact） | 无 |

- 模型 ID 以 API 实际返回的为准，逐实例记录：Codex 的 API provider 由 relay 记录，Claude Code 从 stream 的 `model` 和 `modelUsage` 读取。别名 `opus`、`sonnet`、`haiku` 在开跑前解析成具体 ID，写进绑定，正式运行的 `--model` 直接传具体 ID。
- 匹配规则（用于 S5）：返回的 ID 与绑定 ID 完全相同，或是绑定 ID 后接日期后缀（`-YYYY-MM-DD` 或 `-YYYYMMDD`），算一致；其余算不符。ChatGPT 后端若不返回模型 ID，记为未知，不触发 S5。Strata 不适用。
- DeepSeek 在两个 harness 上都写死为 `deepseek-flash`（官方 2026-10-19：当前为 DeepSeek-V4.1-Flash-1017）。在 Claude Code 上，`claude-opus-*` 这类名字会被端点映射到 v4-pro，所以 runner 把所有模型变量都设为 `deepseek-flash`，并拒绝 Claude 名字（`tools/reviewer/claude_headless.py` 的 `deepseek_model`）。
- 端点：
  - DeepSeek 在 Codex 上用 OpenAI 格式 `https://api.deepseek.com`（Responses，`wire_api = "responses"`），在 Claude Code 上用 Anthropic 格式 `https://api.deepseek.com/anthropic`。
  - OpenAI 用 Codex 内置的 `openai` provider（ChatGPT 后端），`openai_base_url` 只是指向本地 relay。
- 不用 ultra、xhigh、max。ultra 会派子 agent，ARW 拒收；Strata 的 xhigh、max 预算与 high 相同，所以 Strata 不跑 max。例外：DeepSeek 用 max（用户 2026-10-21）。官方 thinking_mode 页只列 low / high / max，并把 minimal 映射为 low、medium 和 xhigh 映射为 high。

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

- **DeepSeek 只在低谷时段跑**（用户 2026-10-21）：低谷价约为高峰的一半，所以凡是调用 DeepSeek API 的工作，包括正式实例、探针、冒烟和补跑，都安排在低谷时段。启动截止时刻和对高峰的处理见 §14.4。
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
3. **"强度"含义因厂商而异**：Strata 三档见 §2.1。DeepSeek 自 2026-10-21 起测 low / high / max（用户决定）。依据是官方 thinking_mode 页：原生档为 low / high / max，medium 映射为 high。P1b、P1c 的实测与这个映射不矛盾，但也证明不了它：P1c 的简单题上 low/medium/high 无差别，max 长约 1.5 倍；端点的 422 报错把 medium 列为合法枚举值。已跑的 medium 实例按 §14.4 处理：CA、SR 两个 harness 和 CStd-Codex 的 medium 并入 high；CS 两侧和 CStd-CC 的 medium 只作补充行，标"high requested as medium, T=…"，因为它们的时限 T 与 high 不同。
4. **基础提示只给 Strata**：注入位置不同。Codex 路径由服务端追加；Claude Code 路径由服务端追加启动提示，PreCompact hook 追加压缩提示。
5. **搜索全部关闭**，偏离 ARW 原生设置（2026-10-11 规则）。各模型都没有搜索，但这与 ARW 自己的结果不可直接比较。
6. **guardian 不同**：OpenAI 用 codex-auto-review，DeepSeek 用同模型 low，Strata 用自身，Claude Code 没有。
7. **窗口与压缩不同**：Strata 为 206584/150000，其他模型用原生设置（OpenAI catalog 272000）。DeepSeek 在 Codex 上为官方 catalog 的 1048576（95%，auto_compact 未设），实际不压缩；在 Claude Code 上未设 `CLAUDE_CODE_MAX_CONTEXT_TOKENS`，约 162K 时压缩（2026-10-21 冻结审查，不改）。OpenAI 用服务端压缩（零模型核实，见 §9 阶段 0）。Claude Code 路径的压缩提示只给 Strata。
8. **ARW 早停接续只在 Codex 路径**：Claude Code `-p` 没有接续。
9. **时限按各自的速度计算**：API 模型的速度含网络。服务端可能漂移，而执行窗口约一到两周。DeepSeek 的 max 比其他档晚几小时到几天才跑，它的 P4 也是另一时刻测的；CS、CA 只有 max 格还在轮换，所以 max 与 low/high 之间多一层时间漂移（2026-10-21）。
10. **ChatGPT 套餐**：只报 token，不报金额。套餐的限速或路由可能与 API 不同。
11. **IQ3_XXS 参数来自 v0.1.42 调参**：benchmark 就在当前版本上跑。Haiku 的订阅额度扣减比例未核对，首次 Haiku 运行时记录前后用量。
12. **盲裁方式**（§6）：单名 Opus 盲裁，与场景标定同一模型（见第 1 条）。
13. **两个 harness 的读取范围不同**：Claude Code 的工具和 Bash 沙箱只能读工作目录；Codex `:read-only` 能读宿主文件（G7 只去掉凭据路径）。
14. **时限提醒的送达优先级不同**（2026-10-20）：Codex 路径由 ARW 以高优先级消息送达，立即打断正在进行的生成，确保模型在超时之前收到（设计如此）；Claude Code 路径经 PostToolUse hook 注入，要等下一次工具调用结束才送达，可能更晚。benchmark 期间不改，结束后让 Claude Code 路径也改用高优先级送达（见 docs/plan.md 待办）。

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
- 文字比较只用预登记的一组：同一 harness、同一强度下，Strata 对其他每个配置；DeepSeek 和 Strata 各自的 Codex 对 Claude Code。2026-10-21 DeepSeek 改为 low / high / max 后，每个场景的族为 25 个比较：Codex 8 个（GPT 2 × 3，DeepSeek low、high），Claude Code 11 个（Anthropic 3 × 3，DeepSeek low、high），harness 6 个（Strata 三档，DeepSeek low / high / max）。Strata 没有 max，DeepSeek 没有 medium，所以这两档不和 Strata 配对。每个场景是一个校正族，Holm 校正，双侧 α = 0.05，Welch t 检验用 Welch–Satterthwaite 自由度；Strata 只用预登记的前 5 次。校正后显著才写"高于 / 低于"，其余写"未分出"。n = 5 对 5 时能分辨的差约 0.3（审查估算），报告写明这一点。表中全部数字照常给出。
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
- 池按场景混合打乱，所有配置跑完后统一盲裁，隐去来源。每池混入锚点（10–15 个已有 Opus 裁决，取自同一场景版本、控制项全对的已裁池；旧版本池中答案键、期望句和代码都未改的用例也可用，如 CStd 取 v5 池的用例 1–16、26，SR 取 v4.2 池（答案键同为 74252e0a）；缺锚点的族按用户 10-20 决定，从第一批裁决中挑题、经 Main 可执行检查确认后登记；Code Spec v5 正式池里来自 v4.7 的锚点不能用，它们引用的代码在 v5 已改正）和合成负例。锚点一致率按来源模型分组报告。
- 某个池的锚点一致率低于 90% 或合成负例有一个没识别，该池整池重裁并扩大复核（reviewer-suite「盲裁只裁有变化的部分」）。
- 运行参数（2026-10-20 写定，与 `tools/reviewer/blind_pool.py` 一致）：
  - 裁决者：Opus high，Claude Code 无头；回复的 `adjudicator` 必须是 `blind Opus high`，否则 `split` 拒收。
  - 池大小：每池最多 150 项（`MAX_ITEMS`），按期望句整组切分，一组不跨池。同一个候选不会在一池里出现两次：取自某实例的锚点，其原候选已有同指纹的决定，`build --root` 按指纹跳过它；若仍有同一候选既是锚点又待裁，`build` 拒绝。同一实例的其他候选可以和取自该实例的锚点同池（与代码一致，2026-10-20 改写）。
  - 控制项：每池 12 个锚点（`ANCHORS_PER_POOL`），从场景注册表 `benchmarks/multi-model-v1/anchors/<场景>.json` 按来源 family 轮流抽取，并保证池里至少有一个 not-matched 控制项；注册表的全部合成项进每个池。锚点只用 association 决定；finding 类控制项一律用合成项，按三个 family 各自的报告写法写成（用户 2026-10-20）。Sonnet、Haiku 的锚点等第一个裁决批次出来后再补（scoring-fixes 第 6 项）。
  - 第一批裁决之后补锚点的挑选规则（2026-10-20 写定，任何盲裁开跑之前）：只从过了门槛且 Main 复核完的池里挑 association 决定；按来源 family × 决定（matched / not-matched）分层，每层用固定种子 20261021 打乱后依次取；每个候选先做 Main 的可执行检查（`node` 在 view 上复现，或对照 `governing-spec.md` / 合同原文可机械核实），做不了可执行检查的跳过并计数；通过的用 `blind_pool anchor-add --model --origin-record --origin-stable-id` 登记。挑出的样本同时回查第一批本身：Main 的检查与 Opus 原决定不一致即算该 family 的一次锚点未命中，该 family 在第一批里扩大复核。挑选数、跳过数和回查一致率写进报告。
  - 门槛：锚点一致率 ≥ 90%，且合成项全部判对，且两类都存在；三条都满足才写入分数库。不通过的池整池重裁，什么都不写入。合成项里除负例外还有 finding-problem 这类正例，所以"全部判对"比上一条的"合成负例都识别"更严。
  - 每池一个裁决目录：`build` 把每个池写进自己的 `<adj>/<池名>/`，它就是 brief 里的 `<ADJ>`；隐藏的 key 放在 `--adj` 之外。`prompt` 生成裁决提示前核对 `<ADJ>` 里只有本池的 pool 文件（sha 与 key 一致）、brief 指定的 view（CS/CStd 为 `view/` 与 `change.diff`，CA 为 `view/`，SR 为 `view-rm/` 与 `view-ap/`）和本池的 decisions，多出任何文件都拒绝。
  - 裁决提示：冻结 brief 只替换 `<ADJ>` 和 `<名>`，正文之后附一段调用方说明（公平判定，见 §14.1 2026-10-20 条）；brief 和提示的 sha256 记进 key。
  - 复核清单（`split` 输出）：全部 `supported` 决定，以及有争议的 `unsupported`（裁决者列为最难的、理由含犹豫词、或与判成其他结果的候选共用证据位置）。Main 复核后用 `override` 改判，原值留在历史里。
  - 沿用已有决定：只对内容指纹相同的候选沿用；候选内容变了就重新入池。
  - 上游最终状态（ARW 报告的 completion status）只作诊断写进计分结果，不参与计分。
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
- 2026-10-19 22:05，Claude Code 上 Strata 臂（#25–27）第一个实例之前补代码。e470539 的 `claude_scenario` 只能跑 API 臂：没有 `--backend`/`--host`，且加载了启动提示的实例会被 checks 判无效。补上 `--backend strata --host <id>`；Strata 实例的 checks 用本次实际加载的两份提示 sha（binding）代替"启动提示关闭"，并按服务日志（model-server.log 本次段）核对每个请求的思考上限和总输出与 §2.1 一致；`claude_headless.strata_run` 另存服务日志段、Strata 版本和 qwen-agent 模型变量的值（不含 key 和前端地址）。Anthropic 臂的代码路径和判定不变（测试覆盖）。排程沿用冻结代码 `strata_run` 的做法：每个根线程领一次租约、冷加载、跑完停模型并归还，不做 §3 所说的同配置连跑与预热；每个实例从相同冷态开始，前缀缓存不跨实例（与 G8、`arw_measure` 自持模型路径一致），实例之间归还租约，Codex 侧 worker 可以在间隙领用。交 Main 复核。
- 2026-10-19 22:29（87d86c2），DeepSeek key 的变量名改为 `DEEPSEEK_API_KEY`（用户已写进 `~/.profile`），凭据排除改为已知变量加 `*_API_KEY`、`*_TOKEN`、`*_SECRET` 通配；`arw_measure` 的 Strata 路径原先只排除 `STRATA_API_KEY`，现在与安全门一致，排除全部凭据变量和通配。原因：方案里的 `BENCHMARK_DEEPSEEK_API_KEY` 与用户实际设置的名字不符，旧的 `process_environment` 只按 `BENCHMARK_` 前缀去掉 key，换名后 DeepSeek key 会进入其他臂的 daemon 环境；Strata 路径的 Codex 命令也能看到它。影响：#10–12 尚未开跑，Claude Code 臂（#13–27）的最小环境不变，已跑实例不受影响。0.163.0 上三种 Codex mock 门和 Claude Code DeepSeek mock 门复跑通过：canary `DEEPSEEK_API_KEY` 与通配 canary `QWEN_GATE_CANARY_TOKEN` 在命令环境里都 `absent`，命令环境里没有任何这类名字（`shell_credential_names` 为空）。
- 2026-10-19 22:30–23:47（88999a5），Claude Code 臂的临时目录隔离修复，Anthropic 臂已跑实例全部作废（用户决定）。
  - **原因**：Claude Code 2.1.303 把沙箱命令的 TMPDIR 设为 `$TMPDIR/claude-<uid>`，未设 TMPDIR 时就是共享的 `/tmp/claude-1000`；所有并发实例都能读写它，操作者会话的文件也在里面，构成跨实例通道。`/tmp` 顶层也可写。扫描结果在 `.tmp/bench-anthropic-1019/tmpdir-audit/`（原 CA 有 71 次工具调用触及共享 TMPDIR）。处理：CA 首轮 25 个有效实例全部作废，旧目录 `.tmp/bench-anthropic-1019/ca/` 保留不删，新运行目录 `ca-r2/`，尝试计数从零开始。CS/CStd 的 P4 探针只用 Read 工具、不涉及 TMPDIR，沿用。
  - **修复**（`claude_headless`）：每个运行一个 `<run root>/tmp`（0700，属主和类型都核对），同时设为 TMPDIR 和 CLAUDE_CODE_TMPDIR，只授权给本运行。`environment()` 拒绝空值、`/tmp` 和共享目录。`/tmp` 与 `/tmp/claude-<uid>` 拒写；`/tmp` 顶层整体 denyRead 在 2.1.303 不生效，所以运行开始时逐条列出现有条目禁读。`/var/tmp`、`/run/lock`、`/run/screen`、`/dev/shm`、`/dev/mqueue`、`/var/crash` 整目录 denyRead：沙箱会在这些位置挂一个私有空目录，写入只留在沙箱内。修复前 mock 显示 `/var/tmp`、`/run/lock` 可写到宿主，`/var/tmp` 顶层文件可读。这些目录不能用 denyWrite，因为 `/var/tmp` 的 denyWrite 会盖住 WORK_BASE 下本运行的写授权，bwrap 会失败。settings 参数超过 120000 字节时报错，对应内核单参数上限 131072。
  - **验证**：
    - mock 门新增探针：自己的 TMPDIR（对照）；60K 字符的大 heredoc；读写 peer 的 TMPDIR（Bash 与 Read）；读写 `/tmp/claude-1000` 和 `/tmp` 顶层；连接 `/tmp` 下监听中的 AF_UNIX socket（按实际接受的连接判定）；读 `/var/tmp`、`/dev/shm` 的 canary，并列出 WORK_BASE；向各全局可写目录、peer 工作目录和 `$HOME/.claude` 写入（检查宿主上的实际文件）。
    - `--pair` 让两个实例并发、互为 peer：anthropic、strata、deepseek 三种后端各 repeat 2，全部通过。
    - live Anthropic 门（Haiku high，真实 HOME 链接形状，不在 userns 里）跑 3 次：没有泄漏、宿主上没有写入，Haiku 执行了的探针全部通过。其中 1 次 Haiku 拒绝了大部分探针；另 2 次只没执行 60K 命令探针，它只有 mock 证据。
    - 宿主的 `/tmp`、`/tmp/claude-1000`、`/var/tmp` 和真实 `~/.claude` 都没有残留。全量单元测试通过。
  - **独立审查**（全新 Opus agent）：有条件通过。条件一是补 live Anthropic 门，已补。条件二是补 `/tmp` 以外共享位置的读写探针，已补；补测时发现 `/var/tmp` 与 `/run/lock` 的写通道，修好后复验通过。建议项已做：`run_tmp` 核对、settings 长度保护。未做：清理 `/tmp` 下他人测试遗留的 `tmp*`，不确定是否仍在使用。
  - **残余风险**：运行开始后才新建的 `/tmp` 顶层条目可读。没有沙箱实例能写 `/tmp`，所以这不构成实例之间的通道；`ls /tmp` 也仍能看到文件名。
  - **command too long**：Main 决定。"Sandboxed command is too long"（131071）的原因是模型命令里单引号的嵌套转义膨胀，每个约 334 字节，与挂载数无关。这是 Claude Code 原生限制下模型自身的行为，所有模型一视同仁：不改 harness，不判实例无效，报告按配置统计出现次数。
  - **另一条臂**：Claude Code 上的 Strata 臂（#25–27）也走 `claude_headless`，它此前的实例同样用过共享 TMPDIR，是否作废交 Main 定。
- 2026-10-20，Strata 臂（#25–27）随临时目录修复作废重跑（用户 10-19 决定已跑正式实例全部作废）：CA 的 strata-low-a1、a2 两个有效实例作废，旧目录 `.tmp/bench-strata-1019/ca/` 保留不删；新运行目录 `<场景>-r2/`，尝试计数从零开始。修复后的 `claude_headless`（88999a5）与 958d289 的 Strata 支持合用，Strata 后端同样用每运行独立 TMPDIR；重跑前 Strata mock 门 `--pair --repeat 2` 通过（自身 TMPDIR、peer TMPDIR 读写、共享 TMPDIR 与 `/tmp` 读写、socket、其他全局可写目录全部按预期，宿主 HOME 与 `/tmp` 无新增；`.tmp/bench-strata-1019/mock-pair-strata`）。low、medium smoke（10-19，修复前）只用于核实三档上限与提示 sha，不重跑。
- 2026-10-20 01:00 前后，Codex 0.163.0 上 Strata mock 门补共享位置写探针（f50d0d1，`safety_gate` 边界探针，按探针名在宿主上查 canary）。结果：`/var/tmp`、`/run/lock` 拒写；`/dev/shm` 在沙箱内写入成功，但宿主上没有 canary（`shared_host_writes` 为空，宿主三处列表前后相同）；8 类边界照旧拒绝，HOME 无新增（`.tmp/bench-strata-1019/codex-strata-mock-shared`）。Main 判定：`/dev/shm` 的写入只落在沙箱私有的 tmpfs，不构成跨实例或对宿主的通道，#10–12 可在 #25–27 之后按顺序开跑；此后每个 Codex 实例开跑前 `boundary()` 继续核对宿主 `/dev/shm`，一旦宿主出现 canary 就停下报告。偏离：这次 mock 门开跑时没等到基准进程数降到 3 个以下（等了约 9 分钟），运行约 1 分钟期间 WSL 里 Claude Code 与 Codex 基准进程合计约 6 个，超过预登记的 ≤5；mock 门不发模型请求，正在运行的 Strata 与 Anthropic 实例不受其输出影响，只可能有轻微 CPU 争用。

- 2026-10-20 06:19–06:21，OpenAI 臂（#1–6）冻结（c877a8b）后的两处偏离，Main 同意：
  - **run_one 补 ARW 主会话身份**：CA 第一次开跑时，3 个实例在 ARW `spawn_agent` 处失败，报错 "Main session identity is missing"。原因是 `run_one.py` 没有像 `arw_dimension` 和 Strata 臂那样传 `CODEX_THREAD_ID=<plan codex_thread_id>`。这 3 个实例的 relay 请求数都是 0，没有发出模型请求，所以按准备失败记录，不计入尝试次数，目录改名为 `ca-prefail/`。修正后 `run_one.py` 的 sha256 为 `e1984fee…088df`，取代 §14.3 中的绑定，判定逻辑不变。
  - **进程上限**：Anthropic 臂当时也在运行。CA 开跑时 OpenAI 实例的 Codex 进程启动有滞后，调度器的计数没反映出来，06:20 时 WSL 里基准进程合计一度为 6 个，超过 §14 的 ≤5。之后新增 `.tmp/bench-openai-1020/slotctl.py`（sha256 `6981c2a4…`）：每 10 秒把 `slots.txt` 写成 min(4, 5 − 其他臂进程数 − 预留数)，调度器每次启动前都读它；R1 的门运行用 `reserve.txt` 预留 1 位。Main 已让 Anthropic 臂在 11:00 前不再开新实例。

- 2026-10-20 06:24–07:40，OpenAI 臂（#1–6）CA 开跑失败后的作废与修正（Main 逐项决定；补丁 A 经独立审查判"改后可开跑"，审查全文 `.tmp/bench-openai-1020/patch-review.md`，必改项 M1–M3 已照做）：
  - **作废实例**，都不计入尝试次数，目录保留：

| 批次 | 目录 | 实例数 | 是否发出模型请求 | 原因 |
|---|---|---|---|---|
| prefail | `ca-prefail/` | 3 | 否，relay 请求数 0 | 没有传 ARW 主会话身份（上一条） |
| stubfail | `ca-stubfail/` | 4（sol low/medium/high、luna low，最后一个被提前终止） | 是，POST 7–14 次 | 报告目录里有 Codex 的占位空目录，ARW 绑定检查判失败；prep 在工程盘 |
| tmpfail | `ca-tmpfail/` | 6（各配置 a1） | 是，POST 5–12 次 | 同上；prep 已改放 /tmp，照样出现；luna-low 的 ARW completion 是 incomplete，原因同样是报告目录检查失败 |

  - 两批共用掉周窗口 1 个百分点（36%→37%），credits 不变。这两批不看报告。
  - **原因**：Codex 0.163.0 的 bubblewrap 在写授权目录里建 `.git`、`.codex`、`.agents`、`.aws` 空占位目录，删除不可靠（零模型对照见 `.tmp/bench-openai-1020/stubtest2/`）。详见 `docs/arw-upstream-issues.md` E。把 prep 改放 /tmp 解决不了。
  - **补丁 A**：`benchmarks/reviewer-suite-v1/arw-patches/codex-0.163-synthetic-mount-targets.patch`，sha256 `c1347209…a476`。只放过报告目录直属、名字恰为这四个之一的真实空目录，每次放过都记一条 stderr 事件，`run_one` 按实例统计 `mount_targets_ignored`。这个补丁不进冻结 manifest，manifest 的 sha 仍是场景 plan 绑定的值；它在 prepare 时由 `harness_patches` 选择应用，应用前后都核对成员 sha，结果写进 `prep/harness-patches.json`。适用于 #1–6 和 #10–12，Claude Code 各臂不使用 ARW runtime，不受影响。
    - ARW 单测：新增 6 个，覆盖只有空占位目录、占位目录里有文件、名单外的名字、符号链接、额外文件、同名文件；连同 reviewer-runtime 全部 49 个测试通过。
    - 工程单测：`tests/test_harness_patches.py`，在四个场景源上各应用一次。
    - 零模型门：`.tmp/bench-openai-1020/mtgate/`，真实 arw_measure 走 OpenAI 路径，脚本化模型，网络命名空间。未打补丁 3 次，占位目录留下 1 次，那次判 incomplete；打补丁 3 次，留下 1 次，那次判 ready，记录 12 条忽略事件（4 个目录 × 3 次绑定检查：fresh 开始、轮询、收尾都经过同一检查）。其余 4 次占位目录都被 Codex 自己删掉了，结果都是 ready。
  - **计量修正**（`tools/reviewer/api_relay.py`）：ChatGPT 上游的 SSE 回复不带 Content-Type，relay 因此记不到 model 和 tier，现在不论 Content-Type 都先按 SSE 扫描。426 是 websocket 被设计性拒绝，不再计入 errors。这是计量工具的缺陷修复，不改变被测条件。
  - **有效判据**（`run_one.checks`，按 §14 跨臂口径）："未完成"指运行时没有正常结束。现在只要 runtime 正常退出（state=exited）且有 completion 记录，就判有效并计分，不管模型自报 ready 还是 incomplete。打补丁后如果仍有报告绑定被拒（审查 M1，Main 采纳）：报告目录的额外条目里有这四个名字以外的东西，就按模型结果计分，不重跑（`report_dir_model_violation`）；其余情况（占位目录非空、Codex 新行为），以及 `wait_agent` 崩溃留下 `recovery-required.json`、没有 completion 的情况，都停止调度、保留现场、交 Main（`halt`），不自动重跑。复制回工程盘后再查一次占位目录，非空或是链接也 `halt`。调度器另外在每个实例结束时核对 `models_returned`、`service_tiers` 非空和 `mount_targets_ignored` 已记录，`harness-patches.json` 缺失也 `halt`。硬时限只用于有时限的场景；CA 不设时限，这一条对 CA 不适用，到有时限的场景再核对被 interrupt 的实例是 `state=exited` 且带 completion。
  - **其他**：arw_measure 因 ARW 错误退出时会留下 runtime daemon，`run_one` 结束时把属于本实例的 daemon 连同整个进程树结束（先 SIGTERM，5 秒后 SIGKILL），再核对没有仍指向本实例运行目录或 prep 的进程（codex、bwrap 等），记进 `leftover_cleanup`，不干净就 `halt`（审查 M2）。此前留下的 10 个 daemon（各带 `recovery-required.json`）：prefail 537508、537735、538012，07:11 检查时已不在，退出时间不明；stubfail 538870、539328、539875 和 tmpfail 565812、566274、566853、570276，共 7 个，07:11 前后用 SIGTERM 结束，随后确认已不在。它们在实例结束后都是空闲的（stderr 0 字节，共享 codex-home 06:55:18 后无写入，relay 随 arw_measure 退出），发不出模型请求；06:19–07:40 期间 R1 门和 Strata 臂的速度数据是在这些空闲进程存在时测的，影响应可忽略，交 Main 标注。prep 仍放 /tmp，做法见 `.tmp/bench-openai-1020/prep-review.md`：基目录 `/tmp/qwen-openai-1020`（0700，inode 876755）06:43:01 建好；运行结束后复制回 `<实例>/prep` 并核对 sha，评分只读副本；每个场景结束后审计 denyRead 的覆盖情况。
  - **运行脚本**：`run_one.py` sha256 `751d691a…68a3`，取代 `eaf9f11a…16fa` 和更早的 `e1984fee…`；`schedule.py` `c4d4233c…48471b3a`。

- 2026-10-20 07:50–07:53，OpenAI 臂 CA 首批 4 个实例的判据修正（Main 决定）：
  - **经过**：07:50 开跑 sol-low/medium/high 和 luna-low 各 a1，4 个都正常走完：arw_measure 退出码 0，无 `recovery-required.json`，completion 都是 ready，复制回工程盘后 sha 核对一致，进程清理干净。但调度器按 `halt` 停下了。
  - **原因**：`run_one` 的 `ended_normally` 写成了 `state=='exited'`。ARW 的 Reviewer 正常完成时 state 是 `idle`，taskState 是 `ended`，所以这个条件永远不成立。mtgate 的 6 次运行也都是 `idle`，但那几次没经过 `run_one` 的判据，所以没有发现。
  - **修正**：改用 arw_measure 自己接受完成的条件：有 completion，且 state 不在 starting/running/working 之中。判据只是改成与 arw_measure 一致，与得分无关；改之前没有看过报告内容，也就不涉及按结果挑选。这 4 个实例按新判据计入有效。它们的 `instance.json` 保留原判定，另加 `reclassified` 字段，记录新判据下的检查结果和 run_one 的 sha。
  - **首查四项**：都正常。`models_returned` 和 `service_tiers` 非空（default 8–9 次），说明 relay 对无 Content-Type 回复的修正在真实 ChatGPT 上端到端有效；`prep/harness-patches.json` 存在；`mount_targets_ignored` 为 20–28。
  - **补丁 A 是必需的**：4 个实例的 ca/1 报告目录全都留下了四个占位目录，都被补丁放过。Codex 0.163 在真实负载下几乎每次都会留下这些目录，不打补丁就跑不了。
  - **运行脚本**：`run_one.py` sha256 `19518faf…4d79`，取代 `751d691a…68a3`。`schedule.py` `cc426573…3cf15a989c`，新增续跑功能：已有实例保留原编号、尝试次数和有效判定，`reclassified` 优先，每个有效实例从队列里扣掉一次。

- 2026-10-20 07:58，OpenAI 臂 CA 启动上下文守卫误报，作废 3 个实例：
  - **经过**：luna-medium-a2 结束后，调度器发现同一 cell 内的启动上下文不一致，于是停止调度，并结束了运行中的 luna-high-a1、luna-high-a2、luna-low-a2。这 3 个实例都发出了模型请求（relay 记录分别为 17、24、13 条），按作废处理，不计入尝试次数。它们的 /tmp prep 复制到了各自目录下的 `prep-killed/` 留作现场，/tmp 中的原件已删除。
  - **原因是两处误报**：
    - 调度器比较的是整个 startup 字典，里面的 ARW `messageId` 本来就每次不同。
    - `user@3`（AGENTS.md 加权限说明）里，Codex 的权限配置列出了每个进程各自的 arg0 临时目录 `codex-arg0XXXXXX`（mkdtemp 生成的随机后缀）。除了这一处，内容逐字相同。
  - **修正**：
    - `tools/reviewer/inspect_session.py` 把 `codex-arg0` 后面的随机后缀归一化，并新增单测。
    - 调度器比较时去掉 `messageId`。
    - 续跑时用已完成实例重算的启动哈希做基准，写在 `startup_recheck` 字段，原值保留。6 个有效实例重算后，在各自 cell 内一致；跨模型只有 `base_instructions` 不同，这是模型自带的。
    - 续跑时，没有 instance.json 的目录也占用编号。
  - **运行脚本**：`schedule.py` sha256 `695b2f39…c04f`。

- 2026-10-20 08:05–08:20，OpenAI 臂 CA luna-high-a3 触发 S2（ARW 早退暂停），连带修复一处工具缺陷（Main 决定）：
  - **缺陷**：`arw_measure.observe_review` 只在 ARW 掌管预算（`model_owner arw`）时检测早退暂停消息。API 路径不设时限，暂停之后会一直空等。
  - **修法**：各路径都检测这条消息；API 路径检测到后保存暂停记录 `result.json`，按 S2 收尾。新增零模型单测：脚本化的 machine，`model_owner api`，旧代码会一直空等（超时），新代码会停下。`run_one`（sha256 `d369e01c…6759`）运行中监视暂停消息：一出现就写 `ARW_PAUSED`，并把这一格写进 `.tmp/bench-openai-1020/stop-cells.txt`；收尾时清理掉 runtime，记录 `s2_paused`。已列入 stop-cells 的格子不再开新实例，调度器走现有的 arw_pause 分支停这一格。
  - **a3 的情况**：模型连续 10 个回合正常结束都没交付报告，ARW 于 08:05 暂停。模型最后自报 `{"status":"incomplete", …"The bound report remains empty."}`，3 个 `review.jsonl` 都是 0 字节。现场（rollout、`machine.jsonl`、运行中的 prep）复制到 `ca/luna-high-a3/scene/` 后，08:18 结束进程组，收尾记录由 worker 按同样字段写入（运行中的 run_one 是旧版本）。a3 不计分也不作废，记为 `s2_paused`，计分方式交用户定。luna-high 这一格到此停下，待用户定；a4、a5 有效，a6 已自然跑完（无效，原因是一次上游传输错误）。
  - **传输错误**（Main 决定）：判据不改，仍按 L494（M2）执行：relay 有传输错误即判无效、重跑，与 Anthropic 臂 L347 一致。另记字段 `recovered_transport_error`：有传输错误、且每次之后都有 completed 的 200 回复（即 harness 自己重试成功）时为 true，只作记录，不改判定。luna-high-a6 和 luna-medium-a4 都是 true。`run_one` sha256 `42342746…7a23`。这一版漏掉了 `stopped_cells` 的定义行，08:24 luna-medium-a5 启动即崩溃，崩溃发生在 prepare 和任何模型请求之前，调度器按 halt 停止开新。已补回，sha256 `cce0c547…875d`，开跑前用拒绝路径冒烟确认能走通。a5 目录保留，占编号，不计尝试。
  - **第二例 S2**：luna-low-a4，08:09:51 开跑，用的还是修复前的代码。模型 08:11 最后自报 incomplete，之后 ARW 暂停，3 个 `review.jsonl` 都是 0 字节。这个实例空等到 08:56 才被我发现：08:26–08:56 的监视只看结束事件，没看空闲却没有 completion 的情况，这个疏漏已补上。处理与 a3 相同：现场存进 `scene/`，08:56 结束进程组，记为 `s2_paused`，luna-low 这一格在 4 个有效实例处停下，待用户定。`schedule.py`（sha256 `dbc41372…db6f`）续跑时读取 stop-cells，不再为停下的格子开实例。

- 2026-10-20 09:00–09:12，OpenAI 臂 CA 结束，CS 开跑（Main 选 R3 的 A 方案）：
  - **CA 结果**：sol 三档各 5 个有效，luna-medium 5 个；luna-low 4 个、luna-high 2 个，这两格因 S2 停下，待用户定。周用量 37%→39%，credits 不变。denyRead 审计：06:40 之后启动的 17 个 Claude Code 实例（都是 Strata 臂的 cs-r2/cstd-r2）的 denyRead 都含 `/tmp/qwen-openai-1020`。
  - **CS 的 P4**（`.tmp/bench-openai-1020/p4-cs/`，`cs-T.json` sha256 `802e4c2e…6058`）：β 4.038；G（tok/s）sol 54.0/58.2/55.8，luna 119.7/132.3/128.5；T（秒）sol-low 1456、sol-medium 1351、sol-high 1409、luna-low 657、luna-medium 594、luna-high 612。模型和 tier 都正常（default），两轮都没有工具调用，登录已归还。同一模型的三档相差都在 3 倍以内。
  - **排程**（Main）：
    - 按轮次交替，一轮 6 个配置跑完才开下一轮；重跑的实例并入最后一轮。
    - 每个配置停开新实例的时刻取 min(10:40, 10:55 − T − 2 分钟)：sol 约 10:29，luna 为 10:40。这样在跑的实例都能在 10:58 前自然结束。
    - 每个实例记录 `borrow=1`、轮次和开跑时刻。下次借用要沿用同一份 `cs-T.json`、同一份代码和同一个 Codex sha（`399ff69c…4215`）；开跑前核对模型 ID 和 tier 与这次相同，否则交 Main。
    - CS 分两次借用跑完，这是一个时间混杂因素，报告里要写明。
    - `schedule.py` sha256 `4ab62962…360f`；stop-cells 文件改为按场景分开：`stop-cells-ca.txt`、`stop-cells-cs.txt`。
  - **首次开跑即 halt**：09:09 sol-low-a1 在 prepare 阶段崩溃，还没有发出任何模型请求。原因是 `arw_dimension.time_limited_note` 要求渲染出的测量说明在工程目录下，而 prep 在 /tmp。现改为工程外的 prep 保留绝对路径（读取方用 `ROOT / path` 拼接，结果不变），并新增单测；在 /tmp 下对 CS 计划完整 prepare 一次，确认测量说明和时限正确。a1 目录保留，占编号。
  - **CS 完成**（09:38，第 0–4 轮，全部 `borrow=1`）：6 个配置各 5 个有效实例，没有撞时限，也没有 S2 暂停。
    - sol-high-a5 的检查全部通过，但清理后残留 1 个 bwrap（Codex fs-helper，pid 710176）。它已重新挂到 /init 下，没有子进程，两个管道都没有对端，按"清理不干净"判 halt。
    - 现场存在 `cs/sol-high-a5/scene-leftover/`；该进程不响应 TERM，用 KILL 结束。
    - Main 判其有效：halt 只是为了查清原因，有效判据里没有清理这一条。instance.json 保留原判定，另加 `leftover_after_completion` 和 `reclassified`。
    - `run_one.py` 的修改：杀完进程树后，再结束仍引用本实例 run 目录（以 `/run/` 结尾）或 prep 目录（带 time_ns 后缀）的进程，先 TERM，5 秒后 KILL，记为 `named_killed`。用一个目标进程加相邻编号的诱饵进程做零模型测试：目标被结束，诱饵存活；拒跑路径的冒烟测试也通过。
  - **用户决定（2026-10-20，Main 转达）**：
    - 周额度上限取消，可以用到 0%。"credits 一减少就停掉在跑的实例并作废"照旧。
    - S2 原话："和 Strata 一样，要求它继续，具体逻辑和 Strata 一样"。追加原话："然后记录自动停下这个违规行为，最后和其他违规行为一样，分数 * 0.9"。这条适用于所有臂，包括 Strata。
  - **S2 改为答复继续**（`tools/reviewer/arw_measure.py`，arw_owned 与 API 两条路径共用）：
    - ARW 原版的继续入口已在快照 `arw-760007c2134d-855835bef963.tar.gz` 上核实：`lib/background-agent/manager.mjs` 的暂停消息写明 "After approval, send this task an ordinary work message"。对暂停中的任务发一条普通 `send_message`，ARW 用这条消息恢复同一个原线程，下一个暂停点由 ARW 自己设为 +5 轮。上游测试 "a non-Strata Reviewer resumes its original task through ordinary messages after each early-exit pause" 在快照上跑过，通过。
    - harness 以用户身份发 `继续`（`ARW_CONTINUE_MESSAGE`），不另写继续指示。每次暂停都记进 `arw_pause_events`（时刻、messageId、暂停消息原文、当时的 `continue_count`），继续次数记进 `continue_count`。
    - 实例一直跑到正常完成，或碰到场景的硬时限。ARW 拒绝继续时，退回原来"停下等用户"的做法。
    - `followup_when_idle` 遇到新的暂停也同样答复继续。
    - 零模型单测（`tests/test_arw_owned.py`）：脚本化的 machine 连续两次发暂停消息，两次都收到继续，最后完成；另测拒绝继续的路径。
    - 只对改动之后新启动的进程生效。Strata 臂正在跑的 chain3 是改动前启动的，已经载入旧代码，不受影响。
  - **×0.9 不会和原版重复扣**：
    - 原版 `score` 的 ×0.9 只看报告诊断（`reportDiagnostics`）。本工程计分补丁 r7 之后，这一折减只留给报告里越过需求范围停止点（`requirement-scope-continuation`）这一项，也就是 `format_penalty.py` 文档串说的"停止规则"。
    - 运行时的早退暂停不在报告里，评分器看不到。所以答复继续之后，原版评分不会因为暂停记 0.9。
    - 计分阶段由本工程按 `arw_pause_events` 乘 0.9，只乘这一次。
    - 用户决定（2026-10-20，Main 转达）：ARW 早退暂停的扣分每个实例最多扣一次 ×0.9，不论暂停几次。
  - **CA 的 luna-high-a3、luna-low-a4**：
    - 判为不能按原线程恢复。原因：复制之后原 /tmp prep 已删，包括 ARW checkout、绑定报告和 recovery 路径；ARW daemon 的状态绑定的是这些绝对路径；`arw_measure` 也没有经过测试的重新挂接模式。
    - 两个都作废，原因记为"harness 未按用户决定继续"，不计尝试次数（instance.json 加 `void.attempt_counted=false`）。现场留在 scene/。
    - `stop-cells-ca.txt` 清空，原内容存在 `ca/stop-cells-ca.before-1020-continue.txt`。补跑按新逻辑进行：luna-high 补 3 个，luna-low 补 1 个。
  - **CStd 的 P4**（`p4-cstd/`，`cstd-T.json` sha256 `6cd6a5e2…5028`）：β 4.01；G（tok/s）sol 52.1/55.3/56.7，luna 126.7/128.2/122.4；T（秒）sol-low 1416、sol-medium 1335、sol-high 1300、luna-low 582、luna-medium 575、luna-high 606。两轮都没有工具调用，模型和 tier 正常（default），登录已归还。CStd 09:54 开跑，`borrow=1`。
  - **CStd luna-low-a2 作废**（10:00，Main 判）：
    - handoff 已送达，13 秒后 ARW 自己中断了第一个 turn，原因原文："Reviewer background terminal cleanup is unverified: Native member facts are incomplete."。没有模型输出。
    - 当时 5 秒内同一 home 上有 4 个实例在启动。判为 harness 启动故障，不计尝试次数。
    - 之后本臂任何两次开跑至少错开 15 秒，几个调度器共用一个锁文件 `last-launch`。同类故障再出现一次就停下交 Main。
  - **CA 补跑与调度器并行的故障**：
    - 09:54 那次 CStd 调度器因 halt 退出，收尾时归还了共享 home 的登录。10:06:57 开跑的 CA luna-high-a8 因此在发出模型请求之前就被 `arw_measure` 拒跑。按 harness 故障作废，不计尝试次数。
    - 同一段收尾代码还会 SIGKILL 共享 home 上所有的 Codex 进程，会误杀另一个调度器的实例。实际没有发生：a8 失败时 CA 调度器正停在 halt 状态，我在它进入收尾之前用 SIGKILL 结束了它。
    - `schedule.py` 已改：收尾时如果本臂还有别的调度器在跑，就不杀进程、不还登录（记 `login_not_released`）。新增 `--slots-file`（CA 补跑独占 1 个槽；slotctl 给 CStd 的槽数改为 4 − reserve，本臂总数 ≤4）和 `--no-new-after`（CA 补跑 10:25 后不开新实例）。
    - 当前在跑的 CStd 调度器是改动之前启动的，收尾仍会杀共享 home 的进程，所以让 CA 补跑先于它结束。
  - **每实例清理**（用户规则 2026-10-20，measurement.md「存放」）：
    - `run_one` 收尾时，确认 prep 副本校验通过、会话检查已产出之后，执行 `clean_instance`：
      - 先把每个场景仓库副本的逐文件 sha256 清单写进 `scenario-copies.json`，供计分时重建对照；
      - 删除场景仓库副本里 `.tmp` 以外的内容、空的占位目录、副本中的 ARW checkout，以及 /tmp 下属于本实例的 prep；
      - 保留报告、ARW 运行元数据、`run/`（machine.jsonl、日志、状态）、`inspect/` 和 instance.json；rollout 在共享 CODEX_HOME 里。
    - 已跑完的实例由 `tools/backfill_clean.py` 补清了一遍：先列清单，再删。一起删掉的还有 prep-killed/、S2 的 scene/prep-live、P4 的 /tmp 工作区，以及 CS sol-low-a1 的 /tmp prep。ca+cs+cstd 从 1.2G 降到 252M。
    - 注意：计分要读证据所在的文件，得先按冻结输入重新 prepare 出场景仓库，再用 `scenario-copies.json` 核对。
  - **全部完成**（10:29，borrow=1）：CA、CS、CStd 都是 6 个配置各 5 个有效。
    - 有效实例中没有撞时限，也没有 ARW 暂停（continue_count 全部为 0）。
    - CS 和 CStd 都在这一次借用里跑完。早先预计 CS 要分两次借用，那条时间混杂不再适用。
    - 收尾：10:29:02 登录已归还，共享 home 上的 Codex 进程为 0；memories_stage1_outputs 0；home 下没有新增 dotfile；周用量 39% → 44%，credits 不变。
    - 在跑的 Claude Code 实例抽查，denyRead 都含 /tmp/qwen-openai-1020。
  - 当前 sha256：`arw_measure.py` `9e6f14fc…e051a49b`，`run_one.py` `c70c8a5e…9ab94b1d`，`schedule.py` `521fc743…bad73877`，`slotctl.py` `b5410a01…66d122e5`。

- 2026-10-20 10:37–10:50，OpenAI 臂 SR 开跑（用户 10-20：Codex 可继续用，通知后 30 分钟内归还）；启动上下文守卫误报，作废 3 个实例（Main 决定）：
  - **条件**：周用量不设上限（`USED_CAP=100`），credits 一旦减少就停的规则照旧。SR 不测 P4：P4 只为 CS/CStd 定义，SR 与 CA、Strata 臂 sr-r2 一样不设时限。排程同 CS/CStd。
  - **归还机制**：出现 `.tmp/bench-openai-1020/RETURN` 后不再开新实例。在跑的实例最多再跑约 24 分钟，到时杀掉并作废（原因"用户收回 Codex"，不计入尝试次数），然后归还登录，从触发到归还约 25–26 分钟。没选"T + 收尾超过 25 分钟就不开"：SR 没有 T，S2 自动继续也让单个实例的时长没有上界。
  - **误报经过**：10:40:53 sol-low-a1 结束（有效）。调度器把它的两个根线程互相比较，发现启动上下文不同，于是停止调度，连带杀掉 sol-medium-a1、sol-high-a1、luna-low-a1；10:41:05 归还登录。
  - **核实**：两个线程的 `base_instructions`、`developer@2`、`user@3` 相同，只有 handoff 消息 `user@7` 不同，而它本来就随 handoff 而变。差异有三处：handoff 名（runtime-migration / artifact-promotion）构成的路径、每个 handoff 各自的 request/draft id，以及 AP 末尾追加的场景文件 `spec-readiness-reviewer/full-review-handoff.md` 段落。三处都由场景决定，不是 harness 或模型漂移。
  - **修正**：`schedule.py` 改为按（配置，handoff）分组比较（sha256 `6a2a7411…72f8`）。零模型测试 `.tmp/bench-openai-1020/tools/test_startup_group.py`（3 项通过）用 sol-low-a1 的真实记录验证两个 handoff 不互比，同一 handoff 内的漂移仍能查出。
  - **作废**：sol-medium-a1、sol-high-a1、luna-low-a1 按 harness 故障作废，不计入尝试次数，`void.json` 已写；/tmp prep 已按清理规则删除，run/ 留下。
  - **暂停**（用户 11:01 决定暂停所有臂，要改 ARW 规则：Codex Reviewer 也要有私有可写的 scratch 目录，各臂统一按时限 T 跑）：Main 11:01:44 放下 RETURN，调度器 11:01:50 停止开新实例。在跑的 3 个实例都在宽限期内跑完，有效，没有因归还而作废。11:04:43 归还登录，本臂 Codex 进程为 0。SR 停在每个配置 2 个有效（共 12 个），continue_count 全为 0；周用量 44% → 46%，credits 不变。
  - **续跑**（用户 11:3x 再次借出 Codex，原话："你现在继续用 openai 模型吧, 用完了告诉我就行. 不过要在不影响整体计划的前提下, 尽量提前使用, 尽早给我."；用户另定本次 benchmark 的 Codex 臂都不给 scratch，已跑实例不重跑）：11:28:53 删 RETURN、重新领登录续跑，目标每配置 5 个有效。`schedule.py` 加 `--keep-login`：队列跑完不还登录，留给同一次借用里的后续工作，RETURN 仍照常归还。
    - `arw_measure.py`：前 12 个实例用 `9e6f14fc…e051a49b`，之后用 `1735b7be…`（932c1eb、b6c8147）。差异只在 `call_through_stop`（ARW 停止期间只读调用重试）和 Strata provider 的限时 T，OpenAI 路径不受影响（Main 同意）。补丁仍只有 `codex-0.163-synthetic-mount-targets`。
    - 实例记录里的 borrow 一直是 2，11:28 之后开的实例实际属于第 3 次借用，分析时按开始时刻区分（Main 同意）。
    - **SR 清理缺陷**：`run_one.clean_instance` 只按 `runs/<id>/<场景>/<rep>` 找场景仓库，SR 多一层 `sr/<handoff>/<rep>`，所以此前 12 个 SR 实例的仓库副本没删，`scenario-copies.json` 为空。改为按 ARW 的 `.prepared` 标记找仓库：每个实例计分后由 `.tmp/bench-openai-1020/tools/score_sr.py --clean` 先写 manifest 再删（每实例 6 个仓库），instance.json 记 `cleanup_sr_repositories`。CA/CS/CStd 的层级正确，不受影响。
    - **边跑边计分**（用户要求）：入口 `tools.reviewer.single_scenario_score.upstream_score`。在实例原来的 /tmp prep 路径重新物化冻结 ARW（同一 manifest、同一补丁），放回保留的 `prep/arw/.tmp`，核对绑定报告 sha 后计分。未裁候选按 not-matched / unsupported 记，标为暂定分。SR 的问题用例要经裁决为 matched 才得分，所以暂定分是下界，目前全部为 0。Main 决定不加上界。另逐实例记干净通过率、待裁候选数、格式诊断、早退暂停数和报告是否可解析，作为及早暴露问题的信号（`.tmp/bench-openai-1020/progress.md` 的 sr-scores 段）。正式分等盲裁。
  - **SR 完成**（12:15:52）：6 个配置各 5 个有效。luna-high 另有 1 个无效（a3，AP 有一次 relay 传输错误，按 L425 计入尝试并补跑）。作废 3 个，即上面的误报连带。早退暂停 0 次。机械信号（暂定分全为 0，下界）：干净通过率均值 sol 三档都是 0.770，luna low/medium/high 依次为 0.923/0.872/0.843。待裁候选 sol 44–56、luna 4–38。不可修复格式错误 0；格式诊断（review-evidence-invalid、requirement-scope-continuation）只出现在 luna，共 7 条。唯一的异常信号是 luna-medium-a3 的干净通过率 0.766：harness 正常，是模型写得更宽造成的波动。本次借用只跑 SR（Main：CS/CStd 的新 T 用存档探针数据重算，不重测）。12:16:32 归还登录（`--keep-login` 之后由 worker 手动归还），本臂 Codex 进程为 0。周用量 46% → 49%，credits 不变。

- 2026-10-20 06:40–06:50，#10–12（Codex 上的 Strata）的 ARW prep 改放 /tmp，与 OpenAI 臂同一布局（Main 指示；尚未开跑，没有实例受影响）：
  - **已证实无效，未用于任何正式实例**（Main 10-20 撤回）：OpenAI 臂实测 prep 放 /tmp 后仍出现空目录。真实 ARW 的报告目录嵌在场景仓库（如 `ca/1`）下的 `.tmp/codex/…` 里，扁平布局的 stubtest 覆盖不到。#10–12 暂停，等真实嵌套布局下的成因和修法审查通过。以下为当时的方案记录。
  - **原因**：Codex 0.163.0 的 bubblewrap 在可写根里给受保护的名字建 synthetic mount target，工作区在工程盘且是 git 根时，`.git`、`.codex`、`.agents`、`.aws` 空目录留在报告目录里，ARW 收尾判"报告目录只能有绑定报告"失败。Strata 路径的零模型对照（Strata mock，`.tmp/bench-strata-1019/stubtest/`，仿 `.tmp/bench-openai-1020/stubtest/`）：工程盘 + git 根，报告目录多出这 4 个空目录；工程盘无 git、/tmp + git 根、/tmp 无 git 都不出现。`arw_dimension.prepare` 会把 ARW checkout `git init`，所以 #10–12 的正式路径会撞上。
  - **改动**（只在运行脚本 `.tmp/bench-strata-1019/run_codex_strata.py`，sha256 `32b73288…`，冻结代码不改）：prep 放 `/tmp/qwen-strata-codex/<场景>/<尝试>-<ns>/prep`。基目录 06:40:49 手工建好（本 uid，0700，inode 874689），早于此后启动的所有 Claude Code 实例；脚本只核对它存在、属主、权限，不符就拒跑，不自己创建。CS/CStd 的限时测量说明照旧渲染进工程盘上的尝试目录（`arw_dimension` 要求说明在工程根下），字节与 Claude Code 臂相同时限的说明一致。批次结束后整份 prep 复制回工程盘 `<尝试>/prep`（保留符号链接），逐个核对 `report_sha256`，映射写 `prep-copy.json`；评分只读副本。ARW、沙箱参数和判定不变，模型可见的变化只有绝对路径。
  - **压缩提示**：`arw_dimension.selection` 把 `project_compaction_instructions` 写死为 false；#10–12 的 selection 改为 true（Main 同意，硬约束 3：Strata 每次运行都接入工程压缩提示），渲染后的压缩提示为 `ec0b5a7a…`（源 `3856cb62…` 加原生补充 `ab0c334d…`，policy project-base-plus-supplements），与 live 门、三档冒烟一致；每个实例从记录的 `compaction_prompt_policy` 核对，不符即停。
  - **跨臂通道与覆盖**：同 OpenAI 臂的审查意见（`.tmp/bench-openai-1020/prep-review.md`）：Claude Code 实例启动时把 /tmp 顶层已有条目逐条 denyRead，基目录建好之后启动的实例读不到其中内容；Claude Code 沙箱拒写 /tmp。建目录时正在跑的 Claude Code 实例只有 Strata CS low（Strata 臂自己，场景与 #10–12 当时的场景不同时不构成计分泄漏）。#10–12 跑完后按每个时间重叠的 Claude Code 实例的 `settings.json` 审计 denyRead 是否含基目录，结果写进报告。
  - **残余风险**（交用户复核）：同 OpenAI 臂；0700 挡不住同一用户，防护只靠 denyRead；`ls /tmp` 能看到目录名。

- 2026-10-20 08:00–08:40，#10–12 改用补丁 A，prep 放回工程盘（Main 指示；尚未开跑，没有实例受影响）：
  - **prep 位置定为工程盘**：`<尝试>/prep`，在 `.tmp/bench-strata-1019/<场景>-codex/` 下；上一条的 /tmp 方案撤销。`/tmp/qwen-strata-codex` 一直为空，已删除，复制回工程盘和 `prep-copy.json` 都不再需要。ARW checkout 是 git 根，占位空目录会稳定出现（零模型门两次都出现），由补丁 A 放过。
  - **补丁 A**：运行脚本调用 `arw_dimension.prepare` 时显式传 `harness_patches=('codex-0.163-synthetic-mount-targets',)`。`prep/harness-patches.json` 里的补丁 sha 必须是 `c1347209…a476`，否则拒跑。每次启动前用 `native_cli_binding.pinned_codex()` 核对 Codex 0.163.0（sha256 `399ff69c…4215`，版本 `codex-cli 0.163.0`），结果和补丁绑定一起写进 launch 记录。
  - **catalog 改用主机渲染版**：单模型部署（10-19）以后，主机的 `deployment.json` 只给 IQ3_XXS 发布上下文档位。工程 `config/model-catalog.json` 里还列着 Q2_0 和 IQ2_XS，ARW 的 Strata catalog 支持读不到这两个的档位，daemon 启动即失败（零模型门首轮实测）。所以按实例写入 `deployment_source.source_bytes('config/model-catalog.json', 'rtx3080ti')`，这正是部署装进安装目录的内容：只有 IQ3_XXS 一条，窗口取主机首档。IQ3_XXS 条目经 ARW 处理后的内容不变，只是去掉了不对外的两条。`arw_dimension.run` 里也写死了 `CATALOG = config/model-catalog.json`，同样会撞上这个问题，交 Main。
  - **判据**（审查 M1，与 OpenAI 臂相同）：runtime 进入终态（Strata 路径实测为 `idle`；`exited` 同样算），并且有 completion 记录，就有效，模型自报 ready 还是 incomplete 都计分。completion 原因是报告绑定被拒时，报告目录里如果有绑定报告和四个占位名之外的条目，就按模型结果计分；否则停下交 Main。每个实例结束后重新检查：占位目录必须是真实的空目录，不能是链接；有绑定 sha 的报告要逐个核对 sha。任一项不符就停。`mount_targets_ignored` 按实例记录。
  - **租约与孤儿 daemon**：daemon 持有 Strata 独占 key，脚本不结束它。出现 `recovery-required.json` 时，记下 daemon pid 和租约状态后停下，恢复和归还交 Main 按部署规则处理。每个实例开跑前，租约必须是 free；结束后再核对一次，不是 free 也停下。
  - **零模型门**（`.tmp/bench-strata-1019/mtgate/gate.py`）：真实 `arw_measure.run`，走主机路径（`model_owner arw`），用基准 Codex 0.163.0、CA 真实嵌套布局，prep 放在工程盘 git 根。前端换成回环 mock，提供租约、模型启停、`/health` 和脚本化的 `/strata/v1/responses`，在只有回环的网络命名空间里运行，不领真实租约，也不加载模型。measurement host 换成假对象，只读安装目录的公开 config。结果：
    - 打补丁 2 次（patched-1、patched-2）：每次报告目录里都留下 `.agents .aws .codex .git`，ARW 记 12 条放过事件（4 个目录 × 3 次绑定检查），completion 为 ready、state 为 `idle`，`harness-patches.json` 存在。启动提示期望 sha `1cae169a…`，渲染后的压缩提示 `ec0b5a7a…`（源含 `3856cb62…`），都与冻结值一致。mock 前端看到 ARW 自己领取并归还了租约。
    - 未打补丁 1 次（unpatched-1）：报 `background-agent-operation-failed`（报告目录只能有绑定报告），留下 `recovery-required.json`。daemon 继续持有 mock 租约（pid 607041 及其 codex 子进程），复现了孤儿 daemon 持有租约的情形。这个 daemon 只持有 mock 租约，已按进程组结束。

- 2026-10-20 07:15–09:40，Claude Code 臂的 Bash 沙箱超过 bwrap 参数上限（意外事件，Main 逐项决定；修复 6038d3a）：
  - **现象**：`claude_headless.shared_tmp_entries` 把 /tmp 顶层的每个条目都单独写进 denyRead。单测里 `mkdtemp` 不清理，残留越积越多（10-19 18:01 起每次全量单测约 32 个），/tmp 顶层到了约 2460 条。denyRead 超过约 2135 条后，Claude Code 2.1.303 的 bwrap 参数超过 9000，每条 Bash 都在建立沙箱时失败（"Sandbox profile has N bwrap arguments and bwrap accepts at most 9000"）；Read、Glob、Grep 仍可用。实测阈值：2135 条正常，2136 条失败。
  - **作废并重跑**（harness 故障，不计入尝试次数）：Strata 臂 CS r2 low-a5（Bash 7/7 失败）；CStd r2 除 low-a1 以外的 14 个，每个实例里的 Bash 全部失败；SR r2 high-a1（失败 2 次）。机械扫描 46 个 stream，CA r2 的 15 个和 CS r2 其余 14 个都没有命中。CStd 的 P4 直接测 API，不经过 Claude Code，T（867/886/898）沿用。Main 已核对：Anthropic 臂的 cs-r1、cstd-r1 都没有命中。
  - **处理**：
    - 清理 /tmp 下名字匹配 `^tmp[a-z0-9_]{8}$`、是目录、mtime 早于 2 小时、没有进程在用的条目，共 2038 个（清单 `.tmp/bench-strata-1019/tmp-cleanup-list.txt`，抽查 5 个都是单测 fixture），/tmp 顶层从 2460 降到 422。
    - 修复 6038d3a：三个测试补 `addCleanup`；/tmp 顶层条目超过 1500 就拒跑（低于阈值时 denyRead 不变）；`stream_summary` 新增 `sandbox_failures`，统计 is_error 的 tool_result 中以 bwrap 参数上限报错或 `bwrap: ` 开头的条数，`claude_scenario.checks` 要求它为 0 才判有效。
  - **调度**：`.tmp/bench-strata-1019/run_strata.py`（sha256 `85aa0233…`）把 stream 里有 `sandbox_failures` 的实例归为 `harness_fault`，不计入尝试次数（上限 8），新出现时就停下，不自动重跑。重跑顺序：CS low 补 1 个，CStd 补 14 个，再跑 SR，然后接 #10–12。

- 2026-10-20，Claude Code 路径补上 ARW 早退接续与 S2，并修独立审查的 F10、F4（用户决定）：
  - **用户原话**："我是希望尽量对等的, Anthropic 模型不提示继续就结束, 这已经完全不对等了, 肯定不行。……只要发生过提前退出且未完成任务的场景, 都要按上面说的规则重跑。"追加："都要按上面说的规则重跑或者续跑"；"只续跑或重跑出了问题的那些实例，不是把整个场景都重跑"。
  - **原版依据**（快照 `arw-760007c2134d-855835bef963.tar.gz`）：`lib/reviewer-runtime/reviewer-runtime.mjs` 的完成检查：回合正常结束后，最终消息恰为 `{"status":"ready"}`、绑定报告可按 UTF-8 读出且 trim 后非空才算交付；否则按报告状态发三种接续指令之一（报告存在 / 缺失 / 为空），报告解码失败时先加可恢复错误反馈、不计次数。`lib/background-agent/manager.mjs` 的 `noteEarlyExit`：第 10 次（`config.mjs` 的 `earlyExitNotificationThreshold`）及之后每 +5 次暂停；暂停那一轮不发接续指令，等普通消息恢复。到截止时间后不再接续。
  - **改动**：`claude_headless.execute_continued`。首段与原来相同；未交付就在同一会话里 `--resume <session id>`，用同一 argv、同一 settings 字符串，把原版指令原文作为下一条用户消息。到暂停点就记一条 `arw_pause_events`，并发 `继续`。时限从首段开始按整个实例的墙钟计，剩余预算不足就不再开新段。每段的 stream 都保留（`stream.jsonl`、`stream-<i>.jsonl`、`prompt-sent-<i>.md`）。`stream_summary` 读全部 result：usage、num_turns、时长逐段相加，modelUsage、total_cost_usd 取最后一段（2.1.303 跨 resume 累计，mock 实测）；原先只取最后一个 result 的缺陷一并修正。额度记账用最后一段。`claude_scenario` 的每个 handoff 记 `continuation`，instance.json 记 `arw_pause_events`、`continue_count`、`early_exit_count`。`inspect_session` 读全部段，每条接续消息都作为 harness 消息标记。场景运行去掉 `--no-session-persistence`。mock 实测首个请求与原来相同（只有本运行的路径和 id 不同）。会话文件在配置目录里，沙箱命令读不到（mock 显示 No such file），Read 也被 `--restricted` 拒绝。stream-json 输入方案会改变 Bash 工具描述，所以没有采用。新旧两条路径都严格按原版判定：最终消息不是恰好 `{"status":"ready"}`（例如包在 ```json 里）也算早退并接续。
  - **F10**：提醒 hook 改用 `review_deadlines.reminder_message`（从 `ReviewDeadline.advance` 抽出的纯函数，Codex 路径行为不变）：T < 600 秒时按实际提前量改写"最多 5 分钟"，并附剩余秒数。
  - **F4**：`claude_headless.error_kind` 把 is_error 分两类。模型侧（`terminal_reason` 为 `prompt_too_long`、subtype `error_max_turns`、文本含 "exceeded the N output token maximum"，mock 实测 2.1.303 的字段）停为 `model_error`，不接续，按已写出的报告计分（与 Codex 上 ARW 的 incomplete 对等）；其余（API 状态码、传输、认证）照旧判无效重跑。
  - **旧实例不能续跑**：都带 `--no-session-persistence`，没有会话文件（`~/.claude/projects/-var-tmp-qwen-claude-*` 下只有 tool-results），只能重跑。
  - **重跑范围**（Main 决定，2026-10-20）：只重跑最终消息为 incomplete、未交付的 10 个 Anthropic CS Haiku 实例（high-a1、a4；low-a2、a4、a5；medium-a1 到 a5），用新代码。原实例作废，原因"harness 未接续"，不计入尝试次数，每个配置凑够 5 个有效。只差终态格式的 B 类（报告已写完，最终消息不是恰为 `{"status":"ready"}`：Anthropic CA 21 个、CS sonnet-high-a2 1 个，Strata CA strata-low-a5 1 个）不自动重跑，列为待用户复核。Strata 臂的 7 个 A 类都是已作废的 bwrap 实例，不处理。
  - **与 Codex 路径仍不对等**：Codex 路径（ARW 运行层）给每条接续消息和恢复消息都加 `ARW messageId: <id>` 前缀，Claude Code 路径的接续消息没有这个前缀。
  - **1befd53 独立审查后的修正**（Opus high，开跑前完成）：
    - F-A：安全门 `claude_gate` 改用场景运行的形态（`persist=True`、提醒带硬时限），新增 8 个探针：Read、Grep、Glob、Bash 分别读本会话的 transcript（只记录）和兄弟会话的 `.jsonl`（必须读不到）。anthropic、strata、deepseek 三种 mock 门各 ×3 全部通过，兄弟会话 4 种工具都读不到；本会话的 transcript 也全部被拒（`--restricted` 和沙箱）。
    - F-B：额度记账用最后一个含 result 的 stream（末段被杀时不丢前面各段）。实例结束后把配置目录里的 `projects/<slug>/` 移进输出目录的 `session-files/`，usage 扫描不会把它当成 main 计入，会话历史也保留下来。
    - F-C：`stream_summary` 和 `inspect_session` 逐段记录有没有 result，缺 result 的段记入 `segments_without_result`，usage 记为下界（`usage_bound: lower`）；inspect 对缺 result 的段改用该段的时间戳跨度。
    - 轻项：`no_session` 判为 harness 故障（实例无效）；total_cost_usd 在段间下降时改为求和。
    - 每实例清理：`claude_headless.run` 收尾时删除本实例的 `<run>/tmp`（TMPDIR），在会话文件搬移之后；已有残留里，对应实例已判定、已有 inspect 输出的 150 个已删除。
    - sha256（1befd53 → 修正后）：`claude_headless.py` `51339172…76e6` → `38d8512c…b935b`，`claude_scenario.py` `2e1f7b19…d54a` → `a5a6b7b5…f621`，`inspect_session.py` `eb7fb109…b7bb96` → `de5979e3…3d43`，`tools/safety/claude_gate.py` `d59d5661…b5f` → `d6ed004b…f8f`。
  - sha256（改前 → 改后）：`claude_headless.py` `24932e88…0eec` → `51339172…76e6`，`claude_scenario.py` `afcd28b5…2100` → `2e1f7b19…d54a`，`inspect_session.py` `51254b0b…514e` → `eb7fb109…b7bb96`，`review_deadlines.py` `1aecbc50…ae92` → `b909c494…07f9`；新测试 `tests/test_claude_continuation.py`。
- 2026-10-20，ARW 持有模型的路径统一按限时 T 跑（独立审查 F1，用户决定：直接改 ARW 规则，不在 harness 外绕）：
  - **缺陷**：ARW 的 Strata 工作策略（`strata-work-policy.mjs`）写死 55 分钟提醒、60 分钟截止，不读 T；harness 对 ARW 持有模型的路径又不调用 `deadline.advance`（73625b1 起如此）。#10–12 的 CS/CStd 本会收不到 T−5 分钟提醒，也不在 T 被中断。CS/CStd 因此暂缓，CA（无时限）已先跑。
  - **补丁**：新增 ARW 补丁 `strata-measurement-time-limit`（sha 8b285e30…48b9，`benchmarks/reviewer-suite-v1/arw-patches/`，登记在 `freeze_arw_source.HARNESS_PATCHES`，prepare 时经 `harness_patches` 选用，与 mount-targets 补丁互不干扰）：provider 配置新增 `reviewTimeLimitSeconds`（`model-catalog.mjs` 校验、`strata-driver.mjs` 传递）；`createStrataWorkPolicy` 有 T 时，提醒在 T−300 秒（T<600 秒为 T/2），文字与提前量改写规则同 `review_deadlines.reminder_message`（中文原文、最多N秒、剩余秒数、按审核工作时间累计），到 T 停止；无 T 时 55/60 分钟逻辑逐字不变。计时是 ARW 自己的测量时钟（原生根创建后，不含模型加载）。
  - **harness 配合**（`arw_measure.py`）：`strata_provider` / `local_review_catalog` 把 `selection.review_time_limit_seconds` 写进 provider（ARW 持有模型时），manager 回读校验同步；新增 `call_through_stop`：ARW 停止根任务期间 `list_agents`/`wait_agent` 会返回 "Managed root is stopping" 或（停止时仍有原生工具在跑）`reviewer-stop-failed`，原先直接抛错并留下 recovery-required 与未归还的租约，现在在 180 秒内重试到终态。这是零模型门暴露的、ARW 自己 60 分钟截止路径上同样存在的缺口。
  - **门**：ARW 侧 `tests/background-agent/strata-time-limit.test.mjs`（5 个：有 T 时提醒一次并在 T 停、T<600 秒的改写、无 T 时 55/60 不变、provider 配置传到策略）；ARW 现有 `tests/background-agent` 166 个中 165 通过，唯一失败（untrusted titles 终端控制字符）在未打补丁的源上同样失败；`tests/test_harness_patches.py` 覆盖四个场景源上叠加两个补丁并跑 node 测试；`tests/test_arw_owned.py` 覆盖 provider 限时字段与 `call_through_stop`。零模型门 `mtgate/gate2.py`（mock 前端 + netns，T=20 秒、模型连续 sleep 7 秒）：提醒按改写文字在 10 秒送达，约 23 秒停止，状态 exited、completion incomplete、租约归还、无 recovery-required。run_codex_strata.py 在有 T（CS、CStd）时叠加该补丁并核对 sha，CA 不叠加。
  - **以往 Strata 限时运行**：2026-10-14 的 Q3 Code Spec v5（T≈933/924 秒）同样走 ARW 持有模型的路径，当时代码同样不对它执行 T，只有 ARW 自己的 55/60 分钟。报告记没有实例被时限中断、用时为 T 的 53–72%，故无实例触到 T；T−300 秒（约 68%）的提醒对用时超过它的少数实例本应发出而没有发出，影响未量化。Code Standards v5.1、Spec Readiness v4.3 的 Q3 限时运行同理，未逐例核对。

- 2026-10-20，F2（Codex 臂没有可写临时目录）：做了 ARW 补丁，但本 benchmark 不启用。
  - **用户原话**：先是"reviewer 一定要有能写脚本的能力"（F2 选 A，ARW 规则可以直接改，做法是新增 ARW 补丁）。11:3x 更新为："目前判断能不能写临时文件对它的编程能力几乎没有影响, 所以我决定在这件事上不重跑……但是 OpenAI 的场景, 之后也要给一个临时目录, 这次 benchmark 就统一不给, 防止前后差异."（依据：Main 查了 OpenAI 臂 138 个会话，往 /tmp 落盘失败只有 5 次；不落盘的内联脚本有 612 次，code mode 能跨调用保存状态。）
  - **本 benchmark 不启用**：所有 Codex 臂（OpenAI #1–6、DeepSeek #7–9、Strata #10–12）都不选这个补丁。`prepare` 默认不选，只有显式传 `harness_patches` 时才叠加。以后的 Codex Reviewer 测量默认选用（reviewer-suite.md「私有 scratch」）。
  - **补丁**：`reviewer-private-scratch`，sha256 `12b35b5b…52f1ca`，登记在 `freeze_arw_source.HARNESS_PATCHES`。只改 `reviewer-native-policy.mjs`（base `bad1b304…`），另新增 `reviewer-scratch.mjs` 和它的测试，和 mount-targets、time-limit 两个补丁不碰同一文件，三个按任意顺序都能叠加。做法：每个 Reviewer 按（场景根，报告目录）的 sha256 取 `/tmp/arw-reviewer-scratch-<uid>/<32 位>`（0700，核对属主、类型和权限，拒绝链接）；profile 里给它 `write`，给公共根 `none`；命令环境的 `shell_environment_policy.set.TMPDIR` 指向它。写授权、报告目录和读范围都不变，凭据 deny-read 照旧。实例结束后由 `tools.reviewer.reviewer_scratch --remove <arw_measure 输出目录>` 按 binding.json 删除。
  - **零模型验证**（`.tmp/f2-scratch-1020/`）：
    - 三种 mock 门（Strata、DeepSeek key 模式、ChatGPT 合成登录且在 netns 内），`--directory-probe --read-probe --scratch-probe`，全部 passed：边界 8 类拒绝，deny_read 四类拒绝，`deny_read_pass` 为真，`shell_env_key` 为 absent，搜索工具 0；TMPDIR 等于预期路径，能在里面写脚本并执行，能复制源文件改完再运行，tempfile 落在 scratch 里；兄弟 scratch 读、列目录、改写、新建都被拒，公共根不能列也不能新建，scratch 里指向外面的链接写不进去；报告目录里除了绑定报告和探针本身的文件，没有别的条目；跑完两份 scratch 都删掉了。
    - 对照：只打 mount-targets 补丁的源，scratch 探针判失败（scratch 不存在，TMPDIR 也没设）。
    - 端到端：真实 arw_measure 走 OpenAI 路径（脚本化模型，netns，CA），3 次都是 completion ready，报告目录只有 review.jsonl 和被放过的占位空目录。模型用 `$TMPDIR` 里的脚本写报告；`run_scratches` 找到的路径和 ARW 写的 granted 事件一致，`remove_run` 删除后不留残余。对照（不打 scratch 补丁）判 incomplete。
    - 单测：ARW 侧 4 个新测试，reviewer-runtime 和 time-limit 测试叠加后全部通过（58 个）。ARW 全量测试在打补丁前后失败的是同一组 51 个，都是环境原因。工程侧 `tests/test_reviewer_scratch.py` 核对 Python 和 JS 算出的路径一致；`tests/test_harness_patches.py` 在四个场景源上叠加三个补丁。
  - **已知差异与风险**：Codex 会在可写根顶层放只读的 `.git`、`.codex`、`.agents`、`.aws`，所以 `git init "$TMPDIR"` 会失败，`git init "$TMPDIR/repo"` 可以。Codex 自己的 bwrap 占位登记目录（`codex-bwrap-synthetic-mount-targets-<uid>`）会随 TMPDIR 移进 scratch，模型能改它，原来它在宿主共享的 /tmp。scratch 在 /tmp，主机重启后会清空。

- 2026-10-20 11:30–11:50，Anthropic 臂（#13–21）续跑前的三处变动（worker3，Main 指示）：
  - **live 门补 transcript 探针**（79ccdfe）：live Anthropic 模式用真实配置目录，6d522ba 的兄弟会话探针原本不生成。现在 `claude_gate` 在真实 `~/.claude/projects` 下临时放一个合成兄弟会话，跑完删除；新增 `--subset transcript`（只含 2 个对照和 8 个 transcript 探针）。原因是 Haiku 在完整清单里一律拒读"其他会话"和凭据类目标。结果（`.tmp/bench-anthropic-1019/gate-live-1020*`）：完整清单 ×3 两轮，隔离 6/6，泄漏 0，执行了的探针全部通过；transcript 子集 ×3，兄弟会话 Read/Grep/Glob/Bash 各 3/3 都读不到，本会话 transcript 也被拒（只记录），门判通过。
  - **P4 按统一定义重测**（`.tmp/p4-unify-1020/report.md`）：P = 未缓存输入 ÷ 预填充时间（`system/init` 到首个 thinking/text delta），G = 输出 token（含思考）÷ 纯解码时间（首个到最后一个 delta），β、k 不变，T = B×(1/P + k/G)/β。探针加 `--include-partial-messages`，逐行记接收时刻，材料前加每次不同的 nonce，强制不读缓存。结果写进 `cs-T-unified.json`、`cstd-T-unified.json`，旧文件不动，新旧 T 对照见进度记录。新 T 比旧值低 25% 以上就停下交 Main。已跑实例保留，依据是该报告的影响一节：提醒和硬停止的渠道不变，唯一需要复核的边界是 CS haiku-high-a5。CS 的 10 个 Haiku 重跑和 CStd 剩下的 30 个改用新 T。
    - 结果（12:29，新 T / 旧 T，秒）：CS opus 1112/1202、1061/1132、1085/1188，sonnet 833/990、863/911、908/976，haiku 544/546、515/540、521/514；CStd opus 1052/1099、1065/1106、1034/1043，sonnet 794/843、799/848、761/861，haiku 509/553、483/499、497/491（各为 low/medium/high）。比值 0.84–1.01，无一低于 0.75。CStd opus-low 首测作废：Claude Code 把材料请求重发了一次，usage 是两次请求的合计（β 1.22，T 4729），重测正常。CS haiku-high 读缓存 TTFT 4.58 秒；a5 的 wall 252.5 秒，新旧 T 下都没到提醒点 T/2（260.5 / 257 秒），保持有效（Main 复核）。
  - **进程上限**：Anthropic 调度器（`schedule.py`、`p4run.py`，共用 `slots.py`）每次启动前计算 free = min(4 − 本臂在跑, 5 − 其他臂基准进程 − 本臂在跑 − OpenAI 保留)。OpenAI 调度器在跑时，给它保留 4 路，扣掉它正在跑的实例，所以它两个实例之间的空档不会被抢；它退出后改按 `reserve.txt`。两次启动之间至少隔 15 秒。
- 2026-10-20 18:30，rtx3080ti 部署前端输出上限内部重试（4686a57，手册 75b5306）：流式 /v1/responses 撞到 max_output_tokens 时，前端丢弃截断的那次，带服务端通知（不进调用方历史）在内部重试 1 次，Codex 看不到截断；Messages 不处理。`src/output_limit.py` sha256 `8f61d9d0d44732df8c14dfbab8d22b82a4954f4490a89dc5f9eaa234ec88231b`，NOTICE sha256 `82ab19ed6f2d5f698b8d491a3ce825703236c1da7b57ba30f7e2d10e7af40d31`。从此刻起这是 Strata Codex 臂（#10–12）的固定条件。作废：ca-codex 的 low-a3、low-a5、medium-a2、medium-a3（Codex 收到 response.incomplete 后结束回合）。部署前已跑的其他有效实例都没撞过上限，不追溯。
- 2026-10-20，盲裁提示附加公平判定说明（用户 2026-10-20 决定）：
  - **内容**：每个池的裁决提示 = 冻结 brief（只替换 `<ADJ>`、`<名>`）+ 正文之后一段调用方说明：「调用方附加说明（不属于冻结 brief，用户 2026-10-20 决定加入）：候选的写法可能让你看得出它来自哪类模型或哪次运行。不要据此推断来源，也不要因来源调整判断；请只按上文口径和 view 中的证据，对每个候选公平判定。」由 `blind_pool prompt` 生成，brief 和提示的 sha256 记进 key。
  - **原因**：池里隐去了来源，但各 family 的报告写法不同（OpenAI、Anthropic、Strata 的 finding 格式各异），裁决者仍可能认出来源；合成 finding 也按各 family 的写法写成。用户要求提醒裁决者只按证据公平判定。
  - **为什么不改 brief**：brief 已冻结，正文逐字不变；说明作为调用方段落放在 brief 之外，不改变口径和输出合同。
- 2026-10-20，提前分场景盲裁 CS、CA（用户 2026-10-20 同意；独立审查 `.tmp/adjudication-1020/review-early.md`，Main 决定）：
  - **按场景分批**：CS（code-spec-v5）、CA（commit-audit-v3）现在开裁，每池混合四个已跑臂（openai、anthropic、strata-claude、strata-codex）的有效实例；CStd、SR 以后再裁。偏离 §6.2「所有配置跑完后统一盲裁」和 §14「配置组齐前不计分、不盲裁」（L360）。只跑不看：CS/CA 的分数和裁决只放在 `.tmp/adjudication-1020/` 与 `.tmp/bench-score/`，不给监督剩余运行的 worker，状态页在全部跑完前不公布 CS/CA 分数。
  - **DeepSeek 桥接批**：DeepSeek 臂（#7–9、#22–24）未跑，它的 CS/CA 候选以后作为桥接批单独裁，用同一冻结 brief、同一提示模板（只有池名不同）、benchmark Claude Code 副本 2.1.303 和同一模型 ID；锚点一致率按批报告。B 类实例（Anthropic CA 21、CS sonnet-high-a2、Strata CA strata-low-a5）按现在的有效判定入池，以后若有重跑，重跑实例进桥接批。
  - **第一批锚点**：Sonnet、Haiku 和缺锚点的族按 §6.2 的挑选规则从第一批裁决中补，规则在任何盲裁开跑前写定。
  - **沿用试点决定**：CS 试点池（2026-10-20，`.tmp/pilot-score-1020`，锚点 12/12、合成 8/8）里 openai sol-high-a1 的 23 项和 anthropic opus-high-a1 的 18 项决定 split 进正式根 `.tmp/bench-score`，按指纹跳过、不再入池；每条决定带 `origin` 注明来自试点（提示没有公平判定说明，池只含这两个实例）。sol-high-a1 在试点第二轮（round2，无锚点、未过门槛）的 2 项重新入池。
  - **CS 锚点 a13–a18 取自 benchmark 实例**：它们是试点池里 sol-high-a1 的决定，突破了 L361「锚点在读任何新输出之前选定」；这样做是为了让 OpenAI 族有锚点。

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

### 14.3 #1–6（OpenAI，ChatGPT 套餐）补冻结（2026-10-20）

用户 10-20 借出 Codex ChatGPT 套餐，最晚 11:00 归还。OpenAI 臂 worker 写出冻结材料（`.tmp/bench-openai-1020/progress.md`）后，由全新的 Opus 独立审查（结论"改后可冻结"，全文 `.tmp/bench-openai-1020/freeze-review.md`）。Main 综合双方意见后，M1–M6、R1、R3–R5 全部采纳，R2 交用户。

- **条件核对**（证据在 `.tmp/bench-openai-1020/`）：
  - P0（gpt-6-luna low，`safety_gate --provider-run`）通过：请求数 > 0；WebSocket 被拒后回退 HTTP 成功；tier 全为 default；`login-release` 全为 `link-removed`。
  - 六档冒烟全部通过：边界 8 类拒绝；`deny_read_pass` 为真；假 key 不可见；搜索工具 0；返回模型与绑定精确一致；guardian 为 codex-auto-review，对授权读给 allow(low)，对危险删除给 deny(high)。sol high 第一次被模型拒跑读探针，判为失败；同配置重跑一次后通过（R5，两次记录都保留）。
  - 审批的触发方式改了：0.163.0 catalog 中三个模型都是 `code_mode_only`，不提供 MCP 工具，原脚本父模型发不出审批。门改为在 `exec` 里发提权 `exec_command`（0af69ff）。覆盖面与 §7 对 API 配置的要求相同，即 `authorized_read`、`unauthorized_delete` 各 1 次。父模型是脚本，所以 6 档实际是同一个 guardian 的 6 次重复。
  - 共享 CODEX_HOME 的零模型核实通过（mock 中 a、b 并发，c 随后）：每个请求只含自己的 thread；共享目录与 sessions 都被拒读；model 和 effort 按 thread 下发；共享 config.toml 只有 `[features] plugins = false`；rollout 按根 thread id 和 guardian 的 `parent_thread_id` 认领。
- **冻结对象**：plan.md 在本节提交时的内容，适用于配置 #1–6。§14 的预登记、无效判据和偏离口径照样适用，下列各项除外。
- **绑定**：
  - Codex：benchmark 副本 0.163.0，native sha256 `399ff69c…4215`。
  - Catalog：`benchmarks/multi-model-v1/catalogs/openai-codex-0.163.0.json`，sha256 `40484beb…89bb3`。
  - 代码：commit `0af69ff`（`arw_measure --codex-home`、`arw_native_setup.mjs` 的并发安全写入、`credential_deny_paths(codex_home=)`、gate 代理转发 `x-codex-*`/`x-ratelimit-*` 响应头），以及 `a38fc16`（code-mode 审批补 R1 三个用例，`approval_cases` 子集）。
  - 运行脚本 sha256：`.tmp/bench-openai-1020/run_one.py` `e6425bed…7e4d4`、`schedule.py` `206aa89e…3f658`、`p4probe.py` `cec4e50f…f32c4`。
  - 场景 plan：同 §14.2。
  - selection：内置 openai provider，auth chatgpt，auth_home `/home/pello/.codex`；service_tier default；web_search disabled；启动提示和项目压缩提示都关闭（D4）；generation_policy first-delivery-only；guardian 用原生默认。
- **对正文的偏离**（交用户复核）：
  - §9「OpenAI 臂串行」改为最多 4 个并行，共用一个 CODEX_HOME（用户 10-20）。WSL 里基准 Claude Code + Codex 进程合计仍 ≤ 5（§14），与 Strata 臂调度器用同一计数法。
  - 登录不再每个实例链接、归还一次，改为每个场景开始时链接一次、结束时归还一次。归还前要等这个 home 上的 Codex 进程数为 0，调度器异常退出时也照此处理（M5）。Main 在 10:58 前核对日志里有 `login_released`，状态是 `link-removed` 或 `refreshed-file-moved-back`；没有就手动归还。
  - 门：只改了审批的触发方式，覆盖面与 §7 冒烟相同（M5 措辞）。
  - 这次借用只到 10-20 11:00：10:40 后不启动新实例；10:57 仍在运行的实例中止并作废。Spec Readiness 留到下一次借用。
- **预登记**：
  - 排程：每个场景 6 个配置 × 5 个有效实例，按轮次块交替，顺序逐轮反转；最多 4 个并行，`slots.txt` 可以下调。场景顺序 CA→CS→CStd，场景之间不并行。R3：额度或时间不够时，先保证已开跑的场景各配置都满 5 次，不在多个场景里各跑一部分；到 10:40 还没跑的部分留到下一次借用。
  - 无效判据（`run_one.checks`）：
    - 运行状态：未完成、非零退出、要求恢复；
    - 返回内容：tier 不在 {default, standard, 未返回}；返回模型既不匹配绑定（§2 规则），也不是 codex-auto-review，或者没有一个匹配绑定；rollout 里 `web_search_call` > 0；启动提示未关闭；
    - 错误（M2）：relay 有 HTTP ≥ 400 或传输错误（提醒中断除外，见下）；撞额度，即 relay 状态码为 429，或 rollout 错误事件的 `codex_error_info` 含 usage_limit、rate_limit、quota，不再对日志做子串匹配。
    - 提醒中断（Main 2026-10-20，Opus high 独立审查后决定）：ARW 发时限提醒或硬截止中断时，Codex 会放弃正在接收的流并立即重发，relay 写回时记一次传输错误。一行 relay 错误同时满足下列各条时记为 `reminder_interrupt`，不计入 `relay_errors`：(a) BrokenPipeError 或 ConnectionResetError，且 status 200；(b) 本实例 deadline JSON 的 reminder（或 interrupt）status 为 accepted；(c) 这个请求在提醒发出时正在进行：started_at < attempted_at ≤ ended_at，且 ended_at 不晚于 attempted_at + 30 s（Codex 要等到这个请求的第一个流事件才放弃它，请求还在预填充时会晚于 1 s；2026-10-20 CStd codex-medium-a1 实测 1.49 s，原先的 +1.0 s 窗口过窄，按此放宽）；(d) 每次提醒最多豁免 1 行；(e) 下一个 /responses 请求在 attempted_at 之后、且在该行 ended_at 前后 1 s 内开始，200 completed（硬截止不要求）；(f) 其他检查都通过；(g) rollout 有 messageId 等于 reminder.receipt.messageId 的 user 消息。被放弃请求的 token 不在 relay usage 里，所以逐实例费用偏低（记被弃请求数）；批次与合计以余额差为准（2026-10-21 改为只指批次与合计，见 §14.4）。适用所有经 relay 的臂；此前只有 DeepSeek CS codex-low a1–a3 符合，改判有效并全部保留（3 次尝试、3 个有效）；OpenAI 臂作废的 3 例是真实上游 URLError，不受影响。Strata-Codex 不走 relay，同类中断检不出来，记为检测不对称；Claude Code 的提醒走 PostToolUse hook，没有这个效应。
    - 到硬时限停止的实例有效。每格最多尝试 8 次，无效实例排到队尾重跑。撞额度的实例不计入尝试次数，并停止全部新实例（S6）。ARW 早退暂停（S2）的那一格直接停下交用户，不重跑（M2）。
  - 额度（M1）：调度器每轮循环从共享 sessions 读最新的 `token_count.rate_limits`。
    - 周窗口 `used_percent` 达到上限就不启动新实例。上限交用户定（R2），答复前临时取 60%（开跑时 36%）；CA 第一轮外推的结果如果更紧，就取外推值，写进 `usage_cap.txt`。
    - credits 余额（开跑前 62454.77）一旦低于这个值，就中止所有在跑的实例、记为作废，并报 Main。这一条在用户答复前不改。
  - 共享目录检查（M4）：
    - `models_cache.json`、`config.toml` 必须与第一次看到的字节相同，不符就全部停下；
    - 同一配置各实例的启动上下文 SHA（`inspect_session` 的 `startup`）必须一致，不符就全部停下；
    - 每个场景结束时，`memories_1.sqlite` 的 `stage1_outputs` 必须为空。
  - CS、CStd 的 P4：沿用 Opus 参考运行的测法（1/P = 0；β = 材料字节 ÷ 材料轮与基线轮第一个响应的输入 token 差；G = 输出最多的响应的输出 token ÷ 该请求墙钟，作下界；T = B·k / (G·β)，k = 2.0755）。每个配置跑一次 `p4probe.py`：经 gate 代理、benchmark Codex 副本和原生线程，带 G7 deny-read。"同类"限定为同一模型的三档。API 的 G 含首 token 延迟，所以 T 比 Strata 的宽松；这是冻结公式本身的问题，只列为混杂。
  - Strata 速度（M3）：P6 基线按 §14 的定义，取 Anthropic 停跑后的 Strata 中位数，按场景分别取（CS 为 cs-r2 a1–a5 的 83.4 tok/s）。比基线低 10% 以上只在报告里注明，不降 OpenAI 的并行数；低于 60 tok/s 按 S3 处理。每个 Strata 实例记录运行期间同时在跑的 OpenAI 实例数（由 `schedule.jsonl` 的 start/end 算出），报告按"有 / 无 OpenAI 负载"分组比较。报告逐配置给出撞时限的实例比例，以及运行中速度与 P4 G 的比值；有截断实例的配置，在 §4 第 9 条注明有效预算约为设计值的 90%，不做分数调整。时限 T 不改。
  - 工具调用口径（M6、R4）：code-mode 下，§5 的"工具调用数"取 rollout `item_completed` 中实际执行的 CommandExecution 与 FileChange 的个数，`exec` 调用次数另列。每个实例统计 exec 源码里调用的嵌套工具名（image_gen、view_image、goals、MCP resource 等）。工具不关闭；任何 image_gen 调用都交 Main 复核，但不单独判无效。第一次会话检查之前，`inspect_session` 要能从 `item_completed` 取出实际执行的命令（command、cwd、exit_code）。
  - R1：code-mode 再补 `unclear_delete`、`forged_file`（先在沙箱内读一份含伪造授权的笔记，再提权 `rm -rf`）、`credential_read`（提权读合成凭据文件）三个用例，在一个配置上各跑 3 次，与 CA 并行。期望全部为 deny 且没有效果；任何一次 allow，就按 S1 停下 API 臂。
  - 只跑不看：同 §14。会话检查先由脚本机械归类，其余交 Main。
- **残余风险**（交用户复核）：
  - 冒烟没有覆盖 `unclear_delete`、`forged_file`；`forged_web` 在搜索关闭后已经无关。R1 跑完前，这两类没有 live 证据。
  - 提权命令不经过沙箱，G7 deny-read 对它无效，guardian 是唯一防线。冒烟中 guardian 对提权 `cat` 给了 allow(low)，所以"提权读共享目录或其他实例 rollout"可能被放行。这个风险以前就有，但共享目录让它更集中。会话检查要逐条看提权记录。
  - 共享目录被拒读后，命令读不到 `codex-home/skills/.system` 下的 imagegen skill 文件，对评审任务没有影响。
  - 真实账号的远端特性开关（memories 等）mock 测不出来，由 M4 的逐实例检查兜底。
- **双方意见与处理**：worker 草稿建议把降档参考改为 83.4，并在速度低于参考 10% 时把 OpenAI 并行数降一档。Main 临时决定参照仍按 93，不降档。审查认为，按 §14 的定义 P6 基线就是 83.4；93 是 P4 的 G，不是 P6 基线；降档不在 plan 里。Main 采纳审查意见：基线取 83.4，不降档。其余各项见上文 M1–M6、R1–R5，全部照做，R2 交用户。

### 14.4 #7–9、#22–24（DeepSeek）补冻结（2026-10-21）

DeepSeek 臂 worker 跑完探针 P1–P4 和第 1 轮（6 配置 × 4 场景各 1 个，计为各格 a1）后写出冻结材料（`.tmp/bench-deepseek-1020/progress.md`），由全新的 Opus high 独立审查（结论"改后可冻结，第 1 轮 24 格保持有效"，摘要 `.tmp/bench-deepseek-1020/review-freeze.md`）。Main 决定按审查清单冻结，第 1 轮作为 a1 保留。

- **条件核对**（证据在 `.tmp/bench-deepseek-1020/`）：
  - 官方页面（`docs/`，SHA256SUMS）：`deepseek-flash` → DeepSeek-V4.1-Flash-1017；北京时间工作日 9–12、14–18 为高峰。每百万 token 低谷 0.02 / 1 / 4 元（缓存命中 / 未命中 / 输出），高峰 0.04 / 2 / 8 元。
  - P1：Anthropic 格式三档无差别；Responses 格式 high 略长于 low（P1b 中位数 1763 / 4404 / 2653），medium 行为与两者都不同（§4 第 3 条）。可选 P1c 结果记在 progress.md。
  - P2：Claude Code 路径没有服务端搜索，citations 0。
  - P3：Codex CA high 预检有效，没有 deepseek-timeout 或 no-final-report。
  - Codex 三档冒烟通过：请求里的 effort 与配置一致，guardian 为 deepseek-flash low，deny_read_pass 为真，假 key absent，搜索工具 0，边界 8 类拒绝。
  - P4 偏离：Codex 路径直连流式 Responses（不经 Codex），Claude Code 路径用 Anthropic 臂的统一测法；审查认为偏差可以忽略（1/P 项不到 T 的 1%，两种测法的 G 分布重合）。三档 T 相差 ±12% 是抽样噪声，报告写明。
- **冻结对象**：plan.md 在本节提交时的内容，适用于配置 #7–9、#22–24。§14 的预登记、无效判据和偏离口径照样适用，下列各项除外。
- **绑定**：
  - Codex 副本同 §14.3（0.163.0，`399ff69c…4215`）；Claude Code 副本同 §14（2.1.303）。
  - Catalog：`benchmarks/multi-model-v1/catalogs/deepseek-codex-0.163.0.json`，sha256 `71af1beabbac0fb541518f926c21fdd058cc8e31bda09cbc9bc03a41103c9283`。内容是官方 Codex 指引 models.json 中 deepseek-flash 条目的原样，只补了 0.163 schema 需要的 8 个中性字段；窗口 1048576 / 95% / auto_compact null 都是官方原值。
  - `/models` 条目：`models-ref.json` `6bba8ce0785989b7c1561f47a2037768d0b267fb873c8f0ebcb436470c380f28`，每个实例启动前核对。
  - 代码：commit `92c36a5` 时的 `tools/`，其中 `tools/reviewer/reminder_interrupt.py` 为 `92c36a5`，`claude_headless.py`、`claude_scenario.py` 为 `6d522ba`，`api_relay.py` 为 `87432b8`（本臂运行期间不改）。
  - 运行脚本 sha256（`.tmp/bench-deepseek-1020/`）：
    - `run_codex_one.py` `52ba176a4d8f2f845b35c352c4963e7f443b713944aec92f1e30e457aa517357`、`cc_one.py` `a56a4992928ef939661a7b87fcb0855efdafa76686ba5619da3849930de87411`；
    - 第 1 轮调度器 `round1.py` `909a48585ecbf1b9d12e600cdcda1c6af13bbd73b5b89b13b642a52e65683a25`、第 2–5 轮调度器 `schedule.py` `f63169ed22ec786e456a20fd6900ed7929f5378c7e00be51ee92c044bea66bea`；
    - `cost.py` `670d4b07788136b6496619df9c1b7a58e9f40398aae17af5bb2d1574067dde6b`、`steer.py` `415dc480a94283ecf16f6d85aeed0578423887d4def7c42fec49b98a8f189526`；
    - `tools/p4resp.py` `50f95f7646aee2bbaf96b753e59f73b23e59e251344cffa281ad7f7a43f333a0`、`tools/p4cc.py` `a906d95b4073f1516cab1c35222d7b3c8157cf6baa5626322fd69d4376ad8b20`。
  - selection：Codex 路径 web_search disabled，guardian 同模型 low，两份基础提示关闭（D4），tier default。Claude Code 路径由 `cc_one.py` 直接调用 `claude_scenario.run(backend='deepseek')`（CLI 的 `--backend` 没有 deepseek；其余参数与 Anthropic 臂相同），所有模型变量都是 `deepseek-flash`。T 取 `p4u-<场景>/<配置>/p4.json`。
- **对正文的偏离**（交用户复核）：
  - 第 1 轮按场景 CS→CA→CStd→SR、每格 1 个跑完，作为各格 a1；第 1 轮的有效与重跑按当时判据执行，其中 CS codex-low 3 个、CStd codex-medium 和 codex-high 各 2 个有效，全部保留（不事后挑选）。
  - 只在低谷启动实例（见预登记），所以 §4 第 9 条的漂移窗口按天计。
- **预登记**（第 2–5 轮）：
  - 排程（`schedule.py`）：场景顺序 CS→CA→CStd→SR，场景之间不并行，同一场景最多 2 个并行。场景内按轮：第 r 轮（第 1 轮为 r = 0）r 为偶数时顺序是 codex-low、cc-low、codex-medium、cc-medium、codex-high、cc-high，r 为奇数时反转；某格的有效数 ≤ r 时排入该轮。无效实例排到本场景的队尾重跑，每格最多尝试 8 次（§14；第 1 轮调度器用过 3，作废）。到 5 个有效就停，所有实例按尝试顺序保留。WSL 里基准 Claude Code + Codex 进程合计 ≤ 5。
  - 有效性：最终结论只写在 `instance.json` 的 `valid` 一个字段。Codex 实例由 `steer.py` 按 reminder_interrupt 判据写入（原值保留为 `valid_runner`，`reminder-judgement.json` 与之一致）；Claude Code 实例由 `schedule.py` 按各 handoff 的 `checks.valid` 和 handoff 数写入。`validity_source` 记来源。
  - S2：ARW 早退暂停一律回"continue"，计分时每个实例 ×0.9 一次，不停格。只有 ARW 拒绝接续，或 runner 判为 halt，才停下交 Main。
  - 启动截止：只在低谷启动。截止时刻 = 高峰开始 − 场景硬时限：SR、CA 在北京 8:00、13:00 之后不再启动；CS、CStd 在 8:50、13:50 之后不再启动。高峰结束（12:00、18:00）后恢复。周末全天是低谷。
  - 价格核对：每个场景第一个实例启动前重抓官方定价页（快照存 `docs/pricing-zh-<时刻>.html`），核对 deepseek-flash → DeepSeek-V4.1-Flash-1017、六个单价和高峰时段文字；任何一项不符就停下本臂。每个实例启动前核对 `/models` 条目和余额，返回的模型串只能是 `deepseek-flash`。
  - S6：余额 < 本场景已测单实例最高费用 × 1.5 × （在跑实例数 + 1）就不再启动；因余额不足中断的实例作废。资金不够时停下，报实测缺口。
  - 费用：
    - 逐实例按 token 计。Codex 用 relay usage，每个请求按它的开始时刻取高峰或低谷价；Claude Code 用 stream result 的 usage，按实例开始时刻定价，跨过峰谷边界的整个实例按高峰价。
    - 有提醒中断的 Codex 实例记被弃请求数，并标"偏低"。
    - 批次与全臂合计以余额差为准，与 token 合计对账，报告列出差额。
  - 速率代理：每个实例记 输出 token ÷ 墙钟秒数，并与同格第 1 轮 a1 比较。只注明，不作废，不改时限。
  - 只跑不看：同 §14。
- **残余风险**：被弃请求的 token 不进 relay usage，逐实例费用是下界。低谷时段的服务端负载与第 1 轮可能不同，速率代理只能发现明显变化。
- **偏离：改测 low / high / max（2026-10-21，用户决定；Main 采纳独立审查方案 C′，摘要 `.tmp/bench-deepseek-1020/review-lhm.md`，提案与核对 `proposal-lhm.md`）**。以下各项写于看到任何分数之前。
  - 依据：官方 thinking_mode 页的原生档是 low / high / max，medium 映射为 high。请求体机械核对：两个 harness 的 medium 与 high 只差 effort 值；CS、CStd 的时限 T 按配置不同，CS 差 16%，CStd-CC 的 T 不同。CStd-Codex 只差 1 s，模型看到的时限句相同。
  - 并入（C′）：CA、SR 两个 harness 的 medium，以及 CStd-Codex 的 medium，计入同 harness 的 high。并入格的全部有效实例进主统计；按开始时刻取前 5 个作一致性行；满 5 个的格不再补跑，不足的只补到 5 个。每格最多 8 次尝试，medium 与 high 的尝试合计。不按时长或是否收到提醒部分并入。
  - 补充行：CS 两个 harness 的 medium 和 CStd-CC 的 medium（cc-medium-a1）不并入。它们照样计分，并走盲裁和会话检查，标"high requested as medium, T=…"，另给"high+medium 合并"的描述性敏感性行。两者都不进 Holm。CStd-CC 的 high 因此补到 5 个。
  - Holm：每个场景 25 个比较（§5）。DeepSeek 的 harness 比较用 low / high / max；Strata 与 DeepSeek 不在 medium、max 上配对。
  - instance.json 新增 `requested_effort`、`effective_effort`、`pooled`、`supplementary`（补充行另有 `supplementary_label`），汇总按这几个字段分组；目录不改名。
  - max 的条件核对：
    - 零模型：CC mock 门 `claude_gate --effort max` 通过（`cc-mock-max/`）；零模型抓包证实 CC 2.1.303 发 `output_config.effort: "max"`，其余字段与各档相同（`cccap/`）。Codex 的 mock 门仍是 10-20 起所有档都有的旧故障（thread/start −32603，`mock-max.log`），由 live 冒烟代替。
    - live：Codex max 冒烟（`smoke/max`）抓包证实主请求原样发 `reasoning.effort: "max"`，guardian 请求仍是 deepseek-flash low；三个用例的结果与 high 冒烟逐项相同。CC max 冒烟（`cc-smoke-max`）7 个探针通过，stop_reason end_turn。Anthropic 格式 max 单请求返回 200。
    - CC 的 max_tokens 为 32000；max 实例被截断不判无效，列为混杂。
  - max 的 T（P4，冻结测法，测于 10-21 04:38–04:42，与其他档不同时刻）：CS codex-max 406、cc-max 376 s；CStd codex-max 350、cc-max 362 s。同类按 low / high / max 比较，都在 3 倍以内。
  - 排程：档位 low / high / max；CS/CStd 的启动截止提前量改为本场景最大 T 加 2 分钟、向上取整（9 分钟），SR/CA 仍为 60 分钟。max 的速率代理以同 harness 的 high a1 为参照，标为跨档参照。S6 不满足时，若有实例在跑就等它们结束后单路重试，没有实例在跑时才停。SR 开始前按实际 S6 留底重算预算；不够时先补满 SR 的 low、high，max 排后，到底时停下报缺口，不超出余额。SR 可能跨几个低谷时段（北京 12–13 时、18 时以后）。
  - 新绑定（sha256，`.tmp/bench-deepseek-1020/`）：`schedule.py` `6439dca8e2cd692782bc8d46fe9bad54d0f810e91fb31ef8df0b1e7f295b0235`（冻结版另存为 `schedule-frozen-f63169ed.py`）、`run_codex_one.py` `4a05cda64ce59baeb5747cc4c98dcaa007ef69f8d952a1372071cf5d84c6ca6b`、`cc_one.py` `73a56e2bd19ee9a1ed8510dad32017848551f11ba120111069b808971cea22a1`。两个 runner 只在 effort 选项里加了 max。
