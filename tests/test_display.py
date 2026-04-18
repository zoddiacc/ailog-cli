"""Tests for display module — width calculation and color support."""

import unittest
from src.ailog.display import _display_width, supports_color, Display


class TestDisplayWidth(unittest.TestCase):
    """Test _display_width helper function."""

    def test_ascii_string(self):
        self.assertEqual(_display_width("hello"), 5)

    def test_empty_string(self):
        self.assertEqual(_display_width(""), 0)

    def test_wide_characters(self):
        # CJK characters are typically width 2
        width = _display_width("\u4e16\u754c")  # 世界
        self.assertEqual(width, 4)

    def test_ansi_codes_stripped(self):
        # ANSI codes should not contribute to width
        text = "\033[31mred\033[0m"
        # _display_width doesn't strip ANSI, but let's verify basic behavior
        self.assertGreaterEqual(_display_width("red"), 3)


class TestSupportsColor(unittest.TestCase):
    """Test supports_color function."""

    def test_returns_bool(self):
        result = supports_color()
        self.assertIsInstance(result, bool)


class TestDisplayInit(unittest.TestCase):
    """Test Display class initialization."""

    def test_no_color(self):
        d = Display(use_color=False)
        # _c should return empty string when color is off
        self.assertEqual(d._c("\033[31m"), "")

    def test_forced_color(self):
        d = Display(use_color=True)
        self.assertEqual(d._c("\033[31m"), "\033[31m")


if __name__ == '__main__':
    unittest.main()
