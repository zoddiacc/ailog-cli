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
        os.makedirs(config_dir, exist_ok=True)
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
                except IOError:
                    pass
                return DEFAULT_CONFIG.copy()
        return DEFAULT_CONFIG.copy()

    def _save(self):
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self._config, f, indent=2)
            # Restrict file permissions to owner-only (0o600) since config may
            # contain API keys in plaintext.
            os.chmod(self.config_path, 0o600)
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
        self._plaintext_warning = True

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
            self._config["openai_url"] = url.rstrip("/")
        elif provider == "anthropic":
            pass  # Anthropic URL is fixed
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
