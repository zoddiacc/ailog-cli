# AILog — AI Log Triage for AOSP & Android Automotive

[![Tests](https://github.com/zoddiacc/AILog/actions/workflows/test.yml/badge.svg)](https://github.com/zoddiacc/AILog/actions/workflows/test.yml)
[![PyPI](https://img.shields.io/pypi/v/ailog-cli)](https://pypi.org/project/ailog-cli/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> Stop drowning in 50,000 lines. Let AI find what matters.

AILog is a CLI tool for **AOSP and Android Automotive (AAOS) platform developers** — the people debugging VHAL, CarService, HALs, and framework code in a terminal, not an IDE. It wraps `m` builds and `adb logcat`, filters the noise with rule-based patterns first (free, instant), then sends only the important lines to an AI model for root-cause analysis and fix suggestions.

By default the AI runs **locally via Ollama, so logs never leave your machine** — built for OEM and Tier-1 environments where they can't. It works just as well on regular Android app logcat, too.

## Features

- **AOSP/Automotive knowledge pack**: A built-in library of verified facts — VHAL properties, SELinux denials, native tombstones, CarWatchdog, power/user HAL, binder — that explains automotive errors *without* relying on the model's own knowledge, so even a small local model gives good answers ([details below](#the-knowledge-pack--how-small-models-punch-above-their-weight))
- **Bugreport triage**: Point `ailog bugreport` at a giant `adb bugreport` and get a ranked list of crashes, ANRs, native tombstones, watchdog kills, and SELinux denials — each explained
- **Automotive-aware**: Dedicated patterns for VHAL, CarService, CarAudio, EVS, CarWatchdog, power management
- **AOSP build wrapper**: Wraps `m`/`make` with real-time error interpretation
- **Local-first AI**: Ollama by default (logs stay on your machine); OpenAI-compatible APIs and Anthropic Claude optional
- **Two-stage filtering**: Rule-based noise filter removes ~70% of lines before AI, saving tokens and time
- **Logcat wrapper**: Wraps `adb logcat` with noise filtering and batch AI analysis
- **File analyzer**: Batch analyze saved log files with chunked processing

## Requirements

- **Python 3.9+** (stdlib only — no pip packages needed)
- **adb** (for `ailog cat`) — included with [Android SDK Platform Tools](https://developer.android.com/tools/releases/platform-tools)
- For local AI: [Ollama](https://ollama.com) with a model pulled
- For cloud AI: API key from OpenAI, Anthropic, Groq, Together, etc.

## Installation

| Platform | `analyze` | `bugreport` | `cat` | `build` | Install method |
|----------|-----------|-----------|-------|---------|----------------|
| Linux    | Yes | Yes | Yes | Yes | `pip install ailog-cli` |
| macOS    | Yes | Yes | Yes | Yes | `pip install ailog-cli` |
| Windows  | Yes | Yes | Yes | No (AOSP builds are Linux/macOS only) | `pip install ailog-cli` |

`analyze` and `bugreport` work on any log file/bugreport (no device or adb needed);
`cat` needs `adb`; `build` needs a Linux/macOS AOSP tree.

### pip (Recommended)

```bash
pip install ailog-cli
```

### Linux / macOS (from source)

```bash
git clone https://github.com/zoddiacc/AILog.git && cd AILog
bash install.sh
```

If `~/.local/bin` is not in your PATH:
```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc   # Bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc     # Zsh
```

### Windows

```powershell
pip install ailog-cli
ailog --help
```

## Quick Start

### Ollama (Local, Free — Default)

```bash
# 1. Install Ollama from https://ollama.com, or:
brew install ollama              # macOS
curl -fsSL https://ollama.ai/install.sh | sh   # Linux

# 2. Start the server and pull a model
ollama serve                     # keep running in background
ollama pull qwen2.5-coder:3b    # in another terminal (~2 GB)

# 3. Verify and select a model
ailog config --list-models       # list all pulled models
ailog config --model qwen2.5-coder:3b   # select the model to use

# 4. Test it
ailog analyze examples/build_error.log
```

> **Model tips**: `qwen2.5-coder:3b` is the default — fast and lightweight (~2 GB). For better results, try `qwen2.5-coder:7b` or `codellama:13b`. Pull any model with `ollama pull <name>`, then select it with `ailog config --model <name>`.

### Cloud Providers

```bash
# OpenAI / Groq / Together / etc.
ailog config --provider openai
ailog config --api-key sk-...
ailog config --model gpt-4o-mini
ailog config --base-url https://api.groq.com/openai/v1   # for non-OpenAI providers

# Anthropic Claude
ailog config --provider anthropic
ailog config --api-key sk-ant-...
```

## Usage

```bash
# Wrap an AOSP build (run from a lunch'd shell)
ailog build
ailog build -- -j16 framework

# Live logcat with AI
ailog cat --focus VHAL --noise-level high        # Focus on a component + aggressive filtering
ailog cat --explain                              # AI explains each error inline
ailog cat -s DEVICE_SERIAL --explain             # When multiple devices connected
ailog cat -p com.example.myapp --explain         # App development: filter to one package

# Analyze a saved log file
ailog analyze build.log
ailog analyze logcat.txt --focus CarService
ailog analyze build.log --output report.md

# Triage an adb bugreport (crashes, ANRs, native tombstones, SELinux denials)
ailog bugreport bugreport-device-2026.zip
ailog bugreport bugreport.zip --no-ai            # Instant triage, no model needed
ailog bugreport bugreport.zip --focus com.oem.dashboard --output triage.md
```

## Commands

### Global options

These apply to any command (place them before the subcommand, e.g. `ailog --redact cat`):

| Flag | Description |
|------|-------------|
| `--redact` / `--no-redact` | Force secret redaction on/off before sending log content to AI. **On by default for cloud providers, off for local Ollama.** |
| `--dry-run` | Show what AI call would be made without sending it |
| `--show-tokens` | Print estimated token counts for AI calls |
| `--no-color` | Disable colored output |

> **Privacy:** with local Ollama (the default) nothing leaves your machine. When you switch to a cloud provider, secrets (API keys, tokens, passwords, JWTs, etc.) are redacted from log content and source files by default — pass `--no-redact` only if you understand the implications.

### `ailog analyze <file>`

| Flag | Description |
|------|-------------|
| `--type build\|logcat\|auto` | Log type (default: auto-detect) |
| `--full` | Disable noise filtering |
| `--output <path>` | Save report to file |
| `--focus <keyword>` | Focus AI on specific component |

### `ailog build [-- make args]`

| Flag | Description |
|------|-------------|
| `--no-filter` | Show all logs |
| `--summary-only` | Hide raw logs, show AI summary only |
| `--module <name>` | Module hint for better AI context |

### `ailog cat [adb logcat args]`

| Flag | Description |
|------|-------------|
| `-s, --device <serial>` | Target device when multiple are connected |
| `-p, --package <pkg>` | Filter by app package name (resolves PID automatically) |
| `--noise-level low\|medium\|high` | Filtering aggressiveness |
| `--focus <tag/keyword>` | Focus AI attention |
| `--explain` | Inline AI explanations for each error |
| `--no-source` | Don't read source files for crash-fix suggestions |
| `--batch-interval <seconds>` | AI summary interval (default: 5) |

### `ailog bugreport <file>`

Triage an `adb bugreport` (`.zip` or `.txt`) — extracts Java crashes, native
tombstones, ANRs, watchdog kills, and SELinux denials, and explains each using
the AOSP/Automotive knowledge pack (and optionally AI).

| Flag | Description |
|------|-------------|
| `--no-ai` | Knowledge-pack triage only, no AI calls (works fully offline) |
| `--focus <keyword>` | Only show issues mentioning this package/keyword |
| `--output <path>` | Save the triage report to a markdown file |

### `ailog config`

```bash
ailog config --show              # Show current config
ailog config --provider ollama   # Switch provider
ailog config --api-key sk-xxx    # Set API key
ailog config --model <name>      # Set model
ailog config --base-url <url>    # Custom base URL
ailog config --list-models       # List available Ollama models
ailog config --set KEY=VALUE     # Set any config key (e.g. --set noise_level=high)
ailog config --reset             # Reset to defaults
```

## Configuration

Config file: `~/.config/ailog/config.json`

| Key | Default | Description |
|-----|---------|-------------|
| `provider` | `ollama` | AI provider: ollama, openai, anthropic |
| `ollama_url` | `http://localhost:11434` | Ollama server URL |
| `ollama_model` | `qwen2.5-coder:3b` | Ollama model |
| `openai_url` | `https://api.openai.com/v1` | OpenAI-compatible base URL |
| `openai_model` | `gpt-4o-mini` | OpenAI model |
| `anthropic_model` | `claude-sonnet-4-20250514` | Anthropic model |
| `noise_level` | `medium` | Default noise filter level (low/medium/high) |
| `batch_interval` | `5` | Seconds between AI batches |
| `max_ai_calls` | `5` | Max AI calls per session |
| `timeout` | `30` | AI request timeout (seconds) |
| `system_prompt` | `""` | Override the AI system prompt (empty = built-in) |

Any of these can be set with `ailog config --set key=value`.

API keys can also be set via environment variables: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`.

## How It Works

```
Input (log file, adb logcat, bugreport, or make output)
         |
Stage 1: Rule-Based Noise Filter (instant, free) — drops ~70% of lines
         |
Stage 2: Knowledge Pack lookup — matches known AOSP/Automotive signatures
         |         ├─ produces an instant, always-correct hint (no AI needed)
         |         └─ supplies verified facts as context for the AI step
         |
Stage 3: AI Analysis (only if errors detected) — explains the rest,
         grounded in the facts from Stage 2
         |
Terminal Display (color-coded lines, boxed AI analysis, stats bar)
```

## The knowledge pack — how small models punch above their weight

Most people running this tool use a **small local model** (the default is
`qwen2.5-coder:3b`) that knows little about VHAL, CarService, SELinux, or native
tombstones. A generic "pipe the log to an LLM" tool gives weak or wrong answers
for automotive platform issues as a result.

AILog fixes this by keeping the domain intelligence in **curated data it ships**,
not in the model's weights. A built-in knowledge pack maps log signatures to
verified facts (what a VHAL property means and which `Car.PERMISSION_*` it needs,
how to read an `avc: denied` line, what a `SIGABRT` tombstone implies, and so on).
It's used two ways:

1. **Instant hints, no AI** — when a line matches a known signature, you get an
   always-correct one-liner immediately. This works fully offline, which is why
   `ailog bugreport --no-ai` is genuinely useful with no model at all.
2. **Grounded AI answers** — the matching facts are injected into the AI prompt as
   authoritative context, so a small local model *summarizes known-good knowledge*
   instead of guessing.

The pack currently covers ~35 error signatures plus ~80 VHAL properties across
powertrain, energy/EV, HVAC, body, power management, user HAL, watchdog, cluster,
and diagnostics — and it's pure data, so it grows without code changes.
`tools/gen_vhal_knowledge.py` can extend the VHAL coverage straight from a
`VehicleProperty.aidl` in an AOSP tree.

## Development

**Testing**: AILog has an extensive unit-test suite covering all major modules. Tests run in CI across Python 3.8, 3.9, 3.10, 3.11, and 3.12 via GitHub Actions, with ruff linting.

```bash
python3 -m unittest discover -s tests -v
```

## Further Reading

- **[TESTING.md](TESTING.md)** — Step-by-step guide to test AILog with a real Android app
- **[UNINSTALL.md](UNINSTALL.md)** — How to completely remove AILog
- **[ARCHITECTURE.md](ARCHITECTURE.md)** — Technical architecture and design decisions
- **[CHANGELOG.md](CHANGELOG.md)** — Version history

## License

MIT
