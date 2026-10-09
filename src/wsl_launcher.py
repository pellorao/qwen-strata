"""Installed WSL entry points for direct Windows-hosted inference."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import urllib.request
from service_settings import load_service_settings

ROOT = Path(__file__).resolve().parents[1]
MODELS = ('Q2_0', 'IQ2_XS', 'IQ3_XXS')


def wsl_network():
    routes = json.loads(subprocess.check_output(['ip', '-j', '-4', 'route', 'show', 'default'], text=True))
    gateways = {row['gateway'] for row in routes if row.get('gateway')}
    if len(gateways) != 1:
        raise RuntimeError('Expected one IPv4 WSL NAT gateway.')
    host = str(ipaddress.IPv4Address(gateways.pop()))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
        connection.connect((host, load_service_settings(ROOT)['listen_port']))
        client = connection.getsockname()[0]
    return host, client


def windows_path(path):
    return subprocess.check_output(['wslpath', '-w', str(path)], text=True).strip()


def host_command(action, host=None, client=None, model='Q2_0'):
    python = ROOT / 'runtime/Strata/.venv/Scripts/python.exe'
    if not python.is_file():
        raise RuntimeError('Use the entry point in the model installation directory.')
    command = [str(python), '-B', windows_path(ROOT / 'src/windows_host.py'), action]
    if host is not None:
        command += ['--host', host, '--client', client, '--model', model]
    result = subprocess.run(command, stdout=subprocess.PIPE, text=True, encoding='utf-8')
    if result.returncode:
        raise RuntimeError(f'Windows host operation failed ({result.returncode}).')
    return json.loads(result.stdout)


def health(host):
    settings = load_service_settings(ROOT)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f'http://{host}:{settings["listen_port"]}/health', timeout=5) as response:
            value = json.load(response)
    except OSError as error:
        raise RuntimeError('WSL cannot reach the host bridge. Run Setup-WSL-Network.sh once to allow TCP 8100/8101 on the Windows WSL virtual adapter; then retry. No forwarding is used.') from error
    model_host = host if settings['model_address'] == 'host' else settings['model_address']
    if value.get('service') != 'strata-responses-bridge' or value.get('backend') != f'http://{model_host}:{settings["model_port"]}':
        raise RuntimeError('Unexpected host bridge.')
    return value




def main():
    if sys.platform != 'linux' or 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower():
        raise SystemExit('Run this entry point inside WSL.')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('controller', 'firewall'))
    args = parser.parse_args()
    if args.action == 'firewall':
        host, client = wsl_network()
        host_command('network', host, client)
        result = subprocess.run(['powershell.exe', '-NoProfile', '-File', windows_path(ROOT / 'src/setup_wsl_firewall.ps1'), '-HostAddress', host])
        return result.returncode
    else:
        host, client = wsl_network()
        value = host_command('controller', host, client)
        health(host)
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        raise SystemExit(str(error))
