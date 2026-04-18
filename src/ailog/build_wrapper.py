"""
Build wrapper: intercepts AOSP make/m output and provides AI interpretation.
"""

import subprocess
import sys
import time
import threading
from collections import deque
from .ai_client import AIClient
from .noise_filter import NoiseFilter
from .display import Display


class BuildWrapper:
    BATCH_SIZE = 80  # lines before considering an AI call
    ERROR_WINDOW = 30  # lines of context around an error

    def __init__(self, config, display: Display):
        self.config = config
        self.display = display
        self.ai = AIClient(config)
        self.filter = NoiseFilter(noise_level='medium')
        self.max_ai_calls = config.get('max_ai_calls', 5)

        self._line_count = 0
        self._error_lines = deque(maxlen=200)
        self._warning_lines = deque(maxlen=100)
        self._filtered_count = 0
        self._ai_calls = 0

    def run(self, args):
        # Determine the build command
        make_args = args.make_args
        if make_args and make_args[0] == '--':
            make_args = make_args[1:]

        # Try 'm' first (AOSP shortcut), fall back to make
        cmd = self._resolve_build_cmd(make_args)
        if cmd is None:
            self.display.error(
                "No build command found (m or make). "
                "Are you in an AOSP source tree? Run 'source build/envsetup.sh && lunch' first."
            )
            return

        self.display.header('AILog — AI Build Interpreter')
        self.display.info(f"Command: {' '.join(cmd)}")
        self.display.info(f"Provider: {self.config.provider} ({self.ai.model})")
        if args.module:
            self.display.info(f"Module hint: {args.module}")
        self.display.dim(
            f"Noise filtering: {'off' if args.no_filter else 'on'}  |  "
            f"Mode: {'summary only' if args.summary_only else 'streaming'}"
        )
        self.display.separator()
        print()

        start_time = time.time()

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
                f"Build command not found: {cmd[0]}. "
                f"Are you in an AOSP source tree? Run 'source build/envsetup.sh && lunch' first."
            )
            return

        pending_batch = []

        try:
            for line in proc.stdout:
                line = line.rstrip('\n')
                self._line_count += 1

                is_important = self.filter.is_important(line)
                is_noise = self.filter.is_noise(line) or (
                    not args.no_filter and self.filter.is_build_noise(line)
                )

                if is_noise and not is_important:
                    self._filtered_count += 1
                    continue

                if is_important:
                    if 'error' in line.lower() or 'FAILED' in line:
                        self._error_lines.append(line)
                    elif 'warning' in line.lower():
                        self._warning_lines.append(line)

                if not args.summary_only:
                    self.display.log_line(line)

                pending_batch.append(line)

                # Trigger AI when we see an error cluster
                if (len(pending_batch) >= self.BATCH_SIZE and
                        self.filter.should_trigger_ai(pending_batch)):
                    self._analyze_batch(pending_batch, args.module, args.summary_only)
                    pending_batch = []
        except KeyboardInterrupt:
            proc.terminate()
            proc.wait()
            self.display.warning("Build interrupted by user.")
            return

        proc.wait()
        elapsed = time.time() - start_time

        # Analyze any remaining batch
        if pending_batch and self.filter.should_trigger_ai(pending_batch):
            self._analyze_batch(pending_batch, args.module, args.summary_only)

        # Final summary
        self._final_summary(proc.returncode, elapsed, args.module)

    def _analyze_batch(self, lines, module_hint, summary_only):
        """Call AI on a batch of lines that contain errors."""
        if self._ai_calls >= self.max_ai_calls:
            return

        relevant = [l for l in lines if self.filter.is_important(l)]
        if not relevant:
            return

        log_text = '\n'.join(lines[-self.ERROR_WINDOW:])  # last N lines for context

        with self.display.spinner_start('AI analyzing error cluster...'):
            try:
                analysis = self.ai.analyze_build_log(log_text, module_hint)
                self._ai_calls += 1
            except RuntimeError as e:
                self.display.warning(f"AI analysis failed: {e}")
                return

        self.display.ai_box('Build Error', analysis, level='error')

    def _final_summary(self, returncode, elapsed, module_hint):
        """Show final build summary."""
        self.display.separator()
        print()

        if returncode == 0:
            self.display.success(f"Build SUCCEEDED in {elapsed:.1f}s")
        else:
            self.display.error(f"Build FAILED (exit {returncode}) after {elapsed:.1f}s")

        self.display.stats_bar({
            'errors':   len(self._error_lines),
            'warnings': len(self._warning_lines),
            'filtered': self._filtered_count,
            'lines':    self._line_count,
            'ai calls': self._ai_calls,
            'provider': f"{self.config.provider}",
        })

        # If build failed and we have errors, do a final holistic analysis
        if returncode != 0 and self._error_lines and self._ai_calls < self.max_ai_calls:
            print()
            with self.display.spinner_start('Generating final build analysis...'):
                try:
                    summary = self.ai.summarize_session(
                        self._error_lines,
                        self._warning_lines,
                        self._filtered_count
                    )
                except RuntimeError as e:
                    self.display.warning(f"Could not generate final summary: {e}")
                    return

            self.display.ai_box('Build Session Summary', summary,
                                level='error' if returncode != 0 else 'success')

    def _resolve_build_cmd(self, extra_args):
        """Try to find the right build command."""
        import shutil

        if shutil.which('m'):
            base = ['m']
        elif shutil.which('make'):
            base = ['make']
        else:
            return None

        return base + (extra_args if extra_args else [])
