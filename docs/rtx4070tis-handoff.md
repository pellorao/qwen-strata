# rtx4070tis 上线交接

给 rtx4070tis 上运行的会话看。本工程整体复制到这台机器，由这里的会话就地运行和调参，不从 rtx3080ti 远程管理（用户 2026-10-24）。

> 状态：2026-10-28 完成上线与初始部署；仍在执行的待办以[状态页](../.status/index.html)为准。本文保留现场步骤和结果供追溯。

## 前提（交接前在 rtx3080ti 上完成）

- 本机遗留问题已解决；多模型 benchmark v2 的冻结与运行继续只在 rtx3080ti 上做，与本机无关，本机不参与（2026-10-25）。
- 工程可移植化：
  - 工程能识别当前主机，按主机选 `config/deployments/<host>.json`；
  - 代码里不再写死 rtx3080ti 的地址和安装路径；
  - 两台机器之间的 git 同步方式已定（主仓库在 rtx3080ti Windows 侧，见下表 git 一行）；
  - 让 Codex 也能按本工程规则工作（见下节「与 Claude Code 管理方式的兼容」；工程侧已完成，2026-10-25）。
- 本文已按可移植化的结果改写（2026-10-25）。

Git 约定（2026-10-30 起）：两台机器都只使用 `master`。开工前先拉取；每组工作提交后直接推送。推送被拒绝时先 pull/rebase；不 force push。主机相关事实放在每机文件，减少并发修改共享文档造成的冲突。

## 与 Claude Code 管理方式的兼容（新机用 Codex，用户 2026-10-24）

rtx3080ti 上由 Claude Code 管理本工程，rtx4070tis 上用 Codex。同一个工程要让两种 agent 都能按同一套规则工作，工程侧已在 rtx3080ti 上落实如下（2026-10-25）：

| 方面 | Claude Code（rtx3080ti） | Codex（rtx4070tis）上的做法 |
|---|---|---|
| 工程指令 | `CLAUDE.md` 引用 `AGENTS.md` | Codex 原生读 `AGENTS.md`，内容通用，不用改 |
| 专题规则 | `.claude/rules/` 按文件头 `paths` 自动加载 | Codex 不会自动加载。`AGENTS.md` 已写明：不按路径自动加载规则的 harness，动到表中路径之前先读对应规则 |
| 可重复流程 | `.claude/skills/` | 工程根的符号链接 `.agents/skills -> ../.claude/skills`：Codex 扫描 `$REPO_ROOT/.agents/skills` 并跟随符号链接（[官方文档](https://learn.chatgpt.com/docs/build-skills)），不复制第二份。已用 Codex 0.164.0 的 `codex debug prompt-input`（不调用模型）核实：4 个 skill 全部列出，skill 根解析到 `.claude/skills` |
| 用户级规则 | `~/.claude/CLAUDE.md`、`~/.claude/docs/` | 工程依赖的运行规则（状态页、推送、用户亲手操作、后台长任务、独立审查、额度）已移进 [agent-operations](agent-operations.md)，`AGENTS.md` 指向它；内容重叠时 Claude Code 以用户级为准。个人偏好不进工程，放 Codex 用户级指令 |
| 状态页、推送 | `~/.claude/status/status.py`、`~/.claude/hooks/stop-notify/push.sh` | 脚本本身与 harness 无关，复制到同一路径后照用（见「需要用户动手的步骤」）；agent 按规则在回复前调用 `push.sh`。会话结束自动推送（Codex 的 `notify` 配置）可选，需要时另写适配脚本 |
| 额度判定 | `~/.claude/statusline/estimate.sh` 估算 Anthropic 账号额度 | Codex 用 OpenAI 额度，`estimate.sh` 不适用；是否需要类似判定**待用户决定**，决定前 Codex 侧跳过（agent-operations「额度」） |
| 子 agent 与后台 | Agent、SendMessage、CronCreate、20 分钟检查 | 长任务用分离进程（`setsid nohup`）加进度文件，至少每 20 分钟检查一次（agent-operations「后台长任务」） |
| 独立审查 | 不低于 Main 的独立 agent（Opus high） | `codex exec --sandbox read-only` 新开会话，模型和推理强度不低于 Main（agent-operations「独立审查」） |
| 记忆 | `~/.claude/projects/.../memory/` | 不跟随复制；工程必需的事实已经在文档里，记忆里有工程相关内容的，交接前移进文档 |
| git | 主仓库是 rtx3080ti Windows 侧的 bare 仓库 `C:\Users\pello\repos\qwen_strata.git`（用户 2026-10-25：主仓库必须在 rtx3080ti）；rtx3080ti 的 WSL 工程是它的子仓库，`origin` 指向本地路径 | rtx4070tis 也是子仓库，经 SSH 连 rtx3080ti 的 Windows OpenSSH 推拉（`ssh://<用户>@<rtx3080ti>/C:/Users/pello/repos/qwen_strata.git`）；两台都使用 `master`。clone 到 WSL 文件系统，`.agents/skills` 符号链接才能保留 |

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

- rtx3080ti 上启用 Windows OpenSSH 服务端（`sshd.exe` 已在系统里，需要启动服务并设为自动、放行防火墙，要 UAC），放入 rtx4070tis 的公钥；Git for Windows 已装。rtx4070tis 从主仓库 clone 工程，不要整目录复制。
- 复制私有配置。`project.private.toml`、安装目录的 `installation.private.toml` 不进 git，由用户自己放到位。`project.private.toml` 顶层的 `local_host` 是当前主机的唯一来源，由 `tools.ops.deployment_source.current_host` 读取。
- 准备 Codex 侧的用户级配置。本机由 Codex 管理，不需要 `~/.claude/` 的 CLAUDE.md、`docs/`、`statusline/`：
  - 从 rtx3080ti 复制 `~/.claude/status/status.py` 和 `~/.claude/hooks/stop-notify/` 到本机同一路径；其中 `ntfy-topic` 是私有文件，由用户自己放入。脚本需要 `python3`、`jq`、`curl`。
  - 在 Codex 用户级指令 `~/.codex/AGENTS.md` 写个人偏好（对话和文档用简体中文、回复简短等），并加一行：在本工程工作时按 `docs/agent-operations.md` 执行运行规则。工程 `AGENTS.md` 已指向该文档，这一行只作保险。
  - 决定 Codex 侧是否需要额度判定（上表「额度判定」）。
  - 可选：在 `~/.codex/config.toml` 配 `notify`，会话结束时自动推送；需另写适配脚本调用 `push.sh`。
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
   - 思考上限沿用 8192/24576；guardian 用思考 512 / 总输出 1024；采样（temperature、top_p、top_k、presence_penalty）显式写进 `installation_defaults`，调用手册要用到。
   - 写调用手册的本机段落 `docs/installation-readme-hosts/rtx4070tis.md` 和 `rtx4070tis.zh-CN.md`（段名与 rtx3080ti 的相同，内容按本机实测），缺任何一项渲染即报错。
4. 安装最新版 Strata：用 `tools.ops.upgrade_release` 或重建安装。`install_offline` 用已装在 `runtime/Strata/engine` 的引擎（按 `installed-release.json` 的 `engine_version` 核对），所以重建前先用 `upgrade_release` 装好发布版。
5. 部署（命令不加 `cd … &&` 前缀和管道）。部署会备份并删除安装目录里不对外量化的 prebuilt 和已退役的 `config/maintenance-baseline.json`；防循环已弃用（默认关闭、启动提示不加载防循环段），随工程部署即带上。
6. 检查：安全门、compact probe、短检查（`strata-upgrade` skill）。
7. GPU 调参：按[调参目录](host-tuning/README.md)「每机执行方法」对 IQ3_XXS 独立调参，rtx3080ti 的调参结论不套用。
   - 16GB 显存下要重新测 prefill（现 16384）、kv-resident（现 20480）、显存预留、专家缓存、pool-workers。
   - sm_86 专用的解码开关表（含 `STRATA_SM86_PERF`）不适用。
   - 可以顺带对照 256584 档在非 int8 KV 下的 200K 检索错误（已作为低优先级事项列入状态页）。
8. 写上线报告，登记 README「现行决定」（rtx4070tis 的参数绑定），状态页 `know` 交用户复核。

## 旧计划清理记录

`docs/plan.md` 里原有的 rtx4070tis 旧条目（「顺序」第 3、6 条、「ARW 同步与 Spec 恢复」「升级后 Spec Readiness 配置比较」「上下文配置的测量与选择」、IQ3_XXS 遗留事项）已在 rtx3080ti 上核对并删除（2026-10-24），经过见 [work-history](work-history.md)「plan 清理：rtx4070tis 旧条目」。不再适合作为当前队列的 `docs/plan.md` 已于 2026-10-30 退役；现行待办统一在状态页维护。新机不需要再做 Spec Readiness 十二实例和 Q2_0 基线；ARW 已同步到 760007c，随工程一起复制，新机只需重跑安全门等检查。
