import tempfile
import unittest
from pathlib import Path

from tools.safety import claude_gate as gate


class StrataLiveGateTest(unittest.TestCase):
    """G8: the live Strata gate goes through the lease on a registered host and names the served model."""

    def test_live_strata_needs_a_host(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                gate.gate(Path(folder) / 'out', backend='strata', model='qwen3.8-flash-next-iq3_xxs', live=True)

    def test_live_strata_needs_no_quota_label_but_api_backends_do(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'label'):
                gate.gate(Path(folder) / 'out', backend='anthropic', live=True)

    def test_live_strata_rejects_another_model_before_taking_the_lease(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'served model'):
                with gate.strata_live(Path(folder), 'qwen3.8-flash-next-q2_0', 'high', Path(folder), Path(folder),
                                      'rtx3080ti'):
                    pass


if __name__ == '__main__':
    unittest.main()
