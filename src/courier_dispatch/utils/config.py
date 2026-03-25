"""Shared configuration management for Courier Dispatch."""

import tomllib
from pathlib import Path

import tomli_w

CONFIG_PATH = Path.home() / ".config" / "dispatch" / "config.toml"


def load_config() -> dict:
    """Load the user config from ~/.config/dispatch/config.toml."""
    if not CONFIG_PATH.is_file():
        return {}
    try:
        with open(CONFIG_PATH, "rb") as f:
            return tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError):
        return {}


def save_config(data: dict) -> None:
    """Write config dict to ~/.config/dispatch/config.toml."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "wb") as f:
        tomli_w.dump(data, f)


def get_config_value(key: str) -> str | None:
    """Get a config value by dot-notation key (e.g., 'ngrok.authtoken')."""
    data = load_config()
    parts = key.split(".")
    for part in parts:
        if not isinstance(data, dict):
            return None
        data = data.get(part)
        if data is None:
            return None
    return data if isinstance(data, str) else str(data)


def set_config_value(key: str, value: str) -> None:
    """Set a config value by dot-notation key and save."""
    data = load_config()
    parts = key.split(".")
    target = data
    for part in parts[:-1]:
        if part not in target or not isinstance(target[part], dict):
            target[part] = {}
        target = target[part]
    target[parts[-1]] = value
    save_config(data)


def load_project_config(project_root: Path) -> dict:
    """Load config from project dispatch.toml or user config, merged.

    Project config takes precedence. Returns the [runner] section
    with defaults applied.
    """
    config = {
        "extra_allowed": [],
        "extra_denied": [],
        "timeout": 120,
    }

    paths = [
        project_root / "dispatch.toml",
        CONFIG_PATH,
    ]

    for config_path in paths:
        if config_path.is_file():
            try:
                with open(config_path, "rb") as f:
                    data = tomllib.load(f)
                runner = data.get("runner", {})
                config["extra_allowed"] = runner.get("extra_allowed", [])
                config["extra_denied"] = runner.get("extra_denied", [])
                config["timeout"] = runner.get("timeout", 120)
                break
            except (tomllib.TOMLDecodeError, OSError):
                pass

    return config
