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


def find_matches(text, limit=4):
    """Return knowledge entries whose signature matches `text`.

    Preserves pack order (most-specific first), dedups by id, caps at `limit`.
    """
    if not text:
        return []
    matches = []
    for entry in KNOWLEDGE:
        if entry.signature.search(text):
            matches.append(entry)
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
