"""
Configuration manager for ailog.
Stores settings in ~/.config/ailog/config.json
"""

import os
import json
import shutil
import urllib.parse

DEFAULT_CONFIG = {
    "provider": "ollama",
    "ollama_url": "http://localhost:11434",
    "ollama_model": "qwen2.5-coder:3b",
    "openai_url": "https://api.openai.com/v1",
    "openai_api_key": "",
    "openai_model": "gpt-4o-mini",
    "anthropic_api_key": "",
    "anthropic_model": "claude-sonnet-4-20250514",
    "noise_level": "medium",
    "batch_interval": 5,
    "max_ai_calls": 5,
    "timeout": 30,
    "system_prompt": "",
}


class ConfigManager:
    def __init__(self):
        config_dir = os.path.expanduser("~/.config/ailog")
        os.makedirs(config_dir, mode=0o700, exist_ok=True)
        self.config_path = os.path.join(config_dir, "config.json")
        self._config = self._load()

    def _load(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path) as f:
                    data = json.load(f)
                    # Merge with defaults so new keys are always present
                    return {**DEFAULT_CONFIG, **data}
            except (json.JSONDecodeError, IOError):
                # Corrupted config — backup and recreate
                backup = self.config_path + ".bak"
                try:
                    shutil.copy2(self.config_path, backup)
                    # The corrupted config may still hold a recoverable API key,
                    # so lock the backup down too (copy2 preserves source perms).
                    os.chmod(backup, 0o600)
                except IOError:
                    pass
                return DEFAULT_CONFIG.copy()
        return DEFAULT_CONFIG.copy()

    def _save(self):
        # Write to a temp file created owner-only (0o600) from the start, then
        # atomically replace the real config. This avoids a window where the
        # file with a plaintext API key exists at the default (world-readable)
        # umask before a later chmod — and a crash can't leave a partial or
        # loose-permissioned config behind.
        tmp_path = self.config_path + ".tmp"
        try:
            fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                with os.fdopen(fd, 'w') as f:
                    json.dump(self._config, f, indent=2)
            except BaseException:
                os.unlink(tmp_path)
                raise
            os.replace(tmp_path, self.config_path)
        except PermissionError:
            raise RuntimeError(
                f"Permission denied writing to {self.config_path}. "
                f"Check directory permissions for ~/.config/ailog/"
            )

    def get(self, key, default=None):
        return self._config.get(key, default)

    def set(self, key, value):
        self._config[key] = value
        self._save()

    def reset(self):
        self._config = DEFAULT_CONFIG.copy()
        self._save()

    # --- Provider helpers ---

    @property
    def provider(self):
        return self._config.get("provider", "ollama")

    def set_provider(self, provider):
        if provider not in ("ollama", "openai", "anthropic"):
            raise ValueError(f"Unknown provider: {provider}. Choose: ollama, openai, anthropic")
        self._config["provider"] = provider
        self._save()

    def get_api_key(self):
        """Get API key for current provider. Env vars take priority."""
        provider = self.provider
        if provider == "ollama":
            return ""  # No key needed
        elif provider == "openai":
            return (os.environ.get("OPENAI_API_KEY")
                    or self._config.get("openai_api_key", ""))
        elif provider == "anthropic":
            return (os.environ.get("ANTHROPIC_API_KEY")
                    or self._config.get("anthropic_api_key", ""))
        return ""

    def set_api_key(self, key):
        """Set API key for current provider.

        Note: Keys are stored in plaintext in config.json (permissions 0600).
        Consider using environment variables (OPENAI_API_KEY, ANTHROPIC_API_KEY)
        for additional security.
        """
        provider = self.provider
        if provider == "ollama":
            # Accept it but warn — ollama doesn't need keys
            pass
        elif provider == "openai":
            self._config["openai_api_key"] = key
        elif provider == "anthropic":
            self._config["anthropic_api_key"] = key
        self._save()

    def get_model(self):
        """Get model for current provider."""
        provider = self.provider
        return self._config.get(f"{provider}_model",
                                DEFAULT_CONFIG.get(f"{provider}_model", ""))

    @staticmethod
    def _validate_model(model):
        """Validate a model name."""
        if not model or not model.strip():
            raise ValueError("Model name cannot be empty")

    @staticmethod
    def _validate_url(url):
        """Validate a URL."""
        if not url or not url.strip():
            raise ValueError("Invalid URL: URL cannot be empty")
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            raise ValueError("Invalid URL: must start with http:// or https://")
        if not parsed.hostname:
            raise ValueError("Invalid URL: missing hostname")

    @staticmethod
    def _validate_openai_url(url):
        """OpenAI base URL carries a Bearer API key, so require https off-localhost."""
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or ''
        if parsed.scheme != 'https' and host not in ('localhost', '127.0.0.1', '::1'):
            raise ValueError(
                "OpenAI base URL must use https:// (an http URL would send your API "
                "key in cleartext). http is only allowed for localhost."
            )

    def set_model(self, model):
        """Set model for current provider."""
        self._validate_model(model)
        provider = self.provider
        key = f"{provider}_model"
        self._config[key] = model
        self._save()

    def get_base_url(self):
        """Get base URL for current provider."""
        provider = self.provider
        if provider == "ollama":
            return self._config.get("ollama_url", "http://localhost:11434")
        elif provider == "openai":
            return self._config.get("openai_url", "https://api.openai.com/v1")
        elif provider == "anthropic":
            return "https://api.anthropic.com/v1"
        return ""

    def set_base_url(self, url):
        """Set base URL for current provider."""
        self._validate_url(url)
        provider = self.provider
        if provider == "ollama":
            self._config["ollama_url"] = url.rstrip("/")
        elif provider == "openai":
            self._validate_openai_url(url)
            self._config["openai_url"] = url.rstrip("/")
        elif provider == "anthropic":
            pass  # Anthropic URL is fixed
        self._save()

    # Keys settable via `ailog config --set key=value`, with a value coercer.
    _SETTABLE = {
        'provider': str, 'ollama_url': str, 'ollama_model': str,
        'openai_url': str, 'openai_model': str, 'anthropic_model': str,
        'noise_level': str, 'batch_interval': int, 'max_ai_calls': int,
        'timeout': int, 'system_prompt': str,
    }

    def set_option(self, key, value):
        """Set a config key from a raw string value, with validation/coercion.

        Backs `ailog config --set key=value`. Rejects unknown keys and bad values.
        (API keys are intentionally not settable this way — use --api-key.)
        """
        if key not in self._SETTABLE:
            raise ValueError(
                f"Unknown setting '{key}'. Settable keys: "
                f"{', '.join(sorted(self._SETTABLE))}"
            )
        caster = self._SETTABLE[key]
        try:
            coerced = caster(value)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid value for {key}: expected {caster.__name__}")

        if key == 'provider':
            self.set_provider(coerced)
            return
        if key == 'noise_level' and coerced not in ('low', 'medium', 'high'):
            raise ValueError("noise_level must be one of: low, medium, high")
        if key in ('batch_interval', 'max_ai_calls', 'timeout') and coerced < 1:
            raise ValueError(f"{key} must be >= 1")
        if key.endswith('_url'):
            self._validate_url(coerced)
            if key == 'openai_url':
                self._validate_openai_url(coerced)
            coerced = coerced.rstrip('/')
        self._config[key] = coerced
        self._save()

    def show(self, display):
        """Display current configuration."""
        display.section("ailog Configuration")
        display.info(f"Provider: {self.provider}")
        display.info(f"Model: {self.get_model()}")

        provider = self.provider
        if provider == "ollama":
            display.info(f"Ollama URL: {self.get_base_url()}")
            display.info("API Key: not required (local)")
        elif provider == "openai":
            display.info(f"Base URL: {self.get_base_url()}")
            key = self.get_api_key()
            if key:
                source = "from env" if os.environ.get("OPENAI_API_KEY") else "from config"
                masked = key[:8] + "..." + key[-4:] if len(key) > 12 else "***"
                display.info(f"API Key: {masked} ({source})")
            else:
                display.warning("API Key: NOT SET — run: ailog config --api-key YOUR_KEY")
        elif provider == "anthropic":
            key = self.get_api_key()
            if key:
                source = "from env" if os.environ.get("ANTHROPIC_API_KEY") else "from config"
                masked = key[:8] + "..." + key[-4:] if len(key) > 12 else "***"
                display.info(f"API Key: {masked} ({source})")
            else:
                display.warning("API Key: NOT SET — run: ailog config --api-key YOUR_KEY")

        display.info(f"Noise level: {self._config.get('noise_level', 'medium')}")
        display.info(f"AI batch interval: {self._config.get('batch_interval', 5)}s")
        display.info(f"Max AI calls: {self._config.get('max_ai_calls', 5)}")
        display.info(f"Config file: {self.config_path}")
