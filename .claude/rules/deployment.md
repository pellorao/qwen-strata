---
paths:
  - "src/**"
  - "config/**"
  - "scripts/**"
  - "tools/ops/**"
  - "docs/installation-directory-readme.md"
---

# 部署规则

- 安装目录只放运行所需的服务、配置和调用手册（源文件为 `docs/installation-directory-readme.md`）。工程的 reports、benchmarks、tools、tests 和主题文档不部署。
- 每机配置由工程模板加 `config/deployments/<host>.json` 渲染生成。不把一台的配置复制给另一台。
- 部署流程（`tools/ops/deploy.py`）：等前端空闲 → 领租约 → 确认模型已停 → 关闭前端 → 备份、替换 → 逐文件回读 SHA → 由计划任务重启前端并等待 `/health`。租约被持有时中止，不抢占。
- 修改部署集合内的源文件后，同步所有已注册主机。离线的主机记为"待同步"，恢复后补上；一台成功不算全部完成。
- 调用接口或参数变化时，先改调用手册源文件，再部署。
- 备份与保留（用户 2026-10-14）：部署和升级的备份放工程 `.tmp/maintenance-backups/`，只保留最新的升级备份和最近的部署备份；`artifacts/` 下每种制品只保留最新版和前一个版本（前一版用于遇到无法修复的问题时回退），更早的版本删除文件、保留下载清单中的来源和 SHA。
- 安装目录运行时不读工程目录（用户坚持）。重建安装目录时改名旧目录、移动大目录，不原地删除。租约不加自动回收或空闲超时，卡住的租约靠重启前端清除（用户拒绝过自动回收）。
- 区分请求类别（如 Codex guardian）用协议元数据（`thread_source`、subagent 头），不匹配提示词前缀（用户 2026-10-12）；没有结构化标识时先提备选并说明风险。
- 部署后用 `qwen-agent` 测 Claude Code 的冒烟检查，按测量规则「Claude Code 测试隔离」运行。
