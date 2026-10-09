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
- 每机配置由工程模板加 `config/deployments/<host>.json` 渲染生成。不把一台的配置复制给另一台，也不从安装目录反向取源。
- 部署流程：等前端空闲 → 领维护 key → 确认模型已停 → 替换 → 逐文件回读 SHA → 需要时核对服务重载 → 归还 key。
- 修改部署集合内的源文件后，同步所有已注册主机。离线的主机记为"待同步"，恢复后补上；一台成功不算全部完成。
- 调用接口或参数变化时，先改调用手册源文件，再部署。
- 部署和升级的备份放工程 `.tmp/maintenance-backups/`。
