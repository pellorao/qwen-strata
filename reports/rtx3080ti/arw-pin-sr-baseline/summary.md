# 固定 ARW 提交上的 Spec Readiness 基线（rtx3080ti，2026-11-22）

## 结论
- 用固定的 ARW 提交 6ca23a9（`config/arw-pin.json`，夹具树 4326aca）的 `reviewer-capability run`，在 Strata（IQ3_XXS，安装默认档 206584／150000，effort high）上跑出 Spec Readiness 3 个有效实例，无作废，模型加载一次，租约事后为 free。
- **盲裁尚未做**：本工作按约束不开子 agent，裁判须由 Main 另派（至少 Sonnet high）。已建好盲池，见下。因此还没有可比较的最终分，只有无裁决的区间。
- 区间（`score --provisional`，n=3 实例，均值 ± 标准差）：下界（所有未裁候选算错）-0.242 ± 0.030，上界（所有未裁候选算对）0.509 ± 0.089。区间很宽（47 个待裁候选 + 19 个对照），不能当分数用，也不能与 v1 的 SR v4.3 分数直接比较。

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

## 盲裁交接（Main 或后续工作）
盲池在 `.tmp/arwpin/pool/sr-baseline/`（47 个真实候选 + 19 个对照，`pool view`、`pool prompt` 已做；原始实例文件在 `.tmp/arwpin/sr-baseline/`）。用 ARW 的 `$reviewer-capability` 盲裁步骤：把 `adj/` 复制进裁判工作目录，用 `prompt.md` 启动裁判，得到 `decisions-sr-baseline.json` 后 `pool split <root> sr-baseline <decisions>`，再对每个实例 `score ... --decisions <root>/sr-baseline/decisions.json --no-repair --agent a<N>/agent.json --instance a<N>`，最后 `summary`。完成后把最终分补进本报告和 README 现行决定。
