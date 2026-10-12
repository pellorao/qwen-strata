"""No-model check that a tuning Codex session can read only its own workspace.

A loopback mock plays the model: it asks the real native Codex, configured exactly as a workload session
(`codex_workload.codex_overrides`), to run shell probes that try to read the answer bank, the project, the session's
own CODEX_HOME, other instance material and the provider key, once in the sandbox and once asking for escalation.
Inside the workspace, reading, writing and running Python must still work.

    python3 -m tools.tuning.sandbox_probe --out DIR
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
    bank = ROOT / 'benchmarks/tuning-workloads-v1'
    return [('answer-bank', bank / 'sampling/set-draft.json', 'file'),
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
    problems += [n + ' failed' for n in ('workspace-read', 'workspace-write', 'python') if lines.get(n) != 'OK']
    return problems


def probe(out, workload='sampling'):
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
        plan = {'model': 'IQ3_XXS', 'workload': workload, 'fixed_conditions': {'effort': 'high'}}
        spec = {'context_window': 156584, 'threshold': 100000}
        args = codex_workload.codex_overrides(plan, spec, here, f'http://127.0.0.1:{server.server_port}/v1')
        code, _, seconds = codex_workload.codex_exec(args, workspace, home, KEY, 'Run the probe.',
                                                     here / 'codex.jsonl', 120)
    finally:
        server.shutdown()
    results = [{'probe': p, 'output': o, 'problems': verdict(o)}
               for p, o in zip(('sandboxed', 'escalation-requested'), server.outputs)]
    problems = [] if len(results) == 2 else [f'only {len(results)} of 2 probes returned output']
    if workload == 'window':
        for r in results:
            r['problems'] = [p for p in r['problems'] if p != 'workspace-write failed']
            if 'workspace-write OK' in str(r['output']):
                r['problems'].append('window workspace is writable')
    problems += [f'{r["probe"]}: {p}' for r in results for p in r['problems']]
    result = {'ok': not problems and code == 0, 'exit': code, 'seconds': round(seconds, 1), 'problems': problems,
              'results': results, 'mock_requests': len(server.requests), 'real_model_requests': 0}
    (out / 'sandbox-probe.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--workload', choices=('sampling', 'window'), default='sampling')
    args = parser.parse_args()
    print(json.dumps(probe(args.out, args.workload), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
