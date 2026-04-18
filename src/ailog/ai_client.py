"""
Multi-provider AI client for log analysis.
Supports: Ollama (local), OpenAI-compatible APIs, Anthropic.
"""

import json
import re
import sys
import time
import urllib.request
import urllib.error

# Patterns for common secrets that should be redacted before sending to AI
_SECRET_PATTERNS = [
    re.compile(r'(?i)(api[_-]?key|apikey)\s*[:=]\s*\S+'),
    re.compile(r'(?i)(secret|password|passwd|pwd)\s*[:=]\s*\S+'),
    re.compile(r'(?i)(token|auth|bearer)\s*[:=]\s*\S+'),
    re.compile(r'(?i)(access[_-]?key|secret[_-]?key)\s*[:=]\s*\S+'),
    re.compile(r'sk-[a-zA-Z0-9]{20,}'),       # OpenAI keys
    re.compile(r'sk-ant-[a-zA-Z0-9-]{20,}'),   # Anthropic keys
    re.compile(r'ghp_[a-zA-Z0-9]{36,}'),       # GitHub PATs
    re.compile(r'gho_[a-zA-Z0-9]{36,}'),       # GitHub OAuth
    re.compile(r'AIza[a-zA-Z0-9_-]{35}'),      # Google API keys
]


def _redact_secrets(text):
    """Strip common secret patterns from text."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub('[REDACTED]', text)
    return text


SYSTEM_PROMPT = """You are an expert Android/AOSP and automotive software engineer specializing in log analysis.
Your job is to interpret Android build logs, logcat output, and AOSP compilation errors for developers.

When analyzing logs:
1. IDENTIFY the root cause clearly — not just symptoms
2. EXPLAIN in plain English what went wrong and why
3. SUGGEST concrete fixes (commands, code changes, config changes)
4. NOTE the cascade: if error A caused errors B and C, say so
5. FLAG automotive/HAL/VHAL/CarService issues with extra context
6. Be CONCISE — developers are busy. No fluff.

Format your response with clear sections:
- 🔴 ROOT CAUSE (1-2 sentences)
- 📋 WHAT HAPPENED (brief explanation)
- 🔧 HOW TO FIX (numbered steps, be specific)
- 💡 CONTEXT (optional: why this happens, related issues)

Keep the total response under 400 words unless the issue is truly complex."""


NOISE_FILTER_PROMPT = """You are a log filter for Android/AOSP development.
Given a batch of log lines, return ONLY the important ones.

Remove:
- Verbose Binder transaction logs
- HAL polling heartbeats
- Routine GC logs
- Standard service startup messages (unless they fail)
- Repetitive identical lines (show first + count)
- Debug logs from framework internals that aren't errors
- Audio/media routine state changes
- Routine property set/get logs

Keep:
- ALL errors and exceptions
- ALL warnings that indicate actual issues
- Stack traces (full)
- Build failures
- Service crashes or ANRs
- VHAL/CarService errors
- Memory/permission errors
- First occurrence of repeated patterns

Respond with JSON: {"kept": ["line1", "line2", ...], "filtered_count": N, "patterns": ["repeated pattern summary"]}
Return ONLY valid JSON, no other text."""


class AIClient:
    """Multi-provider AI client with unified interface."""

    def __init__(self, config):
        """
        config: ConfigManager instance (or any object with provider, get_api_key(),
                get_model(), get_base_url() methods).
        """
        self.provider = config.provider
        self.api_key = config.get_api_key()
        self.model = config.get_model()
        self.base_url = config.get_base_url()
        self.timeout = config.get('timeout', 30)
        self.dry_run = getattr(config, 'dry_run', False)
        self.show_tokens = getattr(config, 'show_tokens', False)
        self.redact = getattr(config, 'redact', False)
        self._system_prompt = config.get('system_prompt', '') or SYSTEM_PROMPT

    @staticmethod
    def _estimate_tokens(text):
        """Estimate token count using ~4 chars per token heuristic."""
        return max(1, len(text) // 4)

    def chat(self, system_prompt, user_message, max_tokens=1000, timeout=None):
        """Send a chat request to the configured provider. Returns response text."""
        if self.redact:
            user_message = _redact_secrets(user_message)
        if self.dry_run:
            prompt_tokens = self._estimate_tokens(system_prompt + user_message)
            preview = user_message[:200] + ('...' if len(user_message) > 200 else '')
            return (
                f"[DRY RUN] Would call {self.provider} ({self.model})\n"
                f"  System prompt: {len(system_prompt)} chars\n"
                f"  User message: {len(user_message)} chars\n"
                f"  Estimated input tokens: ~{prompt_tokens}\n"
                f"  Max output tokens: {max_tokens}\n"
                f"  Preview: {preview}"
            )

        effective_timeout = timeout or self.timeout

        if self.provider == "anthropic":
            result = self._call_anthropic(system_prompt, user_message, max_tokens, effective_timeout)
        else:
            # Both ollama and openai use OpenAI-compatible API
            result = self._call_openai_compatible(system_prompt, user_message, max_tokens, effective_timeout)

        if self.show_tokens:
            input_tokens = self._estimate_tokens(system_prompt + user_message)
            output_tokens = self._estimate_tokens(result) if result else 0
            print(
                f"\033[2m  [tokens] ~{input_tokens} in, ~{output_tokens} out\033[0m",
                file=sys.stderr
            )

        return result

    def _call_openai_compatible(self, system_prompt, user_message, max_tokens, timeout):
        """Call OpenAI-compatible API (works for Ollama and OpenAI/Groq/Together/etc)."""
        if self.provider == "ollama":
            url = f"{self.base_url}/v1/chat/completions"
        else:
            url = f"{self.base_url}/chat/completions"

        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        }

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        return self._http_post(url, payload, headers, self._parse_openai_response, timeout)

    def _call_anthropic(self, system_prompt, user_message, max_tokens, timeout):
        """Call Anthropic Messages API."""
        url = f"{self.base_url}/messages"
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_message},
            ],
        }
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        return self._http_post(url, payload, headers, self._parse_anthropic_response, timeout)

    def _http_post(self, url, payload, headers, parse_fn, timeout=None):
        """Execute HTTP POST with comprehensive error handling and 5xx retry."""
        effective_timeout = timeout or self.timeout
        data = json.dumps(payload).encode("utf-8")

        for attempt in range(2):
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=effective_timeout) as response:
                    result = json.loads(response.read().decode("utf-8"))
                    return parse_fn(result)
            except urllib.error.HTTPError as e:
                if e.code >= 500 and attempt == 0:
                    time.sleep(2)
                    continue
                self._handle_http_error(e)
            except urllib.error.URLError as e:
                self._handle_url_error(e)
            except json.JSONDecodeError:
                raise RuntimeError("Failed to parse AI response as JSON.")
            except TimeoutError:
                raise RuntimeError(
                    "AI request timed out. Check your connection or try a smaller model."
                )

    def _parse_openai_response(self, result):
        """Parse OpenAI-compatible response format."""
        try:
            return result["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            # Try to return something useful
            return str(result)

    def _parse_anthropic_response(self, result):
        """Parse Anthropic Messages API response format."""
        try:
            return result["content"][0]["text"]
        except (KeyError, IndexError):
            return str(result)

    def _handle_http_error(self, e):
        """Handle HTTP errors with provider-specific messages."""
        code = e.code
        try:
            body = e.read().decode("utf-8")
            err_data = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            body = str(e)
            err_data = {}

        if code == 401:
            if self.provider == "ollama":
                raise RuntimeError("Unexpected auth error from Ollama.")
            raise RuntimeError(
                f"Invalid API key for {self.provider}. "
                f"Run: ailog config --api-key YOUR_KEY"
            )
        elif code == 404:
            model = self.model
            if self.provider == "ollama":
                raise RuntimeError(
                    f"Model '{model}' not found in Ollama. "
                    f"Pull it with: ollama pull {model}\n"
                    f"Or list available: ailog config --list-models"
                )
            raise RuntimeError(
                f"Model '{model}' not found. Check the model name for your provider."
            )
        elif code == 429:
            raise RuntimeError(
                "Rate limited by AI provider. Wait a moment and try again."
            )
        elif code >= 500:
            # Extract message if available
            msg = ""
            if isinstance(err_data, dict):
                msg = err_data.get("error", {}).get("message", "")
            raise RuntimeError(
                f"Server error ({code}) from {self.provider}. {msg}"
            )
        else:
            msg = ""
            if isinstance(err_data, dict):
                msg = err_data.get("error", {}).get("message", body[:200])
            raise RuntimeError(f"API error {code}: {msg}")

    def _handle_url_error(self, e):
        """Handle connection-level errors."""
        reason = str(e.reason) if hasattr(e, "reason") else str(e)
        if "Connection refused" in reason or "Errno 111" in reason or "Errno 61" in reason:
            if self.provider == "ollama":
                raise RuntimeError(
                    "Ollama is not running. Start it with: ollama serve"
                )
            raise RuntimeError(
                f"Connection refused to {self.base_url}. Is the server running?"
            )
        raise RuntimeError(f"Network error: {reason}")

    def list_models(self):
        """List available models. Only works for Ollama."""
        if self.provider != "ollama":
            return [self.model]

        url = f"{self.base_url}/api/tags"
        req = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
                models = data.get("models", [])
                return [m.get("name", "unknown") for m in models]
        except urllib.error.URLError:
            raise RuntimeError(
                "Ollama is not running. Start it with: ollama serve"
            )
        except (json.JSONDecodeError, KeyError):
            raise RuntimeError("Failed to parse Ollama model list.")

    # --- Convenience methods for log analysis ---

    def analyze_build_log(self, log_text, module_hint=None):
        """Analyze a build log and return AI interpretation."""
        context = f"Module being built: {module_hint}\n\n" if module_hint else ""
        prompt = (
            f"{context}Analyze this Android/AOSP build log and explain what went wrong:\n\n"
            f"```\n{log_text}\n```"
        )
        return self.chat(self._system_prompt, prompt)

    def analyze_logcat_batch(self, log_lines, focus=None):
        """Analyze a batch of logcat lines."""
        text = "\n".join(log_lines)
        focus_hint = f"Focus especially on issues related to: {focus}\n\n" if focus else ""
        prompt = f"{focus_hint}Analyze these Android logcat lines:\n\n```\n{text}\n```"
        return self.chat(self._system_prompt, prompt)

    def filter_noise(self, log_lines):
        """Filter noise from log lines. Returns dict with kept lines and stats."""
        text = "\n".join(log_lines)
        prompt = f"Filter these Android log lines:\n\n{text}"

        try:
            raw = self.chat(NOISE_FILTER_PROMPT, prompt, max_tokens=2000)
            # Strip any markdown fences
            clean = raw.strip()
            if clean.startswith("```"):
                clean = "\n".join(clean.split("\n")[1:])
            if clean.endswith("```"):
                clean = "\n".join(clean.split("\n")[:-1])
            return json.loads(clean.strip())
        except (json.JSONDecodeError, KeyError):
            return {"kept": log_lines, "filtered_count": 0, "patterns": []}

    # Error-type-specific extra context to guide the AI
    _ERROR_HINTS = {
        'NullPointerException': (
            'Focus on: which object reference was null, why it was not initialized, '
            'and whether it needs a null-check, lazy init, or lifecycle fix.'
        ),
        'ArithmeticException': (
            'Focus on: what division or modulo operation used a zero denominator, '
            'and how to guard against it (zero-check, default value).'
        ),
        'ClassNotFoundException': (
            'Focus on: missing class at runtime — check ProGuard/R8 keep rules, '
            'multidex config, or missing dependency in build.gradle.'
        ),
        'OutOfMemoryError': (
            'Focus on: memory leaks (static references, unregistered listeners, bitmap handling). '
            'Suggest using LeakCanary, inSampleSize for bitmaps, or increasing largeHeap.'
        ),
        'SecurityException': (
            'Focus on: which permission is missing. Check AndroidManifest.xml declarations '
            'and runtime permission requests for Android 6.0+.'
        ),
        'IllegalStateException': (
            'Focus on: lifecycle timing issues — fragment transactions after onSaveInstanceState, '
            'view access after onDestroyView, or state machine violations.'
        ),
        'ActivityNotFoundException': (
            'Focus on: missing activity declaration in AndroidManifest.xml, '
            'wrong intent action/category, or target app not installed.'
        ),
        'ClassCastException': (
            'Focus on: incorrect type cast — check generic types, view IDs returning '
            'wrong view types, or serialization/deserialization mismatches.'
        ),
        'StackOverflowError': (
            'Focus on: infinite recursion — find the recursive call chain '
            'and suggest a termination condition or iterative alternative.'
        ),
        'NetworkOnMainThreadException': (
            'Focus on: network call on UI thread. Move to a background thread '
            'using coroutines (viewModelScope.launch), AsyncTask, or RxJava.'
        ),
        'TransactionTooLargeException': (
            'Focus on: Bundle or Binder transaction exceeding 1MB limit. '
            'Reduce data passed between components, use ViewModel or database instead.'
        ),
        'DeadObjectException': (
            'Focus on: IPC to a dead process. The remote service or system process crashed. '
            'Suggest reconnection logic or checking process state.'
        ),
        'SQLiteException': (
            'Focus on: database schema mismatch, missing migration, or SQL syntax error. '
            'Check Room @Database version and migration paths.'
        ),
        'ANR': (
            'Focus on: Application Not Responding — main thread blocked for 5+ seconds. '
            'Look for disk I/O, network calls, or lock contention on the main thread. '
            'Suggest moving work to background threads.'
        ),
    }

    def explain_crash(self, crash_lines, exception_type='', source_snippet=None):
        """Analyze a complete crash block with error-type-specific guidance."""
        text = "\n".join(crash_lines)

        # Find matching error hint
        extra_hint = ''
        for err_key, hint in self._ERROR_HINTS.items():
            if err_key.lower() in exception_type.lower() or err_key.lower() in text.lower():
                extra_hint = f'\n\nERROR-SPECIFIC GUIDANCE: {hint}'
                break

        source_section = ''
        if source_snippet:
            source_section = (
                f"\n\nSOURCE CODE (from the developer's project):\n"
                f"```\n{source_snippet}\n```\n"
                f"Use this source code to suggest a precise inline fix. "
                f"Show a BEFORE/AFTER code snippet with the exact change needed.\n"
            )

        prompt = (
            f"A crash occurred in an Android app. Here is the full crash output:\n\n"
            f"```\n{text}\n```\n"
            f"{extra_hint}{source_section}\n\n"
            f"Provide a crash analysis with these exact sections:\n\n"
            f"🔍 Root Cause\n"
            f"1-2 sentences explaining exactly what went wrong and why.\n\n"
            f"🔧 How to Fix\n"
            f"Numbered steps with specific code changes. Include actual code snippets "
            f"where helpful (e.g., a null-check, try-catch, or guard clause).\n\n"
            f"💡 Tip\n"
            f"One-liner with extra context — common cause, prevention pattern, or related gotcha. "
            f"Skip this section if there's nothing useful to add.\n\n"
            f"Be specific: reference exact class, method, and line number from the stack trace. "
            f"Keep the total under 250 words."
        )
        max_tok = 700 if source_snippet else 500
        return self.chat(self._system_prompt, prompt, max_tokens=max_tok)

    def generate_fix(self, source_content, crash_line, crash_analysis, exception_type=''):
        """Generate a fixed version of a source file based on crash analysis.

        Returns the complete fixed file content as a string.
        """
        prompt = (
            f"A crash occurred at line {crash_line} of this file.\n\n"
            f"Exception: {exception_type}\n\n"
            f"Crash analysis:\n{crash_analysis}\n\n"
            f"Here is the FULL source file:\n"
            f"```\n{source_content}\n```\n\n"
            f"Return ONLY the complete fixed file content. "
            f"No explanation, no markdown fences, no commentary — just the code. "
            f"Make the minimal change needed to fix the crash."
        )
        # Scale max tokens to file size (rough: 1 token ≈ 4 chars), with a floor
        max_tok = max(1000, self._estimate_tokens(source_content) + 200)
        return self.chat(self._system_prompt, prompt, max_tokens=max_tok, timeout=60)

    def explain_line(self, line, context_lines=None):
        """Explain a single error/warning line with context."""
        ctx = ""
        if context_lines:
            ctx = "Context (surrounding lines):\n```\n" + "\n".join(context_lines) + "\n```\n\n"
        prompt = f"{ctx}Explain this Android log line briefly (2-3 sentences max):\n\n`{line}`"
        return self.chat(self._system_prompt, prompt, max_tokens=200)

    def summarize_session(self, errors, warnings, filtered_count):
        """Summarize an entire logcat or build session."""
        error_text = "\n".join(list(errors)[:30])
        warn_text = "\n".join(list(warnings)[:20])

        prompt = f"""Summarize this Android development session:

ERRORS ({len(errors)} total, showing up to 30):
```
{error_text}
```

WARNINGS ({len(warnings)} total, showing up to 20):
```
{warn_text}
```

Filtered noise lines: {filtered_count}

Give a session summary: what was the overall health, what were the main issues, priority order to fix them."""

        return self.chat(self._system_prompt, prompt, max_tokens=600)
