"""Offline regressions for reviewback W1-W9; no model subprocess is executed."""
import concurrent.futures
import contextlib
import io
import json
import multiprocessing
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tests.test_benchmark_summary import ranked, record
from tools.reviewer import benchmark_export, blind_pool

RUNNER = Path(__file__).resolve().parents[1] / 'benchmarks/multi-model-v1/runners/hydrogen-1114'


def module(name):
    return runpy.run_path(str(RUNNER / name))


def process_reserve(args):
    """A separate interpreter state, using the same ledger as the other processes."""
    folder, pool = args
    m = module('judge.py')
    m['reserve_call'].__globals__.update(CALLS=Path(folder) / 'calls.jsonl', EXPECT=Path(folder) / 'expect.json')
    try:
        return m['reserve_call'](pool)
    except RuntimeError:
        return None


class JudgeReviewbackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.m = module('judge.py')
        self.log = Mock()
        self.g = self.m['judge'].__globals__
        self.g.update(KEYS=self.base, JUDGE=self.base / 'judge', CALLS=self.base / 'calls.jsonl',
                      EXPECT=self.base / 'expect.json', log=self.log)

    def pool(self, name):
        adj = self.base / name
        adj.mkdir()
        (self.base / f'key-{name}.json').write_text(json.dumps({'pool_path': str(adj / 'pool.json')}))
        (self.base / f'prompt-{name}.md').write_text('offline fixture')
        (adj / f'decisions-{name}.json').write_text('{}')

    def test_w1_threads_reserve_unique_numbers_without_exceeding_cap(self):
        (self.base / 'expect.json').write_text('{"cap": 3}')
        def reserve(i):
            try:
                return self.m['reserve_call'](str(i))
            except RuntimeError:
                return None
        with concurrent.futures.ThreadPoolExecutor(12) as executor:
            results = list(executor.map(reserve, range(24)))
        self.assertEqual(sorted(n for n in results if n is not None), [1, 2, 3])
        self.assertEqual([json.loads(l)['n'] for l in (self.base / 'calls.jsonl').read_text().splitlines()], [1, 2, 3])

    def test_w1_processes_share_the_same_cap(self):
        (self.base / 'expect.json').write_text('{"cap": 3}')
        with multiprocessing.get_context('fork').Pool(4) as pool:
            results = pool.map(process_reserve, [(str(self.base), str(i)) for i in range(12)])
        self.assertEqual(sorted(n for n in results if n is not None), [1, 2, 3])

    def test_w1_cap_blocks_the_model_command(self):
        self.pool('a')
        (self.base / 'expect.json').write_text('{"cap": 0}')
        self.g['tools'] = lambda: (None, None)
        with patch('subprocess.call') as call:
            self.m['judge'](['a'], 1)
        call.assert_not_called()
        self.assertFalse((self.base / 'judge/split-a.ok').exists())
        self.assertIn('STOP:', str(self.log.call_args_list))

    def test_w2_split_error_preserves_later_success_and_retry(self):
        for p in ('bad', 'good'):
            self.pool(p)
        (self.base / 'expect.json').write_text('{"cap": 4}')
        verdict = dict(passed=True, anchors=1, anchor_rate=1, synthetic_all_right=True, decision_counts={}, review=[])
        def split(key, *args, **kw):
            if key.stem == 'key-bad':
                raise ValueError('malformed decisions')
            return verdict, [], []
        split_mock = Mock(side_effect=split)
        self.g['tools'] = lambda: (SimpleNamespace(split=split_mock), None)
        with patch('subprocess.call', return_value=0):
            self.m['judge'](['bad', 'good'], 2)
            self.assertTrue((self.base / 'judge/split-good.ok').is_file())
            self.assertFalse((self.base / 'judge/split-bad.ok').exists())
            self.assertIn('ValueError: malformed decisions', str(self.log.call_args_list))
            split_mock.side_effect = lambda *args, **kw: (verdict, [], [])
            self.m['judge'](['bad', 'good'], 2)
        self.assertTrue((self.base / 'judge/split-bad.ok').is_file())
        self.assertEqual(len((self.base / 'calls.jsonl').read_text().splitlines()), 3)

    def test_w5_pool_name_boundary_including_numbered_shards(self):
        self.g.update(SCENARIOS={'a': 'scenario'}, SCORE=self.base, valid_records=lambda: [])
        for key, skip in [('ab', False), ('a-l', False), ('a-1', True), ('a', True)]:
            with self.subTest(key=key):
                path = self.base / f'key-{key}.json'
                path.write_text('{}')
                build = Mock(side_effect=ValueError('build reached'))
                self.g['tools'] = lambda: (SimpleNamespace(build=build), None)
                if skip:
                    self.m['build']()
                    build.assert_not_called()
                else:
                    with self.assertRaisesRegex(ValueError, 'build reached'):
                        self.m['build']()
                path.unlink()


class SummaryReviewbackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.m = module('summarize.py')
        self.rows = ranked([record(c, i, None, harness_version='1.5.9', requested_effort=effort,
                                   effective_effort=effort, speeds=dict.fromkeys(('engine_input', 'engine_output', 'task_input', 'task_output')))
                            for c, effort in ((30, 'medium'), (31, 'high')) for i in (1, 2)])
        for r in self.rows:
            r.update(effort=r['requested_effort'], handoffs=[], pause_count=0)
        self.records = self.base / 'records.jsonl'
        self.scores = self.base / 'scores'
        for r in self.rows:
            p = self.scores / r['id'] / 'score.json'
            p.parent.mkdir(parents=True)
            p.write_text(json.dumps({'status': 'no-report' if r['attempt'] == 1 else 'final',
                                     'final': 0 if r['attempt'] == 1 else 0.5,
                                     'handoffs': [{'k': 0, 'scored': 'modelFailure:no-report'}] if r['attempt'] == 1 else []}))

    def run_summary(self):
        self.records.write_text(''.join(json.dumps(r) + '\n' for r in self.rows))
        argv = ['summarize.py', '--records', str(self.records), '--score-root', str(self.scores), '--out', str(self.base / 'out')]
        with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(io.StringIO()):
            self.m['main']()
        out = self.base / 'out'
        return json.loads((out / 'summary.json').read_text()), json.loads((out / 'hydrogen-results.json').read_text())

    def test_w3_w4_w6_shared_summary_and_export(self):
        summary, export = self.run_summary()
        benchmark_export.check_source(summary, benchmark_export.sha256(self.base / 'out/summary.json'))
        scenario = summary['scenarios']['commit-audit-v3']
        self.assertEqual(scenario['comparisons'], [])
        self.assertNotIn('paired', summary)
        self.assertNotIn('comparisonDesign', export)
        self.assertEqual([c['n'] for c in scenario['configs']], [2, 2])
        self.assertEqual([c['mean'] for c in scenario['configs']], [0.25, 0.25])
        rows = export['instances']
        self.assertEqual([r['scoring']['score'] for r in rows], [0, 0.5, 0, 0.5])
        self.assertTrue(all(r['configKey'].startswith('antigravity/gemini-4-hydrogen/') for r in rows))
        self.assertTrue(all(r['startedAt'].endswith('+00:00') for r in rows))
        self.assertEqual(rows[0]['startedAt'], '1970-01-01T00:16:40.000000+00:00')
        self.assertTrue(all(r['harnessVersion'] == '1.5.9' and 'agyVersion' not in r and 'speeds' in r for r in rows))

    def test_w8_missing_score_remains_unscored(self):
        (self.scores / self.rows[0]['id'] / 'score.json').unlink()
        summary, export = self.run_summary()
        row = next(r for r in export['instances'] if r['id'] == self.rows[0]['id'])
        self.assertIsNone(row['scoring']['score'])
        self.assertEqual(row['scoring']['status'], 'unscored')
        self.assertFalse(summary['complete'])

    def test_w7_shared_safety_refuses_forbidden_keys_and_preserves_outputs(self):
        self.run_summary()
        out = self.base / 'out'
        before = {p.name: p.read_bytes() for p in out.iterdir()}
        original_build = benchmark_export.build
        for key in ('path', 'prompt', 'answerKey', 'sessionId', 'decisions'):
            with self.subTest(key=key):
                def bad_build(*args, **kwargs):
                    result = original_build(*args, **kwargs)
                    result['instances'][0][key] = 'safe-looking'
                    return result
                with patch.object(benchmark_export, 'build', side_effect=bad_build), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaisesRegex(SystemExit, 'publication-safety'):
                        self.run_summary()
                self.assertEqual({p.name: p.read_bytes() for p in out.iterdir()}, before)


class AnchorsReviewbackTest(unittest.TestCase):
    def test_w9_origin_and_stable_id_and_same_batch_idempotence(self):
        m = module('anchors.py')
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            registry = base / 'registry'
            registry.mkdir()
            target = registry / 'scenario.json'
            target.write_text(json.dumps({'anchors': [{'origin': {'record': 'old', 'stable_id': 'E1'}}]}))
            p = dict(record='new', stable_id='E1', pool_id='pool-001', blind='matched', item={})
            (base / 'picks.json').write_text(json.dumps({'strata': {'scenario:matched': {'picks': [p, p]}}}))
            (base / 'checks.json').write_text(json.dumps({'pool-001': {'decision': 'matched', 'method': 'offline', 'evidence': 'fixture'}}))
            m['register'].__globals__.update(SCENARIOS=('scenario',), REGISTRY=registry, PICKS=base / 'picks.json', CHECKS=base / 'checks.json')
            def add(*args, **kwargs):
                reg = json.loads(target.read_text())
                anchor = {'id': 'new-anchor', 'origin': kwargs['origin']}
                reg['anchors'].append(anchor)
                target.write_text(json.dumps(reg))
                return anchor
            with patch.object(blind_pool, 'anchor_add', side_effect=add) as mock, \
                 patch.object(blind_pool, 'FAMILIES', blind_pool.FAMILIES), contextlib.redirect_stdout(io.StringIO()):
                m['register']()
                m['register']()
                mock.assert_called_once()
            self.assertEqual([a['origin']['record'] for a in json.loads(target.read_text())['anchors']], ['old', 'new'])


if __name__ == '__main__':
    unittest.main()
