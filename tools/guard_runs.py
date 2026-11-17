"""Run registry and start-rate net of the local usage guard (~/.claude/lib/usage_guard.py), for scripts that start a model process.

The library exists on the maintainer's machine only; where it is missing every call here does nothing, so the project still runs
elsewhere. `registered` shows the run on the status page while it goes; `rate` stops a script that starts model processes over and
over (stop marker, exit 75 through Stopped; an agent acks it after finding the cause: usage_guard.py --ack LABEL --note ...)."""
import contextlib
import importlib
import os
import sys

LIB = os.path.expanduser('~/.claude/lib')
_ug = None


class Stopped(Exception):
    """The start rate of a label is over its cap (a stop marker was written, or an earlier one is not acknowledged yet)."""


def _test_without_state_dirs():
    """A unit test run (unittest loaded) with no USAGE_GUARD_DIR / USAGE_GUARD_RUNS override must not write the real counts and run registry."""
    return 'unittest' in sys.modules and not (os.environ.get('USAGE_GUARD_DIR') and os.environ.get('USAGE_GUARD_RUNS'))


def _lib():
    global _ug
    if _test_without_state_dirs():
        return None
    if _ug is None and os.path.isdir(LIB):
        if LIB not in sys.path:
            sys.path.append(LIB)
        try:
            _ug = importlib.import_module('usage_guard')
        except ImportError:
            pass
    return _ug


def rate(label, max_starts, per_secs):
    """Count one start of `label`; raise Stopped when more than max_starts fall in per_secs."""
    ug = _lib()
    if ug is None:
        return
    try:
        ug.rate_check(label, max_starts, per_secs)
    except ug.Stopped as error:
        raise Stopped(str(error)) from error


@contextlib.contextmanager
def registered(label, harness, model='', effort='', source='', pid=None):
    """Register a model run for the status page for the duration of the block (pid: the process that lives as long as the run)."""
    ug = _lib()
    run = ug.register(label, harness, model=model, effort=effort, source=source, pid=pid) if ug else None
    try:
        yield run
    finally:
        if run:
            run.close()


@contextlib.contextmanager
def agy(label, model, effort='', pid=None):
    """`registered` for an Antigravity (`agy -p`) run: the harness (agy-gemini / agy-claude) and the page's model name come from the model."""
    ug = _lib()
    if ug is None:
        with registered(label, 'agy'):
            yield None
        return
    try:
        import agy_rate
    except ModuleNotFoundError as e:
        if e.name != 'agy_rate':
            raise
        raise RuntimeError('Antigravity (agy) was removed on this machine: ~/.claude/lib/agy_rate.py no longer exists, so agy() cannot run') from e
    group = agy_rate.group_of(model)
    harness = group.replace('antigravity-', 'agy-') if group else 'agy'
    name, tier = agy_rate.display_model(model, effort)
    with registered(label, harness, model=name, effort=tier, source=harness if group else '', pid=pid) as run:
        yield run
