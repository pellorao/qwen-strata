# 测量与维护工具

从工程根目录以包方式运行：`python3 -m tools.<子目录>.<模块>`；`.mjs` 用 `node tools/<子目录>/<文件>`。各工具的参数见 `--help`。会加载模型的工具，运行前按 [运行计划](../.claude/skills/run-plan/SKILL.md) 写下计划并核对条件。原始明细写入 `.tmp/`，只有结束后的汇总进 `reports/`。

## ops：部署与运维

只处理本机安装（经 `wslpath` 访问），不使用 SSH。

| 模块 | 用途 |
|---|---|
| `deployment_source` | 由工程模板、`config/deployments/<host>.json` 和私有配置渲染每机安装文件 |
| `deploy` | 经前端租约关闭前端，部署服务文件和调用手册，回读 SHA，再由计划任务重启前端 |
| `model_catalog` | 由所装 Codex 的 luna 条目生成日常 `config/model-catalog.json`；`--check` 核对是否与当前 Codex 版本一致 |
| `upgrade_release` | 安装已校验的 Strata 源包和引擎，带备份和回滚；同样经前端租约停服 |
| `install_offline` | 在 Windows 上用已有文件离线重建安装 |
| `claude_compact_probe` | 假 Anthropic 服务器上核对 Claude Code 在 `qwen-agent` 档位下的压缩点（阈值 ±100，两回合与回合中途），不用模型和租约 |
| `controller_client`、`measurement_host` | 测量用的前端租约客户端和引擎内部日志读取 |
| `export_reports` | 只发布按版本 / 类型的汇总 |

## metrics：计量

| 模块 | 用途 |
|---|---|
| `strata_tokens` | 从引擎内部日志统计 read / reused / generated，测量 token 的唯一来源 |
| `review_work_time` | 工作时间：排除停机和回合结束后的空闲 |
| `model_lifetime` | 模型存活时长，保留区间估计 |
| `streamed_chat` | 采集 Chat SSE 文本和时序 |
| `context_capacity`、`context_metrics` | 窗口容量公式；从原生会话提取压缩证据 |
| `prompt_policy` | 组合工程压缩提示与调用方补充 |
| `host_telemetry`、`windows_resource_sampler` | Windows 只读资源采样 |
| `measurement_format` | 统一展示，汇总后再舍入 |

## loop：防循环检测

**已弃用（2026-10-11）**，等用户触发后与服务端提醒一起删除。规则见 [loop-detection.md](../.claude/rules/loop-detection.md)，全部离线，不调用模型。

| 模块 | 用途 |
|---|---|
| `build_model_behavior_corpus`、`verify_model_behavior_annotations` | 由原生会话生成清洗语料；校验 Main 标注 |
| `loop_replay`、`replay_model_behavior`、`replay_progress_guard` | 因果重放和全集观测 |
| `verify_loop_detection_corpus` | 冻结样例回归 |
| `progress_guard`、`command_loop_guard`、`arw_command_loop_guard.mjs`、`native_command_evidence` | 无进展 / 重复命令提示原型 |
| `reasoning_loop_guard` | 文本复现原型和动态文本特征（未验证，不接入 harness） |
| `loop_reminders` | 跨调用和单响应两类提醒文本 |

## reviewer：ARW Reviewer 测量

规则见 [reviewer-suite.md](../.claude/rules/reviewer-suite.md)。

| 模块 | 用途 |
|---|---|
| `freeze_arw_source` | 冻结上游 ARW 源码字节；展开时打上 manifest 列出的工程兼容补丁并校验结果 |
| `arw_measure`、`arw_native.mjs`、`arw_native_setup.mjs`、`arw_runtime.mjs` | 用原版 ARW 运行层执行冻结交接 |
| `context_measure` | 执行一个已批准的同线程合并实例 |
| `review_deadlines`、`monitor_review_deadlines` | 55/60、10/15 分钟时限 |
| `review_continuations`、`prepare_continuation_score`、`arw_recovery` | 早停接续、上游诊断评分、停止后恢复核对 |
| `arw_metrics`、`review_observations` | 补充每轮计量；提取可见执行观测 |
| `inspect_session` | 会话检查：提取并判定每次工具调用，输出逐条动作表和标记项全文 |
| `repair_reviewer_report` | 在独立副本上做格式归一（单值行号、成对写法的范围），供评分使用 |
| `harness_pins` | 当前工作固定的 Codex、Claude Code 版本、SHA 与 benchmark 副本路径（唯一配置点） |
| `native_cli_binding`、`wsl_client`、`verify_codex_compact_prompt` | Codex CLI 绑定、app-server 客户端、原生压缩提示采集 |
| `check_briefs`、`adjudication_view` | 盲裁 brief 冻结前的机械核对；从冻结 fixture 构造盲裁 view |
| `benchmark_summary` | 多模型 benchmark 跨模型汇总：读 `bench_records` 记录与 `bench_score` 分数，按计分阶段（`--phase`，默认 1）选实例，逐格统计（含一致性行、补充行）、每场景 25 个预登记比较（Welch、Holm）、逐实例表 |

## safety：安全验收

| 模块 | 用途 |
|---|---|
| `safety_gate`、`safety_native.mjs` | 原生沙箱与 guardian 安全门，只用合成目标 |
| `verify_reviewer_sandbox` | 探测 Linux Codex 执行边界：不带 `--base-url` 为零模型 `command/exec` 探针，带上时加真实模型回合；用 ARW 运行的原生 Codex 二进制，窗口取 `--model` 的默认档 |
| `reviewer_permissions` | 测量专用 Codex 权限 profile |
| `safety_mcp_fixture` | 合成 MCP 动作，删除类工具只记录调用 |

## tuning：资源校准

| 模块 | 用途 |
|---|---|
| `resource_calibration` | 在独占 key 下执行已批准的冻结资源比较，计划文件在 `benchmarks/resource-calibration-v1/` |

## resources

- `codex/0.160.1/`：该版本 Codex 原生压缩提示及来源。换用新版 Codex 后需重新采集并新建版本目录。
- `arw/`：Reviewer 关闭上下文恢复补丁及绑定。
