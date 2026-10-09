"""Synchronize project service inputs to registered installations under ownership."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import subprocess
import sys

from tools.ops.controller_client import Controller
from tools.ops.deploy_wsl import deploy
from tools.ops.deployment_source import load_host, stage
from tools.ops.install_windows import remote_python
from tools.ops.remote_windows import connection_environment

ROOT=Path(__file__).resolve().parents[2]


def restart_local(installation,controller):
    """Reload owned controller code while keeping the maintenance key held."""
    root=subprocess.check_output(['wslpath','-w',str(installation)],text=True).strip()
    python=str(installation/'runtime/Strata/.venv/Scripts/python.exe')
    code='''import json,sys
from pathlib import Path
payload=json.load(sys.stdin);r=Path(payload['root']);key=payload['key']
sys.path.insert(0,str(r/'src'))
from windows_host import startup_lock,listener,assert_owner,terminate,_controller
from service_access import authorize
from service_settings import load_service_settings
from urllib.parse import urlsplit
s=load_service_settings(r);info=payload['info'];host=urlsplit(info['controller_base_url']).hostname
with startup_lock():
 if not authorize(r/'.state/ownership.json',key):raise RuntimeError('Maintenance ownership changed')
 model_host=host if s['model_address']=='host' else s['model_address']
 if listener(s['model_port'],model_host):raise RuntimeError('Model is running; refuse controller restart')
 broker=listener(s['listen_port'],host)
 if broker:
  assert_owner(broker,r/'src/responses_bridge.py');terminate(broker)
 _controller(host,info.get('clients') or [info['client']],s)
 if not authorize(r/'.state/ownership.json',key):raise RuntimeError('Ownership was lost during restart')
print(json.dumps({'controller_restarted':True,'maintenance_key_preserved':True}))
'''
    payload={'root':root,'key':controller.key,'info':controller.info}
    reply=subprocess.run([python,'-B','-c',code],input=json.dumps(payload).encode(),capture_output=True,timeout=90)
    if reply.returncode:raise RuntimeError('Owned local controller restart failed; private payload not echoed')
    return json.loads(reply.stdout)


def sync(host,out):
    profile=load_host(host);out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    remote=profile['transport']=='ssh-windows'
    if remote:
        settings=connection_environment(host=host)
        controller=Controller(Path(profile['installation_root']),out,base_url=settings['api_base_url'])
    else:
        installation=Path(subprocess.check_output(['wslpath','-u',profile['installation_root']],text=True).strip())
        controller=Controller(installation,out)
    health=controller.call('/health',timeout=10)
    if health['ownership']!='free':raise RuntimeError('Installation is busy; preserve owner and retry when free')
    controller.__enter__()
    try:
        if controller.call('/ownership/status',timeout=10)['status']!='stopped':raise RuntimeError('Model must be stopped for deployment')
        if remote:
            package=out/'stage';manifest=stage(host,package)
            payload={target:base64.b64encode((package/target).read_bytes()).decode() for target in manifest['files']}
            python=PureWindowsPath(profile['installation_root'])/'runtime/Strata/.venv/Scripts/python.exe'
            capture='''import base64,json,sys
from pathlib import Path
r=Path(sys.argv[1]);names=json.loads(sys.argv[2]);key=sys.argv[3]
sys.path.insert(0,str(r/'src'))
from windows_host import startup_lock,listener,assert_owner
from service_access import authorize
from service_settings import load_service_settings
settings=load_service_settings(r)
with startup_lock():
 if not authorize(r/'.state/ownership.json',key):raise RuntimeError('Maintenance ownership changed')
 model_host=settings['listen_address'] if settings['model_address']=='host' else settings['model_address']
 if listener(settings['model_port'],model_host):raise RuntimeError('Model listener is occupied')
 broker=listener(settings['listen_port'],settings['listen_address'])
 if broker:assert_owner(broker,r/'src/responses_bridge.py')
 before={name:base64.b64encode((r/name).read_bytes()).decode() if (r/name).exists() else None for name in names}
print(json.dumps({'before':before}))
'''
            before=json.loads(remote_python(settings,capture,(profile['installation_root'],json.dumps(list(payload)),controller.key),executable=python))['before']
            # Persist the backup before any replacement, so a lost SSH reply
            # cannot leave recovery dependent on remote process memory.
            backups=ROOT/'.tmp/maintenance-backups'/('remote-'+host+'-'+str(__import__('time').time_ns()))
            backups.mkdir(parents=True)
            for name,data in before.items():
                if data is not None:
                    p=backups/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(data))
            (backups/'before-manifest.json').write_text(json.dumps({name:hashlib.sha256(base64.b64decode(data)).hexdigest() if data is not None else None for name,data in before.items()},indent=2)+'\n',encoding='utf-8')
            # Ownership is passed only through encrypted SSH stdin, never argv.
            code='''import base64,hashlib,json,sys
from pathlib import Path
r=Path(sys.argv[1]);payload=json.loads(sys.argv[2]);expected=json.loads(sys.argv[3]);key=sys.argv[4];before=json.loads(sys.argv[5])
sys.path.insert(0,str(r/'src'))
from windows_host import startup_lock,listener,assert_owner,terminate
from service_access import authorize
from service_settings import load_service_settings
settings=load_service_settings(r)
with startup_lock():
 if not authorize(r/'.state/ownership.json',key):raise RuntimeError('Maintenance ownership changed')
 model_host=settings['listen_address'] if settings['model_address']=='host' else settings['model_address']
 if listener(settings['model_port'],model_host):raise RuntimeError('Model listener is occupied')
 broker=listener(settings['listen_port'],settings['listen_address'])
 if broker:assert_owner(broker,r/'src/responses_bridge.py')
 for name,data in before.items():
  p=r/name;actual=p.read_bytes() if p.exists() else None
  if actual!=(base64.b64decode(data) if data is not None else None):raise RuntimeError('Target changed since saved backup')
 try:
  for name,data in payload.items():
   p=r/name;p.parent.mkdir(parents=True,exist_ok=True);temporary=p.with_name(p.name+'.deploy-stage');temporary.write_bytes(base64.b64decode(data));temporary.replace(p)
   if hashlib.sha256(p.read_bytes()).hexdigest()!=expected[name]['sha256']:raise RuntimeError('Installed source SHA differs')
 except BaseException:
  for name,data in before.items():
   p=r/name
   if data is None:p.unlink(missing_ok=True)
   else:p.write_bytes(base64.b64decode(data))
  raise
 if broker:terminate(broker)
# Bootstrap outside the mutex: the new interpreter acquires that same lock.
import subprocess
restart_error=None
try:
 reply=subprocess.run([sys.executable,'-B',str(r/'src/windows_host.py'),'native-controller'],capture_output=True,timeout=60)
 if reply.returncode:restart_error='Controller restart failed; ownership is preserved for recovery'
 if not authorize(r/'.state/ownership.json',key):restart_error='Maintenance ownership was lost during restart'
except subprocess.TimeoutExpired:restart_error='Controller restart timed out; inspect before recovery'
print(json.dumps({'source_sha_verified':True,'files':len(payload),'restart_error':restart_error}))
'''
            result=json.loads(remote_python(settings,code,(profile['installation_root'],json.dumps(payload),json.dumps(manifest['files']),controller.key,json.dumps(before)),timeout=120,executable=python))
            result['backup']=str(backups)
            if result.get('restart_error'):
                (out/'failure.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
                raise RuntimeError(result['restart_error'])
        else:
            os.environ['STRATA_API_KEY']=controller.key
            try:result=deploy(installation,deployment=host)
            finally:os.environ.pop('STRATA_API_KEY',None)
            result.update(restart_local(installation,controller))
        result.update(host=host,model_requests=0)
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    finally:controller.__exit__(None,None,None)
    if controller.call('/health',timeout=10)['ownership']!='free':raise RuntimeError('Ownership return not confirmed')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--hosts',nargs='+');parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();hosts=args.hosts or [p.stem for p in sorted((ROOT/'config/deployments').glob('*.json'))]
    results=[]
    for host in hosts:
        result=sync(host,args.out/host);results.append({'host':host,'files':result.get('files',len(result.get('deployed_sha256',{}))),'model_requests':0})
    print(json.dumps(results,indent=2))
