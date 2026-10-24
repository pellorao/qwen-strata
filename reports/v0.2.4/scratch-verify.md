# Codex 私有 scratch 补丁验证（2026-10-24）

worker（Opus high）报告，Main 整理存档。提交 4c212c6，已合入 master。

## 结论

补丁现在可以启用，四项本地问题已解决并验证；没有发现可被利用的越权。

1. **bwrap 占位登记目录：安全，出错时只影响本实例。**
   - Codex 0.164.0 把登记目录随 TMPDIR 放进 scratch，但在沙箱内是 ro-bind：写入、rmdir、rename、unlink、rmtree 全部被拒；在宿主上预置成符号链接时，Codex 直接 panic，命令不运行。
   - 最坏只是本实例的命令跑不了。
   - safety_gate 新增登记目录防篡改探针，零模型门已通过。
   - 注意：multi-model-v1 plan 第 573 行写"模型能改它"，在 0.164.0 上不成立。该计划已冻结，没有改。
2. **从暂停恢复拿不到 scratch：已修。**
   - 冷恢复入口 `restorePausedTask` 用原始交接设置重开线程，丢掉了权限 profile、scratch、TMPDIR 和凭据 deny-read。
   - `tools/reviewer/arw_native_setup.mjs` 新增 `reviewerResumeOpen`：补回与首段相同的设置。
   - 登记为 ARW 上游缺陷 F。
3. **inspect_session 识别 scratch：已修。** 本实例 scratch 内的读写不再标成出根；兄弟实例 scratch、/tmp 等仍照常标出。已在 sampling-dim 的真实会话上验证。
4. **清理步骤：已就位。** `tools/tuning/arw_blocks.py` 已调用 `reviewer_scratch --remove`；v1 归档 runner 未改。

## 未验证

- 恢复修法只有单测，没有跑真实的运行时重启或 `--resume` 全链路。
- 登记目录探针只在 Codex 0.164.0 上验证过。
