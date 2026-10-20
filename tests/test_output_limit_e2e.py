"""Output-limit retry end to end: the real frontend Handler between a scripted engine (Strata v0.1.45 fixture streams)
and the real clients, Codex 0.163.0 (benchmark copy) and Claude Code (isolated config).  No model is used."""
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from test_frontend import FakeModel, frontend, serve
from tools.reviewer.native_cli_binding import CODEX

FIXTURES = ROOT / 'tests/fixtures/output_limit'
CLAUDE = shutil.which('claude')


class Script(BaseHTTPRequestHandler):
    """Serves the next fixture stream to each generation request; Claude Code's side requests get a plain answer."""
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])) or b'{}')
        if self.path.endswith('/count_tokens'):
            raw = b'{"input_tokens": 100}'
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        main = self.path == '/v1/responses' or bool(body.get('tools'))
        if main:
            self.server.seen.append(body)
        script = self.server.script
        name = script[min(len(self.server.seen), len(script)) - 1] if main else script[-1]
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        self.wfile.write((FIXTURES / f'{name}.sse').read_bytes())
        self.close_connection = True


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.engine = serve(Script)
        self.engine.seen = []
        self.server = serve(frontend.Handler)
        front = frontend.Frontend.__new__(frontend.Frontend)
        front.model, front.lock = FakeModel(), __import__('threading').Lock()
        front.model.port = self.engine.server_port
        front.key_sha256 = front.loaded_model = None
        front.allowed = lambda client: True
        front.search_results = frontend.hosted_search.Results()
        front.new_search_session()
        self.server.frontend = front
        self.key = front.acquire()['key']
        front.start(self.key, {})
        self.folder = Path(tempfile.mkdtemp(prefix='outcap-e2e-'))
        self.base = f'http://127.0.0.1:{self.server.server_port}/strata'

    def tearDown(self):
        for server in (self.server, self.engine):
            server.shutdown()
            server.server_close()
        shutil.rmtree(self.folder, ignore_errors=True)

    def client(self, args, env):
        process = subprocess.Popen(args, cwd=self.folder / 'ws', env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, start_new_session=True)
        try:
            out, err = process.communicate(timeout=90)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, 9)
            out, err = process.communicate()
            self.fail('client timed out; stdout tail: ' + out.decode()[-3000:] + ' stderr tail: ' + err.decode()[-1500:])
        finally:
            if process.poll() is None:
                os.killpg(process.pid, 9)
                process.wait()
        return process.returncode, out.decode(), err.decode()

    def test_frontend_passes_streams_without_a_limit_hit_byte_for_byte(self):
        import http.client
        for path, name, stream in (('/v1/responses', 'responses-calls', True), ('/v1/responses', 'responses-text', False),
                                   ('/v1/responses', 'responses-limit-after-call', True),
                                   ('/v1/messages', 'messages-tool', True),
                                   ('/v1/messages', 'messages-limit-after-tool', True)):
            with self.subTest(name=name, stream=stream):
                self.engine.script, self.engine.seen = [name], []
                connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
                connection.request('POST', '/strata' + path, json.dumps({'stream': stream, 'input': 'hi', 'tools': [
                    {'type': 'function', 'name': 'x'}], 'max_tokens': 8192}), {'Authorization': 'Bearer ' + self.key,
                                                                             'Content-Type': 'application/json'})
                reply = connection.getresponse()
                self.assertEqual(reply.read(), (FIXTURES / f'{name}.sse').read_bytes())
                self.assertEqual(len(self.engine.seen), 1)
                connection.close()

    @unittest.skipUnless(CODEX.is_file(), 'Codex 0.163.0 benchmark copy not installed')
    def test_codex_continues_its_turn_and_never_sees_the_cut_off_call(self):
        self.engine.script = ['responses-limit-custom', 'responses-retry-ok', 'responses-text']
        (self.folder / 'ws').mkdir()
        catalog = json.loads((ROOT / 'config/model-catalog.json').read_text())
        catalog['models'] = [m for m in catalog['models'] if m['slug'] == 'qwen3.8-flash-next-iq3_xxs']
        (self.folder / 'catalog.json').write_text(json.dumps(catalog))
        config = {'model': 'qwen3.8-flash-next-iq3_xxs', 'model_provider': 'front',
                  'model_catalog_json': str(self.folder / 'catalog.json'), 'features.plugins': False,
                  'web_search': 'disabled', 'model_providers.front.name': 'frontend',
                  'model_providers.front.base_url': self.base + '/v1', 'model_providers.front.wire_api': 'responses',
                  'model_providers.front.env_key': 'STRATA_API_KEY', 'model_providers.front.supports_websockets': False,
                  'model_providers.front.requires_openai_auth': False,
                  'model_providers.front.request_max_retries': 0, 'model_providers.front.stream_max_retries': 0}
        args = [str(CODEX), 'exec', '--json', '--skip-git-repo-check', '-s', 'workspace-write']
        for key, value in config.items():
            args += ['-c', key + '=' + json.dumps(value)]
        env = {'PATH': '/usr/bin:/bin', 'HOME': str(self.folder), 'CODEX_HOME': str(self.folder / 'codex-home'),
               'LANG': 'C.UTF-8', 'STRATA_API_KEY': self.key}
        (self.folder / 'codex-home').mkdir()
        code, out, err = self.client(args + ['write the report'], env)
        lines = [json.loads(line) for line in out.splitlines()]
        self.assertEqual(code, 0, err[-2000:])
        self.assertEqual(lines[-1]['type'], 'turn.completed')
        self.assertNotIn('error', [line['type'] for line in lines])
        self.assertEqual((self.folder / 'ws/a.txt').read_text(), 'hello\n')       # the retry's patch ran
        retry, after = self.engine.seen[1], self.engine.seen[2]
        notice = frontend.output_limit.NOTICE.format(limit=retry['max_output_tokens'], what='a tool call (apply_patch)')
        self.assertEqual(retry['input'][-1]['content'][0]['text'], notice)
        history = json.dumps(after['input'])
        self.assertNotIn('call_c1', history)                                   # the cut-off call
        self.assertNotIn('Output limit: automatic notice', history)            # the notice stays with the engine
        self.assertIn('call_r1', history)
        rollout = next((self.folder / 'codex-home/sessions').rglob('rollout-*.jsonl')).read_text()
        self.assertNotIn('"incomplete"', rollout)
        self.assertNotIn('Incomplete response returned', rollout)

    @unittest.skipUnless(CLAUDE, 'Claude Code not installed')
    def test_claude_code_gets_the_retry_in_place_of_the_cut_off_tool_use(self):
        self.engine.script = ['messages-limit-tool', 'messages-retry-ok', 'messages-text']
        (self.folder / 'ws').mkdir()
        config = self.folder / 'claude-config'
        config.mkdir()
        (config / 'settings.json').write_text('{}')
        env = {'PATH': str(Path(CLAUDE).parent) + ':/usr/bin:/bin', 'HOME': str(self.folder), 'LANG': 'C.UTF-8',
               'CLAUDE_CONFIG_DIR': str(config), 'ANTHROPIC_BASE_URL': self.base, 'ANTHROPIC_API_KEY': self.key,
               'DISABLE_TELEMETRY': '1', 'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC': '1',
               'CLAUDE_CODE_MAX_OUTPUT_TOKENS': '8192', **{name: 'qwen3.8-flash-next-iq3_xxs' for name in (
                   'ANTHROPIC_MODEL', 'ANTHROPIC_DEFAULT_HAIKU_MODEL', 'ANTHROPIC_DEFAULT_SONNET_MODEL',
                   'ANTHROPIC_DEFAULT_OPUS_MODEL', 'CLAUDE_CODE_SUBAGENT_MODEL')}}
        code, out, err = self.client([CLAUDE, '-p', 'write the report', '--setting-sources', 'user',
                                      '--output-format', 'stream-json', '--verbose', '--max-turns', '4'], env)
        self.assertEqual(code, 0, err[-2000:])
        self.assertEqual(json.loads(out.splitlines()[-1])['subtype'], 'success')
        retry, after = self.engine.seen[1], self.engine.seen[2]
        self.assertEqual(retry['messages'][-1]['content'][-1]['text'],
                         frontend.output_limit.NOTICE.format(limit=retry['max_tokens'], what='a tool call (Write)'))
        history = json.dumps(after['messages'])
        self.assertNotIn('toolu_2', history)
        self.assertNotIn('Output limit: automatic notice', history)
        self.assertIn('toolu_5', history)
        self.assertNotIn('max_tokens', out)


if __name__ == '__main__':
    unittest.main()
