# 快速参数比较的范围

当前短任务批次包含53个参数维度：40个引擎参数、3个环境开关、10个采样/预算参数。每候选三次，逐维选择；不是组合矩阵或所有可能数值的穷举。冻结候选清单和实际结果见本批次parameter-comparison数据。

- 第一阶段比较prefill、KV类型/resident、worker数量、PCIe比例、MTP窗口数/接受阈值及temperature/top_p/top_k/思考和输出预算。
- 第二阶段比较专家cache、显存预留、adaptive参数、MTP工作窗口、PCIe模式、专家归约/布局、CPU affinity、PLE读取/并发、6个运行开关、3个环境开关和5个额外采样参数。
- 第三阶段比较8个图/重叠/精度开关，以及PLE行缓存、短读阈值、suffix draft、MTP cap和3个prompt checkpoint参数。一轮冷请求加两轮续接，覆盖单轮请求无法观察的前缀复用。

以下选项不作为本轮短任务的独立维度；每次升级应重新核对上游代码及适用条件，而非永久忽略：

| 类别 | 本轮边界与原因 |
|---|---|
| native投影/算子标志 | `--native`已整体启用stream-token、GR MMVF、BF16投影、PLE key、MoE combine、GDN/router/QSA/indexer/RoPE/PLE postops；重复添加同一个true标志不产生新候选。`gr-fp32-activations`仍单独验证 |
| CPU oracle q8_0 | 上游明确不能与当前expert cache或profile并用；本机无AVX-512，不用改变专家计算合同去凑一个速度条件 |
| no-ple、no-pool、graph-only、gpu-only-full | 前者删除模型计算，后者用于省略部分计算的诊断/floor；不能作为保持完整模型的优化候选。正常no-capture候选的真实启动拒绝仍保留 |
| 多GPU/P2P/layer split | 本机只有一张GPU，无有效硬件条件 |
| vision / 短向量attention | 当前是文本review，短attention路径要求max-context不超过256，与固定250K窗口不兼容 |
| RoPE缩放与上下文容量 | 需要真正的长输入质量/容量验收，31K短任务不能选出这些参数。250K窗口固定，不能以缩小窗口获得速度并称为等价 |
| mmap/resident/shared arena与conversation parking | 分别需要冷热OS页缓存、物理内存余量，或多会话停放/恢复的完整工作负载；当前单会话续接不能给出有效选择。未测，不声明已最优 |
| 外部embedding、control vector及模型资产 | 本轮未配置这些额外资产；不临时替换权重或下载素材混入引擎参数比较 |
| trace/dump/check-logits/stage timing/故障延迟 | 用于诊断、转储或故障注入，不以关闭输出或删掉核验来发布性能推荐 |
| expert profile | 按升级流程作为下一独立维度训练和验收，不与快速引擎维度组合 |

短请求的六项确定性检查用于发现明显正确性、格式及截断退化，不是ARW能力得分。temperature为零时部分采样过滤器、未启用惩罚时的penalty_last_n可能不改变采样，耗时波动不作为质量改善证据。长review、长上下文和多会话的最优配置仍需对应工作负载，不能由本表外推。

五个启动失败开关各三次的原生错误摘要见parameter-startup-errors.json。它们不是工具使用失败或ARW能力实例，不计入正式review失败统计。
