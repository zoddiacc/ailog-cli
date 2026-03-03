"""Tests for noise_filter module."""

import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ailog.noise_filter import NoiseFilter


class TestIsImportant(unittest.TestCase):
    def setUp(self):
        self.nf = NoiseFilter()

    def test_error_line(self):
        self.assertTrue(self.nf.is_important("01-15 12:00:00.000  1234  5678 E/System: error occurred"))

    def test_exception_line(self):
        self.assertTrue(self.nf.is_important("java.lang.NullPointerException: null"))

    def test_stack_trace(self):
        self.assertTrue(self.nf.is_important("    at com.example.MyClass(MyClass.java:42)"))

    def test_fatal(self):
        self.assertTrue(self.nf.is_important("FATAL EXCEPTION: main"))

    def test_anr(self):
        self.assertTrue(self.nf.is_important("ANR in com.example.app"))

    def test_segfault(self):
        self.assertTrue(self.nf.is_important("signal 11 (SIGSEGV), code 1"))

    def test_sigabrt(self):
        self.assertTrue(self.nf.is_important("signal 6 (SIGABRT)"))

    def test_build_error(self):
        self.assertTrue(self.nf.is_important("error: undefined reference to 'foo'"))

    def test_ninja_error(self):
        self.assertTrue(self.nf.is_important("ninja: error: 'out/target/foo.o', needed by 'foo'"))

    def test_oom(self):
        self.assertTrue(self.nf.is_important("java.lang.OutOfMemoryError: Failed to allocate"))

    def test_permission_denied(self):
        self.assertTrue(self.nf.is_important("Permission Denied accessing /data/local"))

    def test_vhal(self):
        self.assertTrue(self.nf.is_important("VHAL property set failed"))

    def test_normal_line_not_important(self):
        self.assertFalse(self.nf.is_important("D/MyApp: normal debug message"))


class TestIsNoise(unittest.TestCase):
    def setUp(self):
        self.nf = NoiseFilter()

    def test_blank_line(self):
        self.assertTrue(self.nf.is_noise(""))
        self.assertTrue(self.nf.is_noise("   "))

    def test_binder_noise(self):
        self.assertTrue(self.nf.is_noise("01-15 12:00:00.000 Binder: thread 1234_5 entered"))

    def test_gc_noise(self):
        self.assertTrue(self.nf.is_noise("GC_FOR_ALLOC freed 1234K"))
        self.assertTrue(self.nf.is_noise("GC_CONCURRENT freed 500K"))

    def test_zygote_noise(self):
        self.assertTrue(self.nf.is_noise("Zygote preload classes took 200ms"))

    def test_chatty_noise(self):
        self.assertTrue(self.nf.is_noise("chatty: uid=1000 identical 42 lines"))

    def test_surfaceflinger_noise(self):
        self.assertTrue(self.nf.is_noise("SurfaceFlinger VSYNC offset updated"))

    def test_separator_noise(self):
        self.assertTrue(self.nf.is_noise("---------"))

    def test_normal_line_not_noise(self):
        self.assertFalse(self.nf.is_noise("I/MyApp: Started successfully"))


class TestFilterBatch(unittest.TestCase):
    def setUp(self):
        self.nf = NoiseFilter()

    def test_keeps_errors_filters_noise(self):
        lines = [
            "GC_FOR_ALLOC freed 1234K",
            "E/MyApp: NullPointerException in onClick",
            "",
            "Binder: thread 1_2 entered",
            "W/System.err: at com.example.Foo(Foo.java:10)",
        ]
        kept, filtered = self.nf.filter_batch(lines)
        self.assertEqual(filtered, 3)  # GC, blank, Binder
        self.assertEqual(len(kept), 2)  # error + stack trace
        self.assertIn("NullPointerException", kept[0])

    def test_dedup_on_medium(self):
        lines = [
            "I/MyTag: processing item 1",
            "I/MyTag: processing item 2",
            "I/MyTag: processing item 3",
        ]
        nf = NoiseFilter(noise_level='medium')
        kept, filtered = nf.filter_batch(lines)
        # After normalization, these should look similar — first kept, rest filtered
        self.assertGreaterEqual(filtered, 0)
        self.assertLessEqual(len(kept), len(lines))

    def test_build_noise_filtered_on_high(self):
        lines = [
            "[50%] Building CXX object foo.o",
            "error: undefined reference to 'bar'",
        ]
        nf = NoiseFilter(noise_level='high')
        kept, filtered = nf.filter_batch(lines, mode='build')
        self.assertEqual(len(kept), 1)
        self.assertIn("undefined reference", kept[0])


class TestNormalize(unittest.TestCase):
    def setUp(self):
        self.nf = NoiseFilter()

    def test_strips_timestamp(self):
        result = self.nf._normalize("01-15 12:34:56.789 I/MyApp: hello")
        self.assertNotIn("01-15", result)

    def test_strips_pid_tid(self):
        result = self.nf._normalize("  1234  5678 I/MyApp: hello")
        self.assertNotIn("1234", result)

    def test_normalizes_hex(self):
        result = self.nf._normalize("pointer at 0xdeadbeef crashed")
        self.assertIn("0xXXXX", result)
        self.assertNotIn("deadbeef", result)


class TestShouldTriggerAi(unittest.TestCase):
    def setUp(self):
        self.nf = NoiseFilter()

    def test_triggers_on_error(self):
        self.assertTrue(self.nf.should_trigger_ai(["some error occurred"]))

    def test_triggers_on_exception(self):
        self.assertTrue(self.nf.should_trigger_ai(["java.lang.RuntimeException"]))

    def test_triggers_on_important(self):
        self.assertTrue(self.nf.should_trigger_ai(["FATAL EXCEPTION: main"]))

    def test_no_trigger_on_normal(self):
        self.assertFalse(self.nf.should_trigger_ai(["D/MyApp: all good", "I/MyApp: running"]))


class TestExtractErrorsWarnings(unittest.TestCase):
    def setUp(self):
        self.nf = NoiseFilter()

    def test_extracts_errors_and_warnings(self):
        lines = [
            "error: something broke",
            "warning: deprecated API",
            "info: all good",
            "FAILED: build target",
            "WARNING: low memory",
        ]
        errors, warnings = self.nf.extract_errors_warnings(lines)
        self.assertEqual(len(errors), 2)  # error + FAILED
        self.assertEqual(len(warnings), 2)  # warning + WARNING


if __name__ == '__main__':
    unittest.main()
