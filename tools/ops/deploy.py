"""Deploy the frontend, configs and caller manual to a local host installation.

Weights, runtime and private dependencies are never touched. The frontend is
stopped through its own lease and restarted by its Windows scheduled task.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

from tools.ops.deployment_source import MODELS, load_host, load_private, source_bytes

ROOT = Path(__file__).resolve().parents[2]
TASK = 'QwenStrataFrontend'
# installation target -> project source
FILES = {f'src/{name}': f'src/{name}' for name in (
    'frontend.py', 'model_process.py', 'native_service.py', 'startup_instructions.py', 'project_files_mcp.py',
    'brave_search.py', 'hosted_search.py', 'brave_mcp.py')}
FILES.update({name: name for name in (
    'config/prompts/startup-instructions.txt', 'config/prompts/compact-prompt.txt', 'config/model-catalog.json',
    'config/maintenance-baseline.json', 'config/deployment.json', 'config/frontend.json')})
FILES.update({f'config/{m.lower()}-prebuilt.json': f'config/templates/{m.lower()}-prebuilt.json' for m in MODELS})
FILES['README.md'] = 'docs/installation-directory-readme.md'
FILES['maintenance/Install-Frontend.ps1'] = 'scripts/windows/Install-Frontend.ps1'
FILES['bin/qwen-agent'] = 'scripts/wsl/qwen-agent'
FILES['bin/qwen-approve'] = 'scripts/wsl/qwen-approve'
# Left by the retired WSL controller and SSH bridge.
OBSOLETE = ('Run-Strata-Controller.ps1', 'Run-Strata-Controller.sh', 'maintenance/Setup-Native-Network.ps1',
            'maintenance/Setup-WSL-Network.sh', 'config/service.json', 'config/startup-instructions.txt',
            'config/compact_prompt.txt', *(f'src/{name}' for name in (
                'responses_bridge.py', 'windows_host.py', 'wsl_launcher.py',
                'setup_wsl_firewall.ps1', 'service_access.py', 'service_settings.py', 'controller_backend.py')))
OBSOLETE_TREES = ('.state', '.tmp/controller-model')
PRIVATE = 'installation.private.toml'


def private_bytes(project=None):
    """Installation credentials, rendered in-process from project.private.toml; never printed or backed up."""
    key = load_private(project).get('brave', {}).get('api_key')
    if not isinstance(key, str) or not key.strip():
        raise ValueError('project.private.toml needs [brave] api_key')
    return ('[brave]\napi_key = ' + json.dumps(key.strip()) + '\n').encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def local_path(windows):
    return Path(subprocess.check_output(['wslpath', '-u', windows], text=True).strip())


class Frontend:
    def __init__(self, base):
        self.base, self.key = base.rstrip('/'), None
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(self, path, body=None, timeout=30):
        headers = {'Content-Type': 'application/json'}
        if self.key:
            headers['Authorization'] = 'Bearer ' + self.key
        request = urllib.request.Request(self.base + path, None if body is None else json.dumps(body).encode(), headers)
        with self.opener.open(request, timeout=timeout) as reply:
            return json.load(reply)

    def reachable(self):
        try:
            self.call('/health', timeout=5)
            return True
        except OSError:
            return False

    def wait(self, up, timeout=60):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.reachable() == up:
                return
            time.sleep(1)
        raise TimeoutError('Frontend did not ' + ('start' if up else 'stop'))


@contextmanager
def maintenance(base):
    """Hold the frontend down while files change; never displace a lease holder."""
    frontend = Frontend(base)
    if frontend.reachable():
        try:
            frontend.key = frontend.call('/lease/acquire', {})['key']
        except urllib.error.HTTPError as error:
            if error.code == 409:
                raise RuntimeError('Frontend lease is held; wait until it is free') from None
            raise
        try:
            if frontend.call('/model/status')['status'] != 'stopped':
                frontend.call('/model/stop', {}, timeout=300)
            frontend.call('/admin/shutdown', {})
        except BaseException:
            frontend.call('/lease/release', {}, timeout=300)
            raise
        frontend.wait(False)
    yield
    started = subprocess.run(['schtasks.exe', '/run', '/tn', TASK], capture_output=True)  # output is in the Windows code page
    if started.returncode:
        raise RuntimeError(f'Scheduled task {TASK} is missing; run maintenance\\Install-Frontend.ps1 once')
    frontend.wait(True)


def deploy(identifier, docs_only=False):
    host = load_host(identifier)
    root = local_path(host['installation_root'])
    if not (root / 'runtime/Strata/.venv').is_dir():
        raise RuntimeError('Installation runtime is missing')
    files = {t: s for t, s in FILES.items() if not docs_only or t == 'README.md'}
    expected = {target: source_bytes(source, identifier) for target, source in files.items()}
    private = None if docs_only else private_bytes()
    backup = ROOT / '.tmp/maintenance-backups' / ('deploy-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    before = {}
    for target in sorted(expected) + ([] if docs_only else list(OBSOLETE)):
        path = root / target
        before[target] = sha(path.read_bytes()) if path.is_file() else None
        if path.is_file():
            (backup / 'files' / target).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, backup / 'files' / target)
    backup.mkdir(parents=True, exist_ok=True)
    (backup / 'before.json').write_text(json.dumps(before, indent=2) + '\n')

    def write():
        for target, data in expected.items():
            path = root / target
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                stream.write(data)
            os.replace(stream.name, path)
        removed = []
        if private is not None:
            with tempfile.NamedTemporaryFile(dir=root, delete=False) as stream:
                stream.write(private)
            os.replace(stream.name, root / PRIVATE)
        if not docs_only:
            for target in OBSOLETE:
                if (root / target).is_file():
                    (root / target).unlink()
                    removed.append(target)
            for tree in OBSOLETE_TREES:
                if (root / tree).is_dir():
                    shutil.rmtree(root / tree)  # private state of the retired controller; never copied
                    removed.append(tree + '/')
        actual = {target: sha((root / target).read_bytes()) for target in expected}
        if actual != {target: sha(data) for target, data in expected.items()}:
            raise RuntimeError('Read-back SHA differs; backup at ' + str(backup))
        if private is not None and (root / PRIVATE).read_bytes() != private:
            raise RuntimeError('Read-back of ' + PRIVATE + ' differs')
        if not docs_only:
            manifest = {'deployment': identifier, 'source': 'maintenance project only',
                        'files': {t: {'source': files[t], 'sha256': actual[t]} for t in sorted(actual)}}
            (root / 'deployment-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        return removed, actual

    # Verified before the frontend restarts, so a failed restart still leaves a checked installation.
    if docs_only:
        removed, actual = write()
    else:
        with maintenance(host['frontend_url']):
            removed, actual = write()
    return {'host': identifier, 'files': len(actual), 'read_back_verified': True,
            'private_file': None if private is None else PRIVATE + ' written and verified',
            'removed': removed, 'backup': str(backup)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--docs-only', action='store_true', help='Only replace the caller manual; frontend keeps running.')
    args = parser.parse_args()
    print(json.dumps(deploy(args.host, args.docs_only), indent=2))


if __name__ == '__main__':
    main()
