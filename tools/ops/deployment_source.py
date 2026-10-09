"""Render installation inputs exclusively from project templates and host data."""
import argparse
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
from tools.ops.remote_windows import host_configuration

ROOT = Path(__file__).resolve().parents[2]
MODELS = ('Q2_0', 'IQ2_XS', 'IQ3_XXS')
HARDWARE_OPTIONS = {
    'prefill': (4096, 8192, 16384), 'kv-resident': (20480, 32768),
    'pool-workers': (8, 12, 15, 23), 'expert-cache': ('auto', 5000, 6000),
    'vram-reserve-mib': (700, 981, 1200), 'pool-affinity': ('auto', 'p-cores', 'all'),
}


def load_host(identifier='local', project=None):
    project = Path(project or ROOT)
    if not isinstance(identifier, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]*', identifier):
        raise ValueError('Invalid deployment identifier')
    value = json.loads((project / 'config/deployments' / (identifier + '.json')).read_text(encoding='utf-8'))
    if value.get('schema_version') != 1 or value.get('id') != identifier:
        raise ValueError('Deployment identity/schema mismatch')
    allowed = {'schema_version', 'id', 'transport', 'installation_root', 'cuda_arch',
               'models', 'engine_overrides', 'hardware', 'qualification', 'ssh_host',
               'connection_host', 'listen_address', 'model_address', 'allowed_clients', 'installation_defaults'}
    if set(value) - allowed:
        raise ValueError('Unknown deployment field; do not put credentials in host data')
    connection = value.get('connection_host')
    if connection:
        private = host_configuration(project / 'hosts.private.toml', connection)
        if private['transport'] != value['transport']:
            raise ValueError('Public/private deployment transport differs')
        value['installation_root'] = private['installation_path']
        value['service_ports'] = private['service']
        value['access_address'] = private['ip']
    root = value.get('installation_root')
    if not isinstance(root, str) or not PureWindowsPath(root).is_absolute() or '..' in PureWindowsPath(root).parts:
        raise ValueError('Deployment needs an absolute Windows installation root')
    if value.get('transport') not in ('wsl-local', 'ssh-windows'):
        raise ValueError('Unsupported deployment transport')
    if value['transport'] == 'ssh-windows' and not connection and (not isinstance(value.get('ssh_host'), str)
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', value['ssh_host'])):
        raise ValueError('Remote deployment requires an SSH config alias')
    if type(value.get('cuda_arch')) is not int or value['cuda_arch'] <= 0:
        raise ValueError('Deployment needs its actual CUDA architecture')
    models = value.get('models')
    if (not isinstance(models, list) or not models or any(m not in MODELS for m in models)
            or len(set(models)) != len(models)):
        raise ValueError('Invalid installed model selection')
    overrides = value.get('engine_overrides')
    if not isinstance(overrides, dict):
        raise ValueError('Hardware overrides must be an object')
    for key, item in overrides.items():
        if (key not in HARDWARE_OPTIONS or isinstance(item, bool)
                or item not in HARDWARE_OPTIONS[key]
                or key not in ('expert-cache', 'pool-affinity') and type(item) is not int
                or key == 'expert-cache' and item != 'auto' and type(item) is not int):
            raise ValueError('Unsupported hardware override: ' + key)
    defaults=value.get('installation_defaults',{})
    permitted={'max_context','reasoning_effort','reasoning_budget_tokens','max_tokens','cpu_prefill_share','temperature','top_p','top_k'}
    if not isinstance(defaults,dict) or set(defaults)-permitted:
        raise ValueError('Unsupported per-host installation defaults')
    for key,item in defaults.items():
        if key=='reasoning_effort':valid=item in ('low','medium','high')
        elif key=='cpu_prefill_share':valid=type(item)in(int,str)and item in (0,'auto')
        elif key=='max_context':valid=type(item)is int and item in (80000,125000,188000,250000,120584,156584,206584,256584)
        elif key=='reasoning_budget_tokens':valid=type(item)is int and 2048<=item<=8192
        elif key=='temperature':valid=type(item)in(int,float)and 0<=item<=2
        elif key=='top_p':valid=type(item)in(int,float)and 0<=item<=1
        elif key=='top_k':valid=type(item)is int and 1<=item<=64
        else:valid=type(item)is int and 8192<=item<=24576
        if not valid:raise ValueError('Invalid per-host installation default: '+key)
    if any(k in defaults for k in ('reasoning_budget_tokens','max_tokens'))and'reasoning_effort'not in defaults:
        raise ValueError('Installed budget defaults require an effort binding')
    return value


def service_configuration(deployment='local', project=None):
    host = load_host(deployment, project)
    ports = host.get('service_ports', {'listen_port': 8101, 'model_port': 8100, 'access_port': 8101})
    native = host['transport'] == 'ssh-windows'
    return {'schema_version': 1, 'transport': host['transport'],
            'listen_address': host.get('listen_address') if native else None,
            'listen_port': ports['listen_port'],
            'model_address': host.get('model_address', '127.0.0.1' if native else 'host'),
            'model_port': ports['model_port'],
            'access_base_url': f"http://{host['access_address']}:{ports['access_port']}" if native else None,
            'allowed_clients': host.get('allowed_clients', [])}


def model_configuration(model, deployment='local', project=None):
    project = Path(project or ROOT)
    host = load_host(deployment, project)
    if model not in host['models']:
        raise ValueError('Model is not registered for this deployment')
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
    value['port'] = service_configuration(deployment, project)['model_port']
    for key, item in host['engine_overrides'].items():
        flag = '--' + key
        if flag in value['args']:
            value['args'][value['args'].index(flag) + 1] = str(item)
        else:
            value['args'].extend((flag, str(item)))
    defaults=host.get('installation_defaults',{})
    if 'max_context'in defaults:
        value['args'][value['args'].index('--max-context')+1]=str(defaults['max_context'])
    request={k:defaults[k]for k in ('reasoning_effort','reasoning_budget_tokens','max_tokens','temperature','top_p','top_k')if k in defaults}
    if request:value['request_defaults']=request
    if 'cpu_prefill_share'in defaults:
        value['engine_environment']={'STRATA_PREFILL_CPU_SHARE':defaults['cpu_prefill_share']}
    return value


def baseline_configuration(deployment='local', project=None):
    project = Path(project or ROOT)
    host = load_host(deployment, project)
    value = json.loads((project / 'config/maintenance-baseline.json').read_text(encoding='utf-8'))
    value['start_options']['engine_overrides'].update(host['engine_overrides'])
    return value


def source_bytes(relative, deployment='local', project=None):
    project = Path(project or ROOT)
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Source must be a project-relative path')
    if path.parent.as_posix() == 'config/templates':
        model = path.name.removesuffix('-prebuilt.json').upper()
        value = model_configuration(model, deployment, project)
        return (json.dumps(value, indent=2) + '\n').encode()
    if path.as_posix() == 'config/deployment.json':
        host = load_host(deployment, project)
        return (json.dumps(host, indent=2) + '\n').encode('utf-8')
    if path.as_posix() == 'config/service.json':
        return (json.dumps(service_configuration(deployment, project), indent=2) + '\n').encode('utf-8')
    if path.as_posix() == 'config/maintenance-baseline.json':
        raw = (project / path).read_bytes()
        value = baseline_configuration(deployment, project)
        # Preserve the current local baseline byte binding when hardware values
        # are unchanged. Remote values are explicit, never inferred from target.
        if value == json.loads(raw):
            return raw
        return (json.dumps(value, indent=2) + '\n').encode()
    return (project / path).read_bytes()


def installation_model_config(installation, model, deployment='local', project=None):
    """Return project input after checking the target copy, never use it as a template."""
    expected = model_configuration(model, deployment, project)
    actual = json.loads((Path(installation) / 'config' / (model.lower() + '-prebuilt.json')).read_text(encoding='utf-8'))
    if actual != expected:
        raise ValueError('Installed model configuration differs from project deployment source')
    return expected


def stage(deployment, out, project=None):
    from tools.ops.deploy_wsl import FILES
    project = Path(project or ROOT)
    host = load_host(deployment, project)
    out = Path(out).resolve()
    # A staging directory must never be confused with a runnable installation.
    if out.exists():
        raise ValueError('Staging destination exists; preserve earlier deployment evidence')
    payloads = {}
    for target, source in FILES.items():
        if source.startswith('config/templates/') and source.split('/')[-1].split('-prebuilt')[0].upper() not in host['models']:
            continue
        payloads[target] = source_bytes(source, deployment, project)
    manifest = {'deployment': host['id'], 'installation_root': host['installation_root'],
                'cuda_arch': host['cuda_arch'], 'models': host['models'],
                'source': 'maintenance project only', 'files': {}}
    out.mkdir(parents=True)
    for target, data in payloads.items():
        path = out / target
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        manifest['files'][target] = {'source': FILES[target], 'sha256': hashlib.sha256(data).hexdigest()}
    (out / 'deployment-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deployment', default='local')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = stage(args.deployment, args.out)
    print(json.dumps({'deployment': result['deployment'], 'files': len(result['files']),
                      'out': str(args.out), 'model_started': False}))
