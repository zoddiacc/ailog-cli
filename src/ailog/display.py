"""
Terminal display utilities with ANSI colors and formatting.
"""

import sys
import shutil
import time
import threading
import unicodedata


# ANSI color codes
class Colors:
    RESET     = '\033[0m'
    BOLD      = '\033[1m'
    DIM       = '\033[2m'

    BLACK     = '\033[30m'
    RED       = '\033[31m'
    GREEN     = '\033[32m'
    YELLOW    = '\033[33m'
    BLUE      = '\033[34m'
    MAGENTA   = '\033[35m'
    CYAN      = '\033[36m'
    WHITE     = '\033[37m'

    BG_RED    = '\033[41m'
    BG_GREEN  = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE   = '\033[44m'
    BG_CYAN   = '\033[46m'

    BRIGHT_RED     = '\033[91m'
    BRIGHT_GREEN   = '\033[92m'
    BRIGHT_YELLOW  = '\033[93m'
    BRIGHT_BLUE    = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN    = '\033[96m'
    BRIGHT_WHITE   = '\033[97m'


def _display_width(text):
    """Calculate terminal display width, accounting for wide characters (emojis, CJK)."""
    w = 0
    for ch in text:
        if unicodedata.east_asian_width(ch) in ('W', 'F'):
            w += 2
        else:
            w += 1
    return w


def supports_color():
    return hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()


class Display:
    def __init__(self, use_color=None):
        self.color = use_color if use_color is not None else supports_color()
        self.term_width = shutil.get_terminal_size().columns

    def _c(self, code):
        return code if self.color else ''

    def _fmt(self, text, *codes):
        if not self.color:
            return text
        return ''.join(codes) + text + Colors.RESET

    def separator(self, char='─', label=None):
        if label:
            label_str = f' {label} '
            pad = (self.term_width - len(label_str)) // 2
            line = char * pad + label_str + char * pad
        else:
            line = char * self.term_width
        print(self._fmt(line, Colors.DIM))

    def header(self, text):
        print()
        self.separator('═', text)
        print()

    def section(self, text):
        print()
        print(self._fmt(f'▶ {text}', Colors.BOLD, Colors.BRIGHT_CYAN))
        print(self._fmt('─' * min(len(text) + 4, self.term_width), Colors.DIM))

    def ai_box(self, title, content, level='info'):
        """Render a boxed AI interpretation block."""
        colors = {
            'info':    (Colors.BRIGHT_CYAN,   '🤖'),
            'warning': (Colors.BRIGHT_YELLOW, '⚠️ '),
            'error':   (Colors.BRIGHT_RED,    '🔴'),
            'success': (Colors.BRIGHT_GREEN,  '✅'),
        }
        color, icon = colors.get(level, colors['info'])

        width = min(self.term_width, 100)
        border_top    = '╔' + '═' * (width - 2) + '╗'
        border_bottom = '╚' + '═' * (width - 2) + '╝'
        border_mid    = '╠' + '═' * (width - 2) + '╣'

        print()
        print(self._fmt(border_top, color))
        title_line = f'  {icon}  AI ANALYSIS: {title}'
        padding = width - 2 - _display_width(title_line)
        print(self._fmt(f'║{title_line}{" " * max(0, padding)}║', color, Colors.BOLD))
        print(self._fmt(border_mid, color))

        # Word-wrap content (1 border + 3 left pad + content + 2 right pad + 1 border = 7)
        inner_width = width - 7
        for line in content.strip().split('\n'):
            line = line.rstrip()
            if not line:
                print(self._fmt(f'║   {" " * inner_width}  ║', color))
                continue
            while len(line) > inner_width:
                split_at = line.rfind(' ', 0, inner_width)
                if split_at == -1:
                    split_at = inner_width
                chunk = line[:split_at]
                padding = inner_width - len(chunk)
                print(self._fmt('║   ', color) + chunk + ' ' * padding + self._fmt('  ║', color))
                line = line[split_at:].lstrip()
            padding = inner_width - len(line)
            print(self._fmt('║   ', color) + line + ' ' * padding + self._fmt('  ║', color))

        print(self._fmt(border_bottom, color))
        print()

    def crash_summary_box(self, metadata, ai_analysis):
        """Render a crash summary with extracted metadata and AI analysis."""
        width = min(self.term_width, 100)
        iw = width - 7  # inner content width (1 border + 3 left + content + 2 right + 1 border)

        fmt = self._fmt

        border_color = Colors.BRIGHT_RED
        top    = '┏' + '━' * (width - 2) + '┓'
        mid    = '┣' + '━' * (width - 2) + '┫'
        bot    = '┗' + '━' * (width - 2) + '┛'
        dash   = '┃   ' + '╌' * (iw) + '  ┃'

        def row(text=''):
            """Print a row inside the box."""
            text = text.rstrip()
            if not text:
                print(fmt('┃', border_color) + ' ' * (width - 2) + fmt('┃', border_color))
                return
            while len(text) > iw:
                split_at = text.rfind(' ', 0, iw)
                if split_at == -1:
                    split_at = iw
                chunk = text[:split_at]
                pad = iw - len(chunk)
                print(fmt('┃', border_color) + '   ' + chunk + ' ' * pad + '  ' + fmt('┃', border_color))
                text = text[split_at:].lstrip()
            pad = iw - len(text)
            print(fmt('┃', border_color) + '   ' + text + ' ' * pad + '  ' + fmt('┃', border_color))

        def label_row(label, value):
            """Print a label: value row with colored label."""
            text = value
            if len(label) + 2 + len(text) > iw:
                # Truncate value if too long
                text = text[:iw - len(label) - 5] + '...'
            pad = iw - 12 - len(text)
            print(
                fmt('┃', border_color) + '   '
                + fmt(f'{label:<12}', Colors.DIM, Colors.BOLD)
                + fmt(text, Colors.BRIGHT_WHITE)
                + ' ' * max(0, pad) + '  '
                + fmt('┃', border_color)
            )

        print()
        print(fmt(top, border_color))

        # Title
        title = '  💥 CRASH DETECTED'
        pad = width - 2 - _display_width(title)
        print(fmt('┃', border_color) + fmt(title, Colors.BRIGHT_RED, Colors.BOLD) + ' ' * max(0, pad) + fmt('┃', border_color))

        print(fmt(mid, border_color))
        row()

        # Metadata fields
        if metadata.get('exception'):
            label_row('Exception', metadata['exception'])
        if metadata.get('thread'):
            label_row('Thread', metadata['thread'])
        if metadata.get('process'):
            label_row('Process', metadata['process'])
        if metadata.get('location'):
            label_row('Location', metadata['location'])
        if metadata.get('method'):
            # Indented under location
            pad = iw - 12 - len(metadata['method']) - 2
            print(
                fmt('┃', border_color) + '   '
                + ' ' * 12
                + fmt('→ ' + metadata['method'], Colors.DIM)
                + ' ' * max(0, pad) + '  '
                + fmt('┃', border_color)
            )
        if metadata.get('source_file'):
            label_row('Source', metadata['source_file'])

        row()
        print(fmt(dash, border_color, Colors.DIM))
        row()

        # AI analysis content — render sections with colored headers
        for line in ai_analysis.strip().split('\n'):
            line = line.rstrip()
            if not line:
                row()
                continue
            # Detect section headers and color them
            is_header = False
            for marker, hdr_color in [
                ('ROOT CAUSE', Colors.BRIGHT_RED),
                ('WHAT WENT WRONG', Colors.BRIGHT_RED),
                ('HOW TO FIX', Colors.BRIGHT_YELLOW),
                ('FIX', Colors.BRIGHT_YELLOW),
                ('TIP', Colors.BRIGHT_GREEN),
                ('CONTEXT', Colors.BRIGHT_CYAN),
            ]:
                if marker in line.upper():
                    # Print as colored header
                    text = line
                    if len(text) > iw:
                        text = text[:iw]
                    pad = iw - len(text)
                    print(
                        fmt('┃', border_color) + '   '
                        + fmt(text, hdr_color, Colors.BOLD)
                        + ' ' * max(0, pad) + '  '
                        + fmt('┃', border_color)
                    )
                    is_header = True
                    break
            if not is_header:
                row(line)

        row()
        print(fmt(bot, border_color))
        print()

    def log_line(self, line, level=None):
        """Print a log line with appropriate coloring."""
        if level == 'error' or any(k in line for k in ['ERROR', 'FAILED', 'fatal error', 'error:']):
            print(self._fmt(line, Colors.BRIGHT_RED))
        elif level == 'warning' or any(k in line for k in ['WARNING', 'warning:', 'WARN']):
            print(self._fmt(line, Colors.BRIGHT_YELLOW))
        elif any(k in line for k in ['BUILD SUCCESSFUL', 'OK', 'SUCCESS']):
            print(self._fmt(line, Colors.BRIGHT_GREEN))
        elif any(k in line for k in ['make:', 'ninja:', 'soong']):
            print(self._fmt(line, Colors.CYAN))
        else:
            print(self._fmt(line, Colors.DIM))

    def filtered_line(self, line, tag=None):
        """Print a logcat line."""
        if ' E ' in line or line.startswith('E/'):
            print(self._fmt(line, Colors.BRIGHT_RED))
        elif ' W ' in line or line.startswith('W/'):
            print(self._fmt(line, Colors.BRIGHT_YELLOW))
        elif ' I ' in line or line.startswith('I/'):
            print(self._fmt(line, Colors.WHITE))
        elif ' D ' in line or line.startswith('D/'):
            print(self._fmt(line, Colors.DIM))
        elif ' V ' in line or line.startswith('V/'):
            print(self._fmt(line, Colors.DIM + Colors.DIM))
        else:
            print(line)

    def noise_filtered(self, count):
        """Show noise filter stats inline."""
        if count > 0:
            print(self._fmt(
                f'  ╌╌ {count} noise line(s) filtered ╌╌',
                Colors.DIM, Colors.MAGENTA
            ))

    def spinner_start(self, text):
        """Return a spinner context."""
        return Spinner(text, self.color)

    def success(self, text):
        print(self._fmt(f'✅ {text}', Colors.BRIGHT_GREEN))

    def error(self, text):
        print(self._fmt(f'🔴 {text}', Colors.BRIGHT_RED), file=sys.stderr)

    def warning(self, text):
        print(self._fmt(f'⚠️  {text}', Colors.BRIGHT_YELLOW))

    def info(self, text):
        print(self._fmt(f'ℹ️  {text}', Colors.BRIGHT_CYAN))

    def hint(self, text):
        """Print a human-readable hint below a log line."""
        print(self._fmt(f'    ↳ {text}', Colors.DIM, Colors.BRIGHT_GREEN))

    def show_diff(self, old_lines, new_lines):
        """Show a unified-diff-style preview between old and new file content."""
        import difflib
        diff = list(difflib.unified_diff(old_lines, new_lines, lineterm='', n=3))
        if not diff:
            self.info("No changes detected.")
            return
        for line in diff:
            if line.startswith('+++') or line.startswith('---'):
                print(self._fmt(line, Colors.BOLD))
            elif line.startswith('@@'):
                print(self._fmt(line, Colors.BRIGHT_CYAN))
            elif line.startswith('+'):
                print(self._fmt(line, Colors.BRIGHT_GREEN))
            elif line.startswith('-'):
                print(self._fmt(line, Colors.BRIGHT_RED))
            else:
                print(self._fmt(line, Colors.DIM))

    def prompt_yes_no(self, question):
        """Prompt user with a yes/no question. Returns True for yes, False for no."""
        try:
            sys.stdout.write(
                self._fmt(f'\n  ❓ {question} [Y/n] ', Colors.BRIGHT_CYAN, Colors.BOLD)
            )
            sys.stdout.flush()
            answer = input().strip().lower()
            return answer in ('', 'y', 'yes')
        except (EOFError, KeyboardInterrupt):
            print()
            return False

    def dim(self, text):
        print(self._fmt(text, Colors.DIM))

    def stats_bar(self, stats: dict):
        """Render a one-line stats summary."""
        parts = []
        colors_map = {
            'crashes':  Colors.BRIGHT_RED,
            'errors':   Colors.BRIGHT_RED,
            'warnings': Colors.BRIGHT_YELLOW,
            'filtered': Colors.MAGENTA,
            'lines':    Colors.CYAN,
            'provider': Colors.BRIGHT_BLUE,
        }
        for key, val in stats.items():
            color = colors_map.get(key, Colors.WHITE)
            parts.append(self._fmt(f'{key}: {val}', Colors.BOLD, color))
        print('  ' + '  │  '.join(parts))


class Spinner:
    FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

    def __init__(self, text, color=True):
        self.text = text
        self.color = color
        self._frame = 0
        self._active = False
        self._start = None
        self._thread = None

    def __enter__(self):
        self._active = True
        self._start = time.time()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def _spin(self):
        """Background spin loop — runs in a thread."""
        while self._active:
            self.tick()
            time.sleep(0.1)

    def tick(self):
        if self._active:
            frame = self.FRAMES[self._frame % len(self.FRAMES)]
            elapsed = time.time() - self._start
            if self.color:
                sys.stdout.write(f'\r\033[2m{frame}\033[0m \033[96m{self.text}\033[0m \033[2m({elapsed:.1f}s)\033[0m   ')
            else:
                sys.stdout.write(f'\r{frame} {self.text} ({elapsed:.1f}s)   ')
            sys.stdout.flush()
            self._frame += 1

    def __exit__(self, *args):
        self._active = False
        if self._thread:
            self._thread.join(timeout=1.0)
        sys.stdout.write('\r' + ' ' * 80 + '\r')
        sys.stdout.flush()
