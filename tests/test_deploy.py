"""Installation credentials are rendered from the project private file only."""
from pathlib import Path
import json
import sys
import tempfile
import tomllib
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.ops.deploy import deployment_files, obsolete_files, private_bytes


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
        self.assertNotIn('installation.private.toml', deployment_files({'models': ['IQ3_XXS']}))

    def test_only_the_served_models_prebuilt_is_deployed_and_the_others_are_removed(self):
        host = {'models': ['IQ3_XXS']}
        files = deployment_files(host)
        self.assertEqual(files['config/iq3_xxs-prebuilt.json'], 'config/templates/iq3_xxs-prebuilt.json')
        self.assertEqual(sorted(t for t in files if t.endswith('-prebuilt.json')), ['config/iq3_xxs-prebuilt.json'])
        self.assertNotIn('config/maintenance-baseline.json', files)
        obsolete = obsolete_files(host)
        # backed up, then removed; weights, runtime and data are never listed
        self.assertTrue({'config/q2_0-prebuilt.json', 'config/iq2_xs-prebuilt.json',
                         'config/maintenance-baseline.json'} <= set(obsolete))
        self.assertFalse(set(obsolete) & set(files))
        self.assertTrue(all(t.startswith(('config/', 'src/', 'maintenance/', 'Run-')) for t in obsolete))

    def test_every_quantization_template_pins_the_mtp_drafter(self):
        # v0.2.10 treats a missing "drafting" as Auto, which swaps to DFlash2 once its drafter file is on the machine
        templates = sorted((Path(__file__).resolve().parents[1]/'config'/'templates').glob('*-prebuilt.json'))
        self.assertEqual(len(templates), 3)
        for template in templates:
            self.assertEqual(json.loads(template.read_text())['drafting'], 'mtp', template.name)


if __name__ == '__main__':
    unittest.main()
