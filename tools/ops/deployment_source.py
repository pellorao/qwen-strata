"""Render installation inputs exclusively from project templates and host data."""
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
import tomllib

ROOT = Path(__file__).resolve().parents[2]
# Every quantization the project knows; a host serves exactly one of them (its `models` entry, user 2026-10-19).
# Overrides, environment and tiers of the others stay in the host file as unpublished data.
MODELS = ('Q2_0', 'IQ2_XS', 'IQ3_XXS')
MODEL_PORT = 8100
PUBLIC_FIELDS = {'schema_version', 'id', 'cuda_arch', 'models', 'engine_overrides', 'model_overrides', 'model_environment', 'hardware',
                 'qualification', 'listen_address', 'port', 'installation_defaults', 'context_tiers', 'note'}
# presence_penalty: Strata 0.2.x fills sampling keys the request and the run config leave out from the model card, whose
# thinking-off set carries presence_penalty 1.5 (serve/server.py MODEL_CARD_SAMPLING), so a host pins it explicitly.
INSTALLATION_DEFAULTS = {'reasoning_effort', 'reasoning_budget_tokens', 'max_tokens',
                         'guardian_reasoning_budget_tokens', 'guardian_max_tokens',
                         'cpu_prefill_share', 'temperature', 'top_p', 'top_k', 'presence_penalty'}
CONDITION_FIELDS = {'id', 'model', 'model_overrides', 'model_environment', 'request_defaults'}
# A tuning condition may vary only these request defaults (min_p, presence_penalty: sampling dimension, 2026-10-24), and only for its own model
CONDITION_REQUEST_DEFAULTS = {'temperature', 'top_p', 'top_k', 'min_p', 'presence_penalty'}


def load_private(project=None):
    """Parse project.private.toml in-process; its values never go to output, logs or reports."""
    return tomllib.loads((Path(project or ROOT) / 'project.private.toml').read_text(encoding='utf-8-sig'))


def load_host(identifier, project=None, condition=None):
    """Host deployment; a tuning `condition` overlays one model's overrides/environment/sampling until the default returns."""
    project = Path(project or ROOT)
    if not isinstance(identifier, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]*', identifier):
        raise ValueError('Invalid host identifier')
    value = json.loads((project / 'config/deployments' / (identifier + '.json')).read_text(encoding='utf-8'))
    if value.get('schema_version') != 2 or value.get('id') != identifier:
        raise ValueError('Deployment identity/schema mismatch')
    if set(value) - PUBLIC_FIELDS:
        raise ValueError('Unknown deployment field; credentials belong in project.private.toml')
    private = load_private(project).get('hosts', {}).get(identifier, {})
    value['installation_root'] = private.get('installation_path', '')
    value['frontend_url'] = private.get('frontend_url', '')
    root = PureWindowsPath(value['installation_root'])
    if not root.is_absolute() or '..' in root.parts:
        raise ValueError('Host needs an absolute Windows installation_path in project.private.toml')
    if type(value.get('cuda_arch')) is not int or value['cuda_arch'] <= 0:
        raise ValueError('Deployment needs its actual CUDA architecture')
    models = value.get('models')
    if not isinstance(models, list) or len(models) != 1 or set(models) - set(MODELS):
        raise ValueError('A host serves exactly one known model')
    if not isinstance(value.get('engine_overrides'), dict):
        raise ValueError('engine_overrides must be an object')
    per_model = value.setdefault('model_overrides', {})
    if (not isinstance(per_model, dict) or set(per_model) - set(MODELS)
            or not all(isinstance(v, dict) for v in per_model.values())):
        raise ValueError('model_overrides maps known models to engine overrides tuned for that model')
    environment = value.setdefault('model_environment', {})
    if (not isinstance(environment, dict) or set(environment) - set(MODELS)
            or not all(isinstance(v, dict) for v in environment.values())):
        raise ValueError('model_environment maps known models to engine environment tuned for that model')
    defaults = value.get('installation_defaults', {})
    if not isinstance(defaults, dict) or set(defaults) - INSTALLATION_DEFAULTS:
        raise ValueError('Unsupported per-host installation defaults')
    guardian = [defaults.get(k) for k in ('guardian_reasoning_budget_tokens', 'guardian_max_tokens')]
    if guardian != [None, None] and not all(type(v) is int and v > 0 for v in guardian):
        raise ValueError('Guardian defaults need both a thinking budget and a total output limit')
    tiers = value.setdefault('context_tiers', {})
    if not isinstance(tiers, dict) or set(tiers) - set(MODELS) or not all(
            isinstance(v, list) and v and len({t.get('context_window') for t in v}) == len(v) and all(
                isinstance(t, dict) and set(t) == {'context_window', 'auto_compact_token_limit'}
                and type(t['context_window']) is int and type(t['auto_compact_token_limit']) is int
                and 0 < t['auto_compact_token_limit'] < t['context_window'] for t in v) for v in tiers.values()):
        raise ValueError('context_tiers maps known models to measured context windows with their compaction limits')
    if condition is not None:
        from src.model_process import ENVIRONMENT
        if (not isinstance(condition, dict) or set(condition) - CONDITION_FIELDS
                or not re.fullmatch(r'[a-z0-9][a-z0-9.-]*', str(condition.get('id', '')))
                or condition.get('model') not in models
                or not all(isinstance(condition.get(k, {}), dict)
                           for k in ('model_overrides', 'model_environment', 'request_defaults'))
                or set(condition.get('model_environment', {})) - ENVIRONMENT
                or set(condition.get('request_defaults', {})) - CONDITION_REQUEST_DEFAULTS
                or not all(type(v) in (int, float) for v in condition.get('request_defaults', {}).values())):
            raise ValueError('A deployment condition names the served model and its engine overrides/environment/sampling')
        model = condition['model']
        per_model[model] = {**per_model.get(model, {}), **condition.get('model_overrides', {})}
        environment[model] = {**environment.get(model, {}), **condition.get('model_environment', {})}
        if condition.get('request_defaults'):
            value['condition_request_defaults'] = {model: condition['request_defaults']}
        value['deployment_condition'] = condition['id']
    return value


def _public_host_file(identifier, project=None):
    if not isinstance(identifier, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]*', identifier):
        raise ValueError('Invalid host identifier')
    return json.loads((Path(project or ROOT) / 'config/deployments' / (identifier + '.json')).read_text(encoding='utf-8'))


def served_model(identifier, project=None):
    """The one model the host serves, from the public host file (no private inputs)."""
    models = _public_host_file(identifier, project).get('models')
    if not isinstance(models, list) or len(models) != 1 or models[0] not in MODELS:
        raise ValueError(f'{identifier} must serve exactly one known model')
    return models[0]


def published_tier(identifier, model, context_window=None, project=None):
    """One published context tier from the public host file (no private inputs): the default first tier
    unless `context_window` names another. A model without published tiers is an error, never a guess."""
    tiers = _public_host_file(identifier, project).get('context_tiers', {}).get(model)
    if not tiers:
        raise ValueError(f'{identifier} publishes no context tier for {model}')
    match = [t for t in tiers if context_window is None or t['context_window'] == context_window]
    if not match:
        raise ValueError(f'{identifier} publishes no {context_window} tier for {model}')
    return {'context_window': match[0]['context_window'], 'auto_compact_token_limit': match[0]['auto_compact_token_limit']}


def host_for_installation(installation, project=None):
    """Registered host whose private installation_path is this local installation."""
    import subprocess
    project = Path(project or ROOT)
    for path in sorted((project / 'config/deployments').glob('*.json')):
        root = load_private(project).get('hosts', {}).get(path.stem, {}).get('installation_path')
        if root and Path(subprocess.check_output(['wslpath', '-u', root], text=True).strip()) == Path(installation):
            return path.stem
    raise ValueError('Installation is not a registered local host')


def load_condition(path):
    """A frozen condition file; its bytes' SHA binds the deployment to the plan."""
    raw = Path(path).read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def frontend_configuration(identifier, project=None):
    host = load_host(identifier, project)
    return {'listen_address': host['listen_address'], 'port': host['port'], 'model_port': MODEL_PORT}


def model_configuration(model, identifier, project=None, condition=None):
    project = Path(project or ROOT)
    host = load_host(identifier, project, condition)
    if model not in host['models']:
        raise ValueError('Model is not registered for this host')
    value = json.loads((project / 'config/templates' / (model.lower() + '-prebuilt.json')).read_text(encoding='utf-8'))

    def render(item):
        if isinstance(item, str):
            result = item.replace('${INSTALL_ROOT}', host['installation_root'])
            if '${' in result:
                raise ValueError('Unresolved deployment template variable')
            return result
        if isinstance(item, list):
            return [render(x) for x in item]
        if isinstance(item, dict):
            return {k: render(x) for k, x in item.items()}
        return item

    value = render(value)
    value['port'] = MODEL_PORT
    overrides = {**host['engine_overrides'], **host['model_overrides'].get(model, {})}
    defaults = host.get('installation_defaults', {})
    tiers = host['context_tiers'].get(model)
    if tiers:
        # The first published tier is the default window; callers may select only a published tier.
        overrides['max-context'] = tiers[0]['context_window']
    for key, item in overrides.items():
        item, flag = render(item), '--' + key
        if item is None:
            if flag in value['args']:
                del value['args'][value['args'].index(flag):value['args'].index(flag) + 2]
        elif flag in value['args']:
            value['args'][value['args'].index(flag) + 1] = str(item)
        else:
            value['args'] += [flag, str(item)]
    if tiers:
        value['context_tiers'] = tiers
    request = {k: v for k, v in defaults.items() if k != 'cpu_prefill_share'}
    request.update(host.get('condition_request_defaults', {}).get(model, {}))
    if request:
        value['request_defaults'] = request
    if 'cpu_prefill_share' in defaults:
        value['engine_environment'] = {'STRATA_PREFILL_CPU_SHARE': defaults['cpu_prefill_share']}
    if host['model_environment'].get(model):
        # null leaves the variable unset, so the engine applies its own default
        environment = {**value.get('engine_environment', {}), **host['model_environment'][model]}
        value['engine_environment'] = {k: v for k, v in environment.items() if v is not None}
        if not value['engine_environment']:
            del value['engine_environment']
    return value


def public_host(identifier, project=None, condition=None):
    """The installation's deployment.json: per-model data only for the served model."""
    host = load_host(identifier, project, condition)
    value = {k: v for k, v in host.items() if k in PUBLIC_FIELDS | {'deployment_condition'}}
    for field in ('model_overrides', 'model_environment', 'context_tiers'):
        value[field] = {m: v for m, v in value[field].items() if m in host['models']}
    return value


def source_bytes(relative, identifier, project=None, condition=None):
    """Bytes the installation must hold at `relative`'s target, rendered for this host."""
    project = Path(project or ROOT)
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Source must be a project-relative path')
    if path.parent.as_posix() == 'config/templates':
        model = path.name.removesuffix('-prebuilt.json').upper()
        return (json.dumps(model_configuration(model, identifier, project, condition), indent=2) + '\n').encode()
    if path.as_posix() == 'config/deployment.json':
        return (json.dumps(public_host(identifier, project, condition), indent=2) + '\n').encode()
    if path.as_posix() == 'config/frontend.json':
        return (json.dumps(frontend_configuration(identifier, project), indent=2) + '\n').encode()
    if path.as_posix() == 'config/model-catalog.json':
        # The installed catalog lists only the served model, with its default (first published) tier on this host.
        # A served model without published tiers would leave the catalog window unrelated to the engine's.
        raw = (project / path).read_bytes()
        host, value = load_host(identifier, project, condition), json.loads(raw)
        value['models'] = [e for e in value['models']
                           if e['slug'].removeprefix('qwen3.8-flash-next-').upper() in host['models']]
        if len(value['models']) != 1:
            raise ValueError(f'The catalog needs one entry for {identifier} served model {host["models"][0]}')
        for entry in value['models']:
            model = entry['slug'].removeprefix('qwen3.8-flash-next-').upper()
            if model not in host['context_tiers']:
                raise ValueError(f'{identifier} publishes no context tier for served model {model}')
            entry['context_window'] = entry['max_context_window'] = host['context_tiers'][model][0]['context_window']
        return raw if value == json.loads(raw) else (json.dumps(value, ensure_ascii=False, indent=1) + '\n').encode()
    return (project / path).read_bytes()


def installation_model_config(installation, model, identifier, project=None):
    """Return project input after checking the target copy, never use it as a template."""
    expected = model_configuration(model, identifier, project)
    actual = json.loads((Path(installation) / 'config' / (model.lower() + '-prebuilt.json')).read_text(encoding='utf-8'))
    if actual != expected:
        raise ValueError('Installed model configuration differs from project deployment source')
    return expected
