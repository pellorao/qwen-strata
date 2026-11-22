"""Capture the installed Codex native compact prompt using a loopback mock only.

This tool never accesses the Strata installation, controller, or a real model.
Full requests and app-server events stay in the supplied temporary directory.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
from tools.metrics.prompt_policy import NATIVE_COMPACT_VERSION
from tools.ops.deployment_source import MODELS, published_tier, served_model
from tools.strata.native_cli_binding import CODEX
from tools.safety.scripted_responses import scripted_stream


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


class MockResponses(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_POST(self):
        if self.path != '/v1/responses':
            self.send_error(404)
            return
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.requests.append(body)
        save(self.server.folder / f'request-{len(self.server.requests)}.json', body)
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Connection', 'close')
        self.end_headers()

        def emit(event):
            self.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())
            self.wfile.flush()

        scripted_stream(emit, body, {}, 'Mock checkpoint: COMPACT_PATH_CANARY=blue-482731. No tool operation occurred.')
        self.close_connection = True


class Client:
    def __init__(self, folder, workspace, base_url, slug, tier, catalog_path=None, extra_config=None, codex=None):
        """tier: published window and compaction limit applied to the catalog entry and config; None keeps the entry as
        given (catalog_path: another catalog file, e.g. the DeepSeek one) and sets no window or limit of its own.
        extra_config: further config keys (dotted names) laid over the defaults; codex: another binary."""
        home = folder / 'codex-home'
        home.mkdir()
        catalog = json.loads((catalog_path or ROOT / 'config/model-catalog.json').read_text())
        catalog['models'] = [m for m in catalog['models'] if m['slug'] == slug]
        model = catalog['models'][0]
        if tier:
            model.update(context_window=tier['context_window'], max_context_window=tier['context_window'])
        save(folder / 'catalog.json', catalog)
        config = {
            'model': model['slug'], 'model_provider': 'loopback_mock',
            'model_catalog_json': str(folder / 'catalog.json'),
            **({'model_context_window': tier['context_window'],
                'model_auto_compact_token_limit': tier['auto_compact_token_limit']} if tier else {}),
            'model_reasoning_effort': 'high', 'features.plugins': False,
            'model_providers.loopback_mock.name': 'Loopback mock, no inference',
            'model_providers.loopback_mock.base_url': base_url,
            'model_providers.loopback_mock.wire_api': 'responses',
            'model_providers.loopback_mock.requires_openai_auth': False,
            'model_providers.loopback_mock.supports_websockets': False,
            'model_providers.loopback_mock.request_max_retries': 0,
            'model_providers.loopback_mock.stream_max_retries': 0,
            **(extra_config or {}),
        }
        overrides = []
        for key, value in config.items():
            overrides += ['-c', key + '=' + json.dumps(value)]
        save(folder / 'config-overrides.json', config)
        env = {k: v for k, v in os.environ.items() if
               not k.upper().endswith('_PROXY') and
               not k.startswith(('CODEX_', 'OPENAI_', 'STRATA_', 'QWEN_'))}
        env['CODEX_HOME'] = str(home)
        self.stderr = (folder / 'stderr.log').open('w')
        self.events = (folder / 'app-server-events.jsonl').open('w')
        self.messages = []
        self.responses = queue.Queue()
        self.changed = threading.Condition()
        self.number = 0
        self.proc = subprocess.Popen([str(codex or CODEX), '--no-daemon', *overrides,
            'app-server'], cwd=workspace, env=env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=self.stderr, start_new_session=True)
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()

    def read(self):
        for raw in self.proc.stdout:
            value = json.loads(raw)
            self.events.write(json.dumps(value, ensure_ascii=False) + '\n')
            self.events.flush()
            with self.changed:
                self.messages.append(value)
                self.changed.notify_all()
            if 'id' in value:
                self.responses.put(value)

    def send(self, method, params, notify=False):
        self.number += 1
        request = {'method': method, 'params': params}
        if not notify:
            request['id'] = self.number
        self.proc.stdin.write((json.dumps(request) + '\n').encode())
        self.proc.stdin.flush()
        if notify:
            return
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            value = self.responses.get(timeout=max(.1, deadline - time.monotonic()))
            if 'method' in value:
                raise RuntimeError('Unexpected server request: ' + value['method'])
            if value.get('id') == self.number:
                if 'error' in value:
                    raise RuntimeError(json.dumps(value['error']))
                return value['result']
        raise TimeoutError(method)

    def wait_compact(self, offset):
        deadline = time.monotonic() + 30
        with self.changed:
            while time.monotonic() < deadline:
                for value in self.messages[offset:]:
                    if (value.get('method') == 'item/completed' and
                            value['params']['item'].get('type') == 'contextCompaction'):
                        return value
                    if value.get('method') == 'error':
                        raise RuntimeError(json.dumps(value['params']))
                if self.proc.poll() is not None:
                    raise RuntimeError('app-server exited')
                self.changed.wait(min(1, max(.1, deadline - time.monotonic())))
        raise TimeoutError('Native compact completion')

    def close(self):
        if self.proc.poll() is None:
            os.killpg(self.proc.pid, signal.SIGTERM)
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(self.proc.pid, signal.SIGKILL)
            self.proc.wait(timeout=5)
        self.reader.join(timeout=5)
        self.stderr.close()
        self.events.close()


def run(folder, model='IQ3_XXS'):
    folder = folder.resolve()
    slug, tier = 'qwen3.8-flash-next-' + model.lower(), published_tier(model)
    folder.mkdir(parents=True, exist_ok=False)
    workspace = folder / 'workspace'
    workspace.mkdir()
    version = subprocess.check_output([str(CODEX), '--version'], text=True).strip()
    server = ThreadingHTTPServer(('127.0.0.1', 0), MockResponses)
    server.folder, server.requests = folder, []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    client = None
    result = {'status': 'failed', 'codex_version': version, 'real_model_requests': 0,
              'scope': 'Native manual compact prompt capture against loopback mock only'}
    try:
        client = Client(folder, workspace, f'http://127.0.0.1:{server.server_port}/v1', slug, tier)
        client.send('initialize', {'clientInfo': {'name': 'compact_prompt_capture', 'version': '1'},
                                  'capabilities': {'experimentalApi': True}})
        client.send('initialized', {}, notify=True)
        thread = client.send('thread/start', {'model': slug,
            'modelProvider': 'loopback_mock', 'cwd': str(workspace), 'sandbox': 'read-only',
            'approvalPolicy': 'on-request', 'approvalsReviewer': 'auto_review', 'ephemeral': True})
        thread_id = thread['thread']['id']
        client.send('thread/inject_items', {'threadId': thread_id, 'items': [
            {'type': 'message', 'role': 'user', 'content': [{'type': 'input_text',
             'text': 'Remember COMPACT_PATH_CANARY=blue-482731; no pending task or tool.'}]},
            {'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text',
             'text': 'Recorded COMPACT_PATH_CANARY=blue-482731.'}]}]})
        offset = len(client.messages)
        client.send('thread/compact/start', {'threadId': thread_id})
        result['completion'] = client.wait_compact(offset)
        if len(server.requests) != 1:
            raise ValueError('Expected exactly one mock compact request')
        body = server.requests[0]
        texts = [c['text'] for item in body['input'] if item.get('role') == 'user'
                 for c in item.get('content', []) if c.get('type') == 'input_text']
        candidate = texts[-1]
        (folder / 'captured-native-compact-prompt.txt').write_text(candidate)
        saved = (ROOT / 'tools/resources/codex' / NATIVE_COMPACT_VERSION / 'compact-prompt.txt').read_text()
        result.update(status='passed', thread_id=thread_id, mock_requests=1,
            native_prompt_sha256=hashlib.sha256(candidate.encode()).hexdigest(),
            native_prompt_utf8_bytes=len(candidate.encode()),
            previous_snapshot_sha256=hashlib.sha256(saved.encode()).hexdigest(),
            previous_snapshot_exact_match=candidate == saved,
            request_sha256=hashlib.sha256((folder / 'request-1.json').read_bytes()).hexdigest())
    except Exception as error:
        result['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        if client is not None:
            client.close()
        server.shutdown()
        server.server_close()
        save(folder / 'result.json', result)
    return result


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--model', choices=MODELS, help='quantization (default: the one the installation serves, from its deployment config)')
    args = parser.parse_args(argv)
    args.model = args.model or served_model()
    return args


if __name__ == '__main__':
    args = arguments()
    result = run(args.out, args.model)
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result['status'] == 'passed' else 1)
