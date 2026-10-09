"""Render every structural event as exact field changes for manual inspection.

Requires the SHA-verified text references from render_reviewer_session_deltas.
This provides a reading view only, never an inspection verdict.
"""
import argparse
import copy
import json
from pathlib import Path
import re

IDENTIFIERS = {}
IDENTIFIER_PATTERN = re.compile(r"(?:(?:fc|fco|call|rs|msg|retained)_)?(?:[a-f0-9]{24,64}|[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12})")


def references(value):
    if isinstance(value, dict):
        if set(value) == {"exact_text_reference", "sha256"}:
            return {"TEXT": value["exact_text_reference"]}
        return {k: references(v) for k, v in value.items()}
    if isinstance(value, list):
        return [references(v) for v in value]
    if isinstance(value, str) and IDENTIFIER_PATTERN.fullmatch(value):
        if value not in IDENTIFIERS:
            IDENTIFIERS[value] = len(IDENTIFIERS) + 1
        return {"IDENTIFIER": IDENTIFIERS[value]}
    return value


def changes(old, new, path=()):
    if isinstance(old, dict) and isinstance(new, dict):
        result = []
        for key in sorted(old.keys() - new.keys()):
            result.append(("delete", (*path, key), None))
        for key in new:
            if key not in old:
                result.append(("set", (*path, key), new[key]))
            else:
                result.extend(changes(old[key], new[key], (*path, key)))
        return result
    return [] if type(old) is type(new) and old == new else [("set", path, new)]


def event_blocks(text):
    """Accept both canonical single-line and producer multi-line event views."""
    headers = list(re.finditer(r'^EVENT (\d+)([^\n]*)\n?', text, re.MULTILINE))
    for index, match in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        suffix = match[2].strip()
        body = (suffix + '\n' + text[match.end():end]).strip()
        if body.startswith(':'):
            body = body[1:].strip()
        if not body:
            raise ValueError('Incomplete structural event block')
        yield int(match[1]), body


def render(directory):
    previous = {}
    blocks = []
    count = 0
    for source in sorted(directory.glob("events-*.txt")):
        for number, body in event_blocks(source.read_text()):
            assert number == count
            count += 1
            if not body.startswith("{"):
                blocks.append(f"EVENT {number}: {body}\n")
                continue
            event = references(json.loads(body))
            p = event.get("payload", {})
            kind = (event["type"], p.get("type"), p.get("item", {}).get("type"))
            if kind not in previous:
                block = f"EVENT {number} FULL " + json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
            else:
                prior_number, prior = previous[kind]
                delta = changes(prior, event)
                restored = copy.deepcopy(prior)
                block = f"EVENT {number}: all fields same as EVENT {prior_number}, except:\n"
                for operation, path, value in delta:
                    target = restored
                    for key in path[:-1]:
                        target = target[key]
                    if operation == "delete":
                        del target[path[-1]]
                    elif path:
                        target[path[-1]] = value
                    else:
                        restored = value
                    block += json.dumps([operation, list(path), value], ensure_ascii=False, separators=(",", ":")) + "\n"
                assert restored == event, number
            previous[kind] = (number, event)
            blocks.append(block)
    output = directory / "event-deltas"
    output.mkdir(exist_ok=True)
    for stale in output.glob("page-*.txt"):
        stale.unlink()
    page, page_number = "", 1
    for block in blocks:
        if page and len(page) + len(block) > 14000:
            (output / f"page-{page_number:03}.txt").write_text(page)
            page, page_number = "", page_number + 1
        page += block
    if page:
        (output / f"page-{page_number:03}.txt").write_text(page)
    (output / "identifiers.json").write_text(json.dumps({v: k for k, v in IDENTIFIERS.items()}, indent=2) + "\n")
    (output / "manifest.json").write_text(json.dumps({
        "events": count, "pages": page_number, "characters": sum(map(len, blocks)),
        "all_structural_fields_reconstructed": True,
        "text_reference_sha_in_original_bindings": True,
        "inspection_verdict": None,
    }, indent=2) + "\n")
    return {"events": count, "pages": page_number, "characters": sum(map(len, blocks))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    args = parser.parse_args()
    print(json.dumps(render(Path(args.directory))))
