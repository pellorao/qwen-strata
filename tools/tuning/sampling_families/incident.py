"""incident: find the root cause of a failure to place orders from the interleaved logs of several services.

The generator injects one known fault into a small service graph and simulates the logs: background traffic with
request-rate metrics, the fault's own evidence, and the symptoms it causes upstream (timeouts, refused connections,
exhausted pools, HTTP errors, each retried and logged per attempt), a little later and one dependency further up.  The
distractors are the kind real incidents have: a real but unrelated fault in a service no order request uses, which
starts earlier; a harmless deploy or configuration change shortly before; an earlier problem that recovered; restarts
caused by the outage; and (tiers 2 and 3) a second real fault on the order path that the outage itself causes later (a
process running out of memory under the retry backlog).  From tier 2 every service writes its own clock and the
measured clock offsets are given: the faulty service's clock runs ahead, so its evidence is logged after the first
symptoms (except a certificate's validity, printed at start-up, and a traffic surge seen at the edge), while the later
secondary fault's clock runs behind, so it is logged first.  Several faults look alike by their symptoms and differ
only in the evidence around them: a pool limit lowered by configuration versus a saturated pool under genuine load
(compare the incoming rate at the edge), a retry setting that multiplies the load versus a traffic surge.  The answer
is the faulty service and the kind of cause, both fixed by construction.  Tier 1: 8 services, no clock offsets.  Tier
2: 9 services, clock offsets, the secondary fault.  Tier 3: as tier 2 with only the look-alike faults, more traffic
and one more unrelated error that recovered.
"""
from datetime import datetime, timedelta
from math import ceil

ROLES = {
    'edge': ['gateway', 'edge', 'frontdoor'], 'app': ['api', 'backend', 'core-api'],
    'auth': ['auth', 'identity', 'sso'], 'orders': ['orders', 'checkout', 'billing'],
    'db': ['orders-db', 'pg-main', 'ledger-db'], 'queue': ['queue', 'broker', 'events-bus'],
    'cache': ['cache', 'redis', 'session-store'], 'search': ['search', 'catalog', 'indexer'],
    'mail': ['mailer', 'notify', 'smtp-relay'],
}
CALLS = {'edge': ['app', 'search'], 'app': ['auth', 'orders', 'cache'], 'orders': ['db', 'queue'],
         'mail': ['queue'], 'auth': [], 'db': [], 'queue': [], 'cache': [], 'search': []}
SERVICES = {1: ['edge', 'app', 'auth', 'orders', 'db', 'queue', 'cache', 'search'],
            2: ['edge', 'app', 'auth', 'orders', 'db', 'queue', 'cache', 'search', 'mail'],
            3: ['edge', 'app', 'auth', 'orders', 'db', 'queue', 'cache', 'search', 'mail']}
CODES = {
    'STORAGE': 'a disk or volume is full or failing',
    'MEMORY': 'a process ran out of memory',
    'NETWORK': 'the network between services is broken (routing, DNS, firewall)',
    'CERTIFICATE': 'a TLS certificate is expired or otherwise invalid',
    'CLOCK': "a machine's system time is wrong",
    'CONFIGURATION': 'a configuration value was changed to a bad value',
    'SOFTWARE': 'a defect in newly deployed code',
    'CAPACITY': 'genuine load beyond the provisioned capacity',
}
SCENARIOS = {1: ['disk', 'oom', 'bug', 'pool', 'cert', 'clock'],
             2: ['disk', 'oom', 'pool', 'cert', 'retry', 'surge'],
             3: ['pool', 'retry', 'surge', 'cert', 'oom']}
ROOT = {'disk': ('db', 'STORAGE'), 'oom': ('queue', 'MEMORY'), 'bug': ('orders', 'SOFTWARE'),
        'pool': ('orders', 'CONFIGURATION'), 'cert': ('auth', 'CERTIFICATE'), 'clock': ('auth', 'CLOCK'),
        'retry': ('app', 'CONFIGURATION'), 'surge': ('orders', 'CAPACITY')}
EVIDENCE = {'disk': 'No space left', 'oom': 'OOM killer', 'bug': 'deployed version 7.', 'pool': 'max_size=2',
            'cert': 'valid until', 'clock': 'stepped forward', 'retry': 'max_retries=6', 'surge': 'campaign'}
DISTRACTORS = {1: ['unrelated', 'side-fault', 'deploy', 'recovered', 'restarts'],
               2: ['unrelated', 'side-fault', 'deploy', 'recovered', 'restarts', 'secondary'],
               3: ['unrelated', 'side-fault', 'deploy', 'recovered', 'restarts', 'secondary', 'side-error']}
BASE_RATE = 120  # requests per second at the edge


def attempts(t, role, level, message, retried=True):
    """A failed call logged once per attempt (the caller retries twice), or once."""
    if not retried:
        return [(t, role, level, message)]
    return [(t + 0.3 * k, role, level, f'{message} (attempt {k + 1}/3)') for k in range(3)]


def scenario_events(rng, kind, at, name, tier):
    """(true seconds, role, level, message) of the fault and its symptoms; `at` is the fault time."""
    o, a = name['orders'], name['app']
    retried = tier >= 2
    ev = []

    def order_failure(t, code, what):
        out = attempts(t, 'app', 'ERROR', f'POST /orders -> {o} {what}', retried)
        out.append((t + 1, 'edge', 'ERROR', f'POST /api/orders {code} (upstream {a})'))
        return out

    if kind == 'disk':
        db = name['db']
        ev += [(at - rng.randint(200, 400), 'db', 'WARN', f'disk usage on /var/lib/{db} at 94%'),
               (at, 'db', 'ERROR', 'could not write to file "pg_wal/xlogtemp.31337": No space left on device')]
        for k in range(rng.randint(3, 5)):
            t = at + 4 + k * rng.randint(8, 20)
            ev += [(t, 'db', 'ERROR', 'could not extend file "base/16384/2619": No space left on device'),
                   (t + 1, 'orders', 'ERROR', f'insert into orders failed: could not extend file (SQLSTATE 53100) '
                                              f'from {db}')]
            ev += order_failure(t + 2, 502, 'returned 500')
        ev += [(at + 70, 'orders', 'WARN', 'connection pool exhausted (32/32 busy), requests are queueing'),
               (at + 75, 'orders', 'ERROR', 'timed out after 5000ms waiting for a database connection')]
    elif kind == 'oom':
        q = name['queue']
        ev += [(at - 120, 'queue', 'WARN', 'resident memory 3.6GiB of the 4GiB limit'),
               (at, 'queue', 'ERROR', 'broker killed by the kernel OOM killer (rss 4.0GiB, limit 4GiB)')]
        for k in range(rng.randint(3, 4)):
            t = at + 3 + k * rng.randint(25, 40)
            ev += [(t, 'queue', 'INFO', f'starting broker, recovering 48000 messages (pid {4100 + 37 * k})'),
                   (t + 1, 'orders', 'ERROR', f'publish order.created failed: connection refused ({q}:5672)')]
            ev += order_failure(t + 2, 502, 'returned 500')
            ev += [(t + 15, 'queue', 'ERROR', 'broker killed by the kernel OOM killer (rss 4.0GiB, limit 4GiB)')]
    elif kind == 'bug':
        ev += [(at, 'orders', 'INFO', f'deployed version 7.{rng.randint(1, 9)}.0 (build {rng.randint(4000, 4999)})')]
        for k in range(rng.randint(3, 5)):
            t = at + 20 + k * rng.randint(10, 25)
            ev += [(t, 'orders', 'ERROR', "unhandled KeyError: 'currency' in price_order (handlers.py:88)")]
            ev += order_failure(t + 1, 502, 'returned 500')
    elif kind == 'pool':
        ev += [(at, 'orders', 'INFO', 'configuration reloaded from release 2026.10.3: db.pool.max_size=2 '
                                      '(previously 40), db.pool.wait_ms=2000')]
        for k in range(rng.randint(3, 5)):
            t = at + 30 + k * rng.randint(10, 25)
            ev += [(t, 'orders', 'WARN', 'waited 2000ms for a database connection (2/2 busy)'),
                   (t + 1, 'orders', 'ERROR', 'connection pool exhausted (2/2 busy), request rejected'),
                   (t + 3, 'db', 'INFO', 'connections: 2 active, 0 waiting, 61 idle slots')]
            ev += order_failure(t + 2, 504, 'timed out after 3000ms')
    elif kind in ('cert', 'clock'):
        auth = name['auth']
        if kind == 'cert':
            ev += [(-1, 'auth', 'INFO', f'serving TLS certificate CN={auth}.internal, valid until {{clock:{at}}} UTC')]
        else:
            ev += [(at + 8, 'auth', 'INFO', 'clock adjusted: system time stepped forward by 7385.2s after '
                                            're-reading the hardware clock')]
        for k in range(rng.randint(3, 5)):
            t = at + (1 if kind == 'cert' else 12) + k * rng.randint(8, 20)
            if kind == 'cert':
                ev += attempts(t, 'app', 'ERROR', f'TLS handshake with {auth}:8443 failed: x509: certificate has '
                                                  'expired or is not yet valid', retried)
            else:
                ev += [(t, 'auth', 'INFO', f'issued token for user u{rng.randint(1000, 9999)}'),
                       (t + 1, 'app', 'WARN', 'token rejected: not valid before 2h03m in the future (nbf check)')]
            code = 502 if kind == 'cert' else 401
            ev += [(t + 1.5, 'edge', 'ERROR', f'GET /api/account {code} (upstream {a})'),
                   (t + 2, 'edge', 'ERROR', f'POST /api/orders {code} (upstream {a})')]
    elif kind in ('retry', 'surge'):
        if kind == 'retry':
            ev += [(at, 'app', 'INFO', f'configuration reloaded from release 2026.10.3: {o}.client.max_retries=6 '
                                       '(previously 1), retry backoff 0ms')]
        else:
            ev += [(at - rng.randint(20, 60), 'app', 'INFO', 'configuration reloaded from release 2026.10.3: '
                                                             'feature.new_banner=true (previously false)'),
                   (at, 'edge', 'INFO', 'traffic from campaign "autumn-sale" started (newsletter sent to 1.2M '
                                        'recipients)')]
        for k in range(rng.randint(3, 5)):
            t = at + 25 + k * rng.randint(10, 25)
            ev += [(t, 'orders', 'WARN', 'worker pool saturated (64/64 busy), requests are queueing'),
                   (t + 1, 'orders', 'ERROR', 'shedding load: queue full, returned 503'),
                   (t + 3, 'db', 'INFO', 'connections: 18 active, 0 waiting, 45 idle slots')]
            ev += order_failure(t + 2, 503, 'returned 503')
    failing = 'all' if kind in ('cert', 'clock') else 'orders'
    return ev, failing


def metrics(rng, kind, at, end, services, step):
    """Rate lines every `step` seconds: incoming requests at the edge and at orders."""
    ev, t = [], rng.randint(0, step)
    while t < end:
        edge = BASE_RATE + rng.randint(-8, 8)
        orders = 20 + rng.randint(-3, 3)
        if kind == 'surge' and t >= at:
            edge, orders = edge * 5 + rng.randint(0, 40), orders * 5 + rng.randint(0, 10)
        elif kind == 'retry' and t >= at:
            orders = orders * 6 + rng.randint(0, 10)
        ev.append((t, 'edge', 'INFO', f'incoming {edge} req/s'))
        if 'orders' in services:
            ev.append((t + 0.5, 'orders', 'INFO', f'incoming {orders} req/s'))
        t += step
    return ev


def distractor_events(rng, kind, at, scenario, name):
    s = name.get('search', 'search')
    if kind == 'unrelated':
        return [(at - rng.randint(30, 200), 'search', 'WARN', f'slow query on index products: {rng.randint(1500, 2600)}ms'),
                (at + rng.randint(20, 120), 'search', 'WARN', f'slow query on index products: {rng.randint(1500, 2600)}ms')]
    if kind == 'side-fault':  # a real fault in a service no order request uses, starting before the outage
        start = at - rng.randint(90, 240)
        out = [(start - 60, 'search', 'WARN', f'disk usage on /var/lib/{s} at 97%')]
        for k in range(rng.randint(4, 6)):
            t = start + k * rng.randint(20, 45)
            out += [(t, 'search', 'ERROR', 'index segment merge failed: No space left on device'),
                    (t + 1, 'edge', 'ERROR', f'GET /api/search?q={rng.choice(["lamp", "desk", "rug"])} 500 (upstream '
                                             f'{s})')]
        return out
    if kind == 'deploy':
        role = 'cache' if ROOT[scenario][0] != 'cache' else 'edge'
        return [(at - rng.randint(60, 180), role, 'INFO', f'deployed version 2.{rng.randint(10, 30)}.0 (build '
                                                          f'{rng.randint(1000, 1999)})')]
    if kind == 'recovered':
        return [(at - rng.randint(500, 700), 'cache', 'WARN', 'eviction storm: 12000 keys evicted in 5s'),
                (at - rng.randint(380, 480), 'cache', 'INFO', 'eviction rate back to normal (40 keys/s)')]
    if kind == 'restarts':
        return [(at + rng.randint(100, 140), 'app' if ROOT[scenario][0] != 'app' else 'edge', 'WARN',
                 'liveness probe failed 3 times; restarting worker 2'),
                (at + rng.randint(150, 170), 'app' if ROOT[scenario][0] != 'app' else 'edge', 'INFO',
                 'worker 2 started')]
    if kind == 'side-error':
        return [(at - rng.randint(250, 400), 'mail', 'ERROR', 'SMTP 421 from relay: too many connections, will retry'),
                (at - rng.randint(100, 240), 'mail', 'INFO', 'retried 14 queued messages, all delivered')]
    raise ValueError(kind)


def secondary(rng, at, role):
    """A real fault on the order path caused by the outage: memory grows under the retry backlog."""
    when = at + rng.randint(45, 90)
    return when, [(when - 30, role, 'WARN', 'heap 3.7GiB of the 4GiB limit, retry backlog 41000 requests'),
                  (when, role, 'ERROR', 'worker 3 killed: out of memory (heap 4.0GiB, limit 4GiB)'),
                  (when + 6, role, 'INFO', 'worker 3 started')]


def traffic(rng, start, end, services, failing, at, gap):
    """Background successes; after `at` the failing paths log errors instead (written by the scenario)."""
    ev, t = [], start
    while t < end:
        t += rng.randint(*gap)
        pick = rng.random()
        broken = t >= at
        if pick < 0.25 and 'search' in services:
            ev.append((t, 'search', 'INFO', f'query products: {rng.randint(3, 60)} hits'))
        elif pick < 0.55 and not (broken and failing == 'all'):
            ev.append((t, 'edge', 'INFO', f'GET /api/catalog 200 {rng.randint(30, 120)}ms'))
            ev.append((t, 'app', 'INFO', 'GET /catalog 200'))
            if 'cache' in services:
                ev.append((t, 'cache', 'INFO', f'hit ratio {rng.randint(90, 99)}%'))
        elif not broken:
            ev.append((t, 'edge', 'INFO', f'POST /api/orders 201 {rng.randint(90, 240)}ms'))
            ev.append((t, 'app', 'INFO', 'POST /orders 201'))
            if 'auth' in services:
                ev.append((t, 'auth', 'INFO', f'validated token for user u{rng.randint(1000, 9999)}'))
            ev.append((t, 'orders', 'INFO', f'order {rng.randint(50000, 59999)} created'))
            ev.append((t, 'db', 'INFO', f'commit {rng.randint(10, 80)}ms'))
            if 'queue' in services:
                ev.append((t, 'queue', 'INFO', 'published order.created'))
        if 'mail' in services and rng.random() < 0.08:
            ev.append((t, 'mail', 'INFO', 'sent order confirmation'))
    return ev


def item(rng, tier):
    roles = SERVICES[tier]
    name = {r: rng.choice(ROLES[r]) for r in roles}
    scenario = rng.choice(SCENARIOS[tier])
    root_role, code = ROOT[scenario]
    begin = datetime(2026, rng.randint(1, 12), rng.randint(1, 28), rng.randint(0, 23), rng.randint(0, 59),
                     rng.randint(0, 59))
    at = {1: 420, 2: 480, 3: 540}[tier] + rng.randint(0, 60)
    end = at + {1: 200, 2: 220, 3: 260}[tier]
    ev, failing = scenario_events(rng, scenario, at, name, tier)
    for kind in DISTRACTORS[tier]:
        if kind != 'secondary':
            ev += distractor_events(rng, kind, at, scenario, name)
    offsets = {r: 0 for r in roles}
    late_role = None
    if tier >= 2:
        late_role = 'edge' if root_role == 'app' or scenario == 'cert' else 'app'
        when, late = secondary(rng, at, late_role)
        ev += late
        for r in roles:
            offsets[r] = rng.choice([-2, -1, 0, 0, 1, 2])
        if scenario not in ('cert', 'surge'):  # the faulty service's evidence is logged after the first symptoms
            evidence = min(t for t, role, _, m in ev if role == root_role and EVIDENCE[scenario] in m)
            symptom = min(t for t, role, level, m in ev if level == 'ERROR' and role in ('edge', 'app') and
                          'orders' in m)
            offsets[root_role] = ceil(max(0, symptom - evidence)) + 2 + rng.randint(5, 40)
        offsets[late_role] = -(when - at + rng.randint(20, 60))
    ev += metrics(rng, scenario, at, end, roles, {1: 60, 2: 45, 3: 30}[tier])
    ev += traffic(rng, 0, end, roles, failing, at, {1: (9, 22), 2: (8, 20), 3: (7, 16)}[tier])
    ev = [x for x in ev if x[1] in roles]
    stamp = {}

    def clock(seconds):
        if seconds not in stamp:
            stamp[seconds] = rng.randint(0, 999)
        return (begin + timedelta(seconds=seconds, milliseconds=stamp[seconds])).strftime('%H:%M:%S.%f')[:-3]

    logged = sorted(((max(t, 0) + offsets[role], role, level, message) for t, role, level, message in ev),
                    key=lambda x: x[0])
    lines, root_line, late_line, first_symptom = [], None, None, None
    width = max(map(len, name.values()))
    for t, role, level, message in logged:
        if root_line is None and (role == root_role or scenario == 'surge') and EVIDENCE[scenario] in message:
            root_line = len(lines)
        if late_line is None and role == late_role and 'out of memory' in message:
            late_line = len(lines)
        if first_symptom is None and level == 'ERROR' and 'orders' in message and role in ('edge', 'app'):
            first_symptom = len(lines)
        if '{clock:' in message:
            head, _, rest = message.partition('{clock:')
            message = head + (begin + timedelta(seconds=int(rest.split('}')[0]))).strftime('%Y-%m-%d %H:%M:%S') + \
                rest.split('}', 1)[1]
        lines.append(f'{clock(t)} {name[role]:<{width}} {level:<5} {message}')
    calls = '\n'.join(f'- {name[r]} calls {", ".join(name[c] for c in CALLS[r] if c in roles)}'
                      for r in roles if any(c in roles for c in CALLS[r]))
    codes = '\n'.join(f'- {k}: {v}' for k, v in CODES.items())
    clocks = ''
    if tier >= 2:
        listed = '\n'.join(f'- {name[r]}: {offsets[r]:+d} s' for r in roles)
        clocks = ('Every service stamps its log lines with its own clock. A clock check that day measured how far '
                  'each clock was ahead of the true time (negative: behind); the true time of a line is its '
                  f'timestamp minus its service\'s offset:\n\n{listed}\n\nThe lines below are merged in the order of '
                  'their timestamps as written, not in true time. ')
    prompt = (f'An online shop had an outage on {begin:%Y-%m-%d}: customers could not place orders. Its services and '
              f'their calls:\n\n{calls}\n\n{clocks}'
              + ('A caller retries a failed call twice, and every attempt is logged. ' if tier >= 2 else '')
              + 'Below are all log lines from that period'
              + (', merged in time order (one clock for all services)' if tier < 2 else '')
              + '. Exactly one fault started the outage; every other problem in the log is either a consequence of '
              'it (possibly a real fault itself, but caused by the outage) or unrelated to the failing orders.\n\n'
              '```\n' + '\n'.join(lines) + f'\n```\n\nCause kinds:\n\n{codes}\n\n'
              'Question: Which service had the fault that started the outage, and what kind of cause was it? Choose '
              'the kind of the underlying cause, not of a symptom. Answer as the service name and the cause kind '
              'separated by a comma (for example ' + f'{name["search"]},NETWORK).')
    return {'kind': 'answer', 'prompt': prompt, 'answer': f'{name[root_role]},{code}'.lower(),
            'incident': {'scenario': scenario, 'root': [name[root_role], code], 'lines': len(lines),
                         'root_line': root_line, 'secondary_line': late_line, 'first_symptom_line': first_symptom,
                         'offsets': {name[r]: v for r, v in offsets.items()}, 'distractors': DISTRACTORS[tier]}}
