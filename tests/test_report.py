"""Tests for report module — HTML generation."""

import unittest
from src.ailog.report import _text_to_html, generate_html_report


class TestTextToHtml(unittest.TestCase):
    """Test _text_to_html conversion."""

    def test_escapes_html(self):
        result = _text_to_html('<script>alert("xss")</script>')
        self.assertNotIn('<script>', result)
        self.assertIn('&lt;script&gt;', result)

    def test_code_blocks(self):
        text = "before\n```java\npublic void foo() {}\n```\nafter"
        result = _text_to_html(text)
        self.assertIn('<pre class="code-block">', result)
        self.assertIn('public void foo()', result)

    def test_section_headers_bolded(self):
        text = "ROOT CAUSE: null pointer\nHOW TO FIX: add null check"
        result = _text_to_html(text)
        self.assertIn('<strong class="section-header">', result)
        self.assertIn('ROOT CAUSE', result)
        self.assertIn('HOW TO FIX', result)

    def test_newlines_to_br(self):
        text = "line one\nline two"
        result = _text_to_html(text)
        self.assertIn('<br>', result)

    def test_newlines_not_in_pre(self):
        text = "```\ncode line 1\ncode line 2\n```"
        result = _text_to_html(text)
        # Inside <pre>, newlines should NOT be converted to <br>
        pre_start = result.find('<pre')
        pre_end = result.find('</pre>')
        pre_content = result[pre_start:pre_end]
        self.assertNotIn('<br>', pre_content)


class TestGenerateHtmlReport(unittest.TestCase):
    """Test generate_html_report function."""

    def test_basic_report(self):
        data = {
            'stats': {'crashes': 1, 'errors': 5, 'warnings': 3, 'filtered': 100, 'lines': 500},
            'crashes': [
                ({'exception': 'NullPointerException', 'thread': 'main'}, 'Check for null before calling method'),
            ],
            'batch_analyses': [('Logcat Analysis', 'Multiple errors detected')],
            'summary': 'Fix the NPE first',
            'config': {'provider': 'ollama', 'model': 'qwen2.5-coder:3b', 'noise_level': 'medium'},
            'timestamp': '2024-03-05 12:00:00',
        }
        html = generate_html_report(data)
        self.assertIn('<!DOCTYPE html>', html)
        self.assertIn('AILog Session Report', html)
        self.assertIn('NullPointerException', html)
        self.assertIn('Fix the NPE first', html)
        self.assertIn('Logcat Analysis', html)

    def test_empty_report(self):
        data = {
            'stats': {'crashes': 0, 'errors': 0, 'warnings': 0, 'filtered': 0, 'lines': 0},
            'crashes': [],
            'batch_analyses': [],
            'summary': '',
            'config': {'provider': 'ollama', 'model': 'test', 'noise_level': 'medium'},
            'timestamp': '2024-01-01 00:00:00',
        }
        html = generate_html_report(data)
        self.assertIn('No crashes detected', html)
        self.assertIn('Clean session', html)

    def test_xss_prevention(self):
        """Ensure user-controlled data is escaped."""
        data = {
            'stats': {'crashes': 0, 'errors': 0, 'warnings': 0, 'filtered': 0, 'lines': 0},
            'crashes': [({'exception': '<img onerror=alert(1)>'}, '<script>alert(1)</script>')],
            'batch_analyses': [],
            'summary': '',
            'config': {'provider': '<b>evil</b>', 'model': 'test', 'noise_level': 'medium'},
            'timestamp': '<script>',
        }
        html = generate_html_report(data)
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertNotIn('<img onerror', html)


if __name__ == '__main__':
    unittest.main()
