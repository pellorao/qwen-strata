// Hydrogen first-batch anchors, commit-audit-v3 (node ca-checks.mjs <read-only copy of the pool view>)
const V = process.argv[2] + '/src/dispatch/';
const out = (k, v) => console.log(k, JSON.stringify(v));
// ca-3-007 expectation and finding: authorizeRouteBatch accepts a batch whose first route fails depot ownership
const access = await import(V + 'access.mjs');
out('batch first fails', access.authorizeRouteBatch({depotId: 'A'}, [{depotId: 'Z'}, {depotId: 'A'}]));
out('batch second fails', access.authorizeRouteBatch({depotId: 'A'}, [{depotId: 'A'}, {depotId: 'Z'}]));
out('batch all pass', access.authorizeRouteBatch({depotId: 'A'}, [{depotId: 'A'}]));
// ca-5-004 expectation: credential in an object inside an array under auth survives; finding adds null-prototype objects
const tel = await import(V + 'telemetry.mjs');
out('auth top-level token', tel.redactManifestEvent({auth: {token: 't', user: 'u'}}).auth);
out('auth array item token', tel.redactManifestEvent({auth: {keys: [{token: 't', id: 1}]}}).auth);
const np = Object.assign(Object.create(null), {secret: 's', id: 2});
out('auth null-prototype secret kept', 'secret' in tel.redactManifestEvent({auth: {inner: np}}).auth.inner);
