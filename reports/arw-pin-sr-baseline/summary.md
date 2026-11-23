# 固定 ARW 提交上的 Spec Readiness 基线（本机，2026-11-22）

## 结论
- 用固定的 ARW 提交 6ca23a9（`config/arw-pin.json`，夹具树 4326aca）的 `reviewer-capability run`，在 Strata（IQ3_XXS，安装默认档 206584／150000，effort high）上跑出 Spec Readiness 3 个有效实例，无作废，模型加载一次，租约事后为 free。
- **最终分（盲裁已做，2026-11-22）**：Spec Readiness 3 实例均值 0.459 ± 0.057（SD，n=3，SE 0.033，95% 区间 0.317 到 0.602），实例 a1 0.515、a2 0.462、a3 0.401；无格式罚、无修复、无模型失败。47 个真实候选加 19 个对照全部裁定，候选集合已空，分数为定稿。
- 与 v1 的 SR v4.3 分数不可直接比：场景版本（v4.5 修订 48，v2 草案口径）、ARW 提交和计分口径都不同，只能作为 ARW 固定版的新基线供 arwtune 等比较。
- 盲裁质量：锚点 12 个一致率 1.0，合成对照 7 个全对，通过（pool split passed）；裁决分布 matched 39、not-matched 14、supported 4、unsupported 3、problem 3、false-positive 3。
- 复核清单（Main 可选复核）：4 个 supported（sr-baseline-054、056、060、063）加 1 个有争议的 unsupported（sr-baseline-064，裁判点名最难，另有 029、059）。
- 裁判是 Sonnet 5.5 high（我本人，不是 Opus；`decisions` 的 adjudicator 字段如实写 blind Sonnet 5.5 high），按 ARW skill 的下限（至少 Sonnet high）。

## 条件
| 项 | 值 |
|---|---|
| ARW | 提交 6ca23a9d5b9d1116a9690bbbc39b42a408b8df07，未改，工作树干净；运行时版本 0.5.4-pre，与检出一致 |
| 提供方 | `driver: strata`，隔离 HOME（自带 ARW 安装与守护进程），安装目录经影子视图补 `listen_address` |
| 启动提示 | Strata 服务端每次请求追加；/health 加载 SHA 1cae169a… = sha256(startup_prompt_bytes(raw, False))，见 `binding.json`（ok） |
| 压缩提示 | ARW 取安装目录 `config/prompts/compact-prompt.txt`，ARW 未改 |
| 实例 | a1 a2 a3，每个一次 `run`，单实例并发 1 |

## 实例
| 实例 | 墙钟秒 | 非缓存输入 | 缓存输入 | 输出 | 下界 | 上界 |
|---|---|---|---|---|---|---|
| a1 | 458.7 | 82,213 | 1,882,504 | 36,089 | -0.275 | 0.609 |
| a2 | 387.3 | 82,100 | 1,825,053 | 29,371 | -0.216 | 0.478 |
| a3 | 447.4 | 93,802 | 2,325,426 | 34,734 | -0.235 | 0.439 |

墙钟均值 431 s（n=3），输出约 76-79 token/s（输出 token ÷ 墙钟，含工具时间，是粗算，不是逐请求公式）。`token-speed.py` 看不到这个隔离 HOME 里的 Codex 会话，所以没有按公式的模型速度；对比速度时须另补，不能直接比这个粗算值。每实例用时远低于 ARW 的 60 分钟模型工作上限。

## 偏离与注意
- 固定的 ARW 用 git 克隆（`.tmp/arw/<提交>/`，从本机 ARW 克隆，不是 `git archive`），因为 `run` 需要 git 检出。
- 首跑两次作废（inspect-blocked）：缺 CODEX_HOME 的模型目录，其后 `thread/start` 被拒（-32600）：Codex 的 `config.toml` 里没有 `[model_providers.qwen_strata]`。已在 `tools/arw/run.py` 的 `init` 里建私有 CODEX_HOME 并写这两项；作废实例不计入，不算上面的 3 个。
- 安装目录的 `frontend.json` 没有 `listen_address`（固定 ARW 要求），沿用 arwtune 记的做法用影子视图，不改安装目录。

## 盲裁
盲池（47 个真实候选加 19 个对照，锚点 12、合成对照 7）已全部裁定，裁判为 Sonnet 5.5 high，按 ARW `$reviewer-capability` 盲裁步骤做（`pool view`、`pool prompt`、裁判裁定、`pool split`，再对每个实例带 `--decisions --no-repair` 计分，最后 `summary`）。裁决原件在 `decisions.json`，三个实例的最终分和均值在 `summary.json`；盲池视图与原始实例文件不入库，不影响这些分数的复核（分数由 `decisions.json` 加实例的候选列表重算，候选列表随原始实例文件已清理，重算需重跑）。
