const base = process.argv[2];
const li = await import(base + '/billing/line-items.mjs');
const cp = await import(base + '/catering/catering-pricing.mjs');
const svc = await import(base + '/catering/catering-service.mjs');
// 21-141: extraCharges item not frozen in place
const extra = {memberId: 'm1', reservationId: 'r1', roomId: 'x', buildingId: 'b', startAt: 5, endAt: 5, kind: 'catering', amount: 10};
const out = li.buildLineItems([], {memberId: 'm1', periodStart: 0, periodEnd: 100}, [extra]);
console.log('21-141 caller object frozen?', Object.isFrozen(extra), 'same identity?', out[0] === extra);
// 9-204/23-177/14-093: invoiceCharges fields from a real-shaped order
const order = {id: 'o1', reservationId: 'r1', memberId: 'm1', buildingId: 'b', roomId: 'x', deliverAt: 50, state: 'confirmed', charge: {subtotal: 100, serviceCharge: 10}};
const ic = cp.invoiceCharges([order]);
console.log('invoiceCharges row', JSON.stringify(ic[0]));
// 21-148: cursor record absent from result set
const mk = (id, at) => ({id, deliverAt: at});
const store = {list: async () => [mk('a', 10), mk('c', 30), mk('d', 40)]};
const page = await svc.listOrders({page: {after: mk('b', 20), limit: 5}, query: {}, store});
console.log('21-148 absent cursor page', page.map((o) => o.id));
const page2 = await svc.listOrders({page: {after: 'a', limit: 5}, query: {}, store});
console.log('13-150 id cursor page', page2.map((o) => o.id));
// 19-089 concurrency: two saves with same requestKey
const st = (await import(base + '/catering/catering-store.mjs')).createCateringStore();
const r1 = await st.save({id: 'o1', requestKey: 'k'}); const r2 = await st.save({id: 'o2', requestKey: 'k'});
console.log('store saves', r1 && r1.id, r2, (await st.list()).map((o) => o.id));
