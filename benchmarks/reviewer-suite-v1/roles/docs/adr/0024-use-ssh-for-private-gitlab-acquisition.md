# 对私有 GitLab 统一使用 SSH 来源

## Context

ARW 源码仓库位于要求认证的私有 GitLab. 当前维护环境通过 SSH 密钥取得访问权, 而 HTTPS 取得会进入另一套凭据路径. 引导安装, 发布候选包和标签创建后维护命令如果分别选择传输方式, 同一次发布流程可能使用不同的认证和来源语义.

用户可以根据自己的授权通过 HTTPS 或 SSH 取得 `scripts/install-arw.mjs`. 这项外部取得操作不要求 ARW 固定一种传输方式. 本决定只约束 ARW 代码自己发起的私有 GitLab 通信.

## Decision

ARW 代码访问配置的私有来源时只使用 SSH. 当前规范仓库远程地址只保存在根 `release-validation.json`; 本 ADR 只规定 SSH 传输策略, 不保存远程地址值.

Bootstrap 生成过程把当前配置的规范远程地址投影到单文件生成物. 发布候选包准备和标签创建后验证读取同一配置值. 生成物中的派生字面值, 实际命令事件和运行时观察都不成为第二权威来源.

默认发布验证在隔离本地 Repository 中迭代候选. 验证子进程保持配置的规范 SSH URL 作为 `origin` 显示值, 但使用只作用于该子进程的 Git URL 映射把准确 URL 重定向到本地裸 Repository. 这项映射不修改 Bootstrap, 配置, 用户或 Repository Git 配置, 不访问私有来源, 不声称验证 SSH, 并在子进程结束时消失.

本地和正式标签创建后验证都复用本轮 `prepare-bundles` 创建的候选裸仓库. Main Agent 通过公开命令参数传入该仓库的绝对路径, 不将路径写入 `bundles.json`. Tag-after Module 在此仓库中通过 `git fetch` 取得准确 `<version>` 标签, 比较候选引用和标签提交, 再通过 `git show` 读取 `scripts/install-arw.mjs` 的准确字节. 本地验证的 Git 传输按上段映射到隔离 Repository; 正式发布不使用映射并访问配置的 SSH 远端. Module 不创建新仓库, 不使用当前源码仓库, 不运行远程 `git archive`, 也不解析 tar. 维护命令只报告实际观察, 仍由 Main Agent 与当前候选比较.

这项决定取代 ADR 0020 中 Bootstrap 固定 HTTPS 远程地址的部分, 但不规定用户如何取得 Bootstrap 文件, 也不改变外部 Node.js, 稳定 SemVer, 精确标签与提交核对, 临时签出副本, 对应版本的 Installer 或 Installation 归属.

## Consequences

运行正式引导安装或正式远程发布阶段的主机必须具有 Git, SSH 客户端, 可用 SSH 密钥和配置来源的访问权. 本地发布验证只要求 Git 和隔离 Repository, 不要求私有来源访问权. 正式分支推送, commit 取得和标签创建后验证复用同一 SSH 认证通道, 不保存凭据, 不接受远端覆盖值, 也不通过 HTTPS 与配置的私有 GitLab 通信.

`release-validation.json` 缺失, 无效或包含未知字段时, 发布验证在网络或虚拟机变更前关闭式失败. 本地映射缺失, 泄漏, 映射其他 URL 或没有指向本轮隔离 Repository 时同样失败. 标签创建后验证还必须确认传入路径是裸仓库, 取得准确标签, 确认标签解析后的提交与已准备候选相同, 并要求 `git show` 返回文件的原始 Buffer 字节. 仓库无效, 本地映射或正式 SSH 获取失败, 标签不存在, 提交不匹配, 文件不存在或返回值不是字节都阻止对应阶段通过.

当前远程地址变化时只修改 `release-validation.json`, 再重新生成并验证 `scripts/install-arw.mjs`. 测试验证配置消费和生成物一致性, 不断言当前远程地址字面值永远不变. 发布证据归档的规范 tar 责任不受影响.
