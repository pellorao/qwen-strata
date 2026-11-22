"""Frozen v1 ARW helpers (notes, selection, host catalog), kept for the v1 scoring tools until they are dropped."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.reviewer import frozen_arw
from tools.reviewer.frozen_arw import (MEASUREMENT_NOTE, extract_agent_config, plain_note, required_scenario_note, selection,
                                       sha, time_limited_note)

ROOT = Path(__file__).resolve().parents[1]


class FrozenNoteTests(unittest.TestCase):
    def test_manual_config_is_extracted(self):
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
            with mock.patch.object(frozen_arw, 'codex_binary', return_value=codex), \
                    mock.patch.object(frozen_arw, 'plain_note', return_value={'path': 'note'}):
                chosen = selection(plan, {})
        self.assertTrue(chosen['startup_instructions'])
        self.assertTrue(chosen['project_compaction_instructions'])

    def test_host_catalog_is_rendered_for_the_host_and_condition(self):
        condition = {'model_overrides': {'spec': '4'}}
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(frozen_arw, 'source_bytes', return_value=b'{}\n') as rendered:
            path, digest = frozen_arw.host_catalog('rtx3080ti', Path(tmp), condition)
            self.assertEqual((path.name, path.read_bytes(), digest), ('host-model-catalog.json', b'{}\n', sha(b'{}\n')))
        rendered.assert_called_once_with('config/model-catalog.json', 'rtx3080ti', condition=condition)


if __name__ == '__main__':unittest.main()
