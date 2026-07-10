"""Tests for the bugreport triage command — parsing, detection, no-AI path."""

import io
import os
import tempfile
import unittest
import zipfile
from unittest.mock import MagicMock
from src.ailog.bugreport import BugreportAnalyzer


SAMPLE = """\
========================================================
== dumpstate: 2026-07-10 14:20:00
========================================================
Build fingerprint: 'Android/car_x86_64/emu:14/UQ1A.240101/123:userdebug/dev-keys'
Kernel: Linux version 6.1.0
Bootloader: unknown
Uptime: up 0 weeks, 0 days, 1 hour

------ SYSTEM LOG (logcat -v threadtime) ------
07-10 14:19:01.100  1200  1220 E AndroidRuntime: FATAL EXCEPTION: main
07-10 14:19:01.100  1200  1220 E AndroidRuntime: Process: com.oem.dashboard, PID: 1200
07-10 14:19:01.100  1200  1220 E AndroidRuntime: java.lang.NullPointerException: boom
07-10 14:19:01.100  1200  1220 E AndroidRuntime:   at com.oem.dashboard.Main.onCreate(Main.java:42)
07-10 14:19:05.200   900   950 W ActivityManager: ANR in com.oem.telemetry
07-10 14:19:05.200   900   950 W ActivityManager: Reason: Input dispatching timed out
07-10 14:19:06.300   520   520 W avc: denied { read } for name="prop" scontext=u:r:hal_vehicle_default:s0 tcontext=u:object_r:sysfs:s0 tclass=file
07-10 14:19:06.400   520   520 W avc: denied { read } for name="prop" scontext=u:r:hal_vehicle_default:s0 tcontext=u:object_r:sysfs:s0 tclass=file
07-10 14:19:07.000   300   300 E Watchdog: *** WATCHDOG KILLING SYSTEM PROCESS: system_server blocked

------ TOMBSTONE ------
*** *** *** *** *** *** *** *** *** *** *** *** *** *** *** ***
Build fingerprint: 'Android/car_x86_64/emu:14/UQ1A.240101/123:userdebug/dev-keys'
pid: 1180, tid: 1180, name: vehicle.default
signal 6 (SIGABRT), code -6 (SI_TKILL), fault addr --------
abort message: 'CHECK failed in VehicleHalManager'
backtrace:
  #00 pc 0004a1b0 /vendor/bin/hw/android.hardware.automotive.vehicle
"""


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


class _Args:
    def __init__(self, file, no_ai=True, focus=None, output=None):
        self.file = file
        self.no_ai = no_ai
        self.focus = focus
        self.output = output


def _analyzer():
    return BugreportAnalyzer(_Cfg(), MagicMock())


class TestDetection(unittest.TestCase):
    def setUp(self):
        self.a = _analyzer()

    def test_device_info(self):
        info = dict(self.a._device_info(SAMPLE))
        self.assertIn('Build fingerprint', info)
        self.assertIn('car_x86_64', info['Build fingerprint'])
        self.assertEqual(info['Kernel'], 'Linux version 6.1.0')

    def test_detects_all_kinds(self):
        issues, selinux = self.a._detect(SAMPLE.splitlines())
        kinds = {i.kind for i in issues}
        self.assertEqual(kinds, {'java', 'anr', 'native', 'watchdog'})

    def test_java_crash_title(self):
        issues, _ = self.a._detect(SAMPLE.splitlines())
        java = next(i for i in issues if i.kind == 'java')
        self.assertIn('NullPointerException', java.title)
        self.assertIn('com.oem.dashboard', java.title)

    def test_native_crash_detected(self):
        issues, _ = self.a._detect(SAMPLE.splitlines())
        native = next(i for i in issues if i.kind == 'native')
        self.assertIn('SIGABRT', native.title)
        self.assertIn('abort message', native.block)

    def test_selinux_deduped(self):
        _, selinux = self.a._detect(SAMPLE.splitlines())
        # Two identical denials collapse to one unique entry
        self.assertEqual(len(selinux), 1)

    def test_focus_filters(self):
        issues, _ = self.a._detect(SAMPLE.splitlines(), focus='telemetry')
        self.assertTrue(all('telemetry' in i.block.lower() for i in issues))
        self.assertTrue(any(i.kind == 'anr' for i in issues))


class TestRunNoAI(unittest.TestCase):
    def test_txt_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'bugreport-test.txt')
            with open(p, 'w') as f:
                f.write(SAMPLE)
            out = os.path.join(d, 'report.md')
            rc = _analyzer().run(_Args(p, no_ai=True, output=out))
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(out))
            report = open(out, encoding='utf-8').read()
            self.assertIn('NullPointerException', report)
            self.assertIn('SELinux', report)

    def test_zip_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            zpath = os.path.join(d, 'bugreport.zip')
            buf = io.BytesIO()
            with zipfile.ZipFile(zpath, 'w') as z:
                z.writestr('bugreport-car-123.txt', SAMPLE)
                z.writestr('version.txt', 'ignore me')
            del buf
            rc = _analyzer().run(_Args(zpath, no_ai=True))
            self.assertEqual(rc, 0)

    def test_missing_file(self):
        rc = _analyzer().run(_Args('/no/such/bugreport.zip', no_ai=True))
        self.assertEqual(rc, 1)

    def test_no_issues_clean_report(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'clean.txt')
            with open(p, 'w') as f:
                f.write("Build fingerprint: 'x'\n------ SYSTEM LOG ------\nD Nothing interesting here\n")
            rc = _analyzer().run(_Args(p, no_ai=True))
            self.assertEqual(rc, 0)


if __name__ == '__main__':
    unittest.main()
