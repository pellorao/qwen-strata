import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tools.reviewer import bench_records, bench_score, blind_pool

CID = 'code-spec-reviewer:default-42b4f896-1071-4617-bcba-e1110a1fc457-instance-1:scope-1:problem-14:CODE-SPEC-FINDINGS:finding-9'
SR = ('spec-readiness-reviewer:artifact-promotion-6ccd5ad3-55e9-477f-93b4-0e9e0c9167c0-instance-2:scope-5:unassociated:'
      'MODULE-DESIGN-APPLICABILITY:finding-1')


class TemplateFindingsTest(unittest.TestCase):
    def test_near_identical_text_on_three_findings_is_flagged_with_its_credited_candidates(self):
        iid = 'default-819ae2b0-e494-4642-97c2-fd7ba85d8536-instance-1'
        text = 'The applicable adapter contract needed to establish this behavior is not present (`{}`).'
        cands = [{'candidateId': f'r:{iid}:scope-1:unassociated:G1:finding-{i}', 'instanceId': iid, 'check': 'G1',
                  'findingIndex': i, 'finding': text.format(name), 'kind': 'finding'}
                 for i, name in enumerate(('a', 'bb', 'c'))]
        cands.append({'candidateId': f'r:{iid}:scope-1:unassociated:G1:finding-9', 'instanceId': iid, 'check': 'G1',
                      'findingIndex': 9, 'finding': 'Line 12 rejects a total equal to the limit.', 'kind': 'finding'})
        decisions = {'r:default:scope-1:unassociated:G1:finding-1': {'stable_id': 'r:default:scope-1:unassociated:G1:finding-1',
                                                             'decision': 'problem-6', 'source': 'pool x'},
                     'r:default:scope-1:unassociated:G1:finding-2': {'stable_id': 'r:default:scope-1:unassociated:G1:finding-2',
                                                             'decision': 'unsupported', 'source': 'pool x'}}
        out = bench_score.template_findings(cands, decisions)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['findings'], 3)
        self.assertEqual([c['decision'] for c in out[0]['credited']], ['problem-6'])
        self.assertEqual(bench_score.template_findings(cands[:2] + cands[3:], decisions), [])


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

    def test_r8_4_negative_scores_are_kept_and_deducted_by_their_size(self):
        # s - d|s|: a positive score as s(1 - d), a negative one lower still; 0 stays 0.
        self.assertAlmostEqual(bench_score.merge(-0.2, 0.0, True, False)[1], -0.22)
        self.assertAlmostEqual(bench_score.merge(-0.5, 0.04, False, True)[1], -0.55)
        self.assertAlmostEqual(bench_score.merge(-1.3, 0.05, False, False)[1], -1.365)
        self.assertEqual(bench_score.merge(0.0, 0.1, True, True)[1], 0.0)
        # Bit for bit the r8.3 product when s >= 0 (s - d*s can differ from s*(1-d) in the last bit).
        self.assertEqual(bench_score.deduct(0.4662056413372203, 0.1), 0.4662056413372203 * (1 - 0.1))
        # The r8.3 counterpart: cut at 0, deduction multiplied; equal to r8.4 whenever the score is >= 0.
        self.assertEqual(bench_score.r83(-0.2, 0.1), (0.0, 0.0))
        for s, d in ((0.8, 0.1), (0.5, 0.06), (0.0, 0.1), (1.0, 0.0)):
            self.assertEqual(bench_score.r83(s, d)[0], s)
            self.assertAlmostEqual(bench_score.r83(s, d)[1], bench_score.merge(s, d, False, False)[1], places=15)

    def test_no_report_uses_the_model_failure_score_of_the_scoring_patch(self):
        # One decision (user, pending: -1 or 0) in two places: bench_score and scoring-k.patch.
        patch = (bench_score.ROOT / 'benchmarks/reviewer-suite-v1/arw-patches/scoring-k.patch').read_text()
        fails = '+const MODEL_FAILURE_FAILS_CLEAN_CASES = true;' in patch
        self.assertNotEqual(fails, '+const MODEL_FAILURE_FAILS_CLEAN_CASES = false;' in patch)
        self.assertEqual(bench_score.MODEL_FAILURE_FINAL, -1.0 if fails else 0.0)

    def test_pause_once_however_many_pauses(self):
        record = {'id': 'x', 'pause_known': True, 'pause_count': 3, 'pause_note': None, 'pause_basis': 'recorded'}
        state = bench_score.pause_state(record)
        self.assertTrue(state['paused'])
        self.assertEqual(state['pause_basis'], 'recorded')
        self.assertEqual(bench_score.merge(1.0, 0.0, state['paused'], False)[1], 0.9)

    def test_a_pause_without_basis_is_refused(self):
        record = {'id': 'x', 'pause_known': False, 'pause_count': None, 'pause_note': 'no machine log'}
        with self.assertRaises(ValueError):
            bench_score.pause_state(record)
        rebuilt = {'id': 'x', **bench_records.rebuilt_pause(0, 'old harness, 0 by construction')}
        self.assertEqual(bench_score.pause_state(rebuilt)['paused'], False)


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

    def test_a_final_status_error_adds_one_to_r(self):
        up = upstream(0.8)
        plain = bench_score.repetition_score(up, {'default-x-instance-1': None}, self.registry)
        b = bench_score.repetition_score(up, {'default-x-instance-1': None}, self.registry, final_status_errors=1)
        self.assertEqual((b['r'] - plain['r'], b['rFinalStatus'], plain['rFinalStatus']), (1, 1, 0))
        self.assertGreater(b['f'], plain['f'])

    def test_a_cut_that_disagrees_with_the_codes_is_an_error(self):
        with self.assertRaises(ValueError):
            bench_score.repetition_score(upstream(0.8, score=0.72), {'default-x-instance-1': None}, self.registry)

    def test_r8_4_arw_cut_of_a_negative_score_lowers_it(self):
        up = upstream(-0.4, codes=('some-new-code',), score=-0.44)
        row = bench_score.repetition_score(up, {'default-x-instance-1': None}, self.registry)
        self.assertTrue(row['arw_cut'])
        # The r8.3 form (x 0.9 = -0.36) no longer matches.
        with self.assertRaises(ValueError):
            bench_score.repetition_score(upstream(-0.4, codes=('some-new-code',), score=-0.36),
                                         {'default-x-instance-1': None}, self.registry)

    def test_r8_5_missing_checks_are_recorded_and_bound_to_the_plan_version(self):
        up = upstream(0.5)
        up['results'][0]['repetitions'][0].update(missingChecks=2, neutralCleanCases=7)
        up['results'][0]['repetitions'][0]['instances'][0]['missingChecks'] = 2
        row = bench_score.repetition_score(up, {'default-x-instance-1': None}, self.registry)
        self.assertEqual((row['missing_checks'], row['neutral_clean_cases']), (2, 7))
        self.assertEqual(row['per_handoff']['default-x-instance-1']['missingChecks'], 2)
        bench_score.check_scoring_version('r8.5', row)
        with self.assertRaisesRegex(ValueError, 'another version'):
            bench_score.check_scoring_version('r8.4', row)
        old = bench_score.repetition_score(upstream(0.5), {'default-x-instance-1': None}, self.registry)
        self.assertIsNone(old['missing_checks'])
        bench_score.check_scoring_version('r8.4', old)
        with self.assertRaisesRegex(ValueError, 'another version'):
            bench_score.check_scoring_version('r8.5', old)
        # v1 plans select nothing (r8.4); v2 plans select r8.5.
        self.assertEqual(bench_score.scoring_version({'fixed_conditions': {}}), 'r8.4')
        self.assertEqual(bench_score.scoring_version({'fixed_conditions': {'scoring': 'r8.5'}}), 'r8.5')


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


class StoredDecisionTest(unittest.TestCase):
    def test_a_decision_holds_only_for_the_content_it_was_made_for(self):
        live = {**candidate(1), 'check': 'CODE-SPEC-FINDINGS', 'expectation': 'E1', 'finding': '- f', 'result': 'gap',
                'evidence': [{'filePath': 'src/a.mjs', 'line': 400}]}
        sid = bench_score.stable_id(live['candidateId'])
        store = {sid: {'decision': 'not-matched', 'reason': 'r', 'source': 'pool p:p001',
                       'fingerprint': blind_pool.fingerprint(live, 'code-spec-v5')}}
        self.assertEqual(bench_score.stored_choice(store, live, 'code-spec-v5'), ('not-matched', 'r', 'pool p:p001'))
        # Same stable id, the evidence changed (a spill conversion made it valid): adjudicate again.
        changed = {**live, 'evidence': [{'filePath': 'src/a.mjs', 'line': 4}]}
        self.assertEqual(bench_score.stored_choice(store, changed, 'code-spec-v5'), 'stale')
        self.assertIsNone(bench_score.stored_choice({}, live, 'code-spec-v5'))
        legacy = {sid: {'decision': 'matched', 'reason': 'r'}}  # no fingerprint: never reused
        self.assertEqual(bench_score.stored_choice(legacy, live, 'code-spec-v5'), 'stale')


CA_IID = 'default-42b4f896-1071-4617-bcba-e1110a1fc457-instance-1'
EMPTY = hashlib.sha256(b'').hexdigest()


def ca_candidate(check, index, finding):
    return {'candidateId': f'commit-audit-reviewer:{CA_IID}:scope-1:problem-1:{check}:finding-{index + 1}',
            'instanceId': CA_IID, 'check': check, 'findingIndex': index, 'finding': finding, 'kind': 'association'}


class RequirementSourceTest(unittest.TestCase):
    ROWS = [
        {'source': {'filePath': '.scratch/0001-x/issues/01-a.md', 'line': 7}, 'requirement': 'r7', 'result': 'gap',
         'finding': 'same text'},
        {'source': {'filePath': '.scratch/0001-x/issues/01-a.md', 'line': 9}, 'requirement': 'r9', 'result': 'satisfied'},
        {'source': {'filePath': '.scratch/0001-x/issues/02-b.md', 'line': 3}, 'requirement': 'r3', 'result': 'uncertain',
         'finding': 'only in gate one'},
        {'source': {'filePath': '.scratch/0001-x/spec.md', 'line': 11}, 'requirement': 's11', 'result': 'gap',
         'finding': 'spec only'},
        {'source': {'filePath': '.scratch/0001-x/spec.md', 'line': 12}, 'requirement': 's12', 'result': 'gap',
         'finding': 'twice'},
        {'source': {'filePath': '.scratch/0001-x/spec.md', 'line': 14}, 'requirement': 's14', 'result': 'gap',
         'finding': 'twice'},
    ]

    def test_the_row_of_a_finding_by_text_within_its_gate(self):
        source = bench_score.requirement_source(ca_candidate('COMMIT-AUDIT-GATE-1', 1, 'only in gate one'), self.ROWS)
        self.assertEqual(source, {'filePath': '.scratch/0001-x/issues/02-b.md', 'line': 3, 'requirement': 'r3'})
        # findingIndex counts per gate: the spec row is GATE-2 finding 0.
        source = bench_score.requirement_source(ca_candidate('COMMIT-AUDIT-GATE-2', 0, 'spec only'), self.ROWS)
        self.assertEqual(source['line'], 11)

    def test_a_repeated_text_is_resolved_by_finding_index_or_refused(self):
        self.assertEqual(bench_score.requirement_source(ca_candidate('COMMIT-AUDIT-GATE-2', 2, 'twice'), self.ROWS)['line'], 14)
        with self.assertRaises(ValueError):
            bench_score.requirement_source(ca_candidate('COMMIT-AUDIT-GATE-2', 0, 'twice'), self.ROWS)
        with self.assertRaises(ValueError):
            bench_score.requirement_source(ca_candidate('COMMIT-AUDIT-GATE-2', 0, 'same text'), self.ROWS)

    def test_annotate_reads_the_scored_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / 'review.jsonl'
            report.write_text(''.join(json.dumps(r) + '\n' for r in self.ROWS) + 'not json\n')
            upstream_input = {'artifacts': [{'reviewerId': 'commit-audit-reviewer', 'instances': [
                {'instanceId': CA_IID, 'artifactPaths': None,
                 'formatCorrection': {'originalReportPath': 'x', 'correctedReportPath': str(report)}}]}]}
            c = bench_score.annotate(ca_candidate('COMMIT-AUDIT-GATE-1', 0, 'same text'), 'commit-audit-v3', upstream_input, {})
            self.assertEqual(c['requirementSource']['line'], 7)
            self.assertEqual(blind_pool.pool_item(c, 'commit-audit-v3')['requirementSource']['requirement'], 'r7')
            other = bench_score.annotate({'candidateId': CID}, 'code-spec-v5', upstream_input, {})
            self.assertNotIn('requirementSource', other)


class ReportsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.prepared = {'preparedPath': str(t / 'prepared.json'), 'handoffs': [
            {'instanceId': CA_IID, 'reviewerId': 'code-spec-reviewer', 'scenarioRoot': str(t / 'scenario'),
             'input': {'reportPath': str(t / 'scenario/.tmp/reports/review-result.md')}}]}
        Path(self.prepared['preparedPath']).write_text(json.dumps({'contracts': []}))
        self.work = t / 'work'

    def tearDown(self):
        self.tmp.cleanup()

    def record(self, **handoff):
        return {'id': 'anthropic/code-spec-v5/opus-low-a1', 'dir': self.tmp.name, 'original_prepared': None,
                'handoffs': [{'k': 0, 'instanceId': CA_IID, 'sub_scenario': 'default', 'report': None,
                              'report_sha256': None, 'report_ok': False, **handoff}]}

    def test_a_recorded_sha_without_its_report_is_an_error(self):
        with self.assertRaises(ValueError):
            bench_score.place_reports(self.record(report_sha256='ab' * 32), self.prepared, self.work)

    def test_no_report_goes_upstream_as_a_model_failure(self):
        upstream_input, repairs, rows = bench_score.place_reports(self.record(report_exists=False), self.prepared, self.work)
        [entry] = upstream_input['artifacts'][0]['instances']
        self.assertEqual(entry['artifactPaths'], None)
        self.assertTrue(entry['modelFailure']['reason'].strip())
        self.assertNotIn('formatCorrection', entry)
        self.assertEqual(repairs, {CA_IID: None})
        self.assertEqual(rows[0]['scored'], 'modelFailure: no report')

    def failures(self, **entry):
        path = Path(self.tmp.name) / 'model-failures.json'
        path.write_text(json.dumps({'failures': [{'record': 'anthropic/code-spec-v5/opus-low-a1', 'k': 0,
                                                  'sub_scenario': 'default', 'report_sha256': EMPTY, 'basis': 'test basis',
                                                  'confirmed': 'Main test', **entry}]}))
        return path

    def test_a_confirmed_empty_report_goes_upstream_as_a_model_failure(self):
        report = Path(self.tmp.name) / 'review-result.md'
        report.write_text('')
        record = self.record(report=str(report), report_sha256=EMPTY, report_ok=True, report_exists=True)
        upstream_input, repairs, rows = bench_score.place_reports(record, self.prepared, self.work, self.failures())
        [entry] = upstream_input['artifacts'][0]['instances']
        self.assertEqual(entry['artifactPaths'], None)
        self.assertIn('test basis', entry['modelFailure']['reason'])
        self.assertEqual(repairs, {CA_IID: None})
        self.assertEqual(rows[0]['scored'], 'modelFailure: confirmed')
        # Not confirmed: the empty report goes upstream as written (ARW then asks for a confirmed modelFailure).
        self.assertEqual(bench_score.confirmed_failures(record['id'], Path(self.tmp.name) / 'none.json'), {})
        self.assertEqual(bench_score.confirmed_failures('anthropic/code-spec-v5/opus-low-a2', self.failures()), {})

    def test_a_confirmation_binds_one_empty_report(self):
        report = Path(self.tmp.name) / 'review-result.md'
        report.write_text('- `src/a.mjs:1`: a finding.\n')
        sha = hashlib.sha256(report.read_bytes()).hexdigest()
        record = self.record(report=str(report), report_sha256=sha, report_ok=True, report_exists=True)
        with self.assertRaisesRegex(ValueError, 'another sub-scenario or report'):
            bench_score.place_reports(record, self.prepared, self.work, self.failures())
        with self.assertRaisesRegex(ValueError, 'with content'):
            bench_score.place_reports(record, self.prepared, self.work, self.failures(report_sha256=sha))
        with self.assertRaisesRegex(ValueError, 'does not have'):
            bench_score.place_reports(record, self.prepared, self.work, self.failures(k=3))
        with self.assertRaisesRegex(ValueError, 'without basis'):
            bench_score.place_reports(record, self.prepared, self.work, self.failures(basis=' '))

    def test_registered_model_failures_bind_empty_reports_with_a_basis(self):
        entries = json.loads(bench_score.MODEL_FAILURES.read_text())['failures']
        self.assertEqual(len({(e['record'], e['k']) for e in entries}), len(entries))
        for e in entries:
            self.assertEqual(e['report_sha256'], EMPTY)
            self.assertTrue(e['basis'].strip() and e['confirmed'].strip())

    def test_preparation_without_original_or_manifest_is_marked_unverified(self):
        checks = bench_score.check_preparation(self.record(), self.prepared)
        self.assertTrue(checks['unverified'])
        self.assertEqual(checks['trees'], [{'k': 0, 'tree': 'no manifest kept'}])


def local_codex_plan(plan, directory):
    """The plan with its Codex pin pointed at a stand-in executable: these tests score reports and never run Codex, so
    they must not need the benchmark copy of whichever version a (finished or later) plan was frozen with."""
    from unittest.mock import patch
    executable = Path(directory) / 'codex'
    executable.write_bytes(b'stand-in for the Codex binary')
    plan['fixed_conditions'].update(codex='stand-in', native_cli_sha256=hashlib.sha256(executable.read_bytes()).hexdigest())
    return patch('tools.tuning.arw_dimension.codex_binary', return_value=executable)


class SpillScoringEndToEndTest(unittest.TestCase):
    """A spill-cited report on a fresh zero-model Code Standards v5.1 preparation, scored by the frozen ARW scorer:
    the converted fragments counted in r are locators T reads, one each, and T is the same for the report as written,
    the converted copy and a report written with the source lines directly."""

    def test_r_and_t_count_the_same_fragments(self):
        from tools.reviewer.repair_reviewer_report import spill_map, staged_sources
        from tools.tuning.arw_dimension import load_plan, prepare
        plan = load_plan(bench_records.ROOT / 'benchmarks/multi-model-v1/scenarios/code-standards-v5.1.json')[0]
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            with local_codex_plan(plan, work):
                prepare(plan, None, work / 'prep', time_limit_seconds=1200)
            prepared = json.loads((work / 'prep/preparation.json').read_text())
            handoff = prepared['handoffs'][0]
            diff = subprocess.run(['git', '-C', handoff['scenarioRoot'], 'diff', '--cached'], capture_output=True,
                                  text=True, check=True).stdout
            spill_text = 'other output\n' * 400 + diff
            spill = work / 'spill.txt'
            spill.write_text(spill_text)
            mapping, counts = spill_map(spill_text), staged_sources(handoff['scenarioRoot'])
            n = next(n for n in sorted(mapping) if n > counts[mapping[n][0]] and all(
                mapping.get(n + d, (None, None))[:2] == (mapping[n][0], mapping[n][1] + d) for d in (1, 2)))
            path, line = mapping[n][:2]
            other = next(p for p in sorted(counts) if p != path and p.endswith('.mjs'))
            body = lambda a: (f'- `{path}:{a},{a + 1}-{a + 2}`, `{other}:1`: first finding.\n'
                              f'- `{other}:2`: second finding.\n')
            old = os.environ.get('CODEX_THREAD_ID')
            os.environ['CODEX_THREAD_ID'] = plan['codex_thread_id']
            try:
                results = {}
                for name, text, spills in (('spill', body(n), [str(spill)]), ('as-written', body(n), []),
                                           ('direct', body(line), [])):
                    report = work / f'{name}.md'
                    report.write_text(text)
                    record = {'id': f'anthropic/code-standards-v5.1/{name}', 'handoffs': [
                        {'k': 0, 'instanceId': handoff['instanceId'], 'report': str(report),
                         'report_sha256': hashlib.sha256(report.read_bytes()).hexdigest(), 'report_ok': True,
                         'spill_files': spills}]}
                    upstream_input, repairs, rows = bench_score.place_reports(record, prepared, work / name)
                    bench_score.save(work / name / 'in.json', upstream_input)
                    up, _, _, _ = bench_score.adjudicate(
                        prepared, work / name / 'in.json', work / name / 'up',
                        lambda c: (bench_score.bound_decision(c, 'lower'), 'test', 'test'))
                    results[name] = (bench_score.repetition_score(up, repairs), rows[0])
            finally:
                if old is None:
                    os.environ.pop('CODEX_THREAD_ID', None)
                else:
                    os.environ['CODEX_THREAD_ID'] = old
        spilled, row = results['spill']
        self.assertEqual((row['spill_edits'], row['spill_fragments']), (1, 2))
        self.assertEqual(spilled['rRepairable'], 2)
        self.assertEqual({name: r['T_locators'] for name, (r, _) in results.items()},
                         {'spill': 4, 'as-written': 4, 'direct': 4})
        self.assertEqual(results['direct'][0]['rRepairable'], 0)
        # The converted copy is scored as the report written with the source lines.
        self.assertEqual(spilled['scoreBeforePenalty'], results['direct'][0]['scoreBeforePenalty'])


class ModelFailureEndToEndTest(unittest.TestCase):
    """r8.4 on the four frozen answer keys of the benchmark: the negative-score denominator kCleanWeight (every clean
    case's k, no-other cases at 0.25, a merged case once, the Spec Readiness pair added up) and the model failure score
    (no clean case failed: 0, the same as reporting nothing, user 2026-10-21), through a fresh zero-model preparation
    and the frozen ARW scorer."""

    # Plan: (Σk of the clean cases, handoffs). Commit Audit v3: 50 clean cases with 18 merged pairs -> 50 units at 0.25.
    EXPECTED = {'code-spec-v5': (7.25, 1), 'code-standards-v5.1': (16.25, 1), 'spec-readiness-v4.3': (14.75, 2),
                'commit-audit-v3': (12.5, 1)}

    def test_clean_weight_and_model_failure_score_of_each_scenario(self):
        from tools.tuning.arw_dimension import load_plan, prepare
        old = os.environ.get('CODEX_THREAD_ID')
        try:
            for name, (clean_weight, handoffs) in self.EXPECTED.items():
                with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                    plan = load_plan(bench_records.ROOT / f'benchmarks/multi-model-v1/scenarios/{name}.json')[0]
                    work = Path(tmp)
                    limited = 'measurement_note_template' in plan['fixed_conditions']
                    with local_codex_plan(plan, work):
                        prepare(plan, None, work / 'prep', time_limit_seconds=1200 if limited else None)
                    prepared = json.loads((work / 'prep/preparation.json').read_text())
                    os.environ['CODEX_THREAD_ID'] = plan['codex_thread_id']
                    # The first repetition, as an instance record pairs its handoffs with the fresh ones.
                    record = {'id': f'anthropic/{name}/failure', 'handoffs': [
                        {'k': k, 'instanceId': h['instanceId'], 'report': None, 'report_sha256': None}
                        for k, h in enumerate(prepared['handoffs'][:handoffs])]}
                    upstream_input, repairs, _ = bench_score.place_reports(record, prepared, work / 'score')
                    bench_score.save(work / 'in.json', upstream_input)
                    up, seen, _, pending = bench_score.adjudicate(prepared, work / 'in.json', work / 'up', lambda c: None)
                    self.assertEqual((seen, pending), ({}, []))
                    [rep] = [rep for result in up['results'] for rep in result['repetitions']]
                    self.assertAlmostEqual(rep['kCleanWeight'], clean_weight)
                    self.assertEqual(rep['kFailedCleanWeight'], 0)
                    self.assertEqual(rep['kEarnedProblemPoints'], 0)
                    self.assertAlmostEqual(rep['scoreBeforePenalty'], bench_score.MODEL_FAILURE_FINAL)
                    self.assertEqual(rep['rawScore'], 0)
                    # The format penalty of the scorer's model failure output: no error, no locator, f 0.
                    scored = bench_score.repetition_score(up, repairs)
                    self.assertEqual((scored['r'], scored['T_locators'], scored['f']), (0, 0, 0))
        finally:
            if old is None:
                os.environ.pop('CODEX_THREAD_ID', None)
            else:
                os.environ['CODEX_THREAD_ID'] = old


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
