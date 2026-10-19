"""Project files that state a context window agree with the published host tiers."""
import json
from pathlib import Path
import tempfile
import unittest

from tools.ops import model_catalog

ROOT = Path(__file__).resolve().parents[1]


def host(folder, identifier, tiers=None):
    value = {'id': identifier, **({'context_tiers': tiers} if tiers is not None else {})}
    (Path(folder) / (identifier + '.json')).write_text(json.dumps(value), encoding='utf-8')


def tier(window, limit):
    return [{'context_window': window, 'auto_compact_token_limit': limit}]


class CatalogWindowTests(unittest.TestCase):
    def test_default_window_is_the_first_tier_hosts_agree_on(self):
        with tempfile.TemporaryDirectory() as folder:
            host(folder, 'a', {'Q2_0': tier(156584, 100000), 'IQ2_XS': tier(156584, 100000),
                               'IQ3_XXS': tier(206584, 150000) + tier(156584, 100000)})
            host(folder, 'offline')  # a host without tiers states nothing
            self.assertEqual(model_catalog.default_windows(folder),
                             {'Q2_0': 156584, 'IQ2_XS': 156584, 'IQ3_XXS': 206584})
            host(folder, 'b', {'IQ3_XXS': tier(156584, 100000)})
            with self.assertRaisesRegex(ValueError, r'IQ3_XXS \[156584, 206584\]'):
                model_catalog.default_windows(folder)
        with tempfile.TemporaryDirectory() as folder:
            host(folder, 'a', {'Q2_0': tier(156584, 100000)})
            with self.assertRaisesRegex(ValueError, 'IQ2_XS'):
                model_catalog.default_windows(folder)

    def test_committed_catalog_states_each_default_tier(self):
        windows = model_catalog.default_windows()
        catalog = json.loads((ROOT / 'config/model-catalog.json').read_text(encoding='utf-8'))
        for entry in catalog['models']:
            quant = next(q for q, s in model_catalog.MODELS.items() if entry['slug'] == 'qwen3.8-flash-next-' + s)
            self.assertEqual((entry['context_window'], entry['max_context_window']), (windows[quant],) * 2)


class ServedModelTests(unittest.TestCase):
    def test_each_host_serves_one_model_and_publishes_its_default_tier_first(self):
        """One served model per host (user 2026-10-19); its default window is the first tier, as the catalog states it.
        The maintenance baseline is the served model with the deployment defaults; no separate baseline file."""
        self.assertFalse((ROOT / 'config/maintenance-baseline.json').exists())
        windows = model_catalog.default_windows()
        for path in sorted((ROOT / 'config/deployments').glob('*.json')):
            host = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(len(host['models']), 1, path.name)
            tiers = host.get('context_tiers', {}).get(host['models'][0])
            if tiers:  # a host returning from offline adds its tiers before it is deployed
                self.assertEqual(tiers[0]['context_window'], windows[host['models'][0]], path.name)


if __name__ == '__main__':
    unittest.main()
