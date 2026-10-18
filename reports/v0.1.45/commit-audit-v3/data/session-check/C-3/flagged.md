# 标记项全文

## #7 e40 exec_command：workdir outside root: /home/pello/projects/qwen_strata/.tmp/commit-audit/v3formal/q3/runs/C/arw/.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_reviewer-cap/runs/a1ac9352-26a3-4f5e-8189-46ed8c9e2164/_reviewer-cap/runs/a1ac9352-26a3-4f5e-831b-b2341c763358/ca/3; denied/permission in result

```
cat -n docs/dispatch/dispatch-policy.md
```

结果（141 字）：

```
exec_command failed: CreateProcess { message: "Rejected(\"Failed to create unified exec process: No such file or directory (os error 2)\")" }
```

## #26 e165 exec_command：denied/permission in result

```
node --input-type=module -e "
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
const req=JSON.parse(readFileSync('.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_commit-audit-capability/request.json','utf8'));
const p='.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_commit-audit-capability/reports/review.jsonl';
const rows=readFileSync(p,'utf8').split('\n').filter(l=>l.trim()!=='').map(l=>JSON.parse(l));
const staged=new Map();
for(const f of execFileSync('git',['diff','--cached','--name-only'],{encoding:'utf8'}).split('\n').filter(Boolean)){
  staged.set(f, execFileSync('git',['show',':'+f],{encoding:'utf8'}).split('\n'));
}
const problems=[];
const want=new Map();
for(const g of req.gate1) for(const r of g.requirements) want.set(g.issueId+'|'+r.filePath+'|'+r.line, r);
const gate2=new Set(); for(const g of req.gate2) for(const d of g.documents) gate2.add(d);
const seen=new Set();
for(const [i,o] of rows.entries()){
  const n=i+1;
  const keys=Object.keys(o);
  for(const k of ['source','requirement','result','evidence']) if(!keys.includes(k)) problems.push(n+' missing '+k);
  for(const k of keys) if(!['source','requirement','result','evidence','finding'].includes(k)) problems.push(n+' extra key '+k);
  if(!['satisfied','gap','uncertain'].includes(o.result)) problems.push(n+' bad result');
  if(o.result==='satisfied'&&'finding' in o) problems.push(n+' satisfied has finding');
  if(o.result!=='satisfied'&&!(typeof o.finding==='string'&&o.finding.length>0)) problems.push(n+' missing finding');
  if(typeof o.requirement!=='string'||o.requirement.length===0) problems.push(n+' bad requirement');
  const fp=o.source.filePath, ln=o.source.line;
  if(!Number.isInteger(ln)||ln<1) problems.push(n+' bad line');
  if(!Array.isArray(o.evidence)||o.evidence.length===0) problems.push(n+' empty evidence');
  const perFile=new Map();
  for(const e of o.evidence){
    const ek=Object.keys(e);
    if(ek.length===1&&ek[0]==='filePath'){
      if(!staged.has(e.filePath)) problems.push(n+' evidence file not staged: '+e.filePath);
      else{
        const len=staged.get(e.filePath).length;
        if(perFile.has(e.filePath)) problems.push(n+' duplicate file evidence '+e.filePath);
        perFile.set(e.filePath,true);
        const items=Array.isArray(e.lines)?e.lines:[e.lines];
        let prev=0;
        for(const it of items){
          let a,b;
          if(Number.isInteger(it)){a=it;b=it;}
          else if(Array.isArray(it)&&it.length===2&&Number.isInteger(it[0])&&Number.isInteger(it[1])&&it[0]<=it[1]){a=it[0];b=it[1];}
          else {problems.push(n+' bad lines entry '+JSON.stringify(it)); continue;}
          if(a<1||b>len) problems.push(n+' out of range '+e.filePath+' '+a+'-'+b+' len '+len);
          if(a<=prev+1&&prev!==0) problems.push(n+' unsorted or unmerged '+e.filePath+' after '+prev);
          prev=b;
        }
      }
    } else if(ek.length===1&&ek[0]==='command'){ if(typeof e.command!=='string'||!e.command.length||!Number.isInteger(e.exitCode)) problems.push(n+' bad command evidence'); }
    else problems.push(n+' bad evidence shape '+ek.join(','));
  }
  const key=(o.source.filePath.startsWith('.scratch/0001-dispatch-control/issues/')? (o.source.filePath.includes('01-')?'issue:0001:01':'issue:0001:02'):'')+'|'+o.source.filePath+'|'+o.source.line;
  if(want.has(key)){ if(!want.get(key)) problems.push(n+' duplicate gate1 row'); want.delete(key); }
  else if(gate2.has(o.source.filePath)) { if(seen.has(key)) problems.push(n+' duplicate gate2 row'); seen.add(key); }
  else problems.push(n+' row not in request scope '+o.source.filePath+':'+o.source.line);
}
for(const k of want) problems.push('missing gate1 row '+k);
// gate2 coverage of spec body lines
const spec=staged.get('.scratch/0001-dispatch-control/spec.md');
let inFence=false; const body=[];
spec.forEach((l,i)=>{const t=l.trim(); if(t.startsWith('\`\`\`')) {inFence=!inFence; return;} if(inFence) return; if(t===''||t.startsWith('#')) return; body.push(i+1);});
const covered=new Set(rows.filter(r=>r.source.filePath==='.scratch/0001-dispatch-control/spec.md').map(r=>r.source.line));
const minLines=req.gate2[0].minimumSourceLines[0].count;
console.log('spec body lines',body.length,'ceil/3',Math.ceil(body.length/3),'request min',minLines);
console.log('gate2 distinct source lines',covered.size,'missing body lines',body.filter(l=>!covered.has(l)).join(',')||'none');
console.log('gate1 rows',rows.filter(r=>r.source.filePath.includes('/issues/')).length,'gate2 rows',rows.filter(r=>r.source.filePath.endsWith('spec.md')).length);
console.log('problems',problems.length); for(const p2 of problems) console.log(' -',p2);
"
```

结果（2772 字）：

```
Chunk ID: fa6aef
Wall time: 0.0000 seconds
Process exited with code 1
Original token count: 667
Output:
node:internal/child_process:1160
    result.error = new ErrnoException(result.error, 'spawnSync ' + options.file);
                   ^

<ref *1> Error: spawnSync git EPERM
    at Object.spawnSync (node:internal/child_process:1160:20)
    at spawnSync (node:child_process:928:24)
    at execFileSync (node:child_process:971:15)
    at file:///home/pello/projects/qwen_strata/.tmp/commit-audit/v3formal/q3/runs/C/arw/.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_reviewer-cap/runs/a1ac9352-26a3-4f5e-831b-b2341c763358/ca/3/[eval1]:8:16
    at ModuleJob.run (node:internal/modules/esm/module_job:561:25)
    at async node:internal/modules/esm/loader:223:26
    at async ModuleLoader.executeModuleJob (node:internal/modules/esm/loader:220:20)
    at async asyncRunEntryPointWithESMLoader (node:internal/modules/run_main:101:5) {
  errno: -1,
  code: 'EPERM',
  syscall: 'spawnSync git',
  path: 'git',
  spawnargs: [ 'diff', '--cached', '--name-only' ],
  error: [Circular *1],
  status: 0,
  signal: null,
  output: [
    null,
    '.scratch/0001-dispatch-control/issues/01-assemble-dispatch-plan.md\n' +
      '.scratch/0001-dispatch-control/issues/02-publish-dispatch-manifest.md\n' +
      'src/dispatch/access.mjs\n' +
      'src/dispatch/capacity.mjs\n' +
      'src/dispatch/executor.mjs\n' +
      'src/dispatch/index.mjs\n' +
      'src/dispatch/manifest.mjs\n' +
      'src/dispatch/normalize.mjs\n' +
      'src/dispatch/publisher.mjs\n' +
      'src/dispatch/queue.mjs\n' +
      'src/dispatch/retry.mjs\n' +
      'src/dispatch/runtime.mjs\n' +
      'src/dispatch/schedule.mjs\n' +
      'src/dispatch/serialize.mjs\n' +
      'src/dispatch/storage.mjs\n' +
      'src/dispatch/telemetry.mjs\n' +
      'tests/dispatch/plan.test.mjs\n' +
      'tests/dispatch/publish.test.mjs\n' +
      'tests/dispatch/scenarios.mjs\n',
    ''
  ],
  pid: 9,
  stdout: '.scratch/0001-dispatch-control/issues/01-assemble-dispatch-plan.md\n' +
    '.scratch/0001-dispatch-control/issues/02-publish-dispatch-manifest.md\n' +
    'src/dispatch/access.mjs\n' +
    'src/dispatch/capacity.mjs\n' +
    'src/dispatch/executor.mjs\n' +
    'src/dispatch/index.mjs\n' +
    'src/dispatch/manifest.mjs\n' +
    'src/dispatch/normalize.mjs\n' +
    'src/dispatch/publisher.mjs\n' +
    'src/dispatch/queue.mjs\n' +
    'src/dispatch/retry.mjs\n' +
    'src/dispatch/runtime.mjs\n' +
    'src/dispatch/schedule.mjs\n' +
    'src/dispatch/serialize.mjs\n' +
    'src/dispatch/storage.mjs\n' +
    'src/dispatch/telemetry.mjs\n' +
    'tests/dispatch/plan.test.mjs\n' +
    'tests/dispatch/publish.test.mjs\n' +
    'tests/dispatch/scenarios.mjs\n',
  stderr: ''
}

Node.js v24.21.0

```

