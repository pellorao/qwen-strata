// Hydrogen first-batch anchors, code-standards-v5.1 (node cstd-checks.mjs <read-only copy of the pool view>)
const V = process.argv[2] + '/src/';
const out = (k, v) => console.log(k, JSON.stringify(v));
// cstd-1-118 expectation and finding: addLine pushes into the caller's order.lines (the push runs before any later check)
{
  const svc = await import(V + 'catering/catering-service.mjs');
  const order = {id: 'o1', state: 'placed', vendorId: 'v1', lines: [{menuId: 'a', servings: 1}], dietary: [], deliverAt: 10};
  const before = order.lines.length;
  try { await svc.addLine({feeds: {menu: async () => '[]'}, line: {menuId: 'b', servings: 2}, order, store: {save: async (x) => x}, taxBasisPoints: 0}); }
  catch (e) { out('addLine error (expected, empty menu)', e.message); }
  out('caller order.lines length before/after', [before, order.lines.length]);
}
// cstd-3-053 expectation and finding: placeOrder's inline suspension test equals members/suspension.mjs isSuspended
{
  const {isSuspended} = await import(V + 'members/suspension.mjs');
  const inline = (member, at) => at < (member.suspension?.expiresAt ?? at);   // catering-service.mjs:55 verbatim
  const cases = [[{}, 5], [{suspension: {expiresAt: 10}}, 5], [{suspension: {expiresAt: 10}}, 10], [{suspension: {expiresAt: 10}}, 15]];
  out('inline vs isSuspended', cases.map(([m, at]) => [inline(m, at), isSuspended(m, at)]));
}
// cstd-1-049 / cstd-1-035 expectation: a failed save (request key used) resolves undefined; their findings: the store is a class
{
  const mod = await import(V + 'catering/catering-store.mjs');
  const st = mod.createCateringStore();
  const r1 = await st.save({id: 'o1', requestKey: 'k'});
  let r2, rejected = false;
  try { r2 = await st.save({id: 'o2', requestKey: 'k'}); } catch { rejected = true; }
  out('second save with used key', {first: r1 && r1.id, second: r2, rejected, stored: (await st.list()).map((o) => o.id)});
  out('store is a class instance', {ctor: st.constructor.name, exports: Object.keys(mod)});
}
