"""Blind-adjudication views built from the frozen fixture, never from a run directory a Reviewer worked in.

ARW's own zero-model preparation materializes the scenario root(s) from the frozen source manifest; each root is
copied (without `.git`) as the view the brief names, with the staged comparison the Reviewer saw. Spec Readiness has
one view per sub-scenario (`view-rm`, `view-ap`), each with that sub-scenario's Reviewer Request copied as
`REVIEWER-REQUEST.json` and its `draftPath` redacted (the path names the run). `view-binding.json` records the manifest
and the SHA-256 of every view file, so a pool can cite the exact view it was judged against.

  python3 -m tools.reviewer.adjudication_view --manifest <manifest> --reviewer <id> --work <dir> --out <ADJ>
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# A fixed preparation identity: the view does not depend on which session built it.
THREAD = '00000000-0000-4000-8000-00000000ad1d'
SPEC_VIEWS = {'runtime-migration': 'view-rm', 'artifact-promotion': 'view-ap'}
REDACTED = '<redacted>'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(manifest, reviewer, work):
    """ARW's zero-model preparation of a materialized frozen copy; returns its prepared handoffs."""
    from tools.reviewer.frozen_arw import extract_agent_config
    arw = work / 'arw'
    subprocess.run([sys.executable, '-m', 'tools.reviewer.freeze_arw_source', '--manifest', str(manifest), '--out', str(arw)],
                   cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    (arw / 'config.json').write_text(extract_agent_config((arw / 'docs/manuals/agent-cli.md').read_text()))
    subprocess.run(['git', 'init', '-q'], cwd=arw, check=True)
    result = subprocess.run(['node', 'scripts/reviewer-capability-conformance.mjs', 'prepare', '--reviewer', reviewer],
                            cwd=arw, env=dict(os.environ, CODEX_THREAD_ID=THREAD), check=True, capture_output=True, text=True)
    (work / 'prepare.json').write_text(result.stdout)
    return json.loads(result.stdout)['handoffs']


# Preparation state and the ARW workflow files preparation installs (root AGENTS.md, docs/agents) are not part of the
# fixture under review; the Commit Audit v3 view was built the same way. Fixture files such as src/AGENTS.md stay.
EXCLUDED = {'.git', '.tmp', '.prepared', 'AGENTS.md', 'docs/agents'}


def copy_view(root, target):
    root = Path(root)
    shutil.copytree(root, target, symlinks=True,
                    ignore=lambda folder, names: [n for n in names if (Path(folder) / n).relative_to(root).as_posix() in EXCLUDED])
    return subprocess.run(['git', 'diff', '--cached', '--no-ext-diff', 'HEAD'], cwd=root, check=True,
                          capture_output=True).stdout


def redacted_request(path):
    request = json.loads(Path(path).read_text())
    if not isinstance(request.get('draftPath'), str):
        raise ValueError('Reviewer Request has no draftPath')
    request['draftPath'] = REDACTED
    return json.dumps(request, ensure_ascii=False, indent=2) + '\n'


def build(manifest, reviewer, work, out):
    work, out = Path(work).resolve(), Path(out).resolve()
    work.mkdir(parents=True, exist_ok=False)
    out.mkdir(parents=True, exist_ok=False)
    handoffs = prepare(manifest, reviewer, work)
    views = {}
    if reviewer == 'spec-readiness-reviewer':
        # Every repetition is prepared from the same fixture; the first one of each sub-scenario is the view.
        for handoff in handoffs:
            name = SPEC_VIEWS[handoff['scenarioId']]
            if name in views:
                continue
            root = Path(handoff['input']['cwd'])
            requests = sorted(root.glob('.tmp/codex/*/*/spec-readiness/requests/request-*.json'))
            if len(requests) != 1:
                raise ValueError('Expected exactly one prepared Reviewer Request in ' + name)
            copy_view(root, out / name)
            target = out / name / 'REVIEWER-REQUEST.json'
            if target.exists():
                raise ValueError('The scenario root already holds REVIEWER-REQUEST.json')
            target.write_text(redacted_request(requests[0]))
            views[name] = handoff['scenarioId']
        if set(views) != set(SPEC_VIEWS.values()):
            raise ValueError('Spec Readiness needs both sub-scenario views')
    else:
        if len({h['input']['cwd'] for h in handoffs}) < 1:
            raise ValueError('Preparation returned no scenario root')
        diff = copy_view(handoffs[0]['input']['cwd'], out / 'view')
        (out / 'change.diff').write_bytes(diff)
        views['view'] = reviewer
    files = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    manifest = Path(manifest).resolve()
    binding = {'reviewer': reviewer, 'manifest': str(manifest.relative_to(ROOT) if manifest.is_relative_to(ROOT) else manifest), 'manifest_sha256': sha(manifest),
               'views': views, 'files': files}
    (out / 'view-binding.json').write_text(json.dumps(binding, ensure_ascii=False, indent=2) + '\n')
    return binding


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--reviewer', required=True)
    parser.add_argument('--work', type=Path, required=True, help='fresh directory for the materialized copy')
    parser.add_argument('--out', type=Path, required=True, help='fresh adjudication directory (ADJ)')
    args = parser.parse_args()
    binding = build(args.manifest, args.reviewer, args.work, args.out)
    print(json.dumps({'views': binding['views'], 'files': len(binding['files'])}))
