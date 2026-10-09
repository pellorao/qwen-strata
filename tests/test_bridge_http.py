import json, sys, time, threading, unittest, urllib.request, urllib.error, tempfile
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from responses_bridge import Handler
class Backend(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        req=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if req['messages'][-1]['content']=='reject':
            body=b'{"error":{"message":"fixture failure"}}';self.send_response(400);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
        if req['messages'][-1]['content']=='stall_headers':time.sleep(.2)
        self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
        if req['messages'][-1]['content']=='stall_body':
            self.wfile.write(b': heartbeat\n\n');self.wfile.flush();time.sleep(.2);return
        if req['messages'][-1]['content']=='stall_headers':return
        if req['messages'][-1]['content']=='unknown_tool':
            value={'choices':[{'delta':{'tool_calls':[{'index':0,'function':{'name':'missing','arguments':'{}'}}]},'finish_reason':'tool_calls'}]}
            self.wfile.write(('data: '+json.dumps(value)+'\n\ndata: [DONE]\n\n').encode());self.wfile.flush();return
        if req['messages'][-1]['content']=='stream_fail':
            for value in [{'choices':[{'delta':{'content':'partial'}}]},{'error':{'message':'engine silent; the next request restarts it'}}]:
                self.wfile.write(('data: '+json.dumps(value)+'\n\n').encode());self.wfile.flush()
            return
        for value in [{'choices':[{'delta':{'content':'Hello '}}]},{'choices':[{'delta':{'content':'world'},'finish_reason':'stop'}]},{'choices':[],'usage':{'prompt_tokens':200000,'completion_tokens':2,'total_tokens':200002}}]:
            self.wfile.write(('data: '+json.dumps(value)+'\n\n').encode());self.wfile.flush()
        self.wfile.write(b'data: [DONE]\n\n')
class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backend=ThreadingHTTPServer(('127.0.0.1',0),Backend)
        cls.bridge=ThreadingHTTPServer(('127.0.0.1',0),Handler);cls.bridge.backend='http://127.0.0.1:'+str(cls.backend.server_port);cls.bridge.trace=None
        for server in (cls.backend,cls.bridge):threading.Thread(target=server.serve_forever,daemon=True).start()
    @classmethod
    def tearDownClass(cls):
        for server in (cls.bridge,cls.backend):server.shutdown();server.server_close()
    def request(self,text,stream=False):
        req=urllib.request.Request('http://127.0.0.1:'+str(self.bridge.server_port)+'/v1/responses',json.dumps({'input':text,'stream':stream}).encode(),{'Content-Type':'application/json'})
        return urllib.request.urlopen(req,timeout=5)
    def assert_failed(self,events,code):
        self.assertEqual(events[-1]['type'],'response.failed')
        response=events[-1]['response']
        self.assertEqual(response['status'],'failed')
        self.assertEqual(response['id'],events[0]['response']['id'])
        self.assertEqual(response['error']['code'],'server_error')
        self.assertIn('['+code+']',response['error']['message'])
        self.assertEqual([e['sequence_number'] for e in events],list(range(len(events))))
        self.assertNotIn('response.completed',[e['type'] for e in events])
        return response
    def test_nonstream_usage(self):
        with self.request('ok') as response:d=json.load(response)
        self.assertEqual(d['output'][0]['content'][0]['text'],'Hello world');self.assertEqual(d['usage']['input_tokens'],200000)

    def test_owned_model_mismatch_is_http409_without_upstream_request(self):
        self.bridge.ownership=SimpleNamespace(require=lambda key:None,
            status=lambda key:{'status':'running','model':'qwen3.8-flash-next-q2_0'},
            backend=SimpleNamespace(request_defaults=lambda:{}))
        try:
            with patch.object(Backend,'do_POST',autospec=True) as upstream:
                for path in ('/v1/chat/completions','/v1/responses','/responses'):
                    for stream in (False,True):
                        body={'model':'qwen3.8-flash-next-iq3_xxs','stream':stream,
                              'input':'synthetic','messages':[{'role':'user','content':'synthetic'}]}
                        request=urllib.request.Request('http://127.0.0.1:'+str(self.bridge.server_port)+path,
                            json.dumps(body).encode(),{'Content-Type':'application/json','Authorization':'Bearer fixture-key'})
                        with self.assertRaises(urllib.error.HTTPError) as caught:
                            urllib.request.urlopen(request,timeout=5)
                        with caught.exception as response:
                            self.assertEqual(response.code,409)
                            self.assertEqual(json.load(response)['error']['code'],'model_mismatch')
                upstream.assert_not_called()
        finally:
            del self.bridge.ownership
    def test_client_allowlist_rejects_health_and_inference(self):
        self.bridge.allowed_clients={'192.0.2.7'}
        try:
            for action in (lambda:self.request('ok'),lambda:urllib.request.urlopen('http://127.0.0.1:'+str(self.bridge.server_port)+'/health',timeout=5)):
                with self.assertRaises(urllib.error.HTTPError) as caught:action()
                self.assertEqual(caught.exception.code,403);caught.exception.close()
        finally:self.bridge.allowed_clients=None
    def test_stream_events(self):
        with self.request('ok',True) as response:lines=response.read().decode().splitlines()
        events=[json.loads(x[6:]) for x in lines if x.startswith('data: ')]
        self.assertEqual(events[0]['type'],'response.created');self.assertEqual(events[-1]['type'],'response.completed')
        self.assertEqual(''.join(x.get('delta','') for x in events),'Hello world')
    def test_mid_stream_error_is_not_completed_and_next_request_works(self):
        with self.request('stream_fail',True) as response:lines=response.read().decode().splitlines()
        events=[json.loads(x[6:]) for x in lines if x.startswith('data: ')]
        failed=self.assert_failed(events,'upstream_error')
        self.assertIn('engine silent',failed['error']['message'])
        self.assertEqual(failed['output'][0]['content'][0]['text'],'partial')
        self.assertEqual(failed['output'][0]['status'],'in_progress')
        with self.request('ok') as response:self.assertEqual(json.load(response)['output'][0]['content'][0]['text'],'Hello world')
    def test_invalid_model_tool_has_diagnostic_error_and_trace(self):
        with tempfile.TemporaryDirectory() as folder:
            self.bridge.trace=Path(folder)
            try:
                with self.request('unknown_tool',True) as response:lines=response.read().decode().splitlines()
                events=[json.loads(x[6:]) for x in lines if x.startswith('data: ')]
                failed=self.assert_failed(events,'invalid_response')
                self.assertIn('unknown tool',failed['error']['message'])
                errors=list(Path(folder).glob('*-error.json'));self.assertEqual(len(errors),1)
                error=json.loads(errors[0].read_text());self.assertEqual(error['error_type'],'ValueError')
                self.assertEqual(error['tool_calls']['0']['name'],'missing')
                self.assertNotIn('args',error['tool_calls']['0'])
                self.assertNotIn('message',error)
            finally:self.bridge.trace=None
    def test_nonstream_backend_generation_failure_is_503(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:self.request('stream_fail')
        self.assertEqual(caught.exception.code,503)
        self.assertIn('upstream_error',caught.exception.read().decode());caught.exception.close()
    def test_timeout_before_headers_is_504_and_next_request_works(self):
        self.bridge.upstream_timeout=.05
        try:
            with self.assertRaises(urllib.error.HTTPError) as caught:self.request('stall_headers')
            self.assertEqual(caught.exception.code,504);self.assertIn('upstream_timeout',caught.exception.read().decode());caught.exception.close()
        finally:self.bridge.upstream_timeout=900
        with self.request('ok') as response:self.assertEqual(json.load(response)['output'][0]['content'][0]['text'],'Hello world')
    def test_timeout_after_stream_headers_is_error_not_completion(self):
        self.bridge.upstream_timeout=.05
        try:
            with self.request('stall_body',True) as response:lines=response.read().decode().splitlines()
            events=[json.loads(x[6:]) for x in lines if x.startswith('data: ')]
            self.assert_failed(events,'upstream_timeout')
        finally:self.bridge.upstream_timeout=900
    def test_connection_refused_is_503(self):
        original=self.bridge.backend;self.bridge.backend='http://127.0.0.1:1'
        try:
            with self.assertRaises(urllib.error.HTTPError) as caught:self.request('ok')
            self.assertEqual(caught.exception.code,503);self.assertIn('upstream_error',caught.exception.read().decode());caught.exception.close()
        finally:self.bridge.backend=original
    def test_backend_error_propagates(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:self.request('reject')
        self.assertEqual(caught.exception.code,400);self.assertIn('fixture failure',caught.exception.read().decode());caught.exception.close()
if __name__=='__main__':unittest.main()
