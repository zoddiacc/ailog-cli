"""
Rule-based human-readable hints for Android log lines.
Instant, free — no AI calls. Maps common log patterns to plain-English descriptions.
"""

import re

# (compiled_regex, hint_template) — template can use {0}, {1}... for capture groups
_HINT_RULES = [
    # --- App lifecycle ---
    (re.compile(r'ActivityManager.*START.*cmp=(\S+)'),
     'Launching activity: {0}'),
    (re.compile(r'ActivityManager.*Process (\S+).*has died'),
     'App process died: {0}'),
    (re.compile(r'ActivityThread.*handleBindApplication.*app=(\S+)'),
     'App starting: {0}'),

    # --- Errors & Crashes ---
    (re.compile(r'FATAL EXCEPTION:\s*(\S+)'),
     'App crashed on thread: {0}'),
    (re.compile(r'(java\.\S+Exception):\s*(.*)'),
     '{0}: {1}'),
    (re.compile(r'(android\.\S+Exception):\s*(.*)'),
     '{0}: {1}'),
    (re.compile(r'Process:\s*(\S+),\s*PID:\s*(\d+)'),
     'Crash in app {0} (PID {1})'),
    # Stack trace — only hint on app code, skip android/java/androidx framework frames
    (re.compile(r'at\s+((?!android\.|java\.|javax\.|androidx\.|com\.google\.android\.|dalvik\.|com\.android\.internal\.|libcore\.)[\w\.\$]+)\(([\w\.]+):(\d+)\)'),
     'App code: {0} at {1} line {2}'),
    (re.compile(r'Caused by:\s*(.+)'),
     'Root cause: {0}'),
    (re.compile(r'ANR in\s*(\S+)'),
     'App Not Responding: {0}'),

    # --- Permissions ---
    (re.compile(r'Permission [Dd]enial.*from.*pid=(\d+).*uid=(\d+)'),
     'Permission denied for PID {0} / UID {1}'),
    (re.compile(r'avc:\s*denied.*scontext=(\S+).*tcontext=(\S+)'),
     'SELinux denied: {0} accessing {1}'),

    # --- Toast / UI ---
    (re.compile(r'Toast.*show.*caller\s*=\s*(\S+?)(?::(\d+))?(?:\s|$)'),
     'Toast shown from {0} (line {1})'),

    # --- Network ---
    (re.compile(r'NetworkAgent.*Connected.*type\s*=\s*(\S+)'),
     'Network connected: {0}'),
    (re.compile(r'ConnectivityManager.*NetworkCallback.*onLost'),
     'Network connection lost'),
    (re.compile(r'java\.net\.\S*Exception:\s*(.*)'),
     'Network error: {0}'),

    # --- Database ---
    (re.compile(r'SQLiteLog.*\((\d+)\)\s*(.+)'),
     'SQLite error ({0}): {1}'),
    (re.compile(r'ROOM.*Migration.*from\s+(\d+)\s+to\s+(\d+)'),
     'Database migration: version {0} to {1}'),

    # --- Memory ---
    (re.compile(r'OutOfMemoryError'),
     'App ran out of memory'),
    (re.compile(r'lowmemorykiller.*kill.*(\S+).*adj\s*(\d+)'),
     'System killed {0} to free memory (adj={1})'),

    # --- Services ---
    (re.compile(r'ServiceManager.*Waiting for service\s+(\S+)'),
     'Waiting for system service: {0}'),

    # --- Broadcast ---
    (re.compile(r'BroadcastQueue.*Process.*(\S+).*timeout'),
     'Broadcast timeout for {0}'),

    # --- Warnings ---
    (re.compile(r'StrictMode.*policy violation.*~duration=(\d+)\s+ms'),
     'StrictMode violation ({0}ms) — possible main thread I/O'),
    (re.compile(r'Skipped\s+(\d+)\s+frames.*application may be doing too much work'),
     'UI jank: skipped {0} frames — main thread overloaded'),

    # --- General log levels ---
    (re.compile(r'\sE\s+(\S+?)\s*:\s*(.{0,80})'),
     'Error in {0}: {1}'),
    (re.compile(r'\sW\s+(\S+?)\s*:\s*(.{0,80})'),
     'Warning in {0}: {1}'),
]


def get_hint(line: str) -> str:
    """Return a human-readable hint for a log line, or empty string if no match."""
    for pattern, template in _HINT_RULES:
        m = pattern.search(line)
        if m:
            try:
                groups = m.groups()
                # Replace {0}, {1}... with captured groups
                hint = template
                for i, g in enumerate(groups):
                    hint = hint.replace('{' + str(i) + '}', g if g else '?')
                return hint
            except (IndexError, AttributeError):
                continue
    return ''
