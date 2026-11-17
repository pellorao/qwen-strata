"""reviewfix1117: judge_low / judge_carbon / judge_old carry the same fixes as hydrogen-1114/judge.py; offline."""
import concurrent.futures
import json
import runpy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

RUNNERS = Path(__file__).resolve().parents[1] / 'benchmarks/multi-model-v1/runners'
COPIES = [RUNNERS / 'hydrogen-1114/judge_low.py', RUNNERS / 'timelimit-rerun/judge_carbon.py',
          RUNNERS / 'timelimit-rerun/judge_old.py']


class JudgeCopyTest(unittest.TestCase):
    def load(self, path):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        m = runpy.run_path(str(path))
        log = Mock()
        m['judge'].__globals__.update(KEYS=base, JUDGE=base / 'judge', CALLS=base / 'calls.jsonl',
                                      EXPECT=base / 'expect.json', log=log)
        return m, base, log

    def pool(self, base, name):
        adj = base / name
        adj.mkdir()
        (base / f'key-{name}.json').write_text(json.dumps({'pool_path': str(adj / 'pool.json')}))
        (base / f'prompt-{name}.md').write_text('x')
        (adj / f'decisions-{name}.json').write_text('{}')

    def test_reserve_call_is_atomic_across_threads(self):
        for path in COPIES:
            with self.subTest(path=path.name):
                m, base, _ = self.load(path)
                (base / 'expect.json').write_text('{"cap": 3}')
                def reserve(i):
                    try:
                        return m['reserve_call'](str(i))
                    except RuntimeError:
                        return None
                with concurrent.futures.ThreadPoolExecutor(12) as ex:
                    got = list(ex.map(reserve, range(24)))
                self.assertEqual(sorted(n for n in got if n), [1, 2, 3])
                self.assertEqual(len((base / 'calls.jsonl').read_text().splitlines()), 3)

    def test_one_failing_pool_keeps_the_others_marker(self):
        verdict = dict(passed=True, anchors=1, anchor_rate=1, synthetic_all_right=True, decision_counts={}, review=[])
        for path in COPIES:
            with self.subTest(path=path.name):
                m, base, log = self.load(path)
                for p in ('bad', 'good'):
                    self.pool(base, p)
                (base / 'expect.json').write_text('{"cap": 4}')
                def split(key, *a, **kw):
                    if key.stem == 'key-bad':
                        raise ValueError('malformed')
                    return verdict, [], []
                m['judge'].__globals__['tools'] = lambda: (SimpleNamespace(split=Mock(side_effect=split)), None)
                with patch('subprocess.call', return_value=0):
                    m['judge'](['bad', 'good'], 2)
                self.assertTrue((base / 'judge/split-good.ok').is_file())
                self.assertFalse((base / 'judge/split-bad.ok').exists())
                self.assertIn('ValueError: malformed', str(log.call_args_list))

    def test_pool_name_prefix_is_not_a_match(self):
        for path in COPIES:
            for key, skip in [('ab', False), ('a-l', False), ('a-1', True), ('a', True)]:
                with self.subTest(path=path.name, key=key):
                    m, base, _ = self.load(path)
                    m['build'].__globals__.update(SCENARIOS={'a': 'scenario'}, SCORE=base, valid_records=lambda: [])
                    (base / f'key-{key}.json').write_text('{}')
                    build = Mock(side_effect=ValueError('build reached'))
                    m['build'].__globals__['tools'] = lambda: (SimpleNamespace(build=build), None)
                    if skip:
                        m['build']()
                        build.assert_not_called()
                    else:
                        with self.assertRaisesRegex(ValueError, 'build reached'):
                            m['build']()

    def test_carbon_registers_hydrogen_family(self):
        m = runpy.run_path(str(RUNNERS / 'timelimit-rerun/judge_carbon.py'))
        blind_pool, _ = m['tools']()
        self.assertIn('hydrogen', blind_pool.FAMILIES)


if __name__ == '__main__':
    unittest.main()
