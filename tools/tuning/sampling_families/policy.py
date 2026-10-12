"""policy: apply a written fee regulation (definitions, exceptions, exceptions to exceptions, stated precedence) to
several booking cases.

The regulation is prose with numbered sections; the cases are facts (dates, times, attendance, purpose), never the
defined terms themselves, so every case needs the definitions read exactly.  Sections conflict on purpose and the
text says which one prevails: community events override the charity exemption and the ticket rule of the commercial
definition, but a large attendance overrides that again; reductions do not apply to the community rate, except the
senior one; emergencies are exempt from the late fee, except commercial ones; a weekday public holiday doubles the
weekend surcharge.  The generator keeps a case set only when each listed misreading (the other date for an age, "or"
read as "and", a boundary read inclusively, part hours prorated, reductions combined the other way, a surcharge
reduced, an exception read too widely or too narrowly, a precedence read the other way...) changes the answer, so a
single misread clause loses the item; cases are drawn so that several clauses meet in one case.
Tier 1: 5 cases; definitions, base fee, reductions, weekend and evening surcharges, charities, community events, late
fee, minimum charge.  Tier 2: 6 cases; adds bookings past midnight, public holidays and emergency bookings.  Tier 3:
7 cases; adds a loyalty reduction that depends on the applicant's other bookings in the same month (counted in order
of application, so cases interact) and a limit on the reductions together.
"""
from datetime import date, timedelta
from fractions import Fraction
from math import ceil

WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
PEOPLE = ['R. Okafor', 'M. Lindqvist', 'T. Haddad', 'J. Moreau', 'S. Varga', 'P. Nakamura', 'L. Castillo',
          'A. Brennan', 'K. Osei', 'D. Petrov', 'E. Rossi', 'N. Abebe']
CHARITIES = ['Harbour Food Bank', 'Riverside Youth Choir', 'Oak Lane Hospice Friends', 'Northgate Literacy Trust',
             'Millbrook Allotment Society']
BUSINESSES = ['Brightline Events Ltd', 'Kestrel Fitness', 'Copperpot Catering', 'Nimbus Software', 'Tidewater Yoga']
PURPOSES = ['private party', 'meeting', 'workshop', 'concert', 'community event']
MISREADINGS = {1: ['senior_date', 'resident_date', 'commercial_logic', 'commercial_boundary', 'hours_exact',
                   'combine_other', 'combine_add', 'surcharge_reduced', 'evening_whole', 'evening_exact',
                   'reduce_commercial', 'charity_always', 'late_base', 'late_boundary', 'minimum_charity',
                   'community_nonresident', 'community_tickets', 'community_crowd', 'community_resident_reduction',
                   'community_no_senior', 'charity_community_free'],
               2: ['weekend_start_only', 'evening_after_midnight', 'holiday_single', 'holiday_weekend_double',
                   'emergency_commercial', 'emergency_ignored'],
               3: ['loyalty_event_order', 'loyalty_from_second', 'loyalty_skip_commercial', 'loyalty_any_month',
                   'loyalty_community', 'cap_ignored']}
SIZE = {1: 7, 2: 8, 3: 10}
DAY = 24 * 60


def rules(rng, tier):
    r = {'tier': tier, 'resident_months': rng.choice([6, 12, 18]), 'senior_age': rng.choice([60, 65, 67]),
         'senior_on': rng.choice(['event', 'application']), 'commercial': rng.choice(['or', 'and']),
         'crowd': rng.choice([80, 100, 150]), 'rate': rng.choice([20, 24, 30]),
         'commercial_rate': rng.choice([40, 45, 60]), 'community_rate': rng.choice([8, 10, 12]),
         'resident_pct': rng.choice([20, 25, 30]), 'senior_pct': rng.choice([30, 40, 50]),
         'combine': rng.choice(['larger', 'sequential']), 'weekend': rng.choice([25, 35, 50]),
         'evening_from': rng.choice([19, 20, 21]), 'evening_rate': rng.choice([8, 10, 15]),
         'late_days': rng.choice([7, 10, 14]), 'late_pct': rng.choice([10, 15, 20]),
         'minimum': rng.choice([30, 40, 50])}
    if tier >= 2:
        days = []  # at least one public holiday on a weekday and one on a weekend
        while not (any(d.weekday() < 5 for d in days) and any(d.weekday() >= 5 for d in days)):
            days = [date(2026, m, rng.randint(1, 28)) for m in rng.sample(range(3, 12), 4)]
        r['holidays'] = sorted(d.isoformat() for d in days)
    if tier >= 3:
        r['loyalty_pct'] = rng.choice([25, 35, 40])  # can exceed the resident reduction, so it matters alone
        r['combine'] = 'sequential'  # the limit binds only on combinations, so reductions must combine
        r['cap_pct'] = max(r['resident_pct'], r['senior_pct'], r['loyalty_pct']) + 5
    return r


def months_between(start, end):
    months = (end.year - start.year) * 12 + end.month - start.month
    return months - (end.day < start.day)


def age_on(born, day):
    return day.year - born.year - ((day.month, day.day) < (born.month, born.day))


def ranks(cases, r, wrong):
    """Loyalty number of each case: its place among the same applicant's bookings in the same calendar month."""
    order = sorted(range(len(cases)), key=lambda k: (
        (cases[k]['event'], cases[k]['start']) if 'loyalty_event_order' in wrong else cases[k]['application'], k))
    seen, out = {}, [0] * len(cases)
    for k in order:
        if 'loyalty_skip_commercial' in wrong and commercial_of(cases[k], r, wrong):
            continue
        month = None if 'loyalty_any_month' in wrong else (cases[k]['event'].year, cases[k]['event'].month)
        key = (cases[k]['name'], month)
        seen[key] = seen.get(key, 0) + 1
        out[k] = seen[key]
    return out


def commercial_of(case, r, wrong):
    crowd = case['attendance'] >= r['crowd'] if 'commercial_boundary' in wrong else case['attendance'] > r['crowd']
    if case['kind'] == 'business':
        return True
    if case['purpose'] == 'community event' and 'community_tickets' not in wrong:
        return crowd and 'community_crowd' not in wrong
    logic = r['commercial'] if 'commercial_logic' not in wrong else {'or': 'and', 'and': 'or'}[r['commercial']]
    return (case['tickets'] or crowd) if logic == 'or' else (case['tickets'] and crowd)


def fees(cases, r, wrong=frozenset()):
    """Amounts payable under the regulation `describe(r)` prints; `wrong` names misreadings to apply instead."""
    rank = ranks(cases, r, wrong) if r['tier'] >= 3 else [1] * len(cases)
    return [fee(case, r, wrong, k) for case, k in zip(cases, rank)]


def fee(case, r, wrong, rank):
    tier = r['tier']
    individual, charity = case['kind'] == 'individual', case['kind'] == 'charity'
    resident = individual and months_between(
        case['registered'], case['event' if 'resident_date' in wrong else 'application']) >= r['resident_months']
    senior_on = r['senior_on'] if 'senior_date' not in wrong else \
        {'event': 'application', 'application': 'event'}[r['senior_on']]
    senior = individual and age_on(case['born'], case[senior_on]) >= r['senior_age']
    commercial = commercial_of(case, r, wrong)
    community = case['purpose'] == 'community event' and not commercial and (
        resident or charity or ('community_nonresident' in wrong and individual))
    minutes = case['end'] - case['start']
    hours = Fraction(minutes, 60) if 'hours_exact' in wrong else ceil(minutes / 60)
    base = hours * (r['community_rate'] if community else r['commercial_rate'] if commercial else r['rate'])
    if charity and (not commercial or 'charity_always' in wrong) and \
            not (community and 'charity_community_free' not in wrong):
        base = 0
    loyal = tier >= 3 and rank >= (2 if 'loyalty_from_second' in wrong else 3)
    if community:
        reductions = [('senior', senior and 'community_no_senior' not in wrong),
                      ('resident', resident and 'community_resident_reduction' in wrong),
                      ('loyalty', loyal and 'loyalty_community' in wrong)]
    else:
        reductions = [('resident', resident), ('senior', senior), ('loyalty', loyal)]
        if commercial and 'reduce_commercial' not in wrong:
            reductions = []
    pct = {'resident': r['resident_pct'], 'senior': r['senior_pct'], 'loyalty': r.get('loyalty_pct', 0)}
    given = [Fraction(pct[name], 100) for name, on in sorted(reductions, key=lambda x: ['resident', 'senior',
                                                                                         'loyalty'].index(x[0]))
             if on]
    combine = r['combine'] if 'combine_other' not in wrong else \
        {'larger': 'sequential', 'sequential': 'larger'}[r['combine']]
    if 'combine_add' in wrong:
        kept = 1 - sum(given)
    elif combine == 'larger':
        kept = 1 - max(given, default=0)
    else:
        kept = 1
        for x in given:
            kept *= 1 - x
    if tier >= 3 and not community and 'cap_ignored' not in wrong:
        kept = max(kept, 1 - Fraction(r['cap_pct'], 100))
    touched = [case['event']] + ([case['event'] + timedelta(days=1)] if case['end'] > DAY else [])
    if 'weekend_start_only' in wrong:
        touched = touched[:1]
    holidays = {date.fromisoformat(d) for d in r.get('holidays', [])}
    weekday_holiday = any(d in holidays and d.weekday() < 5 for d in touched)
    weekend_holiday = any(d in holidays and d.weekday() >= 5 for d in touched)
    weekend = any(d.weekday() >= 5 for d in touched)
    double = (weekday_holiday and 'holiday_single' not in wrong) or \
        (weekend_holiday and 'holiday_weekend_double' in wrong)
    surcharge = r['weekend'] * (2 if double else 1 if weekend or weekday_holiday else 0)
    evening_end = DAY if 'evening_after_midnight' in wrong or tier < 2 else DAY + 6 * 60
    evening = max(0, min(case['end'], evening_end) - max(case['start'], r['evening_from'] * 60))
    if 'evening_whole' in wrong and evening:
        evening = minutes
    surcharge += (Fraction(evening, 60) if 'evening_exact' in wrong else ceil(evening / 60)) * r['evening_rate']
    total = (base + surcharge) * kept if 'surcharge_reduced' in wrong else base * kept + surcharge
    days = (case['event'] - case['application']).days
    late = days <= r['late_days'] if 'late_boundary' in wrong else days < r['late_days']
    if tier >= 2 and case['emergency'] and 'emergency_ignored' not in wrong and \
            (not commercial or 'emergency_commercial' in wrong):
        late = False
    if late:
        total += Fraction(r['late_pct'], 100) * (base * kept if 'late_base' in wrong else total)
    if not charity or 'minimum_charity' in wrong:
        total = max(total, r['minimum'])
    return int(total + Fraction(1, 2))  # nearest whole unit, halves up


def clock(minutes):
    return f'{minutes % DAY // 60:02d}:{minutes % 60:02d}' + (' (next day)' if minutes > DAY else '')


def describe(r):
    tier = r['tier']
    other = {'event': 'application', 'application': 'event'}[r['senior_on']]
    commercial = (f'tickets are sold for it, or its expected attendance exceeds {r["crowd"]} people (either is '
                  'enough)' if r['commercial'] == 'or' else
                  f'tickets are sold for it and, in addition, its expected attendance exceeds {r["crowd"]} people')
    combine = ('When more than one reduction applies, only the largest one is given.' if r['combine'] == 'larger'
               else 'When more than one reduction applies, they are taken one after another in the order resident, '
                    'senior' + (', loyalty' if tier >= 3 else '') + ', each from the amount left after the previous '
                    'ones.')
    s = [
        ('Definitions',
         [f'"Resident" means an individual who, on the date of application, has been registered in the district for '
          f'at least {r["resident_months"]} full months. Organisations are never residents.',
          f'"Senior" means an individual aged {r["senior_age"]} or over on the date of the {r["senior_on"]} (the age '
          f'on the date of the {other} does not matter).',
          f'A booking is "commercial" when {commercial}. A booking made by a business is always commercial.',
          'A booking lasts from its start time to its end time.'
          + (' It starts on the event date; an end time marked "(next day)" is on the day after, and such a booking '
             'falls on both days.' if tier >= 2 else ' It is on the event date.'),
          f'"Evening time" is any booked time from {r["evening_from"]}:00 until midnight'
          + (', and any booked time after midnight until 06:00 the next morning.' if tier >= 2 else '.'),
          'A "community event" is a booking whose stated purpose is a community event.']),
        ('Base fee',
         [f'The base fee is {r["rate"]} for each hour or part of an hour of the booking ({r["commercial_rate"]} for a '
          'commercial booking). For example, a booking of 2 hours 10 minutes is charged as 3 hours.']),
        ('Reductions',
         [f'A resident receives a reduction of {r["resident_pct"]}% of the base fee.',
          f'A senior receives a reduction of {r["senior_pct"]}% of the base fee.']
         + ([f'Loyalty: when one applicant (the same name) has several bookings whose event dates are in the same '
             f'calendar month, those bookings are numbered in order of their application dates (bookings applied for '
             f'on the same date in the order of their case numbers below); the third and every later one receives a '
             f'loyalty reduction of {r["loyalty_pct"]}% of the base fee. Every booking is numbered, including '
             'commercial bookings and bookings that receive no reduction.'] if tier >= 3 else [])
         + [combine, 'Reductions apply to the base fee only. A commercial booking receives no reductions.']
         + ([f'The reductions of this section together never take off more than {r["cap_pct"]}% of the base fee.']
            if tier >= 3 else [])),
        ('Surcharges',
         [('A booking any part of which falls on a Saturday or Sunday' if tier >= 2 else
           'A booking on a Saturday or Sunday') + f' pays a weekend surcharge of {r["weekend"]}.']
         + ([f'Public holidays this year: {", ".join(r["holidays"])}. A booking any part of which falls on a public '
             'holiday that is a Monday to Friday pays the weekend surcharge twice (2 times the amount, once per '
             'booking, whether or not it also falls on a Saturday or Sunday). A public holiday on a Saturday or '
             'Sunday counts as an ordinary weekend day.'] if tier >= 2 else [])
         + [f'A booking pays an evening surcharge of {r["evening_rate"]} for each hour or part of an hour of its '
            'evening time (only the evening time counts, not the rest of the booking).',
            'Surcharges are added after any reduction and are never reduced.']),
        ('Registered charities',
         ['A booking made by a registered charity pays no base fee, unless the booking is commercial, in which case '
          'the base fee is charged in full as in Section 2. Surcharges apply to charities as to everyone else.']),
        ('Community events',
         [f'A community event booked by a resident or by a registered charity is charged {r["community_rate"]} for '
          'each hour or part of an hour instead of the base fee of Section 2 (the "community rate"). This section '
          'prevails over Section 5: a registered charity pays the community rate for a community event.',
          'Despite Section 1(c), selling tickets never makes a community event commercial. However, a community '
          f'event whose expected attendance exceeds {r["crowd"]} people is commercial, and then paragraph (a) does '
          'not apply.',
          'Section 3 does not apply to the community rate, except that a senior still receives the senior '
          'reduction, on its own' + (' and without the limit in Section 3' if tier >= 3 else '') + '.']),
        ('Late applications',
         [f'If the application is made fewer than {r["late_days"]} days before the event date, a late fee of '
          f'{r["late_pct"]}% of the amount due under all the sections above (after reductions and surcharges) is '
          'added.']
         + (['No late fee is charged for an emergency booking, unless the booking is commercial.']
            if tier >= 2 else [])),
        ('Minimum charge',
         [f'Except for bookings made by a registered charity, the amount payable is never less than {r["minimum"]}, '
          'even after all the other sections.']),
        ('Rounding',
         ['Amounts are exact until the end; the amount payable is rounded to the nearest whole unit, and an amount '
          'exactly halfway is rounded up.']),
    ]
    out = []
    for k, (title, clauses) in enumerate(s, 1):
        out.append(f'Section {k}. {title}\n' + '\n'.join(f'({chr(96 + j)}) {c}' for j, c in enumerate(clauses, 1)))
    return '\n\n'.join(out)


def person(rng, r, name, anchors):
    """An individual's fixed facts: born near the senior age and registered near the residence threshold, both
    measured from one of the `anchors` (a booking's application or event date)."""
    anchor = rng.choice(anchors)
    months = r['resident_months'] + rng.choice([-1, 0, 0, 1, rng.randint(-5, 30)])
    year, month = anchor.year, anchor.month - months
    while month < 1:
        year, month = year - 1, month + 12
    target = r['senior_age'] + rng.choice([-1, 0, 0, 1, rng.randint(-20, 15)])
    anchor = rng.choice(anchors)
    born = date(anchor.year - target, anchor.month, min(anchor.day, 28))
    return {'kind': 'individual', 'name': name, 'registered': date(year, month, rng.randint(1, 28)),
            'born': born + timedelta(days=rng.choice([-3, -1, 0, 1, 3, rng.randint(-200, 200)]))}


def booking(rng, r, who, event=None):
    tier = r['tier']
    if event is None:
        holidays = [date.fromisoformat(d) for d in r.get('holidays', [])]
        if holidays and rng.random() < 0.3:
            event = rng.choice(holidays) - timedelta(days=rng.choice([0, 0, 1]))
        else:
            event = date(2026, rng.randint(3, 11), rng.randint(1, 28))
    lead = rng.choice([r['late_days'] - 1, r['late_days'], r['late_days'] + 1, rng.randint(2, 60)])
    case = dict(who, event=event, application=event - timedelta(days=lead), weekday=event.weekday(),
                tickets=rng.random() < 0.4, purpose=rng.choice(PURPOSES + ['community event'] * 2),
                attendance=rng.choice([r['crowd'], r['crowd'] + 1, r['crowd'] - rng.randint(1, 40),
                                       r['crowd'] + rng.randint(2, 60)]),
                emergency=tier >= 2 and rng.random() < 0.3)
    if tier >= 2 and rng.random() < 0.4:  # past midnight
        start = rng.randint(18 * 4, 23 * 4) * 15
        case['end'] = min(DAY + 3 * 60, max(DAY + 15, start + rng.randint(4, 24) * 15 + rng.choice([0, 5, 10])))
    else:
        start = rng.randint(8 * 4, 21 * 4) * 15
        case['end'] = min(DAY, start + rng.randint(3, 22) * 15 + rng.choice([0, 0, 5, 10]))
    case['start'] = start
    return case


def random_case(rng, r, names):
    kind = rng.choice(['individual'] * 3 + ['charity', 'business'])
    pool = {'individual': PEOPLE, 'charity': CHARITIES, 'business': BUSINESSES}[kind]
    name = rng.choice([x for x in pool if x not in names])
    case = booking(rng, r, {'kind': kind, 'name': name})
    if kind == 'individual':
        case.update(person(rng, r, name, [case['application'], case['event']]))
    return case


def loyalty_group(rng, r, names):
    """Five bookings of one individual: four with event dates in one month, one in the next month.  In order of
    application the four are commercial, ordinary, ordinary and a community event, so the loyalty numbering, the
    commercial and community exceptions and the month all matter; event order differs from application order."""
    name = rng.choice([x for x in PEOPLE if x not in names])
    month = rng.randint(3, 10)
    days = rng.sample(range(1, 29), 4)
    while days == sorted(days):
        rng.shuffle(days)
    applied = sorted(rng.sample(range(1, 41), 4), reverse=True)
    out = []
    for role, day, before in zip(['commercial', 'ordinary', 'ordinary', 'community'], days, applied):
        case = booking(rng, r, {'kind': 'individual', 'name': name}, date(2026, month, day))
        case['application'] = date(2026, month, 1) - timedelta(days=before)
        if role == 'commercial':
            case.update(purpose=rng.choice(['concert', 'workshop']), tickets=True,
                        attendance=r['crowd'] + rng.randint(1, 60))
        elif role == 'ordinary':
            case.update(purpose=rng.choice(['private party', 'meeting', 'workshop']), tickets=False,
                        attendance=r['crowd'] - rng.randint(0, 60))
        else:
            case.update(purpose='community event', attendance=r['crowd'] - rng.randint(0, 60))
        if role != 'commercial':  # long enough that the minimum charge does not hide the reductions
            case['start'] = rng.randint(9 * 4, 14 * 4) * 15
            case['end'] = case['start'] + rng.randint(16, 32) * 15 + rng.choice([0, 5, 10])
        out.append(case)
    late = booking(rng, r, {'kind': 'individual', 'name': name}, date(2026, month + 1, rng.randint(1, 10)))
    late.update(application=date(2026, month, 1) - timedelta(days=rng.randint(1, 40)), tickets=False,
                purpose=rng.choice(['private party', 'meeting', 'workshop']), attendance=r['crowd'] - rng.randint(0, 60))
    out.append(late)
    for _ in range(200):  # resident when applying for the community event, so it gets the community rate; not a
        # senior, so the limit on reductions together does not hide the loyalty reduction
        who = person(rng, r, name, [x for c in out for x in (c['application'], c['event'])])
        if months_between(who['registered'], out[3]['application']) >= r['resident_months'] and \
                all(age_on(who['born'], c[k]) < r['senior_age'] for c in out for k in ('application', 'event')):
            break
    return [dict(c, **who) for c in out]


def caught(cases, r, wrongs):
    right = fees(cases, r)
    return frozenset(w for w in wrongs if fees(cases, r, {w}) != right)


def item(rng, tier):
    wrongs = [w for t in range(1, tier + 1) for w in MISREADINGS[t]
              if not (tier >= 3 and w == 'combine_add')]  # under the limit adding is nearly the same as sequential
    size = SIZE[tier]
    for _ in range(40):  # some fee scales make a misreading rare, so each attempt draws the scales again
        r = rules(rng, tier)
        group = []
        for _ in range(200 if tier >= 3 else 0):  # the group alone must catch every loyalty misreading
            group = loyalty_group(rng, r, set())
            if {w for w in wrongs if w.startswith('loyalty')} <= caught(group, r, wrongs):
                break
        names = {c['name'] for c in group}
        pool = []
        for _ in range(1000):
            case = random_case(rng, r, names)
            pool.append((caught([case], r, wrongs), case))
        chosen = list(group)
        while len(chosen) < size:  # greedy cover of the misreadings; names must differ outside the group
            covered = caught(chosen, r, wrongs) if chosen else frozenset()
            taken = {c['name'] for c in chosen}
            chosen.append(max((c for c in pool if c[1]['name'] not in taken),
                              key=lambda c: (len(c[0] - covered), rng.random()))[1])
        for _ in range(60):  # then swap single cases in for the misreadings still missed
            missing = frozenset(wrongs) - caught(chosen, r, wrongs)
            if not missing:
                break
            new = rng.choice([c for c in pool if c[0] & missing])[1]
            options = [chosen[:k] + [new] + chosen[k + 1:] for k in range(len(group), size)
                       if all(c['name'] != new['name'] for j, c in enumerate(chosen) if j != k)]
            best = max(options, key=lambda cs: (len(caught(cs, r, wrongs)), rng.random()), default=None)
            if best is not None and len(caught(best, r, wrongs)) >= len(wrongs) - len(missing):
                chosen = best
        if caught(chosen, r, wrongs) == frozenset(wrongs):
            break
    else:
        raise AssertionError('policy cases do not catch every misreading')
    rng.shuffle(chosen)
    answer = fees(chosen, r)
    listed = '\n'.join(f'Case {k}. {case_text(c, r)}' for k, c in enumerate(chosen, 1))
    prompt = (f'A town hall charges for room bookings under the regulation below.\n\n{describe(r)}\n\nCases:\n\n'
              f'{listed}\n\nQuestion: What amount is payable for each case, in order? Answer with {size} whole '
              'numbers separated by commas (for example ' + ','.join(str(30 + 7 * k) for k in range(size)) + ').')
    return {'kind': 'answer', 'prompt': prompt, 'answer': ','.join(map(str, answer)),
            'policy': {'rules': r, 'misreadings': wrongs,
                       'cases': [{k: v.isoformat() if isinstance(v, date) else v for k, v in c.items()}
                                 for c in chosen]}}


def case_text(case, r):
    who = {'individual': f'{case["name"]}, a private individual', 'charity': f'{case["name"]}, a registered charity',
           'business': f'{case["name"]}, a business'}[case['kind']]
    facts = [f'Applicant: {who}.']
    if case['kind'] == 'individual':
        facts.append(f'Born {case["born"]:%Y-%m-%d}; registered in the district since {case["registered"]:%Y-%m-%d}.')
    facts += [f'Purpose: {case["purpose"]}.',
              f'Application date: {case["application"]:%Y-%m-%d}. Event date: {case["event"]:%Y-%m-%d} '
              f'({WEEKDAYS[case["weekday"]]}).',
              f'Booked from {clock(case["start"])} to {clock(case["end"])}.',
              f'Expected attendance: {case["attendance"]}. Tickets sold: {"yes" if case["tickets"] else "no"}.']
    if r['tier'] >= 2:
        facts.append(f'Emergency booking: {"yes" if case["emergency"] else "no"}.')
    return ' '.join(facts)
