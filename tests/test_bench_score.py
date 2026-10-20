import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tools.reviewer import bench_records, bench_score

CID = 'code-spec-reviewer:default-42b4f896-1071-4617-bcba-e1110a1fc457-instance-1:scope-1:problem-14:CODE-SPEC-FINDINGS:finding-9'
SR = ('spec-readiness-reviewer:artifact-promotion-6ccd5ad3-55e9-477f-93b4-0e9e0c9167c0-instance-2:scope-5:unassociated:'
      'MODULE-DESIGN-APPLICABILITY:finding-1')


class StableIdTest(unittest.TestCase):
    def test_preparation_uuid_and_instance_number_are_dropped(self):
        self.assertEqual(bench_score.stable_id(CID), 'code-spec-reviewer:default:scope-1:problem-14:CODE-SPEC-FINDINGS:finding-9')
        self.assertEqual(bench_score.stable_id(SR),
                         'spec-readiness-reviewer:artifact-promotion:scope-5:unassociated:MODULE-DESIGN-APPLICABILITY:finding-1')
        other = CID.replace('42b4f896-1071-4617-bcba-e1110a1fc457', '00000000-1111-2222-3333-444444444444')
        self.assertEqual(bench_score.stable_id(other), bench_score.stable_id(CID))
        with self.assertRaises(ValueError):
            bench_score.stable_id('code-spec-reviewer:default:scope-1')


class MergeTest(unittest.TestCase):
    def test_one_overall_deduction_the_largest(self):
        self.assertEqual(bench_score.merge(0.8, 0.0, False, False), (0.0, 0.8))
        deduction, final = bench_score.merge(0.8, 0.04, True, False)
        self.assertEqual(deduction, 0.1)
        self.assertAlmostEqual(final, 0.72)
        deduction, final = bench_score.merge(0.8, 0.1, True, True)
        self.assertAlmostEqual(final, 0.72)  # pause, f and the ARW cut never multiply
        deduction, final = bench_score.merge(0.5, 0.06, False, False)
        self.assertAlmostEqual(final, 0.47)
        self.assertEqual(bench_score.merge(-0.2, 0.0, True, False)[1], 0.0)

    def test_pause_once_however_many_pauses(self):
        record = {'id': 'x', 'pause_known': True, 'pause_count': 3, 'pause_note': None}
        state = bench_score.pause_state(record, 'refuse')
        self.assertTrue(state['paused'])
        self.assertEqual(bench_score.merge(1.0, 0.0, state['paused'], False)[1], 0.9)

    def test_unknown_pause_is_refused_unless_scored_as_none(self):
        record = {'id': 'x', 'pause_known': False, 'pause_count': None, 'pause_note': 'old harness'}
        with self.assertRaises(ValueError):
            bench_score.pause_state(record, 'refuse')
        state = bench_score.pause_state(record, 'none')
        self.assertFalse(state['paused'])
        self.assertIn('old harness', state['pause_basis'])


def upstream(score_before, codes=(), score=None):
    instance = {'instanceId': 'default-x-instance-1', 'judgmentBinding': {'expectedSha256': 'k'}, 'locatorCount': 50,
                'unrepairableFormatErrors': 0, 'overrunLocators': 0, 'score': score_before, 'rawScore': score_before}
    return {'status': 'diagnostic', 'results': [{'reviewerId': 'r', 'repetitions': [
        {'repetition': 1, 'instances': [instance], 'scoreBeforePenalty': score_before,
         'score': score_before if score is None else score, 'reportDiagnostics': [{'code': c} for c in codes]}]}]}


class RepetitionScoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.registry = Path(self.tmp.name) / 'baseline.json'
        runs = [{'run': 'h', 'r': 2, 'T': 50, 'rRepairable': 2, 'rUnrepairable': 0, 'rOverrun': 0, 'reports': []}]
        self.registry.write_text(json.dumps({'r': {'k': {'runs': runs, 'pBase': 0.04}}}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_treated_diagnostics_keep_score_before_penalty(self):
        up = upstream(0.8, codes=('requirement-scope-continuation', 'review-evidence-invalid'))
        row = bench_score.repetition_score(up, {'default-x-instance-1': None}, self.registry)
        self.assertFalse(row['arw_cut'])
        self.assertEqual(row['scoreBeforePenalty'], 0.8)

    def test_an_untreated_diagnostic_is_the_arw_cut(self):
        up = upstream(0.8, codes=('some-new-code',), score=0.72)
        row = bench_score.repetition_score(up, {'default-x-instance-1': None}, self.registry)
        self.assertTrue(row['arw_cut'])
        self.assertEqual(row['arw_cut_codes'], ['some-new-code'])
        self.assertAlmostEqual(bench_score.merge(row['scoreBeforePenalty'], row['f'], False, row['arw_cut'])[1], 0.72)

    def test_a_cut_that_disagrees_with_the_codes_is_an_error(self):
        with self.assertRaises(ValueError):
            bench_score.repetition_score(upstream(0.8, score=0.72), {'default-x-instance-1': None}, self.registry)


def candidate(n, kind='association'):
    cid = CID.replace('finding-9', f'finding-{n}')
    if kind == 'finding':
        cid = cid.replace('problem-14', 'unassociated')
        return {'candidateId': cid, 'kind': 'finding', 'allowedDecisions': ['unsupported', 'supported', 'problem-14']}
    return {'candidateId': cid, 'kind': 'association', 'allowedDecisions': ['matched', 'not-matched']}


class AdjudicateTest(unittest.TestCase):
    """Upstream stand-in: association candidates first; a finding candidate for each not-matched one; final after."""

    def scorer(self, repository, prepared, input_path, adjudication):
        decided = {}
        if adjudication:
            decided = {d['candidateId']: d['decision'] for d in json.loads(Path(adjudication).read_text())['decisions']}
        self.calls.append(dict(decided))
        pending = [c for c in self.first if c['candidateId'] not in decided]
        for c in self.first:
            if decided.get(c['candidateId']) == 'not-matched':
                f = candidate(c['candidateId'].rsplit('-', 1)[1], 'finding')
                if f['candidateId'] not in decided:
                    pending.append(f)
        reply = {'status': 'needs-adjudication', 'candidates': pending} if pending else upstream(0.5)
        return SimpleNamespace(stdout=json.dumps(reply), stderr='', returncode=0 if not pending else 1)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.first = [candidate(1), candidate(2)]
        self.calls = []
        self.prepared = {'repositoryRoot': 'arw', 'preparedPath': 'prepared.json'}

    def tearDown(self):
        self.tmp.cleanup()

    def test_rounds_until_final_with_stored_decisions(self):
        store = {bench_score.stable_id(candidate(1)['candidateId']): 'matched',
                 bench_score.stable_id(candidate(2)['candidateId']): 'not-matched',
                 bench_score.stable_id(candidate(2, 'finding')['candidateId']): 'supported'}
        decide = lambda c: (store[bench_score.stable_id(c['candidateId'])], 'r', 'store') \
            if bench_score.stable_id(c['candidateId']) in store else None
        up, seen, used, pending = bench_score.adjudicate(self.prepared, 'in.json', self.tmp.name, decide, scorer=self.scorer)
        self.assertEqual(pending, [])
        self.assertEqual(up['status'], 'diagnostic')
        self.assertEqual(len(used), 3)
        self.assertEqual(len(self.calls), 3)
        # Each round gives only decisions of candidates listed so far (no decision the scorer has not asked for).
        self.assertEqual(len(self.calls[1]), 2)

    def test_missing_decisions_are_returned_pending(self):
        decide = lambda c: ('not-matched', 'r', 'store') if c['kind'] == 'association' else None
        up, seen, used, pending = bench_score.adjudicate(self.prepared, 'in.json', self.tmp.name, decide, scorer=self.scorer)
        self.assertEqual([c['kind'] for c in pending], ['finding', 'finding'])

    def test_lower_bound_enumerates_every_finding_candidate(self):
        decide = lambda c: (bench_score.bound_decision(c, 'lower'), 'enumeration', 'enumerate')
        up, seen, used, pending = bench_score.adjudicate(self.prepared, 'in.json', self.tmp.name, decide, scorer=self.scorer)
        self.assertEqual(sorted(c['kind'] for c in seen.values()), ['association', 'association', 'finding', 'finding'])

    def test_a_decision_outside_allowed_values_is_an_error(self):
        with self.assertRaises(ValueError):
            bench_score.adjudicate(self.prepared, 'in.json', self.tmp.name, lambda c: ('supported', 'r', 's'),
                                   scorer=self.scorer)


class RecordHelpersTest(unittest.TestCase):
    def test_tree_differences_leave_out_git_and_tmp(self):
        a = {'src/a.mjs': '1', '.git/index': 'x', '.tmp/reports/r.md': 'y'}
        b = {'src/a.mjs': '1', '.git/index': 'z'}
        self.assertEqual(bench_records.tree_differences(a, b), [])
        self.assertEqual(bench_records.tree_differences(a, {'src/a.mjs': '2'}), ['src/a.mjs'])

    def test_sub_scenario_and_run_suffix(self):
        self.assertEqual(bench_records.sub_scenario(SR.split(':')[1]), 'artifact-promotion')
        self.assertEqual(bench_score.run_suffix('/x/_reviewer-cap/runs/6ccd5ad3/sr/runtime-migration/1'),
                         'sr/runtime-migration/1')

    def test_pause_fields_tell_unknown_from_none(self):
        self.assertEqual(bench_records.pause_fields([], 0, None)['pause_count'], 0)
        unknown = bench_records.pause_fields(None, None, 'old')
        self.assertFalse(unknown['pause_known'])
        self.assertIsNone(unknown['pause_count'])


if __name__ == '__main__':
    unittest.main()
