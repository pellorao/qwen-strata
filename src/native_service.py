"""Run the unchanged upstream server with the installation startup instructions."""
import os
from pathlib import Path
import re
import sys


def install_sampling_trace(engine, emit=None):
    """Observe upstream's exact pipe options without changing their production."""
    original = engine.sampling_keys
    emit = emit or (lambda text: print(text, file=sys.stderr, flush=True))

    def sampling_keys(sampling):
        keys = original(sampling)
        # Numeric pipe options only: no prompt IDs, arbitrary values or secrets.
        visible = [word for word in keys.split()
                   if re.fullmatch(r'[a-z_]+=[+\-0-9.eE]+', word)]
        try:
            emit('[native-sampling-trace] ' + ' '.join(visible))
        except OSError:
            pass  # A diagnostic sink cannot fail a generation.
        return keys

    engine.sampling_keys = staticmethod(sampling_keys)


def health_with_startup(base, startup):
    """Report the startup instructions this process actually loaded on /health."""
    class Handler(base):
        def _json(self, status, value, *args, **kwargs):
            if status == 200 and self.command == 'GET' and self.path.split('?', 1)[0] == '/health':
                value = dict(value, startup_instructions=startup)
            return super()._json(status, value, *args, **kwargs)
    return Handler


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'runtime/Strata'))
    from serve import server
    if os.environ.get('STRATA_BATCH_TRACE'):
        install_sampling_trace(server.StrataEngine)
    from startup_instructions import load_startup_instructions, install_startup_instructions
    selection = os.environ.get('QWEN_PROJECT_STARTUP_INSTRUCTIONS', '1')
    if selection not in ('0', '1'):
        raise ValueError('Invalid process startup instruction selection.')
    enabled = selection == '1'
    loop_selection = os.environ.get('QWEN_PROJECT_LOOP_PREVENTION', '0')
    if loop_selection not in ('0', '1'):
        raise ValueError('Invalid process loop prevention instruction selection.')
    instructions, metadata = load_startup_instructions(
        root, enabled=enabled, include_loop_prevention=loop_selection == '1')
    if enabled:
        install_startup_instructions(server.Service, instructions)
    original = server.make_handler
    server.make_handler = lambda svc: health_with_startup(original(svc), metadata)
    return server.main()


if __name__ == '__main__':
    raise SystemExit(main())
