"""Project files that state a context window agree with the published tiers."""
import json
from pathlib import Path
import tempfile
import unittest

from tools.ops import model_catalog

ROOT = Path(__file__).resolve().parents[1]


def installation(folder, tiers):
    path = Path(folder) / 'installation.json'
    path.write_text(json.dumps({'context_tiers': tiers}), encoding='utf-8')
    return path


def tier(window, limit):
    return [{'context_window': window, 'auto_compact_token_limit': limit}]


class CatalogWindowTests(unittest.TestCase):
    def test_default_window_is_the_first_tier(self):
        with tempfile.TemporaryDirectory() as folder:
            path = installation(folder, {'Q2_0': tier(156584, 100000), 'IQ2_XS': tier(156584, 100000),
                                         'IQ3_XXS': tier(206584, 150000) + tier(156584, 100000)})
            self.assertEqual(model_catalog.default_windows(path),
                             {'Q2_0': 156584, 'IQ2_XS': 156584, 'IQ3_XXS': 206584})
        with tempfile.TemporaryDirectory() as folder:
            path = installation(folder, {'Q2_0': tier(156584, 100000)})
            with self.assertRaisesRegex(ValueError, 'IQ2_XS'):
                model_catalog.default_windows(path)

    def test_committed_catalog_states_each_default_tier(self):
        windows = model_catalog.default_windows()
        catalog = json.loads((ROOT / 'config/model-catalog.json').read_text(encoding='utf-8'))
        for entry in catalog['models']:
            quant = next(q for q, s in model_catalog.MODELS.items() if entry['slug'] == 'qwen3.8-flash-next-' + s)
            self.assertEqual((entry['context_window'], entry['max_context_window']), (windows[quant],) * 2)


class ServedModelTests(unittest.TestCase):
    def test_the_installation_serves_one_model_and_publishes_its_default_tier_first(self):
        """One served model (user 2026-10-19); its default window is the first tier, as the catalog states it.
        The maintenance baseline is the served model with the deployment defaults; no separate baseline file."""
        self.assertFalse((ROOT / 'config/maintenance-baseline.json').exists())
        windows = model_catalog.default_windows()
        value = json.loads((ROOT / 'config/installation.json').read_text(encoding='utf-8'))
        self.assertEqual(len(value['models']), 1)
        tiers = value.get('context_tiers', {}).get(value['models'][0])
        self.assertEqual(tiers[0]['context_window'], windows[value['models'][0]])


if __name__ == '__main__':
    unittest.main()
