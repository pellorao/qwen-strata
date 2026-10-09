"""Brave MCP server speaks JSON-RPC over stdio and maps tools onto search actions."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import brave_mcp
from brave_search import SearchError


class Search:
    def __init__(self):
        self.calls = []

    def execute(self, args):
        self.calls.append(args)
        if args['action'] == 'open_page':
            raise SearchError('private address', 'invalid_url')
        return {'results': [{'url': 'https://e.com'}]}


class McpTests(unittest.TestCase):
    def call(self, method, params=None, ident=1):
        return brave_mcp.handle({'jsonrpc': '2.0', 'id': ident, 'method': method, 'params': params or {}}, self.search)

    def setUp(self):
        self.search = Search()

    def test_handshake_and_listing(self):
        self.assertEqual(self.call('initialize', {'protocolVersion': '2025-03-26'})['result']['protocolVersion'], '2025-03-26')
        self.assertIsNone(brave_mcp.handle({'jsonrpc': '2.0', 'method': 'notifications/initialized'}, self.search))
        names = [t['name'] for t in self.call('tools/list')['result']['tools']]
        self.assertEqual(names, ['web_search', 'open_page', 'find_in_page'])

    def test_calls_map_to_actions_and_errors_are_tool_results(self):
        found = self.call('tools/call', {'name': 'web_search', 'arguments': {'query': 'q'}})['result']
        self.assertFalse(found['isError'])
        self.assertEqual(self.search.calls[0], {'query': 'q', 'action': 'search'})
        failed = self.call('tools/call', {'name': 'open_page', 'arguments': {'url': 'http://10.0.0.1'}})['result']
        self.assertTrue(failed['isError'])
        self.assertIn('invalid_url', failed['content'][0]['text'])
        self.assertIn('error', self.call('tools/call', {'name': 'rm', 'arguments': {}}))
        self.assertIn('error', self.call('resources/list'))


if __name__ == '__main__':
    unittest.main()
