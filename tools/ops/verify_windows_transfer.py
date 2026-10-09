"""User-run Windows-native SCP/SSH roundtrip; no model transfer or inference."""
import argparse
import base64
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import subprocess
import sys
import time
import uuid

from tools.ops.remote_windows import host_configuration

ROOT = Path(__file__).resolve().parents[2]


def literal(value):
    if '\n' in value or '\r' in value:
        raise ValueError('Invalid transfer path')
    return "'" + value.replace("'", "''") + "'"


def process_image(pid):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                               wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        raise RuntimeError('Cannot verify native client process identity')
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        count = wintypes.DWORD(len(buffer))
        if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(count)):
            raise RuntimeError('Native executable identity is unavailable')
        return buffer.value
    finally:
        kernel.CloseHandle(handle)


def verify(host):
    if os.name != 'nt':
        raise SystemExit('Run this test from Windows PowerShell using Windows Python.')
    settings = host_configuration(host=host)
    executable_root = Path(os.environ['SystemRoot']) / 'System32/OpenSSH'
    ssh, scp = executable_root / 'ssh.exe', executable_root / 'scp.exe'
    if not ssh.is_file() or not scp.is_file():
        raise SystemExit('Windows OpenSSH client executables are missing.')
    out = ROOT / '.tmp/multi-host-install' / ('windows-file-transfer-probe-' + uuid.uuid4().hex)
    out.mkdir(parents=True, exist_ok=False)
    proofs = []
    identity = settings['ssh'].get('identity_file')
    key_options = []
    if identity:
        if not Path(identity).is_file():
            raise SystemExit('Configured Windows SSH private-key file is missing.')
        key_options = ['-i', identity, '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes']

    def execute(command, capture=False):
        # The inherited Windows console handles password entry. The driver does
        # not read, log, copy to arguments or save the configured password.
        started = time.monotonic()
        process = subprocess.Popen(command, stdout=subprocess.PIPE if capture else None)
        image = process_image(process.pid)
        proofs.append({'pid': process.pid, 'image': image})
        if os.path.normcase(image) != os.path.normcase(str(Path(command[0]).resolve())):
            process.terminate()
            raise RuntimeError('Client process is not the selected Windows executable')
        output, _ = process.communicate()
        if process.returncode:
            raise RuntimeError('Native client failed; inspect its message in your local terminal')
        return output, time.monotonic() - started

    def remote(script):
        encoded = base64.b64encode(script.encode('utf-16le')).decode()
        command = [str(ssh), '-T', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=10',
                   *key_options, '-p', str(settings['ssh']['port']), '-l', settings['ssh']['username'], settings['ip'],
                   'powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded]
        output, _ = execute(command, capture=True)
        return json.loads(output.decode('utf-8-sig').strip())

    prefix = "$ErrorActionPreference='Stop';[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false);"
    root = PureWindowsPath(settings['installation_path'])
    folder = root / '.tmp' / ('windows-transfer-probe-' + uuid.uuid4().hex)
    destination = folder / '中文 文件.bin'
    source = out / '中文 文件.bin'
    source.write_bytes('Windows 原生文件传输校验\n'.encode() + os.urandom(65536))
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    print('Testing native Windows SSH/SCP with a 64 KiB file. ' +
          ('Using configured key authentication.' if identity else 'Enter SSH passwords in this terminal when prompted.'), flush=True)
    remote(prefix + "$dir=" + literal(str(folder)) + ";"
           "if(Test-Path -LiteralPath $dir){throw 'Probe directory exists'};"
           "New-Item -ItemType Directory -Path $dir -Force|Out-Null;"
           "[ordered]@{created=$true}|ConvertTo-Json -Compress")
    host_path = settings['ssh']['username'] + '@' + settings['ip'] + ':/' + destination.as_posix()
    base = [str(scp), '-S', str(ssh), '-P', str(settings['ssh']['port']),
            *key_options, '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=10']
    _, uploaded = execute([*base, str(source), host_path])
    actual = remote(prefix + "$file=" + literal(str(destination)) + ";"
                    "[ordered]@{bytes=(Get-Item -LiteralPath $file).Length;"
                    "sha256=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLower()}|ConvertTo-Json -Compress")
    if actual['sha256'] != expected or actual['bytes'] != source.stat().st_size:
        raise RuntimeError('Remote test file checksum or size differs; preserve test evidence')
    downloaded = out / 'roundtrip.bin'
    _, download_time = execute([*base, host_path, str(downloaded)])
    if hashlib.sha256(downloaded.read_bytes()).hexdigest() != expected:
        raise RuntimeError('Roundtrip checksum differs; preserve test evidence')
    remote(prefix + "Remove-Item -LiteralPath " + literal(str(destination)) + ";"
           "[System.IO.Directory]::Delete(" + literal(str(folder)) + ");"
           "[ordered]@{removed=$true}|ConvertTo-Json -Compress")
    result = {'status': 'passed', 'native_windows_clients': True, 'processes': proofs,
              'bytes': source.stat().st_size, 'sha256': expected, 'remote_sha256': actual['sha256'],
              'roundtrip_sha256': hashlib.sha256(downloaded.read_bytes()).hexdigest(),
              'upload_seconds': uploaded, 'download_seconds': download_time,
              'remote_probe_removed': True, 'password_logged': False, 'model_requests': 0}
    result['host'] = host
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.host), indent=2))
