# 下载与恢复清单

rtx3080ti 已于 2026-11-03 安装 v0.2.10（Control 与 Qwen 引擎 0.1.56），见[升级报告](../reports/rtx3080ti/v0.2.10/upgrade.md)；前一版 v0.2.9 保留供回退（[升级报告](../reports/rtx3080ti/v0.2.9/upgrade.md)）。rtx4070tis 已于 2026-10-28 部署 v0.2.4（Qwen 引擎 0.1.48）；后续升级待办见[状态页](../.status/index.html)。单个不超过1GB的文件可由助手下载；超过1GB的模型等由用户下载，来源与校验由工程维护。以下链接供恢复及后续升级核对。`artifacts/` 只保留最新版和前一个版本（前一版用于无法修复时回退）；更早的版本只保留下面的来源、大小和 SHA，需要时重新下载核对（用户 2026-10-14）。

探索下载的候选模型、分词器和配套文件统一放工程`.tmp/`；仅在确认需要采用后才进入`artifacts/`。工程长期保留公共来源、固定版本、大小、SHA及必要结果，临时缓存位置不表示已采用或已部署；清空临时目录后重新下载／准备。此规则同时适用于助手和提供给用户的探索下载路径。

## Strata v0.2.10（rtx3080ti 已安装）

2026-11-03 核对官方发布，附注标签 `v0.2.10`（标签对象 `db0500a5`）指向提交 `ffa80d73133ea5c548aefe57889a16e8085a938f`，发布时间 2026-11-02T23:52Z。Control 与引擎同为 0.1.56（CMake `VERSION 0.1.56`，与引擎包一致，不需要 `source_cmake_version`）。同一发布的 `strata-dsv41-*` 包不用。由升级 worker 下载。

- 引擎：[strata-engine-0.1.56-windows-x86_64-cuda-cuda13.tar.gz](https://github.com/Niko1221/Strata/releases/download/v0.2.10/strata-engine-0.1.56-windows-x86_64-cuda-cuda13.tar.gz)，627806827 字节，官方 SHA256 `5336671c55bc1b819d076104608522147227001d1711378f35ea5d524bc866ec`，与 API digest 一致（build_id `06698c674673+cuda13.0`，源 `f-0291-rc1`，清单 SHA `978eca44…7de897`，安装后 970225121 字节）。
- feed：[strata-feed.json](https://github.com/Niko1221/Strata/releases/download/v0.2.10/strata-feed.json)，15552 字节，SHA256 `bb421243a4e36d9b2aff24f53f48226237cb7de5dde3287813eb3497a20f134d`（sequence 120），Ed25519 签名已用固定公钥 `5d1bc23abbeffd0d` 核验，引擎清单签名同样通过；feed 与 `.sig` 存于 `artifacts/strata/0.2.10/`。
- 源码：[标签 ZIP](https://github.com/Niko1221/Strata/archive/refs/tags/v0.2.10.zip)，36598440 字节，本地 SHA256 `f00cfe9a3d220328c7961e27992295c88371afa62d1e9d461000f449d8a60eb3`（顶层目录 `Strata-0.2.10/`，ZIP 注释为标签提交）。`AGENTS.md`（`83bb196c…cfafd`）只改版本行，`requirements.txt` 未变；0.2.9 有而本版没有的源码路径：无。
- 工程文件为 `artifacts/strata/0.2.10/engine.tar.gz` 和 `source.zip`，版本清单见[制品清单](../config/artifacts/strata-v0.2.10.json)，`strata-release.json` 已指向本版。2026-11-03 安装到 rtx3080ti 并通过短检查。rtx4070tis 仍是 v0.2.4，待同步。

## Strata v0.2.9（rtx3080ti 曾安装，回退用）

2026-11-02 核对官方发布，附注标签 `v0.2.9`（标签对象 `d94bac6a`）指向提交 `c62d5e3a15b40ea51c96aae9e8d36928965f53ab`，发布时间 2026-10-31T08:02Z。Control 与引擎同为 0.1.55（CMake `VERSION 0.1.55`，与引擎包一致，不需要 `source_cmake_version`）。同一发布的 `strata-dsv41-*` 包（422 MB，DeepSeek）不用。由升级 worker 下载。

- 引擎：[strata-engine-0.1.55-windows-x86_64-cuda-cuda13.tar.gz](https://github.com/Niko1221/Strata/releases/download/v0.2.9/strata-engine-0.1.55-windows-x86_64-cuda-cuda13.tar.gz)，621585315 字节，官方 SHA256 `34f399a0a22e4af8b434439de04dcce3734ccba7e884ef6003439ba148d667df`，与 API digest 一致（build_id `99866a47a2b8+cuda13.0`，源 `f-029-rel`，清单 SHA `84271f6e…b98d`，安装后 949389792 字节）。
- feed：[strata-feed.json](https://github.com/Niko1221/Strata/releases/download/v0.2.9/strata-feed.json)，15491 字节，SHA256 `05cc1b2287e69fd1627cfdf5feacdb2708fcdd46f9a5b9c77fe6bdb592ba4014`（sequence 118），Ed25519 签名已用固定公钥 `5d1bc23abbeffd0d` 核验，引擎清单签名同样通过；feed 与 `.sig` 存于 `artifacts/strata/0.2.9/`。
- 源码：[标签 ZIP](https://github.com/Niko1221/Strata/archive/refs/tags/v0.2.9.zip)，34878231 字节，本地 SHA256 `4c5f3c00ee6a1e28ff17c46f43ca6f8aaeebbc224ad2f4e812b9ac0dafd51e6f`（顶层目录 `Strata-0.2.9/`，ZIP 注释为标签提交）。`AGENTS.md`（`ba70683a…7a69`，文档改写）有变化，`requirements.txt` 未变；0.2.4 有而本版没有的源码路径：无。
- 工程文件为 `artifacts/strata/0.2.9/engine.tar.gz` 和 `source.zip`，版本清单见[制品清单](../config/artifacts/strata-v0.2.9.json)，`strata-release.json` 已指向本版。2026-11-02 安装到 rtx3080ti 并通过短检查。`artifacts/strata/0.2.2/` 已删除（只保留最新版和前一版）。rtx4070tis 仍是 v0.2.4，待同步。

## Strata v0.2.4（rtx3080ti 曾安装，回退用）

2026-10-24 核对官方发布，附注标签 `v0.2.4`（标签对象 `0303f658`，标签时间 02:14Z）指向提交 `96ca4383c7b05a8a3e6064c65d9e9977d4b3bb59`。发布页之后更新为 Terminal 0.2.4.1／Control 0.1.49.1（DeepSeek 准备脚本补丁，main 上 `c33fa7ba`），标签未移动，我们装的是标签内容。DeepSeek V4.1-Flash 的 `strata-dsv41-*` 包只用于 Terminal，不安装。由升级 worker 下载。

- 引擎：[strata-engine-0.1.48-windows-x86_64-cuda-cuda13.tar.gz](https://github.com/Niko1221/Strata/releases/download/v0.2.4/strata-engine-0.1.48-windows-x86_64-cuda-cuda13.tar.gz)，581299508 字节，官方 SHA256 `1e1611b0977d984bd7d8e79591a1ba1a7e550a2f4a66bfa45744a77308a71b95`，与 API digest 一致，是 0.2.3 的同一文件（build_id `6f8800aefe27+cuda13.0`，源 `f-023-rel`）。包内 7 个文件：`strata.exe`、`strata_kq.dll`、`strata-vision.exe`、`cublas64_13.dll`、`cublasLt64_13.dll`、`BUILD.json`、`engine-component.json`；清单 SHA `17670345…1a6f`，两个 cublas DLL 与 0.2.2 相同故未重写。
- feed：[strata-feed.json](https://github.com/Niko1221/Strata/releases/download/v0.2.4/strata-feed.json)，14242 字节，SHA256 `9ece054762f0a4f55f252a733ddbe15f718ca8ca6a664b5faf454fc37ba012b8`，Ed25519 签名已用固定公钥 `5d1bc23abbeffd0d` 核验，引擎清单签名同样通过；feed 与 `.sig` 存于 `artifacts/strata/0.2.4/`。
- 源码：[标签 ZIP](https://github.com/Niko1221/Strata/archive/refs/tags/v0.2.4.zip)，33002954 字节，本地 SHA256 `d543da4aa06cb548ed177b8e96353112ee06b45c0d57a5fb9c4beee3ea3d8f0a`（顶层目录 `Strata-0.2.4/`，ZIP 注释为标签提交）。CMake 版本是 0.1.49（DeepSeek 引擎），引擎包是 0.1.48，`upgrade_release` 的元数据用 `source_cmake_version` 明确绑定。`AGENTS.md`（`685edaa9…03bb5`，只改版本行）和 `requirements.txt`（`517d23bc…6506`，certifi 2026.10.19、新增 truststore 0.10.5）有变化；0.2.2 有而本版没有的源码路径：无。
- 工程文件为 `artifacts/strata/0.2.4/engine.tar.gz` 和 `source.zip`，版本清单见[制品清单](../config/artifacts/strata-v0.2.4.json)，`strata-release.json` 已指向本版。2026-10-24 安装到 rtx3080ti 并通过短检查。2026-11-03 升级到 v0.2.10 后本地文件已删除。

## Strata v0.2.2（rtx3080ti 曾安装，回退用）

2026-10-22 核对官方发布，附注标签 `v0.2.2`（标签对象 `e6fff4ad`）指向提交 `011c9e600a93bbc9fd451c563501b5831c32bbca`。从 0.2.0 起发布版本与引擎版本分开：发布 0.2.2，引擎 0.1.47（CMake `VERSION 0.1.47`，build_id `76f90e58436d+cuda13.0`）。由升级 worker 下载。

- 引擎：[strata-engine-0.1.47-windows-x86_64-cuda-cuda13.tar.gz](https://github.com/Niko1221/Strata/releases/download/v0.2.2/strata-engine-0.1.47-windows-x86_64-cuda-cuda13.tar.gz)，580428476 字节，官方 SHA256 `59833d875b2f3807791533f5dd077a0cb0ed08d4c1cab3136ad2ceb165871cd1`，与 API digest、`SHA256SUMS.txt` 和 [strata-feed.json](https://github.com/Niko1221/Strata/releases/download/v0.2.2/strata-feed.json)（11744 字节，SHA256 `fbf4acaa462f8010f8280425b96ed4ed9825ac428828b4d6de74f1d28f9d3a18`，Ed25519 签名已用固定公钥 `5d1bc23abbeffd0d` 核验，引擎清单签名同样通过；feed 与 `.sig` 存于 `artifacts/strata/0.2.2/`）一致。包内无顶层目录，7 个普通文件：`strata.exe`、`strata_kq.dll`、`strata-vision.exe`、`cublas64_13.dll`、`cublasLt64_13.dll`、`BUILD.json`、`engine-component.json`；清单 SHA `95eb1eef404859e3afae56811cccb3da27bbab6b589e276fe4e4e701dfbe9427` 等于 feed 的 `manifest_sha256`，逐文件大小和 SHA 与清单一致，合计 876210108 字节。不含 cudart DLL（feed 备注写 "cudart and cublas bundled"，实际只带 cublas/cublasLt）。同一发布的 cuda12（experimental）、hip 引擎包，以及 app 安装程序（`.exe`）和 Terminal（`install.ps1`）都不用：后两者另建 `%LOCALAPPDATA%\Strata`、Documents 等目录并改 PATH。
- 源码：[标签 ZIP](https://github.com/Niko1221/Strata/archive/refs/tags/v0.2.2.zip)，31785221 字节，本地 SHA256 `8dbfa60f9c013e28a3f1ce578cbdac79f2cb442b40d590b526753765d027a54b`（顶层目录 `Strata-0.2.2/`，ZIP 注释为标签提交；GitHub 归档没有官方摘要）。`AGENTS.md`（SHA256 `15194f49…de58`）和 `requirements.txt`（`d30c7dd2…a314`，只把 cmake、ninja 移到 `requirements-build.txt`）有变化；0.1.45 有而本版没有的源码路径只有 `docker-entrypoint.sh`。
- 工程文件为 `artifacts/strata/0.2.2/engine.tar.gz` 和 `artifacts/strata/0.2.2/source.zip`，版本清单见[制品清单](../config/artifacts/strata-v0.2.2.json)，`strata-release.json` 已指向本版。2026-10-22 安装到 rtx3080ti 并通过短检查。

## Strata v0.1.45（rtx3080ti 曾安装）

2026-10-18 核对官方最新发布，标签提交 `477ac13cbe8e582c20484871ce459d20d82df09d`（附注标签对象 `b39442e6`）。由升级 worker 下载。

- 引擎：[strata-windows-x64.zip](https://github.com/Niko1221/Strata/releases/download/v0.1.45/strata-windows-x64.zip)，165243142 字节，官方 SHA256 `a1d4cafb8319c253f3010ff118dbd5ed07c232056b939ac7735819559f3b859e`，已核对一致（发布附带的 SHA256.txt 与 API digest）。包内仍是 `strata.exe`、`strata_kq.dll`、`strata-vision.exe`、`BUILD.json`。同一发布的 `-cuda12` 和 `-hip` 包不用。
- 源码：[标签 ZIP](https://github.com/Niko1221/Strata/archive/refs/tags/v0.1.45.zip)，23208999 字节，本地 SHA256 `8d90ac92dae659390783a6c9da20bd4204cbfa0349f45fcbedb690c41495c17f`（顶层目录 `Strata-0.1.45/`，ZIP 注释为标签提交；GitHub 归档没有官方摘要）。
- 曾采用：工程文件 `artifacts/strata/0.1.45/` 已于 2026-10-24 删除（只保留最新版和前一版），版本清单见[制品清单](../config/artifacts/strata-v0.1.45.json)；需要时按上面的链接重新下载并核对 SHA。

## Strata v0.1.44.1（rtx3080ti 曾安装）

2026-10-14 核对官方最新发布，标签提交 `296b59d2f73c8f04a805df29c2fa97655adace78`。外网约 640KB/s，由 Main 下载。

- 引擎：[strata-windows-x64.zip](https://github.com/Niko1221/Strata/releases/download/v0.1.44.1/strata-windows-x64.zip)，155480443 字节，官方 SHA256 `a29bda047f440e6d2ce1649306c3a7047ba35df5a032097c7509d4494fa2b448`，已核对一致。包内新增 `strata_kq.dll`（K-quant 预填核，只在模型含这些格式时加载）。同一发布的 `-cuda12` 和 `-hip` 包不用。
- 源码：[标签 ZIP](https://github.com/Niko1221/Strata/archive/refs/tags/v0.1.44.1.zip)，22629639 字节，本地 SHA256 `22be94124b4d37dc2ff76e742c49498a3e5f31873ed916a636b2a31707d09b31`（顶层目录 `Strata-0.1.44.1/`，ZIP 注释为标签提交；GitHub 归档没有官方摘要）。
- 曾采用：工程文件 `artifacts/strata/0.1.44.1/` 已于 2026-10-24 删除（只保留最新版和前一版），版本清单见[制品清单](../config/artifacts/strata-v0.1.44.1.json)；需要时按上面的链接重新下载并核对 SHA。

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
