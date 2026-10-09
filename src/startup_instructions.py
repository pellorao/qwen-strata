"""Snapshot installation-owned instructions once per native model process."""
import hashlib
from pathlib import Path


def startup_prompt_bytes(raw, include_loop_prevention=True):
    """Omit only the named diagnostic block; preserve every remaining byte."""
    if type(include_loop_prevention) is not bool:
        raise ValueError('Loop prevention selection must be boolean.')
    if include_loop_prevention:
        return raw
    first = b'Progress and loop prevention:\n'
    next_section = b'\n\nComplete the assigned task:\n'
    if (not raw.startswith(first) or raw.count(first) != 1
            or raw.count(next_section) != 1):
        raise ValueError('Cannot identify the exact loop prevention block.')
    return b'Complete the assigned task:\n' + raw.split(next_section, 1)[1]


def load_startup_instructions(root, enabled=True, include_loop_prevention=True):
    if type(enabled) is not bool:
        raise ValueError('Startup instruction selection must be boolean.')
    if not enabled:
        return None, {'path': None, 'sha256': hashlib.sha256(b'').hexdigest(),
                      'enabled': False, 'scope': 'explicit-diagnostic-no-project-startup'}
    path = Path(root) / 'config/prompts/startup-instructions.txt'
    source = path.read_bytes()
    raw = startup_prompt_bytes(source, include_loop_prevention)
    text = raw.decode('utf-8').strip()
    if not text:
        raise ValueError('Installation startup instructions must not be empty.')
    metadata = {'path': 'config/prompts/startup-instructions.txt',
                'sha256': hashlib.sha256(raw).hexdigest()}
    if not include_loop_prevention:
        metadata.update(enabled=True, loop_prevention_enabled=False,
                        source_sha256=hashlib.sha256(source).hexdigest(),
                        scope='explicit-diagnostic-without-loop-prevention-block')
    return text, metadata


def add_startup_instructions(messages, instructions):
    """Keep caller data intact; each render starts from its original history."""
    result = list(messages)
    if result and result[0].get('role') == 'system':
        first = dict(result[0])
        content = first.get('content', '')
        if isinstance(content, list):
            first['content'] = [*content, {'type': 'text', 'text': instructions}]
        else:
            first['content'] = content + '\n\n' + instructions
        result[0] = first
    else:
        result.insert(0, {'role': 'system', 'content': instructions})
    return result


def install_startup_instructions(service_class, instructions):
    original = service_class.prepare

    def prepare(self, messages, *args, **kwargs):
        return original(self, add_startup_instructions(messages, instructions),
                        *args, **kwargs)

    service_class.prepare = prepare
