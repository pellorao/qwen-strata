"""Frontend lease, defaults and passthrough without a model."""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import frontend
import model_process
from test_hosted_search import FakeSearch, MESSAGE, SEARCH, native_round


class FakeModel:
    def __init__(self):
        self.port, self.native_key, self.reasoning_defaults = None, None, {}
        self.running = False

    def stopped(self):
        return not self.running

    def start(self, options):
        self.running, self.native_key = True, 'native-secret'
        self.reasoning_defaults = {'reasoning_effort': 'high', 'reasoning_budget_tokens': 8192, 'max_tokens': 24576}
        return {'status': 'running', 'model': 'qwen3.8-flash-next-q2_0'}

    def stop(self):
        self.running, self.native_key = False, None
        return {'status': 'stopped', 'clean_unload': True}

    def status(self):
        return {'status': 'running' if self.running else 'stopped'}


class Upstream(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.seen.append((self.path, self.headers['Authorization'], body))
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        if any(t.get('name') == 'web_search' for t in body.get('tools', [])):
            searched = any(i.get('type') == 'function_call_output' for i in body['input'])
            for kind, data in native_round('resp_' + str(len(self.server.seen)), [MESSAGE] if searched else [SEARCH]):
                self.wfile.write(b': keep-alive\n\n' if data is None else
                                 f'event: {kind}\ndata: {json.dumps(data)}\n\n'.encode())
        else:
            self.wfile.write(b'data: one\n\ndata: two\n\n')
        self.close_connection = True


def serve(handler):
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class LeaseTests(unittest.TestCase):
    def setUp(self):
        self.front = frontend.Frontend.__new__(frontend.Frontend)
        self.front.model, self.front.lock = FakeModel(), threading.Lock()
        self.front.key_sha256 = self.front.loaded_model = None

    def test_one_holder_and_release_revokes_and_stops(self):
        key = self.front.acquire()['key']
        with self.assertRaises(frontend.Refused) as held:
            self.front.acquire()
        self.assertEqual(held.exception.status, 409)
        with self.assertRaises(frontend.Refused):
            self.front.start('wrong', {})
        self.front.start(key, {})
        self.assertEqual(self.front.release(key)['model_stop']['status'], 'stopped')
        self.assertTrue(self.front.model.stopped())
        with self.assertRaises(frontend.Refused):
            self.front.status(key)
        self.assertEqual(self.front.health()['lease'], 'free')

    def test_acquire_does_not_wait_behind_a_starting_model(self):
        self.front.lock.acquire()  # a holder's model load in progress
        try:
            with self.assertRaises(frontend.Refused) as held:
                self.front.acquire()
            self.assertEqual(held.exception.status, 409)
        finally:
            self.front.lock.release()
        self.front.acquire()

    def test_acquire_stops_a_model_left_without_lease(self):
        self.front.model.running = True
        self.front.acquire()
        self.assertTrue(self.front.model.stopped())

    def test_allowlist_is_local_networks_only(self):
        import ipaddress
        self.front.networks = [ipaddress.ip_network('127.0.0.0/8'), ipaddress.ip_network('192.168.60.0/24')]
        self.front.networks_at = float('inf')
        self.assertTrue(self.front.allowed('192.168.60.7'))
        self.assertFalse(self.front.allowed('192.168.61.7'))


class DefaultTests(unittest.TestCase):
    installed = {'reasoning_effort': 'high', 'reasoning_budget_tokens': 8192, 'max_tokens': 24576}

    def test_installed_effort_uses_installed_budget(self):
        body = frontend.apply_reasoning_defaults({}, '/v1/responses', self.installed)
        self.assertEqual(body, {'reasoning': {'effort': 'high'}, 'max_output_tokens': 24576,
                                'reasoning_budget_tokens': 8192})

    def test_other_effort_uses_table_and_explicit_output_caps_budget(self):
        body = frontend.apply_reasoning_defaults({'reasoning_effort': 'medium', 'max_tokens': 4000},
                                                 '/v1/chat/completions', self.installed)
        self.assertEqual(body['reasoning_budget_tokens'], 2000)
        self.assertEqual(frontend.apply_reasoning_defaults({'reasoning_effort': 'none'}, '/v1/chat/completions',
                                                           self.installed).get('reasoning_budget_tokens'), None)

    def test_explicit_budget_is_kept(self):
        body = frontend.apply_reasoning_defaults({'reasoning_budget_tokens': 1}, '/v1/chat/completions', self.installed)
        self.assertEqual(body['reasoning_budget_tokens'], 1)


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        (root / 'config').mkdir()
        (root / 'config/q2_0-prebuilt.json').write_text(json.dumps({
            'args': ['--max-context', '156584', '--expert-profile', 'x'],
            'request_defaults': {'reasoning_effort': 'high', 'reasoning_budget_tokens': 8192,
                                 'max_tokens': 24576, 'top_k': 20},
            'engine_environment': {'STRATA_PREFILL_CPU_SHARE': 'auto'}}))
        self.patch = patch.object(model_process, 'ROOT', root)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_overrides_sampling_and_environment(self):
        model, config, env, reasoning = model_process.configuration(
            {'engine_overrides': {'vram-reserve-mib': 500, 'no-capture': True}}, 8100)
        self.assertEqual(model, 'Q2_0')
        self.assertEqual(config['args'][-3:], ['--vram-reserve-mib', '500', '--no-capture'])
        self.assertEqual(config['sampling'], {'top_k': 20})
        self.assertEqual((config['port'], config['host']), (8100, '127.0.0.1'))
        self.assertEqual(env['STRATA_PREFILL_CPU_SHARE'], 'auto')
        self.assertEqual(reasoning['reasoning_budget_tokens'], 8192)

    def test_another_effort_drops_installed_budget(self):
        reasoning = model_process.configuration({'request_defaults': {'reasoning_effort': 'medium'}}, 8100)[3]
        self.assertEqual(reasoning, {'reasoning_effort': 'medium'})

    def test_rejects_unknown_or_injected_values(self):
        for options in ({'engine_overrides': {'api-key': 'x'}}, {'engine_overrides': {'prefill': '1 --x'}},
                        {'engine_environment': {'PATH': 'x'}}, {'request_defaults': {'seed': 1}},
                        {'model': 'Q8'}, {'profile_file': '/elsewhere/p.json'}, {'unknown': 1}):
            with self.assertRaises(ValueError, msg=options):
                model_process.configuration(options, 8100)


class PassthroughTests(unittest.TestCase):
    def setUp(self):
        self.upstream = serve(Upstream)
        self.upstream.seen = []
        self.server = serve(frontend.Handler)
        front = frontend.Frontend.__new__(frontend.Frontend)
        front.model, front.lock = FakeModel(), threading.Lock()
        front.model.port = self.upstream.server_port
        front.key_sha256 = front.loaded_model = None
        front.allowed = lambda client: True
        front.new_search_session()
        self.server.frontend = front

    def tearDown(self):
        for server in (self.server, self.upstream):
            server.shutdown()
            server.server_close()

    def post(self, path, body, key=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        connection.request('POST', path, json.dumps(body), {'Content-Type': 'application/json',
                           **({'Authorization': 'Bearer ' + key} if key else {})})
        reply = connection.getresponse()
        return reply.status, reply.read()

    def test_requires_lease_and_model_then_streams_with_native_key(self):
        self.assertEqual(self.post('/strata/v1/chat/completions', {})[0], 403)
        key = json.loads(self.post('/lease/acquire', {})[1])['key']
        self.assertEqual(self.post('/strata/v1/chat/completions', {}, key)[0], 503)
        self.post('/model/start', {}, key)
        self.assertEqual(self.post('/strata/v1/responses', {'model': 'other'}, key)[0], 409)
        status, raw = self.post('/strata/v1/responses', {'input': 'hi'}, key)
        self.assertEqual((status, raw), (200, b'data: one\n\ndata: two\n\n'))
        path, authorization, body = self.upstream.seen[-1]
        self.assertEqual((path, authorization), ('/v1/responses', 'Bearer native-secret'))
        self.assertEqual(body['model'], 'qwen3.8-flash-next-q2_0')
        self.assertEqual(body['reasoning_budget_tokens'], 8192)
        self.post('/strata/v1/messages', {'max_tokens': 5}, key)
        self.assertNotIn('reasoning_budget_tokens', self.upstream.seen[-1][2])

    def test_hosted_web_search_runs_between_native_rounds(self):
        key = json.loads(self.post('/lease/acquire', {})[1])['key']
        self.post('/model/start', {}, key)
        self.server.frontend.search = FakeSearch()
        tools = [{'type': 'web_search', 'external_web_access': True}]
        self.assertEqual(self.post('/strata/v1/responses', {'input': 'q', 'tools': tools}, key)[0], 400)
        status, raw = self.post('/strata/v1/responses', {'input': 'q', 'stream': True, 'tools': tools}, key)
        self.assertEqual(status, 200)
        events = [json.loads(line[5:]) for line in raw.decode().splitlines() if line.startswith('data:')]
        output = events[-1]['response']['output']
        self.assertEqual([i['type'] for i in output], ['web_search_call', 'message'])
        self.assertEqual(len(self.upstream.seen), 2)
        self.assertEqual(self.upstream.seen[0][1], 'Bearer native-secret')
        self.assertIn(output[0]['id'], self.server.frontend.search_results)
        self.post('/lease/release', {}, key)
        self.assertEqual(self.server.frontend.search_results, {})


if __name__ == '__main__':
    unittest.main()
