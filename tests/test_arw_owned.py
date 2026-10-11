import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.reviewer.arw_measure import ARW_PAUSE_PREFIX, capture_segment, local_review_catalog, observe_review, run


class ArwOwnedTests(unittest.TestCase):
    def test_pause_message_stops_observation_for_the_user(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            record = {'accepted': {'runId': 'run', 'messageId': 'm'}, 'role': 'commit-audit-reviewer', 'instanceId': 'i', 'started_at': 10,
                      'selection': {'model_owner': 'arw'}}
            pause = {'type': 'message', 'sequence': 4, 'text': ARW_PAUSE_PREFIX + '10 normally completed turns ...'}
            class Machine:
                def call(self, operation, value, **kwargs):
                    assert operation == 'list_agents', operation  # no deadline reminder or continuation from the driver
                    return {'runId': 'run', 'state': 'idle', 'taskState': 'working', 'notifications': [pause],
                            'measurement': {}}
            result = observe_review(Machine(), record, folder)
            self.assertEqual(result['arw_pause']['notification'], pause)
            self.assertFalse(result['complete'])

    def test_catalog_enables_arw_strata_provider_only_when_arw_owns_the_model(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / 'catalog.json'
            source.write_text(json.dumps({'models': [{'slug': 'qwen3.8-flash-next-iq3_xxs'}]}))
            plain = json.loads(local_review_catalog(source, folder / 'a.json', 'IQ3_XXS').read_text())
            self.assertNotIn('providers', plain)
            owned = json.loads(local_review_catalog(source, folder / 'b.json', 'IQ3_XXS', None, '/install').read_text())
            self.assertEqual(owned['providers'], {'qwen_strata': {'driver': 'strata', 'installationDirectory': '/install'}})

    def test_segment_is_bounded_by_the_next_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            log = b'old\nengine started: --max-context 156584\nmine\nnext instance\n'
            class Host:
                def log_bytes_since(self, model, offset):
                    return log[offset:]
            start = len(b'old\n'); end = log.index(b'next')
            _, _, started = capture_segment(Host(), 'IQ3_XXS', start, end, folder)
            self.assertEqual((folder / 'engine-request-log.txt').read_text(), 'engine started: --max-context 156584\nmine\n')
            self.assertEqual(started, '--max-context 156584')

    def test_arw_owned_runs_refuse_driver_parameters(self):
        from unittest.mock import patch
        class Host:
            def __init__(self, *args):
                self.installation = Path('/install'); self.deployment = {'hardware': 'h'}
        selection = {'host_id': 'rtx3080ti', 'host_hardware': 'h', 'model_owner': 'arw', 'model': 'IQ3_XXS',
                     'engine_overrides': {'spec-min-p': 0.9}}
        with patch('tools.reviewer.native_cli_binding.verify_native_cli', return_value=None), \
                patch('tools.ops.measurement_host.MeasurementHost', Host):
            with self.assertRaisesRegex(ValueError, 'installation defaults'):
                run(None, Path('/nonexistent'), selection, [], Path('c'), host='rtx3080ti')


if __name__ == '__main__':
    unittest.main()
