"""Mochi's own body: how loud its speaker is and how warm its processor runs."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

THERMAL = Path("/sys/class/thermal/thermal_zone0/temp")  # millidegrees Celsius


class Device:
    def __init__(self, audio_cfg: dict):
        """audio_cfg: the [audio] table. The mixer card is taken from device ("plughw:CARD=M1A,DEV=0")."""
        card = re.search(r"CARD=([^,]+)", audio_cfg["device"])
        self.card = audio_cfg.get("mixer_card") or (card.group(1) if card else "0")
        self.control = audio_cfg.get("mixer_control", "PCM")
        # never so quiet that "louder" can no longer be confirmed out loud
        self.min_volume = int(audio_cfg.get("min_volume", 20))

    def _amixer(self, *args: str) -> str:
        return subprocess.run(["amixer", "-c", self.card, *args], capture_output=True, text=True, timeout=5).stdout

    def volume(self) -> int | None:
        """Speaker level 0-100, or None when the mixer cannot be read."""
        m = re.search(r"\[(\d+)%\]", self._amixer("sget", self.control))
        return int(m.group(1)) if m else None

    def set_volume(self, percent: int) -> int | None:
        """Sets the speaker level (kept within min_volume..100) and returns what it now is."""
        percent = max(self.min_volume, min(100, int(percent)))
        self._amixer("sset", self.control, f"{percent}%", "unmute")
        return self.volume()

    def temperature(self) -> float | None:
        """Processor temperature in degrees Celsius."""
        try:
            return int(THERMAL.read_text()) / 1000
        except (OSError, ValueError):
            return None
