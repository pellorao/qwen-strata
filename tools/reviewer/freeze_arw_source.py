"""Freeze current upstream source bytes; extract only verified source members.

This never imports Git history or copies runtime state. Materialization and
original ARW preparation happen in a separate temporary copy. Project-owned
compatibility patches listed in the manifest are applied after extraction and
their results verified; a fresh freeze starts without them. The project's ARW scoring
upgrade (evidence F2 instead of F3 and paired cases, user 2026-10-14) is applied to every
materialized copy after the manifest patches, and to an already materialized copy before it scores.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile

ROOTS = {'lib', 'scripts', 'docs', '.agents', 'tests'}
FILES = {'arw.mjs', 'package.json', 'arw.config.json', 'release-manifest.json', 'release-validation.json',
         '.gitignore', 'AGENTS.md', 'README.md'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def freeze(source, destination):
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    names = subprocess.check_output(['git', 'ls-files', '--cached', '--others',
        '--exclude-standard', '-z'], cwd=source).decode().split('\0')
    selected = sorted({n for n in names if n and (n.split('/')[0] in ROOTS or n in FILES)
                       and (source / n).exists()})
    payload = {}
    modes = {}
    for name in selected:
        path = source / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('Source must be an ordinary file: ' + name)
        payload[name] = path.read_bytes()
        modes[name] = 0o755 if path.stat().st_mode & 0o111 else 0o644
    hashes = {name: sha(raw) for name, raw in payload.items()}
    destination.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
        for name, raw in payload.items():
            member = tarfile.TarInfo(name)
            member.size, member.mode, member.mtime = len(raw), modes[name], 0
            archive.addfile(member, io.BytesIO(raw))
    # A moving worktree cannot silently become an inconsistent frozen source.
    if any(sha((source / name).read_bytes()) != expected for name, expected in hashes.items()):
        raise ValueError('Upstream changed during snapshot; preserve the prior freeze')
    raw = buffer.getvalue()
    filename = f'arw-{head[:12]}-{sha(raw)[:12]}.tar.gz'
    target = destination / filename
    if target.exists() and target.read_bytes() != raw:
        raise ValueError('Snapshot name collision')
    target.write_bytes(raw)
    manifest = {'schema': 2, 'source_head': head,
        'current_files_include_uncommitted_changes': bool(subprocess.check_output(
            ['git', 'status', '--porcelain', '--', *sorted(ROOTS), *sorted(FILES)], cwd=source)),
        'framework': 'Unmodified current upstream prepare/generate/verify/score-completed and Reviewer runtime',
        'snapshot': {'file': filename, 'sha256': sha(raw), 'bytes': len(raw)},
        'sha256': hashes, 'modes': modes,
        'scope': 'Repository source/configuration/skills/tests only; no Git history, scratch plans, '
                 'sessions, private credentials, installation or model state.'}
    return manifest


PATCHES = Path(__file__).resolve().parents[2] / 'benchmarks/reviewer-suite-v1/arw-patches'
PAIRS = Path(__file__).resolve().parents[2] / 'benchmarks/reviewer-suite-v1/pairs'
FIXTURES = Path('tests/fixtures/reviewer-capability')
SCORING_UPGRADE = {
    'file': 'scoring-f2.patch',
    'sha256': 'df85dcad195d5193dd71b833e5dc380b1899fb71b88d618d136c5d88f53cc3fe',
    # Members no scenario patch touches: (ARW original, upgraded). The conformance module differs
    # per scenario patch, so it is checked by the patch applying, not by its bytes.
    'members': {
        'lib/release/reviewer-capability-scoring.mjs': (
            '89a4e6bdc0a47756c28abce013ce6940ebf224e8609ebf809a499c57b85d60c4',
            'dfffb39933527ad30d40ea0ccd83d47be4654fe6a751bf21dc2a7c47eade775b'),
        'docs/agents/reviewer-capability-scoring.md': (
            '8dac785a4dc2eee70949fd02a212b65959039c256fa87f6a3e86c105ec011769',
            'bba382d823dc4984e794194aea962412c272dee618e1edf80358eb452e11e239'),
        'docs/agents/reviewer-capability-scenarios.md': (
            '5fe9b4e5511416a4af636baa67b812bf46f627710b75b1285e6c49758fdb909b',
            'd0d333cbd08adf5f3bb248a45fdf3fb3546047a5d3195326d63c69f6ab7b3c2a')}}


def git_apply(patch, destination, *options):
    # Stop repository discovery: inside an enclosing repository git apply resolves paths
    # against that repository and silently skips patches with git headers.
    return subprocess.run(['git', 'apply', '-p1', *options, str(patch.resolve())], cwd=destination,
                          check=not options, capture_output=bool(options),
                          env=dict(os.environ, GIT_CEILING_DIRECTORIES=str(Path(destination).resolve().parent)))


def check_pairs(table, expected):
    """Check every pair against the complete answer key: scope, index and expectation on both sides,
    clean cases in the problem's scope, and no clean case paired with more than one problem case."""
    scopes = {scope['scope']: scope for scope in expected['scopes']}
    twins = set()

    def case(ref, kind):
        scope = scopes.get(ref.get('scope'))
        index = ref.get('index')
        cases = scope[kind] if scope else []
        if not (isinstance(index, int) and 0 <= index < len(cases)
                and cases[index].get('expectation') == ref.get('expectation')):
            raise ValueError(f"Pair table {table['scenario']} names a {kind} entry the answer key lacks: {ref}")

    for pair in table['pairs']:
        case(pair['problem'], 'problemCases')
        if not pair['clean']:
            raise ValueError(f"Pair table {table['scenario']} has a problem case without clean cases")
        for clean in pair['clean']:
            case(clean, 'cleanCases')
            key = (clean['scope'], clean['index'])
            if clean['scope'] != pair['problem']['scope'] or key in twins:
                raise ValueError(f"Pair table {table['scenario']} pairs clean case {key} outside its scope or twice")
            twins.add(key)


def bind_pair_tables(destination):
    """Copy in the pair tables bound to this copy's expected.json bytes; returns their names.
    An unchanged set is left in place; a changed one is staged beside it and swapped in."""
    target = Path(destination) / 'reviewer-pairs'
    bound = {}
    for table_path in sorted(PAIRS.glob('*.json')):
        table = json.loads(table_path.read_text())
        expected = Path(destination) / FIXTURES / table['reviewerId'] / 'expected.json'
        if expected.is_file() and sha(expected.read_bytes()) == table['expectedSha256']:
            check_pairs(table, json.loads(expected.read_text()))
            bound[table_path.name] = table_path.read_bytes()
    current = {path.name: path.read_bytes() for path in target.glob('*')} if target.is_dir() else None
    if current != (bound or None):
        staged = target.with_name('reviewer-pairs.staged')
        retired = target.with_name('reviewer-pairs.retired')
        for path in (staged, retired):
            shutil.rmtree(path, ignore_errors=True)
        if bound:
            staged.mkdir()
            for name, raw in bound.items():
                (staged / name).write_bytes(raw)
        if target.exists():
            target.rename(retired)
        if bound:
            staged.rename(target)
        shutil.rmtree(retired, ignore_errors=True)
    return list(bound)


def upgrade_scoring(destination):
    """Bring a materialized copy to the project's scoring rule: evidence F2 and paired cases
    (user 2026-10-14). Applies the upgrade once and rebinds the pair tables every time."""
    patch = PATCHES / SCORING_UPGRADE['file']
    if sha(patch.read_bytes()) != SCORING_UPGRADE['sha256']:
        raise ValueError('Scoring upgrade patch differs: ' + SCORING_UPGRADE['file'])
    members = SCORING_UPGRADE['members']
    current = {name: sha((Path(destination) / name).read_bytes()) for name in members}
    applied = False
    if not all(current[name] == new for name, (_, new) in members.items()):
        if any(current[name] != old for name, (old, _) in members.items()):
            raise ValueError('ARW scoring members differ from both the original and the upgrade; re-materialize the copy')
        git_apply(patch, destination)
        applied = True
    elif git_apply(patch, destination, '--reverse', '--check').returncode != 0:
        raise ValueError('ARW conformance module lacks the scoring upgrade')
    if any(sha((Path(destination) / name).read_bytes()) != new for name, (_, new) in members.items()):
        raise ValueError('Upgraded scoring member differs')
    return {'applied': applied, 'pair_tables': bind_pair_tables(destination)}


def materialize(manifest, archive_path, destination, patch_directory=None):
    raw = archive_path.read_bytes()
    if sha(raw) != manifest['snapshot']['sha256']:
        raise ValueError('Frozen source archive differs')
    destination.mkdir(parents=True, exist_ok=False)
    seen = set()
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if (not member.isfile() or path.is_absolute() or '..' in path.parts
                    or member.name in seen or member.name not in manifest['sha256']):
                raise ValueError('Unexpected archive member: ' + member.name)
            stream = archive.extractfile(member)
            data = stream.read()
            if sha(data) != manifest['sha256'][member.name]:
                raise ValueError('Frozen member differs: ' + member.name)
            target = destination / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            target.chmod(manifest['modes'][member.name])
            seen.add(member.name)
    if seen != set(manifest['sha256']):
        raise ValueError('Frozen source members are missing')
    for entry in manifest.get('patches', []):
        patch = (patch_directory or archive_path.parent) / entry['file']
        if sha(patch.read_bytes()) != entry['sha256']:
            raise ValueError('Compatibility patch differs: ' + entry['file'])
        git_apply(patch, destination)
        for name, expected in entry['result'].items():
            if sha((destination / name).read_bytes()) != expected:
                raise ValueError('Patched member differs: ' + name)
    upgrade_scoring(destination)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--source', type=Path)
    mode.add_argument('--manifest', type=Path)
    mode.add_argument('--upgrade-scoring', type=Path, metavar='ARW', help='upgrade an already materialized copy')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--archive-directory', type=Path)
    args = parser.parse_args()
    if args.upgrade_scoring:
        print(json.dumps({'scoring_upgrade': SCORING_UPGRADE['file'], **upgrade_scoring(args.upgrade_scoring)}))
    elif args.out is None:
        parser.error('--out is required with --source or --manifest')
    elif args.source:
        result = freeze(args.source, args.out)
        (args.out / 'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'files': len(result['sha256']), 'snapshot': result['snapshot']}))
    else:
        result = json.loads(args.manifest.read_text())
        archive = (args.archive_directory or args.manifest.parent) / result['snapshot']['file']
        materialize(result, archive, args.out)
        print(json.dumps({'materialized_files': len(result['sha256']),
                          'patches': [entry['file'] for entry in result.get('patches', [])] + [SCORING_UPGRADE['file']]}))
