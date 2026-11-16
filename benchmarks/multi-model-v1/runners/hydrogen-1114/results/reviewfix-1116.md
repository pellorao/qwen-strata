# common/review 11-16：Q1–Q3 离线复现与修复

2026-11-16。三条问题均先复现、后修复；只执行离线统计和模拟测试，没有调用模型、Strata、裁决服务或真实运行注册，没有读取凭据文件，没有修改状态页，也没有推送。

开工已执行 `git pull --ff-only`，结果为 Already up to date。仓库只有 `master` 和 `origin/master`，没有 `main`；按本次用户明确要求从当前提交创建本地 `main` 提交。

## Q1：low 重复计数

修复前实际运行 `python3 -I benchmarks/multi-model-v1/runners/hydrogen-1114/low_report.py`，四个 low 格均显示 n=10，各实例分数列表重复一遍。离线测试核对：导出文件有 20 个有效、入选 mainStatistic 的 low 实例（每场景 5 个），20 个 id 与 `.tmp/hydrolow/records.jsonl` 的全部有效实例 id 集合相同。其他三档也是每场景 5 个。因此单独读取 hydrolow 会重复统计。

修复：只读长期保存的 `results/phase4/benchmark-results.json`，沿用有效性和 mainStatistic 筛选；返回前逐格断言 n=5。缺格、少样本、重复样本均报错。脚本不再依赖临时原始数据。

影响追溯：

- 在仓库的 reports、docs、benchmarks、README 中检索脚本名、hydrolow 和旧分数均值 ± 标准差；又检查所有 Git 跟踪的 Markdown、文本、HTML、RST、CSV 中的脚本名与完整旧 low 行，未发现错误输出被文档引用。
- 用 `git log --all -G` 检查上述文档格式中脚本名和四个旧分数均值 ± 标准差的历史引入/删除记录，没有命中。范围是本地可见 Git 历史，未访问外部网站的部署副本。
- 脚本说明指向仓库外的 `~/projects/.tasks/common/hydroeffort/report.md`，该报告确实引用 `low_report.py`；将修正后的 16 行汇总表和 16 行实例明细与它逐行对照，32/32 行完全一致，其中 low 已是 n=5。因此现有这份报告没有受错误数字影响，无需改数。
- `results/phase4/summary.md` 的 low 每格原本就是 n=5，分数标准差与重算相符；导出数据不需要重写。均值未变，只有原脚本的 n、部分标准差和重复的实例列表需要修正。未查到需要更正的已发布数字。

以下为脚本输出的新旧值，均为均值 ± 样本标准差；耗时单位为分钟。其他三档的 12 行输出完全不变。

| 场景 | 版本 | n | 分数 | 耗时（分钟） | 输出 token | 思考 token | 工具调用 | 时限（秒） |
|---|---|---|---|---|---|---|---|---|
| SR | 修复前 | 10 | 0.265 ± 0.049 | 1.9 ± 0.1 | 12201 ± 854 | 9638 ± 965 | 17.0 ± 0.9 | 3600 |
| SR | 修复后 | 5 | 0.265 ± 0.052 | 1.9 ± 0.1 | 12201 ± 906 | 9638 ± 1023 | 17.0 ± 1.0 | 3600 |
| CS | 修复前 | 10 | 0.468 ± 0.081 | 3.1 ± 0.7 | 9052 ± 1511 | 3929 ± 742 | 49.6 ± 14.5 | 900 |
| CS | 修复后 | 5 | 0.468 ± 0.086 | 3.1 ± 0.8 | 9052 ± 1602 | 3929 ± 787 | 49.6 ± 15.4 | 900 |
| CStd | 修复前 | 10 | 0.476 ± 0.044 | 1.2 ± 0.2 | 6600 ± 557 | 3798 ± 868 | 13.2 ± 4.2 | 900 |
| CStd | 修复后 | 5 | 0.476 ± 0.046 | 1.2 ± 0.2 | 6600 ± 590 | 3798 ± 920 | 13.2 ± 4.4 | 900 |
| CA | 修复前 | 10 | 0.257 ± 0.242 | 2.2 ± 0.2 | 18283 ± 2126 | 10150 ± 1099 | 26.2 ± 0.8 | 3600 |
| CA | 修复后 | 5 | 0.257 ± 0.256 | 2.2 ± 0.2 | 18283 ± 2255 | 10150 ± 1165 | 26.2 ± 0.8 | 3600 |

实例明细修复后每格只显示 5 项（修复前下列列表各重复两遍）：

| 场景 | 档 | 各实例分数 |
|---|---|---|
| SR | low | 0.276, 0.296, 0.174, 0.302, 0.276 |
| CS | low | 0.350, 0.578, 0.454, 0.441, 0.518 |
| CStd | low | 0.526, 0.436, 0.462, 0.431, 0.524 |
| CA | low | 0.707, 0.066, 0.158, 0.159, 0.194 |

## Q2：provisional 参数未分开

修复前，四个文件的真实 main 解析 `score --provisional lower/upper`，将真实 `run_bench_score` 产生的 subprocess argv 截获（禁止启动子进程），均得到单个元素 `['--provisional lower']` 或 `['--provisional upper']`，与目标 CLI 的独立参数不符；8 个子用例失败。普通 score 和 enumerate 对照通过。

修复四个文件：`hydrogen-1114/judge.py`、`judge_low.py`、`timelimit-rerun/judge_carbon.py`、`judge_old.py`。mode 统一为参数列表，score 传 `['--provisional', value]` 或 `[]`，enumerate 传 `['--enumerate']`，构造 argv 时用 extend。修复后四文件 × 四种模式（lower、upper、无 provisional、enumerate）全部通过截获 argv 和 argparse 解析检查。没有执行真正的计分或裁决流程。

## Q3：锁目录缺失

从 drive.py 提取真实 acquire_slot 函数，ROOT 指向工程 .tmp 下的新临时目录，usage guard 用假对象代替。修复前调用即报 `FileNotFoundError: .../.tmp/carbonbench/slot.lock`，不会走到注册。

修复：open 前执行 `lock.parent.mkdir(parents=True, exist_ok=True)`。修复后同一最小复现成功创建锁文件，并调用假 register 一次；保留原有 flock 保护。未触及真实锁或注册表。

## 验证

`python3 -m unittest tests.test_hydrogen_reviewfix -v`：4 项通过，覆盖 Q1 单源统计及缺失/重复断言、Q2 四文件四模式、Q3 缺目录创建。修复前同一组的前三项回归测试复现 12 个失败子用例和 1 个 FileNotFoundError（断言防护测试为修复后新增）。Q1 脚本已离线重算并与外部报告逐行核对；未进行任何真实模型运行验证，也未运行可能涉及服务的全量测试。
