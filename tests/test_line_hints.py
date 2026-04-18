"""Tests for line_hints module — rule-based hint matching."""

import unittest
from src.ailog.line_hints import get_hint


class TestGetHint(unittest.TestCase):
    """Test get_hint function with various log patterns."""

    def test_activity_launch(self):
        line = "03-05 12:00:00.000 ActivityManager: START u0 {cmp=com.example.app/.MainActivity} from uid 10123"
        hint = get_hint(line)
        self.assertIn('Launching activity', hint)
        self.assertIn('com.example.app/.MainActivity', hint)

    def test_fatal_exception(self):
        line = "E AndroidRuntime: FATAL EXCEPTION: main"
        hint = get_hint(line)
        self.assertIn('crashed', hint.lower())
        self.assertIn('main', hint)

    def test_null_pointer_exception(self):
        line = "E AndroidRuntime: java.lang.NullPointerException: Attempt to invoke method"
        hint = get_hint(line)
        self.assertIn('NullPointerException', hint)

    def test_process_crash(self):
        line = "E AndroidRuntime: Process: com.example.app, PID: 1234"
        hint = get_hint(line)
        self.assertIn('com.example.app', hint)
        self.assertIn('1234', hint)

    def test_anr(self):
        line = "E ActivityManager: ANR in com.example.app"
        hint = get_hint(line)
        self.assertIn('App Not Responding', hint)

    def test_permission_denial(self):
        line = "W System: Permission Denial: reading from pid=1234, uid=10001"
        hint = get_hint(line)
        self.assertIn('Permission denied', hint)

    def test_out_of_memory(self):
        line = "E AndroidRuntime: java.lang.OutOfMemoryError: Failed to allocate"
        hint = get_hint(line)
        self.assertIn('out of memory', hint.lower())

    def test_anr_detection(self):
        line = "E ActivityManager: ANR in com.myapp.test"
        hint = get_hint(line)
        self.assertIn('App Not Responding', hint)

    def test_selinux_denied(self):
        line = "W SELinux: avc: denied { read } scontext=u:r:untrusted_app:s0 tcontext=u:object_r:system_file:s0"
        hint = get_hint(line)
        self.assertIn('SELinux denied', hint)

    def test_skipped_frames(self):
        line = "I Choreographer: Skipped 120 frames! The application may be doing too much work on its main thread."
        hint = get_hint(line)
        self.assertIn('120', hint)
        self.assertIn('jank', hint.lower())

    def test_no_hint_for_normal_line(self):
        line = "D MyApp: Loading preferences"
        hint = get_hint(line)
        self.assertEqual(hint, '')

    def test_network_error(self):
        line = "E MyApp: java.net.SocketException: Connection reset"
        hint = get_hint(line)
        # Matches the java exception rule before the network-specific rule
        self.assertIn('SocketException', hint)

    def test_sqlite_error(self):
        line = "E SQLiteLog: (14) cannot open file at line 34024 of [abc123]"
        hint = get_hint(line)
        self.assertIn('SQLite error', hint)

    def test_app_code_stack_frame(self):
        line = "E AndroidRuntime: \tat com.myapp.utils.Helper.doStuff(Helper.java:42)"
        hint = get_hint(line)
        self.assertIn('App code', hint)
        self.assertIn('42', hint)

    def test_framework_stack_frame_no_app_hint(self):
        """Framework frames should not match the app-code hint rule."""
        line = "E AndroidRuntime: \tat android.app.Activity.performCreate(Activity.java:8000)"
        hint = get_hint(line)
        self.assertNotIn('App code', hint)


if __name__ == '__main__':
    unittest.main()
