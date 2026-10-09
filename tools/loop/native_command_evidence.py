"""Incremental public native-output lookup, bound to one root thread and digests."""
import hashlib
import json
from pathlib import Path


class NativeCommandEvidence:
    def __init__(self, path, thread_id):
        self.path = Path(path)
        self.thread_id = thread_id
        self.offset = 0
        self.outputs = {}
        self.verified = False

    def refresh(self):
        if self.path.stat().st_size < self.offset:
            raise ValueError('Bound native record shrank')
        with self.path.open('rb') as stream:
            stream.seek(self.offset)
            while True:
                start = stream.tell()
                raw = stream.readline()
                if not raw or not raw.endswith(b'\n'):
                    self.offset = start
                    break
                event = json.loads(raw)
                payload = event.get('payload', {})
                if not self.verified:
                    if event.get('type') != 'session_meta' or payload.get('id') != self.thread_id:
                        raise ValueError('Native record identity differs from the bound root')
                    self.verified = True
                if event.get('type') != 'event_msg' or payload.get('type') != 'item_completed':
                    continue
                if payload.get('thread_id') != self.thread_id:
                    continue
                item = payload.get('item', {})
                if item.get('type') == 'CommandExecution' and isinstance(item.get('aggregated_output'), str):
                    self.outputs[item['id']] = (payload.get('turn_id'), item['aggregated_output'])
        # Only observations need output; do not persist full outputs in guard state.
        if len(self.outputs) > 4096:
            self.outputs = dict(list(self.outputs.items())[-4096:])

    def enrich(self, facts):
        self.refresh()
        result = []
        for fact in facts:
            value = dict(fact)
            found = self.outputs.get(fact.get('itemId'))
            if (found and fact.get('threadId') == self.thread_id and found[0] == fact.get('turnId')
                    and hashlib.sha256(found[1].encode()).hexdigest() == fact.get('outputDigest')):
                value['output'] = found[1]
            result.append(value)
        return result
