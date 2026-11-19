"""Keeping Mochi silent (AGENTS 9.2, 12.1): empty replies, or muting the speaker as a fallback."""

from datetime import datetime, timedelta
from typing import Literal

from mochi_backend.platform.clock import Clock

Strategy = Literal["empty_reply", "mute_speaker"]


class SilencePolicy:
    """Decides `speaker_muted` for the device state.

    `empty_reply`: never muted (an empty reply is expected to keep the agent quiet).
    `mute_speaker`: muted except while a SPEAK reply or host line is playing.
    """

    def __init__(
        self, strategy: Strategy, clock: Clock, base_seconds: float, seconds_per_word: float
    ) -> None:
        self._strategy = strategy
        self._clock = clock
        self._base = base_seconds
        self._per_word = seconds_per_word
        self._speaking_until: datetime | None = None

    def begin_speaking(self, text: str) -> None:
        """Open a speaking window: 0.6 s plus 0.45 s per word by default."""
        seconds = self._base + self._per_word * len(text.split())
        self._speaking_until = self._clock.now() + timedelta(seconds=seconds)

    def finished_speaking(self) -> None:
        """Close the window early (when Agora says the agent stopped speaking)."""
        self._speaking_until = None

    def speaker_muted(self) -> bool:
        """The `speaker_muted` value for the Pi bridge."""
        if self._strategy == "empty_reply":
            return False
        return not self._is_speaking()

    def _is_speaking(self) -> bool:
        return self._speaking_until is not None and self._clock.now() < self._speaking_until
