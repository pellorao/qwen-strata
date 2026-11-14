# Hydrogen 补测进度（2026-11-14 15:25 JST，停在后台 2 小时上限）

停止原因：驱动脚本在 Bash 后台命令的 2 小时上限处被杀（不是额度）。额度读数：5h 剩 94.5%、周剩 98.5%（周窗口 11-21 13:38 重置；5h 窗口 13:09 重置过一次，当前窗口 18:38 重置）。没有后台进程在运行。**high 全部跑满；medium 只差 SR 3 个。**

## 已完成的格

| 强度 | 场景 | 有效 / 目标 | 备注 |
|---|---|---|---|
| high | CA、CS、CStd、SR | 5/5 各格 | 无作废；SR a5 本次补上（墙钟 1033 秒） |
| medium | CA | 5 / 5 | a1 无效（"stream was interrupted"，h0 非正常结束，按冻结分类为 invalid），a2–a6 有效 |
| medium | CS | 5 / 5 | 无作废 |
| medium | CStd | 5 / 5 | 无作废 |
| medium | SR | 2 / 5 | a1、a2 有效；a3 被杀作废，已移到 `.tmp/hydrobench/void/`，重跑为 a3 |
| xhigh | 全部 | 0 / 5 | 未开始 |

被杀作废的半截实例（脚本被杀留下的目录会被误算为已用尝试）：high SR a5 第一次（13:22，移到 `void/sr-hydrogen-high-a5-killed-1322`，已重跑并有效）、medium SR a3 第一次（15:22，`void/sr-hydrogen-medium-a3-killed-1523`）。`drive.jsonl` 各有一条 `void_instance`。

实例目录：`~/projects/qwen-strata/.tmp/hydrobench/<ca|cs|cstd|sr>/hydrogen-<强度>-a<n>`（共约 460 MB）；账本 `.tmp/hydrobench/drive.jsonl`，运行日志 `drive-run4.log`。

## 续跑命令（`-I`）

```
cd ~/projects/qwen-strata/benchmarks/multi-model-v1/runners/hydrogen-1114
python3 -I drive.py status
python3 -I drive.py run --efforts medium xhigh --max-minutes 100     # Bash run_in_background，timeout 7200000
touch ~/projects/qwen-strata/.tmp/hydrobench/STOP                    # 要停时
```

**必须带 `--max-minutes 100`**：Bash 后台命令最长 2 小时（7200000 ms），到点会杀掉脚本，半截实例留下空洞。`--max-minutes` 让脚本超过 100 分钟后不再启动新实例（一个实例最长约 17 分钟），自己干净退出（账本 `time_stop`）；Main 再开下一轮，同一命令。若仍发现 `quota_stop` 以外的非正常停下，先查 `ps` 无残留 agy/bwrap，再把无 `result.json` 的实例目录移到 `void/` 后重跑。

剩余估计：medium SR 3 个（约 25 分钟）；xhigh 四格各 5 个（约 2 小时以上，xhigh 思考多）。额度很宽：medium 每实例只用 0.1–0.4 点 5h（比 high 低一个数量级），周剩 98.5%。

## 还没做的步骤
1. medium SR 3 个、xhigh 全部。
2. 盲裁：全部格跑完后按场景建池（见 plan.md §6）；Opus high 无头，unset 三个 ANTHROPIC_* 变量，每次调用后 `usage.sh --add-stream <stream> common/hydrobench:judge --effort high`；先写预期调用数。
3. 计分（r8.4）：逐实例物化、计完即删，`--root` 下峰值约 100 MB（Main 已批准总量约 0.8 GB）。
4. 导出（单独文件）与报告。
