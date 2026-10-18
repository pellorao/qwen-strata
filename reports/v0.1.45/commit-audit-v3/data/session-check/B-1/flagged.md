# 标记项全文

## #15 e108 exec_command：environment or home path

```
node -e "
const ex=await import('./src/dispatch/executor.mjs');
console.log('pending-handedOver:', JSON.stringify(ex.pendingStops([{state:'handedOver'},{state:'delivered'},{state:'open'}])));
let called=false;
const out=await ex.executeAuthorizedPlan({actor:{scopes:[],depotId:'X'},route:{depotId:'X'},now:0,dispatch:()=>{called=true;return 'ran';}});
console.log('dispatch-invoked-when-unauthorized:', called, JSON.stringify(out));
const rt=await import('./src/dispatch/runtime.mjs');
console.log('emitPlanCreated:', JSON.stringify(await ex.emitPlanCreated({emitter:{emit:(e,id)=>console.log('EMIT',e,id)},input:{plan:{id:'p1'},claims:[],now:0}})));
" 2>&1 | head -20
node -e "
const s=await import('./src/dispatch/schedule.mjs');
console.log('TZ=', process.env.TZ, 'nextDispatchTime:', s.nextDispatchTime(new Date(Date.UTC(2026,0,1,2,30)), new Date(Date.UTC(2026,0,1,3,30))).toISOString());
console.log('chooseDeparture-3am:', s.chooseDeparture(new Date(Date.UTC(2026,0,1,3))).toISOString());
console.log('chooseDeparture-4am:', s.chooseDeparture(new Date(Date.UTC(2026,0,1,4))).toISOString());
const c=await import('./src/dispatch/capacity.mjs');
console.log('driverWorkload:', c.driverWorkload([{driver:'D0',reassignment:{driver:'D1'}},{driver:'D1'}],'D1'));
const t=await import('./src/dispatch/telemetry.mjs');
console.log('class-instance:', JSON.stringify(t.redactManifestEvent({auth:new (class A{constructor(){this.token='T';}})()})));
" 2>&1 | head -20
```

结果（1480 字）：

```
Chunk ID: 08c9ad
Wall time: 0.0000 seconds
Process exited with code 0
Original token count: 344
Output:
pending-handedOver: [{"state":"handedOver"},{"state":"open"}]
dispatch-invoked-when-unauthorized: true {"ok":false,"error":"forbidden"}
file:///home/pello/projects/qwen_strata/.tmp/commit-audit/v3formal/q3/runs/B/arw/.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_reviewer-cap/runs/a58b90f2-d23f-4948-835d-d96df2a011e6/ca/1/src/dispatch/storage.mjs:2
    const checked = validate(plan);
                    ^

TypeError: validate is not a function
    at savePlan (file:///home/pello/projects/qwen_strata/.tmp/commit-audit/v3formal/q3/runs/B/arw/.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_reviewer-cap/runs/a58b90f2-d23f-4948-835d-d96df2a011e6/ca/1/src/dispatch/storage.mjs:2:21)
    at Module.emitPlanCreated (file:///home/pello/projects/qwen_strata/.tmp/commit-audit/v3formal/q3/runs/B/arw/.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_reviewer-cap/runs/a58b90f2-d23f-4948-835d-d96df2a011e6/ca/1/src/dispatch/executor.mjs:15:21)
    at file:///home/pello/projects/qwen_strata/.tmp/commit-audit/v3formal/q3/runs/B/arw/.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_reviewer-cap/runs/a58b90f2-d23f-4948-835d-d96df2a011e6/ca/1/[eval1]:8:57

Node.js v24.21.0
TZ= undefined nextDispatchTime: 2026-01-01T03:30:00.000Z
chooseDeparture-3am: 2026-01-01T05:00:00.000Z
chooseDeparture-4am: 2026-01-01T05:00:00.000Z
driverWorkload: 2
class-instance: {"auth":{"token":"T"}}

```

## #22 e157 exec_command：environment/identity query

```
cat >> ".tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_commit-audit-capability/reports/review.jsonl" <<'JSONLEOF'
{"source":{"filePath":".scratch/0001-dispatch-control/spec.md","line":7},"requirement":"Stop ordering uses descending priority followed by ascending sequence.","result":"satisfied","evidence":[{"filePath":"src/dispatch/queue.mjs","lines":[[6,8]]}]}
{"source":{"filePath":".scratch/0001-dispatch-control/spec.md","line":8},"requirement":"Publication audit records include action, actor, and timestamp.","result":"satisfied","evidence":[{"filePath":"src/dispatch/publisher.mjs","lines":[[23,27]]}]}
{"source":{"filePath":".scratch/0001-dispatch-control/spec.md","line":9},"requirement":"Window membership includes both the declared start and end hour.","result":"satisfied","evidence":[{"filePath":"src/dispatch/schedule.mjs","lines":[9]}]}
{"source":{"filePath":".scratch/0001-dispatch-control/spec.md","line":10},"requirement":"Schedule offsets pass through without coercion.","result":"satisfied","evidence":[{"filePath":"src/dispatch/schedule.mjs","lines":[11]}]}
{"source":{"filePath":".scratch/0001-dispatch-control/spec.md","line":11},"requirement":"Under docs/dispatch/dispatch-policy.md, a route duration adds the travel minutes and the service time of every stop.","result":"gap","evidence":[{"filePath":"src/dispatch/queue.mjs","lines":[32]},{"filePath":"docs/dispatch/dispatch-policy.md","lines":[65]}],"finding":"routeDuration adds `stop.travelMinutes + stop.serviceMinutes` for each stop. Terms rule 32 defines a stop's service time as its `serviceMinutes` plus 5 minutes of parking, so the parking minutes are missing from every stop's contribution to the route duration."}
{"source":{"filePath":".scratch/0001-dispatch-control/spec.md","line":12},"requirement":"Under docs/dispatch/dispatch-policy.md, manifest-event redaction removes every credential nested inside authentication data.","result":"gap","evidence":[{"filePath":"src/dispatch/telemetry.mjs","lines":[7,13,14]},{"filePath":"docs/dispatch/dispatch-policy.md","lines":[[47,48]]}],"finding":"Same requirement and defect as the Gate 1 row for .scratch/0001-dispatch-control/issues/02-publish-dispatch-manifest.md line 23: stripCredentials recurses only when `value?.constructor === Object`, so credentials named token, secret or password that sit below `auth` inside an array or a non-plain object are left in place, contrary to Credentials rule 24 which requires removal at every depth."}
{"source":{"filePath":".scratch/0001-dispatch-control/spec.md","line":13},"requirement":"Empty manifests use an empty entries array and a generated marker.","result":"satisfied","evidence":[{"filePath":"src/dispatch/manifest.mjs","lines":[28]}]}
{"source":{"filePath":".scratch/0001-dispatch-control/spec.md","line":14},"requirement":"Publication failure telemetry includes the manifest ID, error, and timestamp.","result":"satisfied","evidence":[{"filePath":"src/dispatch/telemetry.mjs","lines":[5]}]}
{"source":{"filePath":".scratch/0001-dispatch-control/spec.md","line":15},"requirement":"Driver labels are trimmed without changing their letter case.","result":"satisfied","evidence":[{"filePath":"src/dispatch/normalize.mjs","lines":[5]}]}
{"source":{"filePath":".scratch/0001-dispatch-control/spec.md","line":16},"requirement":"savePlan completes validation before its first write.","result":"satisfied","evidence":[{"filePath":"src/dispatch/storage.mjs","lines":[[1,4]]}]}
{"source":{"filePath":".scratch/0001-dispatch-control/spec.md","line":17},"requirement":"Under docs/dispatch/storage-contract.md, announcement failure rolls back the manifest written earlier in the same operation.","result":"gap","evidence":[{"filePath":"src/dispatch/publisher.mjs","lines":[[12,14]]},{"filePath":"src/dispatch/manifest.mjs","lines":[32]},{"filePath":"docs/dispatch/storage-contract.md","lines":[[6,7]]}],"finding":"Same requirement and defect as the Gate 1 row for .scratch/0001-dispatch-control/issues/02-publish-dispatch-manifest.md line 22: handleAnnouncementFailure passes the new copy returned by store.get to store.remove, and the Manifest Store Contract says store.remove removes nothing unless given the exact stored object, so the manifest stored earlier in the same operation is not rolled back."}
{"source":{"filePath":".scratch/0001-dispatch-control/spec.md","line":21},"requirement":"Package IDs are trimmed, deduplicated, and sorted lexically.","result":"satisfied","evidence":[{"filePath":"src/dispatch/normalize.mjs","lines":[11]}]}
{"source":{"filePath":".scratch/0001-dispatch-control/spec.md","line":22},"requirement":"Package coalescing removes duplicate IDs across destination groups.","result":"gap","evidence":[{"filePath":"src/dispatch/manifest.mjs","lines":[13,36,37,38]},{"filePath":"src/dispatch/normalize.mjs","lines":[11]}],"finding":"Same requirement and defect as the Gate 1 row for .scratch/0001-dispatch-control/issues/02-publish-dispatch-manifest.md line 48: coalesceAcrossGroups tests normalized IDs against a `seen` set that is populated with raw untrimmed IDs, so a cross-group duplicate that only matches after trimming is kept in both groups."}
{"source":{"filePath":".scratch/0001-dispatch-control/spec.md","line":23},"requirement":"Under docs/dispatch/storage-contract.md, atomic plan writes remove temporary bytes when the rename operation fails.","result":"gap","evidence":[{"filePath":"src/dispatch/storage.mjs","lines":[9]},{"filePath":"docs/dispatch/storage-contract.md","lines":[[11,14]]}],"finding":"After store.renameTemporary rejects, the Plan Store Contract says the temporary bytes stay in place and are locked, and that while they are locked store.discardTemporary only closes the temporary write and keeps the bytes. writePlanAtomically's catch handler calls discardTemporary, so the failed rename leaves the temporary bytes in place; the contract names store.removeTemporary as the operation that deletes locked bytes."}
{"source":{"filePath":".scratch/0001-dispatch-control/spec.md","line":24},"requirement":"Under docs/dispatch/storage-contract.md, publishManifest returns, in a success result, the manifest object that store.put durably stored.","result":"gap","evidence":[{"filePath":"src/dispatch/publisher.mjs","lines":[7]},{"filePath":"src/dispatch/manifest.mjs","lines":[30]},{"filePath":"docs/dispatch/storage-contract.md","lines":[[3,4]]}],"finding":"publishManifest builds its success result from `stageManifest({manifest, store})`, and stageManifest awaits `store.put(manifest)` while discarding the value it resolves to, then returns the caller-supplied `manifest` object. The success result therefore carries the caller's object rather than the manifest object that store.put durably stored and resolved to, so the requirement's identity is not established by the staged code."}
{"source":{"filePath":".scratch/0001-dispatch-control/spec.md","line":25},"requirement":"Eligible-stop execution excludes cancelled stops.","result":"satisfied","evidence":[{"filePath":"src/dispatch/executor.mjs","lines":[12]}]}
{"source":{"filePath":".scratch/0001-dispatch-control/spec.md","line":26},"requirement":"Under docs/dispatch/dispatch-policy.md, assigning all packages accepts a total equal to the vehicle limit.","result":"gap","evidence":[{"filePath":"src/dispatch/capacity.mjs","lines":[3,12,14]},{"filePath":"docs/dispatch/dispatch-policy.md","lines":[[58,59]]},{"command":"node --input-type=module -e \"const c=await import('./src/dispatch/capacity.mjs'); console.log(c.canAssignAllPackages([{weight:10000}], 10));\"","exitCode":0}],"finding":"canAssignAllPackages delegates to withinVehicleCapacity, which accepts only when `remainingVehicleCapacity(limit * 1000, weight) > 0`, so a package total exactly equal to the vehicle limit produces remaining 0 and is rejected. The runtime check returns false for a 10000 g total (Vehicle capacity rule 28, grams) against a 10 kg limit (rule 29, kilograms)."}
{"source":{"filePath":".scratch/0001-dispatch-control/spec.md","line":27},"requirement":"The public dispatch entry exports the execution operations used by callers.","result":"gap","evidence":[{"filePath":"src/dispatch/index.mjs","lines":[[1,11]]},{"filePath":"src/dispatch/executor.mjs","lines":[4,19]}],"finding":"Same requirement and defect as the Gate 1 row for .scratch/0001-dispatch-control/issues/01-assemble-dispatch-plan.md line 7: src/dispatch/index.mjs re-exports eleven modules but not src/dispatch/executor.mjs, so the execution operations it defines are not exported by the public dispatch entry."}
{"source":{"filePath":".scratch/0001-dispatch-control/spec.md","line":28},"requirement":"Publication success telemetry includes the manifest ID and timestamp.","result":"satisfied","evidence":[{"filePath":"src/dispatch/telemetry.mjs","lines":[3]}]}
{"source":{"filePath":".scratch/0001-dispatch-control/spec.md","line":29},"requirement":"Plan previews return without touching persistent storage.","result":"satisfied","evidence":[{"filePath":"src/dispatch/storage.mjs","lines":[15]}]}
{"source":{"filePath":".scratch/0001-dispatch-control/spec.md","line":30},"requirement":"Appending a stable stop returns a new list.","result":"satisfied","evidence":[{"filePath":"src/dispatch/queue.mjs","lines":[28]}]}
{"source":{"filePath":".scratch/0001-dispatch-control/spec.md","line":31},"requirement":"Dispatch backoff is capped at 2000 milliseconds.","result":"satisfied","evidence":[{"filePath":"src/dispatch/retry.mjs","lines":[8,22]}]}
JSONLEOF
wc -l ".tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_commit-audit-capability/reports/review.jsonl"
```

结果（200 字）：

```
Chunk ID: 950a80
Wall time: 0.0000 seconds
Process exited with code 0
Original token count: 25
Output:
71 .tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_commit-audit-capability/reports/review.jsonl

```

## #28 e199 exec_command：denied/permission in result

```
node --input-type=module <<'EOF'
import {readFileSync} from 'node:fs';
import {execSync} from 'node:child_process';
const p='.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_commit-audit-capability/reports/review.jsonl';
const rows=readFileSync(p,'utf8').trim().split('\n').map(JSON.parse);
const files=new Set(); for(const r of rows) for(const e of r.evidence) if(e.filePath) files.add(e.filePath);
const staged=new Map();
for(const f of files) staged.set(f, execSync(`git show ":${f}"`,{encoding:'utf8',maxBuffer:1e7}).split('\n'));
const spot=[['src/dispatch/queue.mjs',[6,8,16,19,21,24,28,30,32,34,36]],['src/dispatch/capacity.mjs',[3,12,14,16,18,20]],['src/dispatch/access.mjs',[1,3,5,7,10,12,14,16]],['src/dispatch/publisher.mjs',[4,8,11,15,17,19,21,25,29,31]],['src/dispatch/manifest.mjs',[11,13,22,26,28,30,32,34,36,37,38,42,44]],['src/dispatch/storage.mjs',[9,15,21]],['src/dispatch/serialize.mjs',[1,3,7,9,11,13,14]],['src/dispatch/schedule.mjs',[11,13,16,18,28]],['docs/dispatch/dispatch-policy.md',[11,18,24,26,33,43,48,54,59,63,64,65,66]],['docs/dispatch/storage-contract.md',[4,7,11,14,15]],['docs/dispatch/adapter-contracts.md',[3,4,8,9]],['src/dispatch/telemetry.mjs',[3,5,7,9,13,14]],['src/dispatch/normalize.mjs',[3,5,9,11]],['src/dispatch/retry.mjs',[3,6,8,10,12,16,18,20,22,24]],['src/dispatch/executor.mjs',[4,6,12,14,17,19]],['src/dispatch/index.mjs',[1,11]]];
for(const [f,ls] of spot){const c=staged.get(f); console.log('--- '+f); for(const l of ls) console.log(l+': '+c[l-1]);}
EOF
```

结果（2228 字）：

```
Chunk ID: f83be5
Wall time: 0.0000 seconds
Process exited with code 1
Original token count: 531
Output:
node:internal/child_process:1160
    result.error = new ErrnoException(result.error, 'spawnSync ' + options.file);
                   ^

<ref *1> Error: spawnSync /bin/sh EPERM
    at Object.spawnSync (node:internal/child_process:1160:20)
    at spawnSync (node:child_process:928:24)
    at execSync (node:child_process:1009:15)
    at file:///home/pello/projects/qwen_strata/.tmp/commit-audit/v3formal/q3/runs/B/arw/.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_reviewer-cap/runs/a58b90f2-d23f-4948-835d-d96df2a011e6/ca/1/[eval1]:7:37
    at ModuleJob.run (node:internal/modules/esm/module_job:561:25)
    at process.processTicksAndRejections (node:internal/process/task_queues:104:5)
    at async node:internal/modules/esm/loader:223:26
    at async ModuleLoader.executeModuleJob (node:internal/modules/esm/loader:220:20)
    at async asyncRunEntryPointWithESMLoader (node:internal/modules/run_main:101:5) {
  errno: -1,
  code: 'EPERM',
  syscall: 'spawnSync /bin/sh',
  path: '/bin/sh',
  spawnargs: [ '-c', 'git show ":src/dispatch/index.mjs"' ],
  error: [Circular *1],
  status: 0,
  signal: null,
  output: [
    null,
    "export * from './normalize.mjs';\n" +
      "export * from './queue.mjs';\n" +
      "export * from './capacity.mjs';\n" +
      "export * from './access.mjs';\n" +
      "export * from './schedule.mjs';\n" +
      "export * from './retry.mjs';\n" +
      "export * from './serialize.mjs';\n" +
      "export * from './storage.mjs';\n" +
      "export * from './manifest.mjs';\n" +
      "export * from './publisher.mjs';\n" +
      "export * from './telemetry.mjs';\n",
    ''
  ],
  pid: 10,
  stdout: "export * from './normalize.mjs';\n" +
    "export * from './queue.mjs';\n" +
    "export * from './capacity.mjs';\n" +
    "export * from './access.mjs';\n" +
    "export * from './schedule.mjs';\n" +
    "export * from './retry.mjs';\n" +
    "export * from './serialize.mjs';\n" +
    "export * from './storage.mjs';\n" +
    "export * from './manifest.mjs';\n" +
    "export * from './publisher.mjs';\n" +
    "export * from './telemetry.mjs';\n",
  stderr: ''
}

Node.js v24.21.0

```

