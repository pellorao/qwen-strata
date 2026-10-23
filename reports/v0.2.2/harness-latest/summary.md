# harness 换到最新版（2026-10-24）

## 结论

- 工具里写死的 harness 版本改为单一配置点 `tools/reviewer/harness_pins.py`，现指向 **Codex 0.164.0** 与 **Claude Code 2.1.309** 的 benchmark 副本（用户 2026-10-23：每项工作开始时用当时最新版，工作期间固定）。pin 机制保留：Codex 核对 SHA 和版本；Claude Code 由只核对版本改为同时核对 SHA，任一不符就拒绝运行。
- 新版上单测、两侧零模型 mock 门、compact probe、Strata 上的高优先级送达实测 2 例全部通过。
- 实质差异一处：Claude Code 2.1.309 在每个请求里多加一个工具搜索占位工具，Claude 侧 mock 门第一轮因此全部失败；runner 环境设 `ENABLE_TOOL_SEARCH=false` 后去掉，重跑全部通过。日常 `qwen-agent` 路径没有改（属于部署集合，另列待办）。
- benchmark v1 的计划、导出常量和历史记录不动；冻结计划重新 prepare 时按计划自己记的 Codex 版本取副本，所以 v1 重新计分不受换版影响。

## 新副本（只读，不在 PATH 上）

| 项 | Codex 0.164.0（npm latest，2026-10-23 发布） | Claude Code 2.1.309（官方 latest） |
|---|---|---|
| 路径 | `~/.local/share/qwen-bench/codex-0.164.0/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex` | `~/.local/share/qwen-bench/claude-code-2.1.309/claude` |
| sha256 | `b93f6811d3f653f0fb83be4050d857fb9abbb111dfa2ce160563327daff7f306` | `4d704a8aecbe038affa3000f498ae17c1b4f753add8facb8764120affc99b658` |
| 来源核对 | 由 `@openai/codex@0.164.0` 与 `0.164.0-linux-x64` 两个 tarball 解出，sha512 与 registry integrity 一致；无安装脚本和符号链接，未运行任何脚本；vendor 43 个文件 | 从日常安装的 2.1.309 复制，sha256 与官方发布清单 `manifest.json`（linux-x64）一致 |

0.163.0 与 2.1.303 副本保留；0.163.0 是 v1 冻结计划重新 prepare 所需，不能删。

## 代码改动

- 新增 `tools/reviewer/harness_pins.py`：两个版本、两个 SHA、副本路径，以及 `codex_binary(version)`。
- `native_cli_binding.py`、`claude_headless.py` 改从 `harness_pins` 取值；`pinned_binary` 核对 SHA 和版本；`CLAUDE` 默认值由 PATH 上的 `claude` 改为副本；`claude_scenario --claude` 不再必填，`claude_gate` 默认用副本。
- `tools/tuning/arw_dimension.selection`：冻结计划用计划自己记的 Codex 版本的副本（第一轮单测 5 个错误即由此而来）。
- `claude_headless.environment` 加 `ENABLE_TOOL_SEARCH=false`，注释记录 2.1.309 上的核对项。
- 测试：`test_claude_headless`、`test_native_cli_binding`、`test_arw_dimension`、`test_output_limit_e2e`。
- 文档：测量规则「harness 版本」写明唯一配置点与旧副本保留条件；`tools/README.md`；调用手册源文件「自动压缩」记 2.1.309 核对结果，已 `deploy --docs-only` 到 rtx3080ti（只换手册，前端未重启）；plan 第 13 项前置标为完成。

## 检查结果

- 单测：全量 748 项通过。
- Claude 侧 mock 门（a71d578 的 5 组中 Claude 的 4 组：anthropic、strata、deepseek 各 ×3，`--pair` ×2）：第一轮全部 `isolation_pass=false`，探针都没失败，只是工具表不符；加 `ENABLE_TOOL_SEARCH=false` 后 4 组全部通过。
- Codex 侧 mock 门（`safety_gate --mock-report-write --directory-probe --read-probe`）通过；边界、凭据 deny-read、`shell_env_key absent` 与 0.163.0 逐项相同；请求中模型可见内容（工具表、input、instructions）除路径和日期外相同。
- Codex 其他零模型检查：`verify_codex_compact_prompt` 通过（原生压缩提示仍为 `ab0c334d…`）；`--mock-approval` routing 通过；`debug models --bundled` 的 catalog 与 0.163.0 逐字节相同。`--write-tool apply_patch` 判 failed，原因是该模式下边界探针不运行（`boundary.ran=false`），属工具组合限制，与版本无关。
- compact probe：2.1.309 副本 `--repeat 3`，12 格全部通过（149.9K 不压缩，150.1K 压缩后继续）。
- 送达行为零模型对照：gen-now 与 bash-interrupt（含 `--resume`）事件序列与 2.1.303 相同。
- Strata 实测（rtx3080ti，IQ3_XXS，Strata 0.2.2 / 引擎 0.1.47）：

| 实例 | 提醒落点 | 送达方式 | 结果 | 耗时 | 引擎输出 |
|---|---|---|---|---|---|
| A 合成 `sleep 240` | 长 Bash 执行中 | 先 interrupt 再写 now | 被打断那一轮 `aborted_tools`，之后会话继续、正常结束 | 139 s | 100 tok/s |
| B commit-audit-v3 | 生成中 | now | 被打断那一轮 `aborted_streaming`；报告已交付，有效性 `valid=true`，提示 SHA 一致 | 8.6 分钟 | 106 tok/s |

两例模型都是 clean stop，租约已归还。

## 新旧版行为差异

1. Claude Code 2.1.309 每个请求多一个 `DeferredToolPlaceholder` 工具（`defer_loading`，描述 "never call this tool"）；`ENABLE_TOOL_SEARCH=false` 去掉它，mock 核实请求只有工具表变化。
2. 2.1.309 的 result 事件多 `model_usage_since_last_result` 字段；`total_cost_usd` 仍跨 `--resume` 累计，`duration_api_ms` 与 2.1.303 相同。
3. Codex 0.164.0 features：`incremental_tools`、`bedrock_setup_wizard`、`mcp_oauth_refresh_coordination` 转 stable 默认开；`worktrees`、`realtime_conversation`、`transcript_v2`、`stable_environment_tools` 标 removed。实际请求无变化。
4. denyRead、TMPDIR 隔离、stream-json、priority now、control_request interrupt、压缩点与旧版一致。

## 未验证

- `prompt_too_long` 这类错误 result 的字段格式没有在 2.1.309 上重新取样，单测仍用 2.1.303 样本。
- 2.1.303 时记下的特例（顶层 `/home`、`/tmp` 的 denyRead 不生效，bwrap 参数上限）没有单独复测；现行做法（按具名目录 deny）在新版 mock 门通过。
- 没有跑 `safety_gate --legacy-landlock`、`--scratch-probe`、`exec_escalated`，以及要用真实模型的 `verify_reviewer_sandbox`。

## 遗留

- 日常 `qwen-agent` 走 Strata 时请求里同样带占位工具，前端 `src/` 不处理 `defer_loading`，它会作为普通工具出现在 Strata 的工具表里。是否在 `qwen-agent` 设 `ENABLE_TOOL_SEARCH=false` 属于部署变更，按硬约束 1 经独立审查后决定，列入待办。

提交：`620fbf6`（代码与测试）、`a30967b`（文档、手册、plan）。运行明细在 `.tmp/harness-latest-1024/`。
