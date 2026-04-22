# AILog — AI-Powered Android/AOSP Log Interpreter

[![Tests](https://github.com/zoddiacc/AILog/actions/workflows/test.yml/badge.svg)](https://github.com/zoddiacc/AILog/actions/workflows/test.yml)
[![PyPI](https://img.shields.io/pypi/v/ailog-cli)](https://pypi.org/project/ailog-cli/)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> Stop drowning in 50,000 lines. Let AI find what matters.

AILog is a CLI tool that interprets Android build logs, logcat output, and AOSP compilation errors using AI. It filters noise first (free, instant), then sends only important lines to an AI model for root cause analysis and fix suggestions.

## Features

- **Two-stage filtering**: Rule-based noise filter removes ~70% of lines before AI, saving tokens and time
- **Multi-provider AI**: Ollama (local, free), OpenAI-compatible APIs, Anthropic Claude
- **Build wrapper**: Wraps `m`/`make` with real-time error interpretation
- **Logcat wrapper**: Wraps `adb logcat` with noise filtering and batch AI analysis
- **File analyzer**: Batch analyze saved log files with chunked processing
- **Automotive-aware**: Special patterns for VHAL, CarService, CarAudio, EVS

## Requirements

- **Python 3.8+** (stdlib only — no pip packages needed)
- **adb** (for `ailog cat`) — included with [Android SDK Platform Tools](https://developer.android.com/tools/releases/platform-tools)
- For local AI: [Ollama](https://ollama.com) with a model pulled
- For cloud AI: API key from OpenAI, Anthropic, Groq, Together, etc.

## Installation

| Platform | `analyze` | `cat` | `build` | Install method |
|----------|-----------|-------|---------|----------------|
| Linux    | Yes | Yes | Yes | `pip install ailog-cli` |
| macOS    | Yes | Yes | Yes | `pip install ailog-cli` |
| Windows  | Yes | Yes | No (AOSP builds are Linux/macOS only) | `pip install ailog-cli` |

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
# Analyze a saved log file
ailog analyze build.log
ailog analyze logcat.txt --focus CarService
ailog analyze build.log --output report.md

# Live logcat with AI
ailog cat --explain                              # AI explains each error inline
ailog cat -p com.example.myapp --explain         # Filter to your app only
ailog cat -s DEVICE_SERIAL --explain             # When multiple devices connected
ailog cat --focus VHAL --noise-level high        # Focus + aggressive filtering

# Wrap an AOSP build
ailog build
ailog build -- -j16 framework
```

## Commands

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
| `--batch-interval <seconds>` | AI summary interval (default: 5) |

### `ailog config`

```bash
ailog config --show              # Show current config
ailog config --provider ollama   # Switch provider
ailog config --api-key sk-xxx    # Set API key
ailog config --model <name>      # Set model
ailog config --base-url <url>    # Custom base URL
ailog config --list-models       # List available Ollama models
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
| `noise_level` | `medium` | Default noise filter level |
| `batch_interval` | `5` | Seconds between AI batches |
| `max_ai_calls` | `5` | Max AI calls per session |

API keys can also be set via environment variables: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`.

## How It Works

```
Input (log file, adb logcat, or make output)
         |
Stage 1: Rule-Based Noise Filter (instant, free)
         |
Stage 2: AI Analysis (only if errors detected, max 5 calls/session)
         |
Terminal Display (color-coded lines, boxed AI analysis, stats bar)
```

## Development

**Testing**: AILog has 136 unit tests covering all major modules. Tests run in CI across Python 3.8, 3.9, 3.10, 3.11, and 3.12 via GitHub Actions, with ruff linting.

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
