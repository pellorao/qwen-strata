import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from native_service import install_sampling_trace


class SamplingTraceTests(unittest.TestCase):
    def test_trace_preserves_original_options_and_hides_non_numeric_payloads(self):
        calls = []
        expected = ' temperature=1.0 top_p=0.95 top_k=20 projection=1 tune=private-value'

        class Engine:
            @staticmethod
            def sampling_keys(options):
                calls.append(options)
                return expected

        options = {'temperature': 1, 'top_p': .95, 'top_k': 20}
        messages = []
        install_sampling_trace(Engine, messages.append)
        self.assertIs(Engine.sampling_keys(options), expected)
        self.assertEqual(calls, [options])
        self.assertIs(calls[0], options)
        self.assertEqual(options, {'temperature': 1, 'top_p': .95, 'top_k': 20})
        self.assertEqual(messages, ['[native-sampling-trace] temperature=1.0 top_p=0.95 top_k=20 projection=1'])

    def test_broken_diagnostic_sink_does_not_change_generation_options(self):
        class Engine:
            @staticmethod
            def sampling_keys(options):
                return ' top_p=1.0 top_k=20'

        def closed_sink(message):
            raise OSError('Closed log')

        install_sampling_trace(Engine, closed_sink)
        self.assertEqual(Engine().sampling_keys({'temperature': 0}), ' top_p=1.0 top_k=20')


if __name__ == '__main__':
    unittest.main()
