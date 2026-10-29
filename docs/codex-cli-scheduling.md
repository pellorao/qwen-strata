# Codex CLI 定时唤醒

本规则只适用于 Codex CLI。CLI 没有 Scheduled 管理界面，也不能在退出后由定时器重新启动；因此定时器只向**仍打开的现有会话**排队消息，不调用 `codex exec` 或 `codex resume`。

## 规则

- 用户保持 Codex CLI/TUI 常开。关闭 CLI 后，不恢复会话、不补跑错过的时间。
- 会话 UUID 取 `$CODEX_THREAD_ID`。所有操作使用完整 UUID，不使用可能重名的会话名。
- 定时器只执行 `codex queue --thread <UUID> --message <文本>`。queue 的消息在当前回合结束后成为下一回合，不会 steer 或打断忙碌中的 Main。
- 定时检查只在 Main 空闲时处理。到点唤醒后，检查指定任务或 subagent：仍在运行就安排下一次检查后结束回合；已经完成就汇总并停止；任务已不存在就不重建定时器。
- systemd timer 是用外部时钟触发消息；Codex 会话仍由原 CLI 进程持有。timer 不是新的 Codex 会话。
- Codex CLI 正常关闭时，`SessionEnd` hook 删除该 UUID 的全部 timer。强杀、崩溃和断电可能跳过 hook；下一次 timer 触发时如果 `codex queue` 失败，timer 自删。需要“强制终止也立即清理”时必须让 CLI 本身由外部 supervisor 运行，本项目不采用这种启动方式。

## 安装清理 hook

仓库模板见 [codex-cli-scheduling-hooks.json](codex-cli-scheduling-hooks.json)。将它合并到仓库的 `.codex/hooks.json`，再在 Codex CLI 运行 `/hooks` 审查并信任该 hook。项目 `.codex/` 层必须受信任，否则清理 hook 不会运行。

SessionEnd 使用 3 秒上限，因此清理命令只停止 `codex-timer-<session-tag>-*.timer`。systemd 的 transient timer 停止后自行卸载，不需要再删除文件。

## 安排任务

从工程根运行：

```bash
session_id="${CODEX_THREAD_ID:?CODEX_THREAD_ID is required}"
```

二十分钟后检查一次：

```bash
scripts/wsl/codex-timers schedule \
  --session-id "$session_id" \
  --seconds 1200 \
  --message "定时检查：只读状态页和指定任务；subagent 仍在运行则安排下一次检查后结束，完成则汇总并停止。"
```

指定时刻检查一次：

```bash
scripts/wsl/codex-timers schedule \
  --session-id "$session_id" \
  --at "2026-10-30 11:13:00" \
  --message "定时检查：执行 2026-10-30 的每日检查。"
```

每二十分钟周期检查：

```bash
scripts/wsl/codex-timers schedule \
  --session-id "$session_id" \
  --every "*-*-* *:00/20:00" \
  --message "定时检查：只读状态页和指定任务；subagent 仍在运行则等待下一次检查，完成则汇总并停止。"
```

列出和手动清理：

```bash
scripts/wsl/codex-timers list --session-id "$session_id"
scripts/wsl/codex-timers cleanup --session-id "$session_id"
```

## 首次验收

安装 hook 后先做一个短测试，不能直接依赖未验证的唤醒：

1. 用 `--seconds 60` 安排一条无副作用检查。
2. 回到空闲的 CLI；到点后确认收到新的 Codex 回合，且不是当前回合被打断。
3. 关闭 CLI，在独立 shell 中重新运行同一 UUID 的 `list`；结果应为空。
4. 如有残留，检查 `/hooks` 是否已信任当前 hook 版本，并手动运行 `cleanup` 保留现场。

## 边界

- 官方说明 Codex CLI 没有 Scheduled 管理界面：[Scheduled tasks](https://learn.chatgpt.com/docs/automations)。
- `queue` 面向已有 session：[Codex CLI reference](https://learn.chatgpt.com/docs/cli/reference)。
- SessionEnd 在 CLI 正常关闭、归档/删除，或会话空闲且没有已连接客户端 30 分钟后运行；强杀不在保证内：[Hooks](https://learn.chatgpt.com/docs/hooks)。
