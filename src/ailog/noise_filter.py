"""
Rule-based noise filter for Android logs.
Applied BEFORE AI to reduce token usage and speed up processing.
"""

import re
from typing import List, Tuple


# Patterns that are ALWAYS noise (never interesting)
ALWAYS_NOISE = [
    # Binder routine traffic
    r'Binder:.*\d+_\d+',
    r'BINDER_WRITE_READ',

    # GC logs (routine)
    r'GC_FOR_ALLOC.*freed',
    r'GC_CONCURRENT.*freed',
    r'GC_EXPLICIT.*freed',
    r'Explicit concurrent.*GC',
    r'Background sticky.*GC',
    r'Background concurrent.*GC freed',
    r'concurrent mark compact GC freed',
    r'Using CollectorType.*GC',
    r'Compiler allocated.*to compile',

    # Routine audio HAL polling
    r'AudioFlinger.*FastMixer.*sleeping',
    r'audio_hw_primary.*out_write',

    # Routine property ops
    r'getprop.*ro\.',
    r'property_get.*persist\.',

    # Verbose Zygote
    r'Zygote.*preload.*took.*ms',
    r'Zygote.*fork',

    # Routine surfaceflinger
    r'SurfaceFlinger.*VSYNC',
    r'HWC.*composition',

    # SELinux denials already handled (audit logs are noise unless critical)
    r'avc:  granted',

    # Network routine
    r'WifiStateMachine.*handleMessage',
    r'ConnectivityService.*updateNetworkScore',

    # Routine ActivityManager lifecycle (non-error)
    r'ActivityManager.*START.*Intent',
    r'ActivityManager.*No longer want',

    # --- Android app UI/framework noise ---

    # View/rendering internals
    r'VRI\[.*\].*onDisplayChanged',
    r'VRI\[.*\].*Relayout returned',
    r'VRI\[.*\].*reportDrawFinished',
    r'VRI\[.*\].*reportNextDraw',
    r'VRI\[.*\].*Setup new sync',
    r'VRI\[.*\].*Creating new active sync',
    r'VRI\[.*\].*registerCallbacksForSync',
    r'VRI\[.*\].*mThreadedRenderer',
    r'VRI\[.*\].*Received frame',
    r'VRI\[.*\].*Setting up sync',
    r'VRI\[.*\].*synced displayState',
    r'VRI\[.*\].*setView',
    r'VRI\[.*\].*performConfigurationChange',
    r'VRI\[.*\].*handleResized',
    r'VRI\[.*\].*handleAppVisibility',
    r'VRI\[.*\].*visibilityChanged',
    r'VRI\[.*\].*stopped\(',
    r'VRI\[.*\].*WindowStopped',
    r'VRI\[.*\].*Not drawing due to',
    r'VRI\[.*\].*dispatchDetachedFromWindow',
    r'VRI\[.*\].*ViewPostIme pointer',
    r'VRI\[.*\].*call setFrameRateCategory',
    r'VRI\[.*\].*mWNT:',
    r'ViewRootImpl.*Skipping stats',

    # HWUI / rendering pipeline
    r'HWUI.*treat.*sRGB',
    r'HWUI.*CacheManager',
    r'HWUI.*setMaxSurfaceArea',
    r'HWUI.*CFMS',
    r'HardwareRenderer.*onDisplayChanged',
    r'HardwareRenderer.*Set largestWidth',

    # BLASTBufferQueue (frame buffer management)
    r'BLASTBufferQueue',

    # Display/graphics setup
    r'DisplayManager.*Choreographer',
    r'GraphicsEnvironment',
    r'DecorView.*setWindowBackground',
    r'NativeCustomFrequencyManager',

    # Input/IME routine
    r'InputTransport.*channel (constructed|destroyed)',
    r'InputMethodManager.*handleMessage',
    r'InputMethodManager.*startInputInner',
    r'InputMethodManagerUtils.*startInputInner',
    r'InsetsController.*hide\(ime',
    r'InsetsSourceConsumer.*applyRequestedVisibility',
    r'InsetsController.*onStateChanged',
    r'ImeFocusController.*onP.*WindowFocus.*skipped',
    r'ImeTracker.*onCancelled',

    # Activity/app lifecycle noise (non-error)
    r'ActivityThread.*setConscryptValidator',
    r'AppCompatDelegate.*Checking for metadata',
    r'CompatChangeReporter.*Compat change id',
    r'DesktopModeFlags.*Toggle override',
    r'WindowOnBackDispatcher',
    r'Activity.*onBackInvoked',

    # Android Studio deploy agent
    r'studio\.deploy',

    # Profile installer
    r'ProfileInstaller',

    # IDS training
    r'IDS_TAG',

    # Nativeloader routine
    r'nativeloader.*Load.*using.*ns',
    r'nativeloader.*Configuring clns',

    # hiddenapi access (warnings, not errors)
    r'hiddenapi.*Accessing hidden method',
    r'hiddenapi.*DexFile.*is in boot class path',

    # Redefining intrinsic method warnings
    r'Redefining intrinsic method',

    # Camera HAL verbose internals
    r'WNC\]',
    r'Unihal\s*:',
    r'Samsung_CameraDeviceSession',
    r'ENN_FRAMEWORK',
    r'IRTA\s*:',
    r'Camera3-Device.*waitUntilDrained',
    r'Camera3-Device.*createStream',
    r'Camera3-Device.*configureStreams',
    r'Camera3-Device.*CameraPerf',
    r'Camera3-Utils',
    r'AidlCamera3-Device',
    r'CameraDeviceClient',
    r'SessionConfigUtils',

    # Verbose logcat itself
    r'^-+$',
    r'^-+ beginning of',
    r'^\s*$',
    r'chatty.*lines?',
]

# Patterns that are ALWAYS important (never filter these)
ALWAYS_KEEP = [
    r'[Ee]rror',
    r'[Ee]xception',
    r'FAILED',
    r'[Ff]ailed',
    r'[Cc]rash',
    r'[Ss]egfault',
    r'fatal',
    r'FATAL',
    r'ANR',
    r'at\s+[\w\.\$]+\(.*\.(?:java|kt):\d+\)',  # Stack trace lines (Java & Kotlin)
    r'[Nn]ull[Pp]ointer',
    r'[Oo]ut[Oo]f[Mm]emory',
    r'[Pp]ermission [Dd]enied',
    r'avc:.*denied',
    r'SIGSEGV',
    r'SIGABRT',
    r'W/System\.err',
    r'E/.*:',

    # Automotive/VHAL specific
    r'VHAL',
    r'VehicleHal',
    r'CarService.*[Ee]rror',
    r'CarAudio.*[Ff]ail',
    r'EvsCamera.*[Ee]rror',

    # Build errors
    r'error:',
    r'undefined reference',
    r'ninja: error',
    r'make.*Error',
    r'ld:',
]

# Build-specific noise
BUILD_NOISE = [
    r'^\[\s*\d+%\] Building.*',      # Progress indicators
    r'^Note: .*uses unchecked.*',     # Java unchecked warnings
    r'^Note: Some input files.*',
    r'^\[.*\] Compiling.*',
    r'^\[.*\] Linking.*',
    r'^\[.*\] Processing.*',
]

# Compile regexes once
_NOISE_RE = [re.compile(p) for p in ALWAYS_NOISE]
_KEEP_RE = [re.compile(p) for p in ALWAYS_KEEP]
_BUILD_NOISE_RE = [re.compile(p) for p in BUILD_NOISE]


class NoiseFilter:
    def __init__(self, noise_level: str = 'medium'):
        """
        noise_level: 'low' (filter little), 'medium', 'high' (filter aggressively)
        """
        self.noise_level = noise_level

    def is_important(self, line: str) -> bool:
        """Check if a line should always be kept."""
        for pattern in _KEEP_RE:
            if pattern.search(line):
                return True
        return False

    def is_noise(self, line: str) -> bool:
        """Check if a line is always noise."""
        if not line.strip():
            return True
        for pattern in _NOISE_RE:
            if pattern.search(line):
                return True
        return False

    def is_build_noise(self, line: str) -> bool:
        for pattern in _BUILD_NOISE_RE:
            if pattern.search(line):
                return True
        return False

    def filter_batch(self, lines: List[str], mode: str = 'logcat') -> Tuple[List[str], int]:
        """
        Filter a batch of lines.
        Returns (kept_lines, filtered_count)
        """
        kept = []
        filtered = 0
        seen = {}  # for deduplication

        for line in lines:
            # Always keep important lines
            if self.is_important(line):
                kept.append(line)
                continue

            # Always drop pure noise
            if self.is_noise(line):
                filtered += 1
                continue

            # Build-specific noise
            if mode == 'build' and self.is_build_noise(line):
                if self.noise_level == 'high':
                    filtered += 1
                    continue

            # Deduplication for medium/high
            if self.noise_level in ('medium', 'high'):
                normalized = self._normalize(line)
                if normalized in seen:
                    seen[normalized] += 1
                    filtered += 1
                    continue
                seen[normalized] = 1

            kept.append(line)

        return kept, filtered

    def _normalize(self, line: str) -> str:
        """Normalize a line for dedup by removing timestamps, PIDs, and hex addresses."""
        # Remove leading timestamp like "01-15 12:34:56.789"
        line = re.sub(r'^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+\s+', '', line)
        # Remove PID/TID like "1234  5678"
        line = re.sub(r'^\s*\d+\s+\d+\s+', '', line)
        # Normalize hex addresses (pointers vary between runs)
        line = re.sub(r'0x[0-9a-fA-F]+', '0xXXXX', line)
        return line.strip()

    def extract_errors_warnings(self, lines: List[str]) -> Tuple[List[str], List[str]]:
        """Extract error and warning lines from a list."""
        errors = []
        warnings = []
        error_re = re.compile(r'.*(error:|ERROR|FAILED|Exception|FATAL|fatal).*', re.IGNORECASE)
        warn_re = re.compile(r'.*(warning:|WARNING|WARN).*', re.IGNORECASE)

        for line in lines:
            if error_re.search(line):
                errors.append(line)
            elif warn_re.search(line):
                warnings.append(line)

        return errors, warnings

    def should_trigger_ai(self, lines: List[str]) -> bool:
        """Decide if a batch of lines warrants an AI call."""
        for line in lines:
            if self.is_important(line):
                return True
            if 'error' in line.lower() or 'exception' in line.lower():
                return True
        return False
