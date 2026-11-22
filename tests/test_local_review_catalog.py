import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.strata.review_catalog import local_review_catalog


class LocalReviewCatalogTests(unittest.TestCase):
    def test_local_guardian_and_honest_text_search_keep_source_catalog_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder)/'input.json', Path(folder)/'effective.json'
            original = {'models': [{'slug': 'qwen3.8-flash-next-q2_0',
                'auto_review_model_override': 'codex-auto-review', 'supports_search_tool': True,
                'web_search_tool_type': 'text_and_image'},
                {'slug': 'qwen3.8-flash-next-iq2_xs', 'supports_search_tool': True}]}
            source.write_text(json.dumps(original))
            local_review_catalog(source, target, 'Q2_0')
            effective = json.loads(target.read_text())
            self.assertEqual(effective['models'][0]['auto_review_model_override'], 'qwen3.8-flash-next-q2_0')
            self.assertTrue(effective['models'][0]['supports_search_tool'])
            self.assertEqual(effective['models'][0]['web_search_tool_type'], 'text')
            self.assertEqual(effective['models'][1], original['models'][1])
            self.assertEqual(json.loads(source.read_text()), original)
            with self.assertRaises(ValueError):
                local_review_catalog(source, target, 'IQ3_XXS')

    def test_capacity_is_bound_only_to_selected_model(self):
        with tempfile.TemporaryDirectory() as folder:
            source,target=Path(folder)/'source.json',Path(folder)/'target.json'
            original={'models':[{'slug':'qwen3.8-flash-next-q2_0','context_window':250000},
                                {'slug':'qwen3.8-flash-next-iq2_xs','context_window':250000}]}
            source.write_text(json.dumps(original))
            for capacity in (80000,125000,188000,250000,120584,156584,206584,256584):
                local_review_catalog(source,target,'Q2_0',capacity)
                effective=json.loads(target.read_text())
                self.assertEqual(effective['models'][0]['context_window'],capacity)
                self.assertEqual(effective['models'][0]['max_context_window'],capacity)
                self.assertEqual(effective['models'][1],original['models'][1])
                self.assertEqual(json.loads(source.read_text()),original)
            for value in (True,125000.0,100000):
                with self.assertRaises(ValueError):local_review_catalog(source,target,'Q2_0',value)


if __name__ == '__main__':
    unittest.main()
