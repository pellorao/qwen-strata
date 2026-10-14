"""The project's ARW scoring upgrade: evidence F2 instead of F3 (user 2026-10-14) and the
two-part score of judgment cases and other cases (user 2026-10-15)."""
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

# Synthetic Spec Readiness cases: P judgment problem, Q ordinary problem, C judgment clean, D ordinary clean.
TWO_PART_PROBE = r'''
import {resolve} from 'node:path';
const arw = process.argv[1];
const {createReviewerCapabilityScenarioScorer} = await import(resolve(arw, 'lib/release/reviewer-capability-scoring.mjs'));
const {reviewerCapabilityVerificationCore: core} = await import(resolve(arw, 'lib/release/reviewer-capability-verification.mjs'));
const filePath = 'specs/rules.md';
const scope = 'SPEC-READINESS-REQUIREMENTS';
const evidenceSources = new Map([[filePath, ['Alpha.', 'Beta.', 'Gamma.', 'Delta.', 'Clean target.', 'Other clean.', 'Problem two.',
    'Third clean.', 'Problem three.'].join('\n')]]);
const lines = (...numbers) => numbers.map(line => ({filePath, line}));
const problem = (expectation, terms, evidence, association, judgment) => ({associationEvidence: lines(...association),
    evidence: lines(...evidence), expectation, findingTerms: terms, ...(judgment ? {judgment: true} : {}),
    placements: [{associationEvidence: lines(...association), check: scope, evidence: lines(...evidence)}], result: 'gap'});
const clean = (expectation, terms, evidence, extra = {}) => ({evidence: lines(...evidence), expectation, findingTerms: terms, ...extra});
const P = problem('The alpha rule is violated.', ['alpha rule'], [1, 2, 3, 4], [1], true);
const Q = problem('The second problem is present.', ['second problem'], [7], [7], false);
const R = problem('The third problem is present.', ['third problem'], [9], [9], true);
const C = clean('The clean target is correct.', ['clean target'], [5], {judgment: true});
const D = clean('The other clean part is correct.', ['other clean'], [6]);
const E = clean('The third clean part is correct.', ['third clean'], [8], {judgment: true});
const scorerFor = (problemCases, cleanCases) => createReviewerCapabilityScenarioScorer({evidenceSources, instanceId: 'probe',
    expected: {cleanCount: cleanCases.length + 1, kind: 'spec-readiness-artifact', problemCount: problemCases.length,
        scopes: [{scope, problemCases, cleanCases: [...cleanCases, {noOtherSupportedFinding: true}]}]},
    reviewerId: 'spec-readiness-reviewer', scenarioRoot: resolve('/probe')});
const run = (scorer, findings, present = true) => {
    const checks = present ? [{check: scope, findings, result: findings.length ? 'gap' : 'pass'}] : [];
    // As ARW scores Spec Readiness: every clean case of a missing check gets observation score 0.
    const cleanObservationScores = present ? new Map() : new Map([[scope, new Map([0, 1, 2].map(index => [index, 0]))]]);
    const provisional = scorer({checks, cleanObservationScores});
    return scorer({adjudicationDecisions: new Map(provisional.candidates.map(candidate => [candidate.candidateId, 'matched'])), checks,
        cleanObservationScores});
};
const pick = result => ({...Object.fromEntries(['judgmentCases', 'judgmentPoints', 'judgmentScore', 'judgmentWeight', 'bScore', 'rawScore',
    'score', 'judgmentWarning'].map(key => [key, result[key]])), problem: result.caseScores.problem});
const single = scorerFor([P, Q], [C, D]);
const finding = (text, ...evidence) => ({evidence: lines(...evidence), finding: text, result: 'gap'});
// Spec Readiness pair: C is scored in both scenarios at half share, R and E only in the second.
const half = {...C, judgmentShare: 0.5};
const first = run(scorerFor([P, Q], [half, D]), []);
const second = run(scorerFor([R, Q], [half, D, E]), []);
let unequal, partial;
try { core.combineScenarios([first]); } catch (error) { unequal = error.message; }
// A result without two-part counts, such as ARW's own synthetic test data, counts as all B.
const plain = run(scorerFor([Q], [D]), [finding('The second problem is present.', 7)]);
const countKeys = ['bCleanCases', 'bEarnedCleanPoints', 'bEarnedProblemPoints', 'bProblemCases', 'judgmentCases',
    'judgmentCleanCases', 'judgmentPoints', 'judgmentProblemCases', 'noOtherCases'];
const stripped = Object.fromEntries(Object.entries(plain).filter(([key]) => !countKeys.includes(key)));
try { core.combineScenarios([{...stripped, judgmentCases: 0}]); } catch (error) { partial = error.message; }
const counts = {bCleanCases: 9, bEarnedCleanPoints: 9, bEarnedProblemPoints: 4, bProblemCases: 8, judgmentCases: 4,
    judgmentCleanCases: 2, judgmentPoints: 2, judgmentProblemCases: 2, noOtherCases: 1, totalCleanCases: 11, totalProblemCases: 10};
console.log(JSON.stringify({
    silent: pick(run(single, [])),
    hit: pick(run(single, [finding('The alpha rule is violated.', 1, 2, 3, 4), finding('The second problem is present.', 7)])),
    weakHit: pick(run(single, [finding('The alpha rule is violated.', 1), finding('The second problem is present.', 7)])),
    falseClean: pick(run(single, [finding('The clean target is wrong.', 5)])),
    missingCheck: pick(run(single, [], false)),
    pairFirst: pick(first),
    pair: pick(core.combineScenarios([first, second])),
    unequal,
    withoutCounts: pick(core.combineScenarios([stripped, stripped])),
    plain: pick(core.combineScenarios([plain, plain])),
    partial,
    belowCap: core.twoPartScore(counts),
    noJudgment: core.twoPartScore({...counts, bCleanCases: 11, bEarnedCleanPoints: 11, bEarnedProblemPoints: 5, bProblemCases: 10,
        judgmentCases: 0, judgmentCleanCases: 0, judgmentPoints: 0, judgmentProblemCases: 0}),
}));
'''


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def f2(clean, problem):
    return 5 * problem * clean / (4 * clean + problem)


class ScoringUpgradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.arw = Path(cls.tmp.name) / 'arw'
        manifest = json.loads((SNAPSHOTS / 'manifest-code-spec-v5.json').read_text())
        materialize(manifest, SNAPSHOTS / manifest['snapshot']['file'], cls.arw)
        cls.probe = json.loads(subprocess.run(['node', '--input-type=module', '-e', TWO_PART_PROBE, str(cls.arw)],
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

    def test_judgment_cases_score_plus_or_minus_one(self):
        # Reporting nothing: the missed problem is wrong, the clean case right.
        self.assertEqual(self.probe['silent']['judgmentScore'], 0)
        self.assertEqual(self.probe['hit']['judgmentScore'], 1)
        self.assertEqual(self.probe['hit']['score'], 1)
        # A hit whose evidence score is below 0.5 earns partial ordinary points but counts as wrong.
        self.assertGreater(self.probe['weakHit']['problem'][0], 0)
        self.assertEqual(self.probe['weakHit']['judgmentPoints'], 0)
        self.assertEqual(self.probe['falseClean']['judgmentScore'], -1)
        # A clean case of a missing check is wrong, as in a model failure.
        self.assertEqual(self.probe['missingCheck']['judgmentScore'], -1)

    def test_spec_readiness_pair_counts_a_shared_case_once(self):
        first, pair = self.probe['pairFirst'], self.probe['pair']
        self.assertEqual((first['judgmentCases'], first['judgmentPoints']), (1.5, -0.5))
        self.assertIn('unequal', first['judgmentWarning'])
        # P, R missed (-2); the shared clean case (+0.5 twice) and E (+1) right.
        self.assertEqual((pair['judgmentCases'], pair['judgmentPoints'], pair['judgmentScore']), (4, 0, 0))
        self.assertNotIn('judgmentWarning', pair)
        self.assertIn('unequal in one scoring unit', self.probe['unequal'])

    def test_results_without_two_part_counts_count_as_all_b(self):
        self.assertEqual(self.probe['withoutCounts'], self.probe['plain'])
        self.assertEqual(self.probe['withoutCounts']['judgmentWeight'], 0)
        self.assertIn('incomplete two-part counts', self.probe['partial'])

    def test_weight_is_capped_and_negative_totals_become_zero(self):
        self.assertEqual(self.probe['silent']['judgmentWeight'], 0.5)
        self.assertEqual(self.probe['falseClean']['rawScore'], -0.5)
        self.assertEqual(self.probe['falseClean']['score'], 0)
        below = self.probe['belowCap']
        self.assertAlmostEqual(below['judgmentWeight'], 4 / 20)
        self.assertAlmostEqual(below['score'], 0.2 * 0.5 + 0.8 * f2(1, 0.5))
        self.assertEqual(self.probe['noJudgment']['judgmentWeight'], 0)
        self.assertAlmostEqual(self.probe['noJudgment']['score'], f2(1, 0.5))

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
            'equal, correctly counted': (registry, {**overlay, 'counts': {'problem': 1, 'clean': 2}}),
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

    def test_judgment_marks_in_the_answer_key_need_in_key_registration(self):
        expected = self.arw / 'tests/fixtures/reviewer-capability/code-spec-reviewer/expected.json'
        original = expected.read_bytes()
        registry = json.loads((freeze_arw_source.JUDGMENT / 'registry.json').read_text())
        try:
            for marks, judgment, message in (((1, 1), 'all-B', 'registered as all-B'), ((1, 0), 'in-key', 'equal, nonzero'),
                                              ((0, 0), 'in-key', 'equal, nonzero'), ((1, 1), 'in-key', None)):
                with self.subTest(marks=marks, judgment=judgment), tempfile.TemporaryDirectory() as directory:
                    marked = json.loads(original)
                    for kind, count in zip(('problem', 'clean'), marks):
                        for case in marked['scopes'][0][kind + 'Cases'][:count]:
                            case['judgment'] = True
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

if __name__ == '__main__':
    unittest.main()
