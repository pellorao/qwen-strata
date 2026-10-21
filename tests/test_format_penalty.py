"""Benchmark format penalty of scoring upgrade r7 (user 2026-10-15)."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.reviewer.format_penalty import (ARCHIVE, REGISTRY, bootstrap_interval, final_score, penalty, pooled_baseline,
                                           registered_baseline, registered_entry, repairable_count, score_repetitions,
                                           verify_archive)

ROOT = Path(__file__).resolve().parents[1]
CS51 = ('code-standards-reviewer', '3950875c7c223af3beee58265c1fb9eb3ff48cf21cbd4b94ffa43a124a0d0b66')
SR41 = ('spec-readiness-reviewer', '3093980fc37278abd16a935cd10d143dbcbab19435671bdee7e7fd2f13c3526f')


def instance(instance_id, key=CS51, locators=100, unrepairable=0, overrun=0, **extra):
    return {'instanceId': instance_id, 'locatorCount': locators, 'judgmentBinding': {'expectedSha256': key[1]},
            'unrepairableFormatErrors': unrepairable, 'overrunLocators': overrun, **extra}


def upstream(reviewer, *instances, score=0.8):
    return {'results': [{'reviewerId': reviewer, 'repetitions': [{'repetition': 1, 'score': score, 'instances': list(instances)}]}]}


def short(before):
    return {'kind': 'short-evidence-path', 'before': before}


class FormatPenaltyTests(unittest.TestCase):
    def test_repairable_errors_count_in_scorer_units(self):
        changes = {'details': [short('`a.mjs:3`'), short('`a.mjs:3,7-9`'), {'kind': 'markdown-preamble', 'before': ['# T\n']}]}
        self.assertEqual(repairable_count(changes), 4)
        self.assertEqual(repairable_count({'details': []}), 0)
        self.assertEqual(repairable_count({'details': [{'kind': 'requirement-line'}, {'kind': 'requirement-line'}]}), 2)
        spill = {'kind': 'spill-locator', 'before': '`a.mjs:90,95-99`', 'converted': [{'before': 'a.mjs:90'}, {'before': '95-99'}]}
        self.assertEqual(repairable_count({'details': [spill]}), 2)
        with self.assertRaises(ValueError):
            repairable_count({'details': [{'kind': 'other'}]})

    def test_penalty_scales_with_the_baseline_and_is_capped(self):
        self.assertEqual(penalty(0, 50, 0.08), (0, 0))
        p, f = penalty(4, 50, 0.08)
        self.assertAlmostEqual(p, 0.08)
        self.assertAlmostEqual(f, 0.05)
        self.assertAlmostEqual(penalty(30, 50, 0.08)[1], 0.1)
        self.assertAlmostEqual(final_score(0.8, 0.05), 0.76)
        self.assertEqual(final_score(-0.2, 0.05), 0)

    def test_baseline_is_pooled_with_a_floor_of_two_per_report(self):
        self.assertAlmostEqual(pooled_baseline([(7, 41), (0, 44), (1, 54), (0, 37), (10, 48)])['pBase'], 18 / 224)
        # Fewer than 2 errors per report: the floor 2 / mean T applies.
        self.assertAlmostEqual(pooled_baseline([(0, 40), (1, 60)])['pBase'], 2 / 50)

    def test_registered_baseline_of_code_standards_v51(self):
        self.assertAlmostEqual(registered_baseline(*CS51), 18 / 224)

    def test_unregistered_or_inconsistent_baselines_are_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'registry.json'
            registry = json.loads(REGISTRY.read_text())
            path.write_text(json.dumps(registry))
            with self.assertRaisesRegex(ValueError, 'not registered'):
                registered_baseline(CS51[0], '0' * 64, path)
            registry[CS51[0]][CS51[1]]['pBase'] = 0.5
            path.write_text(json.dumps(registry))
            with self.assertRaisesRegex(ValueError, 'does not match'):
                registered_baseline(*CS51, path)

    def test_repetitions_count_every_format_error(self):
        # Repairable errors from the repair record, unrepairable ones left in the scored report, ranges cut at the end of a file.
        output = upstream(CS51[0], instance('i1', unrepairable=1, overrun=2))
        [row] = score_repetitions(output, {'i1': {'details': [short('`a.mjs:1,2,3,4`')] * 2}})
        self.assertEqual((row['r'], row['rRepairable'], row['rUnrepairable'], row['rOverrun'], row['T']), (11, 8, 1, 2, 100))
        self.assertAlmostEqual(row['f'], 0.1 * min(1, 0.11 / (2 * 18 / 224)))
        self.assertAlmostEqual(row['score'], 0.8 * (1 - row['f']))
        self.assertEqual(score_repetitions(upstream(CS51[0], instance('i1')), {'i1': None})[0]['score'], 0.8)

    def test_every_instance_declares_its_repair(self):
        with self.assertRaisesRegex(ValueError, 'declares no repair'):
            score_repetitions(upstream(CS51[0], instance('i1')), {})
        # A copy scored through a format correction cannot be declared unrepaired.
        corrected = instance('i1', formatCorrection={'kind': 'probe'})
        with self.assertRaisesRegex(ValueError, 'format correction'):
            score_repetitions(upstream(CS51[0], corrected), {'i1': None})
        # Output of an earlier scorer without the format error counts.
        old = {key: value for key, value in instance('i1').items() if key != 'overrunLocators'}
        with self.assertRaisesRegex(ValueError, 'current scoring upgrade'):
            score_repetitions(upstream(CS51[0], old), {'i1': None})

    def test_spec_readiness_pair_sums_r_and_t_over_both_scenarios(self):
        output = upstream(SR41[0], instance('rm', SR41, locators=40, unrepairable=1), instance('ap', SR41, locators=60, overrun=1))
        [row] = score_repetitions(output, {'rm': None, 'ap': {'details': [short('`a.md:3`')]}})
        self.assertEqual((row['r'], row['T'], row['instances']), (3, 100, ['rm', 'ap']))
        self.assertAlmostEqual(row['f'], 0.1 * 0.03 / (2 * registered_baseline(*SR41)))

    def test_instances_of_one_repetition_need_one_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'registry.json'
            registry = json.loads(REGISTRY.read_text())
            other = json.loads(json.dumps(registry[CS51[0]][CS51[1]]))
            other['runs'][0].update(r=other['runs'][0]['r'] + 5, rRepairable=other['runs'][0]['rRepairable'] + 5)
            other['pBase'] = pooled_baseline([(run['r'], run['T']) for run in other['runs']])['pBase']
            registry[CS51[0]]['f' * 64] = other
            path.write_text(json.dumps(registry))
            output = upstream(CS51[0], instance('a'), instance('b', (CS51[0], 'f' * 64)))
            with self.assertRaisesRegex(ValueError, 'different format baselines'):
                score_repetitions(output, {'a': None, 'b': None}, path)

    def test_command_line_rejects_an_undeclared_instance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'upstream.json'
            path.write_text(json.dumps(upstream(CS51[0], instance('i1'))))
            command = [sys.executable, '-m', 'tools.reviewer.format_penalty', '--upstream', str(path)]
            missing = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn('declares no repair', missing.stderr)
            declared = subprocess.run(command + ['--no-repair', 'i1'], cwd=ROOT, capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(declared.stdout)[0]['score'], 0.8)

    def test_registered_baselines_are_bound_to_their_archive(self):
        registry = json.loads(REGISTRY.read_text())
        for reviewer, entries in registry.items():
            for key, entry in entries.items():
                with self.subTest(reviewer):
                    self.assertGreater(verify_archive(entry), 0)
                    runs = [(run['r'], run['T']) for run in entry['runs']]
                    self.assertEqual(entry['pBaseBootstrap90'], [round(value, 7) for value in bootstrap_interval(runs)])
                    low, high = entry['pBaseBootstrap90']
                    self.assertLessEqual(low, registered_baseline(reviewer, key))
                    self.assertLessEqual(registered_baseline(reviewer, key), high)
        # A changed archived file or a repair record of another report is an error.
        entry = registered_entry(*CS51)
        tampered = json.loads(json.dumps(entry))
        tampered['runs'][0]['reports'][0]['reportSha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'differs from its registration'):
            verify_archive(tampered)
        tampered = json.loads(json.dumps(entry))
        tampered['runs'][0]['rRepairable'] += 1
        with self.assertRaisesRegex(ValueError, 'repairable count'):
            verify_archive(tampered)
        self.assertTrue((ARCHIVE / entry['archive'].removeprefix('format-baseline/')).is_dir())


if __name__ == '__main__':
    unittest.main()
