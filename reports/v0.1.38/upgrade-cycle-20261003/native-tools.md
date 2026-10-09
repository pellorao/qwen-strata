# 原生工具兼容预检

日期：2026-10-03。Codex 0.160.0。此处只使用隔离的假provider检查原生请求和工具协议，没有真实模型推理或真实搜索，不属于能力测量。

原版ARW Reviewer设置保留on-request/auto_review、原生网络和工具。普通请求带有Hosted `web_search`，本工程Responses桥在转换工具清单时抛出`Unsupported tool type: web_search`；模型尚未选择是否搜索，整个请求就会失败。复制stock catalog中的工具能力元数据也没有消除这个问题。

启用Codex原生独立搜索的两个配置项后，请求改为函数工具`web.run`，桥能转换完整的118个函数工具。通过桥的实际SSE转换器发送一次合成工具调用，捕获到Codex依次请求`/v1/responses`、`/v1/alpha/search`及下一次`/v1/responses`。假搜索端点刻意返回HTTP 400，原生运行层把错误反馈给下一次模型请求。这证明协议路径及失败反馈，不证明真实搜索可用。

当前Strata安装和桥没有兼容的`/v1/alpha/search`后端。OpenAI[官方配置说明](https://learn.chatgpt.com/docs/config-file/config-advanced)也明确独立搜索尚在开发、默认关闭，声明支持本身不足以启用，provider还必须提供兼容端点。仅改工具清单、默默忽略Hosted工具，或者广告独立搜索而保留未实现的端点，都不能满足本批次的工具可用要求。

正式四类能力实例尚未启动。需要先确定可用搜索后端及其数据流；若改为其他工具或关闭内置搜索，属于测量条件差异，必须先经用户同意，不能自动按原版能力结果发布。其他参数比较和无工具的独立profile训练不依赖该接口。

具体请求保存在本批次`.tmp`中，长期摘要及源字节SHA-256见[native-tools.json](native-tools.json)。所有配置均仅用于隔离诊断，没有修改全局Codex配置或原ARW工程。
