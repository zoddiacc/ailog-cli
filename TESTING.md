# Testing AILog with an Android App

This guide walks you through testing every AILog feature using a real Android app on a device or emulator.

## Prerequisites

1. Android device or emulator connected via USB/ADB
2. `adb` in your PATH
3. AI provider configured

Verify your setup:

```bash
adb devices                    # Should list your device
ailog config --show            # Check AI provider is set
```

If you haven't configured a provider yet, see the [Quick Start](README.md#quick-start) in the README for full setup steps. Quick version:

```bash
# Option A: Local AI with Ollama (free, no API key)
# 1. Install Ollama from https://ollama.com
# 2. Start it:
ollama serve
# 3. Pull a model (in another terminal):
ollama pull qwen2.5-coder:3b
# 4. List and select a model:
ailog config --list-models       # shows all pulled models
ailog config --model qwen2.5-coder:3b   # select the one to use

# Option B: Cloud AI
ailog config --provider openai
ailog config --api-key sk-...
```

## Command Overview

| Command | What it does | When to use |
|---------|-------------|-------------|
| `ailog cat` | Wraps `adb logcat` — filters noise in real-time, sends errors to AI | While your app is **running** |
| `ailog analyze` | Reads a saved log file and sends it to AI for analysis | After you've **saved** logs to a file |
| `ailog build` | Wraps AOSP `m`/`make` builds with AI interpretation | Only for **AOSP source builds** |

## Live Analysis While Running Your App

### From Android Studio

Android Studio has its own Logcat panel, but AILog adds AI interpretation on top. Run AILog in a **separate terminal** alongside Android Studio:

```bash
# Step 1: Open your terminal (Terminal app, iTerm, Windows Terminal, etc.)
# Step 2: Start AILog — it reads from adb logcat, same device Android Studio uses
ailog cat --explain
```

Now hit **Run** (or **Debug**) in Android Studio as usual. Both Android Studio's Logcat and AILog will show logs simultaneously — Android Studio shows raw logs, AILog shows filtered + AI-analyzed logs.

To focus only on your app:

```bash
# Filter by your app's package name (resolves PID automatically)
ailog cat -p com.your.package --explain

# Multiple devices? Specify which one
ailog cat -s DEVICE_SERIAL -p com.your.package --explain

# Filter by a log tag you use in your code (e.g., Log.e("MyApp", ...))
ailog cat -- -s "MyApp:*"

# Combine package filter + focus + explain
ailog cat -p com.your.package --explain --focus "MyActivity"
```

> **Tip**: Keep Android Studio open for editing/building and AILog in a side terminal for smarter log analysis. They don't interfere with each other — both read from the same `adb logcat` stream.

### From AOSP Source Tree

For AOSP builds, AILog wraps the build command directly:

```bash
# Step 1: Set up your AOSP environment as usual
source build/envsetup.sh
lunch aosp_car_arm64-eng          # or your target

# Step 2: Build through AILog instead of running 'm' directly
ailog build                       # wraps 'm' with AI analysis
ailog build -- -j16 framework     # pass args to make after '--'
ailog build --module CarService   # hint the module for better AI context
```

For live logcat from an AOSP device/emulator:

```bash
# Start the emulator or connect device, then:
ailog cat --explain --focus "VHAL"

# Filter to a specific AOSP app
ailog cat -p com.android.car.settings --explain

# For automotive-specific testing:
ailog cat --noise-level high --focus "CarService" --explain
```

### From a Gradle Build (non-AOSP Android apps)

AILog's `build` command is for AOSP `m`/`make` only. For Gradle-based apps, capture and analyze the build output:

```bash
# Pipe Gradle build output to AILog
./gradlew assembleDebug 2>&1 | ailog analyze -

# Or save first, then analyze
./gradlew assembleDebug 2>&1 > build_output.log
ailog analyze build_output.log --type build
```

## Live Logcat Tests

### Basic: Watch your app's logs

```bash
ailog cat
```

Open your Android app and use it. AILog will:
- Filter out noise (GC, Binder, AudioFlinger spam)
- Color-code lines (red = error, yellow = warning)
- Every 5 seconds, if errors are detected, show an AI analysis in a boxed summary

Press `Ctrl+C` to stop and see a session summary with all errors analyzed.

### Filter by your app's package or tag

```bash
# By package name (recommended — resolves PID automatically)
ailog cat -p com.your.package

# Multiple devices connected? Add -s
ailog cat -s DEVICE_SERIAL -p com.your.package

# By log tag
ailog cat -- -s "YourAppTag:*"
```

### Explain mode: AI explains every error inline

```bash
ailog cat --explain
```

Trigger errors in your app. Each error line gets an AI explanation printed right below it.

### Focus on a specific component

```bash
ailog cat --focus "YourActivity"
ailog cat --focus "NullPointer"
```

AI pays special attention to lines matching the focus keyword, and non-matching non-error lines are filtered out.

### Noise filtering levels

```bash
# High: aggressive filtering, only shows important lines
ailog cat --noise-level high --explain

# Low: shows more lines, minimal filtering
ailog cat --noise-level low
```

### Combined flags

```bash
# Focus + explain + aggressive filtering
ailog cat --focus "VHAL" --noise-level high --explain

# Custom AI batch interval (analyze every 10 seconds instead of 5)
ailog cat --batch-interval 10
```

## Saved Log Analysis

### Capture and analyze

```bash
# Step 1: Capture logs while using your app
adb logcat > my_app_logs.txt
# (Use app, trigger crashes, then Ctrl+C)

# Step 2: Analyze
ailog analyze my_app_logs.txt

# Step 3: Focus on a specific issue
ailog analyze my_app_logs.txt --focus "NullPointerException"

# Step 4: Save the report
ailog analyze my_app_logs.txt --output report.md
```

### Analyze without noise filtering

```bash
# --full sends ALL lines to AI (uses more tokens but nothing is skipped)
ailog analyze my_app_logs.txt --full
```

### Pipe logs from stdin

```bash
# Dump current logcat buffer and analyze
adb logcat -d | ailog analyze -

# Pipe any saved log
cat crash.log | ailog analyze -
```

## Example Logs

The project includes example logs you can use without a device:

```bash
# AOSP build error (linker failure, missing symbols)
ailog analyze examples/build_error.log

# Logcat with VHAL errors, audio focus failures, and a NullPointerException crash
ailog analyze examples/logcat_example.log
```

## Dry Run (No API Calls)

See exactly what would be sent to the AI without making an actual API call:

```bash
ailog --dry-run analyze examples/logcat_example.log
ailog --dry-run cat
```

## Quick Crash Test

The fastest way to see AILog in action:

```bash
# Terminal 1: Start AILog filtered to your app
ailog cat -p com.your.package --explain --noise-level high

# Terminal 2: Force-restart your app to trigger a crash
adb shell am force-stop com.your.package
adb shell am start -n com.your.package/.MainActivity
# Now trigger the crash in your app
```

AILog shows the crash stack trace in red with an AI explanation of the root cause and fix suggestions right below it.

## Running Unit Tests

AILog includes unit tests that run without a device or API key:

```bash
# Run all tests
python3 -m unittest discover -s tests -v

# Run a specific test file
python3 -m unittest tests.test_noise_filter -v
python3 -m unittest tests.test_ai_client -v
python3 -m unittest tests.test_config_manager -v
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `adb not found` | Install [Android SDK Platform Tools](https://developer.android.com/tools/releases/platform-tools) and add to PATH |
| `more than one device/emulator` | Multiple devices connected. Specify one: `ailog cat -s SERIAL --explain` (find serials with `adb devices`) |
| `Could not find running process` | The app isn't running on the device. Launch it first, then use `-p` |
| `No API key configured` | Run `ailog config --api-key YOUR_KEY` or switch to Ollama: `ailog config --provider ollama` |
| `Connection refused` (Ollama) | Ollama server isn't running. Start it: `ollama serve` |
| `Model not found` (Ollama) | You haven't pulled the model yet. Run: `ollama pull qwen2.5-coder:3b` |
| `ailog config --list-models` shows nothing | Either Ollama isn't running (`ollama serve`) or no models are pulled yet |
| AI responses are slow (Ollama) | Use a smaller model: `ailog config --model qwen2.5-coder:3b`. Larger models need more RAM/GPU |
| AI analysis says "token limit" | Use `--noise-level high` to reduce input size |
| Too much noise in output | Use `--noise-level high` or `--focus "YourTag"` |
| Not enough detail | Use `--noise-level low` or `--full` (for analyze) |
