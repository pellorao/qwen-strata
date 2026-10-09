import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from brave_search import BraveSearch, SearchError, fetch_public, page_text, public_url, search_tool
from hosted_search import combined_usage, run_hosted
from responses_bridge import Handler, Translator, to_chat
from service_access import Ownership


class Lifecycle:
    running = False
    def stopped(self): return not self.running
    def start(self, options): self.running = True; return {}
    def stop(self): self.running = False; return {}
    def status(self): return {'status': 'running' if self.running else 'stopped'}


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.calls = []
        self.search = BraveSearch(self.temp.name, self.transport)
        self.search.key_file.write_text('unit-test-secret')

    def tearDown(self): self.temp.cleanup()

    def transport(self, url, headers, check, **kwargs):
        check(); self.calls.append((url, headers, kwargs))
        if url.startswith('https://api.search.brave.com/'):
            return url, 'application/json', json.dumps({'web': {'results': [
                {'url': 'https://example.org/docs', 'title': 'Docs', 'description': 'Indexed alpha excerpt.'}]}}).encode()
        return url, 'text/html', b'<html><title>Page</title><script>secret script</script><p>Live beta content.</p></html>'

    def execute(self, args, live=False, **fields):
        return self.search.execute('owner', args, {'type': 'web_search', 'external_web_access': live, **fields}, lambda: None)

    def test_native_text_content_type_is_supported_and_images_fail_explicitly(self):
        for content in (None, ['text']):
            tool = search_tool({'type': 'web_search', 'search_content_types': content})
            self.assertEqual(tool['name'], 'strata_web_search')
        for content in ([], ['image'], ['text', 'image'], 'text'):
            with self.subTest(content=content), self.assertRaisesRegex(ValueError, 'Only text'):
                search_tool({'type': 'web_search', 'search_content_types': content})

    def test_indexed_open_and_find_do_not_fetch_website(self):
        result = self.execute({'action': 'search', 'query': 'alpha'})
        ref = result['results'][0]['ref']
        opened = self.execute({'action': 'open_page', 'url': ref})
        found = self.execute({'action': 'find_in_page', 'url': ref, 'pattern': 'alpha'})
        self.assertTrue(opened['results'][0]['indexed_excerpt'])
        self.assertEqual(len(found['results'][0]['matches']), 1)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][1]['X-Subscription-Token'], 'unit-test-secret')
        self.assertTrue(self.execute({'action':'open_page','url':'https://example.org/docs'})['results'][0]['indexed_excerpt'])
        with self.assertRaisesRegex(SearchError, 'Indexed mode'):
            self.execute({'action': 'open_page', 'url': 'https://example.org/not-indexed'})

    def test_live_fetch_sends_no_brave_key_and_extracts_text(self):
        result = self.execute({'action': 'open_page', 'url': 'https://example.org/docs'}, live=True)
        self.assertFalse(result['results'][0]['indexed_excerpt'])
        self.assertIn('Live beta content', result['results'][0]['text'])
        self.assertNotIn('secret script', result['results'][0]['text'])
        self.assertNotIn('X-Subscription-Token', self.calls[0][1])

    def test_private_references_persist_and_are_not_shared_across_owners(self):
        ref = self.execute({'action': 'search', 'query': 'alpha'})['results'][0]['ref']
        restarted = BraveSearch(self.temp.name, self.transport)
        self.assertTrue(restarted.execute('owner', {'action': 'open_page', 'url': ref}, {'type': 'web_search', 'external_web_access': False}, lambda: None)['results'])
        with self.assertRaises(SearchError):
            restarted.execute('other', {'action': 'open_page', 'url': ref}, {'type': 'web_search', 'external_web_access': False}, lambda: None)

    def test_missing_key_errors_without_disclosing_contents(self):
        self.search.key_file.unlink()
        with self.assertRaises(SearchError) as caught: self.execute({'action': 'search', 'query': 'alpha'})
        self.assertEqual(caught.exception.code, 'not_configured')
        self.assertEqual(self.calls, [])

    def test_explicit_private_and_invalid_urls_block_before_connection(self):
        for url in ('file:///etc/passwd', 'http://user:key@example.org/', 'https://example.org:9999/',
                    'http://127.0.0.1/', 'http://10.1.2.3/', 'http://169.254.169.254/', 'http://[::1]/',
                    'http://192.0.2.1/', 'http://localhost/', 'http://service.local/'):
            with self.assertRaises(SearchError): public_url(url)

    def test_domain_restriction_applies_before_fetch(self):
        with self.assertRaisesRegex(SearchError, 'outside allowed_domains'):
            self.execute({'action': 'open_page', 'url': 'https://other.org/'}, live=True, filters={'allowed_domains': ['example.org']})
        self.assertEqual(self.calls, [])
        with self.assertRaises(SearchError):
            fetch_public('https://other.org/', {}, lambda: None, domains=['example.org'])

    def test_standard_http_client_receives_hostname_without_custom_dns_or_proxy(self):
        reply=io.BytesIO(b'body');reply.headers={'Content-Type':'text/plain'}
        opener=MagicMock();opener.open.return_value=reply
        with patch('brave_search.urllib.request.build_opener',return_value=opener) as build, patch('socket.getaddrinfo') as resolve:
            result=fetch_public('https://api.search.brave.com/res/v1/web/search?q=test',{'X-Subscription-Token':'secret'},lambda:None)
            self.assertEqual(result[2],b'body')
            self.assertEqual(opener.open.call_args.args[0].full_url,'https://api.search.brave.com/res/v1/web/search?q=test')
            self.assertEqual(len(build.call_args.args),1)
            resolve.assert_not_called()

    def test_api_key_never_follows_redirect_and_page_domain_filter_checks_each_hop(self):
        for url,headers,domains,location in [
            ('https://api.search.brave.com/res/v1/web/search',{'X-Subscription-Token':'secret'},(), 'https://other.org/'),
            ('https://example.org/',{},('example.org',),'https://other.org/')]:
            opener=MagicMock();opener.open.side_effect=urllib.error.HTTPError(url,302,'redirect',{'Location':location},None)
            with patch('brave_search.urllib.request.build_opener',return_value=opener):
                with self.assertRaises(SearchError):fetch_public(url,headers,lambda:None,domains=domains)
                self.assertEqual(opener.open.call_count,1)

    def test_unsupported_options_and_binary_are_explicit(self):
        for value in ({'foo': 1}, {'user_location': {'type': 'approximate'}}, {'external_web_access': 'false'}, {'filters': {'bad': []}}):
            with self.assertRaises(ValueError): search_tool({'type': 'web_search', **value})
        with self.assertRaises(SearchError): page_text(b'%PDF', 'application/pdf')


class HostedHttpTests(unittest.TestCase):
    transport = SearchTests.transport
    def setUp(self):
        SearchTests.setUp(self)
        self.owner = Ownership(Path(self.temp.name) / 'ownership.json', Lifecycle())
        self.key = self.owner.acquire()['key']
        self.owner.start(self.key, {})
        self.model_calls = []
        parent = self
        class Model(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                req = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                parent.model_calls.append(req)
                tools = [m for m in req['messages'] if m['role'] == 'tool']
                prompt = next(m['content'] for m in req['messages'] if m['role'] == 'user')
                if not tools:
                    calls = [{'index': 0, 'id': 'search-call', 'function': {'name': 'strata_web_search', 'arguments': json.dumps({'action': 'search', 'query': 'alpha'})}}]
                    if prompt == 'discover':
                        calls = [{'index':0,'id':'discover-call','function':{'name':'codex_tool_search','arguments':'{"query":"deployment status","limit":2}'}}]
                    if prompt == 'mixed':
                        calls.append({'index': 1, 'id': 'client-call', 'function': {'name': 'shell', 'arguments': '{}'}})
                    delta = {'reasoning_content': 'Need evidence.', 'tool_calls': calls}
                    usage = {'prompt_tokens': 50, 'completion_tokens': 8, 'total_tokens': 58, 'prompt_tokens_details': {'cached_tokens': 10}, 'completion_tokens_details': {'reasoning_tokens': 2}}
                    finish = 'length' if prompt == 'truncated' else 'tool_calls'
                else:
                    delta = {'content': 'Evidence: [Docs](https://example.org/docs).'}
                    usage = {'prompt_tokens': 80, 'completion_tokens': 10, 'total_tokens': 90, 'prompt_tokens_details': {'cached_tokens': 22}, 'completion_tokens_details': {'reasoning_tokens': 3}}
                    finish = 'stop'
                self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
                for event in ({'choices': [{'delta': delta, 'finish_reason': finish}]}, {'choices': [], 'usage': usage}):
                    self.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())
                self.wfile.write(b'data: [DONE]\n\n')
        self.model = ThreadingHTTPServer(('127.0.0.1', 0), Model)
        self.bridge = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.bridge.backend = f'http://127.0.0.1:{self.model.server_port}'
        self.bridge.trace = None; self.bridge.search = self.search; self.bridge.ownership = self.owner
        for server in (self.model, self.bridge): threading.Thread(target=server.serve_forever, daemon=True).start()

    def tearDown(self):
        for server in (self.bridge, self.model): server.shutdown(); server.server_close()
        SearchTests.tearDown(self)

    def call(self, prompt='search', stream=False, key=None, history=None, choice=None):
        req = {'input': history if history is not None else prompt, 'stream': stream,
               'max_output_tokens': 100, 'tools': [{'type': 'web_search', 'external_web_access': False}, {'type': 'function', 'name': 'shell', 'parameters': {'type': 'object'}}]}
        if choice is not None: req['tool_choice']=choice
        return urllib.request.urlopen(urllib.request.Request(
            f'http://127.0.0.1:{self.bridge.server_port}/v1/responses', json.dumps(req).encode(),
            {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + (key or self.key)}), timeout=5)

    def test_hosted_events_and_usage_cover_both_model_rounds(self):
        with self.call(stream=True) as reply:
            events = [json.loads(line[6:]) for line in reply.read().decode().splitlines() if line.startswith('data: ')]
        self.assertEqual(events[-1]['type'], 'response.completed')
        self.assertEqual([e['sequence_number'] for e in events], list(range(len(events))))
        response = events[-1]['response']
        self.assertEqual(response['usage']['input_tokens'], 130)
        self.assertEqual(response['usage']['input_tokens_details']['cached_tokens'], 32)
        self.assertEqual(response['usage']['output_tokens'], 18)
        self.assertEqual(self.model_calls[1]['max_tokens'], 92)
        message = next(i for i in response['output'] if i['type'] == 'message')
        self.assertEqual(message['content'][0]['annotations'][0]['url'], 'https://example.org/docs')
        self.assertNotIn('function_call', [i['type'] for i in response['output']])

    def test_mixed_tools_execute_only_search_and_replay_native_history(self):
        with self.call('mixed') as reply: response = json.load(reply)
        self.assertEqual(len(self.model_calls), 1)
        self.assertEqual(next(i for i in response['output'] if i['type'] == 'function_call')['name'], 'shell')
        history = [{'role': 'user', 'content': 'mixed'}, *response['output'], {'type': 'function_call_output', 'call_id': 'client-call', 'output': 'client executed its own tool'}]
        with self.call(history=history) as reply: self.assertEqual(json.load(reply)['status'], 'completed')
        calls = next(m for m in self.model_calls[1]['messages'] if m.get('tool_calls'))['tool_calls']
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(self.calls), 1)

    def test_additional_tools_reaches_model_without_server_side_execution(self):
        history = [{'type': 'additional_tools', 'role': 'developer', 'tools': [
            {'type': 'namespace', 'name': 'functions', 'tools': [
                {'type': 'function', 'name': 'exec_command', 'description': 'Native guardian read-only checks',
                 'parameters': {'type': 'object', 'properties': {'cmd': {'type': 'string'}}}}]}]},
            {'role': 'user', 'content': 'mixed'}]
        with self.call(history=history) as reply: response = json.load(reply)
        self.assertEqual(response['status'], 'completed')
        declaration = next(t for t in self.model_calls[0]['tools']
                           if t['function']['name'] == 'functions__exec_command')
        self.assertEqual(declaration['function']['parameters']['properties']['cmd'], {'type': 'string'})
        self.assertEqual(next(i for i in response['output'] if i['type'] == 'function_call')['name'], 'shell')
        self.assertEqual(len(self.calls), 1)  # Only the hosted search ran here.

    def test_client_discovery_http_roundtrip_preserves_inventory_and_executes_nothing(self):
        declaration={'type':'tool_search','execution':'client','parameters':{
            'type':'object','properties':{'query':{'type':'string'},'limit':{'type':'number'}}}}
        def request(history):
            body={'input':history,'tools':[declaration],'stream':False}
            return urllib.request.urlopen(urllib.request.Request(
                f'http://127.0.0.1:{self.bridge.server_port}/v1/responses',json.dumps(body).encode(),
                {'Content-Type':'application/json','Authorization':'Bearer '+self.key}),timeout=5)
        with request([{'role':'user','content':'discover'}]) as reply:response=json.load(reply)
        discovery=response['output'][1]  # The mock also emits a reasoning item.
        self.assertEqual(discovery['type'],'tool_search_call')
        self.assertEqual(discovery['arguments'],{'query':'deployment status','limit':2})
        found={'type':'function','name':'mcp__deployment__status','description':'Read status','parameters':{'type':'object'}}
        history=[{'role':'user','content':'discover'},*response['output'],{
            'type':'tool_search_output','execution':'client','status':'completed',
            'call_id':'discover-call','tools':[found]}]
        with request(history) as reply:self.assertEqual(json.load(reply)['status'],'completed')
        self.assertEqual(len(self.model_calls),2)
        self.assertIn('mcp__deployment__status',[t['function']['name'] for t in self.model_calls[1]['tools']])
        self.assertEqual(self.calls,[])  # Neither MCP discovery nor search executes in the bridge.

    def test_429_is_a_failed_tool_result_and_model_can_recover(self):
        def failure(*args, **kwargs): raise SearchError('Search upstream returned HTTP 429; request was not retried.', 'rate_limited')
        self.search.transport = failure
        with self.call() as reply: response = json.load(reply)
        self.assertEqual(response['strata_search']['tool_failures'], ['rate_limited'])
        self.assertEqual(next(i for i in response['output'] if i['type'] == 'web_search_call')['status'], 'failed')
        self.assertIn('rate_limited', self.model_calls[1]['messages'][-1]['content'])

    def test_invalid_or_returned_owner_never_searches(self):
        with self.assertRaises(urllib.error.HTTPError) as caught: self.call(key='wrong')
        self.assertEqual(caught.exception.code, 403); caught.exception.close()
        self.assertEqual(self.calls, []); self.assertEqual(self.model_calls, [])
        self.owner.release(self.key)
        with self.assertRaises(urllib.error.HTTPError) as caught: self.call()
        self.assertEqual(caught.exception.code, 403); caught.exception.close()

    def test_tool_choice_none_blocks_even_a_disobedient_model(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:self.call(choice='none')
        self.assertIn('tool_choice=none',caught.exception.read().decode());caught.exception.close()
        self.assertEqual(self.calls,[])

    def test_revocation_during_search_stops_followup_generation(self):
        def revoke(url, headers, check, **kwargs):
            self.owner.release(self.key); check()
        self.search.transport = revoke
        with self.call(stream=True) as reply: text = reply.read().decode()
        self.assertIn('event: response.failed', text)
        self.assertNotIn('event: response.completed', text)
        self.assertEqual(len(self.model_calls), 1)

    def test_length_finish_does_not_execute_truncated_search(self):
        with self.call('truncated') as reply: response = json.load(reply)
        self.assertEqual(response['status'], 'incomplete')
        self.assertEqual(self.calls, [])

    def test_unknown_usage_is_not_fabricated_zero(self):
        usage = combined_usage([{'prompt_tokens': 3, 'completion_tokens': 4,'total_tokens':7}, {'prompt_tokens': 6, 'completion_tokens': 7,'total_tokens':13}])
        self.assertEqual(usage['input_tokens'], 9)
        self.assertNotIn('input_tokens_details',usage)
        self.assertNotIn('output_tokens_details',usage)
        with self.assertRaisesRegex(RuntimeError,'unknown'):
            combined_usage([{'completion_tokens':4}])


if __name__ == '__main__': unittest.main()
