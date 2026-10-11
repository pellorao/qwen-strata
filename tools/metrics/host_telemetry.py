"""Start and collect an installation-bound native sampler through host transport."""
import base64
import hashlib
import json
from pathlib import Path
from tools.reviewer.wsl_client import save

SOURCE=Path(__file__).with_name('windows_resource_sampler.py')


# NVML clocks-event (throttle) reason bits; idle is normal at low load and not a slowdown.
THROTTLE_REASONS={0x1:'gpu_idle',0x2:'applications_clocks',0x4:'sw_power_cap',0x8:'hw_slowdown',0x10:'sync_boost',
                  0x20:'sw_thermal',0x40:'hw_thermal',0x80:'hw_power_brake',0x100:'display_clocks'}


def gpu_thermal(rows):
    """Peak temperature, lowest SM clock and every limiting reason seen; unknown stays None."""
    gpu=[r['gpu'] for r in rows if r.get('gpu')]
    known=lambda key:[g[key] for g in gpu if g.get(key) is not None]
    temperatures,clocks,reasons=known('temperature_c'),known('sm_clock_mhz'),known('throttle_reasons')
    seen=0
    for value in reasons:seen|=value
    return {'max_gpu_temperature_c':max(temperatures) if temperatures else None,
            'min_sm_clock_mhz':min(clocks) if clocks else None,
            'throttle_reasons_seen':[name for bit,name in THROTTLE_REASONS.items() if seen&bit] if reasons else None}


def start(host, folder):
    raw=SOURCE.read_bytes()
    result=host._remote('''import base64,json,sys,tempfile,uuid,subprocess
from pathlib import Path
r=Path(tempfile.gettempdir())/('strata-resource-'+uuid.uuid4().hex);r.mkdir()
code=r/'sampler.py';code.write_bytes(base64.b64decode(sys.argv[2]))
log=r/'samples.jsonl';stop=r/'stop'
p=subprocess.Popen([sys.executable,str(code),sys.argv[1],str(log),str(stop)],
 stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
 creationflags=subprocess.CREATE_NO_WINDOW|subprocess.CREATE_BREAKAWAY_FROM_JOB)
print(json.dumps({'pid':p.pid,'root':str(r),'log':str(log),'stop':str(stop)}))
''',(str(host.windows_root),base64.b64encode(raw).decode()))
    result['source_sha256']=hashlib.sha256(raw).hexdigest();save(folder/'telemetry-binding.json',result)
    return result


def finish(host, binding, folder):
    result=host._remote('''import base64,json,sys,time
from pathlib import Path
import psutil
r=Path(sys.argv[1]);pid=int(sys.argv[2]);(r/'stop').touch()
try:
 p=psutil.Process(pid)
 if str(r/'sampler.py') not in p.cmdline():raise RuntimeError('Sampler identity changed')
 p.wait(timeout=5)
except psutil.NoSuchProcess:pass
log=r/'samples.jsonl';raw=log.read_bytes() if log.exists() else b'';stopped=not psutil.pid_exists(pid)
if stopped:
 import shutil;shutil.rmtree(r,ignore_errors=True)
print(json.dumps({'raw':base64.b64encode(raw).decode(), 'sampler_stopped':stopped}))
''',(binding['root'],str(binding['pid'])))
    raw=base64.b64decode(result.pop('raw'));(folder/'telemetry.jsonl').write_bytes(raw)
    rows=[json.loads(x) for x in raw.splitlines()]
    result.update(samples=len(rows),raw_sha256=hashlib.sha256(raw).hexdigest(),interval_seconds=1,**gpu_thermal(rows))
    save(folder/'telemetry-result.json',result);return result
