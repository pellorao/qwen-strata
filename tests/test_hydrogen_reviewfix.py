"""Offline regressions for common/review 11-16; never start a model or driver."""
import argparse
import ast
import contextlib
import io
import json
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
RUNNERS = ROOT / 'benchmarks/multi-model-v1/runners'
HYDRO = RUNNERS / 'hydrogen-1114'
JUDGES = [HYDRO / 'judge.py', HYDRO / 'judge_low.py',
          RUNNERS / 'timelimit-rerun/judge_carbon.py', RUNNERS / 'timelimit-rerun/judge_old.py']


class ReviewFixTest(unittest.TestCase):
    def low_module(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return runpy.run_path(str(HYDRO / 'low_report.py'))

    def test_export_is_complete_and_low_is_counted_once(self):
        data = json.loads((HYDRO / 'results/phase4/benchmark-results.json').read_text())
        selected = [i for i in data['instances']
                    if (i['selection'] or {}).get('mainStatistic') and i['validity']['valid']]
        low = [i for i in selected if i['requestedEffort'] == 'low']
        self.assertEqual(len(low), 20)
        self.assertEqual(len({i['id'] for i in low}), 20)
        module = self.low_module()
        rows = module['rows']()
        for effort in module['EFFORTS']:
            for scenario, _ in module['SC']:
                with self.subTest(effort=effort, scenario=scenario):
                    self.assertEqual(len(rows[effort, scenario]), 5)

    def test_low_report_rejects_incomplete_or_duplicated_cell(self):
        module = self.low_module()
        source = HYDRO / 'results/phase4/benchmark-results.json'
        data = json.loads(source.read_text())
        selected = next(i for i in data['instances']
                        if i['requestedEffort'] == 'low' and (i['selection'] or {}).get('mainStatistic')
                        and i['validity']['valid'])
        for extra in (False, True):
            changed = dict(data, instances=list(data['instances']))
            if extra:
                changed['instances'].append(selected)
            else:
                changed['instances'].remove(selected)
            with self.subTest(extra=extra), patch.object(Path, 'read_text', return_value=json.dumps(changed)):
                with self.assertRaisesRegex(AssertionError, 'expected 5 main-statistic instances'):
                    module['rows']()

    def test_judge_modes_are_separate_arguments(self):
        for path in JUDGES:
            module = runpy.run_path(str(path))
            for mode, expected in [('lower', ['--provisional', 'lower']),
                                   ('upper', ['--provisional', 'upper']),
                                   (None, []), ('enumerate', ['--enumerate'])]:
                with self.subTest(path=path.name, mode=mode):
                    args = ['judge', 'enumerate' if mode == 'enumerate' else 'score']
                    if mode in ('lower', 'upper'):
                        args += ['--provisional', mode]
                    def score_step(flags, *unused):
                        module['run_bench_score']('offline-record', flags)
                    fake_path = Mock()
                    with patch.dict(module['main'].__globals__, SHM=fake_path, SCORE=fake_path, step=score_step), \
                         patch.object(sys, 'argv', args), patch.object(subprocess, 'run') as run:
                        module['main']()
                    argv = run.call_args.args[0]
                    self.assertEqual(argv[argv.index('--root') + 2:], expected)
                    parser = argparse.ArgumentParser()
                    parser.add_argument('--enumerate', action='store_true')
                    parser.add_argument('--provisional', choices=['lower', 'upper'])
                    parser.parse_args(argv[argv.index('--root') + 2:])

    def test_slot_creates_missing_parent_before_registration(self):
        # Extract only acquire_slot: importing the driver loads operational helpers.
        tree = ast.parse((HYDRO / 'drive.py').read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'acquire_slot')
        (ROOT / '.tmp').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / '.tmp') as folder:
            import fcntl
            guard = SimpleNamespace(live_runs=Mock(return_value=[]), register=Mock(return_value='offline-slot'))
            namespace = dict(ROOT=Path(folder), ug=guard, fcntl=fcntl, MAX_GEMINI=3, LABEL='offline')
            exec(compile(ast.Module(body=[function], type_ignores=[]), str(HYDRO / 'drive.py'), 'exec'), namespace)
            self.assertEqual(namespace['acquire_slot']('low'), 'offline-slot')
            self.assertTrue((Path(folder) / '.tmp/carbonbench/slot.lock').is_file())
            guard.register.assert_called_once()


if __name__ == '__main__':
    unittest.main()
