"""Install a verified upstream tag source ZIP and engine package (tar.gz with engine-component.json) into a local host, with a backup and rollback."""
import argparse
import base64
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
ENGINE = 'runtime/Strata/engine/'
MANIFEST = 'engine-component.json'
CHUNK = 1 << 20
FEED = 'strata-feed.json'
KEYS = 'strata_control/update_keys.json'
# Upstream feed/component Ed25519 key, pinned when first reviewed (v0.2.2); a rotated key needs a reviewed change here.
TRUSTED_KEYS = {'5d1bc23abbeffd0d': 'KjnXZB0T1r3dmBNot8h+c4rTicRtllg1LH9fUlTw4ZY='}
RESERVED = re.compile(r'(con|prn|aux|nul|com[0-9]|lpt[0-9])(\..*)?', re.IGNORECASE)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def member(name):
    """A relative POSIX path that is also a plain Windows path: no traversal, drive, reserved device name or trailing dot/space."""
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or '..' in path.parts or str(path) != name.rstrip('/')
            or any(c in name for c in ':\\<>"|?*') or any(ord(c) < 32 for c in name)
            or any(RESERVED.fullmatch(part) or part[-1] in '. ' for part in path.parts)):
        raise ValueError('Unsafe archive member: ' + name)
    return str(path)


def atomic(path, data):
    """Replace path with bytes, or with the bytes of a readable binary stream; a failed write leaves no stage file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = tempfile.NamedTemporaryFile(dir=path.parent, delete=False)
    stage = Path(stream.name)
    try:
        with stream:
            if isinstance(data, bytes):
                stream.write(data)
            else:
                shutil.copyfileobj(data, stream, CHUNK)
        os.replace(stage, path)
    finally:
        stage.unlink(missing_ok=True)


def rollback(root, backup):
    """Restore every recorded file, continuing past failures, and raise once with all of them."""
    manifest = json.loads((backup / 'before.json').read_text())
    failures = []
    for relative, digest in manifest.items():
        try:
            target = root / member(relative)
            if digest is None:
                target.unlink(missing_ok=True)
                continue
            saved = backup / 'files' / relative
            if sha(saved) != digest:
                raise RuntimeError('backup hash mismatch')
            with saved.open('rb') as stream:
                atomic(target, stream)
            if sha(target) != digest:
                raise RuntimeError('restored hash mismatch')
        except Exception as error:
            failures.append(f'{relative}: {error}')
    if failures:
        raise RuntimeError(f'Rollback left {len(failures)} file(s) unrestored; rerun --rollback {backup}: '
                           + '; '.join(failures))
    return {'rolled_back': True, 'backup': str(backup)}


def verify_signature(payload, signature, keys):
    """The key_id of a pinned Ed25519 key that signed payload (RFC 8032, as upstream strata_control/signing.py)."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    if not isinstance(signature, dict) or signature.get('alg') != 'ed25519' or signature.get('key_id') not in keys:
        raise RuntimeError('Signature is missing or made by an untrusted key')
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(keys[signature['key_id']], validate=True)).verify(
            base64.b64decode(signature.get('value', ''), validate=True), payload)
    except (InvalidSignature, ValueError):
        raise RuntimeError('Signature does not match the signed content') from None
    return signature['key_id']


def verify_feed(feed, release, package):
    """The signed release feed must carry exactly the engine package entry the metadata names."""
    asset = next(a for a in release['assets'] if a['name'] == FEED)
    payload = feed.read_bytes()
    if asset['digest'] != 'sha256:' + hashlib.sha256(payload).hexdigest() or asset['size'] != len(payload):
        raise RuntimeError('Feed differs from the official release size or SHA256')
    signature = json.loads(Path(str(feed) + '.sig').read_text(encoding='utf-8-sig'))
    key_id = verify_signature(payload, signature, TRUSTED_KEYS)
    entries = [p for p in json.loads(payload)['engine']['packages'] if p.get('url') == package['url']]
    if entries != [package]:
        raise RuntimeError('Engine package differs from the signed release feed')
    return key_id


def manifest_payload(manifest):
    """Upstream engine_component.signing_payload: the manifest without signature, canonical JSON."""
    body = {k: v for k, v in manifest.items() if k != 'signature'}
    return json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def engine_files(engine):
    """Yield (name, TarInfo, archive) for each regular file of the package; links, devices and unsafe paths are refused."""
    with tarfile.open(engine, 'r:gz') as archive:
        for info in archive:
            if info.isdir():
                member(info.name)
                continue
            if not info.isreg():
                raise RuntimeError('Unexpected engine archive entry: ' + info.name)
            yield member(info.name), info, archive


def read_engine(engine, package, version, cuda_arch):
    """Check every file against engine-component.json, whose SHA must equal the release feed's manifest_sha256."""
    seen, manifest_bytes, build = {}, None, None
    for name, info, archive in engine_files(engine):
        # Windows paths are case-insensitive, so names that differ only in case collide too.
        if name.lower() in {n.lower() for n in seen}:
            raise RuntimeError('Duplicate engine archive entry: ' + name)
        stream, digest, size = archive.extractfile(info), hashlib.sha256(), 0
        data = b'' if name in (MANIFEST, 'BUILD.json') else None
        while chunk := stream.read(CHUNK):
            digest.update(chunk)
            size += len(chunk)
            if data is not None:
                data += chunk
        seen[name] = {'sha256': digest.hexdigest(), 'bytes': size}
        if name == MANIFEST:
            manifest_bytes = data
        elif name == 'BUILD.json':
            build = json.loads(data)
    if manifest_bytes is None or hashlib.sha256(manifest_bytes).hexdigest() != package['manifest_sha256']:
        raise RuntimeError('Engine manifest missing or differs from the release feed manifest_sha256')
    manifest = json.loads(manifest_bytes)
    files = {member(f['path']): {'sha256': f['sha256'], 'bytes': f['bytes']} for f in manifest['files']}
    if len(files) != len(manifest['files']) or MANIFEST in files or 'strata.exe' not in files:
        raise RuntimeError('Engine manifest lists duplicate or reserved paths')
    expected = {'id': 'strata-engine', 'version': version, 'platform': 'windows-x86_64', 'backend': 'cuda',
                'entrypoint': 'strata.exe', 'build_id': package['build_id'], 'archs': package['archs']}
    if any(manifest.get(k) != v for k, v in expected.items()) or set(seen) != set(files) | {MANIFEST}:
        raise RuntimeError('Engine manifest does not match the release feed or the archive members')
    if any(seen[n] != files[n] for n in files):
        raise RuntimeError('Engine file differs from its manifest size or SHA256')
    if (type(cuda_arch) is not int or build is None or build.get('version') != version
            or 'sm_' + str(cuda_arch) not in manifest['archs'] or cuda_arch not in build.get('archs', [])):
        raise RuntimeError('Engine build version or GPU architecture mismatch')
    verify_signature(manifest_payload(manifest), manifest.get('signature'), TRUSTED_KEYS)
    return seen, build, manifest


def upgrade(root, metadata, source, engine, feed, cuda_arch=89):
    release, package = metadata['release'], metadata['engine_package']
    feed_key = verify_feed(feed, release, package)
    version, commit = release['tag_name'].removeprefix('v'), metadata['commit']
    engine_version = package['version']
    # Since v0.2.15 the feed names an engine reused from an earlier release by full URL; the asset is its file name.
    asset = next(a for a in release['assets'] if a['name'] == package['url'].rsplit('/', 1)[-1])
    if (asset['size'] != package['size'] or asset['digest'] != 'sha256:' + package['sha256']
            or engine.stat().st_size != asset['size'] or sha(engine) != package['sha256']):
        raise RuntimeError('Engine differs from the official release size or SHA256')
    if not (root / 'config/installed-release.json').is_file():
        raise RuntimeError('An existing installation is required')
    writes = {}
    with zipfile.ZipFile(source) as archive:
        if archive.testzip():
            raise RuntimeError('Source ZIP CRC failure')
        # Tag archives are named by version and carry the commit as the ZIP comment.
        prefix = 'Strata-' + version + '/'
        if archive.comment != commit.encode():
            raise RuntimeError('Source ZIP comment does not bind the release commit')
        # Since v0.2.16 the tag keeps the Python runtime under terminal/ and the engine source under engine/ (the
        # installed runtime/Strata is that terminal/ folder, whose engine/ holds the binaries): only terminal/ and the
        # top-level AGENTS.md are installed, and engine/CMakeLists.txt is read for the version check.
        has_terminal_layout = prefix + 'terminal/serve/server.py' in archive.namelist()
        cmake = None
        for info in archive.infolist():
            if info.is_dir():
                continue
            if not info.filename.startswith(prefix) or info.external_attr >> 16 & 0o170000 == 0o120000:
                raise RuntimeError('Unexpected source archive entry')
            name = info.filename[len(prefix):]
            if has_terminal_layout:
                if name == 'engine/CMakeLists.txt':
                    cmake = archive.read(info)
                if name.startswith('terminal/'):
                    name = name[len('terminal/'):]
                elif name != 'AGENTS.md':
                    continue
            data, relative = archive.read(info), 'runtime/Strata/' + member(name)
            if relative.lower() in {r.lower() for r in writes}:
                raise RuntimeError('Duplicate source archive entry: ' + relative)
            writes[relative] = (data, hashlib.sha256(data).hexdigest())
    # The source's own trusted keys must be the pinned ones, so the installed Control trusts no other key.
    shipped = json.loads(writes['runtime/Strata/' + KEYS][0])
    if {k['key_id']: k['public'] for k in shipped['keys']} != TRUSTED_KEYS:
        raise RuntimeError('Source update keys differ from the pinned feed key')
    # A changed file passes only when metadata binds the exact new bytes a maintainer reviewed.
    reviewed, changed = metadata.get('reviewed_changes', {}), []
    for name in ('AGENTS.md', 'requirements.txt'):
        data = writes['runtime/Strata/' + name][0]
        if data == (root / 'runtime/Strata' / name).read_bytes():
            continue
        changed.append(name)
        if reviewed.get(name) != hashlib.sha256(data).hexdigest():
            raise RuntimeError('Changed instructions/dependencies require review: ' + name)
    # The release (tag) and engine versions differ since 0.2.0; CMake carries the engine version.  v0.2.4 ships the
    # unchanged Qwen engine 0.1.48 while its source tree is already 0.1.49 (the DeepSeek engine): the metadata then names
    # that CMake version explicitly (source_cmake_version), a reviewed deviation, never a default.
    cmake_version = metadata.get('source_cmake_version', engine_version)
    if not re.search(r'\bVERSION\s+' + re.escape(cmake_version) + r'(?:\s|\)|$)',
                     (cmake or writes['runtime/Strata/CMakeLists.txt'][0]).decode()):
        raise RuntimeError('Source version does not match the engine version')
    engine_digests, build, manifest = read_engine(engine, package, engine_version, cuda_arch)
    for name, entry in engine_digests.items():
        writes[ENGINE + name] = (None, entry['sha256'])
    data = (json.dumps({'version': version, 'commit': commit, 'engine_version': engine_version}, indent=2) + '\n').encode()
    writes['config/installed-release.json'] = (data, hashlib.sha256(data).hexdigest())
    # The installation is on a case-insensitive Windows volume: a path differing only in case is the written file.
    written = {r.lower() for r in writes}
    removals = set()
    for relative in metadata.get('previous_source_paths', []):
        target = 'runtime/Strata/' + member(relative)
        if target.lower() not in written and (root / target).is_file():
            removals.add(target)
    # The engine folder holds exactly the package, so no stale DLL from an earlier package is loaded beside it.
    engine_dir = root / ENGINE
    if engine_dir.is_dir():
        for path in engine_dir.rglob('*'):
            relative = path.relative_to(root).as_posix()
            if not path.is_dir() and relative.lower() not in written:
                removals.add(relative)
    unchanged = {r for r, (_, digest) in writes.items() if (root / r).is_file() and sha(root / r) == digest}
    writes = {r: v for r, v in writes.items() if r not in unchanged}
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
        for relative, (data, digest) in writes.items():
            if data is not None:
                atomic(root / relative, data)
        if any(r.startswith(ENGINE) for r in writes):
            for name, info, archive in engine_files(engine):
                if ENGINE + name in writes:
                    atomic(root / ENGINE / name, archive.extractfile(info))
        for relative, (_, digest) in writes.items():
            if sha(root / relative) != digest:
                raise RuntimeError('Installed hash mismatch: ' + relative)
        for relative in removals:
            (root / relative).unlink()
        # A removal must not have taken a written file with it.
        for relative, (_, digest) in writes.items():
            if not (root / relative).is_file() or sha(root / relative) != digest:
                raise RuntimeError('Installed file lost or changed after removals: ' + relative)
    except BaseException:
        rollback(root, backup)
        raise
    result = {'version': version, 'commit': commit, 'engine_version': engine_version,
              'source_zip_sha256': sha(source), 'engine_archive_sha256': package['sha256'],
              'engine_manifest_sha256': package['manifest_sha256'], 'engine_build_id': manifest['build_id'],
              'feed_sha256': sha(feed), 'signatures_verified': {'feed': feed_key, 'engine_manifest': manifest['signature']['key_id']},
              'engine_build': build, 'backup': str(backup),
              'written_sha256': {r: d for r, (_, d) in writes.items()}, 'unchanged_files': len(unchanged),
              'removed_upstream_files': sorted(removals),
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
    parser.add_argument('--feed', type=Path, help='strata-feed.json of the release; its .sig must sit beside it')
    parser.add_argument('--rollback', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    from tools.ops.deploy import local_path, maintenance
    from tools.ops.deployment_source import load_host, require_current_host
    host = load_host(require_current_host(args.host))
    root = local_path(host['installation_root']).resolve(strict=True)
    # The frontend is shut down through its own lease, so no model can start meanwhile.
    with maintenance(host['frontend_url']):
        result = rollback(root, args.rollback) if args.rollback else upgrade(
            root, json.loads(args.metadata.read_text()), args.source, args.engine, args.feed,
            cuda_arch=host['cuda_arch'])
    atomic(args.output, (json.dumps(result, indent=2) + '\n').encode())
    print(json.dumps({k: v for k, v in result.items() if k != 'written_sha256'}, indent=2))


if __name__ == '__main__':
    main()
