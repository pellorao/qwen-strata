"""Blind adjudication pools of the multi-model benchmark (plan §6.2), in the format of the frozen briefs
(benchmarks/reviewer-suite-v1/<scenario>-brief.md), and the way back to each instance's decision store.

    build   real candidates (bench_score --enumerate, candidates.json of each instance) + controls -> pools of at most
            --max items (default 150), each in its own adjudication directory <adj>/<pool>/pool-<pool>.json (that
            directory is the brief's <ADJ>, so an adjudicator sees only its own pool); the hidden key goes to --keys,
            never under --adj. Items are grouped by expectation (E##, finding candidates one group each, F##), sources hidden.
            Controls in every pool: the anchors of the scenario registry (association decisions already made in a
            blind pool of the same scenario version, or confirmed by Main with an executable check) and all of its
            synthetic items; every pool holds at least one not-matched control. Finding-kind controls are always synthetic (user 2026-10-20); synthetic findings are
            written in each report family's own style (OpenAI "- Title sentence. ...", Anthropic "- `loc` — ...",
            Strata "1. `loc` - ..."), since the layout of a finding shows its family anyway (accepted, user 2026-10-20).
    split   <ADJ>/decisions-<name>.json + key -> control agreement by report family (anchors, synthetic), the pool
            verdict (anchors >= 90 % and every synthetic item right, else the pool is adjudicated again: nothing is
            written), the decisions written into <score root>/<record id>/decisions.json keyed by stable candidate id
            with the fingerprint of the item the adjudicator saw (earlier values kept in its history; a decision is
            reused only for a candidate with the same fingerprint), and Main's review lists: every `supported` decision, and the disputed
            `unsupported` ones (named among the adjudicator's hardest, hedged reasons, or evidence shared with an item
            decided otherwise).
    prompt  the adjudication prompt of one pool: the frozen brief (benchmarks/reviewer-suite-v1/<scenario>-brief.md)
            with only <ADJ> and <名> replaced, then the caller's fairness note (user 2026-10-20) as a paragraph after
            the brief body, not an edit of the frozen text (plan §14.1). It checks that <ADJ> holds the pool the key
            was written for, the view the brief names, its own decisions and nothing else (no other pool or key), writes
            <keys>/prompt-<pool>.md and records the brief and prompt sha256 in the key.
    override  Main's decision after review, into the store (history kept).
    anchor-add  register an association decision as a new anchor (Main's executable check, or a blind decision of a
            same-version pool); kind and allowedDecisions are filled in.

    python3 -m tools.reviewer.blind_pool build --scenario code-spec-v5 --name cs1 --adj ADJ --keys KEYS \\
        --candidates .tmp/bench-score/*/code-spec-v5/*/candidates.json
    python3 -m tools.reviewer.blind_pool prompt --key KEYS/key-cs1.json [--adj-as adj]   # after staging ADJ/cs1/view and change.diff
    python3 -m tools.reviewer.blind_pool split --key KEYS/key-cs1.json --decisions ADJ/cs1/decisions-cs1.json \\
        [--hard p001 p017] [--root .tmp/bench-score]
    python3 -m tools.reviewer.blind_pool override --record openai/code-spec-v5/sol-high-a1 --stable-id ID \\
        --decision supported --reason '...' [--root .tmp/bench-score]
"""
import argparse
import hashlib
import json
import random
import re
from pathlib import Path

from tools.reviewer import bench_records

ROOT = bench_records.ROOT
REGISTRY = ROOT / 'benchmarks/multi-model-v1/anchors'
DEFAULT_ROOT = ROOT / '.tmp/bench-score'
MAX_ITEMS = 150
ANCHORS_PER_POOL = 12  # plan §6.2: 10-15 anchors per pool
DECISION = re.compile(r'^(matched|not-matched|unsupported|supported|problem-[1-9][0-9]*|false-positive:clean-[1-9][0-9]*)$')
ANCHOR_THRESHOLD = 0.9
ADJUDICATOR = 'blind Opus high'
# Field order of the frozen briefs; `scenario` only for Spec Readiness, `requirementSource` only when present (Commit
# Audit), problemOptions and cleanTargets only for finding candidates.
FIELDS = ('kind', 'scenario', 'check', 'allowedDecisions', 'expectation', 'finding', 'result', 'evidence',
          'requirementSource', 'problemOptions', 'cleanTargets')
SUB_SCENARIOS = ('runtime-migration', 'artifact-promotion')
HEDGES = re.compile(r'可能|似乎|不确定|难以|无法确定|或许|勉强|边界|倾向|存疑|不太|未必|大概')
FAMILIES = ('openai', 'anthropic', 'strata')
BRIEFS = ROOT / 'benchmarks/reviewer-suite-v1'
# Caller-appended paragraph after the frozen brief body (user 2026-10-20; plan §14.1): report layout can show its family.
FAIRNESS_NOTE = ('调用方附加说明（不属于冻结 brief，用户 2026-10-20 决定加入）：候选的写法可能让你看得出它来自哪类模型或哪次运行。'
                 '不要据此推断来源，也不要因来源调整判断；请只按上文口径和 view 中的证据，对每个候选公平判定。')
# What the brief lets an adjudicator read in <ADJ> besides its pool, per scenario family.
VIEWS = {'spec-readiness': ('view-rm', 'view-ap'), 'commit-audit': ('view',), 'code-': ('view', 'change.diff')}


def load(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=1) + '\n')


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def record_family(record_id):
    """Report style family of a record id arm/scenario/<model>-<effort>-aN."""
    match = bench_records.DIR_NAME.match(record_id.rsplit('/', 1)[1])
    return bench_records.MODELS[match.group('model')][2]


def pool_item(candidate, scenario):
    """The adjudicator's view of a candidate: the brief's fields, nothing that names its run."""
    item = {}
    for field in FIELDS:
        if field == 'scenario':
            if scenario.startswith('spec-readiness'):
                item['scenario'] = candidate.get('scenario') or bench_records.sub_scenario(candidate['instanceId'])
                if item['scenario'] not in SUB_SCENARIOS:
                    raise ValueError(f"{candidate.get('candidateId')}: no Spec Readiness sub-scenario")
            continue
        if field == 'requirementSource':
            if candidate.get('requirementSource') is not None:
                item['requirementSource'] = candidate['requirementSource']
            continue
        if field in ('problemOptions', 'cleanTargets') and candidate['kind'] != 'finding':
            continue
        item[field] = candidate.get(field)
    if candidate['kind'] == 'finding':
        item['expectation'] = None
    return item


def item_fingerprint(item):
    """sha256 of a pool item without its pool id and group."""
    text = json.dumps({k: v for k, v in item.items() if k not in ('id', 'group')}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()


def fingerprint(candidate, scenario):
    """Fingerprint of the adjudicator's view of a candidate: a stored decision holds only for the same content."""
    return item_fingerprint(pool_item(candidate, scenario))


def registry_paths(scenario, registry=REGISTRY):
    return Path(registry) / f'{scenario}.json'


def load_registry(scenario, registry=REGISTRY):
    path = registry_paths(scenario, registry)
    if not path.is_file():
        return {'scenario': scenario, 'anchors': [], 'synthetic': []}, None
    value = load(path)
    if value.get('scenario') != scenario:
        raise ValueError(f'{path}: registry of another scenario')
    return value, sha256_file(path)


def check_control(control, kind_allowed):
    item = control['item']
    if item['kind'] not in kind_allowed:
        raise ValueError(f"{control['id']}: control kind {item['kind']} not allowed here")
    if control['expected'] not in item['allowedDecisions']:
        raise ValueError(f"{control['id']}: expected decision not among allowedDecisions")
    if control.get('family') not in FAMILIES:
        raise ValueError(f"{control['id']}: control without a report family")


def pick_anchors(anchors, count, rnd):
    """At most count anchors, taken in turn from each report family (so every family is checked)."""
    by_family = {}
    for anchor in sorted(anchors, key=lambda a: a['id']):
        by_family.setdefault(anchor['family'], []).append(anchor)
    for items in by_family.values():
        rnd.shuffle(items)
    picked = []
    while len(picked) < count and any(by_family.values()):
        for family in sorted(by_family):
            if by_family[family] and len(picked) < count:
                picked.append(by_family[family].pop())
    left = [a for items in by_family.values() for a in items if a['expected'] == 'not-matched']
    if picked and left and not any(a['expected'] == 'not-matched' for a in picked):
        # A pool needs a not-matched control; swap one in for the last pick of the same family when possible.
        swap = next((a for a in left if a['family'] == picked[-1]['family']), left[0])
        picked[-1] = swap
    return picked


def controls(registry, anchor_count=None, rnd=None):
    out = []
    anchors = registry.get('anchors', [])
    if anchor_count is not None and len(anchors) > anchor_count:
        anchors = pick_anchors(anchors, anchor_count, rnd)
    for anchor in anchors:
        check_control(anchor, ('association',))
        out.append((anchor['item'], {'source': 'anchor', 'control': anchor['id'], 'expected': anchor['expected'],
                                     'family': anchor['family'], 'model': anchor.get('model'),
                                     'origin': anchor.get('origin')}))
    for synthetic in registry.get('synthetic', []):
        check_control(synthetic, ('association', 'finding'))
        out.append((synthetic['item'], {'source': 'synthetic', 'control': synthetic['id'], 'type': synthetic['type'],
                                        'expected': synthetic['expected'], 'family': synthetic['family'],
                                        'model': synthetic.get('model')}))
    return out


def chunks(groups, limit):
    """Pack whole groups (lists of items) into pools of at most limit items, largest groups first."""
    pools = []
    for group in sorted(groups, key=len, reverse=True):
        if len(group) > limit:
            raise ValueError(f'one expectation group has {len(group)} items, more than a pool can take')
        target = next((p for p in pools if len(p) + len(group) <= limit), None)
        if target is None:
            pools.append([])
            target = pools[-1]
        target.extend(group)
    return pools


def stored(root, record_id):
    """stable id -> fingerprint of the decisions an instance's store holds."""
    path = store_path(root, record_id)
    if not path.is_file():
        return {}
    return {sid: d.get('fingerprint') for sid, d in load(path)['decisions'].items()}


def build(scenario, name, adj, keys, candidate_files, registry=REGISTRY, limit=MAX_ITEMS, seed=20261020,
          anchor_count=ANCHORS_PER_POOL, root=None):
    if Path(keys).resolve().is_relative_to(Path(adj).resolve()):
        raise ValueError('the key directory must not be under the adjudication directory')
    reg, reg_sha = load_registry(scenario, registry)
    rnd = random.Random(seed)
    control_items = controls(reg, anchor_count, rnd)
    if not any(meta['expected'] == 'not-matched' for _, meta in control_items):
        raise ValueError(f'{scenario}: no not-matched control (anchor or synthetic) for the pools')
    anchor_origins = {(c['origin']['record'], c['origin']['stable_id']) for c in reg.get('anchors', [])
                      if (c.get('origin') or {}).get('record')}
    real, skipped, stores = [], 0, {}
    for path in candidate_files:
        for candidate in load(path):
            if candidate['record'].split('/')[1] != scenario:
                raise ValueError(f"{path}: candidate of {candidate['record']}, not {scenario}")
            item = pool_item(candidate, scenario)
            mark = item_fingerprint(item)
            if root is not None:
                if candidate['record'] not in stores:
                    stores[candidate['record']] = stored(root, candidate['record'])
                if stores[candidate['record']].get(candidate['stable_id']) == mark:
                    skipped += 1  # already adjudicated with the same content: only what changed is adjudicated again
                    continue
            real.append((item,
                         {'source': 'instance', 'record': candidate['record'], 'stable_id': candidate['stable_id'],
                          'candidateId': candidate['candidateId'], 'kind': candidate['kind'],
                          'family': record_family(candidate['record']), 'fingerprint': mark}))
    clash = [m for _, m in real if (m['record'], m['stable_id']) in anchor_origins]
    if clash:
        # An anchor taken from an instance being scored would show the adjudicator the same item twice.
        raise ValueError(f'{len(clash)} candidates are registered anchors of the same instance; drop those anchors first')
    groups = {}
    for item, meta in real:
        groups.setdefault(item['expectation'] if item['kind'] == 'association' else ('finding', meta['record'],
                                                                                     meta['stable_id']), []).append((item, meta))
    room = limit - len(control_items)
    if room <= 0:
        raise ValueError('controls alone fill a pool')
    packed = chunks(list(groups.values()), room) if real else [[]]
    written = []
    for n, items in enumerate(packed, 1):
        pool_name = name if len(packed) == 1 else f'{name}-{n}'
        items = items + control_items
        rnd.shuffle(items)
        expectations = sorted({i['expectation'] for i, _ in items if i['expectation'] is not None})
        rnd.shuffle(expectations)
        gid = {e: f'E{k:02d}' for k, e in enumerate(expectations, 1)}
        finding_numbers = iter(range(1, 10000))
        labels = [gid[i['expectation']] if i['expectation'] is not None else f'F{next(finding_numbers):02d}'
                  for i, _ in items]
        order = sorted(range(len(items)), key=lambda j: labels[j])
        pool, key = [], {}
        for k, j in enumerate(order, 1):
            pid = f'{pool_name}-{k:03d}'
            item, meta = items[j]
            pool.append({'id': pid, 'group': labels[j], **item})
            key[pid] = meta
        pool_path = Path(adj) / pool_name / f'pool-{pool_name}.json'
        save(pool_path, pool)
        key_path = Path(keys) / f'key-{pool_name}.json'
        save(key_path, {'pool': pool_name, 'scenario': scenario, 'pool_path': str(pool_path),
                        'pool_sha256': sha256_file(pool_path), 'registry_sha256': reg_sha, 'items': key})
        written.append({'pool': pool_name, 'adj': str(pool_path.parent), 'items': len(pool),
                        'real': len(pool) - len(control_items), 'controls': len(control_items),
                        'already_decided_skipped': skipped, 'key': str(key_path)})
    return written


# ---- prompt -------------------------------------------------------------------------------------------------------

def brief_path(scenario):
    return BRIEFS / f'{scenario}-brief.md'


def views(scenario):
    return next(v for prefix, v in VIEWS.items() if scenario.startswith(prefix))


def check_adj(key):
    """<ADJ> of a pool holds exactly its pool, the view the brief names and, after the run, its decisions."""
    adj, name = Path(key['pool_path']).parent, key['pool']
    if sha256_file(key['pool_path']) != key['pool_sha256']:
        raise ValueError('pool file differs from the one the key was written for')
    allowed = {f'pool-{name}.json', f'decisions-{name}.json', *views(key['scenario'])}
    extra = sorted(p.name for p in adj.iterdir() if p.name not in allowed)
    if extra:
        raise ValueError(f'{adj} holds more than the current pool and its view: {extra}')
    missing = [v for v in views(key['scenario']) if not (adj / v).exists()]
    if missing:
        raise ValueError(f'{adj}: stage {missing} (the reviewed view the brief names) first')
    return adj


def prompt(key_path, adj_as=None):
    """adj_as: the path the adjudicator's run sees <ADJ> at (e.g. `adj` when the runner copies <ADJ> into its working
    directory as `adj`); default the absolute path of <ADJ>."""
    key = load(key_path)
    adj = check_adj(key)
    brief = brief_path(key['scenario'])
    text = brief.read_text()
    for placeholder in ('<ADJ>', '<名>'):
        if placeholder not in text:
            raise ValueError(f'{brief}: no {placeholder} to replace')
    body = text.replace('<ADJ>', adj_as or str(adj.resolve())).replace('<名>', key['pool']).rstrip('\n')
    out = Path(key_path).with_name(f"prompt-{key['pool']}.md")
    out.write_text(f'{body}\n\n{FAIRNESS_NOTE}\n')
    key.update({'brief_path': str(brief), 'brief_sha256': sha256_file(brief), 'prompt_path': str(out),
                'prompt_sha256': sha256_file(out), 'adj_as': adj_as or str(adj.resolve())})
    save(key_path, key)
    return {k: key[k] for k in ('pool', 'brief_path', 'brief_sha256', 'prompt_path', 'prompt_sha256')} | {'adj': str(adj)}


# ---- split --------------------------------------------------------------------------------------------------------

def evidence_points(item):
    points = set()
    for e in item.get('evidence') or []:
        if not isinstance(e, dict) or 'filePath' not in e:
            continue
        if 'line' in e:
            points.add((e['filePath'], e['line']))
        elif 'lineStart' in e:
            points.update((e['filePath'], n) for n in range(e['lineStart'], (e.get('lineEnd') or e['lineStart']) + 1))
        elif isinstance(e.get('lines'), list):
            for part in e['lines']:
                if isinstance(part, int):
                    points.add((e['filePath'], part))
                elif isinstance(part, list) and len(part) == 2:
                    points.update((e['filePath'], n) for n in range(part[0], part[1] + 1))
    return points


def agreement(rows, field='family'):
    out = {}
    for row in rows:
        entry = out.setdefault(str(row.get(field)), {'n': 0, 'agree': 0, 'misses': []})
        entry['n'] += 1
        if row['decision'] == row['expected']:
            entry['agree'] += 1
        else:
            entry['misses'].append({k: row[k] for k in ('id', 'control', 'expected', 'decision')})
    for entry in out.values():
        entry['rate'] = entry['agree'] / entry['n']
    return out


def split(key_path, decisions_path, root=DEFAULT_ROOT, hard=(), accept_failed=False):
    key = load(key_path)
    pool = {item['id']: item for item in load(key['pool_path'])}
    if sha256_file(key['pool_path']) != key['pool_sha256']:
        raise ValueError('pool file differs from the one the key was written for')
    reply = load(decisions_path)
    if reply.get('adjudicator') != ADJUDICATOR:
        raise ValueError(f"adjudicator is {reply.get('adjudicator')!r}, not {ADJUDICATOR!r}")
    decisions = {}
    for d in reply['decisions']:
        if d['id'] in decisions:
            raise ValueError(f"{d['id']} decided twice")
        decisions[d['id']] = d
    if set(decisions) != set(key['items']) or set(pool) != set(key['items']):
        raise ValueError('decision ids differ from the pool')
    for pid, d in decisions.items():
        if d['decision'] not in pool[pid]['allowedDecisions'] or not str(d.get('reason', '')).strip():
            raise ValueError(f'{pid}: decision {d["decision"]!r} not allowed or without a reason')
    rows = [{'id': pid, **meta, 'decision': decisions[pid]['decision']} for pid, meta in key['items'].items()]
    anchors = [r for r in rows if r['source'] == 'anchor']
    synthetic = [r for r in rows if r['source'] == 'synthetic']
    anchor_rate = sum(r['decision'] == r['expected'] for r in anchors) / len(anchors) if anchors else None
    synthetic_ok = all(r['decision'] == r['expected'] for r in synthetic)
    passed = anchor_rate is not None and anchor_rate >= ANCHOR_THRESHOLD and synthetic_ok and bool(synthetic)
    verdict = {'pool': key['pool'], 'passed': passed, 'anchor_rate': anchor_rate, 'anchors': len(anchors),
               'synthetic': len(synthetic), 'synthetic_all_right': synthetic_ok,
               'anchor_agreement_by_family': agreement(anchors), 'anchor_agreement_by_model': agreement(anchors, 'model'),
               'synthetic_by_family': agreement(synthetic),
               'decision_counts': {}}
    for d in decisions.values():
        verdict['decision_counts'][d['decision']] = verdict['decision_counts'].get(d['decision'], 0) + 1
    real = [r for r in rows if r['source'] == 'instance']
    review = review_lists(real, pool, decisions, set(hard))
    verdict['review'] = {'supported': len(review['supported']), 'disputed_unsupported': len(review['disputed_unsupported'])}
    if passed or accept_failed:
        written = write_stores(real, decisions, key['pool'], root)
        verdict['written'] = written
    else:
        verdict['written'] = 0
        verdict['note'] = 'controls failed: adjudicate the whole pool again (plan §6.2); nothing written'
    out = Path(key_path).with_name(f"split-{key['pool']}.json")
    save(out, {'verdict': verdict, 'review': review})
    return verdict, review, out


def review_lists(real, pool, decisions, hard):
    supported, disputed = [], []
    for r in real:
        d = decisions[r['id']]
        entry = {'id': r['id'], 'record': r['record'], 'stable_id': r['stable_id'], 'decision': d['decision'],
                 'reason': d['reason'], 'finding': pool[r['id']]['finding']}
        if d['decision'] == 'supported':
            supported.append(entry)
        if d['decision'] != 'unsupported':
            continue
        why = []
        if r['id'] in hard:
            why.append('among the hardest the adjudicator named')
        if HEDGES.search(d['reason']):
            why.append('hedged reason')
        points = evidence_points(pool[r['id']])
        others = [o['id'] for o in real if o['id'] != r['id'] and decisions[o['id']]['decision'] != 'unsupported'
                  and points & evidence_points(pool[o['id']])]
        if others:
            why.append(f'evidence shared with items decided otherwise: {others[:8]}')
        if why:
            disputed.append({**entry, 'why': why})
    return {'supported': supported, 'disputed_unsupported': disputed}


def store_path(root, record_id):
    return Path(root) / record_id / 'decisions.json'


def write_stores(real, decisions, pool_name, root):
    by_record = {}
    for r in real:
        by_record.setdefault(r['record'], []).append(r)
    for record_id, rows in by_record.items():
        path = store_path(root, record_id)
        store = load(path) if path.is_file() else {'decisions': {}, 'history': []}
        for r in rows:
            d = decisions[r['id']]
            if not r.get('fingerprint'):
                raise ValueError(f"{r['id']}: key item without a fingerprint")
            new = {'decision': d['decision'], 'reason': d['reason'], 'source': f"pool {pool_name}:{r['id']}",
                   'kind': r['kind'], 'fingerprint': r['fingerprint']}
            old = store['decisions'].get(r['stable_id'])
            if old is not None and old != new:
                store['history'].append({'stable_id': r['stable_id'], 'replaced': old, 'by': new['source']})
            store['decisions'][r['stable_id']] = new
        save(path, store)
    return sum(len(rows) for rows in by_record.values())


def override(record_id, stable_id, decision, reason, by='Main review', root=DEFAULT_ROOT):
    path = store_path(root, record_id)
    store = load(path)
    old = store['decisions'].get(stable_id)
    if old is None:
        raise ValueError(f'{record_id}: {stable_id} has no adjudicated decision to override')
    if not reason.strip():
        raise ValueError('an override needs a reason')
    association = old.get('kind') == 'association'
    if not DECISION.match(decision) or association != (decision in ('matched', 'not-matched')):
        raise ValueError(f'{decision!r} is not a decision of a {old.get("kind")} candidate')
    new = {'decision': decision, 'reason': reason, 'source': f'override ({by})', 'kind': old.get('kind'),
           'fingerprint': old.get('fingerprint')}
    store['history'].append({'stable_id': stable_id, 'replaced': old, 'by': new['source']})
    store['decisions'][stable_id] = new
    save(path, store)
    return new


def anchor_add(scenario, item, expected, family, confirmed_by, origin=None, registry=REGISTRY, anchor_id=None):
    if item.get('kind', 'association') != 'association':
        raise ValueError('anchors are association decisions; finding-kind controls are synthetic (user 2026-10-20)')
    if expected not in ('matched', 'not-matched'):
        raise ValueError('an anchor decision is matched or not-matched')
    reg, _ = load_registry(scenario, registry)
    item = {'kind': 'association', 'allowedDecisions': ['matched', 'not-matched'],
            **{k: v for k, v in item.items() if k not in ('kind', 'allowedDecisions', 'problemOptions', 'cleanTargets')}}
    anchor_id = anchor_id or f"a{len(reg['anchors']) + 1:02d}"
    if any(a['id'] == anchor_id for a in reg['anchors']):
        raise ValueError(f'{anchor_id} already registered')
    anchor = {'id': anchor_id, 'family': family, 'expected': expected, 'confirmed_by': confirmed_by,
              'origin': origin, 'item': {k: item[k] for k in FIELDS if k in item}}
    check_control(anchor, ('association',))
    reg['anchors'].append(anchor)
    save(registry_paths(scenario, registry), reg)
    return anchor


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    b = sub.add_parser('build')
    b.add_argument('--scenario', required=True, choices=bench_records.SCENARIOS)
    b.add_argument('--name', required=True)
    b.add_argument('--adj', type=Path, required=True, help='parent of the per-pool adjudication directories <ADJ>')
    b.add_argument('--keys', type=Path, required=True, help='hidden key directory (not under <ADJ>)')
    b.add_argument('--candidates', type=Path, nargs='+', required=True)
    b.add_argument('--registry', type=Path, default=REGISTRY)
    b.add_argument('--max', type=int, default=MAX_ITEMS)
    b.add_argument('--seed', type=int, default=20261020)
    b.add_argument('--anchors', type=int, default=ANCHORS_PER_POOL, help='anchors per pool (plan: 10-15)')
    b.add_argument('--root', type=Path, help='score root: skip candidates its decision stores already hold')
    p = sub.add_parser('prompt')
    p.add_argument('--key', type=Path, required=True)
    p.add_argument('--adj-as', help='path of <ADJ> as the adjudicator run sees it (default: its absolute path)')
    s = sub.add_parser('split')
    s.add_argument('--key', type=Path, required=True)
    s.add_argument('--decisions', type=Path, required=True)
    s.add_argument('--hard', nargs='*', default=[], help="pool ids the adjudicator named as hardest")
    s.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    s.add_argument('--accept-failed', action='store_true', help='write decisions although the controls failed')
    o = sub.add_parser('override')
    o.add_argument('--record', required=True)
    o.add_argument('--stable-id', required=True)
    o.add_argument('--decision', required=True)
    o.add_argument('--reason', required=True)
    o.add_argument('--by', default='Main review')
    o.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    a = sub.add_parser('anchor-add')
    a.add_argument('--scenario', required=True, choices=bench_records.SCENARIOS)
    a.add_argument('--item', type=Path, required=True, help='JSON of the association item (pool item or candidate)')
    a.add_argument('--expected', required=True, choices=('matched', 'not-matched'))
    a.add_argument('--family', required=True, choices=FAMILIES)
    a.add_argument('--confirmed-by', required=True, help="e.g. 'Main executable check: node -e ...'")
    a.add_argument('--registry', type=Path, default=REGISTRY)
    args = parser.parse_args()
    if args.command == 'build':
        print(json.dumps(build(args.scenario, args.name, args.adj, args.keys, args.candidates, args.registry, args.max,
                               args.seed, args.anchors, args.root), indent=1))
    elif args.command == 'prompt':
        print(json.dumps(prompt(args.key, args.adj_as), ensure_ascii=False))
    elif args.command == 'split':
        verdict, _, out = split(args.key, args.decisions, args.root, args.hard, args.accept_failed)
        print(json.dumps({**{k: verdict[k] for k in ('pool', 'passed', 'anchor_rate', 'synthetic_all_right', 'written',
                                                       'review')}, 'details': str(out)}, ensure_ascii=False))
    elif args.command == 'override':
        print(json.dumps(override(args.record, args.stable_id, args.decision, args.reason, args.by, args.root),
                         ensure_ascii=False))
    else:
        print(json.dumps(anchor_add(args.scenario, load(args.item), args.expected, args.family, args.confirmed_by,
                                    registry=args.registry), ensure_ascii=False))


if __name__ == '__main__':
    main()
