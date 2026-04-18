"""Tests for build_wrapper module — command resolution and batch logic."""

import unittest
from unittest.mock import patch, MagicMock
from src.ailog.build_wrapper import BuildWrapper


class MockConfig:
    """Minimal config for testing."""
    provider = 'ollama'
    dry_run = False
    show_tokens = False

    def get(self, key, default=None):
        defaults = {
            'provider': 'ollama',
            'ollama_model': 'test-model',
            'ollama_url': 'http://localhost:11434',
            'timeout': 30,
            'system_prompt': '',
            'max_ai_calls': 5,
            'batch_interval': 5,
        }
        return defaults.get(key, default)

    def get_api_key(self):
        return ''

    def get_model(self):
        return 'test-model'

    def get_base_url(self):
        return 'http://localhost:11434'


class TestResolveBuildCmd(unittest.TestCase):
    """Test _resolve_build_cmd method."""

    def _make_wrapper(self):
        display = MagicMock()
        config = MockConfig()
        return BuildWrapper(config, display)

    @patch('shutil.which', return_value='/usr/bin/m')
    def test_detects_m_command(self, mock_which):
        wrapper = self._make_wrapper()
        cmd = wrapper._resolve_build_cmd([])
        self.assertEqual(cmd[0], 'm')

    @patch('shutil.which', side_effect=lambda x: '/usr/bin/make' if x == 'make' else None)
    def test_falls_back_to_make(self, mock_which):
        wrapper = self._make_wrapper()
        cmd = wrapper._resolve_build_cmd([])
        self.assertEqual(cmd[0], 'make')

    @patch('shutil.which', return_value=None)
    def test_returns_none_when_no_build_cmd(self, mock_which):
        wrapper = self._make_wrapper()
        cmd = wrapper._resolve_build_cmd([])
        self.assertIsNone(cmd)

    @patch('shutil.which', return_value='/usr/bin/m')
    def test_passes_extra_args(self, mock_which):
        wrapper = self._make_wrapper()
        cmd = wrapper._resolve_build_cmd(['-j16', 'framework'])
        self.assertIn('-j16', cmd)
        self.assertIn('framework', cmd)


if __name__ == '__main__':
    unittest.main()
