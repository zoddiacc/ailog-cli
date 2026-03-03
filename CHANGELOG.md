# Changelog

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
