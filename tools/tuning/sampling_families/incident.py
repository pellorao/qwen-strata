"""incident: find the root cause of an outage from the interleaved logs of several services.

The generator injects one known fault into a small service graph and simulates the logs: background traffic, the
fault's own evidence, and the symptoms it causes upstream (timeouts, refused connections, exhausted pools, HTTP
errors), each a little later and one dependency further up.  Distractors are added by tier: an unrelated warning in
a service no failing request uses, a harmless deploy shortly before the outage, an earlier problem that recovered,
restarts caused by the outage, and an error in an unrelated service.  The loudest or earliest-looking error is often
a consequence (an exhausted pool, a refused connection, an x509 error), so the answer needs the causal chain, not a
search for ERROR.  The answer is the faulty service and the kind of cause, both fixed by construction.
Tier 1: 6 services, a direct fault, 2 distractors.  Tier 2: 8 services, adds faults whose evidence is a consequence
in another service, 4 distractors.  Tier 3: 9 services, faults whose own evidence is not an error (a configuration
reload, a clock step, a certificate's end date), all 5 distractors and more traffic.
"""
from datetime import datetime, timedelta

ROLES = {
    'edge': ['gateway', 'edge', 'frontdoor'], 'app': ['api', 'backend', 'core-api'],
    'auth': ['auth', 'identity', 'sso'], 'orders': ['orders', 'checkout', 'billing'],
    'db': ['orders-db', 'pg-main', 'ledger-db'], 'queue': ['queue', 'broker', 'events-bus'],
    'cache': ['cache', 'redis', 'session-store'], 'search': ['search', 'catalog', 'indexer'],
    'mail': ['mailer', 'notify', 'smtp-relay'],
}
CALLS = {'edge': ['app', 'search'], 'app': ['auth', 'orders', 'cache'], 'orders': ['db', 'queue'],
         'mail': ['queue'], 'auth': [], 'db': [], 'queue': [], 'cache': [], 'search': []}
SERVICES = {1: ['edge', 'app', 'orders', 'db', 'queue', 'search'],
            2: ['edge', 'app', 'auth', 'orders', 'db', 'queue', 'cache', 'search'],
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
SCENARIOS = {1: ['disk', 'oom', 'bug'], 2: ['disk', 'oom', 'bug', 'pool', 'cert'],
             3: ['pool', 'clock', 'cert', 'disk', 'oom']}
ROOT = {'disk': ('db', 'STORAGE'), 'oom': ('queue', 'MEMORY'), 'bug': ('orders', 'SOFTWARE'),
        'pool': ('orders', 'CONFIGURATION'), 'cert': ('auth', 'CERTIFICATE'), 'clock': ('auth', 'CLOCK')}
DISTRACTORS = {1: ['unrelated', 'restarts'], 2: ['unrelated', 'deploy', 'recovered', 'restarts'],
               3: ['unrelated', 'deploy', 'recovered', 'restarts', 'side-error']}


def scenario_events(rng, kind, at, name):
    """(seconds, role, level, message) of the fault and its symptoms; `at` is the fault time."""
    o, a, e = name['orders'], name['app'], name['edge']
    ev = []
    if kind == 'disk':
        db = name['db']
        ev += [(at - rng.randint(200, 400), 'db', 'WARN', f'disk usage on /var/lib/{db} at 94%'),
               (at, 'db', 'ERROR', 'could not write to file "pg_wal/xlogtemp.31337": No space left on device')]
        for k in range(rng.randint(3, 5)):
            t = at + 4 + k * rng.randint(8, 20)
            ev += [(t, 'db', 'ERROR', 'could not extend file "base/16384/2619": No space left on device'),
                   (t + 1, 'orders', 'ERROR', f'insert into orders failed: could not extend file (SQLSTATE 53100) '
                                              f'from {db}'),
                   (t + 2, 'app', 'ERROR', f'POST /orders -> {o} returned 500'),
                   (t + 2, 'edge', 'ERROR', f'POST /api/orders 502 (upstream {a})')]
        ev += [(at + 70, 'orders', 'WARN', 'connection pool exhausted (32/32 busy), requests are queueing'),
               (at + 75, 'orders', 'ERROR', 'timed out after 5000ms waiting for a database connection')]
    elif kind == 'oom':
        q = name['queue']
        ev += [(at - 120, 'queue', 'WARN', 'resident memory 3.6GiB of the 4GiB limit'),
               (at, 'queue', 'ERROR', 'broker killed by the kernel OOM killer (rss 4.0GiB, limit 4GiB)')]
        for k in range(rng.randint(3, 4)):
            t = at + 3 + k * rng.randint(25, 40)
            ev += [(t, 'queue', 'INFO', f'starting broker, recovering 48000 messages (pid {4100 + 37 * k})'),
                   (t + 1, 'orders', 'ERROR', f'publish order.created failed: connection refused ({q}:5672)'),
                   (t + 2, 'app', 'ERROR', f'POST /orders -> {o} returned 500'),
                   (t + 2, 'edge', 'ERROR', f'POST /api/orders 502 (upstream {a})'),
                   (t + 15, 'queue', 'ERROR', 'broker killed by the kernel OOM killer (rss 4.0GiB, limit 4GiB)')]
    elif kind == 'bug':
        ev += [(at, 'orders', 'INFO', f'deployed version 7.{rng.randint(1, 9)}.0 (build {rng.randint(4000, 4999)})')]
        for k in range(rng.randint(3, 5)):
            t = at + 20 + k * rng.randint(10, 25)
            ev += [(t, 'orders', 'ERROR', "unhandled KeyError: 'currency' in price_order (handlers.py:88)"),
                   (t + 1, 'app', 'ERROR', f'POST /orders -> {o} returned 500'),
                   (t + 1, 'edge', 'ERROR', f'POST /api/orders 502 (upstream {a})')]
    elif kind == 'pool':
        ev += [(at, 'orders', 'INFO', 'configuration reloaded from release 2026.10.3: db.pool.max_size=2 '
                                      '(previously 40), db.pool.wait_ms=2000')]
        for k in range(rng.randint(3, 5)):
            t = at + 30 + k * rng.randint(10, 25)
            ev += [(t, 'orders', 'WARN', 'waited 2000ms for a database connection (2/2 busy)'),
                   (t + 1, 'orders', 'ERROR', 'connection pool exhausted (2/2 busy), request rejected'),
                   (t + 2, 'app', 'ERROR', f'POST /orders -> {o} timed out after 3000ms'),
                   (t + 2, 'edge', 'ERROR', f'POST /api/orders 504 (upstream {a})'),
                   (t + 3, 'db', 'INFO', 'connections: 2 active, 0 waiting, 61 idle slots')]
    elif kind == 'cert':
        auth = name['auth']
        end = at
        ev += [(-1, 'auth', 'INFO', f'serving TLS certificate CN={auth}.internal, valid until '
                                    f'{{clock:{end}}} UTC')]
        for k in range(rng.randint(3, 5)):
            t = at + 1 + k * rng.randint(8, 20)
            ev += [(t, 'app', 'ERROR', f'TLS handshake with {auth}:8443 failed: x509: certificate has expired or is '
                                       'not yet valid'),
                   (t + 1, 'edge', 'ERROR', f'GET /api/account 502 (upstream {a})'),
                   (t + 2, 'edge', 'ERROR', f'POST /api/orders 502 (upstream {a})')]
    elif kind == 'clock':
        ev += [(at + 8, 'auth', 'INFO', 'clock adjusted: system time stepped forward by 7385.2s after re-reading '
                                        'the hardware clock')]
        for k in range(rng.randint(3, 5)):
            t = at + 12 + k * rng.randint(8, 20)
            ev += [(t, 'auth', 'INFO', f'issued token for user u{rng.randint(1000, 9999)}'),
                   (t + 1, 'app', 'WARN', 'token rejected: not valid before 2h03m in the future (nbf check)'),
                   (t + 1, 'edge', 'ERROR', f'GET /api/account 401 (upstream {a})'),
                   (t + 2, 'edge', 'ERROR', f'POST /api/orders 401 (upstream {a})')]
    failing = {'disk': 'orders', 'oom': 'orders', 'bug': 'orders', 'pool': 'orders', 'cert': 'all',
               'clock': 'all'}[kind]
    return ev, failing


def distractor_events(rng, kind, at, scenario, tier):
    if kind == 'unrelated':
        return [(at - rng.randint(30, 200), 'search', 'WARN', f'slow query on index products: {rng.randint(1500, 2600)}ms'),
                (at + rng.randint(20, 120), 'search', 'WARN', f'slow query on index products: {rng.randint(1500, 2600)}ms')]
    if kind == 'deploy':
        root = ROOT[scenario][0]
        role = 'app' if root != 'app' else 'edge'
        return [(at - rng.randint(60, 180), role, 'INFO', f'deployed version 2.{rng.randint(10, 30)}.0 (build '
                                                          f'{rng.randint(1000, 1999)})')]
    if kind == 'recovered':
        return [(at - rng.randint(500, 700), 'cache', 'WARN', 'eviction storm: 12000 keys evicted in 5s'),
                (at - rng.randint(380, 480), 'cache', 'INFO', 'eviction rate back to normal (40 keys/s)')]
    if kind == 'restarts':
        return [(at + rng.randint(100, 140), 'app', 'WARN', 'liveness probe failed 3 times; restarting worker 2'),
                (at + rng.randint(150, 170), 'app', 'INFO', 'worker 2 started')]
    return [(at - rng.randint(250, 400), 'mail', 'ERROR', 'SMTP 421 from relay: too many connections, will retry'),
            (at - rng.randint(100, 240), 'mail', 'INFO', 'retried 14 queued messages, all delivered')]


def traffic(rng, start, end, services, failing, at, gap):
    """Background successes; after `at` the failing paths log errors instead (written by the scenario)."""
    ev, t = [], start
    while t < end:
        t += rng.randint(*gap)
        pick = rng.random()
        broken = t >= at
        if pick < 0.3 and 'search' in services:
            ev.append((t, 'edge', 'INFO', f'GET /api/search?q={rng.choice(["lamp", "desk", "chair", "rug"])} 200 '
                                          f'{rng.randint(20, 90)}ms'))
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
        if 'mail' in services and rng.random() < 0.1:
            ev.append((t, 'mail', 'INFO', 'sent order confirmation'))
    return ev


def item(rng, tier):
    roles = SERVICES[tier]
    name = {r: rng.choice(ROLES[r]) for r in roles}
    scenario = rng.choice(SCENARIOS[tier])
    begin = datetime(2026, rng.randint(1, 12), rng.randint(1, 28), rng.randint(0, 23), rng.randint(0, 59),
                     rng.randint(0, 59))
    at = {1: 300, 2: 420, 3: 600}[tier] + rng.randint(0, 60)
    ev, failing = scenario_events(rng, scenario, at, name)
    for kind in DISTRACTORS[tier]:
        ev += distractor_events(rng, kind, at, scenario, tier)
    ev += traffic(rng, 0, at + {1: 200, 2: 240, 3: 300}[tier], roles, failing, at,
                  {1: (10, 24), 2: (8, 20), 3: (7, 16)}[tier])
    ev = [x for x in ev if x[1] in roles]
    stamp = {}

    def clock(seconds):
        if seconds not in stamp:
            stamp[seconds] = rng.randint(0, 999)
        return (begin + timedelta(seconds=seconds, milliseconds=stamp[seconds])).strftime('%H:%M:%S.%f')[:-3]

    lines, root_line = [], None
    evidence = {'disk': 'No space left', 'oom': 'OOM killer', 'bug': 'deployed version 7.', 'pool': 'max_size=2',
                'cert': 'valid until', 'clock': 'stepped forward'}[scenario]
    for t, role, level, message in sorted(ev, key=lambda x: x[0]):
        if root_line is None and role == ROOT[scenario][0] and evidence in message:
            root_line = len(lines)
        if '{clock:' in message:
            head, _, rest = message.partition('{clock:')
            message = head + (begin + timedelta(seconds=int(rest.split('}')[0]))).strftime('%Y-%m-%d %H:%M:%S') + \
                rest.split('}', 1)[1]
        lines.append(f'{clock(max(t, 0))} {name[role]:<{max(map(len, name.values()))}} {level:<5} {message}')
    service, code = ROOT[scenario]
    calls = '\n'.join(f'- {name[r]} calls {", ".join(name[c] for c in CALLS[r] if c in roles)}'
                      for r in roles if any(c in roles for c in CALLS[r]))
    codes = '\n'.join(f'- {k}: {v}' for k, v in CODES.items())
    prompt = (f'An online shop had an outage on {begin:%Y-%m-%d}. Its services and their calls:\n\n{calls}\n\n'
              'Below are all log lines from that period, merged in time order (one clock for all services). Exactly '
              'one fault started the outage; every other problem in the log is either a consequence of it or '
              f'unrelated to it.\n\n```\n' + '\n'.join(lines) + f'\n```\n\nCause kinds:\n\n{codes}\n\n'
              'Question: Which service had the fault that started the outage, and what kind of cause was it? Choose '
              'the kind of the underlying cause, not of a symptom. Answer as the service name and the cause kind '
              'separated by a comma (for example ' + f'{name["search"]},NETWORK).')
    return {'kind': 'answer', 'prompt': prompt, 'answer': f'{name[service]},{code}'.lower(),
            'incident': {'scenario': scenario, 'root': [name[service], code], 'lines': len(lines),
                         'root_line': root_line,
                         'distractors': DISTRACTORS[tier]}}
