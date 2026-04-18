"""
Logcat wrapper: wraps adb logcat with real-time AI filtering and interpretation.
"""

import os
import re
import subprocess
import sys
import time
import threading
import signal
from collections import deque
from datetime import datetime
from .ai_client import AIClient
from .noise_filter import NoiseFilter
from .display import Display
from .line_hints import get_hint
from . import report


class LogcatWrapper:
    def __init__(self, config, display: Display):
        self.config = config
        self.display = display
        self.ai = AIClient(config)
        self.max_ai_calls = config.get('max_ai_calls', 5)
        self._running = True

        self._line_count = 0
        self._error_lines = deque(maxlen=200)
        self._warning_lines = deque(maxlen=100)
        self._filtered_count = 0
        self._pending_for_ai = []
        self._context_buffer = deque(maxlen=20)  # sliding window for context
        self._last_ai_time = 0
        self._ai_lock = threading.Lock()
        self._ai_rendering = threading.Event()
        self._ai_rendering.set()  # start set (clear = rendering in progress)
        self._ai_calls = 0

        # Crash block tracking (explain mode)
        self._in_crash_block = False
        self._crash_block_lines = []

        # Streaming deduplication: collapse consecutive identical lines
        self._last_displayed_line = None
        self._repeat_count = 0

        # Source-aware crash fix: consent flag (None = not asked, True/False = answered)
        self._source_consent = None

        # Session data for HTML report
        self._session_crashes = []     # list of (metadata_dict, ai_analysis_str)
        self._session_ai_boxes = []    # list of (title, content)

    def run(self, args):
        self.filter = NoiseFilter(noise_level=args.noise_level)
        self.focus = args.focus
        self.explain_mode = args.explain
        self.batch_interval = (args.batch_interval if args.batch_interval is not None
                               else self.config.get('batch_interval', 5))
        self.no_source = getattr(args, 'no_source', False)
        if self.no_source:
            self._source_consent = False

        # Build adb base command
        logcat_args = args.logcat_args
        if logcat_args and logcat_args[0] == '--':
            logcat_args = logcat_args[1:]

        adb_cmd = ['adb']
        if args.device:
            adb_cmd += ['-s', args.device]

        # Detect multiple devices early
        if not args.device:
            try:
                result = subprocess.run(
                    ['adb', 'devices'], capture_output=True, text=True, timeout=5
                )
                lines = [l for l in result.stdout.strip().splitlines()[1:] if l.strip()]
                if len(lines) > 1:
                    self.display.error("Multiple devices connected. Specify one with -s SERIAL:")
                    for line in lines:
                        serial = line.split()[0]
                        self.display.info(f"  {serial}")
                    self.display.info(f"\nExample: ailog cat -s {lines[0].split()[0]} --explain")
                    return
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        # Resolve --package to --pid
        if args.package:
            pid = self._resolve_pid(adb_cmd, args.package)
            if pid is None:
                return
            logcat_args = ['--pid=' + pid] + (logcat_args if logcat_args else [])

        # Default to showing only new logs (skip old buffer) unless user
        # passed their own -T/-t/-d flags
        if logcat_args is None:
            logcat_args = []
        has_time_flag = any(a in logcat_args for a in ['-d', '-t', '-T'])
        if not has_time_flag:
            logcat_args = ['-T', '1'] + logcat_args

        cmd = adb_cmd + ['logcat'] + logcat_args

        self.display.header('AILog — AI Logcat Filter')
        self.display.info(f"Command: {' '.join(cmd)}")
        self.display.info(f"Provider: {self.config.provider} ({self.ai.model})")
        self.display.info(f"Noise level: {args.noise_level}  |  AI interval: {self.batch_interval}s")
        if self.focus:
            self.display.info(f"Focus: {self.focus}")
        if self.explain_mode:
            self.display.info("Explain mode: ON (AI explains each error inline)")

        # Ask for source-reading consent upfront (only in explain mode, only if not --no-source)
        if self.explain_mode and self._source_consent is None:
            self._source_consent = self.display.prompt_yes_no(
                'Read source files from this project to suggest precise code fixes?'
            )

        self.display.dim("Press Ctrl+C to stop and show session summary")
        self.display.separator()
        print()

        # Handle Ctrl+C gracefully
        signal.signal(signal.SIGINT, self._handle_exit)

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                errors='replace',
            )
        except FileNotFoundError:
            self.display.error(
                "adb not found. Install Android SDK platform-tools and add to your PATH."
            )
            return

        # Start batch AI timer thread
        if not self.explain_mode:
            timer_thread = threading.Thread(
                target=self._batch_timer, args=(proc,), daemon=True
            )
            timer_thread.start()

        self._proc = proc

        noise_streak = 0

        for line in proc.stdout:
            if not self._running:
                break

            line = line.rstrip('\n')
            self._line_count += 1
            self._context_buffer.append(line)

            is_important = self.filter.is_important(line)
            is_noise = self.filter.is_noise(line)

            # Focus filter: if focus set, deprioritize non-focus lines
            if self.focus and not is_important:
                if self.focus.lower() not in line.lower():
                    if not any(k in line for k in [' E ', ' W ', 'Error', 'error']):
                        self._filtered_count += 1
                        noise_streak += 1
                        if noise_streak >= 20:
                            self.display.noise_filtered(noise_streak)
                            noise_streak = 0
                        continue

            if is_noise and not is_important:
                self._filtered_count += 1
                noise_streak += 1
                if noise_streak >= 20:
                    self.display.noise_filtered(noise_streak)
                    noise_streak = 0
                continue

            # Reset noise streak counter on visible line
            if noise_streak > 0:
                self.display.noise_filtered(noise_streak)
                noise_streak = 0

            # Collect stats (skip lines inside a crash block — those are one crash, not N errors)
            if is_important and not self._in_crash_block:
                if any(k in line for k in [' E ', 'Error', 'Exception', 'FATAL', 'fatal']):
                    self._error_lines.append(line)
                elif any(k in line for k in [' W ', 'Warning', 'WARN']):
                    self._warning_lines.append(line)

            # Wait if AI is rendering output (avoid spinner collision)
            self._ai_rendering.wait()

            # Streaming deduplication: collapse consecutive identical lines
            normalized = self._normalize_for_dedup(line)
            if normalized == self._last_displayed_line:
                self._repeat_count += 1
                # Still collect for crash block even if not displayed
                if self.explain_mode and self._in_crash_block and ' E ' in line:
                    self._crash_block_lines.append(line)
                continue
            else:
                # Flush any pending repeats before showing the new line
                self._flush_repeat()
                self._last_displayed_line = normalized

            # Display the line
            self.display.filtered_line(line)

            # Show human-readable hint below the line (skip inside crash blocks —
            # the crash summary box will explain everything)
            if self.explain_mode and not self._in_crash_block:
                hint = get_hint(line)
                if hint:
                    self.display.hint(hint)

            # In explain mode: detect crash blocks and summarize them
            if self.explain_mode:
                is_error_line = ' E ' in line
                is_crash_start = 'FATAL EXCEPTION' in line or 'beginning of crash' in line

                if is_crash_start:
                    # Start collecting a new crash block
                    self._in_crash_block = True
                    self._crash_block_lines = [line]
                elif self._in_crash_block:
                    if is_error_line:
                        # Continue collecting crash lines
                        self._crash_block_lines.append(line)
                    else:
                        # Non-error line: crash block ended, flush repeats then summary
                        self._flush_repeat()
                        self._flush_crash_summary()
                        if is_important and is_error_line:
                            self._explain_inline(line)

                elif is_important and is_error_line:
                    self._explain_inline(line)
            else:
                # Thread-safe append to pending list
                with self._ai_lock:
                    self._pending_for_ai.append(line)

        proc.wait()
        # Flush any pending repeat count
        self._flush_repeat()
        # Flush any pending crash block that didn't get a non-error line to close it
        if self._in_crash_block:
            self._flush_crash_summary()
        self._show_session_summary()

    def _resolve_pid(self, adb_cmd, package):
        """Resolve a package name to a PID using adb shell pidof."""
        try:
            result = subprocess.run(
                adb_cmd + ['shell', 'pidof', package],
                capture_output=True, text=True, timeout=5
            )
            pid = result.stdout.strip().split()[0] if result.stdout.strip() else ''
        except (subprocess.TimeoutExpired, FileNotFoundError, IndexError):
            pid = ''

        if not pid:
            self.display.error(
                f"Could not find running process for '{package}'. "
                f"Is the app running on the device?"
            )
            return None
        self.display.info(f"Resolved {package} → PID {pid}")
        return pid

    def _normalize_for_dedup(self, line):
        """Normalize a line for dedup comparison (strip timestamp/PID, keep content)."""
        # Remove leading timestamp like "03-05 23:30:45.451"
        normalized = re.sub(r'^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+\s+', '', line)
        # Remove PID/TID like "32119 32119"
        normalized = re.sub(r'^\s*\d+\s+\d+\s+', '', normalized)
        return normalized.strip()

    def _flush_repeat(self):
        """If there are pending repeats, show the count and reset."""
        if self._repeat_count > 0:
            self.display.hint(f'... repeated {self._repeat_count} more time{"s" if self._repeat_count > 1 else ""} (collapsed)')
            self._repeat_count = 0

    @staticmethod
    def _parse_crash_metadata(crash_lines):
        """Extract structured metadata from a crash block."""
        meta = {}
        full_text = '\n'.join(crash_lines)

        # Exception type + message
        m = re.search(r'([\w\.]+(?:Exception|Error)):\s*(.+)', full_text)
        if m:
            meta['exception'] = f'{m.group(1)}: {m.group(2).strip()}'
            meta['exception_type'] = m.group(1)
        elif re.search(r'([\w\.]+(?:Exception|Error))', full_text):
            meta['exception_type'] = re.search(r'([\w\.]+(?:Exception|Error))', full_text).group(1)
            meta['exception'] = meta['exception_type']

        # Thread
        m = re.search(r'FATAL EXCEPTION:\s*(\S+)', full_text)
        if m:
            meta['thread'] = m.group(1)

        # Process + PID
        m = re.search(r'Process:\s*(\S+),\s*PID:\s*(\d+)', full_text)
        if m:
            meta['process'] = f'{m.group(1)} (PID {m.group(2)})'

        # Top app stack frame (first `at` line pointing to app code, not android/java framework)
        for line in crash_lines:
            m = re.search(r'at\s+([\w\.\$]+)\(([\w\.]+):(\d+)\)', line)
            if m:
                full_class = m.group(1)
                file_name = m.group(2)
                line_num = m.group(3)
                # Prefer app code over framework code
                if not any(fw in full_class for fw in [
                    'android.', 'java.', 'androidx.', 'com.google.android.material.',
                    'dalvik.', 'com.android.internal.'
                ]):
                    meta['location'] = f'{file_name}:{line_num}'
                    meta['method'] = full_class.split('$')[0].rsplit('.', 1)[-1] + '.' + full_class.split('.')[-1].replace('$', '.')
                    # Try to get a cleaner method name
                    parts = full_class.rsplit('.', 1)
                    if len(parts) == 2:
                        meta['method'] = full_class
                    break
            # Also check "Caused by" lines for deeper root cause
            m2 = re.search(r'Caused by:\s*([\w\.]+(?:Exception|Error)):\s*(.+)', line)
            if m2:
                meta['exception'] = f'{m2.group(1)}: {m2.group(2).strip()}'
                meta['exception_type'] = m2.group(1)

        # Fallback location: first `at` line at all
        if 'location' not in meta:
            m = re.search(r'at\s+([\w\.\$]+)\(([\w\.]+):(\d+)\)', full_text)
            if m:
                meta['location'] = f'{m.group(2)}:{m.group(3)}'
                meta['method'] = m.group(1)

        return meta

    @staticmethod
    def _find_source_file(filename):
        """Search CWD recursively for a source file, skipping build/generated dirs."""
        skip_dirs = {'build', '.gradle', '.idea', '.git', 'node_modules', '__pycache__',
                     'generated', 'intermediates', 'out', '.cxx'}
        for root, dirs, files in os.walk('.'):
            # Prune directories we don't want to search
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            if filename in files:
                return os.path.join(root, filename)
        return None

    @staticmethod
    def _read_source_snippet(filepath, line_num, context=10):
        """Read ~2*context lines around the crash line from a source file."""
        try:
            with open(filepath, 'r', errors='replace') as f:
                lines = f.readlines()
        except (OSError, IOError):
            return None

        start = max(0, line_num - context - 1)
        end = min(len(lines), line_num + context)
        snippet_lines = []
        for i in range(start, end):
            marker = ' >> ' if i == line_num - 1 else '    '
            snippet_lines.append(f'{i + 1:4d}{marker}{lines[i].rstrip()}')
        return '\n'.join(snippet_lines)

    def _flush_crash_summary(self):
        """Summarize a completed crash block with AI and display it."""
        if not self._crash_block_lines:
            self._in_crash_block = False
            return

        # Deduplicate crash lines for AI (recursive traces repeat the same frame)
        seen = set()
        deduped = []
        for line in self._crash_block_lines:
            normalized = self._normalize_for_dedup(line)
            if normalized not in seen:
                seen.add(normalized)
                deduped.append(line)

        crash_lines = deduped
        self._crash_block_lines = []
        self._in_crash_block = False

        # Extract metadata from the raw crash lines
        metadata = self._parse_crash_metadata(crash_lines)

        if self._ai_calls >= self.max_ai_calls:
            # Still show metadata even without AI
            analysis = '(AI call limit reached — no analysis available)'
            self.display.crash_summary_box(metadata, analysis)
            self._session_crashes.append((metadata, analysis))
            return

        # Source-aware crash fix: try to read source file for precise fix
        source_snippet = None
        location = metadata.get('location', '')
        if location and self._source_consent:
            # Parse filename and line number from location (e.g. "MainActivity.kt:35")
            loc_match = re.match(r'(.+):(\d+)$', location)
            if loc_match:
                src_filename = loc_match.group(1)
                src_line = int(loc_match.group(2))
                src_path = self._find_source_file(src_filename)
                if src_path:
                    source_snippet = self._read_source_snippet(src_path, src_line)
                    if source_snippet:
                        metadata['source_file'] = src_path

        try:
            with self.display.spinner_start('Analyzing crash...'):
                analysis = self.ai.explain_crash(
                    crash_lines,
                    exception_type=metadata.get('exception_type', ''),
                    source_snippet=source_snippet,
                )
            self._ai_calls += 1
            self.display.crash_summary_box(metadata, analysis)
            self._session_crashes.append((metadata, analysis))
            # Offer auto-fix if source file was found
            self._offer_auto_fix(metadata, analysis)
        except RuntimeError as e:
            # Still show metadata even if AI fails, but tell the user why
            analysis = f'(AI analysis failed: {e})'
            self.display.crash_summary_box(metadata, analysis)
            self._session_crashes.append((metadata, analysis))

    def _offer_auto_fix(self, metadata, analysis):
        """Prompt user to auto-fix source file based on crash analysis."""
        src_path = metadata.get('source_file')
        if not src_path:
            return
        if self._ai_calls >= self.max_ai_calls:
            return

        filename = os.path.basename(src_path)
        if not self.display.prompt_yes_no(f'Apply AI fix to {filename}?'):
            self.display.dim('  Fix skipped.')
            return

        # Read the full source file
        try:
            with open(src_path, 'r', errors='replace') as f:
                original_content = f.read()
        except OSError as e:
            self.display.error(f'Could not read {src_path}: {e}')
            return

        # Parse crash line number from location
        loc = metadata.get('location', '')
        loc_match = re.match(r'.+:(\d+)$', loc)
        crash_line = int(loc_match.group(1)) if loc_match else 0

        # Call AI to generate fix
        try:
            with self.display.spinner_start(f'Generating fix for {filename}...'):
                fixed_content = self.ai.generate_fix(
                    original_content,
                    crash_line,
                    analysis,
                    exception_type=metadata.get('exception_type', ''),
                )
            self._ai_calls += 1
        except RuntimeError as e:
            self.display.error(f'AI fix generation failed: {e}')
            return

        # Show diff preview
        old_lines = original_content.splitlines()
        new_lines = fixed_content.splitlines()
        if old_lines == new_lines:
            self.display.info('AI produced no changes.')
            return

        print()
        self.display.show_diff(old_lines, new_lines)
        print()

        if not self.display.prompt_yes_no('Apply this change?'):
            self.display.dim('  Fix skipped.')
            return

        # Create a backup before applying the fix
        import shutil
        backup_path = src_path + '.bak'
        try:
            shutil.copy2(src_path, backup_path)
        except OSError as e:
            self.display.error(f'Could not create backup {backup_path}: {e}')
            return

        # Write the fixed file
        try:
            with open(src_path, 'w') as f:
                f.write(fixed_content)
            self.display.success(f'Fix applied to {src_path}')
            self.display.dim(f'  Backup saved: {backup_path}')
        except OSError as e:
            self.display.error(f'Could not write {src_path}: {e}')
            # Restore from backup
            try:
                shutil.copy2(backup_path, src_path)
                self.display.info(f'Restored original from backup.')
            except OSError:
                pass

    def _explain_inline(self, line):
        """Explain a single error line inline (explain mode)."""
        if self._ai_calls >= self.max_ai_calls:
            return
        context = list(self._context_buffer)
        try:
            explanation = self.ai.explain_line(line, context)
            self._ai_calls += 1
            indent = '    '
            for l in explanation.split('\n'):
                print(f"\033[2m{indent}💡 {l}\033[0m")
        except RuntimeError:
            pass  # Silent fail for inline explanations

    def _batch_timer(self, proc):
        """Background thread: trigger AI analysis every N seconds if there's activity."""
        while self._running and proc.poll() is None:
            time.sleep(self.batch_interval)

            if self._ai_calls >= self.max_ai_calls:
                continue

            with self._ai_lock:
                if not self._pending_for_ai:
                    continue
                if not self.filter.should_trigger_ai(self._pending_for_ai):
                    self._pending_for_ai = []
                    continue

                batch = self._pending_for_ai.copy()
                self._pending_for_ai = []

            self._run_batch_ai(batch)

    def _run_batch_ai(self, batch):
        """Run AI on a batch, display results."""
        self._ai_rendering.clear()
        try:
            analysis = self.ai.analyze_logcat_batch(batch, self.focus)
            self._ai_calls += 1
            self.display.ai_box('Logcat Analysis', analysis, level='warning')
            self._session_ai_boxes.append(('Logcat Analysis', analysis))
        except RuntimeError as e:
            self.display.warning(f"AI analysis failed: {e}")
        finally:
            self._ai_rendering.set()

    def _handle_exit(self, sig, frame):
        """Gracefully handle Ctrl+C."""
        self._running = False
        print()
        self.display.info("Stopping... generating session summary")
        if hasattr(self, '_proc'):
            self._proc.terminate()

    def _show_session_summary(self):
        """Show end-of-session AI summary."""
        self.display.separator()
        print()

        stats = {
            'crashes':  len(self._session_crashes),
            'errors':   len(self._error_lines),
            'warnings': len(self._warning_lines),
            'filtered': self._filtered_count,
            'lines':    self._line_count,
            'provider': f"{self.config.provider}",
        }
        self.display.stats_bar(stats)

        summary_text = None

        if self._error_lines or self._warning_lines:
            if self._ai_calls >= self.max_ai_calls:
                self.display.warning(f"Reached max AI calls ({self.max_ai_calls}). Skipping summary.")
            else:
                with self.display.spinner_start('Generating session summary...'):
                    try:
                        summary_text = self.ai.summarize_session(
                            self._error_lines,
                            self._warning_lines,
                            self._filtered_count
                        )
                    except RuntimeError as e:
                        self.display.warning(f"Could not summarize session: {e}")

                if summary_text:
                    self.display.ai_box('Session Summary', summary_text, level='info')
        else:
            self.display.success("Clean session — no errors or warnings detected!")

        self._generate_html_report(stats, summary_text)

    _REPORT_DIR = os.path.join(os.path.expanduser('~'), '.local', 'share', 'ailog', 'reports')
    _REPORT_MAX_AGE_DAYS = 30

    def _generate_html_report(self, stats, summary_text):
        """Generate an HTML session report file and rotate old reports."""
        now = datetime.now()
        timestamp = now.strftime('%Y-%m-%d %H:%M:%S')

        data = {
            'stats': stats,
            'crashes': self._session_crashes,
            'batch_analyses': self._session_ai_boxes,
            'summary': summary_text or '',
            'config': {
                'provider': self.config.provider,
                'model': self.ai.model,
                'noise_level': getattr(self, 'filter', None) and self.filter.noise_level or 'N/A',
            },
            'timestamp': timestamp,
        }

        html_content = report.generate_html_report(data)

        report_dir = self._REPORT_DIR
        os.makedirs(report_dir, exist_ok=True)

        filename = now.strftime('ailog-report-%Y%m%d-%H%M%S.html')
        filepath = os.path.join(report_dir, filename)

        try:
            with open(filepath, 'w') as f:
                f.write(html_content)
            self.display.info(f"HTML report saved: {filepath}")
            self._rotate_reports(report_dir)
        except OSError as e:
            self.display.warning(f"Could not write HTML report: {e}")

    def _rotate_reports(self, report_dir):
        """Delete reports older than _REPORT_MAX_AGE_DAYS."""
        try:
            cutoff = time.time() - self._REPORT_MAX_AGE_DAYS * 86400
            for name in os.listdir(report_dir):
                if not (name.startswith('ailog-report-') and name.endswith('.html')):
                    continue
                path = os.path.join(report_dir, name)
                if os.path.getmtime(path) < cutoff:
                    os.remove(path)
        except OSError:
            pass  # best-effort cleanup
