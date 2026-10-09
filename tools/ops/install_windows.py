"""Initialize a fresh Windows installation from project-owned pinned inputs."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import time
import uuid
import zipfile
import subprocess

from tools.ops.deployment_source import load_host, stage
from tools.ops.remote_windows import connection_environment, host_configuration, powershell
from tools.ops.ssh_files import copy_file, powershell_literal

ROOT = Path(__file__).resolve().parents[2]


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def remote_python(settings, code, arguments=(), timeout=120, executable=None):
    wrapper="import json\ntry:\n exec("+repr(code)+")\nexcept Exception as error:\n print(json.dumps({'installer_phase_error':type(error).__name__,'message':str(error)}))"
    if os.name=='nt':
        from tools.ops.windows_remote import python_command
        reply=python_command(settings['host_id'],wrapper,arguments,timeout,executable=executable)
    else:
        worker=subprocess.check_output(['wslpath','-w',str(ROOT/'tools/ops/windows_remote.py')],text=True).strip()
        request={'operation':'python','code':wrapper,'args':[str(x) for x in arguments],'timeout':timeout}
        if executable is not None:request['executable']=str(executable)
        result=subprocess.run(['/mnt/c/Python314/python.exe',worker,'--host',settings['host_id']],
                              input=json.dumps(request).encode('utf-8'),capture_output=True,timeout=timeout+15)
        if result.returncode:raise RuntimeError('Native installer transport failed; private stderr not echoed')
        value=json.loads(result.stdout.decode('utf-8-sig'))
        if not value.get('ok'):raise RuntimeError(value.get('error','Native installer transport failed'))
        reply=value['stdout']
    parsed = json.loads(reply)
    if isinstance(parsed, dict) and parsed.get('installer_phase_error'):
        raise RuntimeError(parsed['installer_phase_error'] + ': ' + parsed.get('message', 'Installer phase failed'))
    return reply


def initialize(host, out, resume=False):
    if os.name != 'nt':
        raise RuntimeError('Initialize through Windows Python and native Windows SSH/SCP')
    settings = connection_environment(host=host)
    profile = load_host(host)
    root = PureWindowsPath(settings['installation_path'])
    out = Path(out).resolve();out.mkdir(parents=True, exist_ok=resume)
    release = json.loads((ROOT / 'config/artifacts/strata-release.json').read_text(encoding='utf-8'))
    dependencies = json.loads((ROOT / 'config/artifacts/windows-dependencies.json').read_text(encoding='utf-8'))
    known = Path(os.environ['USERPROFILE']) / '.ssh/known_hosts'
    local = Path(host_configuration(host='local')['installation_path'])
    if resume:
        receipt=json.loads((out/'source-installation.json').read_text(encoding='utf-8'))
        binding=json.loads((out/'service/deployment-manifest.json').read_text(encoding='utf-8'))
        if not receipt.get('source_and_service_installed'):raise RuntimeError('Source installation is not confirmed')
    else:
        service = out / 'service';binding = stage(host, service)
        bundle = out / 'service.zip'
        with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in service.rglob('*'):
                if path.is_file():archive.write(path, path.relative_to(service).as_posix())
        incoming = root / 'downloads' / ('installation-' + uuid.uuid4().hex)
        code = '''import json,sys
    from pathlib import Path
    r=Path(sys.argv[1]);incoming=Path(sys.argv[2])
    if (r/'config/installed-release.json').exists() or (r/'.state/ownership.json').exists():raise RuntimeError('Existing service must use owned maintenance deployment')
    incoming.mkdir(parents=True,exist_ok=False)
    print(json.dumps({'fresh_install':True,'model_started':False}))
    '''
        json.loads(remote_python(settings, code, (root, incoming)))
        print(json.dumps({'stage': 'upload-project-source', 'host': host}), flush=True)
        items = [(ROOT / release['source']['project_file'], incoming / 'source.zip', release['source']['sha256']),
                 (ROOT / release['engine']['project_file'], incoming / 'engine.zip', release['engine']['sha256']),
                 (bundle, incoming / 'service.zip', hashlib.file_digest(bundle.open('rb'), 'sha256').hexdigest())]
        for source, destination, digest in items:
            if hashlib.file_digest(source.open('rb'), 'sha256').hexdigest() != digest:
                raise RuntimeError('Project release input SHA differs')
            copy_file(source, destination, settings, known, timeout=1200)
        metadata = {'release': release, 'architecture': profile['cuda_arch'],
                    'source_sha256': items[0][2], 'engine_sha256': items[1][2], 'service_sha256': items[2][2]}
        code = '''import hashlib,json,sys,zipfile
    from pathlib import Path,PurePosixPath
    r=Path(sys.argv[1]);incoming=Path(sys.argv[2]);meta=json.loads(sys.argv[3])
    for name,digest in [('source.zip',meta['source_sha256']),('engine.zip',meta['engine_sha256']),('service.zip',meta['service_sha256'])]:
     with (incoming/name).open('rb') as stream:
      if hashlib.file_digest(stream,'sha256').hexdigest()!=digest:raise RuntimeError('Uploaded package SHA differs')
    def extract(path,target,prefix=''):
     with zipfile.ZipFile(path) as archive:
      if archive.testzip():raise RuntimeError('Archive CRC failed')
      for member in archive.infolist():
       if member.is_dir():continue
       if not member.filename.startswith(prefix):raise RuntimeError('Unexpected source prefix')
       relative=PurePosixPath(member.filename[len(prefix):])
       if relative.is_absolute() or '..' in relative.parts or ':' in str(relative) or chr(92) in str(relative) or member.external_attr>>16&0o170000==0o120000:raise RuntimeError('Unsafe archive member')
       destination=target/str(relative);destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(archive.read(member))
    extract(incoming/'source.zip',r/'runtime/Strata','Strata-'+meta['release']['commit']+'/')
    with zipfile.ZipFile(incoming/'engine.zip') as archive:
     build=json.loads(archive.read('BUILD.json'))
     if build['version']!=meta['release']['engine_version'] or meta['architecture'] not in build['archs']:raise RuntimeError('Wrong engine architecture/version')
     if set(archive.namelist())!={'strata.exe','strata-vision.exe','BUILD.json'}:raise RuntimeError('Wrong engine archive members')
    extract(incoming/'engine.zip',r/'runtime/Strata/engine')
    extract(incoming/'service.zip',r)
    print(json.dumps({'source_and_service_installed':True,'engine_build':build,'model_started':False}))
    '''
        receipt = json.loads(remote_python(settings, code, (root, incoming, json.dumps(metadata))))
        write_json(out / 'source-installation.json', receipt)
    print(json.dumps({'stage': 'create-private-python', 'host': host}), flush=True)
    script = ("$ErrorActionPreference='Stop';$root=" + powershell_literal(str(root)) + ";"
              "& 'C:\\Python314\\python.exe' -m venv (Join-Path $root 'runtime\\Strata\\.venv');"
              "if($LASTEXITCODE-ne 0){throw 'Private Python creation failed'};"
              "New-Item -ItemType Directory -Path (Join-Path $root 'downloads\\wheels') -Force|Out-Null;[Console]::WriteLine('ready')")
    if powershell(script, settings, timeout=120).strip() != 'ready':raise RuntimeError('Private Python setup not confirmed')
    wheels = []
    for item in dependencies['files']:
        source = local / 'downloads/wheels' / item['filename']
        if source.stat().st_size != item['bytes']:raise RuntimeError('Existing dependency size differs')
        print(json.dumps({'stage': 'dependency-upload', 'package': item['package'], 'bytes': item['bytes']}), flush=True)
        copy_file(source, root / 'downloads/wheels' / item['filename'], settings, known, timeout=1200)
        wheels.append(item)
    code = '''import hashlib,json,sys
from pathlib import Path
r=Path(sys.argv[1]);items=json.loads(sys.argv[2])
for item in items:
 p=r/'downloads/wheels'/item['filename']
 with p.open('rb') as stream:
  if p.stat().st_size!=item['bytes'] or hashlib.file_digest(stream,'sha256').hexdigest()!=item['sha256']:raise RuntimeError('Dependency integrity differs')
print(json.dumps({'wheels_verified':len(items)}))
'''
    verification = json.loads(remote_python(settings, code, (root, json.dumps(wheels))))
    install_pinned_dependencies(settings, root, dependencies)
    code = '''import json,sys
from pathlib import Path
r=Path(sys.argv[1]);release=json.loads(sys.argv[2]);(r/'config/installed-release.json').write_text(json.dumps({'version':release['version'],'commit':release['commit']},indent=2)+'\\n',encoding='utf-8')
print(json.dumps({'installed_release_written':True,'model_started':False}))
'''
    json.loads(remote_python(settings, code, (root, json.dumps(release))))
    result = {'status': 'source-dependencies-ready', 'host': host, 'version': release['version'],
              'engine_build': receipt['engine_build'], 'dependencies': verification,
              'service_files': len(binding['files']), 'models_and_support_assets_pending': True,
              'controller_started': False, 'model_requests': 0}
    write_json(out / 'result.json', result)
    return result


def install_pinned_dependencies(settings, root, dependencies):
    """Install the full pinned set, including CUDA packages outside requirements."""
    code='''import hashlib,json,os,subprocess,sys
from pathlib import Path
r=Path(sys.argv[1]);items=json.loads(sys.argv[2]);wheels=r/'downloads/wheels'
for item in items:
 p=wheels/item['filename']
 with p.open('rb') as stream:
  if p.stat().st_size!=item['bytes'] or hashlib.file_digest(stream,'sha256').hexdigest()!=item['sha256']:raise RuntimeError('Pinned dependency integrity differs')
python=r/'runtime/Strata/.venv/Scripts/python.exe'
env=dict(os.environ,PIP_NO_INDEX='1',PIP_DISABLE_PIP_VERSION_CHECK='1')
command=[str(python),'-m','pip','install','--no-index','--find-links',str(wheels),*[str(wheels/i['filename']) for i in items]]
reply=subprocess.run(command,capture_output=True,env=env,timeout=600)
if reply.returncode:raise RuntimeError('Full pinned offline dependency install failed')
reply=subprocess.run([str(python),'-m','pip','check'],capture_output=True,env=env,timeout=60)
if reply.returncode:raise RuntimeError('Installed dependency consistency failed')
print(json.dumps({'pinned_packages_installed':len(items),'pip_check':True,'model_requests':0}))
'''
    return json.loads(remote_python(settings,code,(root,json.dumps(dependencies['files'])),timeout=720))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    print(json.dumps(initialize(args.host, args.out, args.resume), indent=2))
