import yaml
import os
from pathlib import Path
from typing import Dict, Any


def _find_project_root() -> Path:
    """Find project root by looking for pyproject.toml or config directory."""
    # Try from current file location
    current = Path(__file__).resolve().parent
    
    # Walk up to find project root
    for _ in range(5):
        if (current / "pyproject.toml").exists() or (current / "config").exists():
            return current
        current = current.parent
    
    # Fallback to cwd
    return Path.cwd()


def load_env(env_path: str = None) -> None:
    """
    Load environment variables from .env file.
    Does NOT log or expose secrets.
    """
    if env_path:
        path = Path(env_path)
    else:
        # Find .env in project root
        project_root = _find_project_root()
        path = project_root / ".env"
    
    if not path.exists():
        return
    
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()


def load_config(config_path: str = "config/settings.yaml") -> Dict[str, Any]:
    """
    Load configuration from YAML file and merge with environment variables.
    Environment variables take precedence for sensitive data.
    """
    # Load .env first
    load_env()
    
    # Resolve config path relative to project root
    path = Path(config_path)
    if not path.is_absolute():
        project_root = _find_project_root()
        path = project_root / config_path
    
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found at: {path.absolute()}")
    
    with open(path, "r", encoding="utf-8") as f:
        try:
            config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Error parsing YAML configuration: {e}") from e
    
    # Inject Tradier credentials from environment (DO NOT log these)
    tradier_token = os.environ.get("TRADIER_TOKEN", "")
    tradier_base = os.environ.get("TRADIER_BASE", "https://api.tradier.com/v1")
    
    if "providers" not in config:
        config["providers"] = {}
    if "tradier" not in config["providers"]:
        config["providers"]["tradier"] = {}
    
    # Override with env values if present
    if tradier_token:
        config["providers"]["tradier"]["api_token"] = tradier_token
    if tradier_base:
        config["providers"]["tradier"]["base_url"] = tradier_base
    
    return config
