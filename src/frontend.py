"""Resident LAN frontend: one exclusive lease, model lifecycle and native Strata passthrough."""
import hashlib
import hmac
import http.client
import ipaddress
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import sys
import threading
import time

from model_process import ROOT, ModelProcess

MAX_BODY = 64 * 1024 * 1024
UPSTREAM_TIMEOUT = 900
BIND_RETRY = 10
# Thinking budget and total output per effort, used when a request names neither.
EFFORT_BUDGETS = {'none': (0, 8192), 'low': (2048, 8192), 'medium': (4096, 16384),
                  'high': (8192, 24576), 'xhigh': (8192, 24576), 'max': (8192, 24576)}
GENERATION = ('/v1/chat/completions', '/v1/responses', '/v1/messages', '/v1/messages/count_tokens')


class Refused(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def local_networks():
    import psutil
    networks = [ipaddress.ip_network('127.0.0.0/8')]
    for addresses in psutil.net_if_addrs().values():
        for address in addresses:
            if address.family.name == 'AF_INET' and address.netmask:
                networks.append(ipaddress.ip_network(f'{address.address}/{address.netmask}', strict=False))
    return networks


def apply_reasoning_defaults(body, path, defaults):
    """Fill effort, thinking budget and output limit a Chat or Responses request leaves out."""
    responses = path == '/v1/responses'
    if responses:
        reasoning = dict(body.get('reasoning') or {})
        effort = reasoning.setdefault('effort', defaults.get('reasoning_effort', 'high'))
        body['reasoning'] = reasoning
        output = 'max_output_tokens'
    else:
        effort = body.setdefault('reasoning_effort', defaults.get('reasoning_effort', 'high'))
        output = 'max_tokens'
    budget, total = EFFORT_BUDGETS.get(effort, EFFORT_BUDGETS['high'])
    if effort == defaults.get('reasoning_effort'):
        budget = defaults.get('reasoning_budget_tokens', budget)
        total = defaults.get('max_tokens', total)
    explicit_output = body.get(output) is not None
    body.setdefault(output, total)
    if budget and 'reasoning_budget_tokens' not in body:
        body['reasoning_budget_tokens'] = min(budget, body[output] // 2) if explicit_output else budget
    return body


class Frontend:
    def __init__(self, model_port):
        self.model = ModelProcess(model_port)
        self.lock = threading.Lock()
        self.key_sha256 = None
        self.loaded_model = None
        self.networks, self.networks_at = [], 0.0

    def allowed(self, client):
        if time.monotonic() - self.networks_at > 60:
            self.networks, self.networks_at = local_networks(), time.monotonic()
        address = ipaddress.ip_address(client)
        return any(address in network for network in self.networks)

    def require(self, key):
        if not key or self.key_sha256 is None or not hmac.compare_digest(
                hashlib.sha256(key.encode()).hexdigest(), self.key_sha256):
            raise Refused(403, 'A valid lease key is required.')

    def health(self):
        return {'service': 'qwen-strata-frontend', 'lease': 'held' if self.key_sha256 else 'free',
                'model': self.loaded_model}

    def acquire(self):
        # Never wait behind a holder, who may keep the lock for a whole model load.
        if self.key_sha256 or not self.lock.acquire(blocking=False):
            raise Refused(409, 'The model is leased by another caller.')
        try:
            if self.key_sha256:
                raise Refused(409, 'The model is leased by another caller.')
            if not self.model.stopped():
                self.model.stop()  # left over from a failed release or an earlier frontend
            key = secrets.token_urlsafe(32)
            self.key_sha256 = hashlib.sha256(key.encode()).hexdigest()
            return {'key': key, 'lease': 'held'}
        finally:
            self.lock.release()

    def release(self, key):
        with self.lock:
            self.require(key)
            self.key_sha256 = None  # revoked first, even if stopping fails
            self.loaded_model = None
            return {'lease': 'free', 'model_stop': self.model.stop()}

    def start(self, key, options):
        with self.lock:
            self.require(key)
            status = self.model.start(options)
            self.loaded_model = status['model']
            return status

    def stop(self, key):
        with self.lock:
            self.require(key)
            self.loaded_model = None
            return self.model.stop()

    def status(self, key):
        self.require(key)
        return self.model.status()


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, form, *args):
        print(f'{self.client_address[0]} {form % args}', file=sys.stderr, flush=True)

    def send_json(self, status, value):
        raw = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def key(self):
        value = self.headers.get('Authorization', '')
        return value[7:].strip() if value.lower().startswith('bearer ') else self.headers.get('x-api-key', '')

    def body(self):
        size = int(self.headers.get('Content-Length') or 0)
        if not 0 <= size <= MAX_BODY:
            raise Refused(413, 'Request body is too large.')
        return self.rfile.read(size)

    def handle_any(self):
        frontend = self.server.frontend
        path = self.path.split('?', 1)[0]
        try:
            if not frontend.allowed(self.client_address[0]):
                raise Refused(403, 'Client address is not on a local network.')
            if path.startswith('/strata/'):
                return self.passthrough(self.path[len('/strata'):])
            raw = self.body() if self.command == 'POST' else b''
            options = json.loads(raw or b'{}')
            routes = {
                ('GET', '/health'): frontend.health,
                ('POST', '/lease/acquire'): frontend.acquire,
                ('POST', '/lease/release'): lambda: frontend.release(self.key()),
                ('POST', '/model/start'): lambda: frontend.start(self.key(), options),
                ('POST', '/model/stop'): lambda: frontend.stop(self.key()),
                ('GET', '/model/status'): lambda: frontend.status(self.key()),
                ('POST', '/admin/shutdown'): lambda: self.shutdown(self.key()),
            }
            route = routes.get((self.command, path))
            if route is None:
                raise Refused(404, 'Unknown endpoint.')
            self.send_json(200, route())
        except Refused as error:
            self.send_json(error.status, {'error': {'message': str(error)}})
        except (ValueError, TypeError) as error:
            self.send_json(400, {'error': {'message': str(error)}})
        except Exception as error:
            self.send_json(503, {'error': {'message': str(error)}})

    do_GET = do_POST = handle_any

    def shutdown(self, key):
        frontend = self.server.frontend
        frontend.require(key)
        if not frontend.model.stopped():
            raise Refused(409, 'Stop the model before shutting the frontend down.')
        threading.Thread(target=self.server.shutdown, daemon=True).start()
        return {'shutdown': True}

    def passthrough(self, target):
        frontend = self.server.frontend
        frontend.require(self.key())
        native_key, loaded = frontend.model.native_key, frontend.loaded_model
        if not native_key or not loaded:
            raise Refused(503, 'No model is running. Start one through /model/start.')
        raw = self.body() if self.command == 'POST' else None
        path = target.split('?', 1)[0]
        if raw and path in GENERATION:
            body = json.loads(raw)
            if body.get('model', loaded) != loaded:
                raise Refused(409, f'Requested model differs from the loaded model {loaded}.')
            body['model'] = loaded
            if path in ('/v1/chat/completions', '/v1/responses'):
                apply_reasoning_defaults(body, path, frontend.model.reasoning_defaults)
            raw = json.dumps(body, ensure_ascii=False).encode()
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() in ('content-type', 'accept', 'anthropic-version', 'anthropic-beta')}
        headers['Authorization'] = 'Bearer ' + native_key
        upstream = http.client.HTTPConnection('127.0.0.1', frontend.model.port, timeout=UPSTREAM_TIMEOUT)
        sent = False
        try:
            upstream.request(self.command, target, raw, headers)
            reply = upstream.getresponse()
            sent = True
            self.send_response(reply.status)
            for name in ('Content-Type', 'Cache-Control'):
                if reply.getheader(name):
                    self.send_header(name, reply.getheader(name))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.close_connection = True
            while chunk := reply.read1(65536):
                self.wfile.write(chunk)
                self.wfile.flush()
        except OSError:
            if not sent:
                raise
            self.close_connection = True  # caller or model left mid-stream; closing lets Strata cancel
        finally:
            upstream.close()


def main():
    config = json.loads((ROOT / 'config/frontend.json').read_text(encoding='utf-8'))
    (ROOT / 'logs').mkdir(exist_ok=True)
    sys.stdout = sys.stderr = open(ROOT / 'logs/frontend.log', 'a', encoding='utf-8', buffering=1)  # pythonw has no console
    while True:
        try:
            server = ThreadingHTTPServer((config['listen_address'], config['port']), Handler)
            break
        except OSError as error:  # at logon the LAN address may not be assigned yet
            print(f'bind {config["listen_address"]}:{config["port"]} failed: {error}; retrying', flush=True)
            time.sleep(BIND_RETRY)
    server.daemon_threads = True
    server.frontend = Frontend(config['model_port'])
    server.frontend.model.stop()  # never inherit a model without its lease
    print(f'frontend ready on http://{config["listen_address"]}:{config["port"]}', flush=True)
    server.serve_forever()
    server.server_close()


if __name__ == '__main__':
    main()
