# Strata v0.2.2 升级（本机，IQ3_XXS）

## 结论

- 本机已从 v0.1.45 升到 Strata v0.2.2。标签提交 `011c9e60`，引擎 0.1.47，build `76f90e58436d+cuda13.0`。本版**通过短检查**：IQ3_XXS，一个实例，每项跑一次。检查走 `bin/qwen-agent` 入口，覆盖 Claude Code 2.1.308 和 Codex 0.163.0。审查第 3 节的 2–8 项全部通过。
- 这只是短检查，不是完整验收，也不继承 0.1.45 的结论。参数沿用原有 IQ3_XXS 调参结果，没改默认值，部署文件没变，所以没有重新部署模型配置。
- **greedy 对比没有逐 token 一致，也不能写"答案相同"。** 同版本内本来就复现不了，0.1.45 自身两次冷加载、两遍的输出都不同。但长提示第 1 问有一个**一致的差异**：0.2.2 四次都答"R1309 和 R1338 并列最大 9997"，这是错的，R1309 实际是 9941；0.1.45 四次都答对 R1338。只有 8 个样本，而且同一提示，不能下质量结论；但它说明 0.2.2 在本机的输出分布有可观察的变化。后续测量不与 0.1.45 的结果直接比较。
- 速度：greedy 同条件下，引擎输出 0.1.45 为 88.1 tok/s，0.2.2 为 91.4 tok/s；逐请求速度比的中位数 1.075。冷 49K 预填约 2720 tok/s，0.1.45 为 2740。短检查 14 段合计输出 105.9 tok/s，单段最低 97.1；所有 50 token 以上的请求最低 77.3。全部高于 60 的意外线。

## 审查与 Main 综合意见的采纳情况

独立审查的结论是有条件通过，5 项必须全部采纳。Main 采纳的建议都已执行：

- **必须 1（安装前列出引擎目录）**：安装前只读列出 `runtime/Strata/engine/`，只有 `BUILD.json`、`strata-vision.exe`、`strata.exe`、`strata_kq.dll`，没有子目录。
- **必须 2（停服务前提）**：前端可达，lease free，模型未加载，没有 strata.exe。python 进程只有两组：前端（pythonw）和用户自己的 Virtual Mouse 计划任务，后者与本工程无关。
- **必须 3（核对提示 SHA）**：每次加载 `/health.startup_instructions` 都是 `1cae169a…`（源 `5f9efc02…`，防循环段关闭）。说明 0.2.2 下我们的 monkeypatch 仍然生效。
- **必须 4（工具调用按文本返回）**：所有运行的 model-server 日志里，`did not read as a call` 都是 0 行。C/X 的回复里含 `<tool_call>` 文本的也是 0 个。
- **必须 5（两处行为变化）**：写在下一节。
- **建议：greedy 基线**：已做，结果见后。
- **建议：工具加固**：已做，见「工具改动」。
- **建议：真实规模回滚演练**：已做，见「回滚演练」。
- **建议：短检查补审查第 3 节 2–8 项**：已做。
- **未采纳**：把"引擎目录未知文件"改成拒绝。改为安装前只读列清单，效果相同。

## 两处行为变化（与 0.1.45 结果不可比的原因）

**工具调用解析（#3075 / #3441）**
- 请求声明了工具时，调用未声明的名字，0.1.45 会作为 tool_call 返回、由客户端报错重试；0.2.2 改成按普通文本返回，所以 Codex 或 Claude Code 的那一轮可能以一段 `<tool_call>` 文字直接结束。
- `<=NAME>`、`<function:NAME>` 这类偏写，只要 NAME 是已声明的工具，现在会被读成调用。
- Chat 和 `/v1/messages` 在没声明工具时不再返回 tool_calls。
- 这会改变失败模式，以及防循环和 Reviewer 场景的行为统计。本次短检查里没有出现这种情况（0 行、0 个回复）。

**sm_86 解码开关表**
- 引擎启动行写明 8 个开关默认打开：ADAPT_NOWAIT、CPU_IQ_ALL_EXACT1、SIDE_MIXER、ATTN_DAILY、GR_UP75、GU_SWIGLU、QSA_ROWS、B6_MMVQ_ROWS。`STRATA_SM86_PERF=0` 可以关掉。
- 上游的"答案相同"没覆盖我们的组合：Windows、IQ3_XXS、spec 4、spec-min-p 0.9、ADAPT_LAG 2。
- 我们的 `src/model_process.py` 白名单里还没有 `STRATA_SM86_PERF`，所以目前无法做 A/B。

## 工具改动（`tools/ops/upgrade_release.py`、`tests/test_upgrade_release.py`）

- `atomic()` 写入失败时删掉临时文件。
- `rollback()` 遇到失败逐文件继续，最后汇总失败清单再报错；恢复改为流式复制，恢复后再回读 SHA。
- 删除和 `previous_source_paths` 的路径比较一律转小写，因为 drvfs 不分大小写。
- 删除旧文件之后，对全部写入文件再做一次存在和 SHA 复核。
- 文件名拒绝 Windows 保留名（CON、NUL、COM1 等，含带扩展名的形式）、以点或空格结尾的名字，以及 `<>"|?*` 和控制字符。
- **签名核验**
  - 新增 `--feed` 参数：核验 `strata-feed.json` 的 release 摘要和 Ed25519 签名，元数据里的引擎包条目必须与签名 feed 中的条目完全相同；同时核验引擎清单签名（与上游 `signing_payload` 相同的规范 JSON）。
  - 公钥固定在工具里（key_id `5d1bc23abbeffd0d`）；源码 ZIP 自带的 `strata_control/update_keys.json` 必须与它相同。
  - **偏离**：Main 原意是用源码 ZIP 自带的 `signing.py` 核验。我改用本机 `cryptography` 46 做 RFC 8032 核验，没有执行下载来的代码；算法相同。
- **测试**：从 9 个增加到 17 个。新增签名、Windows 名字、源码写入故障、unlink 故障、`atomic` 残留、回滚部分失败、未变引擎文件被跳过且不删、大小写变体不删。全量单测 735 个 OK（最后一次 101 秒）。
- 文档 `docs/installation.md`、`docs/frontend.md`（命令加 `--feed`）、`docs/downloads.md` 已同步。feed 和 `.sig` 存在 `artifacts/strata/0.2.2/`。

## 回滚演练（真实规模）

- 把 `runtime/Strata` 复制到 `.tmp`（不含 .venv，3302 个文件，402 MB，WSL ext4），用真实制品跑 upgrade：6.3 秒，写 1566 个文件，3067 个未变，删除 `docker-entrypoint.sh`，引擎目录变成 7 个文件。
- rollback 用时 0.5 秒，之后逐文件 SHA 与升级前**完全相同**。
- 留下 109 个空目录（`apps/` 等），已知、无害。
- 副本和演练备份已删除。
- 局限：副本在 ext4 上，没有验证 drvfs 的大小写行为和速度。

## 安装

- 命令：`python3 -m tools.ops.upgrade_release --metadata <元数据> --source artifacts/strata/0.2.2/source.zip --engine artifacts/strata/0.2.2/engine.tar.gz --feed artifacts/strata/0.2.2/strata-feed.json --output <回执>`
- 结果：用时 86 秒，含停止和重启前端。写入 1566 个文件，3067 个未变跳过，删除 `docker-entrypoint.sh`。feed 和清单签名都由 `5d1bc23abbeffd0d` 签发，核验通过。
- 独立复核：
  - `installed-release.json` 为 0.2.2 / 011c9e60 / 0.1.47。
  - 引擎目录 7 个文件逐个与清单 SHA 一致：strata.exe、strata_kq.dll、strata-vision.exe、cublas64_13.dll、cublasLt64_13.dll、BUILD.json、engine-component.json。
  - 21 个部署文件与工程渲染结果一致，配置没变，不部署。
- AGENTS.md 和 requirements.txt 按审查绑定的 SHA 写入。requirements 只把 cmake、ninja 移出，`.venv` 不变。
- Claude Code 2.1.308 与手册记录的 2.1.304 不同，所以先跑了 `claude_compact_probe --repeat 3`，206584/150000 档 12 格全部通过。之后把手册版本号改为"2.1.304、2.1.308"，`deploy --docs-only` 1 个文件回读通过。

## 短检查

**隔离**：`env -i` 最小环境，全新的 `CLAUDE_CONFIG_DIR` 和 `CODEX_HOME`，Claude Code 加 `--setting-sources user --strict-mcp-config`。工作目录 `/home/pello/smoke-0.2.2`，用完已删除。档位为默认 206584/150000，high。

| 阶段 | 内容 | 结果 |
|---|---|---|
| C1 | Bash 写随机标记（经 qwen-approve）→ Read 读回 → Brave MCP 搜发布页 | 通过：标记原样读回，URL 为 `releases/tag/v0.2.2` |
| C2 | 同一会话 `/compact` | 通过：16,307 token → 3,411 token 摘要，按工程压缩提示分 6 节，没有带入全局 CLAUDE.md |
| C3 | 恢复会话，不用工具回忆 | 通过：只输出 JSON，两个值都正确，没调用工具 |
| X1 | Codex `cat note.txt` 加托管搜索 | 通过：输出正确，web_search 先搜索、再打开正确的发布页 |
| X2 | `--approve-for-me` 下 curl 申请提权 | 通过：沙箱内返回 000（exit 6），提权后 200；guardian 预算 512/1024 |

| 阶段 | 总耗时（秒） | 执行段 | 未缓存输入 | 已缓存输入 | 输出 | 引擎输入 tok/s | 引擎输出 tok/s |
|---|---:|---:|---:|---:|---:|---:|---:|
| C1（含冷加载） | 64.9 | 5 | 27403 | 11906 | 1188 | 1635.3 | 106.5 |
| C2 | 47.5 | 1 | 1832 | 14475 | 3411 | 1008.8 | 105.0 |
| C3 | 16.9 | 1 | 4774 | 8946 | 121 | 1849.0 | 107.2 |
| X1 | 31.8 | 3 | 17760 | 20982 | 623 | 1913.2 | 111.1 |
| X2 | 32.7 | 4 | 15822 | 19132 | 651 | 1621.4 | 104.0 |
| 合计 | 193.8 | 14 | 67591 | 75441 | 5994 | 1681.5 | 105.9 |

- token 全部取自引擎日志，所有执行段都能被 `strata_tokens` 解析。
- 思考上限：主请求 8192/24576，guardian 512/1024，qwen-approve 最大 1024。
- Messages 的 usage 拆分变了（#2289）：C1 里 input 3、cache_creation 25543、cache_read 11906，与引擎的 read 25546、reused 11906 对得上，总量不变。
- 总耗时是每阶段 qwen-agent 的起止时间，C1 含冷加载。

**审查第 3 节 2–8 项与方案第 7 步**

- 提示 SHA：见上，每次加载都是 `1cae169a…`。
- 工具调用按文本返回：0 行，0 个回复。
- 输出上限重试：流式 `/v1/responses` 设 `max_output_tokens` 300。第 1 次撞上限，前端重试一次（第 2 次也撞上限），之后按 MAX_RETRIES=1 原样返回 incomplete。符合设计。
- 断连：流式请求读 42 帧后关闭连接，引擎记 `(disconnect, cancel=True)`；2 秒后下一请求 1.05 秒正常完成。
- 无 key 访问：直连 127.0.0.1:8100 `/v1/messages`，不带 key、空 key、错 key 都返回 401。health 显示 `api_key: true`，日志里没有 "no API key" 警告。
- 启动行：
  - 23 个 worker，逻辑处理器 2,4,…,31，每个物理核一个，host 在 0；
  - reserve 512 MiB（另 +184 给 draft head），专家缓存 2922 槽、4.78 GiB；
  - health 的 `images` 为 false；没有 GPU 角色行。
  - **新警告**：`23 CPU expert workers … more than this CPU can use well … Recommended: --pool-workers 15`。0.1.45 没有这个警告。按硬约束 5，这个值是在 0.1.45 上调出来的，0.2.2 上是否最优没有验证。本次不改。
- 显存：加载完成后剩 276 MiB；请求开始时最低 112–148 MiB，0.1.45 为 274 / 134。速度正常，没有 OOM。
- cublas DLL 实际来源：**未能实测**。引擎以管理员令牌运行，`Get-Process` 读 Modules 和 psutil 读 memory_maps 都被拒（AccessDenied）。推断：`lib_dirs` 只是加到 PATH 里，Windows 先搜程序所在目录，所以应该加载 `engine/` 里随包带的 cublas64_13 / cublasLt64_13。`.venv` 的 cu13 目录里也有这两个 DLL 和 cudart64_13；cudart 是否静态链接也没实测。
- 约 20K 的 prefill：greedy 长提示实际 49,249 token，冷预填约 2720 tok/s。
- stop→start：两次 stop 后都没有 strata.exe 和 native service 进程，重载 26.7 秒，请求正常。
- 冷加载时间：0.2.2 约 26.8–27.8 秒，0.1.45 约 23–26 秒。

## greedy 逐 token 对比

**做法**
- 3 个固定 Chat 请求，temperature 0，max_tokens 3072，思考 1024，非流式，单请求串行：
  - short：350 token 提示；
  - long：49,249 token 合成表格加三问；
  - tool：635 token，一次 `get_weather` 调用。
- 每版冷加载 2 次，每次按 short long tool short long tool 的顺序跑。
- 比较正文、思考和工具调用的完整内容，以及输出 token 数。
- 两版的请求体字节相同，提示 token 数逐个相同（350 / 49,249 / 635）。

| 请求 | 045#1 | 045#2 | 022#1 | 022#2 |
|---|---|---|---|---|
| short 第 1 遍 | A（2623） | B（2364） | C（2649） | D（2409） |
| short 第 2 遍 | E（2598） | F（2109） | G（2518） | H（2487） |
| long 第 1 遍 | A（1972） | B（1947） | C（1894） | D（2057） |
| long 第 2 遍 | E（1575） | F（1818） | G（1988） | H（1844） |
| tool 第 1 遍 | A（64） | B（59） | C（64） | D（60） |
| tool 第 2 遍 | E（58） | E（58） | F（62） | E（58） |

（同一字母表示完整内容逐字相同；括号里是输出 token 数。）

- 同版本复现不了，与 v0.1.45 升级时的发现一致。所以"逐 token 一致"无从核实。
- 有跨版本完全相同的输出：tool 第 2 遍 045#1、045#2、022#2 都是 E。8 次工具调用的参数全部是 `get_weather {"city":"Kyoto","unit":"celsius"}`。
- long 的三问：
  - 第 3 问（511）8/8 正确；
  - 第 2 问（正解 28）两版都答错，答 34，0.1.45 有一次答 47；
  - **第 1 问** 0.1.45 4/4 答 R1338（正确），0.2.2 4/4 答"R1309 与 R1338 并列 9997"（错误）。0.1.45 load2 的正文里也提到过 R1309 可能并列，说明这道题本来就处在模型判断的边界上。
- 只记录，不作为回滚理由；任务给的回滚条件不含逐 token 差异。

## 偏离

- 长提示实际 49K token，计划写的是约 25K；表格比估算长，仍覆盖 20K 级 prefill。
- 签名核验没用 `signing.py`，理由见「工具改动」。
- **探针脚本**：前三次失败都是我写的客户端问题，不是 Strata：
  - 第 1 次：请求体带 `model=IQ3_XXS`，前端按名字不符返回 409；
  - 第 2 次：sed 删掉了大括号，语法错误，没有加载模型；
  - 第 3 次：断连时 `conn.sock` 为 None。
  - 共多花 3 次模型加载。第 3 次里输出上限重试那部分已经正常运行。
- **X1 第一次挂起 9.7 分钟**：`codex exec` 在 stdin 不是 TTY 时等待 EOF（"Reading additional input from stdin..."），没有发出任何模型请求。结束 codex 进程后租约由 qwen-agent 正常归还；改为 stdin=DEVNULL 后重跑 X1、X2，都通过。
- 手册的 Claude Code 核对版本已改并部署到 本机；

## 未验证

- cublas / cudart 的实际加载路径（需要提权读取进程模块）。
- 0.2.2 上 pool-workers 23 对比 15 的速度（引擎新增建议；属速度类参数，要按块交替测）。
- sm_86 开关表开和关的对比（白名单缺 `STRATA_SM86_PERF`）。
- 长提示第 1 问的系统性差异是否来自 sm_86 开关表、route tail skip 或其他改动。
- 版本间速度的正式对比：本次只有单次 greedy，输出长度也不同，只作参考。
- `install_offline` 用发布版本号拼 `engine-v<version>` 目录的已知限制（只影响重建）。

## 回退

- 命令：`python3 -m tools.ops.upgrade_release --rollback .tmp/maintenance-backups/release-backup-20261022-205620-310129 --output <回执>`
- 演练实测字节完全复原，会留下空目录。
- 回退后还要把 `config/artifacts/strata-release.json`、`strata-v0.2.2.json`、`strata-v0.1.45.json` 和 `docs/downloads.md` 改回去。
- 0.1.45 制品在 `artifacts/strata/0.1.45/`；按 zip 路径重装需要从 git b871dfe 取旧工具。

## 留给 Main

1. **git 未提交**。工作树改动：
   - `tools/ops/upgrade_release.py`、`tests/test_upgrade_release.py`；
   - `config/artifacts/strata-release.json`、`strata-v0.2.2.json`（新增，已改为 installed-本机-sha-verified，含写入数、备份、签名已核验）、`strata-v0.1.45.json`（superseded-本机-2026-10-22）；
   - `docs/downloads.md`（改为已安装）、`docs/installation.md`、`docs/frontend.md`、`docs/installation-directory-readme.md`（Claude Code 2.1.308）、`.gitignore`；
   - `docs/plan.md` 是 Main 自己的改动；
   - 未跟踪：`artifacts/strata/0.2.2/strata-feed.json`、`.sig`（12KB；`.gitignore` 是否覆盖 artifacts 请核对）。
2. **v0.1.44.1 制品待删**（没有删，交 Main 核对）：
   - `artifacts/strata/0.1.44.1/engine.zip`（155,480,443 字节）；
   - `artifacts/strata/0.1.44.1/source.zip`（22,629,639 字节）。
   - 来源和 SHA 留在 `docs/downloads.md` 和 `config/artifacts/strata-v0.1.44.1.json`；`reports/v0.1.44.1/upgrade.md` 只记录路径，属历史引用。
3. **备份保留**：`.tmp/maintenance-backups/` 现在有
   - `release-backup-20261018-114848-289807`（0.1.45 升级的旧备份；按规则在新备份确认可用后删）；
   - `release-backup-20261022-205620-310129`（本次升级）；
   - `deploy-20261020-183033-597814`；
   - `deploy-20261022-205816-636035`（本次 docs-only）。
   - 按规则只留最新的升级备份和最近的部署备份，我没有删。
4. 运行明细在 `.tmp/strata-022-1022/`：`progress.md`、`greedy-045/`、`greedy-022/`、`probe/`、`smoke/`（含 Claude 会话与 Codex home）、`drill-report.json`、`upgrade-receipt.json`、脚本 `greedy.py`、`compare.py`、`probe.py`、`smoke.py`。

## 存活进程与租约

- 本 worker 启动的后台任务全部已结束：两次 greedy、单测、compact probe、探针、smoke 驱动；挂起的 X1/X2 codex（pid 186928 等）和 smoke 驱动 186066 已手动结束。
- 最后一次核对：WSL 内没有 codex、qwen-agent 或驱动残留；Windows 上没有 strata.exe。
- 前端 `/health`：lease free，model null（收尾时领租约停掉常驻模型后已归还）。

## 附：升级前分析与独立审查要点（Main 补记）

- **方案**（分析 worker，Opus）：不用官方安装程序和 `install.ps1`（会改 PATH、另建目录和模型库，违反“工程是唯一来源”），继续用“标签源码 ZIP + 预编译引擎”，引擎选 cuda13 tar.gz（驱动 617.42 ≥ 580.65，cuda12 包上游标为 experimental）。
- **独立审查**（Opus，有条件通过）：路径与时机合适；模板用绝对路径 `exe`，0.2.2 的引擎组件机制不会生效；工程依赖的上游内部接口（`sampling_keys`、`Service.prepare`、`make_handler`、`_json`、`main`、`/health`、`/unload`）都还在。必须项 5 条：安装前列出引擎目录、确认服务已停、核对提示 SHA、统计工具调用变文本、报告写明两处行为变化。另提出 greedy 基线、真实规模回滚演练、签名核验、`atomic()` 与 `rollback()` 加固等建议。
- **Main 综合**：采纳全部必须项和上述建议；没采纳“引擎目录未知文件改为拒绝”，改为安装前只读列清单（效果相同、改动更少）；制品配置与工具改动在安装成功后一起提交。
