"""Experimental offline text recurrence prototype; NOT validated for harness use.

The annotations used to develop this detector are not runtime inputs. Only the
current root's native text, completed observations and known progress are read.
"""
import hashlib
import re

_WORD = re.compile(r'[A-Za-z][A-Za-z_0-9]*|\d+')
_CAMEL = re.compile(r'[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+')
_STOP = set('a an the and or but if then so to of in on at for from with as by is are was were be been being it its this that these those i me my we our you your they their he she not no yes do does did done have has had having will would could can should may might must let now also actually really just again once more still already each every all any some other same one two three first last next need needs needed using use used make made get got give take about into only through before after while when whether which what why how where there here else than up out satisfied gap uncertain finding findings requirement requirements evidence report reports line lines file files source sources result results value values'.split())
_CUE = re.compile(r'(?i)\b(?:reconsider|revisit|once more|again|already|still|double.?check|let me|i(?:\s+will|\s+should|\s+need|\s+think|[’\']ll)|hmm|wait|actually|on second thought|before (?:writing|ending|finalizing))\b')
_REVISIT = re.compile(r'(?i)\b(?:reconsider|revisit|once more|again|already|still|hmm|wait|actually)\b')
_DECISION = re.compile(r'(?i)\b(?:satisfied|gap|uncertain|accept|reject|write|rewrite|regenerate|normalize|normalization|append|fix|repair|verify|validation|decision|interpret|count|recount|total|same|repeat)\w*\b')
_SCOPE = re.compile(r'(?im)^\s*(?:\*{0,2})?(?:L|Line\s+)(\d+)\s*[:.]')


def _stem(word):
    if len(word) > 7 and word.endswith('ization'):
        word = word[:-7] + 'ize'
    elif len(word) > 5 and word.endswith('ing'):
        word = word[:-3]
    elif len(word) > 4 and word.endswith('ed'):
        word = word[:-2]
    elif len(word) > 4 and word.endswith('s'):
        word = word[:-1]
    return word


def terms(text):
    words = []
    for match in _WORD.finditer(text):
        token = match[0]
        parts = _CAMEL.findall(token) if any(c.isupper() for c in token[1:]) else [token]
        for value in parts:
            value = value.lower()
            if value not in _STOP and not value.isdecimal() and len(value) > 2:
                words.append(_stem(value))
    return set(words)


def segments(text, offset=0):
    """A return must be a separate paragraph, never its own sentence mirror."""
    fence = False
    scope = None
    for match in re.finditer(r'[^\n]+(?:\n(?!\n)[^\n]+)*', text):
        paragraph = match[0]
        if '```' in paragraph:
            # Quoted code can be cited twice during one reasonable verification.
            continue
        if paragraph.lstrip().startswith(('{"', '"source":', '[COPY ', 'END TEXT')):
            continue
        identity = _SCOPE.match(paragraph)
        if identity:
            scope = identity[1]
        if len(paragraph.strip()) < 35:
            continue
        begin = offset + match.start()
        yield {'start': begin, 'end': begin + len(paragraph), 'scope': scope,
               'text': paragraph, 'terms': terms(paragraph),
               'cue': bool(_CUE.search(paragraph)), 'revisit': bool(_REVISIT.search(paragraph)),
               'decision': bool(_DECISION.search(paragraph))}


def similarity(a, b):
    shared = len(a & b)
    return shared / min(len(a), len(b)) if a and b else 0.0


def observe_model_text(state, facts, thread_id):
    """Return bounded hints with actual text spans; never a task-completion verdict."""
    state.setdefault('text_seen', [])
    state.setdefault('text_history', [])
    state.setdefault('text_warned', [])
    hints = []
    for fact in facts:
        if fact.get('threadId') != thread_id or fact.get('compaction') or fact.get('programInjected'):
            continue
        identity = [fact.get('turnId'), fact.get('itemId')]
        if not identity[1] or identity in state['text_seen']:
            continue
        text = fact.get('text')
        if not isinstance(text, str):
            continue
        state['text_seen'] = (state['text_seen'] + [identity])[-4096:]
        local = []
        # Long contiguous exact line repetition is independently observable.
        previous = None
        run = []
        at = fact.get('sourceOffset', 0)
        for line in text.splitlines(keepends=True):
            clean = line.strip()
            if clean and len(clean) >= 12 and clean == previous:
                run.append([identity, at, at + len(line)])
            else:
                run = [[identity, at, at + len(line)]]
                previous = clean
            if len(run) == 3:
                key = hashlib.sha256((str(identity) + clean).encode()).hexdigest()
                if key not in state['text_warned']:
                    state['text_warned'].append(key)
                    hints.append(_hint('literal-text-repeat', run, key))
            at += len(line)
        for row in segments(text, fact.get('sourceOffset', 0)):
            row['identity'] = identity
            if len(row['terms']) < 3:
                continue
            pool = state['text_history'] + local
            candidates = []
            for old in pool[-160:]:
                if row['scope'] and old['scope'] and row['scope'] != old['scope']:
                    continue
                if old['identity'] == identity and old['end'] > row['start']:
                    continue
                score = similarity(set(old['terms']), row['terms'])
                shared = set(old['terms']) & row['terms']
                strong_anchor = any(len(t) >= 7 for t in shared)
                if score >= .5 and len(shared) >= 3:
                    candidates.append(old)
            minimum = 2
            candidates = [c for c in candidates if c['revisit'] or c['decision']]
            if not (row['revisit'] and row['decision']):
                candidates = []
            if len(candidates) >= minimum:
                witnesses = candidates[-max(minimum, 2):] + [row]
                signature = sorted(set.intersection(*(set(w['terms']) for w in witnesses)))
                key = hashlib.sha256((str(identity) + '|'.join(signature)).encode()).hexdigest()
                if key not in state['text_warned']:
                    state['text_warned'].append(key)
                    hints.append(_hint('reasoning-return',
                        [[w['identity'], w['start'], w['end']] for w in witnesses], key))
            local.append({k: sorted(v) if k == 'terms' else v
                          for k, v in row.items() if k != 'text'})
        state['text_history'] = (state['text_history'] + local)[-160:]
        state['text_warned'] = state['text_warned'][-128:]
    return hints


def _hint(kind, positions, key):
    return {'kind': kind, 'key': 'text:' + key, 'evidence_spans': positions,
            'evidence_ids': [p[0] for p in positions],
            'instruction': 'Your current task text returns to the same decision or reproduces the same passage '
                'without an intervening tool observation inside that text. Reuse conclusions already established '
                'from authorized evidence. Write the work already completed to the original bound deliverable '
                'before another broad remapping. Check only the specific remaining uncertainty. Keep the original '
                'scope, permissions and cumulative deadline; this observation does not provide an audit answer '
                'or authorize replaying a tool with unknown side effects.'}
