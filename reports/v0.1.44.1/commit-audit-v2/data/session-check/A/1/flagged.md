# 标记项全文

## #17 e102 exec_command：environment/identity query

```
set -e
node --input-type=module -e 'import("./src/dispatch/index.mjs").then(m=>console.log("executeAuthorizedPlan" in m, "emitPlanCreated" in m, "runEligibleStops" in m, "executeDryRun" in m, "planFailure" in m))' && \
node --input-type=module -e 'import("./src/dispatch/executor.mjs").then(async m=>{let c=0;const r=await m.executeAuthorizedPlan({actor:{scopes:[],depotId:"D1"},route:{depotId:"D2"},dispatch:()=>{c+=1;return 1}});console.log("dispatchCalls="+c,JSON.stringify(r))})' && \
node --input-type=module -e 'import("./src/dispatch/schedule.mjs").then(m=>console.log(m.departureWindow.hourOf(new Date("2026-01-01T00:30:00Z")),m.chooseDeparture(new Date("2026-01-01T00:30:00Z"))))' && \
node --input-type=module -e 'import("./src/dispatch/executor.mjs").then(async m=>{const o=[];await m.emitPlanCreated({emitter:{emit:()=>o.push("emit")},input:{plan:{id:"P1"},store:{write:async()=>o.push("write")},validate:()=>({ok:true})}});console.log(o.join(","))})' && \
node --input-type=module -e 'import("./src/dispatch/queue.mjs").then(m=>console.log(m.hasDuplicateRouteKeys([{routeKey:"a"},{routeKey:"A"}])))' && \
node --input-type=module -e 'import("./src/dispatch/retry.mjs").then(m=>console.log(JSON.stringify(m.parseRetryCount(3)),JSON.stringify(m.parseRetryCount(2))))' && \
node --input-type=module -e 'import("./src/dispatch/queue.mjs").then(m=>{const s=[{priority:1,sequence:2},{priority:9,sequence:1}];m.createDispatchPlan({stops:s,claims:[],now:0});console.log(s.map(x=>x.sequence).join(","))})' && \
node --input-type=module -e 'import("./src/dispatch/capacity.mjs").then(m=>console.log(m.withinVehicleCapacity(10,10),m.canAssignAllPackages([{weight:4},{weight:6}],10)))' && \
node --input-type=module -e 'import("./src/dispatch/access.mjs").then(m=>console.log(m.canPlanRoute({scopes:["routes:plan"],depotId:"D1"},{depotId:"D2"}),m.canPlanRoute({scopes:[],depotId:"D1"},{depotId:"D1"})))' && \
node --input-type=module -e 'import("./src/dispatch/serialize.mjs").then(m=>console.log(JSON.stringify(m.serializePlan({a:1}))))'
echo "chain-exit=$?"
```

结果（309 字）：

```
Chunk ID: 144681
Wall time: 0.0394 seconds
Process exited with code 0
Original token count: 52
Output:
false false false false false
dispatchCalls=1 {"ok":false,"error":"forbidden"}
9 null
emit,write
false
{"ok":false,"value":3} {"ok":true,"value":2}
1,2
false false
true true
"{\n  \"a\": 1\n}"
chain-exit=0

```

## #18 e109 exec_command：environment/identity query

```
set -e
node --input-type=module -e 'import("./src/dispatch/publisher.mjs").then(async m=>{const ops=[];const r=await m.publishManifest({manifest:{entries:[{packageId:"  "}]},store:{put:async()=>ops.push("put")}});console.log(ops.join(","),JSON.stringify(r))})' && \
node --input-type=module -e 'import("./src/dispatch/publisher.mjs").then(async m=>{const ops=[];const store={put:async()=>ops.push("put"),remove:async()=>ops.push("remove")};const r=await m.publishWithAnnouncement({announcer:{send:async()=>{throw new Error("down")}},manifest:{id:"M1"},store});console.log(ops.join(","),JSON.stringify(r))})' && \
node --input-type=module -e 'import("./src/dispatch/publisher.mjs").then(async m=>{let n=0;try{await m.publishWithRetry({manifest:{entries:[{packageId:"x"}]},store:{put:async()=>{n+=1;const e=new Error("boom");e.transient=false;throw e}}})}catch(err){console.log("attempts="+n,err.message)}})' && \
node --input-type=module -e 'import("./src/dispatch/manifest.mjs").then(m=>console.log(m.orderManifestGroups([{destination:"B"},{destination:"A"},{destination:"C"}]).map(g=>g.destination).join(",")))' && \
node --input-type=module -e 'import("./src/dispatch/serialize.mjs").then(m=>console.log(JSON.stringify(m.serializeManifestRecords([{a:1},{b:2}]))))' && \
node --input-type=module -e 'import("./src/dispatch/manifest.mjs").then(m=>console.log(JSON.stringify(m.coalescePackages([{destination:"A",packageIds:["P1","P1"]},{destination:"B",packageIds:["P1","P2"]}]).map(g=>g.packageIds))))' && \
node --input-type=module -e 'import("./src/dispatch/telemetry.mjs").then(m=>console.log(JSON.stringify(m.redactManifestEvent({event:"e",auth:{driver:{token:"SECRET"}}}))))'
echo "chain-exit=$?"
```

结果（334 字）：

```
Chunk ID: 0ec109
Wall time: 0.0292 seconds
Process exited with code 0
Original token count: 58
Output:
put {"ok":false,"error":"invalid-manifest"}
put {"ok":false,"error":"Error: down","manifestId":"M1"}
attempts=2 boom
C,B,A
"{\"a\":1}\n{\"b\":2}"
[["P1"],["P1","P2"]]
{"event":"e","auth":{"driver":{"token":"SECRET"}}}
chain-exit=0

```

## #20 e123 exec_command：environment/identity query

```
set -e
node --input-type=module -e 'import("./src/dispatch/storage.mjs").then(async m=>{let removed=false;try{await m.writePlanAtomically({bytes:"b",store:{writeTemporary:async()=>{},renameTemporary:async()=>{throw new Error("rename-fail")},removeTemporary:async()=>{removed=true}}})}catch(err){console.log("temporaryRemoved="+removed,err.message)}})' && \
node --input-type=module -e 'import("./src/dispatch/access.mjs").then(m=>console.log(m.authorizeRouteBatch({depotId:"D1"},[{depotId:"D1"},{depotId:"D2"}]),m.scopeAllowsPlan("routes:planning")))' && \
node --input-type=module -e 'import("./src/dispatch/retry.mjs").then(m=>console.log(m.retryAfterDelay(500),m.retryAfterDelay(5000)))' && \
node --input-type=module -e 'import("./src/dispatch/normalize.mjs").then(m=>console.log(JSON.stringify(m.formatRouteToken({routeKey:"\uFF21B",destination:"x"})),JSON.stringify(m.normalizeRouteKey("\uFF21B"))))' && \
node --input-type=module -e 'import("./src/dispatch/queue.mjs").then(m=>{const s=[{priority:1,sequence:2},{priority:9,sequence:1}];m.partitionUrgentStops(s);console.log(s.length,s.map(x=>x.sequence).join(","))})' && \
node --input-type=module -e 'import("./src/dispatch/serialize.mjs").then(m=>console.log(JSON.stringify(m.toStableJson({a:{z:1,y:2}}))))'
echo "chain-exit=$?"
```

结果（242 字）：

```
Chunk ID: 30cf31
Wall time: 0.0000 seconds
Process exited with code 0
Original token count: 36
Output:
temporaryRemoved=false rename-fail
true true
2000 5000
"X:ＡB" "AB"
1 2
"{\n  \"a\": {\n    \"z\": 1,\n    \"y\": 2\n  }\n}\n"
chain-exit=0

```

