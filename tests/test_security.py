"""Tests for security features — redaction and config file permissions."""

import os
import unittest
import tempfile
from unittest.mock import patch
from src.ailog.ai_client import _redact_secrets, AIClient
from src.ailog.config_manager import ConfigManager
from src.ailog.display import sanitize_terminal


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
        # Fake key assembled at runtime so secret scanners don't flag it
        fake_key = "AIzaSy" + "A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q"
        text = "key " + fake_key
        result = _redact_secrets(text)
        self.assertNotIn('AIzaSy', result)


class TestSanitizeTerminal(unittest.TestCase):
    """Untrusted log/AI text must not carry terminal escape sequences."""

    def test_strips_escape_sequences(self):
        # Screen-clear + window-title injection from a malicious log line
        payload = "normal\x1b[2J\x1b]0;OWNED\x07text"
        result = sanitize_terminal(payload)
        self.assertNotIn('\x1b', result)
        self.assertNotIn('\x07', result)
        self.assertEqual(result, "normal[2J]0;OWNEDtext")

    def test_strips_c1_and_del(self):
        self.assertNotIn('\x9b', sanitize_terminal("a\x9bb"))
        self.assertNotIn('\x7f', sanitize_terminal("a\x7fb"))

    def test_preserves_tab_and_newline(self):
        self.assertEqual(sanitize_terminal("a\tb\nc"), "a\tb\nc")

    def test_plain_text_unchanged(self):
        text = "E AndroidRuntime: java.lang.NullPointerException"
        self.assertEqual(sanitize_terminal(text), text)


class _RedactConfig:
    """Minimal config to exercise AIClient redaction resolution."""
    def __init__(self, provider, redact=None):
        self.provider = provider
        self.redact = redact

    def get_api_key(self):
        return 'x'

    def get_model(self):
        return 'm'

    def get_base_url(self):
        return 'http://localhost:11434'

    def get(self, key, default=None):
        return default


class TestRedactionDefaults(unittest.TestCase):
    """Redaction must default ON for remote providers, OFF for local Ollama."""

    def test_default_on_for_cloud(self):
        self.assertTrue(AIClient(_RedactConfig('openai')).redact)
        self.assertTrue(AIClient(_RedactConfig('anthropic')).redact)

    def test_default_off_for_ollama(self):
        self.assertFalse(AIClient(_RedactConfig('ollama')).redact)

    def test_explicit_override_wins(self):
        self.assertFalse(AIClient(_RedactConfig('openai', redact=False)).redact)
        self.assertTrue(AIClient(_RedactConfig('ollama', redact=True)).redact)


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
