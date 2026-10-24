# Strata v0.2.4 升级报告（rtx3080ti，IQ3_XXS，2026-10-24）

## 结论

- rtx3080ti 已从 v0.2.2（引擎 0.1.47）升到 **Strata v0.2.4**，通过短检查。
  - 标签 `v0.2.4`（标签对象 `0303f658`）指向提交 `96ca4383c7b05a8a3e6064c65d9e9977d4b3bb59`。
  - Qwen 引擎 0.1.48，build `6f8800aefe27+cuda13.0`，源 `f-023-rel`。
  - 官方 Control 在标签里是 0.1.49，我们用不到。
- 这只是短检查，不继承旧版结论。部署文件和调参结果都没改，所以没有重新部署模型配置。只做了 `--docs-only` 部署，改的是手册里的 Claude Code 核对版本。
- 引擎包 `strata-engine-0.1.48-windows-x86_64-cuda-cuda13.tar.gz` 就是 0.2.3 的同一个文件。
  - 大小 581,299,508 字节，SHA256 `1e1611b0977d984bd7d8e79591a1ba1a7e550a2f4a66bfa45744a77308a71b95`，与官方 API digest 一致。
  - 小于 1GB，自行下载，没有触发硬约束 8。
  - cublas 两个 DLL 与 0.2.2 相同，没有重写。
- 发布页在标签之后又改成了 Terminal 0.2.4.1／Control 0.1.49.1（DeepSeek 准备脚本补丁，main 上 `c33fa7ba`）。标签没有移动，我们装的是标签内容。补丁只涉及 DeepSeek，与我们无关。

## 发布说明要点与相关性（0.2.3、0.2.3.1、0.2.4）

| 条目 | 与我们的关系 |
|---|---|
| #3493 缓存大小按空闲内存自动定 | **无影响**，见下节 |
| Strix Halo 提速、Intel Arc 引擎、HC_Q8、gfx1151 分块 | 不是 NVIDIA sm_86，不相关 |
| DFlash2 草稿器（只在 Terminal，需手动选） | 不相关。`drafting.py` 的 `SUGGESTED` 表里 ampere（sm_86）建议 mtp。`ENGINE_SERVES_DFLASH2 = False`，服务模式下 DFlash2 本来就不生效 |
| Agent chat 满上下文处理、审批门拒绝（读不到权限模式时拒绝）、shell 命令里引号内的 `&` 或括号不再要审批、自定义命令工具的目录和 shell | 全在 Strata 自带 app 的 agent（`apps/host/.../strata-gate.mjs`、`agent-bridge.mjs`）。我们的审批走 Codex／Claude Code 自己的 harness 和 `qwen-approve`，不经过它。无需验证 |
| #3722 HTTPS 用系统证书 | `serve/server.py` 启动时调用 `strata_control.tls.install()`。`.venv` 里没有 truststore，回退到 certifi，导入正常。我们的路径不依赖它 |
| `serve/frontend.py`、`serve/server.py` 的工具调用解析改动 | **相关**。新增 `namespace__member` 对已声明的 `namespace.member` 工具的别名；未声明名字仍按文本返回，并在日志列出名字；`</function>` 流式收尾拆成 `function_done` 状态。短检查里 Codex 流式工具调用、MCP 都正常，0 次按文本返回 |
| `Service.prepare` 签名 | 没变（`messages, tools, kwargs, max_new, force, req, cancel`），启动提示 monkeypatch 继续有效 |
| `STRATA_SPEC_ADAPT_SM86` | 只在显式设为 1 时才生效，上游 5 对 A/B 不显著（0.995），默认关。无影响 |
| DeepSeek V4.1-Flash（独立 `strata-dsv41` 包） | 不安装，也没下载 |
| 近似平局时答案可能不同（0.2.2、0.2.3 都有，0.2.4 重申） | 实测与此一致，见 greedy 一节 |

## #3493 缓存自动定大小对我们的影响：没有

- 源码 `src/program/generate.cpp` 约 9376 行：只有 `conversation_cache_mib < 0`（即没传该参数）时才按空闲内存自动定，上限 8 GiB，按 40% 的可用量减去 `min_free` 计算。
- 注释写明 "An explicit value, 0 included, is never touched."。部署文件显式写了 `conversation-cache-mib` 8192、`conversation-cache-slots` 4、`conversation-cache-min-free-mib` 5120，所以不触发。
- 实测引擎日志里没有 "conversation cache sized from the free RAM" 那一行。会话缓存按原值工作：parked 到 4 个会话，evictions=0，restore 29–42 ms。
- `kv-resident` 20480 是显式参数，同样没变。专家缓存仍是 2922 槽、4.78 GiB，与 0.2.2 相同；日志写 "5.46 GiB free, 512 MiB reserved (+184 MiB draft head)"。

## 核对安装

- 命令：`python3 -m tools.ops.upgrade_release --host rtx3080ti --metadata .tmp/strata-024/metadata.json --source artifacts/strata/0.2.4/source.zip --engine artifacts/strata/0.2.4/engine.tar.gz --feed artifacts/strata/0.2.4/strata-feed.json --output .tmp/strata-024/upgrade-receipt.json`
- 结果：
  - 写入 479 个文件，4416 个未变，没有删除（`previous_source_paths` 为空）。
  - feed 和引擎清单签名都由 `5d1bc23abbeffd0d` 签发，核验通过。
  - 源码 ZIP 注释绑定提交 `96ca438`，备份 `.tmp/maintenance-backups/release-backup-20261024-125327-325162`。
  - `config/installed-release.json` 已写为 0.2.4、`96ca4383…`、引擎 0.1.48。
- 其它核对：
  - 源码 ZIP SHA256 `d543da4a…8f0a`，33,002,954 字节。
  - feed SHA256 `9ece0547…2b8`，14,242 字节。
  - `AGENTS.md`（`685edaa9…03bb5`）只改版本行。
  - `requirements.txt`（`517d23bc…6506`）改了两处：certifi 升到 2026.10.19，新增 `truststore==0.10.5`。两个文件的 SHA 都按审查绑定写入了元数据。
  - 用 `.venv` 的 Python 在无模型下导入 `serve.server`、`strata_control.tls`：正常，`tls.mode` 为 certifi，`Service.prepare` 存在。
- 启动提示 SHA 每次加载都是 `1cae169a…`（源 `5f9efc02…`，防循环段关闭）。压缩提示按手册沿用。

## 工具改动

`tools/ops/upgrade_release.py` 增加可选的元数据字段 `source_cmake_version`。

- 原因：v0.2.4 源码的 CMake `VERSION` 是 0.1.49（DeepSeek 引擎），而 Qwen 引擎包还是 0.1.48。原有检查要求两者相等，会直接拒绝安装。
- 做法：元数据里显式写 `source_cmake_version: "0.1.49"`；不写则默认等于引擎版本，行为不变。
- 测试：`tests.test_upgrade_release` 新增一项（18 项通过）；Main 随后跑全量单测 743 项通过。
- 以后 CMake 与引擎包版本再分家，仍需人工核对后在元数据里绑定，不会自动放行。

## Claude Code 版本

- 当前 Claude Code 是 2.1.310，手册记的是 2.1.309，所以先跑了压缩探针：`python3 -m tools.ops.claude_compact_probe --out .tmp/strata-024/compact-probe --repeat 3`。206584／150000 档 12 格全部通过。
- 手册已改成 "2.1.309、2.1.310 于 2026-10-24 重新核对"，`deploy --docs-only` 1 个文件回读通过（备份 `deploy-20261024-131144-941965`）。
- Codex 是 0.163.0，没变。

## 短检查（一个实例，每项一次，隔离环境）

- 条件：`env -i` 式最小环境，全新 `CLAUDE_CONFIG_DIR` 和 `CODEX_HOME`；Claude Code 加 `--setting-sources user --strict-mcp-config`，Codex 的 stdin 用 DEVNULL；档位 206584／150000，high；工作目录在 `/home/pello` 下的临时目录，用完已删。
- 驱动脚本沿用 v0.2.2 的 `smoke.py`，改了版本号。运行记录在 `.tmp/strata-024/smoke/`（第 1 遍）和 `smoke2/`（第 2 遍）。

| 阶段 | 内容 | 结果 |
|---|---|---|
| C1 | Bash 写标记（经 qwen-approve）、Read 读回、Brave MCP 搜发布页 | 通过：标记原样读回，URL 为 `releases/tag/v0.2.4` |
| C2 | 同一会话 `/compact` | 通过：34,715 缓存输入，摘要约 3.5K token，按工程压缩提示分节 |
| C3 | 恢复会话，不用工具回忆 | 通过：只输出 JSON，标记和 URL 都对，没调用工具 |
| X1 | Codex `cat note.txt` 加托管搜索 | 通过：note 内容正确；web_search 先搜索，再打开 v0.2.4 发布页 |
| X2 | `--approve-for-me` 下 curl 申请提权 | 通过：提权后返回 HTTP 200 |

两遍都全过，所有 `did not read as a call` 为 0 行，输出里含 `<tool_call>` 文本的回复为 0 个。

第 1 遍计量（token 取自引擎日志）：

| 阶段 | 秒 | 段数 | 未缓存输入 | 已缓存输入 | 输出 | 引擎输入 tok/s | 引擎输出 tok/s |
|---|---:|---:|---:|---:|---:|---:|---:|
| C1（含冷加载） | 79.8 | 8 | 39763 | 69651 | 1670 | 1838 | 78.9 |
| C2 | 46.4 | 1 | 1832 | 34715 | 3502 | 960 | 104.2 |
| C3 | 14.1 | 1 | 5009 | 16046 | 123 | 1747 | 111.1 |
| X1 | 29.1 | 3 | 16636 | 20917 | 654 | 1832 | 112.9 |
| X2 | 25.9 | 3 | 15535 | 9487 | 385 | 1680 | 99.4 |
| 合计 | 195.4 | 16 | | | 6334 | | 96.7 |

- C1 第 1 遍偏慢，第 2 遍复现不了。第 1 遍 C1 各段 70–83 tok/s，最低 69.8（85 token 的一段），高于 60 的意外线，但比 0.2.2 的 C1（106.5）低。第 2 遍（同条件、冷加载）C1 为 106.3，各段 92–119，全程最低 92.2，合计 108.0。判断为安装后第一次冷加载的瞬时现象，原因没有查明（可能是新 `strata.exe` 的文件缓存冷）；没有降到 60 以下，不按意外事件处理，只记录。
- 第 1 遍加载后的提示 SHA、`/health` 都正常。显存告警与 0.2.2 一样：请求开始时剩 274 和 146 MiB（#2065 的警告行），速度正常，没有 OOM。
- 启动行：`sm_86 (Ampere): 8 exact speed switches on by default`，与 0.2.2 相同；`--pool-workers 15` 的建议警告仍在，没动，保持 23。

## greedy 对比（一次冷加载对，非计分）

- 做法：复用 0.2.2 的 3 个固定 Chat 请求和请求体字节（short 350 token、long 49,249 token、tool 635 token），temperature 0，2 次冷加载，每次 short long tool short long tool。记录在 `.tmp/strata-024/greedy-024/`。
- 速度：引擎输出 96.8／95.9 tok/s（0.2.2 为 91.4，0.1.45 为 88.1）；引擎输入 2365／2246 tok/s；冷 49K 预填约 2725／2681 tok/s（0.2.2 约 2720）；冷加载 26.7／26.1 秒（0.2.2 为 26.8–27.8）。
- 答案：和 0.2.2 一样不是逐 token 一致。
  - 同版本内也不一致：0.2.4 两次冷加载的 short 和 long 全不相同。tool 两遍里 5 份只有第 2 遍有一份和 0.1.45／0.2.2 某一份相同。
  - 8 次工具调用参数全是 `get_weather {"city":"Kyoto","unit":"celsius"}`。
  - long 第 2 问（正解 28）所有版本都答 34，与 0.2.2 一样错；0.1.45 有一次答 47。
  - long 第 3 问（正解 511）全部答对。
  - long 第 1 问（正解 R1338）：0.2.4 的 4 次里 3 次答 R1338，1 次答"R1309 与 R1338 并列"。0.2.2 是 0/4（4 次一致答错），0.1.45 是 4/4。这是同一提示的 4 个样本，不能下质量结论；只说明 0.2.2 的"四次一致答错"不是 0.2.x 的稳定偏差，这道题处在模型判断的边界上。
- 结论：近似平局时答案会不同，与发布说明的 Known limits 一致，是预期现象，不作为回退理由。

## 偏离与未验证项

- 偏离 1：为安装补了 `source_cmake_version`（见上）。
- 偏离 2：短检查比 0.2.2 多跑了一遍（第 2 遍）、加了一次 greedy，原因是 C1 第 1 遍偏慢。
- 偏离 3：驱动脚本 `greedy.py` 开头加了一步"若模型在运行先停掉"，因为第 1 遍短检查后模型还驻留着。
- 旧制品清理：worker 的删除命令被自动模式分类器拒绝，没有绕过；Main 按部署规则「备份与保留」（用户 2026-10-14）核对清单后删除了 `artifacts/strata/0.1.45/`、`artifacts/strata/0.1.44.1/` 和旧升级备份 `release-backup-20261018-114848-289807`、`release-backup-20261022-205620-310129`，来源与 SHA 留在 `docs/downloads.md`。0.2.2 制品（前一版）保留，回退用。
- `requirements.txt` 新增的 `truststore==0.10.5` 没有装进 `.venv`（我们只用 certifi 回退路径，启动日志无异常）。
- cublas／cudart 实际加载路径仍没实测（同 0.2.2，需要提权读进程模块）。
- `--pool-workers 15` 对比 23 仍未验证（速度类参数，要按块交替测）。
- 近似平局的差异只做了 greedy 小样本，没有做 ARW 之类的分数对比。
- rtx4070tis 离线，没有升级。
- 没有做故障恢复、取消、Reviewer 兼容等完整回归；它们按周安排，不属于短检查。

## 提交

- `fbc6ff9`：升级 rtx3080ti 到 Strata v0.2.4（引擎 0.1.48）：upgrade_release 支持元数据绑定源码 CMake 版本，制品清单、下载清单、手册 Claude Code 核对版本 2.1.310。

## 回退

- `python3 -m tools.ops.upgrade_release --host rtx3080ti --rollback .tmp/maintenance-backups/release-backup-20261024-125327-325162 --output <回执>`。字节级复原已在 0.2.2 做过演练。
- 回退后要把 `config/artifacts/strata-release.json`、`strata-v0.2.4.json`、`strata-v0.2.2.json` 和 `docs/downloads.md` 改回去。

## 残留检查

- 后台任务全部结束（下载、两次 smoke、greedy、final_stop），没有残留进程；Windows 上没有 `strata.exe`。
- 收尾时领租约把常驻模型停掉，随后归还。最后一次 `/health`：`{"lease": "free", "model": null}`，前端健康。
- 临时工作目录已删除；运行明细在 `.tmp/strata-024/`，可删。
