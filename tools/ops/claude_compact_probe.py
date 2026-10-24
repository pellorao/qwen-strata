"""Check where Claude Code auto-compacts under qwen-agent's settings, against a loopback fake Anthropic server.

No model and no lease: every request is answered locally with a scripted reply whose usage claims a chosen
context size, and the environment is the one `scripts/wsl/qwen-agent` gives Claude Code for the host's
published default tier. Two ways in for each claimed size:
- two turns: turn 1 reports the claimed input; turn 2 (`--continue`) shows whether Claude Code compacts first;
- mid turn: the first reply is a tool call, so the follow-up inside the same turn shows the same decision.

Default grid: the tier's compaction threshold ±100 tokens, both ways. It passes when every size below the
threshold runs without compaction, every size above it compacts and then continues, and every run exits 0.
`CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE` is undocumented, so rerun this after every Claude Code upgrade.

    python3 -m tools.ops.claude_compact_probe --out .tmp/<work>/compact-probe [--repeat 3]

Isolation (measurement rule "Claude Code 测试隔离"): fresh HOME and CLAUDE_CONFIG_DIR per run,
`--setting-sources user`, `--strict-mcp-config`, and a throwaway working directory outside the home directory.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.machinery import SourceFileLoader
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time

from tools.ops.deployment_source import current_host, published_tier

ROOT = Path(__file__).resolve().parents[2]
AGENT = ROOT / 'scripts/wsl/qwen-agent'
MODELS = {'Q2_0': 'q2_0', 'IQ2_XS': 'iq2_xs', 'IQ3_XXS': 'iq3_xxs'}
STEP = 100  # tokens either side of the threshold in the default grid
# Claude Code's own compaction instruction; a request carrying it is the summary call.
MARKER = 'Your task is to create a detailed summary of the conversation so far'
SUMMARY_CLAIM = 2000  # input the fake server claims for the summary call itself
TIMEOUT = 180  # seconds per Claude Code run


def is_compaction(body):
    return MARKER in json.dumps(body.get('messages', []), ensure_ascii=False)


def blocking_limit(window):
    """Claude Code's default compaction point without the override: window - 20000 - 3000."""
    return window - 23000


class FakeAnthropic(ThreadingHTTPServer):
    def __init__(self, folder, claimed, note=None):
        super().__init__(('127.0.0.1', 0), Handler)
        self.folder, self.claimed, self.note = Path(folder), claimed, note  # note: file the mid-turn tool call reads
        self.log, self.tool_sent = [], False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
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
        s = self.server
        raw = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        try:
            body = json.loads(raw)
        except ValueError:
            body = {}
        n = len(s.log) + 1
        (s.folder / f'request-{n}.json').write_bytes(raw)
        compact = is_compaction(body)
        entry = {'n': n, 'path': self.path, 'model': body.get('model'), 'max_tokens': body.get('max_tokens'),
                 'messages': len(body.get('messages', [])), 'compaction': compact, 'stream': body.get('stream'),
                 'claimed_input': None, 'tool_use': False, 'at': time.time()}
        s.log.append(entry)
        if 'count_tokens' in self.path:
            return self.reply_json({'input_tokens': 10})
        claimed = SUMMARY_CLAIM if compact else s.claimed
        entry['claimed_input'] = claimed
        text = '<summary>Fake summary. Nothing happened.</summary>' if compact else 'OK.'
        tool = None
        if s.note and not compact and not s.tool_sent and body.get('tools'):
            s.tool_sent = True
            tool = {'type': 'tool_use', 'id': 'toolu_fake_1', 'name': 'Read', 'input': {'file_path': str(s.note)}}
        entry['tool_use'] = bool(tool)
        usage = {'input_tokens': claimed, 'cache_creation_input_tokens': 0, 'cache_read_input_tokens': 0,
                 'output_tokens': 1}
        message = {'id': f'msg_fake_{n}', 'type': 'message', 'role': 'assistant', 'model': body.get('model', 'x'),
                   'content': [], 'stop_reason': None, 'stop_sequence': None, 'usage': usage}
        if not body.get('stream'):
            message.update(content=[tool or {'type': 'text', 'text': text}],
                           stop_reason='tool_use' if tool else 'end_turn', usage=dict(usage, output_tokens=5))
            return self.reply_json(message)
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()

        def emit(kind, value):
            self.wfile.write(f'event: {kind}\ndata: {json.dumps(value)}\n\n'.encode())
            self.wfile.flush()
        emit('message_start', {'type': 'message_start', 'message': message})
        if tool:
            emit('content_block_start', {'type': 'content_block_start', 'index': 0,
                                         'content_block': dict(tool, input={})})
            emit('content_block_delta', {'type': 'content_block_delta', 'index': 0,
                                         'delta': {'type': 'input_json_delta', 'partial_json': json.dumps(tool['input'])}})
        else:
            emit('content_block_start', {'type': 'content_block_start', 'index': 0,
                                         'content_block': {'type': 'text', 'text': ''}})
            emit('content_block_delta', {'type': 'content_block_delta', 'index': 0,
                                         'delta': {'type': 'text_delta', 'text': text}})
        emit('content_block_stop', {'type': 'content_block_stop', 'index': 0})
        emit('message_delta', {'type': 'message_delta', 'usage': {'output_tokens': 5},
                               'delta': {'stop_reason': 'tool_use' if tool else 'end_turn', 'stop_sequence': None}})
        emit('message_stop', {'type': 'message_stop'})
        self.close_connection = True


def agent_environment(base, model, effort, tier, blocking_override=True):
    """The variables qwen-agent itself gives Claude Code, pointed at `base` with a fake key."""
    agent = SourceFileLoader('qwen_agent', str(AGENT)).load_module()
    frontend = type('Frontend', (), {'base': base, 'key': 'fake-loopback'})()
    _, environment = agent.claude(frontend, model, effort, tier, [])
    if not blocking_override:
        environment.pop('CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE')
    return environment


def probe(folder, cwd, model, effort, tier, claimed, mid_turn=False, blocking_override=True, claude='claude'):
    """One claimed size, one way in. Writes request-N.json and result.json under `folder`."""
    folder, cwd = Path(folder), Path(cwd)
    folder.mkdir(parents=True)
    note = cwd / 'note.txt'
    note.write_text('NOTE-OK\n')
    server = FakeAnthropic(folder, claimed, note if mid_turn else None)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    home, config = folder / 'home', folder / 'claude-config'
    home.mkdir()
    config.mkdir()
    env = {'PATH': os.environ['PATH'], 'HOME': str(home), 'LANG': 'C.UTF-8', 'TERM': 'dumb',
           'CLAUDE_CONFIG_DIR': str(config), 'DISABLE_AUTOUPDATER': '1',
           **agent_environment(f'http://127.0.0.1:{server.server_port}', model, effort, tier, blocking_override)}
    base = [claude, '--setting-sources', 'user', '--strict-mcp-config', '--permission-mode', 'default', '-p']
    turns = ((('turn1', [], 'Read note.txt and say OK.'),) if mid_turn else
             (('turn1', [], 'Say OK.'), ('turn2', ['--continue'], 'Say OK again.')))
    runs = []
    try:
        for label, extra, prompt in turns:
            start = len(server.log)
            done = subprocess.run(base + extra + [prompt], cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True, timeout=TIMEOUT)
            runs.append({'label': label, 'exit': done.returncode, 'stdout': done.stdout[-600:],
                         'stderr': done.stderr[-600:], 'requests': server.log[start:]})
    finally:
        server.shutdown()
        server.server_close()
    # The decision falls on the requests after the one that reported the claimed size.
    after = runs[1]['requests'] if len(runs) > 1 else runs[0]['requests'][1:]
    compacted = any(r['compaction'] for r in after)
    first = next((i for i, r in enumerate(after) if r['compaction']), None)
    limit = tier['auto_compact_token_limit'] if blocking_override else blocking_limit(tier['context_window'])
    result = {'model': model, 'effort': effort, 'window': tier['context_window'], 'limit': tier['auto_compact_token_limit'],
              'blocking_override': blocking_override, 'effective_limit': limit, 'claimed': claimed, 'mid_turn': mid_turn,
              'claude_version': subprocess.run([claude, '--version'], capture_output=True, text=True).stdout.strip(),
              'compacted': compacted, 'expected_compaction': claimed > limit,
              'continued': first is not None and any(not r['compaction'] for r in after[first + 1:]),
              'main_requests_after': sum(not r['compaction'] for r in after),
              'exits': [run['exit'] for run in runs], 'runs': runs}
    result['ok'] = (all(code == 0 for code in result['exits']) and compacted == result['expected_compaction']
                    and (not compacted or result['continued']))
    (folder / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n')
    return result


def cell_name(window, limit, claimed, mid_turn, blocking_override, repeat):
    return (f'w{window}-l{limit}-c{claimed}{"" if blocking_override else "-nob"}{"-mid" if mid_turn else ""}'
            f'-r{repeat}')


def run(out, host=None, model='IQ3_XXS', effort='high', claimed=None, ways=('two-turn', 'mid-turn'),
        repeat=1, blocking_override=True, tier=None, claude=None, log=lambda line: print(line, flush=True)):
    out, host = Path(out), host or current_host()
    tier = tier or published_tier(host, model)
    claude = claude or shutil.which('claude')
    if not claude:
        raise SystemExit('claude is not on PATH')
    if claimed is None:
        point = tier['auto_compact_token_limit'] if blocking_override else blocking_limit(tier['context_window'])
        claimed = [point - STEP, point + STEP]
    slug = 'qwen3.8-flash-next-' + MODELS[model]
    cells = []
    for r in range(1, repeat + 1):
        for way in ways:
            for size in claimed:
                folder = out / cell_name(tier['context_window'], tier['auto_compact_token_limit'], size,
                                         way == 'mid-turn', blocking_override, r)
                # Outside the home directory, so no ancestor CLAUDE.md is picked up; removed after the run.
                with tempfile.TemporaryDirectory(prefix='claude-compact-probe-', dir='/tmp') as cwd:
                    result = probe(folder, cwd, slug, effort, tier, size, way == 'mid-turn', blocking_override, claude)
                cells.append({'cell': folder.name, 'way': way, 'repeat': r,
                              **{k: result[k] for k in ('claimed', 'effective_limit', 'expected_compaction', 'compacted',
                                                         'continued', 'exits', 'ok')}})
                log(json.dumps(cells[-1]))
    summary = {'host': host, 'model': model, 'effort': effort, 'tier': tier, 'blocking_override': blocking_override,
               'claude_version': result['claude_version'], 'agent_environment': {
                   k: v for k, v in agent_environment('http://127.0.0.1:0', slug, effort, tier, blocking_override).items()
                   if k.startswith('CLAUDE_CODE_')},
               'cells': cells, 'pass': all(c['ok'] for c in cells)}
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1) + '\n')
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--out', type=Path, required=True, help='new directory for this check (under .tmp/)')
    p.add_argument('--host', help='host whose published default tier qwen-agent uses (default: this machine)')
    p.add_argument('--model', choices=MODELS, default='IQ3_XXS')
    p.add_argument('--effort', choices=('low', 'medium', 'high'), default='high')
    p.add_argument('--repeat', type=int, default=1)
    p.add_argument('--claimed', type=int, nargs='+', help='claimed input sizes (default: threshold ±100)')
    p.add_argument('--way', choices=('two-turn', 'mid-turn'), action='append', help='default: both')
    p.add_argument('--window', type=int, help='explore another window (with --limit) instead of the published tier')
    p.add_argument('--limit', type=int)
    p.add_argument('--no-blocking-override', action='store_true', help="drop qwen-agent's compaction override")
    p.add_argument('--claude', help='Claude Code binary to probe (default: claude on PATH), e.g. the benchmark copy')
    a = p.parse_args()
    if a.out.exists():
        p.error(f'{a.out} exists')
    if (a.window is None) != (a.limit is None):
        p.error('--window and --limit go together')
    tier = a.window and {'context_window': a.window, 'auto_compact_token_limit': a.limit}
    summary = run(a.out, a.host, a.model, a.effort, a.claimed, tuple(a.way or ('two-turn', 'mid-turn')), a.repeat,
                  not a.no_blocking_override, tier, a.claude)
    print(json.dumps({k: summary[k] for k in ('claude_version', 'tier', 'agent_environment', 'pass')}))
    raise SystemExit(0 if summary['pass'] else 1)


if __name__ == '__main__':
    main()
