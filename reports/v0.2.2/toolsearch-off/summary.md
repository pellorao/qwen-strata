# 日常 qwen-agent 关闭 Claude Code 工具搜索（2026-10-24）

## 结论

- `qwen-agent` 启动 Claude Code 时固定设 `ENABLE_TOOL_SEARCH=false`，调用方环境不能覆盖（19e9e43，已部署到 本机，冒烟通过）。
- 原因：Claude Code 2.1.309 起默认开工具搜索，会把部分工具延迟加载（`defer_loading`），并加一个 `DeferredToolPlaceholder` 和 ToolSearch 工具。Strata 的 Messages 接口不实现 `defer_loading`，也会丢掉 ToolSearch 返回的 `tool_reference` 块（`runtime/Strata/serve/frontend.py` 633–634、202–224 行，已登记到 [Strata 上游缺陷](../../../docs/strata-upstream-issues.md)第 5 条），所以工具搜索在 Strata 上不可用：占位工具会作为普通工具交给模型，延迟的工具（含 brave）也可能始终到不了模型。
- 关掉后，工具表恢复成 2.1.303 时的样子，与测量 runner（`claude_headless`）一致。日常只有 brave 3 个 MCP 工具，全部内联对 206584 窗口没有压力。
- 适用范围：本机，Claude Code 2.1.309。

## 双方意见

- Main：设环境变量最简单，并与测量 runner 一致。
- 独立审查（Opus high）：有条件同意。在前端按名字丢弃占位工具，违反"服务端只做通用能力"；丢弃全部 `defer_loading` 工具，又会把真实工具一起藏掉；通用做法是让 Strata 实现延迟加载语义，作为上游缺陷登记，不阻塞这次改动。条件是部署前先做零模型抓包对照。

## 验证

- 零模型抓包对照（日常形态：同 settings、brave MCP、不加 `--tools`）：
  - 2.1.309 开工具搜索：12 个工具，含 ToolSearch 和 `DeferredToolPlaceholder`；延迟工具清单在 `messages[1]`，共 12 个，含 brave 3 个。
  - 2.1.309 关工具搜索：22 个工具全部内联，没有 `defer_loading`；除工具表和延迟清单外，与开时没有差异。
  - 关掉后，2.1.309 的工具名清单和顺序与 2.1.303 相同。
- 压缩探针：2.1.309、关闭状态下通过，149.9K 不压缩、150.1K 压缩后继续。
- 单测：756 项通过；新增测试检查调用方传 true、auto 或 1 时，最终值仍是 false。
- 部署：21 个文件，回读 SHA 全部一致，`/health` 正常。
- 冒烟：在隔离环境运行，调用一次 `mcp__brave__web_search` 成功；init 报告 22 个工具，ToolSearch 和占位工具出现 0 次。局限：前端和引擎日志不记录请求里的工具表，所以部署后核对的是 Claude Code 自己报告的工具表，请求原文以零模型抓包为准。

明细在 `.tmp/toolsearch-1024/`。
