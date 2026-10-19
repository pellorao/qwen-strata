import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.reviewer.api_relay import Relay, load, tier_summary
from tools.reviewer.providers import (api_provider, credential_present, link_login, process_environment, provider_config,
    release_login, shell_exclude)
from tools.safety.safety_gate import guardian_request, request_body, synthetic_login, web_search_tools

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
        self.send_response(200);self.send_header('Content-Type','text/event-stream')
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
            self.assertEqual(shell_exclude(provider),['BENCHMARK_DEEPSEEK_API_KEY','BENCHMARK_OPENAI_API_KEY','STRATA_API_KEY',
                                                      'STRATA_REMOTE_PASSWORD'])
            env={'BENCHMARK_DEEPSEEK_API_KEY':'d','BENCHMARK_OPENAI_API_KEY':'o','PATH':'/bin','STRATA_API_KEY':'s'}
            self.assertEqual(process_environment(provider,env),{'PATH':'/bin','STRATA_API_KEY':'s'})
            deepseek=api_provider({'provider':{'id':'deepseek','base_url':'https://api.deepseek.com'}})
            self.assertEqual(sorted(process_environment(deepseek,env)),['BENCHMARK_DEEPSEEK_API_KEY','PATH','STRATA_API_KEY'])
            for bad in ({'id':'openai'},{'id':'openai','auth_home':'relative'},{'id':'openai','auth_home':tmp,'env_key':'X_KEY'},
                        {'id':'openai','auth_home':str(Path(__file__).resolve().parents[1]/'x')},
                        {'id':'deepseek','base_url':'https://api.deepseek.com','auth_home':tmp},
                        {'id':'deepseek','auth':'chatgpt','auth_home':tmp}):
                with self.assertRaises(ValueError):api_provider({'provider':bad})

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
