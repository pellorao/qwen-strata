# rtx3080ti 调用手册的本机段落

[English](installation-local-sections.md) | [简体中文](installation-local-sections.zh-CN.md)

这里汇总了详细手册模板 `docs/installation-directory-manual.zh-CN.md` 中 `{{local.<名称>}}` 占位符对应的内容，包含仅对本机成立的实测数据与说明。每段以 `<!-- 名称 -->` 开头，到下一个标记或文件末尾结束，忽略首尾空行，部署时由 `tools.ops.deployment_source.render_manual` 负责渲染。

<!-- presets -->
rtx3080ti 对外提供的模型为 IQ3_XXS。自 2026-10-14 起，其默认档设为窗口 206584、自动压缩阈值 150000；另有可选档，窗口为 156584、阈值为 100000。206584 窗口已在约 151K token 以内的长上下文检索负载上通过验证，相同负载下速度与 156584 档一致；更长的提示在 200K 级检索中出现过系统性错误，256584 未发布。在配置与调用方面，`config/model-catalog.json` 只列出对外模型，其中的窗口即本机默认档；因为服务不会替调用方压缩，所以调用方仍需将自身 harness 的自动压缩阈值设为所用档的值（IQ3_XXS 默认档为 150000）。而 `bin/qwen-agent` 会直接使用对外模型的默认档，即 `context_tiers` 的第一档（见[与 Codex 的参数对照](#与-codex-的参数对照)）。其余预置参数为：high，思考 8192／总输出 24576，temperature 0、top_p 1、top_k 20、presence_penalty 0，CPU 辅助 auto。其中 presence_penalty 0 是显式指定的，因为 Strata 0.2.x 会把请求和安装配置都未提供的采样键补成模型卡的值，若不显式指定，关闭思考的请求就会被加上 presence_penalty 1.5。以上配置仅作为维护起点，并非完整质量验收或最优参数的结论。

<!-- load_time -->
rtx3080ti 上旧 Q2_0 约 20 秒，IQ3_XXS 未单独记录

<!-- compact_check -->
Claude Code 不会按 `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` 触发压缩，而是只在达到阻塞上限（即窗口 − 20000 − 3000：206584 窗口对应 183584，156584 窗口对应 133584）时才压缩；因此需要通过 `CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE` 将该上限设为所用档的阈值，使其与 Codex 保持一致。在 Claude Code 2.1.303 上通过假服务器（涵盖两回合与回合中途工具调用两种方式）核对的结果如下：使用 206584／150000 档时，输入达 150.1K 会触发压缩，149.9K 则不压缩；使用 156584／100000 档时，输入达 100.1K 会压缩，99.9K 则不压缩；若在 206584 窗口下不设该变量，则要到 183.7K 才压缩，183.5K 不压缩。所有测试在压缩后会话均能正常继续。后续又在多个版本上用压缩探针复核了 206584／150000 档，涵盖 Claude Code 2.1.304（2026-10-20）、2.1.308（2026-10-22）、2.1.309 与 2.1.310（2026-10-24）、2.1.317（2026-11-04）及 2.1.319（2026-11-08），每版各跑 3 次，全部通过。由于这个变量不在 Claude Code 的公开文档里，升级 Claude Code 后要重新核对。

<!-- approval_cache -->
引擎单会话持有显存前缀缓存，所以审批请求会挤掉主对话的缓存。为此，本机默认开启会话暂存（`conversation-cache-mib 8192`、`conversation-cache-slots 4`、`conversation-cache-min-free-mib 5120`），在会话切换时将其暂存到内存中：约 17K token 的主对话暂存耗时约 0.1 秒，恢复约 0.03 秒；如果不开启暂存，每次审批后主对话都要整段重读（17K 约需 16 秒）。实测在同一审批场景下，开启暂存后每次运行的耗时从 69.0 → 46.2 秒。
