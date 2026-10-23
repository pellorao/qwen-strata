"""Host-bound frontend and log access for measurements; project files remain sources."""
import argparse
import copy
import hashlib
import json
from pathlib import Path, PureWindowsPath
import subprocess

from tools.ops.controller_client import Controller
from tools.ops.deployment_source import load_host, model_configuration, source_bytes

ROOT = Path(__file__).resolve().parents[2]


def local_path(windows):
    return Path(subprocess.check_output(['wslpath', '-u', str(windows)], text=True).strip())


ENGINE_ENVIRONMENT = '''import json,sys,os
from pathlib import Path
import psutil
expected=os.path.normcase(str(Path(sys.argv[1])/'runtime/Strata/engine/strata.exe'))
rows=[]
for p in psutil.process_iter(['pid','exe']):
 if os.path.normcase(p.info['exe'] or '')==expected:
  try:env=p.environ()
  except psutil.AccessDenied:rows.append({'pid':p.pid,'environment':None,'unreadable':'access denied: the engine runs elevated'});continue
  rows.append({'pid':p.pid,'environment':{k:env.get(k)for k in sys.argv[2:]}})
print(json.dumps(rows))
'''


class MeasurementHost:
    condition = None

    def __init__(self, identifier, installation=None, condition=None):
        """`condition` is the tuning condition deployed for this run; sources are checked with it overlaid."""
        self.identifier, self.condition = identifier, condition
        self.deployment = load_host(identifier, condition=condition)
        self.windows_root = PureWindowsPath(self.deployment['installation_root'])
        self.installation = local_path(self.windows_root)
        if installation is not None and Path(installation) != self.installation:
            raise ValueError('Installation differs from the selected host; use private host configuration')

    def _remote(self, code, arguments=()):
        """Run read-only Python on the host's Windows side with the installation runtime; return its JSON stdout.

        WSL interop reaches only the Windows side of this machine, so this host must be the local one.
        """
        python = self.installation / 'runtime/Strata/.venv/Scripts/python.exe'
        if not python.is_file():
            raise RuntimeError('Host Windows side is not reachable from this machine')
        reply = subprocess.run([str(python), '-I', '-c', code, *arguments], cwd='/mnt/c',
                               capture_output=True, text=True, encoding='utf-8',
                               errors='replace', timeout=120, check=True)
        return json.loads(reply.stdout)

    def controller(self, folder):
        return Controller(self.installation, folder, base_url=self.deployment['frontend_url'])

    def metadata(self):
        return {'host_id': self.identifier, 'hardware': self.deployment.get('hardware'),
                'hardware_source_overrides': self.deployment['engine_overrides'],
                'installation_root': str(self.windows_root),
                'deployment_condition': self.condition,
                'source': 'project deployment templates and host configuration'}

    def installed_release(self):
        """Read public upstream version metadata without using it as a source."""
        return json.loads((self.installation / 'config/installed-release.json').read_text())

    def read_deployed_bytes(self, relative):
        from tools.ops.deploy import deployment_files
        if relative not in deployment_files(self.deployment):
            raise ValueError('Only registered public deployment files of the served model may be read')
        return (self.installation / relative).read_bytes()

    def verify_sources(self):
        from tools.ops.deploy import deployment_files, obsolete_files
        expected = {target: hashlib.sha256(source_bytes(source, self.identifier, condition=self.condition)).hexdigest()
                    for target, source in deployment_files(self.deployment).items()}
        actual = {target: hashlib.sha256((self.installation / target).read_bytes()).hexdigest()
                  for target in expected}
        if actual != expected:
            raise RuntimeError('Installed public sources differ from this host project deployment')
        left = [target for target in obsolete_files(self.deployment) if (self.installation / target).exists()]
        if left:
            raise RuntimeError('Installation still holds retired or unserved-model files: ' + ', '.join(left))
        return {'files': actual, 'source_sha_verified': True, **self.metadata()}

    def configuration(self, model):
        expected = model_configuration(model, self.identifier, condition=self.condition)
        actual = json.loads(self.read_deployed_bytes('config/' + model.lower() + '-prebuilt.json'))
        if actual != expected:
            raise RuntimeError('Installed model configuration differs from its host project source')
        return expected

    def profile_sha256(self, model):
        arguments = self.configuration(model)['args']
        profile = local_path(arguments[arguments.index('--expert-profile') + 1])
        return hashlib.sha256(profile.read_bytes()).hexdigest()

    def engine_environment(self, names):
        """The named variables as each running engine process actually holds them (None: unset)."""
        return self._remote(ENGINE_ENVIRONMENT, (str(self.windows_root), *sorted(names)))

    def log_path(self, model):
        return local_path(self.configuration(model)['log'])

    def service_log_path(self):
        """model-server.log: the native service's own stderr (sampling trace), apart from the engine log."""
        return self.installation / 'logs/model-server.log'

    def log_offset(self, model=None):
        log = self.log_path(model) if model else self.service_log_path()
        return log.stat().st_size if log.exists() else 0

    def log_bytes_since(self, model, offset):
        """Bytes appended since offset to the model's engine log, or to the service log when model is None."""
        if type(offset) is not int or offset < 0:
            raise ValueError('Log offset must be a nonnegative byte count')
        log = self.log_path(model) if model else self.service_log_path()
        if log.stat().st_size < offset:
            raise RuntimeError('Bound engine log shrank; cannot attribute stages')
        with log.open('rb') as stream:
            stream.seek(offset)
            return stream.read()


def host_selection(source, identifier):
    """Freeze host hardware values before a run; never silently change them in run."""
    result = copy.deepcopy(source)
    deployment = load_host(identifier)
    if result.get('model_owner') != 'arw':
        # ARW-owned runs start the model with the installation defaults, recorded in the preflight receipt.
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
    selection = args.selection and host_selection(json.loads(args.selection.read_text(encoding='utf-8')), args.host)
    host = MeasurementHost(args.host, condition=selection and selection.get('deployment_condition'))
    if selection:
        (args.out / 'selection.json').write_text(json.dumps(selection, ensure_ascii=False, indent=2) + '\n')
    receipt = host.verify_sources()
    health = host.controller(args.out / 'controller').call('/health', timeout=15)
    if health.get('lease') != 'free':
        raise RuntimeError('Selected host is leased; do not displace its holder')
    # The frontend keeps a released model resident (idle stop after 30 minutes); report it, never assume a stopped engine.
    receipt.update(lease='free', resident_model=health.get('model'), generation_requests=0,
                   model_configurations={m: host.configuration(m) for m in host.deployment['models']},
                   default_profile_sha256={m: host.profile_sha256(m) for m in host.deployment['models']})
    (args.out / 'preflight.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'host': args.host, 'source_files': len(receipt['files']), 'lease': 'free',
                      'resident_model': receipt['resident_model'], 'generation_requests': 0}))


if __name__ == '__main__':
    main()
