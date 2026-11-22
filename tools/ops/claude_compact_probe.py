"""Check where Claude Code auto-compacts under qwen-agent's settings, against a loopback fake Anthropic server.

No model and no lease: every request is answered locally with a scripted reply whose usage claims a chosen
context size, and the environment is the one `scripts/wsl/qwen-agent` gives Claude Code for the installation's
published default tier. Two ways in for each claimed size:
- two turns: turn 1 reports the claimed input; turn 2 (`--continue`) shows whether Claude Code compacts first;
- mid turn: the first reply is a tool call, so the follow-up inside the same turn shows the same decision.

Default grid: the tier's compaction threshold ±100 tokens, both ways. It passes when every size below the
threshold runs without compaction, every size above it compacts and then continues, and every run exits 0.
`CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE` is undocumented, so rerun this after every Claude Code upgrade.

    python3 -m tools.ops.claude_compact_probe --out .tmp/<work>/compact-probe [--repeat 3]

`--plan <scenario plan>` probes the DeepSeek arm instead (multi-model v2 plan §5.3, F6): the environment is the plan's
`fixed_conditions.deepseek_claude_environment` through `claude_headless.deepseek_environment`, the grid is the plan's
`CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE` ±100 and, as a second pass, the fallback `window - 23000` ±100 with the
override removed (the point Claude Code uses when the variable is unset). While any of the three variables is still
null the probe does not guess a default: it reports "待 F5 填值", writes a summary with `pending` and exits 2.

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

from tools.ops.deployment_source import published_tier

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


def deepseek_plan_limits(plan_path):
    """The three DeepSeek-arm variables a scenario plan fixes, and the names still null (None when the plan has none)."""
    limits = json.loads(Path(plan_path).read_text())['fixed_conditions'].get('deepseek_claude_environment')
    if limits is None:
        raise ValueError(f'{plan_path} fixes no deepseek_claude_environment')
    return limits, sorted(name for name, value in limits.items() if value is None)


def deepseek_env_for(limits, model):
    """Environment builder of the DeepSeek arm: the plan's limits (the override dropped on request), fake key and endpoint."""
    from tools.strata import claude_headless as ch

    def build(base, blocking_override=True):
        wanted = {k: v for k, v in limits.items() if blocking_override or k != 'CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE'}
        return ch.deepseek_environment(model, 'fake-loopback', base=base, limits=wanted)
    return build


def agent_environment(base, model, effort, tier, blocking_override=True):
    """The variables qwen-agent itself gives Claude Code, pointed at `base` with a fake key."""
    agent = SourceFileLoader('qwen_agent', str(AGENT)).load_module()
    frontend = type('Frontend', (), {'base': base, 'key': 'fake-loopback'})()
    _, environment = agent.claude(frontend, model, effort, tier, [])
    if not blocking_override:
        environment.pop('CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE')
    return environment


def probe(folder, cwd, model, effort, tier, claimed, mid_turn=False, blocking_override=True, claude='claude', env_for=None):
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
           **(env_for(f'http://127.0.0.1:{server.server_port}', blocking_override) if env_for else
              agent_environment(f'http://127.0.0.1:{server.server_port}', model, effort, tier, blocking_override))}
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
              # max_tokens of the main (non-summary) requests: the output limit Claude Code really sends (F8).
              'max_tokens': sorted({r['max_tokens'] for run in runs for r in run['requests'] if not r['compaction']},
                                   key=str),
              'exits': [run['exit'] for run in runs], 'runs': runs}
    result['ok'] = (all(code == 0 for code in result['exits']) and compacted == result['expected_compaction']
                    and (not compacted or result['continued']))
    (folder / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n')
    return result


def cell_name(window, limit, claimed, mid_turn, blocking_override, repeat):
    return (f'w{window}-l{limit}-c{claimed}{"" if blocking_override else "-nob"}{"-mid" if mid_turn else ""}'
            f'-r{repeat}')


def run(out, model='IQ3_XXS', effort='high', claimed=None, ways=('two-turn', 'mid-turn'),
        repeat=1, blocking_override=True, tier=None, claude=None, log=lambda line: print(line, flush=True),
        env_for=None, slug=None):
    out = Path(out)
    tier = tier or published_tier(model)
    claude = claude or shutil.which('claude')
    if not claude:
        raise SystemExit('claude is not on PATH')
    if claimed is None:
        point = tier['auto_compact_token_limit'] if blocking_override else blocking_limit(tier['context_window'])
        claimed = [point - STEP, point + STEP]
    slug = slug or 'qwen3.8-flash-next-' + MODELS[model]
    cells = []
    for r in range(1, repeat + 1):
        for way in ways:
            for size in claimed:
                folder = out / cell_name(tier['context_window'], tier['auto_compact_token_limit'], size,
                                         way == 'mid-turn', blocking_override, r)
                # Outside the home directory, so no ancestor CLAUDE.md is picked up; removed after the run.
                with tempfile.TemporaryDirectory(prefix='claude-compact-probe-', dir='/tmp') as cwd:
                    result = probe(folder, cwd, slug, effort, tier, size, way == 'mid-turn', blocking_override, claude, env_for)
                cells.append({'cell': folder.name, 'way': way, 'repeat': r,
                              **{k: result[k] for k in ('claimed', 'max_tokens', 'effective_limit', 'expected_compaction', 'compacted',
                                                         'continued', 'exits', 'ok')}})
                log(json.dumps(cells[-1]))
    summary = {'model': model, 'effort': effort, 'tier': tier, 'blocking_override': blocking_override,
               'claude_version': result['claude_version'], 'agent_environment': {
                   k: v for k, v in (env_for('http://127.0.0.1:0', blocking_override) if env_for else
                                     agent_environment('http://127.0.0.1:0', slug, effort, tier, blocking_override)).items()
                   if k.startswith('CLAUDE_CODE_')},
               'cells': cells, 'pass': all(c['ok'] for c in cells)}
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1) + '\n')
    return summary


PENDING_NOTE = '待 F5 填值：{names} 仍为 null，探针不用默认值代替'


def run_deepseek_plan(out, plan_path, model='deepseek-v4-flash', effort='high', repeat=1, claude=None,
                      log=lambda line: print(line, flush=True)):
    """Probe the DeepSeek arm of a v2 scenario plan: override pass, then the unset-override fallback pass."""
    out = Path(out)
    limits, pending = deepseek_plan_limits(plan_path)
    if pending:
        out.mkdir(parents=True)
        summary = {'plan': str(plan_path), 'pending': pending, 'note': PENDING_NOTE.format(names='、'.join(pending)),
                   'pass': False}
        (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1) + '\n')
        return summary
    window, override = limits['CLAUDE_CODE_MAX_CONTEXT_TOKENS'], limits['CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE']
    tier = {'context_window': window, 'auto_compact_token_limit': override}
    env_for = deepseek_env_for(limits, model)
    passes = {name: run(out / name, 'IQ3_XXS', effort, None, ('two-turn', 'mid-turn'), repeat, with_override, tier,
                        claude, log, env_for, model)
              for name, with_override in (('override', True), ('fallback', False))}
    seen = sorted({m for v in passes.values() for c in v['cells'] for m in c['max_tokens']}, key=str)
    expected = limits['CLAUDE_CODE_MAX_OUTPUT_TOKENS']
    summary = {'plan': str(plan_path), 'pending': [], 'limits': limits, 'fallback_point': blocking_limit(window),
               'passes': {k: {'pass': v['pass'], 'cells': v['cells']} for k, v in passes.items()},
               'max_tokens_seen': seen, 'output_limit_ok': seen == [expected],
               'claude_version': passes['override']['claude_version'],
               'pass': all(v['pass'] for v in passes.values()) and seen == [expected]}
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1) + '\n')
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--out', type=Path, required=True, help='new directory for this check (under .tmp/)')
    p.add_argument('--model', choices=MODELS, default='IQ3_XXS')
    p.add_argument('--effort', choices=('low', 'medium', 'high'), default='high')
    p.add_argument('--repeat', type=int, default=1)
    p.add_argument('--claimed', type=int, nargs='+', help='claimed input sizes (default: threshold ±100)')
    p.add_argument('--way', choices=('two-turn', 'mid-turn'), action='append', help='default: both')
    p.add_argument('--window', type=int, help='explore another window (with --limit) instead of the published tier')
    p.add_argument('--limit', type=int)
    p.add_argument('--no-blocking-override', action='store_true', help="drop qwen-agent's compaction override")
    p.add_argument('--claude', help='Claude Code binary to probe (default: claude on PATH), e.g. the benchmark copy')
    p.add_argument('--plan', type=Path, help='probe the DeepSeek arm of this v2 scenario plan instead of qwen-agent\'s tier')
    p.add_argument('--deepseek-model', default='deepseek-v4-flash')
    a = p.parse_args()
    if a.out.exists():
        p.error(f'{a.out} exists')
    if (a.window is None) != (a.limit is None):
        p.error('--window and --limit go together')
    if a.plan:
        summary = run_deepseek_plan(a.out, a.plan, a.deepseek_model, a.effort, a.repeat, a.claude)
        print(summary.get('note') or json.dumps({k: summary[k] for k in ('claude_version', 'limits', 'fallback_point', 'max_tokens_seen', 'pass')}))
        raise SystemExit(0 if summary['pass'] else 2 if summary['pending'] else 1)
    tier = a.window and {'context_window': a.window, 'auto_compact_token_limit': a.limit}
    summary = run(a.out, a.model, a.effort, a.claimed, tuple(a.way or ('two-turn', 'mid-turn')), a.repeat,
                  not a.no_blocking_override, tier, a.claude)
    print(json.dumps({k: summary[k] for k in ('claude_version', 'tier', 'agent_environment', 'pass')}))
    raise SystemExit(0 if summary['pass'] else 1)


if __name__ == '__main__':
    main()
