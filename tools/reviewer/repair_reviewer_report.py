"""Main deterministic independent-copy repair; unchanged original fallback validator."""
from pathlib import Path
import copy, hashlib, json, sys
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--batch-directory',required=True)
parser.add_argument('--name',required=True)
parser.add_argument('--continued',action='store_true')
parser.add_argument('--execution-preparation',help='Exact preparation for an arw_measure batch with per-instance result.json records.')
args=parser.parse_args()
B=Path(args.batch_directory).resolve()
import tools.reviewer.arw_measure as arw_measure
name=args.name
if args.execution_preparation:
 assert not args.continued, 'Per-instance preparation and legacy continuation are distinct bindings'
 prepared=json.loads(Path(args.execution_preparation).read_text())
 h=next(v for v in prepared['handoffs'] if v['instanceId']==name)
 f=B/name; r=json.loads((f/'result.json').read_text())
 assert r['instanceId']==name and r.get('finished_at') and r.get('stop',{}).get('status')=='stopped'
 p=Path(r['report']); assert p.resolve()==Path(h['input']['reportPath']).resolve()
 sha=hashlib.sha256(p.read_bytes()).hexdigest(); assert sha==r['report_sha256']
 original=[json.loads(s) for s in p.read_text().splitlines()]; assert len(original)==118
 corrected=copy.deepcopy(original); changes=[]
 for i,row in enumerate(corrected,1):
  for k,e in enumerate(row.get('evidence',[])):
   n=e.get('lines')
   if isinstance(n,int) and not isinstance(n,bool):
    assert n>0
    e['lines']=[n]; changes.append({'report_row':i,'evidence_index':k,'before':n,'after':[n]})
 assert changes
 back=copy.deepcopy(corrected)
 for c in changes: back[c['report_row']-1]['evidence'][c['evidence_index']]['lines']=c['before']
 assert back==original
 first=json.loads((f/'main-closed-processing/generation-binding.json').read_text())['generation']
 assert first['exit_code']==0 and first['result']['kind']=='review-output-invalid' and first['result']['phase']=='review-syntax'
 where=f/'main-mechanical-repair';where.mkdir()
 confirmation=where/'generation-confirmation';confirmation.mkdir()
 second=arw_measure.generate_original(Path(prepared['repositoryRoot']),prepared,h,confirmation)
 assert second['exit_code']==0 and second['result']==first['result']
 # The frozen ARW validates the original error and scores the independent copy.
 # Keep its exact current formatCorrection contract, rather than legacy fields.
 out=Path(h['input']['cwd'])/'.tmp/main-format-repair'/name/'review.jsonl'
 out.parent.mkdir(parents=True,exist_ok=False)
 out.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in corrected),encoding='utf-8')
 assert hashlib.sha256(p.read_bytes()).hexdigest()==sha
 value={'instanceId':name,'report_sha256':sha,'corrected_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),
  'formatCorrection':{'originalReportPath':str(p),'correctedReportPath':str(out)},
  'generationFailures':[first['result'],second['result']],'model_requests':0,'reviewer_followups':0,'report_changed':False,'changes':changes}
 (where/'result.json').write_text(json.dumps(value,indent=2)+'\n')
 print(json.dumps({'repair_count':len(changes),'records':len(original),'original_sha':sha,'binding':str(where/'result.json')}))
 sys.exit(0)
j=next(j for j in json.loads((B/'jobs.json').read_text()) if Path(j['folder']).name==name)
f=Path(j['folder']); d=json.loads(Path(j['dispatch']).read_text()); r=json.loads((f/'results.json').read_text())[0]
if args.continued:
 f=B/'premature-continuations'/name
 continued=json.loads((f/'result.json').read_text())
 assert (f/'run-finished.json').exists() and continued['ownership_returned']
 r=dict(r,report=continued['final_report_path'],report_sha256=continued['final_report_sha256'],generation=continued['generation'])
p=Path(r['report']); sha=hashlib.sha256(p.read_bytes()).hexdigest(); assert sha==r['report_sha256']
original=[json.loads(s) for s in p.read_text().splitlines()]; assert len(original)==118
corrected=copy.deepcopy(original); changes=[]
for i,row in enumerate(corrected,1):
 for k,e in enumerate(row.get('evidence',[])):
  n=e.get('lines')
  if isinstance(n,int) and not isinstance(n,bool):
   assert n>0
   e['lines']=[n]; changes.append({'report_row':i,'evidence_index':k,'before':n,'after':[n]})
assert changes
back=copy.deepcopy(corrected)
for c in changes: back[c['report_row']-1]['evidence'][c['evidence_index']]['lines']=c['before']
assert back==original
where=f/'main-mechanical-repair'; where.mkdir()
a=where/'generation-confirmation'; a.mkdir()
gen=arw_measure.generate_original(Path(d['repositoryRoot']),d,d['handoffs'][0],a)
first=r['generation']['result'] if r.get('generation') else json.loads((f/'main-initial-diagnostic/generation-1/generation-result.json').read_text())
second=gen['result']; assert first==second and first['kind']=='review-output-invalid'
assert gen['exit_code']==0 and first['status']=='failed'
scenario=Path(d['generations'][0]['workdir']); out=scenario/('.tmp/main-continuation-format-repair/review.jsonl' if args.continued else '.tmp/main-initial-format-repair/review.jsonl')
out.parent.mkdir(parents=True,exist_ok=False)
out.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in corrected))
fallback={'originalReviewPath':str(p),'correctedReviewPath':str(out),'switchReason':'Main-only deterministic scalar line-number wrapping; no Reviewer revision, no inferred evidence, original bound report and failure preserved. Two original generation validations of the same unchanged draft retain real ordered syntax failures.','generationFailures':[first,second]}
assert hashlib.sha256(p.read_bytes()).hexdigest()==sha
value={'instanceId':j['instanceId'],'report_sha256':sha,'corrected_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'artifactPaths':None,'fallback':fallback,'model_requests':0,'reviewer_followups':0,'report_changed':False,'changes':changes}
(where/'result.json').write_text(json.dumps(value,indent=2)+'\n')
reference=json.loads((B/'high-1/main-finding-check/main-finding-check.json').read_text())
for rel,h in reference['scenario_source_sha256'].items(): assert hashlib.sha256((scenario/rel).read_bytes()).hexdigest()==h
findings=sum(x.get('result') in ('gap','uncertain') for x in original)
print(json.dumps({'repair_count':len(changes),'records':len(original),'findings':findings,'original_sha':sha,'binding':str(where/'result.json')}))
