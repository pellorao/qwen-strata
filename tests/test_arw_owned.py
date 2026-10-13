import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.reviewer.arw_measure import ARW_PAUSE_PREFIX, capture_segment, cold_start_arw_batch, followup_when_idle, local_review_catalog, spec_repetition_order, observe_review, run


class ArwOwnedTests(unittest.TestCase):
    def test_pause_message_stops_observation_for_the_user(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            record = {'accepted': {'runId': 'run', 'messageId': 'm'}, 'role': 'commit-audit-reviewer', 'instanceId': 'i', 'started_at': 10,
                      'selection': {'model_owner': 'arw'}}
            pause = {'type': 'message', 'sequence': 4, 'text': ARW_PAUSE_PREFIX + '10 normally completed turns ...'}
            class Machine:
                def call(self, operation, value, **kwargs):
                    assert operation == 'list_agents', operation  # no deadline reminder or continuation from the driver
                    return {'runId': 'run', 'state': 'idle', 'taskState': 'working', 'notifications': [pause],
                            'measurement': {}}
            result = observe_review(Machine(), record, folder)
            self.assertEqual(result['arw_pause']['notification'], pause)
            self.assertFalse(result['complete'])

    def test_followup_waits_for_the_original_task_instead_of_abandoning_on_busy(self):
        busy = RuntimeError(json.dumps({'code': 'reviewer-busy', 'message': 'The original Reviewer is still executing.'}))

        class Machine:
            def __init__(self, states, followups):
                self.states, self.followups, self.calls = states, followups, []

            def call(self, operation, value, **kwargs):
                self.calls.append(operation)
                if operation == 'list_agents':
                    return self.states.pop(0)
                outcome = self.followups.pop(0)
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome

        machine = Machine([{'state': 'running', 'completion': None}, {'state': 'idle', 'completion': {'status': 'ready'}}],
                          [busy, {'runId': 'r', 'accepted': True}])
        self.assertEqual(followup_when_idle(machine, {'runId': 'r'}, poll=0), {'runId': 'r', 'accepted': True})
        self.assertEqual(machine.calls, ['followup_task', 'list_agents', 'list_agents', 'followup_task'])
        paused = Machine([{'state': 'idle', 'completion': None,
                           'notifications': [{'type': 'message', 'text': ARW_PAUSE_PREFIX + '10 early exits.'}]}], [busy])
        with self.assertRaisesRegex(RuntimeError, 'user decides'):
            followup_when_idle(paused, {'runId': 'r'}, poll=0)
        other = Machine([], [RuntimeError(json.dumps({'code': 'recovery-not-found'}))])
        with self.assertRaisesRegex(RuntimeError, 'recovery-not-found'):
            followup_when_idle(other, {'runId': 'r'}, poll=0)

    def test_catalog_enables_arw_strata_provider_only_when_arw_owns_the_model(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / 'catalog.json'
            source.write_text(json.dumps({'models': [{'slug': 'qwen3.8-flash-next-iq3_xxs'}]}))
            plain = json.loads(local_review_catalog(source, folder / 'a.json', 'IQ3_XXS').read_text())
            self.assertNotIn('providers', plain)
            owned = json.loads(local_review_catalog(source, folder / 'b.json', 'IQ3_XXS', None, '/install').read_text())
            self.assertEqual(owned['providers'], {'qwen_strata': {'driver': 'strata', 'installationDirectory': '/install'}})
            tier = json.loads(local_review_catalog(source, folder / 'c.json', 'IQ3_XXS', 65536, '/install').read_text())
            # The window is a provider choice that ARW resolves against the installation's published tiers.
            self.assertEqual(tier['providers']['qwen_strata']['contextWindow'], 65536)
            self.assertNotIn('context_window', tier['models'][0])

    def test_arw_reads_the_bound_provider_and_installation_tier_through_its_own_catalog(self):
        import subprocess
        from tools.reviewer.freeze_arw_source import materialize
        root = Path(__file__).resolve().parents[1]
        snapshots = root / 'benchmarks/reviewer-suite-v1/source-snapshots/current'
        manifest = json.loads((snapshots / 'manifest.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            materialize(manifest, snapshots / manifest['snapshot']['file'], folder / 'arw')
            (folder / 'strata/config').mkdir(parents=True)
            (folder / 'strata/config/deployment.json').write_text(json.dumps({'context_tiers': {'IQ3_XXS': [
                {'context_window': 156584, 'auto_compact_token_limit': 100000},
                {'context_window': 65536, 'auto_compact_token_limit': 40000}]}}))
            source = folder / 'catalog.json'
            source.write_text(json.dumps({'models': [{'slug': 'qwen3.8-flash-next-iq3_xxs', 'context_window': 1}]}))
            catalog = local_review_catalog(source, folder / 'bound.json', 'IQ3_XXS', 65536, folder / 'strata')
            info = {'repositoryRoot': str(folder / 'arw'), 'installationDirectory': str(folder / 'install'), 'catalog': str(catalog)}
            script = ("import {createIsolatedNativeSessions} from %s;"
                      "const {modelCatalog}=await createIsolatedNativeSessions(%s);"
                      "const path=await modelCatalog.prepare();"
                      "console.log(JSON.stringify({providers:await modelCatalog.getProviders(),"
                      "models:JSON.parse((await import('node:fs')).readFileSync(path,'utf8')).models}));"
                      % (json.dumps((root / 'tools/reviewer/arw_native_setup.mjs').as_uri()), json.dumps(info)))
            (folder / 'install').mkdir(mode=0o700)
            value = json.loads(subprocess.run(['node', '--input-type=module', '-e', script], capture_output=True, text=True, check=True).stdout)
            self.assertEqual(value['providers'], {'qwen_strata': {'driver': 'strata', 'installationDirectory': str(folder / 'strata'),
                                                                  'contextWindow': 65536, 'maxInstances': 1}})
            self.assertEqual(value['models'][0]['context_window'], 65536)
            # The isolated home turns off the per-home plugin marketplace clone.
            self.assertEqual((folder / 'install/codex-home/config.toml').read_text(), '[features]\nplugins = false\n')

    def test_segment_is_bounded_by_the_next_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            log = b'old\nengine started: --max-context 156584\nmine\nnext instance\n'
            class Host:
                def log_bytes_since(self, model, offset):
                    return log[offset:]
            start = len(b'old\n'); end = log.index(b'next')
            _, _, started = capture_segment(Host(), 'IQ3_XXS', start, end, folder)
            self.assertEqual((folder / 'engine-request-log.txt').read_text(), 'engine started: --max-context 156584\nmine\n')
            self.assertEqual(started, '--max-context 156584')

    def test_segment_close_collects_that_instance_telemetry(self):
        from unittest.mock import patch
        from tools.reviewer.arw_measure import close_arw_segment
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            record = {'binding_path': str(folder / 'binding.json'), 'engine_log_start_offset': 0, 'complete': True}
            class Host:
                def log_bytes_since(self, model, offset):
                    return b''
            with patch('tools.metrics.host_telemetry.finish', return_value={'samples': 3}) as finish:
                close_arw_segment(record, Host(), 'IQ3_XXS', 0, ({'pid': 1}, folder / 'telemetry'))
            finish.assert_called_once()
            self.assertEqual(record['telemetry'], {'samples': 3})

    def test_spec_readiness_orders_each_repetition_runtime_migration_first(self):
        ids = [('runtime-migration', 1), ('runtime-migration', 2), ('artifact-promotion', 2), ('artifact-promotion', 1)]
        jobs = [(None, {'scenarioId': s, 'instanceId': f'{s}-x-instance-{n}'}, None) for s, n in ids]
        order = [(h['scenarioId'], h['instanceId'][-1]) for _, h, _ in spec_repetition_order(jobs)]
        self.assertEqual(order, [('runtime-migration', '1'), ('artifact-promotion', '1'),
                                 ('runtime-migration', '2'), ('artifact-promotion', '2')])

    def test_arw_owned_runs_refuse_driver_parameters(self):
        from unittest.mock import patch
        class Host:
            def __init__(self, *args):
                self.installation = Path('/install'); self.deployment = {'hardware': 'h'}
        selection = {'host_id': 'rtx3080ti', 'host_hardware': 'h', 'model_owner': 'arw', 'model': 'IQ3_XXS',
                     'engine_overrides': {'spec-min-p': 0.9}}
        with patch('tools.reviewer.native_cli_binding.verify_native_cli', return_value=None), \
                patch('tools.ops.measurement_host.MeasurementHost', Host):
            with self.assertRaisesRegex(ValueError, 'installation defaults'):
                run(None, Path('/nonexistent'), selection, [], Path('c'), host='rtx3080ti')
            selection = {**selection, 'engine_overrides': {}, 'auto_compact_token_limit': 100000}
            with self.assertRaisesRegex(ValueError, 'published context tier'):
                run(None, Path('/nonexistent'), selection, [], Path('c'), host='rtx3080ti')


    def test_batch_starts_cold_through_a_lease_and_reports_the_stopped_model(self):
        from unittest.mock import patch
        class Frontend:
            """Approved residency: release keeps the model; acquiring a measurement lease stops it."""
            def __init__(self, stops):
                self.model, self.lease, self.calls, self.stops = 'qwen3.8-flash-next-iq3_xxs', 'free', [], stops
            def health(self):
                return {'lease': self.lease, 'model': self.model}
        class Controller:
            def __init__(self, frontend): self.frontend = frontend
            def __enter__(self):
                assert self.frontend.lease == 'free'  # never displaces a holder
                self.frontend.lease = 'held'; self.frontend.calls.append('acquire')
                if self.frontend.stops: self.frontend.model = None; self.frontend.calls.append('stop')
                return self
            def call(self, path):
                return {'status': 'stopped' if self.frontend.model is None else 'running'}
            def __exit__(self, *exc):
                self.frontend.lease = 'free'; self.frontend.calls.append('release')
        for stops in (True, False):
            frontend = Frontend(stops)
            class Host:
                def controller(self, folder): return Controller(frontend)
            with patch('tools.reviewer.arw_measure.arw_owned_health', lambda host: frontend.health()):
                if stops:
                    result = cold_start_arw_batch(Host(), Path('unused'))
                    self.assertEqual(result['health'], {'lease': 'free', 'model': None})
                else:
                    with self.assertRaisesRegex(RuntimeError, 'did not stop'):
                        cold_start_arw_batch(Host(), Path('unused'))
            self.assertEqual(frontend.lease, 'free')  # the lease is returned even when the stop fails
            self.assertEqual(frontend.calls, ['acquire', 'stop', 'release'] if stops else ['acquire', 'release'])

if __name__ == '__main__':
    unittest.main()
