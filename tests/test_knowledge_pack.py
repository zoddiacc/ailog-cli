"""Tests for the AOSP/Automotive knowledge pack — retrieval and integrity."""

import unittest
from src.ailog import knowledge_pack as kp
from src.ailog.line_hints import get_hint


class TestPackIntegrity(unittest.TestCase):
    """The pack is data; guard its structural invariants."""

    def test_pack_non_empty(self):
        self.assertGreater(len(kp.KNOWLEDGE), 0)

    def test_ids_unique(self):
        ids = [e.id for e in kp.KNOWLEDGE]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_entry_well_formed(self):
        for e in kp.KNOWLEDGE:
            self.assertTrue(e.id and e.category, f"{e.id}: missing id/category")
            self.assertTrue(e.hint.strip(), f"{e.id}: empty hint")
            # Guidance must be substantial, not a stub
            self.assertGreater(len(e.guidance), 40, f"{e.id}: guidance too short")
            self.assertTrue(hasattr(e.signature, 'search'), f"{e.id}: signature not compiled")


class TestFindMatches(unittest.TestCase):
    def test_selinux_denial_matches(self):
        line = ('avc: denied { read } for name="foo" scontext=u:r:untrusted_app:s0 '
                'tcontext=u:object_r:system_data_file:s0 tclass=file')
        ids = [e.id for e in kp.find_matches(line)]
        self.assertIn('selinux-denial', ids)

    def test_native_sigsegv_matches(self):
        line = 'F DEBUG: signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x0'
        ids = [e.id for e in kp.find_matches(line)]
        self.assertIn('native-sigsegv', ids)

    def test_vhal_not_available_matches(self):
        line = 'E VehicleHal: get(0x11600203) returned StatusCode: NOT_AVAILABLE'
        ids = [e.id for e in kp.find_matches(line)]
        self.assertIn('vhal-not-available', ids)

    def test_car_watchdog_matches(self):
        line = 'W CarWatchdog: Terminating process com.example.svc for health check timeout'
        ids = [e.id for e in kp.find_matches(line)]
        self.assertIn('car-watchdog-kill', ids)

    def test_no_match_on_plain_text(self):
        self.assertEqual(kp.find_matches('D ActivityManager: Displayed com.foo/.Main'), [])

    def test_empty_input(self):
        self.assertEqual(kp.find_matches(''), [])
        self.assertEqual(kp.find_matches(None), [])

    def test_limit_is_respected(self):
        # A blob that triggers several signatures at once
        blob = ('avc: denied { read } scontext=u:r:x:s0 tcontext=u:object_r:y:s0 tclass=file\n'
                'signal 11 (SIGSEGV)\n'
                'signal 6 (SIGABRT)\n'
                'DeadObjectException\n'
                'ninja: build stopped: subcommand failed\n')
        self.assertLessEqual(len(kp.find_matches(blob, limit=2)), 2)


class TestRetrieveContext(unittest.TestCase):
    def test_returns_block_with_guidance(self):
        ctx = kp.retrieve_context('avc: denied { read } scontext=u:r:x:s0 '
                                  'tcontext=u:object_r:y:s0 tclass=file')
        self.assertIn('AUTHORITATIVE', ctx)
        self.assertIn('SELinux', ctx)
        self.assertIn('allow', ctx)  # the actual sepolicy guidance

    def test_empty_when_no_match(self):
        self.assertEqual(kp.retrieve_context('nothing interesting here'), '')

    def test_empty_input_safe(self):
        self.assertEqual(kp.retrieve_context(''), '')


class TestLineHintsIntegration(unittest.TestCase):
    """Domain hints must reach the no-AI path and take priority over generic rules."""

    def test_domain_hint_used(self):
        line = ('avc: denied { write } for scontext=u:r:untrusted_app:s0 '
                'tcontext=u:object_r:sysfs:s0 tclass=file')
        hint = get_hint(line)
        self.assertIn('SELinux', hint)

    def test_native_crash_hint(self):
        hint = get_hint('F DEBUG: signal 6 (SIGABRT), code -6')
        self.assertIn('SIGABRT', hint)

    def test_generic_fallback_still_works(self):
        # A line with no domain entry should fall back to the generic rules
        hint = get_hint('ANR in com.example.app')
        self.assertTrue(hint)  # generic rule fires
        self.assertNotIn('[', hint[:1])  # not a domain-tagged hint


if __name__ == '__main__':
    unittest.main()
