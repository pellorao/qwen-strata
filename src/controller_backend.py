"""Windows model lifecycle reachable only through the ownership controller."""
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import time
import urllib.request

from windows_host import ROOT, RUNTIME, LOGS, startup_lock, listener, assert_owner, terminate, spawn
from service_access import atomic_json

MODELS = ('Q2_0', 'IQ2_XS', 'IQ3_XXS')
ENTRY = ROOT / 'src/native_service.py'
OVERRIDES = {'max-context': (80000, 125000, 188000, 250000, 120584, 156584, 206584, 256584),
             'prefill': (4096, 8192, 16384), 'kv': ('int8', 'fp16', 'q4_0'),
             'kv-resident': (20480, 32768), 'pool-workers': (8, 12, 15, 23),
             'pcie-frac': (0.0, 0.25, 0.5), 'spec': (2, 4), 'spec-min-p': (0.3, 0.5, 0.7),
             'expert-cache': ('auto', 5000, 6000), 'vram-reserve-mib': (700,981,1200),
             'adapt-every': (4,2,8,0), 'adapt-swaps': (96,48,192), 'adapt-decay': (.7,.5,.9),
             'mtp-window': (32768,16384,65536), 'pcie-mode': ('auto','direct','dma','kernel'),
             'expert-cache-per-layer': (False,True), 'expert-cache-cpu-order': (False,True),
             'pool-affinity':('auto','p-cores','all'),'ple-io':('direct','mmap'),
             'ple-inflight':(256,128,512),
             'no-capture':(False,True),'no-host-worker':(False,True),
             'no-ple-prefetch':(False,True),'no-prefill-borrow':(False,True),
             'no-split-rows':(False,True),'no-coupled-draft':(False,True),
             'shared-late':(False,True),'keep-canonical':(False,True),
             'no-token-graph':(False,True),'no-fused-gr':(False,True),
             'no-hit-poke':(False,True),'ple-sync-submit':(False,True),
             'no-spec-split':(False,True),'gr-fp32-activations':(False,True),
             'ple-row-cache':(1048576,0,262144), 'short-read':(64,0,256),
             'suffix-draft':(3,0,5),'mtp-max-t':(0,2,4),
             'prompt-cache':(6,0,2),'prompt-cache-every':(16384,0,8192),
             'prompt-cache-root':(2048,0,4096)}
BOOL_FLAGS = {'expert-cache-per-layer','expert-cache-cpu-order','no-capture','no-host-worker',
              'no-ple-prefetch','no-prefill-borrow','no-split-rows','no-coupled-draft',
              'shared-late','keep-canonical','no-token-graph','no-fused-gr','no-hit-poke',
              'ple-sync-submit','no-spec-split','gr-fp32-activations'}
ENVIRONMENT = {'STRATA_HC_SPLIT':(0,1),'STRATA_ADAPT_NOWAIT':(0,1),'STRATA_SSD_KEEPALIVE':(0,100,200),
               'STRATA_BATCH_TRACE':(1,), 'STRATA_PREFILL_CPU_SHARE':(0,'auto')}


def validate_request_defaults(value):
    if not isinstance(value,dict):
        raise ValueError('request_defaults must be an object.')
    limits = {'temperature': (0,2), 'top_p': (0,1), 'top_k': (1,64), 'min_p': (0,1),
              'presence_penalty':(-2,2),'frequency_penalty':(-2,2),
              'repetition_penalty':(.5,2),'penalty_last_n':(0,65536),
              'max_tokens':(8192,24576),'reasoning_budget_tokens':(2048,8192)}
    for key,item in value.items():
        if key == 'reasoning_effort':
            if item not in ('low','medium','high'):
                raise ValueError('Invalid request default effort.')
        elif key not in limits or type(item) not in (int,float) or not limits[key][0]<=item<=limits[key][1]:
            raise ValueError('Invalid request default: '+key)
        elif key in {'top_k','penalty_last_n','max_tokens','reasoning_budget_tokens'} and type(item) is not int:
            raise ValueError('Request default must be an integer: '+key)
    if any(k in value for k in ('max_tokens','reasoning_budget_tokens')) and 'reasoning_effort' not in value:
        raise ValueError('Budget defaults require an effort binding.')
    return dict(value)


class Backend:
    def __init__(self, host, access_file, *, model_host=None, model_port=8100, api_port=8101, api_base_url=None):
        self.host = host
        self.model_host = model_host or host
        self.model_port = model_port
        self.api_port = api_port
        self.api_base_url = api_base_url or f'http://{host}:{api_port}'
        self.access_file = Path(access_file)
        secret_file = self.access_file.with_name('maintenance.key')
        if not secret_file.exists():
            secret_file.parent.mkdir(parents=True, exist_ok=True)
            secret_file.write_text(secrets.token_urlsafe(32), encoding='utf-8')
        self.maintenance_key = secret_file.read_text(encoding='utf-8')
        if len(self.maintenance_key) < 40:
            raise RuntimeError('Invalid controller maintenance credential.')

    def request(self, path, data=None, timeout=3):
        request = urllib.request.Request(f'http://{self.model_host}:{self.model_port}{path}',
            None if data is None else json.dumps(data).encode(),
            {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + self.maintenance_key})
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=timeout) as response:
            return json.load(response)

    def _processes(self):
        import psutil
        entries = {os.path.normcase(str(ENTRY)), os.path.normcase(str(RUNTIME/'engine/strata.exe'))}
        found = {}
        for process in psutil.process_iter(['pid', 'cmdline']):
            args = process.info['cmdline'] or []
            if any(os.path.normcase(os.path.abspath(a)) in entries for a in args):
                found[process.pid] = process
        return found

    def stopped(self):
        return listener(self.model_port, self.model_host) is None and not self._processes()

    def status(self):
        process = listener(self.model_port, self.model_host)
        if process is None:
            return {'status': 'stopped' if not self._processes() else 'partial', 'model_pid': None}
        assert_owner(process, ENTRY)
        health = self.request('/health')
        return {'status': 'running' if health.get('loaded') else 'unloaded', 'model_pid': process.pid,
                'native_health': health, 'model': health.get('model'),
                'chat_base_url': self.api_base_url+'/v1', 'responses_base_url': self.api_base_url+'/v1'}

    def _configuration(self, options):
        if set(options) - {'model', 'engine_overrides', 'profile_file', 'profile_save_file', 'request_defaults', 'engine_environment', 'fit_max_tokens', 'startup_instructions', 'loop_prevention_instructions'}:
            raise ValueError('Unknown model startup option.')
        instructions = options.get('startup_instructions', True)
        if type(instructions) is not bool:
            raise ValueError('startup_instructions must be boolean.')
        loop_prevention = options.get('loop_prevention_instructions', True)
        if type(loop_prevention) is not bool:
            raise ValueError('loop_prevention_instructions must be boolean.')
        model = options.get('model', 'Q2_0')
        if model not in MODELS:
            raise ValueError('Unknown model quantization.')
        config = json.loads((ROOT/f'config/{model.lower()}-prebuilt.json').read_text())
        if 'fit_max_tokens' in options:
            if type(options['fit_max_tokens']) is not bool:
                raise ValueError('fit_max_tokens must be a boolean.')
            # Native Strata admission policy; never truncate the input. An
            # omitted option preserves the installed configuration/default.
            config['fit_max_tokens'] = options['fit_max_tokens']
        overrides = options.get('engine_overrides', {})
        if not isinstance(overrides, dict):
            raise ValueError('engine_overrides must be an object.')
        for name, value in overrides.items():
            if name in BOOL_FLAGS:
                if type(value) is not bool:
                    raise ValueError('Boolean engine flag required: '+name)
                flag = '--'+name
                config['args'] = [a for a in config['args'] if a != flag]
                if value:
                    config['args'].append(flag)
                continue
            integral = name not in ('kv', 'pcie-frac', 'spec-min-p','adapt-decay','pcie-mode','expert-cache','pool-affinity','ple-io')
            if name not in OVERRIDES or isinstance(value, bool) or value not in OVERRIDES[name] or (integral and type(value) is not int):
                raise ValueError('Unsupported engine override: ' + name)
            if name == 'expert-cache' and value != 'auto' and type(value) is not int:
                raise ValueError('Expert cache must be auto or an integer.')
            flag = '--' + name
            if flag in config['args']:
                config['args'][config['args'].index(flag)+1] = str(value)
            else:
                config['args'] += [flag, str(value)]
        for field in ('profile_file', 'profile_save_file'):
            if field not in options:
                continue
            raw = options[field]
            if not isinstance(raw, str) or not Path(raw).is_absolute():
                raise ValueError('Profile paths must be absolute strings.')
            path = Path(raw).resolve()
            profile_root = (ROOT/'data/profiles').resolve()
            if not path.is_relative_to(profile_root):
                raise ValueError('Profiles must be under the installation data/profiles directory.')
            if field == 'profile_file':
                if not path.is_file():
                    raise ValueError('Profile file does not exist.')
                config['args'][config['args'].index('--expert-profile')+1] = str(path)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                config.update(expert_profile_save=str(path), expert_profile_save_every=0)
        defaults=validate_request_defaults(config.pop('request_defaults',{}))
        explicit=validate_request_defaults(options.get('request_defaults',{}))
        if 'reasoning_effort'in explicit and explicit['reasoning_effort']!=defaults.get('reasoning_effort'):
            defaults={k:v for k,v in defaults.items()if k not in ('reasoning_budget_tokens','max_tokens')}
        config['_request_defaults'] = dict(defaults,**explicit)
        environment = config.pop('engine_environment',{})
        supplied = options.get('engine_environment',{})
        if not isinstance(environment,dict)or not isinstance(supplied,dict):
            raise ValueError('Unsupported engine environment override.')
        environment=dict(environment,**supplied)
        if not isinstance(environment,dict) or any(k not in ENVIRONMENT or (v is not None and (type(v) not in (int,str) or v not in ENVIRONMENT[k])) for k,v in environment.items()):
            raise ValueError('Unsupported engine environment override.')
        config['_engine_environment'] = dict(environment)
        config['_startup_instructions_enabled'] = instructions
        config['_loop_prevention_instructions_enabled'] = loop_prevention
        return model, config

    def request_defaults(self):
        path = self.access_file.with_name('request-defaults.json')
        return json.loads(path.read_text()) if path.exists() else {}

    def start(self, options):
        import psutil
        model, config = self._configuration(options)
        expected_context = int(config['args'][config['args'].index('--max-context')+1])
        defaults = config.pop('_request_defaults')
        environment = config.pop('_engine_environment')
        instructions = config.pop('_startup_instructions_enabled')
        loop_prevention = config.pop('_loop_prevention_instructions_enabled')
        with startup_lock():
            if not self.stopped():
                raise RuntimeError('Stop the current model before choosing startup options.')
            parent = ROOT/'.tmp/controller-model'
            parent.mkdir(parents=True, exist_ok=True)
            folder = Path(tempfile.mkdtemp(prefix='model-', dir=parent))
            config_path = folder/'active-config.json'
            config_path.write_text(json.dumps(config), encoding='utf-8')
            env = dict(os.environ, STRATA_ACCESS_FILE=str(self.access_file), STRATA_MAINTENANCE_KEY=self.maintenance_key,
                       QWEN_PROJECT_STARTUP_INSTRUCTIONS='1' if instructions else '0',
                       QWEN_PROJECT_LOOP_PREVENTION='1' if loop_prevention else '0')
            for key,value in environment.items():
                if value is None:
                    env.pop(key,None)
                else:
                    env[key] = str(value)
            LOGS.mkdir(exist_ok=True)
            with (LOGS/'wsl-server.log').open('ab') as log:
                import subprocess
                process = subprocess.Popen([sys.executable, '-B', str(ENTRY), '--engine', 'strata',
                    '--config', str(config_path), '--host', self.model_host, '--port', str(self.model_port)], cwd=RUNTIME,
                    stdin=subprocess.DEVNULL, stdout=log, stderr=log, env=env, creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                deadline = time.monotonic()+600
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError('Native model exited before ready; inspect installation logs.')
                    try:
                        health = self.request('/health')
                        if health.get('loaded'):
                            if health.get('model') != 'qwen3.8-flash-next-'+model.lower() or health.get('max_context') != expected_context:
                                raise RuntimeError('Loaded model differs from requested configuration.')
                            atomic_json(self.access_file.with_name('request-defaults.json'),defaults)
                            return self.status()
                    except (OSError, ValueError):
                        pass
                    time.sleep(1)
                raise TimeoutError('Model startup exceeded 600 seconds.')
            except BaseException:
                if process.poll() is None:
                    terminate(psutil.Process(process.pid))
                raise

    def stop(self):
        with startup_lock():
            process = listener(self.model_port, self.model_host)
            if process:
                assert_owner(process, ENTRY)
            clean = None
            if process:
                try:
                    self.request('/unload', {}, timeout=180)
                    clean = True
                except (OSError, ValueError):
                    clean = False
            processes = self._processes()
            if process:
                processes[process.pid] = process
            import psutil
            for owned in processes.values():
                try:
                    if owned.is_running():
                        terminate(owned)
                except psutil.NoSuchProcess:
                    pass
            if not self.stopped():
                raise RuntimeError('Owned native model did not stop.')
            return {'status': 'stopped', 'clean_unload': clean}
