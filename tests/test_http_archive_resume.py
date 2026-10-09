import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.reviewer.review_continuations import HttpArchive


class HttpArchiveResumeTests(unittest.TestCase):
    def test_resume_preserves_prior_archive_and_collects_new_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            db = folder / 'logs.sqlite'
            with sqlite3.connect(db) as connection:
                connection.execute('CREATE TABLE logs (id INTEGER PRIMARY KEY, ts INTEGER, ts_nanos INTEGER, level TEXT, target TEXT, feedback_log_body TEXT, thread_id TEXT, process_uuid TEXT)')
            original = HttpArchive(db, folder)
            with sqlite3.connect(db) as connection:
                connection.execute('INSERT INTO logs VALUES (1,1,0,?,?,?, ?, ?)', ('INFO', 'codex_http_client::client', 'Authorization: Bearer secret_value', 'first', 'process'))
            original.stop.set()
            original.run()
            old_bytes = original.archive_path.read_bytes()
            old_sha = hashlib.sha256(old_bytes).hexdigest()
            self.assertNotIn(b'secret_value', old_bytes)
            resumed = HttpArchive(db, folder)
            with sqlite3.connect(db) as connection:
                connection.execute('INSERT INTO logs VALUES (2,2,0,?,?,?,?,?)', ('INFO', 'codex_http_client::client', 'new request', 'second', 'process'))
            resumed.stop.set()
            resumed.run()
            self.assertNotEqual(original.archive_path, resumed.archive_path)
            self.assertEqual(hashlib.sha256(original.archive_path.read_bytes()).hexdigest(), old_sha)
            rows = [json.loads(line) for line in resumed.archive_path.read_text().splitlines()]
            self.assertEqual([row['id'] for row in rows], [2])
            status = json.loads((folder / 'http-archive-status.json').read_text())
            self.assertEqual(status['archive_file'], resumed.archive_path.name)
            self.assertEqual(status['last_id'], 2)
            self.assertIsNone(status['error'])


if __name__ == '__main__':
    unittest.main()
