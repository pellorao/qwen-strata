"""Optional exact line deltas; full text is the safe fallback."""
import difflib


def exact_line_changes(prior, value):
    old = prior.splitlines(keepends=True)
    new = value.splitlines(keepends=True)
    try:
        operations = difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes()
        restored = ''.join(''.join(old[a:b]) if tag == 'equal' else ''.join(new[c:d])
                           for tag, a, b, c, d in operations)
        if restored != value:
            return None
        return [{'old_lines': [a + 1, b], 'new_lines': [c + 1, d],
                 'new_text': ''.join(new[c:d])}
                for tag, a, b, c, d in operations if tag != 'equal']
    except (AttributeError, TypeError, ValueError, IndexError):
        return None
