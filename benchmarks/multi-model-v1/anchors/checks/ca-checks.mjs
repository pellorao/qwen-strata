const V = process.argv[2] + '/src/dispatch/';
const out = (k, v) => console.log(k, JSON.stringify(v));
const access = await import(V + 'access.mjs');
// ca-21-062 expectation: suspended actor with active routes:plan claim can plan
out('suspended+claim canPlanRoute', access.canPlanRoute({suspended: true, scopes: ['routes:plan'], depotId: 'A', claims: [{scope: 'routes:plan', startsAt: 0, expiresAt: 100}]}, {depotId: 'A'}, 50));
out('suspended no claim canPlanRoute', access.canPlanRoute({suspended: true, scopes: ['routes:plan'], depotId: 'A', claims: []}, {depotId: 'A'}, 50));
// ca-7-099 expectation: retryAfter 0 -> backoff
const retry = await import(V + 'retry.mjs');
out('nextRetryDelay(0, 0)', retry.nextRetryDelay(0, 0));
out('nextRetryDelay(0, 1)', retry.nextRetryDelay(0, 1));
// ca-19-005 expectation: publishManifest stores invalid manifest
const pub = await import(V + 'publisher.mjs');
const man = await import(V + 'manifest.mjs');
{
  const stored = [];
  const store = {put: async (m) => { stored.push(m); return m; }};
  const r = await pub.publishManifest({manifest: {id: 'm1', entries: [{}]}, store});
  out('manifestEntryIsValid({})', man.manifestEntryIsValid({}));
  out('publishManifest invalid entry', {ok: r.ok, stored: stored.length});
}
// ca-8-066 expectation: pendingStops returns handedOver
const ex = await import(V + 'executor.mjs');
out('pendingStops', ex.pendingStops([{id: 'a', state: 'delivered'}, {id: 'b', state: 'handedOver'}, {id: 'c', state: 'queued'}]).map((s) => s.id));
// ca-17-068 expectation vs finding: authorizeRouteBatch
out('batch first fails', access.authorizeRouteBatch({depotId: 'A'}, [{depotId: 'Z'}, {depotId: 'A'}]));
out('batch second fails', access.authorizeRouteBatch({depotId: 'A'}, [{depotId: 'A'}, {depotId: 'Z'}]));
out('batch all pass', access.authorizeRouteBatch({depotId: 'A'}, [{depotId: 'A'}]));
// ca-35-033 expectation: handleAnnouncementFailure removes get copy, stored manifest not removed; no removeTemporary call
{
  const db = new Map(); const calls = [];
  const store = {
    put: async (m) => { db.set(m.id, m); return m; },
    get: async (id) => (db.has(id) ? structuredClone(db.get(id)) : undefined),
    remove: async (m) => { calls.push('remove'); if (db.get(m.id) === m) db.delete(m.id); },
    removeTemporary: async () => { calls.push('removeTemporary'); },
  };
  const r = await pub.publishWithAnnouncement({announcer: {send: async () => { throw new Error('down'); }}, manifest: {id: 'm1', entries: []}, store});
  out('announce failure', {ok: r.ok, stillStored: db.has('m1'), storeCalls: calls});
}
