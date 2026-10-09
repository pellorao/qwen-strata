# 独立review profile训练

五个训练任务均finish_reason=stop；正常停止保存并归还独占权。没有执行能力评分或profile收益验收，accepted_for_use=false，默认profile继续保留。

请求总墙钟265.669秒，加载另计。学习文件196632字节，48层×512专家，24576个互异排序项及逆序表核对通过；24571个排序位置变化。这证明文件变化，不证明收益。

| 任务 | 工作负载 | 秒 | 未缓存输入(API) | 已缓存输入(API) | 输出(API) | 完成 |
|---|---|---:|---:|---:|---:|---|
| 1 | code-standards-reviewer/implementation | 60.055 | unknown | unknown | 6247 | stop |
| 2 | code-spec-reviewer/contract | 63.178 | unknown | unknown | 6679 | stop |
| 3 | spec-readiness-reviewer/maintenance requirements | 34.812 | 14050 | 0 | 3376 | stop |
| 4 | spec-readiness-reviewer/API requirements | 51.158 | unknown | unknown | 5418 | stop |
| 5 | commit-audit-reviewer/requirements and implementation | 56.466 | 5 | 12642 | 5910 | stop |

三个请求的API cached_input超过input，不作负数或零处理，两个输入分类标为unknown，保留完整原始响应。API计数与物理引擎计数不是相同范围。

引擎共有9个实际生成片段：未缓存输入76463、已缓存输入70519、输出27561。包含同一请求内部的thinking/output分段，来源及逐片段值见[训练数据](profile-training.json)。

训练材料、角色规则和完整提示词审计见本轮材料清单及审计记录。10个正文源文件与冻结fixture 107个哈希无重合；角色说明与原版冻结SHA一致。每任务单条新消息，不提供工具或历史。输出限定五个关注点及两个有证据的正常行为，仅用于独立训练，不更改正式ARW场景、报告要求或评分。

第一次训练因计量代码未处理矛盾计数在第二个任务后中断，第二份完整响应未能保存。已保留[失败记录](profile-training-failure.json)、部分profile及全部材料，修正计数处理和先保存原始响应的顺序后，新批次从默认profile独立完成全部五任务。没有将两批次拼成成功结果。

默认SHA-256：`8f59b4aa8873209dff11c11e37bcda9529a1335b724a1afeea37bf6388975baf`。

学习SHA-256：`d965e7f503c69bec538eb56d542db558a9232ed47a560889269645ed0319e426`。

下一步须冻结文件、禁止保存，在不改变ARW场景和评分的条件下与默认profile对照，四类各三次。原生搜索端点尚不兼容，正式测量未开始，见[工具预检](native-tools.md)。
