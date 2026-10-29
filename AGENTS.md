# qwen_strata

维护本地 Qwen3.8-Flash-Next / Strata 推理服务（Windows 原生运行），并测量它作为 Codex / Claude 等 agent 后端的表现。

专题规则：Claude Code 按文件头 `paths` 自动加载；不按路径自动加载规则的 harness（如 Codex、Antigravity/agy），动到表中路径之前先读对应规则。在 plan、`.tmp` 或对话里设计测量、评分口径、场景时，路径触发覆盖不到，也要先读对应规则。可重复流程在 `.claude/skills/`（Codex、Antigravity 经符号链接 `.agents/skills` 发现同一份）。整个工程的现行决定在 [README](README.md#现行决定)。

运行规则（状态页与推送、后台长任务、独立审查、额度）：没有加载用户级 `~/.claude/` 规则的 harness（如 Codex、Antigravity），开始工作前读 [agent-operations](docs/agent-operations.md)。

Codex CLI 定时唤醒、未来待办提醒或 subagent 周期检查：读 [codex-cli-scheduling](docs/codex-cli-scheduling.md)，timer 只能 queue 到仍打开的现有会话。

| 专题规则 | 适用路径 |
|---|---|
| [测量](.claude/rules/measurement.md) | `tools/`、`reports/`、`benchmarks/` |
| [防循环检测](.claude/rules/loop-detection.md) | `benchmarks/loop-detection-v2/`、`tools/loop/` |
| [ARW Reviewer](.claude/rules/reviewer-suite.md) | `benchmarks/reviewer-suite-v1/`、`tools/reviewer/`、`tools/safety/` |
| [部署](.claude/rules/deployment.md) | `src/`、`config/`、`scripts/`、`tools/ops/`、调用手册源文件 |

## Git 与主机

- Git 只有一个长期分支 `master`，两台机器都直接在 `master` 上拉取、提交和推送。开始工作前先拉取；推送被拒绝时先 pull/rebase，禁止 force push。
- 每台机器各有一份工程副本，只管本机。当前主机只由 `project.private.toml` 顶层的 `local_host` 指定；`python3 -m tools.ops.deployment_source` 只输出主机 id，是有副作用的操作校验当前主机的统一入口。部署、升级、调参和测量只接受当前主机。只读渲染和检查可以显式指定其他 host。
- 主机相关事实按机器分开：配置在 `config/deployments/<host>.json`，调用手册段落在 `docs/installation-readme-hosts/<host>.md`，主页在 `docs/hosts/<host>.md`，新报告在 `reports/<host>/<版本或主题>/`。主文档保留共用规则；主机差异多而常变时放子文档，少量差异可以直接写在主文档的对应小节。
- 安装路径、前端地址和凭据只在 `project.private.toml`，不写进其他来源。历史报告中的主机名表示证据来源，不是当前主机声明。

已知主机入口：[rtx3080ti](docs/hosts/rtx3080ti.md)、[rtx4070tis](docs/hosts/rtx4070tis.md)。

## 硬约束

1. **默认工作方式：按状态页自主推进**（用户 2026-10-14）。按 `.status/index.html` 的 `queue` 顺序推进，做完一项接下一项，包括模型运行，不逐项等审批；会加载模型的工作开跑前按[运行计划](.claude/skills/run-plan/SKILL.md)写下计划并核对条件。待办做完就停，不自己发明新工作；rtx3080ti 的 Claude Code 按额度预检决定是否开始，其他主机没有额度预检脚本，完成 key／租约检查后直接执行；每项工作之间归还租约；用户叫停立即停；GPU 空闲时可给测量加测（见测量规则「空闲时加测」）。
   - **重要决策**（冻结、默认参数改值、部署、改测量设计）先由智能水平和推理强度不低于 Main 的独立 agent 分析并给出意见，Main 综合双方意见后执行。双方意见和结果写进该工作的报告；对整个工程有影响的结论登记到 README「现行决定」（一行：结论、日期、报告链接）；状态页 `know` 交用户复核。
   - **测量目标和设计规则由用户定**（测什么、什么算捷径、评分口径这类定义）：列入状态页 `decide`（全局规则会推送），同时做其他能推进的工作；30 分钟内没有答复，再按上一条交独立 agent 给意见后执行，并标明待用户复核。
   - **意外事件**（主机重启、租约异常、降速——引擎输出低于 60 tok/s、实例超时、工具故障等）：先记录，再尽量解决；解决不了就绕过它造成的问题（跳过受影响的步骤、改用可行的替代路径、作废受影响实例后重跑），安全地继续推进，汇报时说明。
   - **已知类型外的安全违规**：停止受影响的工作、保留现场，并列入状态页 `decide`。
   - **删除前核对**：删除文件或目录前先列出清单再核对；不删运行中工作仍在用的文件，不删文档或报告引用的数据；清理 `.tmp/` 只删已确认作废的运行目录。
   - **汇报**：每完成一个工作组，在状态页加 `know` 条目（结论、决策、偏离、遗留）；推送按全局规则。
2. **独占 key**。所有模型操作先经前端领取 key，用完归还。不抢占他人持有，不抹掉持有状态。维护流程见部署规则。
3. **基础提示必须接入**。每次模型运行都接入 `config/prompts/startup-instructions.txt` 和 `config/prompts/compact-prompt.txt`。启动提示默认去掉已弃用的防循环段加载。开跑前核对实际加载的 SHA 并保存绑定；场景提示只能追加，不能替代。例外：多模型 benchmark 中两份基础提示只给 Strata，其他模型都不接入（用户 2026-10-19，D4；做法见 [benchmark 计划](benchmarks/multi-model-v1/plan.md#3-固定条件)）。
4. **凭据不外泄**。`project.private.toml`、安装目录的 `installation.private.toml` 和 `.state/`（若存在）不读入会话，不进 git、日志、报告或提示词。
5. **每台机器只对外一个模型，参数按"主机 + 量化"绑定**（用户 2026-10-19）。对外模型是 `config/deployments/<host>.json` 的 `models`（恰好一个），所有任务都用它；当前值见各机主机说明。其他量化权重可以保留，只在用户提出专门针对它们的任务时运行或测试，做法见部署规则。一台机器或一个量化的调参结论，不套用到另一台或另一量化。
6. **工程是唯一来源**。代码、提示、调用手册和每机配置以本工程为准；安装目录只是部署目标，不反向取源。
7. **推理在 Windows 原生进程**。WSL 保持 NAT，不加端口转发。
8. **下载**。单文件不超过 1GB 可以自行下载（用户 2026-10-13/14）；超过则给出链接、大小、SHA，由用户下载。探索性下载只放 `.tmp/`，决定采用后才进入长期位置。
9. **不依赖 harness 的付费服务**。Strata 作为后端时，审批、搜索、摘要等辅助能力由 Strata 或本工程（如 Brave）提供，不使用 Codex、Claude Code 自家模型或服务；只有不需要订阅也能使用的服务才可以例外。

## 工作方式

- 开始前读 `README.md`（现行决定、主线与进展）和 `.status/index.html`（待办与当前状态），再以实际文件和服务状态为准。历史报告不等于当前状态。
- **临时文件放 `.tmp/`**：临时数据、探测脚本和中间结果都放工程 `.tmp/` 下，不放全局 `/tmp` 或会话 scratchpad（重启后 WSL 的 `/tmp` 会被清空）。禁止对 `.tmp` 整体或工程根做递归内容搜索（`grep -r`、`rg`、`find … -exec`、`xargs grep` 等），这会把运行目录里大量文件读进 WSL 缓存、占住 Windows 内存；只在已知的具体运行目录内定位，先用 `ls` 或 `find -maxdepth` 找到目录。
- **正确性优先于效率**：测量、部署和处理流程都先保证结果正确，再考虑省时；具体做法见测量规则（预热连跑、速度类参数按块交替）。
- **简化优先**：不保留一次性脚本、已关闭路线的代码和无价值的测试。新增实现前先看能否删除或合并旧的。
- 汇报时先说结论、意义和适用范围，再给关键数据和链接。失败和未验证项要明说，局部或模拟通过不说成整体通过。
- **少用付费模型**：能先用本地模型或机械检查排除的问题，先排除再决定是否需要付费模型（Opus 等的子 agent、参考运行、审计和裁决；用户 2026-10-13）。
- **昂贵搜索用二分法**（用户 2026-10-14）：调参、场景难度这类每一步都要跑模型的搜索，不做小步迭代（梯度下降式的微调需要太多步）。先定取值范围，从中点开始：结果偏小就直接跳到上界，偏大就取当前点和已知偏小点的中点，每一步把区间对半缩小。上界未知时先大步或倍增探出边界，再对半。前提是评分在区间内单调；发现不单调就停下重新划区间。单次结果有噪声，落在判定线附近时先补测再定方向。停止条件事先写进计划（区间小于有意义的分辨率，或已达到目标）。
- 进度记录：`README.md` 放现行决定和跨机主线；完成项移入 `docs/work-history/<host>.md`（旧记录留在 `docs/work-history.md`）；全部待办和仍需重复执行的流程只放状态页 `queue`。待用户决定的事项只放状态页 `decide`。

## 目录

目录布局用 `ls` 查看。`docs/` 里 `arw-upstream-issues.md`、`strata-upstream-issues.md` 记 ARW 与 Strata 的上游缺陷；`docs/hosts/<host>.md` 记录每机当前事实，`installation-directory-readme.md` 是安装目录调用手册的模板，按主机渲染（本机段落在 `installation-readme-hosts/`）。`.tmp/` 是可随时删除的运行明细，长期文档不得依赖它。

## 命令

- 测试：`python3 -m unittest discover -s tests -p 'test_*.py'`
- 工具：从工程根运行 `python3 -m tools.<子目录>.<模块>`
