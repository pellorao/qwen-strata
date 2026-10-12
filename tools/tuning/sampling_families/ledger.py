"""ledger: implement settlement for a long, multi-rule account specification (hidden tests cover the edge cases).

Level 4 is the full v4 rule set: ordering, opening, overdraft, a percentage withdrawal fee with a floor, a daily cap
(large withdrawals counted double), freezing, a fee waiver, reversals, interest and overdraft charges, closing, and
holds that reserve money until they are captured, released or expire, checked against the available balance
(balance minus active holds) while interest and the fee waiver still use the balance.  Level 5 adds linked backup
accounts: a withdrawal that would take the available balance below zero first sweeps the shortfall in from the
backup, limited by a per-sweep maximum and by the backup's own available balance (no overdraft), freezing and daily
cap, and the overdraft allowance only covers what is left.  Level 6 also sweeps for outgoing transfers and holds
and charges the backup a sweep fee.  (`tier` in this module is the level.)
"""
import math

DAY = 86400
ACCOUNTS = ['ana', 'bo', 'cy', 'dee', 'eli', 'fay', 'gus']


def rules(rng, tier):
    return {'tier': tier, 'tie': rng.choice(['ascending', 'descending']), 'overdraft': rng.choice([0, 100, 250]),
            'fee': rng.randint(1, 4) * 25, 'cap': rng.choice([800, 1000, 1500]),
            'waiver': rng.choice([2000, 3000, 5000]), 'rate': rng.choice([50, 125, 200]),
            'charge': rng.choice([300, 500, 1000]), 'large': rng.choice([400, 500, 600]),
            'fee_bp': rng.choice([100, 150, 250]), 'expiry': rng.choice([1, 2]),
            'sweep_max': rng.choice([300, 500, 800]) if tier >= 5 else None,
            'sweep_fee': rng.choice([10, 20, 35]) if tier >= 6 else None}


def settle(events, r):
    """Reference implementation of the specification `describe(r)` prints."""
    tier = r['tier']
    order = sorted(events, key=lambda e: (e['t'], e['id'] if r['tie'] == 'ascending' else -e['id']))
    balance, overdraft, frozen, closed, fees, rejected = {}, {}, set(), set(), 0, []
    spent, done = {}, {}  # (account, day) -> capped amount; id -> accepted reversible event with its fee
    holds = {}  # id -> (account, amount, time placed); dropped once captured, released or expired
    backup = {}  # account -> its linked backup account

    def live(a):
        return a in balance and a not in closed

    def fee_of(amount):
        return max(r['fee'], math.ceil(amount * r['fee_bp'] / 10000))

    def positive(e):
        return isinstance(e.get('amount'), int) and not isinstance(e.get('amount'), bool) and e['amount'] > 0

    def held(a, now):
        return sum(x for b, x, t in holds.values() if b == a and now < t + r['expiry'] * DAY)

    def active_hold(h, now):
        return h in holds and now < holds[h][2] + r['expiry'] * DAY

    def sweep(a, need, now, day, skip=None):
        """The (amount, fee) the backup of `a` sends so that a's available balance covers `need`; (0, 0) if none."""
        b = backup.get(a)
        short = need - (balance[a] - held(a, now))
        if tier < 5 or short <= 0 or b is None or b == skip or not live(b) or b in frozen:
            return 0, 0
        cost = r['sweep_fee'] if tier >= 6 else 0
        amount = min(short, r['sweep_max'], balance[b] - held(b, now) - cost, r['cap'] - spent.get((b, day), 0))
        return (amount, cost) if amount > 0 else (0, 0)

    def apply_sweep(a, moved, day):
        nonlocal fees
        amount, cost = moved
        if amount:
            b = backup[a]
            balance[b] -= amount + cost
            balance[a] += amount
            fees += cost
            spent[(b, day)] = spent.get((b, day), 0) + amount

    for e in order:
        op, ok = e['op'], False
        day, now = e['t'] // DAY, e['t']
        if op == 'open':
            a = e['acct']
            ok = a not in balance
            if ok:
                balance[a], overdraft[a] = 0, e.get('overdraft', r['overdraft'])
        elif op == 'deposit':
            ok = live(e['acct']) and positive(e)
            if ok:
                balance[e['acct']] += e['amount']
                done[e['id']] = (e, 0)
        elif op == 'withdraw':
            a = e['acct']
            if live(a) and positive(e) and a not in frozen:
                amount = e['amount']
                fee = 0 if balance[a] >= r['waiver'] else fee_of(amount)
                counted = amount * (2 if amount > r['large'] else 1)
                moved = sweep(a, amount + fee, now, day)
                ok = balance[a] + moved[0] - held(a, now) - amount - fee >= -overdraft[a] and \
                    spent.get((a, day), 0) + counted <= r['cap']
                if ok:
                    apply_sweep(a, moved, day)
                    balance[a] -= amount + fee
                    fees += fee
                    spent[(a, day)] = spent.get((a, day), 0) + counted
                    done[e['id']] = (e, fee)
        elif op == 'transfer':
            a, b = e['from'], e['to']
            if live(a) and live(b) and a != b and positive(e) and a not in frozen:
                amount = e['amount']
                moved = sweep(a, amount, now, day, skip=b) if tier >= 6 else (0, 0)
                ok = balance[a] + moved[0] - held(a, now) - amount >= -overdraft[a] and \
                    spent.get((a, day), 0) + amount <= r['cap']
                if ok:
                    apply_sweep(a, moved, day)
                    balance[a] -= amount
                    balance[b] += amount
                    spent[(a, day)] = spent.get((a, day), 0) + amount
                    done[e['id']] = (e, 0)
        elif op in ('freeze', 'unfreeze'):
            a = e['acct']
            ok = live(a) and ((a in frozen) == (op == 'unfreeze'))
            if ok:
                (frozen.add if op == 'freeze' else frozen.discard)(a)
        elif op == 'reverse':
            target = done.get(e.get('target'))
            if target:
                t, fee = target
                if t['op'] == 'deposit':
                    moves = {t['acct']: -t['amount']}
                elif t['op'] == 'withdraw':
                    moves = {t['acct']: t['amount'] + fee}
                else:
                    moves = {t['from']: t['amount'], t['to']: -t['amount']}
                ok = all(live(a) for a in moves) and \
                    all(balance[a] - held(a, now) + v >= -overdraft[a] for a, v in moves.items())
                if ok:
                    for a, v in moves.items():
                        balance[a] += v
                    fees -= fee
                    del done[e['target']]
        elif op == 'interest':
            ok = True
            for a in sorted(balance):
                if not live(a):
                    continue
                if balance[a] > 0:
                    balance[a] += balance[a] * r['rate'] // 10000
                elif balance[a] < 0:
                    charge = math.ceil(-balance[a] * r['charge'] / 10000)
                    balance[a] -= charge
                    fees += charge
        elif op == 'close':
            a = e['acct']
            ok = live(a) and balance[a] == 0 and a not in frozen and not held(a, now)
            if ok:
                closed.add(a)
        elif op == 'hold':
            a = e['acct']
            if live(a) and positive(e) and a not in frozen:
                moved = sweep(a, e['amount'], now, day) if tier >= 6 else (0, 0)
                ok = balance[a] + moved[0] - held(a, now) - e['amount'] >= -overdraft[a]
                if ok:
                    apply_sweep(a, moved, day)
                    holds[e['id']] = (a, e['amount'], now)
        elif op == 'capture':
            h = e.get('target')
            if active_hold(h, now) and live(holds[h][0]) and holds[h][0] not in frozen:
                a, amount, _ = holds[h]
                fee = 0 if balance[a] >= r['waiver'] else fee_of(amount)
                counted = amount * (2 if amount > r['large'] else 1)
                ok = balance[a] - (held(a, now) - amount) - amount - fee >= -overdraft[a] and \
                    spent.get((a, day), 0) + counted <= r['cap']
                if ok:
                    del holds[h]
                    balance[a] -= amount + fee
                    fees += fee
                    spent[(a, day)] = spent.get((a, day), 0) + counted
        elif op == 'release':
            ok = active_hold(e.get('target'), now)
            if ok:
                del holds[e['target']]
        elif op == 'link' and tier >= 5:
            a, b = e['acct'], e.get('backup')
            ok = live(a) and live(b) and a != b
            if ok:
                backup[a] = b
        if not ok:
            rejected.append(e['id'])
    return {'balances': {a: v for a, v in sorted(balance.items()) if a not in closed}, 'rejected': rejected,
            'fees': fees}

def describe(r):
    tier = r['tier']
    fee = f'max({r["fee"]}, ceil(amount * {r["fee_bp"]} / 10000))'
    days = 'one day' if r['expiry'] == 1 else f'{r["expiry"]} days'
    lines = [
        'Each event is a dict with an integer `id` (unique), an integer time `t` in seconds, and `op`. The list is '
        f'NOT in order: process events by `t` ascending, and events with equal `t` by `id` {r["tie"]}.',
        'Amounts are integer cents. A deposit, withdrawal, transfer or hold whose `amount` is missing, not an int (a '
        'bool is not an int), or not positive is rejected; the other ops carry no amount and this rule does not '
        'apply to them.',
        '`{"op": "open", "acct": A}` (optionally with `"overdraft": N`, which is always a non-negative int and is '
        f'used as given) opens account A with balance 0 and overdraft allowance N (default {r["overdraft"]}). '
        'Opening an account that was already opened is rejected (also after it was closed).',
        'Every other event that names an account that is not open at that point is rejected.',
        '`{"op": "deposit", "acct": A, "amount": X}` adds X.',
        f'`{{"op": "withdraw", "acct": A, "amount": X}}` subtracts X plus a fee of {fee}. It is rejected when the '
        'balance after subtracting X and the fee would be below minus the account\'s overdraft allowance.',
        '`{"op": "transfer", "from": A, "to": B, "amount": X}` moves X from A to B (no fee). It is rejected when A '
        'and B are the same account, or A\'s balance would fall below minus A\'s overdraft allowance.',
        f'Daily cap: for each account and each day (day = t // {DAY}), the accepted withdrawals and outgoing '
        f'transfers of that account on that day may total at most {r["cap"]} (fees are not counted). An event '
        f'that would exceed it is rejected. A withdrawal of more than {r["large"]} counts twice its amount towards '
        'the cap.',
        f'Fee waiver: a withdrawal pays no fee when the account\'s balance just before it is at least {r["waiver"]}.',
        '`{"op": "freeze", "acct": A}` / `{"op": "unfreeze", "acct": A}`: a frozen account rejects withdrawals and '
        'outgoing transfers; deposits and incoming transfers are still accepted. Freezing a frozen account or '
        'unfreezing an account that is not frozen is rejected.',
        '`{"op": "reverse", "target": I}` undoes the accepted deposit, withdrawal or transfer with id I that was '
        'processed earlier: a deposit\'s amount is taken back, a withdrawal\'s amount and its fee are given back '
        '(the fee no longer counts in the fee total), a transfer\'s amount moves back from B to A. It is rejected '
        'when I is not such an event, was already reversed, or any account it changes would end below minus its '
        'overdraft allowance or is closed. A reversal ignores freezing and the daily cap, and does not give back '
        'the cap the original event used. The allowance check covers every account the reversal changes, '
        'including one whose balance it raises: if such an account would still end below minus its allowance, '
        'the reversal is rejected.',
        '`{"op": "interest"}` is always accepted: every open account with a positive balance gains '
        f'floor(balance * {r["rate"]} / 10000); every open account with a negative balance pays an overdraft '
        f'charge of ceil(-balance * {r["charge"]} / 10000), which counts in the fee total. Interest and charges '
        'cannot be reversed.',
        '`{"op": "close", "acct": A}` closes A; it is rejected unless A\'s balance is exactly 0 and A is not frozen '
        'and has no active hold. A closed account no longer counts as open.',
        '`{"op": "hold", "acct": A, "amount": X}` places a hold of X on A (the hold is identified by this event\'s '
        'id). It does not change the balance, pays no fee and does not count towards the daily cap. It is '
        'rejected when A is frozen or when A\'s available balance minus X would be below minus the overdraft '
        'allowance.',
        f'A hold placed at time t is active until it is captured or released, but only while the time is less '
        f'than t + {r["expiry"] * DAY} ({days}); from then on it has expired and no longer exists.',
        'The available balance of an account is its balance minus the amounts of its active holds. Every '
        'overdraft-allowance check of withdrawals, transfers, reversals and holds uses the available balance '
        'instead of the balance. The fee waiver and interest/overdraft charges still use the balance itself.',
        '`{"op": "capture", "target": H}` turns the active hold H into a withdrawal of its amount from its account '
        'at the capture\'s time: the hold ends, and the amount plus the usual withdrawal fee (with the waiver) is '
        'subtracted. It counts towards that day\'s cap like a withdrawal (large amounts count twice). It is '
        'rejected when H is not an active hold, the account is frozen, the cap would be exceeded, or the '
        'available balance (not counting H itself) minus the amount and fee would be below minus the overdraft '
        'allowance. A capture cannot be reversed.',
        '`{"op": "release", "target": H}` ends the active hold H without moving money; it is rejected when H is '
        'not an active hold.',
    ]
    if tier >= 5:
        swept = 'a withdrawal, an outgoing transfer or a hold' if tier >= 6 else 'a withdrawal'
        cost = (f' The backup also pays a sweep fee of {r["sweep_fee"]} for every sweep that moves money (never '
                'waived; it counts in the fee total and is not part of the swept amount).' if tier >= 6 else '')
        lines += [
            '`{"op": "link", "acct": A, "backup": B}` makes B the backup of A, replacing any earlier backup of A. It '
            'is rejected when A or B is not open or A and B are the same account. Backups do not chain: a sweep '
            'never pulls money into the backup from its own backup.',
            f'Sweep: when {swept} on an account A with a backup B is not rejected before the money check (A open and '
            'not frozen, valid amount' + (', a transfer\'s other checks' if tier >= 6 else '') + ') and A\'s '
            'available balance is less than what the event needs (' + ('X plus the withdrawal fee; X for a '
            'transfer or hold' if tier >= 6 else 'X plus the withdrawal fee') + '), the shortfall is moved from B '
            f'to A first (the shortfall is that need minus A\'s available balance), as if B made a transfer, but limited to at most {r["sweep_max"]}, to what keeps B\'s '
            'available balance at least 0' + (' after the sweep fee' if tier >= 6 else '') + ' (B\'s overdraft '
            'allowance is not used), and to what B\'s daily cap still allows (the swept amount counts towards B\'s '
            'cap, never towards A\'s). Nothing is swept when B is not open or is frozen' + (', or when the event is '
            'a transfer to B itself' if tier >= 6 else '') + '. A partial sweep is allowed: the event is then '
            'checked as usual against A\'s overdraft allowance with the swept money included. If the event is '
            'rejected anyway, the sweep does not happen either.' + cost,
            'The fee waiver uses A\'s balance before the sweep. Sweeps are not events of their own: they are never '
            'reversed (reversing a swept ' + ('event' if tier >= 6 else 'withdrawal') + ' gives back only what '
            'that event itself moved), and ' + ('captures' if tier >= 6 else 'transfers, holds, captures') + ' and '
            'reversals never sweep.',
        ]
    lines += ['A rejected event changes nothing. Any other `op` is rejected.']
    result = ('Return `{"balances": {account: balance, ...}, "rejected": [ids], "fees": total}`: balances of every '
              'account that was opened and is not closed, the ids of the rejected events in processing order, and '
              'the total of the fees and charges collected.')
    return lines, result


def events(rng, r, shortest=8, longest=30):
    """A plausible timeline (opens early and funded, links early, freezes followed by unfreezes, reversals of earlier
    money events) with invalid amounts, unknown accounts, equal times and shuffled ids, then the list order
    shuffled."""
    tier, names = r['tier'], rng.sample(ACCOUNTS, rng.randint(3, 4))
    out = []
    for a in names:
        if rng.random() < 0.9:
            e = {'op': 'open', 'acct': a}
            if rng.random() < 0.25:
                e['overdraft'] = rng.choice([0, 50, 500])
            out.append(e)
            funds = rng.randint(500, 2500) if tier < 5 else rng.randint(100, 1200)  # holds and captures can succeed
            out.append({'op': 'deposit', 'acct': a, 'amount': funds})
    if tier >= 5:
        for a in rng.sample(names, 2):
            out.append({'op': 'link', 'acct': a, 'backup': rng.choice(names)})
    ops = ['deposit'] * 4 + ['withdraw'] * 5 + ['transfer'] * 4 + ['open', 'freeze', 'unfreeze', 'reverse',
           'reverse', 'interest', 'close', 'close', 'hold', 'hold', 'hold', 'capture', 'capture', 'release']
    if tier >= 5:
        ops += ['link', 'withdraw', 'withdraw'] + ['transfer', 'transfer', 'hold', 'hold'] * (tier >= 6)
    size = rng.randint(shortest, longest)
    while len(out) < size:
        op, a = rng.choice(ops), rng.choice(names + ['zed'] * (rng.random() < 0.05))
        bad = rng.random() < 0.08
        amount = rng.choice([0, -5, 300.0, '50']) if bad else rng.randint(1, 900 if tier < 5 else 1500)
        if op == 'deposit':
            out.append({'op': op, 'acct': a, 'amount': amount if bad else rng.randint(300, 3500)})
        elif op == 'withdraw':
            out.append({'op': op, 'acct': a, 'amount': amount})
        elif op == 'transfer':
            out.append({'op': op, 'from': a, 'to': rng.choice(names), 'amount': amount})
        elif op == 'reverse':
            money = [k for k, x in enumerate(out) if x['op'] in ('deposit', 'withdraw', 'transfer')]
            out.append({'op': op, 'target': rng.choice(money) if money and rng.random() < 0.85 else len(out)})
        elif op == 'interest':
            out.append({'op': op})
        elif op == 'hold':
            out.append({'op': op, 'acct': a, 'amount': amount if bad else rng.randint(1, 400 if tier < 6 else 900)})
        elif op in ('capture', 'release'):  # mostly a recent hold, so it can still be active
            placed = [k for k, x in enumerate(out) if x['op'] == 'hold'][-2:]
            out.append({'op': op, 'target': rng.choice(placed) if placed and rng.random() < 0.9 else len(out)})
        elif op == 'close' and rng.random() < 0.5:  # empty the account first, so a close can succeed
            out.append({'op': 'withdraw', 'acct': a, 'amount': rng.randint(1, 900)})
            out.append({'op': op, 'acct': a})
        elif op == 'unfreeze':
            frozen = [x['acct'] for x in out if x['op'] == 'freeze']
            out.append({'op': op, 'acct': rng.choice(frozen) if frozen and rng.random() < 0.8 else a})
        elif op == 'link':
            out.append({'op': op, 'acct': a, 'backup': rng.choice(names + ['zed'])})
        else:
            out.append({'op': op, 'acct': a})
    ids = list(range(1, len(out) + 1))
    rng.shuffle(ids)
    t = rng.randint(0, 2) * DAY + rng.randint(0, DAY - 1)
    for k, e in enumerate(out):
        e['id'] = ids[k]
        e['t'] = t
        t += rng.choice([0, 0, 1, 60, 3600, 20000, 40000, DAY, DAY - 1, 50000])
    for e in out:
        if e['op'] in ('reverse', 'capture', 'release'):  # the target was an index into the timeline
            e['target'] = out[e['target']]['id'] if e['target'] < len(out) else max(ids) + 1
    rng.shuffle(out)
    return [dict(sorted(e.items())) for e in out]


def item(rng, tier):
    r = rules(rng, tier)
    cases = [{'args': [e], 'expected': settle(e, r)} for e in (events(rng, r) for _ in range(40))]
    lines, result = describe(r)
    prompt = ('Implement `settle(events: list[dict]) -> dict` for this ledger.\n\nRules:\n'
              + '\n'.join(f'{i}. {x}' for i, x in enumerate(lines, 1)) + f'\n\n{result}\n\n'
              'No examples are given; follow the rules exactly as written.\n\n'
              'Use only the Python 3 standard library. Hidden tests use other event lists, including edge cases.')
    return {'kind': 'code', 'entry': 'settle', 'prompt': prompt, 'tests': cases,
            'stub': 'def settle(events: list[dict]) -> dict:\n    raise NotImplementedError\n'}
