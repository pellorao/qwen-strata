"""Time-limit rule of the agy drivers (runners/carbon-1114, runners/hydrogen-1114): an instance of cs / cstd that was hard-stopped at T is
`timeout` (voided, rerun at 3600 s, not counted as valid); one that timed out at the 3600 s cap stops the driver."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

RUNNERS = Path(__file__).resolve().parents[1] / 'benchmarks/multi-model-v1/runners'


def load(name):
    sys.modules.pop('agyrun', None)   # each runner dir has its own agyrun
    path = RUNNERS / name / 'drive.py'
    spec = importlib.util.spec_from_file_location('drive_' + name.replace('-', '_'), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules.pop('agyrun', None)
    return module


def write(root, key, effort, prefix, attempt, T, hard_stop, valid=True):
    folder = Path(root) / key / f'{prefix}-{effort}-a{attempt}'
    folder.mkdir(parents=True)
    checks = {'valid': valid, 'hard_stop': hard_stop, 'ended_normally': True, 'model_match': True}
    (folder / 'instance.json').write_text(json.dumps({'T': T, 'handoffs': [{'k': 0, 'checks': checks}]}))
    return folder


class TimelimitDriveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def check(self, name, prefix):
        drive = load(name)
        drive.OUT = self.root
        if hasattr(drive, 'CARRY'):
            drive.CARRY = self.root / 'carryover.json'
        a1 = write(self.root, 'cs', 'high', prefix, 1, 1034, True)
        a2 = write(self.root, 'cs', 'high', prefix, 2, 1034, False)
        ca = write(self.root, 'ca', 'high', prefix, 1, None, True)   # only cs / cstd are voided by a hard stop
        self.assertEqual(drive.classify(a1)[0], 'timeout')
        self.assertEqual(drive.classify(a2)[0], 'valid')
        self.assertEqual(drive.classify(ca)[0], 'valid')
        state = drive.cell_state('high', 'cs')
        self.assertEqual((len(state['valid']), len(state['timeout']), state['timeout_at_cap']), (1, 1, []))
        self.assertEqual(drive.limit_for('cs', 'high'), 3600)   # a cell with a timeout reruns at 3600
        write(self.root, 'cs', 'medium', prefix, 1, 3600, True)
        self.assertEqual(drive.cell_state('medium', 'cs')['timeout_at_cap'], [f'{prefix}-medium-a1'])
        return drive

    def test_carbon(self):
        drive = self.check('carbon-1114', 'carbon')
        self.assertEqual(drive.limit_for('cstd', 'low'), 3600)   # Carbon: every cs / cstd instance runs at the cap
        self.assertIsNone(drive.limit_for('ca', 'high'))

    def test_hydrogen(self):
        drive = self.check('hydrogen-1114', 'hydrogen')
        (self.root / 'p4').mkdir()
        (self.root / 'p4/cstd-T.json').write_text(json.dumps({'high': 401, 'medium': 5000, 'xhigh': 341}))
        self.assertEqual([drive.limit_for('cstd', e) for e in ('high', 'medium')], [900, 3600])   # clamped to [900, 3600]
        (self.root / 'carryover.json').write_text(json.dumps({'xhigh/cstd': {'valid': 2, 'timeout': 3, 'attempts': 5}}))
        state = drive.cell_state('xhigh', 'cstd')
        self.assertEqual((len(state['valid']), len(state['timeout']), state['next_attempt']), (2, 3, 6))
        self.assertEqual(drive.limit_for('cstd', 'xhigh'), 3600)


if __name__ == '__main__':
    unittest.main()
