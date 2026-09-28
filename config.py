"""Loads config.toml (settings), config.local.toml (own values, not in git) and .env (hosts, passwords)."""

import tomllib
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent

load_dotenv(ROOT / ".env")


def _merge(base, override):
    """Tables are merged key by key; everything else (values, lists) is replaced."""
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


with open(ROOT / "config.toml", "rb") as f:
    CONFIG = tomllib.load(f)

if (ROOT / "config.local.toml").exists():
    with open(ROOT / "config.local.toml", "rb") as f:
        _merge(CONFIG, tomllib.load(f))
