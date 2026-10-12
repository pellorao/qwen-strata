"""Generated, program-judged question bank for the sampling tuning workload (v3).

Five directions, three tiers (tools.tuning.sampling_families): ledger (implement a long settlement specification),
machine (output of a register machine whose semantics are easy to misread), count (counting that needs modelling,
far beyond enumeration), codec (inverse of a multi-step text encoder), debug (fix a small multi-file package from a
bug report).  The solver has a shell, so difficulty never comes from computation: run2/run3 showed Qwen solving every
computable v2 item.  It comes from reading long rules exactly, traps and edge cases, long chains of steps, and having
to work out what to compute.  Answers and hidden tests come from reference code, checked against brute force or a
round trip in the tests.

    python3 -m tools.tuning.sampling_bank build --seed S --out bank.json         # candidate bank (with answers)
    python3 -m tools.tuning.sampling_bank export --bank bank.json --out DIR      # answer-free workspace
    python3 -m tools.tuning.sampling_bank score --bank bank.json --workspace DIR # instance score
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from tools.tuning.sampling_families import FAMILIES, TIERS, item

CODE_TIMEOUT_SECONDS = 20


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def generator_sha():
    files = [Path(__file__)] + sorted((Path(__file__).parent / 'sampling_families').glob('*.py'))
    return sha(b''.join(f.name.encode() + b'\0' + f.read_bytes() for f in files))


def build(seed, per_cell):
    """Candidate bank: `per_cell` items for every family and tier, seeds seed*1000 + k."""
    items = [item(f, t, seed * 1000 + k) for t in TIERS for f in FAMILIES for k in range(per_cell)]
    items = [dict(x, number=f'C{n:03d}') for n, x in enumerate(items, 1)]
    return {'schema': 'sampling-bank-v3', 'generator_sha256': generator_sha(), 'seed': seed,
            'per_cell': per_cell, 'items': items}


def select(bank, ids):
    """Frozen set: the given items in the given order, numbered P01.. ."""
    by_id = {i['id']: i for i in bank['items']}
    items = [dict(by_id[x], number=f'P{n:02d}') for n, x in enumerate(ids, 1)]
    return {**bank, 'schema': 'sampling-set-v1', 'items': items}


def grouped(bank):
    """Fixed set order: direction by direction (FAMILIES order), tiers ascending, candidate order within a cell; the
    driver runs the set in groups along this order (tools.tuning.codex_workload.groups)."""
    return [x['id'] for x in sorted(bank['items'], key=lambda x: (FAMILIES.index(x['family']), x['tier']))]


# ---------------------------------------------------------------- workspace and scoring

SET_README = '''# Problem set

Each problem is in `problems/<P>.md`. Solve every problem.

- Answer problems (they end with a "Question:"): write only the final answer to `answers/<P>.txt`, one line,
  in the format the problem asks for.
- Code problems (they ask you to implement or fix code): write the requested function in `solutions/<P>.py` (a stub
  is there), or, when the problem's files are under `solutions/<P>/`, fix those files in place. Only the Python 3
  standard library is available.

You may use the shell and write scratch files anywhere inside this directory. Paths outside it, including /tmp,
are not available. Nothing outside this directory is needed. Answers are checked automatically after you finish;
there is no partial credit inside a problem.

There is a hard time limit. When it is reached you are stopped without warning and only the files already written
are scored; a problem with no written answer or solution scores zero. So write each answer or solution file as soon
as that problem is done, before moving to the next one, and do the problems you are surest of first.
'''


def export(bank, folder, numbers=None):
    """Answer-free workspace for the selected numbers (all by default)."""
    folder = Path(folder)
    for sub in ('problems', 'answers', 'solutions'):
        (folder / sub).mkdir(parents=True, exist_ok=True)
    (folder / 'README.md').write_text(SET_README)
    for x in bank['items']:
        if numbers and x['number'] not in numbers:
            continue
        prompt = x['prompt'].replace('{P}', x['number'])
        (folder / 'problems' / (x['number'] + '.md')).write_text(f'# {x["number"]}\n\n{prompt}\n')
        if x['kind'] == 'code':
            (folder / 'solutions' / (x['number'] + '.py')).write_text(x['stub'])
        elif x['kind'] == 'package':
            (folder / 'solutions' / x['number']).mkdir(exist_ok=True)
            for name, text in x['files'].items():
                (folder / 'solutions' / x['number'] / name).write_text(text)
    return folder


def written(x, workspace):
    """The item's result files if the solver wrote or changed them, else None: answer text, solution source, or
    the package's {name: bytes}."""
    workspace = Path(workspace)
    if x['kind'] == 'answer':
        path = workspace / 'answers' / (x['number'] + '.txt')
        return path.read_text(errors='replace') if path.is_file() else None
    if x['kind'] == 'code':
        path = workspace / 'solutions' / (x['number'] + '.py')
        source = path.read_bytes() if path.is_file() else b''
        return source if source and source != x['stub'].encode() else None
    folder = workspace / 'solutions' / x['number']
    files = {f.name: f.read_bytes() for f in folder.glob('*.py')} if folder.is_dir() else {}
    return files if files and files != {k: v.encode() for k, v in x['files'].items()} else None


def written_at(x, workspace):
    """Latest modification time of the item's result files (None when nothing was written)."""
    workspace = Path(workspace)
    if written(x, workspace) is None:
        return None
    if x['kind'] == 'answer':
        return (workspace / 'answers' / (x['number'] + '.txt')).stat().st_mtime
    if x['kind'] == 'code':
        return (workspace / 'solutions' / (x['number'] + '.py')).stat().st_mtime
    return max(f.stat().st_mtime for f in (workspace / 'solutions' / x['number']).glob('*.py'))


def normalize(text):
    return ','.join(part.strip().strip('`').strip().lower() for part in text.strip().strip('`').split(','))


RUNNER = '''import json, sys
sys.path.insert(0, sys.argv[1])
entry = getattr(__import__(sys.argv[2]), sys.argv[3])
passed = 0
for case in json.load(open(sys.argv[4])):
    try:
        passed += entry(*case['args']) == case['expected']
    except Exception:
        pass
print(json.dumps({'passed': passed}))
'''


def run_tests(files, module, entry, tests):
    """Hidden tests in a separate isolated interpreter with a time limit, the solution files ({name: bytes}) alone
    on the import path; any failure to run scores zero."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / 'runner.py').write_text(RUNNER)
        (tmp / 'tests.json').write_text(json.dumps(tests))
        (tmp / 'solution').mkdir()
        for name, raw in files.items():
            (tmp / 'solution' / name).write_bytes(raw)
        try:
            reply = subprocess.run([sys.executable, '-I', 'runner.py', 'solution', module, entry, 'tests.json'],
                                   cwd=tmp, capture_output=True, text=True, timeout=CODE_TIMEOUT_SECONDS)
            passed = json.loads(reply.stdout.strip().splitlines()[-1])['passed']
        except (subprocess.TimeoutExpired, ValueError, IndexError, KeyError):
            passed = 0
    return passed


def points_of(bank):
    """Per-item points of a frozen set (all items carry `points`), or None for an unweighted draft or pilot set."""
    given = [x.get('points') for x in bank['items']]
    if all(p is None for p in given):
        return None
    if any(p is None or p <= 0 for p in given):
        raise ValueError('Either every item has positive points or none has')
    return {x['id']: x['points'] for x in bank['items']}


def score(bank, workspace):
    """Per item: correct is all-or-nothing.  Instance score = points of correct items / all points (each item one
    point in an unweighted set); per-tier rates are reported unweighted."""
    workspace, rows = Path(workspace), []
    points = points_of(bank)
    for x in bank['items']:
        given = written(x, workspace)
        row = {'number': x['number'], 'id': x['id'], 'tier': x['tier'], 'family': x['family'],
               'answered': given is not None}
        if x['kind'] == 'answer':
            row['correct'] = given is not None and normalize(given) == normalize(x['answer'])
        else:
            files = {'solution.py': given} if x['kind'] == 'code' else given
            module = 'solution' if x['kind'] == 'code' else x['module']
            passed = run_tests(files, module, x['entry'], x['tests']) if given is not None else 0
            row.update(correct=passed == len(x['tests']), tests_passed=passed, tests_total=len(x['tests']))
        rows.append(row)
        rows[-1]['points'] = points[x['id']] if points else 1
    return weighted(rows)


def weighted(rows):
    by_tier = {t: [r['correct'] for r in rows if r['tier'] == t] for t in TIERS}
    by_family = {f: [r['correct'] for r in rows if r['family'] == f] for f in FAMILIES}
    total = sum(r['points'] for r in rows)
    return {'score': sum(r['points'] for r in rows if r['correct']) / total, 'points_total': total,
            'correct': sum(r['correct'] for r in rows), 'items': len(rows),
            'by_tier': {t: sum(v) / len(v) for t, v in by_tier.items() if v},
            'by_family': {f: sum(v) / len(v) for f, v in by_family.items() if v}, 'rows': rows}


def reference_files(x):
    """A package item's reference: the given files with every injected bug reverted."""
    files = dict(x['files'])
    for name, old, new in x['bugs']:
        files[name] = files[name].replace(new, old)
    return {k: v.encode() for k, v in files.items()}


def self_check(bank):
    """No-model precheck: reference answers are canonical, hidden tests exist, a package's reference passes them
    and its given files fail them, and the exported workspace holds no answer or hidden expected value."""
    problems = []
    for x in bank['items']:
        if x['kind'] == 'answer':
            if not x['answer'] or normalize(x['answer']) != x['answer'].lower():
                problems.append(x['id'] + ': answer not in canonical form')
        elif not x['tests'] or any('expected' not in t for t in x['tests']):
            problems.append(x['id'] + ': missing hidden tests')
        elif x['kind'] == 'package':
            given = {k: v.encode() for k, v in x['files'].items()}
            if run_tests(reference_files(x), x['module'], x['entry'], x['tests']) != len(x['tests']):
                problems.append(x['id'] + ': the reference package fails its hidden tests')
            if run_tests(given, x['module'], x['entry'], x['tests']) == len(x['tests']):
                problems.append(x['id'] + ': the given package already passes')
    with tempfile.TemporaryDirectory() as tmp:
        export(bank, tmp)
        text = '\n'.join(p.read_text() for p in Path(tmp).rglob('*') if p.is_file())
        for x in bank['items']:
            if x['kind'] == 'answer':
                if len(x['answer']) > 6 and x['answer'] in text:
                    problems.append(x['id'] + ': the answer appears in the workspace')
            elif any(json.dumps(t['expected']) in text for t in x['tests'] if len(json.dumps(t['expected'])) > 12):
                problems.append(x['id'] + ': a hidden expected value appears in the workspace')
        blank = score(bank, tmp)
        if blank['correct']:
            problems.append('an untouched workspace scored above zero')
    return {'ok': not problems, 'problems': problems, 'items': len(bank['items'])}


# ---------------------------------------------------------------- Opus calibration (run by Main through subagents)

CALIBRATION_PROMPT = """You are solving a timed problem set. Work only inside {workspace}: read README.md there and
follow it. Do not read, list or search any other directory, and do not use the network. Solve every problem as well
as you can. The hard limit is {minutes} minutes: at the limit the files are taken as they are and you are stopped, so
write each answer or solution file as soon as that problem is done.
When you are done, reply with the single word DONE."""


def calibration_prepare(bank, out, runs, minutes):
    """Per independent Opus run, one job per family (a fresh answer-free workspace with that family's items and the
    exact prompt): a whole bank in one agent context would need compaction."""
    out = Path(out)
    jobs = []
    for k in range(1, runs + 1):
        for family in FAMILIES:
            numbers = {x['number'] for x in bank['items'] if x['family'] == family}
            if not numbers:
                continue
            here = out / f'run-{k}' / family
            workspace = export(bank, here / 'workspace', numbers).resolve()
            prompt = CALIBRATION_PROMPT.format(workspace=workspace, minutes=minutes)
            (here / 'prompt.txt').write_text(prompt)
            jobs.append({'run': k, 'part': family, 'folder': str(here.relative_to(out)), 'workspace': str(workspace),
                         'items': len(numbers), 'prompt_sha256': sha(prompt.encode())})
    manifest = {'bank_sha256': sha(json.dumps(bank, sort_keys=True).encode()), 'runs': runs, 'jobs': jobs,
                'minutes': minutes,
                'timing': 'For every job Main writes <folder>/start-epoch before it starts and <folder>/timing.json '
                          'as {"seconds": <wall seconds of the job>}; at the hard limit it copies the workspace to '
                          '<folder>/deadline-snapshot, which is then scored instead of the workspace'}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=1) + '\n')
    return manifest


def write_intervals(bank, workspace, started):
    """Approximate per-item time: gap between consecutive result writes (first gap from the start); items with no
    written result are absent.  A solver may work on several items at once, so this is only a cost signal."""
    stamps = sorted((t, x['id']) for x in bank['items'] for t in [written_at(x, workspace)] if t is not None)
    previous, result = started, {}
    for stamp, item_id in stamps:
        result[item_id] = max(0.0, stamp - previous)
        previous = stamp
    return result


def calibration_score(bank, out):
    """Per item: Opus passes out of the runs; per run: score (all its jobs together) and time.  Items with zero
    passes must be replaced."""
    out = Path(out)
    manifest = json.loads((out / 'manifest.json').read_text())
    passed, seconds = {x['id']: [] for x in bank['items']}, {x['id']: [] for x in bank['items']}
    rows, timing, scored = {}, {}, {}
    for job in manifest['jobs']:
        here = out / job['folder']
        snapshot = here / 'deadline-snapshot'
        workspace = snapshot if snapshot.is_dir() else Path(job['workspace'])  # the hard limit: files at the deadline
        part = {**bank, 'items': [x for x in bank['items'] if x['family'] == job['part']]}
        result = score(part, workspace)
        rows.setdefault(job['run'], []).extend(result['rows'])
        spent = here / 'timing.json'
        timing.setdefault(job['run'], []).append(json.loads(spent.read_text())['seconds'] if spent.exists() else None)
        scored.setdefault(job['run'], {})[job['part']] = 'deadline-snapshot' if snapshot.is_dir() else 'workspace'
        for r in result['rows']:
            if r['correct']:
                passed[r['id']].append(job['run'])
        if (here / 'start-epoch').exists():
            for item_id, gap in write_intervals(part, workspace, float((here / 'start-epoch').read_text())).items():
                seconds[item_id].append(gap)
    runs = []
    for k in sorted(rows):
        result = weighted(rows[k])
        runs.append({'run': k, 'score': result['score'], 'by_tier': result['by_tier'],
                     'by_family': result['by_family'],
                     'seconds': None if None in timing[k] else sum(timing[k]), 'scored': scored[k]})
    passes = {k: len(v) for k, v in passed.items()}
    n = len(runs)
    items = [{'id': x['id'], 'number': x['number'], 'tier': x['tier'], 'family': x['family'], 'passes': passes[x['id']],
              'passed_runs': passed[x['id']], 'runs': n,
              'opus_seconds': sorted(seconds[x['id']])[len(seconds[x['id']]) // 2] if seconds[x['id']] else None}
             for x in bank['items']]
    return {'runs': runs, 'opus_mean_score': sum(r['score'] for r in runs) / n if n else None,
            'opus_full_marks_runs': sum(r['score'] == 1 for r in runs),
            'replace': [i['id'] for i in items if i['passes'] == 0],
            'pass_rate_by_tier': {t: sum(i['passes'] for i in items if i['tier'] == t)
                                  / (n * sum(i['tier'] == t for i in items)) for t in TIERS if n},
            'items': items}


# ---------------------------------------------------------------- fixed formal set (after Opus calibration and Qwen pilot)

def choose(bank, calibration, pilot, count, low=0.3, high=0.7):
    """Proposal for the fixed formal set (every instance runs the same items; nothing is drawn at random).

    Eligible: Opus solved the item at least once, and the Qwen pilot ran it in a group without compaction.  Each
    family gets an equal share of `count`; within a family the items Qwen got right and wrong are mixed so the whole
    set's pilot accuracy lands at the middle of [low, high], shortest approximate pilot time first.  The instance
    time is estimated as the sum of the chosen items' approximate times (an item of a timed-out group makes it a
    lower bound), and is reported for the user to weigh against the per-instance limit.  Proposed points = the
    item's tier (to be confirmed).  Opus must not get full marks on the subset in any calibration run.
    """
    rows = {r['id']: r for r in pilot['items']}
    affected = sorted(i for g in pilot['groups'] if g['valid'] and g['compactions']
                      for x in bank['items'] if x['number'] in g['items'] for i in [x['id']])
    if affected:
        return {'ok': False, 'problems': [f'items in a compacted pilot group must be rerun: {affected}']}
    opus = {i['id']: i for i in calibration['items']}
    families = sorted({x['family'] for x in bank['items']})
    eligible = {f: sorted((x['id'] for x in bank['items'] if x['family'] == f and x['id'] in rows
                           and opus[x['id']]['passes'] > 0), key=lambda i: (rows[i]['approx_seconds'], i))
                for f in families}
    right_target = round(count * (low + high) / 2)
    chosen, problems = [], []
    for n, f in enumerate(families):
        share = count // len(families) + (n < count % len(families))
        want_right = round(right_target * share / count)
        right = [i for i in eligible[f] if rows[i]['correct']]
        wrong = [i for i in eligible[f] if not rows[i]['correct']]
        take_right = min(len(right), max(want_right, share - len(wrong)))
        picked = right[:take_right] + wrong[:share - take_right]
        if len(picked) < share:
            problems.append(f'{f}: only {len(picked)} eligible items for a share of {share}')
        chosen += picked
    accuracy = sum(rows[i]['correct'] for i in chosen) / len(chosen) if chosen else None
    if accuracy is not None and not low <= accuracy <= high:
        problems.append(f'pilot accuracy {accuracy:.2f} outside [{low}, {high}]')
    points = {i: bank_tier(bank, i) for i in chosen}
    total = sum(points.values())
    run_scores = {r['run']: sum(points[i] for i in chosen if r['run'] in opus[i]['passed_runs']) / total
                  for r in calibration['runs']} if total else {}
    problems += [f'Opus run {r} gets full marks on the subset' for r, v in run_scores.items() if v == 1]
    seconds = sorted(rows[i]['approx_seconds'] for i in chosen)
    valid = [g for g in pilot['groups'] if g['valid']]
    return {'ok': not problems, 'problems': problems, 'count': len(chosen), 'ids': chosen, 'points': points,
            'pilot_accuracy': accuracy, 'band': [low, high],
            'by_family': {f: sum(bank_family(bank, i) == f for i in chosen) for f in families},
            'by_tier': {t: sum(bank_tier(bank, i) == t for i in chosen) for t in sorted({bank_tier(bank, i) for i in chosen})},
            'expected_instance_seconds': round(sum(seconds), 1),
            'expected_is_lower_bound': any(rows[i]['group_timed_out'] for i in chosen),
            'item_seconds': {'median': seconds[len(seconds) // 2], 'max': seconds[-1]} if seconds else None,
            'max_group_context': max((g['context_after'] for g in valid), default=None),
            'opus_subset_scores': run_scores,
            'excluded_opus_zero': [x['id'] for x in bank['items'] if opus[x['id']]['passes'] == 0]}


def bank_tier(bank, item_id):
    return next(x['tier'] for x in bank['items'] if x['id'] == item_id)


def bank_family(bank, item_id):
    return next(x['family'] for x in bank['items'] if x['id'] == item_id)


def freeze(bank, proposal):
    """Fixed formal set from an approved proposal: the chosen items in group order, points attached."""
    chosen = {**bank, 'items': [dict(x, points=proposal['points'][x['id']]) for x in bank['items']
                                if x['id'] in proposal['points']]}
    return {**select(chosen, grouped(chosen)),
            'design': {k: proposal[k] for k in ('count', 'pilot_accuracy', 'expected_instance_seconds')}}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    b = sub.add_parser('build')
    b.add_argument('--seed', type=int, required=True)
    b.add_argument('--per-cell', type=int, default=5)
    b.add_argument('--out', type=Path, required=True)
    s = sub.add_parser('select')
    s.add_argument('--bank', type=Path, required=True)
    s.add_argument('--ids', type=Path, help='JSON list of item ids in set order (default: all, group order)')
    s.add_argument('--out', type=Path, required=True)
    e = sub.add_parser('export')
    e.add_argument('--bank', type=Path, required=True)
    e.add_argument('--out', type=Path, required=True)
    c = sub.add_parser('score')
    c.add_argument('--bank', type=Path, required=True)
    c.add_argument('--workspace', type=Path, required=True)
    k = sub.add_parser('check')
    k.add_argument('--bank', type=Path, required=True)
    cp = sub.add_parser('calibrate-prepare')
    cp.add_argument('--bank', type=Path, required=True)
    cp.add_argument('--out', type=Path, required=True)
    cp.add_argument('--runs', type=int, default=2)
    cp.add_argument('--minutes', type=int, default=45, help='per job (one family)')
    cs = sub.add_parser('calibrate-score')
    cs.add_argument('--bank', type=Path, required=True)
    cs.add_argument('--out', type=Path, required=True)
    d = sub.add_parser('choose', help='propose the fixed formal set from Opus calibration and the Qwen pilot')
    d.add_argument('--bank', type=Path, required=True)
    d.add_argument('--calibration', type=Path, required=True)
    d.add_argument('--pilot', type=Path, required=True, help="the pilot instance's result.json")
    d.add_argument('--count', type=int, default=20)
    d.add_argument('--low', type=float, default=0.3)
    d.add_argument('--high', type=float, default=0.7)
    d.add_argument('--out', type=Path, required=True)
    f = sub.add_parser('freeze', help='fixed formal set from an approved choose proposal')
    f.add_argument('--bank', type=Path, required=True)
    f.add_argument('--design', type=Path, required=True)
    f.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'choose':
        result = choose(json.loads(args.bank.read_text()), json.loads(args.calibration.read_text()),
                        json.loads(args.pilot.read_text()), args.count, args.low, args.high)
        args.out.write_text(json.dumps(result, indent=1) + '\n')
        print(json.dumps({k: v for k, v in result.items() if k not in ('ids', 'points')}))
        return
    if args.command == 'freeze':
        result = freeze(json.loads(args.bank.read_text()), json.loads(args.design.read_text()))
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n')
        return
    if args.command == 'calibrate-prepare':
        print(json.dumps(calibration_prepare(json.loads(args.bank.read_text()), args.out, args.runs, args.minutes)))
        return
    if args.command == 'calibrate-score':
        result = calibration_score(json.loads(args.bank.read_text()), args.out)
        (args.out / 'calibration.json').write_text(json.dumps(result, indent=1) + '\n')
        print(json.dumps({k: v for k, v in result.items() if k != 'items'}))
        return
    if args.command == 'build':
        args.out.write_text(json.dumps(build(args.seed, args.per_cell), ensure_ascii=False, indent=1) + '\n')
    elif args.command == 'select':
        bank = json.loads(args.bank.read_text())
        ids = json.loads(args.ids.read_text()) if args.ids else grouped(bank)
        args.out.write_text(json.dumps(select(bank, ids), ensure_ascii=False, indent=1) + '\n')
    elif args.command == 'export':
        export(json.loads(args.bank.read_text()), args.out)
    elif args.command == 'score':
        result = score(json.loads(args.bank.read_text()), args.workspace)
        print(json.dumps({k: v for k, v in result.items() if k != 'rows'}))
    else:
        print(json.dumps(self_check(json.loads(args.bank.read_text()))))


if __name__ == '__main__':
    main()
