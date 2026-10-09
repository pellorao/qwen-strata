import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.reviewer.render_session_event_deltas import render


class SessionEventDeltasTests(unittest.TestCase):
    def test_producer_multiline_and_inline_views_reconstruct_same_full_events(self):
        events = [
            {'type': 'response_item', 'payload': {'type': 'function_call', 'arguments': {'decoded_json': {'cmd': {'exact_text_reference': 3, 'sha256': 'evidence'}}}}},
            {'type': 'response_item', 'payload': {'type': 'function_call', 'arguments': {'decoded_json': {'cmd': {'exact_text_reference': 7, 'sha256': 'other'}}}}}
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outputs = []
            for multiline in [False, True]:
                folder = root / str(multiline);folder.mkdir()
                blocks = []
                for number, event in enumerate(events):
                    separator = '\n' if multiline else ' '
                    blocks.append(f'EVENT {number}' + separator + json.dumps(event, indent=2 if multiline else None) + '\n\n')
                blocks.append('EVENT 2: numeric diagnostic retained in original JSONL.\n')
                (folder / 'events-001.txt').write_text(''.join(blocks))
                summary = render(folder)
                self.assertEqual(summary['events'], 3)
                self.assertTrue(json.loads((folder / 'event-deltas/manifest.json').read_text())['all_structural_fields_reconstructed'])
                outputs.append((folder / 'event-deltas/page-001.txt').read_text())
            self.assertEqual(outputs[0], outputs[1])
            self.assertIn('numeric diagnostic retained', outputs[0])
            self.assertIn('["payload","arguments","decoded_json","cmd","TEXT"],7', outputs[0])

    def test_truncated_json_event_is_rejected_instead_of_becoming_inspected_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / 'events-001.txt').write_text('EVENT 0\n{"type":"response_item",\n')
            with self.assertRaises(json.JSONDecodeError):
                render(folder)


if __name__ == '__main__':
    unittest.main()
