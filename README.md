# AILog — AI Log Triage for AOSP & Android Automotive

[![Tests](https://github.com/zoddiacc/AILog/actions/workflows/test.yml/badge.svg)](https://github.com/zoddiacc/AILog/actions/workflows/test.yml)
[![PyPI](https://img.shields.io/pypi/v/ailog-cli)](https://pypi.org/project/ailog-cli/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Stop drowning in 50,000 log lines. Let AILog find what matters.**

AILog reads your AOSP build errors, `adb logcat`, and full bugreports — and tells you
what actually broke and how to fix it. It's built for **AOSP and Android Automotive
(AAOS) platform developers** debugging VHAL, CarService, HALs, and native crashes in a
terminal.

- 🔒 **Local-first** — runs on Ollama by default, so your logs never leave your machine
- 🚗 **Automotive-aware** — ships a knowledge pack of VHAL, SELinux, tombstone & CarService facts
- 🪶 **Zero dependencies** — pure Python standard library, installs anywhere
- ⚡ **Works offline** — instant rule-based triage even with no AI model at all

```bash
pip install ailog-cli
```

---

## See it in action

Turn a 100 MB bugreport into a ranked list of real problems — instantly, with no model needed:

```console
$ ailog bugreport bugreport-car-2026.zip --no-ai

═════════════════ AILog — Bugreport Triage ═════════════════
ℹ️  Build fingerprint: Android/car_x86_64/emu:14/UQ1A.240101
   java crashes: 1  │  native crashes: 1  │  ANRs: 1  │  SELinux: 1

▶ 1. [NATIVE] Native crash — signal 6 (SIGABRT)
   ↳ [Native crash] SIGABRT means abort() — often a failed CHECK/assert.
     Read the 'abort message:' line first, then symbolize the backtrace.

▶ 2. [ANR] ANR in com.oem.telemetry
   ↳ App Not Responding: com.oem.telemetry

▶ SELinux denials (1 unique)
   ↳ [SELinux] Denied — add an allow rule to the domain's .te file
     u:r:hal_vehicle_default:s0 → u:object_r:sysfs:s0 : file { read }
```

Add a model and it explains each crash in depth. Point it at a live device
(`ailog cat --explain`) or your AOSP build (`ailog build`) for the same treatment.

---

## Get started in 60 seconds

**1. Install**

```bash
pip install ailog-cli
```

**2. Try it with zero setup** — the knowledge pack works with no AI at all:

```bash
ailog bugreport your-bugreport.zip --no-ai
```

**3. Turn on AI** — pick one:

<details open>
<summary><b>Option A · Local &amp; private (recommended, free)</b></summary>

```bash
# Install Ollama once: https://ollama.com
ollama pull qwen2.5-coder:3b     # ~2 GB, one-time download
```

That's it — AILog uses Ollama by default. Nothing leaves your machine.
</details>

<details>
<summary><b>Option B · Cloud (OpenAI / Anthropic / Groq / …)</b></summary>

```bash
ailog config --provider openai --api-key sk-...
# or
ailog config --provider anthropic --api-key sk-ant-...
# or any OpenAI-compatible endpoint:
ailog config --provider openai --base-url https://api.groq.com/openai/v1 --api-key ...
```

Secrets in your logs are redacted before anything is sent. See [Privacy](#privacy).
</details>

**4. Use it**

```bash
ailog analyze build.log          # analyze a saved log
ailog cat --explain              # live logcat, explained inline
ailog build                      # wrap an AOSP build
ailog bugreport report.zip       # triage a bugreport
```

Run `ailog --help` or `ailog <command> --help` for everything.

---

## Why AILog is different

Most people run a **small local model** (the default is `qwen2.5-coder:3b`) that knows
almost nothing about VHAL, CarService, SELinux, or tombstones. A generic "pipe the log
to an LLM" tool gives weak or wrong answers for automotive internals as a result.

AILog keeps the domain intelligence in **curated data it ships**, not the model's
weights. A built-in [knowledge pack](#the-knowledge-pack) maps log signatures to
verified facts — so even a tiny local model gives genuinely good answers, and the
common cases are explained instantly with **no AI at all**.

---

## What you can do

| Command | What it does | Needs |
|---------|--------------|-------|
| `ailog analyze <file>` | Analyze a saved build/logcat file | a file |
| `ailog bugreport <file>` | Triage an `adb bugreport` (.zip/.txt) | a file |
| `ailog cat` | AI-filtered live `adb logcat` | `adb` + device |
| `ailog build` | Wrap an AOSP `m`/`make` build | AOSP tree (Linux/macOS) |
| `ailog config` | Configure provider, model, keys | — |

```bash
# Analyze
ailog analyze logcat.txt --focus CarService      # focus the AI on a component
ailog analyze build.log --output report.md       # save a markdown report

# Bugreport triage
ailog bugreport report.zip --no-ai               # instant, offline, no model
ailog bugreport report.zip --focus com.oem.app   # only issues touching a package

# Live logcat
ailog cat --explain                              # explain each error inline
ailog cat --focus VHAL --noise-level high        # focus + aggressive filtering
ailog cat -p com.example.app --explain           # filter to one app

# AOSP build (run from a lunch'd shell)
ailog build
ailog build -- -j16 framework

# Machine-readable output for CI
ailog --json bugreport report.zip --no-ai | jq '.issue_counts'
```

<details>
<summary><b>All flags (per command)</b></summary>

**Global** (place before the subcommand, e.g. `ailog --json analyze x.log`)

| Flag | Description |
|------|-------------|
| `--json` | Machine-readable JSON output (`analyze`, `bugreport`) |
| `--redact` / `--no-redact` | Force secret redaction on/off (on by default for cloud) |
| `--dry-run` | Show the AI call without sending it |
| `--show-tokens` | Print estimated token counts |
| `--no-color` | Disable colored output |

**`ailog analyze <file>`** — `--type build\|logcat\|auto`, `--full` (no filtering), `--output <path>`, `--focus <keyword>`

**`ailog bugreport <file>`** — `--no-ai` (offline triage), `--focus <keyword>`, `--output <path>`

**`ailog cat`** — `-s/--device <serial>`, `-p/--package <pkg>`, `--noise-level low\|medium\|high`, `--focus <tag>`, `--explain`, `--no-source`, `--batch-interval <sec>`

**`ailog build`** — `--no-filter`, `--summary-only`, `--module <name>`
</details>

---

## Configuration

AILog works out of the box with Ollama — you only need `config` to switch providers or
tune behavior.

```bash
ailog config --show                       # see current settings
ailog config --provider anthropic         # switch provider
ailog config --model qwen2.5-coder:7b     # pick a model
ailog config --list-models                # list installed Ollama models
ailog config --set noise_level=high       # set any option (below)
ailog config --reset                      # back to defaults
```

Config lives at `~/.config/ailog/config.json` (created with `0600` permissions). API
keys can also come from `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` env vars, which take
precedence.

<details>
<summary><b>All config keys</b></summary>

| Key | Default | Description |
|-----|---------|-------------|
| `provider` | `ollama` | `ollama`, `openai`, or `anthropic` |
| `ollama_model` | `qwen2.5-coder:3b` | Local model (try `:7b` for better results) |
| `ollama_url` | `http://localhost:11434` | Ollama server URL |
| `openai_model` | `gpt-4o-mini` | OpenAI model |
| `openai_url` | `https://api.openai.com/v1` | OpenAI-compatible base URL |
| `anthropic_model` | `claude-sonnet-4-20250514` | Anthropic model |
| `noise_level` | `medium` | Filter aggressiveness: `low`/`medium`/`high` |
| `batch_interval` | `5` | Seconds between AI batches (live `cat`) |
| `max_ai_calls` | `5` | Max AI calls per session |
| `timeout` | `30` | AI request timeout (seconds) |
| `system_prompt` | `""` | Override the AI system prompt |

Set any of these with `ailog config --set key=value`.
</details>

### Privacy

With local Ollama (the default) **nothing leaves your machine** — ideal for OEM and
Tier-1 environments. When you use a cloud provider, secrets (API keys, tokens,
passwords, JWTs, …) are **redacted from log content and source files by default**
before anything is sent. Pass `--no-redact` only if you understand the implications.

---

## Requirements

- **Python 3.9+** (standard library only — no pip dependencies)
- **adb** for `ailog cat` — from [Android SDK Platform Tools](https://developer.android.com/tools/releases/platform-tools)
- **Ollama** for local AI ([ollama.com](https://ollama.com)), or an API key for cloud AI

| Platform | `analyze` · `bugreport` | `cat` | `build` |
|----------|:---:|:---:|:---:|
| Linux / macOS | ✅ | ✅ | ✅ |
| Windows | ✅ | ✅ | ❌ (AOSP builds are Linux/macOS only) |

`analyze` and `bugreport` need only a file — no device or adb.

<details>
<summary><b>Install from source</b></summary>

```bash
git clone https://github.com/zoddiacc/AILog.git && cd AILog
bash install.sh                 # installs to ~/.local/bin
# or run directly without installing:
python3 run.py --help
```

If `~/.local/bin` isn't on your PATH:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc
```
</details>

---

## How it works

```
Input (log file, adb logcat, bugreport, or build output)
        │
Stage 1 · Rule-based noise filter    → drops ~70% of lines (instant, free)
        │
Stage 2 · Knowledge-pack lookup      → instant hint (no AI) + facts for the AI
        │
Stage 3 · AI analysis (if needed)    → explains the rest, grounded in Stage 2
        │
Terminal output (color-coded lines, boxed analysis, stats)
```

### The knowledge pack

The heart of AILog. It maps log signatures to verified AOSP/Automotive facts (what a
VHAL property means and which `Car.PERMISSION_*` it needs, how to read an `avc: denied`
line, what a `SIGABRT` tombstone implies), used two ways:

1. **Instant hints, no AI** — a matching line gets an always-correct one-liner
   immediately. This is why `ailog bugreport --no-ai` is genuinely useful offline.
2. **Grounded AI answers** — the matching facts are injected into the prompt as
   authoritative context, so a small local model summarizes known-good knowledge
   instead of guessing.

It currently covers **35+ error signatures** and **80+ VHAL properties** (powertrain,
energy/EV, HVAC, body, power/user HAL, watchdog, cluster, diagnostics). It's pure data,
so it grows without code changes — and `tools/gen_vhal_knowledge.py` can generate VHAL
entries straight from a `VehicleProperty.aidl` in an AOSP tree.

---

## Contributing

Contributions are welcome — especially new **knowledge-pack entries** (VHAL properties,
SELinux/CarService/build signatures), which are pure data and a great first PR. See
**[CONTRIBUTING.md](CONTRIBUTING.md)** for setup, and **[SECURITY.md](SECURITY.md)** to
report vulnerabilities privately.

```bash
python3 -m unittest discover -s tests -v     # run the test suite
ruff check src/ tests/ tools/                # lint
```

Tests run in CI across Python 3.9–3.14 with ruff linting.

## Further reading

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — design and internals
- **[TESTING.md](TESTING.md)** — testing against a real Android device
- **[CONTRIBUTING.md](CONTRIBUTING.md)** · **[CHANGELOG.md](CHANGELOG.md)** · **[UNINSTALL.md](UNINSTALL.md)**

## License

MIT
