import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.reviewer.arw_recovery import archive_recovery, verify_stopped_runtime
from tools.reviewer.arw_measure import driver_context, execute_review, load_resume_cleanup

TIER = {'context_window': 206584, 'auto_compact_token_limit': 150000}


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)
        self.source = self.out / 'frozen-source'
        self.new = self.out / 'arw-installation-recovered'
        self.records = [{'instanceId': 'closed', 'finished_at': 10,
                         'runtime_result': {'state': 'idle', 'completion': {'status': 'ready'}}}]
        values = {'runtime.json': {'repositoryRoot': str(self.source),
                                  'installationDirectory': str(self.out / 'old-native'),
                                  'runtimeDirectory': str(self.out / 'old-native/state')},
                  'arw-cleanup.json': {'cleanup': {'status': 'busy'}},
                  'results.json': self.records}
        for name, value in values.items():
            (self.out / name).write_text(json.dumps(value))
        self.identity = patch('tools.reviewer.arw_recovery.subprocess.check_output', return_value=json.dumps(
            {'state': 'ended', 'identity': {'pid': 123, 'createdAt': '456'}}))
        self.identity.start()
        self.addCleanup(self.identity.stop)

    def verify(self):
        return verify_stopped_runtime(self.out, self.source, self.new, self.records, ['next'])

    def test_preserves_uncertain_state_and_closed_evidence(self):
        before = {p.name: p.read_bytes() for p in self.out.iterdir()}
        proof = self.verify()
        archive = archive_recovery(self.out, proof)
        for name, raw in before.items():
            self.assertEqual((archive / name).read_bytes(), raw)
            self.assertEqual((self.out / name).read_bytes(), raw)
        self.assertEqual(proof['pending_instances'], ['next'])
        self.assertFalse(self.new.exists())

    def test_rejects_unrecorded_instance_artifacts(self):
        (self.out / 'next').mkdir()
        with self.assertRaisesRegex(ValueError, 'unrecorded'):
            self.verify()

    def test_rejects_retained_ownership(self):
        (self.out / 'controller-key.private.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'ownership'):
            self.verify()

    def test_rejects_live_or_unknown_native_identity(self):
        for state in ('alive', 'unknown', 'absent'):
            with self.subTest(state=state), patch('tools.reviewer.arw_recovery.subprocess.check_output',
                    return_value=json.dumps({'state': state, 'identity': {'pid': 123}})):
                with self.assertRaisesRegex(ValueError, 'confirm native exit'):
                    self.verify()

    def test_rejects_nonterminal_submitted_task(self):
        self.records[0]['runtime_result']['state'] = 'working'
        with self.assertRaisesRegex(ValueError, 'terminal observation'):
            self.verify()

    def test_rejects_existing_or_outside_recovery_installation(self):
        self.new.mkdir()
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.verify()
        self.new = self.out.parent / 'arw-installation-other'
        with self.assertRaisesRegex(ValueError, 'isolated directory'):
            self.verify()

    def test_missing_cleanup_requires_verified_native_recovery(self):
        missing=self.out/'missing-cleanup.json'
        with self.assertRaisesRegex(ValueError,'cleanup record is missing'):
            load_resume_cleanup(missing)
        observation=load_resume_cleanup(missing,recovering_native=True)
        self.assertEqual(observation['cleanup']['status'],'unknown')
        self.assertFalse(missing.exists())
        with patch('tools.reviewer.arw_recovery.subprocess.check_output',return_value=json.dumps(
                {'state':'alive','identity':{'pid':123,'createdAt':'456'}})):
            with self.assertRaisesRegex(ValueError,'confirm native exit'):
                self.verify()

    def test_corrupt_cleanup_is_not_treated_as_missing(self):
        broken=self.out/'broken-cleanup.json'
        broken.write_text('{')
        with self.assertRaises(json.JSONDecodeError):
            load_resume_cleanup(broken,recovering_native=True)

    def failed_dispatch(self, selection, metadata=None, error='submission failed'):
        shim = self.out / 'bin/arw'
        shim.parent.mkdir()
        shim.write_text('#!/bin/sh\nexit 0\n')
        project = self.out / 'scenario'
        roles = project / 'docs/agents/roles'
        roles.mkdir(parents=True)
        (roles / 'code-spec-reviewer.md').write_text('Role instructions')
        (roles.parent / 'reviewer.md').write_text('Common instructions')
        prepared = self.out / 'prepared.json'
        prepared.write_text(json.dumps({'contracts': [{'instances': [
            {'instanceId': 'next', 'requestPath': str(self.out / 'request.json')}]}]}))
        preparation = {'generations': [], 'preparedPath': str(prepared),
                       'identity': {'sessionId': 'isolated-session'}}
        handoff = {'scenarioRoot': str(project), 'instanceId': 'next',
                   'resultPath': str(project / '.tmp/report.md'),
                   'reviewerId': 'code-spec-reviewer', 'agentType': 'reviewer', 'prompt': 'Original handoff'}
        class FailedMachine:
            def call(self, *_args):
                raise RuntimeError('Native submission failed')
        with patch.dict('os.environ', {'QWEN_ARW_RUNTIME_FILE': str(self.out / 'runtime.json'),
                                      'QWEN_ARW_MODEL_BASE': 'http://localhost/v1'}):
            with self.assertRaisesRegex(RuntimeError, error):
                execute_review(FailedMachine(), self.source, preparation, handoff, self.out / 'next',
                               selection, self.out / 'catalog.json', metadata)

    def test_startup_snapshot_survives_failed_dispatch(self):
        metadata = {'startup_instructions': {'sha256': 'snapshot', 'text': 'Service instructions'},
                    'runtime_installation': str(self.new)}
        self.failed_dispatch({'model': 'Q2_0', 'effort': 'medium', **TIER}, metadata)
        record = json.loads((self.out / 'next/result.json').read_text())
        self.assertEqual(record['startup_instructions'], metadata['startup_instructions'])
        self.assertEqual(record['runtime_installation'], str(self.new))
        self.assertNotIn('accepted', record)

    def test_measurement_note_is_appended_and_bound(self):
        note = {'path': 'benchmarks/reviewer-suite-v1/measurement-note.txt',
                'sha256': '0bf509f03b7c985504340f95c9e42f363b6946ce3f7ebe3af2c4072bb5d23beb'}
        self.failed_dispatch({'model': 'IQ3_XXS', 'effort': 'high', 'measurement_note': note, **TIER})
        binding = json.loads((self.out / 'next/binding.json').read_text())
        self.assertTrue(binding['handoff'].startswith('Original handoff\n\nMeasurement note: '))
        self.assertTrue(binding['handoff'].endswith('outside the scenario root).'))
        self.assertEqual(json.loads((self.out / 'next/result.json').read_text())['measurement_note'], note)

    def test_changed_measurement_note_is_refused(self):
        note = {'path': 'benchmarks/reviewer-suite-v1/measurement-note.txt', 'sha256': '0' * 64}
        self.failed_dispatch({'model': 'IQ3_XXS', 'effort': 'high', 'measurement_note': note, **TIER},
                             error='Measurement note differs')
        self.assertFalse((self.out / 'next/binding.json').exists())

    def test_driver_owned_selection_without_window_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'context_window and auto_compact_token_limit'):
            driver_context({'model': 'IQ3_XXS', 'effort': 'high', 'context_window': 206584})
        self.assertEqual(driver_context(TIER), (206584, 150000))


if __name__ == '__main__':
    unittest.main()
