"""Tests for security features — redaction and config file permissions."""

import os
import unittest
import tempfile
import json
from unittest.mock import patch
from src.ailog.ai_client import _redact_secrets
from src.ailog.config_manager import ConfigManager


class TestRedactSecrets(unittest.TestCase):
    """Test _redact_secrets function."""

    def test_openai_key(self):
        text = "Error with key sk-abc123def456ghi789jkl012mno345pqr678"
        result = _redact_secrets(text)
        self.assertNotIn('sk-abc123', result)
        self.assertIn('[REDACTED]', result)

    def test_anthropic_key(self):
        text = "Using key sk-ant-api03-abcdefghijklmnopqrstuvwxyz"
        result = _redact_secrets(text)
        self.assertNotIn('sk-ant-', result)
        self.assertIn('[REDACTED]', result)

    def test_github_pat(self):
        text = "token=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmn"
        result = _redact_secrets(text)
        self.assertNotIn('ghp_', result)

    def test_api_key_assignment(self):
        text = "api_key=my-super-secret-key-12345"
        result = _redact_secrets(text)
        self.assertNotIn('my-super-secret', result)
        self.assertIn('[REDACTED]', result)

    def test_password_in_log(self):
        text = "password=hunter2"
        result = _redact_secrets(text)
        self.assertNotIn('hunter2', result)

    def test_normal_text_unchanged(self):
        text = "E AndroidRuntime: java.lang.NullPointerException at line 42"
        result = _redact_secrets(text)
        self.assertEqual(result, text)

    def test_google_api_key(self):
        text = "key AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q"
        result = _redact_secrets(text)
        self.assertNotIn('AIzaSy', result)


class TestConfigFilePermissions(unittest.TestCase):
    """Test that config file gets restricted permissions."""

    def test_config_file_has_600_permissions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, 'config.json')
            with patch.object(ConfigManager, '__init__', lambda self: None):
                cm = ConfigManager.__new__(ConfigManager)
                cm.config_path = config_path
                cm._config = {"provider": "ollama"}
                cm._save()

            mode = oct(os.stat(config_path).st_mode & 0o777)
            self.assertEqual(mode, '0o600')


if __name__ == '__main__':
    unittest.main()
