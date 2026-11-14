// Hydrogen first-batch anchors, code-spec-v5 (node cs-checks.mjs <read-only copy of the pool view>)
const V = process.argv[2] + '/src/';
const out = (k, v) => console.log(k, JSON.stringify(v));
const M = 60000;
// cs-2-121 expectation and finding: a confirmed reservation starting exactly at the month start is not counted
{
  const {allowanceSummary} = await import(V + 'members/allowance.mjs');
  const start = Date.UTC(2026, 10, 1), end = Date.UTC(2026, 11, 1);
  const rs = [
    {id: 'r0', memberId: 'm1', state: 'confirmed', startAt: start, endAt: start + 60 * M},
    {id: 'r1', memberId: 'm1', state: 'confirmed', startAt: start + 60 * M, endAt: start + 120 * M},
  ];
  const s = allowanceSummary({memberId: 'm1', tier: 'basic'}, rs, {startAt: start, endAt: end});
  out('allowance month-start', {used: s.used, reservationIds: s.reservationIds});
}
// cs-1-057 expectation and finding: a keyed event recorded in another building is not found, the event is recorded again
{
  const {recordBadgeEvent} = await import(V + 'badges/badge-service.mjs');
  const {createBadgeStore} = await import(V + 'badges/badge-store.mjs');
  const store = createBadgeStore();
  const readers = [{id: 'rd1', buildingId: 'b1', active: true}, {id: 'rd2', buildingId: 'b2', active: true}];
  let n = 0; const nextId = () => `e${++n}`;
  const notifier = {anomaly: async () => {}};
  const at = 1_000_000_000;
  const first = await recordBadgeEvent({event: {buildingId: 'b1', memberId: 'm1', readerId: 'rd1', direction: 'in', at, eventKey: 'K'}, nextId, notifier, now: () => at, readers, store});
  const second = await recordBadgeEvent({event: {buildingId: 'b2', memberId: 'm1', readerId: 'rd2', direction: 'in', at, eventKey: 'K'}, nextId, notifier, now: () => at, readers, store});
  out('same key, other building', {first: first.id, second: second.id, stored: (await store.list()).map((e) => e.id)});
  const third = await recordBadgeEvent({event: {buildingId: 'b1', memberId: 'm1', readerId: 'rd1', direction: 'in', at, eventKey: 'K'}, nextId, notifier, now: () => at, readers, store});
  out('same key, same building', {third: third.id});
}
// cs-1-105 / cs-1-090 expectation: waiting withdraw <60 min refused; their findings: acceptOffer of an expired offer accepted
{
  const {withdrawEntry, acceptOffer} = await import(V + 'waitlist/waitlist-service.mjs');
  const at = 1_000_000_000;
  const store = {save: async (x) => x};
  try { const w = await withdrawEntry({entry: {id: 'e1', state: 'waiting', startAt: at + 30 * M}, now: () => at, store}); out('withdraw-waiting-30min', {ok: true, state: w.state}); }
  catch (e) { out('withdraw-waiting-30min', {ok: false, error: e.message}); }
  try { const a = await acceptOffer({entry: {id: 'e2', state: 'offered', startAt: at + 300 * M, expiresAt: at - M}, now: () => at, store}); out('accept-expired-offer', {ok: true, state: a.state}); }
  catch (e) { out('accept-expired-offer', {ok: false, error: e.message}); }
}
