"""Unique id generation behind a protocol so tests get predictable ids."""

import itertools
import uuid
from typing import Protocol


class IdGenerator(Protocol):
    """Creates prefixed unique ids such as `evt_...`."""

    def new(self, prefix: str) -> str:
        """Return a new unique id starting with `prefix_`."""
        ...


class UuidIdGenerator:
    """Random ids. Example: `UuidIdGenerator().new("evt")` -> `"evt_3f9a1c2b7d4e"`."""

    def new(self, prefix: str) -> str:
        """Return `prefix_` plus 12 random hex characters."""
        return f"{prefix}_{uuid.uuid4().hex[:12]}"


class SequentialIdGenerator:
    """Deterministic ids for the fixtures runner. Example: `new("hint")` -> `"hint_001"`."""

    def __init__(self) -> None:
        self._counter = itertools.count(1)

    def new(self, prefix: str) -> str:
        """Return `prefix_` plus a zero-padded counter shared across prefixes."""
        return f"{prefix}_{next(self._counter):03d}"
