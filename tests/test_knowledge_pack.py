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

    def test_car_not_connected_matches(self):
        line = 'E CarClimate: android.car.CarNotConnectedException: not connected'
        self.assertIn('car-not-connected', [e.id for e in kp.find_matches(line)])

    def test_car_permission_denied_matches(self):
        line = ('E CarService: Permission Denial: does not have '
                'android.car.permission.CONTROL_CAR_CLIMATE')
        self.assertIn('car-permission-denied', [e.id for e in kp.find_matches(line)])

    def test_garage_mode_matches(self):
        line = 'I CarPowerManagementService: Entering Garage Mode'
        self.assertIn('garage-mode', [e.id for e in kp.find_matches(line)])

    def test_car_evs_matches(self):
        line = 'E CarEvsService: EVS camera stream failed to start'
        self.assertIn('car-evs', [e.id for e in kp.find_matches(line)])

    def test_car_user_switch_matches(self):
        line = 'W CarUserService: switchUser timed out waiting for user HAL'
        self.assertIn('car-user-switch', [e.id for e in kp.find_matches(line)])

    def test_car_audio_zone_matches(self):
        line = 'E CarAudioService: car_audio_configuration.xml: device address not found'
        self.assertIn('car-audio-zone-config', [e.id for e in kp.find_matches(line)])

    def test_vhal_permission_matches(self):
        line = 'E VehicleHal: requires android.car.permission.CONTROL_CAR_ENERGY'
        self.assertIn('vhal-permission', [e.id for e in kp.find_matches(line)])

    def test_no_match_on_plain_text(self):
        self.assertEqual(kp.find_matches('D ActivityManager: Displayed com.foo/.Main'), [])

    def test_no_match_on_ordinary_automotive_free_lines(self):
        # Guard against the new automotive regexes over-matching benign lines
        for benign in [
            'I ActivityManager: Start proc 1234:com.example/u0a10',
            'D WifiService: Connected to network',
            'V ViewRootImpl: draw finished',
        ]:
            self.assertEqual(kp.find_matches(benign), [], benign)

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


class TestVhalPropertyTable(unittest.TestCase):
    def test_property_table_non_empty(self):
        self.assertGreater(len(kp.VHAL_PROPERTIES), 20)

    def test_property_values_well_formed(self):
        for name, val in kp.VHAL_PROPERTIES.items():
            self.assertEqual(len(val), 2, f"{name}: expected (short, guidance)")
            short, guidance = val
            self.assertTrue(short.strip(), f"{name}: empty short")
            self.assertGreater(len(guidance), 40, f"{name}: guidance too short")

    def test_property_referenced_in_log_matches(self):
        line = 'E VehicleHal: get(HVAC_TEMPERATURE_SET) failed NOT_AVAILABLE'
        ids = [e.id for e in kp.find_matches(line)]
        self.assertIn('vhal-prop-hvac_temperature_set', ids)

    def test_longest_name_wins(self):
        # PERF_VEHICLE_SPEED_DISPLAY must not be shadowed by PERF_VEHICLE_SPEED
        names = kp._find_vhal_property_names('cluster shows PERF_VEHICLE_SPEED_DISPLAY jitter')
        self.assertIn('PERF_VEHICLE_SPEED_DISPLAY', names)
        self.assertNotIn('PERF_VEHICLE_SPEED', names)

    def test_property_hint_reaches_no_ai_path(self):
        hint = get_hint('W VehicleHal: PARKING_BRAKE_ON stuck true')
        self.assertIn('PARKING_BRAKE_ON', hint)

    def test_property_guidance_injected_into_context(self):
        ctx = kp.retrieve_context('EV_CHARGE_PORT_CONNECTED reported false while charging')
        self.assertIn('EV_CHARGE_PORT_CONNECTED', ctx)
        self.assertIn('PERMISSION_ENERGY_PORTS', ctx)

    def test_no_false_positive_on_plain_words(self):
        # Lowercase / ordinary words must not match property names
        self.assertEqual(kp._find_vhal_property_names('the door lock was fine'), [])


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
