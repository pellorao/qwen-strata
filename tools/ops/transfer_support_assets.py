"""Transfer immutable native packs/MTP directly and verify both sides afterwards."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import time

from tools.ops.remote_windows import connection_environment, host_configuration, powershell
from tools.ops.ssh_files import copy_file, powershell_literal
from tools.ops.install_windows import remote_python

ROOT = Path(__file__).resolve().parents[2]


def run(host, out, resume=False):
    if os.name != 'nt':raise RuntimeError('Use native Windows Python/SSH/SCP')
    settings = connection_environment(host=host)
    source = Path(host_configuration(host='local')['installation_path'])
    destination = PureWindowsPath(settings['installation_path'])
    pinned=json.loads((ROOT/'config/artifacts/native-support.json').read_text(encoding='utf-8'))
    known = Path(os.environ['USERPROFILE']) / '.ssh/known_hosts'
    out = Path(out).resolve();out.mkdir(parents=True, exist_ok=resume)
    records = json.loads((out/'completed-directories.json').read_text(encoding='utf-8')) if resume and (out/'completed-directories.json').exists() else []
    for relative in ('data/packs', 'data/mtp'):
        binding=next(d['files'] for d in pinned['directories'] if d['directory']==relative)
        prior=next((r for r in records if r['directory']==relative),None)
        if prior is not None:
            if {f['path']:(f['bytes'],f['sha256']) for f in prior['files']}!={f['path']:(f['bytes'],f['sha256']) for f in binding}:
                raise RuntimeError('Prior support verification differs from current project manifest')
            print(json.dumps({'stage':'reuse-verified-support','directory':relative}),flush=True)
            continue
        directory = source / relative
        files = sorted(p for p in directory.rglob('*') if p.is_file())
        if not files:raise RuntimeError('Required support assets are absent')
        by_path={item['path']:item for item in binding}
        if {p.relative_to(source).as_posix() for p in files}!=set(by_path):raise RuntimeError('Support asset file set differs from project manifest')
        if any(p.stat().st_size!=by_path[p.relative_to(source).as_posix()]['bytes'] for p in files):raise RuntimeError('Support asset size differs from project manifest')
        target_parent = destination / 'data'
        script = "$ErrorActionPreference='Stop';New-Item -ItemType Directory -Path " + powershell_literal(str(target_parent)) + " -Force|Out-Null;[Console]::WriteLine('ready')"
        if powershell(script, settings).strip() != 'ready':raise RuntimeError('Support target not confirmed')
        print(json.dumps({'stage': 'support-upload', 'directory': relative,
                          'bytes': sum(p.stat().st_size for p in files), 'files': len(files)}), flush=True)
        started = time.monotonic()
        seconds = copy_file(directory, target_parent, settings, known, timeout=12*3600, recursive=True)
        expected = []
        for path in files:
            with path.open('rb') as stream:digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            if digest!=by_path[path.relative_to(source).as_posix()]['sha256']:raise RuntimeError('Transferred source asset SHA differs from project manifest')
            expected.append({'path': path.relative_to(source).as_posix(), 'bytes': path.stat().st_size, 'sha256': digest})
        code = '''import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]);expected=json.loads(sys.argv[2]);results=[]
for item in expected:
 path=root/item['path']
 with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
 if path.stat().st_size!=item['bytes'] or digest!=item['sha256']:raise RuntimeError('Support file integrity differs')
 results.append(item)
print(json.dumps({'verified_files':len(results),'verified_bytes':sum(x['bytes'] for x in results)}))
'''
        verified = json.loads(remote_python(settings, code, (destination, json.dumps(expected)), timeout=1800))
        records.append({'directory': relative, 'upload_seconds': seconds,
                        'total_seconds': time.monotonic()-started, 'files': expected, 'verification': verified})
        (out/'completed-directories.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'stage':'support-verified','directory':relative,**verified}),flush=True)
    result = {'status':'completed','host':host,'directories':records,'model_requests':0}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--host',required=True);parser.add_argument('--out',type=Path,required=True);parser.add_argument('--resume',action='store_true')
    args=parser.parse_args();print(json.dumps(run(args.host,args.out,args.resume),indent=2))
