# 使用外部 glab 创建 GitLab 托管发布对象

## Context

ARW 发布在 tag 后 Bootstrap 和 Release Conformance 通过时已经拥有准确版本标签与候选提交, 但用户还需要 GitLab 托管发布对象承载可安装版本的公告. 公告包含只有准确 tag 确定后才能形成的 Bootstrap 下载地址, 因而不能把占位正文提前提交到 Repository. 直接构建 GitLab HTTP Client 会让 ARW runtime 取得认证, API 兼容, 重试和远端状态恢复责任, 超出发布维护所需的最小边界.

## Decision

Main Agent 使用维护环境中已经安装并通过目标 GitLab 认证的外部 `glab` 创建 GitLab 托管发布对象. 该操作只在 `post-tag` Release Conformance 成功后发生, 并消费准确项目, 已验证 tag 与候选提交, 以及用户一次完整批准后冻结的 title 和公告文件.

Main Agent 先读取同 tag 的既有 Release. 完全匹配的对象作为幂等成功; 冲突对象关闭式停止. 对象缺失时只执行 create-only 调用, 使用 `--no-update`, 不提供 `--ref` 或发布资产. 创建成功或结果不明确后都读回远端对象, 并且只有 tag, commit, title 和 description 全部匹配时才完成发布. 缺失, 冲突或无法读取时不盲目重试, 更新或删除, 并保留已经验证的 tag 等待新的用户决定.

ARW 不新增 GitLab HTTP Module, CLI wrapper, 凭据配置, token 持久化或远端发布状态文件. `glab` 的安装, 更新和认证属于维护环境. 该外部发布操作不是 ARW 代码访问私有 Git 来源, 不改变 [ADR 0024](0024-use-ssh-for-private-gitlab-acquisition.md) 只允许 ARW 代码通过 SSH 访问配置来源的决定.

## Rejected alternatives

不把公告提交到 Repository 后再由自动化发布, 因为准确版本 URL 只有 tag 确定后才能形成, 而持久保存另一份正文会增加同步责任. 不让 Main Agent 在命令行重新组成用户批准的正文, 因为批准对象会在交接中改变. 不使用自定义 HTTP 调用, 自动更新, 删除或结果不明确时重试, 因为这些做法都会扩大凭据处理和破坏性恢复边界.

## Consequences

每次发布前维护环境必须提供可用且已认证的 `glab`. 公告文件保存在 Repository 之外, 用户批准后保持字节不变, 并直接成为创建命令输入. 远端读回是成功判断的一部分, 所以完全匹配的既有对象可以安全恢复结果不明确的调用. GitLab 托管发布对象创建失败不会撤销已经通过 tag 后验证的 tag, 但在远端对象完全匹配前不能报告版本发布完成.

这样可以把公开公告交给现有维护工具, 同时保持产品运行时和安装载荷不承担远端发布责任.
