# AILog Architecture

## Overview

AILog uses a two-stage pipeline to interpret Android/AOSP logs:

1. **Stage 1 — Rule-Based Noise Filter** (`noise_filter.py`): Instant, free regex-based filtering that removes ~70% of noise lines. Runs before any AI call.
2. **Stage 2 — AI Analysis** (`ai_client.py`): Sends batched, filtered lines to an AI model for root cause analysis, fix suggestions, and error cascade detection.

## Module Responsibilities

### `cli.py` — Command Router
- Parses arguments with `argparse`
- Routes to the appropriate handler (build, cat, analyze, config)
- Validates API key presence for cloud providers
- Delegates config operations to `ConfigManager`

### `ai_client.py` — Multi-Provider AI Client
- Unified `AIClient` class with `chat(system_prompt, user_message)` interface
- Three provider backends:
  - **Ollama**: Local, free. Uses OpenAI-compatible endpoint at `localhost:11434/v1/chat/completions`
  - **OpenAI-compatible**: Works with OpenAI, Groq, Together, Mistral, any OpenAI-compat API
  - **Anthropic**: Uses Anthropic's native Messages API format
- Internal routing: `_call_openai_compatible()` for Ollama + OpenAI, `_call_anthropic()` for Anthropic
- `list_models()` for Ollama model discovery
- Comprehensive error handling with provider-specific messages

### `noise_filter.py` — Rule-Based Filter
Three pattern categories:
- **ALWAYS_NOISE**: Binder traffic, GC logs, audio HAL polling, property ops, Zygote, SurfaceFlinger, SELinux grants, network routine, ActivityManager lifecycle
- **ALWAYS_KEEP**: Errors, exceptions, crashes, stack traces, segfaults, ANRs, VHAL/CarService/CarAudio issues, build errors
- **BUILD_NOISE**: Progress indicators, Java unchecked warnings, compile/link messages

Filtering modes:
- `low`: Only remove ALWAYS_NOISE
- `medium`: ALWAYS_NOISE + deduplication (normalize timestamps/PIDs/hex addresses)
- `high`: All of above + BUILD_NOISE removal

### `analyzer.py` — Batch File Analyzer
- Auto-detects log type (build vs logcat) via filename heuristics and timestamp patterns
- Handles large files: processes up to 2000 lines (head + tail for larger files)
- Chunks large filtered output into 150-line batches
- Respects `max_ai_calls` limit
- Generates markdown reports with `--output`
- Error handling: binary file detection, empty file, permissions

### `build_wrapper.py` — Build Output Wrapper
- Wraps `m` (AOSP) or `make` subprocess
- Real-time streaming with noise filtering
- Error cluster detection (batch of 80 lines)
- Context window of 30 lines around errors for AI
- Capped AI calls per build session
- Final holistic summary on build failure
- Graceful Ctrl+C handling

### `logcat_wrapper.py` — Logcat Wrapper
- Wraps `adb logcat` subprocess
- Real-time noise filtering with focus keyword support
- Two AI modes:
  - **Batch mode** (default): Background timer thread triggers AI every N seconds
  - **Explain mode**: AI explains each error line immediately
- Thread-safe pending line buffer with `threading.Lock`
- Session summary on exit with error/warning stats
- Graceful SIGINT handling

### `display.py` — Terminal UI
- ANSI color codes with graceful fallback (no-color if not TTY)
- `ai_box()`: Unicode-bordered box for AI analysis output with word wrapping
- `log_line()` / `filtered_line()`: Color-coded log line display
- `stats_bar()`: One-line summary with per-stat coloring
- `Spinner`: Context manager with background thread, proper cleanup with `join(timeout=1.0)`

### `config_manager.py` — Configuration
- JSON config at `~/.config/ailog/config.json`
- Provider-aware API key, model, and URL management
- Environment variable override (OPENAI_API_KEY, ANTHROPIC_API_KEY)
- Corrupted config recovery: backup + recreate defaults
- Per-provider getters/setters

## Threading Model

- **Build wrapper**: Single thread reads subprocess stdout. Spinner runs in background daemon thread.
- **Logcat wrapper**: Main thread reads subprocess. Batch timer runs in background daemon thread. AI lock protects `_pending_for_ai` list.
- **Analyzer**: Main thread with spinner in background daemon thread.
- All spinner threads are daemon threads with proper `join(timeout=1.0)` on exit.

## Error Handling Strategy

All errors follow the principle: **never crash the tool**. Show a warning and continue.

| Error | Response |
|-------|----------|
| Ollama not running | "Ollama is not running. Start with: ollama serve" |
| Invalid API key | "Invalid API key. Run: ailog config --api-key YOUR_KEY" |
| Model not found | "Model 'X' not found. Pull it: ollama pull X" |
| Timeout | "AI request timed out." |
| Rate limit (429) | "Rate limited. Wait and try again." |
| Server error (5xx) | "Server error from provider." |
| File not found | "File not found: path" |
| Binary file | "This appears to be a binary file" |
| Empty file | "File is empty, nothing to analyze" |
| Corrupt config | Backup corrupt file, recreate defaults, warn |
| adb not found | "adb not found. Install Android SDK platform-tools." |
| Build cmd not found | "Build command not found. Are you in an AOSP source tree?" |
