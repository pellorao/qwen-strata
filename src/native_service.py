"""Run the unchanged upstream server with ownership checks on every HTTP operation."""
import hmac
import os
from pathlib import Path
import re
import sys

from service_access import authorize, bearer


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


def guarded_handler(base, access_file, maintenance_key, startup=None):
    class Guarded(base):
        def _json(self, status, value, *args, **kwargs):
            if startup is not None and status == 200 and self.command == 'GET' and self.path.split('?', 1)[0] == '/health':
                value = dict(value, startup_instructions=startup)
            return super()._json(status, value, *args, **kwargs)

        def _ownership_allowed(self):
            key = bearer(self.headers)
            path = self.path.split('?', 1)[0].rstrip('/')
            maintenance = path in ('/health', '/unload') and self.command in ('GET', 'POST') and bool(key) and hmac.compare_digest(key, maintenance_key)
            if maintenance or authorize(access_file, key):
                return True
            self.close_connection = True
            self._json(403, {'error': {'message': 'A valid ownership key is required.'}})
            return False

        def do_GET(self):
            if self._ownership_allowed():
                super().do_GET()

        def do_POST(self):
            if self._ownership_allowed():
                super().do_POST()

        def do_OPTIONS(self):
            if self._ownership_allowed():
                super().do_OPTIONS()

    return Guarded


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
    loop_selection = os.environ.get('QWEN_PROJECT_LOOP_PREVENTION', '1')
    if loop_selection not in ('0', '1'):
        raise ValueError('Invalid process loop prevention instruction selection.')
    instructions, metadata = load_startup_instructions(
        root, enabled=enabled, include_loop_prevention=loop_selection == '1')
    if enabled:
        install_startup_instructions(server.Service, instructions)
    access_file = os.environ['STRATA_ACCESS_FILE']
    maintenance_key = os.environ['STRATA_MAINTENANCE_KEY']
    original = server.make_handler
    server.make_handler = lambda svc: guarded_handler(original(svc), access_file, maintenance_key, metadata)
    return server.main()


if __name__ == '__main__':
    raise SystemExit(main())
