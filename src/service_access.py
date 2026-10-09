"""Persistent caller ownership, independent of the model process lifetime."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import tempfile
import threading


class AccessError(RuntimeError):
    def __init__(self, message, status=403):
        super().__init__(message)
        self.status = status


def token_digest(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, mode='w', encoding='utf-8', delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(value, stream)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def authorize(path, token):
    try:
        state = json.loads(Path(path).read_text(encoding='utf-8'))
        return bool(token) and state['phase'] == 'held' and hmac.compare_digest(
            token_digest(token), state['key_sha256'])
    except (OSError, ValueError, KeyError, TypeError):
        return False


def bearer(headers):
    value = headers.get('Authorization', '')
    return value[7:].strip() if value.lower().startswith('bearer ') else headers.get('x-api-key', '')


class Ownership:
    """One broker is the only state writer. Native HTTP handlers read the same file."""
    def __init__(self, path, backend):
        self.path = Path(path)
        self.backend = backend
        self.lock = threading.RLock()
        if not self.path.exists():
            self._rotate('free')
        else:
            self._state()  # Corruption fails closed; never silently drop an owner.

    def _state(self):
        state = json.loads(self.path.read_text(encoding='utf-8'))
        if state.get('phase') not in ('free', 'held', 'revoking', 'blocked') or not isinstance(state.get('key_sha256'), str):
            raise AccessError('Ownership state is invalid; operator inspection is required.', 503)
        return state

    def _rotate(self, phase):
        self.pending_key = secrets.token_urlsafe(32)
        atomic_json(self.path, {'phase': phase, 'key_sha256': token_digest(self.pending_key)})

    def require(self, key):
        if not authorize(self.path, key):
            raise AccessError('Missing, incorrect or returned ownership key.')

    def available(self):
        with self.lock:
            phase = self._state()['phase']
            return {'ownership': phase, 'available': phase == 'free' and self.backend.stopped()}

    def acquire(self):
        with self.lock:
            state = self._state()
            if state['phase'] == 'held':
                raise AccessError('The model service is owned by another caller.', 409)
            if state['phase'] in ('revoking', 'blocked'):
                # A previous return already authorized cleanup. Grant nothing until it succeeds.
                try:
                    self.backend.stop()
                except Exception as error:
                    raise AccessError('Returned service cleanup has not completed.', 503) from error
            if not self.backend.stopped():
                raise AccessError('The model service must be stopped before issuing a key.', 409)
            if not hasattr(self, 'pending_key') or token_digest(self.pending_key) != state['key_sha256']:
                self._rotate('free')
            key = self.pending_key
            atomic_json(self.path, {'phase': 'held', 'key_sha256': token_digest(key)})
            del self.pending_key
            return {'key': key, 'ownership': 'held'}

    def start(self, key, options):
        with self.lock:
            self.require(key)
            return self.backend.start(options)

    def stop(self, key):
        with self.lock:
            self.require(key)
            return self.backend.stop()

    def status(self, key):
        with self.lock:
            self.require(key)
            return self.backend.status()

    def release(self, key):
        with self.lock:
            self.require(key)
            self._rotate('revoking')  # Revoke before any unload/stop, including failures.
            try:
                result = self.backend.stop()
                if not self.backend.stopped():
                    raise RuntimeError('Model processes remain after stop.')
            except Exception as error:
                state = self._state(); state['phase'] = 'blocked'
                atomic_json(self.path, state)
                raise AccessError('Key revoked; service cleanup failed. No key can be issued yet.', 503) from error
            state = self._state(); state['phase'] = 'free'
            atomic_json(self.path, state)
            return {'ownership': 'free', 'previous_key_revoked': True, 'model_stop': result}
