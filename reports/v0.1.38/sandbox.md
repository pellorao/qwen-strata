# Codex 受限执行与自动审批验证

2026-10-03，Linux Codex 0.160.0，Windows 原生 Strata v0.1.38。

命名权限配置已经验证：工具可读指定工程，可写固定 scratch，源码和 Git
只读，工程外宿主文件不可读，工具网络拒绝。工程外文件、其他工程、用户
配置、Windows 文件、符号链接、路径穿越、子进程和 /proc 根目录逃逸的读
探针均遭拒绝；工程源码写入和 /tmp 写入也遭拒绝。重启与 resume 后继续
生效。模型实际读取源码、用 apply_patch 写入 scratch 并读取结果成功；
源码 apply_patch 被实际工具输出拒绝，宿主 canary 保持原字节。

这满足目前测得的宿主文件访问边界，但没有完全满足“只允许读工程，且在
任何命名空间都只能写一个目录”的字面要求。Codex 必须读取最小系统运行时
和自身可执行文件；bubblewrap 私有文件系统中部分未挂载空目录允许创建
短命文件，它们不写回对应宿主目录。固定写目录的 Landlock 外层原型又与
bubblewrap 的 uid 映射、挂载操作冲突，目前不能推荐该原型。实际配置、
全部探针、限制和拒绝输出见 [sandbox.json](sandbox.json)。

原始验证收集器只检查 item/completed，遗漏了遭拒绝的 apply_patch，因而
将 actual_denied_patch 写成 false；本报告用 session 中的真实
custom_tool_call_output 补证。原始记录保持不改。命名空间额外写入这一
失败独立存在，不能借修正收集器把整体严格验证宣称通过。

approve-for-me 已在 qwen_strata 下通过一次真实的无害升级调用。父会话和
guardian 会话时间、命令匹配，审批模型为同一本地 Q2_0，effort=low，思考
预算 2048、总输出预算 8192。审批耗时约 3.569 秒，仅是一个兼容性样本，
不属于正常 code review 对照均值，也不证明审批质量可靠。预算是上限，
当前桥无法可靠报告实际思考长度。完整可见证据见
[approval-session-evidence.json](approval-session-evidence.json)。

Codex 0.160.0 的 guardian 模型选择优先使用配置的审批模型；目录找不到
审批模型时可回退父模型，并在模型支持时优先 low。本地实际会话证据与
[固定版本官方源码](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/ext/guardian-reviewer/src/model.rs)
一致。这次本地审批没有依赖 OpenAI；不能据此概括其他工程和 provider 的
所有配置。用户要求的随机可见审批摘要另存于
[approval-history-examples.json](approval-history-examples.json)，这些云端
历史样例的模型是 codex-auto-review，不能混作本地 Qwen 的审批摘要。

本只读评审场景完成逐维对照后选择 sandbox + never：范围内直接执行，
越界拒绝。auto_review 可能允许升级，不能等同于硬性边界。正常评审的
冻结提示不请求提权，六次模式评审均未调用审批；分数与耗时差不能归因于
guardian。完整逐维结果见[code-review.md](code-review.md)。

独立无害提权诊断两模式各三次，实际本地 Q2_0/low guardian 平均
3.552秒。sandbox 提权请求被拒后，三次均在原沙箱内重试同一 no-op 成功，
没有改变权限。该诊断不混入评分，且不能推导复杂动作审批可靠性；见
[approval-cost.md](approval-cost.md)。字面上的私有命名空间写范围限制
仍如上，不因选用 sandbox 而宣称已经满足。
