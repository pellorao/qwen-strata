const V = process.argv[2] + '/src/';
const out = (k, v) => console.log(k, JSON.stringify(v));
const M = 60000;
// 1. reschedule ignores 240-minute limit (expectation of cs-1-044); applyTransition mutates received history (its finding)
{
  const {rescheduleReservation} = await import(V + 'reservations/reservation-service.mjs');
  const {applyTransition} = await import(V + 'reservations/transitions.mjs');
  const start = 10 * 24 * 60 * M; // far future, slot aligned
  const res = {id: 'r1', roomId: 'room1', state: 'held', startAt: start, endAt: start + 60 * M, history: [{state: 'held', at: 0}], expiresAt: 1e15};
  const store = {list: async () => [], save: async () => {}};
  const rooms = [{id: 'room1', buildingId: 'b1', hourlyRate: 10, capacity: 4, amenities: [], active: true}];
  let r;
  try { r = await rescheduleReservation({endAt: start + 300 * M, startAt: start, now: () => M, reservation: structuredClone(res), rooms, store}); out('reschedule300', {accepted: true, minutes: (r.endAt - r.startAt) / M}); }
  catch (e) { out('reschedule300', {accepted: false, error: e.message}); }
  const input = structuredClone(res);
  applyTransition(input, 'confirm', 5);
  out('applyTransition-input-history-len', input.history.length);
}
// 2. quoteField
{
  const {quoteField} = await import(V + 'exports/csv-format.mjs');
  out('quoteField a"b"c', quoteField('a"b"c'));
}
// 3. intentRequest drops issuedAt -> fee 0 (expectation of cs-4-027); paymentStatus paid 0 (its finding)
{
  const {createPaymentIntent, paymentStatus} = await import(V + 'payments/payment-service.mjs');
  const at = 100 * 24 * 60 * M;
  const issuedAt = at - 20160 * M - M; // late
  const saved = [];
  const store = {findByRequestKey: async () => null, listByInvoice: async () => [], save: async (x) => { saved.push(x); return x; }, list: async () => saved};
  const notifier = {authorized: async () => {}};
  let intent;
  try {
    intent = await createPaymentIntent({nextId: () => 'p1', notifier, now: () => at, store,
      request: {idempotencyKey: 'k1', invoice: {id: 'inv1', memberId: 'm1', total: 1000, issuedAt, state: 'issued'}}});
    out('lateIntent', {fee: intent.fee, amount: intent.amount, expiresInMinutes: (intent.expiresAt - at) / M});
  } catch (e) { out('lateIntent-error', e.message); }
  const captured = {id: 'p2', invoiceId: 'inv1', state: 'captured', captured: 500, refunded: 0};
  const st = await paymentStatus({invoice: {id: 'inv1', issuedAt}, now: () => at, store: {list: async () => [captured]}});
  out('paymentStatus-paid-with-captured-500', st.paid);
}
// 4. hasEnded with endAt 30 s after now
{
  const {hasEnded} = await import(V + 'schedules/closures.mjs');
  out('hasEnded(+30s)', hasEnded({endAt: 1_000_000 + 30_000}, 1_000_000));
  out('hasEnded(+60s)', hasEnded({endAt: 1_000_000 + 60_000}, 1_000_000));
}
// 5. waitlist: waiting withdraw <60 min (expectation of cs-4-098); acceptOffer of expired offer (its finding)
{
  const {withdrawEntry, acceptOffer} = await import(V + 'waitlist/waitlist-service.mjs');
  const at = 1_000_000_000;
  const store = {save: async (x) => x};
  try { const w = await withdrawEntry({entry: {id: 'e1', state: 'waiting', startAt: at + 30 * M}, now: () => at, store}); out('withdraw-waiting-30min', {ok: true, state: w.state}); }
  catch (e) { out('withdraw-waiting-30min', {ok: false, error: e.message}); }
  try { const a = await acceptOffer({entry: {id: 'e2', state: 'offered', startAt: at + 300 * M, expiresAt: at - M}, now: () => at, store}); out('accept-expired-offer', {ok: true, state: a.state}); }
  catch (e) { out('accept-expired-offer', {ok: false, error: e.message}); }
}
