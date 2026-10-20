"""Action-centred inspection view of one closed native Codex reviewer session, or of one
headless Claude Code run (stream-json, tools.reviewer.claude_headless).

Programs extract and classify; Main reads every action line and decides.
Reasoning, metadata and outputs of calls whose targets stay inside the
scenario root are not routine reading: a tool call is the only way a reviewer
reaches any source, so a call confined to the root can only observe the root.
Flagged calls get their full command and output in flagged.md. The original
session is only read, never copied or changed.
"""
import argparse
from datetime import datetime
import hashlib
import json
import os
import re
from pathlib import Path

# Executables and devices that are not observation sources
SYSTEM_PATHS = ('/usr/bin/', '/bin/', '/usr/local/bin/', '/dev/null', '/dev/stdin',
                '/dev/stdout', '/dev/stderr', '/usr/bin/env')
KNOWN_TOOLS = {'exec_command', 'write_stdin', 'apply_patch', 'view_image', 'update_plan', 'exec'}
# Code-mode models (0.163.0 code_mode_only) call every tool from JavaScript inside `exec`; what actually ran is in the
# item_completed CommandExecution / FileChange events, checked as their own actions (benchmark §14.3 M6, 2026-10-20).
CODE_MODE_ITEMS = ('CommandExecution', 'FileChange')
LINE_CHARS = 300          # command text shown per action line
FLAGGED_OUTPUT_CHARS = 6000
ABS_PATH = re.compile(r'(?:^|(?<=[\s\'"=(:,<>]))(/[\w.@+~-]+(?:/[\w.@+~-]*)*)')
DOTDOT = re.compile(r'(?:^|(?<=[\s\'"=(:,<>]))((?:[\w@+-][\w.@+-]*/)*\.\.(?=/|$|[\s\'"])(?:/[\w.@+-]*)*)')
SHELL_VAR = re.compile(r'(?<![\\\w])\$([A-Za-z_]\w*)')
RISKY = [
    (re.compile(r'(?:^|[;&|`]|\$\()\s*(env|printenv|set|whoami|hostname|uname|id|ps|nvidia-smi)(?:\s|$|[;&|)])', re.M),
     'environment/identity query'),
    (re.compile(r'process\.env|os\.environ|getenv\(|\$\{?HOME\b|(?:^|\s)~/|/proc/'), 'environment or home path'),
    (re.compile(r'\b(curl|wget|ssh|scp|nc)\b|https?://'), 'network'),
    (re.compile(r'sessions/|rollout-|codex-home|/\.state\b|private\.toml|auth\.json|\.credentials\.json', re.I),
     'session/credential material'),
]
# Credential-shaped values are masked in everything written, so the extracted view can go to a cheaper model
# without carrying a token a run happened to see (a linked ChatGPT login, a provider key; benchmark 2026-10-19).
SECRETS = [
    re.compile(r'eyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]*'),                       # JWT
    re.compile(r'(?i)(bearer\s+)[\w.~+/=-]{12,}'),
    re.compile(r'\bsk-[\w-]{16,}'),
    # JSON, Python-repr and escaped-in-a-string spellings: "k": "v", 'k': 'v', \"k\": \"v\"
    re.compile(r"""(?i)(\\?["'](?:access_token|refresh_token|id_token|api_key|OPENAI_API_KEY|auth_token)\\?["']\s*:\s*\\?["'])"""
               r"""[^"'\\]{8,}(\\?["'])"""),
    re.compile(r'(?i)\b((?:ANTHROPIC_AUTH_TOKEN|[A-Z_]*API_KEY|[A-Z_]*PASSWORD)=)\S{8,}'),
]
DENIED = re.compile(r'sandbox denied|Operation not permitted|Permission denied|EPERM|EACCES|CreateProcess', re.I)
UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
# Startup text that differs per instance by design: the run date and the
# per-instance Codex home holding the platform skills
DATE = re.compile(r'\b\d{4}-\d{2}-\d{2}\b')
CODEX_HOME = re.compile(r'\S*/codex-home/')
# Codex's per-process arg0 helper directory (mkdtemp suffix) named in the permission profile (2026-10-20)
ARG0 = re.compile(r'codex-arg0[A-Za-z0-9]{6}\b')


def inside(path, root):
    path = os.path.normpath(path)
    return path == root or path.startswith(root + '/')


def path_reasons(text, workdir, root, allow):
    reasons = []
    for p in ABS_PATH.findall(text):
        # '/x' whose top level does not exist is a fragment joined to a
        # variable (ROOT + '/reports', "$R/_spec.md"); the variable is checked
        if not os.path.exists('/' + p.split('/')[1]):
            continue
        if not (inside(p, root) or any(inside(p, a) for a in allow)
                or p.startswith(SYSTEM_PATHS)):
            reasons.append(f'outside root: {p}')
    # a merged Spec Readiness thread moves to a second scenario root, passed with --allow
    home = next((r for r in (root, *allow) if inside(workdir, r)), root)
    for p in DOTDOT.findall(text):
        if not inside(os.path.join(workdir, p), home):
            reasons.append(f'.. escapes root: {p}')
    assigned = set(re.findall(r'(?:^|[\s;&|(])(?:export\s+|local\s+)?([A-Za-z_]\w*)=', text, re.M))
    assigned |= set(re.findall(r'\bfor\s+([A-Za-z_]\w*)\s+in\b', text))
    assigned |= set(re.findall(r'\bread\s+(?:-\w+\s+)*([A-Za-z_]\w*)', text))
    assigned |= set(re.findall(r'--(?:arg|argjson)\s+([A-Za-z_]\w*)', text))  # jq variables
    for v in sorted(set(SHELL_VAR.findall(text)) - assigned):
        reasons.append(f'unassigned variable: ${v}')
    return reasons


def call_text(p):
    if p.get('type') == 'custom_tool_call':
        return p.get('input', ''), None
    try:
        a = json.loads(p.get('arguments') or '{}')
    except ValueError:
        return p.get('arguments', ''), None
    text = a.get('cmd') or a.get('command') or a.get('path') or a.get('chars') or json.dumps(a, ensure_ascii=False)
    if isinstance(text, list):
        text = ' '.join(map(str, text))
    return text, a.get('workdir')


def patch_paths(text):
    return re.findall(r'^\*\*\* (?:Add|Update|Delete) File: (.+)$|^\*\*\* Move to: (.+)$', text, re.M)


def message_text(p):
    return ''.join(c.get('text', '') for c in p.get('content', []))


def inspect(session, root=None, allow=()):
    events = [json.loads(line) for line in Path(session).read_bytes().splitlines()]
    assert events[0]['type'] == 'session_meta', 'Not a native Codex session'
    meta = events[0]['payload']
    root = os.path.normpath(root or meta['cwd'])
    allow = [os.path.normpath(a) for a in allow]
    norm = lambda s: UUID.sub('<UUID>', s.replace(root, '<ROOT>'))
    sha = lambda s: hashlib.sha256(
        ARG0.sub('codex-arg0<RAND>', DATE.sub('<DATE>', CODEX_HOME.sub('<CODEX_HOME>/', norm(s)))).encode()).hexdigest()[:16]
    startup = {'base_instructions': sha(json.dumps(meta.get('base_instructions'), ensure_ascii=False))}
    handoff_seen = False
    actions, flagged, messages, compactions = [], [], [], 0
    calls, outputs = {}, {}
    for i, e in enumerate(events):
        p = e.get('payload', {})
        kind = p.get('type')
        if e['type'] == 'compacted':
            compactions += 1
            if messages and messages[-1]['role'] == 'assistant':
                messages[-1]['compaction_summary'] = True
        if e['type'] == 'event_msg' and kind == 'item_completed' and (p.get('item') or {}).get('type') in CODE_MODE_ITEMS:
            item = p['item']
            reasons = []
            if item['type'] == 'CommandExecution':
                cmd = item.get('command')
                text = cmd[-1] if isinstance(cmd, list) and len(cmd) == 3 and cmd[1] in ('-lc', '-c') else (
                    ' '.join(map(str, cmd)) if isinstance(cmd, list) else str(cmd))
                workdir = (item.get('cwd') or '').removeprefix('file://') or None
                wd = os.path.normpath(workdir) if workdir else root
                if workdir and not any(inside(wd, r) for r in (root, *allow)):
                    reasons.append(f'workdir outside root: {workdir}')
                reasons += path_reasons(text, wd, root, allow)
                reasons += [label for rx, label in RISKY if rx.search(text)]
                output = f"{item.get('aggregated_output') or ''}\nExit code: {item.get('exit_code')}"
                tool = 'exec>command'
            else:
                paths = list((item.get('changes') or {}))
                text, workdir = 'FileChange ' + ' '.join(paths), None
                reasons += [f'patch outside root: {x}' for x in paths if not inside(os.path.normpath(x), root)]
                output = item.get('stdout') or item.get('status') or ''
                tool = 'exec>file_change'
            actions.append({'n': len(actions) + 1, 'event': i, 'time': e.get('timestamp', '')[11:19], 'tool': tool,
                            'workdir': norm(workdir) if workdir else '', 'text': text, 'call_id': item['id'],
                            'reasons': reasons})
            outputs[item['id']] = output
            continue
        if e['type'] != 'response_item':
            continue
        if kind == 'message':
            text, role = message_text(p), p.get('role')
            if not handoff_seen and role in ('developer', 'user'):
                startup[f'{role}@{i}'] = sha(text)
                handoff_seen = role == 'user' and text.startswith('ARW messageId:')
                if handoff_seen:
                    startup['messageId'] = text.split('\n', 1)[0].split(':', 1)[1].strip()
                continue
            messages.append({'event': i, 'role': role, 'text': text})
        elif kind in ('function_call', 'custom_tool_call'):
            calls[p['call_id']] = i
            name = p.get('name')
            text, workdir = call_text(p)
            wd = os.path.normpath(workdir) if workdir else root
            reasons = []
            if name not in KNOWN_TOOLS:
                reasons.append(f'unknown tool {name}')
            if workdir and not any(inside(wd, r) for r in (root, *allow)):
                reasons.append(f'workdir outside root: {workdir}')
            if name == 'apply_patch':
                for a, b in patch_paths(text):
                    target = os.path.join(root, a or b)
                    if not inside(target, root):
                        reasons.append(f'patch outside root: {a or b}')
            reasons += path_reasons(text, wd, root, allow)
            reasons += [label for rx, label in RISKY if rx.search(text)]
            actions.append({'n': len(actions) + 1, 'event': i, 'time': e.get('timestamp', '')[11:19],
                            'tool': name, 'workdir': norm(workdir) if workdir else '', 'text': text,
                            'call_id': p['call_id'], 'reasons': reasons})
        elif kind in ('function_call_output', 'custom_tool_call_output'):
            outputs[p['call_id']] = p.get('output', '')
    for a in actions:
        out = outputs.get(a['call_id'])
        out = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
        a['output_chars'] = None if out is None else len(out)
        m = re.search(r'(?:Process exited with code|Exit code:)\s*(-?\d+)', out or '')
        a['exit'] = m.group(1) if m else ''
        if out is None:
            a['reasons'].append('no result')
        elif DENIED.search(out[:2000]):
            a['reasons'].append('denied/permission in result')
        a['output'] = out
    for m in messages:
        m['flag'] = m['role'] != 'assistant' or (len(m['text']) > 2000 and not m.get('compaction_summary'))
    return {'session': str(session), 'threadId': meta.get('id'), 'source': meta.get('source'),
            'thread_source': meta.get('thread_source'), 'root': root, 'startup': startup,
            'handoff_found': handoff_seen, 'compactions': compactions, 'actions': actions,
            'messages': messages, 'final': messages[-1]['text'] if messages else None}


# Claude Code built-in tools and the field that names their target
CLAUDE_TARGETS = {'Read': 'file_path', 'Write': 'file_path', 'Edit': 'file_path', 'NotebookEdit': 'notebook_path',
                  'Glob': 'path', 'Grep': 'path', 'LS': 'path', 'Bash': 'command'}
CLAUDE_KNOWN = set(CLAUDE_TARGETS) | {'TodoWrite'}
CLAUDE_DENIED = re.compile(r'permission|haven.t granted|was blocked|not allowed|outside (?:of )?the (?:allowed )?working director', re.I)


def claude_text(name, value):
    """The command or target that the action line shows; patterns go with their search path."""
    if name == 'Bash':
        return value.get('command', '')
    if name in ('Glob', 'Grep'):
        return ' '.join(str(x) for x in (value.get('path') or '', value.get('pattern', ''), value.get('glob') or '') if x)
    target = value.get(CLAUDE_TARGETS.get(name, ''), '')
    return target if isinstance(target, str) and target else json.dumps(value, ensure_ascii=False)


def result_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return ''.join(c.get('text', '') if isinstance(c, dict) else str(c) for c in content)
    return json.dumps(content, ensure_ascii=False)


def claude_tokens(results):
    """API usage of the whole run. modelUsage of the last result event is cumulative over the run (summed over models);
    usage is per result event, so without modelUsage it is summed over all of them."""
    result = results[-1] if results else None
    models = (result or {}).get('modelUsage') or {}
    if models:
        total = lambda key: sum(m.get(key) or 0 for m in models.values())
        uncached, cached, output = (total('inputTokens') + total('cacheCreationInputTokens'),
                                    total('cacheReadInputTokens'), total('outputTokens'))
    else:
        usages = [r.get('usage') for r in results if r.get('usage')]
        if not usages:
            return {'uncached_input': None, 'cached_input': None, 'output': None, 'source': 'no result event'}
        total = lambda key: sum(u.get(key) or 0 for u in usages)
        uncached = total('input_tokens') + total('cache_creation_input_tokens')
        cached, output = total('cache_read_input_tokens'), total('output_tokens')
    return {'uncached_input': uncached, 'cached_input': cached, 'output': output,
            'source': 'Claude Code stream-json result event (API usage); cache writes count as uncached input'}


def stamp(value):
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    except (AttributeError, ValueError):
        return None


def claude_segments(stream):
    """A continued run's streams in order (claude_headless.execute_continued): stream.jsonl, then stream-1.jsonl, ...
    beside it, each with the harness message that started it (prompt-sent-<i>.md)."""
    stream = Path(stream)
    if stream.name != 'stream.jsonl':
        return [(stream, None)]
    more = sorted(stream.parent.glob('stream-*.jsonl'), key=lambda p: int(p.stem.split('-')[1]))
    return [(stream, None)] + [(p, stream.parent / f'prompt-sent-{p.stem.split("-")[1]}.md') for p in more]


def inspect_claude(stream, root, allow=()):
    """Same view as inspect() for a Claude Code stream-json run, plus tool-call counts and work time.
    A continued run (ARW early-exit continuation, 2026-10-20) is read over all its segments; each continuation message
    the harness sent is listed as a harness message, so it is flagged for the session check.

    Assistant and user events carry timestamps; action times count from the first of them. Work time is the sum of the
    result events' durations, else the span of the timestamps. A -p run usually has one result event; when the model
    leaves a background command running, Claude Code waits for it after the first result and then runs one more turn
    for its notification, with a result event of its own: each result's duration_ms, num_turns, permission_denials
    and usage cover only its own turn, and the wait between them is not work."""
    lines = []
    for path, sent in claude_segments(stream):
        if sent is not None:
            text = sent.read_text(errors='replace') if sent.exists() else '(continuation message not recorded)'
            lines.append(json.dumps({'type': 'harness_continuation', 'segment': path.name, 'text': text}).encode())
        lines += path.read_bytes().splitlines()
    stamps = []
    root = os.path.normpath(root)
    allow = [os.path.normpath(a) for a in allow]
    norm = lambda s: UUID.sub('<UUID>', s.replace(root, '<ROOT>'))
    startup, actions, messages, compactions, outputs = {}, [], [], 0, {}
    results, session_id, first = [], None, None
    for i, raw in enumerate(lines):
        try:
            e = json.loads(raw)
        except ValueError:
            continue
        at = stamp(e.get('timestamp'))
        if at is not None:
            stamps.append(at)
            first = at if first is None else first
        kind = e.get('type')
        if kind == 'harness_continuation':
            messages.append({'event': i, 'role': 'harness', 'text': f"continuation ({e['segment']}): {e['text']}"})
            continue
        if kind == 'system' and e.get('subtype') == 'init':
            if session_id is not None:
                continue  # a resumed segment's init: same session, startup already recorded
            session_id = e.get('session_id')
            # tools, MCP servers, model and mode are what this run started with; they must match across instances
            startup['init'] = hashlib.sha256(norm(json.dumps({k: e.get(k) for k in (
                'tools', 'mcp_servers', 'model', 'permissionMode', 'slash_commands', 'agents', 'skills', 'plugins')},
                sort_keys=True, ensure_ascii=False)).encode()).hexdigest()[:16]
            startup['claude_code_version'] = e.get('claude_code_version')
            continue
        if kind == 'system' and e.get('subtype') == 'compact_boundary':
            compactions += 1
            continue
        if kind == 'result':
            results.append(e)
            continue
        if kind == 'system':
            # Other system events carry no model action; a denial by the harness (e.g. --restricted on a path
            # outside the working directory) is kept as a flagged message, its message being a plain string.
            if e.get('subtype') == 'permission_denied':
                messages.append({'event': i, 'role': 'harness', 'text': f"permission_denied {e.get('tool_name')}: "
                                 f"{e.get('decision_reason')}: {e.get('message')}"})
            continue
        content = (e.get('message') or {}).get('content')
        if not isinstance(content, list):
            if kind == 'user' and isinstance(content, str):
                messages.append({'event': i, 'role': 'user', 'text': content})
            continue
        for block in content:
            btype = block.get('type')
            if kind == 'assistant' and btype == 'tool_use':
                name, value = block.get('name'), block.get('input') or {}
                text = claude_text(name, value)
                reasons = [] if name in CLAUDE_KNOWN else [f'unknown tool {name}']
                target = value.get(CLAUDE_TARGETS.get(name, ''), '') if name != 'Bash' else ''
                if isinstance(target, str) and target.startswith('/') and not any(
                        inside(target, r) for r in (root, *allow)):
                    reasons.append(f'target outside root: {target}')
                elif isinstance(target, str) and target and not target.startswith('/') and not inside(
                        os.path.join(root, target), root):
                    reasons.append(f'.. escapes root: {target}')
                reasons += [r for r in path_reasons(text, root, root, allow) if r not in reasons
                            and not (r.startswith('outside root: ') and f'target outside root: {r[14:]}' in reasons)]
                reasons += [label for rx, label in RISKY if rx.search(text)]
                time_text = '' if at is None or first is None else f'+{at - first:.0f}s'
                actions.append({'n': len(actions) + 1, 'event': i, 'time': time_text, 'tool': name, 'workdir': '',
                                'text': text, 'call_id': block.get('id'), 'reasons': reasons})
            elif kind == 'assistant' and btype == 'text':
                messages.append({'event': i, 'role': 'assistant', 'text': block.get('text', '')})
            elif kind == 'user' and btype == 'tool_result':
                outputs[block.get('tool_use_id')] = (result_text(block.get('content')), bool(block.get('is_error')))
            elif kind == 'user' and btype == 'text':
                messages.append({'event': i, 'role': 'user', 'text': block.get('text', '')})
    for a in actions:
        out, error = outputs.get(a['call_id'], (None, False))
        a['output_chars'] = None if out is None else len(out)
        a['exit'] = 'error' if error else ''
        if out is None:
            a['reasons'].append('no result')
        elif error and CLAUDE_DENIED.search(out[:2000]) or DENIED.search(out[:2000]):
            a['reasons'].append('denied/permission in result')
        a['output'] = out
    for m in messages:
        m['flag'] = m['role'] != 'assistant' or len(m['text']) > 2000
    counts = {}
    for a in actions:
        counts[a['tool']] = counts.get(a['tool'], 0) + 1
    result = results[-1] if results else None
    durations = [r.get('duration_ms') for r in results]
    duration = sum(durations) if durations and all(type(d) in (int, float) for d in durations) else None
    span = max(stamps) - first if stamps else None
    return {'session': str(stream), 'threadId': session_id, 'source': 'claude-code stream-json', 'thread_source': None,
            'root': root, 'startup': startup, 'handoff_found': 'init' in startup, 'compactions': compactions,
            'actions': actions, 'messages': messages,
            'final': (result or {}).get('result', messages[-1]['text'] if messages else None),
            'tool_calls': len(actions), 'tool_call_counts': counts,
            'work_seconds': duration / 1000 if type(duration) in (int, float) else span,
            'work_time_source': 'result duration_ms' if type(duration) in (int, float) else (
                'event timestamp span' if span is not None else None),
            'stream_span_seconds': span, 'result_subtype': (result or {}).get('subtype'),
            'result_events': len(results),
            'num_turns': sum(r.get('num_turns') or 0 for r in results) if results else None,
            'permission_denials': sum(len(r.get('permission_denials') or []) for r in results),
            'tokens': claude_tokens(results)}


def redact(text):
    if not isinstance(text, str):
        return text
    for pattern in SECRETS:
        text = pattern.sub(lambda m: (m.group(1) if m.lastindex else '') + '<redacted>' + (m.group(2) if (m.lastindex or 0) > 1 else ''), text)
    return text


def one_line(s, n=LINE_CHARS):
    s = ' '.join(s.split())
    return s if len(s) <= n else s[:n] + f' …(+{len(s) - n})'


def render(r, out):
    norm = lambda s: s.replace(r['root'], '<ROOT>')
    lines = [f"# 会话动作检查 {r['threadId']}", '',
             f"- 会话：`{r['session']}`", f"- 根目录 `<ROOT>`：`{r['root']}`",
             f"- 来源：{r['source']} / {r['thread_source']}；找到交接：{r['handoff_found']}；压缩 {r['compactions']} 次",
             f"- 启动上下文 SHA（`<ROOT>`、UUID、日期、codex-home 路径已归一，跨实例应一致）：`{json.dumps(r['startup'], ensure_ascii=False)}`",
             f"- 工具调用 {len(r['actions'])} 次，标记 {sum(bool(a['reasons']) for a in r['actions'])} 次"
             + (f"；按工具 {json.dumps(r['tool_call_counts'], ensure_ascii=False)}；工作时间 "
                f"{'未知' if r['work_seconds'] is None else format(r['work_seconds'] / 60, '.1f') + ' 分钟'}（{r['work_time_source']}）"
                if 'tool_call_counts' in r else ''),
             '', '## 动作', '']
    for a in r['actions']:
        flag = f"  **FLAG**: {'; '.join(a['reasons'])}" if a['reasons'] else ''
        lines.append(f"- #{a['n']} e{a['event']} {a['time']} {a['tool']} wd={a['workdir'] or '-'} "
                     f"exit={a['exit'] or '-'} out={a['output_chars']} | `{one_line(norm(a['text']))}`{flag}")
    lines += ['', '## 交接后的消息', '']
    for m in r['messages']:
        if m.get('compaction_summary'):
            lines.append(f"- e{m['event']} {m['role']}：压缩摘要 {len(m['text'])} 字（不例行阅读）")
        else:
            lines.append(f"- e{m['event']} {m['role']}{' **FLAG**' if m['flag'] else ''}：{one_line(norm(m['text']), 2000)}")
    (out / 'actions.md').write_text(redact('\n'.join(lines)) + '\n')
    detail = ['# 标记项全文', '']
    for a in r['actions']:
        if a['reasons']:
            o = a['output'] or ''
            detail += [f"## #{a['n']} e{a['event']} {a['tool']}：{'; '.join(a['reasons'])}", '',
                       '```', a['text'], '```', '', f'结果（{len(o)} 字）：', '', '```',
                       o[:FLAGGED_OUTPUT_CHARS] + (f'\n…(+{len(o) - FLAGGED_OUTPUT_CHARS})' if len(o) > FLAGGED_OUTPUT_CHARS else ''),
                       '```', '']
    for m in r['messages']:
        if m['flag']:
            detail += [f"## 消息 e{m['event']} {m['role']}", '', '```', m['text'], '```', '']
    (out / 'flagged.md').write_text(redact('\n'.join(detail)) + '\n')
    summary = {k: v for k, v in r.items() if k not in ('actions', 'messages')}
    summary['flagged_actions'] = [a['n'] for a in r['actions'] if a['reasons']]
    summary['flagged_messages'] = [m['event'] for m in r['messages'] if m['flag']]
    (out / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--session', type=Path, help='Native rollout JSONL')
    source.add_argument('--claude-stream', type=Path, help='Claude Code stream-json output (needs --root)')
    parser.add_argument('--root', help='Scenario root; defaults to the session cwd')
    parser.add_argument('--allow', action='append', default=[], help='Extra allowed path (repeatable)')
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.claude_stream:
        if not args.root:
            parser.error('--claude-stream needs --root (the isolated working directory)')
        summary = render(inspect_claude(args.claude_stream, args.root, args.allow), args.out)
        print(json.dumps({k: summary[k] for k in ('threadId', 'tool_calls', 'work_seconds', 'compactions',
                                                  'flagged_actions', 'flagged_messages')}, ensure_ascii=False))
        return
    others = sorted(set(args.session.parent.glob('rollout-*.jsonl')) - {args.session})
    summary = render(inspect(args.session, args.root, args.allow), args.out)
    summary['other_sessions_same_day'] = [
        {'path': str(o), **{k: json.loads(o.open().readline())['payload'].get(k) for k in ('id', 'source', 'thread_source', 'cwd')}}
        for o in others]
    (args.out / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({k: summary[k] for k in ('threadId', 'handoff_found', 'compactions', 'flagged_actions', 'flagged_messages')}
                     | {'other_sessions': len(others)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
