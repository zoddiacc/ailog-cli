"""Tests for ai_client module."""

import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ailog.ai_client import AIClient


class MockConfig:
    """Minimal config object for testing AIClient without real config files."""

    def __init__(self, **kwargs):
        self._data = {
            'provider': 'ollama',
            'api_key': '',
            'model': 'test-model',
            'base_url': 'http://localhost:11434',
            'timeout': 10,
            'system_prompt': '',
        }
        self._data.update(kwargs)
        self.dry_run = kwargs.get('dry_run', False)
        self.show_tokens = kwargs.get('show_tokens', False)

    @property
    def provider(self):
        return self._data['provider']

    def get_api_key(self):
        return self._data['api_key']

    def get_model(self):
        return self._data['model']

    def get_base_url(self):
        return self._data['base_url']

    def get(self, key, default=None):
        return self._data.get(key, default)


class TestParseOpenAIResponse(unittest.TestCase):
    def setUp(self):
        self.client = AIClient(MockConfig())

    def test_valid_response(self):
        result = {
            "choices": [
                {"message": {"content": "Hello, world!"}}
            ]
        }
        self.assertEqual(self.client._parse_openai_response(result), "Hello, world!")

    def test_empty_choices(self):
        result = {"choices": []}
        # Should return string repr as fallback
        parsed = self.client._parse_openai_response(result)
        self.assertIsInstance(parsed, str)

    def test_missing_choices_key(self):
        result = {"error": "something went wrong"}
        parsed = self.client._parse_openai_response(result)
        self.assertIsInstance(parsed, str)

    def test_malformed_message(self):
        result = {"choices": [{"message": {}}]}
        parsed = self.client._parse_openai_response(result)
        self.assertIsInstance(parsed, str)


class TestParseAnthropicResponse(unittest.TestCase):
    def setUp(self):
        self.client = AIClient(MockConfig())

    def test_valid_response(self):
        result = {
            "content": [
                {"type": "text", "text": "Analysis complete."}
            ]
        }
        self.assertEqual(self.client._parse_anthropic_response(result), "Analysis complete.")

    def test_empty_content(self):
        result = {"content": []}
        parsed = self.client._parse_anthropic_response(result)
        self.assertIsInstance(parsed, str)

    def test_missing_content_key(self):
        result = {"error": {"message": "bad request"}}
        parsed = self.client._parse_anthropic_response(result)
        self.assertIsInstance(parsed, str)

    def test_missing_text_field(self):
        result = {"content": [{"type": "text"}]}
        parsed = self.client._parse_anthropic_response(result)
        self.assertIsInstance(parsed, str)


class TestEstimateTokens(unittest.TestCase):
    def test_short_text(self):
        tokens = AIClient._estimate_tokens("hello")
        self.assertGreaterEqual(tokens, 1)

    def test_longer_text(self):
        text = "a" * 400
        tokens = AIClient._estimate_tokens(text)
        self.assertEqual(tokens, 100)

    def test_empty_text(self):
        tokens = AIClient._estimate_tokens("")
        self.assertEqual(tokens, 1)  # minimum 1

    def test_proportional(self):
        short = AIClient._estimate_tokens("hello world")
        long = AIClient._estimate_tokens("hello world " * 100)
        self.assertGreater(long, short)


class TestDryRun(unittest.TestCase):
    def test_dry_run_returns_string(self):
        config = MockConfig(dry_run=True)
        client = AIClient(config)
        result = client.chat("system prompt", "user message")
        self.assertIsInstance(result, str)
        self.assertIn("[DRY RUN]", result)
        self.assertIn("ollama", result)
        self.assertIn("test-model", result)

    def test_dry_run_no_http_call(self):
        config = MockConfig(dry_run=True, base_url="http://nonexistent:99999")
        client = AIClient(config)
        # Should NOT raise — no HTTP call made
        result = client.chat("system", "user")
        self.assertIn("[DRY RUN]", result)

    def test_dry_run_shows_token_estimate(self):
        config = MockConfig(dry_run=True)
        client = AIClient(config)
        result = client.chat("sys", "a" * 400)
        self.assertIn("Estimated input tokens", result)


class TestCustomSystemPrompt(unittest.TestCase):
    def test_default_system_prompt(self):
        config = MockConfig()
        client = AIClient(config)
        self.assertIn("Android", client._system_prompt)

    def test_custom_system_prompt(self):
        config = MockConfig(system_prompt="You are a custom assistant.")
        client = AIClient(config)
        self.assertEqual(client._system_prompt, "You are a custom assistant.")

    def test_empty_system_prompt_uses_default(self):
        config = MockConfig(system_prompt="")
        client = AIClient(config)
        self.assertIn("Android", client._system_prompt)


class TestTimeout(unittest.TestCase):
    def test_timeout_from_config(self):
        config = MockConfig(timeout=60)
        client = AIClient(config)
        self.assertEqual(client.timeout, 60)

    def test_default_timeout(self):
        config = MockConfig()
        del config._data['timeout']
        client = AIClient(config)
        self.assertEqual(client.timeout, 30)


if __name__ == '__main__':
    unittest.main()
