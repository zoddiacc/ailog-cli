"""Tests for analyzer module — log type detection."""

import unittest
from src.ailog.analyzer import detect_log_type


class TestDetectLogType(unittest.TestCase):
    """Test detect_log_type function."""

    def test_build_filename(self):
        self.assertEqual(detect_log_type('build.log', ''), 'build')
        self.assertEqual(detect_log_type('make_output.txt', ''), 'build')
        self.assertEqual(detect_log_type('compile_errors.log', ''), 'build')
        self.assertEqual(detect_log_type('ninja.log', ''), 'build')

    def test_logcat_filename(self):
        self.assertEqual(detect_log_type('logcat.txt', ''), 'logcat')
        self.assertEqual(detect_log_type('runtime.log', ''), 'logcat')

    def test_logcat_by_content(self):
        """Logcat content has many timestamp patterns."""
        lines = [f"01-15 12:34:{i:02d}.789  1234  1234 I Tag: msg" for i in range(20)]
        content = '\n'.join(lines)
        self.assertEqual(detect_log_type('unknown.txt', content), 'logcat')

    def test_build_by_content_fallback(self):
        """No timestamps and unknown filename defaults to build."""
        content = "error: undefined reference to 'foo'\nld: fatal error\n" * 5
        self.assertEqual(detect_log_type('unknown.txt', content), 'build')

    def test_few_timestamps_defaults_build(self):
        """Less than 10 timestamp matches should default to build."""
        lines = [f"01-15 12:34:{i:02d}.789 msg" for i in range(5)]
        content = '\n'.join(lines)
        self.assertEqual(detect_log_type('unknown.txt', content), 'build')


if __name__ == '__main__':
    unittest.main()
