"""Installation credentials are rendered from the project private file only."""
from pathlib import Path
import sys
import tempfile
import tomllib
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.ops.deploy import FILES, private_bytes


class DeployTests(unittest.TestCase):
    def test_private_file_carries_only_the_brave_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'project.private.toml').write_text('[brave]\napi_key = "k\\"1"\n[hosts.x]\ninstallation_path = "C:\\\\x"\n')
            self.assertEqual(tomllib.loads(private_bytes(root).decode()), {'brave': {'api_key': 'k"1'}})
            (root/'project.private.toml').write_text('[hosts.x]\n')
            with self.assertRaisesRegex(ValueError, 'api_key'):
                private_bytes(root)

    def test_private_file_is_never_a_public_deployment_file(self):
        self.assertNotIn('installation.private.toml', FILES)


if __name__ == '__main__':
    unittest.main()
