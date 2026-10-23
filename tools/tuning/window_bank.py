"""Window workload v2 (benchmarks/window-load-v1/design.md): one long recall conversation with five checkpoints.

One Codex (or Claude Code) conversation: an opening with key facts (K, half marked as needed later), then record
batches of about 6K tokens (B records; U chains, a record whose field changes twice; some K updates), the model
replying only `ACK nn`.  Question turns sit at five checkpoints (cumulative context about 115K, 165K, 210K, 255K and
300K if nothing were compacted), 12 questions each (K 3, B 7, U 2).  Every fact is asked exactly once and never
appears again after it is asked.  Whether a question's source was still in the raw context when it was asked, and
how many compactions it went through, are derived per instance from the measured compactions (`classify`).

    python3 -m tools.tuning.window_bank build --seed S --out window.json [--count-tokens HOST]
    python3 -m tools.tuning.window_bank check --workload window.json
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import subprocess
import tempfile

# Tunables
CHECKPOINTS = (115000, 165000, 210000, 255000, 300000)  # estimated context if never compacted (design §2.1, U9)
BASE_TOKENS = 12000          # harness instructions, tool schemas and startup prompt (estimate; measured per run)
TURN_OVERHEAD_TOKENS = 300   # wrapper, reasoning and the ACK reply per batch turn (estimate)
ANSWER_TOKENS = 600          # a question turn's reply (estimate)
RECORDS_PER_BATCH = 155      # about 6K tokens per batch with the IQ3_XXS tokenizer
UPDATES_PER_BATCH = 6        # update lines per batch (chain updates first, the rest on filler records)
K_FACTS, K_MARKED, K_UPDATED = 16, 8, 5
K_UPDATE_AT = 140000         # the K updates come in the batch at this cumulative position (after a first compaction)
PER_CHECKPOINT = {'K': 3, 'B': 7, 'U': 2}
# B ages (tokens between the record's batch and the checkpoint): [low, high) and how many per checkpoint
B_AGES = ((0, 30000, 2), (30000, 60000, 2), (60000, 100000, 2), (100000, 10 ** 9, 1))
# U chains: (age band of the last update, gap between creation, first and second update in batches)
U_SHAPES = (((0, 30000), 4), ((40000, 90000), 3))
# K asked per checkpoint: (marked, updated) for each of the 15 asked facts; one unmarked fact is never asked
K_PLAN = (((True, False), (False, False), (True, False)),
          ((True, True), (False, True), (True, False)),
          ((True, True), (False, False), (False, False)),
          ((False, True), (True, False), (False, False)),
          ((True, True), (False, False), (True, False)))
CHARS_PER_TOKEN = 2.4        # fallback only; the frozen workload records exact tokenizer counts
FIELDS = ('owner', 'site', 'qty', 'status', 'tag')
STATUS = ('open', 'held', 'packed', 'shipped', 'returned', 'closed')
K_NAMES = ('release codename', 'escalation contact', 'budget ceiling', 'freeze window code', 'primary region',
           'rollback tag', 'vendor reference', 'audit ticket', 'storage quota', 'signing key id', 'retention days',
           'canary percentage', 'support alias', 'build channel', 'license seat count', 'incident bridge code')
MARK = '[later steps depend on this value: keep it]'
SCHEMA = 'window-workload-v2'

OPENING = ('This is a long-context recall test. Below are key facts for this project; some are marked as needed by '
           'later steps. After them I will send numbered batches of synthetic inventory records, some with updates to '
           'earlier records or to key facts. For each batch reply with exactly `ACK <batch number>` and nothing else. '
           'At a few checkpoints I will ask questions instead; answer them as instructed there. Do not run commands, '
           'do not read or write files and do not search: everything exists only in this conversation.\n\n'
           'Key facts:\n{facts}\n\nReply with exactly `ACK 00`.')
QUESTION_HEAD = ('Checkpoint {n} of {total}. Questions about the current state of the records and key facts, after '
                 'all updates sent so far. Answer from this conversation only; do not run commands or read files. Reply '
                 'with one line per question in the form `Q01: <value>`, writing the value exactly as it appears in '
                 'the conversation (write `unknown` if you cannot recall it). The batches continue afterwards.\n\n')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def syllables(rng, parts):
    return ''.join(rng.choice('bdfgklmnprstvz') + rng.choice('aeiou') for _ in range(parts))


def unique(rng, make, used):
    while True:
        value = make()
        if value not in used:
            used.add(value)
            return value


def record_line(r):
    return f'{r["id"]} | owner={r["owner"]} | site={r["site"]} | qty={r["qty"]} | status={r["status"]} | tag={r["tag"]}'


class Maker:
    """Unique identifiers and values (no value repeats anywhere, so a stale or foreign value is always wrong)."""

    def __init__(self, rng):
        self.rng, self.used = rng, set()

    def ident(self):
        r = self.rng
        return unique(r, lambda: f'{r.choice("BCDFGHJKLMNPRSTVWXZ")}{r.choice("BCDFGHJKLMNPRSTVWXZ")}-'
                                 f'{r.randint(1000, 9999)}', self.used)

    def value(self, field):
        r = self.rng
        if field == 'owner':
            return unique(r, lambda: syllables(r, 2).title() + ' ' + syllables(r, 3).title(), self.used)
        if field == 'site':
            return unique(r, lambda: f'{syllables(r, 1).upper()}{r.choice("XQJ")}-{r.randint(10, 99)}', self.used)
        if field == 'tag':
            return unique(r, lambda: syllables(r, 3), self.used)
        if field == 'qty':
            return r.randint(10, 999)
        return r.choice(STATUS)

    def record(self):
        return {'id': self.ident(), **{f: self.value(f) for f in FIELDS}}

    def changed(self, record, field):
        if field == 'qty':
            return unique(self.rng, lambda: self.rng.randint(10, 999), {record['qty']})
        if field == 'status':
            return self.rng.choice([s for s in STATUS if s != record['status']])
        return self.value(field)

    def k_value(self):
        r = self.rng
        return unique(r, lambda: f'{syllables(r, 2).upper()}-{r.randint(100, 9999)}', self.used)


def counter_or_estimate(counter):
    return counter or (lambda texts: [round(len(t) / CHARS_PER_TOKEN) for t in texts])


def build(seed, counter=None):
    """Frozen workload.  `counter(texts) -> token counts` gives exact tokenizer counts (positions are then exact)."""
    count = counter_or_estimate(counter)
    rng = random.Random(f'window-v2/{seed}')
    make = Maker(rng)
    # Batch size from a probe batch (records and update lines are near constant in length).
    probe = Maker(random.Random(f'window-v2/{seed}/probe'))
    sample = [record_line(probe.record()) for _ in range(RECORDS_PER_BATCH)]
    upd = [f'UPDATE {probe.ident()} tag={probe.value("tag")}' for _ in range(UPDATES_PER_BATCH)]
    per_batch = count(['Batch 01/45. New records:\n' + '\n'.join(sample) + '\nUpdates to earlier records (the new '
                       'value replaces the old one):\n' + '\n'.join(upd) + '\n\nReply with exactly `ACK 01`.'])[0]
    # K facts
    k_marked = [True] * K_MARKED + [False] * (K_FACTS - K_MARKED)
    keys = []
    for n in range(K_FACTS):
        keys.append({'id': f'K{n + 1:02d}', 'name': K_NAMES[n], 'value': make.k_value(), 'marked': k_marked[n]})
    rng.shuffle(keys)  # marked and unmarked interleaved in the opening
    for n, k in enumerate(keys):
        k['id'] = f'K{n + 1:02d}'
    facts = '\n'.join(f'{k["id"]} | {k["name"]} = {k["value"]}' + (f' {MARK}' if k['marked'] else '') for k in keys)
    opening = OPENING.format(facts=facts)
    opening_tokens = count([opening])[0]
    # Planned positions: batch b (1-based) ends at end[b]; a question turn adds its own tokens.
    q_estimate = 450
    positions, position, batches = {}, BASE_TOKENS + opening_tokens + TURN_OVERHEAD_TOKENS, 0
    checkpoint_after = []
    while len(checkpoint_after) < len(CHECKPOINTS):
        batches += 1
        position += per_batch + TURN_OVERHEAD_TOKENS
        positions[batches] = position
        if position >= CHECKPOINTS[len(checkpoint_after)] - per_batch / 2:
            checkpoint_after.append(batches)
            position += q_estimate + ANSWER_TOKENS
    start = {b: positions[b] - per_batch - TURN_OVERHEAD_TOKENS for b in positions}
    k_update_batch = next(b for b in positions if positions[b] >= K_UPDATE_AT)
    # Records per batch
    records, created, born, content = {}, {}, {}, {b: [] for b in positions}
    for b in positions:
        for _ in range(RECORDS_PER_BATCH):
            r = make.record()
            records[r['id']], created[r['id']] = dict(r), dict(r)
            born[r['id']] = b
            content[b].append(r['id'])
    taken = set()  # records asked, in a chain, or updated: never a B question
    updates = {b: [] for b in positions}  # (record, field, value)
    history = {}
    questions = []

    def age(b, cp):
        return positions[checkpoint_after[cp]] - start[b]

    for cp, after in enumerate(checkpoint_after):
        ask = []
        # U chains: created, then updated twice on one field, the last update in the age band
        for (low, high), gap in U_SHAPES:
            last = [b for b in range(1, after + 1) if low <= age(b, cp) - 0 < high and b > 2 * gap
                    and len(updates[b]) < UPDATES_PER_BATCH - 1]
            last_b = rng.choice(last)
            first_b, born_b = last_b - gap, last_b - 2 * gap
            pool = [i for i in content[born_b] if i not in taken]
            ident = rng.choice(pool)
            taken.add(ident)
            field = rng.choice(('qty', 'status', 'site', 'tag'))
            for b in (first_b, last_b):
                value = make.changed(records[ident], field)
                records[ident][field] = value
                updates[b].append((ident, field, value))
                history.setdefault(ident, []).append((b, field, value))
            ask.append({'type': 'U', 'record': ident, 'field': field, 'answer': str(records[ident][field]),
                        'stale_values': [str(created[ident][field]), str(history[ident][0][2])],
                        'source': f'batch {last_b:02d}', 'source_batch': last_b, 'born_batch': born_b,
                        'updated_in': [first_b, last_b]})
        # B static records in the age bands
        for low, high, n in B_AGES:
            band = [b for b in range(1, after + 1) if low <= age(b, cp) < high]
            if not band:  # the oldest band at the first checkpoint: take the oldest batches
                band = [1]
            for _ in range(n):
                b = rng.choice(band)
                ident = rng.choice([i for i in content[b] if i not in taken])
                taken.add(ident)
                field = rng.choice(FIELDS)
                ask.append({'type': 'B', 'record': ident, 'field': field, 'answer': str(records[ident][field]),
                            'source': f'batch {b:02d}', 'source_batch': b, 'born_batch': b, 'updated_in': []})
        questions.append(ask)
    # K questions: assign keys by (marked, updated); updates in k_update_batch, before any checkpoint asking them
    key_updates = []
    free = {True: [k for k in keys if k['marked']], False: [k for k in keys if not k['marked']]}
    for cp, plan in enumerate(K_PLAN):
        for marked, updated in plan:
            key = free[marked].pop(0)
            if updated:
                if checkpoint_after[cp] < k_update_batch:
                    raise ValueError('An updated key fact is asked before its update')
                key['old'] = key['value']
                key['value'] = make.k_value()
                key_updates.append((key['id'], key['value']))
            questions[cp].append({'type': 'K', 'record': key['id'], 'field': key['name'], 'marked': marked,
                                  'answer': key['value'], 'updated': updated,
                                  'stale_values': [key['old']] if updated else [],
                                  'source': f'batch {k_update_batch:02d}' if updated else 'opening',
                                  'source_batch': k_update_batch if updated else 0, 'born_batch': 0,
                                  'updated_in': [k_update_batch] if updated else []})
    # Filler updates (never asked records) so that update lines carry no hint of being asked
    for b in positions:
        if b < 3:
            continue
        while len(updates[b]) < UPDATES_PER_BATCH:
            ident = rng.choice([i for i in records if born[i] < b and i not in taken])
            taken.add(ident)
            field = rng.choice(('qty', 'status', 'site', 'tag'))
            value = make.changed(records[ident], field)
            records[ident][field] = value
            updates[b].append((ident, field, value))
    # Texts
    total = len(positions)
    sequence = [{'kind': 'opening', 'label': 'opening', 'text': opening}]
    number = 0
    for cp_index, ask in enumerate(questions):
        rng.shuffle(ask)
        for q in ask:
            number += 1
            q['id'] = f'Q{number:02d}'
            q['checkpoint'] = cp_index + 1
    for b in positions:
        record_updates = updates[b]
        text = f'Batch {b:02d}/{total:02d}. New records:\n' + '\n'.join(record_line(created[i]) for i in content[b])
        if record_updates:
            text += ('\nUpdates to earlier records (the new value replaces the old one):\n'
                     + '\n'.join(f'UPDATE {i} {f}={v}' for i, f, v in record_updates))
        if b == k_update_batch:
            marks = {k['id']: k['marked'] for k in keys}
            text += ('\nUpdates to key facts (the new value replaces the old one):\n'
                     + '\n'.join(f'UPDATE {i} = {v}' + (f' {MARK}' if marks[i] else '') for i, v in key_updates))
        text += f'\n\nReply with exactly `ACK {b:02d}`.'
        sequence.append({'kind': 'batch', 'label': f'batch {b:02d}', 'batch': b, 'text': text})
        if b in checkpoint_after:
            cp = checkpoint_after.index(b) + 1
            ask = questions[cp - 1]
            lines = []
            for q in ask:
                if q['type'] == 'K':
                    lines.append(f'{q["id"]}: What is the current value of key fact {q["record"]} ({q["field"]})?')
                else:
                    lines.append(f'{q["id"]}: What is the {q["field"]} of record {q["record"]}?')
            sequence.append({'kind': 'questions', 'label': f'questions {cp}', 'checkpoint': cp,
                             'text': QUESTION_HEAD.format(n=cp, total=len(CHECKPOINTS)) + '\n'.join(lines)})
    tokens = count([s['text'] for s in sequence])
    position = BASE_TOKENS
    for s, t in zip(sequence, tokens):
        s['tokens'] = t
        position += t + (ANSWER_TOKENS if s['kind'] == 'questions' else TURN_OVERHEAD_TOKENS)
        s['position_after'] = position  # estimated context after this turn if nothing were compacted
    at = {s['label']: s['position_after'] for s in sequence}
    flat = [q for ask in questions for q in ask]
    for q in flat:
        source_at = at['opening'] if q['source'] == 'opening' else at[q['source']]
        q['age_tokens'] = at[f'questions {q["checkpoint"]}'] - source_at
    return {'schema': SCHEMA, 'generator_sha256': sha(Path(__file__).read_bytes()), 'seed': seed,
            'counter': 'tokenizer' if counter else f'chars/{CHARS_PER_TOKEN}',
            'assumptions': {'base_tokens': BASE_TOKENS, 'turn_overhead_tokens': TURN_OVERHEAD_TOKENS,
                            'answer_tokens': ANSWER_TOKENS},
            'checkpoint_targets': list(CHECKPOINTS), 'batches': total, 'k_update_batch': k_update_batch,
            'keys': keys, 'sequence': sequence, 'questions': flat,
            'checkpoint_positions': [at[f'questions {n}'] for n in range(1, len(CHECKPOINTS) + 1)]}


TOKEN_COUNTER = '''import json,sys
from pathlib import Path
root=Path(sys.argv[1]);sys.path.insert(0,str(root/'runtime/Strata/tools'))
from strata_tokenizer import Tokenizer
d=root/'data/packs'/sys.argv[2]/'tokenizer'
vocab=json.loads((d/'vocab.json').read_text(encoding='utf-8'));tokens=[None]*len(vocab)
for t,i in vocab.items():tokens[i]=t
tk=Tokenizer(tokens,[m for m in (d/'merges.txt').read_text(encoding='utf-8').split('\\n') if m])
print(json.dumps([len(tk.encode(t)) for t in json.loads(Path(sys.argv[3]).read_text(encoding='utf-8'))]))
'''


def tokenizer_counter(host_id, pack='iq3_xxs'):
    """Exact counts with the installed Strata tokenizer (read-only Windows-side Python; no model, no lease)."""
    from tools.ops.measurement_host import MeasurementHost
    host = MeasurementHost(host_id)
    python = host.installation / 'runtime/Strata/.venv/Scripts/python.exe'

    def count(texts):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2] / '.tmp') as tmp:
            path = Path(tmp) / 'texts.json'
            path.write_text(json.dumps(texts), encoding='utf-8')
            windows = subprocess.check_output(['wslpath', '-w', str(path)], text=True).strip()
            reply = subprocess.run([str(python), '-I', '-c', TOKEN_COUNTER, str(host.windows_root), pack, windows],
                                   cwd='/mnt/c', capture_output=True, text=True, check=True, timeout=600)
        return json.loads(reply.stdout)
    return count


ANSWER_LINE = re.compile(r'^\W*(Q\d{2})\W*[:=]\s*(.+?)\s*$', re.M)
ACK = re.compile(r'^\s*`?ACK (\d{2})`?\s*$')
CONTEXT_BINS = ((0, 100000, '<100K'), (100000, 150000, '100-150K'), (150000, 10 ** 9, '>=150K'))
AGE_BANDS = ((0, 30000, '<30K'), (30000, 60000, '30-60K'), (60000, 100000, '60-100K'), (100000, 10 ** 9, '>=100K'))


def normalize(value):
    return re.sub(r'\s+', ' ', re.sub(r'^[\s`*"\'.]+|[\s`*"\'.]+$', '', value)).lower()


def band(value, bands):
    return next(name for low, high, name in bands if low <= value < high)


def answers(replies):
    """`replies`: the final text of each question turn.  The last answer to a question wins."""
    given = {}
    for text in replies:
        for ident, value in ANSWER_LINE.findall(text or ''):
            given[ident] = value
    return given


def category(q):
    return 'K-marked' if q['type'] == 'K' and q['marked'] else 'K-unmarked' if q['type'] == 'K' else q['type']


def score(workload, replies, timeline=None, weights=None):
    """Score the 60 questions; with `timeline` (per checkpoint: raw labels, compactions before the turn and the
    context the turn's request carried) split them into the model-dependent components of design §2.2:
    C1 retrieval from raw context by context bin, C2 retention after compaction by category, the mechanical share M
    still in raw text, and E (checkpoints weighted by `weights`, default equal; E equals the raw accuracy then)."""
    given = answers(replies)
    rows = []
    for q in workload['questions']:
        value = given.get(q['id'])
        row = {k: q[k] for k in ('id', 'checkpoint', 'type', 'record', 'field', 'source', 'age_tokens')}
        row.update(category=category(q), given=value,
                   correct=value is not None and normalize(value) == normalize(q['answer']),
                   stale=value is not None and normalize(value) != normalize(q['answer'])
                   and normalize(value) in [normalize(str(o)) for o in q.get('stale_values', [])])
        rows.append(row)
    result = {'raw_score': sum(r['correct'] for r in rows) / len(rows), 'correct': sum(r['correct'] for r in rows),
              'questions': len(rows), 'answered': sum(r['given'] is not None for r in rows),
              'stale_answers': sum(r['stale'] for r in rows), 'rows': rows}
    if timeline is None:
        return result
    turn = {x['label']: i for i, x in enumerate(workload['sequence'])}
    for r in rows:
        point = timeline[r['checkpoint'] - 1]
        r['in_text'] = r['source'] in point['raw']
        r['context_tokens'] = point.get('context_tokens')
        r['bin'] = band(point['context_tokens'], CONTEXT_BINS) if point.get('context_tokens') is not None else None
        r['compactions_since_source'] = sum(1 for c in point['compactions_after'] if turn[c] >= turn[r['source']])
        r['age_band'] = band(r['age_tokens'], AGE_BANDS)
    accuracy = lambda xs: (sum(x['correct'] for x in xs) / len(xs)) if xs else None
    cells = {}
    for r in rows:
        key = ('C1', r['bin']) if r['in_text'] else ('C2', r['category'])
        cells.setdefault(key, []).append(r)
    weights = weights or {n: 1 / len(timeline) for n in range(1, len(timeline) + 1)}
    per_cp = {n: [r for r in rows if r['checkpoint'] == n] for n in weights}
    e = sum(weights[n] * sum(accuracy(cells[('C1', r['bin']) if r['in_text'] else ('C2', r['category'])])
                             for r in per_cp[n]) / len(per_cp[n]) for n in per_cp)
    c2_detail = {}
    for r in rows:
        if not r['in_text']:
            c2_detail.setdefault(f'{r["category"]}/{r["compactions_since_source"]}', []).append(r)
    result.update(
        score=e, weights=weights,
        C1={name: {'accuracy': accuracy(xs), 'n': len(xs)} for (kind, name), xs in sorted(cells.items(), key=str)
            if kind == 'C1'},
        C2={name: {'accuracy': accuracy(xs), 'n': len(xs)} for (kind, name), xs in sorted(cells.items(), key=str)
            if kind == 'C2'},
        C2_by_compactions={k: {'accuracy': accuracy(v), 'n': len(v)} for k, v in sorted(c2_detail.items())},
        M={f'{n}/{a}': sum(r['in_text'] for r in xs) / len(xs) for n in per_cp for a in [b[2] for b in AGE_BANDS]
           if (xs := [r for r in per_cp[n] if r['age_band'] == a])},
        in_text_share=sum(r['in_text'] for r in rows) / len(rows))
    return result


def self_check(workload):
    """No-model precheck: answers equal the replayed state, every fact asked once and never mentioned after it is
    asked, checkpoint composition, positions near the targets, and a scorer that separates perfect from empty."""
    problems, state, keys = [], {}, {}
    seen_after = {}
    asked_at = {}
    sequence = workload['sequence']
    by_checkpoint = {}
    for q in workload['questions']:
        by_checkpoint.setdefault(q['checkpoint'], []).append(q)
        if q['record'] in asked_at:
            problems.append(f'{q["record"]} asked twice')
        asked_at[q['record']] = q['checkpoint']
    for index, s in enumerate(sequence):
        if s['kind'] == 'questions':
            for q in by_checkpoint[s['checkpoint']]:
                current = keys.get(q['record']) if q['type'] == 'K' else state.get(q['record'], {}).get(q['field'])
                if str(current) != q['answer']:
                    problems.append(f'{q["id"]}: answer differs from the replayed state')
            continue
        for line in s['text'].splitlines():
            if s['kind'] == 'opening' and re.match(r'K\d{2} \| ', line):
                ident, rest = line.split(' | ', 1)
                keys[ident] = rest.split(' = ', 1)[1].replace(' ' + MARK, '')
            elif ' | owner=' in line:
                ident, *pairs = line.split(' | ')
                if ident in state:
                    problems.append(f'duplicate record id {ident}')
                state[ident] = dict(p.split('=', 1) for p in pairs)
                seen_after.setdefault(ident, []).append(index)
            elif re.match(r'UPDATE K\d{2} = ', line):
                ident, value = line[len('UPDATE '):].split(' = ', 1)
                keys[ident] = value.replace(' ' + MARK, '')
                seen_after.setdefault(ident, []).append(index)
            elif line.startswith('UPDATE '):
                _, ident, pair = line.split(' ', 2)
                field, value = pair.split('=', 1)
                state[ident][field] = value
                seen_after.setdefault(ident, []).append(index)
    turn_of = {s.get('checkpoint'): i for i, s in enumerate(sequence) if s['kind'] == 'questions'}
    for q in workload['questions']:
        if any(i > turn_of[q['checkpoint']] for i in seen_after.get(q['record'], [])):
            problems.append(f'{q["id"]}: {q["record"]} appears again after it was asked')
        if any(q['record'] in s['text'] for s in sequence[turn_of[q['checkpoint']] + 1:]
               if s['kind'] == 'questions'):
            problems.append(f'{q["id"]}: {q["record"]} asked again later')
    for n, qs in sorted(by_checkpoint.items()):
        counts = {t: sum(q['type'] == t for q in qs) for t in PER_CHECKPOINT}
        if counts != PER_CHECKPOINT:
            problems.append(f'checkpoint {n}: composition {counts}')
    if len(by_checkpoint) != len(CHECKPOINTS):
        problems.append('checkpoint count differs')
    k = [q for q in workload['questions'] if q['type'] == 'K']
    if sum(q['marked'] for q in k) < 7 or sum(not q['marked'] for q in k) < 7:
        problems.append('marked and unmarked key facts are not balanced')
    for target, got in zip(CHECKPOINTS, workload['checkpoint_positions']):
        if abs(got - target) > 8000:
            problems.append(f'checkpoint at {got}, target {target}')
    perfect = score(workload, ['\n'.join(f'{q["id"]}: {q["answer"]}' for q in workload['questions'])])
    if perfect['raw_score'] != 1 or score(workload, [])['raw_score'] != 0:
        problems.append('scorer does not separate perfect and empty replies')
    return {'ok': not problems, 'problems': problems}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    b = sub.add_parser('build')
    b.add_argument('--seed', type=int, required=True)
    b.add_argument('--out', type=Path, required=True)
    b.add_argument('--count-tokens', metavar='HOST', help='count with the installed tokenizer of this host')
    k = sub.add_parser('check')
    k.add_argument('--workload', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'build':
        counter = tokenizer_counter(args.count_tokens) if args.count_tokens else None
        args.out.write_text(json.dumps(build(args.seed, counter), ensure_ascii=False, indent=1) + '\n')
    else:
        print(json.dumps(self_check(json.loads(args.workload.read_text()))))


if __name__ == '__main__':
    main()
