"""Use the unchanged upstream single-completed-repetition diagnostic endpoint."""
from pathlib import Path
import hashlib,json,sys,subprocess
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--batch-directory',required=True)
parser.add_argument('--name',required=True)
args=parser.parse_args()
B=Path(args.batch_directory).resolve();R=Path(__file__).resolve().parents[2];name=args.name;F=B/'premature-continuations'/name
j=next(j for j in json.loads((B/'jobs.json').read_text()) if Path(j['folder']).name==name)
r=json.loads((F/'result.json').read_text());assert (F/'run-finished.json').exists() and r['ownership_returned']
assert hashlib.sha256(Path(r['final_report_path']).read_bytes()).hexdigest()==r['final_report_sha256']
g=r['generation'];assert g['exit_code']==0 and g['result'].get('status')!='failed' and g['result']['files']
d=json.loads(Path(j['dispatch']).read_text());root=Path(d['generations'][0]['workdir']);paths=[str(root/f['sourcePath']) for f in g['result']['files']];assert all(Path(p).is_file() for p in paths)
w=F/'main-scoring';w.mkdir(exist_ok=False)
a=w/'artifacts.json';a.write_text(json.dumps({'artifacts':[{'reviewerId':'commit-audit-reviewer','instances':[{'instanceId':j['instanceId'],'artifactPaths':paths}]}]},indent=2)+'\n')
i={'repositoryRoot':d['repositoryRoot'],'identity':d['identity'],'preparedPath':d['preparedPath'],'artifactsPath':str(a),'options':{}}
(w/'input.json').write_text(json.dumps(i,indent=2)+'\n')
(w/'binding.json').write_text(json.dumps({'instanceId':j['instanceId'],'effort':json.loads((F/'initial-preservation/results.json').read_text())[0]['selection']['effort'],'measurement_repeat':j['repetition'],'original_prepared_repeat':int(j['instanceId'].rsplit('-',1)[1]),'preparedPath':d['preparedPath'],'prepared_sha256':hashlib.sha256(Path(d['preparedPath']).read_bytes()).hexdigest(),'initial_report_sha256':r['initial_report_sha256'],'continued_report_sha256':r['final_report_sha256'],'artifact_sha256':{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths},'only_actual_completed_repeat_selected':True,'other_repeats_omitted_not_zeroed':True,'formal_status_failure_retained':r['terminal_kind']},indent=2)+'\n')
subprocess.run(['node',str(R/'tools/reviewer/arw_native.mjs'),'score-completed',str(w/'input.json'),str(w/'pending.json')],check=True)
p=json.loads((w/'pending.json').read_text());print(json.dumps({'status':p.get('status'),'candidates':len(p.get('candidates',[])),'binding_requests':len(p.get('bindingRequests',[]))}))
