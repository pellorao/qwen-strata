"""Action-centred inspection view of one closed native Codex reviewer session.

Programs extract and classify; Main reads every action line and decides.
Reasoning, metadata and outputs of calls whose targets stay inside the
scenario root are not routine reading: a tool call is the only way a reviewer
reaches any source, so a call confined to the root can only observe the root.
Flagged calls get their full command and output in flagged.md. The original
session is only read, never copied or changed.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path

# Executables and devices that are not observation sources
SYSTEM_PATHS = ('/usr/bin/', '/bin/', '/usr/local/bin/', '/dev/null', '/dev/stdin',
                '/dev/stdout', '/dev/stderr', '/usr/bin/env')
KNOWN_TOOLS = {'exec_command', 'write_stdin', 'apply_patch', 'view_image', 'update_plan'}
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
    (re.compile(r'sessions/|rollout-|codex-home|/\.state\b|private\.toml', re.I), 'session/credential material'),
]
DENIED = re.compile(r'sandbox denied|Operation not permitted|Permission denied|EPERM|EACCES|CreateProcess', re.I)
UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
# Startup text that differs per instance by design: the run date and the
# per-instance Codex home holding the platform skills
DATE = re.compile(r'\b\d{4}-\d{2}-\d{2}\b')
CODEX_HOME = re.compile(r'\S*/codex-home/')


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
        DATE.sub('<DATE>', CODEX_HOME.sub('<CODEX_HOME>/', norm(s))).encode()).hexdigest()[:16]
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


def one_line(s, n=LINE_CHARS):
    s = ' '.join(s.split())
    return s if len(s) <= n else s[:n] + f' …(+{len(s) - n})'


def render(r, out):
    norm = lambda s: s.replace(r['root'], '<ROOT>')
    lines = [f"# 会话动作检查 {r['threadId']}", '',
             f"- 会话：`{r['session']}`", f"- 根目录 `<ROOT>`：`{r['root']}`",
             f"- 来源：{r['source']} / {r['thread_source']}；找到交接：{r['handoff_found']}；压缩 {r['compactions']} 次",
             f"- 启动上下文 SHA（`<ROOT>`、UUID、日期、codex-home 路径已归一，跨实例应一致）：`{json.dumps(r['startup'], ensure_ascii=False)}`",
             f"- 工具调用 {len(r['actions'])} 次，标记 {sum(bool(a['reasons']) for a in r['actions'])} 次",
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
    (out / 'actions.md').write_text('\n'.join(lines) + '\n')
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
    (out / 'flagged.md').write_text('\n'.join(detail) + '\n')
    summary = {k: v for k, v in r.items() if k not in ('actions', 'messages')}
    summary['flagged_actions'] = [a['n'] for a in r['actions'] if a['reasons']]
    summary['flagged_messages'] = [m['event'] for m in r['messages'] if m['flag']]
    (out / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--session', required=True, type=Path, help='Native rollout JSONL')
    parser.add_argument('--root', help='Scenario root; defaults to the session cwd')
    parser.add_argument('--allow', action='append', default=[], help='Extra allowed path (repeatable)')
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
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
