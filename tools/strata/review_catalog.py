"""Measurement model catalog for the Codex-based tools: the selected local Strata model with its provider entry."""
import json
from pathlib import Path

from tools.metrics.context_capacity import CONTEXT_WINDOWS
from tools.strata.wsl_client import save


def strata_provider(installation, context_window=None, time_limit_seconds=None):
    """ARW provider entry: callers choose only the model and, optionally, a published context tier and a measurement
    time limit T (needs the ARW patch strata-measurement-time-limit: reminder before T, stop at T instead of 55/60 minutes)."""
    if context_window is not None and type(context_window) is not int:
        raise ValueError('Unsupported measurement context window')
    if time_limit_seconds is not None and (type(time_limit_seconds) not in (int, float) or time_limit_seconds <= 0):
        raise ValueError('Unsupported measurement time limit')
    return {'driver': 'strata', 'installationDirectory': str(installation),
            **({} if context_window is None else {'contextWindow': context_window}),
            **({} if time_limit_seconds is None else {'reviewTimeLimitSeconds': time_limit_seconds})}


def local_review_catalog(source, target, model, context_window=None, strata_installation=None, time_limit_seconds=None):
    """Declare installed text search and route guardian to the local model."""
    catalog = json.loads(Path(source).read_text())
    if strata_installation is not None:
        # ARW's own Strata provider: it takes the lease, starts the model with the installation
        # defaults and a published context tier, and applies its continuation, pause and work-budget policy.
        catalog['providers'] = {'qwen_strata': strata_provider(strata_installation, context_window, time_limit_seconds)}
    slug = 'qwen3.8-flash-next-' + model.lower()
    selected = next((m for m in catalog['models'] if m['slug'] == slug), None)
    if selected is None:
        raise ValueError('Selected local model is absent from measurement catalog')
    selected['auto_review_model_override'] = slug
    # Borrowed OpenAI metadata advertised image search, which the installed
    # text-only Brave adapter does not implement.
    selected['web_search_tool_type'] = 'text'
    if context_window is not None and strata_installation is None:
        if type(context_window) is not int or context_window not in (80000,125000,188000,250000,*CONTEXT_WINDOWS):
            raise ValueError('Unsupported measurement context window')
        selected['context_window'] = context_window
        selected['max_context_window'] = context_window
    save(target, catalog)
    return target
