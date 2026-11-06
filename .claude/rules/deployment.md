---
paths:
  - "src/**"
  - "config/**"
  - "scripts/**"
  - "tools/ops/**"
  - "docs/installation-directory-*.md"
  - "docs/installation-readme-hosts/**"
---

# 部署规则

- 安装目录只放运行所需的服务、配置和调用手册。调用手册分两篇、各中英两份（英文 `X.md` 为默认，简体中文 `X.zh-CN.md`）：简介 `docs/installation-directory-readme*.md`（部署为安装目录的 `README*.md`）和详细手册 `docs/installation-directory-manual*.md`（部署为 `docs/manuals/caller-manual*.md`），共 4 份模板，两种语言内容保持同步。模板按主机和语言渲染：`{{名称}}` 取自主机配置，`{{host.<段名>}}` 是只对该主机成立的实测段落，在 `docs/installation-readme-hosts/<host>.md`（英文）和 `<host>.zh-CN.md`（中文）；新主机部署前先写它的两份段落文件。工程的 reports、benchmarks、tools、tests 和主题文档不部署。
- 每机配置由工程模板加 `config/deployments/<host>.json` 渲染生成。不把一台的配置复制给另一台。
- 每台机器只对外一个模型（用户 2026-10-19）：安装目录只放 `models` 那一个的 prebuilt 和 catalog 条目，部署时把其他量化的 prebuilt 备份后删除，权重、runtime、`data/` 留着；前端只启动它。不对外量化的覆盖、环境和档位留在主机文件里作不对外数据。维护基线 = 对外模型 + 部署默认值，不另设基线文件。用户提出专门针对不对外量化的任务时，`models` 保持不变，用 `deploy --condition` 部署该量化，专项结束后普通部署恢复；现有代码的 condition 只接受对外模型，多模型渲染和前端放行在第一次需要时实现。
- 部署流程（`tools/ops/deploy.py`）：等前端空闲 → 领租约 → 确认模型已停 → 关闭前端 → 备份、替换 → 逐文件回读 SHA → 由计划任务重启前端并等待 `/health`。租约被持有时中止，不抢占。
- 测量运行期间（运行前检查会比对安装目录和工程源码），部署集合内未部署的改动先在 `master` 上提交但不部署；审查通过后，在两个实例之间部署并推送。否则检查不通过，在跑的测量会停住（2026-10-20 d644935 曾让 Strata 臂停下）。
- 修改部署集合内的源文件后，同步所有已注册主机。离线的主机记为"待同步"，恢复后补上；一台成功不算全部完成。
- 调用接口或参数变化时，先改调用手册源文件，再部署。
- 备份与保留（用户 2026-10-14）：部署和升级的备份放工程 `.tmp/maintenance-backups/`，只保留最新的升级备份和最近的部署备份；`artifacts/` 下每种制品只保留最新版和前一个版本（前一版用于遇到无法修复的问题时回退），更早的版本删除文件、保留下载清单中的来源和 SHA。
- 安装目录运行时不读工程目录（用户坚持）。重建安装目录时改名旧目录、移动大目录，不原地删除。租约不加自动回收或空闲超时，卡住的租约靠重启前端清除（用户拒绝过自动回收）。
- 服务端优先、只做通用能力（用户 2026-10-20）：harness 与 Strata 不协调的地方（例如单次输出撞上限后 Codex 直接结束回合），尽量在前端或 Strata 内部处理，不改写 harness 的消息、不伪造工具调用。内部处理必须是对所有客户端和任务都成立的通用能力，不为某个场景、工具或 benchmark 加专门逻辑。服务端发给模型的提醒要注明是服务端自动通知，只进转发给引擎的请求，不进调用方的历史（先例：`src/loop_reminder.py`）。
- 区分请求类别（如 Codex guardian）用协议元数据（`thread_source`、subagent 头），不匹配提示词前缀（用户 2026-10-12）；没有结构化标识时先提备选并说明风险。
- 部署后用 `qwen-agent` 测 Claude Code 的冒烟检查，按测量规则「Claude Code 测试隔离」运行。
- `qwen-agent` 让 Claude Code 在档位阈值压缩，靠的是未公开的 `CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE`，升级 Claude Code 后可能退回窗口 − 23000 才压缩。用 `qwen-agent` 跑 Claude Code 的测试（冒烟、升级短检查、测量）前，核对 `claude --version` 与调用手册「自动压缩」记的核对版本；不同就先跑 `python3 -m tools.ops.claude_compact_probe --out .tmp/<工作>/compact-probe --repeat 3`（无模型、不领租约），通过后改手册里的版本号（本机段落文件的 `compact_check`，中英两份都要改）并部署；不通过按意外事件处理，修好前不经 Claude Code 路径测量。
