# rtx4070tis 上线交接

给 rtx4070tis 上运行的会话看。本工程整体复制到这台机器，由这里的会话就地运行和调参，不从 rtx3080ti 远程管理（用户 2026-10-24）。

> 状态：草案。rtx3080ti 上的「工程可移植化」完成后定稿；定稿前不要照做。

## 前提（交接前在 rtx3080ti 上完成）

- 所有 benchmark 遗留工作和本机遗留项已做完（`docs/plan.md` 待办，第 14 项之前的各项）。
- 工程可移植化：
  - 工程能识别当前主机，按主机选 `config/deployments/<host>.json`；
  - 代码里不再写死 rtx3080ti 的地址和安装路径；
  - 两台机器之间的 git 同步方式已定；
  - 让 Codex 也能按本工程规则工作（见下节「与 Claude Code 管理方式的兼容」）。
- 本文已按可移植化的结果改写，并删掉「状态：草案」。

## 与 Claude Code 管理方式的兼容（新机用 Codex，用户 2026-10-24）

rtx3080ti 上由 Claude Code 管理本工程，rtx4070tis 上用 Codex。同一个工程要让两种 agent 都能按同一套规则工作。可移植化阶段在 rtx3080ti 上逐项落实，下面先列出差异和打算：

| 方面 | Claude Code（rtx3080ti） | Codex（rtx4070tis）上的做法 |
|---|---|---|
| 工程指令 | `CLAUDE.md` 引用 `AGENTS.md` | Codex 原生读 `AGENTS.md`，内容通用，不用改 |
| 专题规则 | `.claude/rules/` 按文件头 `paths` 自动加载 | Codex 不会自动加载。`AGENTS.md` 写明：动到对应路径前先手动读规则 |
| 可重复流程 | `.claude/skills/` | 核实 Codex 的 skill 机制能不能直接指向同一份目录；不能就在 `AGENTS.md` 写明按路径读 SKILL.md，不复制第二份 |
| 用户级规则 | `~/.claude/CLAUDE.md`、`~/.claude/docs/` | 工程用到的部分（汇报、状态页、额度、删除前核对等）在 Codex 的用户级指令里对应写一份，或者把工程必需的内容移进工程 |
| 状态页、推送 | `~/.claude/status/status.py`、`~/.claude/hooks/stop-notify/push.sh` | 脚本本身与 harness 无关，复制后照用；会话结束的推送钩子按 Codex 的机制另接 |
| 额度判定 | `~/.claude/statusline/estimate.sh` 估算 Anthropic 账号额度 | Codex 用的是 OpenAI 额度，两台机器不再共用 Claude 额度，原来担心的冲突大体消失；Codex 侧是否需要类似的判定另定 |
| 子 agent 与后台 | Agent、SendMessage、CronCreate、20 分钟检查 | Codex 没有对应工具。长任务改用分离进程（`setsid nohup`）加进度文件；规则里依赖这些工具的部分写出 Codex 的替代做法 |
| 独立审查 | 不低于 Main 的独立 agent（Opus high） | 换成 Codex 能用的同级模型新开会话，只读；做法写进规则 |
| 记忆 | `~/.claude/projects/.../memory/` | 不跟随复制；工程必需的事实已经在文档里，记忆里有工程相关内容的，交接前移进文档 |
| git | 两台机器都提交到同一仓库 | 同步方式在可移植化阶段定，如各自分支、定期合并；避免两边同时改同一份文档 |

原则：规则和流程的正文只留一份，放在工程里；两种 harness 各自只保留一层很薄的入口。

## 机器概况

- GPU：RTX 4070 Ti SUPER 16GB（sm_89），与 rtx3080ti（12GB，sm_86）不同。
- CPU：i9-14900K；内存 64GB。
- 2026-10-09 起离线；离线前装的是 Strata v0.1.40.2。以下描述一律先核对实际状态，不沿用离线前的记录。

## 需要用户事先定的事

开始前列入状态页 `decide`：

1. 对外量化：建议沿用 IQ3_XXS（每台机器只对外一个模型）；IQ3_S 以后单独立项。
2. 影响输出的参数（采样 greedy 0/1/20、窗口默认 206584）是否沿用 rtx3080ti 的结论。建议沿用，只重测与硬件有关的维度。
3. 直接装当时的最新版 Strata，不补中间版本。

## 需要用户动手的步骤

每步先说清要做什么，取得同意后再开始：

- 复制工程和私有配置。`project.private.toml`、安装目录的 `installation.private.toml` 不进 git，由用户自己放到位。`project.private.toml` 开头加一行顶层键 `local_host = "rtx4070tis"`，工程据此识别当前主机（`tools.ops.deployment_source.current_host`；环境变量 `QWEN_STRATA_HOST` 可临时覆盖）。
- 准备用户级配置 `~/.claude/`：CLAUDE.md、`docs/`、`status/`、`statusline/`、`hooks/`。具体做法按可移植化的决定。
- 核对 BIOS 微码（14900K 的 Vmin Shift 修复）。
- 系统设置需要 UAC 授权。

## 本机步骤

1. 核对实际状态：工程文件、Strata 版本、驱动（cuda13 引擎要求 ≥580.65）、权重（实际装有哪些量化）、服务和 key 持有状态。不抢占他人持有的 key。
2. 系统环境对齐 rtx3080ti：
   - 计划任务用 Normal 优先级；
   - 锁页内存；
   - 页面文件 32768；
   - 电源计划用平衡。
3. 补全 `config/deployments/rtx4070tis.json`：
   - 监听地址、端口；
   - 对外模型的 `context_tiers`，没有它渲染 catalog 会失败；
   - 核对 `models`，现在的 `["IQ3_XXS"]` 只是占位。
   - 思考上限沿用 8192/24576；guardian 用思考 512 / 总输出 1024。
4. 安装最新版 Strata：用 `tools.ops.upgrade_release` 或重建安装。注意 `install_offline` 按发布版本拼引擎目录的已知限制。
5. 部署（命令不加 `cd … &&` 前缀和管道）。部署会备份并删除安装目录里不对外量化的 prebuilt 和已退役的 `config/maintenance-baseline.json`；防循环已弃用（默认关闭、启动提示不加载防循环段），随工程部署即带上。
6. 检查：安全门、compact probe、短检查（`strata-upgrade` skill）。
7. GPU 调参：按[调参手册](host-tuning.md)「每机执行方法」对 IQ3_XXS 独立调参，rtx3080ti 的调参结论不套用。
   - 16GB 显存下要重新测 prefill（现 16384）、kv-resident（现 20480）、显存预留、专家缓存、pool-workers。
   - sm_86 专用的解码开关表（含 `STRATA_SM86_PERF`）不适用。
   - 可以顺带对照 256584 档在非 int8 KV 下的 200K 检索错误（plan「其他未解决问题」）。
8. 写上线报告，登记 README「现行决定」（rtx4070tis 的参数绑定），状态页 `know` 交用户复核。

## 已清理的旧计划

`docs/plan.md` 里原有的 rtx4070tis 旧条目（「顺序」第 3、6 条、「ARW 同步与 Spec 恢复」「升级后 Spec Readiness 配置比较」「上下文配置的测量与选择」、IQ3_XXS 遗留事项）已在 rtx3080ti 上核对并删除（2026-10-24），经过见 [work-history](work-history.md)「plan 清理：rtx4070tis 旧条目」。新机不需要再做 Spec Readiness 十二实例和 Q2_0 基线；ARW 已同步到 760007c，随工程一起复制，新机只需重跑步骤 6 的安全门等检查。
