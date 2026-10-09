"""Installed service endpoints generated from project-owned host configuration."""
import ipaddress
import json
from pathlib import Path
from urllib.parse import urlsplit


def load_service_settings(root):
    path = Path(root) / 'config/service.json'
    if not path.exists():
        return {'schema_version': 1, 'transport': 'wsl-local', 'listen_address': None,
                'listen_port': 8101, 'model_address': 'host', 'model_port': 8100,
                'access_base_url': None, 'allowed_clients': []}
    value = json.loads(path.read_text(encoding='utf-8'))
    expected = {'schema_version', 'transport', 'listen_address', 'listen_port',
                'model_address', 'model_port', 'access_base_url', 'allowed_clients'}
    if set(value) != expected or value['schema_version'] != 1:
        raise ValueError('Invalid installed service configuration')
    if value['transport'] not in ('wsl-local', 'ssh-windows'):
        raise ValueError('Unknown installed service transport')
    for name in ('listen_port', 'model_port'):
        if type(value[name]) is not int or not 1 <= value[name] <= 65535:
            raise ValueError('Invalid installed listener port')
    if value['listen_port'] == value['model_port']:
        raise ValueError('Public controller and internal model need distinct ports')
    if value['model_address'] != 'host':
        if not ipaddress.IPv4Address(value['model_address']).is_loopback:
            raise ValueError('Separate internal model address must be loopback')
    clients = value['allowed_clients']
    if not isinstance(clients, list):
        raise ValueError('Allowed clients must be an explicit address list')
    for client in clients:
        ipaddress.IPv4Address(client)
    if value['transport'] == 'ssh-windows':
        address = ipaddress.IPv4Address(value['listen_address'])
        networks = [ipaddress.IPv4Network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')]
        if not any(address in network for network in networks) or not clients:
            raise ValueError('Native LAN controller requires a specific private address and explicit clients')
    if value['access_base_url'] is not None:
        url = urlsplit(value['access_base_url'])
        if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.path or url.query or url.fragment:
            raise ValueError('Invalid external service base URL')
        if not url.port:
            raise ValueError('External service URL needs its access port')
    return value
