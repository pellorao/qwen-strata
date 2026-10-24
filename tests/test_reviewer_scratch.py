import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.reviewer import inspect_session, reviewer_scratch
from tools.reviewer.freeze_arw_source import apply_harness_patch, materialize

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = ROOT / 'benchmarks/reviewer-suite-v1/source-snapshots/current'


class ReviewerScratchTest(unittest.TestCase):
    def setUp(self):
        (ROOT / '.tmp').mkdir(exist_ok=True)
        self.tmp = Path(tempfile.mkdtemp(dir=ROOT / '.tmp', prefix='reviewer-scratch-'))
        self.addCleanup(shutil.rmtree, self.tmp)
        self.root = self.tmp / 'root'
        self.root.mkdir(mode=0o700)

    @unittest.skipUnless(shutil.which('node'), 'node is needed to run the patched ARW module')
    def test_the_path_matches_the_patched_arw(self):
        manifest = json.loads((MANIFESTS / 'manifest-commit-audit-v3.json').read_text())
        arw = self.tmp / 'arw'
        materialize(manifest, MANIFESTS / manifest['snapshot']['file'], arw)
        apply_harness_patch('reviewer-private-scratch', arw)
        cwd, reports = '/x/scenario', '/x/scenario/.tmp/a/reports'
        module = (arw / 'lib/reviewer-runtime/reviewer-scratch.mjs').as_uri()
        script = (f'import {{reviewerScratchPath}} from {json.dumps(module)};'
                  f'console.log(reviewerScratchPath({{cwd:{json.dumps(cwd)},writePaths:[{json.dumps(reports)}]}},'
                  f'{json.dumps(str(self.root))}))')
        out = subprocess.run(['node', '--input-type=module', '-e', script], capture_output=True, text=True, check=True)
        self.assertEqual(out.stdout.strip(), str(reviewer_scratch.scratch_path(cwd, [reports], self.root)))

    @unittest.skipUnless(shutil.which('node'), 'node is needed to run the patched ARW module')
    def test_resume_reopens_a_reviewer_with_the_same_scratch_and_deny_read(self):
        # ARW's paused-task restore reopens with raw stored settings; reviewerResumeOpen must reapply reviewerNativeSettings
        # so the resumed Reviewer regains its profile, private scratch, TMPDIR (identical to segment 1) and deny-read.
        manifest = json.loads((MANIFESTS / 'manifest-commit-audit-v3.json').read_text())
        arw = self.tmp / 'arw'
        materialize(manifest, MANIFESTS / manifest['snapshot']['file'], arw)
        apply_harness_patch('reviewer-private-scratch', arw)
        policy = (arw / 'lib/reviewer-runtime/reviewer-native-policy.mjs').as_uri()
        setup = (ROOT / 'tools/reviewer/arw_native_setup.mjs').as_uri()
        script = f'''
import {{reviewerNativeSettings}} from {json.dumps(policy)};
import {{reviewerResumeOpen}} from {json.dumps(setup)};
const raw={{model:'qwen3.8-flash-next-iq3_xxs',modelProvider:'qwen_strata',reasoningEffort:'high',serviceTier:'default',config:{{}}}};
const paths={{cwd:'/review/csp/3',readPaths:[],writePaths:['/review/csp/3/.tmp/reports']}};
const deny=['/home/x/.codex'];
const seg1=reviewerNativeSettings(raw,paths);
const tmp1=seg1.config.shell_environment_policy.set.TMPDIR;
const opens=[];
const wrapped=reviewerResumeOpen(async i=>{{opens.push(i);}},reviewerNativeSettings,deny);
await wrapped({{settings:raw,...paths}});          // resume: raw settings, no profile
await wrapped({{settings:seg1,...paths}});          // normal open: already profiled
const r=opens[0].settings, key=`permissions.${{r.config.default_permissions}}.filesystem`;
const n=opens[1].settings;
console.log(JSON.stringify({{
  resume_profile: typeof r.config.default_permissions,
  tmp_match: r.config.shell_environment_policy.set.TMPDIR===tmp1,
  scratch_write: r.config[key][tmp1],
  root_none: Object.entries(r.config[key]).some(([p,a])=>tmp1.startsWith(p+'/')&&a==='none'),
  deny_on_resume: r.config[key]['/home/x/.codex'],
  normal_profile_kept: n.config.default_permissions===seg1.config.default_permissions,
  deny_on_normal: n.config[`permissions.${{n.config.default_permissions}}.filesystem`]['/home/x/.codex'],
}}));
'''
        env = dict(os.environ, ARW_REVIEWER_SCRATCH_ROOT=str(self.root))
        out = subprocess.run(['node', '--input-type=module', '-e', script], capture_output=True, text=True, env=env)
        self.assertEqual(out.returncode, 0, out.stderr)
        result = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertEqual(result, {'resume_profile': 'string', 'tmp_match': True, 'scratch_write': 'write',
                                  'root_none': True, 'deny_on_resume': 'none', 'normal_profile_kept': True,
                                  'deny_on_normal': 'none'})

    def test_inspect_allows_the_instance_scratch_but_flags_a_sibling(self):
        # inspect reads the Reviewer's own scratch from turn_context.sandbox_policy.writable_roots: reads and writes
        # inside it (and $TMPDIR, which the patch points there) are not out-of-root, but a sibling instance's scratch,
        # bare /tmp and a genuine out-of-root path are still flagged.
        rootdir = '/tmp/qwen-report-write-42'
        scratch = '/tmp/arw-reviewer-scratch-1000/aaaa1111'
        sibling = '/tmp/arw-reviewer-scratch-1000/bbbb2222'
        meta = {'type': 'session_meta', 'payload': {'id': 't1', 'cwd': rootdir, 'base_instructions': 'x'}}
        tc = {'type': 'turn_context', 'payload': {'sandbox_policy': {
            'type': 'workspace-write', 'writable_roots': [scratch, f'{rootdir}/report']}}}

        def call(cid, cmd):
            return {'type': 'response_item', 'payload': {'type': 'function_call', 'call_id': cid,
                                                         'name': 'exec_command', 'arguments': json.dumps({'cmd': cmd})}}

        def out(cid, text):
            return {'type': 'response_item', 'payload': {'type': 'function_call_output', 'call_id': cid, 'output': text}}

        events = [meta, tc,
                  call('c1', f'cat {scratch}/note.txt && echo hi > {scratch}/x && echo "$TMPDIR"'),  # own scratch + TMPDIR
                  out('c1', 'done'),
                  call('c2', f'cat {sibling}/answer.txt'),      # a sibling instance's scratch
                  out('c2', 'leak'),
                  call('c3', 'cat /tmp/names.txt && echo "$UNSET"'),  # bare /tmp and an unassigned variable
                  out('c3', 'done')]
        session = self.tmp / 'rollout.jsonl'
        session.write_text('\n'.join(json.dumps(e) for e in events))
        r = inspect_session.inspect(session)
        by_n = {a['n']: a['reasons'] for a in r['actions']}
        self.assertEqual(by_n[1], [])  # own scratch and $TMPDIR are in scope
        self.assertIn(f'outside root: {sibling}/answer.txt', by_n[2])
        self.assertIn('outside root: /tmp/names.txt', by_n[3])
        self.assertIn('unassigned variable: $UNSET', by_n[3])

    def test_default_root_and_override(self):
        self.assertEqual(reviewer_scratch.scratch_root({}), Path(f'/tmp/arw-reviewer-scratch-{os.getuid()}'))
        self.assertEqual(reviewer_scratch.scratch_root({reviewer_scratch.ROOT_VARIABLE: str(self.root)}), self.root)

    def test_a_run_removes_the_scratch_of_each_bound_reviewer(self):
        out = self.tmp / 'run'
        bound = []
        for name in ('a-instance-1', 'b-instance-1'):
            (out / name).mkdir(parents=True)
            binding = {'cwd': f'/x/{name}', 'writePaths': [f'/x/{name}/.tmp/reports'], 'reportPath': 'r'}
            (out / name / 'binding.json').write_text(json.dumps(binding))
            bound.append(reviewer_scratch.scratch_path(binding['cwd'], binding['writePaths'], self.root))
        bound[0].mkdir()
        (bound[0] / 'script.sh').write_text('x')
        other = self.root / ('f' * 32)
        other.mkdir()
        self.assertEqual(reviewer_scratch.run_scratches(out, self.root), bound)
        self.assertEqual(reviewer_scratch.remove_run(out, self.root), {str(bound[0]): True, str(bound[1]): False})
        self.assertFalse(bound[0].exists())
        self.assertTrue(other.exists())  # another Reviewer's scratch stays

    def test_remove_refuses_paths_outside_the_root_and_links(self):
        with self.assertRaises(ValueError):
            reviewer_scratch.remove(self.tmp / 'elsewhere', self.root)
        target = self.tmp / 'target'
        target.mkdir()
        link = self.root / ('e' * 32)
        link.symlink_to(target)
        with self.assertRaises(ValueError):
            reviewer_scratch.remove(link, self.root)
        self.assertTrue(target.exists())


if __name__ == '__main__':
    unittest.main()
