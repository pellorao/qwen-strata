"""Render the daily Codex model catalog from the installed Codex's own luna entry.

Instructions and message structure come from the native template; every other
field states what Strata actually serves. Work-scope limits belong in scenario
prompts, never here. Measurement runs use frozen catalogs under benchmarks/.
Each model's window is its default (first) context tier in the host deployments;
deployment re-renders it per host (tools.ops.deployment_source).
"""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / 'config/model-catalog.json'
DEPLOYMENTS = ROOT / 'config/deployments'
TEMPLATE = 'gpt-6-luna'
DEFAULT_EFFORT = 'high'
MODELS = {'Q2_0': 'q2_0', 'IQ2_XS': 'iq2_xs', 'IQ3_XXS': 'iq3_xxs'}
EFFORTS = ('low', 'medium', 'high', 'xhigh', 'max')  # the frontend offers no 'none'
FACTS = {
    'visibility': 'list', 'supported_in_api': True, 'availability_nux': None, 'upgrade': None,
    'additional_speed_tiers': [], 'service_tiers': [],
    'input_modalities': ['text'], 'supports_image_detail_original': False,
    'supports_search_tool': True, 'web_search_tool_type': 'text',
    'effective_context_window_percent': 100,
    'default_reasoning_level': DEFAULT_EFFORT, 'supports_reasoning_effort_updates': True,
    'supported_reasoning_levels': [{'effort': e, 'description': 'Strata frontend budget preset; see installation manual.'}
                                   for e in EFFORTS],
    # Plain Responses with direct function tools: no code mode, lite protocol or extra experimental tools.
    'tool_mode': None, 'use_responses_lite': False, 'node_repl_disabled': True, 'node_repl_auto_review_required': True,
    'experimental_supported_tools': [], 'supports_experimental_context': False,
}


def default_windows(deployments=DEPLOYMENTS):
    """Each model's default (first published) context window; every host that publishes tiers must agree."""
    windows = {}
    for path in sorted(Path(deployments).glob('*.json')):
        for model, tiers in json.loads(path.read_text(encoding='utf-8')).get('context_tiers', {}).items():
            windows.setdefault(model, set()).add(tiers[0]['context_window'])
    problems = [m for m in MODELS if len(windows.get(m, ())) != 1]
    if problems:
        raise ValueError('Each model needs one default context tier across host deployments: '
                         + ', '.join(f'{m} {sorted(windows.get(m, ()))}' for m in problems))
    return {m: next(iter(windows[m])) for m in MODELS}


def native_catalog():
    with tempfile.TemporaryDirectory() as home:
        raw = subprocess.check_output(['codex', 'debug', 'models'], env=dict(os.environ, CODEX_HOME=home),
                                      cwd=home, stderr=subprocess.DEVNULL)
    return json.loads(raw)


def render(native, windows):
    template = next(m for m in native['models'] if m['slug'] == TEMPLATE)
    models = []
    for priority, (quant, suffix) in enumerate(MODELS.items(), 1):
        entry = copy.deepcopy(template)
        entry.pop('default_service_tier', None)
        slug = 'qwen3.8-flash-next-' + suffix
        entry.update(copy.deepcopy(FACTS), slug=slug, priority=priority, auto_review_model_override=slug,
                     context_window=windows[quant], max_context_window=windows[quant],
                     display_name=f'Qwen3.8 Flash Next / Strata {quant}',
                     description=f'Local Qwen3.8 Flash Next {quant} served by Strata.')
        models.append(entry)
    return {'models': models}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Fail if the committed catalog differs from this Codex version.')
    args = parser.parse_args()
    version = subprocess.check_output(['codex', '--version'], text=True).strip()
    data = json.dumps(render(native_catalog(), default_windows()), ensure_ascii=False, indent=1) + '\n'
    if args.check:
        same = TARGET.read_text(encoding='utf-8') == data
        print(json.dumps({'codex': version, 'template': TEMPLATE, 'current': same}))
        raise SystemExit(0 if same else 1)
    TARGET.write_text(data, encoding='utf-8')
    print(json.dumps({'codex': version, 'template': TEMPLATE, 'models': list(MODELS), 'bytes': len(data.encode())}))


if __name__ == '__main__':
    main()
