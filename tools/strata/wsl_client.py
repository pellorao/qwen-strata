"""Isolated Linux app-server client for measurements; never installed as a launcher."""
import json
import os
from pathlib import Path
import queue
import shutil
import signal
import subprocess
import threading
import time
import urllib.request
from tools.metrics.prompt_policy import compaction_config
from tools.strata.native_cli_binding import CODEX

ROOT = Path(__file__).resolve().parents[2]


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def http(url, value=None, timeout=900):
    headers = {'Content-Type': 'application/json'}
    if os.environ.get('STRATA_API_KEY'):
        headers['Authorization'] = 'Bearer ' + os.environ['STRATA_API_KEY']
    request = urllib.request.Request(url, None if value is None else json.dumps(value).encode(),
                                     headers)
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=timeout) as response:
        return json.load(response)


def configuration(out, workspace, base_url, *, model_slug, tier, effort='low', extra_config=None):
    """Create only an experiment-local home/catalog, independent of user's config.

    `tier` is the published context tier the model was started with; its window and limit go to the harness."""
    window, limit = tier['context_window'], tier['auto_compact_token_limit']
    home = out / 'codex-home'
    home.mkdir(parents=True, exist_ok=True)
    catalog = json.loads((ROOT / 'config/model-catalog.json').read_text())
    model = next(m for m in catalog['models'] if m['slug'] == model_slug)
    instructions = ('You are a local coding assistant. Use tools only when asked. Work only in the assigned '
                    'workspace. Read actual outputs, edit with apply_patch, and run independent tests. '
                    'Do not use network services, install packages, delegate, or change permissions. '
                    'Never claim an action completed without tool evidence. Preserve exact Unicode identifiers.')
    model['base_instructions'] = instructions
    model['model_messages']['instructions_template'] = instructions
    model['truncation_policy']['limit'] = 36000
    model['context_window'] = model['max_context_window'] = window
    catalog['models'] = [model]
    save(out / 'catalog.json', catalog)
    values = {
        'model': model_slug, 'model_provider': 'qwen_strata', 'model_catalog_json': str(out / 'catalog.json'),
        'model_context_window': window, 'model_auto_compact_token_limit': limit,
        'model_auto_compact_token_limit_scope': 'total', 'model_reasoning_effort': effort,
        'experimental_compact_prompt_file': str(ROOT / 'config/prompts/compact-prompt.txt'),
        'web_search': 'disabled', 'agents.enabled': False, 'features.apps': False,
        'features.plugins': False, 'features.memories': False, 'features.goals': False,
        'sandbox_workspace_write.network_access': False,
        'model_providers.qwen_strata.name': 'Local Strata measurement',
        'model_providers.qwen_strata.base_url': base_url,
        'model_providers.qwen_strata.wire_api': 'responses',
        'model_providers.qwen_strata.requires_openai_auth': False,
        'model_providers.qwen_strata.supports_websockets': False,
        'model_providers.qwen_strata.request_max_retries': 0,
        'model_providers.qwen_strata.stream_max_retries': 0,
        'mcp_servers.project.command': shutil.which('python3'),
        'mcp_servers.project.args': [str(ROOT / 'src/project_files_mcp.py')],
        'mcp_servers.project.env': {'QWEN_PROJECT_WORKSPACE': str(workspace),
                                    'QWEN_PROJECT_AUDIT': str(out / 'mcp-audit.jsonl')},
    }
    values.update(extra_config or {})
    values = compaction_config(values, out / 'prompt-policy')
    if os.environ.get('STRATA_API_KEY'):
        values['model_providers.qwen_strata.env_key'] = 'STRATA_API_KEY'
    args = []
    for key, value in values.items():
        if isinstance(value, dict):
            value = '{' + ','.join(json.dumps(k) + '=' + json.dumps(v) for k, v in value.items()) + '}'
        else:
            value = json.dumps(value)
        args += ['-c', key + '=' + value]
    return home, args


class Client:
    def __init__(self, out, workspace, base_url, *, model_slug, tier, effort='low', extra_config=None):
        self.out, self.workspace = out, workspace
        out.mkdir(parents=True, exist_ok=True)
        self.model_slug = model_slug
        home, overrides = configuration(out, workspace, base_url, model_slug=model_slug, tier=tier,
                                        effort=effort, extra_config=extra_config)
        env = os.environ.copy()
        env['CODEX_HOME'] = str(home)
        for key in list(env):
            if key.upper().endswith('_PROXY') or key.startswith(('CODEX_', 'OPENAI_')):
                if key != 'CODEX_HOME':
                    env.pop(key)
        self.events = (out / 'events.jsonl').open('a', encoding='utf-8')
        self.stderr = (out / 'stderr.log').open('a', encoding='utf-8')
        # The native binary ARW runs use (native_cli), not the npm wrapper on PATH.
        self.proc = subprocess.Popen([str(CODEX), '--no-daemon', *overrides, 'app-server'],
            cwd=workspace, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self.stderr, start_new_session=True)
        self.messages, self.responses = [], queue.Queue()
        self.condition = threading.Condition()
        self.number = 0
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()
        self.send('initialize', {'clientInfo': {'name': 'qwen_wsl_measurement', 'version': '1'},
                                'capabilities': {'experimentalApi': True}})
        self.send('initialized', {}, notify=True)

    def read(self):
        for raw in self.proc.stdout:
            try:
                value = json.loads(raw)
            except ValueError:
                continue
            self.events.write(json.dumps({'at': time.time(), 'event': value}, ensure_ascii=False) + '\n')
            self.events.flush()
            with self.condition:
                self.messages.append(value)
                self.condition.notify_all()
            if 'id' in value:
                self.responses.put(value)

    def send(self, method, params, notify=False):
        self.number += 1
        request = {'method': method, 'params': params}
        if not notify:
            request['id'] = self.number
        self.proc.stdin.write((json.dumps(request, ensure_ascii=False) + '\n').encode())
        self.proc.stdin.flush()
        if notify:
            return
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            value = self.responses.get(timeout=max(.1, deadline - time.monotonic()))
            if value.get('id') == self.number and 'method' not in value:
                if 'error' in value:
                    raise RuntimeError(json.dumps(value['error']))
                return value['result']
            # Never auto-approve a server request in an experiment.
            if 'method' in value:
                raise RuntimeError('Unexpected server request: ' + value['method'])
        raise TimeoutError(method)

    def wait(self, predicate, offset=0, timeout=900):
        deadline = time.monotonic() + timeout
        with self.condition:
            while True:
                for value in self.messages[offset:]:
                    if predicate(value):
                        return value
                if self.proc.poll() is not None:
                    raise RuntimeError('app-server exited; inspect stderr.log')
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('app-server event')
                self.condition.wait(min(remaining, 1))

    def thread(self, resume=None, writable=False, permissions=None, reviewer=None):
        params = {'cwd': str(self.workspace), 'approvalPolicy': 'never',
                  'sandbox': 'workspace-write' if writable else 'read-only'}
        if permissions:
            params.pop('sandbox')
            params['permissions'] = permissions
        if reviewer:
            params.update(approvalPolicy='on-request', approvalsReviewer=reviewer)
        if resume:
            params['threadId'] = resume
            result = self.send('thread/resume', params)
        else:
            result = self.send('thread/start', params | {'model': self.model_slug, 'modelProvider': 'qwen_strata',
                                                       'ephemeral': False})
        return result['thread']['id']

    def begin(self, thread, text):
        offset = len(self.messages)
        result = self.send('turn/start', {'threadId': thread, 'input': [{'type': 'text', 'text': text}]})
        return result['turn']['id'], offset

    def finish(self, thread, turn, offset, timeout=900):
        return self.wait(lambda e: e.get('method') == 'turn/completed'
            and e.get('params', {}).get('threadId') == thread
            and e['params']['turn']['id'] == turn, offset, timeout)['params']['turn']

    def turn(self, thread, text, timeout=900):
        start = time.monotonic()
        turn, offset = self.begin(thread, text)
        result = self.finish(thread, turn, offset, timeout)
        return {'elapsed_s': time.monotonic() - start, 'turn': result,
                'events': self.messages[offset:]}

    def close(self):
        if self.proc.poll() is None:
            self.proc.stdin.close()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid, signal.SIGTERM)
                try:
                    self.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(self.proc.pid, signal.SIGKILL)
                    self.proc.wait(timeout=5)
        self.reader.join(timeout=5)
        self.events.close()
        self.stderr.close()


def text(result):
    return '\n'.join(item.get('text', '') for item in result['turn'].get('items', [])
                     if item['type'] == 'agentMessage')


def statistics(result):
    items = completed_items(result)
    return {'status': result['turn']['status'], 'elapsed_s': result['elapsed_s'],
            'text': text(result), 'tools': [{k: item[k] for k in ('type', 'status', 'tool', 'command', 'exitCode')
                if k in item} for item in items if item['type'] not in ('userMessage', 'agentMessage', 'reasoning')],
            'usage': [e['params'].get('tokenUsage') for e in result['events']
                      if e.get('method') == 'thread/tokenUsage/updated'],
            'compactions': sum(e.get('method') == 'item/completed' and
                e.get('params', {}).get('item', {}).get('type') == 'contextCompaction' for e in result['events'])}


def completed_items(result):
    # turn/completed defaults to itemsView=summary in current Codex; tools live in notifications.
    return [e['params']['item'] for e in result['events'] if e.get('method') == 'item/completed']
