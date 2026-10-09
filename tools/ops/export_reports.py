"""Publish version/type aggregates only. Individual runs remain in .tmp/reports."""
import hashlib, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
RAW=ROOT/'.tmp/reports'
PUBLIC=ROOT/'reports'

def read(rel):
    return json.loads((RAW/rel).read_text(encoding='utf-8-sig'))

def publish(version, kind, sources):
    if not any((RAW/rel).exists() for _,rel,_ in sources):return
    existing=PUBLIC/('v'+version)/(kind+'.json')
    preserved=json.loads(existing.read_text(encoding='utf-8-sig')).get('iq3_memory_decision') if existing.exists() and kind=='research' else None
    data=json.loads(existing.read_text(encoding='utf-8-sig')) if existing.exists() else {'version':version,'type':kind,'results':{}}
    for label,rel,transform in sources:
        if (RAW/rel).exists():data['results'][label]={'evidence_sha256':hashlib.sha256((RAW/rel).read_bytes()).hexdigest(),'statistics':standalone(transform(read(rel)))}
    if data['results']:
        if preserved:data['iq3_memory_decision']=preserved
        data.pop('retained_details',None)
        path=PUBLIC/('v'+version)/(kind+'.json');path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def standalone(x):
    if isinstance(x,dict):return {k:standalone(v) for k,v in x.items() if k not in ('raw_evidence_root','retained_details','bad_summary_continuation') and not (isinstance(v,str) and '.tmp/' in v.replace('\\','/'))}
    if isinstance(x,list):return [standalone(v) for v in x]
    return x

def identity(x):return x

def mcp(x):
    return {k:x[k] for k in ('scope','status','native_exactly_requested_calls','codex_exactly_requested_calls','native_median_wall_s','codex_median_wall_s') if k in x}|{'native_trials':len(x.get('native',[])),'codex_trials':len(x.get('codex',[])),'native_value_pass':all(r.get('value_pass',False) for r in x.get('native',[])),'codex_value_pass':all(r.get('value_pass',False) for r in x.get('codex',[]))}

def compact(x):
    return {name:{'automatic_triggered':r.get('automatic_triggered'),'manual_triggered':r.get('manual_triggered'),'selected_fact_checks':[s.get('checks',{}) for s in r.get('summaries',[])],'summary_latency_s':[s.get('approx_request_s') for s in r.get('summaries',[])]} for name,r in x.items() if isinstance(r,dict)}

def project(x):return {k:x[k] for k in ('exit_code','correct_value','actual_read','file_unchanged','pass','stop_exit_code') if k in x}

def export():
    """Export reusable WSL summaries using each input's actual version."""
    if not RAW.exists():
        print('No raw results available; existing permanent reports preserved.')
        return
    for kind in ('wsl-workflow', 'wsl-compaction', 'wsl-recovery', 'wsl-profile'):
        source = kind + '-summary.json'
        if (RAW / source).is_file():
            publish(read(source)['version'], kind, [('linux_acceptance', source, identity)])
    files = list(PUBLIC.rglob('*.json'))
    print(json.dumps({'summary_files': len(files),
                      'summary_bytes': sum(p.stat().st_size for p in files)}))

if __name__=='__main__':export()
