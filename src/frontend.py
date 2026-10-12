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

from brave_search import BraveSearch
import hosted_search
import loop_reminder
from model_process import PUBLIC_START_OPTIONS, ROOT, ModelProcess

MAX_BODY = 64 * 1024 * 1024
UPSTREAM_TIMEOUT = 900
BIND_RETRY = 10
# A model outlives its lease so the next caller with the same options skips the load (about 16 s and
# 36 GB of SSD reads on rtx3080ti); it is stopped after this many idle minutes without a lease. 0 keeps it.
IDLE_STOP_MINUTES = 30
IDLE_CHECK_SECONDS = 30
# Thinking budget per effort, used when a request names none. Total output is left to Strata, which uses the
# room left in the window. 28672 is half the worst-case room left once compaction is due (156584 - 100000).
# Efforts differ by their prompt, as in Strata and the model's own design; the cap is only a safety net.
# There is no 'none' effort: every request thinks, and one asking for none is refused.
EFFORT_BUDGETS = {'low': 28672, 'medium': 28672, 'high': 28672, 'xhigh': 28672, 'max': 28672}
GENERATION = ('/v1/chat/completions', '/v1/responses', '/v1/messages', '/v1/messages/count_tokens')


def log(message):
    """One frontend log line with local time to the millisecond, for work-time accounting."""
    now = time.time()
    print(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now)) + f'.{int(now % 1 * 1000):03d} {message}',
          file=sys.stderr, flush=True)


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


def guardian_request(body):
    """Codex's approval reviewer, told apart by the turn metadata Codex sends with every request
    (client_metadata["x-codex-turn-metadata"], a JSON string), never by its prompt."""
    meta = body.get('client_metadata')
    raw = meta.get('x-codex-turn-metadata') if isinstance(meta, dict) else None
    try:
        turn = json.loads(raw) if isinstance(raw, str) else None
    except ValueError:
        return False
    return isinstance(turn, dict) and turn.get('thread_source') == 'guardian_review'


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
    if effort not in EFFORT_BUDGETS:
        raise Refused(400, f'Unsupported reasoning effort {effort!r}; use one of {", ".join(EFFORT_BUDGETS)}.')
    budget, total = EFFORT_BUDGETS[effort], None
    if guardian_request(body) and 'guardian_max_tokens' in defaults:
        # A guardian decision is a short JSON verdict, so its limits are its own, whatever effort it names.
        # Strata keeps min(max(512, total // 4), total // 2) of the total for the answer: a total of 2048
        # keeps exactly 512 and leaves the thinking budget its full 1536.
        budget, total = defaults['guardian_reasoning_budget_tokens'], defaults['guardian_max_tokens']
    elif effort == defaults.get('reasoning_effort'):
        budget = defaults.get('reasoning_budget_tokens', budget)
        total = defaults.get('max_tokens')
    explicit_output = body.get(output) is not None
    if not explicit_output and total is not None:
        body[output] = total
    if budget and 'reasoning_budget_tokens' not in body:
        body['reasoning_budget_tokens'] = min(budget, body[output] // 2) if explicit_output else budget
    return body


class Frontend:
    def __init__(self, model_port):
        self.model = ModelProcess(model_port)
        self.lock = threading.Lock()
        self.key_sha256 = None
        self.loaded_model = None
        self.idle_since = None  # monotonic time the last lease was returned with the model still loaded
        self.networks, self.networks_at = [], 0.0
        self.search_results = hosted_search.Results()  # outlive leases: a resumed conversation replays them
        self.new_search_session()

    def new_search_session(self):
        # Pages read for open/find belong to one lease.
        self.search = BraveSearch()

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
        # The loaded model's startup-prompt hashes (never the text), so a caller that let
        # another client start the model can still bind the prompt it ran with.
        startup = None
        if self.loaded_model:
            loaded = (self.model.status().get('native_health') or {}).get('startup_instructions') or {}
            startup = {k: loaded[k] for k in ('enabled', 'sha256', 'source_sha256', 'loop_prevention_enabled')
                       if k in loaded}
        return {'service': 'qwen-strata-frontend', 'lease': 'held' if self.key_sha256 else 'free',
                'model': self.loaded_model, 'startup_instructions': startup}

    def acquire(self):
        # Never wait behind a holder, who may keep the lock for a whole model load.
        if self.key_sha256 or not self.lock.acquire(blocking=False):
            raise Refused(409, 'The model is leased by another caller.')
        try:
            if self.key_sha256:
                raise Refused(409, 'The model is leased by another caller.')
            if self.loaded_model is None and not self.model.stopped():
                self.model.stop()  # a failed start, not a model kept from the previous lease
            self.idle_since = None
            key = secrets.token_urlsafe(32)
            self.key_sha256 = hashlib.sha256(key.encode()).hexdigest()
            self.new_search_session()
            return {'key': key, 'lease': 'held'}
        finally:
            self.lock.release()

    def release(self, key):
        with self.lock:
            self.require(key)
            self.key_sha256 = None
            self.new_search_session()
            if self.loaded_model:
                self.idle_since = time.monotonic()
            return {'lease': 'free', 'model': self.loaded_model}

    def start(self, key, options, maintenance=False):
        with self.lock:
            self.require(key)
            if not maintenance and (not isinstance(options, dict) or set(options) - PUBLIC_START_OPTIONS):
                raise ValueError('Callers choose only the model and a published context_window; '
                                 'engine and request settings are the installation defaults.')
            if not self.model.stopped():
                if self.loaded_model and self.model.matches(options):
                    return dict(self.model.status(), reused=True)
                self.loaded_model = None
                self.model.stop()
            status = self.model.start(options)
            self.loaded_model = status['model']
            return dict(status, reused=False)

    def stop(self, key):
        with self.lock:
            self.require(key)
            self.loaded_model = None
            return self.model.stop()

    def status(self, key):
        self.require(key)
        return self.model.status()

    def stop_if_idle(self, minutes=IDLE_STOP_MINUTES):
        """Stop a model nobody has leased for `minutes`; never waits behind a holder."""
        if not minutes or not self.lock.acquire(blocking=False):
            return False
        try:
            if (self.key_sha256 or self.idle_since is None
                    or time.monotonic() - self.idle_since < minutes * 60):
                return False
            self.loaded_model = self.idle_since = None
            self.model.stop()
            log(f'model stopped after {minutes} idle minutes without a lease')
            return True
        finally:
            self.lock.release()

    def watch_idle(self):
        while True:
            time.sleep(IDLE_CHECK_SECONDS)
            try:
                self.stop_if_idle()
            except Exception as error:  # keep watching; the next lease or check retries the stop
                log(f'idle stop failed: {error}')


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, form, *args):
        log(f'{self.client_address[0]} {form % args}')

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
                # Project measurement and tuning only; not part of the caller interface.
                ('POST', '/maintenance/model/start'): lambda: frontend.start(self.key(), options, maintenance=True),
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
            if path != '/v1/messages/count_tokens':
                try:
                    if loop_reminder.apply(path, body, self.headers):
                        log(f'loop reminder appended to {path}')
                except Exception as error:  # a reminder is advice; never fail the request over it
                    log(f'loop reminder skipped: {type(error).__name__}')  # no request text in the log
            if path == '/v1/responses':
                try:
                    hosted = hosted_search.hosted_tool(body)
                except hosted_search.Refusal as error:
                    raise Refused(400, str(error)) from None
                if hosted:
                    return self.hosted(body, native_key)
                # Requests without the tool (e.g. Codex compaction) still replay earlier searches.
                body['input'] = hosted_search.native_input(body.get('input'), frontend.search_results)
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

    def hosted(self, body, native_key):
        """Serve a Responses stream that uses hosted web_search; see hosted_search."""
        frontend, key = self.server.frontend, self.key()
        started = False

        def upstream(request):
            nonlocal started
            connection = http.client.HTTPConnection('127.0.0.1', frontend.model.port, timeout=UPSTREAM_TIMEOUT)
            try:
                connection.request('POST', '/v1/responses', json.dumps(request, ensure_ascii=False).encode(),
                                   {'Content-Type': 'application/json', 'Accept': 'text/event-stream',
                                    'Authorization': 'Bearer ' + native_key})
                reply = connection.getresponse()
                if reply.status != 200:
                    detail = reply.read(65536).decode('utf-8', 'replace')
                    if not started:
                        raise Refused(reply.status, 'Native model refused the request: ' + detail)
                    raise RuntimeError(f'Native model returned HTTP {reply.status}: {detail}')
                if not started:
                    started = True
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/event-stream')
                    self.send_header('Cache-Control', 'no-cache')
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    self.close_connection = True
                kind = None
                for line in reply:
                    line = line.decode('utf-8').rstrip('\r\n')
                    if line.startswith(':'):
                        yield None, None
                    elif line.startswith('event:'):
                        kind = line[6:].strip()
                    elif line.startswith('data:'):
                        data = json.loads(line[5:])
                        yield kind or data.get('type'), data
                        kind = None
            finally:
                connection.close()

        def write(raw):
            self.wfile.write(raw)
            self.wfile.flush()

        try:
            hosted_search.run(body, frontend.search_results, frontend.search, upstream, write,
                              lambda: frontend.require(key))
        except Refused:
            if started:
                self.close_connection = True
                return
            raise
        except OSError:
            if not started:
                raise
            self.close_connection = True  # caller left mid-stream
        except Exception as error:
            if not started:
                raise
            message = {'type': 'error', 'code': 'hosted_search_failed', 'message': str(error), 'sequence_number': 0}
            try:
                write(f'event: error\ndata: {json.dumps(message)}\n\n'.encode())
            except OSError:
                pass
            self.close_connection = True


def main():
    config = json.loads((ROOT / 'config/frontend.json').read_text(encoding='utf-8'))
    (ROOT / 'logs').mkdir(exist_ok=True)
    sys.stdout = sys.stderr = open(ROOT / 'logs/frontend.log', 'a', encoding='utf-8', buffering=1)  # pythonw has no console
    while True:
        try:
            server = ThreadingHTTPServer((config['listen_address'], config['port']), Handler)
            break
        except OSError as error:  # at logon the LAN address may not be assigned yet
            log(f'bind {config["listen_address"]}:{config["port"]} failed: {error}; retrying')
            time.sleep(BIND_RETRY)
    server.daemon_threads = True
    server.frontend = Frontend(config['model_port'])
    server.frontend.model.stop()  # never inherit a model this process did not start
    threading.Thread(target=server.frontend.watch_idle, daemon=True).start()
    log(f'frontend ready on http://{config["listen_address"]}:{config["port"]}')
    server.serve_forever()
    server.server_close()


if __name__ == '__main__':
    main()
