# Spec Readiness v3 测量报告（原定样本：Opus medium ×3、IQ3_XXS ×5；rtx3080ti，Strata v0.1.42，Codex 0.162.0）

加测批 C/D（目标 10 次，读分前写定于 b3566a5 的计划）仍在运行，10 次附录另报。

## 结论

- v3 是 Spec Readiness 重构的最终冻结版本：三轮两阶段审计，第 3 轮无阻断、无主要（b3566a5，修订号 42）。原定样本下，四条"一切正常"判据都成立：
  1. Opus 明显高于 Q3：0.770 对 0.563，差 0.207，约为 Q3 组内 SD 的 3 倍。
  2. 两个模型都 0 命中的用例有 3 个，都经审计确认有效，没有"审计可疑"的。它们的区分度为 0，列在下文偏离中。
  3. Q3 5 次（10 个线程）会话全部有效。
  4. 评分可复现：盲裁 A1 与全量独立复裁 A2 一致 145/145。
- **相对口径**：Q3 / Opus = 0.563 / 0.770 = **0.731**。
  - 0.75 不是 Q3 在此场景的通过线。
  - Opus 参照是 medium、未接入本工程提示、在 Claude Code 中运行，不是 ARW 定 0.75 线时用的参考模型。
  - 本次 Opus 0.770 高于 0.75；v2.1 键下 Opus 是 0.744，低于 0.75。这只说明场景比原版难，不能用来判断场景有效与否。
- **调参**：判据是两种口径的 SD 都 ≤ 0.068。原定 5 次未达（扣罚后 0.069、扣罚前 0.080）；10 次也未达（扣罚后 0.097、扣罚前 0.109，见文末附录）。**v3 不用于调参**，只用于 ARW 能力验证和 benchmark。
- v3 未能宣称"修到无问题"，残余与偏离见下文"偏离清单"。

## 分数（能力验证口径，ARW 原版罚分）

| | 各次 | 均值 | SD（样本） | 扣罚前均值 / SD | clean 接受率 | 诊断罚分次数 |
|---|---|---|---|---|---|---|
| Opus medium ×3 | 0.790 / 0.761 / 0.759 | 0.770 | 0.017 | 0.770 / 0.017 | 0.943 / 1.000 / 1.000 | 0 / 0 / 0 |
| Q3 ×5 | 0.575 / 0.560 / 0.631 / 0.449 / 0.601 | 0.563 | 0.069 | 0.613 / 0.080 | 0.981 / 0.962 / 0.981 / 0.981 / 1.000 | 0 / 1 / 1 / 3 / 1 |

- 诊断罚分主要是 `requirement-scope-continuation`：RM 发现 REQUIREMENTS 问题后没有停下，ARW 正式生成被拒，按 ARW 评分文档第 37 行提交原稿，每次 ×0.9。批 A 的 RM2、批 B 的 RM1/RM2 是这样处理的。
- 生效核对：
  - 服务日志 thinking 行全为 `budget 8192 (max 24576)`：批 A 1810 行，批 B 1008 行。
  - 启动 SHA 与 v2 一致。
  - 未部署条件，使用 IQ3_XXS 默认配置。

## 逐用例命中率（命中次数 / 次数，均分）

| 用例 | Opus ×3 | Q3 ×5 |
|---|---|---|
| SR-INPUTS#1 | 3/3 1.00 | 5/5 0.88 |
| SR-REQUIREMENTS#1 | 3/3 0.99 | 5/5 0.99 |
| SR-REQUIREMENTS#2 | 3/3 1.00 | 5/5 1.00 |
| SR-REQUIREMENTS#3 | 3/3 1.00 | 5/5 1.00 |
| SR-REQUIREMENTS#4 | 3/3 0.95 | 2/5 0.38 |
| SR-RATIONALE#1 | 3/3 1.00 | 5/5 0.98 |
| SR-ADR-EVALUATION#1 | 3/3 0.98 | 4/5 0.77 |
| MD-APPLICABILITY#1 | 3/3 0.99 | 3/5 0.58 |
| MD-EXEMPTION#1 | 3/3 1.00 | 5/5 0.95 |
| MD-MODULES#1 | 3/3 0.98 | 2/5 0.39 |
| MD-INTERFACES#1（verified principal） | 1/3 0.31 | 2/5 0.36 |
| MD-INTERFACES#2（Policy Adapter 失败） | 3/3 0.99 | 5/5 0.98 |
| MD-INTERFACES#3（rollback failureCode） | 3/3 0.95 | 1/5 0.19 |
| MD-INTERFACES#4（recoverPromotion 测试） | 3/3 0.98 | 3/5 0.58 |
| MD-INTERFACES#5（unexpected-field 顺序） | **0/3** | **0/5** |
| MD-INTERFACES#6（renderReport source） | 0/3 | 3/5 0.55 |
| MD-SEAMS-ADAPTERS#1（recoveryState 成功形状） | **0/3** | **0/5** |
| MD-DEPENDENCIES-DATA-FLOW#1 | 3/3 1.00 | 4/5 0.80 |
| MD-DEPENDENCIES-DATA-FLOW#2（Artifact Storage 读调用） | 1/3 0.33 | 0/5 |
| MD-RATIONALE#1 | 3/3 1.00 | 5/5 0.99 |
| MD-RATIONALE#2（policy 权威理由） | 2/3 0.64 | 0/5 |
| MD-RATIONALE#3（Policy Evaluation Seam 依赖方向） | **0/3** | **0/5** |

与 v2 相比：
- INTERFACES#6 由 v2 的 Q3 1/5 升到 3/5。v3 把用例收窄为"source 输入类型或诊断 path 来源，命中任一半即可"。
- MR#2 的 Opus 命中由 0/3 升到 2/3。
- INTERFACES#2 的 Q3 命中由 2/5 升到 5/5（用例编号沿用 v2 顺序；跨版本对比只作参考，因为措辞和 placement 有改动）。

## 两个模型都 0 命中的用例

这 3 个用例审计确认有效，可以从 Input 推出，没有和其他检查重复。它们在 v2 也基本是 0：v2 的 10 次中，INTERFACES#5 是 0/10，MR3 是 0/10，SEAMS 是 2/10。

1. **MD-INTERFACES#5 unexpected-field 顺序**
   - 缺陷：`architecture/05-validation-report.md:29` 列出 reason `unexpected-field`，并规定"Diagnostic 只报告上述顺序中的第一个 invalid field"。但校验顺序（encoding → syntax → root → requestId → checks → entry 各项）里没有 unexpected-field 的位置，多余根字段与无效 requestId 同时出现时，第一个 diagnostic 不确定。
   - clean 用例 C2（`specs/validation-report.md:104`）把这项明确排除在 Testing Decisions 缺陷之外。
   - 难点：缺陷藏在 600 余字的单行枚举里，要比对"reason 集合"与"顺序表"才看得出来。
   - 原版同一行 Opus 3/3 检出，v2 起降为 0。v2 把顺序文字补全到只差 unexpected-field，检出因此变难；这不是答案键错误。
2. **MD-SEAMS-ADAPTERS#1 recoveryState 成功形状**
   - 缺陷：`specs/promotion-recovery.md:57` 只给成功语义（恢复 priorTrackedState、移除 baseline、形成公开结果），`:59` 给出失败的内部结果精确形状 `{status: "failed", restoreFailureCode, baselineStatus}`。成功的 `recoveryState` 没有序列化形状，调用方无法按同一合同区分成功与失败。
   - 依据：Role 的 `module-design.md` 要求 Seam 的 Adapter 共享同一结果合同。
   - 判为偏薄的理由：
     - 同两行（:57 + :59）上还有 clean C3："不同配置结果可不同不是缺陷"。报"两个 Adapter 结果不一致"会落到 clean 用例上，只有指出"成功形状缺失"才命中。
     - v3 第 1 轮审计（K3）为此把证据组合扩为 placements（:57+51、:57+59）。
     - 审计判它有效，但措辞要求很细。
3. **MD-RATIONALE#3 Access Review → Policy Evaluation Seam 依赖方向**
   - 缺陷：`specs/access-review.md:55` 写明 Access Review 调用 Policy Evaluation Seam。`:74-80` 的 Rationale 对 identity、request facts、Reader 依赖都给了"选择 / 拒绝 / 成本"，唯独没有论证对 Policy Evaluation Seam 的依赖方向。
   - 同场景其他 Module 都论证了 Module→Seam 方向：`validation-report.md:92`、`promotion-recovery.md:85`。
   - 判为低检出的理由：第 3 轮阶段 1 的全量盲审也漏了这项（键中 MRAT P2），阶段 2 复核后才判成立。它和 MR#2（policy 权威理由）位置相邻，容易被视为同一缺陷。
   - 注：第 2–3 轮审计的阶段 2 结论以文本返回给前任 worker，原文只保存在 `v3/change-note.md` 的摘要中。本节的行号证据由接手 worker 对照 v3 冻结夹具（`v3run/adjudicate-A1/scenario/artifact-promotion/`）和答案键 `v3run/adjudicate-A1/expected.json` 核对。

另有 MD-DEPENDENCIES-DATA-FLOW#2：Q3 是 0/5，Opus 是 1/3。它不是双方 0 命中，但区分度也很低。v2 里 Opus 是 3/3，v3 降到 1/3，原因待 10 次附录再看。

## 裁决与可复现

- 原定 5 次和 Opus ×3 共 145 个候选。
- 主裁决 A1：全新 Opus-high，去掉来源，按用例分组，组内乱序（seed 3101），裁决文件是 `v3run/adjudicate-A1/decisions.json`。
- 全量独立复裁 A2：另一个全新 Opus-high，seed 7717。
- 两者 **145/145 一致**。裁决 brief 注明：INTERFACES#6 命中任一半即可 matched；vr:45 处 INTERFACES#5 与 #6 是同一关联点的共同候选，按语义区分。

## 会话检查（Q3 10 个线程，按规则读 actions.md、flagged.md 全文）

- 批 A 6 个线程有效。标记项有 3 条，都没有接触禁止来源：
  - 1 次写 `/tmp` 因只读失败；
  - 2 次幻觉 workdir 失败。
  - 期间发生 3 次压缩。
- 批 B 4 个线程有效，标记项都是幻觉 workdir 失败、无结果。
- 启动上下文 SHA 一致，终态都是 ready。

## 偏离清单（相对"修到无问题"目标）

1. **v3 残余次要项**：第 3 轮未改，记在 `benchmarks/reviewer-suite-v1/spec-readiness-v3.md`「残余」节。
   - (a) RM 中 `access-review.md:15`、`promotion-runtime.md:11`、`promotion-recovery.md:19` 选定的 `#requirements` 把失败结果交给未选定的 Interfaces 节；`promotion-runtime.md:11` 与未选定的 `:27` 有张力。严格的 Reviewer 可能据此报 REQUIREMENTS，答案键里没有对应用例。
   - (b) `vr:45` 处 INTERFACES#5 与 #6 共用关联点，靠裁决区分。
   - (c) MODULES#1 没有 DEPS placement；APPLICABILITY#1 只按 APPLICABILITY 计。
   - (d) `access-review.md:93` 没有覆盖 policy 与 facts 同时无效的情况。
   - (e) `ar:45` request 带额外字段的结果未定义。
2. **3 个双方 0 命中用例**：有效，但区分度为 0，会压低 AP 问题发现率的上限。保留，没有删除。删除需要用户决定。
3. **v2 与 v2.1 分数是 vr:31 歧义的两端**：真实值在两者之间。v3 改了文字，消除了这个歧义；v2、v2.1 的分数只与各自比较。
4. **RM 越过停止点**：Q3 的 RM 经常越过 REQUIREMENTS 早停点（5 次中 4 次在 v2 被罚，v3 中 4/5 次有诊断）。这是模型行为，不是场景缺陷，但它让扣罚后 SD 变大。
5. **Opus 参照的局限**：Opus 是 medium、未接入本工程提示的参照。v2.1 键下 Opus 低于 0.75 线。

## 变更历程（v2 → v2.1 → v3）

| 版本 | 提交 | 改动 | 用途 |
|---|---|---|---|
| v2 | 861a2c5 | 六轮两阶段审计后的夹具与答案键补丁，修订号 41 | Opus ×3、Q3 ×10 实测 |
| v2.1 | c760617 | 只改答案键：删 MODULES clean C0（vr:31），新增 MODULES#2 问题用例；placement 在盲判前写定 | 对 v2 的回答只重评分，不重跑；不登记 manifest |
| v3 | b3566a5 | 改夹具文字，修订号 42。三轮审计各有一个全新的 Opus-high 审计者，各轮盲答结果如下 | Opus ×3、Q3 ×5（加测到 10） |

v3 的文字改动：
- vr:31 写明 `renderReport` 与 `parseArtifact` 是两个独立 operation，各自引用 Invalid Artifact Contract；
- vr:90 补不复用 parseArtifact 的取舍；
- vr:100 补"不需要新 ADR"的结论；
- vr:11 改正 diagnostic path 的措辞；
- rm:15 去掉无来源的 policy；
- rm:45 删去 denied authorization；
- AP 副本 rm:23/:41 对齐公开合同；
- prt:11 与 Module 节对应。

v3 的答案键改动：
- 保留 MODULES clean C0，改写 expectation；
- INTERFACES source 用例收窄；
- SEAMS#1 改为 placements；
- REQ clean 措辞改准。

v3 三轮的盲答结果：

| 轮次 | 盲答 RM | 盲答 AP |
|---|---|---|
| 1 | 0.968 | 0.604 |
| 2 | 0.992 | 0.686 |
| 3 | 0.986 | 0.739（clean 43/43） |

## v2 / v2.1 的 10 次结果（只重评分，不重跑）

| | Opus ×3 | Q3 ×10 扣罚后 均值 / SD | Q3 ×10 扣罚前 均值 / SD | 是否达到 SD ≤ 0.068 |
|---|---|---|---|---|
| v2 | 0.773（SD 0.024） | 0.538 / 0.071 | 0.585 / 0.072 | 否（两口径都超） |
| v2.1 | 0.744（SD 0.023） | 0.537 / 0.064 | 0.584 / 0.065 | 是（两口径都满足） |

- v2.1 新用例 MODULES#2：Opus 0/3，Q3 5/10。盲判 16 个相关 finding，7 个 matched。
- 判据是在读批 C/D 分数之前、针对 v2 写定的（018d58f）。按它判，v2 未达，v2.1 达到。
- v3 是今后实际使用的版本，判断以 v3 的 10 次附录为准。

## 引擎常驻与前端空闲不一致

- **现象**：
  - v2 批 A 04:12:46 启动的 IQ3 引擎，到批 B、C 一直未重启（批 B 引擎日志段没有 `engine started`，"since the start" 计数连续）。
  - 但每批预检都报"租约空闲、模型未启动"。
  - 07:15 批 D 结束时，前端租约空闲，strata.exe 仍常驻，占 9.2GB。
- **处理**：worker 按规则领租约、停模型、归还，确认 strata.exe 已退出、model=null。v3 开跑前同样确认了租约释放、模型已停。
- **影响**：只有精确前缀缓存会跨批复用，这是规则允许的，测量有效。
- **疑似原因**：ARW 持有模型模式下，ARW provider 结束时不停引擎，或前端不把 ARW 启动的引擎记为"已加载"。尚未定位，建议另立问题核对前端 `/health` 与 ARW provider 的停止路径。

## 待清理原始记录（经用户确认再删；合计约 600MB，均在 `.tmp/`）

- `.tmp/spec-v2/q3/`：258M，v2 Q3 ×10
- `.tmp/spec-v2/v3run/`：179M，v3 Opus 与 Q3
- `.tmp/spec-v2/v3/`：51M，v3 三轮审计与盲答
- `.tmp/spec-v2/r1`–`r7`：各 17M，v2 审计轮次
- `.tmp/spec-v2/opus/`：17M
- `base-arw`、`v2-arw`：各 9.1M
- `adjudicate*`、`v21/`：约 3M
- `.tmp/spec-rule-audit/opus/`：17M，v1 规则审查时的 Opus 原始记录

## "一切正常"判定（自主模式决策，2026-10-13）

- **Main 判定**：判据 1、3、4 成立；判据 2 按字面成立，3 个双方 0 命中用例均经审计确认有效。v3 用于 ARW 能力验证和 benchmark，采用相对口径。之后进入下一个场景 Code Spec。
- **独立意见**（全新 Opus-high，第三次，未参与测量）：
  - 判据 2 成立，v3 不必再修。SEAMS#1 要求措辞精确，不等于有歧义；MR3 可从 `module-design.md:35` 以及同场景其他 Module 的依赖方向论证推出。
  - 3 个用例建议保留：删除后缺陷仍在夹具里，会变成未登记缺陷。
  - 不阻断进入 Code Spec，但要先处理引擎常驻与前端空闲不一致，它违反独占 key 硬约束。
- **双方一致**，没有分歧。证据链缺口：v3 第 2、3 轮阶段 2 的审计结论原文只保存了摘要（见 `benchmarks/reviewer-suite-v1/spec-readiness-v3.md` 的变更说明）。
- **残余 (a)**（RM 的 `#requirements` 把失败结果交给未选定的节）要在 10 次附录里核对是否造成失分；如果造成失分，升为修复项。

## 附录：v3 加测至 10 次（批 C/D）

### 结论
- Q3 ×10 扣罚后均值 0.546、SD 0.097；扣罚前均值 0.594、SD 0.109。**两种口径都明显高于判据 ≤0.068，不成立**，v3 不宜作为调参用的低噪声场景。
- 加测 5 次（批 C/D）自身均值 0.528、SD 0.125，比原定 5 次（0.563 / 0.069）更散，主要由两次低值驱动（见"离群"）。
- 相对口径：Q3 ×10 / Opus = 0.546 / 0.770 = 0.709（原定 5 次为 0.731）。0.75 不是 Q3 的及格线。
- 三个双 0 用例在 10 次中仍为 0/10（INTERFACES#5、SEAMS#1、MD-RATIONALE#3）；另 MD-RATIONALE#2 为 Q3 0/10（Opus 2/3）。

### 运行与有效性
| 批 | 时间 | 次数 | RM 正式生成 | 候选 | 会话检查 | 服务日志 thinking 预算 |
|---|---|---|---|---|---|---|
| C | 09:04–09:52 | 3 | RM2 被拒，用草稿 | 40 | 6 线程全部有效 | 1631 行全为 8192 |
| D | 09:52–10:24 | 2 | RM1、RM2 都被拒，用草稿 | 36 | 4 线程全部有效 | 987 行全为 8192 |

- 启动上下文 SHA（`5d36e1d1…` / `50bd785d…` / `c8957099…`）与批 A 一致。
- 会话标记项：jq `$f`/`$k` 变量假阳性；错乱 workdir 被拒且无结果；写 `/tmp`（含 `/tmp/w1.py`）被只读文件系统拒绝。没有接触隐藏答案或其他实例。
- 评分可复现：两批 `score-completed` 带裁决各跑两次，`final`/`repeat` 逐字节一致。

### 裁决
- 76 个候选去来源、按用例分组、新乱序种子，交全新 Opus-high 盲裁（`v3run/adjudicate-B1/`）：matched 59、not-matched 17（批 C 29/40，批 D 30/36）。
- 裁决者列出的最难判项，worker 逐条复核，全部同意：

| 候选 | 用例 | 裁决 | 复核理由 |
|---|---|---|---|
| C009 | DEPS#2 | not-matched | 讲的是不可变 request 的权威来源，不是 Promotion Flow 缺 Artifact Storage 读调用 |
| C010 | （同组） | matched | 点名 Flow 中缺读调用与调用方向，符合用例 |
| C021 / C023 / C024 | INTERFACES#3 | not-matched | 讲的是 recoverPromotion 回滚失败缺测试（INTERFACES#4 的缺陷），不是 failureCode 歧义 |
| C022 / C035 | INTERFACES#3、SEAMS#1 | 两用例都 not-matched | 讲的是 Adapter 接口缺 restore 失败合同，不是成功路径缺 recoveryState 形状 |
| C030 | MODULES#1 | matched | 明确指出 Readiness 与 Promotion 重复校验 |
| C034 | MD-RATIONALE#1 | not-matched | 见下方观察 |

- **C034 观察**：该 finding 说缺 Policy Evaluation Seam 与依赖方向理由（证据 `ar:27/51/67/68/71`），实际描述的是 MD-RATIONALE#3 的缺陷。但 MD-RATIONALE#3 的关联证据是 `ar:79`/`ar:55`，所以这个候选没有进入 MD-RATIONALE#3 的池。MD-RATIONALE#3 的 0/10 可能部分来自 placement 过窄。这一点未改分，列为 v3 键的待查项：给 MD-RATIONALE#3 加 `ar:51/67/68/71` 关联、并对全部批次重新池化盲裁后才能确认。

### 10 次分数
| 次 | 批 | 扣罚前 | 扣罚后 | 诊断数 | clean 接受率 |
|---|---|---|---|---|---|
| 1 | A | 0.575 | 0.575 | 0 | 0.981 |
| 2 | A | 0.623 | 0.560 | 1 | 0.962 |
| 3 | A | 0.701 | 0.631 | 1 | 0.981 |
| 4 | B | 0.499 | 0.449 | 3 | 0.981 |
| 5 | B | 0.668 | 0.601 | 1 | 1.000 |
| 6 | C | 0.547 | 0.547 | 0 | 1.000 |
| 7 | C | 0.494 | 0.444 | 4 | 0.981 |
| 8 | C | 0.406 | 0.366 | 1 | 0.887 |
| 9 | D | 0.671 | 0.604 | 1 | 0.981 |
| 10 | D | 0.755 | 0.680 | 1 | 1.000 |
| 均值 / SD | | 0.594 / 0.109 | 0.546 / 0.097 | | |

扣罚按每条诊断 ×0.9 计入每次；上表"扣罚后"一栏与 `score-completed` 输出一致。

### 离群
- **第 7 次（0.444）**：RM 越过停止点（requirement-scope-continuation），AP2 另有 3 条 review-evidence-invalid（JSONL 第 2、4、6 行，"Evidence does not identify body lines"）。
- **第 8 次（0.366）**：只有 1 条 review-evidence-invalid（AP3 第 3 行，同一信息）。低分主要来自 clean 接受率 0.887 和问题检出率 0.358，不是罚分。
- v2/v3 管线都没有运行 `tools/reviewer/repair_reviewer_report.py`。该工具只修 JSONL 标量 `lines`、Markdown 前言和只含文件的 locator，不覆盖"证据没有指到正文行"这类错误，因此判断它对上述诊断无效。**未实测验证。**

### 逐用例命中（Opus ×3 / Q3 前 5 次 / Q3 ×10，命中次数与均分）
| 用例 | Opus | Q3 ×5 | Q3 ×10 |
|---|---|---|---|
| SR-INPUTS#1 | 3/3 1.00 | 5/5 0.88 | 10/10 0.93 |
| SR-REQUIREMENTS#1 | 3/3 0.99 | 5/5 0.99 | 10/10 0.99 |
| SR-REQUIREMENTS#2 | 3/3 1.00 | 5/5 1.00 | 10/10 0.99 |
| SR-REQUIREMENTS#3 | 3/3 1.00 | 5/5 1.00 | 10/10 1.00 |
| SR-REQUIREMENTS#4 | 3/3 0.95 | 2/5 0.38 | 5/10 0.48 |
| SR-RATIONALE#1 | 3/3 1.00 | 5/5 0.98 | 9/10 0.88 |
| SR-ADR-EVALUATION#1 | 3/3 0.98 | 4/5 0.77 | 8/10 0.76 |
| MD-APPLICABILITY#1 | 3/3 0.99 | 3/5 0.58 | 7/10 0.68 |
| MD-EXEMPTION#1 | 3/3 1.00 | 5/5 0.95 | 10/10 0.95 |
| MD-MODULES#1 | 3/3 0.98 | 2/5 0.39 | 4/10 0.39 |
| MD-INTERFACES#1 | 1/3 0.31 | 2/5 0.36 | 3/10 0.28 |
| MD-INTERFACES#2 | 3/3 0.99 | 5/5 0.98 | 8/10 0.79 |
| MD-INTERFACES#3 | 3/3 0.95 | 1/5 0.19 | 3/10 0.29 |
| MD-INTERFACES#4 | 3/3 0.98 | 3/5 0.58 | 6/10 0.58 |
| MD-INTERFACES#5 | 0/3 | 0/5 | 0/10 |
| MD-INTERFACES#6 | 0/3 | 3/5 0.55 | 3/10 0.27 |
| MD-SEAMS-ADAPTERS#1 | 0/3 | 0/5 | 0/10 |
| MD-DEPS-DATA-FLOW#1 | 3/3 1.00 | 4/5 0.80 | 8/10 0.80 |
| MD-DEPS-DATA-FLOW#2 | 1/3 0.33 | 0/5 | 1/10 0.10 |
| MD-RATIONALE#1 | 3/3 1.00 | 5/5 0.99 | 8/10 0.79 |
| MD-RATIONALE#2 | 2/3 0.64 | 0/5 | 0/10 |
| MD-RATIONALE#3 | 0/3 | 0/5 | 0/10 |

### 残余 (a) 是否造成失分：没有
- 13 份 RM 报告（Opus 3、Q3 10）的 INPUTS、REQUIREMENTS clean 全部通过，没有一条 REQUIREMENTS finding 因残余 (a) 被判为误报。
- 只有 2 份报告提到 `promotion-runtime.md:11` 与 `:27` 的张力：Q3 第 2 次和第 10 次的 RM。两条都以 MODULES / DEPS 报出，属于越过停止点的 continuation 内容。这两份报告里还有多条其他 Module Design finding，所以去掉这一条也照样会触发 continuation 罚分。
- 引用 `access-review.md:15` 的只有批 C RM1 一条，内容是 INPUTS#1（缺 request-consistency Input），已正确匹配，与残余 (a) 无关。

### Opus DEPS#2 为何下降（v2 3/3 → v3 1/3）
- 命中的是 Opus AP1：它明确指出 Promotion Flow 没写由谁、何时调用 `readArtifact(path)`，以及读失败在哪一段产生。AP2、AP3 的 DEPS 只报了 DEPS#1（缺 Source/Authority 表）。全文也没有其他提到 Artifact Storage 读调用的 finding，所以没有候选进池，不是裁决问题，而是没报。
- v3 在这一带只改了 `promotion-runtime.md:11`（"Readiness 在调用 Promotion Persistence Interface 前确认 …"）。DEPS#2 的证据行 `:45/:51/:57/:79` 没改。改动可能让 Flow 看起来更完整、降低了这处缺口的显眼度，但 n=3 时 3/3 与 1/3 的差异没有统计意义，这只是推测，**未验证**。Q3 在 v2/v3 都几乎不命中（v3 为 1/10）。

### 收尾状态
- Spec v3 加测在 10:24 结束后，worker 用 `Controller`（`with c:`）领取租约，停止常驻模型后释放：`{'status': 'stopped', 'model': None}`，当时 strata.exe 已退出，租约空闲。
- 10:45 复查时 strata.exe 又在运行（PID 2764）。这是 Code Spec v2 worker 10:35 开跑的 Q3 批 A（`arw_measure --out .tmp/code-spec-v2/q3/batch-a/run`），属于它的租约，不是 Spec v3 遗留，worker 未干预。
- 引擎常驻问题在批 D 后再次出现（前端按设计跨租约保留模型，ARW provider 在批次之间不停引擎）。建议 `arw_measure` 每批开跑前显式停止模型，见上文"引擎常驻"一节。
