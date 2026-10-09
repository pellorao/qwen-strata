"""Private host settings use UTF-8 independently of the Windows locale."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.ops.remote_windows import host_configuration, connection_environment


FIXTURE = """# 主机配置：密码仅为测试数据，不是实际凭据。
[hosts.test]
transport = 'ssh-windows'
ip = '192.0.2.1'
installation_path = 'C:\\模型\\Strata'
[hosts.test.ssh]
port = 2222
username = 'test-user'
password = 'synthetic-password'
[hosts.test.service]
listen_port = 8000
access_port = 28000
model_port = 8100
"""


class HostEncodingTests(unittest.TestCase):
    def test_key_authentication_does_not_require_or_recreate_password(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'hosts.private.toml'
            text = FIXTURE.replace("password = 'synthetic-password'", "identity_file = 'C:\\Users\\test\\.ssh\\id_rsa'")
            path.write_text(text, encoding='utf-8')
            host = host_configuration(path, 'test')
            settings = connection_environment(path, 'test')
            self.assertNotIn('password', host['ssh'])
            self.assertNotIn('STRATA_REMOTE_PASSWORD', settings)
            self.assertEqual(settings['STRATA_REMOTE_IDENTITY_FILE'], 'C:\\Users\\test\\.ssh\\id_rsa')

    def test_optional_password_keeps_type_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'hosts.private.toml'
            path.write_text(FIXTURE.replace("password = 'synthetic-password'", 'password = 123'), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'SSH fields must be strings'):
                host_configuration(path, 'test')

    def test_utf8_chinese_comments_and_path_do_not_use_locale_encoding(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'hosts.private.toml'
            path.write_bytes(FIXTURE.encode('utf-8'))
            result = host_configuration(path, 'test')
            self.assertEqual(result['installation_path'], 'C:\\模型\\Strata')
            self.assertEqual(result['service']['access_port'], 28000)

    def test_utf8_bom_from_windows_editor_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'hosts.private.toml'
            path.write_bytes(FIXTURE.encode('utf-8-sig'))
            self.assertEqual(host_configuration(path, 'test')['ssh']['port'], 2222)

    def test_invalid_encoding_and_toml_do_not_echo_private_content(self):
        for raw in (b'# secret-sentinel \xff', b"[hosts.test]\npassword = 'secret-sentinel"):
            with self.subTest(raw_type='encoding' if b'\xff' in raw else 'toml'):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / 'hosts.private.toml'
                    path.write_bytes(raw)
                    with self.assertRaises(ValueError) as raised:
                        host_configuration(path, 'test')
                    self.assertEqual(str(raised.exception), 'Invalid private host configuration or unknown host')
                    self.assertIsNone(raised.exception.__cause__)
                    self.assertTrue(raised.exception.__suppress_context__)


if __name__ == '__main__':
    unittest.main()
