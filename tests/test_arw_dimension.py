"""ARW tuning dimensions: frozen plan consistency and the per-instance effect check."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.tuning.arw_dimension import (MEASUREMENT_NOTE, extract_agent_config, flag_values, load_plan, plain_note,
                                        required_scenario_note, selection, sha, time_limited_note, verify_effect)
from tools.tuning import arw_dimension

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

    def test_time_limited_note_outside_the_project_keeps_an_absolute_path(self):
        (ROOT / '.tmp').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / '.tmp') as directory, tempfile.TemporaryDirectory(dir='/var/tmp', prefix='qwen-note-') as outside:
            raw = b'Stop after {{time_limit_minutes}} minutes.\n'
            (Path(directory) / 'template.txt').write_bytes(raw)
            template = {'path': str((Path(directory) / 'template.txt').relative_to(ROOT)), 'sha256': sha(raw)}
            note, _ = time_limited_note({'measurement_note_template': template}, Path(outside), 600)
            self.assertTrue(Path(note['path']).is_absolute())
            self.assertEqual((ROOT / note['path']).read_text(), 'Stop after 10 minutes.\n')

    def test_plain_note_is_the_common_note_or_the_named_scenario_note(self):
        common = (ROOT / MEASUREMENT_NOTE).read_bytes()
        self.assertEqual(plain_note({'measurement_note_sha256': sha(common)}), {'path': MEASUREMENT_NOTE, 'sha256': sha(common)})
        path = 'benchmarks/reviewer-suite-v1/measurement-note-commit-audit.txt'
        raw = (ROOT / path).read_bytes()
        # The Commit Audit note is the common note plus the repeated-requirement sentence (user 2026-10-17).
        self.assertTrue(raw.startswith(common) and b'scored once' in raw[len(common):])
        # Both notes limit what counts as a repeat (third audit S1, user 2026-10-17).
        limit = b'Treat two rows as repeated only when they state the same complete requirement about the same operation.\n'
        template = 'benchmarks/reviewer-suite-v1/measurement-note-time-limit-commit-audit.txt'
        self.assertTrue(raw.endswith(limit) and (ROOT / template).read_bytes().endswith(limit))
        self.assertEqual(plain_note({'measurement_note_path': path, 'measurement_note_sha256': sha(raw)})['path'], path)
        with self.assertRaises(ValueError):
            plain_note({'measurement_note_path': path, 'measurement_note_sha256': sha(common)})

    def test_commit_audit_v2_requires_its_own_note(self):
        manifest = 'benchmarks/reviewer-suite-v1/source-snapshots/current/manifest-commit-audit-v2.json'
        plain = 'benchmarks/reviewer-suite-v1/measurement-note-commit-audit.txt'
        template = 'benchmarks/reviewer-suite-v1/measurement-note-time-limit-commit-audit.txt'
        required_scenario_note({'arw_source_manifest': manifest, 'measurement_note_path': plain}, 'commit-audit-reviewer')
        required_scenario_note({'arw_source_manifest': manifest, 'measurement_note_template': {'path': template}}, 'commit-audit-reviewer')
        # v3 keeps the same note (revision 24 change note).
        v3 = manifest.replace('-v2.json', '-v3.json')
        self.assertTrue((ROOT / v3).is_file())
        required_scenario_note({'arw_source_manifest': v3, 'measurement_note_path': plain}, 'commit-audit-reviewer')
        with self.assertRaisesRegex(ValueError, 'needs the measurement note'):
            required_scenario_note({'arw_source_manifest': v3}, 'commit-audit-reviewer')
        # v3.1 (multi-model benchmark v2 draft) keeps the same note too.
        v31 = 'benchmarks/multi-model-v2/scenarios/manifest-commit-audit-v3.1.json'
        self.assertTrue((ROOT / v31).is_file())
        required_scenario_note({'arw_source_manifest': v31, 'measurement_note_path': plain}, 'commit-audit-reviewer')
        with self.assertRaisesRegex(ValueError, 'needs the measurement note'):
            required_scenario_note({'arw_source_manifest': v31}, 'commit-audit-reviewer')
        # Other reviewers or manifests keep the common note.
        required_scenario_note({'arw_source_manifest': manifest}, 'code-spec-reviewer')
        required_scenario_note({'arw_source_manifest': manifest.replace('-commit-audit-v2', '')}, 'commit-audit-reviewer')
        for fixed in ({}, {'measurement_note_path': MEASUREMENT_NOTE}, {'measurement_note_path': template},
                      {'measurement_note_template': {'path': 'benchmarks/reviewer-suite-v1/measurement-note-time-limit.txt'}},
                      {'measurement_note_template': {'path': plain}}):
            with self.subTest(fixed=fixed), self.assertRaisesRegex(ValueError, 'needs the measurement note'):
                required_scenario_note({'arw_source_manifest': manifest, **fixed}, 'commit-audit-reviewer')

class SelectionTests(unittest.TestCase):
    def test_strata_selection_loads_the_project_compaction_prompt(self):
        # Hard constraint 3: every Strata run gets the project compaction prompt (it was False from d6b09c9 on).
        with tempfile.TemporaryDirectory() as tmp:
            codex = Path(tmp) / 'codex'
            codex.write_bytes(b'cli')
            plan = {'model': 'IQ3_XXS', 'reviewer': 'code-spec-reviewer',
                    'fixed_conditions': {'native_cli_sha256': sha(b'cli'), 'effort': 'medium', 'codex': '0.0',
                                         'arw_source_manifest': 'manifest.json'}}
            with mock.patch.object(arw_dimension, 'codex_binary', return_value=codex), \
                    mock.patch.object(arw_dimension, 'plain_note', return_value={'path': 'note'}):
                chosen = selection(plan, {})
        self.assertTrue(chosen['startup_instructions'])
        self.assertTrue(chosen['project_compaction_instructions'])

    def test_host_catalog_is_rendered_for_the_host_and_condition(self):
        condition = {'model_overrides': {'spec': '4'}}
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(arw_dimension, 'source_bytes', return_value=b'{}\n') as rendered:
            path, digest = arw_dimension.host_catalog('rtx3080ti', Path(tmp), condition)
            self.assertEqual((path.name, path.read_bytes(), digest), ('host-model-catalog.json', b'{}\n', sha(b'{}\n')))
        rendered.assert_called_once_with('config/model-catalog.json', 'rtx3080ti', condition=condition)

    def test_run_passes_the_host_catalog_to_arw_measure(self):
        plan, dimensions, _ = load_plan(PLAN)
        name = dimensions['spec']['schedule'][0]
        host = mock.MagicMock()
        host.log_bytes_since.return_value = b''
        calls = []
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(arw_dimension, 'source_bytes', return_value=b'{"models": []}\n') as rendered, \
                mock.patch.object(arw_dimension, 'prepare'), mock.patch.object(arw_dimension, 'preflight'), \
                mock.patch.object(arw_dimension, 'verify_effect', return_value={'ok': True, 'problems': []}), \
                mock.patch('tools.ops.deploy.deploy', return_value={'model_configuration_sha256': 'x'}), \
                mock.patch('tools.ops.measurement_host.MeasurementHost', return_value=host), \
                mock.patch.object(arw_dimension.subprocess, 'run',
                                  side_effect=lambda cmd, **kw: calls.append(cmd) or mock.Mock(returncode=0)):
            out = Path(tmp) / 'out'
            (out / f'01-{name}').mkdir(parents=True)
            records = arw_dimension.run(PLAN, 'spec', out, limit=1)
            catalog = calls[0][calls[0].index('--catalog') + 1]
            self.assertEqual(Path(catalog), out / f'01-{name}' / 'host-model-catalog.json')
            self.assertEqual(Path(catalog).read_bytes(), b'{"models": []}\n')
        self.assertEqual(rendered.call_args.args[:2], ('config/model-catalog.json', plan['host']))
        self.assertEqual(records[0]['catalog_sha256'], sha(b'{"models": []}\n'))


if __name__ == '__main__':unittest.main()
