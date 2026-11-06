"""Installation credentials are rendered from the project private file only."""
from pathlib import Path
import http.client
import json
import sys
import tempfile
import tomllib
import unittest
import urllib.error
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.ops import deploy
from tools.ops.deploy import deployment_files, obsolete_files, private_bytes


class Reply:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, *args):
        return json.dumps(self.body).encode()


def http_error(code):
    return urllib.error.HTTPError('http://x/', code, 'err', {}, None)


def refused():
    return urllib.error.URLError(ConnectionRefusedError(111, 'refused'))


class FrontendScript:
    """A scripted frontend: per path a list of replies (a reply that is an exception is raised); the last one repeats."""

    def __init__(self, script):
        self.script, self.calls = {path: list(replies) for path, replies in script.items()}, []

    def open(self, request, timeout):
        path = request.full_url.removeprefix('http://frontend')
        self.calls.append(path)
        replies = self.script[path]
        reply = replies.pop(0) if len(replies) > 1 else replies[0]
        if isinstance(reply, BaseException):
            raise reply
        return Reply(reply)


class FrontendTests(unittest.TestCase):
    def frontend(self, script):
        frontend = deploy.Frontend('http://frontend')
        frontend.opener = FrontendScript(script)
        return frontend

    def test_only_connection_failures_mean_not_reachable(self):
        for error, expected in ((http_error(503), True), (http_error(401), True), (ConnectionResetError(), True),
                                (ValueError(), True), (refused(), False),
                                (TimeoutError(), True), (http.client.BadStatusLine('x'), True),
                                (http.client.IncompleteRead(b''), True),
                                (urllib.error.URLError(TimeoutError()), False),
                                (urllib.error.URLError(OSError(101, 'unreachable')), False)):
            self.assertEqual(self.frontend({'/health': [error]}).reachable(), expected, msg=repr(error))
        self.assertTrue(self.frontend({'/health': [{'ok': True}]}).reachable())

    def test_health_error_status_still_takes_the_lease_path_and_a_held_lease_aborts(self):
        frontend = self.frontend({'/health': [http_error(503)], '/lease/acquire': [http_error(409)]})
        with patch.object(deploy, 'Frontend', lambda base: frontend), patch.object(deploy.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'lease is held'):
                with deploy.maintenance('http://frontend'):
                    self.fail('files must not change while the lease is held by someone else')
        self.assertEqual(frontend.opener.calls, ['/health', '/lease/acquire'])
        run.assert_not_called()

    def test_health_error_status_with_a_free_lease_stops_through_the_lease(self):
        frontend = self.frontend({'/health': [http_error(503), http_error(503), refused(), {'ok': True}],
                                  '/lease/acquire': [{'key': 'k'}], '/model/status': [{'status': 'stopped'}],
                                  '/admin/shutdown': [{}]})
        with patch.object(deploy, 'Frontend', lambda base: frontend), patch.object(deploy.time, 'sleep'), \
                patch.object(deploy.subprocess, 'run') as run:
            run.return_value.returncode = 0
            with deploy.maintenance('http://frontend'):
                pass
        self.assertEqual(frontend.opener.calls[1:5], ['/lease/acquire', '/model/status', '/admin/shutdown', '/health'])
        run.assert_called_once()


class DeployTests(unittest.TestCase):
    def test_private_file_carries_only_the_brave_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'project.private.toml').write_text('[brave]\napi_key = "k\\"1"\n[hosts.x]\ninstallation_path = "C:\\\\x"\n')
            self.assertEqual(tomllib.loads(private_bytes(root).decode()), {'brave': {'api_key': 'k"1'}})
            (root/'project.private.toml').write_text('[hosts.x]\n')
            with self.assertRaisesRegex(ValueError, 'api_key'):
                private_bytes(root)

    def test_private_file_is_never_a_public_deployment_file(self):
        self.assertNotIn('installation.private.toml', deployment_files({'models': ['IQ3_XXS']}))

    def test_the_caller_manual_deploys_as_a_readme_and_a_detailed_manual_in_both_languages(self):
        files = deployment_files({'models': ['IQ3_XXS']})
        manual = {t: files[t] for t in ('README.md', 'README.zh-CN.md', 'docs/manuals/caller-manual.md', 'docs/manuals/caller-manual.zh-CN.md')}
        self.assertEqual(manual, deploy.MANUAL_FILES)
        self.assertEqual(len(set(manual.values())), 4)

    def test_installation_local_config_is_never_replaced_or_removed(self):
        host = {'models': ['IQ3_XXS']}
        self.assertNotIn('config.local.json', deployment_files(host))
        self.assertNotIn('config.local.json', obsolete_files(host))
        self.assertNotIn('config.local.json', deploy.OBSOLETE_TREES)

    def test_only_the_served_models_prebuilt_is_deployed_and_the_others_are_removed(self):
        host = {'models': ['IQ3_XXS']}
        files = deployment_files(host)
        self.assertEqual(files['config/iq3_xxs-prebuilt.json'], 'config/templates/iq3_xxs-prebuilt.json')
        self.assertEqual(sorted(t for t in files if t.endswith('-prebuilt.json')), ['config/iq3_xxs-prebuilt.json'])
        self.assertNotIn('config/maintenance-baseline.json', files)
        obsolete = obsolete_files(host)
        # backed up, then removed; weights, runtime and data are never listed
        self.assertTrue({'config/q2_0-prebuilt.json', 'config/iq2_xs-prebuilt.json',
                         'config/maintenance-baseline.json'} <= set(obsolete))
        self.assertFalse(set(obsolete) & set(files))
        self.assertTrue(all(t.startswith(('config/', 'src/', 'maintenance/', 'Run-')) for t in obsolete))

    def test_every_quantization_template_pins_the_mtp_drafter(self):
        # v0.2.10 treats a missing "drafting" as Auto, which swaps to DFlash2 once its drafter file is on the machine
        templates = sorted((Path(__file__).resolve().parents[1]/'config'/'templates').glob('*-prebuilt.json'))
        self.assertEqual(len(templates), 3)
        for template in templates:
            self.assertEqual(json.loads(template.read_text())['drafting'], 'mtp', template.name)


if __name__ == '__main__':
    unittest.main()
