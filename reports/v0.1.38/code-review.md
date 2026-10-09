# Code Standards 20+20 评审测量

本历史批次采用已停用的早期自定义评分；当时选择sandbox-deny + Q2_0 + medium。不能作为现行ARW分数或权限模式选择依据。

Strata v0.1.38 / Linux Codex 0.160.0；按重要度串行：执行模式 → 模型 → 推理强度。
每条件三次算术平均；20问题、20具体干净对照及1全局无误报点，按41点评分。

## 执行模式维度

固定其他条件：Q2_0 / medium。

| 条件 | 三次得分 | 平均分 | 标准差 | 任务秒 | API请求 | 用户回合 | 工具调用 | API失败 | 工具失败 | 范围拒绝 | 审批次数 | 审批秒 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| sandbox-deny | 87.68 / 84.28 / 87.15 | 86.37 | 1.83 | 178.04 | 9.33 | 1.00 | 12.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| approve-for-me | 83.72 / 83.37 / 81.01 | 82.70 | 1.47 | 204.12 | 11.33 | 1.00 | 12.67 | 0.00 | 0.33 | 0.00 | 0.00 | 0.00 |

## 模型维度

固定其他条件：sandbox-deny / medium。

| 条件 | 三次得分 | 平均分 | 标准差 | 任务秒 | API请求 | 用户回合 | 工具调用 | API失败 | 工具失败 | 范围拒绝 | 审批次数 | 审批秒 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Q2_0 | 87.68 / 84.28 / 87.15 | 86.37 | 1.83 | 178.04 | 9.33 | 1.00 | 12.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| IQ2_XS | 81.07 / 84.42 / 89.14 | 84.88 | 4.05 | 212.67 | 8.67 | 1.00 | 10.00 | 0.00 | 1.00 | 0.33 | 0.00 | 0.00 |
| IQ3_XXS | 85.81 / 85.37 / 85.38 | 85.52 | 0.25 | 343.18 | 12.33 | 1.00 | 14.67 | 0.00 | 0.67 | 0.00 | 0.00 | 0.00 |

## 推理强度维度

固定其他条件：sandbox-deny / Q2_0。

| 条件 | 三次得分 | 平均分 | 标准差 | 任务秒 | API请求 | 用户回合 | 工具调用 | API失败 | 工具失败 | 范围拒绝 | 审批次数 | 审批秒 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| low | 61.68 / 83.08 / 84.63 | 76.46 | 12.83 | 136.91 | 10.33 | 1.00 | 11.33 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| medium | 87.68 / 84.28 / 87.15 | 86.37 | 1.83 | 178.04 | 9.33 | 1.00 | 12.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| high | 83.31 / 79.33 / 80.53 | 81.06 | 2.04 | 195.76 | 9.33 | 1.00 | 11.33 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

执行模式选择理由：For this read-only reviewer task, fixed host read/write boundaries and immediate denial suffice. Sandbox has higher three-run mean score and lower mean task time. Neither mode made any approval request, so the observed timing difference is stochastic task behavior, not measured guardian overhead. Approve-for-me offers no demonstrated benefit here; the independent triggered probe confirms local guardian compatibility and an added 3.569 seconds for one no-op approval, not a repeated overhead estimate.

任务时间含生成、工具和审批，不含另存的加载时间。API请求、用户回合和工具调用分别记录。
范围拒绝包括沙箱隐藏禁止写入路径后返回ENOENT；实际错误、恢复与评分影响见各实例failure-adjudication.json。
未知不记零。未触发审批不代表实际审批无开销；小样本分差不能自动归因于失败或审批。
独立实际审批开销见[approval-cost.md](approval-cost.md)，每模式三次，不混入本表评分。
冻结数值评分不单独惩罚合并在真实发现中的错误论断，也不单独计修复正确性；裁决说明保留这些缺陷，分数不是查准率或报告完全正确的保证。
复用后共18个不同正式实例；顺序变更前不符合固定条件的诊断数据保留，不混入均值。
历史报告、逐项裁决、冻结代码及旧规则保留在`.tmp/retired-code-standards-v1-20261004/`；现行测量只使用ARW原版入口。

## 实际失败与恢复

以下只列真实失败，不注入故障、不自动补跑。最终分不能当作失败造成的分差。

| 实例 | 实际失败 | 后续处理 | 最终分 |
|---|---|---|---:|
| modes-r1-approve-for-me-Q2_0-medium | invalid_patch_format | regenerate_patch_with_required_envelope | 83.72 |
| models-r1-IQ3_XXS | invalid_patch_format | rewrite_report_using_shell_heredoc | 85.81 |
| models-r2-IQ2_XS | sandbox_path_unavailable | retry_in_fixed_scratch | 84.42 |
| models-r2-IQ2_XS | invalid_patch_format | regenerate_valid_patch | 84.42 |
| models-r2-IQ2_XS | command_policy_rejected_rm_f | use_python_unlink_in_fixed_scratch | 84.42 |
| models-r3-IQ3_XXS | invalid_patch_hunk_format | switch_to_shell_heredoc_chunks_in_fixed_scratch | 85.38 |

逐项评分影响、实际错误与恢复证据见每个实例的 failure-adjudication.json。API失败为零只表示本批次未观察到，不证明服务不会失败。
