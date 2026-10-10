"""Mechanical repetition detector: dynamic text recurrence only, no model calls.

No keyword, stop-word or business vocabulary: term weights come only from the segments this trace has produced so
far (a term that appears in many earlier segments weighs little). Each judged record is cut into segments, and each
segment is compared with the earlier segments of the last WINDOW records. Every match at weighted cosine c >= FLOOR is
evidence; the record's probability of being a repetition is 1 - prod((1 - c) ** STRENGTH) over all matches of all its
segments, so several partial matches (a step said again in other words) add up like one close copy. A tool record
that repeats the same call and result K times within the window is a repetition (probability 1). A task or feedback
input that brings new content (a segment unlike every earlier input segment) starts a new epoch: answers to a changed
input are not repeats of answers to the old one. An input that only repeats earlier input ("continue") changes nothing.
"""
from collections import Counter, defaultdict
import json
import math
import re

K = 2                 # occurrences before a repeat is reported (the scoring contract's k)
WINDOW = 10           # a record is compared only with the last WINDOW records
FLOOR = 0.3           # weighted cosine below which a match is no evidence
STRENGTH = 0.3        # evidence per match; with 0.3 the alert threshold 0.5 sits at a noisy-OR of about 0.9
NOVELTY = 0.9         # an input segment less similar than this to every earlier input starts a new epoch
MIN_TERMS = 20        # segments with fewer distinct terms are too short to compare
SEGMENT_TERMS = 60    # long paragraphs are cut into pieces of about this many terms
CANDIDATE_TERMS = 6   # rarest terms of a segment used to find earlier candidates

_WORD = re.compile(r'\w+', re.UNICODE)


def terms(text):
    """Words of the text; numbers alone (line numbers, counts, enumerations) are not compared."""
    return [w.lower() for w in _WORD.findall(text or '') if not w.isdigit()]


def segments(text):
    for paragraph in re.split(r'\n\s*\n', text or ''):
        words = terms(paragraph)
        for start in range(0, len(words), SEGMENT_TERMS):
            piece = words[start:start + SEGMENT_TERMS]
            if len(set(piece)) >= MIN_TERMS:
                yield piece


def tool_text(payload):
    return json.dumps([payload.get('name'), payload.get('arguments'), payload.get('output')],
                      sort_keys=True, ensure_ascii=False)


class Mechanical:
    def reset(self, trace):
        self.seen = []                       # (Counter, record, epoch, chain root)
        self.frequency = Counter()           # in how many earlier segments each term occurs
        self.index = defaultdict(list)       # term -> earlier segment numbers
        self.tools = defaultdict(list)       # exact call + result text -> records it occurred at
        self.inputs = []                     # Counter per earlier task / feedback segment
        self.epoch = 0
        self.record = 0

    def _weight(self, term):
        return math.log((len(self.seen) + 2) / (self.frequency[term] + 1))

    def _cosine(self, a, b):
        dot = sum(a[t] * b[t] * self._weight(t) ** 2 for t in a.keys() & b.keys())
        norm = lambda v: math.sqrt(sum((n * self._weight(t)) ** 2 for t, n in v.items()))
        return dot / (norm(a) * norm(b) or 1)

    def _add(self, words):
        """Store the segment; return the log of its remaining doubt, sum((1 - c) ** STRENGTH) in log form."""
        vector = Counter(words)
        rare = sorted(vector, key=lambda t: self.frequency[t])[:CANDIDATE_TERMS]
        candidates = Counter(n for t in rare for n in self.index[t])
        doubt, number = 0.0, len(self.seen)
        root = number
        for earlier_number, shared in candidates.items():
            earlier, record, epoch, earlier_root = self.seen[earlier_number]
            if shared >= 2 and epoch == self.epoch and self.record - record <= WINDOW:
                cosine = self._cosine(vector, earlier)
                if cosine >= FLOOR:
                    doubt += STRENGTH * math.log(max(1 - cosine, 1e-9))
                    root = min(root, earlier_root)
        self.seen.append((vector, self.record, self.epoch, root))
        for t in vector:
            self.frequency[t] += 1
            self.index[t].append(number)
        if root != number:
            self.roots.add(root)
        return doubt

    def observe(self, observation):
        payload = observation.payload
        kind = payload.get('kind')
        self.record += 1
        self.roots = set()                   # roots of the recurrence chains this record matched
        if kind == 'tool':
            text = tool_text(payload)
            at = self.tools[text]
            at.append(self.record)
            for words in segments(json.dumps(payload.get('arguments'), ensure_ascii=False)):
                self._add(words)
            self.roots = {text}
            return 1.0 if sum(self.record - r <= WINDOW for r in at) >= K else 0.0
        if kind in ('reasoning', 'assistant'):
            return 1 - math.exp(sum(self._add(words) for words in segments(payload.get('text'))))
        novel = False
        for words in segments(payload.get('text')):
            vector = Counter(words)
            novel = novel or all(self._cosine(vector, earlier) < NOVELTY for earlier in self.inputs)
            self.inputs.append(vector)
            self._add(words)
        self.epoch += novel
        return 0.0
