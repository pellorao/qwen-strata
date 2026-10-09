"""Local, content-derived comparison features; no loop verdict or model calls.

The lexical units below are generic Unicode text tokens, not Strata usage
tokens. All units come from the complete supplied text; no keyword or stop-word
lists, case-specific templates, downloaded resources or network are used.
"""
from collections import Counter
import hashlib
import math
import re


_TOKEN = re.compile(r'\w+|[^\w\s]', re.UNICODE)


def normalize_whitespace(text: str) -> str:
    return ' '.join(text.split())


def token_vector(text: str) -> Counter:
    # Hash observed text units without consulting a vocabulary or fixture.
    # Preserve identifiers, case, numbers and punctuation as observed.
    return Counter(hashlib.sha256(match[0].encode('utf-8')).hexdigest()
                   for match in _TOKEN.finditer(text))


def character_vector(text: str, width: int = 3) -> Counter:
    if width < 1:
        raise ValueError('Character window must be positive')
    text = normalize_whitespace(text)
    if not text:
        return Counter()
    if len(text) < width:
        return Counter([text])
    return Counter(text[at:at+width] for at in range(len(text)-width+1))


def cosine(left: Counter, right: Counter) -> float | None:
    if not left or not right:
        return None
    small, large = (left,right) if len(left)<len(right) else (right,left)
    dot = sum(value * large.get(key,0) for key,value in small.items())
    norm = math.sqrt(sum(value*value for value in left.values()) *
                     sum(value*value for value in right.values()))
    return dot / norm if norm else None


def compare(left: str, right: str) -> dict:
    """Describe entire-text resemblance, never assert semantic equivalence."""
    left_normal = normalize_whitespace(left)
    right_normal = normalize_whitespace(right)
    return dict(nonempty_identical=bool(left_normal) and left_normal==right_normal,
        left_characters=len(left_normal),right_characters=len(right_normal),
        lexical_token_cosine=cosine(token_vector(left),token_vector(right)),
        character_trigram_cosine=cosine(character_vector(left),character_vector(right)))
