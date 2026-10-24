# presence_penalty 默认值缺口核查（2026-10-24）

worker（Opus high）报告，Main 整理存档。改动在分支 `worktree-agent-affb42f57d000f28f`（e253498），等独立审查后再合入和部署。

## 结论

- **现有运行没有受影响。** 本工程用法下，Claude Code 2.1.309 和 Codex 0.164.0 发出的请求都开着思考，不会被补上 presence_penalty。
- 会被补上 1.5 的只有思考关闭的请求，greedy 下照样生效：
  - Messages 请求带 `thinking.type: "disabled"`；
  - Chat 请求带 `chat_template_kwargs.enable_thinking: false`。

  本工程目前没有发送方会发这两种请求。Responses 和 Chat 用 effort none/minimal 关思考的请求，会先被前端以 400 拒掉。
- 思考开启那一档的模型卡值只有 temperature、top_p、top_k，三个键都已被我们的预置覆盖。其他键（min_p 等）没有同样的缺口。
- 准备的修复：白名单加 `presence_penalty`，rtx3080ti 的 `installation_defaults` 写 `presence_penalty: 0.0`，手册同步更新。渲染出的配置除新增一行外逐字节不变。新增一项测试：主机文件只要设了采样预置，就必须覆盖模型卡会补的全部键。全套 756 项通过。
- 属于防御性的默认值补齐，按硬约束 1 先过独立审查再部署。

## 源码依据（Strata 0.2.4 `serve/`）

- 模型卡表：`server.py:8053-8063`。
- 合并顺序：`server.py:5084-5087`，优先级从低到高为模型卡、config `sampling`、Chat 共享设置、请求自身字段。
- greedy 下照样惩罚：`server.py:1388-1420`，`generate.cpp:13935-13945`。

## 抓包证据（零模型）

- Claude Code：compact probe、`-p` 模式和交互模式共抓 27 个请求。覆盖主线程、子 agent、WebFetch 摘要、标题生成，没有一个带 `thinking.type: disabled`。
- Codex：compact 验证重跑通过，再加今天的 mock 门存档。主请求 effort 是 high，guardian 是 low。

## 未验证

- 没有加载模型看采样 trace。
- Claude Code 的手动 `/compact`、会话记忆、斜杠命令等辅助请求没有覆盖。
- 没有核对安装目录里有没有 Chat 共享设置文件。

## 独立审查（Opus high，2026-10-24）：有条件同意部署

- 源码核对成立：思考开启的请求传给引擎的选项逐字节不变（`sampling_keys` 在值为 0 时不下发），guardian 和审批 hook 不受影响；只有思考关闭的请求从 1.5 变成 0。
- 补充一条思考关闭路径：Messages 请求带 `output_config.effort` 为 none/minimal/off 时，Strata 也会关思考，前端不拦。现在没有发送方，本次修复同样覆盖它。
- 单测的局限：`MODEL_CARD_KEYS` 是照 0.2.4 手抄的，升级后模型卡加键时测试不会报错。已在 strata-upgrade skill 的核对安装一步加上核对模型卡的要求。
- 附带风险：安装目录里如果有 `*.shared-settings.json`（Chat 共享设置），它能覆盖 temperature/top_p/top_k，部署时要确认没有这个文件。
- 部署条件：解决合并冲突后重跑全套测试；部署后回读 prebuilt 的 sampling 块；确认没有共享设置文件；冒烟检查。

## 执行（Main）

- 冲突已解决（两边都在 `tests/test_deployment_source.py` 末尾追加了内容，两段都保留），全套 763 项通过。部署和核对结果见下。
