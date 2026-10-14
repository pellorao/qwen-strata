"""Install verified upstream source/engine ZIPs into a local host, with a backup and rollback."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def member(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or ':' in name or '\\' in name:
        raise ValueError('Unsafe ZIP member: ' + name)
    return str(path)


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        stage = Path(stream.name)
        stream.write(data)
    try:
        os.replace(stage, path)
    finally:
        stage.unlink(missing_ok=True)


def rollback(root, backup):
    manifest = json.loads((backup / 'before.json').read_text())
    for relative, digest in manifest.items():
        target = root / member(relative)
        if digest is None:
            target.unlink(missing_ok=True)
        else:
            saved = backup / 'files' / relative
            if sha(saved) != digest:
                raise RuntimeError('Rollback backup hash mismatch: ' + relative)
            atomic(target, saved.read_bytes())
    return {'rolled_back': True, 'backup': str(backup)}


def upgrade(root, metadata, source, engine, cuda_arch=89):
    release = metadata['release']
    version, commit = release['tag_name'].removeprefix('v'), metadata['commit']
    asset = next(a for a in release['assets'] if a['name'] == 'strata-windows-x64.zip')
    engine_version = version
    reused_release = metadata.get('reused_engine_release')
    if reused_release is not None:
        prior_version = reused_release['tag_name'].removeprefix('v')
        prior_asset = next(a for a in reused_release['assets'] if a['name'] == asset['name'])
        if (not re.fullmatch(r'\d+\.\d+\.\d+', prior_version)
                or not re.fullmatch(re.escape(prior_version) + r'\.\d+', version)
                or prior_asset['size'] != asset['size'] or prior_asset['digest'] != asset['digest']):
            raise RuntimeError('Hotfix engine reuse is not bound to identical official assets')
        engine_version = prior_version
    if engine.stat().st_size != asset['size'] or sha(engine) != asset['digest'].removeprefix('sha256:'):
        raise RuntimeError('Engine differs from the official release size or SHA256')
    if not (root / 'config/installed-release.json').is_file():
        raise RuntimeError('An existing installation is required')
    writes = {}
    with zipfile.ZipFile(source) as archive:
        if archive.testzip():
            raise RuntimeError('Source ZIP CRC failure')
        # Commit archives are named by commit; tag archives by version and carry the commit as the ZIP comment.
        prefix = 'Strata-' + commit + '/'
        tag_prefix = 'Strata-' + version + '/'
        if archive.comment == commit.encode() and all(n.startswith(tag_prefix) for n in archive.namelist()):
            prefix = tag_prefix
        for info in archive.infolist():
            if info.is_dir():
                continue
            if not info.filename.startswith(prefix) or info.external_attr >> 16 & 0o170000 == 0o120000:
                raise RuntimeError('Unexpected source archive entry')
            relative = member(info.filename[len(prefix):])
            writes['runtime/Strata/' + relative] = archive.read(info)
    # A changed file passes only when metadata binds the exact new bytes a maintainer reviewed.
    reviewed, changed = metadata.get('reviewed_changes', {}), []
    for name in ('AGENTS.md', 'requirements.txt'):
        data = writes['runtime/Strata/' + name]
        if data == (root / 'runtime/Strata' / name).read_bytes():
            continue
        changed.append(name)
        if reviewed.get(name) != hashlib.sha256(data).hexdigest():
            raise RuntimeError('Changed instructions/dependencies require review: ' + name)
    if not re.search(r'\bVERSION\s+' + re.escape(engine_version) + r'(?:\s|\)|$)', writes['runtime/Strata/CMakeLists.txt'].decode()):
        raise RuntimeError('Source version does not match release')
    with zipfile.ZipFile(engine) as archive:
        # strata_kq.dll (K-quant prompt kernels, 0.1.44+) is opened only for models in those formats.
        names = set(archive.namelist())
        required = {'strata.exe', 'strata-vision.exe', 'BUILD.json'}
        if archive.testzip() or not required <= names <= required | {'strata_kq.dll'}:
            raise RuntimeError('Unexpected engine ZIP or CRC failure')
        build = json.loads(archive.read('BUILD.json'))
        if type(cuda_arch) is not int or build['version'] != engine_version or cuda_arch not in build['archs']:
            raise RuntimeError('Engine build version or GPU architecture mismatch')
        installed_engine_unchanged = reused_release is not None and all(
            (root / 'runtime/Strata/engine' / name).is_file()
            and (root / 'runtime/Strata/engine' / name).read_bytes() == archive.read(name)
            for name in archive.namelist())
        for name in archive.namelist():
            if not installed_engine_unchanged:
                writes['runtime/Strata/engine/' + name] = archive.read(name)
    writes['config/installed-release.json'] = (json.dumps({'version': version, 'commit': commit}, indent=2) + '\n').encode()
    removals = set()
    for relative in metadata.get('previous_source_paths', []):
        target = 'runtime/Strata/' + member(relative)
        if target not in writes and (root / target).is_file():
            removals.add(target)
    backup = ROOT / '.tmp/maintenance-backups' / ('release-backup-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    backup.mkdir(parents=True)
    before = {}
    for relative in sorted(set(writes) | removals):
        target = root / relative
        before[relative] = sha(target) if target.is_file() else None
        if target.is_file():
            saved = backup / 'files' / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(target, saved)
            if sha(saved) != before[relative]:
                raise RuntimeError('Backup verification failed: ' + relative)
    atomic(backup / 'before.json', (json.dumps(before, indent=2) + '\n').encode())
    try:
        for relative, data in writes.items():
            atomic(root / relative, data)
            if sha(root / relative) != hashlib.sha256(data).hexdigest():
                raise RuntimeError('Installed hash mismatch: ' + relative)
        for relative in removals:
            (root / relative).unlink()
    except BaseException:
        rollback(root, backup)
        raise
    result = {'version': version, 'commit': commit, 'source_zip_sha256': sha(source),
              'engine_zip_sha256': sha(engine), 'engine_build': build, 'backup': str(backup),
              'engine_reused_from_release': engine_version if reused_release is not None else None,
              'installed_engine_unchanged': installed_engine_unchanged,
              'written_sha256': {r: sha(root / r) for r in writes}, 'removed_upstream_files': sorted(removals),
              'model_weights_modified': False, 'model_configuration_modified': False,
              'dependencies_modified': 'requirements.txt' in changed,
              'reviewed_changes': {n: reviewed[n] for n in changed}}
    atomic(backup / 'upgrade.json', (json.dumps(result, indent=2) + '\n').encode())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--metadata', type=Path)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--engine', type=Path)
    parser.add_argument('--rollback', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    from tools.ops.deploy import local_path, maintenance
    from tools.ops.deployment_source import load_host
    host = load_host(args.host)
    root = local_path(host['installation_root']).resolve(strict=True)
    # The frontend is shut down through its own lease, so no model can start meanwhile.
    with maintenance(host['frontend_url']):
        result = rollback(root, args.rollback) if args.rollback else upgrade(
            root, json.loads(args.metadata.read_text()), args.source, args.engine, cuda_arch=host['cuda_arch'])
    atomic(args.output, (json.dumps(result, indent=2) + '\n').encode())
    print(json.dumps({k: v for k, v in result.items() if k != 'written_sha256'}, indent=2))


if __name__ == '__main__':
    main()
