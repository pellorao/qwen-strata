import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.reviewer import prepare_continuation_score as module


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.batch = base / 'batch'
        self.folder = self.batch / 'premature-continuations/one'
        (self.folder / 'initial-preservation').mkdir(parents=True)
        report = base / 'report.md'
        report.write_text('final')
        workdir = base / 'work'
        workdir.mkdir()
        (workdir / 'a.txt').write_text('artifact')
        prepared = base / 'prepared.json'
        prepared.write_text('{}')
        dispatch = base / 'dispatch.json'
        dispatch.write_text(json.dumps({'generations': [{'workdir': str(workdir)}], 'repositoryRoot': 'r', 'identity': 'i', 'preparedPath': str(prepared)}))
        (self.batch / 'jobs.json').write_text(json.dumps([{'folder': str(self.folder), 'dispatch': str(dispatch), 'instanceId': 'x-3', 'repetition': 2}]))
        self.result = {'ownership_returned': True, 'final_report_path': str(report), 'final_report_sha256': hashlib.sha256(b'final').hexdigest(),
                       'initial_report_sha256': 'a', 'terminal_kind': 'ok',
                       'generation': {'exit_code': 0, 'result': {'files': [{'sourcePath': 'a.txt'}]}}}
        (self.folder / 'initial-preservation/results.json').write_text(json.dumps([{'selection': {'effort': 'high'}}]))
        (self.folder / 'run-finished.json').write_text('{}')

    def write_result(self):
        (self.folder / 'result.json').write_text(json.dumps(self.result))

    def test_prepares_scoring_inputs_and_runs_endpoint(self):
        self.write_result()
        def fake_run(command, check):
            (self.folder / 'main-scoring/pending.json').write_text(json.dumps({'status': 'pending', 'candidates': [1, 2], 'bindingRequests': []}))
        with mock.patch.object(module.subprocess, 'run', side_effect=fake_run) as run:
            summary = module.prepare(self.batch, 'one')
        self.assertEqual(summary, {'status': 'pending', 'candidates': 2, 'binding_requests': 0})
        self.assertEqual(run.call_args.args[0][2], 'score-completed')
        binding = json.loads((self.folder / 'main-scoring/binding.json').read_text())
        self.assertEqual(binding['original_prepared_repeat'], 3)
        self.assertEqual(binding['effort'], 'high')

    def test_unfinished_instance_is_an_error_not_an_assert(self):
        self.result['ownership_returned'] = False
        self.write_result()
        with self.assertRaisesRegex(ValueError, 'did not finish'):
            module.prepare(self.batch, 'one')

    def test_report_sha_mismatch_is_an_error(self):
        self.result['final_report_sha256'] = '0' * 64
        self.write_result()
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            module.prepare(self.batch, 'one')

    def test_unknown_job_is_an_error(self):
        self.write_result()
        with self.assertRaisesRegex(ValueError, 'No job named'):
            module.prepare(self.batch, 'other')


if __name__ == '__main__':
    unittest.main()
