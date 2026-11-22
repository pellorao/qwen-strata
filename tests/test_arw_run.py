"""ARW run plumbing: port derivation, startup-prompt binding, result parsing and the provider config."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.arw import run as arw_run


class RunTests(unittest.TestCase):
    def test_ports_follow_user_and_home(self):
        a, b = arw_run.home_ports('/h/one', 'u'), arw_run.home_ports('/h/two', 'u')
        self.assertNotEqual(a, b)
        self.assertEqual(a, arw_run.home_ports('/h/one', 'u'))
        self.assertTrue(30000 <= a[0] < 32768 and 20000 <= a[1] < 30000)

    def test_startup_binding_needs_a_loaded_model_and_equal_sha(self):
        reply = lambda model, sha: {'model': model, 'startup_instructions': {'sha256': sha}}
        self.assertIsNone(arw_run.startup_binding(reply(None, 'x'), 'x')['ok'])
        self.assertTrue(arw_run.startup_binding(reply('m', 'x'), 'x')['ok'])
        differ = arw_run.startup_binding(reply('m', 'y'), 'x')
        self.assertFalse(differ['ok'])
        self.assertEqual((differ['loaded'], differ['expected']), ('y', 'x'))

    def test_expected_startup_sha_is_of_the_loaded_form(self):
        raw = (arw_run.ROOT / 'config/prompts/startup-instructions.txt').read_bytes()
        self.assertEqual(len(arw_run.expected_startup_sha()), 64)
        self.assertNotEqual(arw_run.expected_startup_sha(), arw_run.sha(raw))  # the loop-prevention block is removed

    def test_parse_result_takes_the_last_json_line(self):
        self.assertEqual(arw_run.parse_result('noise\n{"status": "succeeded"}\n'), {'status': 'succeeded'})
        self.assertEqual(arw_run.parse_result('not json')['stage'], 'parse')
        self.assertEqual(arw_run.parse_result('')['status'], 'failed')

    def test_health_reads_the_given_base(self):
        class Reply:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return b'{"lease": "free"}'
        seen = []
        reply = arw_run.health('http://h:1', urlopen=lambda url, timeout: seen.append(url) or Reply())
        self.assertEqual((reply, seen), ({'lease': 'free'}, ['http://h:1/health']))


if __name__ == '__main__':unittest.main()
