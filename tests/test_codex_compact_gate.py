"""The Codex compaction gate (plan v2 F7/F8): mock behaviour and the ladder."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request

from tools.safety import codex_compact_gate as gate

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def post(port, body):
    request = urllib.request.Request(f'http://127.0.0.1:{port}/v1/responses', json.dumps(body).encode(),
                                     {'Content-Type': 'application/json'})
    with OPENER.open(request, timeout=10) as reply:
        return [json.loads(line[6:]) for line in reply.read().decode().splitlines() if line.startswith('data: ')]


class MockTests(unittest.TestCase):
    def test_claims_follow_the_ladder_and_a_compaction_request_is_recognised(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = gate.ThreadingHTTPServer(('127.0.0.1', 0), gate.Mock)
            server.folder, server.log, server.ladder, server.step = Path(tmp), [], [1000, 2000], 0
            threading.Thread(target=server.serve_forever, daemon=True).start()
            tools = [{'type': 'function', 'name': 'shell_command', 'parameters': {}}]
            port = server.server_port

            def usage(events):
                return events[-1]['response']['usage']['total_tokens']
            try:
                first = post(port, {'model': 'm', 'tools': tools, 'input': [], 'max_output_tokens': 7})
                compact = post(port, {'model': 'm', 'tools': tools, 'input': [{'content': [{'text': gate.COMPACT_MARKER}]}]})
                second = post(port, {'model': 'm', 'tools': tools, 'input': []})
                last = post(port, {'model': 'm', 'tools': tools, 'input': []})
            finally:
                server.shutdown()
                server.server_close()
        self.assertEqual([usage(x) for x in (first, compact, second, last)], [1000, gate.SUMMARY_CLAIM, 2000, 2000])
        self.assertEqual([e['compaction'] for e in server.log], [False, True, False, False])
        self.assertEqual(server.log[0]['max_output_tokens'], 7)
        self.assertEqual(first[-2]['item']['name'], 'shell_command')
        self.assertEqual(last[-2]['item']['type'], 'message')

    def test_strata_ladder_straddles_the_limit(self):
        ladder = gate.strata_ladder({'context_window': 206584, 'auto_compact_token_limit': 150000})
        self.assertEqual(ladder, [75000, 149000, 151000, 160000])


if __name__ == '__main__':
    unittest.main()
