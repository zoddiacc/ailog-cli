"""
Batch analyzer: analyze a saved log file with AI.
"""

import os
import re
import sys
import time
from .ai_client import AIClient
from .noise_filter import NoiseFilter
from .display import Display


def detect_log_type(filepath: str, content: str) -> str:
    """Auto-detect whether a log is build output or logcat."""
    filename = os.path.basename(filepath).lower()
    if any(k in filename for k in ['build', 'make', 'compile', 'ninja']):
        return 'build'
    if any(k in filename for k in ['logcat', 'log', 'runtime']):
        return 'logcat'

    # Heuristic: logcat has timestamp pattern like "01-15 12:34:56.789"
    logcat_pattern = re.compile(r'\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+')
    sample = content[:5000]
    matches = logcat_pattern.findall(sample)
    if len(matches) > 10:
        return 'logcat'

    return 'build'


class BatchAnalyzer:
    CHUNK_SIZE = 150  # lines per AI chunk for large files
    MAX_LINES = 2000  # max lines to process from a file

    def __init__(self, config, display: Display):
        self.config = config
        self.display = display
        self.ai = AIClient(config)
        self.max_ai_calls = config.get('max_ai_calls', 5)

    def run(self, args):
        # Handle stdin
        if args.file == '-':
            content = sys.stdin.read()
            filepath = '<stdin>'
            if not content.strip():
                self.display.warning("No input received from stdin.")
                return
        else:
            filepath = args.file

            if not os.path.exists(filepath):
                self.display.error(f"File not found: {filepath}")
                return

            # Check for binary file
            try:
                with open(filepath, 'rb') as f:
                    chunk = f.read(8192)
                    if b'\x00' in chunk:
                        self.display.error("This appears to be a binary file, not a log file.")
                        return
            except PermissionError:
                self.display.error(f"Permission denied: {filepath}")
                return

            try:
                with open(filepath, 'r', errors='replace') as f:
                    content = f.read()
            except PermissionError:
                self.display.error(f"Permission denied: {filepath}")
                return

            if not content.strip():
                self.display.warning("File is empty, nothing to analyze.")
                return

        lines = content.splitlines()

        log_type = args.type if args.type != 'auto' else detect_log_type(filepath, content)

        self.display.header('AILog — Batch Analyzer')
        self.display.info(f"File: {filepath}")
        self.display.info(f"Type: {log_type}  |  Lines: {len(lines)}  |  Provider: {self.config.provider}")
        if args.focus:
            self.display.info(f"Focus: {args.focus}")
        self.display.separator()
        print()

        # For very large files, take head + tail
        if len(lines) > self.MAX_LINES:
            head = lines[:self.MAX_LINES // 2]
            tail = lines[-(self.MAX_LINES // 2):]
            self.display.warning(
                f"File has {len(lines)} lines — analyzing first {self.MAX_LINES // 2} "
                f"and last {self.MAX_LINES // 2} lines."
            )
            lines = head + ['... (middle section skipped) ...'] + tail

        # Filter noise
        nf = NoiseFilter(noise_level='low' if args.full else 'medium')
        kept_lines, filtered_count = nf.filter_batch(lines, mode=log_type)
        errors, warnings = nf.extract_errors_warnings(kept_lines)

        self.display.stats_bar({
            'total lines': len(lines),
            'filtered':    filtered_count,
            'kept':        len(kept_lines),
            'errors':      len(errors),
            'warnings':    len(warnings),
        })
        print()

        # For large files: chunk analysis
        if len(kept_lines) > self.CHUNK_SIZE:
            self._analyze_chunked(kept_lines, errors, warnings, filtered_count,
                                  log_type, args.focus, args.output)
        else:
            self._analyze_full(kept_lines, errors, warnings, filtered_count,
                               log_type, args.focus, args.output)

    def _analyze_full(self, lines, errors, warnings, filtered_count,
                      log_type, focus, output_file):
        """Analyze a small-medium file in one shot."""
        log_text = '\n'.join(lines[:300])  # cap to avoid token limits

        with self.display.spinner_start('Analyzing with AI...'):
            try:
                if log_type == 'build':
                    analysis = self.ai.analyze_build_log(log_text)
                else:
                    analysis = self.ai.analyze_logcat_batch(lines[:200], focus)
            except RuntimeError as e:
                self.display.error(f"AI analysis failed: {e}")
                return

        self.display.ai_box('Full Log Analysis', analysis, level='error' if errors else 'info')

        summary = None
        # Also show session summary if there were errors
        if errors:
            with self.display.spinner_start('Generating priority summary...'):
                try:
                    summary = self.ai.summarize_session(errors, warnings, filtered_count)
                except RuntimeError as e:
                    self.display.warning(f"Summary failed: {e}")

            if summary:
                self.display.ai_box('Priority Summary & Fix Order', summary, level='warning')

        if output_file:
            self._save_report(output_file, analysis, summary)

    def _analyze_chunked(self, lines, errors, warnings, filtered_count,
                         log_type, focus, output_file):
        """Analyze a large file in chunks, then summarize."""
        self.display.info(f"Large file — analyzing in chunks of {self.CHUNK_SIZE} lines...")
        print()

        chunk_analyses = []
        # Process up to MAX_LINES worth of kept lines
        chunks = [lines[i:i + self.CHUNK_SIZE]
                  for i in range(0, min(len(lines), self.MAX_LINES), self.CHUNK_SIZE)]

        ai_calls = 0
        for i, chunk in enumerate(chunks):
            if ai_calls >= self.max_ai_calls:
                self.display.warning(f"Reached max AI calls ({self.max_ai_calls}). Skipping remaining chunks.")
                break

            self.display.section(f'Chunk {i + 1}/{len(chunks)}')

            # Fixed: proper error detection in chunks (was broken with `any()` + display._c)
            has_errors = any(
                'error' in line.lower() or 'exception' in line.lower() or 'failed' in line.lower()
                for line in chunk
            )

            if not has_errors and i > 0:
                self.display.dim("  (No significant issues in this chunk)")
                continue

            with self.display.spinner_start(f'AI analyzing chunk {i + 1}...'):
                try:
                    if log_type == 'build':
                        analysis = self.ai.analyze_build_log('\n'.join(chunk))
                    else:
                        analysis = self.ai.analyze_logcat_batch(chunk, focus)
                    chunk_analyses.append(analysis)
                    ai_calls += 1
                except RuntimeError as e:
                    self.display.warning(f"Chunk {i + 1} analysis failed: {e}")
                    continue

            self.display.ai_box(f'Chunk {i + 1} Analysis', analysis, level='warning')

        # Final holistic summary
        summary = None
        if errors and ai_calls < self.max_ai_calls:
            self.display.section('Overall Session Summary')
            with self.display.spinner_start('Generating holistic summary...'):
                try:
                    summary = self.ai.summarize_session(errors, warnings, filtered_count)
                except RuntimeError as e:
                    self.display.warning(f"Final summary failed: {e}")
                    return

            self.display.ai_box('Priority Fix Order', summary, level='error')

        if output_file:
            self._save_report(output_file, '\n\n---\n\n'.join(chunk_analyses), summary)

    def _save_report(self, path, analysis, summary=None):
        """Save analysis report to a file."""
        content = f"# AILog Analysis Report\n\nGenerated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        content += f"## Analysis\n\n{analysis}\n\n"
        if summary:
            content += f"## Summary & Fix Priority\n\n{summary}\n"

        with open(path, 'w') as f:
            f.write(content)

        self.display.success(f"Report saved to: {path}")
