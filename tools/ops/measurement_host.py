"""Host-bound controller and internal-log access; project files remain sources."""
import argparse
import base64
import copy
import hashlib
import json
import re
from pathlib import Path, PureWindowsPath
import subprocess

from tools.ops.controller_client import Controller
from tools.ops.deployment_source import load_host, model_configuration, source_bytes
from tools.ops.remote_windows import connection_environment
from tools.ops.install_windows import remote_python

ROOT = Path(__file__).resolve().parents[2]


class MeasurementHost:
    def __init__(self, identifier, installation=None):
        self.identifier = identifier
        self.deployment = load_host(identifier)
        self.remote = self.deployment['transport'] == 'ssh-windows'
        root = self.deployment['installation_root']
        self.windows_root = PureWindowsPath(root)
        self.settings = connection_environment(host=identifier) if self.remote else None
        native = root if self.remote else subprocess.check_output(['wslpath', '-u', root], text=True).strip()
        self.installation = Path(native)
        if installation is not None and Path(installation) != self.installation:
            raise ValueError('Installation differs from the selected host; use private host configuration')

    def controller(self, folder):
        return Controller(self.installation, folder,
            base_url=self.settings['api_base_url'] if self.remote else None)

    def metadata(self):
        # Never serialize the private SSH connection object.
        return {'host_id': self.identifier, 'transport': self.deployment['transport'],
                'hardware': self.deployment.get('hardware'),
                'hardware_source_overrides': self.deployment['engine_overrides'],
                'installation_root': str(self.windows_root),
                'source': 'project deployment templates and host configuration'}

    def installed_release(self):
        """Read public upstream version metadata without using it as a source."""
        if not self.remote:
            return json.loads((self.installation/'config/installed-release.json').read_text())
        return self._remote('''import json,sys
from pathlib import Path
print((Path(sys.argv[1])/'config/installed-release.json').read_text(encoding='utf-8'))
''', (str(self.windows_root),))

    def read_search_operation(self, directory_hash, call_id):
        """Fetch a bound public tool receipt; never read ownership credentials."""
        if not re.fullmatch(r'[a-f0-9]{64}', directory_hash) or not re.fullmatch(r'wc_[a-f0-9]{32}', call_id):
            raise ValueError('Invalid bound search operation identity')
        relative = '.state/search/'+directory_hash+'/'+call_id+'.json'
        if not self.remote:
            return json.loads((self.installation/relative).read_text(encoding='utf-8-sig'))
        return self._remote('''import json,sys
from pathlib import Path
print((Path(sys.argv[1])/sys.argv[2]).read_text(encoding='utf-8-sig'))
''', (str(self.windows_root), relative))

    def maintenance_baseline(self, source):
        result = copy.deepcopy(source)
        result['start_options']['engine_overrides'].update(self.deployment['engine_overrides'])
        return result

    def maintenance_profile_binding(self, baseline):
        profile = baseline['profile']
        config = self.configuration('Q2_0')
        args = config['args']
        actual = PureWindowsPath(args[args.index('--expert-profile')+1])
        expected = self.windows_root/profile['installation_relative_path']
        if (actual != expected or config.get('expert_profile_save')
                or any(a.startswith('--expert-profile-save') for a in args)
                or profile['save_enabled'] or self.profile_sha256('Q2_0') != profile['sha256']):
            raise ValueError('Host default profile/no-save binding differs')
        raw = self.read_deployed_bytes('config/q2_0-prebuilt.json')
        return {'profile': profile, 'prebuilt_config_sha256': hashlib.sha256(raw).hexdigest()}

    def _remote(self, code, arguments=()):
        executable = self.windows_root / 'runtime/Strata/.venv/Scripts/python.exe'
        return json.loads(remote_python(self.settings, code, arguments, executable=executable))

    def read_deployed_bytes(self, relative):
        from tools.ops.deploy_wsl import FILES
        if relative not in FILES:
            raise ValueError('Only registered public deployment files may be read')
        if not self.remote:
            return (self.installation / relative).read_bytes()
        result = self._remote('''import base64,json,sys
from pathlib import Path
p=Path(sys.argv[1])/sys.argv[2]
print(json.dumps({'data':base64.b64encode(p.read_bytes()).decode()}))
''', (str(self.windows_root), relative))
        return base64.b64decode(result['data'], validate=True)

    def verify_sources(self):
        from tools.ops.deploy_wsl import FILES
        expected = {target: hashlib.sha256(source_bytes(source, self.identifier)).hexdigest()
                    for target, source in FILES.items()}
        if self.remote:
            actual = self._remote('''import hashlib,json,sys
from pathlib import Path
r=Path(sys.argv[1]);names=json.loads(sys.argv[2])
print(json.dumps({n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in names}))
''', (str(self.windows_root), json.dumps(list(expected))))
        else:
            actual = {target: hashlib.sha256((self.installation / target).read_bytes()).hexdigest()
                      for target in expected}
        if actual != expected:
            raise RuntimeError('Installed public sources differ from this host project deployment')
        return {'files': actual, 'source_sha_verified': True, **self.metadata()}

    def configuration(self, model):
        expected = model_configuration(model, self.identifier)
        actual = json.loads(self.read_deployed_bytes('config/' + model.lower() + '-prebuilt.json'))
        if actual != expected:
            raise RuntimeError('Installed model configuration differs from its host project source')
        return expected

    def profile_sha256(self, model):
        config = self.configuration(model)
        arguments = config['args']
        profile = arguments[arguments.index('--expert-profile') + 1]
        if self.remote:
            return self._remote('''import hashlib,json,sys
from pathlib import Path
print(json.dumps({'sha256':hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest()}))
''', (profile,))['sha256']
        local = subprocess.check_output(['wslpath', '-u', profile], text=True).strip()
        return hashlib.sha256(Path(local).read_bytes()).hexdigest()

    def log_offset(self, model):
        config = self.configuration(model)
        if self.remote:
            return self._remote('''import json,sys
from pathlib import Path
p=Path(sys.argv[1]);print(json.dumps({'size':p.stat().st_size if p.exists() else 0}))
''', (config['log'],))['size']
        local = Path(subprocess.check_output(['wslpath', '-u', config['log']], text=True).strip())
        return local.stat().st_size if local.exists() else 0

    def log_bytes_since(self, model, offset):
        if type(offset) is not int or offset < 0:
            raise ValueError('Log offset must be a nonnegative byte count')
        config = self.configuration(model)
        if self.remote:
            result = self._remote('''import base64,json,sys
from pathlib import Path
p=Path(sys.argv[1]);offset=int(sys.argv[2])
if p.stat().st_size<offset:raise RuntimeError('Bound engine log shrank; cannot attribute stages')
with p.open('rb') as stream:
 stream.seek(offset);data=stream.read()
print(json.dumps({'data':base64.b64encode(data).decode()}))
''', (config['log'], offset))
            return base64.b64decode(result['data'], validate=True)
        local = Path(subprocess.check_output(['wslpath', '-u', config['log']], text=True).strip())
        if local.stat().st_size < offset:
            raise RuntimeError('Bound engine log shrank; cannot attribute stages')
        with local.open('rb') as stream:
            stream.seek(offset)
            return stream.read()


def host_selection(source, identifier):
    """Freeze host hardware values before a run; never silently change them in run."""
    result = copy.deepcopy(source)
    deployment = load_host(identifier)
    result['engine_overrides'].update(deployment['engine_overrides'])
    result['host_id'] = identifier
    result['host_hardware'] = deployment.get('hardware')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--selection', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    host = MeasurementHost(args.host)
    if args.selection:
        selection = host_selection(json.loads(args.selection.read_text(encoding='utf-8')), args.host)
        (args.out/'selection.json').write_text(json.dumps(selection,ensure_ascii=False,indent=2)+'\n')
    receipt = host.verify_sources()
    controller = host.controller(args.out/'controller')
    health = controller.call('/health', timeout=15)
    if health.get('ownership') != 'free' or not health.get('available'):
        raise RuntimeError('Selected host is occupied; do not displace its owner')
    receipt.update(controller_ownership='free', model_started=False, generation_requests=0,
                   model_configurations={m:host.configuration(m) for m in host.deployment['models']},
                   default_profile_sha256={m:host.profile_sha256(m) for m in host.deployment['models']})
    (args.out/'preflight.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'host':args.host,'source_files':len(receipt['files']),
                      'controller_ownership':'free','model_started':False,'generation_requests':0}))


if __name__ == '__main__':
    main()
