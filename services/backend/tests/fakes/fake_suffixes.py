"""Suffix sources for new user ids that tests control (no OS randomness)."""

import hashlib
import itertools


class SeededSuffixes:
    """Implements `SuffixSource` deterministically: a hash of the seed and a counter.

    Example: `SeededSuffixes(7).suffix()` is the same on every run.
    """

    def __init__(self, seed: int) -> None:
        self._seed = seed
        self._counter = itertools.count()

    def suffix(self) -> str:
        """Six lowercase hex characters, the same sequence for the same seed."""
        text = f"{self._seed}:{next(self._counter)}".encode()
        return hashlib.sha256(text).hexdigest()[:6]


class ScriptedSuffixes:
    """Implements `SuffixSource`: hands out the given suffixes in order, then repeats the last."""

    def __init__(self, *suffixes: str) -> None:
        self._waiting = list(suffixes)
        self.drawn = 0

    def suffix(self) -> str:
        """The next scripted suffix."""
        self.drawn += 1
        return self._waiting.pop(0) if len(self._waiting) > 1 else self._waiting[0]
