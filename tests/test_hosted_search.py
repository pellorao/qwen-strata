"""Hosted web_search: native rounds merged into one caller stream, search executed between them."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import hosted_search
from brave_search import SearchError


def native_round(response_id, items, output_tokens=10):
    """Events of one native round: items as (output item, extra delta events)."""
    events = [('response.created', {'type': 'response.created', 'response': {'id': response_id, 'status': 'in_progress'}}),
              (None, None)]
    for index, item in enumerate(items):
        events.append(('response.output_item.added', {'type': 'response.output_item.added', 'output_index': index,
                                                      'item': dict(item, status='in_progress')}))
        if item['type'] == 'message':
            events.append(('response.output_text.delta', {'type': 'response.output_text.delta', 'output_index': index,
                                                          'item_id': item['id'], 'delta': 'hi'}))
        if item['type'] == 'function_call':
            events.append(('response.function_call_arguments.delta', {
                'type': 'response.function_call_arguments.delta', 'output_index': index, 'delta': item['arguments']}))
        events.append(('response.output_item.done', {'type': 'response.output_item.done', 'output_index': index,
                                                     'item': item}))
    usage = {'input_tokens': 100, 'input_tokens_details': {'cached_tokens': 40}, 'output_tokens': output_tokens,
             'output_tokens_details': {'reasoning_tokens': 4}, 'total_tokens': 100 + output_tokens}
    events.append(('response.completed', {'type': 'response.completed', 'response': {
        'id': response_id, 'status': 'completed', 'output': items, 'usage': usage}}))
    return events


REASONING = {'id': 'rs_1', 'type': 'reasoning', 'summary': []}
SEARCH = {'id': 'fc_s', 'type': 'function_call', 'call_id': 'call_s', 'name': 'web_search',
          'arguments': json.dumps({'action': 'search', 'query': 'strata'})}
SHELL = {'id': 'fc_x', 'type': 'function_call', 'call_id': 'call_x', 'name': 'exec_command', 'arguments': '{"cmd": "ls"}'}
MESSAGE = {'id': 'msg_1', 'type': 'message', 'role': 'assistant',
           'content': [{'type': 'output_text', 'text': 'hi', 'annotations': []}]}


class FakeSearch:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def execute(self, args, **options):
        self.calls.append((args, options))
        if self.fail:
            raise SearchError('quota', 'rate_limited')
        return {'action': {'type': 'search', 'query': args['query'], 'sources': [{'type': 'url', 'url': 'https://e.com'}]},
                'results': [{'url': 'https://e.com', 'title': 'E', 'text': 'found'}], 'brave_requests': 1}


class Harness:
    def __init__(self, rounds, search=None, body=None):
        self.rounds, self.requests, self.raw = list(rounds), [], b''
        self.search, self.results = search or FakeSearch(), {}
        self.body = body or {'stream': True, 'max_output_tokens': 100, 'reasoning_budget_tokens': 40,
                             'input': 'find strata', 'tools': [{'type': 'web_search', 'external_web_access': True}, {
                                 'type': 'function', 'name': 'exec_command'}]}

    def upstream(self, request):
        self.requests.append(json.loads(json.dumps(request)))
        yield from self.rounds.pop(0)

    def write(self, raw):
        self.raw += raw

    def run(self, check=lambda: None):
        hosted_search.run(self.body, self.results, self.search, self.upstream, self.write, check)
        events = []
        for block in self.raw.decode().split('\n\n'):
            data = [line[5:] for line in block.splitlines() if line.startswith('data:')]
            if data:
                events.append(json.loads(data[0]))
        return events


class RunTests(unittest.TestCase):
    def test_search_round_is_merged_into_one_response(self):
        h = Harness([native_round('resp_a', [REASONING, SEARCH]), native_round('resp_b', [MESSAGE], 20)])
        events = h.run()
        self.assertEqual([e['sequence_number'] for e in events], list(range(len(events))))
        self.assertEqual([e['type'] for e in events].count('response.created'), 1)
        final = events[-1]['response']
        self.assertEqual(events[-1]['type'], 'response.completed')
        self.assertEqual(final['id'], 'resp_a')
        self.assertEqual([i['type'] for i in final['output']], ['reasoning', 'web_search_call', 'message'])
        search_item = final['output'][1]
        self.assertEqual(search_item['action']['query'], 'strata')
        self.assertEqual(final['usage'], {'input_tokens': 200, 'output_tokens': 30, 'total_tokens': 230,
                                          'input_tokens_details': {'cached_tokens': 80},
                                          'output_tokens_details': {'reasoning_tokens': 8}})
        indices = [(e['type'], e['output_index']) for e in events if 'output_index' in e]
        self.assertIn(('response.output_text.delta', 2), indices)
        self.assertNotIn('response.function_call_arguments.delta', [e['type'] for e in events])
        # The model saw a function tool, then its call and the result in the next round.
        first, second = h.requests
        self.assertEqual(first['tools'][0]['type'], 'function')
        self.assertEqual(first['tools'][0]['name'], 'web_search')
        self.assertEqual([i['type'] for i in second['input'][-3:]], ['reasoning', 'function_call', 'function_call_output'])
        self.assertEqual(second['input'][-1]['call_id'], 'call_s')
        self.assertEqual((second['max_output_tokens'], second['reasoning_budget_tokens']), (90, 40))
        self.assertEqual(json.loads(h.results[search_item['id']])[0]['text'], 'found')

    def test_replayed_search_restores_the_result_the_model_saw(self):
        h = Harness([native_round('resp_a', [REASONING, SEARCH]), native_round('resp_b', [MESSAGE])])
        search_item = h.run()[-1]['response']['output'][1]
        replay = Harness([native_round('resp_c', [MESSAGE])], body={
            'stream': True, 'tools': [{'type': 'web_search'}],
            'input': [{'type': 'message', 'role': 'user', 'content': 'q'},
                      {'type': 'web_search_call', 'id': search_item['id'], 'status': 'completed',
                       'action': {'type': 'search', 'query': 'strata'}},
                      {'type': 'web_search_call', 'id': 'ws_lost', 'status': 'completed',
                       'action': {'type': 'open_page', 'url': 'https://e.com'}}]})
        replay.results = h.results
        replay.run()
        sent = replay.requests[0]['input']
        self.assertEqual([i['type'] for i in sent], ['message', 'function_call', 'function_call_output',
                                                     'function_call', 'function_call_output'])
        self.assertEqual(json.loads(sent[1]['arguments']), {'action': 'search', 'query': 'strata'})
        self.assertEqual(sent[2]['output'], h.results[search_item['id']])
        self.assertIn('no longer available', sent[4]['output'])

    def test_client_call_in_the_same_round_ends_the_request(self):
        h = Harness([native_round('resp_a', [SEARCH, SHELL])])
        final = h.run()[-1]['response']
        self.assertEqual([i['type'] for i in final['output']], ['function_call', 'web_search_call'])
        self.assertEqual(final['output'][0]['name'], 'exec_command')
        self.assertEqual(len(h.requests), 1)

    def test_search_error_is_a_real_tool_result(self):
        h = Harness([native_round('resp_a', [SEARCH]), native_round('resp_b', [MESSAGE])], FakeSearch(fail=True))
        h.run()
        self.assertEqual(json.loads(h.requests[1]['input'][-1]['output'])['code'], 'rate_limited')

    def test_output_budget_is_shared(self):
        h = Harness([native_round('resp_a', [SEARCH], 100)])
        events = h.run()
        self.assertEqual(events[-1]['type'], 'response.incomplete')
        self.assertEqual(len(h.requests), 1)

    def test_lost_lease_stops_before_searching(self):
        h = Harness([native_round('resp_a', [SEARCH])])
        calls = []

        def check():
            calls.append(1)
            if len(calls) > 3:
                raise PermissionError('lease gone')
        with self.assertRaises(PermissionError):
            h.run(check)
        self.assertEqual(h.search.calls, [])


class ToolTests(unittest.TestCase):
    def test_refusals(self):
        for body in ({'tools': [{'type': 'web_search'}]},
                     {'stream': True, 'tools': [{'type': 'web_search', 'user_location': {'type': 'approximate'}}]},
                     {'stream': True, 'tools': [{'type': 'web_search', 'filters': {'blocked_domains': []}}]},
                     {'stream': True, 'tools': [{'type': 'web_search'}, {'type': 'function', 'name': 'web_search'}]}):
            with self.assertRaises(hosted_search.Refusal, msg=body):
                hosted_search.hosted_tool(body)
        self.assertIsNone(hosted_search.hosted_tool({'tools': [{'type': 'function', 'name': 'x'}]}))
        self.assertTrue(hosted_search.hosted_tool({'stream': True, 'tools': [
            {'type': 'web_search', 'external_web_access': True, 'filters': {'allowed_domains': ['e.com']}}]}))

    def test_result_store_drops_oldest_beyond_limit(self):
        results = hosted_search.Results(limit=10)
        results['ws_a'], results['ws_b'] = 'aaaa', 'bbbb'
        results['ws_c'] = 'cccc'
        self.assertNotIn('ws_a', results)
        self.assertEqual((results.get('ws_b'), results.get('ws_c')), ('bbbb', 'cccc'))
        results['ws_d'] = 'd' * 20  # a single oversized result is still kept
        self.assertEqual([k for k in 'bcd' if 'ws_' + k in results], ['d'])

    def test_unknown_usage_is_omitted_not_zeroed(self):
        self.assertIsNone(hosted_search.sum_usage([{'input_tokens': 1, 'output_tokens': 1, 'total_tokens': 2}, {}]))
        self.assertEqual(hosted_search.sum_usage([{'input_tokens': 1, 'output_tokens': 1, 'total_tokens': 2}]),
                         {'input_tokens': 1, 'output_tokens': 1, 'total_tokens': 2})


if __name__ == '__main__':
    unittest.main()
