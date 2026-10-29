# 报告目录

已有 `reports/v*` 历史报告保留原路径。2026-10-30 起，单机产生的新报告写入：

```
reports/<host>/<版本或主题>/
```

例如 `reports/rtx4070tis/v0.2.7/upgrade.md`。一次跨主机汇总的基准报告原则上归入实际执行主机；确需共享的结果另放 `reports/shared/<主题>/`。

`reports/` 只放已结束测量的 `summary.md` 和可重算的完整精度数据；运行明细留在 `.tmp/`。
