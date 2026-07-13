# Changelog

All notable changes are documented here. This project follows
[Keep a Changelog](https://keepachangelog.com/) conventions.

## 2.2.0 — 2026-07-13

### Added
- Knowledge pack grew 35 → 52 error signatures and 82 → 123 VHAL properties.
  New signature coverage: ANR triggers (input dispatch, broadcast, service
  timeouts), main-thread health (slow dispatch, StrictMode), runtime faults
  (CheckJNI aborts, fdsan double-close), HAL/VINTF boot issues (unregistered
  HAL waits, compatibility-matrix mismatches, dm-verity), package/ART failures
  (INSTALL_FAILED_*, dexopt, apexd), API-check build failures, and automotive
  UX (driving-state restrictions, activity blocking, occupant zones). New VHAL
  properties: ADAS (cruise control, AEB, FCW, LDW, LKA, blind spot), wipers,
  interior/exterior light switches, mirrors, regen braking, display units, and
  more HVAC/seat/info properties.

## 2.1.2 — 2026-07-13

### Changed
- Renamed the GitHub repository `AILog` → `ailog-cli` to match the PyPI package
  name (old URLs redirect). All project links updated.
- Default Anthropic model bumped `claude-sonnet-4-20250514` → `claude-sonnet-5`
  (the old model is deprecated upstream). Existing configs keep their saved
  value — run `ailog config --set anthropic_model=claude-sonnet-5` to update.

### Fixed
- README: clarified that the PyPI package is `ailog-cli` while the command is
  `ailog` (and that `pip install ailog` installs an unrelated project); fixed
  the install-from-source `cd` path after the repo rename.
- UNINSTALL.md now covers `pip uninstall ailog-cli` (the primary install path).

## 2.1.1 — 2026-07-10

### Changed
- Renamed the from-source launcher `ailog.py` → `run.py` so it no longer shadows
  the `ailog` package when importing from the repo root; `install.sh` updated to
  match. No change to the installed package (the launcher is not part of the
  wheel/sdist) — `pip` users are unaffected.
- Release workflow reads the package version from installed dist metadata
  (robust regardless of working directory).

## 2.1.0 — 2026-07-10

A large feature + hardening release, and a repositioning around AOSP / Android
Automotive platform development.

### Added
- **AOSP/Automotive knowledge pack** (`knowledge_pack.py`): verified facts keyed by
  log signatures — powers instant, always-correct hints with no AI, and grounds the
  AI with authoritative context so small local models give good answers. Covers ~35
  error signatures (SELinux, native tombstones, binder, watchdog, CarWatchdog,
  CarService, power/user HAL, EVS, VMS, build) plus ~80 VHAL properties.
- **`ailog bugreport`**: triage an `adb bugreport` (`.zip` or `.txt`) — extracts and
  explains Java crashes, native tombstones, ANRs, watchdog kills, and SELinux
  denials. `--no-ai` runs fully offline; `--focus` and `--output` supported.
- **`--json`** output mode for `analyze` and `bugreport` (machine-readable, for CI).
- **`ailog config --set key=value`** to set any config key without hand-editing JSON.
- `tools/gen_vhal_knowledge.py`: generate VHAL knowledge entries from a
  `VehicleProperty.aidl` in an AOSP tree.
- `--no-redact` flag; `dependabot.yml` and a CI coverage job.

### Changed
- Secret redaction now defaults **on for cloud providers** (off for local Ollama),
  covering log content and source files sent to the AI.
- Repositioned for AOSP/Android Automotive platform developers (README, PyPI metadata).
- Minimum Python is now 3.9; CI tests through 3.14.
- Noise filter combines its pattern lists into single regexes (~130 searches per
  line down to a few) for a large speedup on chatty devices.

### Fixed
- **Security:** terminal escape-sequence injection from attacker-controlled log
  lines/AI output (now sanitized before display); config file written atomically at
  0600 (no world-readable window); expanded secret-redaction patterns
  (Authorization/Bearer, JWT, AWS, Slack, Stripe, GitHub, GitLab, PEM, URL creds);
  auto-fix confined to source files inside the project; `--package`/`--device`
  validated before `adb shell`; OpenAI base URLs must be https off-localhost;
  reports written 0700/0600.
- `ailog build` now correctly invokes AOSP's `m` (a shell function) via
  `bash -c 'source build/envsetup.sh && m …'`.
- Commands propagate real exit codes (failed build/analyze no longer exit 0).
- Auto-fix strips markdown fences so AI output can't corrupt source files; all
  source/report I/O is UTF-8.
- Thread-safe AI-call budget in logcat streaming (no overshoot; timer joined on exit).
- Read-timeout no longer crashes on Python 3.9 (`socket.timeout` handled).
- Release workflow gated on tests + tag/version match, least-privilege permissions,
  SHA-pinned third-party actions.

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
