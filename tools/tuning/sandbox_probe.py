"""No-model check that a tuning Codex session can read only its own workspace.

A loopback mock plays the model: it asks the real native Codex, configured exactly as a workload session
(`codex_workload.codex_overrides`), to run shell probes that try to read the workload, the project, the session's
own CODEX_HOME, other instance material and the provider key, once in the sandbox and once asking for escalation.
Inside the workspace, reading and running Python must still work; writing must not (window recall only reads).

    python3 -m tools.tuning.sandbox_probe --out DIR
    python3 -m tools.tuning.sandbox_probe --out DIR --window-replay WORKLOAD [--tier 156584] [--claude]
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shlex
import threading

from tools.safety.scripted_responses import scripted_stream, tool_aliases

ROOT = Path(__file__).resolve().parents[2]
KEY = 'probe-key-not-a-secret'


def targets(here):
    """(name, path, kind) the session must not see; `here` is the session folder holding workspace and CODEX_HOME."""
    return [('workload', ROOT / 'benchmarks/window-load-v1/window-v2-seed1.json', 'file'),
            ('benchmarks-dir', ROOT / 'benchmarks', 'dir'),
            ('project-file', ROOT / 'AGENTS.md', 'file'),
            ('codex-home', here / 'codex-home', 'dir'),
            ('session-folder-file', here / 'probe-marker.txt', 'file'),
            ('user-codex', Path.home() / '.codex', 'dir'),
            ('global-tmp', Path('/tmp'), 'dir'),
            ('windows-drive', Path('/mnt/c'), 'dir')]


def script(here):
    """One shell command printing `<name> READABLE|BLOCKED` per target, then the workspace checks."""
    lines = []
    for name, path, kind in targets(here):
        test = f'head -c1 {shlex.quote(str(path))}' if kind == 'file' else f'ls -A {shlex.quote(str(path))} | head -1'
        lines.append(f'if [ -n "$({test} 2>/dev/null)" ]; then echo "{name} READABLE"; else echo "{name} BLOCKED"; fi')
    lines += ['if [ -n "$STRATA_API_KEY" ]; then echo "provider-key READABLE"; else echo "provider-key BLOCKED"; fi',
              'if head -c1 README.md >/dev/null 2>&1; then echo "workspace-read OK"; fi',
              'if echo ok > probe-write.txt 2>/dev/null; then echo "workspace-write OK"; fi',
              'if [ "$(python3 -c "print(6*7)" 2>/dev/null)" = 42 ]; then echo "python OK"; fi']
    return '\n'.join(lines)


class Mock(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        server = self.server
        server.requests.append(body)
        outputs = [x for x in body.get('input') or [] if x.get('type') == 'function_call_output']
        aliases = tool_aliases(body)
        calls = []
        if len(outputs) < len(server.plan):
            name = next(n for n, m in aliases.items() if m['name'] == 'exec_command')
            calls = [(name, dict(server.plan[len(outputs)], workdir=str(server.workspace)))]
        server.outputs = [x.get('output') for x in outputs]
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Connection', 'close')
        self.end_headers()

        def emit(event):
            self.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())
            self.wfile.flush()

        scripted_stream(emit, body, aliases, 'Probe finished.', calls)
        self.close_connection = True


def verdict(text):
    if 'you cannot ask for escalated permissions' in str(text):
        return []
    lines = {l.split(' ')[0]: l.split(' ')[1] for l in str(text).splitlines() if l.count(' ') == 1}
    readable = [name for name, *_ in targets(Path('.'))] + ['provider-key']
    problems = [n + ' readable' for n in readable if lines.get(n) != 'BLOCKED']
    problems += [n + ' failed' for n in ('workspace-read', 'python') if lines.get(n) != 'OK']
    if lines.get('workspace-write') == 'OK':
        problems.append('workspace is writable')
    return problems


def probe(out):
    """Run both probes (sandboxed, then escalation requested) through the real Codex session setup."""
    from tools.tuning import codex_workload
    out = Path(out).resolve()
    here = out / 'session'
    workspace, home = here / 'workspace', here / 'codex-home'
    workspace.mkdir(parents=True)
    home.mkdir()
    (here / 'probe-marker.txt').write_text('outside the workspace\n')
    (workspace / 'README.md').write_text('# probe workspace\n')
    server = ThreadingHTTPServer(('127.0.0.1', 0), Mock)
    command = script(here)
    server.workspace, server.requests, server.outputs = workspace, [], []
    server.plan = [{'cmd': command},
                   {'cmd': command, 'sandbox_permissions': 'require_escalated',
                    'justification': 'Probe: read files outside the workspace.'}]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        plan = {'model': 'IQ3_XXS', 'workload': 'window', 'fixed_conditions': {'effort': 'high'}}
        spec = {'context_window': 156584, 'threshold': 100000}
        args = codex_workload.codex_overrides(plan, spec, here, f'http://127.0.0.1:{server.server_port}/v1')
        code, _, seconds = codex_workload.codex_exec(args, workspace, home, KEY, 'Run the probe.',
                                                     here / 'codex.jsonl', 120)
    finally:
        server.shutdown()
    results = [{'probe': p, 'output': o, 'problems': verdict(o)}
               for p, o in zip(('sandboxed', 'escalation-requested'), server.outputs)]
    problems = [] if len(results) == 2 else [f'only {len(results)} of 2 probes returned output']
    problems += [f'{r["probe"]}: {p}' for r in results for p in r['problems']]
    result = {'ok': not problems and code == 0, 'exit': code, 'seconds': round(seconds, 1), 'problems': problems,
              'results': results, 'mock_requests': len(server.requests), 'real_model_requests': 0}
    (out / 'sandbox-probe.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return result


COMPACT_MARK = 'Create a compact continuation summary'


class WindowMock(BaseHTTPRequestHandler):
    """Plays the model for the window workload: `ACK nn` for batches, the right answers at checkpoints, a fixed
    summary for compaction requests, and a usage of about chars/2.4 so that Codex compacts at its thresholds."""
    def log_message(self, *_args):
        pass

    def do_POST(self):
        from tools.tuning.codex_workload import message_text, turn_label
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        server = self.server
        users = [x for x in body.get('input') or [] if x.get('type') == 'message' and x.get('role') == 'user']
        last = message_text(users[-1]) if users else ''
        compaction = COMPACT_MARK in last
        label = turn_label(last)
        server.requests.append({'label': 'compaction' if compaction else label,
                                'project_compact_prompt': compaction and server.compact_text in last.replace('\r\n', '\n'),
                                'input_chars': len(json.dumps(body.get('input'))), 'tools': len(body.get('tools') or [])})
        if compaction:
            text = 'Summary (mock): a recall test; reply ACK to each batch; answer checkpoint questions.'
        elif label and label.startswith('questions '):
            n = int(label.split()[1])
            text = '\n'.join(f'{q["id"]}: {q["answer"]}' for q in server.workload['questions'] if q['checkpoint'] == n)
        elif label and label.startswith('batch '):
            text = f'ACK {label.split()[1]}'
        else:
            text = 'ACK 00'
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Connection', 'close')
        self.end_headers()
        tokens = int(len(json.dumps(body.get('input'))) / 2.4) + server.base_tokens

        def emit(event):
            if event.get('type') == 'response.completed':
                event['response']['usage'] = {'input_tokens': tokens, 'output_tokens': 20, 'total_tokens': tokens + 20,
                                              'input_tokens_details': {'cached_tokens': 0},
                                              'output_tokens_details': {'reasoning_tokens': 0}}
            self.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())
            self.wfile.flush()

        scripted_stream(emit, body, {}, text)
        self.close_connection = True


def window_replay(out, workload_path, tier=156584, base_tokens=12000):
    """No-model pipeline check of the window workload (design §2.5 precheck 2): the real Codex session setup against
    WindowMock.  Checks that compaction requests carry the project compact prompt, that the conversation continues
    after each compaction, and that every checkpoint's answers parse and score.  The mock reports exact usage, so
    where Codex compacts is not representative (only the pilot shows that)."""
    from tools.tuning import codex_workload, window_bank
    out = Path(out).resolve()
    workload = json.loads(Path(workload_path).read_text())
    server = ThreadingHTTPServer(('127.0.0.1', 0), WindowMock)
    server.requests, server.workload, server.base_tokens = [], workload, base_tokens
    server.compact_text = (ROOT / 'config/prompts/compact-prompt.txt').read_text().strip()[:200]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    spec = {'context_window': tier, 'threshold': codex_workload.TIERS[tier]}
    plan = {'model': 'IQ3_XXS', 'workload': 'window', 'fixed_conditions': {'effort': 'high'},
            'instance_seconds_limit': 1800}
    try:
        args_for = lambda here: codex_workload.codex_overrides(plan, spec, here,
                                                               f'http://127.0.0.1:{server.server_port}/v1')
        record = codex_workload.run_window(plan, workload, spec, out / f'replay-{tier}', args_for, KEY,
                                           lambda: 0, lambda: 0.0)
    finally:
        server.shutdown()
    compactions = [r for r in server.requests if r['label'] == 'compaction']
    problems = []
    if not compactions:
        problems.append('no compaction request')
    if not all(r['project_compact_prompt'] for r in compactions):
        problems.append('a compaction request lacks the project compact prompt')
    if record['raw_score'] != 1:
        problems.append(f'answers parsed and scored {record["raw_score"]}, not 1')
    if record['turns_planned'] != len(record['turns']) or record['timed_out']:
        problems.append('the conversation did not run to its end')
    after = [c['after_user_turn'] for c in record['compactions']]
    if len(after) != len(compactions):
        problems.append(f'{len(compactions)} compaction requests, {len(after)} compacted events in the rollout')
    result = {'ok': not problems, 'problems': problems, 'tier': tier, 'compactions_after': after,
              'kept_raw': [c['kept_raw'] for c in record['compactions']], 'requests': len(server.requests),
              'ack_problems': record['ack_problems'], 'tool_calls': record['tool_calls'],
              'in_text_share': record['scoring']['in_text_share'], 'C1': record['scoring']['C1'],
              'C2': record['scoring']['C2'], 'real_model_requests': 0}
    (out / f'window-replay-{tier}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return result


class AnthropicWindowMock(BaseHTTPRequestHandler):
    """WindowMock for Claude Code (Anthropic messages API): the same replies, Claude Code's summary call answered
    with a fixed summary, usage about chars/2.4 + base."""
    def log_message(self, *_args):
        pass

    def reply_json(self, value):
        data = json.dumps(value).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.reply_json({})

    do_HEAD = do_GET

    def do_POST(self):
        from tools.ops.claude_compact_probe import MARKER
        from tools.tuning.codex_workload import turn_label
        server = self.server
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
        if 'count_tokens' in self.path:
            return self.reply_json({'input_tokens': 10})
        texts = []
        for m in body.get('messages') or []:
            content = m.get('content')
            for b in ([{'type': 'text', 'text': content}] if isinstance(content, str) else content or []):
                if isinstance(b, dict) and b.get('type') == 'text' and m.get('role') == 'user':
                    texts.append(b.get('text', ''))
        everything = '\n'.join(texts).replace('\r\n', '\n')
        compaction = MARKER in everything
        label = next((turn_label(t) for t in reversed(texts) if turn_label(t)), None)
        server.requests.append({'label': 'compaction' if compaction else label,
                                'project_compact_prompt': compaction and server.compact_text in everything,
                                'tools': len(body.get('tools') or [])})
        if compaction:
            text = '<summary>Summary (mock): a recall test; reply ACK to each batch; answer checkpoint questions.</summary>'
        elif label and label.startswith('questions '):
            n = int(label.split()[1])
            text = '\n'.join(f'{q["id"]}: {q["answer"]}' for q in server.workload['questions'] if q['checkpoint'] == n)
        elif label and label.startswith('batch '):
            text = f'ACK {label.split()[1]}'
        else:
            text = 'ACK 00'
        tokens = 2000 if compaction else int(len(json.dumps(body.get('messages'))) / 2.4) + server.base_tokens
        usage = {'input_tokens': tokens, 'cache_creation_input_tokens': 0, 'cache_read_input_tokens': 0,
                 'output_tokens': 5}
        message = {'id': f'msg_mock_{len(server.requests)}', 'type': 'message', 'role': 'assistant',
                   'model': body.get('model', 'x'), 'content': [], 'stop_reason': None, 'stop_sequence': None,
                   'usage': usage}
        if not body.get('stream'):
            message.update(content=[{'type': 'text', 'text': text}], stop_reason='end_turn')
            return self.reply_json(message)
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()

        def emit(kind, value):
            self.wfile.write(f'event: {kind}\ndata: {json.dumps(value)}\n\n'.encode())
            self.wfile.flush()
        emit('message_start', {'type': 'message_start', 'message': message})
        emit('content_block_start', {'type': 'content_block_start', 'index': 0,
                                     'content_block': {'type': 'text', 'text': ''}})
        emit('content_block_delta', {'type': 'content_block_delta', 'index': 0,
                                     'delta': {'type': 'text_delta', 'text': text}})
        emit('content_block_stop', {'type': 'content_block_stop', 'index': 0})
        emit('message_delta', {'type': 'message_delta', 'usage': {'output_tokens': 5},
                               'delta': {'stop_reason': 'end_turn', 'stop_sequence': None}})
        emit('message_stop', {'type': 'message_stop'})
        self.close_connection = True


def claude_window_replay(out, workload_path, tier=156584, base_tokens=12000):
    """window_replay for the Claude Code path (codex_workload.run_claude_window against AnthropicWindowMock): the
    project compact prompt reaches every summary call, the conversation continues after each compaction, and every
    checkpoint's answers parse and score."""
    from tools.tuning import codex_workload
    out = Path(out).resolve()
    workload = json.loads(Path(workload_path).read_text())
    server = ThreadingHTTPServer(('127.0.0.1', 0), AnthropicWindowMock)
    server.requests, server.workload, server.base_tokens = [], workload, base_tokens
    server.compact_text = (ROOT / 'config/prompts/compact-prompt.txt').read_text().strip()[:200]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    plan = {'model': 'IQ3_XXS', 'host': 'rtx3080ti', 'fixed_conditions': {'effort': 'high'},
            'instance_seconds_limit': 1800, 'conditions': {f'window-{tier}': {'context_window': tier}}}
    try:
        record = codex_workload.run_claude_window(plan, workload, f'window-{tier}', out / f'claude-replay-{tier}',
                                                  mock_base=f'http://127.0.0.1:{server.server_port}')
    finally:
        server.shutdown()
    compactions = [r for r in server.requests if r['label'] == 'compaction']
    problems = []
    if not compactions:
        problems.append('no compaction request')
    if not all(r['project_compact_prompt'] for r in compactions):
        problems.append('a compaction request lacks the project compact prompt')
    if record['raw_score'] != 1:
        problems.append(f'answers parsed and scored {record["raw_score"]}, not 1')
    if record['turns_planned'] != record['turns_done'] or record['hard_interrupt']:
        problems.append('the conversation did not run to its end')
    after = [c['after_user_turn'] for c in record['compactions']]
    if len(after) != len(compactions):
        problems.append(f'{len(compactions)} compaction requests, {len(after)} compact boundaries in the stream')
    result = {'ok': not problems, 'problems': problems, 'tier': tier, 'harness': 'claude-code',
              'compactions_after': after, 'requests': len(server.requests), 'ack_problems': record['ack_problems'],
              'tool_calls': record['tool_calls'], 'in_text_share': record['scoring']['in_text_share'],
              'C1': record['scoring']['C1'], 'C2': record['scoring']['C2'], 'real_model_requests': 0}
    (out / f'claude-window-replay-{tier}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--window-replay', type=Path, metavar='WORKLOAD', help='run window_replay on this workload')
    parser.add_argument('--tier', type=int, default=156584)
    parser.add_argument('--claude', action='store_true', help='--window-replay through Claude Code')
    args = parser.parse_args()
    if args.window_replay and args.claude:
        print(json.dumps(claude_window_replay(args.out, args.window_replay, args.tier), ensure_ascii=False, indent=2))
    elif args.window_replay:
        print(json.dumps(window_replay(args.out, args.window_replay, args.tier), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(probe(args.out), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
