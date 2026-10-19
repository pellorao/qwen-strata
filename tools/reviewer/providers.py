"""Reviewer model providers: the local Strata service, or an API provider reached directly by Codex.

A selection without a ``provider`` entry is the Strata path and keeps its existing settings byte for byte.
An API provider (OpenAI, DeepSeek) takes no lease and has no engine log: tokens come from API usage.
"""
import re

STRATA_PROVIDER = 'qwen_strata'
STRATA_KEY = 'STRATA_API_KEY'
# Default credential variables. The isolated Codex environment drops every CODEX_* and OPENAI_* variable
# (tools/reviewer/arw_native_setup.mjs), so a key under those prefixes would never reach Codex.
API_PROVIDERS = {'openai': {'name': 'OpenAI', 'env_key': 'BENCHMARK_OPENAI_API_KEY'},
                 'deepseek': {'name': 'DeepSeek', 'env_key': 'BENCHMARK_DEEPSEEK_API_KEY'}}
SERVICE_TIERS = ('default', 'flex', 'priority')
WEB_SEARCH_MODES = ('disabled', 'cached', 'live')
# Strata-only selection fields: engine, lease and frontend settings that an API provider cannot honor.
STRATA_ONLY = ('model_owner', 'engine_overrides', 'engine_environment', 'sampling', 'deployment_condition',
               'loop_reminder', 'loop_prevention_instructions', 'automatic_continuation', 'host_id', 'host_hardware')


def api_provider(selection):
    """None for the Strata path; otherwise the validated API provider this selection names."""
    value = selection.get('provider')
    if value is None:
        return None
    if not isinstance(value, dict) or value.get('id') not in API_PROVIDERS:
        raise ValueError('Unsupported Reviewer provider; choose one of ' + ', '.join(API_PROVIDERS))
    known = API_PROVIDERS[value['id']]
    base = value.get('base_url')
    # The endpoint is stated by the run plan from the provider's current documentation, never guessed here.
    if not isinstance(base, str) or not re.fullmatch(r'https://[^\s/]+(/[^\s]*)?', base):
        raise ValueError('An API provider needs its https base_url in the selection')
    env_key = value.get('env_key', known['env_key'])
    if (not isinstance(env_key, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]*', env_key)
            or env_key.startswith(('CODEX_', 'OPENAI_', 'STRATA_'))):
        raise ValueError('Provider env_key must be an uppercase variable outside the CODEX_, OPENAI_ and STRATA_ prefixes')
    extra = set(value) - {'id', 'base_url', 'env_key', 'name'}
    if extra:
        raise ValueError('Unknown provider fields: ' + ', '.join(sorted(extra)))
    return {'id': value['id'], 'codex_id': 'benchmark_' + value['id'], 'name': value.get('name', known['name']),
            'base_url': base.rstrip('/'), 'env_key': env_key}


def provider_entry(provider, base_url=None):
    """Codex model_providers entry; Codex itself reads the key through env_key."""
    return {'name': provider['name'], 'base_url': base_url or provider['base_url'], 'wire_api': 'responses',
            'env_key': provider['env_key'], 'requires_openai_auth': False, 'supports_websockets': False}


def shell_exclude(provider):
    """Variables Reviewer shell commands never see: the provider key, and the Strata key in every case."""
    return [STRATA_KEY] if provider is None else [provider['env_key'], STRATA_KEY]


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
