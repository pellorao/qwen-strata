"""ARW tuning dimensions: frozen plan consistency and the per-instance effect check."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.tuning.arw_dimension import extract_agent_config, flag_values, load_plan, sha, time_limited_note, verify_effect

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / 'benchmarks/resource-calibration-v1/iq3_xxs-arw-dims5-7/plan.json'
STARTED = ('[strata] 2026-10-11 18:47:55 engine started: C:\\x\\strata.exe --serve --expert-profile C:\\x\\p.bin '
           '--spec {spec} --mtp C:\\x\\rt --suffix-draft --max-context 156584\n')


class PlanTests(unittest.TestCase):
    def test_frozen_plan_schedules(self):
        plan, dimensions, conditions = load_plan(PLAN)
        spec = dimensions['spec']['schedule']
        # Latin square rows: each round holds every value once, no value repeats a column
        self.assertEqual([sorted(spec[i:i + 4]) for i in (0, 4, 8)], [sorted(dimensions['spec']['conditions'])] * 3)
        self.assertTrue(all(len({spec[c], spec[c + 4], spec[c + 8]}) == 3 for c in range(4)))
        self.assertEqual(dimensions['cpu-share']['schedule'][:2], ['cpu-share-auto', 'cpu-share-unset'])
        self.assertEqual(dimensions['expert-profile']['schedule'][:2], ['profile-learned', 'profile-shipped'])
        self.assertTrue(dimensions['expert-profile']['blocked'])
        self.assertEqual(len(conditions), 8)

    def test_plan_rejects_unequal_repetitions(self):
        with tempfile.TemporaryDirectory() as temp:
            plan = json.loads(PLAN.read_text())
            plan['dimensions'][1]['schedule'].append('cpu-share-auto')
            (Path(temp) / 'conditions').symlink_to(PLAN.parent / 'conditions')
            (Path(temp) / 'plan.json').write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError, 'same number'):
                load_plan(Path(temp) / 'plan.json')


class EffectTests(unittest.TestCase):
    spec = {'id': 'spec-3', 'model': 'IQ3_XXS', 'model_overrides': {'spec': 3}}
    configuration = {'args': ['--spec', '3', '--expert-profile', 'C:\\x\\p.bin']}

    def test_flags_and_log_lines_must_match(self):
        log = STARTED.format(spec=3) + 'strata verify: window up to 5 tokens, 70.1 MiB\n'
        result = verify_effect(log, [], self.spec, self.configuration, {'log_present': ['window up to 5 tokens']})
        self.assertTrue(result['ok'], result['problems'])
        self.assertEqual(result['facts']['verify_window'], '5')
        wrong = verify_effect(STARTED.format(spec=4), [], self.spec, self.configuration,
                              {'log_present': ['window up to 5 tokens']})
        self.assertEqual(len(wrong['problems']), 2)
        twice = verify_effect(STARTED.format(spec=3) * 2, [], self.spec, self.configuration, {})
        self.assertIn('one engine start', twice['problems'][0])

    def test_environment_is_read_from_the_running_engine(self):
        unset = {'id': 'cpu-share-unset', 'model': 'IQ3_XXS', 'model_environment': {'STRATA_PREFILL_CPU_SHARE': None}}
        log = STARTED.format(spec=4) + 'prefill: the CPU share is ON by default for prompt chunks below 1024 tokens\n'
        checks = {'log_present': ['the CPU share is ON by default|the CPU prefill share is not armed by default']}
        row = lambda value: [{'pid': 1, 'environment': {'STRATA_PREFILL_CPU_SHARE': value}}]
        self.assertTrue(verify_effect(log, row(None), unset, self.configuration, checks)['ok'])
        self.assertFalse(verify_effect(log, row('auto'), unset, self.configuration, checks)['ok'])
        hidden = [{'pid': 1, 'environment': None, 'unreadable': 'access denied: the engine runs elevated'}]
        self.assertTrue(verify_effect(log, hidden, unset, self.configuration, checks)['ok'])
        self.assertFalse(verify_effect(STARTED.format(spec=4), hidden, unset, self.configuration, checks)['ok'])
        self.assertTrue(verify_effect(log, [], unset, self.configuration, checks)['ok'])  # engine already stopped
        auto = {'id': 'cpu-share-auto', 'model': 'IQ3_XXS', 'model_environment': {'STRATA_PREFILL_CPU_SHARE': 'auto'}}
        self.assertFalse(verify_effect(log, row('auto'), auto, self.configuration,
                                       {'log_absent': ['the CPU share is ON by default']})['ok'])

    def test_condition_sampling_must_be_installed(self):
        condition = {'id': 'sampling-t06', 'model': 'IQ3_XXS', 'request_defaults': {'temperature': 0.6}}
        log = STARTED.format(spec=4)
        trace = '[native-sampling-trace] temperature=0.6 top_p=0.95 top_k=20\n'  # the service log, not the engine's
        checks = {'log_present': [r'\[native-sampling-trace\][^\n]*temperature=0\.6\b']}
        installed = dict(self.configuration, request_defaults={'temperature': 0.6, 'top_k': 20})
        self.assertTrue(verify_effect(log, [], condition, installed, checks, trace)['ok'])
        self.assertFalse(verify_effect(log, [], condition, installed, checks)['ok'])
        stale = dict(self.configuration, request_defaults={'temperature': 0.0})
        self.assertIn('request default temperature',
                      verify_effect(log, [], condition, stale, checks, trace)['problems'][0])

    def test_selected_tier_must_reach_the_engine(self):
        plain = {'id': 'window-206584', 'model': 'IQ3_XXS'}
        self.assertTrue(verify_effect(STARTED.format(spec=4), [], plain, self.configuration,
                                      {'context_window': 156584})['ok'])
        self.assertIn('--max-context', verify_effect(STARTED.format(spec=4), [], plain, self.configuration,
                                                     {'context_window': 206584})['problems'][0])

    def test_flag_values_and_manual_config(self):
        self.assertEqual(flag_values('x --spec 3 --suffix-draft --max-context 9'),
                         {'--spec': '3', '--suffix-draft': True, '--max-context': '9'})
        manual = '如果使用 Codex\n\n```json\n{"a": 1}\n```\n\n如果使用 Claude Code\n```json\n{}\n```\n'
        self.assertEqual(json.loads(extract_agent_config(manual)), {'a': 1})


    def test_time_limited_note_renders_the_batch_limit(self):
        (ROOT / '.tmp').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / '.tmp') as directory:
            folder = Path(directory)
            raw = b'Stop after {{time_limit_minutes}} minutes.\n'
            (folder / 'template.txt').write_bytes(raw)
            template = {'path': str((folder / 'template.txt').relative_to(ROOT)), 'sha256': sha(raw)}
            note, limit = time_limited_note({'measurement_note_template': template}, folder, 900)
            self.assertEqual((ROOT / note['path']).read_text(), 'Stop after 15 minutes.\n')
            self.assertEqual(note['sha256'], sha(b'Stop after 15 minutes.\n'))
            self.assertEqual(limit, {'measurement_note_template': template, 'review_time_limit_seconds': 900})
            time_limited_note({'measurement_note_template': template}, folder, 750)
            self.assertEqual((ROOT / note['path']).read_text(), 'Stop after 12.5 minutes.\n')
            for bad in (None, 0, 90.5):
                with self.assertRaises(ValueError):
                    time_limited_note({'measurement_note_template': template}, folder, bad)
            with self.assertRaises(ValueError):
                time_limited_note({'measurement_note_template': {**template, 'sha256': '0' * 64}}, folder, 900)

if __name__ == '__main__':unittest.main()
