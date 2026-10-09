"""Model identity is checked before either API can forward inference."""
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from responses_bridge import Handler, ModelSelectionError, bind_loaded_model
from service_access import AccessError

Q2 = 'qwen3.8-flash-next-q2_0'
IQ2 = 'qwen3.8-flash-next-iq2_xs'
IQ3 = 'qwen3.8-flash-next-iq3_xxs'


class Upstream(io.BytesIO):
    status = 200
    headers = {'Content-Type': 'text/event-stream'}


class ModelSelectionTests(unittest.TestCase):
    def ownership(self, state):
        return SimpleNamespace(require=Mock(), status=Mock(return_value=state),
            backend=SimpleNamespace(request_defaults=lambda: {}))

    def handler(self, path, request, state):
        raw = json.dumps(request).encode()
        handler = Handler.__new__(Handler)
        handler.path = path
        handler.headers = {'Content-Length': str(len(raw)), 'Authorization': 'Bearer fixture-key'}
        handler.client_address = ('127.0.0.1', 1234)
        handler.rfile, handler.wfile = io.BytesIO(raw), io.BytesIO()
        handler.server = SimpleNamespace(ownership=self.ownership(state), backend='http://unused.invalid', trace=None)
        handler.send_json, handler.send_response = Mock(), Mock()
        handler.send_header, handler.end_headers = Mock(), Mock()
        return handler

    def request(self, path, **extra):
        return dict({'messages': [{'role': 'user', 'content': 'synthetic'}]}
                    if path.endswith('/chat/completions') else {'input': 'synthetic'}, **extra)

    def test_mismatches_are_http409_before_forwarding_or_streaming(self):
        for path in ('/v1/chat/completions', '/v1/responses', '/responses'):
            for stream in (False, True):
                with self.subTest(path=path, stream=stream):
                    handler = self.handler(path, self.request(path, model=IQ3, stream=stream),
                                           {'status': 'running', 'model': Q2})
                    with patch('responses_bridge.urllib.request.build_opener') as upstream:
                        handler.do_POST()
                    upstream.assert_not_called()
                    handler.send_response.assert_not_called()
                    status, body = handler.send_json.call_args.args
                    self.assertEqual((status, body['error']['code']), (409, 'model_mismatch'))
                    handler.server.ownership.status.assert_called_once_with('fixture-key')

    def test_not_ready_or_unknown_model_identity_fails_closed(self):
        for state in ({'status': 'stopped'}, {'status': 'unloaded', 'model': Q2},
                      {'status': 'running'}, None):
            for path in ('/v1/chat/completions', '/v1/responses'):
                handler = self.handler(path, self.request(path, model=Q2), state)
                with patch('responses_bridge.urllib.request.build_opener') as upstream:
                    handler.do_POST()
                upstream.assert_not_called()
                status, body = handler.send_json.call_args.args
                self.assertEqual((status, body['error']['code']), (503, 'model_not_ready'))

    def test_omitted_model_tracks_current_loaded_model_for_both_apis(self):
        events = b'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
        for model in (Q2, IQ2, IQ3, Q2):
            for path in ('/v1/chat/completions', '/v1/responses'):
                with self.subTest(model=model, path=path):
                    handler = self.handler(path, self.request(path), {'status': 'running', 'model': model})
                    with patch('responses_bridge.urllib.request.build_opener') as factory:
                        factory.return_value.open.return_value = Upstream(events)
                        handler.do_POST()
                    outgoing = factory.return_value.open.call_args.args[0]
                    self.assertEqual(json.loads(outgoing.data)['model'], model)
                    if path.endswith('/responses'):
                        self.assertEqual(handler.send_json.call_args.args[1]['model'], model)

    def test_matching_model_and_explicit_generation_values_are_preserved(self):
        ownership = self.ownership({'status': 'running', 'model': IQ2})
        request = {'model': IQ2, 'temperature': .7, 'reasoning_effort': 'low'}
        self.assertEqual(bind_loaded_model(request, ownership, 'fixture-key'), request)
        ownership.status.side_effect = AccessError('Invalid key.')
        with self.assertRaises(AccessError):
            bind_loaded_model(request, ownership, 'invalid-key')

    def test_model_and_request_types_are_checked(self):
        ownership = self.ownership({'status': 'running', 'model': Q2})
        for request in ([], None, {'model': None}, {'model': 123}, {'model': ''}):
            with self.assertRaises(ModelSelectionError) as caught:
                bind_loaded_model(request, ownership, 'fixture-key')
            self.assertEqual(caught.exception.status, 400)

    def test_unavailable_status_does_not_fall_back_to_old_model(self):
        ownership = self.ownership({})
        ownership.status.side_effect = OSError('synthetic unavailable service')
        with self.assertRaises(ModelSelectionError) as caught:
            bind_loaded_model({'model': Q2}, ownership, 'fixture-key')
        self.assertEqual((caught.exception.status, caught.exception.code), (503, 'model_not_ready'))


if __name__ == '__main__':
    unittest.main()
