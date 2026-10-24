"""Scoring r8.5 (multi-model benchmark v2 only, user 2026-10-24): the clean cases of a check missing from a report are
neutral (neither pass nor fail, still in the clean weight), problem cases of that check still count as missed, and each
result counts its missing checks. r8.4 copies (every v1 result) keep their code path and scores."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.reviewer import freeze_arw_source
from tools.reviewer.freeze_arw_source import SCORING_OVERLAY, SCORING_UPGRADE, materialize, upgrade_scoring

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = ROOT / 'benchmarks/reviewer-suite-v1/source-snapshots/current'

# Two scopes A and B, each with one problem case (k 0.25), one clean case and no-other.
PROBE = r'''
import {resolve} from 'node:path';
const arw = process.argv[1];
const {createReviewerCapabilityScenarioScorer} = await import(resolve(arw, 'lib/release/reviewer-capability-scoring.mjs'));
const {reviewerCapabilityVerificationCore: core} = await import(resolve(arw, 'lib/release/reviewer-capability-verification.mjs'));
const filePath = 'specs/rules.md';
const evidenceSources = new Map([[filePath, ['Alpha rule.', 'Beta part.', 'Gamma rule.', 'Delta part.'].join('\n')]]);
const lines = (...numbers) => numbers.map(line => ({filePath, line}));
const problem = (scope, expectation, terms, line) => ({associationEvidence: lines(line), evidence: lines(line), expectation,
    findingTerms: terms, placements: [{associationEvidence: lines(line), check: scope, evidence: lines(line)}], result: 'gap'});
const clean = (expectation, terms, line, extra = {}) => ({evidence: lines(line), expectation, findingTerms: terms, ...extra});
const scorerFor = (merge = false) => createReviewerCapabilityScenarioScorer({evidenceSources, instanceId: 'probe',
    expected: {cleanCount: 4, kind: 'spec-readiness-artifact', problemCount: 2, scopes: [
        {scope: 'A', problemCases: [problem('A', 'The alpha rule is violated.', ['alpha rule'], 1)],
            cleanCases: [clean('The beta part is correct.', ['beta part'], 2, merge ? {merge: 'm'} : {}), {noOtherSupportedFinding: true}]},
        {scope: 'B', problemCases: [problem('B', 'The gamma rule is violated.', ['gamma rule'], 3)],
            cleanCases: [clean(merge ? 'The beta part is correct.' : 'The delta part is correct.', merge ? ['beta part'] : ['delta part'],
                merge ? 2 : 4, merge ? {merge: 'm'} : {}), {noOtherSupportedFinding: true}]}]},
    reviewerId: 'spec-readiness-reviewer', scenarioRoot: resolve('/probe')});
const run = (scorer, checks) => {
    // As ARW scores Spec Readiness: every clean case of a missing check gets observation score 0.
    const present = new Set(checks.map(check => check.check));
    const cleanObservationScores = new Map(['A', 'B'].filter(scope => !present.has(scope)).map(scope => [scope, new Map([[0, 0], [1, 0]])]));
    const provisional = scorer({checks, cleanObservationScores});
    const adjudicationDecisions = new Map(provisional.candidates.filter(candidate => candidate.kind === 'association')
        .map(candidate => [candidate.candidateId, 'matched']));
    return scorer({adjudicationDecisions, checks, cleanObservationScores});
};
const alpha = {check: 'A', findings: [{evidence: lines(1), finding: 'The alpha rule is violated.', result: 'gap'}], result: 'gap'};
const pick = result => Object.fromEntries(['kProblemWeight', 'kEarnedProblemPoints', 'kFailedCleanWeight', 'kCleanWeight', 'score',
    'missingChecks', 'neutralCleanCases'].map(key => [key, result[key] ?? null]));
const onlyA = run(scorerFor(), [alpha]);
const none = run(scorerFor(), []);
const both = run(scorerFor(), [alpha, {check: 'B', findings: [], result: 'pass'}]);
let mergeError = null;
try { run(scorerFor(true), [alpha]); } catch (error) { mergeError = error.message; }
console.log(JSON.stringify({onlyA: pick(onlyA), none: pick(none), both: pick(both), pair: pick(core.combineScenarios([onlyA, none])),
    mergeError, mergeBothPresent: pick(run(scorerFor(true), [alpha, {check: 'B', findings: [], result: 'pass'}]))}));
'''


def probe(arw):
    return json.loads(subprocess.run(['node', '--input-type=module', '-e', PROBE, str(arw)],
                                     check=True, capture_output=True, text=True).stdout)


class ScoringR85Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        manifest = json.loads((SNAPSHOTS / 'manifest-spec-readiness-v4.3.json').read_text())
        archive = SNAPSHOTS / manifest['snapshot']['file']
        cls.r84, cls.r85 = Path(cls.tmp.name) / 'r84', Path(cls.tmp.name) / 'r85'
        cls.default = materialize(manifest, archive, cls.r84)
        cls.selected = materialize(manifest, archive, cls.r85, scoring='r8.5')
        cls.old, cls.new = probe(cls.r84), probe(cls.r85)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_a_new_copy_defaults_to_r8_4_and_r8_5_is_opt_in(self):
        self.assertEqual(self.default['scoring_version'], 'r8.4')
        self.assertEqual(self.selected['scoring_version'], 'r8.5')
        for member, (_, upgraded) in SCORING_UPGRADE['members'].items():
            self.assertEqual(freeze_arw_source.sha((self.r84 / member).read_bytes()), upgraded, member)
        for member, (_, overlaid) in SCORING_OVERLAY['members'].items():
            self.assertEqual(freeze_arw_source.sha((self.r85 / member).read_bytes()), overlaid, member)

    def test_upgrading_again_keeps_the_version_and_never_goes_back(self):
        self.assertEqual(upgrade_scoring(self.r84)['scoring_version'], 'r8.4')
        again = upgrade_scoring(self.r85)
        self.assertEqual((again['scoring_version'], again['applied']), ('r8.5', False))
        self.assertEqual(upgrade_scoring(self.r85, 'r8.5')['applied'], False)
        with self.assertRaisesRegex(ValueError, 're-materialize it for r8.4'):
            upgrade_scoring(self.r85, 'r8.4')
        with self.assertRaisesRegex(ValueError, 'Unknown scoring version'):
            upgrade_scoring(self.r85, 'r9')

    def test_an_r8_5_copy_with_a_changed_conformance_module_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest = json.loads((SNAPSHOTS / 'manifest-code-spec-v5.json').read_text())
            copy = Path(folder) / 'arw'
            materialize(manifest, SNAPSHOTS / manifest['snapshot']['file'], copy, scoring='r8.5')
            conformance = copy / SCORING_UPGRADE['patched_member']
            conformance.write_text(conformance.read_text().replace('kMergedCases: cases.length - units.length',
                                                                   'kMergedCases: 0'))
            with self.assertRaisesRegex(ValueError, 'r8.5 copy is incomplete'):
                upgrade_scoring(copy)

    def test_r8_4_clean_cases_of_a_missing_check_fail(self):
        # B is missing: its clean case and no-other fail at 0.25 each; N = 1 - 0.5 over P = 2.
        self.assertEqual(self.old['onlyA']['kFailedCleanWeight'], 0.5)
        self.assertEqual(self.old['onlyA']['score'], 0.25)
        self.assertIsNone(self.old['onlyA']['missingChecks'])
        # No check at all: every clean case fails, -1, below reporting nothing.
        self.assertEqual(self.old['none']['score'], -1)

    def test_r8_5_clean_cases_of_a_missing_check_are_neutral(self):
        only_a = self.new['onlyA']
        # The missing check's problem case is still missed (P = 2); its clean cases cost nothing but stay in the clean weight.
        self.assertEqual((only_a['kProblemWeight'], only_a['kEarnedProblemPoints']), (2, 1))
        self.assertEqual((only_a['kFailedCleanWeight'], only_a['kCleanWeight']), (0, 1))
        self.assertEqual(only_a['score'], 0.5)
        self.assertEqual((only_a['missingChecks'], only_a['neutralCleanCases']), (1, 2))
        # A report without any check scores as reporting nothing.
        self.assertEqual((self.new['none']['score'], self.new['none']['missingChecks'], self.new['none']['neutralCleanCases']), (0, 2, 4))
        # Every check present: the same score as r8.4.
        self.assertEqual(self.new['both'], {**self.old['both'], 'missingChecks': 0, 'neutralCleanCases': 0})

    def test_r8_5_spec_readiness_pair_adds_missing_checks(self):
        self.assertEqual((self.new['pair']['missingChecks'], self.new['pair']['neutralCleanCases']), (3, 6))
        self.assertEqual(self.new['pair']['kCleanWeight'], 2)

    def test_r8_5_merged_case_with_one_side_in_a_missing_check_is_an_error(self):
        self.assertIn('undefined under r8.5', self.new['mergeError'])
        self.assertIsNone(self.old['mergeError'])
        self.assertEqual(self.new['mergeBothPresent']['missingChecks'], 0)


if __name__ == '__main__':
    unittest.main()
