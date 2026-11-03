"""Brave search session without network: URL policy, key handling, actions."""
import json
from pathlib import Path
import socket
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


NONCANONICAL = ('http://127.1/', 'http://0x7f.1/', 'http://2130706433/', 'http://0177.0.0.1/', 'http://0x7f000001/',
                'http://[::1]/', 'http://[::ffff:127.0.0.1]/', 'http://[fe80::1%25eth0]/', 'http://10.1.2.3./')


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
                     {'action': 'open_page', 'url': 'http://printer.local/'}, {'action': 'open_page', 'url': 'http://example.com:8080/'},
                     *({'action': 'open_page', 'url': u} for u in NONCANONICAL)):
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

    def test_compressed_pages_are_decoded_within_the_limit(self):
        import gzip
        self.assertEqual(brave_search.decoded(gzip.compress(PAGE), {'Content-Encoding': 'gzip'}), PAGE)
        self.assertEqual(brave_search.decoded(PAGE, {}), PAGE)
        bomb = gzip.compress(b'a' * (brave_search.PAGE_LIMIT + 1))
        for raw, headers, code in ((bomb, {'Content-Encoding': 'gzip'}, 'response_too_large'),
                                   (PAGE, {'Content-Encoding': 'br'}, 'unsupported_content')):
            with self.assertRaises(SearchError) as error:
                brave_search.decoded(raw, headers)
            self.assertEqual(error.exception.code, code)


class Sock:
    made = []

    def __init__(self, *args):
        self.args, self.connected, self.closed = args, None, False
        Sock.made.append(self)

    def settimeout(self, value):
        self.timeout = value

    def connect(self, address):
        self.connected = address

    def close(self):
        self.closed = True


def answers(*addresses):
    return [(2 if ':' not in a else 10, 1, 6, '', (a, 80)) for a in addresses]


class ConnectTests(unittest.TestCase):
    """The address a host name really resolves to is checked where the connection is made; no network is used."""

    def setUp(self):
        Sock.made = []
        patch.object(brave_search.socket, 'socket', Sock).start()
        self.addCleanup(patch.stopall)

    def resolve(self, *addresses):
        return patch.object(brave_search.socket, 'getaddrinfo', lambda *a, **k: answers(*addresses))

    def test_names_resolving_to_non_public_addresses_are_refused_before_any_socket(self):
        for addresses in (('127.0.0.1',), ('10.0.0.5',), ('::1',), ('::ffff:192.168.0.1',), ('93.184.216.34', '127.0.0.1')):
            with self.resolve(*addresses), self.assertRaises(SearchError, msg=addresses) as error:
                brave_search.connect_public('127-0-0-1.nip.io', 80, 5)
            self.assertEqual(error.exception.code, 'blocked_destination')
        self.assertEqual(Sock.made, [])

    def test_connects_to_the_checked_address(self):
        with self.resolve('93.184.216.34'):
            sock = brave_search.connect_public('example.com', 80, 5)
        self.assertEqual((sock.connected, sock.timeout), (('93.184.216.34', 80), 5))

    def test_fetch_never_reaches_a_name_that_rebinds_to_loopback(self):
        # public_url passes the name; the address check at connect time stops it, redirects included
        for url in ('http://127-0-0-1.nip.io/', 'https://rebind.example.net/'):
            with self.resolve('127.0.0.1'), self.assertRaises(SearchError) as error:
                brave_search.fetch(url, {})
            self.assertEqual(error.exception.code, 'blocked_destination')
        self.assertEqual(Sock.made, [])

    def test_unresolvable_name_is_a_network_error(self):
        def fail(*args, **kwargs):
            raise socket.gaierror
        with patch.object(brave_search.socket, 'getaddrinfo', fail), self.assertRaises(SearchError) as error:
            brave_search.fetch('http://nowhere.example.net/', {})
        self.assertEqual(error.exception.code, 'network_error')


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
