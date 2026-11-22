"""Is someone talking over Mochi? Heard on the Pi itself, while Mochi's own voice is playing.

While Mochi speaks, what the microphone hears is not sent on (Mochi's own voice comes back in it,
and the speech recogniser would write that down as a sentence: docs/DECISIONS.md D-35). So nobody
upstream can notice a person starting to talk, and Mochi talked on over them. This notices it
here, by loudness: the M1A takes most of its own speaker out of its microphone, so Mochi's voice
comes back at about the level of the room, and a person at the table is a good deal louder.

    watch = LevelWatch()
    watch.begin()                       # Mochi starts to speak
    if watch.heard(frame, voiced): ...  # every 20 ms frame while it speaks; True once: stop Mochi

The level of Mochi's own voice in the microphone is learned as it speaks (and remembered from one
stretch of speech to the next), so nothing has to be measured by hand; `ratio` says how much louder
than that a person has to be.
"""
from __future__ import annotations

from collections import deque

import numpy as np


def loudness(frame: bytes) -> float:
    """RMS of a 16-bit mono frame (0 for an empty one)."""
    samples = np.frombuffer(frame, np.int16)
    return float(np.sqrt(np.mean(samples.astype(np.float32) ** 2))) if len(samples) else 0.0


class LevelWatch:
    def __init__(self, ratio: float = 3.5, floor: float = 300.0, need_ms: int = 240, span_ms: int = 400,
                 learn_ms: int = 300, frame_ms: int = 20):
        """ratio: how many times louder than Mochi's own voice in the microphone a person must be.
        floor: and at least this loud (RMS, 16-bit scale): a quiet room has no echo to compare with.
        need_ms of the last span_ms must be that loud: a cough or a door is shorter than a word.
        learn_ms: at the very start of Mochi's first speech its level is not known yet: only listen."""
        self.ratio, self.floor = ratio, floor
        self.need, self.span = max(1, need_ms // frame_ms), max(1, span_ms // frame_ms)
        self.learn = max(1, learn_ms // frame_ms)
        self.echo: float | None = None   # Mochi's own voice in the microphone, as learned so far
        self.begin()

    def begin(self) -> None:
        """Mochi starts a stretch of speech (the learned level is kept)."""
        self.recent: deque[bool] = deque(maxlen=self.span)
        self.seen = 0
        self.fired = False

    def heard(self, frame: bytes, voiced: bool = True) -> bool:
        """One microphone frame while Mochi speaks. True exactly once per stretch: someone is
        talking over it. voiced: the voice detector heard a voice lately (not just a noise)."""
        level = loudness(frame)
        self.seen += 1
        if self.echo is None:  # nothing learned yet: the first frames are taken to be Mochi alone
            self._learn(level, fast=True)
            if self.seen >= self.learn:
                self.echo = self._first
            return False
        loud = level > max(self.ratio * self.echo, self.floor)
        if not loud:
            self._learn(level)
        self.recent.append(loud and voiced)
        if self.fired or sum(self.recent) < self.need:
            return False
        self.fired = True
        return True

    def _learn(self, level: float, fast: bool = False) -> None:
        if fast:
            self._first = max(getattr(self, "_first", 0.0), level)  # the loudest of the first frames
            return
        self.echo += 0.05 * (level - self.echo)  # follows Mochi's voice getting louder or softer
