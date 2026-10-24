"""The offline rebuild finds its installation and engine from what is actually installed."""
import json
from pathlib import Path
import tempfile
import unittest

from tools.ops.install_offline import installation, installed_engine


class InstallOfflineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'qwen-3.8-flash-next'
        self.venv = self.root / 'runtime/Strata/.venv'
        self.venv.mkdir(parents=True)
        (self.root / 'config').mkdir()

    def release(self, **value):
        (self.root / 'config/installed-release.json').write_text(json.dumps(value), encoding='utf-8')

    def engine(self, version, exe=True):
        engine = self.root / 'runtime/Strata/engine'
        engine.mkdir(exist_ok=True)
        (engine / 'BUILD.json').write_text(json.dumps({'version': version, 'archs': [86, 89]}), encoding='utf-8')
        if exe:
            (engine / 'strata.exe').write_bytes(b'')
        return engine

    def test_installation_is_where_the_venv_lives(self):
        self.release(version='0.2.4', engine_version='0.1.48')
        self.assertEqual(installation(self.venv), self.root.resolve())
        with self.assertRaisesRegex(ValueError, 'runtime/Strata/.venv'):
            installation(self.root / 'runtime')
        (self.root / 'config/installed-release.json').unlink()
        with self.assertRaisesRegex(ValueError, 'installed-release.json'):
            installation(self.venv)

    def test_engine_version_comes_from_the_release_record_not_the_tag(self):
        # 0.2.4 ships engine 0.1.48: the old downloads/engine-v0.2.4 folder never existed.
        self.release(version='0.2.4', engine_version='0.1.48')
        engine = self.engine('0.1.48')
        self.assertEqual(installed_engine(self.root), engine)
        self.engine('0.1.47')
        with self.assertRaisesRegex(ValueError, 'not the release engine 0.1.48'):
            installed_engine(self.root)

    def test_pre_020_record_uses_the_release_version(self):
        self.release(version='0.1.45')
        engine = self.engine('0.1.45')
        self.assertEqual(installed_engine(self.root), engine)

    def test_missing_engine_is_refused(self):
        self.release(version='0.2.4', engine_version='0.1.48')
        with self.assertRaisesRegex(ValueError, 'No installed engine'):
            installed_engine(self.root)
        self.engine('0.1.48', exe=False)
        with self.assertRaisesRegex(ValueError, 'No installed engine'):
            installed_engine(self.root)


if __name__ == '__main__':
    unittest.main()
