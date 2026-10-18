# Strata v0.1.45 升级（rtx3080ti，IQ3_XXS）

## 结论

- rtx3080ti 已从 v0.1.44.1 升级到 Strata v0.1.45（提交 477ac13c），**通过短检查**（IQ3_XXS，一个实例，每项一次）。检查走实际使用的 `bin/qwen-agent` 入口，覆盖 Claude Code 2.1.302 和 Codex 0.162.0，并新增一项 Codex auto_review guardian 子会话检查。
- 这只是短检查，不是完整验收，也不继承 v0.1.44.1 的结论。参数沿用原有 IQ3_XXS 调参结果，没有改默认值，也没有在本版上重新测量。ctx-fix 没有并入本次升级。
- **逐字比对没能核实上游说的"答案逐字节相同"**。原因是 v0.1.44.1 自己在本机参数下的 greedy 输出就不能复现：同一次加载里的两遍不同，两次冷加载的首遍也不同。跨版本比对因此只能作参考。参考结果与"分布不变"相符：提示 token 数逐个相同；有完全相同的跨版本输出；24 个回复的答案全部正确，工具调用参数全部相同。详见[逐字比对](#greedy-逐字比对)。
- 计量：14 个执行段全部能解析，没有未识别的行。合计引擎输出 100.1 tok/s，单个请求最低 84.6 tok/s，都高于 60 的意外线。显存告警（#2065）为 276 / 132 MiB，与上一版的 276 / 130 MiB 相同。

## 发布说明核查

升级前由独立审查（Opus high）逐条评估过，Main 已采纳。下表是要点。

| 上游变化 | 对本工程的影响 | 本次核对 |
|---|---|---|
| Flash-Next 答案逐字节相同 | 关键：决定 0.1.44.1 上的 Q3 基线能否沿用 | greedy 重放，见下文；没能核实 |
| 默认 prompt chunk 变大（auto 改为 4096..1024） | 不影响：部署配置显式给出 `--prefill 8192` | 已装 `iq3_xxs-prebuilt.json` SHA 85f37fcb，未变，仍是 8192 |
| NVIDIA prefill 小优化 | 速度可能小幅变化 | 单次测不出；正式对比需按块交替 |
| resident-RAM copy lend region | 可能影响显存或内存 | 显存告警与上一版相同；模型加载中 Windows 可用物理内存 6.7 GiB，可提交内存还剩 57.8 GiB（上一版没有记录这两项） |
| Server：工具调用 / logit-bias 解析、共享前缀分词（#567）、会话缓存复制 | 风险最大 | 工具调用（C1、X1、X2、greedy tool）全部正常；greedy 提示 token 数两版相同；reused 比例见下表 |
| 回答余量：没有思考预算的请求会提前收尾（`ANSWER_ROOM_MIN_CAP`） | 不影响：前端总会给出思考预算 | 日志里主请求 8192/24576，guardian 512/1024，qwen-approve 最大 1024 |
| `reasoning_effort: false` | 不影响：前端只接受 low / medium / high | 静态核对 |
| Prometheus gauge 改为按两次抓取之间计算 | 不影响计量：token 和 tok/s 只取自引擎日志 | `strata_tokens.py` 解析全部执行段 |
| 其他（parallel、batch、多用户、vision、Mac、AMD、Intel） | 不影响：可选功能或其他平台 | — |

源码核对：相对 0.1.44.1 新增 109 个文件，修改 158 个，没有删除；AGENTS.md 和 requirements.txt 不变。CMake 项目版本为 0.1.45。BUILD 为 0.1.45、CUDA 13.0、架构 [75, 86, 89, 120]。引擎包只有 `strata.exe`、`strata_kq.dll`、`strata-vision.exe`、`BUILD.json` 四个文件，都在升级工具的白名单内。本工程用到的 49 个引擎参数和 7 个环境变量全部还在。前端注入启动提示依赖的 `Service.prepare` 与 `make_handler` 签名不变。

## 安装

- 制品：`engine.zip`（`strata-windows-x64.zip`）165,243,142 字节，SHA256 `a1d4cafb…53a9`，与 SHA256.txt 和 API digest 都一致；`source.zip` 是标签 ZIP，23,208,999 字节，SHA256 `8d90ac92…c17f`，ZIP 注释就是标签提交。两者存放在 `artifacts/strata/0.1.45/`。
- 安装：`tools.ops.upgrade_release` 写入 3291 个文件，没有删除。独立回读后，与两个 ZIP 逐字节一致。安装记录为 0.1.45 / 477ac13c。升级备份 `release-backup-20261018-114848-289807` 已核对：保存 3182 个旧文件，SHA 全部匹配，另记 109 个新增文件，可以回退。
- 部署：`tools.ops.deploy` 23 个文件回读通过（只有基线文件内容变了）。
- 提示：启动提示源文件 5f9efc02、压缩提示 3856cb62，与工程一致；health 报告实际加载的启动提示为 1cae169a，防循环段关闭。
- 工程记录：新增 `config/artifacts/strata-v0.1.45.json`；v0.1.44.1 标为在 rtx3080ti 上已被取代；`strata-release.json`、`config/maintenance-baseline.json`、`docs/downloads.md` 已更新。

## 短检查（IQ3_XXS）

只有一个实例，每项跑一次，不取均值，也不算正式评分。每个阶段是一次独立的 `qwen-agent` 运行（固定 156584/100000 档，high）。C1 冷加载模型，之后的阶段复用已加载的模型。

隔离：`CLAUDE_CONFIG_DIR` 和 `CODEX_HOME` 都指向全新目录，工作目录放在工程之外（`/home/pello/smoke-0.1.45`，已删除），Claude Code 另加 `--strict-mcp-config --setting-sources user`。开跑前用一个假服务器截下请求核对过（没有调用模型）：只换 `CLAUDE_CONFIG_DIR` 不够。工作目录在 `/home/pello` 下时，Claude Code 会把祖先目录里的 `/home/pello/.claude/CLAUDE.md` 当成项目说明加载，v0.1.44.1 短检查 C2 摘要带入了全局约束，就是这个原因。加上 `--setting-sources user` 后不再加载。qwen-agent 自己的 hook 用 `--settings` 传入，照常生效：C1 有 qwen-approve 记录，C2 的摘要按工程压缩提示分节写出。

| 阶段 | 内容 | 结果 |
|---|---|---|
| C1 | Bash 写入随机标记（经 qwen-approve 放行）→ Read 读回 → Brave MCP 搜索发布页 | 通过：标记原样读回，URL 正确，Bash 和搜索两次审批都放行 |
| C2 | 同一会话 `/compact`（PreCompact hook 追加工程压缩提示） | 通过：19,127 → 1,974 token，压缩 28.4 秒；摘要按工程压缩提示分节，没有带入用户全局 CLAUDE.md |
| C3 | 同一会话恢复，不用工具回忆标记和 URL | 通过：只输出 JSON，两个值都正确，没有调用工具 |
| X1 | Codex 执行 `cat note.txt`，再用托管搜索找发布页 | 通过：命令输出正确，web_search 先搜索、再打开正确的发布页 |
| X2 | Codex `--approve-for-me` 下运行需要网络的 `curl`，申请提权 | 通过：触发 guardian 子线程（`thread_source=guardian_review`），预算 512/1024，放行后 curl 返回 200 |

| 阶段 | 总耗时（秒） | 执行段 | 未缓存输入 | 已缓存输入 | 输出 | 引擎输入 token/s | 引擎输出 token/s |
|---|---:|---:|---:|---:|---:|---:|---:|
| C1（含冷加载） | 49.2 | 6 | 20173 | 48645 | 835 | 1660.5 | 99.4 |
| C2 | 38.3 | 1 | 4374 | 16229 | 2592 | 1770.1 | 100.3 |
| C3 | 13.7 | 1 | 4349 | 13663 | 127 | 1706.2 | 103.3 |
| X1 | 37.6 | 3 | 17869 | 20852 | 654 | 1818.5 | 102.5 |
| X2 | 29.8 | 3 | 15723 | 9596 | 495 | 1689.6 | 95.9 |
| 合计 | 168.6 | 14 | 62488 | 108985 | 4703 | 1721.4 | 100.1 |

- token 全部取自引擎日志。C1 的执行段包含 2 个 qwen-approve 请求，X2 包含 1 个 guardian 请求。总耗时是每个阶段 `qwen-agent` 的起止时间，C1 含冷加载。
- reused：C3 已缓存 13663（上一版 13578），C2 已缓存 16229（上一版 20585，这次压缩前的会话更短）。C1 第 3、4、6 个请求复用了 16064–16399，X1、X2 的后续请求也都命中了前缀，没有发现复用异常。
- 思考上限（model-server 日志）：主请求 budget 8192 / max 24576；guardian 512 / 1024；qwen-approve 的 max 1024。
- 速度参照：v0.1.44.1 同类短检查合计 96.0 tok/s，本次 100.1 tok/s。但这次负载不同（加了 X2，C1 更短），只跑一次，**不能当作版本对比**。
- 显存：C1 有 2 个请求开始时显存只剩 276 / 132 MiB，与上一版相同，速度正常。其余阶段没有告警，没有 OOM，也没有其他 WARNING。

## greedy 逐字比对

做法：3 个固定 Chat 请求，temperature 0，max_tokens 2048，思考 1024。三个请求是：短生成（315 token 提示）、长提示（25,064 token，跨多个 8192 预填块，附三问可机械核对）、一次工具调用（585 token）。每次冷加载后按 short long tool short long tool 的顺序跑。0.1.44.1 冷加载两次（old、old2），0.1.45 冷加载两次（new、new2），共 24 个回复。比较的是正文、思考和工具调用三者的完整内容。

| 请求 | old | old2 | new | new2 |
|---|---|---|---|---|
| short 第 1 遍（输出 token） | A（148） | B（137） | C（190） | D（132） |
| short 第 2 遍 | B（137） | E（143） | F（132） | G（138） |
| long 第 1 遍 | H（1034） | I（1084） | J（1084） | J（1084） |
| long 第 2 遍 | K（1084） | L（1084） | M（1037） | N（1073） |
| tool 第 1 遍 | P（65） | Q（69） | R（65） | S（67） |
| tool 第 2 遍 | T（69） | U（63） | T（69） | T（69） |

（同一字母表示完整内容逐字相同。）

- **同版本不可复现**：0.1.44.1 的 old#1 与 old2#1 三个请求都不同；同一次加载里第 1、2 遍也都不同。所以"逐字节相同"在本机的服务路径和参数下（spec 4、自适应、会话缓存、prefill 8192）无从核实，跨版本比对只作参考。
- 与"分布不变"相符的证据：
  - 两版提示 token 数逐个相同（315 / 25,064 / 585），说明共享前缀分词没有改变这三个提示的分词结果。
  - 有跨版本完全相同的输出：tool 第 2 遍 old、new、new2 都是 T。
  - long 的三问答案在 24 个回复里全部正确（Kumamoto 2796、17、R0078 8313），只有格式有差别。
  - tool 的调用参数全部是 `get_weather {"city":"Kyoto","unit":"celsius"}`。
- 不确定性的来源没有调查（不在本次范围）。

## 偏离与清理

- 计划里每版只冷加载一次，每个请求跑 2 遍。旧版第一次录制发现同次加载内的两遍不一致，于是两版各加了一次冷加载（old2、new2），用来判断冷加载后的首遍能否复现。每次约 1.5 分钟。
- Codex 阶段也改用全新的 `CODEX_HOME`。上一版只隔离了 Claude Code 的要求，Codex 用的是用户自己的 `~/.codex`。
- 清理：删除了 `artifacts/strata/` 下的 0.1.42 和 0.1.43.1，来源与 SHA 保留在下载清单和制品清单里；`.tmp/maintenance-backups/` 只留本次升级备份和本次部署备份。旧备份路径仍写在 `strata-v0.1.43.1.json`、`strata-v0.1.44.1.json` 和 v0.1.43.1 升级报告里，只是历史记录，文件已不存在。

## 待观察

- 显存告警与上一版相同，暂不改 `--vram-reserve-mib`。

## 未验证

- 与 v0.1.44.1 的回答逐字一致性（理由见上文：旧版自身不可复现）。由此，Code Spec v5、Spec Readiness v4.2/v4.3、Commit Audit v2 在 0.1.44.1 上的 Q3 基线能否沿用到 0.1.45，没有逐字证据。
- 版本间速度对比（需要同一负载按块交替测量）。
- rtx4070tis 离线，没有升级。
