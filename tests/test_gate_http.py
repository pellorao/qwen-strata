import http.client
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import json

from tools.safety.gate_http import read_json_request, read_request_raw


class Echo(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        raw = read_request_raw(self)
        if raw is None:
            return
        self.send_response(200)
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class JsonEcho(Echo):
    def do_POST(self):
        body = read_json_request(self, json.loads)
        if body is None:
            return
        self.send_response(200)
        self.send_header('Content-Length', '0')
        self.end_headers()


class ServerCase(unittest.TestCase):
    handler = Echo

    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), self.handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def post(self, headers, body=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        conn.putrequest('POST', '/')
        for k, v in headers.items():
            conn.putheader(k, v)
        conn.endheaders(body)
        reply = conn.getresponse()
        data = reply.read()
        conn.close()
        return reply.status, data


class ReadRequestRawTest(ServerCase):
    def test_content_length_body_is_read(self):
        self.assertEqual(self.post({'Content-Length': '2'}, b'{}'), (200, b'{}'))

    def test_chunked_is_refused(self):
        status, _ = self.post({'Transfer-Encoding': 'chunked'}, b'2\r\n{}\r\n0\r\n\r\n')
        self.assertEqual(status, 501)

    def test_missing_length_is_refused(self):
        status, _ = self.post({})
        self.assertEqual(status, 411)


class ReadJsonRequestTest(ServerCase):
    handler = JsonEcho

    def test_empty_and_malformed_bodies_get_400(self):
        self.assertEqual(self.post({'Content-Length': '0'}, b'')[0], 400)
        self.assertEqual(self.post({'Content-Length': '3'}, b'{x}')[0], 400)

    def test_valid_body_is_accepted(self):
        self.assertEqual(self.post({'Content-Length': '2'}, b'{}')[0], 200)


if __name__ == '__main__':
    unittest.main()