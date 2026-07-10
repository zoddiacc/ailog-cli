"""
Curated AOSP / Android Automotive knowledge pack.

The intelligence of AILog does not live in the model's weights — a small local
model (e.g. qwen2.5-coder:3b) knows little about VHAL, CarService, SELinux, or
tombstones. It lives here, as verified reference facts keyed by log signatures.

Two consumers use this data:

1. Deterministic path (no AI): `lookup_hint()` returns an instant, always-correct
   one-liner for a matching log line — used by line_hints.
2. Retrieval-augmented path (AI): `retrieve_context()` returns the matching facts
   as an authoritative context block injected into the AI prompt, so even a weak
   local model summarizes known-good knowledge instead of guessing.

Adding an entry is pure data — no code changes. Keep `guidance` accurate and
concise; a wrong fact is worse than none because it is presented as authoritative.
"""

import re
from collections import namedtuple

# id       : stable slug (used for dedup and tests)
# category : grouping shown to the user (e.g. "SELinux", "VHAL")
# signature: compiled regex matched against log text
# hint     : short one-liner for the no-AI path (line_hints)
# guidance : 1-3 sentence authoritative fact injected into AI prompts
KnowledgeEntry = namedtuple(
    'KnowledgeEntry', ['id', 'category', 'signature', 'hint', 'guidance']
)


def _entry(id, category, pattern, hint, guidance, flags=re.IGNORECASE):
    return KnowledgeEntry(id, category, re.compile(pattern, flags), hint, guidance)


# Ordered most-specific first so domain matches win over generic ones.
KNOWLEDGE = [
    # ---------------- Android Automotive: VHAL ----------------
    _entry(
        'vhal-not-available', 'VHAL',
        r'(?:StatusCode[:\s]*)?NOT_AVAILABLE(?:_\w+)?',
        'VHAL property not available in the current vehicle state',
        'A VHAL call returned StatusCode NOT_AVAILABLE: the property exists but '
        'cannot be read/written right now — often the feature is disabled, the '
        'vehicle is in a state that blocks it (e.g. engine off), or the HAL has '
        'not populated it yet. Check the property\'s area/config and the vehicle '
        'state gating it; this is a state issue, not a crash.',
    ),
    _entry(
        'vhal-set-failed', 'VHAL',
        r'(?:VehicleHal|PropertyHalService|CarPropertyService).*(?:set|write).*(?:fail|error|denied)',
        'VHAL setProperty failed',
        'A VHAL write failed. Common causes: the property is read-only, the area '
        'ID does not match the property\'s supported areas, the value is out of '
        'the configured min/max range, or the caller lacks the required '
        'car permission. Verify area IDs and the VehiclePropConfig for this property.',
    ),
    _entry(
        'vhal-prop-config', 'VHAL',
        r'(?:getPropConfigs|VehiclePropConfig|property\s+0x[0-9a-fA-F]+).*(?:unsupported|not\s+found|no\s+config)',
        'VHAL property has no config / is unsupported by this HAL',
        'The referenced vehicle property has no VehiclePropConfig, so the HAL on '
        'this build does not support it. Confirm the property ID against the '
        'VehicleProperty definitions and that the vendor VHAL implements it; '
        'app code should query supported properties before using them.',
    ),
    _entry(
        'vhal-area-id', 'VHAL',
        r'IllegalArgumentException.*area|(?:invalid|wrong|unknown)\s+area\s*id|areaId\s+\S+\s+(?:not|is not)\s+(?:supported|valid)',
        'Wrong VHAL areaId for the property',
        'A VHAL access used an areaId the property does not define. Zoned '
        'properties (per-seat, per-door, per-window) only accept the area IDs '
        'listed in their VehicleAreaConfig; global properties must use areaId 0. '
        'Read the property\'s areaConfigs and pass a matching area, not a guessed bitmask.',
    ),
    _entry(
        'vhal-permission', 'VHAL',
        r'(?:SecurityException|permission).*(?:android\.car\.permission|Car\.PERMISSION)|requires?\s+.*android\.car\.permission',
        'VHAL/Car property needs a specific car permission',
        'Reading/writing this property requires a dedicated car permission (e.g. '
        'android.car.permission.CONTROL_CAR_CLIMATE). Many are signature|privileged, '
        'so the app must be a privileged/preinstalled app AND allowlisted in a '
        'permissions XML — a normal runtime grant is not enough. Vendor properties '
        'need the matching VENDOR permission mapped in the VHAL.',
    ),
    _entry(
        'vhal-subscribe-rate', 'VHAL',
        r'subscribe.*(?:rate|sample).*(?:invalid|out of range|too high)|(?:max|min)SampleRate',
        'VHAL subscribe sample rate out of the property\'s allowed range',
        'A continuous VHAL property can only be subscribed between its minSampleRate '
        'and maxSampleRate (from its config); an out-of-range rate is rejected. On-'
        'change properties cannot be sampled at a rate at all — subscribe with '
        'onChange semantics instead of a fixed Hz.',
    ),

    # ---------------- Android Automotive: Car framework ----------------
    _entry(
        'car-watchdog-kill', 'CarWatchdog',
        r'(?:CarWatchdog|carwatchdog).*(?:kill|terminat|not\s+respond|unresponsive|overuse)',
        'CarWatchdog killed a process (health-check miss or I/O overuse)',
        'CarWatchdog terminated a process because it either stopped answering '
        'health-check pings (an ANR-equivalent for services) or exceeded its '
        'disk-I/O quota. Fix by responding to CarWatchdogManager health checks on '
        'time and reducing background disk writes; do not just raise the quota.',
    ),
    _entry(
        'car-service-restart', 'CarService',
        r'(?:CarServiceHelper|car_service|CarService).*(?:crash|restart|died|reconnect)',
        'CarService crashed or restarted',
        'CarService (the Car API system service) crashed or was restarted; when it '
        'dies, Car*Manager clients get DeadObjectException and must reconnect. Look '
        'earlier in the log for the original CarService exception or native crash — '
        'that is the real fault, not the reconnect messages that follow.',
    ),
    _entry(
        'car-audio', 'CarAudio',
        r'(?:CarAudioService|audioserver).*(?:died|fail|error|zone|focus)',
        'Car audio service error (focus/zone/audioserver)',
        'A CarAudioService or audioserver error. In automotive, audio is split into '
        'zones and controlled by audio focus; failures are usually a focus request '
        'rejected, a missing/misconfigured audio zone, or audioserver having died '
        '(which restarts and drops active tracks). Check the car_audio_configuration '
        'XML and the focus request outcome.',
    ),
    _entry(
        'car-audio-zone-config', 'CarAudio',
        r'car_audio_configuration|CarAudioZone|audio\s+zone\s+\d|no\s+context.*audio',
        'Car audio zone / configuration problem',
        'Automotive audio routing is defined in car_audio_configuration.xml, which '
        'maps each audio zone to physical output devices and assigns each audio '
        'context (MUSIC, NAVIGATION, VOICE_COMMAND, etc.) to a volume group. A '
        'malformed or mismatched config — a device address that does not exist, a '
        'context with no group — makes zones fail to initialize. Validate the XML '
        'against the actual audio_policy device addresses.',
    ),
    _entry(
        'audiocontrol-hal', 'CarAudio',
        r'IAudioControl|audiocontrol.*(?:HAL|hal)|AudioControl.*(?:died|fail|error)',
        'AudioControl HAL error (ducking/gain/routing)',
        'The AudioControl HAL (android.hardware.automotive.audiocontrol) implements '
        'OEM audio ducking, gain, and mute callbacks for CarAudioService. If it dies '
        'or returns errors, focus-based ducking and hardware gain changes stop '
        'working. Check the vendor audiocontrol HAL service and its selinux domain.',
    ),

    # ---------------- Android Automotive: Car API connection & permissions ----------------
    _entry(
        'car-not-connected', 'Car API',
        r'CarNotConnectedException|Car\s+not\s+connected|IllegalStateException.*Car.*not\s+connected',
        'Car API used while not connected to CarService',
        'A Car*Manager was used before Car connected, or after CarService died and '
        'the Car object disconnected. Create Car with Car.createCar() using a '
        'CarServiceLifecycleListener (or check Car.isConnected()), and re-acquire '
        'managers on reconnect — a cached manager becomes stale once CarService '
        'restarts.',
    ),
    _entry(
        'car-permission-denied', 'Car API',
        r'(?:SecurityException|Permission Denial).*(?:android\.car\.permission|CarService)|does not have.*android\.car\.permission',
        'Car permission denied — likely a privileged/allowlist gap',
        'The caller lacks a required android.car.permission. Most car permissions are '
        'protectionLevel signature|privileged, so the app must be installed as a '
        'privileged app (priv-app) AND listed in a privileged-permission allowlist '
        'XML under etc/permissions; otherwise the grant is denied even after '
        'requesting it. Confirm the app\'s install location and allowlist entry.',
    ),

    # ---------------- Android Automotive: power management ----------------
    _entry(
        'car-power-state', 'CarPower',
        r'AP_POWER_STATE|CarPowerManagement|\bCPMS\b|PowerState.*(?:SHUTDOWN_PREPARE|WAIT_FOR_VHAL|SUSPEND|ON)',
        'Car power state transition (CPMS ↔ VHAL)',
        'CarPowerManagementService drives power state via the VHAL AP_POWER_STATE_REQ '
        '(vehicle→Android request) and AP_POWER_STATE_REPORT (Android→vehicle ack) '
        'properties. Stuck transitions are usually a component not finishing its '
        'power-state callback in time, or the VHAL not sending the expected request; '
        'trace which listener has not reported completion.',
    ),
    _entry(
        'garage-mode', 'CarPower',
        r'[Gg]arage\s*[Mm]ode',
        'Garage Mode — background maintenance window during shutdown/suspend',
        'Garage Mode is the window entered during SHUTDOWN_PREPARE where the system '
        'runs deferred background jobs (updates, uploads) before fully powering off '
        'or suspending. If it hangs, shutdown is blocked: look for a long-running '
        'JobScheduler job that never completes or a component not acknowledging the '
        'power-state change.',
    ),
    _entry(
        'suspend-str', 'CarPower',
        r'[Ss]uspend[- ]to[- ]RAM|deep\s+sleep|SystemSuspend|enterDeepSleep|failed to (?:enter )?suspend',
        'Suspend-to-RAM / deep sleep issue',
        'AAOS commonly suspends to RAM (deep sleep) rather than shutting down. A '
        'failure to suspend is usually a held wakelock or a driver blocking the '
        'suspend path; a failure to resume points at a wakeup-source or VHAL '
        'resume-signal problem. Check /sys/power/wakeup_sources and which wakelock '
        'is active at suspend time.',
    ),

    # ---------------- Android Automotive: users, input, displays ----------------
    _entry(
        'car-user-switch', 'CarUser',
        r'CarUserService|user\s+HAL|InitialUserSetting|switchUser|headless\s+system\s+user',
        'Car user management / switching issue',
        'AAOS boots headless: the system user (user 0) runs no UI, and a real driver '
        'user is created/switched into. User switches are coordinated with the user '
        'HAL (INITIAL_USER_INFO / SWITCH_USER). Failures ("no foreground user", '
        'switch timeout) usually mean the user HAL did not respond or a blocking '
        'user-lifecycle listener stalled the switch.',
    ),
    _entry(
        'car-input-rotary', 'CarInput',
        r'CarInputService|RotaryService|\brotary\b',
        'Car input / rotary controller issue',
        'Rotary and hardware-key input in AAOS flows through CarInputService and '
        '(for rotary) RotaryService, which moves focus between focusable views. '
        'Problems are usually focus getting lost (no FocusArea/FocusParkingView in '
        'the layout, from car-ui-lib) or key events not mapped to the intended '
        'CarInputManager target.',
    ),
    _entry(
        'car-cluster', 'CarCluster',
        r'InstrumentCluster|ClusterHomeService|ClusterRenderingService|ClusterOsDoubleService',
        'Instrument cluster display/service issue',
        'The instrument cluster (speed/RPM/nav behind the wheel) is driven by the '
        'cluster services (ClusterHomeService / InstrumentClusterRenderingService). '
        'Blank or frozen clusters are usually the cluster display not registered, '
        'the cluster activity failing to launch on its display, or navigation state '
        'not being forwarded from the nav app.',
    ),
    _entry(
        'car-evs', 'CarEVS',
        r'CarEvsService|\bEVS\b|evs.*(?:camera|stream|buffer)|rearview\s+camera',
        'EVS (rearview / surround camera) issue',
        'EVS (Exterior View System) shows the rearview/surround camera, and must '
        'appear within ~2s of reverse gear — often before Android is fully booted — '
        'via the EVS HAL, EVS manager, and CarEvsService. Failures are usually the '
        'camera stream not starting, buffer starvation, or the EVS HAL not being '
        'brought up early enough in init.',
    ),

    # ---------------- Android Automotive: services ----------------
    _entry(
        'car-telemetry', 'CarTelemetry',
        r'CarTelemetry',
        'CarTelemetryService issue',
        'CarTelemetryService collects on-device metrics by running MetricsConfig '
        'scripts against published data (VHAL, connectivity, memory). Errors are '
        'usually a malformed MetricsConfig, a script referencing an unavailable '
        'publisher, or results not being pulled before they expire.',
    ),
    _entry(
        'car-vms', 'VMS',
        r'\bVMS\b|VmsClientManager|VmsSubscriberManager|Vehicle Map Service',
        'Vehicle Map Service (VMS) messaging issue',
        'VMS is a publish/subscribe layer (over a VHAL property) for sharing map/ADAS '
        'layers between apps and the platform. Failures are usually a publisher/'
        'subscriber layer/version mismatch or a client not registered before '
        'publishing; check the layer availability and that both sides agree on the '
        'layer ID and version.',
    ),

    # ---------------- SELinux ----------------
    _entry(
        'selinux-denial', 'SELinux',
        r'avc:\s*denied\s*\{\s*(?P<perm>[^}]+)\}.*?scontext=(?P<scontext>\S+).*?tcontext=(?P<tcontext>\S+).*?tclass=(?P<tclass>\S+)',
        'SELinux denied an operation — needs an sepolicy allow rule',
        'An `avc: denied` line means the kernel blocked an action under SELinux. '
        'Read it as: the domain in scontext tried the operation(s) in { } on the '
        'type in tcontext of object class tclass. Fix by adding an allow rule to '
        'the scontext domain\'s .te file (form: `allow <scontext_domain> '
        '<tcontext_type>:<tclass> <perm>;`), or generate a starting point with '
        'audit2allow. Never set SELinux permissive to "fix" a denial.',
    ),
    _entry(
        'selinux-neverallow', 'SELinux',
        r'neverallow.*violat|violates?\s+.*neverallow',
        'SELinux neverallow violation — cannot be allowed, must redesign',
        'A neverallow rule was violated at policy build time. Unlike a normal '
        'denial, you CANNOT add an allow rule — neverallow encodes a security '
        'invariant. The access must be removed or moved to a domain that is '
        'permitted to perform it; re-architect rather than trying to grant it.',
    ),

    # ---------------- Native crashes / tombstones ----------------
    _entry(
        'native-sigsegv', 'Native crash',
        r'signal\s+11\s*\(SIGSEGV\)|Fatal signal 11',
        'Native crash: SIGSEGV (invalid memory access)',
        'A native process hit SIGSEGV — a bad memory access (null/dangling pointer, '
        'use-after-free, buffer overrun). In the tombstone, read `fault addr` (0x0 '
        'implies a null deref), the `abort message` if any, and the top backtrace '
        'frames. Symbolize with `ndk-stack -sym out/target/.../symbols` or '
        'development/scripts/stack to turn addresses into file:line.',
    ),
    _entry(
        'native-sigabrt', 'Native crash',
        r'signal\s+6\s*\(SIGABRT\)|Fatal signal 6',
        'Native crash: SIGABRT (abort — often a failed CHECK/assert)',
        'SIGABRT means the process called abort() — usually a failed CHECK/LOG(FATAL), '
        'a C++ exception, or libc detecting heap corruption. The `abort message:` line '
        'in the tombstone is the most important clue; read it first, then the top '
        'backtrace frames after the abort machinery.',
    ),
    _entry(
        'tombstone', 'Native crash',
        r'\*\*\* \*\*\*|Build fingerprint:|backtrace:',
        'Tombstone (native crash dump) — symbolize the backtrace',
        'This is a tombstone: a native crash dump. Key fields are the signal and '
        'fault address, the abort message, and the backtrace. Frame #00 is where it '
        'died; symbolize the stack (ndk-stack / stack script) against the matching '
        'build\'s symbols to get function:line, and correlate the pid/tid with the '
        'logcat lines just before the crash.',
    ),

    # ---------------- Binder / IPC ----------------
    _entry(
        'binder-transaction-failed', 'Binder',
        r'binder.*transaction\s+failed|FAILED_TRANSACTION|transaction\s+failed,?\s*-28',
        'Binder transaction failed (often payload too large or dead peer)',
        'A binder transaction failed. Error -28 (FAILED_TRANSACTION) is usually a '
        'TransactionTooLargeException — the parcel exceeded the ~1MB binder buffer; '
        'reduce the data passed (paginate, use a ContentProvider/shared memory/file). '
        'Error -32 (DEAD_OBJECT) means the remote process died — handle reconnection.',
    ),
    _entry(
        'binder-dead-object', 'Binder',
        r'DeadObjectException|DEAD_OBJECT|Transaction failed.*-32',
        'Binder call to a process that has died',
        'DeadObjectException / DEAD_OBJECT means the remote service or system process '
        'you called has crashed. Find the real fault (that process\'s crash earlier '
        'in the log), and make the client resilient: catch it, and re-acquire the '
        'binder / re-register callbacks after the service restarts.',
    ),

    # ---------------- system_server / stability ----------------
    _entry(
        'watchdog-kill', 'Watchdog',
        r'Watchdog.*(?:WATCHDOG KILLING|blocked|timed?\s*out)',
        'system_server Watchdog killed a blocked thread (likely deadlock)',
        'The system_server Watchdog fired because a monitored thread held a lock or '
        'was blocked for ~60s, and it killed system_server (a full soft reboot). Read '
        'the "blocked in handler on" / attached stacks in the dump: it is usually a '
        'deadlock or a slow synchronous binder call on a critical lock. Fix the '
        'blocking call, not the timeout.',
    ),
    _entry(
        'lmkd-kill', 'Memory',
        r'lowmemorykiller|lmkd.*kill|Kill\s+.*oom_score_adj',
        'Low-memory killer reclaimed a process under memory pressure',
        'lmkd (the low-memory killer) killed a process to relieve memory pressure, '
        'choosing victims by oom_score_adj (higher adj = killed first). Frequent '
        'kills of foreground/perceptible processes indicate a system-wide memory '
        'shortage or a leak; check per-process RSS and whether a service is growing '
        'unbounded, rather than treating the kill as the root cause.',
    ),
    _entry(
        'init-service-exit', 'init/boot',
        r'init:\s*Service\s+\'?\S+\'?.*(?:exited|killed|restart)',
        'init service exited / is being restarted during boot',
        'An init-managed native service exited and init is (re)starting it per its '
        '.rc definition. Repeated restarts (crash loop) usually mean a missing '
        'dependency, a failed SELinux transition, or a fatal error at startup — look '
        'for that service\'s own logs and any avc denials for its domain just before '
        'the exit.',
    ),

    # ---------------- Build (soong / ninja / linker / sepolicy) ----------------
    _entry(
        'ninja-subcommand-failed', 'Build',
        r'ninja:\s*build stopped:\s*subcommand failed',
        'Build stopped — the real error is the FAILED: line above',
        'This ninja line only reports that some build action failed; it is not the '
        'error itself. Scroll UP to the first `FAILED:` block — that command and its '
        'stderr are the actual root cause. In AOSP, filter the build log for '
        '`FAILED:` and `error:` to find it quickly.',
    ),
    _entry(
        'linker-undefined-reference', 'Build',
        r'undefined reference to|error:\s*ld returned|cannot find -l\S+',
        'Linker error: a symbol or library is missing from the module',
        'A link step could not resolve a symbol or library. In the module\'s '
        'Android.bp, add the providing library to `shared_libs` or `static_libs` '
        '(and ensure its headers are in `header_libs`/`export_include_dirs`). '
        '"undefined reference" = missing lib in the deps; "cannot find -lX" = the '
        'library target itself is not built or named differently.',
    ),
    _entry(
        'soong-missing-module', 'Build',
        r'(?:module\s+"[^"]+"\s+not found|Can\'t find|no module named).*|error:.*depends on undefined module',
        'Soong cannot find a referenced module',
        'Soong could not resolve a module dependency — the name in deps/shared_libs '
        'does not match any defined module. Check for a typo, a missing Android.bp, '
        'or a module gated behind a soong_config/product variable that is off for '
        'this lunch target.',
    ),
]

# Fast fail: guarantees the pack is well-formed (also asserted by tests).
_SEEN_IDS = set()
for _e in KNOWLEDGE:
    assert _e.id not in _SEEN_IDS, f"duplicate knowledge id: {_e.id}"
    _SEEN_IDS.add(_e.id)
del _SEEN_IDS


# ---------------------------------------------------------------------------
# VHAL property reference table.
#
# Keyed by VehicleProperty name (as it appears in logs). Values are
# (short_summary, full_guidance). Kept as a table rather than one regex per
# property so it scales to hundreds of entries with a single combined match.
# Facts come from the stable public VehicleProperty / VehiclePropertyIds API;
# tools/gen_vhal_knowledge.py regenerates/extends this from an AOSP tree.
# ---------------------------------------------------------------------------
VHAL_PROPERTIES = {
    # --- Powertrain (Car.PERMISSION_POWERTRAIN, read) ---
    'GEAR_SELECTION': ('gear the driver selected (P/R/N/D/manual)',
        'GEAR_SELECTION is the gear the driver selected (P/R/N/D or a manual gear). '
        'Read-only, requires Car.PERMISSION_POWERTRAIN. Use CURRENT_GEAR for the gear '
        'actually engaged, which can differ during shifts.'),
    'CURRENT_GEAR': ('gear currently engaged by the transmission',
        'CURRENT_GEAR is the gear the transmission has actually engaged (vs the '
        'driver-selected GEAR_SELECTION). Read-only, requires Car.PERMISSION_POWERTRAIN.'),
    'PARKING_BRAKE_ON': ('parking brake engaged (bool)',
        'PARKING_BRAKE_ON is true when the parking brake is engaged. Read-only, '
        'requires Car.PERMISSION_POWERTRAIN.'),
    'IGNITION_STATE': ('ignition position (LOCK/OFF/ACC/ON/START)',
        'IGNITION_STATE reports the ignition switch position: UNDEFINED, LOCK, OFF, '
        'ACC, ON, or START. Read-only, requires Car.PERMISSION_POWERTRAIN.'),

    # --- Speed / motion ---
    'PERF_VEHICLE_SPEED': ('vehicle speed in m/s',
        'PERF_VEHICLE_SPEED is the vehicle speed in meters/second (negative when '
        'moving in reverse). Read-only, requires Car.PERMISSION_SPEED.'),
    'PERF_VEHICLE_SPEED_DISPLAY': ('speed shown on the cluster',
        'PERF_VEHICLE_SPEED_DISPLAY is the speed shown to the driver, which may '
        'intentionally differ from PERF_VEHICLE_SPEED. Read-only, Car.PERMISSION_SPEED.'),
    'PERF_ODOMETER': ('total distance traveled (meters)',
        'PERF_ODOMETER is the odometer reading in meters. Read-only, requires '
        'Car.PERMISSION_MILEAGE.'),
    'PERF_STEERING_ANGLE': ('front wheel steering angle (degrees)',
        'PERF_STEERING_ANGLE is the front-wheel angle in degrees (left negative). '
        'Read-only, requires Car.PERMISSION_READ_STEERING_STATE.'),

    # --- Engine (Car.PERMISSION_CAR_ENGINE_DETAILED, read) ---
    'ENGINE_RPM': ('engine speed (RPM)',
        'ENGINE_RPM is engine revolutions per minute. Read-only, requires '
        'Car.PERMISSION_CAR_ENGINE_DETAILED.'),
    'ENGINE_OIL_TEMP': ('engine oil temperature (°C)',
        'ENGINE_OIL_TEMP is engine oil temperature in Celsius. Read-only, requires '
        'Car.PERMISSION_CAR_ENGINE_DETAILED.'),
    'ENGINE_COOLANT_TEMP': ('engine coolant temperature (°C)',
        'ENGINE_COOLANT_TEMP is coolant temperature in Celsius. Read-only, requires '
        'Car.PERMISSION_CAR_ENGINE_DETAILED.'),

    # --- Energy: fuel & EV (Car.PERMISSION_ENERGY, read) ---
    'FUEL_LEVEL': ('current fuel in milliliters',
        'FUEL_LEVEL is remaining fuel in milliliters (never exceeds '
        'INFO_FUEL_CAPACITY). Read-only, requires Car.PERMISSION_ENERGY.'),
    'FUEL_LEVEL_LOW': ('low-fuel warning (bool)',
        'FUEL_LEVEL_LOW is the low-fuel warning flag and applies to both fuel and EV '
        'battery. Read-only, requires Car.PERMISSION_ENERGY.'),
    'RANGE_REMAINING': ('remaining driving range (meters)',
        'RANGE_REMAINING is remaining range in meters across all energy sources. '
        'Read requires Car.PERMISSION_ENERGY; writing it (for range estimation apps) '
        'requires Car.PERMISSION_ADJUST_RANGE_REMAINING.'),
    'EV_BATTERY_LEVEL': ('current EV battery energy (Wh)',
        'EV_BATTERY_LEVEL is the current usable battery energy in Watt-hours (not a '
        'percentage). Read-only, requires Car.PERMISSION_ENERGY.'),
    'EV_BATTERY_INSTANTANEOUS_CHARGE_RATE': ('instantaneous charge/discharge (W)',
        'EV_BATTERY_INSTANTANEOUS_CHARGE_RATE is the instantaneous charging (positive) '
        'or discharging (negative) rate in Watts. Read-only, Car.PERMISSION_ENERGY.'),
    'EV_CHARGE_STATE': ('EV charging state',
        'EV_CHARGE_STATE reports whether the vehicle is charging, fully charged, or '
        'not charging. Read-only, requires Car.PERMISSION_ENERGY.'),

    # --- Energy ports (Car.PERMISSION_ENERGY_PORTS, read) ---
    'FUEL_DOOR_OPEN': ('fuel door open (bool)',
        'FUEL_DOOR_OPEN is true when the fuel filler door is open. Read requires '
        'Car.PERMISSION_ENERGY_PORTS; write requires Car.PERMISSION_CONTROL_ENERGY_PORTS.'),
    'EV_CHARGE_PORT_OPEN': ('EV charge port open (bool)',
        'EV_CHARGE_PORT_OPEN is true when the charge port is open. Read requires '
        'Car.PERMISSION_ENERGY_PORTS; write requires Car.PERMISSION_CONTROL_ENERGY_PORTS.'),
    'EV_CHARGE_PORT_CONNECTED': ('EV charge connector plugged in (bool)',
        'EV_CHARGE_PORT_CONNECTED is true when a charge connector is physically '
        'plugged in. Read-only, requires Car.PERMISSION_ENERGY_PORTS.'),

    # --- Vehicle info (Car.PERMISSION_CAR_INFO, read, STATIC) ---
    'INFO_MAKE': ('vehicle manufacturer (static)',
        'INFO_MAKE is the manufacturer string. Static/read-only, requires '
        'Car.PERMISSION_CAR_INFO.'),
    'INFO_MODEL': ('vehicle model (static)',
        'INFO_MODEL is the model string. Static/read-only, requires '
        'Car.PERMISSION_CAR_INFO.'),
    'INFO_FUEL_TYPE': ('supported fuel types (static)',
        'INFO_FUEL_TYPE lists the fuel types the vehicle supports. Static/read-only, '
        'requires Car.PERMISSION_CAR_INFO.'),
    'INFO_EV_CONNECTOR_TYPE': ('supported EV connector types (static)',
        'INFO_EV_CONNECTOR_TYPE lists supported EV charge connector types. Static/'
        'read-only, requires Car.PERMISSION_CAR_INFO.'),
    'INFO_VIN': ('vehicle identification number (static)',
        'INFO_VIN is the VIN. Static/read-only, and unlike other INFO_* it requires '
        'the more restricted Car.PERMISSION_IDENTIFICATION.'),

    # --- HVAC / climate (Car.PERMISSION_CONTROL_CAR_CLIMATE, read/write) ---
    'HVAC_TEMPERATURE_SET': ('target cabin temperature per zone',
        'HVAC_TEMPERATURE_SET is the target temperature for an HVAC zone; it is zoned, '
        'so writes must target a valid seat areaId. Read/write, requires '
        'Car.PERMISSION_CONTROL_CAR_CLIMATE.'),
    'HVAC_FAN_SPEED': ('fan speed level per zone',
        'HVAC_FAN_SPEED is the fan speed for a zone. Zoned read/write, requires '
        'Car.PERMISSION_CONTROL_CAR_CLIMATE; HVAC_POWER_ON must be on for it to apply.'),
    'HVAC_FAN_DIRECTION': ('airflow direction per zone',
        'HVAC_FAN_DIRECTION selects airflow direction (face/floor/defrost/combinations) '
        'from HVAC_FAN_DIRECTION_AVAILABLE. Zoned read/write, Car.PERMISSION_CONTROL_CAR_CLIMATE.'),
    'HVAC_AC_ON': ('air conditioning compressor on (bool)',
        'HVAC_AC_ON toggles the A/C compressor. Read/write, requires '
        'Car.PERMISSION_CONTROL_CAR_CLIMATE.'),
    'HVAC_POWER_ON': ('HVAC master power for a zone (bool)',
        'HVAC_POWER_ON is the master power for an HVAC zone; when off, the dependent '
        'properties (fan, A/C, temperature) do not take effect. Read/write, '
        'Car.PERMISSION_CONTROL_CAR_CLIMATE. Check HVAC_POWER_ON first when a climate write "does nothing".'),
    'HVAC_DEFROSTER': ('windshield defroster per window (bool)',
        'HVAC_DEFROSTER controls the defroster for a window area. Zoned read/write, '
        'requires Car.PERMISSION_CONTROL_CAR_CLIMATE.'),
    'HVAC_AUTO_ON': ('automatic climate control (bool)',
        'HVAC_AUTO_ON enables automatic climate control. Read/write, requires '
        'Car.PERMISSION_CONTROL_CAR_CLIMATE.'),

    # --- Body ---
    'DOOR_LOCK': ('door lock state per door (bool)',
        'DOOR_LOCK is the lock state of a door (true = locked). Zoned read/write, '
        'requires Car.PERMISSION_CONTROL_CAR_DOORS.'),
    'DOOR_POS': ('door open position per door',
        'DOOR_POS is a door\'s open position (0 = closed). Zoned read/write, requires '
        'Car.PERMISSION_CONTROL_CAR_DOORS.'),
    'WINDOW_POS': ('window position per window',
        'WINDOW_POS is a window\'s position (0 = fully closed). Zoned read/write, '
        'requires Car.PERMISSION_CONTROL_CAR_WINDOWS.'),
    'SEAT_BELT_BUCKLED': ('seatbelt buckled per seat (bool)',
        'SEAT_BELT_BUCKLED is true when a seat\'s belt is buckled. Zoned, requires '
        'Car.PERMISSION_CONTROL_CAR_SEATS.'),

    # --- Tires (Car.PERMISSION_TIRES, read) ---
    'TIRE_PRESSURE': ('tire pressure per wheel (kPa)',
        'TIRE_PRESSURE is per-wheel pressure in kPa (zoned by tire). Read-only, '
        'requires Car.PERMISSION_TIRES.'),
    'CRITICALLY_LOW_TIRE_PRESSURE': ('critically low tire pressure per wheel',
        'CRITICALLY_LOW_TIRE_PRESSURE is the manufacturer\'s critical-low threshold '
        'per wheel (below which driving is unsafe). Read-only, Car.PERMISSION_TIRES.'),

    # --- Dynamics (Car.PERMISSION_CAR_DYNAMICS_STATE, read) ---
    'ABS_ACTIVE': ('ABS currently engaged (bool)',
        'ABS_ACTIVE is true while the anti-lock braking system is actively modulating. '
        'Read-only, requires Car.PERMISSION_CAR_DYNAMICS_STATE.'),
    'TRACTION_CONTROL_ACTIVE': ('traction control engaged (bool)',
        'TRACTION_CONTROL_ACTIVE is true while traction control is intervening. '
        'Read-only, requires Car.PERMISSION_CAR_DYNAMICS_STATE.'),

    # --- Environment & lights ---
    'ENV_OUTSIDE_TEMPERATURE': ('outside air temperature (°C)',
        'ENV_OUTSIDE_TEMPERATURE is the outside temperature in Celsius. Read-only, '
        'requires Car.PERMISSION_EXTERIOR_ENVIRONMENT.'),
    'NIGHT_MODE': ('day/night mode for UI dimming (bool)',
        'NIGHT_MODE is true when the car signals night — used to switch UI to a dark/'
        'dimmed theme. Read-only, requires Car.PERMISSION_EXTERIOR_ENVIRONMENT. If the '
        'UI does not dim at night, verify apps subscribe to this property.'),
    'TURN_SIGNAL_STATE': ('turn signal state (none/left/right)',
        'TURN_SIGNAL_STATE reports the active turn indicator. Read-only, requires '
        'Car.PERMISSION_EXTERIOR_LIGHTS.'),
    'HEADLIGHTS_STATE': ('headlight state',
        'HEADLIGHTS_STATE reports the current headlight state. Read-only, requires '
        'Car.PERMISSION_EXTERIOR_LIGHTS; the *_SWITCH property (write) needs '
        'Car.PERMISSION_CONTROL_EXTERIOR_LIGHTS.'),

    # --- Display units (Car.PERMISSION_READ_DISPLAY_UNITS, read) ---
    'DISTANCE_DISPLAY_UNITS': ('distance unit (km/mi) shown to driver',
        'DISTANCE_DISPLAY_UNITS is the distance unit shown to the driver. Read requires '
        'Car.PERMISSION_READ_DISPLAY_UNITS; write requires '
        'Car.PERMISSION_CONTROL_DISPLAY_UNITS. It is a global setting, so writes should '
        'use areaId 0.'),
    'FUEL_VOLUME_DISPLAY_UNITS': ('fuel volume unit (L/gal) shown to driver',
        'FUEL_VOLUME_DISPLAY_UNITS is the fuel-volume unit shown to the driver. Read '
        'Car.PERMISSION_READ_DISPLAY_UNITS; write Car.PERMISSION_CONTROL_DISPLAY_UNITS.'),

    # --- Input & power ---
    'HW_KEY_INPUT': ('hardware key event from the car',
        'HW_KEY_INPUT delivers hardware key events (steering-wheel/dash buttons) to '
        'Android via VHAL; CarInputService dispatches them. Used by the platform, not '
        'normal apps.'),
    'HW_ROTARY_INPUT': ('rotary controller input event',
        'HW_ROTARY_INPUT delivers rotary-controller events; RotaryService turns them '
        'into focus movement. Missing rotary navigation usually means the app layout '
        'lacks car-ui-lib FocusArea/FocusParkingView, not a VHAL problem.'),
    'DISPLAY_BRIGHTNESS': ('main display brightness',
        'DISPLAY_BRIGHTNESS is the vehicle-controlled brightness of the main display '
        '(used to sync Android brightness with the car). Platform property.'),
}

# One combined regex over all property names (longest-first so e.g.
# PERF_VEHICLE_SPEED_DISPLAY matches before PERF_VEHICLE_SPEED).
_VHAL_PROP_RE = re.compile(
    r'\b(' + '|'.join(sorted((re.escape(k) for k in VHAL_PROPERTIES), key=len, reverse=True)) + r')\b'
)


def _property_entry(name):
    """Synthesize a KnowledgeEntry from the VHAL property table."""
    short, guidance = VHAL_PROPERTIES[name]
    return KnowledgeEntry(
        id=f'vhal-prop-{name.lower()}',
        category='VHAL property',
        signature=_VHAL_PROP_RE,  # unused after synthesis
        hint=f'{name} — {short}',
        guidance=guidance,
    )


def _find_vhal_property_names(text):
    """Distinct VehicleProperty names referenced in text, in order of appearance."""
    seen, out = set(), []
    for m in _VHAL_PROP_RE.finditer(text):
        name = m.group(1)
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def find_matches(text, limit=4):
    """Return knowledge entries matching `text`.

    Signature entries (specific error patterns) come first, then any referenced
    VHAL property facts. Dedups by id, caps at `limit`.
    """
    if not text:
        return []
    matches = []
    seen = set()
    for entry in KNOWLEDGE:
        if entry.signature.search(text):
            matches.append(entry)
            seen.add(entry.id)
            if len(matches) >= limit:
                return matches
    for name in _find_vhal_property_names(text):
        eid = f'vhal-prop-{name.lower()}'
        if eid in seen:
            continue
        matches.append(_property_entry(name))
        seen.add(eid)
        if len(matches) >= limit:
            break
    return matches


def lookup_hint(line):
    """Instant, always-correct one-liner for a single log line, or '' if none.

    Used by the no-AI path (line_hints). Returns the highest-priority match.
    """
    matches = find_matches(line, limit=1)
    if not matches:
        return ''
    return f"[{matches[0].category}] {matches[0].hint}"


def retrieve_context(text, limit=4):
    """Format matching facts as an authoritative context block for AI prompts.

    Returns '' when nothing matches, so callers can prepend it unconditionally.
    """
    matches = find_matches(text, limit=limit)
    if not matches:
        return ''
    lines = [
        'AUTHORITATIVE AOSP/AUTOMOTIVE REFERENCE (verified facts — prefer these '
        'over your own assumptions; ignore any that are irrelevant):',
        '',
    ]
    for e in matches:
        lines.append(f'- [{e.category}] {e.guidance}')
    lines.append('')
    return '\n'.join(lines)
