"""Freeze current upstream source bytes; extract only verified source members.

This never imports Git history or copies runtime state. Materialization and
original ARW preparation happen in a separate temporary copy. Project-owned
compatibility patches listed in the manifest are applied after extraction and
their results verified; a fresh freeze starts without them.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
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
        # Stop repository discovery: inside an enclosing repository git apply resolves paths
        # against that repository and silently skips patches with git headers.
        subprocess.run(['git', 'apply', '-p1', str(patch.resolve())], cwd=destination, check=True,
                       env=dict(os.environ, GIT_CEILING_DIRECTORIES=str(Path(destination).resolve().parent)))
        for name, expected in entry['result'].items():
            if sha((destination / name).read_bytes()) != expected:
                raise ValueError('Patched member differs: ' + name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--source', type=Path)
    mode.add_argument('--manifest', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--archive-directory', type=Path)
    args = parser.parse_args()
    if args.source:
        result = freeze(args.source, args.out)
        (args.out / 'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'files': len(result['sha256']), 'snapshot': result['snapshot']}))
    else:
        result = json.loads(args.manifest.read_text())
        archive = (args.archive_directory or args.manifest.parent) / result['snapshot']['file']
        materialize(result, archive, args.out)
        print(json.dumps({'materialized_files': len(result['sha256']),
                          'patches': [entry['file'] for entry in result.get('patches', [])]}))
