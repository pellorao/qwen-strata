"""Local WSL and native Windows LAN endpoints have distinct listener/access roles."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from service_settings import load_service_settings


class EndpointSettingsTests(unittest.TestCase):
    def test_legacy_local_defaults_are_preserved_without_new_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            value = load_service_settings(Path(directory))
            self.assertEqual((value['listen_port'], value['model_port']), (8101, 8100))
            self.assertEqual(value['model_address'], 'host')
            self.assertIsNone(value['access_base_url'])

    def fixture(self, root):
        value = {'schema_version': 1, 'transport': 'ssh-windows',
                 'listen_address': '192.168.60.212', 'listen_port': 8000,
                 'model_address': '127.0.0.1', 'model_port': 8100,
                 'access_base_url': 'http://192.168.0.4:28000',
                 'allowed_clients': ['192.168.0.2']}
        path = root / 'config/service.json';path.parent.mkdir()
        return path, value

    def test_existing_router_mapping_does_not_change_model_or_listener_port(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);path, value = self.fixture(root)
            path.write_text(json.dumps(value), encoding='utf-8')
            loaded = load_service_settings(root)
            self.assertEqual(loaded, value)
            self.assertEqual(loaded['access_base_url'], 'http://192.168.0.4:28000')

    def test_unbounded_listener_unprotected_clients_remote_backend_and_credentials_are_rejected(self):
        mutations = [{'listen_address': '0.0.0.0'}, {'allowed_clients': []},
                     {'model_address': '192.168.60.1'}, {'model_port': 8000},
                     {'access_base_url': 'http://password@192.168.0.4:28000'}]
        for mutation in mutations:
            with self.subTest(fields=list(mutation)), tempfile.TemporaryDirectory() as directory:
                root = Path(directory);path, value = self.fixture(root)
                value.update(mutation);path.write_text(json.dumps(value), encoding='utf-8')
                with self.assertRaises(ValueError):load_service_settings(root)


if __name__ == '__main__':
    unittest.main()
