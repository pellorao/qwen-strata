# 调用方接入

安装项目提供模型服务和常驻前端（独占租约加原生接口转发）。各工程自行管理 Codex 或其他 harness，包括 provider、catalog、工具、权限、会话、取消、恢复和压缩；本项目不生成工程配置或修改全局设置。

## 模型与推理强度

对外模型及模型 ID：

每台机器只对外提供一个模型（用户 2026-10-19）：rtx3080ti 为 IQ3_XXS，请求模型 ID `qwen3.8-flash-next-iq3_xxs`。对外模型以安装目录 `config/deployment.json` 的 `models` 为准；`/model/start` 省略 `model` 即用它，其他量化（Q2_0、IQ2_XS 权重仍在，但不对外）返回 400。安装目录的 model catalog 也只列这一个。

请求模型 ID 必须与实际加载量化一致，修改请求名称不会加载另一份模型。维护基线 = 本机唯一对外模型 + 部署默认值（B1，用户 2026-10-19）：high、思考8192、总输出24576，窗口与压缩阈值取该模型的首个上下文档位（rtx3080ti IQ3_XXS 为 206584／150000）。原 Q2_0 运行基线文件（Q2_0/high/default、100K阈值／156584窗口）已删除，历史内容用 `git show ff94f3c:config/maintenance-baseline.json` 查看；历史测量保留原配置。旧Commit Audit的low／medium／high各5次已闭合，诊断结果保留；四类正式reviewer benchmark仍由ARW负责。

Responses 请求用 reasoning.effort；原生 Chat 用 reasoning_effort。Codex 配置字段为 model_reasoning_effort，provider 的 wire_api 使用 responses，base_url 为 `http://192.168.60.212:8000/strata/v1`。工程应管理自己的配置入口和 model catalog；config/ 中的 Windows profile 是环境参考，不能直接复制到 Linux。官方字段见[配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)。

| 强度 | 思考 token 上限 | 默认总输出上限，含思考 |
|---|---:|---:|
| low | 2048 | 8192 |
| medium | 4096 | 16384 |
| high | 8192 | 24576 |

前端按请求补齐预算；若另设 max_output_tokens，思考预算还会被限制到总输出的一半。上限不是实际思考长度；reasoning token usage 当前不足以可靠计算后者。none 可关闭思考，xhigh/max 与 high 同预算，均不作为本次三档测量的额外维度。

当前维护推荐100000压缩阈值、156584引擎/harness窗口；启动时显式传`engine_overrides.max-context=156584`，调用方同步设置自己的`model_context_window=156584`、`model_auto_compact_token_limit=100000`及所选模型catalog窗口。安装原始配置仍为250000，不等于当前推荐容量。输入加输出预算超限返回400，不静默裁剪。压缩阈值、提示与历史由调用方管理，见[压缩方案](compaction-options.md)。

## 调用方独占要求

调用方必须先取得独占权，再按自身需求启动指定量化，并在请求中使用所需推理强度。独占期间其他调用方无权启动、停止、切换或调用模型。安装目录的所有启停入口、Chat/Responses 及模型管理API须检查同一持有凭据；IP允许列表或短暂启动互斥锁不能代替调用方独占。

前端常驻运行，调用方无需启动。完整租约流程、参数表及Python示例在[调用手册](installation-directory-readme.md)。停止保留租约，归还立即撤销key并停止模型；租约只在前端内存中，重启前端即回收。

## 协议与工具

Chat、Responses、Messages分别发往前端`/strata/v1/chat/completions`、`/strata/v1/responses`、`/strata/v1/messages`，均需`Authorization: Bearer <key>`。Codex自定义provider通过env_key取得调用方私有环境变量中的key；网络和防火墙见[前端运行与维护](frontend.md)。

请求由原生Strata直接处理：Responses支持function/custom工具、命名空间、additional_tools及推理内容回放（不支持客户端tool_search，日常catalog已关闭`supports_search_tool`，MCP工具内联发送）；托管`web_search`由前端经Brave执行（设`web_search = "live"`），其他托管工具被原生服务丢弃。工具发现、MCP及其他工具仍由harness执行，服务不自行压缩。原生Responses的协议细节（加密输入、previous_response_id、流错误事件）以新版Codex实测为准。

安装`config/model-catalog.json`只描述模型事实（名称、推理档位、窗口、文本输入、搜索工具类型、各自本地auto_review_model_override），基础指令取自所装Codex版本的luna条目，由`tools/ops/model_catalog.py`生成，窗口取各量化在部署配置`context_tiers`中的第一档，部署时再按本机档位写入；工作范围约束放在场景提示词和沙箱权限中。ARW测量使用`benchmarks/reviewer-suite-v1/catalogs/`下冻结的catalog，不使用这份日常catalog。日常使用推荐安装目录`bin/qwen-agent`启动脚本。使用时在app-server启动时加载catalog；晚到的线程配置可能不会更新已构建的模型目录。是否启用auto_review由调用方决定，原生风险策略通常允许低/中风险行为，即使授权低或未知；它不提供绝对写路径边界。更严格隔离是本工程默认关闭的可选功能，见[沙箱模式](../reports/v0.1.38/safety-20261004/sandbox-modes.md)。

Codex app-server 是会话和工具调度接口，不是模型服务器。验收须真正使用 Linux codex/app-server；从 WSL 调用 Windows codex.exe 仍会使用 Windows 执行环境。模型 API 与工具执行网络应分开管理，模型连通不意味着工具可以外连。

src/project_files_mcp.py 是可选只读文件工具，由调用方显式配置 QWEN_PROJECT_WORKSPACE，可另设 QWEN_PROJECT_AUDIT。无工作目录则拒绝启动；审计记录参数及结果状态，不记录全文。它排除 .git/.venv/node_modules/__pycache__，拒绝越界及越界符号链接，提供目录分页和 UTF-8 分行读取：文件最多16MiB、单次400行/24000字符，必须处理截断、next_line和过长行。此MCP的范围限制不会自动约束shell/apply_patch。

## 权限与审批

本轮原版ARW Reviewer继承`:read-only`，授予显式临时写路径，使用on-request/auto_review。网络、Hosted搜索和MCP按原生工具机制保留；人工交互请求按原版Reviewer规则拒绝。三次完整运行、安全探针及重启恢复见[原版运行验收](../reports/v0.1.38/safety-20261004/native-host.md)。更严格路径集合工具默认关闭，启用时须另行验收，不随Codex版本变化自动加严。

原生guardian实际使用本地qwen_strata、所加载量化及low推理强度。它依据风险策略判断，通常允许低/中风险动作，即使用户授权低或未知，因此默认权限不是提权后仍不可突破的绝对写集合边界。明确恶意注入、高风险越权及授权不明的受控MCP用例已验证，见[审批质量](../reports/v0.1.38/safety-20261004/approval-mcp.md)与[文件伪造授权](../reports/v0.1.38/safety-20261004/approval-quality-preflight.md#文件伪造授权独立诊断)；通过只覆盖已测类别。更早never/sandbox与无害提权的开销记录保留在历史报告，不作为本轮审批质量结论。

模型权重、量化、推理强度、执行权限和独占凭据各有不同作用；选择模型不授权文件写入或权限升级。安装配置不自动应用到其他工程。
