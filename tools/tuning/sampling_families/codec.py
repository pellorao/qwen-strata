"""codec: implement the exact inverse of a multi-step text encoder that is described only in prose.

Every step is invertible and has a reference inverse here (the tests check the round trip on random text), so the
hidden tests are simply (encoded, original) pairs.  Tier 1 has 5 steps and one worked example; tier 2 has 6 steps
including run-length coding or a rail fence; tier 3 has 7 steps including both and a letter-counting shift, without
examples; level 4 has 8 such steps and always ends with the checksum letter.  (`tier` in this module is the level.)
"""
import json

ALPHABET = 'abcdefghijklmnopqrstuvwxyz'
VOWELS = 'aeiou'


def shift_letter(ch, k):
    for alphabet in (ALPHABET, ALPHABET.upper()):
        if ch in alphabet:
            return alphabet[(alphabet.index(ch) + k) % 26]
    return ch


def shift(k):
    def enc(s, sign=1):
        return ''.join(str((int(c) + sign * k) % 10) if c.isdigit() else shift_letter(c, sign * k) for c in s)
    return (lambda s: enc(s), lambda s: enc(s, -1),
            f'Shift every letter forward by {k} places in the alphabet, keeping its case and wrapping z to a; shift '
            f'every digit d to (d + {k}) mod 10. Other characters are unchanged.')


def progressive(k, d):
    def enc(s, sign=1):
        out, i = [], 0
        for c in s:
            if c.isalpha():
                out.append(shift_letter(c, sign * (k + d * i)))
                i += 1
            else:
                out.append(c)
        return ''.join(out)
    return (lambda s: enc(s), lambda s: enc(s, -1),
            f'Shift letters by a growing amount, keeping case and wrapping: the first letter of the string by {k}, '
            f'the second letter by {k + d}, the third by {k + 2 * d}, and so on (only letters are counted; other '
            'characters are unchanged and do not advance the count).')


def reverse_words():
    def enc(s):
        return ' '.join(w[::-1] for w in s.split(' '))
    return (enc, enc, 'Reverse the characters of every word, where words are the pieces between single spaces '
            '(two spaces in a row enclose an empty word); the spaces stay where they are.')


def rail(r):
    def pattern(n):
        rows, row, step = [], 0, 1
        for _ in range(n):
            rows.append(row)
            if r > 1:
                if row == 0:
                    step = 1
                elif row == r - 1:
                    step = -1
                row += step
        return rows

    def enc(s):
        rows = pattern(len(s))
        return ''.join(c for k in range(r) for c, row in zip(s, rows) if row == k)

    def dec(s):
        rows = pattern(len(s))
        order = sorted(range(len(s)), key=lambda i: (rows[i], i))
        out = [''] * len(s)
        for c, i in zip(s, order):
            out[i] = c
        return ''.join(out)
    return (enc, dec, f'Rail fence with {r} rails: write the characters in a zigzag over rails 1..{r} (first '
            f'character on rail 1, going down to rail {r}, then back up to rail 1, and so on), then read rail 1 left '
            f'to right, then rail 2, ..., then rail {r}.')


def evens_odds():
    def dec(s):
        half = (len(s) + 1) // 2
        out = []
        for i in range(len(s)):
            out.append(s[i // 2] if i % 2 == 0 else s[half + i // 2])
        return ''.join(out)
    return (lambda s: s[0::2] + s[1::2], dec,
            'Write the characters at positions 0, 2, 4, ... (counting from 0) in order, followed by the characters '
            'at positions 1, 3, 5, ...')


def rle():
    def enc(s):
        out, i = [], 0
        while i < len(s):
            c = s[i]
            if c == '~':
                out.append('~~')
                i += 1
                continue
            j = i
            while j < len(s) and s[j] == c:
                j += 1
            run = j - i
            while run >= 3:
                take = min(run, 9)
                out.append(f'~{take}{c}')
                run -= take
            out.append(c * run)
            i = j
        return ''.join(out)

    def dec(s):
        out, i = [], 0
        while i < len(s):
            if s[i] == '~':
                if s[i + 1] == '~':
                    out.append('~')
                    i += 2
                else:
                    out.append(s[i + 2] * int(s[i + 1]))
                    i += 3
            else:
                out.append(s[i])
                i += 1
        return ''.join(out)
    return (enc, dec, 'Run-length coding, scanning left to right: every "~" becomes "~~". Any other character c '
            'that starts a run of n equal characters (n counted as long as possible): while n >= 3, write "~", '
            'then the digit min(n, 9), then c, and reduce n by that amount; then write c the remaining n times '
            '(0, 1 or 2).')


def block_reverse(b):
    def enc(s):
        return ''.join(s[i:i + b][::-1] for i in range(0, len(s), b))
    return (enc, enc, f'Cut the string into blocks of {b} characters from the start (the last block may be '
            'shorter) and reverse the characters inside every block.')


def pair_swap():
    def enc(s):
        chars = list(s)
        for i in range(0, len(chars) - 1, 2):
            chars[i], chars[i + 1] = chars[i + 1], chars[i]
        return ''.join(chars)
    return (enc, enc, 'Swap the characters at positions 0 and 1, 2 and 3, 4 and 5, and so on; a last unpaired '
            'character stays in place.')


def vowel_cycle():
    def enc(s, sign=1):
        out = []
        for c in s:
            low = c.lower()
            if low in VOWELS:
                v = VOWELS[(VOWELS.index(low) + sign) % 5]
                out.append(v.upper() if c.isupper() else v)
            else:
                out.append(c)
        return ''.join(out)
    return (lambda s: enc(s), lambda s: enc(s, -1),
            'Replace every vowel by the next one in the cycle a -> e -> i -> o -> u -> a, keeping its case (y is not '
            'a vowel).')


def flip_case(m):
    def enc(s):
        return ''.join(c.swapcase() if i % m == 0 else c for i, c in enumerate(s))
    return (enc, enc, f'Swap the case of the characters at positions 0, {m}, {2 * m}, ... (counting all characters '
            'from 0; characters without case are unchanged).')


def rotate(k):
    def enc(s, sign=1):
        if not s:
            return s
        n = (sign * (len(s) % k)) % len(s)
        return s[n:] + s[:n]
    return (lambda s: enc(s), lambda s: enc(s, -1),
            f'Let n = (length of the string) mod {k}. Move the first n characters to the end, in order.')


def checksum():
    def enc(s):
        return s + ALPHABET[sum(map(ord, s)) % 26]
    return (enc, lambda s: s[:-1], 'Append one lowercase letter: the letter with index (sum of the character '
            'codes of the string) mod 26, where a has index 0.')


def steps(rng, tier):
    plain = [shift(rng.randint(1, 25)), reverse_words(), evens_odds(), block_reverse(rng.randint(3, 5)),
             pair_swap(), vowel_cycle(), flip_case(rng.randint(2, 4)), rotate(rng.randint(3, 7))]
    need = {1: [], 2: [rng.choice([rle(), rail(rng.randint(3, 4))])],
            3: [rle(), rail(rng.randint(3, 4)), progressive(rng.randint(1, 9), rng.randint(2, 7))]}[min(tier, 3)]
    chosen = rng.sample(plain, {1: 5, 2: 6, 3: 7, 4: 8}[tier] - len(need)) + need
    rng.shuffle(chosen)
    if tier >= 4 or tier >= 2 and rng.random() < 0.5:
        chosen.append(checksum())
    return chosen


def samples(rng, count):
    alphabet = 'abcdeiouxyzAEIOUQZ0123456789  !?-.~'
    out = ['', 'a', 'Zz 9', 'aaaa   bbbbbbbbbbbb!!', '~~a~', 'Hello World 2024', 'u U y Y', '11122233']
    while len(out) < count:
        word = ''.join(rng.choice(alphabet) for _ in range(rng.randint(1, 28)))
        if rng.random() < 0.4:
            k = rng.randrange(len(word))
            word = word[:k] + word[k] * rng.randint(3, 12) + word[k:]
        if word not in out:
            out.append(word)
    return out


def item(rng, tier):
    chosen = steps(rng, tier)

    def encode(s):
        for enc, _, _ in chosen:
            s = enc(s)
        return s

    texts = samples(rng, 40)
    encoded = [encode(s) for s in texts]
    if len(set(encoded)) != len(encoded):
        raise AssertionError('codec pipeline is not injective on the samples')
    cases = [{'args': [e], 'expected': s} for s, e in zip(texts, encoded)]
    listed = '\n'.join(f'{i}. {text}' for i, (_, _, text) in enumerate(chosen, 1))
    if tier == 1:
        shown, hidden = cases[-1], cases[:-1]  # a random sample: the fixed edge cases stay hidden everywhere
        example = f'Example: decode({json.dumps(shown["args"][0])}) == {json.dumps(shown["expected"])}\n\n'
    else:
        hidden, example = cases, 'No examples are given; follow the steps exactly as written.\n\n'
    prompt = ('An encoder applies these steps in order, each to the result of the previous one (positions count '
              f'from 0):\n\n{listed}\n\nImplement `decode(s: str) -> str`, the exact inverse of this encoder: '
              f'decode(encoder(t)) == t for every string t.\n\n{example}Use only the Python 3 standard library. '
              'Hidden tests call decode on encoder outputs.')
    return {'kind': 'code', 'entry': 'decode', 'prompt': prompt, 'tests': hidden,
            'stub': 'def decode(s: str) -> str:\n    raise NotImplementedError\n'}
