# 下载与恢复清单

rtx3080ti 已于 2026-10-18 安装 v0.1.45，见[升级报告](../reports/v0.1.45/upgrade.md)；rtx4070tis 离线，仍为 v0.1.40.2，恢复后待同步。单个不超过200MB的文件可由助手下载；超过200MB的模型等由用户下载，来源与校验由工程维护。以下链接供恢复及后续升级核对。`artifacts/` 只保留最新版和前一个版本（前一版用于无法修复时回退）；更早的版本只保留下面的来源、大小和 SHA，需要时重新下载核对（用户 2026-10-14）。

探索下载的候选模型、分词器和配套文件统一放工程`.tmp/`；仅在确认需要采用后才进入`artifacts/`。工程长期保留公共来源、固定版本、大小、SHA及必要结果，临时缓存位置不表示已采用或已部署；清空临时目录后重新下载／准备。此规则同时适用于助手和提供给用户的探索下载路径。

## Strata v0.1.45（rtx3080ti 已安装）

2026-10-18 核对官方最新发布，标签提交 `477ac13cbe8e582c20484871ce459d20d82df09d`（附注标签对象 `b39442e6`）。由升级 worker 下载。

- 引擎：[strata-windows-x64.zip](https://github.com/Niko1221/Strata/releases/download/v0.1.45/strata-windows-x64.zip)，165243142 字节，官方 SHA256 `a1d4cafb8319c253f3010ff118dbd5ed07c232056b939ac7735819559f3b859e`，已核对一致（发布附带的 SHA256.txt 与 API digest）。包内仍是 `strata.exe`、`strata_kq.dll`、`strata-vision.exe`、`BUILD.json`。同一发布的 `-cuda12` 和 `-hip` 包不用。
- 源码：[标签 ZIP](https://github.com/Niko1221/Strata/archive/refs/tags/v0.1.45.zip)，23208999 字节，本地 SHA256 `8d90ac92dae659390783a6c9da20bd4204cbfa0349f45fcbedb690c41495c17f`（顶层目录 `Strata-0.1.45/`，ZIP 注释为标签提交；GitHub 归档没有官方摘要）。
- 已采用：工程文件为 `artifacts/strata/0.1.45/engine.zip` 和 `artifacts/strata/0.1.45/source.zip`，版本清单见[制品清单](../config/artifacts/strata-v0.1.45.json)，`strata-release.json` 已指向本版。v0.1.44.1 的制品保留在 `artifacts/strata/0.1.44.1/`，供回退。

## Strata v0.1.44.1（rtx3080ti 曾安装）

2026-10-14 核对官方最新发布，标签提交 `296b59d2f73c8f04a805df29c2fa97655adace78`。外网约 640KB/s，由 Main 下载。

- 引擎：[strata-windows-x64.zip](https://github.com/Niko1221/Strata/releases/download/v0.1.44.1/strata-windows-x64.zip)，155480443 字节，官方 SHA256 `a29bda047f440e6d2ce1649306c3a7047ba35df5a032097c7509d4494fa2b448`，已核对一致。包内新增 `strata_kq.dll`（K-quant 预填核，只在模型含这些格式时加载）。同一发布的 `-cuda12` 和 `-hip` 包不用。
- 源码：[标签 ZIP](https://github.com/Niko1221/Strata/archive/refs/tags/v0.1.44.1.zip)，22629639 字节，本地 SHA256 `22be94124b4d37dc2ff76e742c49498a3e5f31873ed916a636b2a31707d09b31`（顶层目录 `Strata-0.1.44.1/`，ZIP 注释为标签提交；GitHub 归档没有官方摘要）。
- 已采用：工程文件为 `artifacts/strata/0.1.44.1/engine.zip` 和 `artifacts/strata/0.1.44.1/source.zip`，版本清单见[制品清单](../config/artifacts/strata-v0.1.44.1.json)，2026-10-18 起由 v0.1.45 取代，制品保留供回退。

## Strata v0.1.43.1（rtx3080ti 曾安装）

2026-10-13 核对官方最新发布，标签提交 `a0116b2782a5b82622358c04a06496485d12b2d6`。当时外网只有几 KB/s，两个文件由用户下载，Main 核对后采用。

- 引擎：[strata-windows-x64.zip](https://github.com/Niko1221/Strata/releases/download/v0.1.43.1/strata-windows-x64.zip)，138187009 字节，官方 SHA256 `38b5f1116bcd76554dd46f5344a6d0f5aa428f02e49db64a7d8e2137356e93d0`，已核对一致。同一发布的 `-cuda12`（约 200MB）和 `-hip`（约 629MB）包不用。
- 源码：[标签 ZIP](https://github.com/Niko1221/Strata/archive/refs/tags/v0.1.43.1.zip)，21786355 字节，本地 SHA256 `9e37f07e87473210ac98ee6041e6651c02e1c473bf75eae65191840fa2b80768`（顶层目录 `Strata-0.1.43.1/`，ZIP 注释为标签提交；GitHub 归档没有官方摘要）。
- 曾采用：工程文件 `artifacts/strata/0.1.43.1/` 已于 2026-10-18 删除（只保留最新版和前一版），版本清单见[制品清单](../config/artifacts/strata-v0.1.43.1.json)；需要时按上面的链接重新下载并核对 SHA。

## Strata v0.1.41（rtx3080ti 曾安装）

2026-10-10 核对官方最新发布，标签提交 `fb58e0dbc8399662c0e47c76578c6e878b14f6cf`。

- 引擎：[strata-windows-x64.zip](https://github.com/Niko1221/Strata/releases/download/v0.1.41/strata-windows-x64.zip)，137164559 字节，官方 SHA256 `3dd7715f4844c0f9d2f28eb5067af0198f386df060c93523cd17e1d65b757f13`，下载后已核对一致。
- 源码：[提交 ZIP](https://github.com/Niko1221/Strata/archive/fb58e0dbc8399662c0e47c76578c6e878b14f6cf.zip)，19149640 字节，本地 SHA256 `b6b559866cf7d422d7acace638d542049ea7e3543720f574cb97b2d0bd530d7b`（GitHub 归档没有官方摘要）。
- 曾采用：工程文件 `artifacts/strata/0.1.41/` 已于 2026-10-14 删除（只保留最新版和前一版），版本清单见[制品清单](../config/artifacts/strata-v0.1.41.json)；需要时按上面的链接重新下载并核对 SHA。

## Strata v0.1.40下载记录

已核对2026-10-06官方最新发布及标签提交`1735d6471df29b42c26170efaac1f1446a58640f`。rtx4070tis继续使用标准Windows NVIDIA包，不选择HIP或旧GPU的CUDA12包。

- 下载：[strata-windows-x64.zip](https://github.com/Niko1221/Strata/releases/download/v0.1.40/strata-windows-x64.zip)。
- 大小：131707082字节，约131.7MB／125.6MiB，在助手200MB下载上限以内。
- 当时由助手下载，临时副本已清理；需要恢复时按上面的链接重新下载并核对 SHA。
- 官方SHA256：`cd264b2125fdb85e84a8264da2ab2343463e6c7f9a12f317d4ce7192cd2c6b33`。
- [官方发布页](https://github.com/Niko1221/Strata/releases/tag/v0.1.40)；已完成的长期升级结果见[升级报告](../reports/v0.1.40/upgrade.md)。

已核对大小、官方SHA、ZIP CRC、构建版本及sm_89，并通过维护独占及启动互斥完成安装；模型未启动，维护key已归还。完整结果见[安装记录](../reports/v0.1.40/installation.json)。

## 历史Strata v0.1.38

| 文件 | 地址 |
|---|---|
| 固定源码 | [commit ZIP](https://github.com/Niko1221/Strata/archive/99f3dbd0b21d1401b3769e0c0d963913607f380b.zip) |
| 官方 Windows NVIDIA 引擎 | [strata-windows-x64.zip](https://github.com/Niko1221/Strata/releases/download/v0.1.38/strata-windows-x64.zip) |
| 发布说明 | [v0.1.38](https://github.com/Niko1221/Strata/releases/tag/v0.1.38) |

引擎 ZIP 124279645 字节，官方 SHA256 `78b532bca27af1421ccd1aace6d41869df34d019d619f5426a78dbf01c1f53bf` 已校验。固定源包约13.6MB由助手下载；引擎由用户下载。ZIP CRC、版本和部署回读通过，requirements 与上一版相同，无需重下载依赖。备份及逐文件摘要见 [v0.1.38 安装记录](../reports/v0.1.38/installation.json)。

## GGUF 模型

固定 revision `ed59f92082b1e93c0e96d60a8b11aab089b52f09`。已有 Q2_0、IQ2_XS 各两个分片，必须都保留；本地 SHA 记录在 [长期完整性统计](../reports/v0.1.36/integrity.json)。四个分片先前的整文件SHA256现已与固定revision的公开LFS SHA256全部匹配，当前大小一致，实际加载和200K运行均通过。见[上游完整性](../reports/v0.1.36/integrity.json)。

- [Q2_0 两个分片页面](https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF/tree/ed59f92082b1e93c0e96d60a8b11aab089b52f09/Q2_0)
- [IQ2_XS 两个分片页面](https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF/tree/ed59f92082b1e93c0e96d60a8b11aab089b52f09/IQ2_XS)

量化恢复链接与未安装候选：

- [IQ3_XXS 页面](https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF/tree/ed59f92082b1e93c0e96d60a8b11aab089b52f09/IQ3_XXS)
- [IQ3_S 页面](https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF/tree/ed59f92082b1e93c0e96d60a8b11aab089b52f09/IQ3_S)

IQ3_XXS已下载、安装和基础验收；链接供恢复，并非当前待下载。IQ3_S未安装，不是当前运行必需，也未获新增下载安排；它对64GB RAM余量压力更大。见[模型资源与取舍](tuning.md#模型量化)。

## MTP 与依赖

- [BF16 固定 checkpoint 页面](https://huggingface.co/Qwen/Qwen3.8-Flash-Next/tree/de4b8e4d43b917e7706784d8bb445c9af86a3540)：MTP 是其中 31 张量，共约 5.214 GB，不需要整个 BF16 checkpoint。已下载原始张量并与固定上游 SHA256 全部匹配；已生成并使用 draft pack/runtime。临时解析后签名地址脚本已删除。
- [固定 llama.cpp 源码](https://github.com/ggml-org/llama.cpp/archive/3cf03257f219afbe7334045ff7c6a06ac68c627d.zip)：恢复相关辅助工具，当前无需重编译。
- [Strata requirements](https://github.com/Niko1221/Strata/blob/36fa455e579b23a9c909c2c6fe1bddd9e51cb8ca/requirements.txt)：18 个离线 wheel 已安装且 pip check 通过，精确文件名和 URL 见 [wheel manifest](../reports/v0.1.37/installation/dependencies.json)。
- [CUDA cuBLAS 13.0.2.14 wheels](https://pypi.org/project/nvidia-cublas/13.0.2.14/#files)、[CUDA runtime 13.0.96 wheels](https://pypi.org/project/nvidia-cuda-runtime/13.0.96/#files)：已包含在本地离线依赖中。

当前使用 `C:\Python314\python.exe` 3.14.7 创建的私有 venv，无需额外安装 Python 3.12。CUDA Toolkit 和 VS Build Tools 的rtx4070tis编译对照已结束，后续只使用预编译引擎；无需为运行再次下载编译工具。


四个GGUF的上游校验已完成：先前下载后计算的整文件SHA256，与新获取的固定revision公开LFS SHA256全部一致，当前文件大小也一致。仅获取元数据，没有下载模型。初始preparation-manifest的“未上游对照”是当时状态，当前以gguf-upstream-integrity.json补充证据为准；不篡改旧阶段原始报告。

IQ3_XXS第一片47,039,860,096字节，约43.81GiB；第二片28,800,138,432字节，与已安装的对应分片上游LFS SHA一致，完整校验后按预期名称硬链接复用。这里不包含未安装IQ3_S的第一片大小；资源测量见[调优记录](tuning.md)。


历史 IQ3 下载记录（已完成）：[固定revision下载](https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF/resolve/ed59f92082b1e93c0e96d60a8b11aab089b52f09/IQ3_XXS/Qwen3.8-Flash-Next-GSQ-RCO-IQ3_XXS-00001-of-00002.gguf?download=true)。约43.81GiB。用户已下载并通过验收。第2片复用已校验的同内容分片；源码/引擎/MTP不新增下载。

## 已准备的v0.1.40.2升级制品

rtx4070tisIQ3对照运行期间，已提前下载并校验[官方v0.1.40.2](https://github.com/Niko1221/Strata/releases/tag/v0.1.40.2)制品；量化对照完整收尾后已完成双机安装与快速验证，见[升级报告](../reports/v0.1.40.2/upgrade.md)。版本清单见[工程版本清单](../config/artifacts/strata-v0.1.40.2.json)，当前已安装来源由`strata-release.json`指向本版制品维护。

- [NVIDIA CUDA13.0引擎](https://github.com/Niko1221/Strata/releases/download/v0.1.40.2/strata-windows-x64.zip)：135,496,886字节，SHA256 `02901f0cd0691ab33ec827e354ffa72e1ab4f19a093f0280c6deb7327b26eb30`，与官方asset digest一致。工程文件为`artifacts/strata/0.1.40.2/engine.zip`；BUILD确认包含86／89架构，覆盖两台GPU。
- [固定提交源码](https://codeload.github.com/Niko1221/Strata/zip/e8ca9afd03d839d4f8dbbe82dffce7f8a3bafd7a)：18,736,860字节，下载后SHA256 `9e5a8086fc1869c6a23859bd9d06e93d91adbc066b54c4239f84a70f791e4480`，工程文件为`artifacts/strata/0.1.40.2/source.zip`。源码SHA用于本次下载完整性绑定，不称为官方签名。

两个ZIP的CRC／成员、固定提交及版本已核对；上游AGENTS与requirements逐字保持，未新增依赖。下载验证不替代安装回读或真实快速检查。
