"""Transfer files with OpenSSH/SFTP using program-loaded private host settings."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import subprocess
import time
import uuid

from tools.ops.remote_windows import authentication_environment, connection_environment, powershell


def powershell_literal(value):
    if '\n' in value or '\r' in value:
        raise ValueError('Newlines are not valid in transfer paths')
    return "'" + value.replace("'", "''") + "'"


def copy_file(local, remote, settings, known_hosts, *, download=False, timeout=60, recursive=False):
    local = Path(local).resolve()
    path = PureWindowsPath(remote)
    if not path.is_absolute() or '..' in path.parts or '\n' in str(path) or '\r' in str(path):
        raise ValueError('Remote transfer requires an absolute Windows path')
    destination = settings['STRATA_REMOTE_USER'] + '@' + settings['STRATA_REMOTE_HOST'] + ':/' + path.as_posix()
    if os.name == 'nt':
        ssh_root = Path(os.environ['SystemRoot']) / 'System32/OpenSSH'
        command = [str(ssh_root / 'scp.exe'), '-S', str(ssh_root / 'ssh.exe')]
    else:
        command = ['scp']
    identity = settings.get('STRATA_REMOTE_IDENTITY_FILE')
    command.extend(['-q', '-P', settings['STRATA_REMOTE_PORT'], '-o', 'StrictHostKeyChecking=yes',
               '-o', 'UserKnownHostsFile=' + Path(known_hosts).resolve(strict=True).as_posix(),
               '-o', 'ConnectTimeout=10', '-o', 'BatchMode=no' if settings.get('STRATA_REMOTE_PASSWORD') and not identity else 'BatchMode=yes'])
    if identity:
        command.extend(('-i', identity, '-o', 'IdentitiesOnly=yes'))
    if recursive:
        command.append('-r')
    command.extend((destination, str(local)) if download else (str(local), destination))
    started = time.monotonic()
    with authentication_environment(settings) as environment:
        try:
            result = subprocess.run(command, env=environment, stdin=subprocess.DEVNULL,
                                    capture_output=True, timeout=timeout, start_new_session=True)
        except subprocess.TimeoutExpired:
            raise RuntimeError('File transfer timed out; private command/settings not echoed') from None
    if result.returncode:
        error = result.stderr.decode(errors='replace').lower()
        kind = ('path' if 'no such file' in error or 'not found' in error else
                'permission' if 'permission denied' in error else
                'host-key' if 'host key' in error else 'transport')
        raise RuntimeError(f'File transfer {kind} failed (exit {result.returncode}); private settings not echoed')
    return time.monotonic() - started


def transfer_probe(out, host='rtx3080ti', known_hosts=None):
    settings = connection_environment(host=host)
    known_hosts = Path(known_hosts or '.tmp/multi-host-install/ssh-trust/known-hosts-windows')
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    root = PureWindowsPath(settings['installation_path'])
    folder = root / '.tmp' / ('transfer-probe-' + uuid.uuid4().hex)
    remote = folder / '中文 文件.bin'
    source = out / '中文 文件.bin'
    source.write_bytes('Strata 文件传输校验\n'.encode() + os.urandom(65536))
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    intent = {'status': 'running', 'host': host, 'bytes': source.stat().st_size,
              'sha256': expected, 'unicode_and_space_filename': True, 'model_requests': 0}
    (out / 'intent.json').write_text(json.dumps(intent, indent=2) + '\n', encoding='utf-8')
    script = ("$ErrorActionPreference='Stop';[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false);"
              "$dir=" + powershell_literal(str(folder)) + ";"
              "if(Test-Path -LiteralPath $dir){throw 'Probe directory already exists'};"
              "New-Item -ItemType Directory -Path $dir -Force | Out-Null;"
              "[ordered]@{created=$true;model_started=$false}|ConvertTo-Json -Compress")
    created = json.loads(powershell(script, settings, known_hosts=known_hosts))
    assert created['created']
    upload = copy_file(source, remote, settings, known_hosts)
    script = ("$ErrorActionPreference='Stop';[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false);"
              "$file=" + powershell_literal(str(remote)) + ";"
              "[ordered]@{sha256=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLower();"
              "bytes=(Get-Item -LiteralPath $file).Length}|ConvertTo-Json -Compress")
    actual = json.loads(powershell(script, settings, known_hosts=known_hosts))
    if actual['sha256'] != expected or actual['bytes'] != source.stat().st_size:
        raise RuntimeError('Uploaded test file differs; preserve probe evidence')
    downloaded = out / 'roundtrip.bin'
    download = copy_file(downloaded, remote, settings, known_hosts, download=True)
    if hashlib.sha256(downloaded.read_bytes()).hexdigest() != expected:
        raise RuntimeError('Downloaded test file differs; preserve probe evidence')
    script = ("$ErrorActionPreference='Stop';$file=" + powershell_literal(str(remote)) + ";"
              "$dir=" + powershell_literal(str(folder)) + ";Remove-Item -LiteralPath $file;"
              "[System.IO.Directory]::Delete($dir);[Console]::WriteLine('removed')")
    cleaned = powershell(script, settings, known_hosts=known_hosts).strip() == 'removed'
    result = {**intent, 'status': 'passed', 'remote_sha256': actual['sha256'],
              'roundtrip_sha256': hashlib.sha256(downloaded.read_bytes()).hexdigest(),
              'upload_seconds': upload, 'download_seconds': download,
              'remote_probe_removed': cleaned, 'password_echoed': False}
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', action='store_true', required=True)
    parser.add_argument('--host', default='rtx3080ti')
    parser.add_argument('--known-hosts', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(transfer_probe(args.out, args.host, args.known_hosts), indent=2))
