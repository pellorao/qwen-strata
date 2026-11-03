import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tools.reviewer import freeze_arw_source as freeze


class FreezeArchiveTests(unittest.TestCase):
    def snapshot(self, source, destination):
        def git(command, cwd, **kwargs):
            if command[1] == 'rev-parse':
                return 'a' * 40 + '\n'
            if command[1] == 'ls-files':
                return b'lib/a.mjs\0package.json\0'
            return b''
        with mock.patch.object(freeze.subprocess, 'check_output', side_effect=git):
            return freeze.freeze(source, destination)

    def test_equal_content_gives_equal_archive_bytes_whenever_it_is_frozen(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'src'
            (source / 'lib').mkdir(parents=True)
            (source / 'lib/a.mjs').write_text('export const a = 1;\n')
            (source / 'package.json').write_text('{}\n')
            first = self.snapshot(source, Path(tmp) / 'one')
            time.sleep(1.1)  # the gzip header carries a second-resolution time unless it is pinned
            second = self.snapshot(source, Path(tmp) / 'two')
            self.assertEqual(first['snapshot'], second['snapshot'])


class TierKeyTests(unittest.TestCase):
    def test_spellings_of_one_k_are_one_tier(self):
        self.assertEqual({freeze.tier_key(k) for k in (4, 4.0, '4')}, {'4'})
        self.assertEqual(freeze.tier_key(0.25), '0.25')
        self.assertEqual(freeze.tier_key(1.0), freeze.tier_key(1))


if __name__ == '__main__':
    unittest.main()
