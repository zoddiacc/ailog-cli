"""Tests for logcat_wrapper module — crash metadata parsing and helpers."""

import os
import threading
import unittest
from unittest.mock import MagicMock
from src.ailog.logcat_wrapper import LogcatWrapper, _PACKAGE_RE, _SERIAL_RE


class _Cfg:
    provider = 'ollama'
    dry_run = False
    show_tokens = False
    redact = None

    def get(self, k, d=None):
        return {'max_ai_calls': 5, 'timeout': 30, 'system_prompt': ''}.get(k, d)

    def get_api_key(self):
        return ''

    def get_model(self):
        return 'test-model'

    def get_base_url(self):
        return 'http://localhost:11434'


def _wrapper(max_calls=5):
    w = LogcatWrapper(_Cfg(), MagicMock())
    w.max_ai_calls = max_calls
    return w


class TestReserveAiCall(unittest.TestCase):
    """The AI budget must be atomic across the timer and main threads."""

    def test_never_exceeds_budget_under_concurrency(self):
        w = _wrapper(max_calls=50)
        reserved = []

        def worker():
            for _ in range(100):
                if w._reserve_ai_call():
                    reserved.append(1)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(reserved), 50)   # exactly the budget, never more
        self.assertEqual(w._ai_calls, 50)

    def test_returns_false_when_exhausted(self):
        w = _wrapper(max_calls=1)
        self.assertTrue(w._reserve_ai_call())
        self.assertFalse(w._reserve_ai_call())


class TestSafeFixTarget(unittest.TestCase):
    def test_rejects_non_source_extension(self):
        w = _wrapper()
        self.assertFalse(w._is_safe_fix_target('build.gradle.properties.txt'))

    def test_rejects_path_outside_cwd(self):
        w = _wrapper()
        self.assertFalse(w._is_safe_fix_target('/etc/passwd'))
        self.assertFalse(w._is_safe_fix_target('../../secret.kt'))

    def test_accepts_source_in_cwd(self):
        w = _wrapper()
        path = os.path.join(os.getcwd(), 'src', 'Main.kt')
        self.assertTrue(w._is_safe_fix_target(path))


class TestInputValidationRegexes(unittest.TestCase):
    def test_valid_package(self):
        self.assertTrue(_PACKAGE_RE.match('com.example.my_app'))

    def test_rejects_injection_package(self):
        self.assertIsNone(_PACKAGE_RE.match('foo; reboot'))
        self.assertIsNone(_PACKAGE_RE.match('$(rm -rf /)'))
        self.assertIsNone(_PACKAGE_RE.match('-flag'))

    def test_valid_serial(self):
        self.assertTrue(_SERIAL_RE.match('emulator-5554'))
        self.assertTrue(_SERIAL_RE.match('192.168.1.5:5555'))

    def test_rejects_injection_serial(self):
        self.assertIsNone(_SERIAL_RE.match('a b; rm'))
        self.assertIsNone(_SERIAL_RE.match('$(id)'))


class TestMethodMetadata(unittest.TestCase):
    def test_method_is_full_class(self):
        lines = [
            "E AndroidRuntime: FATAL EXCEPTION: main",
            "E AndroidRuntime: \tat com.oem.dash.Main.onCreate(Main.kt:10)",
        ]
        meta = LogcatWrapper._parse_crash_metadata(lines)
        self.assertEqual(meta['method'], 'com.oem.dash.Main.onCreate')
        self.assertEqual(meta['location'], 'Main.kt:10')


class TestParseCrashMetadata(unittest.TestCase):
    """Test _parse_crash_metadata static method."""

    def test_basic_crash_block(self):
        lines = [
            "03-05 12:00:00.000  1234  1234 E AndroidRuntime: FATAL EXCEPTION: main",
            "03-05 12:00:00.001  1234  1234 E AndroidRuntime: Process: com.example.app, PID: 1234",
            "03-05 12:00:00.002  1234  1234 E AndroidRuntime: java.lang.NullPointerException: Attempt to invoke virtual method on a null object reference",
            "03-05 12:00:00.003  1234  1234 E AndroidRuntime: \tat com.example.app.MainActivity.onCreate(MainActivity.kt:35)",
            "03-05 12:00:00.004  1234  1234 E AndroidRuntime: \tat android.app.Activity.performCreate(Activity.java:8000)",
        ]
        meta = LogcatWrapper._parse_crash_metadata(lines)
        self.assertEqual(meta['exception_type'], 'java.lang.NullPointerException')
        self.assertIn('NullPointerException', meta['exception'])
        self.assertEqual(meta['thread'], 'main')
        self.assertIn('1234', meta['process'])
        self.assertEqual(meta['location'], 'MainActivity.kt:35')

    def test_caused_by_overrides_exception(self):
        lines = [
            "E AndroidRuntime: FATAL EXCEPTION: main",
            "E AndroidRuntime: java.lang.RuntimeException: Unable to start activity",
            "E AndroidRuntime: \tat android.app.ActivityThread.performLaunchActivity(ActivityThread.java:3449)",
            "E AndroidRuntime: Caused by: java.lang.IllegalStateException: View not attached",
            "E AndroidRuntime: \tat com.example.app.MyFragment.onResume(MyFragment.kt:42)",
        ]
        meta = LogcatWrapper._parse_crash_metadata(lines)
        self.assertEqual(meta['exception_type'], 'java.lang.IllegalStateException')
        self.assertIn('View not attached', meta['exception'])

    def test_no_exception_found(self):
        lines = [
            "E AndroidRuntime: something weird happened",
            "E AndroidRuntime: no recognizable exception pattern here",
        ]
        meta = LogcatWrapper._parse_crash_metadata(lines)
        self.assertNotIn('exception', meta)
        self.assertNotIn('exception_type', meta)

    def test_framework_only_stack_trace(self):
        """When all stack frames are framework code, use fallback location."""
        lines = [
            "E AndroidRuntime: FATAL EXCEPTION: main",
            "E AndroidRuntime: java.lang.NullPointerException: msg",
            "E AndroidRuntime: \tat android.app.Activity.performCreate(Activity.java:8000)",
            "E AndroidRuntime: \tat android.app.Instrumentation.callActivityOnCreate(Instrumentation.java:1309)",
        ]
        meta = LogcatWrapper._parse_crash_metadata(lines)
        self.assertEqual(meta['location'], 'Activity.java:8000')

    def test_process_extraction(self):
        lines = [
            "E AndroidRuntime: Process: com.myapp.test, PID: 5678",
            "E AndroidRuntime: java.lang.ArithmeticException: divide by zero",
        ]
        meta = LogcatWrapper._parse_crash_metadata(lines)
        self.assertEqual(meta['process'], 'com.myapp.test (PID 5678)')

    def test_empty_crash_lines(self):
        meta = LogcatWrapper._parse_crash_metadata([])
        self.assertEqual(meta, {})


class TestNormalizeForDedup(unittest.TestCase):
    """Test _normalize_for_dedup static-like method."""

    def test_strips_timestamp(self):
        wrapper = LogcatWrapper.__new__(LogcatWrapper)
        line = "03-05 23:30:45.451  1234  1234 E MyTag: error message"
        normalized = wrapper._normalize_for_dedup(line)
        self.assertNotIn("03-05", normalized)
        self.assertIn("error message", normalized)

    def test_strips_pid_tid(self):
        wrapper = LogcatWrapper.__new__(LogcatWrapper)
        line = "03-05 10:00:00.000 32119 32119 E Tag: msg"
        normalized = wrapper._normalize_for_dedup(line)
        self.assertIn("msg", normalized)

    def test_identical_content_matches(self):
        wrapper = LogcatWrapper.__new__(LogcatWrapper)
        line1 = "03-05 10:00:00.000  1234  1234 E Tag: same error"
        line2 = "03-05 10:00:01.000  1234  1234 E Tag: same error"
        self.assertEqual(
            wrapper._normalize_for_dedup(line1),
            wrapper._normalize_for_dedup(line2),
        )


class TestFindSourceFile(unittest.TestCase):
    """Test _find_source_file static method."""

    def test_nonexistent_file(self):
        result = LogcatWrapper._find_source_file("__nonexistent_file_abc123__.kt")
        self.assertIsNone(result)


class TestReadSourceSnippet(unittest.TestCase):
    """Test _read_source_snippet static method."""

    def test_nonexistent_file(self):
        result = LogcatWrapper._read_source_snippet("/nonexistent/path.kt", 10)
        self.assertIsNone(result)

    def test_reads_with_marker(self):
        import tempfile
        import os
        content = "\n".join(f"line {i}" for i in range(1, 21))
        with tempfile.NamedTemporaryFile(mode='w', suffix='.kt', delete=False) as f:
            f.write(content)
            tmppath = f.name
        try:
            snippet = LogcatWrapper._read_source_snippet(tmppath, 10, context=3)
            self.assertIn('>>', snippet)  # marker on crash line
            self.assertIn('line 10', snippet)
        finally:
            os.unlink(tmppath)


if __name__ == '__main__':
    unittest.main()
