"""
Configuration settings loader for Victor Trading System.
Loads settings from YAML config file and environment variables.
"""
import os
import re
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent

# Config file paths
CONFIG_DIR = PROJECT_ROOT / "config"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
CONFIG_EXAMPLE_FILE = CONFIG_DIR / "config.example.yaml"
KEYWORDS_MAPPING_FILE = CONFIG_DIR / "keywords_mapping.yaml"


def _resolve_env_vars(value: Any) -> Any:
    """Resolve environment variables in config values."""
    if isinstance(value, str):
        # Match ${VAR_NAME} pattern
        pattern = r"\$\{([^}]+)\}"
        matches = re.findall(pattern, value)
        for var_name in matches:
            env_value = os.getenv(var_name, "")
            value = value.replace(f"${{{var_name}}}", env_value)
        return value
    elif isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_env_vars(item) for item in value]
    return value


def load_config(config_path: Optional[Path] = None) -> dict:
    """Load configuration from YAML file with environment variable resolution."""
    if config_path is None:
        config_path = CONFIG_FILE

    if not config_path.exists():
        # Fall back to example config
        config_path = CONFIG_EXAMPLE_FILE
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Resolve environment variables
    config = _resolve_env_vars(config)

    return config


def load_keywords_mapping(mapping_path: Optional[Path] = None) -> dict:
    """Load keyword-stock mapping from YAML file."""
    if mapping_path is None:
        mapping_path = KEYWORDS_MAPPING_FILE

    if not mapping_path.exists():
        return {"stocks": [], "industries": {}, "sentiment_keywords": {}}

    with open(mapping_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class Settings:
    """Application settings singleton."""

    _instance: Optional["Settings"] = None
    _config: dict = {}

    def __new__(cls) -> "Settings":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self) -> None:
        """Load configuration."""
        self._config = load_config()

    def reload(self) -> None:
        """Reload configuration."""
        self._load()

    @property
    def config(self) -> dict:
        """Get full configuration."""
        return self._config

    # Convenience properties
    @property
    def app_name(self) -> str:
        return self._config.get("app", {}).get("name", "victor-trading")

    @property
    def env(self) -> str:
        return self._config.get("app", {}).get("env", "development")

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def log_level(self) -> str:
        return self._config.get("app", {}).get("log_level", "INFO")

    @property
    def kis_config(self) -> dict:
        return self._config.get("kis", {})

    @property
    def news_config(self) -> dict:
        return self._config.get("news", {})

    @property
    def analysis_config(self) -> dict:
        return self._config.get("analysis", {})

    @property
    def trading_config(self) -> dict:
        return self._config.get("trading", {})

    @property
    def slack_config(self) -> dict:
        return self._config.get("slack", {})

    @property
    def scheduler_config(self) -> dict:
        return self._config.get("scheduler", {})

    @property
    def data_paths(self) -> dict:
        return self._config.get("data", {})


# Global settings instance
settings = Settings()
