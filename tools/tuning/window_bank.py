"""Generated long-conversation recall workload for the context window / compaction tuning dimension.

One session per length: an opening turn, then record batches as user messages (later batches also update earlier
records), then question turns about early, middle and recent records, some updated once or twice.  Records live only
in the conversation, so the answers come from context or from the compaction summary, never from files.

    python3 -m tools.tuning.window_bank build --seed S --out window.json [--count-tokens HOST]
    python3 -m tools.tuning.window_bank score --workload window.json --length L130 --replies replies.json
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import subprocess
import tempfile

# target context before the questions, in tokens: L130 crosses the 100K threshold only, L180 crosses both
LENGTHS = {'L130': 130000, 'L180': 180000}
CODEX_BASE_TOKENS = 12000       # Codex instructions, tool schemas and startup prompt (estimate; checked from the log)
TURN_OVERHEAD_TOKENS = 300      # wrapper text, reasoning and the ACK reply per batch turn (estimate)
QUESTION_TOKENS = 4000          # four question turns and answers
RECORDS_PER_BATCH = 125
UPDATES_PER_BATCH = 10
QUESTIONS_PER_TURN = 10
CHARS_PER_TOKEN = 2.4           # fallback only; the frozen workload records exact tokenizer counts
FIELDS = ('owner', 'site', 'qty', 'status', 'tag')
STATUS = ('open', 'held', 'packed', 'shipped', 'returned', 'closed')
CATEGORIES = (('early', 'static', 6), ('early', 'updated', 8), ('early', 'twice', 6), ('middle', 'static', 5),
              ('middle', 'updated', 5), ('recent', 'static', 5), ('recent', 'updated', 5))

OPENING = ('This is a long-context recall test. I will send numbered batches of synthetic inventory records, some '
           'with updates to earlier records. For each batch reply with exactly `ACK <batch number>` and nothing else. '
           'Do not run commands, do not read or write files and do not search: the records exist only in this '
           'conversation. After the last batch I will ask questions about the current state of records.\n\n'
           'Reply with exactly `ACK 00`.')


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


def build_length(rng, name, batches, ask=True):
    used, records, order = set(), {}, []
    turns, updates_at = [], {}

    def new_record():
        ident = unique(rng, lambda: f'{rng.choice("BCDFGHJKLMNPRSTVWXZ")}{rng.choice("BCDFGHJKLMNPRSTVWXZ")}-'
                                    f'{rng.randint(1000, 9999)}', used)
        return {'id': ident, 'owner': unique(rng, lambda: syllables(rng, 2).title() + ' ' + syllables(rng, 3).title(), used),
                'site': unique(rng, lambda: f'{syllables(rng, 1).upper()}{rng.choice("XQJ")}-{rng.randint(10, 99)}', used),
                'qty': rng.randint(10, 999), 'status': rng.choice(STATUS), 'tag': unique(rng, lambda: syllables(rng, 3), used)}

    def changed(r, field):
        if field == 'qty':
            return unique(rng, lambda: rng.randint(10, 999), {r['qty']})
        if field == 'status':
            return rng.choice([s for s in STATUS if s != r['status']])
        if field == 'site':
            return unique(rng, lambda: f'{syllables(rng, 1).upper()}{rng.choice("XQJ")}-{rng.randint(10, 99)}', used)
        return unique(rng, lambda: syllables(rng, 3), used) if field == 'tag' else \
            unique(rng, lambda: syllables(rng, 2).title() + ' ' + syllables(rng, 3).title(), used)

    third = batches // 3
    zone = lambda b: 'early' if b <= third else 'recent' if b > batches - 3 else 'middle'
    history = {}
    for b in range(1, batches + 1):
        fresh = [new_record() for _ in range(RECORDS_PER_BATCH)]
        for r in fresh:
            records[r['id']] = dict(r)
            order.append((r['id'], b))
            history[r['id']] = []
        changes = []
        if b >= 3:
            # a fixed mix per batch: re-updates (records updated twice), the previous batch (recent updates)
            # and any earlier record
            earlier = [i for i, at in order if at < b]
            again = [i for i in earlier if history[i]]
            previous = [i for i, at in order if at == b - 1]
            chosen = rng.sample(again, min(3, len(again))) + rng.sample(previous, 3)
            chosen += rng.sample([i for i in earlier if i not in chosen], UPDATES_PER_BATCH - len(chosen))
            for ident in chosen:
                field = rng.choice(('qty', 'status', 'site', 'tag'))
                value = changed(records[ident], field)
                records[ident][field] = value
                history[ident].append((b, field, value))
                changes.append(f'UPDATE {ident} {field}={value}')
        text = (f'Batch {b:02d}/{batches:02d}. New records:\n' + '\n'.join(map(record_line, fresh))
                + ('\nUpdates to earlier records (the new value replaces the old one):\n' + '\n'.join(changes)
                   if changes else '') + f'\n\nReply with exactly `ACK {b:02d}`.')
        turns.append(text)
    if not ask:
        return {'turns': turns}
    born = dict(order)
    pools = {}
    for ident, b in order:
        kinds = {0: 'static', 1: 'updated'}.get(len(history[ident]), 'twice')
        pools.setdefault((zone(b), kinds), []).append(ident)
    questions = []
    for where, kind, count in CATEGORIES:
        for ident in rng.sample(pools[(where, kind)], count):
            # updated records are asked about an updated field when possible, so the old value is a wrong answer
            field = history[ident][-1][1] if kind != 'static' else rng.choice(FIELDS)
            questions.append({'record': ident, 'field': field, 'answer': str(records[ident][field]),
                              'position': where, 'kind': kind, 'batch': born[ident],
                              'updated_in': [h[0] for h in history[ident]]})
    rng.shuffle(questions)
    for n, q in enumerate(questions, 1):
        q['id'] = f'Q{n:02d}'
    question_turns = []
    for start in range(0, len(questions), QUESTIONS_PER_TURN):
        chunk = questions[start:start + QUESTIONS_PER_TURN]
        question_turns.append(
            'Questions about the current state of the records, after all updates in all batches. Answer from this '
            'conversation only; do not run commands or read files. Reply with one line per question in the form '
            '`Q01: <value>`, writing the value exactly as it appears in the records (write `unknown` if you cannot '
            'recall it).\n\n' + '\n'.join(f'{q["id"]}: What is the {q["field"]} of record {q["record"]}?' for q in chunk))
    return {'name': name, 'batches': batches, 'opening': OPENING, 'turns': turns, 'question_turns': question_turns,
            'questions': questions}


def batches_for(target, tokens_per_batch):
    payload = target - CODEX_BASE_TOKENS - QUESTION_TOKENS
    return max(6, round(payload / (tokens_per_batch + TURN_OVERHEAD_TOKENS)))


def build(seed, counter=None):
    """Frozen workload. `counter(texts) -> token counts` makes the batch count exact for the model's tokenizer."""
    count = counter or (lambda texts: [round(len(t) / CHARS_PER_TOKEN) for t in texts])
    probe = build_length(random.Random(f'window/{seed}/probe'), 'probe', 4, ask=False)
    per_batch = sum(count(probe['turns'][2:])) / 2
    lengths = {}
    for name, target in LENGTHS.items():
        value = build_length(random.Random(f'window/{seed}/{name}'), name, batches_for(target, per_batch))
        tokens = count([value['opening'], *value['turns'], *value['question_turns']])
        value['tokens'] = {'opening': tokens[0], 'batches': sum(tokens[1:1 + value['batches']]),
                           'questions': sum(tokens[1 + value['batches']:]),
                           'estimated_context_before_questions': CODEX_BASE_TOKENS + tokens[0]
                           + sum(tokens[1:1 + value['batches']]) + TURN_OVERHEAD_TOKENS * value['batches'],
                           'counter': 'tokenizer' if counter else f'chars/{CHARS_PER_TOKEN}'}
        lengths[name] = value
    return {'schema': 'window-workload-v1', 'generator_sha256': sha(Path(__file__).read_bytes()), 'seed': seed,
            'targets': LENGTHS, 'assumptions': {'codex_base_tokens': CODEX_BASE_TOKENS,
                                                'turn_overhead_tokens': TURN_OVERHEAD_TOKENS},
            'lengths': lengths}


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


def normalize(value):
    return re.sub(r'\s+', ' ', re.sub(r'^[\s`*"\'.]+|[\s`*"\'.]+$', '', value)).lower()


def score(length, replies):
    """`replies`: the assistant's final text for each question turn, in order.  Last answer to a question wins."""
    given = {}
    for text in replies:
        for ident, value in ANSWER_LINE.findall(text or ''):
            given[ident] = value
    rows = [{**{k: q[k] for k in ('id', 'record', 'field', 'position', 'kind', 'batch')}, 'given': given.get(q['id']),
             'correct': q['id'] in given and normalize(given[q['id']]) == normalize(q['answer'])}
            for q in length['questions']]
    groups = {}
    for r in rows:
        groups.setdefault(f'{r["position"]}/{r["kind"]}', []).append(r['correct'])
    stale = sum(1 for r, q in zip(rows, length['questions']) if not r['correct'] and r['given'] is not None
                and q['kind'] != 'static')
    return {'score': sum(r['correct'] for r in rows) / len(rows), 'correct': sum(r['correct'] for r in rows),
            'questions': len(rows), 'by_group': {k: sum(v) / len(v) for k, v in sorted(groups.items())},
            'wrong_on_updated': stale, 'rows': rows}


def self_check(workload):
    """No-model precheck: unique ids, answers equal the replayed final state, questions cover every category."""
    problems = []
    for name, length in workload['lengths'].items():
        state = {}
        for text in length['turns']:
            for line in text.splitlines():
                if ' | owner=' in line:
                    ident, *pairs = line.split(' | ')
                    if ident in state:
                        problems.append(f'{name}: duplicate record id {ident}')
                    state[ident] = dict(p.split('=', 1) for p in pairs)
                elif line.startswith('UPDATE '):
                    _, ident, pair = line.split(' ', 2)
                    field, value = pair.split('=', 1)
                    state[ident][field] = value
        for q in length['questions']:
            if state[q['record']][q['field']] != q['answer']:
                problems.append(f'{name} {q["id"]}: answer differs from the replayed state')
        for where, kind, count in CATEGORIES:
            if sum(q['position'] == where and q['kind'] == kind for q in length['questions']) != count:
                problems.append(f'{name}: category {where}/{kind} count differs')
        perfect = score(length, ['\n'.join(f'{q["id"]}: {q["answer"]}' for q in length['questions'])])
        if perfect['score'] != 1 or score(length, [])['score'] != 0:
            problems.append(f'{name}: scorer does not separate perfect and empty replies')
    return {'ok': not problems, 'problems': problems}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    b = sub.add_parser('build')
    b.add_argument('--seed', type=int, required=True)
    b.add_argument('--out', type=Path, required=True)
    b.add_argument('--count-tokens', metavar='HOST', help='count with the installed tokenizer of this host')
    c = sub.add_parser('score')
    c.add_argument('--workload', type=Path, required=True)
    c.add_argument('--length', required=True, choices=sorted(LENGTHS))
    c.add_argument('--replies', type=Path, required=True, help='JSON list of the question-turn replies')
    k = sub.add_parser('check')
    k.add_argument('--workload', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'build':
        counter = tokenizer_counter(args.count_tokens) if args.count_tokens else None
        args.out.write_text(json.dumps(build(args.seed, counter), ensure_ascii=False, indent=1) + '\n')
    elif args.command == 'score':
        workload = json.loads(args.workload.read_text())
        result = score(workload['lengths'][args.length], json.loads(args.replies.read_text()))
        print(json.dumps({k: v for k, v in result.items() if k != 'rows'}))
    else:
        print(json.dumps(self_check(json.loads(args.workload.read_text()))))


if __name__ == '__main__':
    main()
