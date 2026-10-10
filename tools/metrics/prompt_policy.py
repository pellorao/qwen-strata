"""Compose project compaction instructions without dropping caller supplements."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NATIVE_COMPACT_VERSION = '0.160.1'


def verify_loaded_startup(metadata, expected_sha256):
    """The loaded SHA pins the exact prompt, with or without the deprecated loop prevention block."""
    if (not isinstance(metadata,dict)
            or metadata.get('path')!='config/prompts/startup-instructions.txt'
            or metadata.get('sha256')!=expected_sha256
            or 'enabled' in metadata and metadata['enabled'] is not True):
        raise ValueError('Loaded startup instructions differ from the frozen project prompt')
    return metadata


def compaction_config(config, folder, root=ROOT, include_project_base=True):
    if type(include_project_base) is not bool:
        raise ValueError('Project compaction instruction selection must be boolean.')
    values = dict(config)
    sources = []
    parts = []

    def include(text, label, raw=None):
        if not isinstance(text, str) or not text.strip():
            raise ValueError('Empty or invalid compaction prompt: ' + label)
        text = text.strip()
        sources.append({'source': label, 'sha256': hashlib.sha256(
            raw if raw is not None else text.encode()).hexdigest()})
        if text not in parts:
            parts.append(text)

    def file(path):
        path = Path(path).resolve()
        raw = path.read_bytes()
        include(raw.decode('utf-8-sig'), str(path), raw)

    if include_project_base:
        file(root / 'config/prompts/compact-prompt.txt')
    supplied = False
    if 'experimental_compact_prompt_file' in values:
        file(values.pop('experimental_compact_prompt_file'))
        supplied = True
    if 'compact_prompt' in values:
        include(values.pop('compact_prompt'), 'caller.compact_prompt')
        supplied = True
    if not supplied:
        # Versioned supplement verified through the installed native compact path.
        file(root / 'tools/resources/codex' / NATIVE_COMPACT_VERSION / 'compact-prompt.txt')
    text = '\n\n'.join(parts) + '\n'
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'compact-prompt.txt'
    path.write_text(text, encoding='utf-8')
    receipt = {'policy': 'project-base-plus-supplements' if include_project_base else 'native-only-diagnostic', 'sources': sources,
               'rendered_path': str(path.resolve()),
               'rendered_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    (folder / 'compact-prompt-policy.json').write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    values['experimental_compact_prompt_file'] = str(path.resolve())
    return values
