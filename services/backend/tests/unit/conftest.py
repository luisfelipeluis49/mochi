"""Lets the unit tests import the tools in the repo's scripts/ directory (latency_compare, ...)."""

import sys
from pathlib import Path

SCRIPTS = str(Path(__file__).resolve().parents[4] / "scripts")
if SCRIPTS not in sys.path:
    sys.path.append(SCRIPTS)
