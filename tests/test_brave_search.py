"""Brave search session without network: URL policy, key handling, actions."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import brave_search
from brave_search import BraveSearch, SearchError

BRAVE = json.dumps({'web': {'results': [
    {'url': 'https://example.com/a', 'title': '<strong>A</strong> &amp; co', 'description': 'first <b>hit</b>', 'extra_snippets': ['more']},
    {'url': 'http://10.0.0.1/x', 'title': 'private', 'description': 'skip'},
    {'url': 'https://other.org/b', 'title': 'B', 'description': 'second'}]}}).encode()
PAGE = b'<html><title>Page A</title><script>x()</script><p>Version v0.1.41</p><p>other line</p></html>'


class Transport:
    def __init__(self):
        self.calls = []

    def __call__(self, url, headers, check):
        self.calls.append((url, headers))
        if url.startswith(brave_search.API):
            return url, 'application/json', BRAVE
        return url, 'text/html; charset=utf-8', PAGE


class BraveTests(unittest.TestCase):
    def setUp(self):
        self.transport = Transport()
        self.search = BraveSearch(lambda: 'secret', self.transport)
        patch.object(brave_search, 'API_INTERVAL', 0).start()
        self.addCleanup(patch.stopall)

    def test_search_filters_private_results_and_keeps_key_on_api(self):
        result = self.search.execute({'action': 'search', 'query': 'strata'})
        self.assertEqual([r['url'] for r in result['results']], ['https://example.com/a', 'https://other.org/b'])
        self.assertEqual(result['results'][0]['text'], 'first hit\nmore')
        self.assertEqual(result['results'][0]['title'], 'A & co')
        self.assertEqual(result['action']['sources'][0], {'type': 'url', 'url': 'https://example.com/a'})
        self.assertEqual(self.transport.calls[0][1]['X-Subscription-Token'], 'secret')

    def test_domains_restrict_query_and_results(self):
        result = self.search.execute({'action': 'search', 'query': 'q'}, domains=['example.com'])
        self.assertIn('site%3Aexample.com', self.transport.calls[0][0])
        self.assertEqual([r['url'] for r in result['results']], ['https://example.com/a'])
        with self.assertRaises(SearchError):
            self.search.execute({'action': 'open_page', 'url': 'https://other.org/b'}, domains=['example.com'])

    def test_open_and_find_fetch_live_page_once(self):
        self.search.execute({'action': 'search', 'query': 'q'})
        opened = self.search.execute({'action': 'open_page', 'url': 'https://example.com/a'})['results'][0]
        self.assertEqual((opened['title'], opened['indexed']), ('Page A', False))
        self.assertIn('L2: Version v0.1.41', opened['text'])
        self.assertNotIn('x()', opened['text'])
        found = self.search.execute({'action': 'find_in_page', 'url': 'https://example.com/a', 'pattern': 'V0.1'})
        self.assertEqual(found['results'][0]['matches'], [{'line': 2, 'text': 'Version v0.1.41'}])
        self.assertEqual(found['action'], {'type': 'find_in_page', 'url': 'https://example.com/a', 'pattern': 'V0.1'})
        self.assertEqual(len(self.transport.calls), 2)
        for _, headers in self.transport.calls[1:]:
            self.assertNotIn('X-Subscription-Token', headers)

    def test_indexed_mode_never_fetches_pages(self):
        with self.assertRaises(SearchError) as error:
            self.search.execute({'action': 'open_page', 'url': 'https://example.com/a'}, live=False)
        self.assertEqual(error.exception.code, 'indexed_only')
        self.search.execute({'action': 'search', 'query': 'q'})
        page = self.search.execute({'action': 'open_page', 'url': 'https://example.com/a'}, live=False)['results'][0]
        self.assertTrue(page['indexed'])
        self.assertEqual(len(self.transport.calls), 1)

    def test_rejects_bad_arguments_and_urls(self):
        for args in ({'action': 'delete'}, {'action': 'search', 'query': ''}, {'action': 'search', 'query': 'q', 'x': 1},
                     {'action': 'find_in_page', 'url': 'https://example.com/a'},
                     {'action': 'open_page', 'url': 'http://127.0.0.1/'}, {'action': 'open_page', 'url': 'file:///etc/passwd'},
                     {'action': 'open_page', 'url': 'https://user:pw@example.com/'},
                     {'action': 'open_page', 'url': 'http://printer.local/'}, {'action': 'open_page', 'url': 'http://example.com:8080/'}):
            with self.assertRaises(SearchError, msg=args):
                self.search.execute(args)
        self.assertEqual(self.transport.calls, [])


class FetchTests(unittest.TestCase):
    def test_key_never_leaves_brave_api(self):
        with self.assertRaises(SearchError):
            brave_search.fetch('https://example.com/', {'X-Subscription-Token': 'k'})

    def test_private_redirect_target_is_refused(self):
        import urllib.error
        from email.message import Message
        headers = Message()
        headers['Location'] = 'http://192.168.1.1/admin'

        class Opener:
            def open(self, request, timeout):
                raise urllib.error.HTTPError(request.full_url, 302, 'Found', headers, None)
        with patch.object(brave_search.urllib.request, 'build_opener', lambda *a: Opener()):
            with self.assertRaises(SearchError) as error:
                brave_search.fetch('https://example.com/', {})
        self.assertEqual(error.exception.code, 'invalid_url')


class KeyTests(unittest.TestCase):
    def test_key_from_installation_private_file(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(SearchError):
                brave_search.load_key(root)
            (Path(root) / 'installation.private.toml').write_text('[brave]\napi_key = " abc "\n')
            self.assertEqual(brave_search.load_key(root), 'abc')
            (Path(root) / 'installation.private.toml').write_text('[brave]\napi_key = "a b"\n')
            with self.assertRaises(SearchError):
                brave_search.load_key(root)


if __name__ == '__main__':
    unittest.main()
