# v0.1.38升级流程总结

基础回归、快速参数比较、本次已安排的profile训练及首次交付对照均已结束。用户已选择继续使用default，后续不再每次升级自动训练和跑完整profile对照；这些步骤保留为可选专项实验。所选维护基线见[完整快照](baseline.json)，原始测量细节保留在`.tmp/upgrade-cycle-v0.1.38-20261003/`。

## 所选配置与使用范围

固定Strata v0.1.38（99f3dbd0b21d1401b3769e0c0d963913607f380b）、Q2_0、medium、默认专家profile，temperature=0、top_p=1、top_k=20，总输出预算16384、思考预算4096。短任务选择spec-min-p=0.7，其余引擎参数保留基线。升级收尾时暂用250000窗口、200000压缩阈值；上下文比较结束后，用户于2026-10-05选定100000压缩阈值及新公式156584窗口，已更新快照中的引擎覆盖及harness参数。选择依据含得分／耗时的平衡和五次完整交付，见[上下文比较报告](../context-comparison/summary.md#用户选定的后续基线)；历史测量条件不追溯改写。快照记录完整启动/请求参数、版本、冻结输入清单和profile/提示词SHA。

启动通过独占控制器，显式传入快照的start_options；Responses请求指定medium，Chat请求同时指定预算。安装原始config的spec-min-p仍为0.5；省略覆盖不能复现0.7基线。不指定profile_file或profile_save_file，使用默认文件且不保存。原生ARW权限、网络与工具保留，guardian使用同一本地Qwen模型的low预算预设。统一防循环提示已部署，但不保证停止重复操作。

## 完成证据

- [升级与文件核验](../upgrade.md)、[基础回归](basics.json)确认固定源码、官方引擎、控制器鉴权、维护互斥与真实模型接口；模型继续在Windows原生执行。
- [参数比较](parameter-comparison.md)和[参数范围](parameter-scope.md)：53个维度、279次实际观测，其中15次未完成；每候选三次，按维度串行选择。仅spec-min-p=0.7满足短任务替换标准，其余保留。六项确定性检查不等于ARW能力分数；历史API口径表格原样保留，不用其数字代表新的内部token计量。
- [Brave搜索验收](brave-search.md)：桥内执行Hosted文本搜索、页面读取、查找及历史重放，调用方不需另装搜索工具。固定版本原生Hosted兼容不足的旧失败见[预检](native-tools.md)。Brave索引摘要与OpenAI缓存全文不等同；限制范围如实记录，每次后续升级仍核查官方支持。
- 原版运行层的[沙箱验收](../safety-20261004/native-host.md)、[文件审批诊断](../safety-20261004/approval-quality-preflight.md)和[MCP审批质量](../safety-20261004/approval-mcp.md)完成受控前置检查。默认:read-only加显式写路径，自动审批仍可允许低风险提权，不宣称绝对写集合隔离或任意工具调用均安全；可选严格模式保持关闭。
- 本次五任务[训练](profile-training.md)及[材料隔离](profile-isolation.md)完成，冻结默认/训练文件保留。随后八组各三次取得原版诊断分，见[首次交付对照](profile-validation-first-pass.md)及[完整精度汇总](profile-validation-first-pass.json)。所有消费token从原始引擎read/reused/generated阶段核对；后续打回修订排除，原始正式失败不删除。

## Profile结论与采用决定

训练profile没有显示四类review的整体优势。Code Standards平均得分小幅提高、费用降低，但耗时略增；Code Spec得分、耗时和费用均未优于default；Spec Readiness平均得分下降且耗时、费用略增。Commit Audit平均得分略降，平均耗时约下降32.4%、等效费用约下降27.2%，是局部效率线索，尚不足以采用通用trained。

每条件三次，独立线程、报告和运行记录；default/trained同一重复编号没有直接数据关联。初批前14份观测未启用统一防循环提示，后16份启用；另存的trained Commit Audit首次授权重跑已启用。小样本、执行顺序和提示词条件差异限制因果解释，不能证明profile本身造成上述差异。等效费用是用户指定token权重下的比较值，不代表实际账单。

用户已同意四类统一default。此后固定升级流程不再自动插入训练和完整profile对照；可选专项实验仍须保持材料隔离、冻结文件、每条件三次及原版评分。保留本次trained文件和异常历史，不将文件存在或专家命中率提高当作采用依据。

## 失败、可靠性与后续工作

原trained Commit Audit首轮在连续无效修复后超时；授权重跑另存且已纳入当前比较，原超时不删除。默认profile也出现过重复失败探测和重读，启动提示词不能保证避免停滞。长期提醒见[安装调用手册](../../../docs/installation-directory-manual.zh-CN.md#已观察到的执行异常)。外部中断尝试、授权新线程重跑、报告格式失败、Main机械修复副本及历史Reviewer修订分别保留，不混入有效首次交付统计。

Spec Readiness两个profile均未达到原版0.75门槛；部分正式格式/来源失败仍保留。当前分数是原版诊断结果，不冒充全套正式验收通过。选择完成表示有明确的维护基线，不表示四类业务已经全部达标或所有参数最优。

本轮收尾已发布此总结和基线，安装目录README及已结束汇总已在维护独占权和启动互斥锁内同步，源文件/部署文件SHA逐项核对一致，运行文件和安装配置未修改、未启动模型，维护key已归还。108项本地模拟回归通过；首轮因当前沙箱禁止localhost服务器而失败的日志保留，授权解除该测试限制后通过。部署和回归明细在`.tmp/upgrade-cycle-v0.1.38-20261003/closure-20261004/`。后续范围按用户2026-10-06决定调整：四类正式reviewer benchmark由ARW负责，本工程下一项为所选100K／156584上下文及Q2_0/default下的Commit Audit推理强度比较，low／medium／high各5次、共15次。不复用本批次不同条件的诊断数据补足新比较；开始前先向用户说明实际实例数、预计耗时并取得同意，之后再进入plan中的独立长上下文可靠性等剩余事项。
