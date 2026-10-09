"""Read-only Windows inventory over SSH; secrets stay in hosts.private.toml."""
import argparse
import base64
from contextlib import contextmanager
import json
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[2]


def host_configuration(path=None, host='rtx3080ti'):
    if not isinstance(host, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]*', host):
        raise ValueError('Use a lowercase alphanumeric host identifier with optional hyphens')
    path = Path(path or ROOT / 'hosts.private.toml')
    try:
        entries = tomllib.loads(path.read_text(encoding='utf-8-sig'))['hosts']
        item = entries[host]
    except (KeyError, TypeError, UnicodeError, tomllib.TOMLDecodeError):
        # A parser exception may quote a line containing a secret.
        raise ValueError('Invalid private host configuration or unknown host') from None
    if not isinstance(item, dict) or item.get('transport') not in ('wsl-local', 'ssh-windows'):
        raise ValueError('Host needs a supported transport')
    expected = {'transport', 'ip', 'installation_path', 'service'}
    if item['transport'] == 'ssh-windows':
        expected.add('ssh')
    if set(item) != expected:
        raise ValueError('Host fields differ from its transport schema')
    service = item['service']
    if not isinstance(service, dict) or set(service) != {'listen_port', 'access_port', 'model_port'}:
        raise ValueError('Service needs listen_port, access_port and model_port fields')
    for port in (service['listen_port'], service['access_port'], service['model_port']):
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('Ports must be integers between 1 and 65535')
    if service['listen_port'] == service['model_port']:
        raise ValueError('Controller and internal model service need distinct listener ports')
    installation = item['installation_path']
    if (not isinstance(installation, str) or not installation or
            not PureWindowsPath(installation).is_absolute() or '..' in PureWindowsPath(installation).parts):
        raise ValueError('Fill installation_path with an absolute Windows path')
    if not isinstance(item['ip'], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.:-]*', item['ip']):
        raise ValueError('Fill host ip/address')
    if item['transport'] == 'ssh-windows':
        ssh = item['ssh']
        if (not isinstance(ssh, dict) or not {'port', 'username'} <= set(ssh)
                or set(ssh) - {'port', 'username', 'password', 'identity_file'}):
            raise ValueError('SSH needs port and username; password and identity_file are optional')
        if type(ssh['port']) is not int or not 1 <= ssh['port'] <= 65535:
            raise ValueError('Invalid SSH port')
        for key in ('username', 'password'):
            if key in ssh and not isinstance(ssh[key], str):
                raise ValueError('SSH fields must be strings')
        if not ssh['username'] or '\n' in ssh['username'] or '\r' in ssh['username']:
            raise ValueError('Fill a valid SSH username')
        if 'identity_file' in ssh and not isinstance(ssh['identity_file'], str):
            raise ValueError('SSH identity_file must be a path string')
    return item


def connection_environment(path=None, host='rtx3080ti'):
    item = host_configuration(path, host)
    if item['transport'] != 'ssh-windows':
        raise ValueError('Local host uses the local entry, not SSH')
    ssh, service = item['ssh'], item['service']
    for key, value in (('ip', item['ip']), ('username', ssh['username'])):
        if not isinstance(value, str):
            raise ValueError('Connection text fields must be strings')
        if not value:
            raise ValueError('Fill private host field: ' + key)
    result = {'STRATA_REMOTE_HOST': item['ip'], 'STRATA_REMOTE_USER': ssh['username'],
            'host_id': host,
            'STRATA_REMOTE_PORT': str(ssh['port']),
            'listen_port': service['listen_port'], 'access_port': service['access_port'],
            'model_port': service['model_port'],
            'installation_path': item['installation_path'],
            'api_base_url': f"http://{item['ip']}:{service['access_port']}"}
    if ssh.get('identity_file'):
        result['STRATA_REMOTE_IDENTITY_FILE'] = ssh['identity_file']
    if 'password' in ssh:
        result['STRATA_REMOTE_PASSWORD'] = ssh['password']
    return result


@contextmanager
def authentication_environment(settings):
    """Keep the password out of commands, files and captured output."""
    environment = dict(os.environ)
    if os.name == 'nt':
        identity = settings.get('STRATA_REMOTE_IDENTITY_FILE')
        if not identity or not Path(identity).is_file():
            raise RuntimeError('Set up the dedicated Windows SSH key before unattended native operations')
        environment.pop('STRATA_PRIVATE_SSH_PASSWORD', None)
        environment['SSH_ASKPASS_REQUIRE'] = 'never'
        yield environment
        return
    with tempfile.TemporaryDirectory(prefix='strata-ssh-', dir='/tmp') as folder:
        password = settings.get('STRATA_REMOTE_PASSWORD')
        if password:
            helper = Path(folder) / 'askpass.py'
            helper.write_text('#!/usr/bin/env python3\nimport os\nprint(os.environ["STRATA_PRIVATE_SSH_PASSWORD"])\n', encoding='utf-8')
            helper.chmod(0o700)
            environment.update(SSH_ASKPASS=str(helper), SSH_ASKPASS_REQUIRE='force',
                               DISPLAY='strata-ssh', STRATA_PRIVATE_SSH_PASSWORD=password)
        yield environment


def powershell(script, settings=None, timeout=60, known_hosts=None):
    settings = settings or connection_environment()
    if os.name != 'nt' and settings.get('STRATA_REMOTE_IDENTITY_FILE'):
        # The networking process must be a native Windows ssh.exe so the user
        # can keep a specific Windows process allowlist. Pass only operational
        # script text through stdin; the Windows worker loads private settings.
        python = os.environ.get('QWEN_WINDOWS_CLIENT_PYTHON', '/mnt/c/Python314/python.exe')
        worker = subprocess.check_output(['wslpath', '-w', str(ROOT / 'tools/ops/windows_remote.py')], text=True).strip()
        request = {'script': script, 'timeout': timeout}
        if known_hosts is not None:
            request['known_hosts'] = subprocess.check_output(['wslpath', '-w', str(Path(known_hosts).resolve(strict=True))], text=True).strip()
        try:
            reply = subprocess.run([python, worker, '--host', settings['host_id']],
                                   input=json.dumps(request).encode('utf-8'), capture_output=True, timeout=timeout + 15)
        except subprocess.TimeoutExpired:
            raise RuntimeError('Native Windows remote operation timed out; private request not echoed') from None
        if reply.returncode:
            raise RuntimeError('Native Windows remote worker failed; private stderr not echoed')
        value = json.loads(reply.stdout.decode('utf-8-sig'))
        if not value.get('ok'):
            raise RuntimeError(value.get('error', 'Native Windows remote operation failed'))
        return value['stdout']
    executable = str(Path(os.environ['SystemRoot']) / 'System32/OpenSSH/ssh.exe') if os.name == 'nt' else 'ssh'
    command = [executable, '-T', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=10',
               '-p', settings['STRATA_REMOTE_PORT'], '-l', settings['STRATA_REMOTE_USER']]
    if known_hosts is not None:
        trusted = Path(known_hosts).resolve(strict=True)
        command.extend(('-o', 'UserKnownHostsFile=' + trusted.as_posix()))
    if settings.get('STRATA_REMOTE_IDENTITY_FILE'):
        identity = Path(settings['STRATA_REMOTE_IDENTITY_FILE']).expanduser()
        if not identity.is_file():
            raise ValueError('SSH identity file does not exist')
        command.extend(('-i', str(identity), '-o', 'IdentitiesOnly=yes'))
    password = settings.get('STRATA_REMOTE_PASSWORD') and not settings.get('STRATA_REMOTE_IDENTITY_FILE')
    command.extend(('-o', 'BatchMode=no' if password else 'BatchMode=yes'))
    encoded = base64.b64encode(script.encode('utf-16le')).decode()
    command.extend((settings['STRATA_REMOTE_HOST'], 'powershell.exe', '-NoProfile',
                    '-NonInteractive', '-EncodedCommand', encoded))
    with authentication_environment(settings) as environment:
        try:
            result = subprocess.run(command, env=environment, stdin=subprocess.DEVNULL,
                                    capture_output=True, timeout=timeout, start_new_session=True)
        except subprocess.TimeoutExpired:
            raise RuntimeError('SSH operation timed out; private command not echoed') from None
    if result.returncode:
        # Do not echo the command, connection data or unfiltered SSH stderr.
        error = result.stderr.decode(errors='replace')
        kind = ('host-key verification' if 'Host key verification failed' in error else
                'authentication' if 'Permission denied' in error else
                'connection' if 'Connection' in error or 'timed out' in error else
                'remote command')
        raise RuntimeError(f'SSH {kind} failed (exit {result.returncode}); private settings were not printed')
    return result.stdout.decode('utf-8-sig').strip()


INVENTORY = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$cpu = Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors
$system = Get-CimInstance Win32_ComputerSystem
$os = Get-CimInstance Win32_OperatingSystem
$gpu = @()
$smi = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
if ($smi) {
  $gpu = @( & $smi.Source --query-gpu=name,memory.total,driver_version,compute_cap --format=csv,noheader,nounits )
  if ($LASTEXITCODE -ne 0) { throw 'nvidia-smi inventory failed' }
}
$python = @(Get-Command python.exe,python3.exe,py.exe -ErrorAction SilentlyContinue | Select-Object Name,Source)
$disks = @(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | Select-Object DeviceID,Size,FreeSpace)
$wsl = $null
if (Get-Command wsl.exe -ErrorAction SilentlyContinue) {
  $wsl = (& wsl.exe --list --quiet 2>$null | Out-String).Trim([char]0, [char]13, [char]10, [char]32)
}
[ordered]@{cpu=@($cpu);ram_bytes=$system.TotalPhysicalMemory;free_ram_kib=$os.FreePhysicalMemory;
  os=$os.Caption;gpu=$gpu;python=$python;disks=$disks;wsl_distributions=$wsl;
  model_started=$false;installation_modified=$false} | ConvertTo-Json -Depth 6 -Compress
'''


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='rtx3080ti', help='Private TOML host identifier.')
    parser.add_argument('--known-hosts', type=Path, help='Existing verified SSH host-key records.')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = json.loads(powershell(INVENTORY, connection_environment(host=args.host), known_hosts=args.known_hosts))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
