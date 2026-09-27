"""Loads config.toml (settings) and .env (hosts, passwords)."""

import tomllib
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent

load_dotenv(ROOT / ".env")

with open(ROOT / "config.toml", "rb") as f:
    CONFIG = tomllib.load(f)
