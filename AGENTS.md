# qwen_strata

维护本地 Qwen3.8-Flash-Next / Strata 推理服务（Windows 原生运行），并测量它作为 Codex / Claude 等 agent 后端的表现。

规则分三层：本文件（总则）；`.claude/rules/` 下的专题规则，处理对应路径前必须阅读（Claude Code 会按文件头 `paths` 自动加载）；`.claude/skills/` 下的可重复流程。

| 专题规则 | 适用路径 |
|---|---|
| [测量](.claude/rules/measurement.md) | `tools/`、`reports/`、`benchmarks/` |
| [防循环检测](.claude/rules/loop-detection.md) | `benchmarks/loop-detection-v2/`、`tools/loop/` |
| [ARW Reviewer](.claude/rules/reviewer-suite.md) | `benchmarks/reviewer-suite-v1/`、`tools/reviewer/`、`tools/safety/` |
| [部署](.claude/rules/deployment.md) | `src/`、`config/`、`scripts/`、`tools/ops/`、调用手册源文件 |

## 主机

| id | 状态 | 说明 |
|---|---|---|
| `rtx3080ti` | 可用，Claude 运行所在机 | 安装 `/mnt/c/Users/pello/AppData/Local/Programs/qwen-3.8-flash-next`；前端常驻 `192.168.60.212:8000` |
| `rtx4070tis` | 离线 | 不尝试连接；恢复后先核对实际文件、版本和服务状态，不沿用离线前的描述 |

主机连接与凭据在 `project.private.toml`，只由程序解析。

## 硬约束

1. **模型运行需批准**。会加载模型的工作，首次开跑前按 [模型运行申请](.claude/skills/model-run-proposal/SKILL.md) 给出计划并取得明确同意。授权覆盖整个工作项直到完成，包括故障修复、重新准备和受影响范围的重跑。改变目标、冻结输入或评分、候选、维度，或增加有效样本时，需要重新授权。用户叫停立即停。
   - **自主推进状态**：用户说明去睡觉或离开、让 agent 按计划推进时，豁免本条及其他一切用户审批（包括模型运行），不能因为用户不在就不跑模型。较重要的决策（如是否现在升级、默认参数是否改值）先由一个智能水平和推理强度都不低于 Main 的独立 agent 分析并给出意见，Main 综合双方意见后执行；决策、双方意见和结果写入文档，用户回来后一起交给用户。
2. **独占 key**。所有模型操作先经前端领取 key，用完归还。不抢占他人持有，不抹掉持有状态。维护（部署、升级）先等空闲，领维护 key，确认模型已停。
3. **基础提示必须接入**。每次模型运行都接入 `config/prompts/startup-instructions.txt` 和 `config/prompts/compact-prompt.txt`。启动提示默认去掉已弃用的防循环段加载。开跑前核对实际加载的 SHA 并保存绑定；场景提示只能追加，不能替代。
4. **凭据不外泄**。`project.private.toml` 和安装目录 `.state/` 不读入会话，不进 git、日志、报告或提示词。
5. **参数按"主机 + 量化"绑定**。一台机器或一个量化的调参结论，不套用到另一台或另一量化。IQ2_XS / IQ3_XXS 尚未独立调参。
6. **工程是唯一来源**。代码、提示、调用手册和每机配置以本工程为准；安装目录只是部署目标，不反向取源。
7. **推理在 Windows 原生进程**。WSL 保持 NAT，不加端口转发。
8. **下载**。单文件不超过 200MB 可以自行下载；超过则给出链接、大小、SHA，由用户下载。探索性下载只放 `.tmp/`，决定采用后才进入长期位置。
9. **不依赖 harness 的付费服务**。Strata 作为后端时，审批、搜索、摘要等辅助能力由 Strata 或本工程（如 Brave）提供，不使用 Codex、Claude Code 自家模型或服务；只有不需要订阅也能使用的服务才可以例外。

## 工作方式

- 开始前读 `README.md`（主线与进展）和 `docs/plan.md`，再以实际文件和服务状态为准。历史报告不等于当前状态。
- **简化优先**：不保留一次性脚本、已关闭路线的代码和无价值的测试。新增实现前先看能否删除或合并旧的。
- 汇报时先说结论、意义和适用范围，再给关键数据和链接。失败和未验证项要明说，局部或模拟通过不说成整体通过。
- 一个已授权工作组完成后，交付结论和下一组计划，然后停下等审核，不自动接下一组。
- 进度记录：`README.md` 只放未完成主线和简要进展；完成项移入 `docs/work-history.md`；`docs/plan.md` 只放待办和仍需重复执行的流程。

## 目录

| 目录 | 内容 |
|---|---|
| `src/` | 部署到安装目录的前端（独占控制、协议桥、搜索）与只读文件 MCP |
| `config/` | 启动和压缩提示、维护基线、模型 catalog、每机部署配置（`deployments/`）、制品校验清单 |
| `tools/{ops,metrics,loop,reviewer,tuning,safety}/` | 部署运维、计量、防循环、ARW 测量、资源校准、安全探针 |
| `benchmarks/` | 冻结场景、标注语料和评分协议 |
| `reports/` | 已结束测量的摘要与完整精度 JSON |
| `docs/` | 主题文档；`installation-directory-readme.md` 是安装目录调用手册的源文件 |
| `.tmp/` | 运行明细和临时文件，可随时删除；长期文档不得依赖它 |

## 命令

- 测试：`python3 -m unittest discover -s tests -p 'test_*.py'`
- 工具：从工程根运行 `python3 -m tools.<子目录>.<模块>`
