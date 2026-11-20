"""Loads config/mochi.toml, and this device's own choices on top of it."""
import tomllib
from pathlib import Path

BRIDGE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = BRIDGE_DIR / "config" / "mochi.toml"
LOCAL_CONFIG = BRIDGE_DIR / "config" / "mochi.local.toml"  # not in git


def load(path: Path = DEFAULT_CONFIG) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def load_with_local(path: Path = DEFAULT_CONFIG, local: Path = LOCAL_CONFIG) -> dict:
    """What the device runs with: `path`, then the keys in config/mochi.local.toml over it.

    The local file holds only what differs on this one device, in the same tables, for example
        [backend]
        kind = "mochi_backend"
    """
    cfg = load(path)
    if local.exists():
        for table, values in load(local).items():
            cfg.setdefault(table, {}).update(values)
    return cfg
