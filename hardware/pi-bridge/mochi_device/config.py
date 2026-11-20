"""Loads config/mochi.toml."""
import tomllib
from pathlib import Path

BRIDGE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = BRIDGE_DIR / "config" / "mochi.toml"


def load(path: Path = DEFAULT_CONFIG) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)
