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
from test_loop_reminder import chat


class FakeModel:
    def __init__(self):
        self.port, self.native_key, self.reasoning_defaults = None, None, {}
        self.running, self.options, self.starts = False, None, 0

    def stopped(self):
        return not self.running

    def matches(self, options):
        return self.running and options == self.options

    def start(self, options):
        assert not self.running
        self.running, self.native_key, self.options = True, 'native-secret', options
        self.starts += 1
        self.reasoning_defaults = {'reasoning_effort': 'high', 'reasoning_budget_tokens': 8192, 'max_tokens': 24576}
        return {'status': 'running', 'model': 'qwen3.8-flash-next-q2_0'}

    def stop(self):
        self.running, self.native_key = False, None
        return {'status': 'stopped', 'clean_unload': True}

    def status(self):
        if not self.running:
            return {'status': 'stopped'}
        return {'status': 'running', 'native_health': {'startup_instructions': {
            'path': 'config/prompts/startup-instructions.txt', 'sha256': 'loaded', 'source_sha256': 'source',
            'enabled': True, 'loop_prevention_enabled': False}}}


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
        self.front.key_sha256 = self.front.loaded_model = self.front.idle_since = None

    def test_one_holder_and_release_revokes_but_keeps_model(self):
        key = self.front.acquire()['key']
        with self.assertRaises(frontend.Refused) as held:
            self.front.acquire()
        self.assertEqual(held.exception.status, 409)
        with self.assertRaises(frontend.Refused):
            self.front.start('wrong', {})
        self.front.start(key, {})
        self.assertEqual(self.front.release(key), {'lease': 'free', 'model': 'qwen3.8-flash-next-q2_0'})
        self.assertFalse(self.front.model.stopped())
        with self.assertRaises(frontend.Refused):
            self.front.status(key)
        self.assertEqual(self.front.health()['lease'], 'free')
        self.assertEqual(self.front.health()['startup_instructions'], {
            'enabled': True, 'sha256': 'loaded', 'source_sha256': 'source', 'loop_prevention_enabled': False})

    def test_next_lease_reuses_same_options_and_restarts_for_different_ones(self):
        key = self.front.acquire()['key']
        self.assertFalse(self.front.start(key, {'model': 'Q2_0'})['reused'])
        self.front.release(key)
        key = self.front.acquire()['key']
        self.assertTrue(self.front.start(key, {'model': 'Q2_0'})['reused'])
        self.assertEqual(self.front.model.starts, 1)
        self.assertFalse(self.front.start(key, {'model': 'Q2_0', 'engine_overrides': {'prefill': 4096}},
                                          maintenance=True)['reused'])
        self.assertEqual(self.front.model.starts, 2)

    def test_callers_choose_only_model_and_context_tier(self):
        key = self.front.acquire()['key']
        for options in ({'model': 'Q2_0', 'engine_overrides': {'prefill': 4096}},
                        {'model': 'Q2_0', 'request_defaults': {'temperature': 0.7}}, {'startup_instructions': False}):
            with self.assertRaisesRegex(ValueError, 'installation defaults'):
                self.front.start(key, options)
        self.assertEqual(self.front.model.starts, 0)

    def test_idle_model_is_stopped_only_without_a_lease_after_the_limit(self):
        key = self.front.acquire()['key']
        self.front.start(key, {})
        self.assertFalse(self.front.stop_if_idle(30))  # leased
        self.front.release(key)
        self.assertFalse(self.front.stop_if_idle(30))  # not idle long enough
        self.assertFalse(self.front.stop_if_idle(0))  # 0 keeps it
        self.front.idle_since -= 30 * 60
        self.assertTrue(self.front.stop_if_idle(30))
        self.assertTrue(self.front.model.stopped())
        self.assertIsNone(self.front.health()['model'])

    def test_acquire_does_not_wait_behind_a_starting_model(self):
        self.front.lock.acquire()  # a holder's model load in progress
        try:
            with self.assertRaises(frontend.Refused) as held:
                self.front.acquire()
            self.assertEqual(held.exception.status, 409)
        finally:
            self.front.lock.release()
        self.front.acquire()

    def test_acquire_stops_a_model_from_a_failed_start(self):
        self.front.model.running = True  # running but never recorded as loaded
        self.front.acquire()
        self.assertTrue(self.front.model.stopped())

    def test_allowlist_is_local_networks_only(self):
        import ipaddress
        self.front.networks = [ipaddress.ip_network('127.0.0.0/8'), ipaddress.ip_network('192.168.60.0/24')]
        self.front.networks_at = float('inf')
        self.assertTrue(self.front.allowed('192.168.60.7'))
        self.assertFalse(self.front.allowed('192.168.61.7'))


class DefaultTests(unittest.TestCase):
    installed = {'reasoning_effort': 'high', 'reasoning_budget_tokens': 28672}

    def test_installed_effort_uses_installed_budget_and_leaves_output_to_strata(self):
        body = frontend.apply_reasoning_defaults({}, '/v1/responses', self.installed)
        self.assertEqual(body, {'reasoning': {'effort': 'high'}, 'reasoning_budget_tokens': 28672})

    def test_installed_output_limit_is_still_filled(self):
        body = frontend.apply_reasoning_defaults({}, '/v1/chat/completions', dict(self.installed, max_tokens=24576))
        self.assertEqual((body['max_tokens'], body['reasoning_budget_tokens']), (24576, 28672))

    def test_other_effort_uses_table_and_explicit_output_caps_budget(self):
        body = frontend.apply_reasoning_defaults({'reasoning_effort': 'low'}, '/v1/chat/completions', self.installed)
        self.assertEqual(body, {'reasoning_effort': 'low', 'reasoning_budget_tokens': 28672})
        body = frontend.apply_reasoning_defaults({'reasoning_effort': 'medium', 'max_tokens': 4000},
                                                 '/v1/chat/completions', self.installed)
        self.assertEqual(body['reasoning_budget_tokens'], 2000)

    def test_none_and_unknown_efforts_are_refused(self):
        for effort in ('none', 'minimal'):
            with self.assertRaises(frontend.Refused) as caught:
                frontend.apply_reasoning_defaults({'reasoning_effort': effort}, '/v1/chat/completions', self.installed)
            self.assertEqual(caught.exception.status, 400)
        with self.assertRaises(frontend.Refused):
            frontend.apply_reasoning_defaults({'reasoning': {'effort': 'none'}}, '/v1/responses', self.installed)

    @staticmethod
    def codex_request(thread_source, **body):
        turn = {'session_id': 's', 'thread_id': 't', 'request_kind': 'turn', 'thread_source': thread_source}
        return dict(body, reasoning={'effort': 'low'}, client_metadata={'x-codex-turn-metadata': json.dumps(turn)})

    def test_guardian_is_told_by_turn_metadata_and_gets_its_own_limits(self):
        guarded = dict(self.installed, guardian_reasoning_budget_tokens=1536, guardian_max_tokens=2048)
        body = frontend.apply_reasoning_defaults(self.codex_request('guardian_review'), '/v1/responses', guarded)
        self.assertEqual((body['reasoning_budget_tokens'], body['max_output_tokens']), (1536, 2048))
        # The main thread at the same effort keeps the effort's budget and leaves output to Strata.
        body = frontend.apply_reasoning_defaults(self.codex_request('user'), '/v1/responses', guarded)
        self.assertEqual((body['reasoning_budget_tokens'], body.get('max_output_tokens')), (28672, None))
        # Prompt text alone never makes a request a guardian one.
        body = frontend.apply_reasoning_defaults(
            {'reasoning': {'effort': 'low'}, 'instructions': 'You are judging one planned coding-agent action.'},
            '/v1/responses', guarded)
        self.assertEqual(body['reasoning_budget_tokens'], 28672)
        # A guardian request's own limits win.
        body = frontend.apply_reasoning_defaults(self.codex_request('guardian_review', max_output_tokens=1000),
                                                 '/v1/responses', guarded)
        self.assertEqual((body['reasoning_budget_tokens'], body['max_output_tokens']), (500, 1000))
        # Without guardian defaults in the installation it is an ordinary low request; bad metadata is ignored.
        body = frontend.apply_reasoning_defaults(self.codex_request('guardian_review'), '/v1/responses', self.installed)
        self.assertEqual(body['reasoning_budget_tokens'], 28672)
        broken = dict(self.codex_request('guardian_review'), client_metadata={'x-codex-turn-metadata': '{'})
        self.assertEqual(frontend.apply_reasoning_defaults(broken, '/v1/responses', guarded)['reasoning_budget_tokens'],
                         28672)

    def test_explicit_budget_is_kept(self):
        body = frontend.apply_reasoning_defaults({'reasoning_budget_tokens': 1}, '/v1/chat/completions', self.installed)
        self.assertEqual(body['reasoning_budget_tokens'], 1)


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        (root / 'config').mkdir()
        (root / 'config/iq3_xxs-prebuilt.json').write_text(json.dumps({
            'args': ['--max-context', '156584', '--expert-profile', 'x'],
            'request_defaults': {'reasoning_effort': 'high', 'reasoning_budget_tokens': 8192,
                                 'max_tokens': 24576, 'top_k': 20},
            'engine_environment': {'STRATA_PREFILL_CPU_SHARE': 'auto'},
            'context_tiers': [{'context_window': 156584, 'auto_compact_token_limit': 100000},
                              {'context_window': 65536, 'auto_compact_token_limit': 40000}]}))
        self.patch = patch.object(model_process, 'ROOT', root)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_overrides_sampling_and_environment(self):
        model, config, env, reasoning = model_process.configuration(
            {'engine_overrides': {'vram-reserve-mib': 500, 'no-capture': True}}, 8100)
        self.assertEqual(model, 'IQ3_XXS')  # default model since 2026-10-11
        self.assertEqual(config['args'][-3:], ['--vram-reserve-mib', '500', '--no-capture'])
        self.assertEqual(config['sampling'], {'top_k': 20})
        self.assertEqual((config['port'], config['host']), (8100, '127.0.0.1'))
        self.assertEqual(env['STRATA_PREFILL_CPU_SHARE'], 'auto')
        self.assertEqual(reasoning['reasoning_budget_tokens'], 8192)

    def test_fit_max_tokens_defaults_on_and_explicit_false_is_kept(self):
        self.assertIs(model_process.configuration({}, 8100)[1]['fit_max_tokens'], True)
        self.assertIs(model_process.configuration({'fit_max_tokens': False}, 8100)[1]['fit_max_tokens'], False)
        with self.assertRaises(ValueError):
            model_process.configuration({'fit_max_tokens': 1}, 8100)

    def test_context_window_selects_only_a_published_tier(self):
        _, config, _, _ = model_process.configuration({'context_window': 65536}, 8100)
        self.assertEqual(config['args'][:2], ['--max-context', '65536'])
        self.assertNotIn('context_tiers', config)
        for window in (100000, '65536', True):
            with self.assertRaisesRegex(ValueError, 'published context tiers'):
                model_process.configuration({'context_window': window}, 8100)

    def test_adapt_lag_environment(self):
        _, _, env, _ = model_process.configuration({'engine_environment': {'STRATA_ADAPT_LAG': 2}}, 8100)
        self.assertEqual(env['STRATA_ADAPT_LAG'], '2')

    def test_null_override_drops_template_flag(self):
        args = model_process.configuration({'engine_overrides': {'prefill': None}}, 8100)[1]['args']
        self.assertNotIn('--prefill', args)
        self.assertEqual(len(args) % 2, 0)

    def test_another_effort_drops_installed_budget(self):
        reasoning = model_process.configuration({'request_defaults': {'reasoning_effort': 'medium'}}, 8100)[3]
        self.assertEqual(reasoning, {'reasoning_effort': 'medium'})

    def test_guardian_defaults_outlive_another_default_effort(self):
        reasoning = model_process.configuration({'request_defaults': {
            'reasoning_effort': 'medium', 'guardian_reasoning_budget_tokens': 1536, 'guardian_max_tokens': 2048}}, 8100)[3]
        self.assertEqual(reasoning, {'reasoning_effort': 'medium', 'guardian_reasoning_budget_tokens': 1536,
                                     'guardian_max_tokens': 2048})

    def test_rejects_unknown_or_injected_values(self):
        for options in ({'engine_overrides': {'api-key': 'x'}}, {'engine_overrides': {'prefill': '1 --x'}},
                        {'engine_environment': {'PATH': 'x'}}, {'request_defaults': {'seed': 1}},
                        {'model': 'Q8'}, {'profile_file': '/elsewhere/p.json'}, {'unknown': 1}):
            with self.assertRaises(ValueError, msg=options):
                model_process.configuration(options, 8100)


class StopTests(unittest.TestCase):
    def test_process_exiting_while_tree_is_walked_still_stops(self):
        class NoSuchProcess(Exception):
            pass

        class Process:
            def __init__(self, gone=False):
                self.gone, self.killed = gone, False

            def children(self, recursive):
                if self.gone:
                    raise NoSuchProcess()
                return [Process(gone=True)]

            def kill(self):
                if self.gone:
                    raise NoSuchProcess()
                self.killed = True
        server = Process(gone=True)
        fake = type(sys)('psutil')
        fake.NoSuchProcess, fake.wait_procs = NoSuchProcess, lambda procs, timeout: None
        model = model_process.ModelProcess.__new__(model_process.ModelProcess)
        model.port = 1
        with patch.dict(sys.modules, psutil=fake), \
                patch.object(model, '_processes', side_effect=[[server], []]), \
                patch.object(model, '_request', side_effect=OSError):
            self.assertEqual(model.stop(), {'status': 'stopped', 'clean_unload': False})


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
        front.search_results = frontend.hosted_search.Results()
        front.new_search_session()
        self.server.frontend = front

    def tearDown(self):
        for server in (self.server, self.upstream):
            server.shutdown()
            server.server_close()

    def post(self, path, body, key=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        connection.request('POST', path, json.dumps(body), {'Content-Type': 'application/json',
                           **({'Authorization': 'Bearer ' + key} if key else {}), **(headers or {})})
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
        # A request without the tool (Codex compaction) still replays the search as the model saw it.
        self.post('/strata/v1/responses', {'input': [output[0]], 'stream': True}, key)
        replayed = self.upstream.seen[-1][2]['input']
        self.assertEqual([i['type'] for i in replayed], ['function_call', 'function_call_output'])
        self.assertEqual(replayed[1]['output'], self.server.frontend.search_results.get(output[0]['id']))
        self.post('/lease/release', {}, key)
        self.assertIn(output[0]['id'], self.server.frontend.search_results)  # a resumed conversation takes a new lease

    def test_loop_reminder_goes_only_to_the_model(self):
        key = json.loads(self.post('/lease/acquire', {})[1])['key']
        self.post('/model/start', {}, key)
        body = chat(['node check.js', 'node check.js'])
        self.post('/strata/v1/chat/completions', body, key, {'X-Loop-Reminder': 'on'})
        forwarded = self.upstream.seen[-1][2]['messages']
        self.assertEqual(forwarded[:-1], body['messages'])
        self.assertTrue(forwarded[-1]['content'].startswith('[Loop check:'))
        self.post('/strata/v1/chat/completions', body, key)  # deprecated: off by default
        self.assertEqual(self.upstream.seen[-1][2]['messages'], body['messages'])


if __name__ == '__main__':
    unittest.main()
