import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import fast_servers  # noqa: E401,F401
import json
import os
import socket
import struct
import time
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.reviewer.api_relay import Fields, Relay, load, tier_summary
from tools.reviewer.providers import (api_provider, credential_present, link_login, process_environment, provider_config,
    release_login, shell_exclude)
from tools.safety.safety_gate import guardian_request, rate_limit_header, request_body, synthetic_login, web_search_tools

SECRET='Bearer synthetic-secret-token'


class Upstream(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass
    def do_POST(self):
        self.server.seen.append({'path':self.path,'auth':self.headers.get('Authorization'),
                                 'body':self.rfile.read(int(self.headers['Content-Length']))})
        events=[{'type':'response.created','response':{'id':'resp_1','model':'gpt-x','status':'in_progress'}},
                {'type':'response.completed','response':{'id':'resp_1','model':'gpt-x','status':'completed',
                 'service_tier':'default','usage':{'input_tokens':9,'output_tokens':2}}}]
        body=''.join('data: '+json.dumps(e)+'\n\n' for e in events).encode()
        if getattr(self.server,'json_body',False):body=json.dumps({**events[-1]['response'],'object':'response'}).encode()
        self.send_response(200)
        ctype=getattr(self.server,'ctype','text/event-stream')
        if ctype:self.send_header('Content-Type',ctype)
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)


class RelayTests(unittest.TestCase):
    def test_relay_forwards_unchanged_and_keeps_only_reply_fields(self):
        upstream=ThreadingHTTPServer(('127.0.0.1',0),Upstream);upstream.seen=[]
        threading.Thread(target=upstream.serve_forever,daemon=True).start()
        try:
            with tempfile.TemporaryDirectory()as tmp, Relay(f'http://127.0.0.1:{upstream.server_port}/backend',tmp) as relay:
                request=urllib.request.Request(relay.url+'/responses',b'{"input":"x"}',
                    {'Authorization':SECRET,'Content-Type':'application/json'},method='POST')
                with urllib.request.urlopen(request)as reply:text=reply.read().decode()
                self.assertIn('response.completed',text)
                self.assertEqual(upstream.seen,[{'path':'/backend/responses','auth':SECRET,'body':b'{"input":"x"}'}])
                ws=urllib.request.Request(relay.url+'/responses',headers={'Upgrade':'websocket','Connection':'Upgrade'})
                with self.assertRaises(urllib.error.HTTPError)as refused:urllib.request.urlopen(ws)
                self.assertEqual(refused.exception.code,426)
                rows=load(Path(tmp)/'relay.jsonl');written=(Path(tmp)/'relay.jsonl').read_text()
                self.assertNotIn('synthetic-secret',written);self.assertNotIn('"input"',written)
                self.assertEqual((rows[0]['service_tier'],rows[0]['model'],rows[0]['usage']['output_tokens']),('default','gpt-x',2))
                summary=relay.summary()
                self.assertEqual((summary['requests'],summary['websocket_refused'],summary['service_tiers']),(1,1,{'default':1}))
        finally:
            upstream.shutdown();upstream.server_close()

    def test_incomplete_response_keeps_its_reason(self):
        fields=Fields()
        event={'type':'response.incomplete','response':{'id':'r1','status':'incomplete',
            'incomplete_details':{'reason':'max_output_tokens'},'usage':{'output_tokens':8192}}}
        fields.feed(b'data: '+json.dumps(event).encode()+b'\n')
        self.assertEqual((fields.values['response_status'],fields.values['incomplete_details']),('incomplete',{'reason':'max_output_tokens'}))
        done=Fields();done.feed(b'data: '+json.dumps({'type':'response.completed','response':{'status':'completed','incomplete_details':None}}).encode()+b'\n')
        self.assertNotIn('incomplete_details',done.values)

    def test_reply_without_content_type_is_scanned_and_refusal_is_no_error(self):
        # The ChatGPT backend streams SSE with no Content-Type (2026-10-20); a plain JSON reply still parses.
        for json_body in (False,True):
            upstream=ThreadingHTTPServer(('127.0.0.1',0),Upstream);upstream.seen=[];upstream.ctype=None;upstream.json_body=json_body
            threading.Thread(target=upstream.serve_forever,daemon=True).start()
            try:
                with tempfile.TemporaryDirectory()as tmp, Relay(f'http://127.0.0.1:{upstream.server_port}',tmp) as relay:
                    ws=urllib.request.Request(relay.url+'/responses',headers={'Upgrade':'websocket','Connection':'Upgrade'})
                    with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(ws)
                    with urllib.request.urlopen(urllib.request.Request(relay.url+'/responses',b'{}',method='POST'))as reply:reply.read()
                    summary=relay.summary()
                    self.assertEqual((summary['models'],summary['service_tiers'],summary['errors'],summary['websocket_refused']),
                                     ({'gpt-x':1},{'default':1},0,1))
            finally:
                upstream.shutdown();upstream.server_close()
        self.assertEqual(tier_summary([{'started_at':1,'status':502}])['errors'],1)

    def test_error_rows_say_which_side_failed(self):
        class Bad(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def log_message(self,*args):pass
            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length') or 0))
                mode=self.path
                if mode=='/status':
                    body=b'{}';self.send_response(502);self.send_header('Content-Length','2');self.end_headers();self.wfile.write(body)
                elif mode=='/cut':  # sends one chunk, then closes without the end chunk: upstream stream cut after 200
                    self.send_response(200);self.send_header('Content-Type','text/event-stream')
                    self.send_header('Transfer-Encoding','chunked');self.end_headers()
                    self.wfile.write(b'b\r\ndata: {}\n\n\r\n');self.wfile.flush()
                    self.close_connection=True
                else:  # long stream the client abandons
                    self.send_response(200);self.send_header('Content-Type','text/event-stream')
                    self.send_header('Content-Length',str(64<<20));self.end_headers()
                    try:
                        for _ in range(64):self.wfile.write(b'x'*(1<<20));self.wfile.flush()
                    except OSError:pass
                    self.close_connection=True
        upstream=ThreadingHTTPServer(('127.0.0.1',0),Bad)
        threading.Thread(target=upstream.serve_forever,daemon=True).start()
        try:
            with tempfile.TemporaryDirectory()as tmp, Relay(f'http://127.0.0.1:{upstream.server_port}',tmp) as relay:
                with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(urllib.request.Request(relay.url+'/status',b'{}',method='POST'))
                try:
                    with urllib.request.urlopen(urllib.request.Request(relay.url+'/cut',b'{}',method='POST'))as reply:reply.read()
                except Exception:pass
                body=b'{}'
                with socket.create_connection(('127.0.0.1',int(relay.url.rsplit(':',1)[1])))as conn:  # reads the head, then drops
                    conn.sendall(b'POST /drop HTTP/1.1\r\nHost: x\r\nContent-Length: 2\r\n\r\n'+body);conn.recv(100)
                    conn.setsockopt(socket.SOL_SOCKET,socket.SO_LINGER,struct.pack('ii',1,0))  # RST on close
                deadline=time.time()+10
                while len(relay.rows)<3 and time.time()<deadline:time.sleep(0.05)
                by={r['path']:r for r in relay.rows}
                self.assertEqual((by['/status']['status'],by['/status']['error_side'],'transport_error' in by['/status']),(502,'upstream',False))
                self.assertEqual((by['/cut']['status'],by['/cut']['error_side']),(200,'upstream'))
                self.assertEqual((by['/drop']['status'],by['/drop']['error_side']),(200,'client'))
            dead=ThreadingHTTPServer(('127.0.0.1',0),Bad);port=dead.server_port;dead.server_close()
            with tempfile.TemporaryDirectory()as tmp, Relay(f'http://127.0.0.1:{port}',tmp) as relay:  # nothing listens
                try:urllib.request.urlopen(urllib.request.Request(relay.url+'/x',b'{}',method='POST'))
                except Exception:pass
                self.assertEqual((relay.rows[0]['status'],relay.rows[0]['error_side']),(None,'upstream'))
        finally:
            upstream.shutdown();upstream.server_close()

    def test_tier_summary_window_and_missing_tier(self):
        rows=[{'started_at':1,'service_tier':'flex'},{'started_at':5,'status':200},{'started_at':9,'service_tier':'default'}]
        self.assertEqual(tier_summary(rows,2,8)['service_tiers'],{'not-returned':1})
        self.assertEqual(tier_summary(rows)['service_tiers'],{'flex':1,'not-returned':1,'default':1})


class ChatgptLoginTests(unittest.TestCase):
    def provider(self,home):
        return api_provider({'provider':{'id':'openai','auth_home':home}})

    def test_chatgpt_is_the_openai_default_and_uses_the_builtin_provider(self):
        with tempfile.TemporaryDirectory()as tmp:
            provider=self.provider(tmp)
            self.assertEqual((provider['auth'],provider['codex_id'],provider['env_key']),('chatgpt','openai',None))
            self.assertEqual(provider_config(provider,'http://127.0.0.1:9'),{'openai_base_url':'http://127.0.0.1:9'})
            self.assertEqual(shell_exclude(provider),['BENCHMARK_OPENAI_API_KEY','DEEPSEEK_API_KEY','STRATA_API_KEY',
                                                      'STRATA_REMOTE_PASSWORD','*_API_KEY','*_TOKEN','*_SECRET'])
            # Synthetic values; a key under a new name (wildcard shapes) is dropped as well.
            env={'DEEPSEEK_API_KEY':'d','BENCHMARK_OPENAI_API_KEY':'o','PATH':'/bin','STRATA_API_KEY':'s',
                 'ANTHROPIC_API_KEY':'a','GH_TOKEN':'g','aws_secret':'x','TOKENIZERS_PARALLELISM':'false'}
            self.assertEqual(process_environment(provider,env),{'PATH':'/bin','STRATA_API_KEY':'s','TOKENIZERS_PARALLELISM':'false'})
            deepseek=api_provider({'provider':{'id':'deepseek','base_url':'https://api.deepseek.com'}})
            self.assertEqual(deepseek['env_key'],'DEEPSEEK_API_KEY')
            self.assertEqual(sorted(process_environment(deepseek,env)),['DEEPSEEK_API_KEY','PATH','STRATA_API_KEY','TOKENIZERS_PARALLELISM'])
            self.assertEqual(shell_exclude(deepseek)[0],'DEEPSEEK_API_KEY')
            for bad in ({'id':'openai'},{'id':'openai','auth_home':'relative'},{'id':'openai','auth_home':tmp,'env_key':'X_KEY'},
                        {'id':'openai','auth_home':str(Path(__file__).resolve().parents[1]/'x')},
                        {'id':'deepseek','base_url':'https://api.deepseek.com','auth_home':tmp},
                        {'id':'deepseek','auth':'chatgpt','auth_home':tmp}):
                with self.assertRaises(ValueError):api_provider({'provider':bad})

    def test_gate_passes_back_only_plan_usage_headers(self):
        self.assertTrue(rate_limit_header('X-Codex-Primary-Used-Percent'))
        self.assertTrue(rate_limit_header('x-codex-secondary-reset-at'))
        for name in ('Set-Cookie','Authorization','openai-organization','Content-Type'):
            self.assertFalse(rate_limit_header(name))

    def test_link_and_release_never_copy_the_login(self):
        with tempfile.TemporaryDirectory()as tmp:
            home=synthetic_login(tmp);provider=self.provider(home);run=Path(tmp)/'run/codex-home'
            self.assertTrue(credential_present(provider))
            link=Path(link_login(provider,run));self.assertTrue(link.is_symlink())
            self.assertEqual(os.readlink(link),str(Path(home)/'auth.json'))
            with self.assertRaises(ValueError):link_login(provider,run)
            self.assertEqual(release_login(provider,run),'link-removed');self.assertFalse(os.path.lexists(link))
            # Codex refreshed the login by writing a new file in place of the link: it moves back, none stays behind.
            link_login(provider,run);link.unlink();link.write_text('{"refreshed":true}')
            self.assertEqual(release_login(provider,run),'refreshed-file-moved-back')
            self.assertFalse(os.path.lexists(link));self.assertIn('refreshed',(Path(home)/'auth.json').read_text())
            self.assertEqual(release_login(provider,run),'missing')
            self.assertFalse(credential_present(self.provider(str(Path(tmp)/'empty'))))


class GateHelperTests(unittest.TestCase):
    def test_guardian_request_and_web_search_tools(self):
        meta={'client_metadata':{'x-codex-turn-metadata':json.dumps({'thread_source':'guardian_review'})}}
        self.assertTrue(guardian_request(meta))
        self.assertFalse(guardian_request({'client_metadata':{'x-codex-turn-metadata':'{bad'}}))
        self.assertFalse(guardian_request({'reasoning':{'effort':'low'}}))
        self.assertTrue(guardian_request({'client_metadata':{'x-openai-subagent':'guardian'}}))
        from compression import zstd
        import gzip
        self.assertEqual(request_body({'Content-Encoding':'zstd'},zstd.compress(b'{"a":1}')),{'a':1})
        self.assertEqual(request_body({'Content-Encoding':'gzip'},gzip.compress(b'{"a":2}')),{'a':2})
        self.assertEqual(request_body({},b'{"a":3}'),{'a':3})
        with self.assertRaises(ValueError):request_body({'Content-Encoding':'br'},b'x')
        with tempfile.TemporaryDirectory()as tmp:
            folder=Path(tmp)
            (folder/'request-1.json').write_text(json.dumps({'tools':[{'type':'function','name':'shell'}]}))
            self.assertEqual(web_search_tools(folder),0)
            (folder/'request-2.json').write_text(json.dumps({'tools':[{'type':'web_search'},{'type':'function','name':'WebFetch'}]}))
            (folder/'request-2-time.json').write_text('{}')
            self.assertEqual(web_search_tools(folder),2)


if __name__=='__main__':
    unittest.main()
