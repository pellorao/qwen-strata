"""Start and stop the native Strata process for the frontend; nothing else launches it."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'runtime/Strata'
ENTRY = ROOT / 'src/native_service.py'
MODELS = ('Q2_0', 'IQ2_XS', 'IQ3_XXS')
LOAD_TIMEOUT = 600

# Engine flags a caller may override. Values are only type-checked: which values
# are measured is decided by the approved run proposal, not by this list.
VALUE_FLAGS = {
    'max-context', 'prefill', 'kv', 'kv-resident', 'pool-workers', 'pool-affinity', 'pcie-frac',
    'pcie-mode', 'spec', 'spec-min-p', 'expert-cache', 'vram-reserve-mib', 'adapt-every',
    'adapt-swaps', 'adapt-decay', 'mtp-window', 'ple-io', 'ple-inflight', 'ple-row-cache',
    'short-read', 'suffix-draft', 'mtp-max-t', 'prompt-cache', 'prompt-cache-every',
    'prompt-cache-root', 'conversation-cache-mib', 'conversation-cache-slots', 'conversation-cache-min-free-mib'}
BOOL_FLAGS = {
    'expert-cache-per-layer', 'expert-cache-cpu-order', 'no-capture', 'no-host-worker',
    'no-ple-prefetch', 'no-prefill-borrow', 'no-split-rows', 'no-coupled-draft', 'shared-late',
    'keep-canonical', 'no-token-graph', 'no-fused-gr', 'no-hit-poke', 'ple-sync-submit',
    'no-spec-split', 'gr-fp32-activations'}
ENVIRONMENT = {'STRATA_HC_SPLIT', 'STRATA_ADAPT_NOWAIT', 'STRATA_SSD_KEEPALIVE',
               'STRATA_BATCH_TRACE', 'STRATA_PREFILL_CPU_SHARE', 'STRATA_ADAPT_LAG'}
SAMPLING = {'temperature', 'top_p', 'top_k', 'min_p', 'presence_penalty', 'frequency_penalty',
            'repetition_penalty', 'penalty_last_n'}
REASONING = {'reasoning_effort', 'reasoning_budget_tokens', 'max_tokens'}
START_OPTIONS = {'model', 'engine_overrides', 'engine_environment', 'request_defaults', 'profile_file',
                 'profile_save_file', 'fit_max_tokens', 'startup_instructions', 'loop_prevention_instructions'}


def _scalar(value):
    return type(value) in (int, float, str) and ' ' not in str(value)


def configuration(options, model_port):
    """Validate start options; return (model, native run config, env, reasoning defaults)."""
    if not isinstance(options, dict) or set(options) - START_OPTIONS:
        raise ValueError('Unknown model start option.')
    model = options.get('model', 'IQ3_XXS')
    if model not in MODELS:
        raise ValueError('Unknown model quantization.')
    config = json.loads((ROOT / f'config/{model.lower()}-prebuilt.json').read_text(encoding='utf-8'))
    config['port'], config['host'] = model_port, '127.0.0.1'
    args = config['args']
    for name, value in (options.get('engine_overrides') or {}).items():
        flag = '--' + name
        if name in BOOL_FLAGS and type(value) is bool:
            args[:] = [a for a in args if a != flag] + ([flag] if value else [])
        elif name in VALUE_FLAGS and value is None:
            if flag in args:
                del args[args.index(flag):args.index(flag) + 2]
        elif name in VALUE_FLAGS and _scalar(value):
            if flag in args:
                args[args.index(flag) + 1] = str(value)
            else:
                args += [flag, str(value)]
        else:
            raise ValueError('Unsupported engine override: ' + str(name))
    for field in ('profile_file', 'profile_save_file'):
        if field not in options:
            continue
        if not isinstance(options[field], str) or not Path(options[field]).is_absolute():
            raise ValueError('Profile paths must be absolute strings.')
        path = Path(options[field]).resolve()
        if not path.is_relative_to((ROOT / 'data/profiles').resolve()):
            raise ValueError('Profiles must be under the installation data/profiles directory.')
        if field == 'profile_file':
            if not path.is_file():
                raise ValueError('Profile file does not exist.')
            args[args.index('--expert-profile') + 1] = str(path)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            config.update(expert_profile_save=str(path), expert_profile_save_every=0)
    environment = dict(config.pop('engine_environment', {}), **(options.get('engine_environment') or {}))
    for name, value in environment.items():
        if name not in ENVIRONMENT or not (value is None or _scalar(value)):
            raise ValueError('Unsupported engine environment: ' + str(name))
    defaults, explicit = config.pop('request_defaults', {}), options.get('request_defaults') or {}
    if explicit.get('reasoning_effort', defaults.get('reasoning_effort')) != defaults.get('reasoning_effort'):
        # Installed budget and output limit belong to the installed effort only.
        defaults = {k: v for k, v in defaults.items() if k not in ('reasoning_budget_tokens', 'max_tokens')}
    defaults = dict(defaults, **explicit)
    if set(defaults) - SAMPLING - REASONING:
        raise ValueError('Unsupported request default.')
    config['sampling'] = dict(config.get('sampling', {}), **{k: v for k, v in defaults.items() if k in SAMPLING})
    reasoning = {k: v for k, v in defaults.items() if k in REASONING}
    if reasoning.get('reasoning_effort', 'high') not in ('low', 'medium', 'high'):
        raise ValueError('Invalid default reasoning effort.')
    if 'fit_max_tokens' in options:
        if type(options['fit_max_tokens']) is not bool:
            raise ValueError('fit_max_tokens must be boolean.')
        config['fit_max_tokens'] = options['fit_max_tokens']
    for name, default in (('startup_instructions', True), ('loop_prevention_instructions', False)):
        if type(options.get(name, default)) is not bool:
            raise ValueError(name + ' must be boolean.')
    env = {k: str(v) for k, v in environment.items() if v is not None}
    env['QWEN_PROJECT_STARTUP_INSTRUCTIONS'] = '1' if options.get('startup_instructions', True) else '0'
    # Loop prevention block: deprecated, off unless explicitly selected.
    env['QWEN_PROJECT_LOOP_PREVENTION'] = '1' if options.get('loop_prevention_instructions', False) else '0'
    return model, config, env, reasoning


class ModelProcess:
    def __init__(self, model_port):
        self.port = model_port
        self.native_key = None
        self.reasoning_defaults = {}
        self.fingerprint = None  # what the running model was started with

    def _fingerprint(self, options):
        return hashlib.sha256(json.dumps(configuration(options, self.port), sort_keys=True).encode()).hexdigest()

    def matches(self, options):
        """Whether the running, loaded model was started with exactly these (validated) options."""
        return (self.fingerprint is not None and self._fingerprint(options) == self.fingerprint
                and self.status()['status'] == 'running')

    def _request(self, path, data=None, timeout=5):
        headers = {'Content-Type': 'application/json'}
        if self.native_key:  # the native server requires its key on every POST, /unload included
            headers['Authorization'] = 'Bearer ' + self.native_key
        request = urllib.request.Request(f'http://127.0.0.1:{self.port}{path}',
            None if data is None else json.dumps(data).encode(), headers)
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=timeout) as reply:
            return json.load(reply)

    def _processes(self):
        import psutil
        owned = {os.path.normcase(str(ENTRY)), os.path.normcase(str(RUNTIME / 'engine/strata.exe'))}
        found = []
        for process in psutil.process_iter(['cmdline']):
            if any(os.path.normcase(os.path.abspath(a)) in owned for a in process.info['cmdline'] or []):
                found.append(process)
        return found

    def stopped(self):
        return not self._processes()

    def status(self):
        if self.stopped():
            return {'status': 'stopped', 'model': None}
        try:
            health = self._request('/health')
        except (OSError, ValueError):
            return {'status': 'starting', 'model': None}
        return {'status': 'running' if health.get('loaded') else 'unloaded',
                'model': health.get('model'), 'native_health': health}

    def start(self, options):
        import psutil
        model, config, env, reasoning = configuration(options, self.port)
        if not self.stopped():
            raise RuntimeError('Stop the current model before starting another.')
        expected_context = int(config['args'][config['args'].index('--max-context') + 1])
        parent = ROOT / '.tmp/model'
        parent.mkdir(parents=True, exist_ok=True)
        config_path = Path(tempfile.mkdtemp(prefix='model-', dir=parent)) / 'active-config.json'
        config_path.write_text(json.dumps(config), encoding='utf-8')
        key = secrets.token_urlsafe(32)
        (ROOT / 'logs').mkdir(exist_ok=True)
        # The frontend runs under pythonw (no console). A console-less parent makes the engine
        # (strata.exe, a console program) open its own visible window, so the native service gets
        # a hidden console that the engine inherits.
        python = Path(sys.executable).with_name('python.exe')
        hidden = {}
        if os.name == 'nt':
            startup = subprocess.STARTUPINFO(dwFlags=subprocess.STARTF_USESHOWWINDOW, wShowWindow=0)  # SW_HIDE
            hidden = {'startupinfo': startup, 'creationflags': subprocess.CREATE_NEW_CONSOLE}
        with (ROOT / 'logs/model-server.log').open('ab') as log:
            process = subprocess.Popen(
                [str(python if python.exists() else sys.executable), '-B', str(ENTRY), '--engine', 'strata', '--config', str(config_path),
                 '--host', '127.0.0.1', '--port', str(self.port)],
                cwd=RUNTIME, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                env=dict(os.environ, STRATA_API_KEY=key, **env), **hidden)
        deadline = time.monotonic() + LOAD_TIMEOUT
        try:
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('Native model exited before ready; see logs/model-server.log.')
                try:
                    health = self._request('/health')
                except (OSError, ValueError):
                    health = {}
                if health.get('loaded'):
                    if (health.get('model') != 'qwen3.8-flash-next-' + model.lower()
                            or health.get('max_context') != expected_context):
                        raise RuntimeError('Loaded model differs from the requested configuration.')
                    self.native_key, self.reasoning_defaults = key, reasoning
                    self.fingerprint = self._fingerprint(options)
                    return self.status()
                time.sleep(1)
            raise TimeoutError(f'Model loading exceeded {LOAD_TIMEOUT} seconds.')
        except BaseException:
            self.stop()
            raise

    def stop(self):
        import psutil
        processes = self._processes()
        clean = None
        if processes:
            try:
                self._request('/unload', {}, timeout=180)
                clean = True
            except (OSError, ValueError):
                clean = False
        owned = []
        for process in processes:
            try:  # the tree changes while it is walked (an unloaded engine or its console host may exit)
                owned += process.children(recursive=True)
            except psutil.NoSuchProcess:
                pass
            owned.append(process)
        for process in owned:
            try:
                process.kill()
            except psutil.NoSuchProcess:
                pass
        psutil.wait_procs(owned, timeout=15)
        self.native_key, self.reasoning_defaults, self.fingerprint = None, {}, None
        if not self.stopped():
            raise RuntimeError('Native model processes did not stop.')
        return {'status': 'stopped', 'clean_unload': clean}
