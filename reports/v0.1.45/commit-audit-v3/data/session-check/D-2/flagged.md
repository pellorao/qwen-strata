# 标记项全文

## #13 e74 exec_command：outside root: /tmp/probe1.mjs; outside root: /tmp/probe1.mjs

```
cat > /tmp/probe1.mjs <<'EOF'
import { withSortedKeys, toStableJson, serializePlan } from './src/dispatch/serialize.mjs';
const a = {b: {x: 1, y: 2}, a: 1};
const b = {a: 1, b: {y: 2, x: 1}};
console.log('nested-order-equal:', toStableJson(a) === toStableJson(b));
console.log(JSON.stringify(withSortedKeys({b:{x:1},a:{p:1,q:2}}), null, 2));
EOF
node /tmp/probe1.mjs
```

结果（892 字）：

```
Chunk ID: 58f144
Wall time: 0.0000 seconds
Process exited with code 1
Original token count: 197
Output:
/bin/bash: line 1: /tmp/probe1.mjs: Read-only file system
node:internal/modules/cjs/loader:1568
  throw err;
  ^

Error: Cannot find module '/tmp/probe1.mjs'
    at Module._resolveFilename (node:internal/modules/cjs/loader:1564:15)
    at wrapResolveFilename (node:internal/modules/cjs/loader:1118:27)
    at defaultResolveImplForCJSLoading (node:internal/modules/cjs/loader:1142:10)
    at resolveForCJSWithHooks (node:internal/modules/cjs/loader:1169:12)
    at Module._load (node:internal/modules/cjs/loader:1341:5)
    at wrapModuleLoad (node:internal/modules/cjs/loader:261:19)
    at Module.executeUserEntryPoint [as runMain] (node:internal/modules/run_main:154:5)
    at node:internal/main/run_main_module:33:47 {
  code: 'MODULE_NOT_FOUND',
  requireStack: []
}

Node.js v24.21.0

```

## #14 e75 exec_command：outside root: /tmp/probe2.mjs; outside root: /tmp/probe2.mjs

```
cat > /tmp/probe2.mjs <<'EOF'
import { nextRetryDelay, parseRetryCount } from './src/dispatch/retry.mjs';
import { canAssignAllPackages, withinVehicleCapacity, splitOverweightStops } from './src/dispatch/capacity.mjs';
import { chooseDeparture } from './src/dispatch/schedule.mjs';
import { hasDuplicateRouteKeys, stopsForDriver, orderedDestinationGroups } from './src/dispatch/queue.mjs';
import { executeAuthorizedPlan } from './src/dispatch/executor.mjs';
import * as index from './src/dispatch/index.mjs';
console.log('nextRetryDelay(1,0)=', nextRetryDelay(1, 0));
console.log('parseRetryCount("")', JSON.stringify(parseRetryCount('')), 'null', JSON.stringify(parseRetryCount(null)), '"+1"', JSON.stringify(parseRetryCount('+1')), '"1.0"', JSON.stringify(parseRetryCount('1.0')), 'true', JSON.stringify(parseRetryCount(true)));
console.log('canAssignAllPackages equal:', canAssignAllPackages([{weight: 10000}], 10), 'within(10,10):', withinVehicleCapacity(10, 10));
const d = new Date(Date.UTC(2026, 0, 5, 3));
console.log('chooseDeparture hour3 ->', chooseDeparture(d).toISOString());
console.log('dup collision:', hasDuplicateRouteKeys([{depotId: 'A', routeKey: 'BC', state: 'open'}, {depotId: 'AB', routeKey: 'C', state: 'open'}]));
console.log('stopsForDriver reassign:', stopsForDriver([{driver: 'X', reassignment: {driver: 'Y'}}], 'Y'));
console.log('orderedDestinationGroups:', JSON.stringify(orderedDestinationGroups([{destination: 'B'}, {destination: 'A'}])));
let invoked = 0;
const r = await executeAuthorizedPlan({actor: {scopes: [], depotId: 'D1'}, route: {depotId: 'D2'}, now: 0, dispatch: () => { invoked += 1; return 'ran'; }});
console.log('unauthorized dispatch invoked:', invoked, JSON.stringify(r));
console.log('index exports executeAuthorizedPlan?', 'executeAuthorizedPlan' in index, 'runEligibleStops?', 'runEligibleStops' in index, 'dispatchRoute?', 'dispatchRoute' in index, 'canPlanRoute?', 'canPlanRoute' in index);
console.log('splitOverweightStops equal:', JSON.stringify(splitOverweightStops([{weight: 10}], 10)));
EOF
node /tmp/probe2.mjs
```

结果（892 字）：

```
Chunk ID: df8859
Wall time: 0.0000 seconds
Process exited with code 1
Original token count: 197
Output:
/bin/bash: line 1: /tmp/probe2.mjs: Read-only file system
node:internal/modules/cjs/loader:1568
  throw err;
  ^

Error: Cannot find module '/tmp/probe2.mjs'
    at Module._resolveFilename (node:internal/modules/cjs/loader:1564:15)
    at wrapResolveFilename (node:internal/modules/cjs/loader:1118:27)
    at defaultResolveImplForCJSLoading (node:internal/modules/cjs/loader:1142:10)
    at resolveForCJSWithHooks (node:internal/modules/cjs/loader:1169:12)
    at Module._load (node:internal/modules/cjs/loader:1341:5)
    at wrapModuleLoad (node:internal/modules/cjs/loader:261:19)
    at Module.executeUserEntryPoint [as runMain] (node:internal/modules/run_main:154:5)
    at node:internal/main/run_main_module:33:47 {
  code: 'MODULE_NOT_FOUND',
  requireStack: []
}

Node.js v24.21.0

```

