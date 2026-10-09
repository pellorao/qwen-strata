"""Current-baseline configuration for native Codex compatibility probes.

The legacy WSL experiment configuration remains separate. All generated homes,
catalogs and prompt bindings belong to the supplied measurement directory.
"""
import hashlib
import json
from pathlib import Path
import shutil

from tools.metrics.prompt_policy import compaction_config
from tools.reviewer.wsl_client import ROOT, save


def configuration(out, workspace, base_url, *, model_slug, effort, extra_config):
    bound = dict(extra_config or {})
    baseline = json.loads(Path(bound.pop('runtime_baseline_file')).read_text())
    harness = baseline['harness']
    if effort != harness['model_reasoning_effort']:
        raise ValueError('Effort differs from the frozen current baseline')
    catalog_path = Path(bound.pop('runtime_catalog_file'))
    catalog = json.loads(catalog_path.read_text())
    selected = next(m for m in catalog['models'] if m['slug'] == model_slug)
    window = harness['model_context_window']
    if (selected['context_window'] != window or selected['max_context_window'] != window or
            selected['auto_review_model_override'] != model_slug or
            not selected['supports_search_tool'] or selected['web_search_tool_type'] != 'text'):
        raise ValueError('Native catalog capacity, local guardian or text search differs')
    home = out / 'codex-home'
    home.mkdir(parents=True, exist_ok=True)
    values = {
        'model': model_slug, 'model_provider': 'qwen_strata',
        'model_catalog_json': str(catalog_path),
        'model_context_window': window,
        'model_auto_compact_token_limit': harness['model_auto_compact_token_limit'],
        'model_auto_compact_token_limit_scope': 'total',
        'model_reasoning_effort': effort,
        'model_providers.qwen_strata.name': 'Local Strata native compatibility probe',
        'model_providers.qwen_strata.base_url': base_url,
        'model_providers.qwen_strata.wire_api': 'responses',
        'model_providers.qwen_strata.env_key': 'STRATA_API_KEY',
        'model_providers.qwen_strata.requires_openai_auth': False,
        'model_providers.qwen_strata.supports_websockets': False,
        'model_providers.qwen_strata.request_max_retries': 0,
        'model_providers.qwen_strata.stream_max_retries': 0,
        'mcp_servers.project.command': shutil.which('python3'),
        'mcp_servers.project.args': [str(ROOT / 'src/project_files_mcp.py')],
        'mcp_servers.project.env': {'QWEN_PROJECT_WORKSPACE': str(workspace),
                                  'QWEN_PROJECT_AUDIT': str(out / 'mcp-audit.jsonl')},
    }
    values.update(bound)
    values = compaction_config(values, out / 'prompt-policy')
    save(out / 'config-overrides.json', values)
    save(out / 'runtime-binding.json', {
        'baseline_sha256': hashlib.sha256(Path(extra_config['runtime_baseline_file']).read_bytes()).hexdigest(),
        'catalog_sha256': hashlib.sha256(catalog_path.read_bytes()).hexdigest(),
        'selected_model': model_slug, 'harness': harness,
        'native_tools_and_network_defaults_preserved': True,
    })
    args = []
    for key, value in values.items():
        rendered = ('{' + ','.join(json.dumps(k) + '=' + json.dumps(v)
                    for k, v in value.items()) + '}' if isinstance(value, dict) else json.dumps(value))
        args += ['-c', key + '=' + rendered]
    return home, args
