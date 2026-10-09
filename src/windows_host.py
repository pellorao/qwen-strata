"""Windows-native process control, called only by the installed WSL entry points."""
import argparse
import contextlib
import ctypes
from ctypes import wintypes
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
from service_settings import load_service_settings

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'runtime/Strata'
LOGS = ROOT / 'logs'


def windows_network(host, client):
    script = "Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -like '*WSL*' } | Select-Object InterfaceAlias,IPAddress,PrefixLength | ConvertTo-Json -Compress"
    output = subprocess.check_output(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], encoding='utf-8')
    rows = json.loads(output)
    if isinstance(rows, dict):
        rows = [rows]
    for row in rows:
        if row['IPAddress'] == host:
            network = ipaddress.IPv4Network(f"{host}/{row['PrefixLength']}", strict=False)
            address = ipaddress.IPv4Address(client)
            if address in (network.network_address, network.broadcast_address) or address == ipaddress.IPv4Address(host) or address not in network:
                raise RuntimeError('Client is not a guest address on the selected WSL network.')
            return row
    raise RuntimeError('The requested host address is not on a Windows WSL virtual adapter.')


@contextlib.contextmanager
def startup_lock():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateMutexW(None, False, 'Local\\QwenStrataStartup')
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    owned = False
    try:
        owned = kernel.WaitForSingleObject(handle, 600000) in (0, 0x80)
        if not owned:
            raise RuntimeError('Another launcher is still starting or stopping Strata.')
        yield
    finally:
        if owned:
            kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)


def request(url, data=None, timeout=3):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, data=None if data is None else json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
    with opener.open(req, timeout=timeout) as response:
        return json.load(response)


def listener(port, address):
    import psutil
    connections = [c for c in psutil.net_connections('tcp') if c.status == psutil.CONN_LISTEN and c.laddr.port == port]
    if any(c.laddr.ip != address for c in connections):
        raise RuntimeError(f'Port {port} already listens on another address; stop before restarting.')
    owners = {c.pid for c in connections}
    if not owners:
        return None
    if len(owners) != 1 or None in owners:
        raise RuntimeError(f'Cannot identify one owner of {address}:{port}.')
    return psutil.Process(owners.pop())


def assert_owner(process, entry):
    command = process.cmdline()
    entry = os.path.normcase(str(entry.resolve()))
    if not process.name().lower().startswith('python') or not any(os.path.normcase(os.path.abspath(arg)) == entry for arg in command):
        raise RuntimeError(f'Port belongs to another application (PID {process.pid}); refusing operation.')


def terminate(process):
    import psutil
    # Capture process identities before killing; do not search by executable name.
    children = process.children(recursive=True)
    for child in reversed(children):
        try:
            child.kill()
        except psutil.NoSuchProcess:
            pass
    try:
        process.kill()
    except psutil.NoSuchProcess:
        pass
    alive = psutil.wait_procs(children + [process], timeout=15)[1]
    if alive:
        raise RuntimeError('Owned process tree did not stop.')


def spawn(label, command, cwd):
    flags = subprocess.CREATE_NO_WINDOW
    if load_service_settings(ROOT)['transport'] == 'ssh-windows':
        flags |= subprocess.CREATE_BREAKAWAY_FROM_JOB
    with (LOGS / f'wsl-{label}.log').open('ab') as log:
        return subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL, stdout=log, stderr=log, creationflags=flags)


def wait_health(url, process):
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('Owned service exited before ready; inspect installation logs.')
        try:
            health = request(url)
            if health.get('loaded', True):
                return health
        except (OSError, ValueError):
            pass
        time.sleep(1)
    raise TimeoutError('Service loading exceeded 600 seconds.')




def _controller(host, clients, settings):
    import psutil
    model_host = host if settings['model_address'] == 'host' else settings['model_address']
    api_port, model_port = settings['listen_port'], settings['model_port']
    api_base = settings['access_base_url'] or f'http://{host}:{api_port}'
    LOGS.mkdir(exist_ok=True)
    entry = ROOT / 'src/responses_bridge.py'
    access = ROOT / '.state/ownership.json'
    with startup_lock():
        process = listener(api_port, host)
        expected = ['--host', host, '--port', str(api_port)]
        for client in dict.fromkeys([*clients, host]):
            expected.extend(('--allow-client', client))
        expected += ['--backend', f'http://{model_host}:{model_port}', '--model-port', str(model_port),
                     '--api-base-url', api_base, '--access-file', str(access)]
        if process:
            assert_owner(process, entry)
            command = process.cmdline()
            if not all(expected[i:i+2] in [command[j:j+2] for j in range(len(command)-1)] for i in range(0, len(expected), 2)):
                raise RuntimeError('Existing controller configuration differs; operator inspection required.')
        else:
            native = listener(model_port, model_host)
            if native:
                assert_owner(native, ROOT/'src/native_service.py')
            proc = spawn('bridge', [sys.executable, '-B', str(entry), *expected], ROOT)
            try:
                wait_health(f'http://{host}:{api_port}/health', proc)
            except BaseException:
                terminate(psutil.Process(proc.pid))
                raise
        return {'controller_base_url': api_base, 'responses_base_url': api_base+'/v1',
                'chat_base_url': api_base+'/v1', 'host': host, 'clients': list(clients),
                'listen_port': api_port, 'model_port': model_port}


def controller(host, client):
    """Bootstrap a WSL broker only; model lifecycle stays key-controlled."""
    settings = load_service_settings(ROOT)
    if settings['transport'] != 'wsl-local':
        raise RuntimeError('Use the native Windows entry for this deployment')
    windows_network(host, client)
    value = _controller(host, [client], settings)
    value['client'] = client
    return value


def native_controller():
    """Bootstrap the configured Windows LAN broker without invoking WSL."""
    settings = load_service_settings(ROOT)
    if settings['transport'] != 'ssh-windows':
        raise RuntimeError('Native Windows LAN entry is not configured')
    host = settings['listen_address']
    command = "Get-NetIPAddress -AddressFamily IPv4 | Select-Object -ExpandProperty IPAddress | ConvertTo-Json -Compress"
    addresses = json.loads(subprocess.check_output(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command], encoding='utf-8'))
    addresses = addresses if isinstance(addresses, list) else [addresses]
    if host not in addresses:
        raise RuntimeError('Configured LAN listener address is not on this Windows computer')
    return _controller(host, settings['allowed_clients'], settings)


def main():
    if os.name != 'nt':
        raise SystemExit('This helper must run with the installed Windows Python.')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('controller', 'native-controller', 'network'))
    parser.add_argument('--host')
    parser.add_argument('--client')
    parser.add_argument('--model', choices=('Q2_0', 'IQ2_XS', 'IQ3_XXS'), default='Q2_0')
    args = parser.parse_args()
    if args.action == 'native-controller':
        result = native_controller()
    elif args.action == 'network':
        result = windows_network(args.host, args.client)
    else:
        result = controller(args.host, args.client)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
