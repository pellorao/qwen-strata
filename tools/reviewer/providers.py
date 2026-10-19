"""Reviewer model providers: the local Strata service, or an API provider reached directly by Codex.

A selection without a ``provider`` entry is the Strata path and keeps its existing settings byte for byte.
An API provider takes no lease and has no engine log: tokens come from API usage.

Two credential modes:
- ``env_key`` (DeepSeek; OpenAI only when a plan asks for an API key): Codex reads the key from a variable through
  its own ``env_key``; the variable is never written anywhere by this project.
- ``chatgpt`` (OpenAI, the default since the user chose the ChatGPT plan, 2026-10-19): the user logs in once in the
  CODEX_HOME named by ``auth_home`` (the default ~/.codex, user 2026-10-19); every run gets a fresh CODEX_HOME holding only a symbolic link to that
  login file. Codex's built-in ``openai`` provider is used unchanged. The project never opens the file.
"""
import os
from pathlib import Path
import re

STRATA_PROVIDER = 'qwen_strata'
STRATA_KEY = 'STRATA_API_KEY'
AUTH_FILE = 'auth.json'
CHATGPT_UPSTREAM = 'https://chatgpt.com/backend-api/codex'
# Default credential variables. The isolated Codex environment drops every CODEX_* and OPENAI_* variable
# (tools/reviewer/arw_native_setup.mjs), so a key under those prefixes would never reach Codex.
API_PROVIDERS = {'openai': {'name': 'OpenAI', 'auth': 'chatgpt', 'env_key': 'BENCHMARK_OPENAI_API_KEY'},
                 'deepseek': {'name': 'DeepSeek', 'auth': 'env_key', 'env_key': 'BENCHMARK_DEEPSEEK_API_KEY'}}
AUTH_MODES = {'openai': ('chatgpt', 'env_key'), 'deepseek': ('env_key',)}
SERVICE_TIERS = ('default', 'flex', 'priority')
WEB_SEARCH_MODES = ('disabled', 'cached', 'live')
# Strata-only selection fields: engine, lease and frontend settings that an API provider cannot honor.
STRATA_ONLY = ('model_owner', 'engine_overrides', 'engine_environment', 'sampling', 'deployment_condition',
               'loop_reminder', 'loop_prevention_instructions', 'automatic_continuation', 'host_id', 'host_hardware')
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def api_provider(selection):
    """None for the Strata path; otherwise the validated API provider this selection names."""
    value = selection.get('provider')
    if value is None:
        return None
    if not isinstance(value, dict) or value.get('id') not in API_PROVIDERS:
        raise ValueError('Unsupported Reviewer provider; choose one of ' + ', '.join(API_PROVIDERS))
    known = API_PROVIDERS[value['id']]
    auth = value.get('auth', known['auth'])
    if auth not in AUTH_MODES[value['id']]:
        raise ValueError('Unsupported credential mode for this provider')
    extra = set(value) - {'id', 'base_url', 'env_key', 'name', 'auth', 'auth_home', 'relay'}
    if extra:
        raise ValueError('Unknown provider fields: ' + ', '.join(sorted(extra)))
    base = value.get('base_url', CHATGPT_UPSTREAM if auth == 'chatgpt' else None)
    # The endpoint is stated by the run plan from the provider's current documentation, never guessed here.
    if not isinstance(base, str) or not re.fullmatch(r'https://[^\s/]+(/[^\s]*)?', base):
        raise ValueError('An API provider needs its https base_url in the selection')
    relay = value.get('relay', True)
    if relay not in (True, False):
        raise ValueError('Provider relay is true or false')
    provider = {'id': value['id'], 'name': value.get('name', known['name']), 'base_url': base.rstrip('/'),
                'auth': auth, 'relay': relay}
    if auth == 'chatgpt':
        if 'env_key' in value:
            raise ValueError('A ChatGPT login has no env_key')
        home = value.get('auth_home')
        if not isinstance(home, str) or not os.path.isabs(home):
            raise ValueError('A ChatGPT login names the absolute benchmark CODEX_HOME that holds it (auth_home)')
        home = os.path.normpath(home)
        if home == str(PROJECT_ROOT) or home.startswith(str(PROJECT_ROOT) + '/'):
            raise ValueError('The benchmark login lives outside the project')
        # Codex's built-in provider: its native behaviour (remote compaction, guardian, catalog) stays unchanged.
        return {**provider, 'codex_id': 'openai', 'env_key': None, 'auth_home': home}
    if 'auth_home' in value:
        raise ValueError('auth_home belongs to a ChatGPT login')
    env_key = value.get('env_key', known['env_key'])
    if (not isinstance(env_key, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]*', env_key)
            or env_key.startswith(('CODEX_', 'OPENAI_', 'STRATA_'))):
        raise ValueError('Provider env_key must be an uppercase variable outside the CODEX_, OPENAI_ and STRATA_ prefixes')
    return {**provider, 'codex_id': 'benchmark_' + value['id'], 'env_key': env_key}


def provider_entry(provider, base_url=None):
    """Codex model_providers entry for a key provider; Codex itself reads the key through env_key."""
    if provider['auth'] == 'chatgpt':
        raise ValueError('A ChatGPT login uses the built-in openai provider')
    return {'name': provider['name'], 'base_url': base_url or provider['base_url'], 'wire_api': 'responses',
            'env_key': provider['env_key'], 'requires_openai_auth': False, 'supports_websockets': False}


def provider_config(provider, base_url=None):
    """Config keys that point Codex at the provider, or at a local relay in front of it (base_url)."""
    if provider['auth'] == 'chatgpt':
        # The built-in provider keeps its id and behaviour; only its endpoint moves to the relay.
        return {'openai_base_url': base_url} if base_url else {}
    return {'model_providers': {provider['codex_id']: provider_entry(provider, base_url)}}


# Every credential variable this project knows of. Reviewer commands never see any of them, whichever provider runs:
# a benchmark key set in the user's environment must not reach an OpenAI or Strata run (review 2026-10-19, M1).
CREDENTIAL_VARIABLES = tuple(sorted({p['env_key'] for p in API_PROVIDERS.values()})) + (STRATA_KEY, 'STRATA_REMOTE_PASSWORD')


def shell_exclude(provider):
    """Variables Reviewer shell commands never see: the provider key first, then every known credential variable."""
    own = [provider['env_key']] if provider and provider.get('env_key') else []
    return own + [name for name in CREDENTIAL_VARIABLES if name not in own]


def process_environment(provider, environ=None):
    """Environment for a Codex process: other providers' benchmark keys removed, so Codex itself never holds a key it
    does not use; the selected provider's key stays for Codex's env_key. Strata variables are left to their own rules."""
    environ = dict(os.environ if environ is None else environ)
    own = provider.get('env_key') if provider else None
    return {k: v for k, v in environ.items() if not (k.startswith('BENCHMARK_') and k != own)}


def credential_deny_paths(provider=None, home=None, project_root=None):
    """Paths no Codex Reviewer command may read (G7, plan §3): the Claude login, the user's Codex home (which holds
    the benchmark ChatGPT login, user 2026-10-19) and the project's private host file. :read-only can read them, and
    an API arm would send what it read to an outside service. home/project_root default to the real ones; gates pass
    synthetic ones. A ChatGPT provider's own auth_home is denied as well. Paths are listed, never opened."""
    home = Path(home) if home is not None else Path.home()
    project_root = Path(project_root) if project_root is not None else PROJECT_ROOT
    paths = [home / '.claude/.credentials.json', home / '.codex', project_root / 'project.private.toml']
    if provider and provider.get('auth') == 'chatgpt':
        paths.append(Path(provider['auth_home']))
    return list(dict.fromkeys(os.path.normpath(str(p)) for p in paths))


def credential_present(provider):
    """Whether the run can authenticate, without opening any credential: the variable is set, or the login file exists."""
    if provider['auth'] == 'chatgpt':
        return os.path.lexists(os.path.join(provider['auth_home'], AUTH_FILE))
    return bool(os.environ.get(provider['env_key']))


def link_login(provider, codex_home):
    """Give a fresh CODEX_HOME the benchmark login as a symbolic link; the file is never opened or copied."""
    if provider['auth'] != 'chatgpt':
        return None
    home = Path(codex_home)
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    link = home / AUTH_FILE
    if os.path.lexists(link):
        raise ValueError('The fresh CODEX_HOME already holds a login file')
    link.symlink_to(Path(provider['auth_home']) / AUTH_FILE)
    return str(link)


def release_login(provider, codex_home):
    """Remove the link after the run. If Codex replaced the link with a refreshed file, move that file back to the
    benchmark home (a rename, never a read), so no login copy stays in the run directory and the refresh is kept."""
    if provider is None or provider['auth'] != 'chatgpt':
        return None
    link = Path(codex_home) / AUTH_FILE
    if link.is_symlink():
        link.unlink()
        return 'link-removed'
    if link.exists():
        os.replace(link, Path(provider['auth_home']) / AUTH_FILE)
        return 'refreshed-file-moved-back'
    return 'missing'


def service_tier(selection):
    """D14 switch: the service tier sent with every request; 'default' as before."""
    value = selection.get('service_tier', 'default')
    if value not in SERVICE_TIERS:
        raise ValueError('Unsupported service tier')
    return value


def web_search_mode(selection):
    """D5 switch: None keeps the native search setting (no config key); otherwise Codex's web_search mode."""
    value = selection.get('web_search')
    if value is not None and value not in WEB_SEARCH_MODES:
        raise ValueError('Unsupported web_search mode')
    return value


def api_model(selection):
    """API providers take the model identifier verbatim; Strata selections name a quantization instead."""
    model = selection.get('model')
    if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]*', model):
        raise ValueError('API provider selections name the provider model identifier')
    return model


def validate_api_selection(selection):
    provider = api_provider(selection)
    if provider is None:
        raise ValueError('Not an API provider selection')
    present = [key for key in STRATA_ONLY if key in selection]
    if present or selection.get('startup_instructions', True) not in (True, False):
        raise ValueError('API provider selections cannot carry Strata engine or lease settings: ' + ', '.join(present))
    api_model(selection)
    if not isinstance(selection.get('effort'), str):
        raise ValueError('API provider selections state the reasoning effort')
    service_tier(selection)
    web_search_mode(selection)
    return provider
