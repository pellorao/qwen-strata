import unittest
from unittest import mock

from tools.strata import verify_codex_compact_prompt as tool


class ArgumentTests(unittest.TestCase):
    def test_model_defaults_to_the_one_the_host_serves(self):
        with mock.patch.object(tool, 'served_model', return_value='Q2_0') as served, \
                mock.patch.object(tool, 'current_host', return_value='h'):
            self.assertEqual(tool.arguments(['--out', 'o']).model, 'Q2_0')
            served.assert_called_with('h')
            self.assertEqual(tool.arguments(['--out', 'o', '--host', 'other']).model, 'Q2_0')
            served.assert_called_with('other')
            self.assertEqual(tool.arguments(['--out', 'o', '--model', 'IQ2_XS']).model, 'IQ2_XS')
            with self.assertRaises(SystemExit):
                tool.arguments(['--out', 'o', '--model', 'Q9'])


if __name__ == '__main__':
    unittest.main()
