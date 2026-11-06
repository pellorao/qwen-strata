# Caller manual paragraphs for rtx4070tis

[English](rtx4070tis.md) | [简体中文](rtx4070tis.zh-CN.md)

This file collects the content for the `{{host.<name>}}` placeholders in the detailed manual template `docs/installation-directory-manual.md`, including measured data and notes that apply only to this host. Each paragraph begins with `<!-- name -->` and ends at the next marker or the end of the file, with leading and trailing blank lines ignored, and is rendered at deployment time by `tools.ops.deployment_source.render_manual`.

<!-- presets -->
The served model on rtx4070tis is IQ3_XXS. Its default tier sets the context window to 206584 and the auto-compact threshold to 150000 (carried over from rtx3080ti, not re-tested on this host); an optional tier sets the context window to 156584 and the threshold to 100000. For configuration and calls, `config/model-catalog.json` lists only the served model, and its context window is the default tier on this host; because the service does not compact on the caller's behalf, callers must still set the auto-compact threshold of their own harness to the value of the tier in use (150000 for the IQ3_XXS default tier). Meanwhile, `bin/qwen-agent` directly uses the default tier of the served model, which is the first tier in `context_tiers` (see [Parameter comparison with Codex](#parameter-comparison-with-codex)). The remaining preset parameters are: high, thinking budget 8192 / total output limit 24576, temperature 0, top_p 1, top_k 20, presence_penalty 0, CPU assist auto. Here presence_penalty 0 is set explicitly because Strata 0.2.x fills in sampling keys omitted by both the request and the installation configuration with the values from the model card; without an explicit setting, requests with thinking disabled would receive presence_penalty 1.5. These settings serve only as a maintenance starting point, not as a conclusion of full quality acceptance or optimal parameters.

<!-- load_time -->
About 32 seconds for cold loading in the Strata v0.2.4 rollout end-to-end test on rtx4070tis (IQ3_XXS, 2026-10-28, single record)

<!-- compact_check -->
Claude Code does not trigger compaction according to `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`; instead, it compacts only when reaching the blocking limit (context window − 20000 − 3000: 183584 for the 206584 context window, and 133584 for the 156584 context window). You therefore need to set that limit to the threshold of the tier in use via `CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE` to keep it consistent with Codex. This behavior has been verified on rtx3080ti using a fake server and the compaction probe (covering Claude Code 2.1.303–2.1.317), but `tools.ops.claude_compact_probe` has not yet been re-run on this host. Because this variable is not in Claude Code's public documentation, re-verify it after upgrading Claude Code.

<!-- approval_cache -->
The engine holds the VRAM prefix cache for a single session, so an approval request evicts the main conversation's cache. To address this, this host can be configured to enable session staging (`conversation-cache-mib 8192`, `conversation-cache-slots 4`, `conversation-cache-min-free-mib 5120`), staging the cache to system memory when switching sessions. Measured data will be updated after rollout in conjunction with independent tuning.
