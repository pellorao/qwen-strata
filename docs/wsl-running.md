# WSL网络与安装维护

> 本文描述旧的 WSL 控制器方式，将随前端重写整体替换，见[计划](plan.md#前端)。

调用方的完整独占API、启动参数及示例统一放在[安装README](installation-directory-readme.md#调用方使用方法)。安装根目录仅公开Run-Strata-Controller.sh；模型启停在控制器内部，其他工程不执行实现脚本。

## 运行与网络边界

模型、tokenizer、专家权重、MTP、私有Python、CUDA及推理进程运行在Windows。WSL发起控制器启动和API请求，使用真正的Linux Codex/harness执行工具。调用方只需安装目录，不依赖维护工程。

控制器监听当次WSL NAT网关8101，承载Chat、Responses及独占控制接口。内部模型监听同网卡8100，对全部HTTP操作验证持有key；内部维护凭据只用于health/unload。模型停止后控制器继续运行，可受理下一次领取。

启动入口动态取得WSL NAT网关和客户端源地址，核对Windows WSL虚拟网卡。绑定具体私网IPv4，不绑定0.0.0.0或物理网卡；不更改NAT，不使用portproxy、隧道或端口转发。控制器另检查发起启动的WSL地址与宿主地址，IP限制不能替代key鉴权。

GET /health检查控制器身份及可领取状态，不证明模型加载或任务质量。带key的GET /ownership/status区分stopped、partial、unloaded、running。模型启动等待ready并核对量化/窗口；停止先正常unload，再核对路径与进程身份清理。卸载失败后的强制结束不保证专家profile保存。

## 一次性防火墙设置

安装维护者从WSL运行：

```bash
qwen_install=/mnt/c/Users/Pello/AppData/Local/Programs/qwen-3.8-flash-next
bash "$qwen_install/maintenance/Setup-WSL-Network.sh"
```

Windows请求一次管理员授权，只创建或更新QwenStrata-WSL-API：指定安装Python、TCP8100/8101、Windows WSL虚拟网卡和同网段rtx3080ti，不改默认防火墙策略。模型和调用方继续普通用户权限。网卡别名改变时重新设置。该入口属于安装维护，不是外部调用方步骤。

存在HTTP代理时，对当前宿主使用NO_PROXY/no_proxy或显式直连。控制器及健康检查使用直连，不修改工程环境变量。不要永久写死示例IP；调用方读取入口JSON或当次WSL路由。

## 部署与验证

维护代码修改后从维护工程执行：

```bash
python3 tools/ops/deploy_wsl.py --install-root /mnt/c/Users/Pello/AppData/Local/Programs/qwen-3.8-flash-next
```

执行运行文件部署前，维护者先通过控制器领取独占key，确认模型已停止，并将key置于部署进程的`STRATA_API_KEY`环境中。工具再次鉴权，在Windows启动互斥锁内备份、替换和回读；完成后归还key。仅同步文档可添加`--docs-only`，无需领取key。

部署控制器入口、内部服务实现、配置及调用方README；主题文档、测量报告和冻结场景留在维护工程。`docs/installation-directory-readme.md`是安装根README的源文件，工程根README不部署。部署逐文件校验，替换前备份到维护工程`.tmp/maintenance-backups/wsl-deploy-*`；升级备份同样放工程`.tmp/maintenance-backups/release-backup-*`。控制器启动配置继续使用安装目录`.tmp/controller-model/`。明确清单中的公开模型启停入口、已归并文档、旧场景和测量明细移除。测量明细只保留在维护工程`.tmp/`，不再部署。模型权重、引擎、依赖和基线配置不变；.state持有记录及内部凭据不作为部署输入。

仅同步安装根调用手册时加--docs-only，不替换运行实现或中断控制器；文档中的本地链接仍须核对。

维护部署、版本升级及控制器进程操作先等待没有持有者，再领取维护key并确认模型停止，不能通过重新启动控制器抢占调用方。服务日志位于logs/wsl-server.log和logs/wsl-bridge.log，.state损坏或key遗失需要维护者检查；不自动抹掉持有状态。固定版本升级与运行文件部署使用同一鉴权和启动互斥保护，实际验收进度见[计划](plan.md)。

真实控制器验收曾用 `verify_controller.py`（已移除，前端重写后另建验收），覆盖错误/归还key、并发领取、实际两种模型请求、控制器重启以及归还关闭。结果见[控制器报告](../reports/v0.1.38/controller.md)。健康检查、短生成和API授权各有范围，不能据此推论任意工程质量或压缩无损。
