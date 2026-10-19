# 每台机器只对外一个模型、维护基线 B1（rtx3080ti，2026-10-19）

## 结论

- 用户决定（2026-10-19）：每台机器的 Strata 只对外提供一个经测试最强且速度满足需求的模型，rtx3080ti 为 IQ3_XXS；Q2_0、IQ2_XS 权重保留，默认不运行、不测试，除非用户提出专门针对它们的任务。维护基线按 B1：取消独立的 `config/maintenance-baseline.json`，基线 = 本机唯一对外模型 + 部署默认值。
- 已实现（ade5a22 代码、配置、测试；6153ef5 规则与文档），全量 446 个测试通过，已部署到 rtx3080ti 并冒烟通过。
- 对外只提供 IQ3_XXS：前端两个启动入口对 Q2_0 返回 400，`qwen-agent` 在领租约前拒绝；三种权重仍在安装目录。
- 按新源重跑的安全门通过：[safety-gate-single-model](../safety-gate-single-model/summary.md)。
- 冒烟发现测试隔离漏洞：从 Claude Code 会话里启动的 `qwen-agent` 子进程继承了父会话的 `CLAUDE_CODE_SESSION_ID`、`CLAUDE_CODE_MESSAGING_SOCKET`、`CLAUDE_CODE_MESSAGING_TOKEN` 等变量。修复见「遗留」。

## 决策过程

- worker 先盘点暴露多个模型的位置并写方案；独立审查（Opus high）结论"改完再实施"，意见全部落实：
  - M1：Q2_0、IQ2_XS 的覆盖参数和档位保留为不对外数据（catalog 生成器要求每模型有默认档；rtx3080ti Q2_0 的 `vram-reserve-mib 512` 是主机 + 量化调参结论）；公开 `deployment.json` 和安装目录 catalog 只含对外模型。
  - M2：部署文件集合按主机生成，测量预检 `verify_sources` 用同一集合，并要求不对外 prebuilt 不存在。
  - M3：专项任务不靠"临时改 `models`"（会把 `qwen-agent` 和前端默认值悄悄换掉），改走部署 `--condition`，普通部署恢复；condition 多模型渲染在第一次需要时再实现，部署规则已写明。
  - M4：补齐文档遗漏（installation、tuning、host-tuning、validation、plan、调用手册逐行、codex、README、AGENTS 硬约束 5）。
  - M5：先部署本改动，再跑安全门，因为安全门保存部署源 SHA。
- 维护基线三个选项（B1/B2/B3）由用户定为 B1，审查同样推荐 B1。

## 改动

- `tools/ops/deployment_source.py`：`load_host` 要求 `models` 恰好一个；每模型数据的键校验放宽到已装权重的量化；`public_host` 过滤为对外模型；catalog 渲染删掉不对外条目，渲染后不是 1 条就报错；删除维护基线渲染；新增 `served_model(host)`。
- `tools/ops/deploy.py`：`deployment_files(host)`（共用文件 + 对外 prebuilt）、`obsolete_files(host)`（原 OBSOLETE、维护基线文件、不对外 `config/<m>-prebuilt.json`，先备份再删除，列进 `removed`）。权重、runtime、data 不动。
- `tools/ops/measurement_host.py`：`read_deployed_bytes`、`verify_sources` 改用 `deployment_files`，并检查 obsolete 文件不存在；删除 `maintenance_baseline`、`maintenance_profile_binding`。
- `src/model_process.py`：删掉 MODELS 常量，从安装目录 `config/deployment.json` 读对外模型，默认 `models[0]`，其他模型 400。
- `scripts/wsl/qwen-agent`：`--model` 默认取 `deployment.json` 的 `models[0]`，不对外模型在领租约前退出。
- `install_offline.py` 默认 IQ3_XXS；`resource_calibration.py` 计划必须显式写模型；`safety_gate.gate_plan` 要求计划模型等于 `served_model(host)`。
- 配置：rtx3080ti `models` = `["IQ3_XXS"]`；rtx4070tis 暂定 `["IQ3_XXS"]`，标为占位，恢复后核实（待同步项记在 `docs/plan.md`）。
- 历史维护基线：`git show ff94f3c:config/maintenance-baseline.json`。

偏离：

1. `safety_gate` 用 `served_model(host)`（读公开主机文件）而不是审查原文的 `load_host(host)['models']`，值相同，测试不依赖私有文件。
2. `published_tier` 仍能读不对外模型的档位，供假服务器探针用；几个零模型探针工具的 `--model` 选项保留。
3. 工程里的 catalog 源文件和 `model_catalog.py` 保留三条作模板；安装目录渲染后只剩一条，`priority` 沿用 3。
4. `docs/codex.md` 删掉一句早已停用的计划（Spec Readiness 合并场景四组合）。

## 部署

命令 `python3 -m tools.ops.deploy --host rtx3080ti`，部署前租约 free、模型未加载。

- 回执：files 20，read_back_verified true；removed：`config/maintenance-baseline.json`、`config/q2_0-prebuilt.json`、`config/iq2_xs-prebuilt.json`，备份在安装目录 `.tmp/maintenance-backups/deploy-20261019-161415-737275/`。
- `config/iq3_xxs-prebuilt.json` 的 `model_configuration_sha256` 为 `85f37fcb…`。

| 项目 | 结果 |
|---|---|
| `config/` 里的 prebuilt | 只剩 `iq3_xxs-prebuilt.json` |
| `config/model-catalog.json` | 1 条：`qwen3.8-flash-next-iq3_xxs` |
| `config/deployment.json` 的 `models` | `["IQ3_XXS"]` |
| `data/models` | IQ2_XS、IQ3_XXS、Q2_0 三种都在 |
| `MeasurementHost('rtx3080ti').verify_sources()` | 通过，20 个文件 |

| 请求 | 结果 |
|---|---|
| `POST /model/start {"model":"Q2_0"}` | 400："This installation serves only IQ3_XXS; other installed quantizations are not served." |
| `POST /maintenance/model/start {"model":"Q2_0"}` | 400，提示同上 |
| `POST /model/start {}` | running，`qwen3.8-flash-next-iq3_xxs`，max_context 206584，冷加载 23.1 秒 |
| 归还租约 | free，模型常驻 |

## 冒烟

- `qwen-agent --model Q2_0 codex exec hi`：输出"this installation serves only IQ3_XXS, not Q2_0"，exit 1，租约仍为 free。
- `claude --version` 2.1.303，与调用手册「自动压缩」记录的核对版本相同，不需要重跑压缩探针。
- Codex 用全新 `CODEX_HOME`；Claude Code 用全新 `CLAUDE_CONFIG_DIR` 并加 `--strict-mcp-config --setting-sources user`；工作目录在 `/home/pello` 之外（已删除）。任务：读出 note.txt 里的随机标记原样回答。
- 启动提示：native_health `sha256` 1cae169a…、`source_sha256` 5f9efc02…、`loop_prevention_enabled` false。

| 阶段 | 结果 | 传给 agent 的档位 | agent 耗时（秒） | 执行段 | 未缓存输入 | 已缓存输入 | 输出 | 引擎输入 tok/s | 引擎输出 tok/s | 任务平均输入 tok/s | 任务平均输出 tok/s |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| X1 Codex `exec` | 通过 | 206584 / 150000，high | 8.9 | 2 | 9056 | 9062 | 114 | 1751.6 | 113.5 | 1020.6 | 12.8 |
| C1 Claude Code `-p` | 通过 | 206584 / 150000 / 24576，high | 13.3 | 2 | 15863 | 15882 | 119 | 1984.4 | 75.2 | 1194.5 | 9.0 |

两次运行后都由 `qwen-agent` 归还租约。冒烟偏离：第一次 X1 作废，原因是测试包装没有关闭 stdin，`codex exec` 一直等输入约 10 分钟（模型未收到请求，租约由该运行自己持有，终止后正常归还）；加 `< /dev/null` 重跑通过。

## 遗留

- **测试隔离漏洞**：`qwen-agent` 原来只去掉 `ANTHROPIC_*`、`OPENAI_*`，从 Claude Code 会话里启动时，子 Claude Code / Codex 继承了父会话的会话 id、消息 socket 和 token，此前的冒烟和测量很可能一样。修复：`qwen-agent` 不再传入以 `CLAUDE` 开头的父环境变量（`CLAUDE_CONFIG_DIR` 除外），只保留它自己设的那几个，并加测试；部署后安全门再按新源重跑。
- rtx4070tis 恢复后：核实实际权重和对外模型，补 IQ3_XXS 档位，部署时清理旧 prebuilt 和基线文件（`docs/plan.md`）。
- 原始数据：`.tmp/single-model-1019/`（方案、审查、实现进度）、`.tmp/deploy-single-1019/`（部署回执、租约核对、冒烟记录）。
