# rtx4070tis 工作记录

2026-10-30 起的新完成项写在这里。此前共用的历史保存在[旧工作记录](../work-history.md)。

## 2026-10-30

- Git 收敛为单一 `master` 分支；原 `host/rtx4070tis` 已合入并删除本地及远端分支。
- 当前主机身份改为只读 `project.private.toml` 的 `local_host`；删除 `QWEN_STRATA_HOST` 覆盖。
- 本机未找到额度预检脚本；规则明确额度预检只在 rtx3080ti 执行。
- 调参工具改为只接受当前主机的计划，为后续 rtx4070tis / IQ3_XXS 调参解开硬编码限制。
