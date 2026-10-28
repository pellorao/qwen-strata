# rtx4070tis 调用手册的本机段落

`docs/installation-directory-readme.md` 里 `{{host.<名称>}}` 的内容，只对本机成立的实测和说明。每段以 `<!-- 名称 -->` 开头，到下一个标记或文件末尾为止，首尾空行不计。部署时按 `tools.ops.deployment_source.render_manual` 渲染。

<!-- presets -->
rtx4070tis：对外模型为 IQ3_XXS，默认档是窗口 206584、自动压缩阈值 150000（沿用 rtx3080ti 的值，本机未重测），另有可选档窗口 156584、阈值 100000。`config/model-catalog.json` 只列对外模型，窗口是它在本机的默认档；调用方仍需把自己 harness 的自动压缩阈值设为所用档的值（IQ3_XXS 默认档为 150000）。`bin/qwen-agent` 使用对外模型的默认档，即 `context_tiers` 的第一档（见[与 Codex 的参数对照](#与-codex-的参数对照)）。其余预置：high，思考 8192／总输出 24576，temperature 0、top_p 1、top_k 20、presence_penalty 0，CPU 辅助 auto。presence_penalty 0 是显式写的：Strata 0.2.x 会给请求和安装配置都没给的采样键补模型卡的值，思考关闭的请求会因此被加上 presence_penalty 1.5。这是维护起点，不是完整质量验收或最优参数的结论。服务不会替调用方压缩。

<!-- load_time -->
rtx4070tis 上 Strata v0.2.4 上线端到端测试的冷加载约 32 秒（IQ3_XXS，2026-10-28，一次记录）

<!-- compact_check -->
Claude Code 不按 `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` 压缩，只在阻塞上限（窗口 − 20000 − 3000：206584 窗口为 183584，156584 窗口为 133584）压缩；`CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE` 把这个上限设为所用档的阈值，与 Codex 相同。该行为在 rtx3080ti 上用假服务器和压缩探针核对过（Claude Code 2.1.303–2.1.310），本机尚未重跑 `tools.ops.claude_compact_probe`。这个变量不在 Claude Code 公开文档里，升级 Claude Code 后要重新核对。

<!-- approval_cache -->
引擎单会话持有显存前缀缓存，审批请求会挤掉主对话的缓存。本机可配置开启会话暂存（`conversation-cache-mib 8192`、`conversation-cache-slots 4`、`conversation-cache-min-free-mib 5120`）：切换时把会话暂存到内存。实测数据将在上线后结合独立调参更新。
