"""Experiment-owned access to the installed controller, with private credentials."""
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

from tools.reviewer.wsl_client import save
from tools.metrics.model_lifetime import ModelAliveClock


class Controller:
    def __init__(self, installation, folder, *, base_url=None):
        self.installation = Path(installation)
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.credential = self.folder / 'controller-key.private.json'
        self.info = {'controller_base_url':base_url} if base_url else json.loads(subprocess.check_output(
            ['bash', str(self.installation / 'Run-Strata-Controller.sh')], text=True))
        self.base = self.info['controller_base_url']
        self.key = None
        self.model_alive_clock = ModelAliveClock(self.folder / "model-alive-events.json")
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(self, path, body=None, timeout=900):
        headers = {'Content-Type': 'application/json'}
        if self.key:
            headers['Authorization'] = 'Bearer ' + self.key
        request = urllib.request.Request(self.base + path,
            None if body is None else json.dumps(body).encode(), headers)
        requested_at=time.time()
        with self.opener.open(request, timeout=timeout) as reply:
            result=json.load(reply)
        confirmed_at=time.time()
        if path in ('/ownership/start','/ownership/stop','/ownership/release','/ownership/status'):
            status=result.get('status')
            if path=='/ownership/start' and status=='running':
                self.model_alive_clock.observe(True,requested_at,estimated=True,
                    bounds=[requested_at,confirmed_at])
            elif path in ('/ownership/stop','/ownership/release') and status in ('stopped','released','free'):
                self.model_alive_clock.observe(False,confirmed_at,estimated=True,
                    bounds=[requested_at,confirmed_at])
            elif path=='/ownership/status' and status in ('running','stopped','unloaded'):
                self.model_alive_clock.observe(status=='running',confirmed_at,
                    estimated=True,bounds=[requested_at,confirmed_at])
        return result

    def __enter__(self):
        fd = os.open(self.credential, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            self.key = self.call('/ownership/acquire', {})['key']
            with os.fdopen(fd, 'w') as stream:
                fd = None
                json.dump({'base_url': self.base, 'key': self.key}, stream)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            if fd is not None:
                os.close(fd)
            if self.key is None:
                self.credential.unlink(missing_ok=True)
            raise
        return self

    def start(self, **options):
        started = time.monotonic()
        value = self.call('/ownership/start', options)
        return value, time.monotonic() - started

    def stop(self):
        return self.call('/ownership/stop', {})

    def __exit__(self, *exc):
        if self.key:
            self.call('/ownership/release', {})
            self.key = None
            self.credential.unlink(missing_ok=True)


def usage_counts(raw):
    """Unknown counts stay unknown; input includes cached input in both APIs."""
    total = raw.get('input_tokens', raw.get('prompt_tokens'))
    cached = raw.get('input_tokens_details', raw.get('prompt_tokens_details', {})).get('cached_tokens')
    output = raw.get('output_tokens', raw.get('completion_tokens'))
    if any(type(v) is not int or v < 0 for v in (total, cached, output)):
        return {'uncached_input': None, 'cached_input': None, 'output': output,
                'reason': 'Missing or invalid input/cache telemetry'}
    if cached > total:
        return {'uncached_input': None, 'cached_input': None, 'output': output,
                'reason': 'Cached input exceeds total input; retain raw usage and physical engine counters'}
    return {'uncached_input': total - cached, 'cached_input': cached, 'output': output}
