# Changelog

All notable changes are documented here. This project follows
[Keep a Changelog](https://keepachangelog.com/) conventions.

## Unreleased

### Added
- **AOSP/Automotive knowledge pack** (`knowledge_pack.py`): verified facts keyed by
  log signatures — powers instant, always-correct hints with no AI, and grounds the
  AI with authoritative context so small local models give good answers. Covers ~35
  error signatures (SELinux, native tombstones, binder, watchdog, CarWatchdog,
  CarService, power/user HAL, EVS, VMS, build) plus ~80 VHAL properties.
- **`ailog bugreport`**: triage an `adb bugreport` (`.zip` or `.txt`) — extracts and
  explains Java crashes, native tombstones, ANRs, watchdog kills, and SELinux
  denials. `--no-ai` runs fully offline; `--focus` and `--output` supported.
- `tools/gen_vhal_knowledge.py`: generate VHAL knowledge entries from a
  `VehicleProperty.aidl` in an AOSP tree.
- `--no-redact` flag; `dependabot.yml` for GitHub Actions.

### Changed
- Secret redaction now defaults **on for cloud providers** (off for local Ollama),
  covering log content and source files sent to the AI.
- Repositioned for AOSP/Android Automotive platform developers (README, PyPI metadata).
- Minimum Python is now 3.9; CI tests through 3.14.

### Fixed
- **Security:** terminal escape-sequence injection from attacker-controlled log
  lines/AI output (now sanitized before display); config file written atomically at
  0600 (no world-readable window); expanded secret-redaction patterns
  (Authorization/Bearer, JWT, AWS, Slack, Stripe, GitHub, GitLab, PEM, URL creds).
- `ailog build` now correctly invokes AOSP's `m` (a shell function) via
  `bash -c 'source build/envsetup.sh && m …'`.
- Commands propagate real exit codes (failed build/analyze no longer exit 0).
- Auto-fix strips markdown fences so AI output can't corrupt source files.
- Read-timeout no longer crashes on Python 3.9 (`socket.timeout` handled).

## 2.0.3 — 2026-04-22

### Fixed
- Deprecation warnings in CI workflows and `pyproject.toml`.
- License metadata reverted to table format for Python 3.8 compatibility.

## 2.0.2 — 2026-04-18

### Changed
- README: PyPI install instructions and badge.

## 2.0.1 — 2026-04-18

### Changed
- Renamed the PyPI package to `ailog-cli` (the name `ailog` was taken).

## 2.0.0 — 2026-03-04

Complete rebuild of AILog with multi-provider support and bug fixes.

### Added
- Multi-provider AI client: Ollama (local, free), OpenAI-compatible, Anthropic
- Ollama as default provider — no API key needed for local use
- `ailog config --provider` to switch between providers
- `ailog config --list-models` to list available Ollama models
- `ailog config --base-url` for custom API endpoints (Groq, Together, etc.)
- `ailog config --model` to set model per provider
- Binary file detection in analyzer
- Empty file detection in analyzer
- Large file handling: head+tail for files >2000 lines
- Max AI calls limit (configurable, default 5) across all commands
- Progress tracking for chunked analysis
- Provider info in stats bar
- Corrupted config recovery (backup + recreate defaults)

### Fixed
- Analyzer chunking bug: broken `any()` expression in chunk error detection
- Spinner thread cleanup: proper `join(timeout=1.0)` instead of orphaned threads
- Race condition in logcat wrapper: `_pending_for_ai` now protected by lock
- Unlimited AI calls: all commands now respect `max_ai_calls` config
- Installer: matches new `src/ailog/` package structure
- Entry point: proper absolute path for `sys.path`
- Dedup normalization: hex addresses now normalized for better dedup

### Changed
- Renamed from `alog` to `ailog`
- Restructured as `src/ailog/` Python package
- Config location: `~/.config/ailog/config.json`
- AI client accepts ConfigManager directly instead of raw API key
- `--set-key` renamed to `--api-key`
- Default provider is Ollama (was Anthropic-only)

## 1.0.0

Initial release with Anthropic-only AI client.
