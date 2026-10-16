"""The project's ARW scoring upgrade: evidence F2 instead of F3 (user 2026-10-14); r7: adjudicated clean
cases, phrase terms, no evidence threshold for problem cases with k >= 1 (user 2026-10-15); r8: every case
weighted by k, score = (earned problem points - failed clean weight) / problem cases (user 2026-10-16)."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from tools.reviewer import freeze_arw_source
from tools.reviewer.freeze_arw_source import PATCHES, SCORING_UPGRADE, git_apply, materialize, upgrade_scoring

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = ROOT / 'benchmarks/reviewer-suite-v1/source-snapshots/current'
CONFORMANCE = 'lib/release/reviewer-capability-conformance.mjs'

# Synthetic Spec Readiness cases: P problem at k 1, Q problem at k 0.25, C clean at k 1, D clean at k 0.25.
K_PROBE = r'''
import {resolve, join} from 'node:path';
import {mkdtempSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
const arw = process.argv[1];
const {createReviewerCapabilityScenarioScorer} = await import(resolve(arw, 'lib/release/reviewer-capability-scoring.mjs'));
const {reviewerCapabilityVerificationCore: core} = await import(resolve(arw, 'lib/release/reviewer-capability-verification.mjs'));
const {reviewerCapabilityReportPolicy: policy} = await import(resolve(arw, 'lib/release/reviewer-capability-conformance.mjs'));
const filePath = 'specs/rules.md';
const scope = 'SPEC-READINESS-REQUIREMENTS';
const evidenceSources = new Map([[filePath, ['Alpha.', 'Beta.', 'Gamma.', 'Delta.', 'Clean target.', 'Other clean.', 'Problem two.',
    'Third clean.', 'Problem three.'].join('\n')]]);
const lines = (...numbers) => numbers.map(line => ({filePath, line}));
const problem = (expectation, terms, evidence, association, k) => ({associationEvidence: lines(...association),
    evidence: lines(...evidence), expectation, findingTerms: terms, ...(k ? {k} : {}),
    placements: [{associationEvidence: lines(...association), check: scope, evidence: lines(...evidence)}], result: 'gap'});
const clean = (expectation, terms, evidence, extra = {}) => ({evidence: lines(...evidence), expectation, findingTerms: terms, ...extra});
const P = problem('The alpha rule is violated.', ['alpha rule'], [1, 2, 3, 4], [1], 1);
const Q = problem('The second problem is present.', ['second problem'], [7], [7]);
const R = problem('The third problem is present.', ['third problem'], [9], [9], 1);
const C = clean('The clean target is correct.', ['clean target'], [5], {k: 1});
const D = clean('The other clean part is correct.', ['other clean'], [6]);
const E = clean('The third clean part is correct.', ['third clean'], [8], {k: 1});
const scorerFor = (problemCases, cleanCases) => createReviewerCapabilityScenarioScorer({evidenceSources, instanceId: 'probe',
    expected: {cleanCount: cleanCases.length + 1, kind: 'spec-readiness-artifact', problemCount: problemCases.length,
        scopes: [{scope, problemCases, cleanCases: [...cleanCases, {noOtherSupportedFinding: true}]}]},
    reviewerId: 'spec-readiness-reviewer', scenarioRoot: resolve('/probe')});
// Association candidates are all matched; finding candidates get findingDecisions[i] for the i-th one, or stay
// undecided (mechanical result) when it is missing.
const run = (scorer, findings, present = true, findingDecisions = []) => {
    const checks = present ? [{check: scope, findings, result: findings.length ? 'gap' : 'pass'}] : [];
    // As ARW scores Spec Readiness: every clean case of a missing check gets observation score 0.
    const cleanObservationScores = present ? new Map() : new Map([[scope, new Map([0, 1, 2].map(index => [index, 0]))]]);
    const provisional = scorer({checks, cleanObservationScores});
    const decisions = new Map(provisional.candidates.filter(candidate => candidate.kind === 'association')
        .map(candidate => [candidate.candidateId, 'matched']));
    const settled = scorer({adjudicationDecisions: decisions, checks, cleanObservationScores});
    settled.candidates.filter(candidate => candidate.kind === 'finding').forEach((candidate, index) => {
        if (findingDecisions[index] !== undefined) decisions.set(candidate.candidateId, findingDecisions[index]);
    });
    return scorer({adjudicationDecisions: decisions, checks, cleanObservationScores});
};
const pick = result => ({...Object.fromEntries(['kProblemWeight', 'kEarnedProblemPoints', 'kFailedCleanWeight', 'kTiers', 'rawScore',
    'score', 'kWarning', 'extraFailedCleanCases', 'locatorCount'].map(key => [key, result[key]])),
    problem: result.caseScores.problem, clean: result.caseScores.clean[0],
    findingCandidates: result.candidates.filter(candidate => candidate.kind === 'finding').map(candidate => candidate.allowedDecisions)});
const single = scorerFor([P, Q], [C, D]);
const finding = (text, ...evidence) => ({evidence: lines(...evidence), finding: text, result: 'gap'});
// Spec Readiness pair: C is scored in both scenarios at half share, R and E only in the second.
const half = {...C, kShare: 0.5};
const first = run(scorerFor([P, Q], [half, D]), []);
const second = run(scorerFor([R, Q], [half, D, E]), []);
let unequal, partial, missing;
try { core.combineScenarios([first]); } catch (error) { unequal = error.message; }
// A result without k counts, or with only some of them, is an error rather than scored at the default k.
const plain = run(scorerFor([Q], [D]), [finding('The second problem is present.', 7)]);
const countKeys = ['kEarnedProblemPoints', 'kFailedCleanWeight', 'kProblemWeight', 'kTiers'];
const stripped = Object.fromEntries(Object.entries(plain).filter(([key]) => !countKeys.includes(key)));
try { core.combineScenarios([{...stripped, kProblemWeight: 1}]); } catch (error) { partial = error.message; }
try { core.combineScenarios([stripped, stripped]); } catch (error) { missing = error.message; }
// A Spec Readiness pair is added up before the score is cut to [0, 1]: three unsupported findings put the first scenario
// below 0 (no-other and two extra failed clean cases), a full hit puts the second above it.
const below = run(scorerFor([Q], [D]), [finding('Something else.', 3), finding('Another thing.', 4), finding('A third thing.', 2)], true,
    ['unsupported', 'unsupported', 'unsupported']);
const above = run(scorerFor([Q], [D]), [finding('The second problem is present.', 7)]);
// A clean case with a partial observation score (Commit Audit): k 1 passes when the score is above 0, k 0.25 loses 1 - score.
const partialClean = single({checks: [{check: scope, findings: [], result: 'pass'}],
    cleanObservationScores: new Map([[scope, new Map([[0, 0.5], [1, 0.5]])]])});
// k 4 in the scorer (answer keys may not mark it before dual adjudication exists): one falsely flagged clean case costs
// as much as four missed problem cases.
const heavy = scorerFor([Q], [{...C, k: 4}]);
const unmarked = ({k, ...rest}) => rest;
// r7: Code Standards evidence of a 10-line file. A range that starts inside the file and runs past its end is cut to the
// last line and counted; a single line or a range starting past the end stays invalid and earns nothing.
const codeFile = 'src/a.mjs';
const codeScorer = createReviewerCapabilityScenarioScorer({evidenceSources: new Map([[codeFile, Array.from({length: 10}, (_, i) => `l${i + 1};`).join('\n')]]),
    expected: {cleanCount: 2, problemCount: 1, scopes: [{scope: 'S', problemCases: [{associationEvidence: [{filePath: codeFile, line: 9}],
        evidence: [{filePath: codeFile, line: 9}, {filePath: codeFile, line: 10}], expectation: 'The alpha rule is violated.',
        findingTerms: [['alpha rule']], result: 'gap'}],
        cleanCases: [{evidence: [{filePath: codeFile, line: 2}], expectation: 'Beta is fine.', findingTerms: [['beta part']]},
            {noOtherSupportedFinding: true}]}]},
    instanceId: 'code', reviewerId: 'code-standards-reviewer', scenarioRoot: resolve('/probe')});
const codeRun = (evidence, reportedFailedCleanCases = 0) => {
    const checks = [{check: 'S', findings: [{evidence, finding: 'The alpha rule is violated.', result: 'gap'}], result: 'gap'}];
    const provisional = codeScorer({checks, reportedFailedCleanCases});
    const adjudicationDecisions = new Map(provisional.candidates.map(candidate => [candidate.candidateId, 'matched']));
    const result = codeScorer({adjudicationDecisions, checks, reportedFailedCleanCases});
    return {...pick(result), overrunLocators: result.overrunLocators, result};
};
const range = (lineStart, lineEnd) => ({filePath: codeFile, lineStart, lineEnd});
const strip = ({result, ...rest}) => rest;
const cut = codeRun([range(8, 10)]);
// Each report diagnostic code through the repetition summary: is the repetition cut by 0.9, and is it an unrepairable format error.
const policyCodes = ['review-format-invalid', 'review-json-invalid', 'review-utf8-invalid', 'review-row-unattributed', 'review-evidence-overrun',
    'review-evidence-invalid', 'evidence-locator-invalid', 'review-row-invalid', 'requirement-row-invalid', 'requirement-missing',
    'requirement-coverage-invalid', 'requirement-duplicate', 'requirement-conflicting', 'requirement-source-unexpected',
    'requirement-source-invalid', 'requirement-scope-continuation', 'some-new-code'];
const treatment = Object.fromEntries(policyCodes.map(code => {
    const reportDiagnostics = [{code, instanceId: 'code', message: code, reviewerId: 'code-standards-reviewer'}];
    const summary = policy.summarizeCapabilityScores({contract: {reviewerId: 'code-standards-reviewer'}, instanceScores: [{artifact: {},
        instanceId: 'code', repetition: 1, reportDiagnostics, result: cut.result, scenarioId: 'default',
        unrepairableFormatErrors: policy.unrepairableFormatErrorCount(reportDiagnostics)}]});
    const [repetition] = summary.repetitions;
    return [code, {cut: repetition.score !== repetition.scoreBeforePenalty, unrepairable: repetition.instances[0].unrepairableFormatErrors}];
}));
// r7: a Spec Readiness report that continues past the requirement-scope stop. The later check, its report lines and their
// diagnostics are ignored; the stop rule itself is one failed clean case at k 0.25.
const stopReport = join(mkdtempSync(join(tmpdir(), 'stop-')), 'draft.jsonl');
writeFileSync(stopReport, [JSON.stringify({check: scope, evidence: [], finding: 'The second problem is present.', result: 'gap'}),
    JSON.stringify({check: 'MODULE-DESIGN-INTERFACES', evidence: ['nowhere:1'], finding: 'Something else.', result: 'gap', extra: 1}),
    'not json', ''].join('\n'));
const stopChecks = [{check: scope, findings: [finding('The second problem is present.', 7)], result: 'gap'},
    {check: 'MODULE-DESIGN-INTERFACES', findings: [finding('Something else.', 3), finding('The alpha rule is violated.', 1)], result: 'gap'}];
const stopDiagnostics = [{code: 'requirement-scope-continuation', message: 'continued'}, {code: 'review-evidence-invalid', line: 2, message: 'x'},
    {code: 'review-format-invalid', line: 2, message: 'x'}, {code: 'review-format-invalid', line: 3, message: 'x'}];
const kept = await policy.withoutScopeContinuation({checks: stopChecks, diagnostics: stopDiagnostics, path: stopReport});
const stopScore = (checks, reportedFailedCleanCases) => {
    const provisional = single({checks, reportedFailedCleanCases});
    const decisions = new Map(provisional.candidates.filter(candidate => candidate.kind === 'association').map(candidate => [candidate.candidateId, 'matched']));
    const result = single({adjudicationDecisions: decisions, checks, reportedFailedCleanCases});
    return {...pick(result), candidates: result.candidates.length};
};
const stopped = [{check: scope, findings: [finding('The second problem is present.', 7)], result: 'gap'}];
console.log(JSON.stringify({
    continuation: {checks: kept.checks.map(check => check.check), diagnostics: kept.diagnostics.map(item => [item.code, item.line ?? null]),
        unrepairable: policy.unrepairableFormatErrorCount(kept.diagnostics), ignored: stopScore(kept.checks, 1),
        unfiltered: stopScore(stopChecks, 1), stopped: stopScore(stopped, 0)},
    overrun: strip(codeRun([range(8, 12)])),
    cut: strip(cut),
    overrunLine: strip(codeRun([{filePath: codeFile, line: 12}])),
    pastEnd: strip(codeRun([range(11, 12)])),
    reportedFailedClean: strip(codeRun([range(8, 10)], 1)),
    treatment,
    silent: pick(run(single, [])),
    hit: pick(run(single, [finding('The alpha rule is violated.', 1, 2, 3, 4), finding('The second problem is present.', 7)])),
    weakHit: pick(run(single, [finding('The alpha rule is violated.', 1), finding('The second problem is present.', 7)])),
    falseClean: pick(run(single, [finding('The clean target is wrong.', 5)])),
    // r7: the nominated false clean is confirmed or rejected by adjudication.
    falseCleanConfirmed: pick(run(single, [finding('The clean target is wrong.', 5)], true, ['false-positive:clean-1'])),
    falseCleanRejected: pick(run(single, [finding('The clean target is wrong.', 5)], true, ['unsupported'])),
    supported: pick(run(single, [finding('The clean target is wrong.', 5)], true, ['supported'])),
    twoUnsupported: pick(run(single, [finding('Something else.', 3), finding('Another thing.', 4)], true, ['unsupported', 'unsupported'])),
    twoFalseCleans: pick(run(single, [finding('The clean target is wrong.', 5), finding('Again the clean target.', 5)], true,
        ['false-positive:clean-1', 'false-positive:clean-1'])),
    // A finding without the association evidence is associated by adjudication.
    addedAssociation: pick(run(single, [finding('The alpha rule is violated.', 2, 3)], true, ['problem-1'])),
    // Multi-word terms match only as a contiguous phrase.
    scatteredTerms: pick(run(single, [finding('The target here is not clean.', 5)])),
    validation: (() => {
        const candidates = [{candidateId: 'a', allowedDecisions: ['matched', 'not-matched']}, {candidateId: 'f', allowedDecisions: ['unsupported', 'supported']}];
        const decide = (...pairs) => core.validateAdjudication({candidates, adjudication: {decisions: pairs.map(([candidateId, decision]) => ({candidateId, decision, reason: 'r'}))}});
        const pending = decide(['a', 'matched']);
        return {pending: pending.pending.map(candidate => candidate.candidateId), notAllowed: 'finding' in decide(['f', 'matched']),
            unknown: 'finding' in decide(['x', 'matched']), complete: decide(['a', 'not-matched'], ['f', 'supported']).pending.length};
    })(),
    timestamps: core.parseMarkdownArtifact({reviewerId: 'code-standards-reviewer', scope: 'S',
        response: '- `src/a.mjs:3,5` runs at `00:00:00.000`, `at = 10:00:30.000Z`, `13:45` and `startAt: 12:00`.'}),
    missingCheck: pick(run(single, [], false)),
    // r8: without its check, a clean case fails even when the caller gives no observation score (Code Review, Commit Audit).
    codeMissing: pick(codeScorer({checks: []})),
    heavyFalseClean: pick(run(heavy, [finding('The clean target is wrong.', 5)])),
    // An instance prepared under the two-part score (r7) keeps judgment marks and shares in its prepared state.
    legacy: pick(run(scorerFor([{...unmarked(P), judgment: true}, Q], [{...unmarked(C), judgment: true, judgmentShare: 0.5}, D]),
        [finding('The clean target is wrong.', 5)])),
    pairFirst: pick(first),
    pair: pick(core.combineScenarios([first, second])),
    unequal,
    plain: pick(core.combineScenarios([plain, plain])),
    partial,
    missing,
    below: pick(below),
    above: pick(above),
    belowAbove: pick(core.combineScenarios([below, above])),
    partialClean: pick(partialClean),
    formula: core.kScore({kEarnedProblemPoints: 3, kFailedCleanWeight: 0.5, kProblemWeight: 5}),
    balanced: core.unbalancedKTiers({1: {clean: 2, problem: 2}, 4: {clean: 1, problem: 4}}),
    unbalanced: core.unbalancedKTiers({1: {clean: 2, problem: 2}, 4: {clean: 1, problem: 1}}),
}));
'''


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ScoringUpgradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.arw = Path(cls.tmp.name) / 'arw'
        manifest = json.loads((SNAPSHOTS / 'manifest-code-spec-v5.json').read_text())
        materialize(manifest, SNAPSHOTS / manifest['snapshot']['file'], cls.arw)
        cls.probe = json.loads(subprocess.run(['node', '--input-type=module', '-e', K_PROBE, str(cls.arw)],
                                              check=True, capture_output=True, text=True).stdout)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_materialized_copy_scores_evidence_with_f2(self):
        source = (self.arw / 'lib/release/reviewer-capability-scoring.mjs').read_text()
        self.assertIn('fBetaScore({beta: 2, precision, recall: coverage})', source)
        self.assertNotIn('beta: 3', source)
        result = upgrade_scoring(self.arw)
        self.assertEqual((result['applied'], result['migrated_from']), (False, None))
        self.assertEqual(result['judgment']['code-spec-reviewer']['judgment'], 'all-B')
        self.assertEqual(json.loads((self.arw / 'reviewer-judgment/registry.json').read_text()),
                         json.loads((freeze_arw_source.JUDGMENT / 'registry.json').read_text()))

    def test_copies_left_by_superseded_drafts_migrate(self):
        conformance = digest(self.arw / CONFORMANCE)
        for name, _ in SCORING_UPGRADE['superseded'].values():
            with self.subTest(name):
                git_apply(PATCHES / SCORING_UPGRADE['file'], self.arw, '--reverse')
                git_apply(PATCHES / name, self.arw)
                (self.arw / 'reviewer-pairs').mkdir(exist_ok=True)
                self.assertEqual(upgrade_scoring(self.arw)['migrated_from'], name)
                self.assertEqual(digest(self.arw / CONFORMANCE), conformance)
                self.assertFalse((self.arw / 'reviewer-pairs').exists())
                for member, (_, upgraded) in SCORING_UPGRADE['members'].items():
                    self.assertEqual(digest(self.arw / member), upgraded, member)

    def test_r8_score_is_earned_problem_points_minus_failed_clean_weight(self):
        probe = self.probe
        # Reporting nothing scores 0; P (k 1) and Q (k 0.25) found with full evidence score 1.
        self.assertEqual((probe['silent']['rawScore'], probe['silent']['kProblemWeight']), (0, 2))
        self.assertEqual(probe['hit']['score'], 1)
        # r7 (R6): an associated problem case at k >= 1 earns 1 whatever its evidence score.
        self.assertGreater(probe['weakHit']['problem'][0], 0)
        self.assertLess(probe['weakHit']['problem'][0], 1)
        self.assertEqual(probe['weakHit']['kEarnedProblemPoints'], 2)
        # The falsely flagged clean case C costs its k 1; a negative total becomes 0.
        self.assertEqual(probe['falseClean']['kFailedCleanWeight'], 1)
        self.assertEqual((probe['falseClean']['rawScore'], probe['falseClean']['score']), (-0.5, 0))
        self.assertEqual(probe['heavyFalseClean']['kFailedCleanWeight'], 4)
        self.assertEqual(probe['heavyFalseClean']['kTiers'], {'4': {'clean': 1, 'problem': 0}})
        self.assertIn('unbalanced', probe['heavyFalseClean']['kWarning'])
        self.assertAlmostEqual(probe['formula']['score'], 0.5)
        self.assertEqual(probe['balanced'], [])
        self.assertEqual(probe['unbalanced'], ['4'])

    def test_r8_reads_judgment_marks_of_instances_prepared_under_r7_as_k_1(self):
        legacy = self.probe['legacy']
        self.assertEqual(legacy['kTiers'], {'1': {'clean': 0.5, 'problem': 1}})
        self.assertEqual(legacy['kFailedCleanWeight'], 0.5)

    def test_r8_clean_cases_of_a_missing_check_fail(self):
        # C (k 1), D and no-other (k 0.25 each).
        self.assertEqual(self.probe['missingCheck']['kFailedCleanWeight'], 1.5)
        self.assertEqual(self.probe['codeMissing']['clean'], [0, 0])
        self.assertEqual(self.probe['codeMissing']['kFailedCleanWeight'], 0.5)

    def test_spec_readiness_pair_counts_a_shared_case_once(self):
        first, pair = self.probe['pairFirst'], self.probe['pair']
        self.assertEqual(first['kTiers'], {'1': {'clean': 0.5, 'problem': 1}})
        self.assertIn('unbalanced', first['kWarning'])
        # P, R, the shared clean case (0.5 twice) and E: balanced at k 1 once paired.
        self.assertEqual(pair['kTiers'], {'1': {'clean': 2, 'problem': 2}})
        self.assertEqual((pair['kProblemWeight'], pair['kFailedCleanWeight'], pair['score']), (4, 0, 0))
        self.assertNotIn('kWarning', pair)
        self.assertIn('unbalanced in one scoring unit', self.probe['unequal'])

    def test_results_without_k_counts_are_rejected(self):
        self.assertEqual(self.probe['plain']['kTiers'], {})
        self.assertIn('incomplete k counts', self.probe['partial'])
        self.assertIn('incomplete k counts', self.probe['missing'])

    def test_spec_readiness_pair_is_added_up_before_the_cut(self):
        below, above, pair = self.probe['below'], self.probe['above'], self.probe['belowAbove']
        self.assertEqual((below['kFailedCleanWeight'], below['extraFailedCleanCases'], below['rawScore']), (0.75, 2, -0.75))
        self.assertEqual(below['score'], 0)
        self.assertGreater(above['rawScore'], 0.75)
        self.assertAlmostEqual(pair['rawScore'], (above['kEarnedProblemPoints'] - 0.75) / 2)
        self.assertAlmostEqual(pair['score'], pair['rawScore'])
        # Cutting each scenario first would score higher.
        self.assertLess(pair['score'], (below['score'] + above['score']) / 2)

    def test_k_1_clean_case_with_a_partial_observation_score_passes(self):
        partial = self.probe['partialClean']
        self.assertEqual(partial['clean'], [0.5, 0.5, 1])
        # C (k 1) passes; D (k 0.25) loses 0.25 x (1 - 0.5).
        self.assertEqual(partial['kFailedCleanWeight'], 0.125)

    def test_unregistered_or_mismatched_answer_keys_are_rejected(self):
        expected = self.arw / 'tests/fixtures/reviewer-capability/code-spec-reviewer/expected.json'
        digest_ = digest(expected)
        fixture = json.loads(expected.read_text())
        index = len(fixture['scopes'][0]['cleanCases']) - 2
        overlay = {'reviewerId': 'code-spec-reviewer', 'expectedSha256': digest_, 'counts': {'problem': 1, 'clean': 1},
                   'cases': [{'scope': fixture['scopes'][0]['scope'], 'kind': kind, 'index': position,
                              'expectation': fixture['scopes'][0][kind + 'Cases'][position]['expectation']}
                             for kind, position in (('problem', 0), ('clean', index))]}
        registry = json.loads((freeze_arw_source.JUDGMENT / 'registry.json').read_text())
        cases = {
            'not registered': ({**registry, 'code-spec-reviewer': {}}, overlay),
            'does not match its fixture': (registry, {**overlay, 'cases': [{**overlay['cases'][0], 'index': 1}, overlay['cases'][1]]}),
            'correctly counted': (registry, {**overlay, 'counts': {'problem': 1, 'clean': 2}}),
            'dual adjudication': (registry, {**overlay, 'counts': {'problem': 1, 'clean': 1},
                                             'cases': [{**item, 'k': 4} for item in overlay['cases']]}),
        }
        for message, (table, content) in cases.items():
            with self.subTest(message), tempfile.TemporaryDirectory() as directory:
                table = json.loads(json.dumps(table))
                if table['code-spec-reviewer']:
                    table['code-spec-reviewer'][digest_] = {'version': 'probe', 'judgment': 'probe.json'}
                (Path(directory) / 'registry.json').write_text(json.dumps(table))
                (Path(directory) / 'probe.json').write_text(json.dumps(content))
                with mock.patch.object(freeze_arw_source, 'JUDGMENT', Path(directory)):
                    with self.assertRaisesRegex(ValueError, message):
                        upgrade_scoring(self.arw)
        # A bound overlay is reported by name and sha256.
        with tempfile.TemporaryDirectory() as directory:
            registry['code-spec-reviewer'][digest_] = {'version': 'probe', 'judgment': 'probe.json'}
            (Path(directory) / 'registry.json').write_text(json.dumps(registry))
            (Path(directory) / 'probe.json').write_text(json.dumps(overlay))
            with mock.patch.object(freeze_arw_source, 'JUDGMENT', Path(directory)):
                bound = upgrade_scoring(self.arw)['judgment']['code-spec-reviewer']
            self.assertEqual(bound['judgment'], 'probe.json')
            self.assertEqual(bound['overlaySha256'], digest(Path(directory) / 'probe.json'))
        upgrade_scoring(self.arw)

    def test_repeated_questions_in_an_answer_key_are_rejected(self):
        """The same expectation, or the same evidence not reviewed as distinct questions, stops the binding
        (user 2026-10-16/17); a legacy key or a listed shared-evidence group passes."""
        expected = self.arw / 'tests/fixtures/reviewer-capability/code-spec-reviewer/expected.json'
        original = expected.read_bytes()
        registry = json.loads((freeze_arw_source.JUDGMENT / 'registry.json').read_text())
        repeats = json.loads(freeze_arw_source.REPEATS.read_text())
        try:
            fixture = json.loads(original)
            scope = fixture['scopes'][0]
            name = scope['scope'] + '/clean/'
            same_expectation = json.loads(original)
            same_expectation['scopes'][0]['cleanCases'][1]['expectation'] = scope['cleanCases'][0]['expectation']
            same_evidence = json.loads(original)
            same_evidence['scopes'][0]['cleanCases'][1]['evidence'] = scope['cleanCases'][0]['evidence']
            same_evidence['scopes'][0]['cleanCases'][1].pop('evidenceAlternatives', None)
            reviewed = {'sharedEvidence': [{'cases': [name + '0', name + '1'], 'reason': 'probe'}]}
            for content, allowed, message in ((same_expectation, {}, r'repeats a question \(expectation\)'),
                                              (same_expectation, reviewed, r'repeats a question \(expectation\)'),
                                              (same_expectation, {'legacy': True}, None),
                                              (same_evidence, {}, r'repeats a question \(evidence\)'),
                                              (same_evidence, reviewed, None)):
                with self.subTest(allowed=allowed, message=message), tempfile.TemporaryDirectory() as directory:
                    expected.write_text(json.dumps(content))
                    table = json.loads(json.dumps(registry))
                    table['code-spec-reviewer'][digest(expected)] = {'version': 'probe', 'judgment': 'all-B'}
                    (Path(directory) / 'registry.json').write_text(json.dumps(table))
                    listed = json.loads(json.dumps(repeats))
                    listed.setdefault('code-spec-reviewer', {})[digest(expected)] = allowed
                    (Path(directory) / 'repeats.json').write_text(json.dumps(listed))
                    with mock.patch.object(freeze_arw_source, 'JUDGMENT', Path(directory)), \
                            mock.patch.object(freeze_arw_source, 'REPEATS', Path(directory) / 'repeats.json'):
                        if message:
                            with self.assertRaisesRegex(ValueError, message):
                                upgrade_scoring(self.arw)
                        else:
                            upgrade_scoring(self.arw)
        finally:
            expected.write_bytes(original)
            upgrade_scoring(self.arw)

    def test_judgment_marks_in_the_answer_key_need_in_key_registration(self):
        expected = self.arw / 'tests/fixtures/reviewer-capability/code-spec-reviewer/expected.json'
        original = expected.read_bytes()
        registry = json.loads((freeze_arw_source.JUDGMENT / 'registry.json').read_text())
        try:
            # A two-part judgment mark counts as k 1; k 4 is refused, balanced or not, until dual adjudication exists.
            for marks, judgment, message, mark in (((1, 1), 'all-B', 'registered as all-B', {'judgment': True}),
                                                   ((1, 0), 'in-key', 'per clean case', {'judgment': True}),
                                                   ((0, 0), 'in-key', 'per clean case', {'judgment': True}),
                                                   ((1, 1), 'in-key', None, {'judgment': True}),
                                                   ((1, 1), 'in-key', 'dual adjudication', {'k': 4}),
                                                   ((4, 1), 'in-key', 'dual adjudication', {'k': 4})):
                with self.subTest(marks=marks, judgment=judgment, mark=mark), tempfile.TemporaryDirectory() as directory:
                    marked = json.loads(original)
                    for kind, count in zip(('problem', 'clean'), marks):
                        for case in marked['scopes'][0][kind + 'Cases'][:count]:
                            case.update(mark)
                    expected.write_text(json.dumps(marked))
                    table = json.loads(json.dumps(registry))
                    table['code-spec-reviewer'][digest(expected)] = {'version': 'probe', 'judgment': judgment}
                    (Path(directory) / 'registry.json').write_text(json.dumps(table))
                    with mock.patch.object(freeze_arw_source, 'JUDGMENT', Path(directory)):
                        if message:
                            with self.assertRaisesRegex(ValueError, message):
                                upgrade_scoring(self.arw)
                        else:
                            self.assertEqual(upgrade_scoring(self.arw)['judgment']['code-spec-reviewer'],
                                             {'judgment': 'in-key', 'expectedSha256': digest(expected)})
        finally:
            expected.write_bytes(original)
            upgrade_scoring(self.arw)

    def test_r7_false_cleans_are_adjudicated(self):
        probe = self.probe
        # Undecided, the finding is charged once (R3b): only the nominated clean case fails, no-other passes.
        self.assertEqual(probe['falseClean']['findingCandidates'], [['unsupported', 'supported', 'false-positive:clean-1', 'problem-1', 'problem-2']])
        self.assertEqual(probe['falseClean']['clean'], [0, 1, 1])
        # A confirmed false clean takes that clean case's slot only.
        self.assertEqual(probe['falseCleanConfirmed']['clean'], [0, 1, 1])
        # Rejected: the clean case passes, the unsupported finding fails no-other only.
        self.assertEqual(probe['falseCleanRejected']['clean'], [1, 1, 0])
        self.assertEqual(probe['falseCleanRejected']['extraFailedCleanCases'], 0)
        self.assertEqual(probe['supported']['clean'], [1, 1, 1])
        # Each further unsupported finding, or further false flag of one clean case, adds a failed clean case at k 0.25.
        for name in ('twoUnsupported', 'twoFalseCleans'):
            with self.subTest(name):
                self.assertEqual(probe[name]['extraFailedCleanCases'], 1)
        self.assertEqual(probe['twoUnsupported']['kFailedCleanWeight'], 0.5)
        self.assertEqual(probe['twoFalseCleans']['kFailedCleanWeight'], 1.25)
        self.assertEqual(probe['twoUnsupported']['clean'], [1, 1, 0])
        self.assertEqual(probe['twoFalseCleans']['clean'], [0, 1, 1])

    def test_r7_ranges_past_the_end_of_a_file_are_cut_and_counted(self):
        overrun, cut = self.probe['overrun'], self.probe['cut']
        self.assertEqual(overrun['overrunLocators'], 1)
        self.assertEqual(cut['overrunLocators'], 0)
        # The cut range scores as the range written to the last line.
        self.assertEqual(overrun['problem'], cut['problem'])
        self.assertGreater(cut['problem'][0], 0)
        self.assertEqual(overrun['locatorCount'], cut['locatorCount'])
        # A line past the end, or a range starting past it, is not cut: invalid evidence, lost inside its case only.
        for name in ('overrunLine', 'pastEnd'):
            with self.subTest(name):
                self.assertEqual(self.probe[name]['overrunLocators'], 0)
                self.assertLess(self.probe[name]['problem'][0], cut['problem'][0])
                self.assertEqual(self.probe[name]['clean'], cut['clean'])

    def test_r7_reported_failed_clean_cases_add_failed_clean_cases(self):
        reported, cut = self.probe['reportedFailedClean'], self.probe['cut']
        self.assertEqual(reported['extraFailedCleanCases'], cut['extraFailedCleanCases'] + 1)
        self.assertEqual(reported['kFailedCleanWeight'], cut['kFailedCleanWeight'] + 0.25)
        self.assertLess(reported['score'], cut['score'])

    def test_r7_report_errors_are_charged_where_they_belong(self):
        treatment = self.probe['treatment']
        format_errors = {'review-format-invalid', 'review-json-invalid', 'review-utf8-invalid', 'review-row-unattributed'}
        # Only codes the policy does not know keep the ARW 0.9 cut; continuing past the stop is one wrong answer.
        cut = {'some-new-code'}
        for code, item in treatment.items():
            with self.subTest(code):
                self.assertEqual(item['cut'], code in cut)
                self.assertEqual(item['unrepairable'], int(code in format_errors))

    def test_r7_content_past_the_requirement_scope_stop_is_ignored(self):
        continuation = self.probe['continuation']
        # The later check and the diagnostics of its lines are dropped; a line that cannot be read stays a format error.
        self.assertEqual(continuation['checks'], ['SPEC-READINESS-REQUIREMENTS'])
        self.assertEqual(continuation['diagnostics'], [['requirement-scope-continuation', None], ['review-format-invalid', 3]])
        self.assertEqual(continuation['unrepairable'], 1)
        ignored, unfiltered, stopped = continuation['ignored'], continuation['unfiltered'], continuation['stopped']
        # Ignored content earns nothing and is no locator or candidate (unfiltered, its locators would count in T).
        self.assertEqual(ignored['problem'], stopped['problem'])
        self.assertEqual(ignored['locatorCount'], stopped['locatorCount'])
        self.assertGreater(unfiltered['locatorCount'], stopped['locatorCount'])
        self.assertEqual(ignored['candidates'], stopped['candidates'])
        # ... and loses nothing: the clean cases are those of a report that stopped, plus the one failed clean case
        # (k 0.25) of the stop rule; no-other and the other clean cases pass.
        self.assertEqual(ignored['clean'], stopped['clean'])
        self.assertEqual(ignored['extraFailedCleanCases'], stopped['extraFailedCleanCases'] + 1)
        self.assertEqual(ignored['kFailedCleanWeight'], stopped['kFailedCleanWeight'] + 0.25)

    def test_r7_adjudication_adds_associations_and_checks_decisions(self):
        added = self.probe['addedAssociation']
        self.assertGreater(added['problem'][0], 0)
        self.assertEqual(added['kEarnedProblemPoints'], 1 + added['problem'][1])
        validation = self.probe['validation']
        self.assertEqual(validation['pending'], ['f'])
        self.assertTrue(validation['notAllowed'])
        self.assertTrue(validation['unknown'])
        self.assertEqual(validation['complete'], 0)

    def test_r7_terms_are_phrases_and_clock_times_are_not_locators(self):
        self.assertEqual(self.probe['scatteredTerms']['findingCandidates'], [['unsupported', 'supported', 'problem-1', 'problem-2']])
        parsed = self.probe['timestamps']
        self.assertEqual(parsed['checks'][0]['findings'][0]['evidence'], [{'filePath': 'src/a.mjs', 'line': 3}, {'filePath': 'src/a.mjs', 'line': 5}])
        self.assertEqual(parsed['reportDiagnostics'], [])
        self.assertEqual(self.probe['hit']['locatorCount'], 5)


if __name__ == '__main__':
    unittest.main()
