"""Tests for config_manager module."""

import unittest
import sys
import os
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ailog.config_manager import ConfigManager


class TempConfigMixin:
    """Mixin that patches ConfigManager to use a temporary directory."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig_expanduser = os.path.expanduser
        # Redirect ~/.config/ailog to tmpdir
        os.path.expanduser = lambda p: p.replace("~", self.tmpdir)

    def tearDown(self):
        os.path.expanduser = self._orig_expanduser
        shutil.rmtree(self.tmpdir, ignore_errors=True)


class TestDefaults(TempConfigMixin, unittest.TestCase):
    def test_default_provider(self):
        cm = ConfigManager()
        self.assertEqual(cm.provider, "ollama")

    def test_default_model(self):
        cm = ConfigManager()
        self.assertEqual(cm.get_model(), "qwen2.5-coder:3b")

    def test_default_timeout(self):
        cm = ConfigManager()
        self.assertEqual(cm.get('timeout', 30), 30)

    def test_default_batch_interval(self):
        cm = ConfigManager()
        self.assertEqual(cm.get('batch_interval', 5), 5)

    def test_default_system_prompt_empty(self):
        cm = ConfigManager()
        self.assertEqual(cm.get('system_prompt', ''), '')


class TestGetSetRoundTrip(TempConfigMixin, unittest.TestCase):
    def test_set_and_get(self):
        cm = ConfigManager()
        cm.set('noise_level', 'high')
        self.assertEqual(cm.get('noise_level'), 'high')

    def test_persists_across_instances(self):
        cm1 = ConfigManager()
        cm1.set('noise_level', 'high')

        cm2 = ConfigManager()
        self.assertEqual(cm2.get('noise_level'), 'high')

    def test_set_model_round_trip(self):
        cm = ConfigManager()
        cm.set_model("llama3:8b")
        self.assertEqual(cm.get_model(), "llama3:8b")

    def test_set_base_url_round_trip(self):
        cm = ConfigManager()
        cm.set_base_url("http://myserver:11434")
        self.assertEqual(cm.get_base_url(), "http://myserver:11434")


class TestProviderSwitching(TempConfigMixin, unittest.TestCase):
    def test_switch_to_openai(self):
        cm = ConfigManager()
        cm.set_provider("openai")
        self.assertEqual(cm.provider, "openai")
        self.assertEqual(cm.get_model(), "gpt-4o-mini")

    def test_switch_to_anthropic(self):
        cm = ConfigManager()
        cm.set_provider("anthropic")
        self.assertEqual(cm.provider, "anthropic")
        self.assertEqual(cm.get_model(), "claude-sonnet-4-20250514")

    def test_invalid_provider_raises(self):
        cm = ConfigManager()
        with self.assertRaises(ValueError):
            cm.set_provider("invalid")

    def test_model_per_provider(self):
        cm = ConfigManager()
        cm.set_model("custom-ollama-model")
        cm.set_provider("openai")
        cm.set_model("custom-openai-model")

        # Switch back to ollama, model should be what we set
        cm.set_provider("ollama")
        self.assertEqual(cm.get_model(), "custom-ollama-model")

        cm.set_provider("openai")
        self.assertEqual(cm.get_model(), "custom-openai-model")


class TestReset(TempConfigMixin, unittest.TestCase):
    def test_reset_restores_defaults(self):
        cm = ConfigManager()
        cm.set_provider("openai")
        cm.set('noise_level', 'high')
        cm.reset()
        self.assertEqual(cm.provider, "ollama")
        self.assertEqual(cm.get('noise_level'), 'medium')


class TestValidation(TempConfigMixin, unittest.TestCase):
    def test_empty_model_rejected(self):
        cm = ConfigManager()
        with self.assertRaises(ValueError) as ctx:
            cm.set_model("")
        self.assertIn("cannot be empty", str(ctx.exception))

    def test_whitespace_model_rejected(self):
        cm = ConfigManager()
        with self.assertRaises(ValueError):
            cm.set_model("   ")

    def test_empty_url_rejected(self):
        cm = ConfigManager()
        with self.assertRaises(ValueError):
            cm.set_base_url("")

    def test_non_http_url_rejected(self):
        cm = ConfigManager()
        with self.assertRaises(ValueError) as ctx:
            cm.set_base_url("ftp://example.com")
        self.assertIn("http", str(ctx.exception))

    def test_no_hostname_rejected(self):
        cm = ConfigManager()
        with self.assertRaises(ValueError):
            cm.set_base_url("http://")

    def test_plain_string_rejected(self):
        cm = ConfigManager()
        with self.assertRaises(ValueError):
            cm.set_base_url("notaurl")

    def test_valid_url_accepted(self):
        cm = ConfigManager()
        cm.set_base_url("https://api.example.com/v1")
        self.assertEqual(cm.get_base_url(), "https://api.example.com/v1")


class TestApiKey(TempConfigMixin, unittest.TestCase):
    def test_ollama_no_key_needed(self):
        cm = ConfigManager()
        self.assertEqual(cm.get_api_key(), "")

    def test_openai_key_from_config(self):
        cm = ConfigManager()
        cm.set_provider("openai")
        cm.set_api_key("sk-test123")
        self.assertEqual(cm.get_api_key(), "sk-test123")

    def test_env_var_takes_priority(self):
        cm = ConfigManager()
        cm.set_provider("openai")
        cm.set_api_key("sk-from-config")
        os.environ["OPENAI_API_KEY"] = "sk-from-env"
        try:
            self.assertEqual(cm.get_api_key(), "sk-from-env")
        finally:
            del os.environ["OPENAI_API_KEY"]


class TestCorruptConfig(TempConfigMixin, unittest.TestCase):
    def test_corrupt_json_recovers(self):
        cm = ConfigManager()
        # Write garbage to config file
        with open(cm.config_path, 'w') as f:
            f.write("{not valid json!!!")
        cm2 = ConfigManager()
        self.assertEqual(cm2.provider, "ollama")


if __name__ == '__main__':
    unittest.main()
