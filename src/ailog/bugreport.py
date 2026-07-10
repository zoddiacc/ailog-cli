"""
Bugreport analyzer: triage an `adb bugreport` (.zip or .txt).

A bugreport is huge (tens to hundreds of MB) and buries the real problems —
Java crashes, native tombstones, ANRs, SELinux denials, watchdog kills — inside
one giant text file. This module extracts those problem blocks, enriches each
with the AOSP/Automotive knowledge pack (instant, no AI), and optionally sends
the worst crashes to the AI for a deeper explanation.

Fully usable with no model at all via --no-ai (the knowledge-pack triage alone
is valuable and always correct).
"""

import json
import os
import re
import time
import zipfile

from .ai_client import AIClient
from .display import Display
from .line_hints import get_hint
from . import knowledge_pack

# Bugreports can be enormous; cap what we read into memory.
MAX_BYTES = 64 * 1024 * 1024  # 64 MB
# Lines of context captured around each problem marker.
CRASH_WINDOW = 30
JAVA_WINDOW = 24
ANR_WINDOW = 18
WATCHDOG_WINDOW = 14
# Caps to keep output and cost bounded.
MAX_ISSUES_SHOWN = 25
MAX_SELINUX_SHOWN = 8

# Device-info fields worth surfacing, in display order.
_INFO_FIELDS = [
    ('Build fingerprint', re.compile(r"^Build fingerprint:\s*'?(.+?)'?\s*$", re.M)),
    ('Kernel', re.compile(r'^Kernel:\s*(.+)$', re.M)),
    ('Bootloader', re.compile(r'^Bootloader:\s*(.+)$', re.M)),
    ('Uptime', re.compile(r'^Uptime:\s*(.+)$', re.M)),
]

_JAVA_CRASH = re.compile(r'FATAL EXCEPTION')
_EXC_TYPE = re.compile(r'((?:[a-zA-Z][\w]*\.)+[A-Z]\w*(?:Exception|Error))')
_PROCESS = re.compile(r'Process:\s*([^\s,]+)')
_NATIVE_SIGNAL = re.compile(r'signal\s+\d+\s+\(SIG[A-Z]+\)')
_ANR = re.compile(r'ANR in\s+([^\s(]+)')
_WATCHDOG = re.compile(r'WATCHDOG KILLING|Watchdog.*blocked')

# SELinux fields parsed independently — they appear in varying order.
_AVC_PERM = re.compile(r'denied\s*\{\s*([^}]+?)\s*\}')
_AVC_SCONTEXT = re.compile(r'scontext=(\S+)')
_AVC_TCONTEXT = re.compile(r'tcontext=(\S+)')
_AVC_TCLASS = re.compile(r'tclass=(\S+)')

# A block ends at the next problem marker or a bugreport section header, so one
# issue's context does not bleed into the next event's hints.
_BLOCK_STOP = re.compile(
    r'FATAL EXCEPTION|signal\s+\d+\s+\(SIG[A-Z]+\)|ANR in\s|WATCHDOG KILLING'
    r'|Watchdog.*blocked|avc:\s*denied|^-{4,}\s'
)


def _extract_block(lines, start, max_window):
    """Collect lines from `start` up to the next problem marker/section header."""
    block = [lines[start]]
    end = min(len(lines), start + max_window)
    for j in range(start + 1, end):
        if _BLOCK_STOP.search(lines[j]):
            break
        block.append(lines[j])
    return '\n'.join(block)


class Issue:
    """One detected problem: a kind, a short title, and its log block."""
    __slots__ = ('kind', 'title', 'block', 'marker')

    def __init__(self, kind, title, block, marker=''):
        self.kind = kind
        self.title = title
        self.block = block
        self.marker = marker


class BugreportAnalyzer:
    def __init__(self, config, display: Display):
        self.config = config
        self.display = display
        self.ai = AIClient(config)
        self.max_ai_calls = config.get('max_ai_calls', 5)
        self._ai_calls = 0

    def _nl(self):
        """A blank line in pretty mode; nothing in JSON mode."""
        if not self.display.json:
            print()

    def run(self, args):
        content = self._read_source(args.file)
        if content is None:
            return 1

        self.display.header('AILog — Bugreport Triage')
        self.display.info(f"File: {args.file}")

        device = self._device_info(content)
        for label, value in device:
            self.display.info(f"{label}: {value}")
        mode = 'deterministic (no AI)' if args.no_ai else f"{self.config.provider} ({self.ai.model})"
        self.display.info(f"Analysis: {mode}")
        self.display.separator()

        lines = content.splitlines()
        issues, selinux = self._detect(lines, focus=args.focus)

        self.display.stats_bar({
            'java crashes':   sum(1 for i in issues if i.kind == 'java'),
            'native crashes': sum(1 for i in issues if i.kind == 'native'),
            'ANRs':           sum(1 for i in issues if i.kind == 'anr'),
            'watchdog':       sum(1 for i in issues if i.kind == 'watchdog'),
            'SELinux':        len(selinux),
        })

        if not issues and not selinux:
            self._nl()
            self.display.success("No crashes, ANRs, watchdog kills, or SELinux denials found.")
            if args.output:
                self._save_report(args.output, device, [], [])
            if self.display.json:
                self._emit_json(args.file, device, [], selinux)
            return 0

        report_sections = []
        shown = issues[:MAX_ISSUES_SHOWN]
        for idx, issue in enumerate(shown, 1):
            self._nl()
            self.display.section(f"{idx}. [{issue.kind.upper()}] {issue.title}")

            # Deterministic triage first — instant, always correct, no model.
            hint_lines = self._triage_hints(issue)
            for h in hint_lines:
                self.display.dim(f"  ↳ {h}")

            analysis = None
            if not args.no_ai and issue.kind in ('java', 'native', 'anr') \
                    and self._ai_calls < self.max_ai_calls:
                analysis = self._ai_explain(issue)

            report_sections.append((issue, hint_lines, analysis))

        if len(issues) > MAX_ISSUES_SHOWN:
            self._nl()
            self.display.warning(
                f"Showing first {MAX_ISSUES_SHOWN} of {len(issues)} issues. "
                f"Use --focus <package/keyword> to narrow down."
            )

        if selinux:
            self._show_selinux(selinux)

        if args.output:
            self._save_report(args.output, device, report_sections, selinux)

        if self.display.json:
            self._emit_json(args.file, device, report_sections, selinux)

        return 0

    def _emit_json(self, file, device, report_sections, selinux):
        """Print the triage result as a single JSON document to stdout."""
        issues = []
        for issue, hint_lines, analysis in report_sections:
            issues.append({
                'kind': issue.kind,
                'title': issue.title,
                'hints': hint_lines,
                'analysis': analysis,
            })
        result = {
            'file': file,
            'device': {label: value for label, value in device},
            'issue_counts': {
                'java': sum(1 for i in issues if i['kind'] == 'java'),
                'native': sum(1 for i in issues if i['kind'] == 'native'),
                'anr': sum(1 for i in issues if i['kind'] == 'anr'),
                'watchdog': sum(1 for i in issues if i['kind'] == 'watchdog'),
                'selinux': len(selinux),
            },
            'issues': issues,
            'selinux': [
                {'scontext': s[1], 'tcontext': s[2], 'tclass': s[3], 'perm': s[0]}
                for s in selinux
            ],
        }
        print(json.dumps(result, indent=2))

    # ---------------- input ----------------

    def _read_source(self, path):
        """Return the main bugreport text from a .zip or .txt, or None on error."""
        if not os.path.exists(path):
            self.display.error(f"File not found: {path}")
            return None

        try:
            if zipfile.is_zipfile(path):
                return self._read_zip(path)
            with open(path, 'r', errors='replace') as f:
                data = f.read(MAX_BYTES + 1)
        except PermissionError:
            self.display.error(f"Permission denied: {path}")
            return None
        except OSError as e:
            self.display.error(f"Could not read {path}: {e}")
            return None

        if len(data) > MAX_BYTES:
            self.display.warning(f"Bugreport is large — analyzing the first {MAX_BYTES // (1024*1024)} MB.")
            data = data[:MAX_BYTES]
        if not data.strip():
            self.display.warning("File is empty, nothing to analyze.")
            return None
        return data

    def _read_zip(self, path):
        """Extract the main bugreport text file from an adb bugreport zip."""
        try:
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
                txts = [n for n in names if n.lower().endswith('.txt')]
                main = [n for n in txts if os.path.basename(n).lower().startswith('bugreport')]
                candidates = main or txts
                if not candidates:
                    self.display.error("No bugreport text file found inside the zip.")
                    return None
                member = max(candidates, key=lambda n: z.getinfo(n).file_size)
                with z.open(member) as f:
                    raw = f.read(MAX_BYTES + 1)
        except (zipfile.BadZipFile, OSError) as e:
            self.display.error(f"Could not open bugreport zip: {e}")
            return None

        if len(raw) > MAX_BYTES:
            self.display.warning(f"Bugreport is large — analyzing the first {MAX_BYTES // (1024*1024)} MB.")
            raw = raw[:MAX_BYTES]
        return raw.decode('utf-8', errors='replace')

    # ---------------- parsing ----------------

    def _device_info(self, content):
        head = content[:20000]  # device info lives near the top
        out = []
        for label, pattern in _INFO_FIELDS:
            m = pattern.search(head)
            if m:
                out.append((label, m.group(1).strip()))
        return out

    def _detect(self, lines, focus=None):
        """Scan lines once, extracting problem blocks. Returns (issues, selinux)."""
        issues = []
        selinux = {}
        seen = set()

        for i, line in enumerate(lines):
            if _JAVA_CRASH.search(line):
                block = _extract_block(lines, i, JAVA_WINDOW)
                exc = _EXC_TYPE.search(block)
                proc = _PROCESS.search(block)
                exc_type = exc.group(1) if exc else 'Java crash'
                who = f" in {proc.group(1)}" if proc else ''
                self._add(issues, seen, Issue('java', f"{exc_type}{who}", block, exc_type), focus)

            elif _NATIVE_SIGNAL.search(line):
                # Include the couple of preceding tombstone-header lines for context.
                lead = lines[max(0, i - 2):i]
                block = '\n'.join(lead) + '\n' + _extract_block(lines, i, CRASH_WINDOW)
                sig = _NATIVE_SIGNAL.search(line).group(0)
                self._add(issues, seen, Issue('native', f"Native crash — {sig}", block, sig), focus)

            elif _ANR.search(line):
                block = _extract_block(lines, i, ANR_WINDOW)
                pkg = _ANR.search(line).group(1)
                self._add(issues, seen, Issue('anr', f"ANR in {pkg}", block, pkg), focus)

            elif _WATCHDOG.search(line):
                block = _extract_block(lines, i, WATCHDOG_WINDOW)
                self._add(issues, seen, Issue('watchdog', line.strip()[:80], block), focus)

            elif 'avc: denied' in line:
                perm = _AVC_PERM.search(line)
                sctx = _AVC_SCONTEXT.search(line)
                tctx = _AVC_TCONTEXT.search(line)
                tclass = _AVC_TCLASS.search(line)
                perm = perm.group(1) if perm else '?'
                sctx = sctx.group(1) if sctx else '?'
                tctx = tctx.group(1) if tctx else '?'
                tclass = tclass.group(1) if tclass else '?'
                key = (perm, tclass, tctx)
                if key not in selinux:
                    selinux[key] = (perm, sctx, tctx, tclass, line.strip())

            if len(issues) >= MAX_ISSUES_SHOWN * 4:  # hard stop on pathological files
                break

        return issues, list(selinux.values())

    @staticmethod
    def _add(issues, seen, issue, focus):
        if focus and focus.lower() not in issue.block.lower():
            return
        # Dedup repeated identical crashes (bugreports log some twice).
        key = (issue.kind, issue.title, issue.block[:120])
        if key in seen:
            return
        seen.add(key)
        issues.append(issue)

    def _triage_hints(self, issue):
        """Formatted, always-correct hint strings for an issue (no AI).

        Prefers AOSP/Automotive domain facts; falls back to a generic line hint
        so even a plain Java crash / ANR gets something useful in --no-ai mode.
        """
        matches = knowledge_pack.find_matches(issue.block)
        if matches:
            return [f"[{m.category}] {m.hint}" for m in matches]
        for line in issue.block.splitlines()[:6]:
            generic = get_hint(line)
            if generic:
                return [generic]
        return []

    # ---------------- AI ----------------

    def _ai_explain(self, issue):
        with self.display.spinner_start(f'AI analyzing {issue.kind} crash...'):
            try:
                analysis = self.ai.explain_crash(
                    issue.block.splitlines(), exception_type=issue.marker
                )
                self._ai_calls += 1
            except RuntimeError as e:
                self.display.warning(f"AI analysis failed: {e}")
                return None
        self.display.ai_box(issue.title, analysis, level='error')
        return analysis

    # ---------------- SELinux ----------------

    def _show_selinux(self, selinux):
        self._nl()
        self.display.section(f"SELinux denials ({len(selinux)} unique)")
        guidance = knowledge_pack.find_matches('avc: denied { read } scontext=x tcontext=y tclass=file')
        if guidance:
            self.display.dim(f"  ↳ [{guidance[0].category}] {guidance[0].hint}")
        for perm, sctx, tctx, tclass, _raw in selinux[:MAX_SELINUX_SHOWN]:
            self.display.info(f"  {sctx or '?'} → {tctx or '?'} : {tclass or '?'} {{ {perm} }}")
        if len(selinux) > MAX_SELINUX_SHOWN:
            self.display.dim(f"  ... and {len(selinux) - MAX_SELINUX_SHOWN} more")

    # ---------------- output ----------------

    def _save_report(self, path, device, sections, selinux):
        parts = [f"# AILog Bugreport Triage\n\nGenerated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"]
        if device:
            parts.append("## Device\n")
            for label, value in device:
                parts.append(f"- **{label}:** {value}")
            parts.append("")
        for issue, hint_lines, analysis in sections:
            parts.append(f"## [{issue.kind}] {issue.title}\n")
            for h in hint_lines:
                parts.append(f"- {h}")
            if analysis:
                parts.append(f"\n{analysis}\n")
            parts.append("\n```\n" + issue.block + "\n```\n")
        if selinux:
            parts.append("## SELinux denials\n")
            for perm, sctx, tctx, tclass, _raw in selinux:
                parts.append(f"- `{sctx} -> {tctx} : {tclass} {{ {perm} }}`")
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(parts))
        except OSError as e:
            self.display.error(f"Could not save report to {path}: {e}")
            return
        self.display.success(f"Report saved to: {path}")
