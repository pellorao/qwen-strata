"""Brave web search and bounded public-page reading, shared by hosted search and the MCP server.

The Brave key comes only from installation.private.toml and is sent only to the
fixed Brave API host. Pages are read from public HTTP(S) addresses only, every
redirect hop is checked again, and nothing from the caller's conversation is
sent to page hosts. Results are untrusted evidence, never instructions.
"""
from html.parser import HTMLParser
import http.client
import ipaddress
import json
from pathlib import Path
import re
import threading
import time
import tomllib
from urllib.parse import urlencode, urljoin, urlsplit
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
API = 'https://api.search.brave.com/res/v1/web/search'
API_INTERVAL = 1.0          # seconds between Brave calls (free plan: 1 request/s)
TIMEOUT = 30                # seconds for one page or API read, redirects included
PAGE_LIMIT = 2 * 1024 * 1024
MAX_REDIRECTS = 5
RESULT_COUNT = {'low': 3, 'medium': 5, 'high': 10}
OPEN_CHARS = 20000          # page text returned by open_page
MAX_MATCHES = 30


class SearchError(RuntimeError):
    def __init__(self, message, code='search_error'):
        super().__init__(message)
        self.code = code


def load_key(root=ROOT):
    try:
        key = tomllib.loads((Path(root) / 'installation.private.toml').read_text(encoding='utf-8'))['brave']['api_key']
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError):
        raise SearchError('Brave key is not configured in installation.private.toml.', 'not_configured') from None
    if not isinstance(key, str) or not key.strip() or any(c.isspace() for c in key.strip()):
        raise SearchError('Brave key in installation.private.toml is invalid.', 'not_configured')
    return key.strip()


def public_url(url):
    """Accept http(s) URLs on public hosts only: no credentials, odd ports, local names or private addresses."""
    try:
        value = urlsplit(url)
        if (value.scheme not in ('http', 'https') or not value.hostname or value.username is not None
                or value.password is not None or value.port not in (None, 80, 443)):
            raise ValueError
        host = value.hostname.lower().rstrip('.')
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if '.' not in host or host.endswith(('.localhost', '.local', '.internal', '.lan', '.home.arpa')):
                raise ValueError from None
        else:
            if not address.is_global:
                raise ValueError
        return value
    except (ValueError, TypeError):
        raise SearchError('Only public HTTP(S) URLs without credentials are supported.', 'invalid_url') from None


def domain_allowed(url, domains):
    host = public_url(url).hostname.lower().rstrip('.')
    return not domains or any(host == d.lower() or host.endswith('.' + d.lower()) for d in domains)


class TextPage(HTMLParser):
    HIDDEN = ('script', 'style', 'noscript', 'svg', 'template')
    BREAKS = ('p', 'div', 'li', 'br', 'h1', 'h2', 'h3', 'h4', 'pre', 'tr', 'section', 'article')

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden, self.in_title, self.parts, self.title = 0, False, [], []

    def handle_starttag(self, tag, attrs):
        self.hidden += tag in self.HIDDEN
        self.in_title = self.in_title or tag == 'title'
        if tag in self.BREAKS:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in self.HIDDEN and self.hidden:
            self.hidden -= 1
        if tag == 'title':
            self.in_title = False

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)
            if self.in_title:
                self.title.append(data)


def page_text(raw, content_type):
    """Return (title, text) for HTML, plain text or JSON; other content is refused."""
    charset = re.search(r'charset=([\w-]+)', content_type or '', re.I)
    try:
        text = raw.decode(charset.group(1) if charset else 'utf-8', 'replace')
    except LookupError:
        text = raw.decode('utf-8', 'replace')
    title = ''
    if 'html' in (content_type or ''):
        parser = TextPage()
        parser.feed(text)
        title, text = ' '.join(parser.title).strip(), ''.join(parser.parts)
    elif not (content_type or '').startswith('text/') and 'json' not in (content_type or ''):
        raise SearchError('Only HTML, plain text and JSON pages can be read.', 'unsupported_content')
    lines = (re.sub(r'\s+', ' ', row).strip() for row in text.splitlines())
    return title[:500], '\n'.join(row for row in lines if row)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def fetch(url, headers, check=lambda: None):
    """GET with manual redirects; returns (final url, content type, body). Never retries."""
    deadline = time.monotonic() + TIMEOUT
    opener = urllib.request.build_opener(NoRedirect())
    keyed = 'X-Subscription-Token' in headers
    for _ in range(MAX_REDIRECTS + 1):
        check()
        target = public_url(url)
        if keyed and (target.scheme != 'https' or target.hostname != 'api.search.brave.com'):
            raise SearchError('The Brave key is only sent to the Brave API.', 'invalid_url')
        try:
            with opener.open(urllib.request.Request(url, headers=dict(headers, **{'Accept-Encoding': 'identity'})),
                             timeout=max(1, deadline - time.monotonic())) as reply:
                chunks, size = [], 0
                while chunk := reply.read1(65536):
                    check()
                    size += len(chunk)
                    if size > PAGE_LIMIT:
                        raise SearchError('Response exceeds the size limit.', 'response_too_large')
                    if time.monotonic() > deadline:
                        raise SearchError('Request exceeded its time limit.', 'timeout')
                    chunks.append(chunk)
                return url, reply.headers.get('Content-Type', ''), b''.join(chunks)
        except urllib.error.HTTPError as error:
            location = error.headers.get('Location')
            error.close()
            if error.code in (301, 302, 303, 307, 308) and location and not keyed:
                url = urljoin(url, location)
                continue
            code = 'rate_limited' if error.code == 429 else 'upstream_error'
            raise SearchError(f'Upstream returned HTTP {error.code}; not retried.', code) from None
        except (OSError, ValueError, http.client.HTTPException):
            raise SearchError('Network request failed.', 'network_error') from None
    raise SearchError('Too many redirects.', 'network_error')


class BraveSearch:
    """One caller's search session: pages it has seen stay in memory for open/find and replay."""

    api_lock = threading.Lock()  # shared by all sessions in a process: one Brave call per interval
    next_call = 0.0

    def __init__(self, key_loader=load_key, transport=fetch):
        self.key_loader, self.transport = key_loader, transport
        self.pages = {}  # url -> {'url', 'title', 'text', 'indexed'}

    def execute(self, args, *, live=True, domains=(), context_size='medium', check=lambda: None):
        """Run one action; returns {'action': ..., 'results': [...], 'brave_requests': n}."""
        if not isinstance(args, dict) or set(args) - {'action', 'query', 'url', 'pattern'}:
            raise SearchError('Arguments are action plus query, url or pattern.', 'invalid_arguments')
        action = args.get('action')
        if action == 'search':
            return self.search(args.get('query'), domains, RESULT_COUNT.get(context_size, 5), check)
        if action in ('open_page', 'find_in_page'):
            return self.read(action, args.get('url'), args.get('pattern'), live, domains, check)
        raise SearchError('Action must be search, open_page or find_in_page.', 'invalid_arguments')

    def search(self, query, domains, count, check):
        if not isinstance(query, str) or not query.strip() or len(query) > 400:
            raise SearchError('Query must be 1-400 characters.', 'invalid_arguments')
        sent = query + (' (' + ' OR '.join('site:' + d for d in domains) + ')' if domains else '')
        key = self.key_loader()
        with BraveSearch.api_lock:
            wait = BraveSearch.next_call - time.monotonic()
            while wait > 0:
                check()
                time.sleep(min(wait, 0.1))
                wait = BraveSearch.next_call - time.monotonic()
            BraveSearch.next_call = time.monotonic() + API_INTERVAL
            _, _, raw = self.transport(API + '?' + urlencode({'q': sent, 'count': count, 'extra_snippets': 'true'}),
                                       {'X-Subscription-Token': key, 'Accept': 'application/json'}, check)
        try:
            rows = (json.loads(raw).get('web') or {}).get('results') or []
        except (ValueError, AttributeError):
            raise SearchError('Brave returned an invalid response.', 'upstream_error') from None
        results = []
        for row in rows[:count]:
            url = row.get('url', '')
            try:
                if not domain_allowed(url, domains):
                    continue
            except SearchError:
                continue
            _, text = page_text('\n'.join([row.get('description', '')] + (row.get('extra_snippets') or [])).encode(),
                                'text/html')
            title = page_text(str(row.get('title', '')).encode(), 'text/html')[1].replace('\n', ' ')
            page = {'url': url, 'title': title[:500], 'text': text[:12000], 'indexed': True}
            self.pages.setdefault(url, page)
            results.append(page)
        return {'action': {'type': 'search', 'query': query, 'sources': [{'type': 'url', 'url': r['url']} for r in results]},
                'results': results, 'brave_requests': 1}

    def read(self, action, url, pattern, live, domains, check):
        if not isinstance(url, str) or not url:
            raise SearchError('A page URL is required.', 'invalid_arguments')
        if action == 'find_in_page' and (not isinstance(pattern, str) or not pattern or len(pattern) > 500):
            raise SearchError('find_in_page needs a literal pattern of 1-500 characters.', 'invalid_arguments')
        if not domain_allowed(url, domains):
            raise SearchError('Page is outside the allowed domains.', 'blocked_destination')
        page = self.pages.get(url)
        if not live and page is None:
            raise SearchError('Without external web access only pages returned by search can be read.', 'indexed_only')
        if live and (page is None or page['indexed']):
            final, content_type, raw = self.transport(
                url, {'User-Agent': 'Strata-Brave-Reader/1.0', 'Accept': 'text/html,text/plain,application/json'}, check)
            if not domain_allowed(final, domains):
                raise SearchError('Page redirected outside the allowed domains.', 'blocked_destination')
            title, text = page_text(raw, content_type)
            page = {'url': final, 'title': title, 'text': text, 'indexed': False}
            self.pages[url] = self.pages[final] = page
        lines = page['text'].splitlines()
        action_data = {'type': action, 'url': url}
        if action == 'find_in_page':
            action_data['pattern'] = pattern
            matches = [{'line': n, 'text': line[:1000]} for n, line in enumerate(lines, 1)
                       if pattern.casefold() in line.casefold()][:MAX_MATCHES]
            result = {'url': page['url'], 'title': page['title'], 'indexed': page['indexed'], 'matches': matches}
        else:
            numbered = '\n'.join(f'L{n}: {line}' for n, line in enumerate(lines, 1))
            result = {'url': page['url'], 'title': page['title'], 'indexed': page['indexed'],
                      'text': numbered[:OPEN_CHARS], 'truncated': len(numbered) > OPEN_CHARS}
        return {'action': action_data, 'results': [result], 'brave_requests': 0}
