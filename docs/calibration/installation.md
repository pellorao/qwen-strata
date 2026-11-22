# rtx3080ti 参数校准

本页保存 rtx3080ti 的本机证据。通用方法见[调参目录](README.md)，历史与统计见[调优记录](../tuning.md)。

## 系统环境

2026-10-11 起：前端计划任务以最高权限、Normal 优先级（Priority 4）运行；专家区使用 2 MB 大页（已授予“Lock pages in memory”）；页面文件固定 32768 MB，commit 上限 95.8 GiB。此前的 IQ3_XXS 第 0–4 维在 Below normal、无大页、页面文件 16384 MB 下完成；维内对照仍有效，绝对速度不与之后直接比较。

## 模型覆盖

| 模型 | 独立调参状态 |
| --- | --- |
| Q2_0 | 完成六项选择专项；显存三值及 spec-min-p 两值未运行；**不对外，默认不测**（2026-10-19） |
| IQ2_XS | **未独立调参**；安装及短调用验收不是参数选优；**不对外，默认不测**（2026-10-19） |
| IQ3_XXS | **唯一对外模型**；2026-10-11 起在 v0.1.42 上逐维调参，详见下文 |

## Q2_0

| 参数维度 | 测试范围／次数 | 结论与选择 |
| --- | --- | --- |
| CPU核心分配 | auto／all，各3，共6；[报告](../../reports/v0.1.40.1/resource-calibration/cpu-affinity/summary.md) | all任务平均少17.9%，已采用并部署；只证明该机短任务收益 |
| CPU专家线程数 | 23／15／12，各3，共9；[报告](../../reports/v0.1.40.1/resource-calibration/worker-count/summary.md) | 15比23仅少1.8%工作时间、输出速率只高0.4%，12更慢，继续23 |
| PLE读取方式 | direct／mmap，各3，共6；[报告](../../reports/v0.1.40.1/resource-calibration/ple-io/summary.md) | mmap工作多9.6%，没有证明收益，继续direct |
| 输入处理分块 | 请求8192／16384，各3，共6；[报告](../../reports/v0.1.40.1/resource-calibration/prefill/summary.md) | 16384全部降为8192，实际未形成容量对照；预置8192，不能宣称16K更快 |
| 防循环采样策略 | 温度0／top_p1，与温度1／top_p0.95；top_k20固定，各3，共6完整评审；[报告](../../reports/v0.1.40.1/loop-prevention-comparison/summary.md) | 平均循环次数36.7→60.0，未证明改善；保留0／1／20 |
| CPU辅助短输入 | 0／auto，各3，共6；[报告](../../reports/v0.1.40.2/resource-calibration/cpu-prefill-share/summary.md) | 短输入处理少24.4%／30.5%，72条正确；采用auto |
| 显存预留 | 1024／768／512各3次；[报告](../../reports/v0.1.41/vram-reserve/summary.md) | 选定512；只写入本机Q2_0的`model_overrides` |
| spec-min-p | 旧组固定0.7，没有0.5／0.7对照；[计划](../../benchmarks/resource-calibration-v1/rtx3080ti-spec-min-p-plan.json)未运行 | 安装预置仍0.5；旧维护起点0.7不等于已验证更优 |

## IQ2_XS

尚未独立调参，没有该模型的参数赢家。不对外、默认不测（2026-10-19）；只有用户提出专门任务时，才重新固定 pack、tokenizer、profile、容量、预算和候选。

## IQ3_XXS

2026-10-11 起在 Strata v0.1.42 上逐维调参。2026-10-13 升级到 v0.1.43.1 后参数沿用，未在新版重新测量；短检查中有 2/13 个请求开始时只剩 128–276 MiB 显存，引擎建议 `--vram-reserve-mib 1280`，512 是否需要重测待长任务观察。

| 参数维度 | 测试范围／次数 | 结论与选择 |
| --- | --- | --- |
| PCIe 分担 | 引擎实测／固定 0.00，各3，共6；[报告](../../reports/v0.1.42/iq3_xxs-tuning/pcie-frac/summary.md) | 实测（定为 0.20）引擎输出快 11.1%，工作少 8.9%，全对；采用 `"pcie-frac": null` |
| CPU核心分配 | auto／all，各3，共6；[报告](../../reports/v0.1.42/iq3_xxs-tuning/pool-affinity/summary.md) | all 引擎输出快 16.9%，工作少 16.7%，全对；保持 all |
| CPU专家线程数 | 23／15／12，各3，共9；[报告](../../reports/v0.1.42/iq3_xxs-tuning/pool-workers/summary.md) | 23 引擎输出最高，全对；保持 23 |
| PLE读取方式 | 自动探测（实际 mmap）／强制 direct，各3，共6；[报告](../../reports/v0.1.42/iq3_xxs-tuning/ple-io/summary.md) | direct 冷 32K 输入快 4.6%，解码持平，内存占用可预测；采用 direct；ARW 出现分钟级停顿则退回 |
| 输入处理分块 | 请求 8192／16384，各3，共6；[报告](../../reports/v0.1.42/iq3_xxs-tuning/prefill/summary.md) | 16384 全部被引擎降为 8192，12 GB 卡上不可行；保持 8192 |
| CPU辅助短输入 | 0／auto，各3，共6；[报告](../../reports/v0.1.42/iq3_xxs-tuning/cpu-prefill-share/summary.md) | auto 引擎输入快 11.5%，输出持平；保持 auto |
| CPU辅助显式 auto／不设置 | 各3，共6；[报告](../../reports/v0.1.42/iq3_xxs-tuning/cpu-prefill-share-unset/summary.md) | 差距不显著；维持显式 auto |
| 采样默认值 | greedy／t06／t10，完整 Commit Audit 各3，共9；[报告](../../reports/v0.1.42/iq3_xxs-tuning/sampling/summary.md) | 分数差 ≤0.08，按速度选 greedy 0/1/20；循环率未测 |
| 显存预留 | 1024／768／512，各3，共9；[报告](../../reports/v0.1.42/iq3_xxs-tuning/vram-reserve/summary.md) | 768 与 512 打平，均快于 1024；采用 512；出现共享显存或卡顿退回 768 |
| spec-min-p | 0.3／0.5／0.7／0.9，完整 Commit Audit 各3，共12；[报告](../../reports/v0.1.42/iq3_xxs-tuning/spec-min-p/summary.md) | 0.9 按引擎输出最快，采用；解码稳定低于约 102 tok/s 或投机解码异常时退回 0.5 |
| 自适应层等待 `STRATA_ADAPT_LAG` | 不设置／2，各3，共6；[报告](../../reports/v0.1.42/iq3_xxs-tuning/adapt-lag/summary.md) | 2 引擎输出 117.2 对 108.2 tok/s；采用 2；ARW 解码低于约 104 tok/s 或停顿则删除 |
| 自适应层换入预算 `--adapt-swaps` | 96／160／48，各3，共9；[报告](../../reports/v0.1.42/iq3_xxs-tuning/adapt-swaps/summary.md) | 160 略高但范围重叠；保持 96 |
| 自适应层重新评估间隔 `--adapt-every` | 4／2／8，各3，共9；[报告](../../reports/v0.1.42/iq3_xxs-tuning/adapt-every/summary.md) | 效应在噪声内；保持 4 |
| 自适应层衰减 `--adapt-decay` | 0.7／0.5／0.9，各3，共9；[报告](../../reports/v0.1.42/iq3_xxs-tuning/adapt-decay/summary.md) | 保持 0.7；长会话命中下降时复测 0.9 |
| KV 显存驻留 `--kv-resident` | 20480／32768／12288，各3，共9；[报告](../../reports/v0.1.42/iq3_xxs-tuning/kv-resident/summary.md) | 12288 被静默抬高而无效；32768 无收益且少约 90 个专家槽位；保持 20480 |
| 长上下文 KV 与窗口档位 | 20480／32768 × 64K／100K／150K／200K，各3，共24；[报告](../../reports/v0.1.42/iq3_xxs-tuning/kv-resident-long/summary.md) | 各档保持 20480；256584 因 200K 检索错误不发布 |
| 窗口档位（第 9 维） | 156584／206584 × ARW，各3；[报告](../../reports/v0.1.42/iq3_xxs-tuning/window/summary.md) | 分数与速度均未分出高下；当时默认 156584 |
| 默认窗口改为 206584 | v0.1.43.1 上 150K／100K 负载 | 2026-10-14 改为 206584／150000；12 个请求全对，无 OOM；156584／100000 保留可选 |
| 投机草稿长度 `--spec` | 3／4／5／6，各3，共12；[报告](../../reports/v0.1.42/iq3_xxs-tuning/spec/summary.md) | 采用 4；速度范围重叠，优势不复现时重比 |

## 当前规则

- 每项选择只对本机唯一对外模型做；Q2_0、IQ2_XS 默认不测。
- 升级后先跑轻量检查；只有发布说明涉及对应路径、性能退化或资源告警时，才比较相关参数。
- 新报告写入 `reports/rtx3080ti/<版本或主题>/`。
