"""Loopback relay in front of an API provider that records what the provider actually returned (D14).

Codex does not keep the service tier of a response, so API provider runs send their model requests through this
relay: every request is forwarded unchanged (method, path below the relay root, body and headers, including the
credential headers Codex adds) and the reply is streamed back unchanged. From the reply only these fields are kept:
HTTP status, model, service tier, response id and status, and usage (Responses ``response.created``/``response.completed`` events, or
an Anthropic Messages ``message_start``/``message_delta`` pair). Headers and bodies are never written.

A WebSocket upgrade is refused with 426 and recorded, so a client that prefers WebSocket falls back to HTTP; the
zero-model probe in benchmarks/multi-model-v1/plan.md checks that Codex does.

Error rows (a transport error, or an upstream status >= 400) carry ``error_side`` saying which side the failure was on:
  'client'   the relay failed writing to the harness (it abandoned the stream or closed the connection), e.g. a
             BrokenPipeError / ConnectionResetError from send_response, end_headers, write or flush;
  'upstream' the upstream failed: connecting to it failed, reading its reply failed (stream cut, timeout), or it
             answered with an error status (>= 400; the reply is passed through, so no transport_error then).
Rows without the field are older records; tools.reviewer.reminder_interrupt.error_side infers the side for them.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request

# Tunables
TIMEOUT = 900  # seconds without upstream bytes before the forward is abandoned
CHUNK = 4096
HOP = {'host', 'connection', 'content-length', 'accept-encoding', 'keep-alive', 'proxy-connection',
       'transfer-encoding', 'upgrade', 'te', 'trailer'}


class Fields:
    """Incremental SSE (or JSON) scan of one reply for the kept fields."""

    def __init__(self):
        self.buffer = b''
        self.values = {}

    def event(self, data):
        kind = data.get('type')
        if kind in ('response.created', 'response.in_progress', 'response.completed', 'response.incomplete',
                    'response.failed') and isinstance(data.get('response'), dict):
            response = data['response']
            for key in ('model', 'service_tier', 'id'):
                if response.get(key) is not None:
                    self.values[key] = response[key]
            if response.get('status') is not None:  # kept apart from the HTTP status of the record
                self.values['response_status'] = response['status']
            if response.get('usage'):
                self.values['usage'] = response['usage']
        elif kind == 'message_start' and isinstance(data.get('message'), dict):
            message = data['message']
            for key in ('model', 'id'):
                if message.get(key) is not None:
                    self.values[key] = message[key]
            usage = message.get('usage') or {}
            if usage.get('service_tier') is not None:
                self.values['service_tier'] = usage['service_tier']
            self.values['usage'] = dict(usage)
        elif kind == 'message_delta' and isinstance(data.get('usage'), dict):
            self.values.setdefault('usage', {}).update(data['usage'])
            if data['usage'].get('service_tier') is not None:
                self.values['service_tier'] = data['usage']['service_tier']

    def feed(self, chunk):
        self.buffer += chunk
        *lines, self.buffer = self.buffer.split(b'\n')
        for line in lines:
            line = line.strip()
            if line.startswith(b'data:'):
                try:
                    data = json.loads(line[5:].strip())
                except ValueError:
                    continue
                if isinstance(data, dict):
                    self.event(data)

    def finish(self, whole_json=None):
        if whole_json is not None:
            try:
                data = json.loads(whole_json)
            except ValueError:
                return self.values
            if isinstance(data, dict):
                if data.get('object') == 'response' or 'output' in data:
                    self.event({'type': 'response.completed', 'response': data})
                elif data.get('type') == 'message':
                    self.event({'type': 'message_start', 'message': data})
        return self.values


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass

    def forward(self):
        relay = self.server.relay
        started = time.time()
        if self.headers.get('Upgrade', '').lower() == 'websocket':
            relay.record({'started_at': started, 'ended_at': time.time(), 'method': self.command, 'path': self.path,
                          'status': 426, 'websocket_refused': True})
            body = b'WebSocket is not relayed; use HTTP.'
            self.send_response(426)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        length = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
        headers['Accept-Encoding'] = 'identity'
        request = urllib.request.Request(relay.upstream + self.path, body, headers, method=self.command)
        fields, status, kind, whole = Fields(), None, '', b''
        side = 'upstream'  # which side an exception raised now belongs to
        try:
            try:
                reply = relay.opener.open(request, timeout=TIMEOUT)
            except urllib.error.HTTPError as error:
                reply = error
            with reply:
                status = reply.status if hasattr(reply, 'status') else reply.code
                kind = reply.headers.get('Content-Type', '')
                if status >= 400:
                    fields.values['error_side'] = 'upstream'
                side = 'client'
                self.send_response(status)
                for key, value in reply.headers.items():
                    if key.lower() not in HOP:
                        self.send_header(key, value)
                self.send_header('Connection', 'close')
                self.end_headers()
                side = 'upstream'
                # The ChatGPT backend streams SSE without a Content-Type (2026-10-20, relayprobe), so every reply is
                # scanned as SSE first and parsed as one JSON body only when no event was found.
                read = getattr(reply, 'read1', reply.read)  # read1 returns what has arrived, so events stream through
                while data := read(CHUNK):
                    fields.feed(data)
                    if len(whole) < 4 << 20:
                        whole += data
                    side = 'client'
                    self.wfile.write(data)
                    self.wfile.flush()
                    side = 'upstream'
            self.close_connection = True
            values = fields.finish(None if fields.values or 'event-stream' in kind else whole)
            relay.record({'started_at': started, 'ended_at': time.time(), 'method': self.command, 'path': self.path,
                          'status': status, **values})
        except Exception as error:  # the client sees a broken stream; the record says so, without any content
            relay.record({'started_at': started, 'ended_at': time.time(), 'method': self.command, 'path': self.path,
                          'status': status, 'transport_error': type(error).__name__, 'error_side': side})
            self.close_connection = True

    do_POST = do_GET = do_PUT = do_DELETE = forward


class Relay:
    """One relay per run directory: start, then point the client at `url` (the upstream's root, relayed)."""

    def __init__(self, upstream, out):
        self.upstream = upstream.rstrip('/')
        self.out = Path(out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.path = self.out / 'relay.jsonl'
        self.lock = threading.Lock()
        self.rows = []
        self.opener = urllib.request.build_opener()  # system proxy settings apply, as they do for Codex itself
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.server.relay = self
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.close()

    def record(self, row):
        with self.lock:
            row = {'n': len(self.rows) + 1, **row}
            self.rows.append(row)
            with self.path.open('a') as out:
                out.write(json.dumps(row, ensure_ascii=False) + '\n')

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def summary(self, since=None, until=None):
        return tier_summary(self.rows, since, until)


def tier_summary(rows, since=None, until=None):
    """Service tiers and models the provider returned for the model requests in [since, until]."""
    chosen = [r for r in rows if (since is None or r['started_at'] >= since) and (until is None or r['started_at'] <= until)]
    tiers, models = {}, {}
    for row in chosen:
        if row.get('websocket_refused'):
            continue
        tier = row.get('service_tier', 'not-returned')
        tiers[tier] = tiers.get(tier, 0) + 1
        if row.get('model'):
            models[row['model']] = models.get(row['model'], 0) + 1
    return {'requests': sum(1 for r in chosen if not r.get('websocket_refused')),
            'websocket_refused': sum(1 for r in chosen if r.get('websocket_refused')),
            # the 426 WebSocket refusal is the relay's own by-design answer (Codex falls back to HTTP), not an error
            'errors': sum(1 for r in chosen if not r.get('websocket_refused')
                          and (r.get('transport_error') or (r.get('status') or 0) >= 400)),
            'service_tiers': tiers, 'models': models,
            'source': 'service_tier and model fields of the provider replies, recorded by tools.reviewer.api_relay'}


def load(path):
    path = Path(path)
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
