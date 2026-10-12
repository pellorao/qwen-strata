"""policy: apply a written fee regulation (definitions, exceptions, precedence) to several booking cases.

The regulation is prose with numbered sections; the cases are facts (dates, times, attendance), never the defined
terms themselves, so every case needs the definitions read exactly.  The generator keeps a case set only when each
listed misreading (the other date for an age, "or" read as "and", a boundary read inclusively, part hours prorated,
reductions combined the other way, a surcharge reduced, an exception read too widely...) changes the answer, so a
single misread clause loses the item.  Tier 1: 2 cases, definitions, base fee, reductions, weekend surcharge.
Tier 2: 4 cases, adds the evening surcharge, charities and "no reductions for commercial bookings".  Tier 3: 5
cases, adds the late-application fee and the minimum charge.
"""
from datetime import date, timedelta
from fractions import Fraction
from math import ceil

WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
PEOPLE = ['R. Okafor', 'M. Lindqvist', 'T. Haddad', 'J. Moreau', 'S. Varga', 'P. Nakamura', 'L. Castillo',
          'A. Brennan', 'K. Osei', 'D. Petrov']
CHARITIES = ['Harbour Food Bank', 'Riverside Youth Choir', 'Oak Lane Hospice Friends', 'Northgate Literacy Trust']
BUSINESSES = ['Brightline Events Ltd', 'Kestrel Fitness', 'Copperpot Catering', 'Nimbus Software']
MISREADINGS = {1: ['senior_date', 'resident_date', 'commercial_logic', 'commercial_boundary', 'hours_exact',
                   'combine_other', 'combine_add', 'surcharge_reduced'],
               2: ['reduce_commercial', 'evening_whole', 'evening_exact', 'charity_always'],
               3: ['late_base', 'late_boundary', 'minimum_charity']}


def rules(rng, tier):
    return {'tier': tier, 'resident_months': rng.choice([6, 12, 18]), 'senior_age': rng.choice([60, 65, 67]),
            'senior_on': rng.choice(['event', 'application']), 'commercial': rng.choice(['or', 'and']),
            'crowd': rng.choice([80, 100, 150]), 'rate': rng.choice([20, 24, 30]),
            'commercial_rate': rng.choice([40, 45, 60]), 'resident_pct': rng.choice([20, 25, 30]),
            'senior_pct': rng.choice([30, 40, 50]), 'combine': rng.choice(['larger', 'sequential']),
            'weekend': rng.choice([25, 35, 50]), 'evening_from': rng.choice([19, 20, 21]),
            'evening_rate': rng.choice([8, 10, 15]), 'late_days': rng.choice([7, 10, 14]),
            'late_pct': rng.choice([10, 15, 20]), 'minimum': rng.choice([30, 40, 50])}


def months_between(start, end):
    months = (end.year - start.year) * 12 + end.month - start.month
    return months - (end.day < start.day)


def age_on(born, day):
    return day.year - born.year - ((day.month, day.day) < (born.month, born.day))


def fee(case, r, wrong=frozenset()):
    """Amount payable under the regulation `describe(r)` prints; `wrong` names misreadings to apply instead."""
    tier = r['tier']
    individual = case['kind'] == 'individual'
    resident = individual and months_between(
        case['registered'], case['event' if 'resident_date' in wrong else 'application']) >= r['resident_months']
    senior_on = r['senior_on'] if 'senior_date' not in wrong else \
        {'event': 'application', 'application': 'event'}[r['senior_on']]
    senior = individual and age_on(case['born'], case[senior_on]) >= r['senior_age']
    crowd = case['attendance'] >= r['crowd'] if 'commercial_boundary' in wrong else case['attendance'] > r['crowd']
    logic = r['commercial'] if 'commercial_logic' not in wrong else {'or': 'and', 'and': 'or'}[r['commercial']]
    commercial = case['kind'] == 'business' or (
        (case['tickets'] or crowd) if logic == 'or' else (case['tickets'] and crowd))
    minutes = case['end'] - case['start']
    hours = Fraction(minutes, 60) if 'hours_exact' in wrong else ceil(minutes / 60)
    base = hours * (r['commercial_rate'] if commercial else r['rate'])
    if tier >= 2 and case['kind'] == 'charity' and (not commercial or 'charity_always' in wrong):
        base = 0
    reductions = [Fraction(p, 100) for p, on in ((r['resident_pct'], resident), (r['senior_pct'], senior)) if on]
    if tier >= 2 and commercial and 'reduce_commercial' not in wrong:
        reductions = []
    combine = r['combine'] if 'combine_other' not in wrong else \
        {'larger': 'sequential', 'sequential': 'larger'}[r['combine']]
    if 'combine_add' in wrong:
        kept = 1 - sum(reductions)
    elif combine == 'larger':
        kept = 1 - max(reductions, default=0)
    else:
        kept = 1
        for x in reductions:
            kept *= 1 - x
    surcharge = r['weekend'] if case['weekday'] >= 5 else 0
    if tier >= 2:
        evening = max(0, case['end'] - max(case['start'], r['evening_from'] * 60))
        if 'evening_whole' in wrong and evening:
            evening = minutes
        surcharge += (Fraction(evening, 60) if 'evening_exact' in wrong else ceil(evening / 60)) * r['evening_rate']
    total = (base + surcharge) * kept if 'surcharge_reduced' in wrong else base * kept + surcharge
    if tier >= 3:
        days = (case['event'] - case['application']).days
        late = days <= r['late_days'] if 'late_boundary' in wrong else days < r['late_days']
        if late:
            total += Fraction(r['late_pct'], 100) * (base * kept if 'late_base' in wrong else total)
        if case['kind'] != 'charity' or 'minimum_charity' in wrong:
            total = max(total, r['minimum'])
    return int(total + Fraction(1, 2))  # nearest whole unit, halves up


def clock(minutes):
    return f'{minutes // 60:02d}:{minutes % 60:02d}'


def describe(r):
    tier = r['tier']
    other = {'event': 'application', 'application': 'event'}[r['senior_on']]
    commercial = (f'tickets are sold for it, or its expected attendance exceeds {r["crowd"]} people (either is '
                  'enough)' if r['commercial'] == 'or' else
                  f'tickets are sold for it and, in addition, its expected attendance exceeds {r["crowd"]} people')
    s = [
        ('Definitions',
         [f'"Resident" means an individual who, on the date of application, has been registered in the district for '
          f'at least {r["resident_months"]} full months. Organisations are never residents.',
          f'"Senior" means an individual aged {r["senior_age"]} or over on the date of the {r["senior_on"]} (the age '
          f'on the date of the {other} does not matter).',
          f'A booking is "commercial" when {commercial}. A booking made by a business is always commercial.',
          'A booking lasts from its start time to its end time on one day.'
          + (f' "Evening time" is any booked time from {r["evening_from"]}:00 onward.' if tier >= 2 else '')]),
        ('Base fee',
         [f'The base fee is {r["rate"]} for each hour or part of an hour of the booking ({r["commercial_rate"]} for a '
          'commercial booking). For example, a booking of 2 hours 10 minutes is charged as 3 hours.']),
        ('Reductions',
         [f'A resident receives a reduction of {r["resident_pct"]}% of the base fee.',
          f'A senior receives a reduction of {r["senior_pct"]}% of the base fee.',
          'When both reductions apply, only the larger one is given.' if r['combine'] == 'larger' else
          'When both reductions apply, the resident reduction is taken first and the senior reduction is then taken '
          'from the remaining amount.',
          'Reductions apply to the base fee only.'
          + (' A commercial booking receives no reductions.' if tier >= 2 else '')]),
        ('Surcharges',
         [f'A booking on a Saturday or Sunday pays a weekend surcharge of {r["weekend"]}.']
         + ([f'A booking pays an evening surcharge of {r["evening_rate"]} for each hour or part of an hour of its '
             'evening time (only the evening time counts, not the rest of the booking).'] if tier >= 2 else [])
         + ['Surcharges are added after any reduction and are never reduced.']),
    ]
    if tier >= 2:
        s.append(('Registered charities',
                  ['A booking made by a registered charity pays no base fee, unless the booking is commercial, in '
                   'which case the base fee is charged in full as in the section "Base fee". Surcharges apply to '
                   'charities as to everyone else.']))
    if tier >= 3:
        s.append(('Late applications',
                  [f'If the application is made fewer than {r["late_days"]} days before the event date, a late fee of '
                   f'{r["late_pct"]}% of the amount due under all the sections above (after reductions and '
                   'surcharges) is added.']))
        s.append(('Minimum charge',
                  [f'Except for bookings made by a registered charity, the amount payable is never less than '
                   f'{r["minimum"]}, even after all the other sections.']))
    s.append(('Rounding',
              ['Amounts are exact until the end; the amount payable is rounded to the nearest whole unit, and an amount '
               'exactly halfway is rounded up.']))
    out = []
    for k, (title, clauses) in enumerate(s, 1):
        out.append(f'Section {k}. {title}\n' + '\n'.join(f'({chr(96 + j)}) {c}' for j, c in enumerate(clauses, 1)))
    return '\n\n'.join(out)


def random_case(rng, r, name):
    tier = r['tier']
    kind = rng.choice(['individual'] * 3 + (['charity'] if tier >= 2 else []) + ['business'])
    event = date(2026, rng.randint(3, 11), rng.randint(1, 28))
    lead = rng.choice([r['late_days'] - 1, r['late_days'], r['late_days'] + 1, rng.randint(2, 60)])
    application = event - timedelta(days=lead)
    case = {'kind': kind, 'event': event, 'application': application, 'weekday': event.weekday(),
            'tickets': rng.random() < 0.4, 'name': name,
            'attendance': rng.choice([r['crowd'], r['crowd'] + 1, r['crowd'] - rng.randint(1, 40),
                                      r['crowd'] + rng.randint(2, 60)])}
    if kind == 'individual':
        months = r['resident_months'] + rng.choice([-1, 0, 0, 1, rng.randint(-5, 30)])
        day = rng.randint(1, 28)
        anchor = application if rng.random() < 0.6 else event
        year, month = anchor.year, anchor.month - months
        while month < 1:
            year, month = year - 1, month + 12
        case['registered'] = date(year, month, min(day, 28))
        target = r['senior_age'] + rng.choice([-1, 0, 0, 1, rng.randint(-20, 15)])
        anchor = rng.choice([application, event])
        born = date(anchor.year - target, anchor.month, min(anchor.day, 28))
        case['born'] = born + timedelta(days=rng.choice([-3, -1, 0, 1, 3, rng.randint(-200, 200)]))
    start = rng.randint(8 * 4, 21 * 4) * 15
    case['start'] = start
    case['end'] = min(24 * 60, start + rng.randint(3, 22) * 15 + rng.choice([0, 0, 5, 10]))
    return case


def case_text(case, r):
    who = {'individual': f'{case["name"]}, a private individual', 'charity': f'{case["name"]}, a registered charity',
           'business': f'{case["name"]}, a business'}[case['kind']]
    facts = [f'Applicant: {who}.']
    if case['kind'] == 'individual':
        facts.append(f'Born {case["born"]:%Y-%m-%d}; registered in the district since {case["registered"]:%Y-%m-%d}.')
    facts += [f'Application date: {case["application"]:%Y-%m-%d}. Event date: {case["event"]:%Y-%m-%d} '
              f'({WEEKDAYS[case["weekday"]]}).',
              f'Booked from {clock(case["start"])} to {clock(case["end"])}.',
              f'Expected attendance: {case["attendance"]}. Tickets sold: {"yes" if case["tickets"] else "no"}.']
    return ' '.join(facts)


def item(rng, tier):
    r = rules(rng, tier)
    wrongs = [w for t in range(1, tier + 1) for w in MISREADINGS[t]]
    size = {1: 2, 2: 4, 3: 5}[tier]
    pool = []
    for k in range(2500):
        case = random_case(rng, r, None)
        case['name'] = rng.choice({'individual': PEOPLE, 'charity': CHARITIES, 'business': BUSINESSES}[case['kind']])
        right = fee(case, r)
        pool.append((frozenset(w for w in wrongs if fee(case, r, {w}) != right), case, right))
    for _ in range(200):  # greedy cover of the misreadings from a random start; names must differ
        chosen = [rng.choice(pool)]
        while len(chosen) < size:
            covered = frozenset().union(*(c[0] for c in chosen))
            names = {c[1]['name'] for c in chosen}
            chosen.append(max((c for c in pool if c[1]['name'] not in names),
                              key=lambda c: (len(c[0] - covered), rng.random())))
        if frozenset().union(*(c[0] for c in chosen)) == frozenset(wrongs):
            break
    else:
        raise AssertionError('policy cases do not catch every misreading')
    rng.shuffle(chosen)
    cases, answer = [c[1] for c in chosen], [c[2] for c in chosen]
    listed = '\n'.join(f'Case {k}. {case_text(c, r)}' for k, c in enumerate(cases, 1))
    prompt = (f'A town hall charges for room bookings under the regulation below.\n\n{describe(r)}\n\nCases:\n\n'
              f'{listed}\n\nQuestion: What amount is payable for each case, in order? Answer with {size} whole '
              'numbers separated by commas (for example ' + ','.join(str(30 + 7 * k) for k in range(size)) + ').')
    return {'kind': 'answer', 'prompt': prompt, 'answer': ','.join(map(str, answer)),
            'policy': {'rules': r, 'misreadings': wrongs,
                       'cases': [{k: v.isoformat() if isinstance(v, date) else v for k, v in c.items()}
                                 for c in cases]}}
