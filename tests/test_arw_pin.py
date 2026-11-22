"""ARW pin: a checkout is accepted only at the pinned commit with the pinned fixture tree and no local change."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.arw import pin as arw_pin


def git(cwd, *args):
    return subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


class PinTests(unittest.TestCase):
    def test_committed_pin_file_is_well_formed(self):
        pin = arw_pin.load()
        self.assertRegex(pin['commit'], r'^[0-9a-f]{40}$')
        self.assertRegex(pin['fixtureTree'], r'^[0-9a-f]{40}$')

    def test_load_rejects_a_missing_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'pin.json'
            path.write_text(json.dumps({'commit': 'a', 'origin': 'x'}))
            with self.assertRaisesRegex(ValueError, 'fixtureTree'):
                arw_pin.load(path)

    def test_ensure_clones_verifies_and_rejects_drift(self):
        # One real-git case: the clone, tree check and drift detection only exist in git itself.
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = tmp / 'arw'
            fixtures = source / arw_pin.FIXTURES
            fixtures.mkdir(parents=True)
            (fixtures / 'a.txt').write_text('a')
            git(source, 'init', '-q')
            git(source, 'add', '.')
            git(source, 'commit', '-q', '-m', 'x')
            pin = {'commit': git(source, 'rev-parse', 'HEAD'), 'fixtureTree': git(source, 'rev-parse', 'HEAD:' + arw_pin.FIXTURES),
                   'origin': 'unused'}
            (tmp / 'pin.json').write_text(json.dumps(pin))
            checkout = arw_pin.ensure(tmp / 'out', tmp / 'pin.json', source)
            self.assertEqual(checkout, tmp / 'out' / pin['commit'])
            self.assertEqual(arw_pin.ensure(tmp / 'out', tmp / 'pin.json', source), checkout)
            (checkout / 'dirty.txt').write_text('x')
            with self.assertRaisesRegex(ValueError, 'local changes'):
                arw_pin.verify(checkout, pin)
            with self.assertRaisesRegex(ValueError, 'does not match the pin'):
                arw_pin.ensure(tmp / 'out', tmp / 'pin.json', source)
            with self.assertRaisesRegex(ValueError, 'fixture tree'):
                arw_pin.verify(checkout, dict(pin, fixtureTree='0' * 40))


if __name__ == '__main__':unittest.main()
