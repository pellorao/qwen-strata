import concurrent.futures
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from native_service import guarded_handler
from responses_bridge import Handler
from service_access import Ownership


class Lifecycle:
    def __init__(self): self.running=False;self.calls=[]
    def stopped(self): return not self.running
    def start(self,options): self.calls.append(('start',options));self.running=True;return {'status':'running'}
    def stop(self): self.calls.append(('stop',));self.running=False;return {'status':'stopped'}
    def status(self): return {'status':'running' if self.running else 'stopped'}


class Native(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def _json(self,status,value):
        raw=json.dumps(value).encode();self.send_response(status)
        self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self): self._json(200,{'status':'ok'})
    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length',0)))
        self._json(200,{'choices':[{'message':{'content':'MODEL-RESULT'}}]})
    def do_OPTIONS(self): self._json(200,{})


class ControllerHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'access.json'
        self.backend=Lifecycle();self.owner=Ownership(self.path,self.backend)
        self.native=ThreadingHTTPServer(('127.0.0.1',0),guarded_handler(Native,self.path,'private-maintenance'))
        self.bridge=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.bridge.backend=f'http://127.0.0.1:{self.native.server_port}'
        self.bridge.trace=None;self.bridge.allowed_clients={'127.0.0.1'};self.bridge.ownership=self.owner
        for server in (self.native,self.bridge): threading.Thread(target=server.serve_forever,daemon=True).start()

    def tearDown(self):
        for server in (self.bridge,self.native):server.shutdown();server.server_close()
        self.temp.cleanup()

    def call(self,path,body=None,key=None,native=False,method=None):
        server=self.native if native else self.bridge
        headers={'Content-Type':'application/json'}
        if key is not None:headers['Authorization']='Bearer '+key
        request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}{path}',
            None if body is None else json.dumps(body).encode(),headers,method=method)
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=5) as response:
                return response.status,json.load(response)
        except urllib.error.HTTPError as error:
            try: return error.code,json.load(error)
            finally: error.close()

    def test_http_key_controls_every_model_operation_and_chat_passthrough(self):
        key=self.call('/ownership/acquire',{})[1]['key']
        for path in ('/ownership/start','/ownership/stop','/ownership/release','/v1/chat/completions','/v1/responses'):
            self.assertEqual(self.call(path,{},'wrong')[0],403)
        self.assertEqual(self.call('/ownership/status',key='wrong')[0],403)
        self.assertEqual(self.call('/ownership/acquire',{})[0],409)
        self.assertEqual(self.call('/ownership/start',{'model':'Q2_0'},key)[0],200)
        self.assertEqual(self.call('/v1/chat/completions',{},key)[1]['choices'][0]['message']['content'],'MODEL-RESULT')
        for path,body in (('/health',None),('/v1/models',None),('/unload',{}),('/settings',{}),('/v1/chat/completions',{})):
            self.assertEqual(self.call(path,body,'wrong',native=True)[0],403)
        self.assertEqual(self.call('/ownership/release',{},key)[0],200)
        self.assertFalse(self.backend.running)
        self.assertEqual(self.call('/v1/chat/completions',{},key,native=True)[0],403)
        self.assertEqual(self.call('/ownership/start',{},key)[0],403)
        self.assertNotEqual(self.call('/ownership/acquire',{})[1]['key'],key)

    def test_http_concurrent_acquire_has_one_winner(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            statuses=list(pool.map(lambda _:self.call('/ownership/acquire',{})[0],range(12)))
        self.assertEqual(statuses.count(200),1);self.assertEqual(statuses.count(409),11)

    def test_native_maintenance_key_cannot_generate_or_change_settings(self):
        self.assertEqual(self.call('/health',key='private-maintenance',native=True)[0],200)
        for path in ('/v1/chat/completions','/settings','/load'):
            self.assertEqual(self.call(path,{},'private-maintenance',native=True)[0],403)


if __name__=='__main__': unittest.main()
