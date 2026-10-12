"""debug: fix a small multi-file Python package from a bug report; hidden tests call its entry function.

Five packages (invoice, scheduler, calendar, calculator, layout), each with a correct reference and a list of
injectable bugs.  Tier 1 injects one bug and the report shows a failing call; tier 2 two bugs in different files, one
shown; tier 3 three bugs, described by symptoms only; level 4 four bugs, symptoms only.  (`tier` here is the
level.)  Each injected bug alone must fail some hidden test, and the
expected values come from running the reference package.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

CALL_RUNNER = '''import json, sys
sys.path.insert(0, sys.argv[1])
module = __import__(sys.argv[2])
entry = getattr(module, sys.argv[3])
out = []
for args in json.load(open(sys.argv[4])):
    try:
        out.append({'value': entry(*args)})
    except Exception as error:
        out.append({'error': type(error).__name__})
print(json.dumps(out))
'''


def call(files, module, entry, args_list):
    """Run entry(*args) for every args in a fresh interpreter on the package `files`; value or error per call."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / 'pkg').mkdir()
        for name, text in files.items():
            (tmp / 'pkg' / name).write_text(text)
        (tmp / 'runner.py').write_text(CALL_RUNNER)
        (tmp / 'args.json').write_text(json.dumps(args_list))
        reply = subprocess.run([sys.executable, '-I', 'runner.py', str(tmp / 'pkg'), module, entry, 'args.json'],
                               cwd=tmp, capture_output=True, text=True, timeout=60, check=True)
        return json.loads(reply.stdout)


# ---------------------------------------------------------------- invoice

INVOICE = {
    'money.py': '''"""Money helpers. Amounts are integer cents."""


def parse(text):
    """'12.5' -> 1250, '-0.05' -> -5, '7' -> 700, '.5' -> 50. At most two decimals."""
    text = text.strip()
    sign = -1 if text.startswith('-') else 1
    whole, _, frac = text.lstrip('+-').partition('.')
    if len(frac) > 2:
        raise ValueError(text)
    return sign * (int(whole or '0') * 100 + int((frac + '00')[:2]))


def percent(amount, rate_bp):
    """amount * rate_bp / 10000 rounded to the nearest cent; halves round away from zero."""
    q, r = divmod(abs(amount) * rate_bp, 10000)
    if 2 * r >= 10000:
        q += 1
    return q if amount >= 0 else -q


def fmt(cents):
    """1250 -> '12.50', -5 -> '-0.05'."""
    sign = '-' if cents < 0 else ''
    cents = abs(cents)
    return f'{sign}{cents // 100}.{cents % 100:02d}'
''',
    'cart.py': '''from money import parse

DEAL = __DEAL__  # SKUs on "buy 3, pay 2"


def lines_total(lines):
    """Sum of price * quantity in cents.  lines: [{'sku': str, 'price': str, 'qty': int}], qty >= 1.
    For a SKU in DEAL every third unit is free, counting the units of that SKU over all lines together (the free
    units are taken at the lowest price among its lines)."""
    total, deal_units = 0, {}
    for line in lines:
        price, qty = parse(line['price']), line['qty']
        if qty < 1:
            raise ValueError(line)
        total += price * qty
        if line['sku'] in DEAL:
            deal_units.setdefault(line['sku'], []).extend([price] * qty)
    for prices in deal_units.values():
        total -= sum(sorted(prices)[:len(prices) // 3])
    return total
''',
    'invoice.py': '''from cart import lines_total
from money import fmt, percent

COUPON_BP = __COUPON__     # coupon discount rate in basis points
COUPON_MIN = __MIN__     # the coupon applies when the subtotal is at least this many cents
COUPON_CAP = __CAP__     # and the discount is at most this many cents
TAX_BP = __TAX__         # tax on the subtotal after the discount


def invoice(lines, coupon):
    """{'subtotal', 'discount', 'tax', 'total'} as formatted strings."""
    subtotal = lines_total(lines)
    discount = 0
    if coupon and subtotal >= COUPON_MIN:
        discount = min(percent(subtotal, COUPON_BP), COUPON_CAP)
    taxed = subtotal - discount
    tax = percent(taxed, TAX_BP)
    return {'subtotal': fmt(subtotal), 'discount': fmt(discount), 'tax': fmt(tax), 'total': fmt(taxed + tax)}
''',
}

INVOICE_BUGS = [
    ('money.py', "int((frac + '00')[:2])", "int(frac or '0')",
     'prices written with one decimal digit (like "3.5") come out far too small'),
    ('money.py', 'if 2 * r >= 10000:', 'if 2 * r > 10000:', 'some taxes are one cent too low'),
    ('money.py', "{cents % 100:02d}", "{cents % 100}", 'some amounts are printed wrongly, e.g. with too few digits'),
    ('cart.py', '''        if line['sku'] in DEAL:
            deal_units.setdefault(line['sku'], []).extend([price] * qty)''', '''        if line['sku'] in DEAL:
            deal_units.setdefault(line['sku'] + str(len(deal_units)), []).extend([price] * qty)''',
     'the buy-3-pay-2 deal is missed when the same product appears on several lines'),
    ('cart.py', 'sorted(prices)[:len(prices) // 3]', 'sorted(prices)[-(len(prices) // 3):] if len(prices) >= 3 else []',
     'deal discounts are sometimes larger than they should be'),
    ('invoice.py', 'subtotal >= COUPON_MIN', 'subtotal > COUPON_MIN', 'a coupon is sometimes refused at the minimum'),
    ('invoice.py', 'tax = percent(taxed, TAX_BP)', 'tax = percent(subtotal, TAX_BP)', 'tax looks too high with coupons'),
    ('invoice.py', 'min(percent(subtotal, COUPON_BP), COUPON_CAP)', 'percent(subtotal, COUPON_BP)',
     'large orders get too much discount'),
]


def invoice_args(rng, count):
    skus = ['pen', 'ink', 'pad', 'clip', 'tape']
    out = []
    for _ in range(count):
        lines = []
        for _ in range(rng.randint(1, 5)):
            cents = rng.choice([rng.randint(1, 4000), rng.randint(1, 40) * 50, rng.randint(1, 99) * 10])
            text = f'{cents // 100}.{cents % 100:02d}'
            if cents % 10 == 0 and rng.random() < 0.5:
                text = text[:-1]
            if text.startswith('0.') and rng.random() < 0.3:
                text = text[1:]
            lines.append({'sku': rng.choice(skus), 'price': text, 'qty': rng.randint(1, 7)})
        if rng.random() < 0.2:  # exactly at a coupon minimum
            lines = [{'sku': 'pen', 'price': rng.choice(['20', '20.00', '50', '50.0']), 'qty': 1}]
        out.append([lines, rng.random() < 0.7])
    return out


def invoice_setup(rng):
    deal = sorted(rng.sample(['pen', 'ink', 'pad', 'clip', 'tape'], 2))
    return {'__DEAL__': repr(set(deal)), '__COUPON__': str(rng.choice([500, 1000, 1500, 2500])),
            '__MIN__': str(rng.choice([2000, 5000])), '__CAP__': str(rng.choice([1500, 3000])),
            '__TAX__': str(rng.choice([625, 750, 825, 1050]))}


# ---------------------------------------------------------------- scheduler

SCHEDULER = {
    'heap.py': '''"""Binary min-heap of comparable items."""


class Heap:
    def __init__(self):
        self.items = []

    def __len__(self):
        return len(self.items)

    def push(self, item):
        h = self.items
        h.append(item)
        i = len(h) - 1
        while i > 0 and h[i] < h[(i - 1) // 2]:
            h[i], h[(i - 1) // 2] = h[(i - 1) // 2], h[i]
            i = (i - 1) // 2

    def pop(self):
        h = self.items
        top, last = h[0], h.pop()
        if h:
            h[0] = last
            i, n = 0, len(h)
            while 2 * i + 1 < n:
                child = 2 * i + 1
                if child + 1 < n and h[child + 1] < h[child]:
                    child += 1
                if h[child] < h[i]:
                    h[i], h[child] = h[child], h[i]
                    i = child
                else:
                    break
        return top
''',
    'tasks.py': '''"""Task specs: "name:priority:duration" or "name:priority:duration:after1,after2"."""


def parse(spec):
    parts = spec.split(':')
    name, priority, duration = parts[0], int(parts[1]), int(parts[2])
    after = [x for x in parts[3].split(',') if x] if len(parts) > 3 else []
    if duration < 1:
        raise ValueError(spec)
    return {'name': name, 'priority': priority, 'duration': duration, 'after': after}
''',
    'runner.py': '''from heap import Heap
from tasks import parse


def run(specs):
    """One worker, starting at time 0.  A task is ready when every task in its `after` list has finished; among
    ready tasks the lowest priority number runs first, ties by position in `specs`.  A task runs to the end
    without interruption.  Returns {'order': [[name, start, end], ...], 'blocked': sorted names never run}.
    A task that waits for an unknown name, or for itself through a chain, never runs."""
    tasks = [parse(s) for s in specs]
    waiting = {t['name']: set(t['after']) for t in tasks}
    heap, clock, order, done = Heap(), 0, [], set()
    for index, t in enumerate(tasks):
        if not waiting[t['name']]:
            heap.push((t['priority'], index))
    while len(heap):
        _, index = heap.pop()
        t = tasks[index]
        order.append([t['name'], clock, clock + t['duration']])
        clock += t['duration']
        done.add(t['name'])
        for other_index, other in enumerate(tasks):
            if other['name'] not in done and t['name'] in waiting[other['name']]:
                waiting[other['name']].discard(t['name'])
                if not waiting[other['name']]:
                    heap.push((other['priority'], other_index))
    return {'order': order, 'blocked': sorted(t['name'] for t in tasks if t['name'] not in done)}
''',
}

SCHEDULER_BUGS = [
    ('heap.py', 'if child + 1 < n and h[child + 1] < h[child]:', 'if child + 1 < n - 1 and h[child + 1] < h[child]:',
     'with many ready tasks the order is sometimes not by priority'),
    ('heap.py', 'while i > 0 and h[i] < h[(i - 1) // 2]:', 'while i > 1 and h[i] < h[(i - 1) // 2]:',
     'a newly ready urgent task sometimes waits behind less urgent ones'),
    ('tasks.py', "int(parts[1])", "int(parts[1].lstrip('-'))", 'negative priorities are not respected'),
    ('runner.py', 'heap.push((t[\'priority\'], index))', "heap.push((t['priority'], -index))",
     'sometimes a task runs before the tasks it waits for, or a task never runs'),
    ('runner.py', "order.append([t['name'], clock, clock + t['duration']])\n        clock += t['duration']",
     "clock += t['duration']\n        order.append([t['name'], clock - t['duration'] + 1, clock])",
     'start times are off'),
    ('runner.py', "'blocked': sorted(t['name'] for t in tasks if t['name'] not in done)",
     "'blocked': [t['name'] for t in tasks if t['name'] not in done]", 'the blocked list comes out in a strange order'),
]


def scheduler_args(rng, count):
    out = []
    for _ in range(count):
        names = rng.sample(['ant', 'bee', 'cat', 'dog', 'eel', 'fox', 'gnu', 'hen', 'ibis', 'jay', 'kiwi'],
                           rng.randint(3, 9))
        specs = []
        for i, name in enumerate(names):
            spec = f'{name}:{rng.randint(-3, 5)}:{rng.randint(1, 9)}'
            if rng.random() < 0.4:
                pool = names[:i] + (['ghost'] if rng.random() < 0.15 else []) + \
                    ([names[min(i + 1, len(names) - 1)]] if rng.random() < 0.1 else [])
                if pool:
                    spec += ':' + ','.join(rng.sample(pool, min(len(pool), rng.randint(1, 2))))
            specs.append(spec)
        out.append([specs])
    return out


# ---------------------------------------------------------------- calendar

CALENDAR = {
    'clock.py': '''"""Times of day as "H:MM" (0:00 to 24:00) and minutes since midnight."""


def to_minutes(text):
    hours, minutes = text.strip().split(':')
    value = int(hours) * 60 + int(minutes)
    if len(minutes) != 2 or not 0 <= value <= 24 * 60:
        raise ValueError(text)
    return value


def to_text(value):
    return f'{value // 60}:{value % 60:02d}'
''',
    'merge.py': '''def merge(intervals):
    """Union of [start, end) minute intervals as a sorted list of disjoint pairs; touching intervals are joined
    and empty intervals (start >= end) are dropped."""
    out = []
    for start, end in sorted(i for i in intervals if i[0] < i[1]):
        if out and start <= out[-1][1]:
            out[-1][1] = max(out[-1][1], end)
        else:
            out.append([start, end])
    return out
''',
    'free.py': '''from clock import to_minutes, to_text
from merge import merge


def free_slots(busy, day_start, day_end, shortest):
    """Free gaps between day_start and day_end ("H:MM") that are at least `shortest` minutes long
    (`shortest` is always a positive whole number of minutes), as "H:MM-H:MM" strings in time order.  busy: list of "H:MM-H:MM" (a busy interval may reach outside the day;
    only its part inside the day counts)."""
    lo, hi = to_minutes(day_start), to_minutes(day_end)
    taken = []
    for item in busy:
        start, end = (to_minutes(x) for x in item.split('-'))
        taken.append([max(start, lo), min(end, hi)])
    out, cursor = [], lo
    for start, end in merge(taken) + [[hi, hi]]:
        if start - cursor >= shortest:
            out.append(to_text(cursor) + '-' + to_text(start))
        cursor = max(cursor, end)
    return out
''',
}

CALENDAR_BUGS = [
    ('clock.py', "{value % 60:02d}", "{value % 60}", 'some times are printed like 9:5'),
    ('clock.py', 'int(hours) * 60 + int(minutes)', 'int(hours[-1]) * 60 + int(minutes)',
     'afternoon meetings seem to be ignored or misplaced'),
    ('merge.py', 'sorted(i for i in intervals if i[0] < i[1])',
     'sorted((i for i in intervals if i[0] < i[1]), key=lambda i: i[1])',
     'with overlapping meetings some busy time is reported as free'),
    ('merge.py', 'out[-1][1] = max(out[-1][1], end)', 'out[-1][1] = end',
     'a long meeting that contains a shorter one is partly reported as free'),
    ('free.py', 'taken.append([max(start, lo), min(end, hi)])', 'taken.append([start, end])',
     'meetings outside the working day produce wrong free slots'),
    ('free.py', 'if start - cursor >= shortest:', 'if start - cursor > shortest:',
     'slots of exactly the minimum length are missing'),
]


def calendar_args(rng, count):
    out = []
    for _ in range(count):
        lo = rng.choice([7, 8, 9]) * 60 + rng.choice([0, 30])
        hi = rng.choice([16, 17, 18, 22]) * 60 + rng.choice([0, 15])
        busy = []
        for _ in range(rng.randint(1, 7)):
            start = rng.randint(lo - 90, hi + 120) // 5 * 5
            end = start + rng.choice([0, 15, 30, 45, 60, 90, 240])
            busy.append(f'{start // 60}:{start % 60:02d}-{min(end, 1440) // 60}:{min(end, 1440) % 60:02d}')
        if busy and rng.random() < 0.5:  # back to back
            last = busy[-1].split('-')[1]
            busy.append(f'{last}-{int(last.split(":")[0]) + 1}:{last.split(":")[1]}')
        rng.shuffle(busy)
        out.append([busy, f'{lo // 60}:{lo % 60:02d}', f'{hi // 60}:{hi % 60:02d}', rng.choice([15, 30, 45, 60])])
    return out


# ---------------------------------------------------------------- calculator

CALCULATOR = {
    'lexer.py': '''def tokens(text):
    """Integers and the symbols + - * / % ^ ( ); spaces are ignored."""
    out, i = [], 0
    while i < len(text):
        c = text[i]
        if c.isspace():
            i += 1
        elif c.isdigit():
            j = i
            while j < len(text) and text[j].isdigit():
                j += 1
            out.append(int(text[i:j]))
            i = j
        elif c in '+-*/%^()':
            out.append(c)
            i += 1
        else:
            raise ValueError(c)
    return out
''',
    'parser.py': '''"""Grammar, loosest first:
  sum     := product (('+' | '-') product)*         left associative
  product := unary (('*' | '/' | '%') unary)*       left associative; '/' is floor division, '%' Python modulo
  unary   := '-' unary | power                       so -2^2 == -(2^2)
  power   := atom ('^' unary)?                       right associative: 2^3^2 == 2^(3^2)
  atom    := integer | '(' sum ')'
"""


class Parser:
    def __init__(self, tokens):
        self.tokens, self.i = tokens, 0

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def take(self):
        self.i += 1
        return self.tokens[self.i - 1]

    def sum(self):
        value = self.product()
        while self.peek() in ('+', '-'):
            value = value + self.product() if self.take() == '+' else value - self.product()
        return value

    def product(self):
        value = self.unary()
        while self.peek() in ('*', '/', '%'):
            op, right = self.take(), self.unary()
            value = value * right if op == '*' else value // right if op == '/' else value % right
        return value

    def unary(self):
        if self.peek() == '-':
            self.take()
            return -self.unary()
        return self.power()

    def power(self):
        base = self.atom()
        if self.peek() == '^':
            self.take()
            return base ** self.unary()
        return base

    def atom(self):
        token = self.take()
        if token == '(':
            value = self.sum()
            if self.take() != ')':
                raise SyntaxError('expected )')
            return value
        if isinstance(token, int):
            return token
        raise SyntaxError(repr(token))
''',
    'calc.py': '''from lexer import tokens
from parser import Parser


def calc(text):
    parser = Parser(tokens(text))
    value = parser.sum()
    if parser.peek() is not None:
        raise SyntaxError('trailing input')
    return value
''',
}

CALCULATOR_BUGS = [
    ('lexer.py', 'while j < len(text) and text[j].isdigit():', 'while j < len(text) and text[j].isdigit() and j - i < 2:',
     'long numbers are misread'),
    ('parser.py', "            value = value + self.product() if self.take() == '+' else value - self.product()",
     "            value = value + self.sum() if self.take() == '+' else value - self.sum()",
     'chains of subtractions give odd results'),
    ('parser.py', "value // right if op == '/'", "int(value / right) if op == '/'",
     'division of negative numbers is off'),
    ('parser.py', '''        if self.peek() == '-':
            self.take()
            return -self.unary()
        return self.power()''', '''        if self.peek() == '-':
            self.take()
            value = -self.atom()
            if self.peek() == '^':
                self.take()
                return value ** self.unary()
            return value
        return self.power()''', 'a minus sign in front of a power gives the wrong sign'),
    ('parser.py', '''            return base ** self.unary()
        return base''', '''            value = base ** self.atom()
            while self.peek() == '^':
                self.take()
                value = value ** self.atom()
            return value
        return base''', 'stacked powers like 2^3^2 come out wrong'),
]


def calculator_args(rng, count):
    def expr(depth):
        roll = rng.random()
        if depth == 0 or roll < 0.25:
            return str(rng.choice([rng.randint(0, 9), rng.randint(10, 999)]))
        if roll < 0.35:
            return '-' + expr(depth - 1)
        if roll < 0.45:
            return '(' + expr(depth - 1) + ')'
        if roll < 0.6:
            base = rng.choice(['2', '3', '-2', '(1+1)', str(rng.randint(2, 5))])
            tail = rng.choice(['2', '3', '0', '2^2', '1^3', '2^1^2'])
            return base + '^' + tail
        return expr(depth - 1) + rng.choice([' + ', ' - ', ' * ', ' / ', ' % ', '-']) + expr(depth - 1)
    out = []
    while len(out) < count:
        if rng.random() < 0.3:  # a flat chain, where associativity matters
            text = expr(1) + ''.join(rng.choice([' - ', '-', ' + ', ' - ', ' / ', ' % ']) + expr(1)
                                     for _ in range(rng.randint(2, 4)))
        else:
            text = expr(rng.randint(2, 4))
        try:
            value = eval(text.replace('^', '**').replace('/', '//'))
        except ZeroDivisionError:
            continue
        if isinstance(value, int) and abs(value) < 10 ** 12:
            out.append([text])
    return out


# ---------------------------------------------------------------- layout

LAYOUT = {
    'wrap.py': '''def wrap(text, width):
    """Greedy word wrap: words are separated by any whitespace; a line holds as many words as fit in `width`
    characters with single spaces between them; a word longer than `width` is cut into pieces of `width`
    characters (the last piece may be shorter and is then treated as a word)."""
    lines, line = [], ''
    for word in text.split():
        while len(word) > width:
            if line:
                lines.append(line)
                line = ''
            lines.append(word[:width])
            word = word[width:]
        if not word:
            continue
        if line and len(line) + 1 + len(word) <= width:
            line += ' ' + word
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines
''',
    'table.py': '''def is_number(cell):
    """Integers, optionally negative: '42', '-7'."""
    return cell.lstrip('-').isdigit() and cell.count('-') <= 1 and not cell.endswith('-')


def render(rows):
    """Columns padded to the widest cell of that column over all rows; numbers right-aligned, other cells
    left-aligned; columns joined by ' | '; no trailing spaces.  Short rows are padded with empty cells."""
    columns = max(len(r) for r in rows)
    rows = [list(r) + [''] * (columns - len(r)) for r in rows]
    widths = [max(len(r[c]) for r in rows) for c in range(columns)]
    out = []
    for r in rows:
        cells = [cell.rjust(w) if is_number(cell) else cell.ljust(w) for cell, w in zip(r, widths)]
        out.append(' | '.join(cells).rstrip())
    return out
''',
    'layout.py': '''from table import render
from wrap import wrap


def layout(rows, caption, width):
    """The rendered table, an empty line, then the caption wrapped to `width`."""
    return render(rows) + [''] + wrap(caption, width)
''',
}

LAYOUT_BUGS = [
    ('wrap.py', 'len(line) + 1 + len(word) <= width', 'len(line) + 1 + len(word) < width',
     'some lines are wrapped earlier than necessary'),
    ('wrap.py', '            lines.append(word[:width])\n            word = word[width:]',
     '            lines.append(word[:width])\n            word = word[width + 1:]', 'long words lose characters'),
    ('table.py', "return cell.lstrip('-').isdigit()", "return cell.isdigit()", 'negative numbers are aligned to the left'),
    ('table.py', "        out.append(' | '.join(cells).rstrip())", "        out.append(' | '.join(cells))",
     'some lines end with spaces'),
    ('table.py', 'widths = [max(len(r[c]) for r in rows) for c in range(columns)]',
     'widths = [len(rows[0][c]) for c in range(columns)]', 'columns are misaligned when a later cell is wider'),
]


def layout_args(rng, count):
    words = ['alpha', 'be', 'cat', 'delta', 'e', 'foxtrot', 'golf', 'hotelier', 'id', 'jupiterian', 'kilo',
             'supercalifragilistic', 'x']
    out = []
    for _ in range(count):
        rows = []
        for _ in range(rng.randint(1, 4)):
            cells = ['', 'ab', 'name', str(rng.randint(-99, 999)), str(rng.randint(-9, -1)), '-', '3-4', 'Total']
            rows.append([rng.choice(cells) for _ in range(rng.randint(1, 4))])
        caption = (' ' * rng.randint(0, 2)).join(rng.choice(words) + rng.choice([' ', '  ', '\n'])
                                                 for _ in range(rng.randint(0, 12)))
        out.append([rows, caption, rng.randint(4, 16)])
    return out


PACKAGES = {
    'invoice': {'files': INVOICE, 'module': 'invoice', 'entry': 'invoice', 'bugs': INVOICE_BUGS,
                'args': invoice_args, 'setup': invoice_setup,
                'about': 'computes an invoice (subtotal, coupon discount, tax, total) from order lines'},
    'scheduler': {'files': SCHEDULER, 'module': 'runner', 'entry': 'run', 'bugs': SCHEDULER_BUGS,
                  'args': scheduler_args, 'about': 'runs prioritised tasks with dependencies on one worker'},
    'calendar': {'files': CALENDAR, 'module': 'free', 'entry': 'free_slots', 'bugs': CALENDAR_BUGS,
                 'args': calendar_args, 'about': 'lists the free time slots of a day around busy meetings'},
    'calculator': {'files': CALCULATOR, 'module': 'calc', 'entry': 'calc', 'bugs': CALCULATOR_BUGS,
                   'args': calculator_args, 'about': 'evaluates integer arithmetic expressions'},
    'layout': {'files': LAYOUT, 'module': 'layout', 'entry': 'layout', 'bugs': LAYOUT_BUGS,
               'args': layout_args, 'about': 'renders a text table followed by a word-wrapped caption'},
}
ORDER = list(PACKAGES)


def inject(files, bugs):
    out = dict(files)
    for name, old, new, _ in bugs:
        if out[name].count(old) != 1:
            raise AssertionError(f'bug anchor not unique in {name}: {old!r}')
        out[name] = out[name].replace(old, new)
    return out


def item(rng, tier, seed):
    name = ORDER[seed % len(ORDER)]
    package = PACKAGES[name]
    files = dict(package['files'])
    if 'setup' in package:
        for key, value in package['setup'](rng).items():
            files = {n: t.replace(key, value) for n, t in files.items()}
    args = package['args'](rng, 45)
    reference = call(files, package['module'], package['entry'], args)
    keep = [(a, r['value']) for a, r in zip(args, reference) if 'value' in r]
    args = [a for a, _ in keep]
    tests = [{'args': a, 'expected': v} for a, v in keep]

    def failing(bugs):
        got = call(inject(files, bugs), package['module'], package['entry'], args)
        return [k for k, (g, t) in enumerate(zip(got, tests)) if g.get('value', g) != t['expected']]
    for _ in range(100):
        count = {1: 1, 2: 2, 3: 3, 4: 4}[tier]
        bugs = rng.sample(package['bugs'], count)
        if len({b[0] for b in bugs}) < min(count, 2):
            continue
        if all(len(failing([b])) >= 2 for b in bugs):  # one failing call may be shown, another stays hidden
            break
    else:
        raise AssertionError(f'{name}: no detectable bug set')
    broken = inject(files, bugs)
    first = failing(bugs[:1])[0]
    shown = call(broken, package['module'], package['entry'], [args[first]])[0]
    call_text = f'{package["entry"]}({", ".join(map(repr, args[first]))})'
    example = (f'For example, `{call_text}` returns `{shown["value"]!r}`, but the correct result is '
               f'`{tests[first]["expected"]!r}`.' if 'value' in shown else
               f'For example, `{call_text}` raises {shown["error"]}, but the correct result is '
               f'`{tests[first]["expected"]!r}`.')
    symptoms = [b[3] for b in bugs]
    if tier == 1:
        report = f'{symptoms[0][0].upper() + symptoms[0][1:]}. {example}'
    elif tier == 2:
        report = (f'Two problems were reported. {example} Separately, users say that {symptoms[1]}.')
    else:
        report = 'Users report several problems: ' + '; '.join(symptoms) + '. No failing example is available.'
    if tier <= 2:  # the shown call is not a hidden test
        tests = [t for k, t in enumerate(tests) if k != first]
    listing = ', '.join(f'`{n}`' for n in sorted(files))
    prompt = (f'The Python package in `solutions/{{P}}/` ({listing}) {package["about"]}. The docstrings and comments '
              f'describe the intended behaviour and are correct; the code has bugs.\n\nBug report: {report}\n\n'
              f'Fix the files in place so that `{package["module"]}.{package["entry"]}` behaves exactly as the '
              'docstrings describe. Keep the file names and function signatures. Hidden tests put that directory on '
              f'the import path, import `{package["module"]}` and call `{package["entry"]}` on many inputs. Use only '
              'the Python 3 standard library.')
    return {'kind': 'package', 'entry': package['entry'], 'module': package['module'], 'package': name,
            'prompt': prompt, 'files': broken, 'tests': tests, 'bugs': [[b[0], b[1], b[2]] for b in bugs]}
