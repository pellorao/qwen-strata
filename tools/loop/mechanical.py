"""Mechanical repetition detector: dynamic text recurrence only, no model calls.

No keyword, stop-word or business vocabulary: term weights come only from the segments this trace has produced so
far (a term that appears in many earlier segments weighs little). Each judged record is cut into segments; a segment
that is close enough to earlier segments of the same trace forms a recurrence chain, and the record is a repetition
when some chain reaches K occurrences within the last WINDOW records. A tool record is a repetition when the
same call returned the same result TOOL_K times. A task or feedback input
that brings new content (a segment unlike every earlier input segment) starts a new epoch: answers to a changed input
are not repeats of answers to the old one. An input that only repeats earlier input ("continue") changes nothing.
"""
from collections import Counter, defaultdict
import json
import math
import re

K = 2                 # occurrences before a repeat is reported (the scoring contract's k)
TOOL_K = 3            # identical call + result occurrences before a tool repeat is reported
WINDOW = 40           # a segment is compared only with segments of the last WINDOW records
SIMILARITY = 0.6      # weighted cosine between two segments to call them the same unit
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
        self.seen = []                       # (Counter, chain size, record, epoch) per segment
        self.frequency = Counter()           # in how many earlier segments each term occurs
        self.index = defaultdict(list)       # term -> earlier segment numbers
        self.tools = Counter()               # exact call + result text -> occurrences
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
        vector = Counter(words)
        rare = sorted(vector, key=lambda t: self.frequency[t])[:CANDIDATE_TERMS]
        candidates = Counter(n for t in rare for n in self.index[t])
        chain = 1
        for number, shared in candidates.items():
            earlier, size, record, epoch = self.seen[number]
            if (shared >= 2 and epoch == self.epoch and self.record - record <= WINDOW and size + 1 > chain
                    and self._cosine(vector, earlier) >= SIMILARITY):
                chain = size + 1
        number = len(self.seen)
        self.seen.append((vector, chain, self.record, self.epoch))
        for t in vector:
            self.frequency[t] += 1
            self.index[t].append(number)
        return chain

    def observe(self, observation):
        payload = observation.payload
        kind = payload.get('kind')
        self.record += 1
        if kind == 'tool':
            text = tool_text(payload)
            self.tools[text] += 1
            chain = K if self.tools[text] >= TOOL_K else 1
            for words in segments(json.dumps(payload.get('arguments'), ensure_ascii=False)):
                self._add(words)
        elif kind in ('reasoning', 'assistant'):
            chain = max([self._add(words) for words in segments(payload.get('text'))] or [1])
        else:
            novel = False
            for words in segments(payload.get('text')):
                vector = Counter(words)
                novel = novel or all(self._cosine(vector, earlier) < NOVELTY for earlier in self.inputs)
                self.inputs.append(vector)
                self._add(words)
            self.epoch += novel
            return 0.0
        return 1.0 if chain >= K else 0.0
