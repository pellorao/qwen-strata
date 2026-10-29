# rtx3080ti 工作记录

2026-10-30 起的新完成项写在这里。此前共用的历史保存在[旧工作记录](../work-history.md)。

## 2026-10-30

- Git 收敛为单一 `master` 分支；原 `host/rtx4070tis` 已合入并删除本地及远端分支。
- 当前主机身份改为只读 `project.private.toml` 的 `local_host`；删除 `QWEN_STRATA_HOST` 覆盖。
- 额度预检只保留在 rtx3080ti 的 Claude Code 路径。
