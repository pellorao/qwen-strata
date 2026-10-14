"""The project's ARW scoring upgrade: evidence F2 and paired problem/clean cases (user 2026-10-14)."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from tools.reviewer import freeze_arw_source
from tools.reviewer.freeze_arw_source import materialize, upgrade_scoring

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = ROOT / 'benchmarks/reviewer-suite-v1/source-snapshots/current'

# One scope, two problem cases (P1 paired with clean C1, P2 unpaired), cleans C1, C2 and the fixed no-other case.
SCORE = r'''
import {createReviewerCapabilityScenarioScorer} from './lib/release/reviewer-capability-scoring.mjs';
const [falseFinding, table, partialTwinEvidence] = JSON.parse(process.argv[1]);
const at = line => [{filePath: 'src/a.mjs', line}];
const problem = (expectation, line, extra = {}) => ({associationEvidence: at(line), evidence: at(line), expectation,
    findingTerms: [], result: 'gap', ...extra});
const expected = {problemCount: 2, cleanCount: 3, scopes: [{scope: 'code-spec', problemCases: [
    problem('P1 shape', 2, table ? {} : {pairedCleanCases: [{scope: 'code-spec', cleanCaseIndex: 0}]}),
    problem('P2 other', 3)],
    cleanCases: [{evidence: at(5), expectation: 'C1 compliant twin', findingTerms: ['twin']},
        {evidence: at(4), expectation: 'C2 unrelated', findingTerms: []}, {noOtherSupportedFinding: true}]}]};
const finding = (line, text) => ({evidence: at(line), finding: text, result: 'gap'});
const findings = [finding(2, 'P1 shape found'), finding(3, 'P2 other found')];
if (falseFinding) findings.push(finding(5, 'twin violates the rule'));
const score = createReviewerCapabilityScenarioScorer({evidenceSources: new Map([['src/a.mjs', 'a\nb\nc\nd\ne\n']]),
    expected, instanceId: 'i1', reviewerId: 'code-spec-reviewer', scenarioRoot: process.cwd()});
const decisions = new Map([1, 2].map(n => [`code-spec-reviewer:i1:scope-1:problem-${n}:code-spec:finding-${n}`, 'matched']));
// A partial clean evidence observation lowers the twin's clean score without any false finding.
const cleanObservationScores = new Map(partialTwinEvidence ? [['code-spec', new Map([[0, 0.5]])]] : []);
const result = score({adjudicationDecisions: decisions, checks: [{check: 'code-spec', result: 'gap', findings}], cleanObservationScores});
console.log(JSON.stringify({problem: result.caseScores.problem, clean: result.caseScores.clean[0], score: result.score,
    unpairedScore: result.unpairedScore, pairing: result.pairing, pairTables: result.pairTables}));
'''


class ScoringUpgradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.arw = Path(cls.tmp.name) / 'arw'
        manifest = json.loads((SNAPSHOTS / 'manifest-code-spec-v5.json').read_text())
        materialize(manifest, SNAPSHOTS / manifest['snapshot']['file'], cls.arw)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def score(self, false_finding, table=None, partial_twin_evidence=False):
        pairs = self.arw / 'reviewer-pairs'
        if table:
            pairs.mkdir(exist_ok=True)
            (pairs / 'probe.json').write_text(json.dumps(table))
        try:
            reply = subprocess.run(['node', '--input-type=module', '-e', SCORE, json.dumps([false_finding, bool(table), partial_twin_evidence])],
                                   cwd=self.arw, capture_output=True, text=True, check=True)
        finally:
            (pairs / 'probe.json').unlink(missing_ok=True)
        return json.loads(reply.stdout)

    def test_materialized_copy_scores_evidence_with_f2(self):
        source = (self.arw / 'lib/release/reviewer-capability-scoring.mjs').read_text()
        self.assertIn('fBetaScore({beta: 2, precision, recall: coverage})', source)
        self.assertNotIn('beta: 3', source)
        self.assertEqual(upgrade_scoring(self.arw)['applied'], False)

    def test_failed_twin_voids_only_its_paired_problem(self):
        clean = self.score(False)
        self.assertEqual(clean['problem'], [1, 1])
        failed = self.score(True)
        self.assertEqual(failed['clean'], [0, 1, 0])  # the twin and the no-other case fail
        self.assertEqual(failed['problem'], [0, 1])
        self.assertEqual(failed['pairing'][0]['unpairedScore'], 1)
        self.assertLess(failed['score'], failed['unpairedScore'])

    def test_partial_twin_evidence_without_false_finding_keeps_the_problem(self):
        result = self.score(False, partial_twin_evidence=True)
        self.assertEqual(result['clean'][0], 0.5)
        self.assertEqual(result['problem'], [1, 1])
        self.assertTrue(result['pairing'][0]['twinsPass'])

    @staticmethod
    def pair(problem, problem_index=0, clean_index=0, clean='C1 compliant twin', scope='code-spec'):
        return {'problem': {'scope': scope, 'index': problem_index, 'expectation': problem},
                'clean': [{'scope': scope, 'index': clean_index, 'expectation': clean}]}

    def test_pair_table_pairs_a_frozen_fixture(self):
        table = {'reviewerId': 'code-spec-reviewer', 'pairs': [self.pair('P1 shape')]}
        result = self.score(True, table)
        self.assertEqual(result['problem'], [0, 1])
        self.assertIn('probe.json', result['pairTables'])

    def test_pair_table_mismatches_are_errors(self):
        for pairs in ([self.pair('P1 shape', clean='renamed')],         # clean expectation differs
                      [self.pair('P1 renamed')],                         # problem expectation differs
                      [self.pair('P1 shape'), self.pair('P2 other', 1)]):  # one clean twin for two problems
            with self.subTest(pairs=pairs), self.assertRaises(subprocess.CalledProcessError):
                self.score(True, {'reviewerId': 'code-spec-reviewer', 'pairs': pairs})

    def test_pair_outside_the_scored_subset_is_skipped(self):
        # Spec Readiness scores its sub-scenarios apart; a pair in a scope this subset lacks is not an error.
        table = {'reviewerId': 'code-spec-reviewer', 'pairs': [self.pair('P1 shape', scope='other-scope')]}
        result = self.score(True, table)
        self.assertEqual(result['problem'], [1, 1])
        self.assertEqual(result['pairing'], [])

    def test_binding_checks_every_pair_against_the_answer_key(self):
        expected = self.arw / 'tests/fixtures/reviewer-capability/code-spec-reviewer/expected.json'
        key = json.loads(expected.read_text())
        scope = key['scopes'][0]
        problem = {'scope': scope['scope'], 'index': 0, 'expectation': scope['problemCases'][0]['expectation']}
        clean = {'scope': scope['scope'], 'index': 0, 'expectation': scope['cleanCases'][0]['expectation']}
        second = {'scope': scope['scope'], 'index': 1, 'expectation': scope['problemCases'][1]['expectation']}
        cases = {'valid': [{'problem': problem, 'clean': [clean]}],
                 'problem mismatch': [{'problem': {**problem, 'expectation': 'renamed'}, 'clean': [clean]}],
                 'clean mismatch': [{'problem': problem, 'clean': [{**clean, 'index': 1}]}],
                 'shared clean': [{'problem': problem, 'clean': [clean]}, {'problem': second, 'clean': [clean]}]}
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(freeze_arw_source, 'PAIRS', Path(directory)):
            for name, pairs in cases.items():
                (Path(directory) / 'probe.json').write_text(json.dumps({
                    'scenario': 'probe', 'reviewerId': 'code-spec-reviewer', 'pairs': pairs,
                    'expectedSha256': hashlib.sha256(expected.read_bytes()).hexdigest()}))
                with self.subTest(name):
                    if name == 'valid':
                        self.assertEqual(upgrade_scoring(self.arw)['pair_tables'], ['probe.json'])
                        before = (self.arw / 'reviewer-pairs/probe.json').stat().st_mtime_ns
                        upgrade_scoring(self.arw)  # an unchanged table is not rewritten
                        self.assertEqual((self.arw / 'reviewer-pairs/probe.json').stat().st_mtime_ns, before)
                    else:
                        with self.assertRaises(ValueError):
                            upgrade_scoring(self.arw)
            (Path(directory) / 'probe.json').unlink()
            upgrade_scoring(self.arw)

    def test_pair_tables_bind_only_to_their_expected_bytes(self):
        expected = self.arw / 'tests/fixtures/reviewer-capability/code-spec-reviewer/expected.json'
        with tempfile.TemporaryDirectory() as directory:
            pairs = Path(directory)
            for name, digest in [('bound.json', hashlib.sha256(expected.read_bytes()).hexdigest()), ('other.json', '0' * 64)]:
                (pairs / name).write_text(json.dumps({'reviewerId': 'code-spec-reviewer', 'expectedSha256': digest, 'pairs': []}))
            with mock.patch.object(freeze_arw_source, 'PAIRS', pairs):
                self.assertEqual(upgrade_scoring(self.arw)['pair_tables'], ['bound.json'])
                for name in ('bound.json', 'other.json'):
                    (pairs / name).unlink()
                self.assertEqual(upgrade_scoring(self.arw)['pair_tables'], [])  # a stale copy is removed
            self.assertFalse((self.arw / 'reviewer-pairs').exists())

    def test_project_pair_tables_bind_to_their_frozen_fixtures(self):
        for table in sorted((ROOT / 'benchmarks/reviewer-suite-v1/pairs').glob('*.json')):
            data = json.loads(table.read_text())
            expected = self.arw / 'tests/fixtures/reviewer-capability' / data['reviewerId'] / 'expected.json'
            self.assertEqual(hashlib.sha256(expected.read_bytes()).hexdigest(), data['expectedSha256'], table.name)

    def test_answer_key_accepts_paired_clean_case_indexes(self):
        probe = self.arw / 'lib/release/probe-conformance.mjs'
        probe.write_text((self.arw / 'lib/release/reviewer-capability-conformance.mjs').read_text()
                         + '\nexport {canonicalExpectedFixture};\n')
        script = ("import {canonicalExpectedFixture} from './lib/release/probe-conformance.mjs';"
                  "const at=[{filePath:'a.mjs',line:1}];"
                  "const p=(e,x={})=>({associationEvidence:at,evidence:at,expectation:e,findingTerms:[['x']],result:'gap',...x});"
                  "const c=e=>({evidence:at,expectation:e,findingTerms:[['x']]});"
                  "const n=k=>Array.from({length:20},(_,i)=>k+(i+2));"  # ARW needs 20 cases of each kind
                  "const fixture=(paired,second)=>JSON.stringify({scopes:[{scope:'s',problemCases:[p('P1',{pairedCleanCases:paired}),"
                  "...(second?[p('P0',{pairedCleanCases:second})]:[]),...n('P').map(e=>p(e))],"
                  "cleanCases:[c('C1'),c('C2'),{noOtherSupportedFinding:true},...n('C').map(c)]}]});"
                  "const read=(paired,second)=>{try{return canonicalExpectedFixture({availablePaths:new Set(['a.mjs']),source:fixture(paired,second)})"
                  ".scopes[0].problemCases[0].pairedCleanCases}catch(e){return 'rejected: '+e.message}};"
                  "console.log(JSON.stringify([read([1]),read([2]),read([]),read([0,0]),read([0],[0])]));")
        try:
            reply = subprocess.run(['node', '--input-type=module', '-e', script], cwd=self.arw,
                                   capture_output=True, text=True, check=True)
        finally:
            probe.unlink()
        accepted, *others = json.loads(reply.stdout)
        self.assertEqual(accepted, [{'cleanCaseIndex': 1, 'scope': 's'}])
        # pairing with the no-other case, an empty list, a repeated index and a clean shared by two problems are rejected
        self.assertEqual([str(o).startswith('rejected') for o in others], [True, True, True, True])


if __name__ == '__main__':
    unittest.main()
