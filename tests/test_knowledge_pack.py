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

    def test_ux_restrictions_matches(self):
        line = 'D CarUxRestrictionsManagerService: restrictions changed: requiresDO=true'
        self.assertIn('car-ux-restrictions', [e.id for e in kp.find_matches(line)])

    def test_activity_blocked_matches(self):
        line = 'I ActivityBlockingActivity: Blocking com.example.app/.VideoActivity'
        self.assertIn('car-activity-blocked', [e.id for e in kp.find_matches(line)])

    def test_occupant_zone_matches(self):
        line = 'E CarOccupantZoneService: no display assigned for occupant zone 2'
        self.assertIn('car-occupant-zone', [e.id for e in kp.find_matches(line)])

    def test_input_dispatch_anr_matches(self):
        line = ('E ActivityManager: Input dispatching timed out '
                '(Waiting to send non-key event because the touched window has not finished)')
        self.assertIn('anr-input-dispatch', [e.id for e in kp.find_matches(line)])

    def test_broadcast_timeout_matches(self):
        line = 'W BroadcastQueue: Timeout of broadcast BroadcastRecord{abc u0 android.intent.action.BOOT_COMPLETED}'
        self.assertIn('anr-broadcast-timeout', [e.id for e in kp.find_matches(line)])

    def test_slow_dispatch_matches(self):
        line = 'W Looper: Slow dispatch took 3212ms android.fg h=android.os.Handler c=... m=0'
        self.assertIn('slow-main-thread', [e.id for e in kp.find_matches(line)])

    def test_jni_error_matches(self):
        line = 'F art: JNI DETECTED ERROR IN APPLICATION: use of deleted local reference 0x75'
        self.assertIn('jni-error', [e.id for e in kp.find_matches(line)])

    def test_fdsan_matches(self):
        line = ("E fdsan: attempted to close file descriptor 42, expected to be unowned, "
                "actually owned by unique_fd 0x7b0")
        self.assertIn('fdsan-error', [e.id for e in kp.find_matches(line)])

    def test_hal_service_wait_matches(self):
        for line in [
            'I ServiceManagement: Waited one second for android.hardware.automotive.vehicle@2.0::IVehicle/default',
            'I ServiceManager: Waited 5000ms for android.hardware.automotive.vehicle.IVehicle/default',
        ]:
            self.assertIn('hal-service-wait', [e.id for e in kp.find_matches(line)], line)

    def test_vintf_matches(self):
        line = 'E init: Check vintf compatibility failed: checkvintf found errors'
        self.assertIn('vintf-incompatible', [e.id for e in kp.find_matches(line)])

    def test_install_failed_matches(self):
        line = 'Failure [INSTALL_FAILED_VERSION_DOWNGRADE]'
        self.assertIn('install-failed', [e.id for e in kp.find_matches(line)])

    def test_apexd_matches(self):
        line = 'E apexd: Failed to activate /data/apex/active/com.android.art@331413030.apex'
        self.assertIn('apexd-fail', [e.id for e in kp.find_matches(line)])

    def test_api_check_matches(self):
        line = 'error: Aborting: Found compatibility problems checking the public API'
        self.assertIn('api-check-failed', [e.id for e in kp.find_matches(line)])

    def test_no_match_on_plain_text(self):
        self.assertEqual(kp.find_matches('D ActivityManager: Displayed com.foo/.Main'), [])

    def test_no_match_on_ordinary_automotive_free_lines(self):
        # Guard against the new automotive regexes over-matching benign lines
        for benign in [
            'I ActivityManager: Start proc 1234:com.example/u0a10',
            'D WifiService: Connected to network',
            'V ViewRootImpl: draw finished',
            'I PackageManager: Package com.example.app installed for user 10',
            'D BluetoothAdapter: isLeEnabled(): ON',
            'I Choreographer: Skipped 3 frames',
            'W Looper: PerfMonitor doFrame: time=18ms',
            'I chatty: uid=1000 system_server expire 5 lines',
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

    def test_adas_property_matches(self):
        line = 'E CarPropertyService: subscribe CRUISE_CONTROL_STATE failed: permission'
        ids = [e.id for e in kp.find_matches(line)]
        self.assertIn('vhal-prop-cruise_control_state', ids)

    def test_wiper_property_matches(self):
        ctx = kp.retrieve_context('W VehicleHal: WINDSHIELD_WIPERS_SWITCH set rejected')
        self.assertIn('WINDSHIELD_WIPERS_SWITCH', ctx)
        self.assertIn('CONTROL_WINDSHIELD_WIPERS', ctx)

    def test_switch_state_pair_distinct(self):
        # HEADLIGHTS_SWITCH must not be shadowed by HEADLIGHTS_STATE or vice versa
        names = kp._find_vhal_property_names('HEADLIGHTS_SWITCH set while HEADLIGHTS_STATE off')
        self.assertIn('HEADLIGHTS_SWITCH', names)
        self.assertIn('HEADLIGHTS_STATE', names)


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
