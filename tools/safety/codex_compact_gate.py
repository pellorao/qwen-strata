"""Zero-model check of where the pinned Codex compacts and what output limit its requests carry (multi-model v2 plan
§5.3 items 2 and 4, F7 and F8). No model, no lease, no network: a loopback Responses mock answers every request and
claims a growing input size in `usage`; Codex's own token accounting then decides when to compact.

One turn is driven through the app-server: each mock reply is a harmless tool call whose usage claims the next size of the
ladder, so the next request shows whether Codex compacted first (a compaction request, an `item/completed`
contextCompaction event). Cases:
- `strata`: the published tier of this host (window and limit as the Strata arms run); the compaction must come right after
  the first claimed size above the limit. This is the control that shows the probe can see a compaction.
- `deepseek`: the DeepSeek arm's catalog entry as v1 and v2 run it (window 1048576, 95% effective, no compaction limit of its
  own): no compaction at any size up to `--max-input`.
Every request body is kept, and the output-limit fields it carries (`max_output_tokens`) are reported per case.

    python3 -m tools.safety.codex_compact_gate --out .tmp/<work>/codex-compact [--max-input 800000]

Codex is the benchmark copy of tools.reviewer.harness_pins (SHA and version checked). The scripted usage is a claim to drive
the accounting, never a measurement.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time

from tools.ops.deployment_source import current_host, published_tier
from tools.reviewer.native_cli_binding import pinned_codex
from tools.reviewer.verify_codex_compact_prompt import Client, ROOT, save
from tools.safety.scripted_responses import scripted_stream, tool_aliases

DEEPSEEK_CATALOG = ROOT / 'benchmarks/multi-model-v1/catalogs/deepseek-codex-0.163.0.json'
DEEPSEEK_SLUG = 'deepseek-flash'
# Marker of Codex's native compaction request (tools/resources/codex/<version>/compact-prompt.txt, first words).
COMPACT_MARKER = 'CONTEXT CHECKPOINT COMPACTION'
SUMMARY_CLAIM = 2000  # input the mock claims for the compaction request itself
# Claimed sizes: coarse steps over the whole 1M window, dense around Codex's default 90% point of the window.
DEEPSEEK_LADDER = (50000, 100000, 200000, 400000, 600000, 800000, 900000, 940000, 945000, 990000, 1040000)
TURN_TIMEOUT = 180


def request_text(body):
    return json.dumps(body.get('input', []), ensure_ascii=False)


class Mock(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        if not self.path.endswith('/responses'):
            self.send_error(404)
            return
        server = self.server
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        number = len(server.log) + 1
        save(server.folder / f'request-{number}.json', body)
        compaction = COMPACT_MARKER in request_text(body)
        aliases = tool_aliases(body)
        tool = next((n for n in ('shell_command', 'exec_command', 'shell') if n in aliases), None)
        entry = {'n': number, 'compaction': compaction, 'claimed': None,
                 'max_output_tokens': body.get('max_output_tokens'), 'keys': sorted(body)}
        if compaction:
            entry['claimed'], calls, text = SUMMARY_CLAIM, [], 'Mock checkpoint. Nothing happened.'
        elif server.step < len(server.ladder) and tool:
            entry['claimed'], text = server.ladder[server.step], None
            calls = [(tool, {'command': 'true'} if tool == 'shell_command' else {'cmd': 'true'})]
            server.step += 1
        else:
            entry['claimed'], calls, text = server.ladder[-1], [], 'Done.'
        server.log.append(entry)
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Connection', 'close')
        self.end_headers()

        def emit(event):
            self.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())
            self.wfile.flush()
        scripted_stream(emit, body, aliases, text, calls, entry['claimed'])
        self.close_connection = True


def wait_turn(client, offset):
    deadline = time.monotonic() + TURN_TIMEOUT
    with client.changed:
        while time.monotonic() < deadline:
            for value in client.messages[offset:]:
                if value.get('method') == 'turn/completed':
                    return value
                if value.get('method') == 'error':
                    raise RuntimeError(json.dumps(value['params']))
            if client.proc.poll() is not None:
                raise RuntimeError('app-server exited')
            client.changed.wait(1)
    raise TimeoutError('turn did not complete')


def run_case(folder, name, slug, ladder, tier=None, catalog_path=None, extra_config=None, codex=None):
    """One case: drive a turn through the ladder; report compactions, where they fell and the output-limit fields."""
    folder = Path(folder).resolve()
    folder.mkdir(parents=True)
    workspace = folder / 'workspace'
    workspace.mkdir()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Mock)
    server.folder, server.log, server.ladder, server.step = folder, [], list(ladder), 0
    threading.Thread(target=server.serve_forever, daemon=True).start()
    client = None
    try:
        client = Client(folder, workspace, f'http://127.0.0.1:{server.server_port}/v1', slug, tier,
                        catalog_path, extra_config, codex)
        client.send('initialize', {'clientInfo': {'name': 'codex_compact_gate', 'version': '1'},
                                   'capabilities': {'experimentalApi': True}})
        client.send('initialized', {}, notify=True)
        thread = client.send('thread/start', {'model': slug, 'modelProvider': 'loopback_mock', 'cwd': str(workspace),
                                              'sandbox': 'read-only', 'approvalPolicy': 'never', 'ephemeral': True})
        offset = len(client.messages)
        client.send('turn/start', {'threadId': thread['thread']['id'], 'input': [{'type': 'text', 'text': 'Run the checks.'}]})
        wait_turn(client, offset)
        events = [m for m in client.messages if m.get('method') == 'item/completed'
                  and m['params']['item'].get('type') == 'contextCompaction']
    finally:
        if client is not None:
            client.close()
        server.shutdown()
        server.server_close()
    log = server.log
    # The size claimed by the reply just before each compaction request: where Codex decided to compact.
    at = [log[i - 1]['claimed'] for i, r in enumerate(log) if r['compaction'] and i > 0]
    result = {'case': name, 'slug': slug, 'tier': tier, 'ladder': list(ladder), 'requests': len(log),
              'compaction_requests': sum(r['compaction'] for r in log), 'compaction_events': len(events),
              'compacted_after_claim': at, 'max_claimed_before_first_compaction': (
                  max((r['claimed'] for r in log[:next(i for i, r in enumerate(log) if r['compaction'])] if r['claimed']),
                      default=None) if at else max((r['claimed'] for r in log), default=None)),
              'max_output_tokens_seen': sorted({r['max_output_tokens'] for r in log}, key=str),
              'request_keys': sorted({k for r in log for k in r['keys']}), 'log': log}
    save(folder / 'result.json', result)
    return result


def strata_ladder(tier):
    limit = tier['auto_compact_token_limit']
    return [limit // 2, limit - 1000, limit + 1000, limit + 10000]


def run(out, host=None, max_input=800000, codex=None, model='IQ3_XXS'):
    """Both cases. Pass: the Strata control compacts right after the first claim above its limit (and not before), and the
    DeepSeek arm never compacts at a claim up to `max_input`."""
    out = Path(out).resolve()
    host = host or current_host()
    codex = codex or pinned_codex()['executable']
    tier = published_tier(host, model)
    control = run_case(out / 'strata', 'strata', 'qwen3.8-flash-next-' + model.lower(), strata_ladder(tier), tier, codex=codex)
    deepseek = run_case(out / 'deepseek', 'deepseek', DEEPSEEK_SLUG, DEEPSEEK_LADDER, None, DEEPSEEK_CATALOG, codex=codex)
    limit = tier['auto_compact_token_limit']
    control_ok = (control['compaction_events'] >= 1 and control['compacted_after_claim']
                  and control['compacted_after_claim'][0] == limit + 1000
                  and control['max_claimed_before_first_compaction'] > limit - 1000 + 0)
    first = deepseek['compacted_after_claim'][0] if deepseek['compacted_after_claim'] else None
    deepseek_ok = first is None or first > max_input
    summary = {'codex': pinned_codex(), 'strata_control': {k: control[k] for k in (
                   'tier', 'compacted_after_claim', 'compaction_events', 'max_output_tokens_seen')} | {'pass': bool(control_ok)},
               'deepseek': {k: deepseek[k] for k in ('compacted_after_claim', 'compaction_events', 'requests',
                                                      'max_output_tokens_seen', 'request_keys')}
               | {'first_compaction_after_claim': first, 'max_input_checked': max_input, 'pass': bool(deepseek_ok)},
               'pass': bool(control_ok and deepseek_ok)}
    save(out / 'summary.json', summary)
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--out', type=Path, required=True, help='new directory for this check (under .tmp/)')
    p.add_argument('--host')
    p.add_argument('--max-input', type=int, default=800000,
                   help='largest request input the DeepSeek arm must run without compaction (default 800000)')
    a = p.parse_args()
    if a.out.exists():
        p.error(f'{a.out} exists')
    summary = run(a.out, a.host, a.max_input)
    print(json.dumps({k: summary[k] for k in ('strata_control', 'deepseek', 'pass')}, ensure_ascii=False))
    raise SystemExit(0 if summary['pass'] else 1)


if __name__ == '__main__':
    main()
